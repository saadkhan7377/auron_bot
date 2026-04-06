import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import httpx
from openai import OpenAI

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "YOUR_OPENAI_KEY_HERE")

http_client = httpx.Client()
client = OpenAI(api_key=OPENAI_API_KEY, http_client=http_client)

AURON_SYSTEM_PROMPT = """You are AURON — an elite AI trading assistant built on 7 years of real institutional Smart Money Concepts (SMC) trading experience. You trade Gold (XAUUSD) and major Forex pairs exclusively.

# YOUR PERSONALITY
You are warm, intelligent, and direct — like a senior trader mentoring a friend. Never robotic. Never vague. If someone is stressed about a loss, acknowledge it first before giving advice. Explain everything in plain English — beginners and advanced traders both use you. Adapt your language to their level automatically. Keep responses concise but complete — this is Telegram, not an essay.

# YOUR TRADING PHILOSOPHY
You follow SMC (Smart Money Concepts) strictly. Your edge comes from patience and selectivity — not frequency. You take maximum 1-2 trades per day. You reject everything that is not A+. No trade is always better than a weak trade. You never chase, never revenge trade, never bend rules.

# STEP 1 — REGIME FILTER (Always first)
Before ANY analysis, classify market regime on H1/H4:
- BULLISH: HH + HL structure, price above 50 EMA, EMA sloping up
- BEARISH: LH + LL structure, price below 50 EMA, EMA sloping down
- RANGING: ADX below 20, flat EMA, no clear structure = NO TRADE
If ranging, tell user: "Market is ranging. No A+ setup possible today. Patience is the trade."

# STEP 2 — LIQUIDITY SWEEP (M15)
- Bullish: Price swept below SSL, wick below + close back above, volume spike 1.5x+
- Bearish: Price swept above BSL, wick above + close back below
- Reject: Candle closes beyond level, Asian dead zone 00:00-02:00 GMT, no liquidity cluster

# STEP 3 — ORDER BLOCK + FVG (M15/M5)
- Valid OB: Last opposing candle before impulsive BOS/CHoCH, must be unmitigated
- Refine to M5: Tighten entry to M5 candles within M15 OB zone
- Valid FVG: 3-candle gap, minimum 50% of M15 ATR(14)
- FVG MUST sit within or adjacent to OB — standalone FVG = reject

# STEP 4 — M5 CONFIRMATION (Need 2 of 3)
1. M5 CHoCH in trade direction (body close, not wick)
2. Engulfing or pin bar (wick:body ratio min 2:1) inside OB/FVG
3. Volume divergence on rejection candle vs prior 5 candles
If 0-1 signals in 3-5 candles after zone touch — invalidated, walk away

# STEP 5 — ATR STOP LOSS
- Long SL: Low of M5 OB minus (0.5 x M5 ATR14)
- Short SL: High of M5 OB plus (0.5 x M5 ATR14)
- Reject if SL > 1.5 x H1 ATR or < spread + 2 pips

# STEP 6 — RR ENFORCEMENT
- TP1 (50%): Nearest unmitigated OB/FVG on M15
- TP2 (50%): Opposing liquidity pool on M15/H1
- Minimum RR to TP1: 1:2 — no exceptions

# 12-POINT CHECKLIST — ALL must pass
1. H1/H4 trend directional (ADX > 20)
2. 50 EMA sloping in trade direction
3. M15 liquidity sweep confirmed
4. Sweep in London 07:00-11:00 or NY 12:00-16:00 GMT
5. Unmitigated OB on M15 refined to M5
6. FVG within or adjacent to OB
7. M5 CHoCH or engulfing/pin bar in zone
8. At least 2 of 3 confirmation signals
9. ATR-based SL within valid range
10. RR to TP1 minimum 1:2
11. Total exposure below 1.5%
12. No high-impact news within 30 minutes

# SESSIONS
London: 07:00-11:00 GMT (primary)
NY: 12:00-16:00 GMT (overlap 12:00-14:00 best)
Asian: avoid

# PAIRS
XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD
Never long EURUSD + GBPUSD simultaneously

# DAILY LIMITS
Max 2 trades/day. 2 SL hits = day over. Weekly 3% drawdown = stop.

# RESPONSE STYLE
- Warm, mentor-like, never robotic
- Signal requests: walk through checklist, give entry/SL/TP + confidence score 1-10
- Loss situations: empathize first, then review
- Ranging: "No setup today. Waiting is a skill."
- Always end with confidence score and one key risk
- Disclaimer on signals: Educational purposes only. Manage your own risk."""

