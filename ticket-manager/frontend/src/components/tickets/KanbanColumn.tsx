import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import type { TicketResponse, TicketStatus, TransitionBlockedError } from "@/types";
import { WORKFLOW_TRANSITIONS } from "@/types";
import { transitionTicket } from "@/api/tickets";
import { KanbanCard } from "@/components/tickets/KanbanCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface Props {
  status: TicketStatus;
  label: string;
  color: string;
  tickets: TicketResponse[];
  projectId: string;
}

export function KanbanColumn({ status, label, color, tickets, projectId }: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [isDragOver, setIsDragOver] = useState(false);
  const [error, setError] = useState<TransitionBlockedError | string | null>(null);
  const [loading, setLoading] = useState(false);

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setIsDragOver(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragOver(false);
    }
  }

  async function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragOver(false);
    setError(null);
    const ticketId = e.dataTransfer.getData("ticketId");
    const fromStatus = e.dataTransfer.getData("fromStatus") as TicketStatus;
    if (!ticketId || fromStatus === status) return;
    const allowed = WORKFLOW_TRANSITIONS[fromStatus] ?? [];
    if (!allowed.includes(status)) {
      setError(`Tickets cannot move directly from ${fromStatus.replace("_", " ")} to ${label}.`);
      return;
    }
    setLoading(true);
    try {
      const result = await transitionTicket(ticketId, status);
      if ("missing_updates" in result) {
        setError(result as TransitionBlockedError);
      } else {
        await queryClient.invalidateQueries({ queryKey: ["tickets", projectId] });
      }
    } catch {
      setError(t("tickets.detail.transitionError"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 min-w-[280px] w-72">
      <div className="flex items-center justify-between px-1 mb-1">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color }} /> {/* swatch-color-required */}
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{label}</h3>
        </div>
        <Badge variant="secondary" className="text-xs">{tickets.length}</Badge>
      </div>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "flex flex-col gap-2 min-h-[240px] rounded-lg p-2 transition-colors duration-100",
          isDragOver ? "bg-accent border-2 border-dashed border-primary" : "bg-muted/30 border-2 border-transparent",
          loading && "opacity-60"
        )}
      >
        {tickets.map((ticket) => (
          <KanbanCard key={ticket.id} ticket={ticket} />
        ))}
        {tickets.length === 0 && (
          <p className="text-center text-muted-foreground text-xs mt-6 pointer-events-none">
            {t("tickets.dropHere")}
          </p>
        )}
      </div>

      {error !== null && (
        <div className="p-2 bg-destructive/10 border border-destructive/20 rounded text-xs text-destructive">
          {typeof error === "string" ? (
            error
          ) : (
            <>
              <strong>Progress updates required before this transition:</strong>
              <ul className="mt-1 pl-4 list-disc">
                {error.missing_updates.map((u) => (
                  <li key={u.user_id}>{u.email}</li>
                ))}
              </ul>
            </>
          )}
          <Button variant="ghost" size="sm" className="mt-1 h-6 text-xs p-0 text-destructive" onClick={() => setError(null)}>
            Dismiss
          </Button>
        </div>
      )}
    </div>
  );
}
