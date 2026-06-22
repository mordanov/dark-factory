import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { listAllTickets } from "@/api/projects";
import type { TicketStatus } from "@/types";
import { KanbanColumn } from "@/components/tickets/KanbanColumn";

interface Props {
  projectId: string;
}

const STATUSES: TicketStatus[] = ["OPEN", "IN_PROGRESS", "IN_REVIEW", "DONE", "CLOSED"];

const STATUS_COLORS: Record<TicketStatus, string> = {
  OPEN: "#2980b9",
  IN_PROGRESS: "#e67e22",
  IN_REVIEW: "#8e44ad",
  DONE: "#27ae60",
  CLOSED: "#7f8c8d",
};

export function KanbanBoard({ projectId }: Props) {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["tickets", projectId],
    queryFn: () => listAllTickets(projectId),
  });

  if (isLoading) return <p className="p-8 text-muted-foreground">{t("tickets.loadingBoard")}</p>;
  if (isError) return <p className="p-8 text-destructive">{t("tickets.failedToLoad")}</p>;

  const tickets = data?.items ?? [];

  return (
    <div className="flex gap-4 overflow-x-auto pb-4">
      {STATUSES.map((status) => (
        <KanbanColumn
          key={status}
          status={status}
          label={t(`tickets.status.${status}`)}
          color={STATUS_COLORS[status]}
          tickets={tickets.filter((tkt) => tkt.status === status)}
          projectId={projectId}
        />
      ))}
    </div>
  );
}
