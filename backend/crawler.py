from __future__ import annotations

import os
import re
import time
from urllib.parse import quote_plus, urljoin, urlparse

import feedparser
import httpx
import trafilatura
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}

KEYWORDS = [
    "新店",
    "新品牌",
    "新兴品牌",
    "新锐",
    "国货",
    "本土品牌",
    "新消费",
    "爆款",
    "首店",
    "首家",
    "区域首店",
    "华中首店",
    "武汉首店",
    "开业",
    "开店",
    "入驻",
    "进驻",
    "扩张",
    "融资",
    "联名",
    "快闪",
    "排队",
    "购物中心",
    "招商",
    "品牌",
    "门店",
    "出海",
    "海外",
    "全国",
    "武汉",
    "光谷",
    "增长",
]

DEFAULT_SEARCH_QUERIES = [
    "国内 新兴品牌 新店 开业",
    "中国 新品牌 首店 购物中心",
    "新锐消费品牌 融资 开店",
    "国货品牌 首店 新店",
    "本土品牌 小红书 爆火 门店",
    "新消费品牌 区域首店 商场",
    "餐饮 新品牌 新店 开业",
    "茶饮 咖啡 新品牌 开店",
    "美妆 香氛 新锐品牌 首店",
    "潮玩 文创 新品牌 快闪",
]

SUPPORTED_SEARCH_PROVIDERS = {"tavily", "serper", "serpapi", "brave", "bing"}


def _client() -> httpx.Client:
    return httpx.Client(timeout=float(os.getenv("HTTP_TIMEOUT_SECONDS", "10")), follow_redirects=True, headers=HEADERS)


def _looks_relevant(text: str) -> bool:
    compact = text.lower()
    return any(keyword.lower() in compact for keyword in KEYWORDS)


def _text_excerpt(text: str, limit: int = 180) -> str:
    raw = text or ""
    if "<" in raw and ">" in raw:
        raw = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    cleaned = re.sub(r"\s+", " ", raw).strip()
    return cleaned[:limit]


def extract_article(url: str) -> dict:
    with _client() as client:
        response = client.get(url)
        response.raise_for_status()
        html = response.text

    extracted = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)
    text = extracted or " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
    return {
        "title": title or urlparse(url).netloc,
        "url": url,
        "excerpt": _text_excerpt(text),
        "content": text[:6000],
    }


def fetch_source(source: dict, limit: int = 12) -> tuple[list[dict], list[str]]:
    adapter = source.get("adapter", "html")
    if adapter == "web_search":
        return fetch_web_search(source, limit)
    if adapter == "rss":
        return fetch_rss(source, limit)
    if adapter == "url_list":
        return fetch_url_list(source, limit)
    return fetch_html_index(source, limit)


