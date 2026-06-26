from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="hotspot-stability-")
os.environ["DOTENV_OVERRIDE"] = "false"
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["AI_PROVIDER"] = "rules"
os.environ["USE_DEEPSEEK_AI"] = "false"
os.environ["USE_OPENAI_AI"] = "false"
os.environ["USE_SAMPLE_DATA"] = "false"
os.environ["SEARCH_MAX_QUERIES_PER_RUN"] = "0"
os.environ["SEARCH_FETCH_ARTICLE_CONTENT"] = "false"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend import crawler, database as db, pipeline as pipeline_module  # noqa: E402
from backend.ai import _apply_daily_verification, compose_daily_briefing, evaluate_article  # noqa: E402
from backend.app import app, should_run_scheduled_catchup  # noqa: E402
from backend.pipeline import (  # noqa: E402
    _aggregate_hotspots_by_brand,
    _apply_coverage_date_gate,
    _apply_priority_adjustments,
    _candidate_score,
    _dedupe,
    _parse_article_date,
    _passes_hotspot_threshold,
    _suppress_unverified_article,
    run_daily_update,
    yesterday_coverage_date,
)


def make_article(
    title: str,
    url: str,
    content: str = "",
    source_type: str = "互联网搜索",
    published_at: str = "2026-06-24T09:00:00+08:00",
) -> dict:
    return {
        "title": title,
        "url": url,
        "source_name": "稳定性测试",
        "source_type": source_type,
        "published_at": published_at,
        "excerpt": (content or title)[:180],
        "content": content or title,
    }


def assert_ok(name: str, condition: bool, detail: object = "") -> None:
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def hotspot_from(article: dict, evaluation: dict, hotspot_id: int) -> dict:
    return {
        "id": hotspot_id,
        "brand_name": evaluation["brand_name"],
        "title": article["title"],
        "signal_type": evaluation["signal_type"],
        "category": evaluation["category"],
        "ai_summary": evaluation["ai_summary"],
        "leasing_insight": evaluation["leasing_insight"],
        "evidence": evaluation["evidence"],
        "tags": evaluation["tags"],
        "source_name": article["source_name"],
        "source_type": article["source_type"],
        "source_url": article["url"],
        "published_at": article.get("published_at", ""),
        "confidence": evaluation["confidence"],
        "relevance": evaluation["relevance"],
        "opportunity_score": evaluation["opportunity_score"],
        "breakout_score": evaluation["breakout_score"],
    }


def test_signal_quality() -> None:
    domestic = make_article(
        "国内新锐香氛品牌「闻野」上海首店开业，小红书连续三天爆火",
        "https://example.com/wenye-first-store",
        "闻野是本土原创香氛新品牌，首店开业后排队明显，多款产品售罄，正在寻找核心购物中心点位。",
    )
    mature = make_article(
        "成熟品牌某某咖啡门店突破1000家，杭州新店开业",
        "https://example.com/mature-coffee-1000",
        "某某咖啡为大型连锁，本次为常规门店开业与周年营销，没有新子品牌或区域首进信息。",
        "行业媒体",
    )
    noise = make_article(
        "某购物中心停车动线优化完成",
        "https://example.com/parking-flow",
        "项目优化停车收费系统与导视，不涉及具体消费品牌、门店拓展或招商机会。",
    )
    domestic_eval = evaluate_article(domestic)
    mature_eval = evaluate_article(mature)
    noise_eval = evaluate_article(noise)
    assert_ok("国内新兴品牌排序优先", _candidate_score(domestic) > _candidate_score(mature))
    assert_ok("国内新兴品牌信号识别", domestic_eval["signal_type"] == "国内新兴品牌", domestic_eval)
    assert_ok("运营噪音拒绝", not _passes_hotspot_threshold(noise_eval, noise), noise_eval)
    assert_ok(
        "成熟连锁普通新闻拒绝",
        not _passes_hotspot_threshold(
            {"brand_name": "某某咖啡", "relevance": 90, "opportunity_score": 80, "breakout_score": 80, "leasing_insight": "常规门店"},
            mature,
        ),
    )


