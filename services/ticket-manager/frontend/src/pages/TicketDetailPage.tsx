import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getTicket, listProgress, listTicketEvents, submitProgress,
  deleteTicket, updateTicket, createFollowUp, assignUser, unassignUser, addTag, removeTag,
  incrementTokensSpent,
} from "@/api/tickets";
import { AssigneeProgressList } from "@/components/tickets/AssigneeProgressList";
import { StatusTransitionButton } from "@/components/tickets/StatusTransitionButton";
import { TicketEventHistory } from "@/components/tickets/TicketEventHistory";
import { TicketForm, type TicketFormValues } from "@/components/tickets/TicketForm";
import { TagInput } from "@/components/tickets/TagInput";
import { AdminAssignModal } from "@/components/tickets/AdminAssignModal";
import type { TicketResponse } from "@/types";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "DONE") return "default";
  if (status === "CLOSED") return "outline";
  return "secondary";
}

export function TicketDetailPage() {
  const { t } = useTranslation();
  const { ticketId } = useParams<{ ticketId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((s) => s.currentUser);

  const [isEditing, setIsEditing] = useState(false);
  const [showFollowUpForm, setShowFollowUpForm] = useState(false);
  const [progressInput, setProgressInput] = useState("");
  const [progressError, setProgressError] = useState<string | null>(null);
  const [progressLoading, setProgressLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [assignError, setAssignError] = useState<string | null>(null);
  const [tagError, setTagError] = useState<string | null>(null);
  const [pendingTags, setPendingTags] = useState<string[] | null>(null);
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [tokensAmount, setTokensAmount] = useState("100");
  const [tokensLoading, setTokensLoading] = useState(false);
  const [tokensError, setTokensError] = useState<string | null>(null);

  const { data: ticket, isLoading, isError } = useQuery({
    queryKey: ["ticket", ticketId],
    queryFn: () => getTicket(ticketId!),
    enabled: !!ticketId,
  });

  const { data: progressData } = useQuery({
    queryKey: ["ticket-progress", ticketId],
    queryFn: () => listProgress(ticketId!),
    enabled: !!ticketId,
  });

  const { data: eventsData } = useQuery({
    queryKey: ["ticket-events", ticketId],
    queryFn: () => listTicketEvents(ticketId!),
    enabled: !!ticketId,
  });

  function handleTransitioned(updated: TicketResponse) {
    queryClient.setQueryData(["ticket", ticketId], updated);
    queryClient.invalidateQueries({ queryKey: ["ticket-events", ticketId] });
  }

  async function handleEdit(values: TicketFormValues) {
    const updated = await updateTicket(ticketId!, {
      title: values.title, description: values.description,
      ticket_type: values.ticket_type, ticket_spec: values.ticket_spec ?? undefined,
      urgent: values.urgent, blocker: values.blocker, bugfix: values.bugfix,
    });
    queryClient.setQueryData(["ticket", ticketId], updated);
    queryClient.invalidateQueries({ queryKey: ["ticket-events", ticketId] });
    setIsEditing(false);
  }

  async function handleDelete() {
    if (!window.confirm(t("tickets.detail.deleteConfirm"))) return;
    setDeleteError(null);
    try {
      await deleteTicket(ticketId!);
      navigate(ticket ? `/projects/${ticket.project_id}` : "/projects", { replace: true });
    } catch (err: unknown) {
      if (typeof err === "object" && err !== null && "response" in err) {
        const e = err as { response: { status: number; data?: { detail?: string } } };
        if (e.response.status === 409) { setDeleteError(t("tickets.detail.deleteConflict")); return; }
      }
      setDeleteError(t("tickets.detail.deleteError"));
    }
  }

  async function handleSubmitProgress() {
    if (!progressInput.trim()) { setProgressError(t("tickets.progress.required")); return; }
    setProgressError(null);
    setProgressLoading(true);
    try {
      await submitProgress(ticketId!, progressInput.trim());
      await queryClient.invalidateQueries({ queryKey: ["ticket-progress", ticketId] });
      await queryClient.invalidateQueries({ queryKey: ["ticket-events", ticketId] });
      setProgressInput("");
    } catch {
      setProgressError(t("tickets.progress.failed"));
    } finally {
      setProgressLoading(false);
    }
  }

  async function handleCreateFollowUp(values: TicketFormValues) {
    const created = await createFollowUp(ticketId!, {
      title: values.title, description: values.description,
      ticket_type: values.ticket_type, ticket_spec: values.ticket_spec!,
      urgent: values.urgent, blocker: values.blocker, bugfix: values.bugfix, tags: values.tags,
    });
    setShowFollowUpForm(false);
    navigate(`/tickets/${created.id}`);
  }

  async function handleAssignMe() {
    setAssignError(null);
    try {
      await assignUser(ticketId!, currentUser!.id);
      await queryClient.invalidateQueries({ queryKey: ["ticket", ticketId] });
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setAssignError(e.response?.data?.detail ?? t("tickets.assign.failed"));
    }
  }

  async function handleUnassign(userId: string) {
    setAssignError(null);
    try {
      await unassignUser(ticketId!, userId);
      await queryClient.invalidateQueries({ queryKey: ["ticket", ticketId] });
    } catch {
      setAssignError(t("tickets.assign.removeFailed"));
    }
  }

  async function handleTagChange(newTags: string[]) {
    if (!ticket) return;
    setTagError(null);
    const currentNames = ticket.tags.map((tg) => tg.name);
    const added = newTags.filter((n) => !currentNames.includes(n));
    const removed = currentNames.filter((n) => !newTags.includes(n));
    try {
      let updated = ticket;
      for (const name of added) updated = await addTag(ticketId!, name);
      for (const name of removed) updated = await removeTag(ticketId!, name);
      queryClient.setQueryData(["ticket", ticketId], updated);
      setPendingTags(null);
    } catch {
      setTagError(t("tickets.tags.failed"));
    }
  }

  async function handleIncrementTokens() {
    const amount = parseInt(tokensAmount, 10);
    if (!amount || amount <= 0) { setTokensError("Amount must be a positive integer."); return; }
    setTokensError(null);
    setTokensLoading(true);
    try {
      await incrementTokensSpent(ticketId!, amount);
      await queryClient.invalidateQueries({ queryKey: ["ticket", ticketId] });
      await queryClient.invalidateQueries({ queryKey: ["ticket-events", ticketId] });
    } catch {
      setTokensError("Failed to update tokens spent.");
    } finally {
      setTokensLoading(false);
    }
  }

  if (!ticketId) return null;
  if (isLoading) return <p className="text-muted-foreground">{t("tickets.loading")}</p>;
  if (isError || !ticket) return <p className="text-destructive">{t("tickets.notFound")}</p>;

  const isCreator = currentUser?.id === ticket.created_by.id;
  const isAssignee = ticket.assignees.some((a) => a.user_id === currentUser?.id);
  const isAdmin = currentUser?.role === "administrator";
  const alreadyAssigned = ticket.assignees.some((a) => a.user_id === currentUser?.id);
  const currentTagNames = pendingTags ?? ticket.tags.map((tg) => tg.name);

  const activeFlags = [
    ticket.urgent && "URGENT",
    ticket.blocker && "BLOCKER",
    ticket.bugfix && "BUGFIX",
  ].filter(Boolean) as string[];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <Link to={`/projects/${ticket.project_id}`} className="text-sm text-primary hover:underline">
          {t("nav.backToProject")}
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-4">
          {/* Ticket header / edit */}
          <Card>
            <CardContent className="pt-4">
              {isEditing ? (
                <>
                  <h2 className="text-base font-semibold mb-3">{t("tickets.editTicket")}</h2>
                  <TicketForm
                    initialValues={{
                      title: ticket.title, description: ticket.description,
                      ticket_type: ticket.ticket_type, ticket_spec: ticket.ticket_spec ?? undefined,
                      urgent: ticket.urgent, blocker: ticket.blocker, bugfix: ticket.bugfix,
                    }}
                    showTags={false}
                    onSubmit={handleEdit}
                    onCancel={() => setIsEditing(false)}
                    submitLabel={t("tickets.form.saveChanges")}
                  />
                </>
              ) : (
                <>
                  <div className="flex justify-between items-start gap-3 mb-2">
                    <div className="flex-1 min-w-0">
                      {ticket.display_id && (
                        <div className="font-mono text-xs font-bold text-primary mb-1">{ticket.display_id}</div>
                      )}
                      <h1 className="text-xl font-semibold leading-snug m-0">{ticket.title}</h1>
                    </div>
                    <Badge variant={statusVariant(ticket.status)} className="shrink-0">
                      {t(`tickets.status.${ticket.status}`)}
                    </Badge>
                  </div>

                  <div className="flex flex-wrap gap-1.5 mb-2">
                    <Badge variant="secondary" className="text-xs">{t(`tickets.type.${ticket.ticket_type}`)}</Badge>
                    {ticket.ticket_spec && (
                      <Badge variant="outline" className="text-xs text-green-700 border-green-300">{t(`tickets.spec.${ticket.ticket_spec}`)}</Badge>
                    )}
                    {activeFlags.map((f) => (
                      <Badge key={f} variant="destructive" className="text-xs">{f}</Badge>
                    ))}
                  </div>

                  {ticket.description && (
                    <p className="text-sm text-foreground leading-relaxed mb-2">{ticket.description}</p>
                  )}
                  <div className="text-xs text-muted-foreground mb-3">
                    {t("tickets.detail.createdBy", { email: ticket.created_by.email })}
                    {ticket.parent_ticket_id && (
                      <> · {t("tickets.detail.followUpOf")}{" "}
                        <Link to={`/tickets/${ticket.parent_ticket_id}`} className="text-primary hover:underline">
                          {t("tickets.detail.parentTicket")}
                        </Link>
                      </>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {isCreator && (
                      <>
                        <Button variant="outline" size="sm" onClick={() => setIsEditing(true)}>{t("tickets.detail.edit")}</Button>
                        <Button variant="outline" size="sm" className="text-destructive border-destructive hover:bg-destructive/10" onClick={handleDelete}>{t("tickets.detail.delete")}</Button>
                      </>
                    )}
                    <Button variant="outline" size="sm" onClick={() => setShowFollowUpForm((v) => !v)}>
                      {showFollowUpForm ? t("tickets.detail.cancelFollowUp") : t("tickets.detail.addFollowUp")}
                    </Button>
                  </div>
                  {deleteError && <p role="alert" className="text-sm text-destructive mt-2">{deleteError}</p>}
                </>
              )}
            </CardContent>
          </Card>

          {/* Follow-up form */}
          {showFollowUpForm && (
            <Card>
              <CardHeader><CardTitle className="text-base">{t("tickets.detail.createFollowUp")}</CardTitle></CardHeader>
              <CardContent>
                <TicketForm
                  onSubmit={handleCreateFollowUp}
                  onCancel={() => setShowFollowUpForm(false)}
                  submitLabel={t("tickets.form.createFollowUp")}
                />
              </CardContent>
            </Card>
          )}

          {/* Status transitions */}
          <Card>
            <CardHeader><CardTitle className="text-sm font-semibold">{t("tickets.detail.statusTransition")}</CardTitle></CardHeader>
            <CardContent>
              <StatusTransitionButton ticket={ticket} onTransitioned={handleTransitioned} />
            </CardContent>
          </Card>

          {/* Progress submit (assignee) */}
          {isAssignee && (
            <Card>
              <CardHeader><CardTitle className="text-sm font-semibold">{t("tickets.progress.submitUpdate")}</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                <Label htmlFor="progress-input" className="sr-only">{t("tickets.progress.submitUpdate")}</Label>
                <Textarea
                  id="progress-input"
                  value={progressInput}
                  onChange={(e) => setProgressInput(e.target.value)}
                  rows={3}
                  disabled={progressLoading}
                  placeholder={t("tickets.progress.placeholder")}
                  className="resize-y"
                />
                {progressError && <p role="alert" className="text-sm text-destructive">{progressError}</p>}
                <Button onClick={handleSubmitProgress} disabled={progressLoading} size="sm">
                  {progressLoading ? t("tickets.progress.submitting") : t("tickets.progress.submit")}
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Activity history */}
          <Card>
            <CardHeader><CardTitle className="text-sm font-semibold">{t("tickets.detail.activityHistory")}</CardTitle></CardHeader>
            <CardContent>
              <TicketEventHistory events={eventsData?.items ?? []} />
            </CardContent>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Assignees & progress */}
          <Card>
            <CardHeader><CardTitle className="text-sm font-semibold">{t("tickets.detail.assigneesProgress")}</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <AssigneeProgressList
                assignees={ticket.assignees}
                progressItems={progressData?.items ?? []}
                currentUserId={currentUser?.id}
                isAdmin={isAdmin}
                onUnassign={handleUnassign}
              />
              <div className="flex flex-wrap gap-2">
                {!alreadyAssigned && (
                  <Button variant="outline" size="sm" onClick={handleAssignMe}>{t("tickets.assign.assignMe")}</Button>
                )}
                {isAdmin && (
                  <Button variant="outline" size="sm" onClick={() => setShowAssignModal(true)}>{t("tickets.assign.assignUser")}</Button>
                )}
              </div>
              {assignError && <p role="alert" className="text-sm text-destructive">{assignError}</p>}
            </CardContent>
          </Card>

          {/* Tags */}
          <Card>
            <CardHeader><CardTitle className="text-sm font-semibold">{t("tickets.detail.tags")}</CardTitle></CardHeader>
            <CardContent>
              <TagInput
                value={currentTagNames}
                onChange={(newTags) => { setPendingTags(newTags); handleTagChange(newTags); }}
              />
              {tagError && <p role="alert" className="text-sm text-destructive mt-2">{tagError}</p>}
            </CardContent>
          </Card>

          {/* Tokens Spent */}
          <Card>
            <CardHeader><CardTitle className="text-sm font-semibold">Tokens Spent</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <p className="text-2xl font-bold tabular-nums">{ticket.tokens_spent.toLocaleString()}</p>
              {isAssignee && (
                <>
                  <div className="flex gap-2 items-center">
                    <input
                      type="number"
                      min={1}
                      value={tokensAmount}
                      onChange={(e) => setTokensAmount(e.target.value)}
                      disabled={tokensLoading}
                      className="border rounded px-2 py-1 text-sm w-24"
                      aria-label="Tokens to add"
                    />
                    <Button size="sm" variant="outline" onClick={handleIncrementTokens} disabled={tokensLoading}>
                      {tokensLoading ? "Adding…" : "+ Add"}
                    </Button>
                  </div>
                  {tokensError && <p role="alert" className="text-sm text-destructive">{tokensError}</p>}
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <AdminAssignModal
        open={showAssignModal}
        onClose={() => setShowAssignModal(false)}
        ticketId={ticketId}
        existingAssigneeIds={ticket.assignees.map((a) => a.user_id)}
        onAssigned={() => queryClient.invalidateQueries({ queryKey: ["ticket", ticketId] })}
      />
    </div>
  );
}