def fetch_web_search(source: dict, limit: int) -> tuple[list[dict], list[str]]:
    logs: list[str] = []
    articles: list[dict] = []
    started = time.monotonic()
    provider = _search_provider()
    queries = _search_queries(source)
    max_queries = int(os.getenv("SEARCH_MAX_QUERIES_PER_RUN", "8"))
    queries = queries[:max_queries]
    per_query_limit = int(os.getenv("SEARCH_RESULTS_PER_QUERY", str(max(3, min(limit, 8)))))
    total_limit = int(os.getenv("SEARCH_RESULTS_PER_SOURCE", str(max(limit, per_query_limit * len(queries)))))
    fetch_content = os.getenv("SEARCH_FETCH_ARTICLE_CONTENT", "true").lower() == "true"
    content_fetch_limit = int(os.getenv("SEARCH_CONTENT_FETCH_LIMIT", "24"))
    source_time_budget = float(os.getenv("SEARCH_SOURCE_TIME_BUDGET_SECONDS", "45"))
    max_query_failures = int(os.getenv("SEARCH_MAX_QUERY_FAILURES", "3"))
    max_content_failures = int(os.getenv("SEARCH_MAX_CONTENT_FAILURES", "8"))
    query_failures = 0
    content_failures = 0

    if provider:
        logs.append(f"{source['name']} 使用 {provider} 搜索，关键词 {len(queries)} 组")
    else:
        logs.append(f"{source['name']} 未发现搜索 API Key，使用 Google News RSS 关键词搜索兜底")

    seen: set[str] = set()
    for query in queries:
        if len(articles) >= total_limit:
            break
        if _time_budget_exceeded(started, source_time_budget):
            logs.append(f"{source['name']} 搜索达到耗时预算 {source_time_budget:.0f}s，提前停止")
            break
        try:
            results = _search_results(query, per_query_limit, provider)
        except Exception as exc:  # noqa: BLE001
            query_failures += 1
            logs.append(f"{source['name']} 搜索失败：{query} ({exc})")
            if query_failures >= max_query_failures:
                logs.append(f"{source['name']} 搜索失败 {query_failures} 次，触发查询熔断")
                break
            continue

        for result in results:
            if len(articles) >= total_limit:
                break
            if _time_budget_exceeded(started, source_time_budget):
                logs.append(f"{source['name']} 搜索结果处理达到耗时预算 {source_time_budget:.0f}s，提前停止")
                break
            url = result.get("url", "").strip()
            title = result.get("title", "").strip()
            if not url or not title:
                continue
            normalized_url = _canonical_url(url)
            if normalized_url in seen:
                continue
            seen.add(normalized_url)
            article = {
                "title": title,
                "url": url,
                "source_name": f"{source['name']} / {query}",
                "source_type": source.get("source_type", "互联网搜索"),
                "published_at": result.get("published_at", ""),
                "excerpt": _text_excerpt(result.get("excerpt", "")),
                "content": _text_excerpt(result.get("content", "") or result.get("excerpt", ""), 2000),
            }
            if fetch_content and content_fetch_limit > 0:
                try:
                    extracted = extract_article(url)
                    extracted_title = extracted.get("title", "").strip()
                    if extracted_title and extracted_title.lower() not in {"google news", "news"}:
                        article["title"] = extracted_title
                    if extracted.get("excerpt"):
                        article["excerpt"] = extracted["excerpt"]
                    if extracted.get("content"):
                        article["content"] = extracted["content"]
                except Exception as exc:  # noqa: BLE001
                    content_failures += 1
                    logs.append(f"{source['name']} 搜索结果正文读取失败：{title} ({exc})")
                    if content_failures >= max_content_failures:
                        fetch_content = False
                        logs.append(f"{source['name']} 正文读取失败 {content_failures} 次，停止正文抓取，仅保留搜索摘要")
                finally:
                    content_fetch_limit -= 1
            articles.append(article)

    return articles, logs


def fetch_rss(source: dict, limit: int) -> tuple[list[dict], list[str]]:
    logs: list[str] = []
    articles: list[dict] = []
    feed = feedparser.parse(source["url"])
    for entry in feed.entries[:limit]:
        title = getattr(entry, "title", "").strip()
        url = getattr(entry, "link", "").strip()
        if not title or not url:
            continue
        if not _looks_relevant(title):
            continue
        article = {
            "title": title,
            "url": url,
            "source_name": source["name"],
            "source_type": source["source_type"],
            "published_at": getattr(entry, "published", ""),
            "excerpt": _text_excerpt(getattr(entry, "summary", "")),
            "content": _text_excerpt(getattr(entry, "summary", ""), 2000),
        }
        try:
            extracted = extract_article(url)
            extracted_title = extracted.get("title", "").strip()
            if extracted_title and extracted_title.lower() not in {"google news", "news"}:
                article["title"] = extracted_title
            if extracted.get("excerpt"):
                article["excerpt"] = extracted["excerpt"]
            if extracted.get("content"):
                article["content"] = extracted["content"]
        except Exception as exc:  # noqa: BLE001
            logs.append(f"{source['name']} RSS 正文读取失败：{title} ({exc})")
        articles.append(article)
    return articles, logs


def fetch_url_list(source: dict, limit: int) -> tuple[list[dict], list[str]]:
    logs: list[str] = []
    articles: list[dict] = []
    urls = [line.strip() for line in source["url"].splitlines() if line.strip()]
    for url in urls[:limit]:
        try:
            article = extract_article(url)
            article["source_name"] = source["name"]
            article["source_type"] = source["source_type"]
            articles.append(article)
        except Exception as exc:  # noqa: BLE001
            logs.append(f"{source['name']} 公开链接读取失败：{url} ({exc})")
    return articles, logs