def test_date_gate_and_dedupe() -> None:
    assert_ok("ISO 日期解析", _parse_article_date("2026-06-24T09:00:00+08:00").isoformat() == "2026-06-24")
    assert_ok("RSS 日期解析", _parse_article_date("Wed, 24 Jun 2026 11:00:00 +0800").isoformat() == "2026-06-24")
    assert_ok("中文日期解析", _parse_article_date("2026年6月24日").isoformat() == "2026-06-24")
    logs: list[str] = []
    kept, stats = _apply_coverage_date_gate(
        [
            make_article("昨日品牌新闻", "https://example.com/a", published_at="2026-06-24"),
            make_article("今日品牌新闻", "https://example.com/b", published_at="2026-06-25"),
            make_article("无日期品牌新闻", "https://example.com/c", published_at=""),
        ],
        "2026-06-24",
        logs,
    )
    assert_ok("日期闸门排除非昨日", len(kept) == 2 and stats["out_of_window"] == 1 and stats["unverified"] == 1, (kept, stats, logs))
    deduped = _dedupe(
        [
            make_article("B", "https://example.com/b"),
            make_article("B slash", "https://example.com/b/"),
            make_article("B tracking", "https://example.com/b?utm_source=x"),
        ]
    )
    assert_ok("URL 归一化去重", len(deduped) == 1, deduped)
    assert_ok("无日期候选默认不进主榜", _suppress_unverified_article(kept[1]), kept[1])


def test_brand_aggregation_and_priority_adjustments() -> None:
    article_a = make_article(
        "新锐咖啡品牌「闻野咖啡」武汉首店开业",
        "https://example.com/wenye-coffee-a",
        "闻野咖啡是本土原创新品牌，武汉首店开业后排队明显。",
        "行业媒体",
    )
    article_b = make_article(
        "闻野咖啡小红书爆火，光谷新店连续排队",
        "https://example.com/wenye-coffee-b",
        "闻野咖啡在小红书爆火，光谷新店连续排队，多平台讨论升温。",
        "互联网搜索",
    )
    eval_a = evaluate_article(article_a)
    eval_b = evaluate_article(article_b)
    hot_a = hotspot_from(article_a, eval_a, 201)
    hot_b = hotspot_from(article_b, eval_b, 202)
    for item, article in [(hot_a, article_a), (hot_b, article_b)]:
        item["article_id"] = item["id"]
        item["source_links"] = [
            {
                "source_name": article["source_name"],
                "source_type": article["source_type"],
                "source_url": article["url"],
                "published_at": article["published_at"],
                "date_status": "verified",
            }
        ]
    hot_a["brand_name"] = "闻野咖啡"
    hot_b["brand_name"] = "闻野咖啡"
    hot_a["opportunity_score"] = 70
    hot_a["breakout_score"] = 72
    hot_b["opportunity_score"] = 74
    hot_b["breakout_score"] = 75
    logs: list[str] = []
    aggregated = _aggregate_hotspots_by_brand([hot_a, hot_b], logs)
    assert_ok("同品牌热点聚合为一条", len(aggregated) == 1 and len(aggregated[0]["source_links"]) == 2, aggregated)
    assert_ok("多来源热点加权", aggregated[0]["opportunity_score"] > max(hot_a["opportunity_score"], hot_b["opportunity_score"]), aggregated[0])
    assert_ok("多来源标签保留", "多来源验证" in aggregated[0]["tags"], aggregated[0]["tags"])

    mature = make_article(
        "成熟品牌某某咖啡门店突破1000家，杭州新店开业",
        "https://example.com/mature-coffee-priority",
        "某某咖啡为大型连锁，本次为常规门店开业与周年营销，没有新子品牌或区域首进信息。",
        "行业媒体",
    )
    ai = {"opportunity_score": 90, "breakout_score": 88, "relevance": 92, "tags": []}
    _apply_priority_adjustments(ai, mature)
    assert_ok("成熟连锁普通扩张降权", ai["opportunity_score"] == 76 and "成熟品牌降权" in ai["tags"], ai)


