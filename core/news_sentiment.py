"""
news_sentiment.py
-----------------
Fetches recent headlines via yfinance, then scores sentiment.
- If ANTHROPIC_API_KEY is set and has credits: uses Claude for accurate analysis
- Otherwise: keyword-based scorer (free, no API needed)
Results cached 30 min so engine doesn't spam on every cycle.
"""

import json
import re
import time
import contextlib
import io

import config

_cache: dict = {}
CACHE_TTL = 30 * 60   # 30 minutes

EMPTY = {"sentiment": "NEUTRAL", "confidence": 0.0, "summary": "No data.", "headlines": []}

BEARISH_WORDS = [
    "crash", "collapse", "plunge", "tumble", "dive", "sink", "fall", "drop", "decline",
    "loss", "losses", "miss", "misses", "disappoint", "disappointing", "weak", "warning",
    "recession", "slowdown", "downturn", "deficit", "debt", "bankrupt", "layoff", "layoffs",
    "cut", "cuts", "downgrade", "sell-off", "selloff", "bear", "bearish", "fear", "fears",
    "concern", "concerns", "risk", "risks", "uncertainty", "volatile", "inflation",
    "tariff", "tariffs", "sanction", "sanctions", "war", "conflict", "crisis", "shortage",
    "below expectations", "lower than expected", "revenue miss", "earnings miss",
    "guidance cut", "lower guidance", "headwinds", "pressure", "hurt", "damage",
]

BULLISH_WORDS = [
    "rally", "surge", "soar", "jump", "climb", "rise", "gain", "gains", "record",
    "beat", "beats", "exceed", "exceeds", "strong", "strength", "growth", "growing",
    "profit", "revenue beat", "earnings beat", "upgrade", "buy", "bullish", "optimism",
    "recovery", "rebound", "boom", "expansion", "breakout", "high", "new high",
    "above expectations", "better than expected", "raised guidance", "positive",
    "outperform", "momentum", "demand", "innovation", "deal", "partnership", "contract",
    "dividend", "buyback", "acquisition",
]


def get_news_sentiment(symbol: str, force: bool = False) -> dict:
    now = time.time()
    if not force and symbol in _cache and _cache[symbol]["expires"] > now:
        return _cache[symbol]["data"]
    result = _fetch_and_analyze(symbol)
    _cache[symbol] = {"data": result, "expires": now + CACHE_TTL}
    return result


def _fetch_headlines(symbol: str) -> list:
    try:
        import yfinance as yf
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            items = yf.Ticker(symbol).news or []
        headlines = []
        for item in items[:10]:
            content = item.get("content", item)
            title   = content.get("title", "").strip()
            pub     = (content.get("provider") or {}).get("displayName", "") or content.get("publisher", "")
            if title:
                headlines.append(f"• {title}" + (f" [{pub}]" if pub else ""))
        return headlines
    except Exception:
        return []


def _keyword_sentiment(headlines: list) -> dict:
    """Score headlines using a bullish/bearish word list."""
    text = " ".join(headlines).lower()

    bull = sum(1 for w in BULLISH_WORDS if w in text)
    bear = sum(1 for w in BEARISH_WORDS if w in text)
    total = bull + bear

    if total == 0:
        return {
            "sentiment": "NEUTRAL", "confidence": 0.3,
            "summary": "No strong signals in headlines.",
            "headlines": headlines, "source": "keyword",
        }

    score = (bull - bear) / total   # -1 to +1
    conf  = round(min(abs(score) * 1.5, 0.9), 2)  # scale up, cap at 0.9

    if score > 0.15:
        sent = "BULLISH"
        summ = f"{bull} bullish vs {bear} bearish signals in headlines"
    elif score < -0.15:
        sent = "BEARISH"
        summ = f"{bear} bearish vs {bull} bullish signals in headlines"
    else:
        sent = "NEUTRAL"
        summ = f"Mixed signals ({bull} bullish, {bear} bearish)"
        conf = round(conf * 0.5, 2)

    return {
        "sentiment": sent, "confidence": conf,
        "summary": summ, "headlines": headlines, "source": "keyword",
    }


def _fetch_and_analyze(symbol: str) -> dict:
    headlines = _fetch_headlines(symbol)

    if not headlines:
        return {**EMPTY, "summary": "No recent headlines found."}

    # Try Claude API first
    api_key = getattr(config, "ANTHROPIC_API_KEY", "")
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            prompt = (
                f"Analyze these recent {symbol} news headlines for short-term trading sentiment.\n"
                f"Reply ONLY with valid JSON — no markdown, no explanation:\n"
                f'{{ "sentiment": "BULLISH|BEARISH|NEUTRAL", "confidence": 0.0-1.0, "summary": "≤12 words" }}\n\n'
                f"Headlines:\n" + "\n".join(headlines)
            )
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=120,
                messages=[{"role": "user", "content": prompt}],
            )
            raw  = resp.content[0].text.strip()
            m    = re.search(r"\{[^}]+\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                sent = data.get("sentiment", "NEUTRAL").upper()
                if sent not in ("BULLISH", "BEARISH", "NEUTRAL"):
                    sent = "NEUTRAL"
                return {
                    "sentiment":  sent,
                    "confidence": round(min(max(float(data.get("confidence", 0.5)), 0.0), 1.0), 2),
                    "summary":    str(data.get("summary", ""))[:80],
                    "headlines":  headlines,
                    "source":     "claude",
                }
        except Exception:
            pass   # fall through to keyword scorer

    # Free keyword fallback
    return _keyword_sentiment(headlines)
