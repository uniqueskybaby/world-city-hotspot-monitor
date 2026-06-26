from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DATA_DIR", str(PROJECT_ROOT / "data"))
os.environ.setdefault("DOTENV_OVERRIDE", "false")

from backend import database as db  # noqa: E402


def build_dashboard() -> dict:
    report = db.get_report()
    return {
        "report": report,
        "hotspots": db.list_hotspots(report["report_date"] if report else None),
        "jobs": db.list_jobs(6),
        "sources": db.list_sources(),
        "auth": {
            "enabled": False,
            "mode": "reserved",
            "message": "第一版暂不启用登录，接口与权限角色已预留。",
            "roles": ["viewer", "editor", "admin"],
        },
        "scheduler": {
            "enabled": False,
            "started": False,
            "daily_update_start": os.getenv("DAILY_UPDATE_START", "06:30"),
            "timezone": os.getenv("APP_TIMEZONE", "Asia/Shanghai"),
            "next_run_at": "",
            "last_check_at": "",
            "last_run_at": "",
            "last_result_status": "",
            "last_result_trigger": "",
            "last_skip_reason": "",
            "last_error": "",
            "latest_job": db.latest_job("daily_hotspot_update"),
        },
    }


def main() -> None:
    db.init_db()
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dashboard": build_dashboard(),
        "reports": db.list_reports(),
    }
    output_path = PROJECT_ROOT / "public" / "demo-data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported demo data to {output_path}")


if __name__ == "__main__":
    main()
