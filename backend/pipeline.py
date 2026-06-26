from __future__ import annotations

import os
import re
import time
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

from . import database as db
from .ai import compose_daily_briefing, evaluate_article
from .crawler import fetch_source
from .sample_data import sample_articles


def timezone() -> ZoneInfo:
    return ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Shanghai"))


def today_report_date() -> str:
    return datetime.now(timezone()).date().isoformat()


def yesterday_coverage_date() -> str:
    return (datetime.now(timezone()).date() - timedelta(days=1)).isoformat()


def run_daily_update(trigger: str = "manual") -> dict:
    db.init_db()
    stale_minutes = int(os.getenv("RUNNING_JOB_STALE_MINUTES", "180"))
    db.mark_stale_running_jobs(stale_minutes)
    job_id, active_job = db.create_job_if_idle("daily_hotspot_update", trigger)
    if job_id is None:
        return {
            "job_id": None,
            "status": "skipped",
            "reason": "已有更新任务正在运行",
            "active_job": active_job,
        }
    logs: list[str] = [f"任务启动：{trigger}"]
    counters = {
        "sources": 0,
        "articles_found": 0,
        "articles_saved": 0,
        "hotspots": 0,
        "sample_used": False,
        "articles_before_date_gate": 0,
        "articles_out_of_window": 0,
        "articles_date_unverified": 0,
        "articles_date_unverified_suppressed": 0,
        "hotspots_aggregated": 0,
        "multi_source_hotspots": 0,
        "ai_evaluated": 0,
        "ai_rule_fallbacks": 0,
    }
    try:
        coverage_date = yesterday_coverage_date()
        logs.append(f"资讯覆盖日期：{coverage_date}")
        sources = db.enabled_sources()
        source_filter = os.getenv("SOURCE_NAME_FILTER", "").strip()
        if source_filter:
            sources = [source for source in sources if source_filter.lower() in source["name"].lower()]
            logs.append(f"本次按 SOURCE_NAME_FILTER 仅运行 {len(sources)} 个信源：{source_filter}")
        counters["sources"] = len(sources)
        articles: list[dict] = []
        per_source_limit = int(os.getenv("CRAWL_LINKS_PER_SOURCE", "6"))
        for source in sources:
            started = time.monotonic()
            fetched, source_logs = fetch_source(source, limit=per_source_limit)
            elapsed = time.monotonic() - started
            logs.extend(source_logs)
            if fetched:
                logs.append(f"{source['name']} 发现 {len(fetched)} 条候选资讯，用时 {elapsed:.1f}s")
                articles.extend(fetched)

        if not articles and os.getenv("USE_SAMPLE_DATA", "true").lower() == "true":
            articles = sample_articles()
            counters["sample_used"] = True
            logs.append("未抓到可用公开资讯，已使用内置样例数据跑通今日流程")

        deduped = _dedupe(articles)
        counters["articles_before_date_gate"] = len(deduped)
        deduped, date_stats = _apply_coverage_date_gate(deduped, coverage_date, logs)
        counters["articles_out_of_window"] = date_stats["out_of_window"]
        counters["articles_date_unverified"] = date_stats["unverified"]
        max_articles = int(os.getenv("MAX_ARTICLES_PER_RUN", "48"))
        max_ai_articles = int(os.getenv("MAX_AI_ARTICLES_PER_RUN", "16"))
        deduped.sort(key=_candidate_score, reverse=True)
        if len(deduped) > max_articles:
            logs.append(f"候选资讯 {len(deduped)} 条，按信号强度保留前 {max_articles} 条")
            deduped = deduped[:max_articles]
        counters["articles_found"] = len(deduped)
        evaluated: list[dict] = []
        ai_pool = [article for article in deduped if not _suppress_unverified_article(article)]
        counters["articles_date_unverified_suppressed"] = len(deduped) - len(ai_pool)
        if counters["articles_date_unverified_suppressed"]:
            logs.append(
                f"日期待核验候选 {counters['articles_date_unverified_suppressed']} 条，"
                "不占用主榜 AI 精读名额"
            )
        ai_candidates = ai_pool[:max_ai_articles]
        if len(ai_pool) > len(ai_candidates):
            logs.append(f"AI 精读前 {len(ai_candidates)} 条已核验高信号资讯，其余候选留待后续批次")
        for article in ai_candidates:
            article_id = db.upsert_raw_article(article)
            counters["articles_saved"] += 1
            ai = evaluate_article(article)
            counters["ai_evaluated"] += 1
            if _uses_rule_fallback(ai):
                counters["ai_rule_fallbacks"] += 1
            if article.get("date_status") == "unverified":
                _mark_date_unverified(ai)
            _apply_priority_adjustments(ai, article)
            if not _passes_hotspot_threshold(ai, article):
                continue
            evaluated.append(
                {
                    "article_id": article_id,
                    "title": article["title"],
                    "source_name": article.get("source_name", "未知来源"),
                    "source_type": article.get("source_type", "公开资讯平台"),
                    "source_url": article["url"],
                    "published_at": article.get("published_at", ""),
                    "date_status": article.get("date_status", ""),
                    "source_links": [_source_link(article)],
                    **ai,
                }
            )

        before_aggregation = len(evaluated)
        evaluated = _aggregate_hotspots_by_brand(evaluated, logs)
        counters["hotspots_aggregated"] = max(0, before_aggregation - len(evaluated))
        counters["multi_source_hotspots"] = sum(1 for item in evaluated if len(item.get("source_links", [])) > 1)
        evaluated.sort(
            key=lambda item: (item["opportunity_score"], item["breakout_score"], item["confidence"]),
            reverse=True,
        )
        report_date = today_report_date()
        db.replace_hotspots_for_date(report_date, evaluated[:128])
        saved_hotspots = db.list_hotspots(report_date)
        insights = build_insights(saved_hotspots)
        briefing = compose_daily_briefing(report_date, coverage_date, saved_hotspots, len(deduped))
        db.upsert_daily_report(report_date, len(deduped), saved_hotspots, insights, briefing)
        counters["hotspots"] = len(saved_hotspots)
        logs.append(
            "日期闸门："
            f"去重后 {counters['articles_before_date_gate']} 条，"
            f"排除非覆盖日期 {counters['articles_out_of_window']} 条，"
            f"日期待核验 {counters['articles_date_unverified']} 条，"
            f"未进主榜 {counters['articles_date_unverified_suppressed']} 条"
        )
        logs.append(
            "AI 评估："
            f"精读 {counters['ai_evaluated']} 条，"
            f"规则/回退 {counters['ai_rule_fallbacks']} 条，"
            f"同品牌聚合 {counters['hotspots_aggregated']} 条，"
            f"多来源热点 {counters['multi_source_hotspots']} 条"
        )
        logs.append(f"日报发布完成：{report_date}，入选热点 {counters['hotspots']} 条")
        db.finish_job(job_id, "success", logs, counters)
        return {"job_id": job_id, "status": "success", "report_date": report_date, "counters": counters, "logs": logs}
    except Exception as exc:  # noqa: BLE001
        logs.append(f"任务失败：{exc}")
        db.finish_job(job_id, "failed", logs, counters)
        return {"job_id": job_id, "status": "failed", "error": str(exc), "counters": counters, "logs": logs}


