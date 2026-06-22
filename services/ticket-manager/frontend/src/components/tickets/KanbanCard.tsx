import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import type { TicketResponse } from "@/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cardHover } from "@/lib/motion";

interface Props {
  ticket: TicketResponse;
}

export function KanbanCard({ ticket }: Props) {
  const { t } = useTranslation();
  const pendingAssignees = ticket.assignees.filter((a) => !a.has_progress_update);

  const activeFlags = [
    ticket.urgent && { label: "U", title: "Urgent" },
    ticket.blocker && { label: "B", title: "Blocker" },
    ticket.bugfix && { label: "F", title: "Bugfix" },
  ].filter(Boolean) as { label: string; title: string }[];

  function handleDragStart(e: React.DragEvent) {
    e.dataTransfer.setData("ticketId", ticket.id);
    e.dataTransfer.setData("fromStatus", ticket.status);
    e.dataTransfer.effectAllowed = "move";
  }

  return (
    <div draggable onDragStart={handleDragStart}>
      <motion.div {...cardHover}>
      <Card className="cursor-grab hover:shadow-md transition-shadow mb-2 select-none">
        <CardContent className="p-2.5">
          <div className="flex justify-between items-start mb-1">
            {ticket.display_id && (
              <span className="font-mono text-xs font-bold text-primary">{ticket.display_id}</span>
            )}
            {activeFlags.length > 0 && (
              <div className="flex gap-1 ml-auto">
                {activeFlags.map((f) => (
                  <Badge key={f.label} variant="destructive" className="h-4 w-4 p-0 text-[10px] flex items-center justify-center rounded-full" title={f.title}>
                    {f.label}
                  </Badge>
                ))}
              </div>
            )}
          </div>

          <Link to={`/tickets/${ticket.id}`} className="block font-semibold text-sm text-foreground hover:underline leading-snug">
            {ticket.title}
          </Link>

          <div className="text-xs text-muted-foreground mt-1">
            {t(`tickets.type.${ticket.ticket_type}`)}
          </div>

          {ticket.assignees.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {ticket.assignees.map((a) => (
                <Avatar key={a.user_id} className="h-6 w-6" title={a.email}>
                  <AvatarFallback className="text-[10px]">{a.email[0].toUpperCase()}</AvatarFallback>
                </Avatar>
              ))}
            </div>
          )}

          {ticket.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {ticket.tags.slice(0, 3).map((tg) => (
                <span key={tg.id} className="bg-accent text-accent-foreground rounded px-1.5 py-px text-[11px]">
                  {tg.name}
                </span>
              ))}
              {ticket.tags.length > 3 && (
                <span className="text-muted-foreground text-[11px]">+{ticket.tags.length - 3}</span>
              )}
            </div>
          )}

          {pendingAssignees.length > 0 && (
            <Badge
              variant="outline"
              className="mt-1.5 text-[11px] text-warning border-warning/50"
              title={`Awaiting progress from: ${pendingAssignees.map((a) => a.email).join(", ")}`}
            >
              ⚠ {pendingAssignees.length} pending
            </Badge>
          )}
        </CardContent>
      </Card>
      </motion.div>
    </div>
  );
}
