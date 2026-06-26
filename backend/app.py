from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv(override=os.getenv("DOTENV_OVERRIDE", "true").lower() == "true")

from . import database as db
from .pipeline import ensure_report_exists, run_daily_update


class SourcePayload(BaseModel):
    name: str = Field(min_length=1)
    source_type: str = "公开资讯平台"
    url: str = Field(min_length=4)
    adapter: str = "html"
    enabled: bool = True
    notes: str = ""


class SourceTogglePayload(BaseModel):
    enabled: bool


app = FastAPI(title="世界城招商热点监测", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    db.init_db()
    db.mark_stale_running_jobs(int(os.getenv("RUNNING_JOB_STALE_MINUTES", "180")))
    if scheduler_enabled():
        if not should_run_scheduled_catchup():
            ensure_report_exists()
        start_scheduler_once()
    else:
        ensure_report_exists()


@app.get("/api/health")
def health() -> dict:
    status = scheduler_status()
    return {
        "ok": True,
        "service": "world-city-hotspot-monitor",
        "scheduler": status["enabled"],
        "scheduler_status": status,
        "timezone": os.getenv("APP_TIMEZONE", "Asia/Shanghai"),
        "daily_update_start": os.getenv("DAILY_UPDATE_START", "06:30"),
        "ai_provider": os.getenv("AI_PROVIDER", "rules"),
        "ai_multi_agent": os.getenv("AI_MULTI_AGENT", "true").lower() == "true",
        "deepseek_flash_model": os.getenv("DEEPSEEK_MODEL_FLASH", "deepseek-v4-flash"),
        "deepseek_pro_model": os.getenv("DEEPSEEK_MODEL_PRO", "deepseek-v4-pro"),
    }


@app.get("/api/dashboard")
def dashboard(date: Optional[str] = None) -> dict:
    report = db.get_report(date)
    hotspots = db.list_hotspots(date)
    jobs = db.list_jobs(6)
    sources = db.list_sources()
    if report is None:
        return {
            "report": None,
            "hotspots": [],
            "jobs": jobs,
            "sources": sources,
            "auth": auth_status(),
            "scheduler": scheduler_status(),
        }
    return {
        "report": report,
        "hotspots": hotspots,
        "jobs": jobs,
        "sources": sources,
        "auth": auth_status(),
        "scheduler": scheduler_status(),
    }


@app.get("/api/reports")
def reports() -> dict:
    return {"reports": db.list_reports()}


@app.get("/api/hotspots/{hotspot_id}")
def hotspot(hotspot_id: int) -> dict:
    item = db.get_hotspot(hotspot_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Hotspot not found")
    return {"hotspot": item}


@app.get("/api/sources")
def sources() -> dict:
    return {"sources": db.list_sources()}


@app.post("/api/sources")
def create_source(payload: SourcePayload) -> dict:
    return {"source": db.add_source(payload.model_dump())}


@app.patch("/api/sources/{source_id}/enabled")
def toggle_source(source_id: int, payload: SourceTogglePayload) -> dict:
    source = db.set_source_enabled(source_id, payload.enabled)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"source": source}


@app.get("/api/jobs")
def jobs() -> dict:
    return {"jobs": db.list_jobs(30)}


@app.post("/api/jobs/run")
def run_job(background_tasks: BackgroundTasks) -> dict:
    background_tasks.add_task(run_daily_update, "manual")
    return {"status": "queued", "message": "更新任务已加入队列"}


@app.post("/api/jobs/run-sync")
def run_job_sync() -> dict:
    return run_daily_update("manual_sync")


@app.get("/api/auth/status")
def auth_status() -> dict:
    return {
        "enabled": False,
        "mode": "reserved",
        "message": "第一版暂不启用登录，接口与权限角色已预留。",
        "roles": ["viewer", "editor", "admin"],
    }


_scheduler_started = False
_scheduler_state_lock = threading.Lock()
_scheduler_state: dict[str, object] = {
    "started": False,
    "last_check_at": "",
    "next_run_at": "",
    "last_run_at": "",
    "last_result_status": "",
    "last_result_trigger": "",
    "last_skip_reason": "",
    "last_error": "",
}


def scheduler_enabled() -> bool:
    return os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"


def app_timezone() -> ZoneInfo:
    return ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Shanghai"))


def _utc_iso(value: datetime) -> str:
    return value.astimezone(dt_timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _local_iso(value: datetime) -> str:
    return value.astimezone(app_timezone()).replace(microsecond=0).isoformat()


def _update_scheduler_state(**values: object) -> None:
    with _scheduler_state_lock:
        _scheduler_state.update(values)


def scheduler_status() -> dict:
    latest = db.latest_job("daily_hotspot_update")
    with _scheduler_state_lock:
        state = dict(_scheduler_state)
    if not state.get("next_run_at") and scheduler_enabled():
        state["next_run_at"] = _local_iso(next_run_datetime(os.getenv("DAILY_UPDATE_START", "06:30")))
    return {
        "enabled": scheduler_enabled(),
        "started": bool(state.get("started")),
        "daily_update_start": os.getenv("DAILY_UPDATE_START", "06:30"),
        "timezone": os.getenv("APP_TIMEZONE", "Asia/Shanghai"),
        "next_run_at": state.get("next_run_at", ""),
        "last_check_at": state.get("last_check_at", ""),
        "last_run_at": state.get("last_run_at", ""),
        "last_result_status": state.get("last_result_status", ""),
        "last_result_trigger": state.get("last_result_trigger", ""),
        "last_skip_reason": state.get("last_skip_reason", ""),
        "last_error": state.get("last_error", ""),
        "latest_job": latest,
    }


def start_scheduler_once() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    _update_scheduler_state(started=True, last_error="")
    thread = threading.Thread(target=scheduler_loop, name="daily-hotspot-scheduler", daemon=True)
    thread.start()


def scheduler_loop() -> None:
    while True:
        try:
            run_scheduled_catchup_if_needed()
            next_at = next_run_datetime(os.getenv("DAILY_UPDATE_START", "06:30"))
            _update_scheduler_state(next_run_at=_local_iso(next_at), last_check_at=_local_iso(datetime.now(app_timezone())))
            time.sleep(max(1, int((next_at - datetime.now(app_timezone())).total_seconds())))
            run_scheduled_update("scheduled")
            time.sleep(60)
        except Exception as exc:  # noqa: BLE001
            _update_scheduler_state(last_error=str(exc), last_check_at=_local_iso(datetime.now(app_timezone())))
            time.sleep(60)


def run_scheduled_catchup_if_needed(now: datetime | None = None) -> dict | None:
    if not should_run_scheduled_catchup(now):
        return None
    return run_scheduled_update("scheduled_catchup")


def run_scheduled_update(trigger: str) -> dict:
    now = datetime.now(app_timezone())
    _update_scheduler_state(last_run_at=_local_iso(now), last_result_trigger=trigger, last_skip_reason="", last_error="")
    result = run_daily_update(trigger)
    _update_scheduler_state(
        last_result_status=result.get("status", ""),
        last_result_trigger=trigger,
        last_skip_reason=result.get("reason", ""),
        last_check_at=_local_iso(datetime.now(app_timezone())),
    )
    return result


def should_run_scheduled_catchup(now: datetime | None = None) -> bool:
    current = now or datetime.now(app_timezone())
    if current.tzinfo is None:
        current = current.replace(tzinfo=app_timezone())
    scheduled_start = scheduled_start_for_day(current, os.getenv("DAILY_UPDATE_START", "06:30"))
    if current < scheduled_start:
        return False
    return not db.has_successful_job_since("daily_hotspot_update", _utc_iso(scheduled_start))


def seconds_until_next_run(hhmm: str) -> int:
    now = datetime.now(app_timezone())
    target = next_run_datetime(hhmm, now)
    return max(1, int((target - now).total_seconds()))


def next_run_datetime(hhmm: str, now: datetime | None = None) -> datetime:
    current = now or datetime.now(app_timezone())
    if current.tzinfo is None:
        current = current.replace(tzinfo=app_timezone())
    target = scheduled_start_for_day(current, hhmm)
    if target <= current:
        target += timedelta(days=1)
    return target


def scheduled_start_for_day(current: datetime, hhmm: str) -> datetime:
    hour, minute = [int(part) for part in hhmm.split(":", 1)]
    return current.astimezone(app_timezone()).replace(hour=hour, minute=minute, second=0, microsecond=0)


dist_dir = Path(__file__).resolve().parents[1] / "dist"
if dist_dir.exists():
    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")


@app.get("/{path:path}")
def serve_app(path: str) -> FileResponse:
    index = dist_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Frontend has not been built yet")
