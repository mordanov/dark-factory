#!/usr/bin/env python3
"""SQLite-backed agent activity recorder and HTML report generator.

This tool stores task-level reporting events for agent work and produces
human-facing summaries. It intentionally uses SQLite so the data stays local to
this repository and does not require database credentials.
"""

from __future__ import annotations

import argparse
import html
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, cast

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "agent_metrics.sqlite3"
DEFAULT_HTML_PATH = BASE_DIR / "report.html"


@dataclass(frozen=True)
class AgentEvent:
    timestamp: str
    agent_name: str
    feature_name: str
    short_task_description: str
    time_spent_seconds: int
    tokens_spent: Optional[int]
    model_used: str
    task_status: str = "completed"
    token_source: str = "self-reported"
    notes: str = ""
    started_at: str = ""
    finished_at: str = ""
    created_at: str = ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso8601(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def resolve_db_path(value: Optional[str]) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return DEFAULT_DB_PATH


def resolve_html_path(value: Optional[str]) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return DEFAULT_HTML_PATH


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            timestamp TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            feature_name TEXT NOT NULL,
            short_task_description TEXT NOT NULL,
            time_spent_seconds INTEGER NOT NULL CHECK(time_spent_seconds >= 0),
            tokens_spent INTEGER CHECK(tokens_spent IS NULL OR tokens_spent >= 0),
            model_used TEXT NOT NULL,
            task_status TEXT NOT NULL DEFAULT 'completed',
            token_source TEXT NOT NULL DEFAULT 'self-reported',
            notes TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_feature ON events(feature_name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_model ON events(model_used)"
    )


def compute_time_spent_seconds(
    *,
    time_spent_seconds: Optional[int] = None,
    time_spent_minutes: Optional[float] = None,
    started_at: str = "",
    finished_at: str = "",
) -> int:
    if time_spent_seconds is not None:
        if time_spent_seconds < 0:
            raise ValueError("time spent seconds must be non-negative")
        return time_spent_seconds

    if time_spent_minutes is not None:
        if time_spent_minutes < 0:
            raise ValueError("time spent minutes must be non-negative")
        return int(round(time_spent_minutes * 60))

    if started_at and finished_at:
        start_dt = parse_iso8601(started_at)
        end_dt = parse_iso8601(finished_at)
        elapsed = (end_dt - start_dt).total_seconds()
        if elapsed < 0:
            raise ValueError("finished_at must be after started_at")
        return int(round(elapsed))

    raise ValueError(
        "provide time_spent_seconds, time_spent_minutes, or started_at and finished_at"
    )


def insert_event(conn: sqlite3.Connection, event: AgentEvent) -> None:
    init_db(conn)
    conn.execute(
        """
        INSERT INTO events (
            timestamp, agent_name, feature_name, short_task_description,
            time_spent_seconds, tokens_spent, model_used, task_status,
            token_source, notes, started_at, finished_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.timestamp,
            event.agent_name,
            event.feature_name,
            event.short_task_description,
            event.time_spent_seconds,
            event.tokens_spent,
            event.model_used,
            event.task_status,
            event.token_source,
            event.notes,
            event.started_at,
            event.finished_at,
            event.created_at or utc_now_iso(),
        ),
    )
    conn.commit()


def fetch_events(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    init_db(conn)
    return list(
        conn.execute(
            """
            SELECT timestamp, agent_name, feature_name, short_task_description,
                   time_spent_seconds, tokens_spent, model_used, task_status,
                   token_source, notes, started_at, finished_at, created_at
            FROM events
            ORDER BY timestamp, id
            """
        )
    )


def format_duration(seconds: int) -> str:
    minutes, remainder = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {remainder}s"
    if minutes:
        return f"{minutes}m {remainder}s"
    return f"{remainder}s"


def aggregate_events(events: Iterable[sqlite3.Row]) -> dict[str, object]:
    by_agent: dict[str, dict[str, int]] = defaultdict(lambda: {"seconds": 0, "tokens": 0, "events": 0, "unknown_tokens": 0})
    by_feature: dict[str, dict[str, int]] = defaultdict(lambda: {"seconds": 0, "tokens": 0, "events": 0, "unknown_tokens": 0})
    by_model: dict[str, dict[str, int]] = defaultdict(lambda: {"seconds": 0, "tokens": 0, "events": 0, "unknown_tokens": 0})

    total_seconds = 0
    total_tokens = 0
    total_events = 0
    unknown_token_events = 0

    rows = list(events)
    for row in rows:
        seconds = int(row["time_spent_seconds"])
        tokens = row["tokens_spent"]
        token_value = int(tokens) if tokens is not None else 0
        token_missing = tokens is None

        total_seconds += seconds
        total_tokens += token_value
        total_events += 1
        if token_missing:
            unknown_token_events += 1

        for group, key in (
            (by_agent, row["agent_name"]),
            (by_feature, row["feature_name"]),
            (by_model, row["model_used"]),
        ):
            group[key]["seconds"] += seconds
            group[key]["tokens"] += token_value
            group[key]["events"] += 1
            if token_missing:
                group[key]["unknown_tokens"] += 1

    reporting_gaps = analyze_reporting_gaps(rows)

    return {
        "events": rows,
        "by_agent": dict(sorted(by_agent.items())),
        "by_feature": dict(sorted(by_feature.items())),
        "by_model": dict(sorted(by_model.items())),
        "total_seconds": total_seconds,
        "total_tokens": total_tokens,
        "total_events": total_events,
        "unknown_token_events": unknown_token_events,
        "reporting_gaps": reporting_gaps,
    }


def analyze_reporting_gaps(events: Iterable[sqlite3.Row]) -> dict[str, object]:
    by_agent: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "events_needing_follow_up": 0,
            "missing_tokens": 0,
            "zero_time": 0,
            "non_self_reported": 0,
            "non_completed": 0,
        }
    )
    gap_events: list[dict[str, object]] = []

    for row in events:
        reasons: list[str] = []
        if int(row["time_spent_seconds"]) == 0:
            reasons.append("zero_time")
        if row["tokens_spent"] is None:
            reasons.append("missing_tokens")
        if str(row["token_source"]) != "self-reported":
            reasons.append(f"token_source={row['token_source']}")
        if str(row["task_status"]) != "completed":
            reasons.append(f"status={row['task_status']}")

        if not reasons:
            continue

        agent_stats = by_agent[str(row["agent_name"])]
        agent_stats["events_needing_follow_up"] += 1
        if "missing_tokens" in reasons:
            agent_stats["missing_tokens"] += 1
        if "zero_time" in reasons:
            agent_stats["zero_time"] += 1
        if str(row["token_source"]) != "self-reported":
            agent_stats["non_self_reported"] += 1
        if str(row["task_status"]) != "completed":
            agent_stats["non_completed"] += 1

        gap_events.append(
            {
                "timestamp": row["timestamp"],
                "agent_name": row["agent_name"],
                "feature_name": row["feature_name"],
                "short_task_description": row["short_task_description"],
                "reasons": reasons,
            }
        )

    return {
        "events_needing_follow_up": len(gap_events),
        "missing_tokens": sum(item["missing_tokens"] for item in by_agent.values()),
        "zero_time": sum(item["zero_time"] for item in by_agent.values()),
        "non_self_reported": sum(item["non_self_reported"] for item in by_agent.values()),
        "non_completed": sum(item["non_completed"] for item in by_agent.values()),
        "by_agent": dict(sorted(by_agent.items())),
        "events": gap_events,
    }


def build_html_report(aggregates: dict[str, object]) -> str:
    events = cast(list[sqlite3.Row], aggregates["events"])
    by_agent = cast(dict[str, dict[str, int]], aggregates["by_agent"])
    by_feature = cast(dict[str, dict[str, int]], aggregates["by_feature"])
    by_model = cast(dict[str, dict[str, int]], aggregates["by_model"])
    reporting_gaps = cast(dict[str, object], aggregates["reporting_gaps"])
    gap_by_agent = cast(dict[str, dict[str, int]], reporting_gaps["by_agent"])
    gap_events = cast(list[dict[str, object]], reporting_gaps["events"])

    def table_rows(mapping: dict[str, dict[str, int]]) -> str:
        rows = []
        for name, stats in mapping.items():
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(name))}</td>"
                f"<td>{stats['events']}</td>"
                f"<td>{format_duration(stats['seconds'])}</td>"
                f"<td>{stats['tokens']}</td>"
                f"<td>{stats['unknown_tokens']}</td>"
                "</tr>"
            )
        return "\n".join(rows) or "<tr><td colspan='5'>No data</td></tr>"

    event_rows = []
    for row in events:
        event_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row['timestamp']))}</td>"
            f"<td>{html.escape(str(row['agent_name']))}</td>"
            f"<td>{html.escape(str(row['feature_name']))}</td>"
            f"<td>{html.escape(str(row['short_task_description']))}</td>"
            f"<td>{format_duration(int(row['time_spent_seconds']))}</td>"
            f"<td>{'' if row['tokens_spent'] is None else row['tokens_spent']}</td>"
            f"<td>{html.escape(str(row['model_used']))}</td>"
            f"<td>{html.escape(str(row['task_status']))}</td>"
            f"<td>{html.escape(str(row['token_source']))}</td>"
            f"<td>{html.escape(str(row['notes']))}</td>"
            "</tr>"
        )

    gap_rows = []
    for agent_name, stats in gap_by_agent.items():
        gap_rows.append(
            "<tr>"
            f"<td>{html.escape(str(agent_name))}</td>"
            f"<td>{stats['events_needing_follow_up']}</td>"
            f"<td>{stats['missing_tokens']}</td>"
            f"<td>{stats['zero_time']}</td>"
            f"<td>{stats['non_self_reported']}</td>"
            f"<td>{stats['non_completed']}</td>"
            "</tr>"
        )

    gap_event_rows = []
    for row in gap_events:
        gap_event_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row['timestamp']))}</td>"
            f"<td>{html.escape(str(row['agent_name']))}</td>"
            f"<td>{html.escape(str(row['feature_name']))}</td>"
            f"<td>{html.escape(str(row['short_task_description']))}</td>"
            f"<td>{html.escape(', '.join(str(reason) for reason in cast(list[str], row['reasons'])))}</td>"
            "</tr>"
        )

    total_events = cast(int, aggregates["total_events"])
    total_seconds = cast(int, aggregates["total_seconds"])
    total_tokens = cast(int, aggregates["total_tokens"])
    unknown_token_events = cast(int, aggregates["unknown_token_events"])
    events_needing_follow_up = cast(int, reporting_gaps["events_needing_follow_up"])
    zero_time_events = cast(int, reporting_gaps["zero_time"])
    missing_token_events = cast(int, reporting_gaps["missing_tokens"])
    non_self_reported_events = cast(int, reporting_gaps["non_self_reported"])

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Project Administrator Report</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 24px; color: #1f2937; }}
    h1, h2 {{ margin-bottom: 0.25rem; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 16px 0 24px; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 12px; padding: 16px; background: #f9fafb; }}
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0 28px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; vertical-align: top; text-align: left; }}
    th {{ background: #f3f4f6; }}
    .note {{ color: #6b7280; font-size: 0.95rem; }}
    .small {{ font-size: 0.9rem; }}
    .warning {{ color: #92400e; background: #fffbeb; border-color: #f59e0b; }}
  </style>
</head>
<body>
  <h1>Project Administrator Report</h1>
  <p class="note">Generated from the local SQLite metrics database.</p>

  <section class="summary">
    <div class="card"><strong>Total events</strong><div>{total_events}</div></div>
    <div class="card"><strong>Total time</strong><div>{format_duration(total_seconds)}</div></div>
    <div class="card"><strong>Total tokens</strong><div>{total_tokens}</div></div>
    <div class="card"><strong>Events with unknown tokens</strong><div>{unknown_token_events}</div></div>
  </section>

  <section class="summary">
    <div class="card warning"><strong>Events needing follow-up</strong><div>{events_needing_follow_up}</div></div>
    <div class="card warning"><strong>Zero-time events</strong><div>{zero_time_events}</div></div>
    <div class="card warning"><strong>Missing-token events</strong><div>{missing_token_events}</div></div>
    <div class="card warning"><strong>Non-self-reported events</strong><div>{non_self_reported_events}</div></div>
  </section>

  <h2>By Agent</h2>
  <table>
    <thead><tr><th>Agent</th><th>Events</th><th>Time</th><th>Tokens</th><th>Unknown Token Entries</th></tr></thead>
    <tbody>{table_rows(by_agent)}</tbody>
  </table>

  <h2>By Feature</h2>
  <table>
    <thead><tr><th>Feature</th><th>Events</th><th>Time</th><th>Tokens</th><th>Unknown Token Entries</th></tr></thead>
    <tbody>{table_rows(by_feature)}</tbody>
  </table>

  <h2>By Model</h2>
  <table>
    <thead><tr><th>Model</th><th>Events</th><th>Time</th><th>Tokens</th><th>Unknown Token Entries</th></tr></thead>
    <tbody>{table_rows(by_model)}</tbody>
  </table>

  <h2>Reporting Gaps by Agent</h2>
  <table>
    <thead><tr><th>Agent</th><th>Events Needing Follow-up</th><th>Missing Tokens</th><th>Zero Time</th><th>Non-self-reported</th><th>Non-completed Status</th></tr></thead>
    <tbody>{''.join(gap_rows) if gap_rows else '<tr><td colspan="6">No reporting gaps detected</td></tr>'}</tbody>
  </table>

  <h2>Events Needing Follow-up</h2>
  <table class="small">
    <thead>
      <tr>
        <th>Timestamp</th><th>Agent</th><th>Feature</th><th>Task</th><th>Gap Reasons</th>
      </tr>
    </thead>
    <tbody>
      {''.join(gap_event_rows) if gap_event_rows else '<tr><td colspan="5">No follow-up required</td></tr>'}
    </tbody>
  </table>

  <h2>Event Log</h2>
  <table class="small">
    <thead>
      <tr>
        <th>Timestamp</th><th>Agent</th><th>Feature</th><th>Task</th><th>Time</th><th>Tokens</th><th>Model</th><th>Status</th><th>Token Source</th><th>Notes</th>
      </tr>
    </thead>
    <tbody>
      {''.join(event_rows) if event_rows else '<tr><td colspan="10">No events recorded</td></tr>'}
    </tbody>
  </table>
</body>
</html>
"""


def print_summary(aggregates: dict[str, object]) -> None:
    total_events = cast(int, aggregates["total_events"])
    total_seconds = cast(int, aggregates["total_seconds"])
    total_tokens = cast(int, aggregates["total_tokens"])
    unknown_token_events = cast(int, aggregates["unknown_token_events"])
    reporting_gaps = cast(dict[str, object], aggregates["reporting_gaps"])
    by_agent = cast(dict[str, dict[str, int]], aggregates["by_agent"])
    by_feature = cast(dict[str, dict[str, int]], aggregates["by_feature"])
    by_model = cast(dict[str, dict[str, int]], aggregates["by_model"])

    print(f"Events: {total_events}")
    print(f"Time: {format_duration(total_seconds)}")
    print(f"Tokens: {total_tokens}")
    print(f"Unknown token entries: {unknown_token_events}")
    print(
        f"Events needing follow-up: {cast(int, reporting_gaps['events_needing_follow_up'])}"
    )
    print()
    print("By agent:")
    for name, stats in by_agent.items():
        print(
            f"  - {name}: {stats['events']} events, {format_duration(stats['seconds'])}, {stats['tokens']} tokens"
        )
    print()
    print("By feature:")
    for name, stats in by_feature.items():
        print(
            f"  - {name}: {stats['events']} events, {format_duration(stats['seconds'])}, {stats['tokens']} tokens"
        )
    print()
    print("By model:")
    for name, stats in by_model.items():
        print(
            f"  - {name}: {stats['events']} events, {format_duration(stats['seconds'])}, {stats['tokens']} tokens"
        )


def print_reporting_gaps(aggregates: dict[str, object]) -> None:
    reporting_gaps = cast(dict[str, object], aggregates["reporting_gaps"])
    gap_by_agent = cast(dict[str, dict[str, int]], reporting_gaps["by_agent"])
    gap_events = cast(list[dict[str, object]], reporting_gaps["events"])

    print(f"Events needing follow-up: {cast(int, reporting_gaps['events_needing_follow_up'])}")
    print(f"Missing tokens: {cast(int, reporting_gaps['missing_tokens'])}")
    print(f"Zero-time events: {cast(int, reporting_gaps['zero_time'])}")
    print(f"Non-self-reported events: {cast(int, reporting_gaps['non_self_reported'])}")
    print(f"Non-completed status events: {cast(int, reporting_gaps['non_completed'])}")

    if not gap_by_agent:
        print()
        print("No reporting gaps detected.")
        return

    print()
    print("By agent:")
    for name, stats in gap_by_agent.items():
        print(
            "  - "
            f"{name}: {stats['events_needing_follow_up']} follow-up, "
            f"missing_tokens={stats['missing_tokens']}, "
            f"zero_time={stats['zero_time']}, "
            f"non_self_reported={stats['non_self_reported']}, "
            f"non_completed={stats['non_completed']}"
        )

    print()
    print("Detailed events:")
    for row in gap_events:
        print(
            "  - "
            f"{row['timestamp']} | {row['agent_name']} | {row['feature_name']} | "
            f"{row['short_task_description']} | {', '.join(cast(list[str], row['reasons']))}"
        )


def add_record_args(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("record", help="Insert a completed task event")
    parser.add_argument("--agent-name", required=True)
    parser.add_argument("--feature-name", required=True)
    parser.add_argument("--task-description", required=True)
    parser.add_argument("--model-used", required=True)
    parser.add_argument("--time-spent-seconds", type=int)
    parser.add_argument("--time-spent-minutes", type=float)
    parser.add_argument("--tokens-spent", type=int)
    parser.add_argument("--token-source", default="self-reported")
    parser.add_argument("--status", default="completed")
    parser.add_argument("--timestamp")
    parser.add_argument("--started-at", default="")
    parser.add_argument("--finished-at", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--db", dest="db_path")
    parser.set_defaults(command="record")


def add_report_args(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("report-html", help="Generate a human-facing HTML report")
    parser.add_argument("--db", dest="db_path")
    parser.add_argument("--output", dest="output_path")
    parser.set_defaults(command="report-html")


def add_summary_args(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("summary", help="Print a text summary")
    parser.add_argument("--db", dest="db_path")
    parser.set_defaults(command="summary")


def add_gaps_args(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("gaps", help="Print reporting gaps that need follow-up")
    parser.add_argument("--db", dest="db_path")
    parser.set_defaults(command="gaps")


def add_init_args(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("init", help="Initialize the SQLite database")
    parser.add_argument("--db", dest="db_path")
    parser.set_defaults(command="init")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_init_args(subparsers)
    add_record_args(subparsers)
    add_summary_args(subparsers)
    add_gaps_args(subparsers)
    add_report_args(subparsers)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    db_path = resolve_db_path(getattr(args, "db_path", None))
    conn = connect(db_path)
    init_db(conn)

    if args.command == "init":
        print(f"Initialized {db_path}")
        return 0

    if args.command == "record":
        try:
            time_spent_seconds = compute_time_spent_seconds(
                time_spent_seconds=args.time_spent_seconds,
                time_spent_minutes=args.time_spent_minutes,
                started_at=args.started_at,
                finished_at=args.finished_at,
            )
        except ValueError as exc:
            parser.error(str(exc))
            return 2

        timestamp = args.timestamp or utc_now_iso()

        event = AgentEvent(
            timestamp=timestamp,
            agent_name=args.agent_name,
            feature_name=args.feature_name,
            short_task_description=args.task_description,
            time_spent_seconds=time_spent_seconds,
            tokens_spent=args.tokens_spent,
            model_used=args.model_used,
            task_status=args.status,
            token_source=args.token_source,
            notes=args.notes,
            started_at=args.started_at,
            finished_at=args.finished_at,
            created_at=utc_now_iso(),
        )
        insert_event(conn, event)
        print(
            f"Recorded event for {event.agent_name} ({event.feature_name}) at {event.timestamp}"
        )
        return 0

    aggregates = aggregate_events(fetch_events(conn))

    if args.command == "summary":
        print_summary(aggregates)
        return 0

    if args.command == "gaps":
        print_reporting_gaps(aggregates)
        return 0

    if args.command == "report-html":
        output_path = resolve_html_path(getattr(args, "output_path", None))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(build_html_report(aggregates), encoding="utf-8")
        print(f"Wrote HTML report to {output_path}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
