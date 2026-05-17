"""B.3 read-only cost aggregator (LangGraph checkpoint DB → per-thread sums)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_cockpit.checkpoint import open_checkpoint_saver

AIDER_KEYS = ("tokens_sent", "tokens_received", "cost_message_usd", "cost_session_usd")
CURSOR_KEYS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
KNOWN_METRIC_KEYS: frozenset[str] = frozenset(AIDER_KEYS + CURSOR_KEYS)
_TOKEN_KEYS = AIDER_KEYS[:2] + CURSOR_KEYS  # cost_* shown separately as cost=$…


@dataclass(frozen=True)
class ThreadCost:
    thread_id: str
    ts: str
    metrics: dict[str, float] = field(default_factory=dict)
    unknown: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CostReport:
    db_path: str
    threads: list[ThreadCost]
    totals: dict[str, float]
    threads_matched: int
    threads_seen: int


def _missing(metrics: dict[str, float]) -> list[str]:
    return sorted(k for k in KNOWN_METRIC_KEYS if k not in metrics)


def _parse_since(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    if raw.lower() == "today":
        return datetime.now(UTC).replace(hour=0, minute=0, second=0,
                                         microsecond=0)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            f"--since: cannot parse {value!r} (expected 'today', "
            "YYYY-MM-DD, or ISO-8601 datetime)") from exc
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _coerce_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _split_metrics(raw: Any) -> tuple[dict[str, float], dict[str, float]]:
    known: dict[str, float] = {}
    unknown: dict[str, float] = {}
    if not isinstance(raw, dict):
        return known, unknown
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        bucket = known if key in KNOWN_METRIC_KEYS else unknown
        bucket[str(key)] = bucket.get(str(key), 0.0) + float(value)
    return known, unknown


def aggregate(db_path: str | Path, *, since: str | None = None) -> CostReport:
    path = Path(db_path)
    if not path.is_file():
        return CostReport(str(path), [], {}, 0, 0)
    since_dt = _parse_since(since)
    threads: list[ThreadCost] = []
    totals: dict[str, float] = {}
    with open_checkpoint_saver(path) as saver:
        latest: dict[str, tuple[datetime | None, Any]] = {}
        for tup in saver.list(None):
            tid = tup.config.get("configurable", {}).get("thread_id")
            if not isinstance(tid, str) or not tid:
                continue
            ts = _coerce_ts(tup.checkpoint.get("ts"))
            cur = latest.get(tid)
            if cur is None or (ts is not None
                               and (cur[0] is None or ts > cur[0])):
                latest[tid] = (ts, tup)
        for tid, (ts, tup) in sorted(latest.items()):
            if since_dt is not None and (ts is None or ts < since_dt):
                continue
            channels = tup.checkpoint.get("channel_values") or {}
            known, unknown = _split_metrics(channels.get("metrics"))
            threads.append(ThreadCost(
                thread_id=tid,
                ts=ts.isoformat() if ts is not None else "",
                metrics=known, unknown=unknown))
            for k, v in {**known, **unknown}.items():
                totals[k] = totals.get(k, 0.0) + v
    return CostReport(str(path), threads, totals, len(threads), len(latest))


def _fmt_tokens(m: dict[str, float]) -> str:
    parts = [f"{k}={m[k]:.0f}" for k in _TOKEN_KEYS if k in m]
    return "tokens=" + ",".join(parts) if parts else "tokens=N/A"


def _fmt_cost(m: dict[str, float]) -> str:
    return (f"cost=${m['cost_session_usd']:.4f}" if "cost_session_usd" in m
            else "cost=N/A (tokens-only)")


def render_text(report: CostReport) -> list[str]:
    lines = [f"db: {report.db_path}"]
    if not report.threads:
        lines.append("no threads matched")
    for t in report.threads:
        extras: list[str] = []
        missing = _missing(t.metrics)
        if missing:
            extras.append(f"missing={','.join(missing)}")
        if t.unknown:
            extras.append(f"unknown={','.join(sorted(t.unknown))}")
        suffix = (" " + " ".join(extras)) if extras else ""
        lines.append(
            f"thread {t.thread_id} | ts {t.ts or '-'} | "
            f"{_fmt_tokens(t.metrics)} {_fmt_cost(t.metrics)} "
            f"coverage={len(t.metrics)}/{len(KNOWN_METRIC_KEYS)}{suffix}")
    lines.append(
        f"totals: {_fmt_tokens(report.totals)} {_fmt_cost(report.totals)} "
        f"threads_matched={report.threads_matched} "
        f"threads_seen={report.threads_seen}")
    return lines


def render_json(report: CostReport) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for t in report.threads:
        row: dict[str, Any] = {
            "thread_id": t.thread_id, "ts": t.ts,
            "metrics": dict(t.metrics), "keys_missing": _missing(t.metrics),
        }
        if t.unknown:
            row["unknown"] = dict(t.unknown)
        rows.append(row)
    return {
        "schema_version": 1, "db_path": report.db_path,
        "threads": rows, "totals": dict(report.totals),
        "threads_matched": report.threads_matched,
        "threads_seen": report.threads_seen,
    }
