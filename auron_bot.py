import logging
import os
import json
import base64
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
    except:
        pass

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
    return [uid for uid, d in load_users().items() if d.get("alerts", True)]

def get_user_count():
    return len(load_users())

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

def get_quote(symbol):
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
        logging.error(f"Price error: {e}")
        return None

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
                f"LIVE PRICE [{q['symbol']}]\n"
                f"Current: {q['price']} | Open: {q['open']}\n"
                f"High: {q['high']} | Low: {q['low']}\n"
                f"Change: {q['change']}% {q['arrow']}"
            )
    events = get_calendar()
    if events:
        ev = "\n".join([f"• {e['event']} ({e['country']}) at {e['time']} UTC" for e in events[:3]])
        parts.append(f"⚠️ HIGH IMPACT NEWS:\n{ev}")
    else:
        parts.append("✅ No high-impact news today.")
    session, active = get_session()
    parts.append(f"SESSION: {session}")
    if not active:
        parts.append("Off-hours — advise waiting for London/NY.")
    return "\n\n".join(parts)

SYSTEM = """You are AURON — elite AI trading assistant with 7 years real SMC experience.

PERSONALITY: Warm, direct, friendly. SHORT responses — max 150 words. Natural emojis. Empathize first if upset.

CHART IMAGE ANALYSIS:
When user sends a chart image, analyze it like a professional SMC trader:
- Identify trend direction (HH/HL or LH/LL)
- Spot liquidity pools (equal highs/lows)
- Find Order Blocks and FVGs
- Check if there's a valid setup
- Give specific levels based on what you SEE in the chart
- Be honest — if chart is unclear or low quality, say so

SMC RULES:
- Only A+ setups. Max 1-2 trades/day.
- REGIME: H1/H4 HH/HL=bull, LH/LL=bear, ADX>20, 50EMA sloping
- SWEEP M15: Wick beyond equal highs/lows, close back, volume 1.5x+
- OB: Last candle before BOS/CHoCH. Unmitigated. Refine M5.
- FVG: 3-candle gap, 50%+ M15 ATR. Must overlap OB.
- ENTRY (2 of 3): M5 CHoCH, engulfing/pin bar, volume spike
- SL: ATR-based tight — NOT wide. Realistic levels.
- RR: Min 1:2 to TP1.
- NO trades 30 min before/after NFP/CPI/FOMC.

SIGNAL FORMAT:
🟢 GOLD LONG / 🔴 GOLD SHORT
💰 Price: $X,XXX
📍 Entry: $X,XXX – $X,XXX (tight zone — max 5-8 pips)
🛑 SL: $X,XXX (just below OB — tight!)
🎯 TP1: $X,XXX
🚀 TP2: $X,XXX
⚖️ R/R: 1:X
🧠 Confidence: X/10
Why: [2 lines from chart]
Educational only. Manage your risk. 🙏

NO SETUP: "Nothing A+ 👀 Watching: [level]. Missing: [what]. Patience 💪"
KEEP SHORT. Real levels only."""

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

def chat_text(uid, msg):
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
        logging.error(f"Claude text error: {e}")
        return "Quick glitch — try again! 🔧"

