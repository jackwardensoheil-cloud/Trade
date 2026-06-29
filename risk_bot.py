import os
import logging
import sqlite3
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler
)

# تنظیمات لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# وضعیت‌های گفتگو
(
    WAITING_FOR_SYMBOL,
    WAITING_FOR_CAPITAL,
    WAITING_FOR_RISK,
    WAITING_FOR_ENTRY,
    WAITING_FOR_STOP,
    WAITING_FOR_AI_SYMBOL
) = range(6)

# تنظیمات جمینای با کلید شما
GEMINI_API_KEY = "AQ.Ab8RN6LlP2WYdA8ylOGK1FgohHbUbNWtT89CpJ5VyWI0ZbVtzA"
genai.configure(api_key=GEMINI_API_KEY)

# سرور مجازی برای بیدار نگه داشتن لایه رایگان رندر
def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# دیتابیس
def init_db():
    conn = sqlite3.connect('crypto_trades.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            trade_type TEXT,
            capital REAL,
            risk_percent REAL,
            entry_price REAL,
            stop_loss REAL,
            position_size REAL,
            required_margin REAL,
            leverage REAL,
            fee REAL,
            score INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_trade(user_id, data):
    conn = sqlite3.connect('crypto_trades.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (user_id, symbol, trade_type, capital, risk_percent, entry_price, stop_loss, position_size, required_margin, leverage, fee, score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, data['symbol'], data['type'], data['capital'], data['risk'],
        data['entry'], data['stop'], data['pos_size'], data['margin'], data['leverage'], data['fee'], data['score']
    ))
    conn.commit()
    conn.close()

# کیبوردهای اصلی
def main_menu_inline():
    keyboard = [
        [InlineKeyboardButton("⚡ محاسبه مدیریت ریسک", callback_data="MENU_RISK")],
        [InlineKeyboardButton("🤖 تحلیل هوش مصنوعی (Gemini)", callback_data="MENU_AI")],
        [InlineKeyboardButton("⭐ واچ‌لیست برتر", callback_data="MENU_WATCHLIST"), InlineKeyboardButton("📊 آنالیز حساب", callback_data="MENU_ANALYTICS")],
        [InlineKeyboardButton("📰 اخبار بازار", callback_data="MENU_NEWS"), InlineKeyboardButton("📜 تاریخچه معاملات", callback_data="MENU_HISTORY")]
    ]
    return InlineKeyboardMarkup(keyboard)

def buy_sell_inline():
    keyboard = [
        [InlineKeyboardButton("🟢 LONG / BUY", callback_data="TYPE_LONG"),
         InlineKeyboardButton("🔴 SHORT / SELL", callback_data="TYPE_SHORT")]
    ]
    return InlineKeyboardMarkup(keyboard)

# شروع ربات
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "⚡ **به پلتفرم هوشمند مدیریت ریسک و تحلیل Gemini خوش آمدید**\n\n"
        "این ربات به شما کمک می‌کند تا سرمایه خود را دقیق مدیریت کنید و تحلیل‌های هوش مصنوعی دریافت کنید.\n"
        "برای شروع یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=main_menu_inline(),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# هندلر کلیک روی منوها
async def handle_menu_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "MENU_RISK":
        await query.message.reply_text("💱 لطفا نام جفت‌ارز خود را ارسال کنید:\n(مثال: BTC یا ETH)")
        return WAITING_FOR_SYMBOL

    elif data == "MENU_AI":
        await query.message.reply_text("🤖 نام ارز مورد نظر خود را بفرستید تا هوش مصنوعی (Gemini Flash) آن را تحلیل کند:\n(مثال: BTC یا SOL)")
        return WAITING_FOR_AI_SYMBOL

    elif data == "MENU_WATCHLIST":
        await query.message.reply_text("⭐ لیست واچ‌لیست شما در حال حاضر خالی است.")
    elif data == "MENU_NEWS":
        await query.message.reply_text("📰 در حال حاضر اخبار جدیدی در دسترس نیست.")
    elif data == "MENU_HISTORY":
        user_id = query.from_user.id
        conn = sqlite3.connect('crypto_trades.db')
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, trade_type, pos_size, score FROM trades WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            await query.message.reply_text("📜 هنوز هیچ معامله‌ای ثبت نکرده‌اید.")
        else:
            text = "📜 **آخرین معاملات ثبت شده شما:**\n\n"
            for row in rows:
                text += f"🔹 ارز: {row[0]} | نوع: {row[1]} | حجم: {row[2]} | امتیاز ریسک: {row[3]}/100\n"
            await query.message.reply_text(text, parse_mode="Markdown")
            
    elif data == "MENU_ANALYTICS":
        await query.message.reply_text("📊 بخش آنالیز حساب به زودی فعال خواهد شد.")
        
    return ConversationHandler.END

