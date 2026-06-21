from __future__ import annotations

import tempfile
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import agent_metrics  # noqa: E402


class AgentMetricsTests(unittest.TestCase):
    def test_record_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "metrics.sqlite3"
            html_path = Path(tmp) / "report.html"

            conn = agent_metrics.connect(db_path)
            agent_metrics.init_db(conn)
            agent_metrics.insert_event(
                conn,
                agent_metrics.AgentEvent(
                    timestamp="2026-05-23T10:00:00+00:00",
                    agent_name="backend",
                    feature_name="ticket-management",
                    short_task_description="Implemented validation",
                    time_spent_seconds=1800,
                    tokens_spent=1200,
                    model_used="claude-3.7-sonnet",
                ),
            )
            agent_metrics.insert_event(
                conn,
                agent_metrics.AgentEvent(
                    timestamp="2026-05-23T11:00:00+00:00",
                    agent_name="project-administrator",
                    feature_name="reporting",
                    short_task_description="Generated human report",
                    time_spent_seconds=120,
                    tokens_spent=None,
                    model_used="claude-3.7-sonnet",
                    token_source="unknown",
                ),
            )

            rows = agent_metrics.fetch_events(conn)
            aggregates = agent_metrics.aggregate_events(rows)
            self.assertEqual(2, aggregates["total_events"])
            self.assertEqual(1920, aggregates["total_seconds"])
            self.assertEqual(1200, aggregates["total_tokens"])
            self.assertEqual(1, aggregates["unknown_token_events"])
            self.assertEqual(1, aggregates["reporting_gaps"]["events_needing_follow_up"])
            self.assertEqual(1, aggregates["reporting_gaps"]["missing_tokens"])
            self.assertEqual(1, aggregates["reporting_gaps"]["non_self_reported"])

            html = agent_metrics.build_html_report(aggregates)
            html_path.write_text(html, encoding="utf-8")
            self.assertIn("Project Administrator Report", html)
            self.assertIn("Reporting Gaps by Agent", html)
            self.assertIn("Events needing follow-up", html)
            self.assertIn("backend", html)
            self.assertIn("ticket-management", html)
            self.assertIn("Generated human report", html)

    def test_compute_time_spent_seconds_from_minutes(self) -> None:
        self.assertEqual(90, agent_metrics.compute_time_spent_seconds(time_spent_minutes=1.5))


if __name__ == "__main__":
    unittest.main()