def test_search_breakers() -> None:
    old_search_results = crawler._search_results
    old_extract = crawler.extract_article
    try:
        os.environ["SEARCH_MAX_QUERIES_PER_RUN"] = "3"
        os.environ["SEARCH_MAX_QUERY_FAILURES"] = "2"

        def failed_search(_query: str, _limit: int, _provider: str | None) -> list[dict]:
            raise RuntimeError("simulated outage")

        crawler._search_results = failed_search
        _articles, logs = crawler.fetch_web_search(
            {"name": "测试搜索源", "source_type": "互联网搜索", "adapter": "web_search", "url": "search://test", "notes": "queries:\nA\nB\nC"},
            limit=6,
        )
        assert_ok("搜索查询失败熔断", any("触发查询熔断" in line for line in logs), logs)

        os.environ["SEARCH_FETCH_ARTICLE_CONTENT"] = "true"
        os.environ["SEARCH_MAX_CONTENT_FAILURES"] = "2"
        os.environ["SEARCH_MAX_QUERIES_PER_RUN"] = "1"

        def ok_search(_query: str, _limit: int, _provider: str | None) -> list[dict]:
            return [
                {"title": f"新品牌{i}", "url": f"https://news.test/{i}", "excerpt": "新品牌 首店", "content": "新品牌 首店"}
                for i in range(4)
            ]

        def failed_extract(_url: str) -> dict:
            raise RuntimeError("article timeout")

        crawler._search_results = ok_search
        crawler.extract_article = failed_extract
        articles, logs = crawler.fetch_web_search(
            {"name": "测试搜索源", "source_type": "互联网搜索", "adapter": "web_search", "url": "search://test", "notes": "queries:\nA"},
            limit=6,
        )
        assert_ok("正文抓取失败熔断", len(articles) == 4 and any("停止正文抓取" in line for line in logs), logs)
    finally:
        crawler._search_results = old_search_results
        crawler.extract_article = old_extract
        os.environ["SEARCH_FETCH_ARTICLE_CONTENT"] = "false"
        os.environ["SEARCH_MAX_QUERIES_PER_RUN"] = "0"


def test_daily_briefing_contract() -> None:
    domestic = make_article(
        "国内新锐香氛品牌「闻野」上海首店开业，小红书连续三天爆火",
        "https://example.com/wenye-first-store",
        "闻野是本土原创香氛新品牌，首店开业后排队明显，多款产品售罄。",
    )
    evaluation = evaluate_article(domestic)
    unverified = hotspot_from(domestic, evaluation, 101)
    unverified["tags"] = [*unverified["tags"], "日期待核验"]
    briefing = compose_daily_briefing("2026-06-25", "2026-06-24", [unverified], 1)
    assert_ok("日报引用热点 ID", briefing["breakout_brands"][0]["hotspot_id"] == 101, briefing)
    assert_ok("日报暴露日期待核验风险", any("日期待核验" in note for note in briefing["risk_notes"]), briefing["risk_notes"])

    verified = _apply_daily_verification(
        {
            **briefing,
            "breakout_brands": [{"hotspot_id": 101}, {"hotspot_id": 999}],
            "key_news": [{"hotspot_id": 101}],
            "top_takeaways": [{"label": "x", "text": "y", "hotspot_ids": [101, 999]}],
            "leasing_actions": [{"priority": "P0", "action": "a", "reason": "r", "hotspot_ids": [101, 999]}],
        },
        {"accuracy_score": 70, "verification_status": "审核未通过", "approved_hotspot_ids": [101], "rejected_hotspot_ids": [101], "issues": ["证据不足"]},
        [unverified],
    )
    assert_ok("审核拒绝会标记待人工复核", verified["verification_status"] == "待人工复核" and not verified["breakout_brands"], verified)


