"""
Trump / Iran / Gold Event Monitor
Monitors Trump's Truth Social posts for market-relevant keywords.
Sends Telegram push notifications on matches.
Only alerts on NEW posts — persists seen IDs across restarts.
"""

import os
import re
import time
import hashlib
import logging
import feedparser
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
POLL_INTERVAL    = int(os.environ.get("POLL_INTERVAL", "180"))
SEEN_IDS_FILE    = "/tmp/seen_ids.txt"

TIER1 = [
    "iran ceasefire", "iran deal", "iran nuclear deal", "iran sanctions",
    "iran strike", "iran attack", "strike iran", "attack iran",
    "ceasefire iran", "us and iran", "strait of hormuz", "hormuz",
    "kharg island", "tehran nuclear", "iran oil", "persian gulf blockade",
    "trump iran", "us iran", " iran ", "iran ",
]

TIER2 = [
    "federal reserve rate", "fed rate cut", "fed rate hike",
    "interest rate decision", "fomc", "jerome powell", "kevin warsh",
    "tariff china", "china tariff", "trade war",
    "opec production", "opec cut", "oil embargo",
]

TIER3 = [
    "taiwan strait", "north korea missile", "nuclear launch",
    "nato article 5", "world war",
]

ALL_KEYWORDS = TIER1 + TIER2 + TIER3

FEEDS = [
    {
        "name": "Trump Truth Social",
        "url": "https://www.trumpstruth.org/feed",
        "trump_only": True,
    },
]


def load_seen_ids():
    try:
        with open(SEEN_IDS_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()


def save_seen_ids(seen):
    try:
        with open(SEEN_IDS_FILE, "w") as f:
            f.write("\n".join(seen))
    except Exception as e:
        log.error(f"Failed to save seen_ids: {e}")


seen_ids = load_seen_ids()


def get_item_id(entry):
    raw = getattr(entry, "id", None) or getattr(entry, "link", None) or entry.get("title", "")
    return hashlib.md5(raw.encode()).hexdigest()


def classify_keywords(text):
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


def strip_html(text):
    return re.sub(r'<[^>]+>', '', text).strip()


def clean_text(text):
    return (text
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'"))


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message[:4000],
                "disable_web_page_preview": True,
            },
            timeout=10
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


def tier_emoji(tier):
    return {1: "🚨", 2: "⚠️", 3: "📡"}.get(tier, "📡")


def backfill_seen_ids():
    """On fresh start, mark all currently visible posts as seen without alerting.
    This prevents replaying old posts every time the container restarts."""
    log.info("Fresh start — backfilling current feed to skip old posts...")
    count = 0
    for feed in FEEDS:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; MarketMonitor/1.0)"}
            parsed = feedparser.parse(feed["url"], request_headers=headers)
            for entry in parsed.entries:
                item_id = get_item_id(entry)
                if item_id not in seen_ids:
                    seen_ids.add(item_id)
                    count += 1
        except Exception as e:
            log.error(f"Backfill error [{feed['name']}]: {e}")
    save_seen_ids(seen_ids)
    log.info(f"Backfilled {count} existing posts — only NEW posts will alert from now on")


def check_feed(feed):
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

            # Mark as seen immediately — even if no keyword match
            seen_ids.add(item_id)

            title   = clean_text(strip_html(getattr(entry, "title",   "")))
            summary = clean_text(strip_html(getattr(entry, "summary", "")))
            link    = getattr(entry, "link", "")
            text    = f"{title} {summary}"

            matched, tier = classify_keywords(text)
            if matched:
                emoji = tier_emoji(tier)
                ts = datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M ET")

                kw_str = ", ".join(matched[:5])
                post_text = summary[:600] if feed.get("trump_only") else summary[:280]

                if feed.get("trump_only"):
                    message = (
                        f"{emoji} TRUMP POST — Tier {tier}  {ts}\n"
                        f"Keywords: {kw_str}\n"
                        f"{'─' * 32}\n"
                        f"{post_text}\n"
                        f"{'─' * 32}\n"
                        f"{link}"
                    )
                else:
                    message = (
                        f"{emoji} Tier {tier} — {feed['name']}  {ts}\n"
                        f"Keywords: {kw_str}\n\n"
                        f"{title}\n\n"
                        f"{post_text}\n\n"
                        f"{link}"
                    )

                log.info(f"MATCH [{feed['name']}] tier={tier} kw={matched} '{title[:60]}'")
                send_telegram(message)
                alerts += 1

        # Save after processing each feed
        save_seen_ids(seen_ids)

    except Exception as e:
        log.error(f"Error [{feed['name']}]: {e}")

    return alerts


def startup_message():
    msg = (
        f"✅ Market Monitor Online\n"
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Polling every {POLL_INTERVAL}s\n\n"
        f"🚨 Tier 1 Iran/Oil: {len(TIER1)} phrases\n"
        f"⚠️ Tier 2 Fed/Macro: {len(TIER2)} phrases\n"
        f"📡 Tier 3 Geopolitical: {len(TIER3)} phrases\n\n"
        f"Source: Trump Truth Social (trumpstruth.org)"
    )
    send_telegram(msg)


def main():
    log.info("Market Monitor starting...")
    # Only backfill on truly fresh start (no persisted file)
    if not load_seen_ids():
        backfill_seen_ids()
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
