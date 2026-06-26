from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

import httpx
from dotenv import load_dotenv


load_dotenv()


CATEGORY_RULES = [
    ("饮品甜品", ["茶饮", "咖啡", "甜品", "奶茶", "烘焙", "饮品"]),
    ("餐饮", ["餐饮", "轻食", "火锅", "烤肉", "汉堡", "披萨", "咖啡烘焙"]),
    ("潮玩文创", ["潮玩", "盲盒", "玩具", "IP", "LABUBU", "文创"]),
    ("零售集合", ["集合店", "零售", "买手店", "生活方式"]),
    ("美妆个护", ["美妆", "护肤", "个护", "香氛", "香水"]),
    ("运动健康", ["运动", "健康", "健身", "轻食", "户外"]),
]

SIGNAL_RULES = [
    ("国内新兴品牌", ["新品牌", "新兴品牌", "新锐", "国货", "本土品牌", "原创品牌", "首家门店", "区域首店"]),
    ("新消费爆款", ["爆款", "出圈", "排队", "抢购", "售罄", "溢价"]),
    ("国际新兴品牌", ["海外", "国际", "新加坡", "亚洲", "欧洲", "全球", "出海"]),
    ("线下扩张", ["开店", "门店", "首店", "扩张", "拓展", "购物中心"]),
    ("社媒爆火", ["小红书", "抖音", "社媒", "打卡", "话题", "平台"]),
    ("融资动态", ["融资", "投资", "A轮", "B轮", "资本"]),
]

BOOST_KEYWORDS = {
    "新品牌": 12,
    "新兴品牌": 12,
    "新锐": 11,
    "国货": 10,
    "本土品牌": 10,
    "原创品牌": 9,
    "新店": 8,
    "排队": 9,
    "抢购": 9,
    "爆款": 10,
    "首店": 8,
    "融资": 8,
    "扩张": 7,
    "海外": 6,
    "购物中心": 6,
    "联名": 7,
    "快闪": 6,
    "售罄": 8,
    "破百万": 7,
    "门店": 5,
}

MATURE_NEWS_KEYWORDS = ["老牌", "成熟品牌", "大型连锁", "门店突破", "第1000家", "万店", "上市公司", "周年"]


def evaluate_article(article: dict[str, Any]) -> dict[str, Any]:
    if _deepseek_enabled():
        try:
            return _deepseek_multi_agent_evaluate(article)
        except Exception as exc:  # noqa: BLE001
            fallback = _rule_evaluate(article)
            fallback["agent_trace"] = [f"deepseek_failed:{type(exc).__name__}", "article_rules"]
            return fallback
    if os.getenv("USE_OPENAI_AI", "false").lower() == "true" and os.getenv("OPENAI_API_KEY"):
        try:
            return _openai_evaluate(article)
        except Exception as exc:  # noqa: BLE001
            fallback = _rule_evaluate(article)
            fallback["agent_trace"] = [f"openai_failed:{type(exc).__name__}", "article_rules"]
            return fallback
    return _rule_evaluate(article)


def compose_daily_briefing(
    report_date: str,
    coverage_date: str,
    hotspots: list[dict[str, Any]],
    total_articles: int,
) -> dict[str, Any]:
    fallback = _rule_daily_briefing(report_date, coverage_date, hotspots, total_articles)
    if not hotspots:
        return fallback
    if _deepseek_enabled():
        try:
            return _deepseek_daily_briefing(report_date, coverage_date, hotspots, total_articles, fallback)
        except Exception as exc:  # noqa: BLE001
            fallback["agent_trace"] = [f"daily_deepseek_failed:{type(exc).__name__}", *fallback.get("agent_trace", [])]
            fallback["verification_notes"] = [
                f"AI 日报智能体调用失败，已使用规则日报回退：{type(exc).__name__}",
                *fallback.get("verification_notes", []),
            ][:6]
            return fallback
    return fallback