def ensure_report_exists() -> None:
    db.init_db()
    if db.get_report() is None:
        run_daily_update("first_boot")


def build_insights(hotspots: list[dict]) -> list[dict]:
    grouped: dict[str, int] = {}
    for item in hotspots:
        grouped[item["signal_type"]] = grouped.get(item["signal_type"], 0) + 1
    top = sorted(grouped.items(), key=lambda pair: pair[1], reverse=True)[:5]
    return [
        {
            "name": name,
            "count": count,
            "summary": _insight_copy(name),
        }
        for name, count in top
    ]


def _insight_copy(name: str) -> str:
    copies = {
        "国内新兴品牌": "国内新锐品牌、国货品牌和区域首店信号更集中，适合优先进入招商跟踪池。",
        "新消费爆款": "今天爆款信号集中在年轻客群、社媒传播和排队抢购。",
        "国际新兴品牌": "国际品牌与海外首店可作为差异化招商线索。",
        "线下扩张": "多条线索体现门店拓展，适合招商团队跟进位置需求。",
        "社媒爆火": "社媒讨论度较高，适合评估快闪、联名和活动引流。",
        "融资动态": "资本加持品牌可能进入下一轮开店周期。",
    }
    return copies.get(name, "出现可跟踪品牌信号，建议结合原文链接进一步核查。")


def _dedupe(articles: list[dict]) -> list[dict]:
    seen: set[str] = set()
    output: list[dict] = []
    for article in articles:
        url = article.get("url", "").strip()
        title = article.get("title", "").strip()
        if not url or not title:
            continue
        key = _canonical_article_url(url)
        if key in seen:
            continue
        seen.add(key)
        output.append(article)
    return output


