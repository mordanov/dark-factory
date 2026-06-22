import { useTranslation } from "react-i18next";
import type { AssigneeSummary, ProgressUpdateResponse } from "@/types";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";

interface Props {
  assignees: AssigneeSummary[];
  progressItems: ProgressUpdateResponse[];
  currentUserId?: string;
  isAdmin?: boolean;
  onUnassign?: (userId: string) => void;
}

export function AssigneeProgressList({ assignees, progressItems, currentUserId, isAdmin, onUnassign }: Props) {
  const { t } = useTranslation();
  const progressByUser = new Map(progressItems.map((p) => [p.user_id, p]));

  if (assignees.length === 0) {
    return <p className="text-sm text-muted-foreground">No assignees.</p>;
  }

  return (
    <ul className="list-none p-0 m-0 space-y-2">
      {assignees.map((a) => {
        const progress = progressByUser.get(a.user_id);
        const canRemove = onUnassign && (isAdmin || a.user_id === currentUserId);
        const initials = a.email.slice(0, 2).toUpperCase();
        return (
          <li key={a.user_id} className="flex flex-col gap-1 bg-background border border-border rounded-md p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-3">
                <Avatar className="h-8 w-8">
                  <AvatarFallback className="text-xs">{initials}</AvatarFallback>
                </Avatar>
                <span className="font-medium text-sm">{a.email}</span>
              </div>
              <div className="flex items-center gap-2">
                {progress ? (
                  <Badge variant="secondary" className="text-xs bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                    Update submitted
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-xs text-warning">
                    Pending
                  </Badge>
                )}
                {canRemove && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={() => onUnassign(a.user_id)}
                    aria-label={t("tickets.assign.removeFailed")}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                )}
              </div>
            </div>
            {progress && (
              <p className="text-sm text-foreground mt-1 pl-11">{progress.content}</p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