def _deepseek_daily_briefing(
    report_date: str,
    coverage_date: str,
    hotspots: list[dict[str, Any]],
    total_articles: int,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    context = _daily_briefing_context(hotspots)
    fact_sheet = _deepseek_agent_json(
        "daily_fact_curator",
        _daily_fact_curator_prompt(report_date, coverage_date, context),
        tier="flash",
    )
    writer = _deepseek_agent_json(
        "daily_report_writer",
        _daily_writer_prompt(report_date, coverage_date, total_articles, context, fact_sheet),
        tier="pro",
    )
    drafted = _ensure_daily_briefing_schema({**fallback, **writer}, hotspots, report_date, coverage_date, total_articles)
    verifier = _deepseek_agent_json(
        "daily_report_verifier",
        _daily_verifier_prompt(report_date, coverage_date, context, drafted),
        tier="flash",
    )
    verified = _apply_daily_verification(drafted, verifier, hotspots)
    verified["agent_trace"] = [
        f"fact_curator:{_deepseek_model('flash')}",
        f"report_writer:{_deepseek_model('pro')}",
        f"verifier:{_deepseek_model('flash')}",
    ]
    return verified


def _rule_daily_briefing(
    report_date: str,
    coverage_date: str,
    hotspots: list[dict[str, Any]],
    total_articles: int,
) -> dict[str, Any]:
    ranked = _rank_hotspots_for_briefing(hotspots)
    breakout = [item for item in ranked if item.get("signal_type") in {"国内新兴品牌", "新消费爆款", "社媒爆火"}]
    if not breakout:
        breakout = ranked[:3]
    top_takeaways = []
    for label, pool in [
        ("最值得跟进", ranked[:1]),
        ("爆火新品牌", breakout[:1]),
        ("招商机会", ranked[1:2] or ranked[:1]),
    ]:
        if not pool:
            continue
        item = pool[0]
        top_takeaways.append(
            {
                "label": label,
                "text": f"{item.get('brand_name', '品牌')}出现{item.get('signal_type', '增长')}信号，建议结合原文核查门店模型和合作窗口。",
                "hotspot_ids": [item.get("id")],
            }
        )

    risk_notes = [
        "所有结论仅基于已抓取公开资讯和原文证据，招商跟进前仍需二次核查品牌官方开店计划。",
        "社媒爆火、排队和售罄类信号存在短周期波动，建议结合近7天复现度判断。",
    ]
    if any("日期待核验" in _as_list(item.get("tags")) for item in hotspots):
        risk_notes.append("部分资讯发布时间无法解析，已标记为日期待核验，招商跟进前需确认是否属于昨日资讯。")

    return _ensure_daily_briefing_schema(
        {
            "report_title": f"{coverage_date} 招商日报",
            "report_date": report_date,
            "coverage_date": coverage_date,
            "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "verification_status": "规则审核通过",
            "accuracy_score": 82 if ranked else 0,
            "top_takeaways": top_takeaways,
            "breakout_brands": [_briefing_brand_card(item) for item in breakout[:5]],
            "key_news": [_briefing_news_card(item) for item in ranked[:8]],
            "leasing_actions": _briefing_actions(ranked[:5]),
            "risk_notes": risk_notes,
            "agent_trace": ["fact_curator:rules", "report_writer:rules", "verifier:rules"],
        },
        hotspots,
        report_date,
        coverage_date,
        total_articles,
    )


def _daily_briefing_context(hotspots: list[dict[str, Any]]) -> str:
    rows = []
    for item in _rank_hotspots_for_briefing(hotspots)[:24]:
        evidence = "；".join(_as_list(item.get("evidence"))[:3])
        tags = "、".join(_as_list(item.get("tags"))[:5])
        rows.append(
            "\n".join(
                [
                    f"热点ID：{item.get('id')}",
                    f"品牌：{item.get('brand_name')}",
                    f"标题：{item.get('title')}",
                    f"信号：{item.get('signal_type')} / {item.get('category')}",
                    f"分数：招商价值{item.get('opportunity_score')}，爆款潜力{item.get('breakout_score')}，可信度{item.get('confidence')}",
                    f"摘要：{item.get('ai_summary')}",
                    f"招商洞察：{item.get('leasing_insight')}",
                    f"证据：{evidence}",
                    f"标签：{tags}",
                    f"来源：{item.get('source_name')} / {item.get('source_type')} / {item.get('source_url')}",
                ]
            )
        )
    return "\n\n---\n\n".join(rows)


def _daily_fact_curator_prompt(report_date: str, coverage_date: str, context: str) -> str:
    return f"""
角色：日报事实整理智能体。
任务：只从输入的热点材料中提取可核验事实，输出 JSON。
输出字段：
fact_cards(list): 每项包含 hotspot_id, brand_name, claim, evidence, source_url, confidence_note。
rules(list): 说明哪些事实可以写入日报，哪些只能作为待核查风险。

硬性要求：
- 不允许补充输入材料之外的事实、数字、门店计划或品牌背景。
- 每个 claim 必须能被同项 evidence 或 source_url 回溯。
- 优先整理国内新兴品牌、刚爆火品牌、首店/新店、融资和社媒热度信号。

日报发布日期：{report_date}
资讯覆盖日期：{coverage_date}

热点材料：
{context}
"""


def _daily_writer_prompt(
    report_date: str,
    coverage_date: str,
    total_articles: int,
    context: str,
    fact_sheet: dict[str, Any],
) -> str:
    return f"""
角色：招商日报撰写智能体。
任务：基于事实整理智能体给出的事实和热点材料，撰写一份高信息密度招商日报 JSON。
输出字段：
report_title, top_takeaways(list), breakout_brands(list), key_news(list), leasing_actions(list), risk_notes(list)

结构要求：
- top_takeaways: 3-5 条，每条包含 label, text, hotspot_ids(list)。
- breakout_brands: 3-6 条，每条包含 hotspot_id, brand_name, signal, why_now, leasing_angle, evidence, source_name, source_url, score。
- key_news: 5-10 条，每条包含 hotspot_id, title, summary, implication, source_name, source_url, tags(list)。
- leasing_actions: 3-6 条，每条包含 priority, action, reason, hotspot_ids(list)。
- risk_notes: 2-4 条，说明需要复核的限制。

写法要求：
- 重点突出昨天最值得招商跟进的新兴品牌和爆火信号。
- 信息密度高，短句，不写营销话术。
- 每一块必须包含可回溯的 hotspot_id 或 source_url。
- 不允许写热点材料之外的事实。

日报发布日期：{report_date}
资讯覆盖日期：{coverage_date}
候选资讯数：{total_articles}

事实整理：
{json.dumps(fact_sheet, ensure_ascii=False)}

热点材料：
{context}
"""


def _daily_verifier_prompt(
    report_date: str,
    coverage_date: str,
    context: str,
    drafted: dict[str, Any],
) -> str:
    return f"""
角色：日报真实准确性审核智能体。
任务：审核撰写智能体生成的日报是否完全基于输入材料，输出 JSON。
输出字段：
verification_status, accuracy_score(0-100), approved_hotspot_ids(list), rejected_hotspot_ids(list), issues(list), required_edits(list)

审核标准：
- 任何没有 hotspot_id、source_url 或 evidence 支撑的内容都应标记为 issue。
- 不能证明的新开店、融资金额、门店数量、排队/售罄等说法必须要求删除或降级。
- 对成熟连锁普通开店新闻，不得夸大为新兴品牌爆火。
- 只允许根据下方热点材料判定，不允许使用外部常识。

日报发布日期：{report_date}
资讯覆盖日期：{coverage_date}

待审核日报：
{json.dumps(drafted, ensure_ascii=False)}

可核验热点材料：
{context}
"""


def _apply_daily_verification(
    drafted: dict[str, Any],
    verifier: dict[str, Any],
    hotspots: list[dict[str, Any]],
) -> dict[str, Any]:
    known_ids = {int(item["id"]) for item in hotspots if item.get("id") is not None}
    rejected_ids = {int(value) for value in _as_list(verifier.get("rejected_hotspot_ids")) if str(value).isdigit()}
    approved_raw = _as_list(verifier.get("approved_hotspot_ids"))
    approved_ids = {int(value) for value in approved_raw if str(value).isdigit()} or known_ids
    allowed_ids = (approved_ids & known_ids) - rejected_ids

    for section in ("breakout_brands", "key_news"):
        drafted[section] = [
            item for item in drafted.get(section, []) if int(item.get("hotspot_id") or 0) in allowed_ids
        ]
    for item in drafted.get("top_takeaways", []):
        item["hotspot_ids"] = [value for value in _as_int_list(item.get("hotspot_ids")) if value in allowed_ids]
    for item in drafted.get("leasing_actions", []):
        item["hotspot_ids"] = [value for value in _as_int_list(item.get("hotspot_ids")) if value in allowed_ids]

    issues = _as_list(verifier.get("issues"))
    edits = _as_list(verifier.get("required_edits"))
    drafted["verification_status"] = str(verifier.get("verification_status") or "AI审核完成")
    drafted["accuracy_score"] = _bounded_int(verifier.get("accuracy_score"), 0, 100)
    drafted["verification_notes"] = issues + edits
    if drafted["accuracy_score"] < 80:
        drafted["verification_status"] = "待人工复核"
    drafted["risk_notes"] = list(dict.fromkeys(_as_list(drafted.get("risk_notes")) + issues[:3]))
    return drafted


def _ensure_daily_briefing_schema(
    report: dict[str, Any],
    hotspots: list[dict[str, Any]],
    report_date: str,
    coverage_date: str,
    total_articles: int,
) -> dict[str, Any]:
    known = {int(item["id"]): item for item in hotspots if item.get("id") is not None}
    ranked = _rank_hotspots_for_briefing(hotspots)
    report["report_title"] = str(report.get("report_title") or f"{coverage_date} 招商日报")[:60]
    report["report_date"] = report_date
    report["coverage_date"] = coverage_date
    report["generated_at"] = str(report.get("generated_at") or datetime.utcnow().replace(microsecond=0).isoformat() + "Z")
    report["total_articles"] = int(total_articles)
    report["total_hotspots"] = len(hotspots)
    report["verification_status"] = str(report.get("verification_status") or "待审核")
    report["accuracy_score"] = _bounded_int(report.get("accuracy_score"), 0, 100)
    report["agent_trace"] = _as_list(report.get("agent_trace")) or ["fact_curator:rules", "report_writer:rules", "verifier:rules"]

    takeaways = []
    for item in report.get("top_takeaways") or []:
        hotspot_ids = [value for value in _as_int_list(item.get("hotspot_ids")) if value in known]
        if not hotspot_ids and ranked:
            hotspot_ids = [int(ranked[0]["id"])]
        takeaways.append(
            {
                "label": str(item.get("label") or "重点")[:20],
                "text": str(item.get("text") or "")[:140],
                "hotspot_ids": hotspot_ids[:4],
            }
        )
    report["top_takeaways"] = [item for item in takeaways if item["text"]][:5]

    report["breakout_brands"] = _normalize_hotspot_cards(
        report.get("breakout_brands") or [_briefing_brand_card(item) for item in ranked[:5]],
        known,
        "brand",
    )[:6]
    report["key_news"] = _normalize_hotspot_cards(
        report.get("key_news") or [_briefing_news_card(item) for item in ranked[:8]],
        known,
        "news",
    )[:10]

    actions = []
    for item in report.get("leasing_actions") or _briefing_actions(ranked[:5]):
        hotspot_ids = [value for value in _as_int_list(item.get("hotspot_ids")) if value in known]
        actions.append(
            {
                "priority": str(item.get("priority") or "P1")[:8],
                "action": str(item.get("action") or "")[:80],
                "reason": str(item.get("reason") or "")[:140],
                "hotspot_ids": hotspot_ids[:4],
            }
        )
    report["leasing_actions"] = [item for item in actions if item["action"]][:6]
    report["risk_notes"] = _as_list(report.get("risk_notes"))[:5]
    report["verification_notes"] = _as_list(report.get("verification_notes"))[:6]
    return report


def _normalize_hotspot_cards(cards: list[dict[str, Any]], known: dict[int, dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    output = []
    for card in cards:
        hotspot_id = _coerce_hotspot_id(card.get("hotspot_id"), known)
        if hotspot_id is None:
            continue
        hotspot = known[hotspot_id]
        if mode == "brand":
            output.append(
                {
                    "hotspot_id": hotspot_id,
                    "brand_name": str(card.get("brand_name") or hotspot.get("brand_name") or "")[:40],
                    "signal": str(card.get("signal") or hotspot.get("signal_type") or "")[:24],
                    "why_now": str(card.get("why_now") or hotspot.get("ai_summary") or "")[:140],
                    "leasing_angle": str(card.get("leasing_angle") or hotspot.get("leasing_insight") or "")[:160],
                    "evidence": str(card.get("evidence") or (_as_list(hotspot.get("evidence")) or [""])[0])[:160],
                    "source_name": hotspot.get("source_name", ""),
                    "source_url": hotspot.get("source_url", ""),
                    "score": _bounded_int(card.get("score") or hotspot.get("opportunity_score"), 0, 100),
                }
            )
        else:
            output.append(
                {
                    "hotspot_id": hotspot_id,
                    "title": str(card.get("title") or hotspot.get("title") or "")[:120],
                    "summary": str(card.get("summary") or hotspot.get("ai_summary") or "")[:160],
                    "implication": str(card.get("implication") or hotspot.get("leasing_insight") or "")[:160],
                    "source_name": hotspot.get("source_name", ""),
                    "source_url": hotspot.get("source_url", ""),
                    "tags": _as_list(card.get("tags"))[:5] or _as_list(hotspot.get("tags"))[:5],
                }
            )
    return output


def _briefing_brand_card(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "hotspot_id": item.get("id"),
        "brand_name": item.get("brand_name", ""),
        "signal": item.get("signal_type", ""),
        "why_now": item.get("ai_summary", ""),
        "leasing_angle": item.get("leasing_insight", ""),
        "evidence": (_as_list(item.get("evidence")) or [item.get("title", "")])[0],
        "source_name": item.get("source_name", ""),
        "source_url": item.get("source_url", ""),
        "score": item.get("opportunity_score", 0),
    }


def _briefing_news_card(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "hotspot_id": item.get("id"),
        "title": item.get("title", ""),
        "summary": item.get("ai_summary", ""),
        "implication": item.get("leasing_insight", ""),
        "source_name": item.get("source_name", ""),
        "source_url": item.get("source_url", ""),
        "tags": _as_list(item.get("tags"))[:5],
    }


def _briefing_actions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = []
    if items:
        actions.append(
            {
                "priority": "P0",
                "action": "优先核查榜首品牌的开店模型和区域首进窗口",
                "reason": f"{items[0].get('brand_name', '品牌')}当前招商价值和爆款潜力综合靠前。",
                "hotspot_ids": [items[0].get("id")],
            }
        )
    breakout_ids = [item.get("id") for item in items if item.get("signal_type") in {"国内新兴品牌", "新消费爆款", "社媒爆火"}]
    if breakout_ids:
        actions.append(
            {
                "priority": "P1",
                "action": "把爆火新兴品牌加入本周招商短名单",
                "reason": "这些品牌具备社媒扩散、新店/首店或排队售罄等短期机会信号。",
                "hotspot_ids": breakout_ids[:4],
            }
        )
    funding_ids = [item.get("id") for item in items if item.get("signal_type") == "融资动态"]
    if funding_ids:
        actions.append(
            {
                "priority": "P2",
                "action": "跟踪融资品牌未来三个月拓店计划",
                "reason": "资本支持可能推动品牌进入下一轮线下扩张。",
                "hotspot_ids": funding_ids[:4],
            }
        )
    return actions


def _rank_hotspots_for_briefing(hotspots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def rank(item: dict[str, Any]) -> tuple[int, int, int, int]:
        signal_bonus = 12 if item.get("signal_type") == "国内新兴品牌" else 0
        signal_bonus += 8 if item.get("signal_type") in {"新消费爆款", "社媒爆火"} else 0
        return (
            int(item.get("opportunity_score", 0)) + signal_bonus,
            int(item.get("breakout_score", 0)),
            int(item.get("confidence", 0)),
            int(item.get("relevance", 0)),
        )

    return sorted(hotspots, key=rank, reverse=True)


def _coerce_hotspot_id(value: Any, known: dict[int, dict[str, Any]]) -> int | None:
    try:
        hotspot_id = int(value)
    except (TypeError, ValueError):
        return None
    return hotspot_id if hotspot_id in known else None


def _as_int_list(value: Any) -> list[int]:
    ints = []
    for item in _as_list(value):
        try:
            ints.append(int(item))
        except ValueError:
            continue
    return ints


def _first_match(text: str, rules: list[tuple[str, list[str]]], fallback: str) -> str:
    for label, keywords in rules:
        if any(keyword.lower() in text.lower() for keyword in keywords):
            return label
    return fallback


def _extract_brand(title: str, content: str) -> str:
    quoted = re.search(r"[「『《\"]([^」』》\"]{2,40})[」』》\"]", title)
    if quoted:
        return quoted.group(1)
    english = re.search(r"\b([A-Z][A-Za-z0-9&'\-\s]{2,30})\b", title)
    if english:
        return english.group(1).strip()
    before = re.split(r"[，,：:完成宣布落地首店全国海外]", title)[0]
    return before.replace("品牌", "").strip()[:18] or "待识别品牌"


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?]\s*", text)
    return [part.strip() for part in parts if len(part.strip()) >= 8][:4]


def _score(text: str, base: int) -> int:
    score = base
    for keyword, boost in BOOST_KEYWORDS.items():
        if keyword.lower() in text.lower():
            score += boost
    if any(keyword.lower() in text.lower() for keyword in MATURE_NEWS_KEYWORDS) and not _has_new_brand_signal(text):
        score -= 10
    return max(50, min(98, score))


def _rule_evaluate(article: dict[str, Any]) -> dict[str, Any]:
    text = f"{article.get('title', '')}\n{article.get('excerpt', '')}\n{article.get('content', '')}"
    title = article.get("title", "")
    brand = _extract_brand(title, text)
    category = _first_match(text, CATEGORY_RULES, "生活方式")
    signal = _first_match(text, SIGNAL_RULES, "品牌动态")
    breakout = _score(text, 62)
    opportunity = _score(text, 58)
    confidence = min(96, 72 + (8 if _is_high_quality_source_type(str(article.get("source_type", ""))) else 0))
    relevance = min(97, int((breakout * 0.42) + (opportunity * 0.42) + (confidence * 0.16)))
    evidence = _sentences(article.get("content") or article.get("excerpt") or title)
    summary = evidence[0] if evidence else title
    tags = [category, signal]
    if _has_new_brand_signal(text):
        tags.append("国内新兴")
    if "海外" in text or "国际" in text or "全球" in text:
        tags.append("国际参考")
    if "购物中心" in text or "门店" in text or "首店" in text:
        tags.append("适合线下关注")
    return {
        "brand_name": brand,
        "category": category,
        "signal_type": signal,
        "regions": "全国/国际",
        "ai_summary": summary,
        "leasing_insight": _leasing_insight(category, signal, text),
        "evidence": evidence or [title],
        "tags": tags,
        "confidence": confidence,
        "relevance": relevance,
        "opportunity_score": opportunity,
        "breakout_score": breakout,
        "agent_trace": ["article_rules"],
    }


def _leasing_insight(category: str, signal: str, text: str) -> str:
    if signal == "国内新兴品牌":
        return f"{category}方向出现国内新兴品牌信号，建议优先核查门店模型、社媒热度和武汉/华中首进可能性。"
    if signal == "融资动态":
        return f"品牌获得资本支持，建议关注其下一轮线下拓展节奏与核心商场合作窗口。"
    if signal == "国际新兴品牌":
        return f"具备国际参考价值，可用于寻找差异化首店、快闪或区域首进合作机会。"
    if signal == "社媒爆火":
        return f"社媒讨论度较高，适合评估快闪、主题活动和年轻客群引流价值。"
    if "购物中心" in text:
        return f"{category}方向已有购物中心场景信号，建议进入招商备选清单并核查门店模型。"
    return f"{category}方向出现增长信号，建议跟踪品牌拓店意愿、坪效模型和客群匹配度。"


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


def _deepseek_enabled() -> bool:
    provider = os.getenv("AI_PROVIDER", "").lower()
    requested = os.getenv("USE_DEEPSEEK_AI", "false").lower() == "true"
    return bool(os.getenv("DEEPSEEK_API_KEY")) and (provider == "deepseek" or requested)


def _deepseek_multi_agent_evaluate(article: dict[str, Any]) -> dict[str, Any]:
    fallback = _rule_evaluate(article)
    if os.getenv("AI_MULTI_AGENT", "true").lower() != "true":
        tier = _strategy_tier(article, fallback)
        parsed = _deepseek_agent_json("single", _single_agent_prompt(article), tier=tier)
        result = _ensure_schema({**fallback, **parsed})
        result["agent_trace"] = [f"single:{_deepseek_model(tier)}"]
        return result

    result: dict[str, Any] = {**fallback}
    agent_trace: list[str] = []

    agents = [
        ("extractor", _extractor_prompt(article), "flash"),
        ("credibility", _credibility_prompt(article), "flash"),
        ("leasing_strategy", _strategy_prompt(article, result), _strategy_tier(article, fallback)),
    ]
    for agent_name, prompt, tier in agents:
        try:
            parsed = _deepseek_agent_json(agent_name, prompt, tier=tier)
            _merge_agent_result(result, parsed)
            agent_trace.append(f"{agent_name}:{_deepseek_model(tier)}")
        except Exception:
            agent_trace.append(f"{agent_name}:rules-fallback")

    result["agent_trace"] = agent_trace
    result["tags"] = _as_list(result.get("tags")) + ["DeepSeek多智能体"]
    return _ensure_schema(result)


def _deepseek_agent_json(agent_name: str, user_prompt: str, tier: str = "flash") -> dict[str, Any]:
    model = _deepseek_model(tier)
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是世界城招商热点监测系统中的一个专业智能体。"
                    "只输出一个 JSON 对象，不要 Markdown，不要解释，不要泄露推理过程。"
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60"))) as client:
        response = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(_extract_json(content))
    if not isinstance(parsed, dict):
        raise ValueError(f"{agent_name} did not return a JSON object")
    return parsed


def _deepseek_model(tier: str) -> str:
    if tier == "pro":
        return os.getenv("DEEPSEEK_MODEL_PRO", "deepseek-v4-pro")
    return os.getenv("DEEPSEEK_MODEL_FLASH", "deepseek-v4-flash")


def _strategy_tier(article: dict[str, Any], fallback: dict[str, Any]) -> str:
    if os.getenv("DEEPSEEK_FORCE_PRO", "false").lower() == "true":
        return "pro"
    text = _article_text(article)
    high_signal_words = [
        "新品牌",
        "新兴品牌",
        "新锐",
        "国货",
        "本土品牌",
        "爆款",
        "海外",
        "国际",
        "全球",
        "融资",
        "首店",
        "新店",
        "联名",
        "抢购",
        "社媒",
        "小红书",
    ]
    high_score = max(int(fallback.get("opportunity_score", 0)), int(fallback.get("breakout_score", 0)))
    if high_score >= int(os.getenv("DEEPSEEK_PRO_SCORE_THRESHOLD", "84")):
        return "pro"
    if any(word.lower() in text.lower() for word in high_signal_words):
        return "pro"
    return "flash"


def _article_text(article: dict[str, Any]) -> str:
    return f"{article.get('title', '')}\n{article.get('excerpt', '')}\n{article.get('content', '')[:5000]}"


def _article_context(article: dict[str, Any]) -> str:
    return f"""
标题：{article.get("title", "")}
来源：{article.get("source_name", "")} / {article.get("source_type", "")}
发布时间：{article.get("published_at", "")}
原始链接：{article.get("url", "")}
摘要：{article.get("excerpt", "")}
正文：{article.get("content", "")[:5000]}
"""


def _extractor_prompt(article: dict[str, Any]) -> str:
    return f"""
角色：信息抽取智能体，使用 V4 Flash 处理常规结构化整理。
任务：从公开资讯中抽取招商热点字段。
输出 JSON 字段：
brand_name, category, signal_type, regions, ai_summary, evidence(list), tags(list)

分类建议：
category 从 饮品甜品/餐饮/潮玩文创/零售集合/美妆个护/运动健康/生活方式 中选择。
signal_type 从 国内新兴品牌/新消费爆款/国际新兴品牌/线下扩张/社媒爆火/融资动态/品牌动态 中选择。
优先识别国内新兴品牌、新锐国货、新开首店和处于早期扩张阶段的品牌。成熟连锁的普通新店新闻应降低相关性，除非是新子品牌、首进区域、爆款模型或重大创新。
ai_summary 控制在 80 字以内。
evidence 保留 2-4 条来自原文的事实依据。

资讯：
{_article_context(article)}
"""


def _credibility_prompt(article: dict[str, Any]) -> str:
    return f"""
角色：信源可信度智能体，使用 V4 Flash 做常规核查。
任务：判断资讯是否可信、是否和世界城招商有关。
输出 JSON 字段：
confidence(0-100), relevance(0-100), evidence(list), tags(list)

评分原则：
官方/权威媒体/多事实支撑更高；软文、信息不足、仅情绪描述更低。
招商相关性看是否涉及门店、扩张、首店、线下消费、购物中心、融资、社媒爆火或国际新品牌。
国内新兴品牌、国货新锐品牌、新店/首店/早期拓店线索优先；成熟连锁的常规开店新闻相关性较低。

资讯：
{_article_context(article)}
"""


def _strategy_prompt(article: dict[str, Any], current: dict[str, Any]) -> str:
    return f"""
角色：招商策略智能体。遇到高价值、跨国、爆款、融资、首店、社媒爆火等复杂判断时使用 V4Pro。
任务：判断该品牌是否值得进入世界城招商晨报。
输出 JSON 字段：
opportunity_score(0-100), breakout_score(0-100), leasing_insight, tags(list)

已有初步判断：
{json.dumps(current, ensure_ascii=False)}

要求：
- leasing_insight 必须面向招商团队，说明为什么值得关注，或应该怎么跟进。
- 不要泛泛而谈，要结合原文事实。
- 爆款潜力看新品牌、新锐国货、新店/首店、排队、抢购、社媒话题、联名、售罄、融资、快速开店、国际首店等信号。
- 对成熟品牌的普通开店、门店数更新或周年营销降级；只有新子品牌、首进区域、产品/场景创新或强社媒爆火才建议入选。

资讯：
{_article_context(article)}
"""


def _single_agent_prompt(article: dict[str, Any]) -> str:
    return f"""
你是商业地产招商研究员。请阅读资讯并输出 JSON，不要输出多余文字。
字段：brand_name, category, signal_type, regions, ai_summary, leasing_insight,
evidence(list), tags(list), confidence(0-100), relevance(0-100),
opportunity_score(0-100), breakout_score(0-100)。
优先关注国内新兴品牌、新锐国货、新店/首店、早期拓店、融资和社媒爆火线索；成熟连锁普通开店新闻需要明显创新或首进价值才入选。

资讯：
{_article_context(article)}
"""


def _merge_agent_result(result: dict[str, Any], parsed: dict[str, Any]) -> None:
    for key, value in parsed.items():
        if value in (None, "", []):
            continue
        if key in {"tags", "evidence"}:
            combined = _as_list(result.get(key)) + _as_list(value)
            result[key] = list(dict.fromkeys(str(item) for item in combined if item))
        else:
            result[key] = value


def _ensure_schema(result: dict[str, Any]) -> dict[str, Any]:
    result["brand_name"] = str(result.get("brand_name") or "待识别品牌")[:40]
    result["category"] = str(result.get("category") or "生活方式")
    result["signal_type"] = str(result.get("signal_type") or "品牌动态")
    result["regions"] = str(result.get("regions") or "全国/国际")
    result["ai_summary"] = str(result.get("ai_summary") or "该资讯出现可跟踪的品牌动态。")[:160]
    result["leasing_insight"] = str(result.get("leasing_insight") or _leasing_insight(result["category"], result["signal_type"], ""))
    result["evidence"] = _as_list(result.get("evidence"))[:5] or [result["ai_summary"]]
    result["tags"] = _as_list(result.get("tags"))[:8] or [result["category"], result["signal_type"]]
    for key in ("confidence", "relevance", "opportunity_score", "breakout_score"):
        result[key] = _bounded_int(result.get(key), 50, 98)
    return result


def _has_new_brand_signal(text: str) -> bool:
    terms = ["新品牌", "新兴品牌", "新锐", "国货", "本土品牌", "原创品牌", "首家门店", "区域首店"]
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def _openai_evaluate(article: dict[str, Any]) -> dict[str, Any]:
    prompt = f"""
你是商业地产招商研究员。请阅读资讯并输出 JSON，不要输出多余文字。
字段：brand_name, category, signal_type, regions, ai_summary, leasing_insight,
evidence(list), tags(list), confidence(0-100), relevance(0-100),
opportunity_score(0-100), breakout_score(0-100)。
优先关注国内新兴品牌、新锐国货、新店/首店、早期拓店、融资和社媒爆火线索；成熟连锁普通开店新闻需要明显创新或首进价值才入选。

标题：{article.get("title", "")}
来源：{article.get("source_name", "")} / {article.get("source_type", "")}
摘要：{article.get("excerpt", "")}
正文：{article.get("content", "")[:5000]}
"""
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "input": prompt,
    }
    headers = {
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=45) as client:
        response = client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    text = data.get("output_text", "")
    if not text:
        chunks = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    chunks.append(content.get("text", ""))
        text = "\n".join(chunks)
    parsed = json.loads(_extract_json(text))
    fallback = _rule_evaluate(article)
    fallback.update(parsed)
    fallback["agent_trace"] = ["openai"]
    return fallback


def _extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("AI response did not contain JSON")
    return match.group(0)