def _apply_coverage_date_gate(
    articles: list[dict],
    coverage_date: str,
    logs: list[str],
) -> tuple[list[dict], dict[str, int]]:
    if os.getenv("ENFORCE_COVERAGE_DATE", "true").lower() != "true":
        return articles, {"out_of_window": 0, "unverified": 0}

    target = date.fromisoformat(coverage_date)
    kept: list[dict] = []
    stats = {"out_of_window": 0, "unverified": 0}
    for article in articles:
        parsed = _parse_article_date(str(article.get("published_at", "")))
        if parsed is None:
            article["date_status"] = "unverified"
            article["coverage_date"] = coverage_date
            stats["unverified"] += 1
            kept.append(article)
            continue
        if parsed != target:
            stats["out_of_window"] += 1
            continue
        article["date_status"] = "verified"
        article["coverage_date"] = coverage_date
        kept.append(article)

    if stats["out_of_window"] or stats["unverified"]:
        logs.append(
            f"日期过滤完成：覆盖 {coverage_date}，"
            f"排除非覆盖日期 {stats['out_of_window']} 条，"
            f"保留日期待核验 {stats['unverified']} 条"
        )
    return kept, stats


def _parse_article_date(value: str) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None

    chinese = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", raw)
    if chinese:
        year, month, day = [int(part) for part in chinese.groups()]
        return date(year, month, day)

    numeric = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", raw)
    if numeric:
        year, month, day = [int(part) for part in numeric.groups()]
        return date(year, month, day)

    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone())
        return parsed.date()
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone())
        return parsed.date()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _mark_date_unverified(ai: dict) -> None:
    tags = list(dict.fromkeys([*ai.get("tags", []), "日期待核验"]))
    ai["tags"] = tags
    ai["confidence"] = max(50, int(ai.get("confidence", 50)) - 6)
    insight = str(ai.get("leasing_insight", ""))
    if "发布日期待核验" not in insight:
        ai["leasing_insight"] = f"{insight} 发布日期待核验，进入招商跟进前需确认资讯时间。"


def _uses_rule_fallback(ai: dict) -> bool:
    trace = [str(item).lower() for item in ai.get("agent_trace", [])]
    return not trace or any("rules" in item or "fallback" in item for item in trace)


def _suppress_unverified_article(article: dict) -> bool:
    if os.getenv("INCLUDE_DATE_UNVERIFIED_HOTSPOTS", "false").lower() == "true":
        return False
    return os.getenv("ENFORCE_COVERAGE_DATE", "true").lower() == "true" and article.get("date_status") == "unverified"


def _apply_priority_adjustments(ai: dict, article: dict) -> None:
    text = f"{article.get('title', '')}\n{article.get('excerpt', '')}\n{article.get('content', '')}"
    if _looks_like_mature_brand_routine_news(text):
        ai["opportunity_score"] = max(50, int(ai.get("opportunity_score", 50)) - 14)
        ai["breakout_score"] = max(50, int(ai.get("breakout_score", 50)) - 12)
        ai["relevance"] = max(50, int(ai.get("relevance", 50)) - 8)
        ai["tags"] = list(dict.fromkeys([*ai.get("tags", []), "成熟品牌降权"]))


def _source_link(article: dict) -> dict:
    return {
        "source_name": article.get("source_name", "未知来源"),
        "source_type": article.get("source_type", "公开资讯平台"),
        "source_url": article.get("url", ""),
        "published_at": article.get("published_at", ""),
        "date_status": article.get("date_status", ""),
    }


