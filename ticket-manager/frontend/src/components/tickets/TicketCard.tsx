import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import type { TicketResponse } from "@/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cardHover } from "@/lib/motion";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "DONE") return "default";
  if (status === "CLOSED") return "outline";
  if (status === "IN_PROGRESS") return "secondary";
  return "outline";
}

interface TicketCardProps {
  ticket: TicketResponse;
  onClick?: () => void;
  className?: string;
}

export function TicketCard({ ticket, className }: TicketCardProps) {
  const { t } = useTranslation();
  const activeFlags = [
    ticket.urgent && "URGENT",
    ticket.blocker && "BLOCKER",
    ticket.bugfix && "BUGFIX",
  ].filter(Boolean) as string[];

  return (
    <motion.div {...cardHover} className={className}>
      <Card className="cursor-pointer hover:shadow-md transition-shadow mb-2">
        <CardContent className="p-4">
          <div className="flex justify-between items-start gap-2 mb-1">
            <div className="flex items-center gap-1.5 flex-wrap">
              {ticket.display_id && (
                <span className="font-mono text-xs font-bold text-primary bg-accent px-1.5 py-0.5 rounded border border-border">
                  {ticket.display_id}
                </span>
              )}
              <Badge variant="secondary" className="text-xs">{t(`tickets.type.${ticket.ticket_type}`)}</Badge>
              {ticket.ticket_spec && (
                <Badge variant="outline" className="text-xs text-green-700 border-green-300">{t(`tickets.spec.${ticket.ticket_spec}`)}</Badge>
              )}
            </div>
            <Badge variant={statusVariant(ticket.status)} className="text-xs shrink-0">
              {t(`tickets.status.${ticket.status}`)}
            </Badge>
          </div>

          <Link to={`/tickets/${ticket.id}`} className="block font-semibold text-sm text-foreground hover:underline line-clamp-2 mb-1">
            {ticket.title}
          </Link>

          <div className="flex gap-1.5 text-xs text-muted-foreground">
            <span>Created {formatDate(ticket.created_at)}</span>
            <span>·</span>
            <span>Updated {formatDate(ticket.updated_at)}</span>
          </div>

          {ticket.assignees.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {ticket.assignees.map((a) => (
                <span key={a.user_id} className="inline-block bg-accent text-accent-foreground rounded-full px-2 py-0.5 text-xs" title={a.email}>
                  {a.email.split("@")[0]}
                </span>
              ))}
            </div>
          )}

          {ticket.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {ticket.tags.map((tg) => (
                <span key={tg.id} className="inline-block bg-accent text-accent-foreground rounded-full px-2 py-0.5 text-xs">
                  {tg.name}
                </span>
              ))}
            </div>
          )}

          {activeFlags.length > 0 && (
            <div className="flex gap-1 mt-1.5">
              {activeFlags.map((f) => (
                <Badge key={f} variant="destructive" className="text-xs">{f}</Badge>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
