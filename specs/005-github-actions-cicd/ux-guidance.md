# UX Guidance: GitHub Actions Operator Experience

**Feature**: 005-github-actions-cicd
**Author**: designer agent
**Scope**: US4 manual rollback UI + DEPLOYMENT.md operator guide usability criteria

---

## 1. Manual Rollback Workflow — GitHub Actions UI (T013)

### 1.1 Workflow Dispatch Input Labels

The `workflow_dispatch` inputs are the entire operator-facing UI for emergency rollback.
Every field label and description must communicate clearly without requiring the operator
to read documentation.

#### Input: `service`

```yaml
inputs:
  service:
    description: 'Service to roll back (choose "all" to restore every service)'
    required: true
    type: choice
    options:
      - uim-backend
      - tm-backend
      - orchestrator
      - context-distiller
      - agent-dispatcher
      - agent-tools
      - uim-frontend
      - tm-frontend
      - nginx
      - all
```

**Rationale**: The description must answer "what does 'all' mean?" without opening docs.
Option order: most-commonly-deployed services first (`uim-backend`, `tm-backend`), then
less-common, then `all` last so it is not accidentally selected.

#### Input: `reason`

```yaml
  reason:
    description: 'Reason for rollback — appears in the audit log (required, e.g. "regression in ticket search")'
    required: true
    type: string
```

**Rationale**: The description must tell the operator (a) that this text is permanent and
visible in audit logs, and (b) provide a concrete example so they write a useful entry
rather than "bug" or "test".

### 1.2 Audit Log Output — UX Acceptance Criteria

The job log is the audit trail. It must be human-readable without parsing.

**AC-UX-01**: The first step in the rollback job MUST print a clearly formatted audit header:

```
=== MANUAL ROLLBACK AUDIT ===
Actor   : <github.actor>
Time    : <github.run_started_at>
Service : <inputs.service>
Reason  : <inputs.reason>
Run URL : https://github.com/<owner>/<repo>/actions/runs/<github.run_id>
==============================
```

**AC-UX-02**: For each service being restored, the log MUST print the before/after tag:

```
[tm-backend] Restoring rollback-20260625143022 → latest
```

**AC-UX-03**: If no rollback snapshot exists for a service, the log MUST print a clear
warning (not a cryptic error):

```
[tm-backend] WARNING: No rollback snapshot found. Skipping. Service remains on current image.
```

**AC-UX-04**: The final step MUST print a summary line indicating success or partial failure:

```
Rollback complete. 1/1 services restored.
```

or:

```
Rollback finished with warnings. 0/1 services restored (no snapshot available).
```

**AC-UX-05**: The workflow MUST use a descriptive job name visible in the GitHub Actions
sidebar, not the default `rollback`:

```yaml
jobs:
  rollback:
    name: "Manual Rollback — ${{ inputs.service }}"
```

This lets an operator scanning the Actions history immediately see what was rolled back.

### 1.3 Error States — Operator-Visible Messages

| Failure condition | Required log output |
|---|---|
| SSH connection to VPS fails | `ERROR: Cannot reach VPS at $VPS_HOST. Check VPS_HOST secret and VPS firewall.` |
| No rollback tag for service | `WARNING: No rollback snapshot for <service>. Skipping.` |
| Docker restart fails on VPS | `ERROR: Failed to restart <service> after rollback. Manual intervention required.` |
| `reason` input is empty | Blocked by `required: true` — GitHub enforces this before the job starts |

**Rule**: No Docker daemon output, no raw shell errors, no stack traces in the user-visible
summary step. Wrap low-level errors with a human sentence before `exit 1`.

---

## 2. DEPLOYMENT.md Operator Guide — UX Writing Criteria (T014)

### 2.1 Document Structure

The guide must follow task-flow order — the sequence a real operator performs on a new
deployment. Do not organize by component (GitHub / VPS / nginx) — organize by when
the operator needs each section.

**Required section order**:

