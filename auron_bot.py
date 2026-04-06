import logging
import os
import requests
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_KEY", "")

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are AURON — a chill, friendly, expert AI trading companion. You've got 7 years of real SMC trading under your belt and you love helping traders level up.

YOUR VIBE:
- Talk like a knowledgeable friend, not a textbook 😎
- Keep it casual, warm, conversational — like texting a trader buddy
- Use emojis naturally (not overdone) — they make things fun and readable
- Short paragraphs — this is Telegram, not an essay
- Simple words for beginners, go deeper for experienced traders
- If someone's upset about a loss, feel their pain first — THEN help
- Never be robotic or stiff — that's boring and unhelpful
- Be encouraging — trading is hard, people need support
- When market is boring/ranging — be honest and funny about it: "Yeah nothing's cooking right now, let's wait 👀"
- Celebrate good setups with energy: "Ooh this is juicy 👀📈"

YOUR TRADING BRAIN (SMC — non-negotiable rules):
- Only A+ setups. 1-2 trades max per day. No trade > bad trade. Always.
- REGIME FIRST: H1/H4 must show HH/HL (bullish) or LH/LL (bearish). ADX>20. 50 EMA sloping. Flat/ranging = NO TRADE, wait patiently.
- LIQUIDITY SWEEP (M15): Price wicks beyond equal highs/lows, snaps back inside with volume spike 1.5x+. London/NY sessions only.
- ORDER BLOCK: Last candle before the big BOS/CHoCH move. Must be fresh/unmitigated. Always refine down to M5.
- FVG: 3-candle imbalance gap, min 50% of M15 ATR size. Only valid if sitting inside/next to the OB.
- ENTRY CONFIRMATION (need 2 of 3): M5 CHoCH in your direction, engulfing or pin bar inside the zone, volume spike on rejection.
- STOP LOSS: ATR-based only. Long = M5 OB low - 0.5xATR. Short = M5 OB high + 0.5xATR. No guessing.
- RR: Minimum 1:2 to TP1. Hard rule. No exceptions. Ever.
- SESSIONS: London 07:00-11:00 GMT (best), NY 12:00-16:00 GMT. Overlap 12-14 is gold. Asian = avoid.
- PAIRS: XAUUSD (Gold), EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD.
- LIMITS: Max 2 trades/day. 2 losses = done for the day. Weekly 3% drawdown = take a break.

WHEN YOU GET LIVE PRICE DATA:
- Use the REAL current price — not estimates
- Build levels around actual price
- Reference real highs/lows from the data
- Be specific with numbers

SIGNAL FORMAT (keep it clean and readable):
🟢 GOLD LONG / 🔴 GOLD SHORT

💰 Current Price: $X
📍 Entry Zone: $X - $X
🛑 Stop Loss: $X
🎯 TP1: $X (close 50% here)
🚀 TP2: $X (let the rest ride)
⚖️ R/R: 1:X
🧠 Confidence: X/10

What's the play:
[2-3 lines explaining the SMC setup in plain English — liquidity, OB, FVG, confirmation]

⚠️ Key risk: [one thing to watch]

Educational only — always manage your own risk 🙏

NO SETUP FORMAT:
"Nothing cooking right now 👀 Market's [ranging/choppy/unclear]. I'm watching for [specific thing] before jumping in. Patience is literally a trade 💪"

