import logging
import os
import json
import requests
from datetime import datetime, timezone
import anthropic
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@AuronSignals")
OWNER_ID = os.environ.get("OWNER_ID", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
logging.basicConfig(level=logging.INFO)

# ============================================================
# USER DATABASE
# ============================================================

USERS_FILE = "users.json"

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r") as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_users(users):
    try:
        with open(USERS_FILE, "w") as f:
            json.dump(users, f)
    except Exception as e:
        logging.error(f"Save error: {e}")

def register_user(user_id, first_name, username=""):
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "name": first_name,
            "username": username,
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "alerts": True,
            "tier": "beta"
        }
        save_users(users)
        return True
    return False

def get_alert_users():
    users = load_users()
    return [uid for uid, d in users.items() if d.get("alerts", True)]

def get_user_count():
    return len(load_users())

# ============================================================
# BROADCAST
# ============================================================

async def broadcast(app, message):
    users = get_alert_users()
    success = 0
    try:
        await app.bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Channel error: {e}")
    for uid in users:
        try:
            await app.bot.send_message(
                chat_id=int(uid),
                text=f"🔔 *AURON Alert*\n\n{message}",
                parse_mode="Markdown"
            )
            success += 1
        except:
            pass
    if OWNER_ID:
        try:
            await app.bot.send_message(
                chat_id=int(OWNER_ID),
                text=f"✅ Alert sent to {success}/{len(users)} users"
            )
        except:
            pass

# ============================================================
# MARKET DATA — Yahoo Finance (accurate, free, no API key)
# ============================================================