# --- مراحل ماشین حساب مدیریت ریسک ---

async def process_risk_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = update.message.text.strip().upper()
    if len(symbol) < 2 or len(symbol) > 12:
        await update.message.reply_text("❌ خطا در نام جفت‌ارز. مجدداً نام صحیح را بفرستید:")
        return WAITING_FOR_SYMBOL
    context.user_data['symbol'] = symbol
    await update.message.reply_text(f"✅ ارز {symbol} ثبت شد.\n\nنوع معامله را مشخص کنید:", reply_markup=buy_sell_inline())
    return WAITING_FOR_CAPITAL

async def process_trade_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['type'] = "LONG" if query.data == "TYPE_LONG" else "SHORT"
    await query.message.reply_text("💰 لطفاً کل سرمایه در دسترس خود را به دلار وارد کنید:\n(مثال: 1000)")
    return WAITING_FOR_RISK

async def process_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        capital = float(update.message.text.strip())
        if capital <= 0: raise ValueError
        context.user_data['capital'] = capital
        await update.message.reply_text("📉 درصد ریسک مد نظر در این معامله را وارد کنید (مثلا 1 یا 2 درصد):")
        return WAITING_FOR_ENTRY
    except ValueError:
        await update.message.reply_text("❌ عدد نامعتبر است. لطفاً کل سرمایه را به صورت عدد لاتین وارد کنید:")
        return WAITING_FOR_CAPITAL

async def process_risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        risk = float(update.message.text.strip())
        if risk <= 0 or risk > 100: raise ValueError
        context.user_data['risk'] = risk
        await update.message.reply_text("🎯 قیمت ورود (Entry Price) را وارد کنید:")
        return WAITING_FOR_STOP
    except ValueError:
        await update.message.reply_text("❌ درصد نامعتبر است. یک عدد بین 0.1 تا 100 وارد کنید:")
        return WAITING_FOR_ENTRY

async def process_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        entry = float(update.message.text.strip())
        if entry <= 0: raise ValueError
        context.user_data['entry'] = entry
        await update.message.reply_text("🛑 قیمت حد ضرر (Stop Loss) را وارد کنید:")
        return WAITING_FOR_RISK  # ارجاع به مرحله بعد
    except ValueError:
        await update.message.reply_text("❌ قیمت ورود نامعتبر است. مجدداً به صورت عددی بفرستید:")
        return WAITING_FOR_STOP

