import telebot
from telebot import types
import config
import sqlite3
from flask import Flask
from threading import Thread

# --- БЛОК ДЛЯ RENDER (ANTI-SLEEP) ---
app = Flask('')
@app.route('/')
def home(): return "Бот для манікюру активний!"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive():
    t = Thread(target=run)
    t.start()

bot = telebot.TeleBot(config.TOKEN)

# --- РОБОТА З БАЗОЮ ДАНИХ ---
def init_db():
    conn = sqlite3.connect('nail.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS slots 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, time TEXT, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- ГОЛОВНЕ МЕНЮ ---
def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📅 Записатися на манікюр", callback_data='choose_day'),
        types.InlineKeyboardButton("💰 Прайс-лист", callback_data='price'),
        types.InlineKeyboardButton("📍 Локація", callback_data='location'),
        types.InlineKeyboardButton("📱 Зв'язок з майстром", url="https://t.me/yspev")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "✨ <b>Привіт! Я твій помічник для запису на манікюр.</b>\nОбери потрібний пункт нижче:", 
                     parse_mode='HTML', reply_markup=main_menu())

@bot.message_handler(commands=['admin'])
def admin(message):
    if message.from_user.id == config.ADMIN_ID:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("➕ Додати віконце", "📊 Список записів")
        bot.send_message(message.chat.id, "🛠 <b>Адмін-панель активована</b>", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "➕ Додати віконце")
def ask_slot(message):
    msg = bot.send_message(message.chat.id, "Введи дату та час через пробіл (наприклад: 21.04 15:00):")
    bot.register_next_step_handler(msg, save_slot)

def save_slot(message):
    try:
        date_val, time_val = message.text.split()
        conn = sqlite3.connect('nail.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO slots (date, time, status) VALUES (?, ?, 'free')", (date_val, time_val))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, "✅ Віконце успішно додано!")
    except:
        bot.send_message(message.chat.id, "❌ Помилка! Спробуй формат: ДД.ММ ГГ:ХХ")

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "price":
        bot.send_message(call.message.chat.id, "💅 <b>Наш прайс:</b>\n- Гігієнічний: 300₴\n- Покриття лаком: 500₴\n- Нарощування: 800₴", parse_mode='HTML')
    
    elif call.data == "location":
        bot.send_message(call.message.chat.id, "📍 Ми знаходимося в центрі міста. Чекаємо на тебе!")

    elif call.data == "choose_day":
        conn = sqlite3.connect('nail.db')
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT date FROM slots WHERE status='free'")
        days = cursor.fetchall()
        conn.close()
        
        if not days:
            bot.answer_callback_query(call.id, "На жаль, вільних віконець немає.")
        else:
            markup = types.InlineKeyboardMarkup()
            for d in days:
                markup.add(types.InlineKeyboardButton(d[0], callback_data=f"day_{d[0]}"))
            bot.edit_message_text("Обери зручну дату:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("day_"):
        day = call.data.split("_")[1]
        conn = sqlite3.connect('nail.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, time FROM slots WHERE date=? AND status='free'", (day,))
        slots = cursor.fetchall()
        conn.close()
        
        markup = types.InlineKeyboardMarkup()
        for s in slots:
            markup.add(types.InlineKeyboardButton(s[1], callback_data=f"book_{s[0]}"))
        bot.edit_message_text(f"Вільний час на {day}:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("book_"):
        slot_id = call.data.split("_")[1]
        conn = sqlite3.connect('nail.db')
        cursor = conn.cursor()
        cursor.execute("SELECT date, time FROM slots WHERE id=?", (slot_id,))
        res = cursor.fetchone()
        cursor.execute("UPDATE slots SET status='booked' WHERE id=?", (slot_id,))
        conn.commit()
        conn.close()
        
        bot.edit_message_text(f"✅ Ви успішно записані на {res[0]} о {res[1]}!", call.message.chat.id, call.message.message_id)
        bot.send_message(config.ADMIN_ID, f"🔥 <b>Новий запис!</b>\nКлієнт: @{call.from_user.username}\nДата: {res[0]} {res[1]}", parse_mode='HTML')

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
