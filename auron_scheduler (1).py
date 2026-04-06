import os
import logging
import requests
import schedule
import time
import threading
from datetime import datetime
from openai import OpenAI

# ============================================================
# AURON AUTO-POSTER — Daily content automation
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@AuronSignals")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_KEY", "")

client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# ============================================================
# TELEGRAM POST FUNCTION
# ============================================================

def post_to_channel(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": CHANNEL_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        res = requests.post(url, data=data, timeout=10)
        if res.status_code == 200:
            logging.info("Posted to channel successfully")
        else:
            logging.error(f"Post failed: {res.text}")
    except Exception as e:
        logging.error(f"Telegram error: {e}")

# ============================================================
# MARKET DATA
# ============================================================

def fetch_quote(symbol):
    try:
        pairs = {
            "XAUUSD": "XAU/USD", "EURUSD": "EUR/USD",
            "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY"
        }
        pair = pairs.get(symbol, symbol)
        url = f"https://api.twelvedata.com/quote?symbol={pair}&apikey={TWELVE_DATA_KEY}"
        res = requests.get(url, timeout=10)
        data = res.json()
        if "close" in data:
            return {
                "symbol": symbol,
                "price": float(data["close"]),
                "high": float(data["high"]),
                "low": float(data["low"]),
                "change": data.get("percent_change", "0")
            }
        return None
    except Exception as e:
        logging.error(f"Price fetch error: {e}")
        return None

def get_market_data():
    data = {}
    for sym in ["XAUUSD", "EURUSD", "GBPUSD"]:
        q = fetch_quote(sym)
        if q:
            data[sym] = q
    return data

# ============================================================
# AI CONTENT GENERATOR
# ============================================================

def generate_content(prompt, max_tokens=600):
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": """You are AURON — elite AI trading assistant. 
Warm, friendly, expert. Use emojis naturally. 
Write for Telegram — short paragraphs, scannable.
Always end with — AURON 🤖"""},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.8
        )
        return res.choices[0].message.content
    except Exception as e:
        logging.error(f"AI error: {e}")
        return None

# ============================================================
# CONTENT TYPES
# ============================================================

def morning_brief():
    logging.info("Posting morning brief...")
    market = get_market_data()

    gold = market.get("XAUUSD", {})
    eur = market.get("EURUSD", {})
    gbp = market.get("GBPUSD", {})

    today = datetime.now().strftime("%B %d, %Y")
    day = datetime.now().strftime("%A")

    prompt = f"""Write AURON morning brief for {day}, {today}.

Live prices right now:
- Gold (XAUUSD): ${gold.get('price', 'N/A')} | High: ${gold.get('high')} | Low: ${gold.get('low')} | Change: {gold.get('change')}%
- EURUSD: {eur.get('price', 'N/A')} | Change: {eur.get('change')}%
- GBPUSD: {gbp.get('price', 'N/A')} | Change: {gbp.get('change')}%

Write a professional but friendly morning brief:
1. Quick market mood (bullish/bearish/mixed)
2. Gold key levels to watch today
3. EURUSD and GBPUSD one-liner each
4. One key thing to watch today
5. Session reminder (London 7-11 GMT, NY 12-16 GMT)

Keep it under 200 words. Use emojis. Make traders feel informed and ready."""

    content = generate_content(prompt)
    if content:
        post_to_channel(f"☀️ *Good Morning Traders!*\n\n{content}")

def market_scanner():
    logging.info("Running market scanner...")
    market = get_market_data()
    gold = market.get("XAUUSD", {})

    if not gold:
        return

    prompt = f"""You are AURON market scanner. Current Gold price: ${gold.get('price')}
High: ${gold.get('high')} | Low: ${gold.get('low')} | Change: {gold.get('change')}%

Check if there's a potential A+ SMC setup:
- Is price near a significant level?
- Any liquidity sweep visible?
- Is it London (7-11 GMT) or NY (12-16 GMT) session?

Current UTC hour: {datetime.utcnow().hour}

If YES — write a signal post with entry zone, SL, TP, confidence (honest 1-10), reasoning.
If NO — write "No A+ setup right now. Watching for X. Patience is the trade 💪"

Be honest. Only post if confidence is 6/10 or higher.
Format signals cleanly with emojis."""

    content = generate_content(prompt, max_tokens=400)
    if content and "No A+" not in content and "no setup" not in content.lower():
        post_to_channel(f"⚡ *AURON SIGNAL*\n\n{content}")
        logging.info("Signal posted!")
    else:
        logging.info("No A+ setup found — no post")

def education_post():
    logging.info("Posting education content...")

    topics = [
        "What is a Liquidity Sweep and why smart money uses it",
        "How to identify a valid Order Block — with real examples",
        "Fair Value Gaps (FVG) explained simply",
        "Why 90% of traders lose — the real reason",
        "How to set stop losses like an institutional trader",
        "Change of Character (CHoCH) — how to spot market reversals",
        "The A+ setup checklist — what we look for before every trade",
        "Position sizing — how to never blow your account",
        "London session secrets — why 7-9 AM GMT is gold",
        "The revenge trade trap — and how to avoid it"
    ]

    import random
    topic = random.choice(topics)

    prompt = f"""Write an educational post about: "{topic}"

Make it:
- Educational but engaging — not boring
- Real examples with current Gold/Forex context
- Simple enough for beginners, deep enough for experienced traders
- Personal — share a real experience or insight
- End with a key takeaway or question for the community

Max 250 words. Telegram format. Emojis welcome."""

    content = generate_content(prompt)
    if content:
        post_to_channel(f"🧠 *AURON Education*\n\n{content}")

def mindset_post():
    logging.info("Posting mindset content...")

    stories = [
        "a time you broke your trading rules and what happened",
        "the most expensive lesson you learned in 7 years of trading",
        "why discipline beats intelligence in trading every time",
        "how to handle a losing streak without blowing your account",
        "why waiting for the right setup is the hardest but most profitable skill",
        "the difference between gambling and trading — most people confuse them",
        "why professional traders are boring on purpose",
    ]

    import random
    story = random.choice(stories)

    prompt = f"""Write a powerful trading mindset post about: "{story}"

Style: Personal, raw, honest. Like a senior trader sharing hard-won wisdom.
Structure: Hook → Story/Insight → Lesson → Call to action
Make it relatable — traders worldwide will connect with this.
This should make people think AND want to share it.
Max 280 words. Use line breaks for readability."""

    content = generate_content(prompt)
    if content:
        post_to_channel(f"💭 *AURON Mindset*\n\n{content}")

def weekly_recap():
    logging.info("Posting weekly recap...")

    prompt = f"""Write AURON weekly recap post for the week ending {datetime.now().strftime('%B %d, %Y')}.

Create a realistic but honest recap:
- 3-5 signals this week (mix of wins and losses — be honest)
- Win rate percentage
- What went well
- What went wrong and WHY
- Key lesson learned this week
- Preview of what to watch next week

This transparency builds massive trust. Be specific with numbers.
Format cleanly. End with something motivating."""

    content = generate_content(prompt)
    if content:
        post_to_channel(f"📊 *AURON Weekly Recap*\n\n{content}")

def weekend_analysis():
    logging.info("Posting weekend analysis...")
    market = get_market_data()
    gold = market.get("XAUUSD", {})

    prompt = f"""Write AURON weekend analysis for next week prep.

Current Gold price: ${gold.get('price', 'N/A')}
Week High: ${gold.get('high', 'N/A')} | Week Low: ${gold.get('low', 'N/A')}

Write:
1. Gold bias for next week — bullish/bearish/neutral and why
2. Key price levels to watch (support and resistance)
3. EURUSD and GBPUSD quick outlook
4. Top 2-3 scenarios AURON is watching
5. Key news events to mark in calendar next week

This is the weekend prep post — traders love this.
Make them feel prepared and confident for Monday."""

    content = generate_content(prompt)
    if content:
        post_to_channel(f"📋 *Weekend Prep — Next Week*\n\n{content}")

def decode_chart():
    logging.info("Posting decode the chart...")
    market = get_market_data()
    gold = market.get("XAUUSD", {})

    prompt = f"""Write an AURON "Decode the Chart" engagement post.

Current Gold: ${gold.get('price', 'N/A')} | High: ${gold.get('high')} | Low: ${gold.get('low')}

Create a post that:
1. Describes current Gold chart setup (H1/H4) in detail
2. Asks community: "What do YOU see here? Bullish or Bearish?"
3. Gives 3 possible scenarios with key levels
4. Says "Drop your analysis below — I'll share mine tomorrow 👇"

Make it interactive and educational.
This drives massive engagement."""

    content = generate_content(prompt)
    if content:
        post_to_channel(f"🔍 *Decode the Chart*\n\n{content}")

# ============================================================
# SCHEDULE — ALL TIMES IN UTC
# ============================================================

def setup_schedule():
    # Morning brief — every day 8 AM UTC
    schedule.every().day.at("08:00").do(morning_brief)

    # Market scanner — London session (7-11 UTC) every 30 min
    schedule.every().monday.at("07:30").do(market_scanner)
    schedule.every().monday.at("09:00").do(market_scanner)
    schedule.every().tuesday.at("07:30").do(market_scanner)
    schedule.every().tuesday.at("09:00").do(market_scanner)
    schedule.every().wednesday.at("07:30").do(market_scanner)
    schedule.every().wednesday.at("09:00").do(market_scanner)
    schedule.every().thursday.at("07:30").do(market_scanner)
    schedule.every().thursday.at("09:00").do(market_scanner)
    schedule.every().friday.at("07:30").do(market_scanner)

    # NY session scanner
    schedule.every().monday.at("13:00").do(market_scanner)
    schedule.every().tuesday.at("13:00").do(market_scanner)
    schedule.every().wednesday.at("13:00").do(market_scanner)
    schedule.every().thursday.at("13:00").do(market_scanner)

    # Education — Tuesday & Thursday 6 PM UTC
    schedule.every().tuesday.at("18:00").do(education_post)
    schedule.every().thursday.at("18:00").do(education_post)

    # Mindset post — Thursday 7 PM UTC
    schedule.every().thursday.at("19:00").do(mindset_post)

    # Weekly recap — Friday 5 PM UTC
    schedule.every().friday.at("17:00").do(weekly_recap)

    # Weekend analysis — Saturday 10 AM UTC
    schedule.every().saturday.at("10:00").do(weekend_analysis)

    # Decode the chart — Wednesday 7 PM UTC
    schedule.every().wednesday.at("19:00").do(decode_chart)

    logging.info("Schedule set up successfully!")
    logging.info("AURON Auto-Poster is LIVE 🚀")

def run_scheduler():
    setup_schedule()
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    print("AURON Auto-Poster starting...")
    print(f"Posting to channel: {CHANNEL_ID}")
    print("Schedule:")
    print("  - Morning Brief: Every day 8:00 AM UTC")
    print("  - Market Scanner: London + NY sessions")
    print("  - Education: Tue + Thu 6 PM UTC")
    print("  - Mindset: Thu 7 PM UTC")
    print("  - Weekly Recap: Fri 5 PM UTC")
    print("  - Weekend Analysis: Sat 10 AM UTC")
    print("  - Decode Chart: Wed 7 PM UTC")
    run_scheduler()
