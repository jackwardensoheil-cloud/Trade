import logging
import sqlite3
import requests
import aiohttp
import asyncio
import os
import threading
import google.generativeai as genai
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

SYMBOL, CAPITAL, RISK, TRADE_TYPE, ORDER_TYPE, ENTRIES, STOP_LOSS, CHECKLIST, AI_INPUT = range(9)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6JDYkjXtxrHrBURcJM8F8z1Qd7gDrNsucyFvVydaY8Jnw")
genai.configure(api_key=GEMINI_API_KEY)

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

def init_db():
    conn = sqlite3.connect('crypto_trades.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, symbol TEXT, trade_type TEXT,
            capital REAL, risk_percent REAL, entry_price REAL, stop_loss REAL,
            position_size REAL, required_margin REAL, leverage REAL, fee REAL, score INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def main_menu_inline():
    keyboard = [
        [InlineKeyboardButton("⚡ محاسبه مدیریت ریسک", callback_data="MENU_RISK")],
        [InlineKeyboardButton("🤖 تحلیل هوشمند بازار (Gemini Flash)", callback_data="MENU_AI")],
        [InlineKeyboardButton("📊 آنالیز حساب", callback_data="MENU_ANALYTICS"), InlineKeyboardButton("⭐ واچ‌لیست برتر", callback_data="MENU_WATCHLIST")],
        [InlineKeyboardButton("📰 اخبار بازار", callback_data="MENU_NEWS"), InlineKeyboardButton("📜 تاریخچه معاملات", callback_data="MENU_HISTORY")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🎯 **به پلتفرم مدیریت ریسک و هوش مصنوعی خوش آمدید**\n\n"
        "برای شروع از دکمه‌های شیشه‌ای زیر استفاده کنید:",
        reply_markup=main_menu_inline(),
        parse_mode="Markdown"
    )

async def handle_menu_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "MENU_RISK":
        await query.message.reply_text("💱 لطفا نام جفت ارز را ارسال کنید (مثال: `BTC` یا `ETH`):", parse_mode="Markdown")
        return SYMBOL
    elif data == "MENU_AI":
        await query.message.reply_text("🤖 **نام ارز مورد نظر خود را بفرستید تا هوش مصنوعی سریع آن را تحلیل کند:**\n(مثال: BTC یا SOL)", parse_mode="Markdown")
        return AI_INPUT
    elif data == "MENU_WATCHLIST":
        await watchlist(update, context)
    elif data == "MENU_NEWS":
        await crypto_news(update, context)
    elif data == "MENU_ANALYTICS":
        await analytics(update, context)
    elif data == "MENU_HISTORY":
        await history(update, context)
        
    return ConversationHandler.END

async def ai_analysis_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_coin = update.message.text.strip().upper()
    processing_msg = await update.message.reply_text("🧠 در حال پردازش فوق‌سریع داده‌ها توسط Gemini Flash...")
    
    price, _, _ = get_live_data(user_coin)
    price_info = f"Current Price: {price:,} USDT" if price else "Price data fetching failed."

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            f"You are an expert crypto trader and market analyst. Analyze the coin: {user_coin}. "
            f"Market context: {price_info}. "
            "Decide if this coin is currently suitable for a short-term trade based on standard volatility and structure. "
            "Your output must be completely in Persian (Farsi). "
            "If it is NOT suitable for a trade, strictly start your response with exactly: 'این ارز برای ترید مناسب نیست' "
            "and then explain a short reason in Persian. "
            "If it IS suitable, output a structured signal exactly with this format in Persian:\n"
            "🟢 سیگنال خرید/فروش صادر شد\n"
            "قیمت ورود: [Provide a logical entry price]\n"
            "تارگت خروج (TP): [Provide target]\n"
            "استاپ لاس (SL): [Provide stop loss]\n"
            "توضیحات تحلیل: [Provide a brief 2-sentence reason in Persian]"
        )
        response = model.generate_content(prompt)
        await processing_msg.delete()
        await update.message.reply_text(f"🤖 **نتیجه تحلیل هوش مصنوعی (Flash):**\n\n{response.text}", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"AI Error: {e}")
        await processing_msg.edit_text("❌ خطایی در ارتباط با سرور هوش مصنوعی رخ داد.")
    return ConversationHandler.END

async def crypto_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message if update.message else update.callback_query.message
    try:
        url = "https://api.coingecko.com/api/v3/news"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            news_list = response.json()['data'][:4]
            msg = "📰 **اخبار فوری و معتبر بازار کریپتو (CoinGecko):**\n\n"
            for news in news_list:
                msg += f"🔥 *{news['title']}*\n🔗 [مشاهده منبع خبر]({news['url']})\n\n"
            await target.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)
        else:
            await target.reply_text("❌ سرور خبری فعلاً پاسخگو نیست.")
    except Exception:
        await target.reply_text("❌ خطای موقت در ارتباط با شبکه اخبار.")

