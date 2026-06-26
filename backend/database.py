from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .sample_data import DEFAULT_SOURCES


def data_dir() -> Path:
    root = Path(os.getenv("DATA_DIR", "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def db_path() -> Path:
    return data_dir() / "hotspots.db"


@contextmanager
def connect() -> Iterable[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for key in (
        "tags_json",
        "evidence_json",
        "source_links_json",
        "coverage_json",
        "insights_json",
        "briefing_json",
        "logs_json",
        "counters_json",
    ):
        if key in item and item[key]:
            item[key.replace("_json", "")] = json.loads(item[key])
            item.pop(key, None)
    return item


def rows_to_list(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in rows if row is not None]


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  adapter TEXT NOT NULL DEFAULT 'html',
  enabled INTEGER NOT NULL DEFAULT 1,
  notes TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  excerpt TEXT DEFAULT '',
  content TEXT DEFAULT '',
  published_at TEXT DEFAULT '',
  date_status TEXT DEFAULT '',
  coverage_date TEXT DEFAULT '',
  fetched_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'fetched'
);

CREATE TABLE IF NOT EXISTS hotspots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_date TEXT NOT NULL,
  article_id INTEGER NOT NULL REFERENCES raw_articles(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  brand_name TEXT NOT NULL,
  category TEXT NOT NULL,
  signal_type TEXT NOT NULL,
  regions TEXT DEFAULT '全国/国际',
  source_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_links_json TEXT NOT NULL DEFAULT '[]',
  published_at TEXT DEFAULT '',
  date_status TEXT DEFAULT '',
  ai_summary TEXT NOT NULL,
  leasing_insight TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  confidence INTEGER NOT NULL,
  relevance INTEGER NOT NULL,
  opportunity_score INTEGER NOT NULL,
  breakout_score INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(report_date, article_id)
);

CREATE TABLE IF NOT EXISTS daily_reports (
  report_date TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  total_articles INTEGER NOT NULL DEFAULT 0,
  total_hotspots INTEGER NOT NULL DEFAULT 0,
  published_at TEXT NOT NULL,
  coverage_json TEXT NOT NULL,
  insights_json TEXT NOT NULL,
  briefing_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS crawl_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL,
  trigger TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT DEFAULT '',
  logs_json TEXT NOT NULL,
  counters_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE,
  role TEXT DEFAULT 'viewer',
  status TEXT DEFAULT 'reserved',
  created_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _parse_utc(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _ensure_schema_columns(conn)
        count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        if count == 0:
            for source in DEFAULT_SOURCES:
                _insert_default_source(conn, source)
        else:
            for source in DEFAULT_SOURCES:
                exists = conn.execute("SELECT 1 FROM sources WHERE url = ?", (source["url"],)).fetchone()
                if not exists:
                    _insert_default_source(conn, source)


def _insert_default_source(conn: sqlite3.Connection, source: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO sources (name, source_type, url, adapter, enabled, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source["name"],
            source["source_type"],
            source["url"],
            source["adapter"],
            source["enabled"],
            source["notes"],
            now_iso(),
            now_iso(),
        ),
    )


def _ensure_schema_columns(conn: sqlite3.Connection) -> None:
    daily_columns = _table_columns(conn, "daily_reports")
    if "briefing_json" not in daily_columns:
        conn.execute("ALTER TABLE daily_reports ADD COLUMN briefing_json TEXT NOT NULL DEFAULT '{}'")
    raw_columns = _table_columns(conn, "raw_articles")
    if "date_status" not in raw_columns:
        conn.execute("ALTER TABLE raw_articles ADD COLUMN date_status TEXT DEFAULT ''")
    if "coverage_date" not in raw_columns:
        conn.execute("ALTER TABLE raw_articles ADD COLUMN coverage_date TEXT DEFAULT ''")
    conn.execute(
        """
        UPDATE raw_articles
        SET date_status = CASE
          WHEN COALESCE(published_at, '') = '' THEN 'unverified'
          ELSE 'legacy'
        END
        WHERE COALESCE(date_status, '') = ''
        """
    )
    hotspot_columns = _table_columns(conn, "hotspots")
    if "source_links_json" not in hotspot_columns:
        conn.execute("ALTER TABLE hotspots ADD COLUMN source_links_json TEXT NOT NULL DEFAULT '[]'")
    if "date_status" not in hotspot_columns:
        conn.execute("ALTER TABLE hotspots ADD COLUMN date_status TEXT DEFAULT ''")
    conn.execute(
        """
        UPDATE hotspots
        SET date_status = CASE
          WHEN COALESCE(published_at, '') = '' THEN 'unverified'
          ELSE 'legacy'
        END
        WHERE COALESCE(date_status, '') = ''
        """
    )


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def list_sources() -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_list(conn.execute("SELECT * FROM sources ORDER BY enabled DESC, id ASC").fetchall())


def enabled_sources() -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_list(conn.execute("SELECT * FROM sources WHERE enabled = 1 ORDER BY id ASC").fetchall())


def add_source(payload: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        now = now_iso()
        conn.execute(
            """
            INSERT INTO sources (name, source_type, url, adapter, enabled, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
              name = excluded.name,
              source_type = excluded.source_type,
              adapter = excluded.adapter,
              enabled = excluded.enabled,
              notes = excluded.notes,
              updated_at = excluded.updated_at
            """,
            (
                payload.get("name", "").strip() or "未命名信源",
                payload.get("source_type", "公开资讯平台").strip() or "公开资讯平台",
                payload.get("url", "").strip(),
                payload.get("adapter", "html").strip() or "html",
                1 if payload.get("enabled", True) else 0,
                payload.get("notes", "").strip(),
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM sources WHERE url = ?", (payload.get("url", "").strip(),)).fetchone()
        return row_to_dict(row)


def set_source_enabled(source_id: int, enabled: bool) -> dict[str, Any] | None:
    with connect() as conn:
        conn.execute(
            "UPDATE sources SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, now_iso(), source_id),
        )
        return row_to_dict(conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone())


def create_job(job_type: str, trigger: str) -> int:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO crawl_jobs (job_type, status, trigger, started_at, logs_json, counters_json)
            VALUES (?, 'running', ?, ?, '[]', '{}')
            """,
            (job_type, trigger, now_iso()),
        )
        return int(cursor.lastrowid)


def create_job_if_idle(job_type: str, trigger: str) -> tuple[int | None, dict[str, Any] | None]:
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        active = conn.execute(
            """
            SELECT * FROM crawl_jobs
            WHERE job_type = ? AND status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (job_type,),
        ).fetchone()
        if active:
            return None, row_to_dict(active)
        cursor = conn.execute(
            """
            INSERT INTO crawl_jobs (job_type, status, trigger, started_at, logs_json, counters_json)
            VALUES (?, 'running', ?, ?, '[]', '{}')
            """,
            (job_type, trigger, now_iso()),
        )
        return int(cursor.lastrowid), None


def finish_job(job_id: int, status: str, logs: list[str], counters: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE crawl_jobs
            SET status = ?, finished_at = ?, logs_json = ?, counters_json = ?
            WHERE id = ?
            """,
            (status, now_iso(), json.dumps(logs, ensure_ascii=False), json.dumps(counters, ensure_ascii=False), job_id),
        )


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_list(
            conn.execute("SELECT * FROM crawl_jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        )


def mark_stale_running_jobs(max_age_minutes: int = 180) -> int:
    cutoff_seconds = max_age_minutes * 60
    now = datetime.now(timezone.utc)
    marked = 0
    with connect() as conn:
        rows = conn.execute("SELECT * FROM crawl_jobs WHERE status = 'running'").fetchall()
        for row in rows:
            started = _parse_utc(row["started_at"])
            if started is None or (now - started).total_seconds() < cutoff_seconds:
                continue
            logs = json.loads(row["logs_json"] or "[]")
            logs.append("服务重启或任务超时，系统已自动标记为失败，可重新触发。")
            counters = json.loads(row["counters_json"] or "{}")
            counters["stale_marked"] = True
            conn.execute(
                """
                UPDATE crawl_jobs
                SET status = 'failed', finished_at = ?, logs_json = ?, counters_json = ?
                WHERE id = ?
                """,
                (now_iso(), json.dumps(logs, ensure_ascii=False), json.dumps(counters, ensure_ascii=False), row["id"]),
            )
            marked += 1
    return marked


def has_successful_job_since(job_type: str, since_iso: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM crawl_jobs
            WHERE job_type = ? AND status = 'success' AND started_at >= ?
            LIMIT 1
            """,
            (job_type, since_iso),
        ).fetchone()
        return row is not None


def latest_job(job_type: str | None = None) -> dict[str, Any] | None:
    with connect() as conn:
        if job_type:
            row = conn.execute(
                "SELECT * FROM crawl_jobs WHERE job_type = ? ORDER BY id DESC LIMIT 1",
                (job_type,),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM crawl_jobs ORDER BY id DESC LIMIT 1").fetchone()
        return row_to_dict(row)


def upsert_raw_article(article: dict[str, Any]) -> int:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO raw_articles (
              url, title, source_name, source_type, excerpt, content, published_at,
              date_status, coverage_date, fetched_at, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'fetched')
            ON CONFLICT(url) DO UPDATE SET
              title = excluded.title,
              source_name = excluded.source_name,
              source_type = excluded.source_type,
              excerpt = excluded.excerpt,
              content = excluded.content,
              published_at = excluded.published_at,
              date_status = excluded.date_status,
              coverage_date = excluded.coverage_date,
              fetched_at = excluded.fetched_at,
              status = 'fetched'
            """,
            (
                article["url"],
                article["title"],
                article.get("source_name", "未知来源"),
                article.get("source_type", "公开资讯平台"),
                article.get("excerpt", ""),
                article.get("content", ""),
                article.get("published_at", ""),
                article.get("date_status", ""),
                article.get("coverage_date", ""),
                now_iso(),
            ),
        )
        row = conn.execute("SELECT id FROM raw_articles WHERE url = ?", (article["url"],)).fetchone()
        return int(row["id"])


def replace_hotspots_for_date(report_date: str, rows: list[dict[str, Any]]) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM hotspots WHERE report_date = ?", (report_date,))
        for row in rows:
            conn.execute(
                """
                INSERT INTO hotspots (
                  report_date, article_id, title, brand_name, category, signal_type, regions,
                  source_name, source_type, source_url, source_links_json, published_at, date_status,
                  ai_summary, leasing_insight,
                  evidence_json, tags_json, confidence, relevance, opportunity_score, breakout_score, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_date,
                    row["article_id"],
                    row["title"],
                    row["brand_name"],
                    row["category"],
                    row["signal_type"],
                    row.get("regions", "全国/国际"),
                    row["source_name"],
                    row["source_type"],
                    row["source_url"],
                    json.dumps(row.get("source_links", []), ensure_ascii=False),
                    row.get("published_at", ""),
                    row.get("date_status", ""),
                    row["ai_summary"],
                    row["leasing_insight"],
                    json.dumps(row.get("evidence", []), ensure_ascii=False),
                    json.dumps(row.get("tags", []), ensure_ascii=False),
                    int(row["confidence"]),
                    int(row["relevance"]),
                    int(row["opportunity_score"]),
                    int(row["breakout_score"]),
                    now_iso(),
                ),
            )


def upsert_daily_report(
    report_date: str,
    total_articles: int,
    hotspots: list[dict[str, Any]],
    insights: list[dict[str, Any]],
    briefing: dict[str, Any] | None = None,
) -> None:
    coverage: dict[str, int] = {}
    for item in hotspots:
        coverage[item["source_type"]] = coverage.get(item["source_type"], 0) + 1
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO daily_reports (
              report_date, status, total_articles, total_hotspots, published_at,
              coverage_json, insights_json, briefing_json
            )
            VALUES (?, 'published', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_date) DO UPDATE SET
              status = 'published',
              total_articles = excluded.total_articles,
              total_hotspots = excluded.total_hotspots,
              published_at = excluded.published_at,
              coverage_json = excluded.coverage_json,
              insights_json = excluded.insights_json,
              briefing_json = excluded.briefing_json
            """,
            (
                report_date,
                total_articles,
                len(hotspots),
                now_iso(),
                json.dumps(coverage, ensure_ascii=False),
                json.dumps(insights, ensure_ascii=False),
                json.dumps(briefing or {}, ensure_ascii=False),
            ),
        )


def latest_report_date() -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT report_date FROM daily_reports ORDER BY report_date DESC LIMIT 1").fetchone()
        return row["report_date"] if row else None


def get_report(report_date: str | None = None) -> dict[str, Any] | None:
    date = report_date or latest_report_date()
    if not date:
        return None
    with connect() as conn:
        return row_to_dict(conn.execute("SELECT * FROM daily_reports WHERE report_date = ?", (date,)).fetchone())


def list_reports(limit: int = 30) -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_list(
            conn.execute("SELECT * FROM daily_reports ORDER BY report_date DESC LIMIT ?", (limit,)).fetchall()
        )


def list_hotspots(report_date: str | None = None) -> list[dict[str, Any]]:
    date = report_date or latest_report_date()
    if not date:
        return []
    with connect() as conn:
        return rows_to_list(
            conn.execute(
                """
                SELECT * FROM hotspots
                WHERE report_date = ?
                ORDER BY opportunity_score DESC, breakout_score DESC, confidence DESC, id ASC
                """,
                (date,),
            ).fetchall()
        )


def get_hotspot(hotspot_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        return row_to_dict(conn.execute("SELECT * FROM hotspots WHERE id = ?", (hotspot_id,)).fetchone())