def _aggregate_hotspots_by_brand(rows: list[dict], logs: list[str]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        key = _brand_key(row.get("brand_name", ""))
        if not key:
            key = f"article:{row.get('article_id')}"
        grouped.setdefault(key, []).append(row)

    output: list[dict] = []
    merged_count = 0
    for items in grouped.values():
        if len(items) == 1:
            output.append(items[0])
            continue
        items.sort(
            key=lambda item: (int(item.get("opportunity_score", 0)), int(item.get("breakout_score", 0)), int(item.get("confidence", 0))),
            reverse=True,
        )
        primary = dict(items[0])
        source_links = _unique_source_links(link for item in items for link in item.get("source_links", []))
        source_count = len(source_links)
        source_type_count = len({link.get("source_type", "") for link in source_links if link.get("source_type")})
        bonus = min(18, max(0, source_count - 1) * 6 + max(0, source_type_count - 1) * 3)
        primary["source_links"] = source_links
        primary["source_name"] = _source_name_summary(source_links)
        primary["source_type"] = _source_type_summary(source_links)
        primary["opportunity_score"] = min(98, int(primary.get("opportunity_score", 0)) + bonus)
        primary["breakout_score"] = min(98, int(primary.get("breakout_score", 0)) + max(0, bonus - 2))
        primary["relevance"] = min(98, int(primary.get("relevance", 0)) + min(8, bonus // 2))
        primary["confidence"] = min(98, int(primary.get("confidence", 0)) + min(6, max(0, source_count - 1) * 2))
        primary["evidence"] = _merge_lists(item.get("evidence", []) for item in items)[:5]
        primary["tags"] = _merge_lists(item.get("tags", []) for item in items)
        if source_count > 1:
            primary["tags"] = list(dict.fromkeys([*primary["tags"], "多来源验证"]))
            primary["leasing_insight"] = _append_source_signal(primary.get("leasing_insight", ""), source_count, source_type_count)
        output.append(primary)
        merged_count += len(items) - 1

    if merged_count:
        logs.append(f"同品牌热点聚合：合并 {merged_count} 条重复热点，形成 {len(output)} 条主热点")
    return output


def _brand_key(value: str) -> str:
    cleaned = re.sub(r"\s+", "", str(value or "").lower())
    cleaned = re.sub(r"[「」『』《》“”\"']", "", cleaned)
    cleaned = cleaned.replace("品牌", "")
    return cleaned


def _unique_source_links(links) -> list[dict]:
    output = []
    seen: set[str] = set()
    for link in links:
        url = str(link.get("source_url", "")).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        output.append(link)
    return output


def _source_name_summary(links: list[dict]) -> str:
    names = [link.get("source_name", "") for link in links if link.get("source_name")]
    unique = list(dict.fromkeys(names))
    if len(unique) <= 2:
        return "、".join(unique)
    return f"{unique[0]} 等{len(unique)}个来源"


def _source_type_summary(links: list[dict]) -> str:
    types = [link.get("source_type", "") for link in links if link.get("source_type")]
    return "、".join(list(dict.fromkeys(types))[:3])


def _merge_lists(values) -> list[str]:
    merged: list[str] = []
    for value in values:
        if isinstance(value, list):
            merged.extend(str(item).strip() for item in value if str(item).strip())
        elif value:
            merged.append(str(value).strip())
    return list(dict.fromkeys(merged))


def _append_source_signal(insight: str, source_count: int, source_type_count: int) -> str:
    suffix = f" 该热点已由{source_count}个来源交叉提及"
    if source_type_count > 1:
        suffix += f"，覆盖{source_type_count}类信源"
    suffix += "，推荐度已上调。"
    return insight if suffix.strip() in insight else f"{insight}{suffix}"


SIGNAL_WEIGHTS = {
    "新品牌": 24,
    "新兴品牌": 24,
    "新锐": 22,
    "国货": 20,
    "本土品牌": 20,
    "原创品牌": 18,
    "首家": 18,
    "新店": 17,
    "爆款": 18,
    "排队": 16,
    "抢购": 16,
    "首店": 18,
    "开业": 12,
    "融资": 12,
    "出海": 12,
    "海外": 10,
    "国际": 10,
    "联名": 10,
    "快闪": 9,
    "开店": 8,
    "扩张": 8,
    "购物中心": 8,
    "小红书": 7,
    "抖音": 7,
    "社媒": 7,
}

DOMESTIC_EMERGING_TERMS = [
    "国内",
    "中国",
    "国货",
    "本土",
    "新锐",
    "新兴品牌",
    "新品牌",
    "原创品牌",
    "区域首店",
    "华中首店",
    "武汉首店",
    "首家门店",
]

STRONG_EMERGING_TERMS = [
    "新品牌",
    "新兴品牌",
    "新锐",
    "国货",
    "本土品牌",
    "原创品牌",
    "首家门店",
    "区域首店",
    "首轮融资",
]

MATURE_BRAND_TERMS = [
    "老牌",
    "成熟品牌",
    "大型连锁",
    "门店突破",
    "第1000家",
    "第千家",
    "万店",
    "上市公司",
    "成立于",
    "周年",
]

NON_BRAND_ENTITY_TERMS = [
    "购物中心",
    "商场",
    "项目",
    "停车",
    "停车场",
    "导视",
    "动线",
    "物业",
    "会员系统",
]

NEGATIVE_ARTICLE_TERMS = [
    "不涉及具体消费品牌",
    "不涉及消费品牌",
    "不涉及具体品牌",
    "不涉及门店拓展",
    "不涉及门店",
    "不涉及招商机会",
    "非品牌新闻",
    "停车动线",
    "停车场",
    "导视",
    "物业服务",
]

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "spm",
    "from",
    "source",
    "fbclid",
    "gclid",
    "yclid",
    "msclkid",
    "utm",
}


def _candidate_score(article: dict) -> int:
    text = f"{article.get('title', '')}\n{article.get('excerpt', '')}\n{article.get('content', '')}"
    score = 0
    for keyword, weight in SIGNAL_WEIGHTS.items():
        if keyword.lower() in text.lower():
            score += weight
    if _has_domestic_emerging_signal(text):
        score += 18
    if _looks_like_mature_brand_routine_news(text):
        score -= 16
    if _is_high_quality_source_type(str(article.get("source_type", ""))):
        score += 5
    if article.get("source_type") == "互联网搜索":
        score += 8
    return score


def _passes_hotspot_threshold(ai: dict, article: dict | None = None) -> bool:
    min_relevance = int(os.getenv("MIN_RELEVANCE_SCORE", "50"))
    min_opportunity = int(os.getenv("MIN_OPPORTUNITY_SCORE", "65"))
    min_breakout = int(os.getenv("MIN_BREAKOUT_SCORE", "65"))
    relevance = int(ai.get("relevance", 0))
    opportunity = int(ai.get("opportunity_score", 0))
    breakout = int(ai.get("breakout_score", 0))
    insight = str(ai.get("leasing_insight", ""))
    brand_name = str(ai.get("brand_name", "")).strip().lower()
    if brand_name in {"未知", "未明确", "unknown", "待识别品牌"}:
        return False
    if len(brand_name) <= 1:
        return False
    title = str((article or {}).get("title", ""))
    url = str((article or {}).get("url", ""))
    if title.strip() in {"找品牌", "找项目"} or "brandList" in url or "projectList" in url:
        return False
    article_text = ""
    if article:
        article_text = f"{article.get('title', '')}\n{article.get('excerpt', '')}\n{article.get('content', '')}"
    if _looks_like_non_brand_operational_news(brand_name, article_text):
        return False
    negative_terms = [
        "无需纳入",
        "非实体品牌",
        "不涉及门店",
        "不涉及招商",
        "无需关注",
        "不建议纳入",
        "未提供具体品牌",
        "未提及具体品牌",
    ]
    if any(term in insight for term in negative_terms):
        return False
    if _looks_like_mature_brand_routine_news(article_text) and max(opportunity, breakout) < 86:
        return False
    return relevance >= min_relevance and (opportunity >= min_opportunity or breakout >= min_breakout)


def _has_domestic_emerging_signal(text: str) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in DOMESTIC_EMERGING_TERMS)


def _looks_like_mature_brand_routine_news(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    mature = any(term.lower() in lowered for term in MATURE_BRAND_TERMS)
    strong_emerging = any(term.lower() in lowered for term in STRONG_EMERGING_TERMS)
    return mature and not strong_emerging


def _is_high_quality_source_type(source_type: str) -> bool:
    if source_type in {"品牌官网", "国际媒体", "行业媒体", "商业地产媒体"}:
        return True
    quality_terms = [
        "行业媒体",
        "商业地产",
        "食品饮料",
        "餐饮",
        "饮品",
        "品牌媒体",
        "零售",
        "大消费",
        "新消费",
    ]
    return any(term in source_type for term in quality_terms)


def _looks_like_non_brand_operational_news(brand_name: str, text: str) -> bool:
    lowered = text.lower()
    if any(term.lower() in lowered for term in NEGATIVE_ARTICLE_TERMS):
        return True
    brand_lowered = brand_name.lower()
    generic_name = any(term.lower() in brand_lowered for term in NON_BRAND_ENTITY_TERMS)
    has_brand_signal = any(term.lower() in lowered for term in STRONG_EMERGING_TERMS)
    return generic_name and not has_brand_signal


def _canonical_article_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in TRACKING_QUERY_KEYS or any(lowered.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
            continue
        query_pairs.append((key, value))
    path = (parsed.path.rstrip("/") or "/").lower()
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            urlencode(query_pairs, doseq=True),
            "",
        )
    )
