import logging
import os
import requests
from datetime import datetime, timezone
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_KEY", "")
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")

client = OpenAI(api_key=OPENAI_API_KEY)
logging.basicConfig(level=logging.INFO)

# ============================================================
# MARKET DATA — Twelve Data
# ============================================================

def get_quote(symbol):
    try:
        pairs = {
            "XAUUSD": "XAU/USD", "EURUSD": "EUR/USD",
            "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY",
            "AUDUSD": "AUD/USD", "USDCAD": "USD/CAD"
        }
        pair = pairs.get(symbol.upper(), symbol)
        url = f"https://api.twelvedata.com/quote?symbol={pair}&apikey={TWELVE_DATA_KEY}"
        r = requests.get(url, timeout=10).json()
        if "close" in r:
            change = float(r.get("percent_change", 0))
            return {
                "symbol": symbol.upper(),
                "price": float(r["close"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "change": round(change, 2),
                "arrow": "📈" if change >= 0 else "📉"
            }
        return None
    except Exception as e:
        logging.error(f"Quote error: {e}")
        return None

# ============================================================
# NEWS — Finnhub
# ============================================================

def get_forex_news():
    try:
        url = f"https://finnhub.io/api/v1/news?category=forex&token={FINNHUB_KEY}"
        r = requests.get(url, timeout=10).json()
        if isinstance(r, list) and len(r) > 0:
            news = []
            for item in r[:5]:
                news.append({
                    "headline": item.get("headline", ""),
                    "summary": item.get("summary", "")[:150],
                    "source": item.get("source", "")
                })
            return news
        return []
    except Exception as e:
        logging.error(f"News error: {e}")
        return []

def get_economic_calendar():
    try:
        from_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = f"https://finnhub.io/api/v1/calendar/economic?from={from_date}&to={from_date}&token={FINNHUB_KEY}"
        r = requests.get(url, timeout=10).json()
        events = r.get("economicCalendar", [])
        high_impact = []
        for e in events:
            if e.get("impact", "").lower() == "high":
                high_impact.append({
                    "event": e.get("event", ""),
                    "country": e.get("country", ""),
                    "time": e.get("time", "")
                })
        return high_impact
    except Exception as e:
        logging.error(f"Calendar error: {e}")
        return []

def get_market_sentiment(symbol):
    try:
        url = f"https://finnhub.io/api/v1/news-sentiment?symbol={symbol}&token={FINNHUB_KEY}"
        r = requests.get(url, timeout=10).json()
        return {
            "bullish": r.get("sentiment", {}).get("bullishPercent", 0),
            "bearish": r.get("sentiment", {}).get("bearishPercent", 0)
        }
    except:
        return None

# ============================================================
# DETECT SYMBOL
# ============================================================

def detect_symbol(text):
    text_upper = text.upper()
    symbols = {
        "GOLD": "XAUUSD", "XAUUSD": "XAUUSD", "XAU": "XAUUSD",
        "EURUSD": "EURUSD", "EUR/USD": "EURUSD", "EUR": "EURUSD",
        "GBPUSD": "GBPUSD", "GBP/USD": "GBPUSD", "GBP": "GBPUSD", "POUND": "GBPUSD",
        "USDJPY": "USDJPY", "USD/JPY": "USDJPY", "JPY": "USDJPY", "YEN": "USDJPY",
        "AUDUSD": "AUDUSD", "AUD": "AUDUSD",
        "USDCAD": "USDCAD", "CAD": "USDCAD",
    }
    for key, val in symbols.items():
        if key in text_upper:
            return val
    return None

# ============================================================
# BUILD CONTEXT FOR AI
# ============================================================

def build_context(user_msg):
    context_parts = []
    symbol = detect_symbol(user_msg)

    # Live price
    if symbol:
        q = get_quote(symbol)
        if q:
            context_parts.append(
                f"LIVE PRICE [{q['symbol']}]\n"
                f"Price: {q['price']} | Open: {q['open']}\n"
                f"High: {q['high']} | Low: {q['low']}\n"
                f"Change: {q['change']}% {q['arrow']}"
            )

    # Economic calendar
    events = get_economic_calendar()
    if events:
        event_list = "\n".join([f"• {e['event']} ({e['country']}) at {e['time']}" for e in events[:3]])
        context_parts.append(f"TODAY'S HIGH IMPACT NEWS:\n{event_list}\n⚠️ Be cautious around these times!")
    else:
        context_parts.append("No high-impact news events today.")

    # Latest forex news
    news = get_forex_news()
    if news:
        news_list = "\n".join([f"• {n['headline']}" for n in news[:3]])
        context_parts.append(f"LATEST FOREX NEWS:\n{news_list}")

    # Current session
    hour = datetime.now(timezone.utc).hour
    if 7 <= hour < 11:
        session = "London session (7-11 UTC) — PRIMARY session, best setups"
    elif 12 <= hour < 16:
        session = "New York session (12-16 UTC) — good for signals"
    elif 11 <= hour < 12:
        session = "London close / Pre-NY — be careful, choppy"
    else:
        session = "Off-hours — Asian session or closed. Lower quality setups."

    context_parts.append(f"CURRENT SESSION: {session}")

    return "\n\n".join(context_parts)

# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM = """You are AURON — elite AI trading assistant. 7 years real SMC experience.

PERSONALITY:
- Friendly, warm, direct. Like a knowledgeable trading friend.
- SHORT responses — Telegram friendly. No walls of text.
- Emojis natural, not overdone.
- If upset/frustrated — empathize FIRST, then help.
- Adapt: simple for beginners, technical for pros.

TRADING RULES (SMC — non-negotiable):
- Only A+ setups. Max 1-2 trades/day.
- REGIME: H1/H4 HH/HL=bullish, LH/LL=bearish, ADX>20, 50 EMA sloping. Flat=NO TRADE.
- LIQUIDITY SWEEP M15: Wick beyond equal highs/lows, close back, volume 1.5x+. London/NY only.
- ORDER BLOCK: Last candle before BOS/CHoCH. Unmitigated. Refine to M5.
- FVG: 3-candle gap, min 50% M15 ATR. Must overlap OB.
- ENTRY (2 of 3): M5 CHoCH, engulfing/pin bar in zone, volume spike.
- SL: ATR-based. Long=M5 OB low-0.5xATR. Short=M5 OB high+0.5xATR.
- RR: Min 1:2 to TP1. Hard rule.
- NEWS RULE: NO trades 30 min before/after high-impact news (NFP, CPI, FOMC).

WHEN GIVEN LIVE DATA:
- Use REAL price. Give SPECIFIC levels based on actual data.
- Check news calendar — warn if high impact event near.
- Factor in session timing.

SIGNAL FORMAT (clean, scannable):
🟢 GOLD LONG / 🔴 GOLD SHORT
💰 Price: $X | Session: London/NY
📍 Entry: $X–$X
🛑 SL: $X
🎯 TP1: $X | 🚀 TP2: $X
⚖️ R/R: 1:X | 🧠 Confidence: X/10
📰 News: [safe/caution/avoid]
Why: [2 lines max — SMC reasoning]
⚠️ Educational only. Manage your risk.

NO SETUP:
"Nothing A+ right now 👀 [reason]. Watching for [level/condition]. Patience = profit 💪"

NEWS WARNING FORMAT:
"⚠️ [Event] in X mins — reduce size or stay out. Let dust settle first."

KEEP IT SHORT. If response >200 words, cut it."""

# ============================================================
# CONVERSATIONS
# ============================================================

conversations = {}

def get_history(uid):
    if uid not in conversations:
        conversations[uid] = []
    return conversations[uid]

def add_history(uid, role, content):
    h = get_history(uid)
    h.append({"role": role, "content": content})
    if len(h) > 16:
        conversations[uid] = h[-16:]

def chat(uid, msg):
    try:
        context = build_context(msg)
        full_msg = f"{msg}\n\n[LIVE CONTEXT]\n{context}"

        add_history(uid, "user", full_msg)
        msgs = [{"role": "system", "content": SYSTEM}] + get_history(uid)

        res = client.chat.completions.create(
            model="gpt-4o",
            messages=msgs,
            max_tokens=600,
            temperature=0.75
        )
        reply = res.choices[0].message.content
        add_history(uid, "assistant", reply)
        return reply
    except Exception as e:
        logging.error(f"Chat error: {e}")
        return "Quick glitch — try again! 🔧"

# ============================================================
# COMMANDS
# ============================================================

async def cmd_start(update: Update, context):
    name = update.effective_user.first_name or "Trader"
    events = get_economic_calendar()
    news_warning = ""
    if events:
        news_warning = f"\n\n⚠️ *Today's high-impact events:*\n" + "\n".join([f"• {e['event']} ({e['country']})" for e in events[:3]])

    await update.message.reply_text(
        f"Yo {name}! 👋\n\n"
        "I'm *AURON* — Gold & Forex AI assistant.\n"
        "7 years SMC experience + live market data + real news 📊\n\n"
        "Ask me anything:\n"
        "• `Gold signal?`\n"
        "• `Analyze EURUSD`\n"
        "• `Any news today?`\n"
        "• `/price gold`\n"
        "• `/news` — latest forex news\n"
        "• `/calendar` — today's events\n\n"
        f"{news_warning}\n\n"
        "_Educational only. Manage your own risk._",
        parse_mode="Markdown"
    )

async def cmd_price(update: Update, context):
    args = context.args
    if not args:
        await update.message.reply_text("Try: /price gold | /price eurusd | /price gbpusd")
        return

    symbol = detect_symbol(" ".join(args))
    if not symbol:
        await update.message.reply_text("Pair not recognized. Try: gold, eurusd, gbpusd, usdjpy")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    q = get_quote(symbol)
    if q:
        await update.message.reply_text(
            f"{q['arrow']} *{q['symbol']} — Live*\n\n"
            f"💰 Price: `{q['price']}`\n"
            f"📂 Open: `{q['open']}`\n"
            f"⬆️ High: `{q['high']}`\n"
            f"⬇️ Low: `{q['low']}`\n"
            f"📊 Change: `{q['change']}%`\n\n"
            f"Want analysis? Just ask! 🧠",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("Can't fetch price right now. Markets might be closed 😅")

async def cmd_news(update: Update, context):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    news = get_forex_news()
    if news:
        text = "📰 *Latest Forex News*\n\n"
        for n in news[:5]:
            text += f"• *{n['headline']}*\n_{n['source']}_\n\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("No news right now. Check back soon! 📰")

async def cmd_calendar(update: Update, context):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    events = get_economic_calendar()
    if events:
        text = "📅 *Today's High Impact Events*\n\n"
        for e in events:
            text += f"🔴 *{e['event']}*\n🌍 {e['country']} | ⏰ {e['time']} UTC\n\n"
        text += "_Avoid trading 30 min before/after these events!_"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "✅ *No high-impact events today!*\n\n"
            "Clean day for trading. Stick to the A+ checklist 💪",
            parse_mode="Markdown"
        )

async def cmd_checklist(update: Update, context):
    await update.message.reply_text(
        "📋 *A+ Checklist — All 12 must pass*\n\n"
        "1️⃣ H1/H4 trend clear (ADX>20)\n"
        "2️⃣ 50 EMA sloping in trade direction\n"
        "3️⃣ M15 liquidity sweep confirmed\n"
        "4️⃣ London or NY session only\n"
        "5️⃣ Unmitigated OB on M15 → M5\n"
        "6️⃣ FVG inside/adjacent to OB\n"
        "7️⃣ M5 CHoCH or engulfing/pin bar\n"
        "8️⃣ 2 of 3 confirmation signals\n"
        "9️⃣ ATR-based SL valid\n"
        "🔟 R/R to TP1 min 1:2\n"
        "1️⃣1️⃣ Exposure below 1.5%\n"
        "1️⃣2️⃣ No high-impact news within 30 min\n\n"
        "11/12 = B+ = *skip it* 🙅",
        parse_mode="Markdown"
    )

async def cmd_sessions(update: Update, context):
    hour = datetime.now(timezone.utc).hour
    if 7 <= hour < 11:
        current = "🟢 *London session ACTIVE* (7-11 UTC)"
    elif 12 <= hour < 16:
        current = "🟢 *New York session ACTIVE* (12-16 UTC)"
    else:
        current = "🔴 *Off-hours* — wait for London or NY"

    await update.message.reply_text(
        f"🕐 *Trading Sessions*\n\n"
        f"{current}\n\n"
        f"🇬🇧 London: 07:00-11:00 UTC\n"
        f"🗽 New York: 12:00-16:00 UTC\n"
        f"🔥 Best overlap: 12:00-14:00 UTC\n"
        f"😴 Asian: Avoid\n\n"
        f"_Outside sessions? Close the charts. Seriously._",
        parse_mode="Markdown"
    )

async def cmd_reset(update: Update, context):
    conversations[update.effective_user.id] = []
    await update.message.reply_text("Fresh start 🧹 What are we looking at? 👀")

async def handle_msg(update: Update, context):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = chat(update.effective_user.id, update.message.text)
    if len(reply) > 4000:
        for chunk in [reply[i:i+4000] for i in range(0, len(reply), 4000)]:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(reply)

# ============================================================
# MAIN
# ============================================================

def main():
    print("AURON v2 starting — live data + news + clean responses 🚀")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("calendar", cmd_calendar))
    app.add_handler(CommandHandler("checklist", cmd_checklist))
    app.add_handler(CommandHandler("sessions", cmd_sessions))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    print("AURON LIVE! 🔥")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
