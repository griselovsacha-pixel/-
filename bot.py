import telebot, psycopg2, config
from telebot import types
from flask import Flask
from threading import Thread

# --- ЖИТТЄЗАБЕЗПЕЧЕННЯ (Flask для Render) ---
app = Flask('')
@app.route('/')
def home(): return "Nail Empire Ultimate: Status ONLINE 💅🔥"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

bot = telebot.TeleBot(config.TOKEN)

# --- РОБОТА З БАЗОЮ (PostgreSQL) ---
def execute_db(query, params=(), fetch=False):
    conn = psycopg2.connect(config.DB_URL)
    cur = conn.cursor()
    cur.execute(query, params)
    data = cur.fetchall() if fetch else None
    conn.commit()
    cur.close(); conn.close()
    return data

# Створення всіх необхідних таблиць
tables = [
    "slots (id SERIAL PRIMARY KEY, date TEXT, time TEXT, status TEXT DEFAULT 'free', user_id TEXT, username TEXT, service_name TEXT)",
    "admins (user_id TEXT PRIMARY KEY)",
    "services (id SERIAL PRIMARY KEY, name TEXT, price TEXT)",
    "settings (key TEXT PRIMARY KEY, value TEXT)",
    "users (user_id TEXT PRIMARY KEY, username TEXT, visits INTEGER DEFAULT 0)",
    "portfolio (id SERIAL PRIMARY KEY, file_id TEXT, description TEXT)"
]
for table in tables: execute_db(f"CREATE TABLE IF NOT EXISTS {table}")

