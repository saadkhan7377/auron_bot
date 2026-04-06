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

SYSTEM_PROMPT = """You are AURON — an elite AI trading assistant built on 7 years of real SMC (Smart Money Concepts) trading experience.

PERSONALITY:
- Warm, direct, mentor-like. Never robotic.
- Talk like a senior trader to a friend — casual but expert.
- If someone is upset about a loss, empathize first THEN advise.
- Adapt language: simple for beginners, technical for advanced traders.
- Use emojis naturally but sparingly.
- Keep Telegram responses clean and readable.

TRADING METHODOLOGY (SMC):
- Only A+ setups. Max 1-2 trades per day. No trade > bad trade.
- REGIME CHECK (always first): H1/H4 must show HH/HL (bullish) or LH/LL (bearish). ADX>20. 50 EMA sloping. Ranging = NO TRADE.
- LIQUIDITY SWEEP (M15): Wick beyond equal highs/lows, close back inside, volume spike 1.5x. London/NY sessions only.
- ORDER BLOCK: Last candle before BOS/CHoCH. Must be unmitigated. Always refine to M5.
- FVG: 3-candle gap minimum 50% of M15 ATR. Must be inside/adjacent to OB.
- ENTRY CONFIRMATION (need 2 of 3): M5 CHoCH, engulfing/pin bar in zone, volume divergence.
- STOP LOSS: ATR-based. Long = M5 OB low minus 0.5xATR. Short = M5 OB high plus 0.5xATR.
- RR: Minimum 1:2 to TP1. Non-negotiable. No exceptions.
- SESSIONS: London 07:00-11:00 GMT (primary), NY 12:00-16:00 GMT. Avoid Asian.
- PAIRS: XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD.
- DAILY LIMITS: Max 2 trades. 2 losses = day over. Weekly 3% drawdown = stop.

WHEN GIVEN LIVE PRICE DATA:
- Use the actual current price in your analysis
- Reference real levels based on current price
- Give specific entry zones, SL, TP based on current price
- Always mention which session is active and if it is a good time to trade

RESPONSE FORMAT FOR SIGNALS:
Pair + Direction
Current Price: $X
Entry Zone: $X - $X
Stop Loss: $X
TP1: $X (50% close)
TP2: $X (trail)
R/R: 1:X
Confidence: X/10
Why: [2-3 lines of SMC reasoning]
Educational purposes only. Manage your own risk.

RESPONSE FOR NO SETUP:
"Market is ranging / no A+ setup right now. Patience is the trade. I will watch for [specific condition] before considering an entry."

Always end analysis with one key risk to watch."""

conversations = {}

def get_msgs(uid):
    if uid not in conversations:
        conversations[uid] = []
    return conversations[uid]

def fetch_price(symbol):
    """Fetch live price from Twelve Data"""
    try:
        # Convert symbol format: XAUUSD -> XAU/USD
        if symbol == "XAUUSD":
            pair = "XAU/USD"
        elif symbol == "EURUSD":
            pair = "EUR/USD"
        elif symbol == "GBPUSD":
            pair = "GBP/USD"
        elif symbol == "USDJPY":
            pair = "USD/JPY"
        elif symbol == "AUDUSD":
            pair = "AUD/USD"
        elif symbol == "USDCAD":
            pair = "USD/CAD"
        else:
            pair = symbol[:3] + "/" + symbol[3:]

        url = f"https://api.twelvedata.com/price?symbol={pair}&apikey={TWELVE_DATA_KEY}"
        res = requests.get(url, timeout=10)
        data = res.json()

        if "price" in data:
            return float(data["price"])
        return None
    except Exception as e:
        logging.error(f"Price fetch error: {e}")
        return None

def fetch_quote(symbol):
    """Fetch detailed quote from Twelve Data"""
    try:
        if symbol == "XAUUSD":
            pair = "XAU/USD"
        elif symbol == "EURUSD":
            pair = "EUR/USD"
        elif symbol == "GBPUSD":
            pair = "GBP/USD"
        elif symbol == "USDJPY":
            pair = "USD/JPY"
        elif symbol == "AUDUSD":
            pair = "AUD/USD"
        elif symbol == "USDCAD":
            pair = "USD/CAD"
        else:
            pair = symbol[:3] + "/" + symbol[3:]

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
        logging.error(f"Quote fetch error: {e}")
        return None

