"""OrchestratorService — coordinates FSM, LLM, TM client, Document Store, Audit.

This is the heart of the Orchestrator.  It handles one job at a time,
but the worker pool runs many instances concurrently (asyncio.Semaphore).
"""
from __future__ import annotations
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.audit_repo import AuditRepository
from src.repositories.job_repo import JobRepository
from src.schemas.schemas import TmTicket
from src.services.distiller.distiller import distill
from src.services.document_store.store import DocumentStore
from src.services.fsm import engine as fsm
from src.services.llm.orchestrator_llm import call_orchestrator_llm
from src.services.tm_client.client import TicketManagerClient

logger = logging.getLogger(__name__)


class OrchestratorService:
    def __init__(
        self,
        db: AsyncSession,
        tm: TicketManagerClient,
        doc_store: DocumentStore,
    ) -> None:
        self._db = db
        self._tm = tm
        self._doc_store = doc_store
        self._job_repo = JobRepository(db)
        self._audit_repo = AuditRepository(db)

    async def process_job(self, job_id: uuid.UUID) -> dict:
        """
        Full lifecycle for one orchestration job:
          1. Mark job as running
          2. Fetch fresh ticket from TM
          3. Run pure FSM evaluation
          4. Resolve dependencies
          5. Fetch project memory + ADRs
          6. Call LLM orchestrator
          7. Apply decision: update TM FSM, save ADR, trigger distiller
          8. Write audit log entry
          9. Mark job done/failed
        """
        await self._job_repo.mark_running(job_id)
        await self._db.commit()

        job = await self._job_repo.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        ticket_id = job.ticket_id
        project_id = job.project_id

        try:
            result = await self._run(job_id, ticket_id, project_id)
            await self._job_repo.mark_done(job_id, result)
            await self._db.commit()
            return result
        except Exception as exc:
            logger.error("Job %s failed: %s", job_id, exc)
            await self._job_repo.mark_failed(job_id, str(exc))
            await self._audit_repo.append(
                ticket_id=ticket_id,
                project_id=project_id,
                action="ERROR",
                details=f"Job failed: {exc}",
                job_id=job_id,
            )
            await self._db.commit()
            raise

    async def _run(self, job_id: uuid.UUID, ticket_id: str, project_id: str) -> dict:
        # 1. Fetch fresh ticket
        ticket_raw = await self._tm.get_ticket_full(project_id, ticket_id)
        ticket = TmTicket(**ticket_raw)

        # 2. Resolve dependencies
        dep_statuses: dict[str, str] = {}
        if ticket.dependencies:
            batch = await self._tm.get_fsm_status_batch(ticket.dependencies)
            dep_statuses = {tid: info.get("fsm_status", "unknown") for tid, info in batch.items()}

        # 3. Pure FSM evaluation
        fsm_eval = fsm.evaluate(ticket, dep_statuses)

        # 4. Short-circuit on WAIT with no LLM needed (dep or needs-estimation)
        if fsm_eval.action == "WAIT" and not fsm_eval.gates_to_evaluate:
            await self._apply_wait(ticket, project_id, fsm_eval, job_id, dep_statuses)
            return {"action": "WAIT", "ticket_id": ticket_id, "reason": fsm_eval.blocked_reason}

        # 5. Fetch project memory + ADRs for LLM context
        memory = await self._doc_store.get_memory(project_id)
        adrs = await self._doc_store.list_adrs(project_id, status_filter="accepted")

        # 6. Call LLM orchestrator
        decision = await call_orchestrator_llm(ticket, fsm_eval, memory, adrs, dep_statuses)

        # 7. Apply decision
        await self._apply_decision(ticket, project_id, decision, job_id)

        return {
            "action": decision.decision.action,
            "ticket_id": ticket_id,
            "to_state": decision.decision.to_state,
            "assigned_agent": decision.decision.assigned_agent,
            "errors": decision.errors,
        }

    async def _apply_wait(self, ticket: TmTicket, project_id: str, fsm_eval, job_id, dep_statuses):
        await self._tm.update_fsm(
            project_id,
            ticket.id,
            fsm_status=fsm_eval.from_state,
            blocked_reason=fsm_eval.blocked_reason,
            assigned_agent=fsm_eval.assigned_agent,
        )
        await self._audit_repo.append(
            ticket_id=ticket.id,
            project_id=project_id,
            action="WAIT",
            from_state=fsm_eval.from_state,
            blocked_reason=fsm_eval.blocked_reason,
            assigned_agent=fsm_eval.assigned_agent,
            details=fsm_eval.blocked_reason or "Waiting",
            job_id=job_id,
        )

    async def _apply_decision(self, ticket: TmTicket, project_id: str, decision, job_id):
        dec = decision.decision
        action = dec.action

        # Update FSM state in TM
        fsm_kwargs: dict = {
            "assigned_agent": dec.assigned_agent,
        }

        if action == "ADVANCE":
            fsm_kwargs["fsm_status"] = dec.to_state
            fsm_kwargs["blocked_reason"] = None
        elif action in ("BLOCK", "WAIT"):
            fsm_kwargs["fsm_status"] = "BLOCKED" if action == "BLOCK" else ticket.fsm_status
            fsm_kwargs["blocked_reason"] = dec.blocked_reason
        elif action == "OVERRIDE_ACCEPTED":
            fsm_kwargs["fsm_status"] = dec.to_state
            fsm_kwargs["blocked_reason"] = None

        # Clear override flag after processing
        if ticket.override:
            fsm_kwargs["clear_override"] = True  # type: ignore[assignment]

        if decision.errors:
            fsm_kwargs["orchestrator_errors"] = decision.errors

        await self._tm.update_fsm(project_id, ticket.id, **fsm_kwargs)

        # Save ADR if generated
        if action == "GENERATE_ADR" and decision.adr:
            adr_id = await self._doc_store.save_adr(project_id, decision.adr, ticket.id)
            logger.info("Saved ADR %s for ticket %s", adr_id, ticket.id)

        # Trigger ContextDistiller if ticket moved to done
        if decision.context_distiller_trigger:
            await self._trigger_distiller(ticket, project_id, job_id)

        # Write audit entry
        audit_entry = decision.audit_entry
        await self._audit_repo.append(
            ticket_id=ticket.id,
            project_id=project_id,
            action=dec.action,
            from_state=dec.from_state,
            to_state=dec.to_state,
            assigned_agent=dec.assigned_agent,
            blocked_reason=dec.blocked_reason,
            override_logged=dec.override_logged,
            details=audit_entry.get("details", ""),
            job_id=job_id,
            decision_payload=decision.model_dump(),
        )

    async def _trigger_distiller(self, ticket: TmTicket, project_id: str, parent_job_id: uuid.UUID):
        """Enqueue a distill job — lightweight, no LLM call here."""
        job_repo = JobRepository(self._db)
        audit_entries, _ = await self._audit_repo.list_for_ticket(ticket.id)
        audit_trail = [
            {"action": e.action, "details": e.details, "created_at": str(e.created_at)}
            for e in audit_entries
        ]
        await job_repo.create(
            job_type="distill",
            ticket_id=ticket.id,
            project_id=project_id,
            triggered_by="orchestrator",
            payload={"audit_trail": audit_trail},
        )


class DistillerService:
    """Handles distill jobs — separate from orchestration jobs."""

    def __init__(self, db: AsyncSession, doc_store: DocumentStore) -> None:
        self._db = db
        self._doc_store = doc_store
        self._job_repo = JobRepository(db)
        self._audit_repo = AuditRepository(db)

    async def process_job(self, job_id: uuid.UUID) -> dict:
        await self._job_repo.mark_running(job_id)
        await self._db.commit()

        job = await self._job_repo.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        try:
            memory = await self._doc_store.get_memory(job.project_id)
            current_content = memory.content if memory else None
            audit_trail = job.payload.get("audit_trail", [])
            ticket_raw = job.payload.get("ticket", {})
            ticket = TmTicket(**ticket_raw) if ticket_raw else TmTicket(
                id=job.ticket_id, project_id=job.project_id,
                title="", description="",
            )

            new_memory = await distill(ticket, audit_trail, current_content)
            await self._doc_store.save_memory(job.project_id, new_memory, job.ticket_id)

            result = {"distilled": True, "project_id": job.project_id}
            await self._job_repo.mark_done(job_id, result)
            await self._db.commit()
            return result
        except Exception as exc:
            await self._job_repo.mark_failed(job_id, str(exc))
            await self._db.commit()
            raise
