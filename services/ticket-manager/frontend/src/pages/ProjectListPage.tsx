import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listProjects, createProject } from "@/api/projects";
import type { ProjectSummary } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { GroupFilter } from "@/components/projects/GroupFilter";

function randomCode(): string {
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const digits = "0123456789";
  const l = Array.from({ length: 4 }, () => letters[Math.floor(Math.random() * 26)]).join("");
  const n = Array.from({ length: 3 }, () => digits[Math.floor(Math.random() * 10)]).join("");
  return `${l}-${n}`;
}

export function ProjectListPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState(() => randomCode());
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [groupFilter, setGroupFilter] = useState<string | undefined>(undefined);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["projects", groupFilter],
    queryFn: () => listProjects(groupFilter ? { group_id: groupFilter } : undefined),
  });

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreateError(null);
    setCreating(true);
    try {
      await createProject({ name: name.trim(), code });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setName("");
      setCode(randomCode());
      setShowForm(false);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setCreateError(e.response?.data?.detail ?? t("projects.failedToCreate"));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-semibold">{t("projects.title")}</h1>
        <div className="flex items-center gap-2">
          <GroupFilter value={groupFilter} onChange={setGroupFilter} />
          <Button
            variant="outline"
            onClick={() => { setShowForm((v) => !v); setCreateError(null); }}
          >
            {showForm ? t("projects.cancel") : t("projects.newProject")}
          </Button>
        </div>
      </div>

      {showForm && (
        <Card>
          <CardContent className="pt-4">
            <form onSubmit={handleCreate} className="space-y-4">
              <h2 className="text-base font-semibold">{t("projects.createProject")}</h2>
              <div className="space-y-2">
                <Label htmlFor="project-name">{t("projects.projectName")}</Label>
                <Input
                  id="project-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="My Project"
                  required
                  disabled={creating}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="project-code">{t("projects.code")}</Label>
                <div className="flex gap-2 items-center">
                  <Input
                    id="project-code"
                    value={code}
                    onChange={(e) => setCode(e.target.value.toUpperCase())}
                    placeholder="AAAA-000"
                    required
                    pattern="[A-Z]{4}-[0-9]{3}"
                    title={t("projects.codeTitle")}
                    className="font-mono tracking-wider"
                    disabled={creating}
                    maxLength={8}
                  />
                  <Button type="button" variant="outline" onClick={() => setCode(randomCode())} disabled={creating} title="Generate a new random code">
                    ↺
                  </Button>
                </div>
                <span className="text-xs text-muted-foreground">{t("projects.codeFormat")}</span>
              </div>
              {createError && <p role="alert" className="text-sm text-destructive">{createError}</p>}
              <Button type="submit" disabled={creating}>
                {creating ? t("projects.creating") : t("projects.create")}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {isLoading && <p>{t("projects.loadingProjects")}</p>}
      {isError && <p className="text-destructive">{t("projects.failedToLoad")}</p>}
      {data && data.length === 0 && !showForm && (
        <p className="text-muted-foreground">{t("projects.noProjects")}</p>
      )}
      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {data.map((p) => (
            <ProjectPlate key={p.id} project={p} />
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectPlate({ project: p }: { project: ProjectSummary }) {
  const { t } = useTranslation();
  const date = new Date(p.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

  return (
    <Link to={`/projects/${p.id}`} className="block no-underline">
      <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
        <CardContent className="p-4">
          <div className="flex justify-between items-start mb-2">
            <span className="font-bold text-base text-foreground flex-1 leading-snug">{p.name}</span>
            {p.code && (
              <span className="font-mono text-xs font-bold bg-accent text-accent-foreground border border-border rounded px-1.5 py-0.5 whitespace-nowrap ml-2">
                {p.code}
              </span>
            )}
          </div>
          <div className="text-xs text-muted-foreground mb-1">
            <span className="inline-block bg-secondary text-secondary-foreground rounded px-1.5 py-0.5 mr-1.5">
              {p.group.identifier}
            </span>
            {p.group.name}
          </div>
          <div className="text-xs text-muted-foreground mb-3">{t("projects.createdOn", { date })}</div>
          <div className="flex gap-2">
            <TicketBucket label={t("projects.tickets.open")} count={p.ticket_counts.open} className="text-blue-600" />
            <TicketBucket label={t("projects.tickets.active")} count={p.ticket_counts.active} className="text-orange-500" />
            <TicketBucket label={t("projects.tickets.done")} count={p.ticket_counts.done} className="text-green-600" />
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function TicketBucket({ label, count, className }: { label: string; count: number; className: string }) {
  return (
    <div className="flex-1 flex flex-col items-center bg-muted rounded-md py-2 border border-border">
      <span className={`text-xl font-bold ${className}`}>{count}</span>
      <span className="text-[10px] text-muted-foreground mt-0.5">{label}</span>
    </div>
  );
}
