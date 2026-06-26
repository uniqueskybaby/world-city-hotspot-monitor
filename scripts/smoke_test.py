from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="hotspot-smoke-")
os.environ["DOTENV_OVERRIDE"] = "false"
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["USE_SAMPLE_DATA"] = "true"
os.environ["AI_PROVIDER"] = "rules"
os.environ["USE_DEEPSEEK_AI"] = "false"
os.environ["USE_OPENAI_AI"] = "false"
os.environ["SEARCH_MAX_QUERIES_PER_RUN"] = "0"
os.environ["SOURCE_NAME_FILTER"] = "__no_live_sources__"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402


def main() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200, health.text
        assert health.json()["ok"] is True

        run = client.post("/api/jobs/run-sync")
        assert run.status_code == 200, run.text
        payload = run.json()
        assert payload["status"] == "success", payload
        assert payload["counters"]["hotspots"] >= 1, payload

        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200, dashboard.text
        data = dashboard.json()
        assert data["report"]["status"] == "published"
        assert data["report"]["briefing"]["verification_status"]
        assert len(data["report"]["briefing"]["breakout_brands"]) >= 1
        assert data["report"]["briefing"]["breakout_brands"][0]["hotspot_id"]
        assert len(data["hotspots"]) >= 1
        assert data["hotspots"][0]["source_url"].startswith("http")
        assert any(source["adapter"] == "web_search" for source in data["sources"])

        source = client.post(
            "/api/sources",
            json={
                "name": "测试公开信源",
                "source_type": "公开资讯平台",
                "url": "https://example.com/test-source",
                "adapter": "html",
                "enabled": True,
                "notes": "烟测新增信源",
            },
        )
        assert source.status_code == 200, source.text
        source_id = source.json()["source"]["id"]

        toggled = client.patch(f"/api/sources/{source_id}/enabled", json={"enabled": False})
        assert toggled.status_code == 200, toggled.text
        assert toggled.json()["source"]["enabled"] == 0

        jobs = client.get("/api/jobs")
        assert jobs.status_code == 200, jobs.text
        assert len(jobs.json()["jobs"]) >= 1

    print("smoke test passed")


if __name__ == "__main__":
    main()