async def get_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol_input = update.message.text.strip()
    processing_msg = await update.message.reply_text("⏳ در حال استعلام داده‌های زنده بازار...")
    price, atr, full_symbol = get_live_data(symbol_input)
    if price is None:
        await processing_msg.edit_text("❌ خطا در نام جفت‌ارز. مجددا تلاش کنید:")
        return SYMBOL
    context.user_data['symbol'] = full_symbol
    context.user_data['entry_price'] = price
    context.user_data['atr'] = atr
    await processing_msg.delete()
    await update.message.reply_text(f"✅ جفت ارز: *{full_symbol}*\n💵 قیمت فعلی: *{price:,} USDT*\n\n💰 **کل سرمایه فیوچرز خود را وارد کنید (دلار):**", parse_mode="Markdown")
    return CAPITAL

async def get_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['capital'] = float(update.message.text)
        await update.message.reply_text("🎯 درصد ریسک مورد نظر روی این پوزیشن (مثال: 1):")
        return RISK
    except ValueError:
        await update.message.reply_text("⚠️ فقط عدد وارد کنید:")
        return CAPITAL

async def get_risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['risk_percent'] = float(update.message.text)
        keyboard = [[InlineKeyboardButton("🟢 خرید (LONG)", callback_data="LONG")], [InlineKeyboardButton("🔴 فروش (SHORT)", callback_data="SHORT")]]
        await update.message.reply_text("🗺️ **جهت پوزیشن را انتخاب کنید:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return TRADE_TYPE
    except ValueError:
        await update.message.reply_text("⚠️ عدد وارد کنید:")
        return RISK

async def get_trade_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['trade_type'] = query.data
    keyboard = [[InlineKeyboardButton("📊 لیمیت (Maker)", callback_data="MAKER")], [InlineKeyboardButton("⚡ مارکت (Taker)", callback_data="TAKER")]]
    await query.edit_message_text("⚙️ **نوع سفارش ورود:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ORDER_TYPE

async def get_order_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['order_type'] = query.data
    await query.message.reply_text("📍 قیمت ورود را وارد کنید:")
    return ENTRIES

async def get_entries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        entries = list(map(float, update.message.text.split()))
        avg_entry = sum(entries) / len(entries)
        context.user_data['entry_price'] = avg_entry
        atr = context.user_data['atr']
        suggested_sl = avg_entry - (1.8 * atr) if context.user_data['trade_type'] == "LONG" else avg_entry + (1.8 * atr)
        await update.message.reply_text(f"📐 میانگین ورود: *{avg_entry:,.2f}*\n🛡️ حد ضرر پیشنهادی: `{suggested_sl:,.2f}`\n\n🛑 **قیمت حد ضرر (Stop Loss) را وارد کنید:**", parse_mode="Markdown")
        return STOP_LOSS
    except Exception:
        await update.message.reply_text("❌ عدد معتبر بفرستید:")
        return ENTRIES

async def get_stop_loss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stop_loss = float(update.message.text)
        entry = context.user_data['entry_price']
        trade_type = context.user_data['trade_type']
        if trade_type == "LONG" and stop_loss >= entry:
            await update.message.reply_text("⚠️ حد ضرر باید پایین‌تر از قیمت ورود باشد! مجددا وارد کنید:")
            return STOP_LOSS
        if trade_type == "SHORT" and stop_loss <= entry:
            await update.message.reply_text("⚠️ حد ضرر باید بالاتر از قیمت ورود باشد! مجددا وارد کنید:")
            return STOP_LOSS
        context.user_data['stop_loss'] = stop_loss
        keyboard = [[InlineKeyboardButton("⭐ 4 امتیاز", callback_data="4"), InlineKeyboardButton("⚡ 3 امتیاز", callback_data="3")], [InlineKeyboardButton("⚠️ 2 امتیاز", callback_data="2"), InlineKeyboardButton("❌ 1 امتیاز", callback_data="1")]]
        await update.message.reply_text("📋 **به این ترید چه امتیازی می‌دهید؟**", reply_markup=InlineKeyboardMarkup(keyboard))
        return CHECKLIST
    except ValueError:
        await update.message.reply_text("⚠️ فقط عدد معتبر وارد کنید:")
        return STOP_LOSS

async def calculate_ultimate_risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    score = int(query.data)
    try:
        entry = float(context.user_data.get('entry_price', 0))
        stop_loss = float(context.user_data.get('stop_loss', 0))
        capital = float(context.user_data.get('capital', 0))
        risk_percent = float(context.user_data.get('risk_percent', 0))
        trade_type = context.user_data.get('trade_type', 'LONG')
        symbol = context.user_data.get('symbol', 'UNKNOWN')
        order_type = context.user_data.get('order_type', 'TAKER')

        total_risk_amount = capital * (risk_percent / 100)
        price_difference = abs(entry - stop_loss) or 0.001
        position_size = total_risk_amount / price_difference
        total_value = position_size * entry
        leverage = max(1, round(total_value / (capital * 0.10))) if capital > 0 else 1
        leverage = min(leverage, 100)
        required_margin = total_value / leverage
        fee_rate = 0.0002 if order_type == "MAKER" else 0.0004
        estimated_fee = total_value * fee_rate

        rr_step = price_difference
        tp1 = entry + (rr_step * 1.0) if trade_type == "LONG" else entry - (rr_step * 1.0)
        tp2 = entry + (rr_step * 2.0) if trade_type == "LONG" else entry - (rr_step * 2.0)
        tp3 = entry + (rr_step * 3.0) if trade_type == "LONG" else entry - (rr_step * 3.0)

        advice = "🟢 **استراتژی قوی**" if score >= 3 else ("🟡 **احتیاط شود**" if score == 2 else "🔴 **ریسک بالا**")

        conn = sqlite3.connect('crypto_trades.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO trades (user_id, symbol, trade_type, capital, risk_percent, entry_price, stop_loss, position_size, required_margin, leverage, fee, score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                       (query.from_user.id, symbol, trade_type, capital, risk_percent, entry, stop_loss, position_size, required_margin, leverage, estimated_fee, score))
        conn.commit()
        conn.close()

        response = (
            f"👑 **برنامه معاملاتی VIP ({trade_type})**\n"
            f"▪️ نماد: `{symbol}` | ورود: `{entry:,.2f}` | استاپ: `{stop_loss:,.2f}`\n"
            f"───────────────────\n"
            f"💰 ریسک خالص: `{total_risk_amount:.2f} $` | اهرم: **X{leverage}**\n"
            f"💼 مارجین: `{required_margin:.2f} $` | کارمزد: `{estimated_fee:.3f} $`\n"
            f"───────────────────\n"
            f"🎯 **تارگت‌ها:**\n"
            f"🥇 **TP1:** `{tp1:,.2f}`\n"
            f"🥈 **TP2:** `{tp2:,.2f}`\n"
            f"🥉 **TP3:** `{tp3:,.2f}`\n"
            f"───────────────────\n"
            f"📊 **تحلیل چک‌لیست:** {advice}"
        )
        await query.message.reply_text(response, parse_mode="Markdown")
    except Exception as e:
        await query.message.reply_text(f"❌ خطا در محاسبه.")
    return ConversationHandler.END

def get_live_data(symbol):
    try:
        sym = symbol.upper().replace("/", "").replace("-", "")
        if not sym.endswith("USDT") and sym != "USDT": sym += "USDT"
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            price = float(response.json()['price'])
            return price, price * 0.015, sym
        return None, None, None
    except Exception: return None, None, None

async def fetch_price_async(session, symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
        async with session.get(url, timeout=2) as response:
            if response.status == 200:
                data = await response.json()
                return symbol, float(data['price'])
            return symbol, None
    except Exception: return symbol, None

async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message if update.message else update.callback_query.message
    default_symbols = ["BTC", "ETH", "BNB", "SOL", "XRP"]
    processing_msg = await target.reply_text("⏳ اسکن قیمت بازار...")
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_price_async(session, sym) for sym in default_symbols]
        results = await asyncio.gather(*tasks)
    msg = "⭐ **قیمت لحظه‌ای ارزهای برتر:**\n\n"
    for sym, price in results:
        msg += f"🔹 `{sym}/USDT`: *{f'{price:,} USDT' if price else 'خطا'}*\n"
    await processing_msg.delete()
    await target.reply_text(msg, parse_mode="Markdown")

async def analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    conn = sqlite3.connect('crypto_trades.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*), AVG(score) FROM trades WHERE user_id = ?', (query.from_user.id,))
    total, avg_score = cursor.fetchone()
    conn.close()
    if not total:
        await query.message.reply_text("📊 دیتایی ثبت نشده است.")
        return
    await query.message.reply_text(f"📊 **آمار شما:**\n\n📈 تعداد معاملات: `{total}`\n🧮 میانگین امتیاز: `{(avg_score or 0):.1f}/4`", parse_mode="Markdown")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    conn = sqlite3.connect('crypto_trades.db')
    cursor = conn.cursor()
    cursor.execute('SELECT symbol, trade_type, entry_price FROM trades WHERE user_id = ? ORDER BY id DESC LIMIT 5', (query.from_user.id,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await query.message.reply_text("📭 تاریخچه خالی است.")
        return
    text = "📜 **تاریخچه ۵ ترید اخیر:**\n\n"
    for row in rows: text += f"🔹 `{row[0]}` ({row[1]}) ⬅️ ورود: `{row[2]:,.2f}`\n"
    await query.message.reply_text(text, parse_mode="Markdown")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ لغو شد.")
    return ConversationHandler.END

def main():
    TOKEN = os.environ.get("BOT_TOKEN", "8602530981:AAEhJbDBhOQb97VjRi3rqBV3SDG7VIR8uWk")
    app = Application.builder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_menu_callbacks, pattern="^MENU_")],
        states={
            SYMBOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_symbol)],
            CAPITAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_capital)],
            RISK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_risk)],
            TRADE_TYPE: [CallbackQueryHandler(get_trade_type_callback)],
            ORDER_TYPE: [CallbackQueryHandler(get_order_type_callback)],
            ENTRIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_entries)],
            STOP_LOSS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_stop_loss)],
            CHECKLIST: [CallbackQueryHandler(calculate_ultimate_risk)],
            AI_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_analysis_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(CommandHandler('start', start_cmd))
    app.add_handler(conv_handler)
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("ربات در فایل جدید آماده کار است...")
    app.run_polling()

if __name__ == '__main__':
    main()
          