def fetch_html_index(source: dict, limit: int) -> tuple[list[dict], list[str]]:
    logs: list[str] = []
    articles: list[dict] = []
    try:
        with _client() as client:
            response = client.get(source["url"])
            response.raise_for_status()
            html = response.text
    except Exception as exc:  # noqa: BLE001
        return [], [f"{source['name']} 首页读取失败：{exc}"]

    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(" ", strip=True)
        href = urljoin(source["url"], anchor["href"])
        if not text or href in seen:
            continue
        if urlparse(href).scheme not in {"http", "https"}:
            continue
        if _looks_relevant(text):
            seen.add(href)
            links.append((text, href))
        if len(links) >= limit:
            break

    for title, url in links:
        article = {
            "title": title,
            "url": url,
            "source_name": source["name"],
            "source_type": source["source_type"],
            "published_at": "",
            "excerpt": "",
            "content": "",
        }
        try:
            article.update(extract_article(url))
        except Exception as exc:  # noqa: BLE001
            article["excerpt"] = title
            article["content"] = title
            logs.append(f"{source['name']} 链接正文读取失败：{title} ({exc})")
        articles.append(article)
    return articles, logs


def _search_queries(source: dict) -> list[str]:
    configured = os.getenv("SEARCH_QUERIES", "").strip()
    if configured:
        return _split_queries(configured)
    notes = str(source.get("notes", ""))
    note_queries = _queries_from_notes(notes)
    if note_queries:
        return note_queries
    url = str(source.get("url", ""))
    if "\n" in url or "," in url:
        url_queries = _split_queries(url)
        if url_queries:
            return url_queries
    return DEFAULT_SEARCH_QUERIES


def _queries_from_notes(notes: str) -> list[str]:
    if "queries:" not in notes.lower():
        return []
    _, raw = re.split(r"queries:", notes, maxsplit=1, flags=re.I)
    return _split_queries(raw)


def _split_queries(raw: str) -> list[str]:
    parts = re.split(r"[\n;；,，]+", raw)
    queries = [part.strip(" ,，") for part in parts if part.strip(" ,，")]
    return list(dict.fromkeys(queries))


def _search_provider() -> str | None:
    requested = os.getenv("SEARCH_PROVIDER", "").strip().lower()
    if requested and requested not in SUPPORTED_SEARCH_PROVIDERS:
        return None
    providers = [requested] if requested else ["tavily", "serper", "serpapi", "brave", "bing"]
    for provider in providers:
        if provider and _search_api_key(provider):
            return provider
    return None


def _search_api_key(provider: str) -> str:
    names = {
        "tavily": ["TAVILY_API_KEY", "SEARCH_API_KEY"],
        "serper": ["SERPER_API_KEY", "SEARCH_API_KEY"],
        "serpapi": ["SERPAPI_API_KEY", "SEARCH_API_KEY"],
        "brave": ["BRAVE_SEARCH_API_KEY", "SEARCH_API_KEY"],
        "bing": ["BING_SEARCH_API_KEY", "AZURE_SEARCH_KEY", "SEARCH_API_KEY"],
    }.get(provider, ["SEARCH_API_KEY"])
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _search_results(query: str, limit: int, provider: str | None) -> list[dict]:
    if provider == "tavily":
        return _search_tavily(query, limit)
    if provider == "serper":
        return _search_serper(query, limit)
    if provider == "serpapi":
        return _search_serpapi(query, limit)
    if provider == "brave":
        return _search_brave(query, limit)
    if provider == "bing":
        return _search_bing(query, limit)
    return _search_google_news(query, limit)


def _search_tavily(query: str, limit: int) -> list[dict]:
    payload = {
        "query": query,
        "search_depth": os.getenv("TAVILY_SEARCH_DEPTH", "basic"),
        "topic": os.getenv("TAVILY_TOPIC", "news"),
        "time_range": os.getenv("SEARCH_TIME_RANGE", "month"),
        "max_results": min(limit, 20),
        "include_answer": False,
        "include_raw_content": os.getenv("TAVILY_INCLUDE_RAW_CONTENT", "false").lower() == "true",
    }
    if os.getenv("TAVILY_TOPIC", "news") == "general":
        payload["country"] = os.getenv("SEARCH_COUNTRY", "china")
    headers = {"Authorization": f"Bearer {_search_api_key('tavily')}", "Content-Type": "application/json"}
    with _client() as client:
        response = client.post("https://api.tavily.com/search", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "excerpt": item.get("content", ""),
            "content": item.get("raw_content") or item.get("content", ""),
            "published_at": item.get("published_date", ""),
        }
        for item in data.get("results", [])
    ]