GENERAL CHAT:
- Answer questions like a mentor who actually cares
- Explain SMC concepts with real examples, keep it simple
- If someone's frustrated — validate it, then help
- Always end with something encouraging"""

conversations = {}

def get_msgs(uid):
    if uid not in conversations:
        conversations[uid] = []
    return conversations[uid]

def fetch_quote(symbol):
    try:
        pairs = {
            "XAUUSD": "XAU/USD", "EURUSD": "EUR/USD",
            "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY",
            "AUDUSD": "AUD/USD", "USDCAD": "USD/CAD"
        }
        pair = pairs.get(symbol, symbol[:3] + "/" + symbol[3:])
        url = f"https://api.twelvedata.com/quote?symbol={pair}&apikey={TWELVE_DATA_KEY}"
        res = requests.get(url, timeout=10)
        data = res.json()
        if "close" in data:
            return {
                "symbol": symbol,
                "price": float(data["close"]),
                "open": float(data["open"]),
                "high": float(data["high"]),
                "low": float(data["low"]),
                "change": data.get("change", "N/A"),
                "percent_change": data.get("percent_change", "N/A")
            }
        return None
    except Exception as e:
        logging.error(f"Price fetch error: {e}")
        return None

def detect_symbol(text):
    text_upper = text.upper()
    symbols = {
        "GOLD": "XAUUSD", "XAUUSD": "XAUUSD", "XAU": "XAUUSD",
        "EURUSD": "EURUSD", "EUR": "EURUSD",
        "GBPUSD": "GBPUSD", "GBP": "GBPUSD", "POUND": "GBPUSD",
        "USDJPY": "USDJPY", "JPY": "USDJPY", "YEN": "USDJPY",
        "AUDUSD": "AUDUSD", "AUD": "AUDUSD",
        "USDCAD": "USDCAD", "CAD": "USDCAD",
    }
    for key, val in symbols.items():
        if key in text_upper:
            return val
    return None

def chat(uid, msg):
    try:
        symbol = detect_symbol(msg)
        market_context = ""
        if symbol:
            quote = fetch_quote(symbol)
            if quote:
                market_context = (
                    f"\n\n[LIVE DATA for {quote['symbol']}]"
                    f"\nPrice: {quote['price']}"
                    f"\nOpen: {quote['open']}"
                    f"\nHigh: {quote['high']}"
                    f"\nLow: {quote['low']}"
                    f"\nChange: {quote['change']} ({quote['percent_change']}%)"
                    f"\n\nUse this real data. Build levels around actual current price."
                )
            else:
                market_context = f"\n\n[Could not fetch live price for {symbol} — markets may be closed. Mention this to user naturally.]"

        full_msg = msg + market_context
        history = get_msgs(uid)
        history.append({"role": "user", "content": full_msg})
        if len(history) > 20:
            conversations[uid] = history[-20:]

        all_msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + conversations[uid]
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=all_msgs,
            max_tokens=1000,
            temperature=0.8
        )
        reply = res.choices[0].message.content
        conversations[uid].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        logging.error(f"Chat error: {e}")
        return "Ran into a glitch — try again in a sec! 🔧"

logging.basicConfig(level=logging.INFO)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Trader"
    await update.message.reply_text(
        f"Yo {name}! 👋\n\n"
        "I'm AURON — your AI trading companion for Gold & Forex 📊\n\n"
        "7 years of real SMC experience, packed into one bot.\n"
        "And yeah — I've got live market prices too 🔴\n\n"
        "What can I do for you?\n"
        "• Gold signal? 🥇\n"
        "• Analyze any pair 📈\n"
        "• Explain SMC concepts 🧠\n"
        "• /price gold — quick price check\n"
        "• /checklist — A+ setup rules\n\n"
        "Just talk to me like a person — I got you 💪\n\n"
        "_Educational only. Always manage your own risk._"
    )

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "Which pair? Try:\n"
            "/price gold\n"
            "/price eurusd\n"
            "/price gbpusd"
        )
        return
    symbol = detect_symbol(" ".join(args))
    if not symbol:
        await update.message.reply_text("Hmm didn't catch that pair 🤔 Try: gold, eurusd, gbpusd, usdjpy")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    quote = fetch_quote(symbol)
    if quote:
        change_val = quote['change']
        try:
            emoji = "📈" if float(change_val) >= 0 else "📉"
        except:
            emoji = "📊"
        await update.message.reply_text(
            f"{emoji} {quote['symbol']} — Live\n\n"
            f"💰 Price: {quote['price']}\n"
            f"🔓 Open: {quote['open']}\n"
            f"⬆️ High: {quote['high']}\n"
            f"⬇️ Low: {quote['low']}\n"
            f"📊 Change: {quote['change']} ({quote['percent_change']}%)\n\n"
            f"Want my full analysis? Just ask! 🧠"
        )
    else:
        await update.message.reply_text(
            "Couldn't grab that price right now 😅\n"
            "Markets might be closed or API limit hit.\n"
            "Try again in a bit!"
        )

async def cmd_checklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 AURON A+ Checklist\n\n"
        "All 12 must pass — no shortcuts!\n\n"
        "1️⃣ H1/H4 trend clear (ADX > 20)\n"
        "2️⃣ 50 EMA sloping in trade direction\n"
        "3️⃣ M15 liquidity sweep confirmed\n"
        "4️⃣ London or NY session only\n"
        "5️⃣ Fresh unmitigated OB on M15 → M5\n"
        "6️⃣ FVG inside or next to the OB\n"
        "7️⃣ M5 CHoCH or engulfing/pin bar\n"
        "8️⃣ 2 of 3 confirmation signals ✓\n"
        "9️⃣ ATR-based SL — not too tight, not too wide\n"
        "🔟 R/R to TP1 minimum 1:2\n"
        "1️⃣1️⃣ Total exposure below 1.5%\n"
        "1️⃣2️⃣ No big news within 30 min\n\n"
        "11/12 = B+ = skip it 🙅‍♂️\n"
        "We only take A+ here 💎"
    )

async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕐 Best Trading Sessions\n\n"
        "🟢 London: 07:00-11:00 GMT\n"
        "The main event. Most A+ setups happen here.\n\n"
        "🟡 New York: 12:00-16:00 GMT\n"
        "Good too — especially 12:00-14:00 overlap 🔥\n\n"
        "🔴 Asian: Generally avoid\n"
        "Low volume, weird price action 😴\n\n"
        "Outside these windows? Chill and wait 🧘"
    )

async def cmd_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Pairs I Cover\n\n"
        "🥇 XAUUSD — Gold (my fav)\n"
        "💶 EURUSD\n"
        "💷 GBPUSD\n"
        "🇯🇵 USDJPY\n"
        "🦘 AUDUSD\n"
        "🍁 USDCAD\n\n"
        "⚠️ Heads up: Never go long on EURUSD\n"
        "AND GBPUSD at the same time —\n"
        "that's just doubling your USD risk 🙅"
    )

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversations[update.effective_user.id] = []
    await update.message.reply_text(
        "Fresh slate! 🧹\n"
        "What are we looking at? 👀"
    )

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    reply = chat(update.effective_user.id, update.message.text)
    if len(reply) > 4000:
        for chunk in [reply[i:i+4000] for i in range(0, len(reply), 4000)]:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(reply)

def main():
    print("AURON starting — chill mode activated 😎")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("checklist", cmd_checklist))
    app.add_handler(CommandHandler("sessions", cmd_sessions))
    app.add_handler(CommandHandler("pairs", cmd_pairs))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    print("AURON LIVE — let's get this bread! 🍞")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
