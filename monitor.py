"""
Trump / Iran / Gold Event Monitor
Polls multiple news sources for keywords relevant to gold/oil/macro trading.
Sends Telegram notifications when matches found.
"""

import os
import time
import hashlib
import logging
import feedparser
import requests
from datetime import datetime, timezone

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
POLL_INTERVAL    = int(os.environ.get("POLL_INTERVAL", "180"))

# ── Keywords ──────────────────────────────────────────────────────────────────
# Tier 1 — Iran/oil chain, direct gold impact
# Specific enough to avoid false positives from general Middle East news
TIER1 = [
    "iran ceasefire",
    "iran deal",
    "iran nuclear deal",
    "iran sanctions",
    "iran strike",
    "iran attack",
    "strike iran",
    "attack iran",
    "ceasefire iran",
    "us and iran",
    "strait of hormuz",
    "hormuz",
    "kharg island",
    "tehran nuclear",
    "iran oil",
    "persian gulf blockade",
    "trump iran",
    "us iran",
    " iran ",
    "iran'",
]

# Tier 2 — Fed/macro chain
TIER2 = [
    "federal reserve rate",
    "fed rate cut",
    "fed rate hike",
    "interest rate decision",
    "fomc",
    "jerome powell",
    "kevin warsh",
    "tariff china",
    "china tariff",
    "trade war",
    "opec production",
    "opec cut",
    "oil embargo",
]

# Tier 3 — Broad geopolitical awareness only
# Kept specific to avoid Israel/Lebanon/Gaza spam
TIER3 = [
    "taiwan strait",
    "north korea missile",
    "nuclear launch",
    "nato article 5",
    "world war",
]

ALL_KEYWORDS = TIER1 + TIER2 + TIER3

# ── News sources ──────────────────────────────────────────────────────────────
# AP Top News and Reuters RSSHub URLs were failing — replaced with direct feeds
FEEDS = [
    {
        "name": "Al Jazeera",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
    },
    {
        "name": "BBC World",
        "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
    },
    {
        "name": "Sky News World",
        "url": "https://feeds.skynews.com/feeds/rss/world.xml",
    },
    {
        "name": "Fox News World",
        "url": "https://moxie.foxnews.com/google-publisher/world.xml",
    },
    {
        "name": "Politico",
        "url": "https://www.politico.com/rss/politicopicks.xml",
    },
    # Truth Social — add your RSSHub URL here once deployed
    # {
    #     "name": "Truth Social",
    #     "url": "https://YOUR-RSSHUB.railway.app/truthsocial/user/realDonaldTrump",
    # },
]

# ── State ─────────────────────────────────────────────────────────────────────
seen_ids: set[str] = set()


def get_item_id(entry) -> str:
    raw = getattr(entry, "id", None) or getattr(entry, "link", None) or entry.get("title", "")
    return hashlib.md5(raw.encode()).hexdigest()


def classify_keywords(text: str) -> tuple[list[str], int]:
    text_lower = text.lower()
    matched = [k for k in ALL_KEYWORDS if k in text_lower]
    if not matched:
        return [], 0
    tier = 3
    for k in matched:
        if k in TIER1:
            tier = min(tier, 1)
        elif k in TIER2:
            tier = min(tier, 2)
    return matched, tier


def send_telegram(message: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=10
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


def tier_emoji(tier: int) -> str:
    return {1: "🚨", 2: "⚠️", 3: "📡"}.get(tier, "📡")


def check_feed(feed: dict) -> int:
    alerts = 0
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; MarketMonitor/1.0)"}
        parsed = feedparser.parse(feed["url"], request_headers=headers)

        if parsed.bozo and not parsed.entries:
            log.warning(f"Feed issue [{feed['name']}]: {parsed.bozo_exception}")
            return 0

        for entry in parsed.entries:
            item_id = get_item_id(entry)
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            title   = getattr(entry, "title",   "")
            summary = getattr(entry, "summary", "")
            link    = getattr(entry, "link",    "")
            text    = f"{title} {summary}"

            matched, tier = classify_keywords(text)
            if not matched:
                continue

            emoji = tier_emoji(tier)
            ts = datetime.now(timezone.utc).strftime("%H:%M UTC")

            message = (
                f"{emoji} <b>Tier {tier} — {feed['name']}</b>  {ts}\n"
                f"Keywords: <code>{', '.join(matched)}</code>\n\n"
                f"<b>{title}</b>\n\n"
                f"{summary[:280]}{'...' if len(summary) > 280 else ''}\n\n"
                f"🔗 {link}"
            )

            log.info(f"MATCH [{feed['name']}] tier={tier} kw={matched} '{title[:60]}'")
            send_telegram(message)
            alerts += 1

    except Exception as e:
        log.error(f"Error [{feed['name']}]: {e}")

    return alerts


def startup_message():
    msg = (
        "✅ <b>Market Monitor Online</b>\n"
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Polling every {POLL_INTERVAL}s · {len(FEEDS)} sources\n\n"
        f"🚨 Tier 1 Iran/Oil: {len(TIER1)} phrases\n"
        f"⚠️ Tier 2 Fed/Macro: {len(TIER2)} phrases\n"
        f"📡 Tier 3 Geopolitical: {len(TIER3)} phrases"
    )
    send_telegram(msg)


def main():
    log.info("Market Monitor starting...")
    startup_message()
    cycle = 0
    while True:
        cycle += 1
        log.info(f"Cycle {cycle} — checking {len(FEEDS)} feeds...")
        alerts = 0
        for feed in FEEDS:
            alerts += check_feed(feed)
            time.sleep(1)
        log.info(f"Cycle {cycle} complete — {alerts} alerts sent")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
