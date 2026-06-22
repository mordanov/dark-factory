import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { TicketResponse, TicketStatus, TransitionBlockedError } from "@/types";
import { WORKFLOW_TRANSITIONS } from "@/types";
import { transitionTicket, submitProgress } from "@/api/tickets";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";

function isTransitionBlockedError(v: unknown): v is TransitionBlockedError {
  return typeof v === "object" && v !== null && "missing_updates" in v;
}

interface StatusTransitionButtonProps {
  ticket: TicketResponse;
  onTransitioned: (updated: TicketResponse) => void;
}

export function StatusTransitionButton({ ticket, onTransitioned }: StatusTransitionButtonProps) {
  const { t } = useTranslation();
  const currentUser = useAuthStore((s) => s.currentUser);
  const nextStatuses = WORKFLOW_TRANSITIONS[ticket.status] ?? [];
  const [blocked, setBlocked] = useState<TransitionBlockedError | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [loading, setLoading] = useState<TicketStatus | null>(null);
  const [pendingToStatus, setPendingToStatus] = useState<TicketStatus | null>(null);
  const [updateText, setUpdateText] = useState("");
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [updateLoading, setUpdateLoading] = useState(false);

  if (nextStatuses.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("tickets.detail.noTransitions")}</p>;
  }

  async function handleTransition(toStatus: TicketStatus) {
    setBlocked(null);
    setApiError(null);
    setLoading(toStatus);
    try {
      const result = await transitionTicket(ticket.id, toStatus);
      if (isTransitionBlockedError(result)) {
        const currentUserBlocking = currentUser
          ? result.missing_updates.some((u) => u.user_id === currentUser.id)
          : false;
        if (currentUserBlocking) {
          setPendingToStatus(toStatus);
        } else {
          setBlocked(result);
        }
      } else {
        const announcer = document.getElementById("status-announcer");
        if (announcer) announcer.textContent = t("tickets.detail.transitionSuccess", { status: t(`tickets.status.${toStatus}`) });
        onTransitioned(result);
      }
    } catch (err: unknown) {
      if (typeof err === "object" && err !== null && "response" in err) {
        const e = err as { response: { status: number; data?: { detail?: string } } };
        if (e.response.status === 409) { setApiError(t("tickets.detail.invalidTransition")); return; }
        if (e.response.status === 403) { setApiError(t("tickets.detail.notAssignedError")); return; }
        if (e.response.data?.detail) { setApiError(e.response.data.detail); return; }
      }
      setApiError(t("tickets.detail.transitionError"));
      const announcer = document.getElementById("status-announcer");
      if (announcer) announcer.textContent = t("tickets.detail.transitionError");
    } finally {
      setLoading(null);
    }
  }

  async function handleSubmitUpdate() {
    if (!updateText.trim()) { setUpdateError(t("tickets.progress.required")); return; }
    if (!pendingToStatus) return;
    setUpdateError(null);
    setUpdateLoading(true);
    try {
      await submitProgress(ticket.id, updateText.trim());
    } catch {
      setUpdateError(t("tickets.progress.failed"));
      setUpdateLoading(false);
      return;
    }
    try {
      const result = await transitionTicket(ticket.id, pendingToStatus);
      if (isTransitionBlockedError(result)) {
        setBlocked(result);
      } else {
        onTransitioned(result);
      }
      setPendingToStatus(null);
      setUpdateText("");
    } catch (err: unknown) {
      if (typeof err === "object" && err !== null && "response" in err) {
        const e = err as { response: { status: number; data?: { detail?: string } } };
        if (e.response.data?.detail) { setApiError(e.response.data.detail); }
        else { setApiError(t("tickets.detail.transitionError")); }
      } else {
        setApiError(t("tickets.detail.transitionError"));
      }
      setPendingToStatus(null);
      setUpdateText("");
    } finally {
      setUpdateLoading(false);
    }
  }

  function handleCancelUpdate() {
    setPendingToStatus(null);
    setUpdateText("");
    setUpdateError(null);
  }

  return (
    <div>
      <div className="flex gap-2 flex-wrap">
        {nextStatuses.map((s) => (
          <Button
            key={s}
            onClick={() => handleTransition(s)}
            disabled={loading !== null}
            size="default"
            className="w-full sm:w-auto"
            aria-label={`Move to ${t(`tickets.status.${s}`)}`}
          >
            {loading === s
              ? t("tickets.detail.movingTo")
              : t("tickets.detail.moveTo", { status: t(`tickets.status.${s}`) })}
          </Button>
        ))}
      </div>

      {apiError && <p role="alert" className="mt-2 text-sm text-destructive">{apiError}</p>}

      {blocked && (
        <div role="alert" className="mt-3 p-3 bg-destructive/10 border border-destructive/20 rounded-md">
          <p className="font-semibold text-destructive text-sm mb-1">{blocked.detail}</p>
          <p className="text-sm mb-1">{t("tickets.detail.transitionBlocked")}</p>
          <ul className="text-sm list-disc pl-5">
            {blocked.missing_updates.map((u) => (
              <li key={u.user_id}>{u.email}</li>
            ))}
          </ul>
        </div>
      )}

      <Dialog
        open={!!pendingToStatus}
        onOpenChange={(open) => !open && handleCancelUpdate()}
      >
        <DialogContent className="w-full max-w-[95vw] sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("tickets.progress.submitUpdate")}</DialogTitle>
            <DialogDescription>{t("tickets.detail.updateRequiredForTransition")}</DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <Textarea
              value={updateText}
              onChange={(e) => setUpdateText(e.target.value)}
              placeholder={t("tickets.progress.placeholder")}
              rows={4}
              disabled={updateLoading}
              className="resize-y"
            />
            {updateError && (
              <p role="alert" className="text-sm text-destructive mt-1">{updateError}</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={handleCancelUpdate} disabled={updateLoading}>
              {t("common.cancel")}
            </Button>
            <Button onClick={handleSubmitUpdate} disabled={updateLoading}>
              {updateLoading ? t("tickets.progress.submitting") : t("tickets.progress.submit")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
