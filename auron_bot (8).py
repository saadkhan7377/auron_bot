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
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_KEY", "")
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
        r = requests.get(
            f"https://api.twelvedata.com/quote?symbol={pair}&apikey={TWELVE_DATA_KEY}",
            timeout=10
        ).json()
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

def get_news():
    try:
        r = requests.get(
            f"https://finnhub.io/api/v1/news?category=forex&token={FINNHUB_KEY}",
            timeout=10
        ).json()
        if isinstance(r, list):
            return [{"headline": i.get("headline", ""), "source": i.get("source", "")} for i in r[:4]]
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
            {"event": e.get("event", ""), "country": e.get("country", ""), "time": e.get("time", "")}
            for e in r.get("economicCalendar", [])
            if e.get("impact", "").lower() == "high"
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
        return "🟡 Pre-NY (11-12 UTC) — Caution", False
    else:
        return "🔴 Off-hours — Low quality setups", False

def build_context(msg):
    parts = []
    symbol = detect_symbol(msg)

    if symbol:
        q = get_quote(symbol)
        if q:
            parts.append(
                f"LIVE PRICE [{q['symbol']}]\n"
                f"Current: {q['price']}\n"
                f"Open: {q['open']} | High: {q['high']} | Low: {q['low']}\n"
                f"Change: {q['change']}% {q['arrow']}"
            )

    events = get_calendar()
    if events:
        ev = "\n".join([f"• {e['event']} ({e['country']}) at {e['time']} UTC" for e in events[:3]])
        parts.append(f"⚠️ HIGH IMPACT NEWS TODAY:\n{ev}\nNo trades 30 min before/after!")
    else:
        parts.append("✅ No high-impact news today — clean day.")

    news = get_news()
    if news:
        nl = "\n".join([f"• {n['headline']}" for n in news[:3]])
        parts.append(f"LATEST FOREX NEWS:\n{nl}")

    session, active = get_session()
    parts.append(f"SESSION: {session}")
    if not active:
        parts.append("IMPORTANT: Not optimal session — warn user to wait for London/NY")

    return "\n\n".join(parts)

# ============================================================
# SYSTEM PROMPT — Claude optimized
# ============================================================

SYSTEM = """You are AURON — an elite AI trading assistant with 7 years of real SMC (Smart Money Concepts) experience in Gold and Forex markets.

## PERSONALITY
- Warm, direct, friendly — like a knowledgeable trading mentor
- SHORT responses — this is Telegram, not an essay
- Use emojis naturally but sparingly
- If someone is stressed or lost money — empathize FIRST, then advise
- Adapt complexity: simple for beginners, technical for pros
- Never be vague — always give specific levels and clear reasoning

## TRADING METHODOLOGY (Non-negotiable SMC rules)

**Regime Filter (always check H1/H4 first):**
- Bullish: HH + HL structure, price above 50 EMA, EMA sloping up, ADX > 20
- Bearish: LH + LL structure, price below 50 EMA, EMA sloping down, ADX > 20  
- Ranging: ADX < 20 or flat EMA = NO TRADE. Say clearly: "Market ranging — no A+ setup possible."

**Liquidity Sweep (M15):**
- Price must wick beyond equal highs (BSL) or equal lows (SSL) then close back inside
- Volume spike 1.5x+ on sweep candle
- Only valid during London (7-11 UTC) or NY (12-16 UTC) sessions

**Order Block:**
- Last opposing candle before impulsive BOS/CHoCH
- Must be unmitigated (fresh — price hasn't returned)
- Always refine from M15 down to M5

**Fair Value Gap (FVG):**
- 3-candle imbalance, minimum 50% of M15 ATR(14) size
- MUST overlap with Order Block — standalone FVG = rejected

**Entry Confirmation (need 2 of 3):**
1. M5 CHoCH in trade direction (body close, not wick)
2. Engulfing or pin bar (wick:body 2:1+) inside OB/FVG
3. Volume spike on rejection candle

**Stop Loss:** ATR-based only
- Long: M5 OB low minus 0.5 × M5 ATR(14)
- Short: M5 OB high plus 0.5 × M5 ATR(14)

**Risk/Reward:** Minimum 1:2 to TP1. Hard rule. No exceptions.

**News Rule:** NO trades 30 minutes before/after NFP, CPI, FOMC, or any red folder event.

## WHEN GIVEN LIVE MARKET DATA
- Use the EXACT current price provided
- Calculate realistic entry zones based on actual high/low of the day
- Reference the real levels — not generic estimates
- Factor in session timing and any news events

## SIGNAL FORMAT (use this exactly)
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

Why: [2 lines — specific SMC reasoning based on real price]

Educational only. Manage your own risk. 🙏
```

## NO SETUP FORMAT
```
Nothing A+ right now 👀

Price: $X,XXX
Watching: [specific level] for a potential [long/short]
Reason: [1 line — what's missing for A+ setup]

Patience = profit 💪
```

## RESPONSE RULES
- Maximum 150 words for analysis
- Maximum 200 words for signals  
- Never use walls of text
- Always use real price from context
- If off-hours session — clearly say to wait for London/NY
- If high impact news — warn strongly before giving any signal"""

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
    if len(h) > 14:
        conversations[uid] = h[-14:]

