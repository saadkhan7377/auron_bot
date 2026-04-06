import logging
import os
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are AURON — an elite AI trading assistant built on 7 years of real SMC trading experience. You trade Gold (XAUUSD) and major Forex pairs.

PERSONALITY: Warm, intelligent, direct. Like a senior trader mentoring a friend. Never robotic. Empathize first if someone is upset, then advise. Simple English for beginners, deeper for advanced. Concise for Telegram.

TRADING RULES (SMC):
- Max 1-2 trades per day. A+ setups only. No trade > weak trade.
- REGIME: H1/H4 must show clear HH/HL (bullish) or LH/LL (bearish). ADX>20. 50 EMA sloping. If ranging = NO TRADE.
- LIQUIDITY SWEEP M15: Wick beyond equal highs/lows, close back inside, volume spike. London/NY only.
- ORDER BLOCK: Last candle before BOS/CHoCH. Must be unmitigated. Refine to M5.
- FVG: 3-candle gap, min 50% of ATR14. Must be inside/adjacent to OB.
- CONFIRMATION (2 of 3): M5 CHoCH, engulfing/pin bar in zone, volume divergence.
- STOP LOSS: ATR-based. Long = M5 OB low - 0.5xATR. Short = M5 OB high + 0.5xATR.
- RR: Minimum 1:2 to TP1. Non-negotiable.
- SESSIONS: London 07-11 GMT, NY 12-16 GMT. Avoid Asian.
- PAIRS: XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD.
- DAILY LIMITS: 2 trades max. 2 losses = stop. Weekly 3% drawdown = stop.

RESPONSES:
- Signals: entry/SL/TP + confidence score 1-10
- Losses: empathize first
- Ranging market: "No setup today. Patience is the trade."
- End signals with: Educational purposes only. Manage your own risk."""

conversations = {}

def get_msgs(uid):
    if uid not in conversations:
        conversations[uid] = []
    return conversations[uid]

def chat(uid, msg):
    try:
        history = get_msgs(uid)
        history.append({"role": "user", "content": msg})
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
        logging.error(f"Error: {e}")
        return "Having a moment — try again shortly."

logging.basicConfig(level=logging.INFO)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Trader"
    await update.message.reply_text(
        f"Hey {name}!\n\n"
        "I'm AURON — AI trading companion for Gold & Forex.\n"
        "Built on 7 years of real SMC experience.\n\n"
        "Ask me anything:\n"
        "- Gold signal?\n"
        "- Analyze EURUSD\n"
        "- What is an order block?\n"
        "- I just lost a trade...\n\n"
        "Here 24/7. What's on your mind?\n\n"
        "Educational only. Always manage your own risk."
    )

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
        "London: 07:00-11:00 GMT\n"
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
    print("AURON starting...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("checklist", cmd_checklist))
    app.add_handler(CommandHandler("sessions", cmd_sessions))
    app.add_handler(CommandHandler("pairs", cmd_pairs))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    print("AURON LIVE!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
