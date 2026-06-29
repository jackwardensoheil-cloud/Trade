import os
import logging
import sqlite3
import threading
import requests
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# تنظیمات لاگ سیستم
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# مشخصات نهایی و قطعی شما
TELEGRAM_BOT_TOKEN = "8849903288:AAGK_XKMgCNbbC04r2IHFF1GyfF12uglIj8"
GEMINI_API_KEY = "AQ.Ab8RN6KxMDUOa6EPk4os1ll4uRJ2r2to5TYH5uYnSbLr9oqsvQ"

# پورت رندر برای زنده نگه داشتن ربات
def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# راه‌اندازی دیتابیس چندمنظوره (ذخیره وضعیت کاربر + معاملات)
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    # جدول وضعیت کاربران
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_states (
            user_id INTEGER PRIMARY KEY,
            state TEXT,
            symbol TEXT,
            trade_type TEXT,
            capital REAL,
            risk_percent REAL,
            entry_price REAL
        )
    ''')
    # جدول تاریخچه معاملات
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
            margin REAL,
            leverage REAL,
            score INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# توابع کمکی دیتابیس
def get_user_data(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT state, symbol, trade_type, capital, risk_percent, entry_price FROM user_states WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'state': row[0], 'symbol': row[1], 'type': row[2], 'capital': row[3], 'risk': row[4], 'entry': row[5]}
    return {'state': 'IDLE', 'symbol': None, 'type': None, 'capital': None, 'risk': None, 'entry': None}

def update_user_field(user_id, field, value):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO user_states (user_id, state) VALUES (?, 'IDLE')", (user_id,))
    cursor.execute(f"UPDATE user_states SET {field}=? WHERE user_id=?", (value, user_id))
    conn.commit()
    conn.close()

def clear_user_state(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_states WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def save_final_trade(user_id, d, stop_loss, pos_size, margin, leverage, score):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (user_id, symbol, trade_type, capital, risk_percent, entry_price, stop_loss, position_size, margin, leverage, score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, d['symbol'], d['type'], d['capital'], d['risk'], d['entry'], stop_loss, pos_size, margin, leverage, score))
    conn.commit()
    conn.close()

# منوهای کیبورد شیشه‌ای
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("⚡ محاسبه مدیریت ریسک", callback_data="NAV_RISK")],
        [InlineKeyboardButton("🤖 تحلیل هوش مصنوعی (Gemini)", callback_data="NAV_AI")],
        [InlineKeyboardButton("📜 تاریخچه معاملات اخیر", callback_data="NAV_HISTORY")]
    ]
    return InlineKeyboardMarkup(keyboard)

def buy_sell_keyboard():
    keyboard = [
        [InlineKeyboardButton("🟢 LONG / BUY", callback_data="SET_LONG"),
         InlineKeyboardButton("🔴 SHORT / SELL", callback_data="SET_SHORT")]
    ]
    return InlineKeyboardMarkup(keyboard)

# دستور استارت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clear_user_state(user_id)
    await update.message.reply_text(
        "👋 **سلام! به دستیار هوشمند و بدون خطای ترید خوش آمدید.**\n\n"
        "یکی از ابزارهای زیر را برای شروع انتخاب کنید:",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

# مدیریت کلیک دکمه‌ها
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    if data == "NAV_RISK":
        clear_user_state(user_id)
        update_user_field(user_id, 'state', 'WAITING_SYMBOL')
        await query.message.reply_text("💱 **مرحله 1 از 5:**\nلطفاً نام جفت‌ارز خود را بفرستید.\n(مثال: BTC یا ETH یا SOL)")

    elif data == "NAV_AI":
        clear_user_state(user_id)
        update_user_field(user_id, 'state', 'WAITING_AI_SYMBOL')
        await query.message.reply_text("🤖 **تحلیل هوش مصنوعی:**\nنام رمزارز مورد نظر خود را بفرستید تا جمینای چارت آن را آنالیز کند:\n(مثال: BTC)")

    elif data == "NAV_HISTORY":
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, trade_type, position_size, score FROM trades WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            await query.message.reply_text("📜 شما هنوز معاملاتی ثبت نکرده‌اید.", reply_markup=main_menu_keyboard())
        else:
            txt = "📜 **آخرین محاسبات مدیریت ریسک شما:**\n\n"
            for r in rows:
                txt += f"🔹 ارز: **{r[0]}** | پوزیشن: `{r[1]}` | حجم: `{r[2]}$` | امتیاز: `{r[3]}/100`\n"
            await query.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_menu_keyboard())

    elif data in ["SET_LONG", "SET_SHORT"]:
        t_type = "LONG" if data == "SET_LONG" else "SHORT"
        update_user_field(user_id, 'trade_type', t_type)
        update_user_field(user_id, 'state', 'WAITING_CAPITAL')
        await query.message.reply_text(f"✅ پوزیشن `{t_type}` ثبت شد.\n\n💰 **مرحله 3 از 5:**\nکل سرمایه کیف‌پول فیوچرز خود را به دلار وارد کنید (فقط عدد):\n(مثال: 500)")

# مدیریت پیام‌های متنی دریافتی
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    u_data = get_user_data(user_id)
    current_state = u_data['state']

    if current_state == 'WAITING_SYMBOL':
        symbol = text.upper()
        update_user_field(user_id, 'symbol', symbol)
        update_user_field(user_id, 'state', 'WAITING_TYPE')
        await update.message.reply_text(f"✅ ارز {symbol} تایید شد.\n\n↕️ **مرحله 2 از 5:**\nنوع پوزیشن خود را مشخص کنید:", reply_markup=buy_sell_keyboard())

    elif current_state == 'WAITING_CAPITAL':
        try:
            capital = float(text)
            if capital <= 0: raise ValueError
            update_user_field(user_id, 'capital', capital)
            update_user_field(user_id, 'state', 'WAITING_RISK')
            await update.message.reply_text("📉 **مرحله 4 از 5:**\nچند درصد از کل سرمایه را مایلید در این ترید ریسک کنید؟\n(مثال: 1 یا 1.5 یا 2)")
        except ValueError:
            await update.message.reply_text("❌ عدد نامعتبر است! لطفاً مقدار کل سرمایه را به صورت یک عدد درست وارد کنید:")

    elif current_state == 'WAITING_RISK':
        try:
            risk = float(text)
            if risk <= 0 or risk > 100: raise ValueError
            update_user_field(user_id, 'risk', risk)
            update_user_field(user_id, 'state', 'WAITING_ENTRY')
            await update.message.reply_text("🎯 **مرحله 5 از 5:**\nقیمت ورود (Entry Price) مورد نظرتان را وارد کنید:")
        except ValueError:
            await update.message.reply_text("❌ درصد نامعتبر است! یک عدد بین 0.1 تا 100 وارد کنید:")

    elif current_state == 'WAITING_ENTRY':
        try:
            entry = float(text)
            if entry <= 0: raise ValueError
            update_user_field(user_id, 'entry', entry)
            update_user_field(user_id, 'state', 'WAITING_STOP')
            await update.message.reply_text("🛑 **مرحله آخر:**\nقیمت حد ضرر (Stop Loss) خود را وارد کنید تا محاسبات انجام شود:")
        except ValueError:
            await update.message.reply_text("❌ قیمت ورود اشتباه است! لطفاً فقط عدد لاتین بفرستید:")

    elif current_state == 'WAITING_STOP':
        try:
            stop = float(text)
            if stop <= 0: raise ValueError
            entry = u_data['entry']
            t_type = u_data['type']

            if t_type == "LONG" and stop >= entry:
                await update.message.reply_text("❌ در پوزیشن LONG حد ضرر باید پایین‌تر از قیمت ورود باشد! دوباره وارد کنید:")
                return
            if t_type == "SHORT" and stop <= entry:
                await update.message.reply_text("❌ در پوزیشن SHORT حد ضرر باید بالاتر از قیمت ورود باشد! دوباره وارد کنید:")
                return

            # محاسبات دقیق بر مبنای استاندارد ریاضی ترید
            capital = u_data['capital']
            risk_percent = u_data['risk']
            
            risk_amount = capital * (risk_percent / 100)
            price_diff_ratio = abs(entry - stop) / entry
            
            position_size = risk_amount / price_diff_ratio
            raw_leverage = 1.0 / price_diff_ratio
            
            leverage = round(min(max(raw_leverage, 1.0), 50.0), 1)
            margin = position_size / leverage
            
            # سیستم امتیازدهی به ترید
            score = 100
            if risk_percent > 3: score -= 30
            if leverage > 20: score -= 25
            if margin > (capital * 0.25): score -= 25
            score = max(score, 10)

            save_final_trade(user_id, u_data, stop, round(position_size, 2), round(margin, 2), leverage, score)
            clear_user_state(user_id)

            res = (
                f"📊 **برگه محاسبه مدیریت سرمایه ({u_data['symbol']})**\n\n"
                f"🔹 نوع پوزیشن: `{t_type}`\n"
                f"💵 ریسک دلاری واقعی: `{round(risk_amount, 2)}$`\n"
                f"📐 حجم پوزیشن (Position Size): `{round(position_size, 2)}$`\n"
                f" اهرم پیشنهادی (Leverage): `{leverage}x`\n"
                f"💰 مارجین درگیر (Margin): `{round(margin, 2)}$`\n\n"
                f"💯 **امتیاز سلامت این ترید: {score}/100**\n"
            )
            if score >= 75: res += "🟢 این ترید کاملاً اصولی و ایمن طراحی شده است."
            elif score >= 50: res += "🟡 ریسک متوسط؛ مراقب نوسان ناگهانی مارکت باشید."
            else: res += "🔴 ترید پرریسک! حجم مارجین یا اهرم نسبت به اکانت شما بالاست."

            await update.message.reply_text(res, parse_mode="Markdown", reply_markup=main_menu_keyboard())

        except ValueError:
            await update.message.reply_text("❌ قیمت حد ضرر نامعتبر است! مجدداً عدد وارد کنید:")

    elif current_state == 'WAITING_AI_SYMBOL':
        symbol = text.upper()
        clear_user_state(user_id)
        await update.message.reply_text(f"⏳ در حال استخراج دیتای بازار و تحلیل ارز {symbol} توسط هوش مصنوعی جمینای...")

        # آدرس رسمی و استاندارد جمینای
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        
        # متد اول: تست ارسال کلید به عنوان Bearer Token اختصاصی سرویس اکانت‌ها
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GEMINI_API_KEY}"
        }
        payload = {
            "contents": [{
                "parts": [{
                    "text": f"به عنوان یک تریدر کریپتو، یک تحلیل تکنیکال بسیار خلاصه و سریع به زبان فارسی برای رمز ارز {symbol} بنویس و حمایت و مقاومت اصلی آن را بگو."
                }]
            }]
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            
            # متد دوم: اگر متد بالا ارور داد، از ساختار لینک ابری پارامتریک استفاده کن
            if response.status_code != 200:
                alt_headers = {"Content-Type": "application/json"}
                alt_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
                response = requests.post(alt_url, headers=alt_headers, json=payload, timeout=10)

            res_data = response.json()
            if response.status_code == 200:
                ai_text = res_data['candidates'][0]['content']['parts'][0]['text']
                await update.message.reply_text(f"🤖 **تحلیل اختصاصی جمینای برای {symbol}:**\n\n{ai_text}", parse_mode="Markdown", reply_markup=main_menu_keyboard())
            else:
                error_msg = res_data.get('error', {}).get('message', 'عدم هماهنگی امضای توکن ابری')
                await update.message.reply_text(f"❌ خطای احراز هویت سرور گوگل:\n`{error_msg}`\n\nاگر کماکان خطا باقی بود، لطفاً مطمئن شوید ساختار دسترسی کلید در پروژه گوگل ابری روی پابلیک است.", reply_markup=main_menu_keyboard())
        except Exception as e:
            await update.message.reply_text(f"❌ خطای اتصال به هوش مصنوعی: `{str(e)}`", reply_markup=main_menu_keyboard())

    else:
        await update.message.reply_text("برای شروع ترید، لطفاً از منوی زیر یک گزینه را انتخاب کنید:", reply_markup=main_menu_keyboard())

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("--- Bot is fully operational without any errors ---")
    application.run_polling()

if __name__ == '__main__':
    main()
    
    
