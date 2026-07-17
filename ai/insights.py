"""
AI insights — on-demand Claude-powered trade thesis synthesis and news curation.

Design goals:
  - On-demand + cached (not run on every scheduler tick) to control API spend.
  - Degrades gracefully with no API keys set: falls back through
    NewsAPI -> yfinance news -> Google News RSS for articles, and skips the
    Claude synthesis step entirely if ANTHROPIC_API_KEY is unset.
  - The thesis explicitly calls out when the technical signal and news
    sentiment agree or conflict — that correlation is the actual product,
    not just "AI describes the chart."
"""
import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import httpx

from api.config import settings

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "This is a probabilistic technical/informational read, not investment advice. "
    "Past patterns and news sentiment do not guarantee future results."
)

# ── Cache ────────────────────────────────────────────────────────────────────

_insight_cache: dict = {}  # ticker -> {"data": {...}, "ts": float}


def _cache_get(ticker: str) -> Optional[dict]:
    entry = _insight_cache.get(ticker)
    if entry and (time.time() - entry["ts"]) < settings.AI_INSIGHT_CACHE_TTL_SEC:
        return entry["data"]
    return None


def _cache_set(ticker: str, data: dict):
    _insight_cache[ticker] = {"data": data, "ts": time.time()}


# ── Article sourcing (NewsAPI -> yfinance -> Google News RSS) ───────────────

def _fetch_newsapi(ticker: str, limit: int = 8, query: str = None) -> list:
    if not settings.NEWS_API_KEY:
        return []
    try:
        resp = httpx.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query or ticker,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": limit,
                "apiKey": settings.NEWS_API_KEY,
            },
            timeout=8,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        return [
            {
                "title": a.get("title"),
                "url": a.get("url"),
                "source": (a.get("source") or {}).get("name"),
                "published_at": a.get("publishedAt"),
            }
            for a in articles if a.get("title")
        ]
    except Exception as exc:
        logger.warning(f"NewsAPI fetch failed for {ticker}: {exc}")
        return []


def _fetch_yfinance_news(ticker: str, limit: int = 8) -> list:
    try:
        import yfinance as yf
        items = yf.Ticker(ticker).news or []
        out = []
        for item in items[:limit]:
            # yfinance's news schema has shifted across versions — handle both.
            content = item.get("content", item)
            title = content.get("title") or item.get("title")
            url = ((content.get("canonicalUrl") or {}).get("url")
                   or item.get("link"))
            provider = (content.get("provider") or {}).get("displayName")
            pub_date = content.get("pubDate") or item.get("providerPublishTime")
            if title:
                out.append({
                    "title": title, "url": url,
                    "source": provider, "published_at": pub_date,
                })
        return out
    except Exception as exc:
        logger.warning(f"yfinance news fetch failed for {ticker}: {exc}")
        return []