def chat(uid, msg):
    try:
        context = build_context(msg)
        full_msg = f"{msg}\n\n[LIVE MARKET DATA]\n{context}"
        add_history(uid, "user", full_msg)

        res = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
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
# HANDLERS
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

    if is_new:
        await update.message.reply_text(
            f"Yo {user.first_name}! 👋\n\n"
            f"Welcome to *AURON* — Beta user #{count} 🎉\n\n"
            "✅ *You're registered for instant alerts!*\n"
            "Every A+ signal → personal notification to you.\n\n"
            "*Commands:*\n"
            "• Just chat naturally — ask anything\n"
            "• `/price gold` — live price\n"
            "• `/news` — latest forex news\n"
            "• `/calendar` — today's events\n"
            "• `/checklist` — A+ setup rules\n"
            "• `/sessions` — active sessions\n"
            "• `/alerts_off` — turn off alerts\n"
            f"{news_warn}\n\n"
            "_Educational only. Manage your own risk._",
            parse_mode="Markdown"
        )
    else:
        session, _ = get_session()
        await update.message.reply_text(
            f"Welcome back {user.first_name}! 👋\n\n"
            f"Session: {session}\n\n"
            f"{news_warn}\n\n"
            "What do you want to analyze? 👀",
            parse_mode="Markdown"
        )

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "Which pair?\n`/price gold` `//price eurusd` `/price gbpusd`",
            parse_mode="Markdown"
        )
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
            f"Want analysis? Just ask! 🧠",
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
            "✅ *No high-impact events today!*\n\nClean day — A+ setups only 💪",
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
        f"🕐 *Trading Sessions*\n\n"
        f"*Now:* {session}\n\n"
        f"🇬🇧 London: 07:00–11:00 UTC\n"
        f"🗽 New York: 12:00–16:00 UTC\n"
        f"🔥 Overlap: 12:00–14:00 UTC\n"
        f"😴 Asian: Avoid\n\n"
        f"_Outside sessions? Close the charts._",
        parse_mode="Markdown"
    )

async def cmd_alerts_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    uid = str(update.effective_user.id)
    if uid in users:
        users[uid]["alerts"] = True
        save_users(users)
    await update.message.reply_text("🔔 Alerts ON — you'll get every A+ signal instantly!")

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
    text = f"📊 *AURON Stats*\n\nTotal: {len(users)} | Alerts on: {alert_on}\n\n"
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
    print("AURON v4 — Claude Sonnet + Live Data + Alerts 🚀")
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
    print("AURON LIVE — Claude Sonnet powered! 🔥")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
