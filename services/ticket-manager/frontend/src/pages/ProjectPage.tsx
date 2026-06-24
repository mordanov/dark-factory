import { useState } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ProjectTicketList } from "@/components/projects/ProjectTicketList";
import { KanbanBoard } from "@/components/projects/KanbanBoard";
import { TicketForm, type TicketFormValues } from "@/components/tickets/TicketForm";
import { createTicket } from "@/api/tickets";
import { listProjects } from "@/api/projects";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type View = "list" | "board";

export function ProjectPage() {
  const { t } = useTranslation();
  const { projectId } = useParams<{ projectId: string }>();
  const [showCreate, setShowCreate] = useState(false);
  const queryClient = useQueryClient();

  const [searchParams, setSearchParams] = useSearchParams();
  const view = (searchParams.get("view") as View) ?? "list";

  function setView(newView: View) {
    setSearchParams({ view: newView }, { replace: true });
  }

  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(),
  });

  const project = projects?.find((p) => p.id === projectId);

  async function handleCreate(values: TicketFormValues) {
    await createTicket(projectId!, {
      title: values.title,
      description: values.description,
      ticket_type: values.ticket_type,
      ticket_spec: values.ticket_spec!,
      urgent: values.urgent,
      blocker: values.blocker,
      bugfix: values.bugfix,
      tags: values.tags,
    });
    await queryClient.invalidateQueries({ queryKey: ["tickets", projectId] });
    setShowCreate(false);
  }

  if (!projectId) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 text-sm">
          <Link to="/projects" className="text-primary hover:underline">{t("nav.backToProjects")}</Link>
          <span className="text-border">/</span>
          <h1 className="text-lg font-semibold m-0">{project?.name ?? "Project"}</h1>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex border border-border rounded overflow-hidden">
            <button
              onClick={() => setView("list")}
              className={cn(
                "px-3 py-1.5 text-xs border-r border-border",
                view === "list" ? "bg-accent text-accent-foreground font-semibold" : "bg-card text-muted-foreground hover:bg-muted"
              )}
            >
              {t("tickets.view.list")}
            </button>
            <button
              onClick={() => setView("board")}
              className={cn(
                "px-3 py-1.5 text-xs",
                view === "board" ? "bg-accent text-accent-foreground font-semibold" : "bg-card text-muted-foreground hover:bg-muted"
              )}
            >
              {t("tickets.view.board")}
            </button>
          </div>
          <Button onClick={() => setShowCreate((v) => !v)} size="sm">
            {showCreate ? t("tickets.form.cancel") : t("tickets.newTicket")}
          </Button>
        </div>
      </div>

      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("tickets.createTicket")}</CardTitle>
          </CardHeader>
          <CardContent>
            <TicketForm
              onSubmit={handleCreate}
              onCancel={() => setShowCreate(false)}
              submitLabel={t("tickets.form.createTicket")}
            />
          </CardContent>
        </Card>
      )}

      {view === "list" ? (
        <ProjectTicketList projectId={projectId} />
      ) : (
        <KanbanBoard projectId={projectId} />
      )}
    </div>
  );
}
