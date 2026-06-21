import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import type { FilterState } from "@/components/common/FilterBar";
import { FilterBar } from "@/components/common/FilterBar";
import { listTickets } from "@/api/projects";
import type { AssigneeSummary } from "@/types";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface ProjectTicketListProps {
  projectId: string;
}

export function ProjectTicketList({ projectId }: ProjectTicketListProps) {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<FilterState>({ status: "", assigneeId: "" });

  const queryParams = {
    ...(filters.status ? { status: filters.status } : {}),
    ...(filters.assigneeId ? { assignee_id: filters.assigneeId } : {}),
  };

  const { data, isLoading, isError } = useQuery({
    queryKey: ["tickets", projectId, queryParams],
    queryFn: () => listTickets(projectId, queryParams),
  });

  const allAssignees = useMemo<AssigneeSummary[]>(() => {
    if (!data) return [];
    const seen = new Set<string>();
    const result: AssigneeSummary[] = [];
    for (const ticket of data.items) {
      for (const a of ticket.assignees) {
        if (!seen.has(a.user_id)) { seen.add(a.user_id); result.push(a); }
      }
    }
    return result;
  }, [data]);

  if (isLoading) return <p>{t("tickets.loading")}</p>;
  if (isError) return <p className="text-destructive">{t("tickets.failedToLoad")}</p>;

  const tickets = data?.items ?? [];

  return (
    <div>
      <FilterBar filters={filters} assignees={allAssignees} onChange={setFilters} />
      {tickets.length === 0 ? (
        <p className="text-muted-foreground text-center py-8">No tickets match the current filters.</p>
      ) : (
        <div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("tickets.list.id")}</TableHead>
                <TableHead>{t("tickets.list.title")}</TableHead>
                <TableHead>{t("tickets.list.type")}</TableHead>
                <TableHead>{t("tickets.list.status")}</TableHead>
                <TableHead>{t("tickets.list.assignees")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tickets.map((ticket) => (
                <TableRow key={ticket.id}>
                  <TableCell className="font-mono text-xs text-primary">{ticket.display_id ?? "-"}</TableCell>
                  <TableCell>
                    <Link to={`/tickets/${ticket.id}`} className="text-sm font-medium hover:underline">
                      {ticket.title}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="text-xs">{t(`tickets.type.${ticket.ticket_type}`)}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">{t(`tickets.status.${ticket.status}`)}</Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {ticket.assignees.map((a) => a.email.split("@")[0]).join(", ") || "-"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="text-xs text-muted-foreground text-right mt-2">{data?.total ?? tickets.length} total</p>
        </div>
      )}
    </div>
  );
}