def detect_symbol(text):
    """Detect which trading pair user is asking about"""
    text_upper = text.upper()
    symbols = {
        "GOLD": "XAUUSD",
        "XAUUSD": "XAUUSD",
        "XAU": "XAUUSD",
        "EURUSD": "EURUSD",
        "EUR": "EURUSD",
        "GBPUSD": "GBPUSD",
        "GBP": "GBPUSD",
        "POUND": "GBPUSD",
        "USDJPY": "USDJPY",
        "JPY": "USDJPY",
        "YEN": "USDJPY",
        "AUDUSD": "AUDUSD",
        "AUD": "AUDUSD",
        "USDCAD": "USDCAD",
        "CAD": "USDCAD",
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
                market_context = f"\n\n[LIVE MARKET DATA - {quote['symbol']}]\nCurrent Price: {quote['price']}\nToday Open: {quote['open']}\nDay High: {quote['high']}\nDay Low: {quote['low']}\nChange: {quote['change']} ({quote['percent_change']}%)\n\nUse this REAL data in your analysis. Give specific levels based on current price."
            else:
                market_context = f"\n\n[Note: Could not fetch live price for {symbol} right now. Analyze based on general SMC principles and mention you could not get live data.]"

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
            temperature=0.7
        )
        reply = res.choices[0].message.content
        conversations[uid].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        logging.error(f"Chat error: {e}")
        return "Having a moment — try again shortly."

logging.basicConfig(level=logging.INFO)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Trader"
    await update.message.reply_text(
        f"Hey {name}! 👋\n\n"
        "I'm AURON — your AI trading companion for Gold & Forex.\n"
        "Built on 7 years of real SMC experience.\n\n"
        "I have access to LIVE market prices 📊\n\n"
        "Ask me anything:\n"
        "• Gold signal?\n"
        "• Analyze EURUSD\n"
        "• What is an order block?\n"
        "• I just lost a trade...\n\n"
        "Here 24/7. What's on your mind?\n\n"
        "Educational only. Always manage your own risk."
    )

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick price check command"""
    args = context.args
    if not args:
        await update.message.reply_text(
            "Which pair? Example:\n"
            "/price gold\n"
            "/price eurusd\n"
            "/price gbpusd"
        )
        return

    symbol = detect_symbol(" ".join(args))
    if not symbol:
        await update.message.reply_text("Pair not recognized. Try: gold, eurusd, gbpusd, usdjpy")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    quote = fetch_quote(symbol)

    if quote:
        change_emoji = "📈" if str(quote['change']).startswith('-') == False and quote['change'] != "N/A" else "📉"
        await update.message.reply_text(
            f"{change_emoji} {quote['symbol']} — Live Price\n\n"
            f"Price: {quote['price']}\n"
            f"Open: {quote['open']}\n"
            f"High: {quote['high']}\n"
            f"Low: {quote['low']}\n"
            f"Change: {quote['change']} ({quote['percent_change']}%)\n\n"
            f"Want my analysis? Just ask!"
        )
    else:
        await update.message.reply_text("Could not fetch price right now. Markets may be closed or API limit reached.")

async def cmd_checklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "A+ Checklist — All 12 must pass\n\n"
        "1. H1/H4 trend directional (ADX>20)\n"
        "2. 50 EMA sloping in trade direction\n"
        "3. M15 liquidity sweep confirmed\n"
        "4. London or NY session\n"
        "5. Unmitigated OB on M15 refined to M5\n"
        "6. FVG within/adjacent to OB\n"
        "7. M5 CHoCH or engulfing/pin bar\n"
        "8. 2 of 3 confirmation signals\n"
        "9. ATR-based SL valid\n"
        "10. RR to TP1 min 1:2\n"
        "11. Exposure below 1.5%\n"
        "12. No news within 30 min\n\n"
        "11/12 = B+. B+ trades not taken."
    )

async def cmd_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Sessions\n\n"
        "London: 07:00-11:00 GMT — Primary\n"
        "New York: 12:00-16:00 GMT\n"
        "Best overlap: 12:00-14:00 GMT\n"
        "Asian: Avoid"
    )

async def cmd_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Pairs Covered\n\n"
        "XAUUSD — Gold\n"
        "EURUSD, GBPUSD\n"
        "USDJPY, AUDUSD, USDCAD\n\n"
        "Never long EURUSD + GBPUSD together."
    )

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversations[update.effective_user.id] = []
    await update.message.reply_text("Fresh start. What are you looking at?")

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
    print("AURON starting with live market data...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("checklist", cmd_checklist))
    app.add_handler(CommandHandler("sessions", cmd_sessions))
    app.add_handler(CommandHandler("pairs", cmd_pairs))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    print("AURON LIVE with real prices!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