def test_pipeline_and_api_contract() -> None:
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="hotspot-stability-pipeline-")
    os.environ["SOURCE_NAME_FILTER"] = "__no_live_sources__"
    os.environ["USE_SAMPLE_DATA"] = "true"
    result = run_daily_update("stability")
    report = db.get_report(result["report_date"])
    hotspots = db.list_hotspots(result["report_date"])
    assert_ok("完整管线样例成功", result["status"] == "success" and result["counters"]["hotspots"] >= 1, result)
    assert_ok("完整管线日期闸门无误排样例", result["counters"]["articles_out_of_window"] == 0, result["counters"])
    assert_ok("完整管线产出日报", bool(report and report["briefing"]["breakout_brands"]), report)

    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="hotspot-stability-api-")
    os.environ["SOURCE_NAME_FILTER"] = "__no_live_sources__"
    os.environ["USE_SAMPLE_DATA"] = "true"
    with TestClient(app) as client:
        run = client.post("/api/jobs/run-sync")
        dashboard = client.get("/api/dashboard")
        data = dashboard.json()
        briefing = data["report"]["briefing"]
        hotspot_ids = {item["id"] for item in data["hotspots"]}
        briefing_ids = {item["hotspot_id"] for item in briefing["breakout_brands"]} | {item["hotspot_id"] for item in briefing["key_news"]}
        assert_ok("API 返回热点日报信源", run.status_code == 200 and dashboard.status_code == 200 and data["hotspots"] and data["sources"])
        assert_ok("API 日报 ID 可追溯", briefing_ids <= hotspot_ids and bool(briefing_ids), (briefing_ids, hotspot_ids))

    assert_ok("热点变量供静态检查使用", bool(hotspots))


