"""
Trump / Iran / Gold Event Monitor
Polls multiple news sources and Truth Social mirrors for keywords
Sends Telegram notifications when matches found
"""

import os
import time
import hashlib
import logging
import feedparser
import requests
from datetime import datetime, timezone

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ── Config from environment variables ────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]      # from BotFather
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]    # your chat ID
POLL_INTERVAL    = int(os.environ.get("POLL_INTERVAL", "180"))  # seconds

# ── Keywords ─────────────────────────────────────────────────────────────────
# Tier 1 — immediate market impact (Iran/oil chain)
TIER1 = [
    "iran", "hormuz", "strait of hormuz", "ceasefire", "cease-fire",
    "nuclear deal", "strait", "kharg", "tehran", "ayatollah",
    "oil embargo", "sanctions iran", "persian gulf",
]

# Tier 2 — Fed/macro chain
TIER2 = [
    "federal reserve", "interest rate", "rate cut", "rate hike",
    "tariff", "trade war", "china tariff", "inflation",
    "opec", "oil price", "crude oil",
]

# Tier 3 — geopolitical tail risk
TIER3 = [
    "taiwan", "north korea", "ukraine", "nato", "missile",
    "nuclear", "attack", "strike", "bomb", "war",
]

ALL_KEYWORDS = TIER1 + TIER2 + TIER3

# ── Sources ───────────────────────────────────────────────────────────────────
# Truth Social blocks server-side requests, so we use:
# 1. Multiple news RSS feeds that cover Trump statements in near-real-time
# 2. Truth Social via RSS-Bridge proxy (self-hostable, or public instances)
# 3. Politico/AP Trump-specific feeds

FEEDS = [
    # News wires — fastest to pick up Trump statements
    {
        "name": "AP Top News",
        "url": "https://rsshub.app/apnews/topics/apf-usnews",
        "tier": 1
    },
    {
        "name": "Reuters World",
        "url": "https://rsshub.app/reuters/world",
        "tier": 1
    },
    {
        "name": "Al Jazeera",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "tier": 1
    },
    {
        "name": "BBC World",
        "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "tier": 1
    },
    # Truth Social via RSSHub (open source, self-hostable)
    # Deploy your own: https://github.com/DIYgod/RSSHub
    # Or use a public instance — replace with your own RSSHub URL
    {
        "name": "Truth Social (RSSHub)",
        "url": "https://rsshub.app/truthsocial/user/realDonaldTrump",
        "tier": 1
    },
    # Politico breaking news
    {
        "name": "Politico Breaking",
        "url": "https://www.politico.com/rss/politicopicks.xml",
        "tier": 2
    },
]

# ── State: track seen item IDs so we don't re-alert ──────────────────────────
seen_ids: set[str] = set()


def get_item_id(entry) -> str:
    """Generate a stable unique ID for a feed entry."""
    raw = getattr(entry, "id", None) or getattr(entry, "link", None) or entry.get("title", "")
    return hashlib.md5(raw.encode()).hexdigest()


def classify_keywords(text: str) -> tuple[list[str], int]:
    """Return matched keywords and the highest tier matched."""
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
    """Send a Telegram message. Returns True on success."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


def tier_emoji(tier: int) -> str:
    return {1: "🚨", 2: "⚠️", 3: "📡"}.get(tier, "📡")


def check_feed(feed: dict) -> int:
    """Check a single feed. Returns count of alerts sent."""
    alerts = 0
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TrumpMonitor/1.0)"}
        parsed = feedparser.parse(feed["url"], request_headers=headers)

        if parsed.bozo and not parsed.entries:
            log.warning(f"Feed parse issue [{feed['name']}]: {parsed.bozo_exception}")
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
            timestamp = datetime.now(timezone.utc).strftime("%H:%M UTC")

            message = (
                f"{emoji} <b>ALERT — Tier {tier} keywords detected</b>\n"
                f"Source: {feed['name']}  |  {timestamp}\n"
                f"Keywords: <code>{', '.join(matched)}</code>\n\n"
                f"<b>{title}</b>\n\n"
                f"{summary[:300]}{'...' if len(summary) > 300 else ''}\n\n"
                f"🔗 {link}"
            )

            log.info(f"MATCH [{feed['name']}] tier={tier} keywords={matched} title={title[:60]}")
            send_telegram(message)
            alerts += 1

    except Exception as e:
        log.error(f"Error checking feed [{feed['name']}]: {e}")

    return alerts


def startup_message():
    """Send a startup notification so you know the bot is live."""
    msg = (
        "✅ <b>Trump/Market Monitor Online</b>\n"
        f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Polling every {POLL_INTERVAL}s across {len(FEEDS)} sources\n\n"
        f"Tier 1 🚨 Iran/Oil chain: {len(TIER1)} keywords\n"
        f"Tier 2 ⚠️ Fed/Macro chain: {len(TIER2)} keywords\n"
        f"Tier 3 📡 Geopolitical tail: {len(TIER3)} keywords"
    )
    send_telegram(msg)


def main():
    log.info("Trump/Market Monitor starting...")
    startup_message()

    cycle = 0
    while True:
        cycle += 1
        log.info(f"Cycle {cycle} — checking {len(FEEDS)} feeds...")

        total_alerts = 0
        for feed in FEEDS:
            alerts = check_feed(feed)
            total_alerts += alerts
            time.sleep(1)  # polite delay between feed requests

        log.info(f"Cycle {cycle} complete — {total_alerts} alerts sent")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
