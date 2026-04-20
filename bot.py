import telebot
from telebot import types
import config
import sqlite3
from flask import Flask
from threading import Thread

# --- ANTI-SLEEP ДЛЯ RENDER ---
app = Flask('')
@app.route('/')
def home(): return "Pro Nail System is Active!"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive():
    t = Thread(target=run)
    t.start()

bot = telebot.TeleBot(config.TOKEN)

# --- РОБОТА З БАЗОЮ ДАНИХ ---
def execute_db(query, params=(), fetch=False):
    conn = sqlite3.connect('nail_pro_max.db')
    cursor = conn.cursor()
    cursor.execute(query, params)
    data = cursor.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return data

# Створення таблиць
execute_db('''CREATE TABLE IF NOT EXISTS slots 
              (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, time TEXT, status TEXT, user_id TEXT, username TEXT)''')
execute_db('''CREATE TABLE IF NOT EXISTS admins (user_id TEXT PRIMARY KEY)''')
execute_db('''CREATE TABLE IF NOT EXISTS services (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price TEXT)''')
execute_db('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')

# Робимо тебе Головним Адміном
execute_db("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (str(config.OWNER_ID),))

# Початкові дані (Прайс та Інфо)
if not execute_db("SELECT * FROM services", fetch=True):
    execute_db("INSERT INTO services (name, price) VALUES (?, ?)", ("Манікюр + Покриття", "500"))
if not execute_db("SELECT * FROM settings WHERE key='master_info'", fetch=True):
    execute_db("INSERT INTO settings (key, value) VALUES (?, ?)", ("master_info", "Привіт! Я твій майстер манікюру. ✨"))

# Перевірка прав
def is_admin(user_id):
    res = execute_db("SELECT user_id FROM admins WHERE user_id=?", (str(user_id),), fetch=True)
    return True if res else False

# --- КЛІЄНТСЬКЕ МЕНЮ ---
def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📅 Записатися на сеанс", callback_data='u_choose_day'),
        types.InlineKeyboardButton("💅 Послуги та прайс", callback_data='u_services'),
        types.InlineKeyboardButton("📋 Мої записи / Скасувати", callback_data='u_my_bookings'),
        types.InlineKeyboardButton("ℹ️ Про майстра", callback_data='u_info')
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🌟 <b>Вітаємо у студії манікюру!</b>\nОберіть потрібну дію:", 
                     parse_mode='HTML', reply_markup=main_menu())

# --- АДМІН-ПАНЕЛЬ ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if is_admin(message.from_user.id):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("➕ Додати вікно", "📋 Список усіх записів", "💰 Керувати послугами", "⚙️ Налаштування майстра")
        if message.from_user.id == config.OWNER_ID:
            markup.add("👑 Назначити адміна")
        bot.send_message(message.chat.id, "🛠 <b>Панель майстра активована!</b>", parse_mode='HTML', reply_markup=markup)

# --- ЛОГІКА ТЕКСТОВИХ КОМАНД АДМІНА ---
@bot.message_handler(func=lambda m: is_admin(m.from_user.id))
def admin_text(message):
    if message.text == "➕ Додати вікно":
        msg = bot.send_message(message.chat.id, "Введіть дату та час через пробіл (напр: 23.04 14:00):")
        bot.register_next_step_handler(msg, save_slot)
    
    elif message.text == "📋 Список усіх записів":
        slots = execute_db("SELECT id, date, time, username FROM slots WHERE status='booked' ORDER BY date", fetch=True)
        if not slots: bot.send_message(message.chat.id, "Наразі записів немає.")
        for s in slots:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ Скасувати запис", callback_data=f"adm_cancel_{s[0]}"))
            bot.send_message(message.chat.id, f"📅 {s[1]} {s[2]}\n👤 Клієнт: @{s[3]}", reply_markup=markup)

    elif message.text == "💰 Керувати послугами":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Додати нову послугу", callback_data="adm_add_serv"))
        servs = execute_db("SELECT id, name, price FROM services", fetch=True)
        for s in servs:
            markup.add(types.InlineKeyboardButton(f"🗑 Видалити {s[1]}", callback_data=f"adm_del_serv_{s[0]}"))
        bot.send_message(message.chat.id, "Ваш прайс-лист:", reply_markup=markup)

    elif message.text == "⚙️ Налаштування майстра":
        msg = bot.send_message(message.chat.id, "Напишіть нову інформацію про себе:")
        bot.register_next_step_handler(msg, save_info)

    elif message.text == "👑 Назначити адміна" and message.from_user.id == config.OWNER_ID:
        msg = bot.send_message(message.chat.id, "Введіть Telegram ID нового адміна:")
        bot.register_next_step_handler(msg, save_new_admin)