def test_scheduler_catchup_contract() -> None:
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="hotspot-scheduler-")
    os.environ["APP_TIMEZONE"] = "Asia/Shanghai"
    os.environ["DAILY_UPDATE_START"] = "06:30"
    db.init_db()
    tz = ZoneInfo("Asia/Shanghai")
    before_start = datetime(2026, 6, 26, 6, 10, tzinfo=tz)
    after_start = datetime(2026, 6, 26, 7, 10, tzinfo=tz)
    assert_ok("调度开始前不补跑", not should_run_scheduled_catchup(before_start))
    assert_ok("调度开始后无成功任务会补跑", should_run_scheduled_catchup(after_start))
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO crawl_jobs (job_type, status, trigger, started_at, finished_at, logs_json, counters_json)
            VALUES ('daily_hotspot_update', 'success', 'manual_sync', '2026-06-25T22:40:00Z', '2026-06-25T22:45:00Z', '[]', '{}')
            """
        )
    assert_ok("调度开始后已有成功任务不重复补跑", not should_run_scheduled_catchup(after_start))


def test_date_unverified_candidates_do_not_starve_verified_ai() -> None:
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="hotspot-date-starvation-")
    os.environ["SOURCE_NAME_FILTER"] = "日期饥饿测试"
    os.environ["USE_SAMPLE_DATA"] = "false"
    os.environ["MAX_AI_ARTICLES_PER_RUN"] = "1"
    os.environ["MAX_ARTICLES_PER_RUN"] = "4"
    os.environ["ENFORCE_COVERAGE_DATE"] = "true"
    os.environ["INCLUDE_DATE_UNVERIFIED_HOTSPOTS"] = "false"
    db.init_db()
    db.add_source(
        {
            "name": "日期饥饿测试",
            "source_type": "行业媒体",
            "url": "https://example.com/date-starvation",
            "adapter": "html",
            "enabled": True,
            "notes": "",
        }
    )
    coverage_date = yesterday_coverage_date()
    unverified = make_article(
        "国货新锐消费品牌首店新店开业爆款融资",
        "https://example.com/unverified",
        published_at="",
    )
    verified = make_article(
        "核验品牌武汉首店开业",
        "https://example.com/verified",
        published_at=f"{coverage_date}T09:00:00+08:00",
    )

    original_fetch = pipeline_module.fetch_source
    original_eval = pipeline_module.evaluate_article

    def fake_fetch_source(source: dict, limit: int = 6) -> tuple[list[dict], list[str]]:
        return [unverified, verified], ["测试信源返回 2 条候选"]

    def fake_evaluate_article(article: dict) -> dict:
        return {
            "brand_name": "核验品牌",
            "category": "餐饮",
            "signal_type": "国内新兴品牌",
            "regions": "武汉/全国",
            "ai_summary": "核验品牌出现首店开业信号。",
            "leasing_insight": "新品牌首店具备招商跟进价值。",
            "evidence": ["原文明确提及首店开业。"],
            "tags": ["新品牌", "首店"],
            "confidence": 92,
            "relevance": 90,
            "opportunity_score": 88,
            "breakout_score": 86,
            "agent_trace": ["test"],
        }

    try:
        pipeline_module.fetch_source = fake_fetch_source
        pipeline_module.evaluate_article = fake_evaluate_article
        result = pipeline_module.run_daily_update("date_starvation")
    finally:
        pipeline_module.fetch_source = original_fetch
        pipeline_module.evaluate_article = original_eval
        os.environ.pop("SOURCE_NAME_FILTER", None)

    assert_ok("日期待核验不挤占 AI 名额", result["counters"]["ai_evaluated"] == 1, result)
    assert_ok("日期待核验被主榜抑制", result["counters"]["articles_date_unverified_suppressed"] == 1, result)
    assert_ok("已核验候选仍生成热点", result["counters"]["hotspots"] == 1, result)


def test_old_schema_migration() -> None:
    old_dir = tempfile.mkdtemp(prefix="hotspot-old-schema-")
    os.environ["DATA_DIR"] = old_dir
    conn = sqlite3.connect(Path(old_dir) / "hotspots.db")
    conn.execute(
        "CREATE TABLE daily_reports (report_date TEXT PRIMARY KEY, status TEXT NOT NULL, "
        "total_articles INTEGER NOT NULL DEFAULT 0, total_hotspots INTEGER NOT NULL DEFAULT 0, "
        "published_at TEXT NOT NULL, coverage_json TEXT NOT NULL, insights_json TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()
    db.init_db()
    with db.connect() as conn:
        report_columns = {row["name"] for row in conn.execute("PRAGMA table_info(daily_reports)").fetchall()}
        raw_columns = {row["name"] for row in conn.execute("PRAGMA table_info(raw_articles)").fetchall()}
        hotspot_columns = {row["name"] for row in conn.execute("PRAGMA table_info(hotspots)").fetchall()}
    assert_ok("旧库迁移补日报字段", "briefing_json" in report_columns, report_columns)
    assert_ok("旧库迁移补原文日期字段", {"date_status", "coverage_date"} <= raw_columns, raw_columns)
    assert_ok("旧库迁移补热点多来源字段", {"source_links_json", "date_status"} <= hotspot_columns, hotspot_columns)


def main() -> None:
    tests = [
        test_signal_quality,
        test_date_gate_and_dedupe,
        test_brand_aggregation_and_priority_adjustments,
        test_search_breakers,
        test_daily_briefing_contract,
        test_pipeline_and_api_contract,
        test_scheduler_catchup_contract,
        test_date_unverified_candidates_do_not_starve_verified_ai,
        test_old_schema_migration,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("stability test passed")


if __name__ == "__main__":
    main()
