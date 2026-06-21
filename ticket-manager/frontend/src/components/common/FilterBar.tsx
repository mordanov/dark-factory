import { useTranslation } from "react-i18next";
import type { TicketStatus, AssigneeSummary } from "@/types";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface FilterState {
  status: TicketStatus | "";
  assigneeId: string;
}

interface FilterBarProps {
  filters: FilterState;
  assignees: AssigneeSummary[];
  onChange: (filters: FilterState) => void;
}

const ALL_STATUSES: TicketStatus[] = ["OPEN", "IN_PROGRESS", "IN_REVIEW", "DONE", "CLOSED"];

export function FilterBar({ filters, assignees, onChange }: FilterBarProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap gap-4 mb-4 p-3 bg-card rounded-md border border-border" role="search" aria-label="Filter tickets">
      <div className="flex items-center gap-2">
        <Label htmlFor="filter-status" className="whitespace-nowrap text-sm">
          {t("filter.status")}
        </Label>
        <Select
          value={filters.status || "all"}
          onValueChange={(v) => onChange({ ...filters, status: v === "all" ? "" : v as TicketStatus })}
        >
          <SelectTrigger id="filter-status" className="h-8 w-[140px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("filter.allStatuses")}</SelectItem>
            {ALL_STATUSES.map((s) => (
              <SelectItem key={s} value={s}>{t(`tickets.status.${s}`)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {assignees.length > 0 && (
        <div className="flex items-center gap-2">
          <Label htmlFor="filter-assignee" className="whitespace-nowrap text-sm">
            {t("filter.assignee")}
          </Label>
          <Select
            value={filters.assigneeId || "all"}
            onValueChange={(v) => onChange({ ...filters, assigneeId: v === "all" ? "" : v })}
          >
            <SelectTrigger id="filter-assignee" className="h-8 w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("filter.allAssignees")}</SelectItem>
              {assignees.map((a) => (
                <SelectItem key={a.user_id} value={a.user_id}>{a.email}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  );
}