# --- ФУНКЦІЇ ЗБЕРЕЖЕННЯ (NEXT STEP HANDLERS) ---
def save_slot(message):
    try:
        d, t = message.text.split()
        execute_db("INSERT INTO slots (date, time, status) VALUES (?, ?, 'free')", (d, t))
        bot.send_message(message.chat.id, "✅ Віконце успішно додано!")
    except: bot.send_message(message.chat.id, "❌ Помилка! Формат має бути: 23.04 14:00")

def save_info(message):
    execute_db("UPDATE settings SET value=? WHERE key='master_info'", (message.text,))
    bot.send_message(message.chat.id, "✅ Дані оновлено!")

def save_new_admin(message):
    execute_db("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (message.text,))
    bot.send_message(message.chat.id, f"✅ Користувач {message.text} тепер адмін.")

def save_service(message):
    try:
        name, price = message.text.split(',')
        execute_db("INSERT INTO services (name, price) VALUES (?, ?)", (name.strip(), price.strip()))
        bot.send_message(message.chat.id, "✅ Послугу додано до прайсу!")
    except: bot.send_message(message.chat.id, "❌ Формат: Назва, Ціна")

# --- ОБРОБКА CALLBACK КНОПОК ---
@bot.callback_query_handler(func=lambda call: True)
def calls(call):
    # Клієнтська частина
    if call.data == "u_services":
        s = execute_db("SELECT name, price FROM services", fetch=True)
        res = "💎 <b>Наші послуги:</b>\n\n"
        for i in s: res += f"▫️ {i[0]} — <b>{i[1]}₴</b>\n"
        bot.edit_message_text(res, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=main_menu())

    elif call.data == "u_info":
        info = execute_db("SELECT value FROM settings WHERE key='master_info'", fetch=True)[0][0]
        bot.edit_message_text(f"ℹ️ <b>Про майстра:</b>\n\n{info}", call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=main_menu())

    elif call.data == "u_choose_day":
        days = execute_db("SELECT DISTINCT date FROM slots WHERE status='free'", fetch=True)
        if not days: bot.answer_callback_query(call.id, "Вільних місць немає.")
        else:
            markup = types.InlineKeyboardMarkup()
            for d in days: markup.add(types.InlineKeyboardButton(f"🗓 {d[0]}", callback_data=f"uday_{d[0]}"))
            bot.edit_message_text("Оберіть дату:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("uday_"):
        day = call.data.split("_")[1]
        slots = execute_db("SELECT id, time FROM slots WHERE date=? AND status='free'", (day,), fetch=True)
        markup = types.InlineKeyboardMarkup()
        for s in slots: markup.add(types.InlineKeyboardButton(f"⏰ {s[1]}", callback_data=f"ubook_{s[0]}"))
        bot.edit_message_text(f"Час на {day}:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("ubook_"):
        sid = call.data.split("_")[1]
        slot = execute_db("SELECT date, time FROM slots WHERE id=?", (sid,), fetch=True)[0]
        execute_db("UPDATE slots SET status='booked', user_id=?, username=? WHERE id=?", (call.from_user.id, call.from_user.username, sid))
        bot.edit_message_text(f"✅ <b>Записано!</b>\n{slot[0]} о {slot[1]}", call.message.chat.id, call.message.message_id, parse_mode='HTML')
        bot.send_message(config.OWNER_ID, f"🔔 Запис: @{call.from_user.username} на {slot[0]} {slot[1]}")

    # Адмінська частина
    elif call.data == "adm_add_serv":
        msg = bot.send_message(call.message.chat.id, "Введіть: Назва, Ціна")
        bot.register_next_step_handler(msg, save_service)

    elif call.data.startswith("adm_del_serv_"):
        execute_db("DELETE FROM services WHERE id=?", (call.data.split("_")[3],))
        bot.answer_callback_query(call.id, "Видалено")
        bot.delete_message(call.message.chat.id, call.message.message_id)

    elif call.data.startswith("adm_cancel_"):
        sid = call.data.split("_")[2]
        user = execute_db("SELECT user_id, date, time FROM slots WHERE id=?", (sid,), fetch=True)[0]
        execute_db("UPDATE slots SET status='free', user_id=NULL, username=NULL WHERE id=?", (sid,))
        bot.send_message(user[0], f"⚠️ Ваш запис на {user[1]} {user[2]} скасовано майстром.")
        bot.answer_callback_query(call.id, "Запис скасовано")
        bot.delete_message(call.message.chat.id, call.message.message_id)

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
