#!/usr/bin/env python3
"""
agent_metrics.py — SQLite-backed task metrics tool for project-administrator.

Commands:
  init         Create the database and tables (idempotent)
  insert       Insert one task event (used by report-task-metrics.sh)
  summary      Print a human-readable summary grouped by agent and feature
  gaps         List events that are missing required fields
  report-html  Generate an HTML report to metrics_report.html
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "metrics.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS task_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT    NOT NULL,
    agent_name       TEXT    NOT NULL,
    feature_name     TEXT    NOT NULL,
    task_id          TEXT,
    task_description TEXT    NOT NULL,
    time_spent_s     INTEGER,
    tokens_spent     INTEGER,
    model_used       TEXT,
    token_source     TEXT    DEFAULT 'self-reported',
    status           TEXT    DEFAULT 'completed',
    notes            TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def cmd_init(args):
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"[agent_metrics] Database initialised at {DB_PATH}")


def cmd_insert(args):
    conn = get_conn()
    conn.executescript(SCHEMA)
    ts = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO task_events
          (timestamp, agent_name, feature_name, task_id, task_description,
           time_spent_s, tokens_spent, model_used, token_source, status, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            ts,
            args.agent_name,
            args.feature_name,
            args.task_id or "",
            args.task_description,
            args.time_spent_seconds,
            args.tokens_spent,
            args.model_used or "",
            args.token_source or "self-reported",
            args.status or "completed",
            args.notes or "",
        ),
    )
    conn.commit()
    conn.close()
    print(f"[agent_metrics] Recorded: {args.agent_name} / {args.task_description[:60]}")


def cmd_summary(args):
    if not DB_PATH.exists():
        print("[agent_metrics] No database found. Run: python agent_metrics.py init")
        return
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM task_events ORDER BY agent_name, timestamp"
    ).fetchall()
    conn.close()

    if not rows:
        print("[agent_metrics] No events recorded yet.")
        return

    totals: dict = {}
    for r in rows:
        key = r["agent_name"]
        if key not in totals:
            totals[key] = {"tasks": 0, "time_s": 0, "tokens": 0}
        totals[key]["tasks"] += 1
        totals[key]["time_s"] += r["time_spent_s"] or 0
        totals[key]["tokens"] += r["tokens_spent"] or 0

    print(f"\n{'Agent':<30} {'Tasks':>6} {'Time(s)':>9} {'Tokens':>9}")
    print("-" * 58)
    for agent, t in sorted(totals.items()):
        print(f"{agent:<30} {t['tasks']:>6} {t['time_s']:>9} {t['tokens']:>9}")
    print(f"\nTotal events: {len(rows)}")


def cmd_gaps(args):
    if not DB_PATH.exists():
        print("[agent_metrics] No database found.")
        return
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT * FROM task_events
        WHERE time_spent_s IS NULL
           OR time_spent_s = 0
           OR tokens_spent IS NULL
           OR tokens_spent = 0
           OR model_used IS NULL
           OR model_used = ''
           OR task_description = ''
        ORDER BY timestamp
        """
    ).fetchall()
    conn.close()

    if not rows:
        print("[agent_metrics] No gaps found — all events look complete.")
        return

    print(f"[agent_metrics] {len(rows)} gap(s) found:\n")
    for r in rows:
        missing = []
        if not r["time_spent_s"]:
            missing.append("time_spent_s")
        if not r["tokens_spent"]:
            missing.append("tokens_spent")
        if not r["model_used"]:
            missing.append("model_used")
        if not r["task_description"]:
            missing.append("task_description")
        print(
            f"  id={r['id']} agent={r['agent_name']} task={r['task_description'][:40]!r} "
            f"missing={missing}"
        )