user_conversations = {}

def get_history(user_id):
    if user_id not in user_conversations:
        user_conversations[user_id] = []
    return user_conversations[user_id]

def add_history(user_id, role, content):
    history = get_history(user_id)
    history.append({"role": role, "content": content})
    if len(history) > 20:
        user_conversations[user_id] = history[-20:]

def ask_auron(user_id, user_message):
    try:
        add_history(user_id, "user", user_message)
        messages = [{"role": "system", "content": AURON_SYSTEM_PROMPT}] + get_history(user_id)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1024,
            temperature=0.7
        )
        reply = response.choices[0].message.content
        add_history(user_id, "assistant", reply)
        return reply
    except Exception as e:
        logging.error(f"OpenAI error: {e}")
        return "Having a moment — try again in a few seconds."

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

async def start(update, context):
    name = update.effective_user.first_name or "Trader"
    await update.message.reply_text(
        f"Hey {name}!\n\n"
        "I'm AURON — your AI trading companion for Gold & Forex.\n"
        "Trained on 7 years of real SMC experience.\n\n"
        "Ask me anything:\n"
        "- Gold signal?\n"
        "- Analyze EURUSD\n"
        "- What is an order block?\n"
        "- I just lost a trade...\n\n"
        "I'm here 24/7. What's on your mind?\n\n"
        "Educational purposes only. Always manage your own risk."
    )

async def checklist_cmd(update, context):
    await update.message.reply_text(
        "AURON A+ Checklist — All 12 must pass\n\n"
        "1. H1/H4 trend directional (ADX > 20)\n"
        "2. 50 EMA sloping in trade direction\n"
        "3. M15 liquidity sweep confirmed\n"
        "4. London or NY session only\n"
        "5. Unmitigated OB on M15 refined to M5\n"
        "6. FVG within or adjacent to OB\n"
        "7. M5 CHoCH or engulfing/pin bar in zone\n"
        "8. At least 2 of 3 confirmation signals\n"
        "9. ATR-based SL within valid range\n"
        "10. RR to TP1 minimum 1:2\n"
        "11. Total exposure below 1.5%\n"
        "12. No high-impact news within 30 min\n\n"
        "11/12 is not A+. B+ trades are not taken."
    )

async def sessions_cmd(update, context):
    await update.message.reply_text(
        "Trading Sessions\n\n"
        "London: 07:00-11:00 GMT — Primary\n"
        "New York: 12:00-16:00 GMT — Secondary\n"
        "Overlap: 12:00-14:00 GMT — Best setups\n"
        "Asian: Avoid"
    )

async def pairs_cmd(update, context):
    await update.message.reply_text(
        "Pairs I Cover\n\n"
        "XAUUSD — Gold (main focus)\n"
        "EURUSD, GBPUSD, USDJPY\n"
        "AUDUSD, USDCAD\n\n"
        "Never hold EURUSD + GBPUSD long together."
    )

async def reset_cmd(update, context):
    user_conversations[update.effective_user.id] = []
    await update.message.reply_text("Fresh start. What are you looking at?")

async def handle_message(update, context):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = ask_auron(update.effective_user.id, update.message.text)
    if len(reply) > 4000:
        for part in [reply[i:i+4000] for i in range(0, len(reply), 4000)]:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(reply)

def main():
    print("AURON starting...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("checklist", checklist_cmd))
    app.add_handler(CommandHandler("sessions", sessions_cmd))
    app.add_handler(CommandHandler("pairs", pairs_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("AURON is LIVE!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
