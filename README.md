# Trump / Market Monitor

Monitors news feeds for keywords relevant to gold, oil, and macro trading.
Sends Telegram push notifications when matches are found.

Built for the eye-of-the-storm trading framework — get alerted within
3 minutes of a market-moving Trump statement or geopolitical event,
while you're away from your screens.

---

## Step 1 — Create your Telegram bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name — e.g. "Market Monitor"
4. Choose a username — e.g. "ivan_market_monitor_bot" (must end in "bot")
5. BotFather gives you a token like `7123456789:AAFxxxxxxxxxxxxxx`
6. **Save this token** — it goes into TELEGRAM_TOKEN

## Step 2 — Get your Telegram Chat ID

1. Search for **@userinfobot** on Telegram
2. Send it any message
3. It replies with your user ID — e.g. `123456789`
4. **Save this number** — it goes into TELEGRAM_CHAT_ID

## Step 3 — Test locally (optional but recommended)

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables temporarily
export TELEGRAM_TOKEN="your_token_here"
export TELEGRAM_CHAT_ID="your_chat_id_here"
export POLL_INTERVAL="60"  # 1 minute for testing

# Run
python monitor.py
```

You should receive a "Monitor Online" Telegram message within seconds.

## Step 4 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/trump-monitor.git
git push -u origin main
```

Make sure `.env` is in `.gitignore` — never push your real tokens.

## Step 5 — Deploy to Railway

1. Go to **railway.app** and sign in with GitHub
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your `trump-monitor` repo
4. Railway detects Python automatically via nixpacks
5. Go to **Variables** tab and add:
   - `TELEGRAM_TOKEN` = your bot token
   - `TELEGRAM_CHAT_ID` = your chat ID
   - `POLL_INTERVAL` = `180`
6. Click **Deploy**
7. Watch the logs — you should see "Trump/Market Monitor starting..."
8. Check Telegram — you should receive the startup message

Railway free tier gives you $5/month of compute credit which is
more than enough for a lightweight polling script running 24/7.

---

## Keyword tiers

| Tier | Emoji | Topics | Action |
|------|-------|--------|--------|
| 1 | 🚨 | Iran, Hormuz, ceasefire, oil embargo | Check trading app immediately |
| 2 | ⚠️ | Fed, rates, tariffs, OPEC | Monitor, assess if trade setup forming |
| 3 | 📡 | Taiwan, nuclear, broader geopolitical | Awareness only |

---

## Adding or removing keywords

Edit the `TIER1`, `TIER2`, `TIER3` lists in `monitor.py`.
Push to GitHub — Railway auto-redeploys.

## Adding news sources

Add entries to the `FEEDS` list in `monitor.py`:
```python
{
    "name": "Source Name",
    "url": "https://example.com/rss.xml",
    "tier": 1
},
```

## Truth Social direct monitoring

Truth Social blocks server-side RSS requests. Best workaround:
1. Self-host RSSHub: https://github.com/DIYgod/RSSHub
2. Deploy on Railway as a separate service (free)
3. Then use: `https://your-rsshub.railway.app/truthsocial/user/realDonaldTrump`
4. Add this URL to the FEEDS list with name "Truth Social"

RSSHub is a powerful open-source RSS generator that handles
authentication and scraping for hundreds of platforms including Truth Social.

---

## Troubleshooting

**No startup message received:**
- Check TELEGRAM_TOKEN is correct (no extra spaces)
- Check TELEGRAM_CHAT_ID is correct (numeric, no quotes)
- Check Railway logs for errors

**Getting too many alerts:**
- Remove Tier 3 keywords or raise thresholds
- Add negative keywords: check `if "keyword" not in text_lower: continue`

**Missing important alerts:**
- Add more keywords to TIER1
- Reduce POLL_INTERVAL to 60 seconds
- Add more RSS sources

**Feed errors in logs:**
- Some feeds block non-browser user agents
- The monitor continues running even if individual feeds fail
- Check if the RSS URL is still valid