def cmd_report_html(args):
    if not DB_PATH.exists():
        print("[agent_metrics] No database found.")
        return
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM task_events ORDER BY timestamp"
    ).fetchall()
    conn.close()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Aggregate
    by_agent: dict = {}
    by_feature: dict = {}
    total_time = 0
    total_tokens = 0

    for r in rows:
        a = r["agent_name"]
        f = r["feature_name"]
        t = r["time_spent_s"] or 0
        tk = r["tokens_spent"] or 0
        total_time += t
        total_tokens += tk
        by_agent.setdefault(a, {"tasks": 0, "time_s": 0, "tokens": 0})
        by_agent[a]["tasks"] += 1
        by_agent[a]["time_s"] += t
        by_agent[a]["tokens"] += tk
        by_feature.setdefault(f, {"tasks": 0, "time_s": 0, "tokens": 0})
        by_feature[f]["tasks"] += 1
        by_feature[f]["time_s"] += t
        by_feature[f]["tokens"] += tk

    def agent_rows_html():
        out = []
        for a, d in sorted(by_agent.items()):
            out.append(
                f"<tr><td>{a}</td><td>{d['tasks']}</td>"
                f"<td>{d['time_s']}</td><td>{d['tokens']:,}</td></tr>"
            )
        return "\n".join(out)

    def feature_rows_html():
        out = []
        for f, d in sorted(by_feature.items()):
            out.append(
                f"<tr><td>{f}</td><td>{d['tasks']}</td>"
                f"<td>{d['time_s']}</td><td>{d['tokens']:,}</td></tr>"
            )
        return "\n".join(out)

    def event_rows_html():
        out = []
        for r in rows:
            notes = r["notes"] or ""
            ts_short = (r["timestamp"] or "")[:19]
            out.append(
                f"<tr>"
                f"<td>{ts_short}</td>"
                f"<td>{r['agent_name']}</td>"
                f"<td>{r['feature_name']}</td>"
                f"<td>{r['task_id'] or ''}</td>"
                f"<td>{r['task_description']}</td>"
                f"<td>{r['time_spent_s'] or ''}</td>"
                f"<td>{r['tokens_spent'] or ''}</td>"
                f"<td>{r['model_used'] or ''}</td>"
                f"<td>{r['token_source'] or ''}</td>"
                f"<td>{r['status'] or ''}</td>"
                f"<td>{notes}</td>"
                f"</tr>"
            )
        return "\n".join(out)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Agent Metrics Report — auth-app</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #222; }}
  h1 {{ color: #1a1a2e; }}
  h2 {{ color: #16213e; margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; font-size: 0.9rem; }}
  th {{ background: #e8eaf6; font-weight: 600; }}
  tr:nth-child(even) {{ background: #f5f5f5; }}
  .summary-box {{ background: #e3f2fd; border-left: 4px solid #1976d2; padding: 1rem; margin-bottom: 1.5rem; }}
  .generated {{ font-size: 0.8rem; color: #666; }}
</style>
</head>
<body>
<h1>Agent Metrics Report — auth-app</h1>
<p class="generated">Generated: {now}</p>

<div class="summary-box">
  <strong>Total events:</strong> {len(rows)} &nbsp;|&nbsp;
  <strong>Total time:</strong> {total_time:,}s &nbsp;|&nbsp;
  <strong>Total tokens:</strong> {total_tokens:,}
</div>

<h2>By Agent</h2>
<table>
<tr><th>Agent</th><th>Tasks</th><th>Time (s)</th><th>Tokens</th></tr>
{agent_rows_html()}
</table>

<h2>By Feature</h2>
<table>
<tr><th>Feature</th><th>Tasks</th><th>Time (s)</th><th>Tokens</th></tr>
{feature_rows_html()}
</table>

<h2>All Events</h2>
<table>
<tr>
  <th>Timestamp</th><th>Agent</th><th>Feature</th><th>Task ID</th>
  <th>Description</th><th>Time (s)</th><th>Tokens</th>
  <th>Model</th><th>Token Source</th><th>Status</th><th>Notes</th>
</tr>
{event_rows_html()}
</table>
</body>
</html>"""

    report_path = Path(__file__).parent / "metrics_report.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"[agent_metrics] Report written to {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Agent metrics tool")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialise the database")
    sub.add_parser("summary", help="Print summary by agent")
    sub.add_parser("gaps", help="List events with missing fields")
    sub.add_parser("report-html", help="Generate HTML report")

    ins = sub.add_parser("insert", help="Insert a task event")
    ins.add_argument("--agent-name", required=True)
    ins.add_argument("--feature-name", required=True)
    ins.add_argument("--task-id", default="")
    ins.add_argument("--task-description", required=True)
    ins.add_argument("--time-spent-seconds", type=int, default=0)
    ins.add_argument("--tokens-spent", type=int, default=0)
    ins.add_argument("--model-used", default="")
    ins.add_argument("--token-source", default="self-reported")
    ins.add_argument("--status", default="completed")
    ins.add_argument("--notes", default="")

    args = parser.parse_args()

    dispatch = {
        "init": cmd_init,
        "summary": cmd_summary,
        "gaps": cmd_gaps,
        "report-html": cmd_report_html,
        "insert": cmd_insert,
    }

    if args.command not in dispatch:
        parser.print_help()
        sys.exit(1)

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