def chat_image(uid, image_data, image_type, caption=""):
    """Analyze chart image with Claude Vision"""
    try:
        events = get_calendar()
        news_context = ""
        if events:
            news_context = "\nHigh impact news today: " + ", ".join([e['event'] for e in events[:2]])

        session, _ = get_session()

        prompt = f"""Analyze this trading chart using SMC methodology.

{f'User says: {caption}' if caption else 'Analyze this chart for trading opportunities.'}

Current session: {session}{news_context}

Please:
1. Identify the timeframe if visible
2. Describe the market structure (bullish/bearish/ranging)
3. Spot any liquidity pools (equal highs/lows)
4. Identify Order Blocks and FVGs if present
5. Determine if there's an A+ setup
6. Give specific entry, SL, TP levels if setup exists
7. Be honest if image is unclear

Use the signal format if setup found. Keep response concise."""

        msg_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_type,
                    "data": image_data
                }
            },
            {
                "type": "text",
                "text": prompt
            }
        ]

        history = get_history(uid)
        messages = history + [{"role": "user", "content": msg_content}]

        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=SYSTEM,
            messages=messages
        )

        reply = res.content[0].text
        add_history(uid, "assistant", reply)
        return reply
    except Exception as e:
        logging.error(f"Claude vision error: {e}")
        return "Chart analysis glitch — try again! 🔧"

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
            f"✅ *Registered for instant alerts!*\n\n"
            f"What I can do:\n"
            f"• Analyze text questions\n"
            f"• 📸 *Analyze your chart images!*\n"
            f"• `/price gold` — live price\n"
            f"• `/news` — forex news\n"
            f"• `/calendar` — today's events\n"
            f"• `/checklist` — A+ rules\n\n"
            f"*Session:* {session}"
            f"{news_warn}\n\n"
            f"_Send me a chart screenshot for SMC analysis!_",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"Welcome back {user.first_name}! 👋\n"
            f"*Session:* {session}{news_warn}\n\n"
            f"Send chart or ask anything 👀",
            parse_mode="Markdown"
        )

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Try: `/price gold` `/price eurusd`", parse_mode="Markdown")
        return
    symbol = detect_symbol(" ".join(args))
    if not symbol:
        await update.message.reply_text("Try: gold, eurusd, gbpusd, usdjpy")
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
        await update.message.reply_text("Can't fetch right now 😅")

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
            "✅ *No high-impact events today!*\nClean day 💪",
            parse_mode="Markdown"
        )

async def cmd_checklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *A+ Checklist — All 12 must pass*\n\n"
        "1️⃣ H1/H4 trend clear (ADX>20)\n"
        "2️⃣ 50 EMA sloping\n"
        "3️⃣ M15 liquidity sweep\n"
        "4️⃣ London or NY session\n"
        "5️⃣ Unmitigated OB M15→M5\n"
        "6️⃣ FVG inside/adjacent OB\n"
        "7️⃣ M5 CHoCH or engulfing\n"
        "8️⃣ 2 of 3 confirmations\n"
        "9️⃣ ATR-based SL\n"
        "🔟 R/R min 1:2\n"
        "1️⃣1️⃣ Exposure below 1.5%\n"
        "1️⃣2️⃣ No news within 30 min\n\n"
        "*11/12 = skip* 🙅",
        parse_mode="Markdown"
    )

async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session, _ = get_session()
    await update.message.reply_text(
        f"🕐 *Sessions*\n\n*Now:* {session}\n\n"
        f"🇬🇧 London: 07:00–11:00 UTC\n"
        f"🗽 NY: 12:00–16:00 UTC\n"
        f"🔥 Best: 12:00–14:00 UTC\n"
        f"😴 Asian: Avoid",
        parse_mode="Markdown"
    )

async def cmd_alerts_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid in users:
        users[uid]["alerts"] = True
        save_users(users)
    await update.message.reply_text("🔔 Alerts ON!")

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
    text = f"📊 *Stats*\nTotal: {len(users)} | Alerts: {alert_on}\n\n"
    for d in list(users.values())[:20]:
        text += f"• {d['name']} — {d['joined']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(OWNER_ID):
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast message")
        return
    await broadcast(context.application, " ".join(context.args))
    await update.message.reply_text("✅ Sent!")

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversations[update.effective_user.id] = []
    await update.message.reply_text("Fresh start 🧹")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.first_name, user.username or "")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = chat_text(user.id, update.message.text)
    if len(reply) > 4000:
        for chunk in [reply[i:i+4000] for i in range(0, len(reply), 4000)]:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(reply)

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle chart images — Claude Vision analyzes them"""
    user = update.effective_user
    register_user(user.id, user.first_name, user.username or "")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        caption = update.message.caption or ""
        reply = chat_image(user.id, image_b64, "image/jpeg", caption)
        if len(reply) > 4000:
            for chunk in [reply[i:i+4000] for i in range(0, len(reply), 4000)]:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(reply)
    except Exception as e:
        logging.error(f"Image handler error: {e}")
        await update.message.reply_text("Chart analyze nahi ho saka — dobara bhejo! 🔧")

def main():
    print("AURON v6 — Claude Vision + Chart Analysis 🚀")
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
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("AURON LIVE — Send chart images for analysis! 📸")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
