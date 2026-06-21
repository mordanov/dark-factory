import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { TagInput } from "@/components/tickets/TagInput";
import type { TicketType, TicketSpec } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface TicketFormValues {
  title: string;
  description: string | null;
  ticket_type: TicketType;
  ticket_spec: TicketSpec | null;
  urgent: boolean;
  blocker: boolean;
  bugfix: boolean;
  tags: string[];
}

interface TicketFormProps {
  initialValues?: Partial<TicketFormValues>;
  onSubmit: (values: TicketFormValues) => Promise<void>;
  onCancel?: () => void;
  submitLabel?: string;
  showTags?: boolean;
}

const TICKET_TYPES: TicketType[] = [
  "feature", "bug", "improvement", "investigation",
  "discovery", "reporting", "testing", "analysis", "other",
];

const TICKET_SPECS: TicketSpec[] = [
  "backend", "frontend", "architecture", "testing",
  "business_analysis", "product_management", "other",
];

export function TicketForm({ initialValues, onSubmit, onCancel, submitLabel, showTags = true }: TicketFormProps) {
  const { t } = useTranslation();
  const [title, setTitle] = useState(initialValues?.title ?? "");
  const [description, setDescription] = useState(initialValues?.description ?? "");
  const [ticketType, setTicketType] = useState<TicketType>(initialValues?.ticket_type ?? "feature");
  const [ticketSpec, setTicketSpec] = useState<TicketSpec | "">(initialValues?.ticket_spec ?? "");
  const [urgent, setUrgent] = useState(initialValues?.urgent ?? false);
  const [blocker, setBlocker] = useState(initialValues?.blocker ?? false);
  const [bugfix, setBugfix] = useState(initialValues?.bugfix ?? false);
  const [tags, setTags] = useState<string[]>(initialValues?.tags ?? []);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const resolvedSubmitLabel = submitLabel ?? t("tickets.form.save");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) { setError(t("tickets.form.titleRequired")); return; }
    if (!ticketSpec) { setError(t("tickets.form.specRequired")); return; }
    setError(null);
    setLoading(true);
    try {
      await onSubmit({
        title: title.trim(),
        description: description.trim() || null,
        ticket_type: ticketType,
        ticket_spec: ticketSpec as TicketSpec,
        urgent, blocker, bugfix, tags,
      });
    } catch (err: unknown) {
      setError(extractErrorMessage(err, t));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="ticket-title">
          {t("tickets.form.title")} <span className="text-destructive">*</span>
        </Label>
        <Input
          id="ticket-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={loading}
          maxLength={500}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="ticket-description">{t("tickets.form.description")}</Label>
        <Textarea
          id="ticket-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          disabled={loading}
          className="resize-y"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="ticket-type">{t("tickets.form.type")}</Label>
          <Select value={ticketType} onValueChange={(v) => setTicketType(v as TicketType)} disabled={loading}>
            <SelectTrigger id="ticket-type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TICKET_TYPES.map((tp) => (
                <SelectItem key={tp} value={tp}>{t(`tickets.type.${tp}`)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="ticket-spec">
            {t("tickets.form.spec")} <span className="text-destructive">*</span>
          </Label>
          <Select value={ticketSpec || "__none__"} onValueChange={(v) => setTicketSpec(v === "__none__" ? "" : v as TicketSpec)} disabled={loading}>
            <SelectTrigger id="ticket-spec">
              <SelectValue placeholder={t("tickets.form.specPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">{t("tickets.form.specPlaceholder")}</SelectItem>
              {TICKET_SPECS.map((s) => (
                <SelectItem key={s} value={s}>{t(`tickets.spec.${s}`)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div>
        <Label className="block mb-2">{t("tickets.form.flags")}</Label>
        <div className="flex gap-6">
          {([
            [t("tickets.flags.urgent"), urgent, setUrgent],
            [t("tickets.flags.blocker"), blocker, setBlocker],
            [t("tickets.flags.bugfix"), bugfix, setBugfix],
          ] as [string, boolean, (v: boolean) => void][]).map(([name, val, setter]) => (
            <label key={name} className="flex items-center gap-1.5 cursor-pointer text-sm">
              <input
                type="checkbox"
                checked={val}
                onChange={(e) => setter(e.target.checked)}
                disabled={loading}
                className="w-4 h-4 accent-primary"
              />
              <span className={val ? "font-semibold" : "text-muted-foreground capitalize"}>{name}</span>
            </label>
          ))}
        </div>
      </div>

      {showTags && (
        <div className="space-y-2">
          <Label>
            {t("tickets.form.tags")}{" "}
            <span className="font-normal text-muted-foreground">{t("tickets.form.tagsHint")}</span>
          </Label>
          <TagInput value={tags} onChange={setTags} disabled={loading} />
        </div>
      )}

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

      <div className="flex gap-2">
        <Button type="submit" disabled={loading}>
          {loading ? t("tickets.form.saving") : resolvedSubmitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={loading}>
            {t("tickets.form.cancel")}
          </Button>
        )}
      </div>
    </form>
  );
}

function extractErrorMessage(err: unknown, t: (key: string) => string): string {
  if (typeof err === "object" && err !== null && "response" in err) {
    const e = err as { response: { data?: { detail?: string } } };
    if (e.response.data?.detail) return e.response.data.detail;
  }
  return t("tickets.form.error");
}