async def process_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stop = float(update.message.text.strip())
        entry = context.user_data['entry']
        trade_type = context.user_data['type']
        
        if stop <= 0: raise ValueError
        if trade_type == "LONG" and stop >= entry:
            await update.message.reply_text("❌ در معاملات LONG حد ضرر باید کوچکتر از قیمت ورود باشد. مجدداً وارد کنید:")
            return WAITING_FOR_RISK
        if trade_type == "SHORT" and stop <= entry:
            await update.message.reply_text("❌ در معاملات SHORT حد ضرر باید بزرگتر از قیمت ورود باشد. مجدداً وارد کنید:")
            return WAITING_FOR_RISK
            
        context.user_data['stop'] = stop
        
        capital = context.user_data['capital']
        risk_percent = context.user_data['risk']
        
        risk_amount = capital * (risk_percent / 100)
        price_diff = abs(entry - stop)
        per_diff_percent = (price_diff / entry) * 100
        
        pos_size = risk_amount / (price_diff / entry)
        
        leverage = round(100 / per_diff_percent, 1)
        if leverage > 50: leverage = 50.0
        if leverage < 1: leverage = 1.0
        
        margin = pos_size / leverage
        fee = pos_size * 0.0008
        
        score = 100
        if risk_percent > 3: score -= 30
        if leverage > 20: score -= 20
        if margin > (capital * 0.2): score -= 20
        if score < 10: score = 10

        context.user_data['pos_size'] = round(pos_size, 2)
        context.user_data['margin'] = round(margin, 2)
        context.user_data['leverage'] = leverage
        context.user_data['fee'] = round(fee, 2)
        context.user_data['score'] = score
        
        save_trade(update.message.from_user.id, context.user_data)
        
        result_text = (
            f"📊 **نتیجه محاسبه مدیریت ریسک برای {context.user_data['symbol']}**\n\n"
            f"🔹 نوع پوزیشن: `{trade_type}`\n"
            f"💵 مقدار ریسک دلاری: `{round(risk_amount, 2)}$`\n"
            f"📐 حجم کل پوزیشن: `{round(pos_size, 2)}$`\n"
            f" Leverage پیشنهاد شده: `{leverage}x`\n"
            f"💰 مارجین (سرمایه درگیر): `{round(margin, 2)}$`\n"
            f"💸 کارمزد تخمینی معامله: `{round(fee, 2)}$`\n\n"
            f"💯 **امتیاز ریسک این معامله: {score}/100**\n"
        )
        if score >= 80:
            result_text += "🟢 این پوزیشن مدیریت ریسک عالی دارد."
        elif score >= 50:
            result_text += "🟡 ریسک متوسط؛ مراقب نوسانات بازار باشید."
        else:
            result_text += "🔴 خطرناک! حجم معامله یا درصد ریسک شما بسیار بالاست."
            
        await update.message.reply_text(result_text, parse_mode="Markdown", reply_markup=main_menu_inline())
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ عدد حد ضرر نامعتبر است. مجدداً ارسال کنید:")
        return WAITING_FOR_RISK

# --- بخش هوش مصنوعی جمینای ---

async def process_ai_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = update.message.text.strip().upper()
    await update.message.reply_text(f"⏳ در حال تحلیل ارز {symbol} توسط هوش مصنوعی جمینای...")

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            f"به عنوان یک تحلیل‌گر ارشد ارزهای دیجیتال، یک تحلیل تکنیکال و فاندامنتال خیلی سریع و خلاصه "
            f"برای رمزارز {symbol} به زبان فارسی بنویس. همچنین سطوح حمایت و مقاومت مهم آن را مشخص کن و در آخر بگو جهت حرکت بازار صعودی است یا نزولی."
        )
        response = model.generate_content(prompt)
        await update.message.reply_text(f"🤖 **تحلیل هوش مصنوعی برای {symbol}:**\n\n{response.text}", parse_mode="Markdown", reply_markup=main_menu_inline())
    except Exception as e:
        await update.message.reply_text(f"❌ خطایی در ارتباط با هوش مصنوعی رخ داد: {str(e)}", reply_markup=main_menu_inline())

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.", reply_markup=main_menu_inline())
    return ConversationHandler.END

def main():
    # توکن ربات تلگرام شما به صورت مستقیم و نهایی جایگزین شد
    TOKEN = "8369003935:AAFixRnyJMzkhwrCsg1DzPbxp-r-57xSOIE" 
    
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_cmd),
            CallbackQueryHandler(handle_menu_callbacks, pattern="^MENU_")
        ],
        states={
            WAITING_FOR_SYMBOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_risk_symbol)],
            WAITING_FOR_CAPITAL: [CallbackQueryHandler(process_trade_type, pattern="^TYPE_")],
            WAITING_FOR_RISK: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_capital)],
            WAITING_FOR_ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_risk)],
            WAITING_FOR_STOP: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_entry)],
            # اصلاح ترتیب هندلر ماشین حساب ریسک
            6: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_stop)], 
            WAITING_FOR_AI_SYMBOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_ai_symbol)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start_cmd))

    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
        