def get_quote(symbol):
    """Yahoo Finance — real prices, no API key needed"""
    try:
        yahoo_symbols = {
            "XAUUSD": "GC=F",
            "EURUSD": "EURUSD=X",
            "GBPUSD": "GBPUSD=X",
            "USDJPY": "USDJPY=X",
            "AUDUSD": "AUDUSD=X",
            "USDCAD": "USDCAD=X",
        }
        ticker = yahoo_symbols.get(symbol.upper(), symbol)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=10).json()
        meta = r["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev = meta.get("previousClose", price)
        change = round(((price - prev) / prev) * 100, 2) if prev else 0
        return {
            "symbol": symbol.upper(),
            "price": round(price, 2),
            "open": round(meta.get("regularMarketOpen", price), 2),
            "high": round(meta.get("regularMarketDayHigh", price), 2),
            "low": round(meta.get("regularMarketDayLow", price), 2),
            "change": change,
            "arrow": "📈" if change >= 0 else "📉"
        }
    except Exception as e:
        logging.error(f"Yahoo price error {symbol}: {e}")
        return None

def get_all_quotes():
    data = {}
    for sym in ["XAUUSD", "EURUSD", "GBPUSD"]:
        q = get_quote(sym)
        if q:
            data[sym] = q
    return data

# ============================================================
# NEWS & CALENDAR — Finnhub
# ============================================================

def get_news():
    try:
        r = requests.get(
            f"https://finnhub.io/api/v1/news?category=forex&token={FINNHUB_KEY}",
            timeout=10
        ).json()
        if isinstance(r, list):
            return [{"headline": i.get("headline",""), "source": i.get("source","")} for i in r[:4]]
        return []
    except:
        return []

def get_calendar():
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        r = requests.get(
            f"https://finnhub.io/api/v1/calendar/economic?from={today}&to={today}&token={FINNHUB_KEY}",
            timeout=10
        ).json()
        return [
            {"event": e.get("event",""), "country": e.get("country",""), "time": e.get("time","")}
            for e in r.get("economicCalendar", [])
            if e.get("impact","").lower() == "high"
        ]
    except:
        return []

# ============================================================
# DETECT SYMBOL & SESSION
# ============================================================

def detect_symbol(text):
    t = text.upper()
    for k, v in {
        "GOLD": "XAUUSD", "XAUUSD": "XAUUSD", "XAU": "XAUUSD",
        "EURUSD": "EURUSD", "EUR": "EURUSD",
        "GBPUSD": "GBPUSD", "GBP": "GBPUSD",
        "USDJPY": "USDJPY", "JPY": "USDJPY",
        "AUDUSD": "AUDUSD", "AUD": "AUDUSD",
        "USDCAD": "USDCAD", "CAD": "USDCAD",
    }.items():
        if k in t:
            return v
    return None

def get_session():
    h = datetime.now(timezone.utc).hour
    if 7 <= h < 11:
        return "🟢 London (7-11 UTC) — ACTIVE", True
    elif 12 <= h < 16:
        return "🟢 New York (12-16 UTC) — ACTIVE", True
    elif 11 <= h < 12:
        return "🟡 Pre-NY — Caution", False
    else:
        return "🔴 Off-hours", False

def build_context(msg):
    parts = []
    symbol = detect_symbol(msg)

    if symbol:
        q = get_quote(symbol)
        if q:
            parts.append(
                f"LIVE PRICE [{q['symbol']}] — Yahoo Finance\n"
                f"Current: {q['price']}\n"
                f"Open: {q['open']} | High: {q['high']} | Low: {q['low']}\n"
                f"Change: {q['change']}% {q['arrow']}"
            )
        else:
            parts.append(f"Price fetch failed for {symbol} — markets may be closed.")

    events = get_calendar()
    if events:
        ev = "\n".join([f"• {e['event']} ({e['country']}) at {e['time']} UTC" for e in events[:3]])
        parts.append(f"⚠️ HIGH IMPACT NEWS TODAY:\n{ev}\nNo trades 30 min before/after!")
    else:
        parts.append("✅ No high-impact news today.")

    news = get_news()
    if news:
        nl = "\n".join([f"• {n['headline']}" for n in news[:3]])
        parts.append(f"LATEST NEWS:\n{nl}")

    session, active = get_session()
    parts.append(f"SESSION: {session}")
    if not active:
        parts.append("NOT optimal session — advise user to wait for London or NY open.")

    return "\n\n".join(parts)

# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM = """You are AURON — elite AI trading assistant. 7 years real SMC experience in Gold and Forex.

## PERSONALITY
- Warm, direct, friendly — like a knowledgeable trading mentor
- SHORT Telegram responses — maximum 150 words
- Natural emojis, not overdone
- Empathize FIRST if someone lost money or is frustrated
- Simple for beginners, technical for pros
- Always specific — real levels, not vague advice

## SMC TRADING RULES (Non-negotiable)
- Only A+ setups. Max 1-2 trades/day. No trade > bad trade.
- REGIME (H1/H4): Bullish = HH+HL, above 50EMA, ADX>20 | Bearish = LH+LL, below 50EMA | Ranging = NO TRADE
- SWEEP (M15): Wick beyond equal highs/lows, close back inside, volume 1.5x+. London/NY only.
- ORDER BLOCK: Last candle before BOS/CHoCH. Unmitigated. Refine to M5.
- FVG: 3-candle gap, 50%+ M15 ATR. Must overlap OB.
- ENTRY (need 2 of 3): M5 CHoCH, engulfing/pin bar in zone, volume spike
- SL: ATR-based. Long = M5 OB low - 0.5xATR. Short = M5 OB high + 0.5xATR
- RR: Min 1:2 to TP1. Hard rule.
- NEWS RULE: NO trades 30 min before/after NFP, CPI, FOMC

## SIGNAL FORMAT
```
🟢 GOLD LONG  or  🔴 GOLD SHORT

💰 Price: $X,XXX
📍 Entry: $X,XXX – $X,XXX
🛑 SL: $X,XXX
🎯 TP1: $X,XXX (close 50%)
🚀 TP2: $X,XXX (trail rest)
⚖️ R/R: 1:X
🧠 Confidence: X/10
📰 News: Safe ✅ / Caution ⚠️ / Avoid 🚫

Why: [2 lines — specific SMC reasoning]

Educational only. Manage your own risk. 🙏
```

## NO SETUP FORMAT
```
Nothing A+ right now 👀

💰 Price: $X,XXX
👁 Watching: [specific level] for [long/short]
❓ Missing: [what's needed — sweep/OB/confirmation]

Patience = profit 💪
```

## IMPORTANT RULES
- NEVER give signals when off-hours (Asian session or market closed)
- NEVER give signals with high-impact news within 30 min
- Always use the EXACT price from live data provided
- If price data unavailable — say so clearly, don't guess
- Keep responses SHORT — traders read on mobile"""

# ============================================================
# CHAT
# ============================================================

conversations = {}

def get_history(uid):
    if uid not in conversations:
        conversations[uid] = []
    return conversations[uid]

def add_history(uid, role, content):
    h = get_history(uid)
    h.append({"role": role, "content": content})
    if len(h) > 14:
        conversations[uid] = h[-14:]

def chat(uid, msg):
    try:
        context = build_context(msg)
        full_msg = f"{msg}\n\n[LIVE DATA]\n{context}"
        add_history(uid, "user", full_msg)
        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=SYSTEM,
            messages=get_history(uid)
        )
        reply = res.content[0].text
        add_history(uid, "assistant", reply)
        return reply
    except Exception as e:
        logging.error(f"Claude error: {e}")
        return "Quick glitch — try again! 🔧"

# ============================================================
# TELEGRAM HANDLERS
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = register_user(user.id, user.first_name, user.username or "")
    count = get_user_count()
    events = get_calendar()
    news_warn = ""
    if events:
        news_warn = "\n\n⚠️ *High impact news today:*\n" + "\n".join(
            [f"• {e['event']} ({e['country']}) at {e['time']} UTC" for e in events[:3]]
        )
    session, _ = get_session()
    if is_new:
        await update.message.reply_text(
            f"Yo {user.first_name}! 👋\n\n"
            f"Welcome to *AURON* — Beta #{count} 🎉\n\n"
            f"✅ *Registered for instant alerts!*\n"
            f"Every A+ signal → personal notification.\n\n"
            f"*Session now:* {session}\n"
            f"{news_warn}\n\n"
            f"*Commands:*\n"
            f"• Just ask anything naturally\n"
            f"• `/price gold` — live price\n"
            f"• `/news` — forex news\n"
            f"• `/calendar` — today's events\n"
            f"• `/checklist` — A+ rules\n"
            f"• `/alerts_off` — stop alerts\n\n"
            f"_Educational only. Manage your risk._",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"Welcome back {user.first_name}! 👋\n"
            f"*Session:* {session}{news_warn}\n\nWhat are we looking at? 👀",
            parse_mode="Markdown"
        )

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Try: `/price gold` `/price eurusd` `/price gbpusd`", parse_mode="Markdown")
        return
    symbol = detect_symbol(" ".join(args))
    if not symbol:
        await update.message.reply_text("Not recognized. Try: gold, eurusd, gbpusd, usdjpy")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    q = get_quote(symbol)
    if q:
        await update.message.reply_text(
            f"{q['arrow']} *{q['symbol']} — Live*\n\n"
            f"💰 `{q['price']}`\n"
            f"📂 Open: `{q['open']}`\n"
            f"⬆️ High: `{q['high']}`\n"
            f"⬇️ Low: `{q['low']}`\n"
            f"📊 Change: `{q['change']}%`\n\n"
            f"_Source: Yahoo Finance_",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("Can't fetch right now — markets might be closed 😅")

async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    news = get_news()
    if news:
        text = "📰 *Latest Forex News*\n\n"
        for n in news:
            text += f"• {n['headline']}\n_{n['source']}_\n\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("No news right now 📰")

async def cmd_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    events = get_calendar()
    if events:
        text = "📅 *Today's High Impact Events*\n\n"
        for e in events:
            text += f"🔴 *{e['event']}*\n🌍 {e['country']} | ⏰ {e['time']} UTC\n\n"
        text += "_Avoid 30 min before/after!_"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "✅ *No high-impact events today!*\nClean day — A+ setups only 💪",
            parse_mode="Markdown"
        )

async def cmd_checklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *AURON A+ Checklist*\n_All 12 must pass_\n\n"
        "1️⃣ H1/H4 trend clear (ADX > 20)\n"
        "2️⃣ 50 EMA sloping in direction\n"
        "3️⃣ M15 liquidity sweep confirmed\n"
        "4️⃣ London or NY session\n"
        "5️⃣ Unmitigated OB on M15 → M5\n"
        "6️⃣ FVG inside/adjacent to OB\n"
        "7️⃣ M5 CHoCH or engulfing/pin bar\n"
        "8️⃣ 2 of 3 confirmation signals\n"
        "9️⃣ ATR-based SL valid\n"
        "🔟 R/R to TP1 min 1:2\n"
        "1️⃣1️⃣ Exposure below 1.5%\n"
        "1️⃣2️⃣ No news within 30 min\n\n"
        "*11/12 = skip it* 🙅‍♂️",
        parse_mode="Markdown"
    )

async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, _ = get_session()
    await update.message.reply_text(
        f"🕐 *Sessions*\n\n*Now:* {session}\n\n"
        f"🇬🇧 London: 07:00–11:00 UTC\n"
        f"🗽 New York: 12:00–16:00 UTC\n"
        f"🔥 Best: 12:00–14:00 UTC overlap\n"
        f"😴 Asian: Avoid\n\n"
        f"_Outside sessions = close the charts._",
        parse_mode="Markdown"
    )

async def cmd_alerts_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid in users:
        users[uid]["alerts"] = True
        save_users(users)
    await update.message.reply_text("🔔 Alerts ON — instant signal notifications enabled!")

async def cmd_alerts_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid in users:
        users[uid]["alerts"] = False
        save_users(users)
    await update.message.reply_text("🔕 Alerts OFF. Type /alerts_on to re-enable.")

async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(OWNER_ID):
        return
    users = load_users()
    alert_on = len([u for u in users.values() if u.get("alerts", True)])
    text = f"📊 *AURON Stats*\n\nTotal: {len(users)} | Alerts: {alert_on}\n\n"
    for d in list(users.values())[:20]:
        text += f"• {d['name']} — {d['joined']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(OWNER_ID):
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return
    await broadcast(context.application, " ".join(context.args))
    await update.message.reply_text("✅ Broadcast sent!")

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversations[update.effective_user.id] = []
    await update.message.reply_text("Fresh start 🧹 What are we looking at? 👀")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.first_name, user.username or "")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = chat(user.id, update.message.text)
    if len(reply) > 4000:
        for chunk in [reply[i:i+4000] for i in range(0, len(reply), 4000)]:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(reply)

# ============================================================
# MAIN
# ============================================================

def main():
    print("AURON v5 — Yahoo Finance + Claude Sonnet 🚀")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("calendar", cmd_calendar))
    app.add_handler(CommandHandler("checklist", cmd_checklist))
    app.add_handler(CommandHandler("sessions", cmd_sessions))
    app.add_handler(CommandHandler("alerts_on", cmd_alerts_on))
    app.add_handler(CommandHandler("alerts_off", cmd_alerts_off))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    print("AURON LIVE — Real prices guaranteed! 🔥")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