# Додавання власника як адміна
execute_db("INSERT INTO admins (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (str(config.OWNER_ID),))

# Налаштування за замовчуванням
defaults = [('studio_name', 'Nail Luxe Studio'), ('location_url', 'http://maps.google.com')]
for k, v in defaults: execute_db("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT DO NOTHING", (k, v))

# --- МЕНЮ ---
def main_menu(uid):
    m = types.InlineKeyboardMarkup(row_width=2)
    u = execute_db("SELECT visits FROM users WHERE user_id=%s", (str(uid),), fetch=True)
    v = u[0][0] if u else 0
    pref = "👑 VIP " if v >= 10 else "🎖️ Pro " if v >= 3 else "✨ "
    m.add(types.InlineKeyboardButton(f"📅 {pref}Записатися", callback_data='u_book'),
          types.InlineKeyboardButton("📸 Портфоліо", callback_data='u_port'),
          types.InlineKeyboardButton("💅 Прайс", callback_data='u_serv'),
          types.InlineKeyboardButton("👤 Профіль", callback_data='u_prof'),
          types.InlineKeyboardButton("📍 Локація", callback_data='u_loc'))
    return m

@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    execute_db("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET username=%s", (uid, message.from_user.username, message.from_user.username))
    s_name = execute_db("SELECT value FROM settings WHERE key='studio_name'", fetch=True)[0][0]
    bot.send_message(message.chat.id, f"🌟 <b>Вітаємо у {s_name}!</b>\nОберіть дію:", parse_mode='HTML', reply_markup=main_menu(uid))

# --- АДМІН-ФУНКЦІЇ ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.from_user.id) == str(config.OWNER_ID):
        m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        m.add("➕ Додати вікно", "📋 Всі записи", "💰 Додати послугу", "🖼️ В портфоліо", "📢 Розсилка", "🏠 Меню")
        bot.send_message(message.chat.id, "🛠 <b>Admin Panel Active</b>", parse_mode='HTML', reply_markup=m)

@bot.message_handler(func=lambda m: True)
def admin_logic(message):
    if str(message.from_user.id) != str(config.OWNER_ID): return
    if message.text == "🏠 Меню": start(message)
    elif message.text == "➕ Додати вікно":
        msg = bot.send_message(message.chat.id, "Введіть дату та час (напр: 25.04 14:00):")
        bot.register_next_step_handler(msg, lambda m: execute_db("INSERT INTO slots (date, time) VALUES (%s, %s)", m.text.split()) or bot.send_message(m.chat.id, "✅ Додано!"))
    elif message.text == "💰 Додати послугу":
        msg = bot.send_message(message.chat.id, "Назва послуги та ціна (напр: Манікюр, 500):")
        bot.register_next_step_handler(msg, lambda m: execute_db("INSERT INTO services (name, price) VALUES (%s, %s)", m.text.split(', ')) or bot.send_message(m.chat.id, "✅ Послугу збережено!"))
    elif message.text == "🖼️ В портфоліо":
        msg = bot.send_message(message.chat.id, "Надішліть ФОТО з описом:")
        bot.register_next_step_handler(msg, lambda m: execute_db("INSERT INTO portfolio (file_id, description) VALUES (%s, %s)", (m.photo[-1].file_id, m.caption)) if m.photo else None)
    elif message.text == "📋 Всі записи":
        recs = execute_db("SELECT date, time, username FROM slots WHERE status='booked'", fetch=True)
        txt = "📋 <b>Актуальні записи:</b>\n\n" + "\n".join([f"🗓️ {r[0]} {r[1]} - @{r[2]}" for r in recs]) if recs else "Записів немає"
        bot.send_message(message.chat.id, txt, parse_mode='HTML')
    elif message.text == "📢 Розсилка":
        msg = bot.send_message(message.chat.id, "Текст для розсилки:")
        bot.register_next_step_handler(msg, lambda m: [bot.send_message(u[0], m.text) for u in execute_db("SELECT user_id FROM users", fetch=True)])

# --- ОБРОБКА КНОПОК ---
@bot.callback_query_handler(func=lambda call: True)
def handle_calls(call):
    uid = str(call.from_user.id)
    if call.data == 'u_serv':
        srv = execute_db("SELECT name, price FROM services", fetch=True)
        txt = "💅 <b>Прайс:</b>\n\n" + "\n".join([f"▫️ {s[0]} — {s[1]}₴" for s in srv]) if srv else "Прайс порожній."
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=main_menu(uid))
    elif call.data == 'u_port':
        imgs = execute_db("SELECT file_id, description FROM portfolio LIMIT 5", fetch=True)
        for i in imgs: bot.send_photo(call.message.chat.id, i[0], caption=i[1])
    elif call.data == 'u_book':
        days = execute_db("SELECT DISTINCT date FROM slots WHERE status='free' ORDER BY date", fetch=True)
        m = types.InlineKeyboardMarkup()
        for d in days: m.add(types.InlineKeyboardButton(f"🗓️ {d[0]}", callback_data=f"d_{d[0]}"))
        bot.edit_message_text("Оберіть дату візиту:", call.message.chat.id, call.message.message_id, reply_markup=m)
    elif call.data.startswith('d_'):
        day = call.data.split('_')[1]
        times = execute_db("SELECT id, time FROM slots WHERE date=%s AND status='free' ORDER BY time", (day,), fetch=True)
        m = types.InlineKeyboardMarkup()
        for t in times: m.add(types.InlineKeyboardButton(f"⏰ {t[1]}", callback_data=f"b_{t[0]}"))
        bot.edit_message_text(f"Оберіть час на {day}:", call.message.chat.id, call.message.message_id, reply_markup=m)
    elif call.data.startswith('b_'):
        sid = call.data.split('_')[1]
        execute_db("UPDATE slots SET status='booked', user_id=%s, username=%s WHERE id=%s", (uid, call.from_user.username, sid))
        execute_db("UPDATE users SET visits = visits + 1 WHERE user_id=%s", (uid,))
        bot.edit_message_text("✅ Запис успішний! До зустрічі! ✨", call.message.chat.id, call.message.message_id)
    elif call.data == 'u_prof':
        u = execute_db("SELECT visits FROM users WHERE user_id=%s", (uid,), fetch=True)
        bot.answer_callback_query(call.id, f"У вас {u[0][0]} візитів! ❤️")

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
