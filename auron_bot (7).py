import logging
import os
import json
import requests
from datetime import datetime, timezone
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_KEY", "")
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@AuronSignals")
OWNER_ID = os.environ.get("OWNER_ID", "")  # Tumhara personal Telegram ID

client = OpenAI(api_key=OPENAI_API_KEY)
logging.basicConfig(level=logging.INFO)

# ============================================================
# USER DATABASE — File based (simple & reliable)
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
        logging.error(f"Save users error: {e}")

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
        logging.info(f"New user registered: {first_name} ({user_id})")
        return True
    return False

def get_alert_users():
    users = load_users()
    return [uid for uid, data in users.items() if data.get("alerts", True)]

def get_user_count():
    return len(load_users())

# ============================================================
# SEND ALERT TO ALL USERS
# ============================================================

async def broadcast_alert(app, message):
    """Send alert to all registered users + channel"""
    users = get_alert_users()
    success = 0
    failed = 0

    # Post to channel
    try:
        await app.bot.send_message(
            chat_id=CHANNEL_ID,
            text=message,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Channel post error: {e}")

    # Send to all users
    for uid in users:
        try:
            await app.bot.send_message(
                chat_id=int(uid),
                text=f"🔔 *AURON Alert*\n\n{message}",
                parse_mode="Markdown"
            )
            success += 1
        except Exception as e:
            logging.error(f"Alert to {uid} failed: {e}")
            failed += 1

    # Notify owner
    if OWNER_ID:
        try:
            await app.bot.send_message(
                chat_id=int(OWNER_ID),
                text=f"📊 Alert sent to {success} users. Failed: {failed}",
                parse_mode="Markdown"
            )
        except:
            pass

    logging.info(f"Alert broadcast: {success} success, {failed} failed")

# ============================================================
# MARKET DATA
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
# NEWS & CALENDAR — Finnhub
# ============================================================

def get_forex_news():
    try:
        url = f"https://finnhub.io/api/v1/news?category=forex&token={FINNHUB_KEY}"
        r = requests.get(url, timeout=10).json()
        if isinstance(r, list):
            return [{"headline": i.get("headline",""), "source": i.get("source","")} for i in r[:5]]
        return []
    except:
        return []

def get_economic_calendar():
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = f"https://finnhub.io/api/v1/calendar/economic?from={today}&to={today}&token={FINNHUB_KEY}"
        r = requests.get(url, timeout=10).json()
        events = r.get("economicCalendar", [])
        return [{"event": e.get("event",""), "country": e.get("country",""), "time": e.get("time","")}
                for e in events if e.get("impact","").lower() == "high"]
    except:
        return []

# ============================================================
# DETECT SYMBOL
# ============================================================

def detect_symbol(text):
    text_upper = text.upper()
    symbols = {
        "GOLD": "XAUUSD", "XAUUSD": "XAUUSD", "XAU": "XAUUSD",
        "EURUSD": "EURUSD", "EUR": "EURUSD",
        "GBPUSD": "GBPUSD", "GBP": "GBPUSD", "POUND": "GBPUSD",
        "USDJPY": "USDJPY", "JPY": "USDJPY",
        "AUDUSD": "AUDUSD", "AUD": "AUDUSD",
        "USDCAD": "USDCAD", "CAD": "USDCAD",
    }
    for key, val in symbols.items():
        if key in text_upper:
            return val
    return None

# ============================================================
# BUILD CONTEXT
# ============================================================

def build_context(msg):
    parts = []
    symbol = detect_symbol(msg)

    if symbol:
        q = get_quote(symbol)
        if q:
            parts.append(
                f"LIVE PRICE [{q['symbol']}]\n"
                f"Price: {q['price']} | Open: {q['open']}\n"
                f"High: {q['high']} | Low: {q['low']}\n"
                f"Change: {q['change']}% {q['arrow']}"
            )

    events = get_economic_calendar()
    if events:
        ev = "\n".join([f"• {e['event']} ({e['country']}) at {e['time']} UTC" for e in events[:3]])
        parts.append(f"HIGH IMPACT NEWS TODAY:\n{ev}\n⚠️ Avoid trading 30 min before/after!")
    else:
        parts.append("No high-impact news today — clean trading day.")

    news = get_forex_news()
    if news:
        nl = "\n".join([f"• {n['headline']}" for n in news[:3]])
        parts.append(f"LATEST NEWS:\n{nl}")

    hour = datetime.now(timezone.utc).hour
    if 7 <= hour < 11:
        session = "London session ACTIVE (7-11 UTC) — best setups"
    elif 12 <= hour < 16:
        session = "New York session ACTIVE (12-16 UTC)"
    elif 11 <= hour < 12:
        session = "Pre-NY — be careful"
    else:
        session = "Off-hours — Asian/closed. Low quality."
    parts.append(f"SESSION: {session}")

    return "\n\n".join(parts)

# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM = """You are AURON — elite AI trading assistant. 7 years real SMC experience.

PERSONALITY: Warm, friendly, direct. Short Telegram responses. Natural emojis. Empathize first if upset.

SMC RULES:
- Only A+ setups. Max 1-2 trades/day.
- REGIME: H1/H4 HH/HL=bull, LH/LL=bear, ADX>20, 50EMA sloping. Flat=NO TRADE.
- SWEEP M15: Wick beyond equal highs/lows, close back, volume 1.5x+. London/NY only.
- OB: Last candle before BOS/CHoCH. Unmitigated. Refine M5.
- FVG: 3-candle gap, 50%+ M15 ATR. Must overlap OB.
- ENTRY (2 of 3): M5 CHoCH, engulfing/pin bar, volume spike.
- SL: ATR-based. RR min 1:2.
- NO trades 30 min before/after NFP/CPI/FOMC.

SIGNAL FORMAT:
🟢 GOLD LONG / 🔴 GOLD SHORT
💰 Price: $X
📍 Entry: $X–$X
🛑 SL: $X
🎯 TP1: $X | 🚀 TP2: $X
⚖️ R/R: 1:X | 🧠 Confidence: X/10
📰 News risk: Safe/Caution/Avoid
Why: [2 lines max]
⚠️ Educational only. Manage your risk.

NO SETUP: "Nothing A+ right now 👀 Watching for [level]. Patience = profit 💪"
KEEP RESPONSES SHORT — max 200 words."""

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
    if len(h) > 16:
        conversations[uid] = h[-16:]

def chat(uid, msg):
    try:
        context = build_context(msg)
        full_msg = f"{msg}\n\n[CONTEXT]\n{context}"
        add_history(uid, "user", full_msg)
        msgs = [{"role": "system", "content": SYSTEM}] + get_history(uid)
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=msgs,
            max_tokens=500,
            temperature=0.75
        )
        reply = res.choices[0].message.content
        add_history(uid, "assistant", reply)
        return reply
    except Exception as e:
        logging.error(f"Chat error: {e}")
        return "Quick glitch — try again! 🔧"

# ============================================================
# HANDLERS
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = register_user(user.id, user.first_name, user.username or "")
    count = get_user_count()

    events = get_economic_calendar()
    news_warn = ""
    if events:
        news_warn = "\n\n⚠️ *High impact news today:*\n" + "\n".join([f"• {e['event']} ({e['country']})" for e in events[:3]])

    if is_new:
        msg = (
            f"Yo {user.first_name}! 👋 Welcome to AURON!\n\n"
            f"You're beta user #{count} 🎉\n\n"
            "✅ *You're now registered for instant alerts!*\n"
            "When I detect an A+ signal — you'll get a personal notification.\n\n"
            "What I can do:\n"
            "• Live Gold & Forex analysis\n"
            "• SMC signals with entry/SL/TP\n"
            "• Real-time news & economic calendar\n"
            "• `/price gold` — live price\n"
            "• `/news` — latest forex news\n"
            "• `/calendar` — today's events\n"
            "• `/alerts off` — turn off notifications\n\n"
            f"{news_warn}\n\n"
            "_Educational only. Always manage your own risk._"
        )
    else:
        msg = (
            f"Welcome back {user.first_name}! 👋\n\n"
            "AURON is watching the markets for you 👀\n"
            f"{news_warn}\n\n"
            "What do you want to analyze?"
        )

    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_alerts_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid in users:
        users[uid]["alerts"] = False
        save_users(users)
    await update.message.reply_text("🔕 Alerts turned off. Type `/alerts on` to re-enable.")

async def cmd_alerts_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid in users:
        users[uid]["alerts"] = True
        save_users(users)
    await update.message.reply_text("🔔 Alerts turned on! You'll get notified on every A+ signal.")

async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner only — see user count"""
    if str(update.effective_user.id) != str(OWNER_ID):
        return
    users = load_users()
    alert_count = len([u for u in users.values() if u.get("alerts", True)])
    await update.message.reply_text(
        f"📊 *AURON Stats*\n\n"
        f"Total users: {len(users)}\n"
        f"Alerts on: {alert_count}\n\n"
        f"Users:\n" + "\n".join([f"• {d['name']} (@{d.get('username','?')}) — {d['joined']}" for d in list(users.values())[:20]]),
        parse_mode="Markdown"
    )

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner only — manual broadcast"""
    if str(update.effective_user.id) != str(OWNER_ID):
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return
    message = " ".join(context.args)
    await broadcast_alert(context.application, message)
    await update.message.reply_text("✅ Broadcast sent!")

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Try: /price gold | /price eurusd")
        return
    symbol = detect_symbol(" ".join(args))
    if not symbol:
        await update.message.reply_text("Not recognized. Try: gold, eurusd, gbpusd")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    q = get_quote(symbol)
    if q:
        await update.message.reply_text(
            f"{q['arrow']} *{q['symbol']}*\n\n"
            f"💰 `{q['price']}`\n"
            f"📂 Open: `{q['open']}`\n"
            f"⬆️ High: `{q['high']}`\n"
            f"⬇️ Low: `{q['low']}`\n"
            f"📊 Change: `{q['change']}%`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("Can't fetch price right now 😅")

async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    news = get_forex_news()
    if news:
        text = "📰 *Latest Forex News*\n\n"
        for n in news:
            text += f"• {n['headline']}\n_{n['source']}_\n\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("No news right now 📰")

async def cmd_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    events = get_economic_calendar()
    if events:
        text = "📅 *Today's High Impact Events*\n\n"
        for e in events:
            text += f"🔴 *{e['event']}*\n🌍 {e['country']} | ⏰ {e['time']} UTC\n\n"
        text += "_Avoid 30 min before/after!_"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("✅ *No high-impact events today!*\nClean day — stick to A+ setups 💪", parse_mode="Markdown")

async def cmd_checklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *A+ Checklist — All 12 must pass*\n\n"
        "1️⃣ H1/H4 trend clear (ADX>20)\n"
        "2️⃣ 50 EMA sloping in direction\n"
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
        "*11/12 = B+ = skip it* 🙅",
        parse_mode="Markdown"
    )

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
    print("AURON v3 — Beta alerts system LIVE 🚀")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("calendar", cmd_calendar))
    app.add_handler(CommandHandler("checklist", cmd_checklist))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("alerts_on", cmd_alerts_on))
    app.add_handler(CommandHandler("alerts_off", cmd_alerts_off))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    print("Ready! Beta users will get instant alerts 🔔")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
