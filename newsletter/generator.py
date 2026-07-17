"""
Weekly AI-generated newsletter draft — market-wide recap, not scoped to any
one user's watchlist (avoids leaking one subscriber's positions to everyone
else's inbox). Drafts are never auto-sent: see api/endpoints/newsletter_admin.py
for the human-approval step required before anything goes out.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ai.insights import fetch_articles, curate_articles, get_anthropic_client
from scheduler.price_fetcher import fetch_history
from core.engine import run_analysis
from db.models import NewsletterIssue

logger = logging.getLogger(__name__)

# Broad market ETFs — a global market recap, independent of any user's own
# watchlist, so the newsletter can't accidentally expose one subscriber's
# positions to every other subscriber.
MARKET_PULSE_TICKERS = ["SPY", "QQQ", "DIA", "IWM"]

# These tickers double as common English words/abbreviations ("spy", "Dia de
# los Muertos", ...), so a bare-ticker news search pulls in unrelated noise —
# search by full name instead.
_NEWS_QUERY_OVERRIDE = {
    "SPY": "S&P 500 stock market",
    "QQQ": "Nasdaq 100 stock market",
    "DIA": "Dow Jones stock market",
    "IWM": "Russell 2000 small cap stocks",
}


def _collect_ticker_summary(ticker: str) -> dict:
    summary = {"ticker": ticker, "pattern": "—", "signal": "WATCH", "confidence": None, "articles": []}
    try:
        df = fetch_history(ticker, period="1mo")
        if df is not None and len(df) >= 20:
            analysis = run_analysis(df=df.copy())
            ta = next((r for r in analysis.results if r.ticker == ticker), None)
            if ta and ta.top_pattern:
                summary["pattern"]    = ta.top_pattern.pattern_type.value.replace("_", " ").title()
                summary["confidence"] = round(ta.top_pattern.confidence_score, 1)
                summary["signal"]     = ta.trade_recommendation.signal.value if ta.trade_recommendation else "WATCH"
    except Exception as exc:
        logger.warning(f"Newsletter: technical summary failed for {ticker}: {exc}")

    try:
        query = _NEWS_QUERY_OVERRIDE.get(ticker)
        articles = curate_articles(ticker, fetch_articles(ticker, limit=6, query=query))
        summary["articles"] = articles[:3]
    except Exception as exc:
        logger.warning(f"Newsletter: article curation failed for {ticker}: {exc}")

    return summary


def _fallback_html(summaries: list) -> str:
    """Used when no ANTHROPIC_API_KEY is set — a plain templated recap so the
    feature still works end-to-end without AI."""
    rows = ""
    for s in summaries:
        arts = "".join(f"<li>{a['title']} ({a.get('source') or 'unknown'})</li>" for a in s["articles"])
        rows += (
            f"<h3>{s['ticker']}</h3>"
            f"<p>Pattern: {s['pattern']} · Signal: {s['signal']}"
            f"{' · Confidence ' + str(s['confidence']) + '/100' if s['confidence'] is not None else ''}</p>"
            f"<ul>{arts}</ul>"
        )
    return f"<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;'>{rows}</div>"


def _ai_html(summaries: list) -> str:
    client = get_anthropic_client()
    if client is None:
        return _fallback_html(summaries)

    blocks = []
    for s in summaries:
        headlines = "; ".join(a["title"] for a in s["articles"]) or "no major headlines this week"
        blocks.append(
            f"{s['ticker']}: pattern={s['pattern']}, signal={s['signal']}, "
            f"confidence={s['confidence']}. Headlines: {headlines}"
        )
    data_block = "\n".join(blocks)

    prompt = (
        "Write this week's market recap newsletter for retail traders using the "
        f"data below on the major market ETFs (S&P 500, Nasdaq 100, Dow, Russell 2000):\n\n"
        f"{data_block}\n\n"
        "Output clean HTML (no <html>/<head>/<body> tags, just inner content): a short "
        "intro paragraph on the week's overall tone, then one short section per ticker "
        "covering the technical setup and what the news flow means for it, and a closing "
        "one-line disclaimer that this is not investment advice. Friendly but concrete, "
        "no filler. Use <h2>/<h3>/<p>/<ul> tags, inline styles only (no <style> blocks, "
        "since this goes into an email client)."
    )
    try:
        msg = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        logger.error(f"Newsletter AI synthesis failed: {exc}")
        return _fallback_html(summaries)


def generate_draft(db: Session) -> NewsletterIssue:
    """Fetches this week's market data + news, writes a draft, and stores it
    with status='draft'. Never sends anything — see newsletter_admin.py."""
    summaries = [_collect_ticker_summary(t) for t in MARKET_PULSE_TICKERS]
    html = _ai_html(summaries)

    week_label = f"Week of {datetime.now(timezone.utc).strftime('%B %-d, %Y')}"
    issue = NewsletterIssue(
        week_label=week_label,
        subject=f"Market Pulse — {week_label}",
        content_html=html,
        status="draft",
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue
