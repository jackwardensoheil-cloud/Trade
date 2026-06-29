import os
import logging
import sqlite3
import threading
import requests
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# مشخصات نهایی و قطعی شما
TELEGRAM_BOT_TOKEN = "8849903288:AAGK_XKMgCNbbC04r2IHFF1GyfF12uglIj8"
# کلید جدید خود را که کپی کردی، دقیقاً بین دو کوتیشن زیر جایگزین کن:
GEMINI_API_KEY = "کلید_جدید_شما_که_با_AIzaSy_شروع_میشود"

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_states (
            user_id INTEGER PRIMARY KEY, state TEXT, symbol TEXT, trade_type TEXT, capital REAL, risk_percent REAL, entry_price REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, symbol TEXT, trade_type TEXT, capital REAL, risk_percent REAL, entry_price REAL, stop_loss REAL, position_size REAL, margin REAL, leverage REAL, score INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_user_data(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT state, symbol, trade_type, capital, risk_percent, entry_price FROM user_states WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row: return {'state': row[0], 'symbol': row[1], 'type': row[2], 'capital': row[3], 'risk': row[4], 'entry': row[5]}
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

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ محاسبه مدیریت ریسک", callback_data="NAV_RISK")],
        [InlineKeyboardButton("🤖 تحلیل هوش مصنوعی (Gemini)", callback_data="NAV_AI")],
        [InlineKeyboardButton("📜 تاریخچه معاملات اخیر", callback_data="NAV_HISTORY")]
    ])