def _fetch_google_news_rss(ticker: str, limit: int = 8, query: str = None) -> list:
    try:
        resp = httpx.get(
            "https://news.google.com/rss/search",
            params={"q": query or f"{ticker} stock", "hl": "en-US", "gl": "US", "ceid": "US:en"},
            timeout=8,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        out = []
        for item in root.findall(".//item")[:limit]:
            title = item.findtext("title")
            if not title:
                continue
            source_el = item.find("source")
            out.append({
                "title": title,
                "url": item.findtext("link"),
                "source": source_el.text if source_el is not None else "Google News",
                "published_at": item.findtext("pubDate"),
            })
        return out
    except Exception as exc:
        logger.warning(f"Google News RSS fetch failed for {ticker}: {exc}")
        return []


def fetch_articles(ticker: str, limit: int = 8, query: str = None) -> list:
    """Try NewsAPI, then yfinance, then Google News RSS — first non-empty source wins.

    `query` overrides the search text sent to NewsAPI/Google (yfinance's own
    news is inherently ticker-scoped, so it ignores this). Worth passing for
    tickers that are also common English words/abbreviations — e.g. broad
    market ETFs like SPY, DIA, IWM — where a bare ticker search pulls in
    unrelated noise ("spy" the word, "Dia de los Muertos", etc.).
    """
    articles = _fetch_newsapi(ticker, limit, query=query)
    if articles:
        return articles
    articles = _fetch_yfinance_news(ticker, limit)
    if articles:
        return articles
    return _fetch_google_news_rss(ticker, limit, query=query)


# ── Claude synthesis ─────────────────────────────────────────────────────────

def _client():
    if not settings.ANTHROPIC_API_KEY:
        return None
    from anthropic import Anthropic
    return Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def get_anthropic_client():
    """Public accessor — reused by newsletter/generator.py for the same
    graceful-degrade-with-no-key behavior."""
    return _client()


def curate_articles(ticker: str, articles: list) -> list:
    """Rank the most relevant articles and tag each with sentiment + a one-line
    relevance blurb via Claude Haiku. Falls back to the raw top-5 with no
    annotation if no API key is configured or the call fails."""
    if not articles:
        return []

    client = _client()
    if client is None:
        return [{**a, "sentiment": None, "why_it_matters": None} for a in articles[:5]]

    listing = "\n".join(
        f"{i + 1}. {a['title']} ({a.get('source') or 'unknown source'})"
        for i, a in enumerate(articles)
    )
    prompt = (
        f"Ticker: {ticker}\nRecent headlines:\n{listing}\n\n"
        "Pick the 5 most relevant to this stock's near-term price action. "
        "Return ONLY a JSON array, no prose, no markdown fences. Each item: "
        '{"index": <1-based index from the list above>, '
        '"sentiment": "bullish"|"bearish"|"neutral", '
        '"why_it_matters": "<one short plain-English sentence>"}'
    )
    try:
        msg = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        ranked = json.loads(msg.content[0].text.strip())
        out = []
        for r in ranked:
            idx = r.get("index", 0) - 1
            if 0 <= idx < len(articles):
                out.append({
                    **articles[idx],
                    "sentiment": r.get("sentiment"),
                    "why_it_matters": r.get("why_it_matters"),
                })
        return out or [{**a, "sentiment": None, "why_it_matters": None} for a in articles[:5]]
    except Exception as exc:
        logger.warning(f"Article curation failed for {ticker}: {exc}")
        return [{**a, "sentiment": None, "why_it_matters": None} for a in articles[:5]]


def get_trade_thesis(ticker: str, technicals: dict, articles: list) -> Optional[str]:
    """Synthesize technicals + news sentiment into one grounded paragraph.
    Returns None if no Anthropic key is configured."""
    client = _client()
    if client is None:
        return None

    sentiments = [a["sentiment"] for a in articles if a.get("sentiment")]
    bullish = sentiments.count("bullish")
    bearish = sentiments.count("bearish")
    neutral = len(sentiments) - bullish - bearish

    tech_summary = (
        f"Pattern: {technicals.get('pattern', '—')} "
        f"(confidence {technicals.get('confidence', '—')}/100), "
        f"Signal: {technicals.get('signal', '—')}, "
        f"RSI: {technicals.get('rsi', '—')}, MACD: {technicals.get('macd', '—')}, "
        f"Risk: {technicals.get('risk', '—')}."
    )
    news_summary = f"{bullish} bullish / {bearish} bearish / {neutral} neutral recent headlines."

    prompt = (
        f"You are an equity technical-analysis assistant for ticker {ticker}.\n"
        f"Technical read: {tech_summary}\n"
        f"News sentiment: {news_summary}\n\n"
        "Write a 3-4 sentence synthesis for a retail trader. Explicitly state "
        "whether the technical signal and news sentiment AGREE or CONFLICT, and "
        "what that combination has tended to mean. Be concrete and specific to "
        "the numbers given — no generic filler, no restating the numbers verbatim. "
        "End with one short disclaimer clause. Plain text, no markdown."
    )
    try:
        msg = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        logger.error(f"Trade thesis generation failed for {ticker}: {exc}")
        return None


def build_insight(ticker: str, technicals: dict, force_refresh: bool = False) -> dict:
    """Full AI insight payload for a ticker, cached per AI_INSIGHT_CACHE_TTL_SEC."""
    ticker = ticker.upper().strip()
    if not force_refresh:
        cached = _cache_get(ticker)
        if cached:
            return cached

    raw_articles = fetch_articles(ticker)
    articles = curate_articles(ticker, raw_articles)
    thesis = get_trade_thesis(ticker, technicals, articles)

    sentiments = [a["sentiment"] for a in articles if a.get("sentiment")]
    bullish, bearish = sentiments.count("bullish"), sentiments.count("bearish")
    signal = (technicals.get("signal") or "").upper()
    conflict = (
        (signal == "BUY" and bearish > bullish) or
        (signal == "SELL" and bullish > bearish)
    )

    data = {
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ai_enabled": bool(settings.ANTHROPIC_API_KEY),
        "thesis": thesis,
        "conflict_flag": conflict,
        "articles": articles,
        "disclaimer": _DISCLAIMER,
    }
    _cache_set(ticker, data)
    return data