1. Prerequisites checklist (what must exist before starting)
2. Step 1: First-time VPS setup (`setup-vps.sh`)
3. Step 2: Place the production `.env` file
4. Step 3: Add GitHub Actions secrets (exactly 3, table with name + value format)
5. Step 4: Trigger first deployment (push a test commit)
6. Step 5: SSL/HTTPS setup (certbot — clearly marked as OPTIONAL, post-HTTP)
7. Reference: Manual rollback procedure
8. Reference: Rollback snapshot retention policy
9. Reference: Certbot renewal cron job

### 2.2 UX Writing Rules for DEPLOYMENT.md

**Rule 1 — One action per step.** Each numbered step has exactly one command or one
decision. Do not bundle "install Docker AND add user to group AND clone repo" into
one paragraph.

**Rule 2 — Show the exact command.** Every action must be copy-pasteable:

```bash
# Good
bash /app/dark-factory/infra/scripts/setup-vps.sh

# Bad
Run the setup script from the infra/scripts folder.
```

**Rule 3 — Mark destructive or irreversible steps.** Use a `> ⚠️` blockquote for any
step that is hard to undo (e.g., running certbot for the first time, adding `.env` over
an existing file).

**Rule 4 — Name the exact secret values, not just their purpose.** The secrets table
must show the exact GitHub secret name in backticks:

| Secret name | Value |
|---|---|
| `VPS_HOST` | IP address of the Hetzner VPS |
| `VPS_USER` | `ubuntu` |
| `VPS_SSH_KEY` | Full contents of the deployment private key (begins `-----BEGIN OPENSSH PRIVATE KEY-----`) |

**Rule 5 — Certbot section must have a clear scope label.** SSL setup is optional and
post-HTTP. The section heading must say: `## Optional: SSL/HTTPS with Certbot`.
This prevents operators from thinking SSL is required to get the pipeline working.

**Rule 6 — Manual rollback section must lead with the trigger path.** Operators under
stress need the fastest path:

```
1. Go to: GitHub → Actions → Manual Rollback
2. Click "Run workflow"
3. Select service + enter reason → Run
```

Follow with: what to verify, where the audit log is, and what to do if no snapshot exists.

**Rule 7 — Retention policy must state numbers.** Not "recent snapshots" — write "the
3 most recent rollback snapshots per service are retained; older ones are deleted
automatically by the pipeline."

### 2.3 Accessibility — Operator Guide

- All code blocks must use language-tagged fences (` ```bash `, ` ```yaml `) for
  syntax highlighting in GitHub markdown rendering.
- All tables must have header rows so they render correctly on GitHub.
- No color-only differentiation — warnings use ⚠️ emoji + bold text, not just color.

---

## 3. Acceptance Criteria Summary (for Autotester)

| ID | Criterion | How to verify |
|---|---|---|
| AC-UX-01 | Audit header printed at rollback start | Run manual rollback; inspect job log first step |
| AC-UX-02 | Before/after tag logged per service | Run manual rollback for one service; check log |
| AC-UX-03 | No-snapshot warning is human-readable | Delete rollback tags; trigger rollback; check log |
| AC-UX-04 | Summary line printed at end of job | Run manual rollback; inspect last step log |
| AC-UX-05 | Job name includes service name in sidebar | Check Actions history — job shows service name |
| AC-UX-06 | `reason` input has example text in description | Open "Run workflow" dialog; read description |
| AC-UX-07 | `service` input description explains "all" | Open "Run workflow" dialog; read description |
| AC-UX-08 | DEPLOYMENT.md sections in task-flow order | Read DEPLOYMENT.md top to bottom |
| AC-UX-09 | Every action has a copy-pasteable command | Audit DEPLOYMENT.md for prose-only instructions |
| AC-UX-10 | Secrets table shows exact GitHub secret names | Find secrets table; verify backtick-formatted names |
| AC-UX-11 | Certbot section marked Optional | Find certbot heading; verify "Optional" in heading |
| AC-UX-12 | Manual rollback section leads with trigger path | Find rollback section; steps 1–3 must be UI path |
| AC-UX-13 | Retention policy states "3 most recent" | Find retention section; verify number is explicit |
