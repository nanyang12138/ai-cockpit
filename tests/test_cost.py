"""B.3 cost-aggregator tests (fixture DBs built in-process; no real LLM)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.sqlite import SqliteSaver

from ai_cockpit.cli import main
from ai_cockpit.cost import KNOWN_METRIC_KEYS, aggregate, render_json, render_text
from ai_cockpit.cost import _missing as missing_keys


def _put(saver: SqliteSaver, tid: str, channels: dict,
         *, ts: str | None = None) -> None:
    cp = empty_checkpoint()
    cp["channel_values"] = channels
    if ts is not None:
        cp["ts"] = ts
    saver.put({"configurable": {"thread_id": tid, "checkpoint_ns": ""}}, cp, {}, {})


@pytest.fixture()
def fixture_db(tmp_path: Path) -> Iterator[Path]:
    """Two threads: aider (yesterday), cursor (now, with one unknown key)."""
    db = tmp_path / "checkpoints.sqlite"
    conn = sqlite3.connect(str(db), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    _put(saver, "aider-thread", {"metrics": {
        "tokens_sent": 100.0, "tokens_received": 200.0,
        "cost_message_usd": 0.001, "cost_session_usd": 0.42,
    }}, ts=yesterday)
    _put(saver, "cursor-thread", {"metrics": {
        "input_tokens": 1000.0, "output_tokens": 500.0,
        "cache_read_tokens": 50.0, "cache_write_tokens": 25.0,
        "experimental_key": 7.0,
    }})
    conn.close()
    yield db


def test_aggregate_empty_db(tmp_path: Path) -> None:
    """Missing DB == fresh-repo state; aggregator must not raise."""
    report = aggregate(tmp_path / "no_such.sqlite")
    assert report.threads == [] and report.totals == {}
    assert report.threads_matched == 0 and report.threads_seen == 0


def test_aggregate_known_unknown_totals(fixture_db: Path) -> None:
    report = aggregate(fixture_db)
    assert report.threads_matched == 2
    threads = {t.thread_id: t for t in report.threads}

    aider = threads["aider-thread"]
    assert aider.metrics["tokens_sent"] == 100.0
    assert aider.metrics["cost_session_usd"] == pytest.approx(0.42)
    assert "input_tokens" in missing_keys(aider.metrics)
    assert aider.unknown == {}

    cursor = threads["cursor-thread"]
    assert cursor.metrics["input_tokens"] == 1000.0
    assert cursor.unknown == {"experimental_key": 7.0}
    assert "tokens_sent" in missing_keys(cursor.metrics)

    assert report.totals["tokens_sent"] == 100.0
    assert report.totals["input_tokens"] == 1000.0
    assert report.totals["cost_session_usd"] == pytest.approx(0.42)
    assert report.totals["experimental_key"] == 7.0


def test_since_filter(fixture_db: Path) -> None:
    """``--since today`` keeps cursor-thread (now), drops aider-thread (yesterday)."""
    report = aggregate(fixture_db, since="today")
    assert [t.thread_id for t in report.threads] == ["cursor-thread"]
    assert report.threads_matched == 1 and report.threads_seen == 2
    with pytest.raises(ValueError, match="since"):
        aggregate(fixture_db, since="not-a-date")


def test_malformed_metrics_do_not_poison_sums(tmp_path: Path) -> None:
    """String/None/bool under known keys must drop, not be counted."""
    db = tmp_path / "bad.sqlite"
    conn = sqlite3.connect(str(db), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    _put(saver, "t1", {"metrics": {"tokens_sent": "x", "tokens_received": True,
                                    "cost_session_usd": None}})
    _put(saver, "t2", {"metrics": "this is not a dict"})
    _put(saver, "t3", {})
    conn.close()
    report = aggregate(db)
    assert report.threads_matched == 3
    for thread in report.threads:
        assert thread.metrics == {} and thread.unknown == {}
        assert len(missing_keys(thread.metrics)) == len(KNOWN_METRIC_KEYS)


def test_render_text_and_json(fixture_db: Path) -> None:
    body = "\n".join(render_text(aggregate(fixture_db)))
    assert body.startswith("db: ")
    assert "thread aider-thread" in body and "thread cursor-thread" in body
    assert "cost=$0.4200" in body and "cost=N/A (tokens-only)" in body
    assert body.splitlines()[-1].startswith("totals:")

    payload = render_json(aggregate(fixture_db))
    assert payload["schema_version"] == 1 and set(payload) >= {
        "db_path", "threads", "totals", "threads_matched",
        "threads_seen", "schema_version"}
    row = next(t for t in payload["threads"]
               if t["thread_id"] == "cursor-thread")
    assert row["metrics"]["input_tokens"] == 1000.0
    assert row["unknown"] == {"experimental_key": 7.0}
    assert row["keys_missing"]


def test_cli_cost(fixture_db: Path, tmp_path: Path) -> None:
    """One CLI test covers: json happy path, missing DB exit-0, invalid --since."""
    runner = CliRunner()
    ok = runner.invoke(main, [
        "cost", "--root", str(tmp_path),
        "--checkpoint-db", str(fixture_db), "--format", "json"])
    assert ok.exit_code == 0, ok.output
    payload = json.loads(ok.output)
    assert payload["schema_version"] == 1 and payload["threads_matched"] == 2

    missing = runner.invoke(main, ["cost", "--root", str(tmp_path)])
    assert missing.exit_code == 0
    assert "no checkpoint db found" in missing.output

    bad = runner.invoke(main, [
        "cost", "--root", str(tmp_path),
        "--checkpoint-db", str(fixture_db), "--since", "bogus"])
    assert bad.exit_code == 2 and "since" in bad.output.lower()
