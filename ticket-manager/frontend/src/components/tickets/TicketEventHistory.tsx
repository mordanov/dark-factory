import { useTranslation } from "react-i18next";
import type { TicketEventResponse } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

interface TicketEventHistoryProps {
  events: TicketEventResponse[];
}

export function TicketEventHistory({ events }: TicketEventHistoryProps) {
  const { t } = useTranslation();

  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("tickets.events.noActivity")}</p>;
  }

  return (
    <div className="space-y-3">
      {events.map((event, idx) => {
        const labelKey = `tickets.events.label.${event.event_type.replace(".", "_")}`;
        const stateChange = renderStateChange(event);
        return (
          <div key={event.id}>
            <div className="flex items-start gap-3 text-sm">
              <Badge variant="secondary" className="shrink-0 text-xs">
                {t(labelKey, { defaultValue: event.event_type })}
              </Badge>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="text-xs text-muted-foreground">
                    {t("tickets.events.by", { email: event.actor.email })}
                  </span>
                  <span
                    className="text-xs text-muted-foreground whitespace-nowrap"
                    title={new Date(event.occurred_at).toLocaleString()}
                  >
                    {formatRelativeTime(event.occurred_at, t)}
                  </span>
                </div>
                {stateChange && (
                  <p className="text-foreground text-xs mt-0.5">{stateChange}</p>
                )}
              </div>
            </div>
            {idx < events.length - 1 && <Separator className="mt-3" />}
          </div>
        );
      })}
    </div>
  );
}

function formatRelativeTime(isoString: string, t: (key: string, opts?: Record<string, unknown>) => string): string {
  const diff = Date.now() - new Date(isoString).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return t("tickets.events.time.justNow");
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return t("tickets.events.time.minutesAgo", { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t("tickets.events.time.hoursAgo", { count: hours });
  const days = Math.floor(hours / 24);
  return t("tickets.events.time.daysAgo", { count: days });
}

function renderStateChange(event: TicketEventResponse): string | null {
  if (event.event_type === "ticket.status_changed") {
    const prev = (event.prev_state as { status?: string } | null)?.status;
    const next = (event.new_state as { status?: string } | null)?.status;
    if (prev && next) return `${prev} → ${next}`;
  }
  if (event.event_type === "ticket.progress_updated") {
    const content = (event.new_state as { content?: string } | null)?.content;
    if (content) return content.length > 120 ? content.slice(0, 120) + "…" : content;
  }
  return null;
}