def buy_sell_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 LONG / BUY", callback_data="SET_LONG"), InlineKeyboardButton("🔴 SHORT / SELL", callback_data="SET_SHORT")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clear_user_state(user_id)
    await update.message.reply_text("👋 **به دستیار هوشمند ترید خوش آمدید.**\n\nیک ابزار را انتخاب کنید:", reply_markup=main_menu_keyboard(), parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    if data == "NAV_RISK":
        clear_user_state(user_id)
        update_user_field(user_id, 'state', 'WAITING_SYMBOL')
        await query.message.reply_text("💱 **مرحله 1 از 5:**\nلطفاً نام جفت‌ارز خود را بفرستید (مثال: BTC):")
    elif data == "NAV_AI":
        clear_user_state(user_id)
        update_user_field(user_id, 'state', 'WAITING_AI_SYMBOL')
        await query.message.reply_text("🤖 **تحلیل هوش مصنوعی:**\nنام رمزارز مورد نظر خود را بفرستید (مثال: BTC):")
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
            for r in rows: txt += f"🔹 ارز: **{r[0]}** | پوزیشن: `{r[1]}` | حجم: `{r[2]}$` | امتیاز: `{r[3]}/100`\n"
            await query.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    elif data in ["SET_LONG", "SET_SHORT"]:
        t_type = "LONG" if data == "SET_LONG" else "SHORT"
        update_user_field(user_id, 'trade_type', t_type)
        update_user_field(user_id, 'state', 'WAITING_CAPITAL')
        await query.message.reply_text(f"✅ پوزیشن `{t_type}` ثبت شد.\n\n💰 **مرحله 3 از 5:**\nکل سرمایه فیوچرز خود را به دلار وارد کنید:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    u_data = get_user_data(user_id)
    current_state = u_data['state']

    if current_state == 'WAITING_SYMBOL':
        update_user_field(user_id, 'symbol', text.upper())
        update_user_field(user_id, 'state', 'WAITING_TYPE')
        await update.message.reply_text(f"✅ ارز {text.upper()} تایید شد.\n\n↕️ **مرحله 2 از 5:**\nنوع پوزیشن را مشخص کنید:", reply_markup=buy_sell_keyboard())
    elif current_state == 'WAITING_CAPITAL':
        try:
            capital = float(text)
            if capital <= 0: raise ValueError
            update_user_field(user_id, 'capital', capital)
            update_user_field(user_id, 'state', 'WAITING_RISK')
            await update.message.reply_text("📉 **مرحله 4 از 5:**\nدرصد ریسک معامله را وارد کنید (مثلا 1 یا 2):")
        except ValueError:
            await update.message.reply_text("❌ عدد نامعتبر است! مجدداً وارد کنید:")
    elif current_state == 'WAITING_RISK':
        try:
            risk = float(text)
            if risk <= 0 or risk > 100: raise ValueError
            update_user_field(user_id, 'risk', risk)
            update_user_field(user_id, 'state', 'WAITING_ENTRY')
            await update.message.reply_text("🎯 **مرحله 5 از 5:**\nقیمت ورود (Entry Price) را وارد کنید:")
        except ValueError:
            await update.message.reply_text("❌ درصد نامعتبر است! مجدداً وارد کنید:")
    elif current_state == 'WAITING_ENTRY':
        try:
            entry = float(text)
            if entry <= 0: raise ValueError
            update_user_field(user_id, 'entry', entry)
            update_user_field(user_id, 'state', 'WAITING_STOP')
            await update.message.reply_text("🛑 **مرحله آخر:**\nقیمت حد ضرر (Stop Loss) را وارد کنید:")
        except ValueError:
            await update.message.reply_text("❌ قیمت ورود اشتباه است! مجدداً وارد کنید:")
    elif current_state == 'WAITING_STOP':
        try:
            stop = float(text)
            entry = u_data['entry']
            t_type = u_data['type']
            if stop <= 0: raise ValueError
            if t_type == "LONG" and stop >= entry:
                await update.message.reply_text("❌ در LONG حد ضرر باید پایین‌تر از ورود باشد! دوباره وارد کنید:")
                return
            if t_type == "SHORT" and stop <= entry:
                await update.message.reply_text("❌ در SHORT حد ضرر باید بالاتر از ورود باشد! دوباره وارد کنید:")
                return

            capital = u_data['capital']
            risk_percent = u_data['risk']
            risk_amount = capital * (risk_percent / 100)
            price_diff_ratio = abs(entry - stop) / entry
            position_size = risk_amount / price_diff_ratio
            leverage = round(min(max(1.0 / price_diff_ratio, 1.0), 50.0), 1)
            margin = position_size / leverage
            
            score = max(10, 100 - (30 if risk_percent > 3 else 0) - (25 if leverage > 20 else 0) - (25 if margin > (capital * 0.25) else 0))
            save_final_trade(user_id, u_data, stop, round(position_size, 2), round(margin, 2), leverage, score)
            clear_user_state(user_id)

            res = f"📊 **برگه محاسبه مدیریت سرمایه ({u_data['symbol']})**\n\n🔹 پوزیشن: `{t_type}`\n💵 ریسک دلاری: `{round(risk_amount, 2)}$`\n📐 حجم پوزیشن: `{round(position_size, 2)}$`\n اهرم: `{leverage}x`\n💰 مارجین درگیر: `{round(margin, 2)}$`\n\n💯 **امتیاز ترید: {score}/100**"
            await update.message.reply_text(res, parse_mode="Markdown", reply_markup=main_menu_keyboard())
        except ValueError:
            await update.message.reply_text("❌ حد ضرر نامعتبر است! مجدداً عدد وارد کنید:")
    elif current_state == 'WAITING_AI_SYMBOL':
        symbol = text.upper()
        clear_user_state(user_id)
        await update.message.reply_text(f"⏳ در حال تحلیل ارز {symbol} توسط هوش مصنوعی...")
        
        # آدرس مستقیم با متد استاندارد برای کلیدهای معمولی گوگل
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": f"به عنوان یک تریدر کریپتو، یک تحلیل تکنیکال بسیار خلاصه و سریع به زبان فارسی برای رمز ارز {symbol} بنویس و حمایت و مقاومت اصلی آن را بگو."}]}]}

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            res_data = response.json()
            if response.status_code == 200:
                ai_text = res_data['candidates'][0]['content']['parts'][0]['text']
                await update.message.reply_text(f"🤖 **تحلیل اختصاصی جمینای برای {symbol}:**\n\n{ai_text}", parse_mode="Markdown", reply_markup=main_menu_keyboard())
            else:
                await update.message.reply_text(f"❌ خطای سرور گوگل:\n`{res_data.get('error', {}).get('message', 'خطا')}`", reply_markup=main_menu_keyboard())
        except Exception as e:
            await update.message.reply_text(f"❌ خطای اتصال: `{str(e)}`", reply_markup=main_menu_keyboard())
    else:
        await update.message.reply_text("لطفاً از منوی زیر یک گزینه را انتخاب کنید:", reply_markup=main_menu_keyboard())

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()

if __name__ == '__main__':
    main()
            