def _search_serper(query: str, limit: int) -> list[dict]:
    endpoint = os.getenv("SERPER_ENDPOINT", "https://google.serper.dev/search")
    payload = {
        "q": query,
        "gl": os.getenv("SEARCH_GL", "cn"),
        "hl": os.getenv("SEARCH_HL", "zh-cn"),
        "num": min(limit, 20),
    }
    headers = {"X-API-KEY": _search_api_key("serper"), "Content-Type": "application/json"}
    with _client() as client:
        response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return [
        _serper_item(item)
        for item in [*data.get("news", []), *data.get("organic", [])]
        if item.get("link") or item.get("url")
    ]


def _serper_item(item: dict) -> dict:
    return {
        "title": item.get("title", ""),
        "url": item.get("link") or item.get("url", ""),
        "excerpt": item.get("snippet", ""),
        "content": item.get("snippet", ""),
        "published_at": item.get("date", ""),
    }


def _search_serpapi(query: str, limit: int) -> list[dict]:
    params = {
        "engine": os.getenv("SERPAPI_ENGINE", "google"),
        "api_key": _search_api_key("serpapi"),
        "q": query,
        "gl": os.getenv("SEARCH_GL", "cn"),
        "hl": os.getenv("SEARCH_HL", "zh-cn"),
        "num": min(limit, 20),
    }
    with _client() as client:
        response = client.get("https://serpapi.com/search.json", params=params)
        response.raise_for_status()
        data = response.json()
    return [
        _serpapi_item(item)
        for item in [*data.get("news_results", []), *data.get("organic_results", [])]
        if item.get("link")
    ]


def _serpapi_item(item: dict) -> dict:
    return {
        "title": item.get("title", ""),
        "url": item.get("link", ""),
        "excerpt": item.get("snippet", ""),
        "content": item.get("snippet", ""),
        "published_at": item.get("date", ""),
    }


def _search_brave(query: str, limit: int) -> list[dict]:
    params = {
        "q": query,
        "count": min(limit, 20),
        "country": os.getenv("SEARCH_COUNTRY_CODE", "CN"),
        "search_lang": os.getenv("SEARCH_LANG", "zh-hans"),
        "freshness": os.getenv("BRAVE_FRESHNESS", "pm"),
        "extra_snippets": "true",
    }
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": _search_api_key("brave"),
    }
    with _client() as client:
        response = client.get("https://api.search.brave.com/res/v1/web/search", params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
    web_results = data.get("web", {}).get("results", [])
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "excerpt": item.get("description", ""),
            "content": " ".join([item.get("description", ""), *item.get("extra_snippets", [])]),
            "published_at": item.get("age", ""),
        }
        for item in web_results
    ]


def _search_bing(query: str, limit: int) -> list[dict]:
    endpoint = os.getenv("BING_SEARCH_ENDPOINT", "https://api.bing.microsoft.com/v7.0/search")
    params = {
        "q": query,
        "count": min(limit, 20),
        "mkt": os.getenv("BING_MARKET", "zh-CN"),
        "freshness": os.getenv("BING_FRESHNESS", "Month"),
        "responseFilter": "Webpages,News",
    }
    headers = {"Ocp-Apim-Subscription-Key": _search_api_key("bing")}
    with _client() as client:
        response = client.get(endpoint, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
    web_pages = data.get("webPages", {}).get("value", [])
    news_pages = data.get("news", {}).get("value", [])
    return [
        {
            "title": item.get("name", ""),
            "url": item.get("url", ""),
            "excerpt": item.get("snippet") or item.get("description", ""),
            "content": item.get("snippet") or item.get("description", ""),
            "published_at": item.get("datePublished", ""),
        }
        for item in [*news_pages, *web_pages]
    ]


def _search_google_news(query: str, limit: int) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    )
    feed = feedparser.parse(url)
    results: list[dict] = []
    for entry in feed.entries[:limit]:
        results.append(
            {
                "title": getattr(entry, "title", ""),
                "url": getattr(entry, "link", ""),
                "excerpt": _text_excerpt(getattr(entry, "summary", "")),
                "content": _text_excerpt(getattr(entry, "summary", ""), 2000),
                "published_at": getattr(entry, "published", ""),
            }
        )
    return results


def _time_budget_exceeded(started: float, budget_seconds: float) -> bool:
    return budget_seconds > 0 and (time.monotonic() - started) >= budget_seconds


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl().lower().rstrip("/")
