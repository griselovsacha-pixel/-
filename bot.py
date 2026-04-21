import telebot
import psycopg2
import config
import datetime
import re
import logging
from telebot import types
from flask import Flask
from threading import Thread
from apscheduler.schedulers.background import BackgroundScheduler

# --- СИСТЕМНІ НАЛАШТУВАННЯ ---
logging.basicConfig(level=logging.INFO)
app = Flask('')
@app.route('/')
def home(): return "Nail Ultra CRM: Status Legendary 💅🔥"
def run_s(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run_s).start()

bot = telebot.TeleBot(config.TOKEN)
scheduler = BackgroundScheduler()
scheduler.start()

# --- DATABASE ENGINE (HIGH RELIABILITY) ---
def execute_db(query, params=(), fetch=False):
    conn = None
    try:
        conn = psycopg2.connect(config.DB_URL)
        cur = conn.cursor()
        cur.execute(query, params)
        data = cur.fetchall() if fetch else None
        conn.commit()
        cur.close()
        return data
    except Exception as e:
        logging.error(f"DB Error: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()

def init_db():
    tables = [
        "slots (id SERIAL PRIMARY KEY, date TEXT, time TEXT, status TEXT DEFAULT 'free', user_id TEXT, username TEXT, phone TEXT, service_name TEXT, price INTEGER DEFAULT 0)",
        "users (user_id TEXT PRIMARY KEY, username TEXT, visits INTEGER DEFAULT 0, is_banned BOOLEAN DEFAULT FALSE)",
        "admins (user_id TEXT PRIMARY KEY, username TEXT)",
        "services (id SERIAL PRIMARY KEY, name TEXT, price INTEGER)",
        "reviews (id SERIAL PRIMARY KEY, user_id TEXT, rating INTEGER, comment TEXT)"
    ]
    for t in tables: execute_db(f"CREATE TABLE IF NOT EXISTS {t}")
    execute_db("INSERT INTO admins (user_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING", (str(config.OWNER_ID), 'Owner'))
    if not execute_db("SELECT id FROM services LIMIT 1", fetch=True):
        execute_db("INSERT INTO services (name, price) VALUES ('Манікюр', 500), ('Нарощування', 1000), ('Педикюр', 700)")

init_db()

# --- VALIDATION UTILS ---
def check_sub(uid):
    try:
        status = bot.get_chat_member(config.CHANNEL_ID, uid).status
        return status in ['member', 'administrator', 'creator']
    except: return True

def is_admin(uid):
    res = execute_db("SELECT user_id FROM admins WHERE user_id=%s", (str(uid),), fetch=True)
    return bool(res)

def is_banned(uid):
    res = execute_db("SELECT is_banned FROM users WHERE user_id=%s", (str(uid),), fetch=True)
    return res[0][0] if res else False

# --- SCHEDULER LOGIC ---
def send_alert(chat_id, text):
    try: bot.send_message(chat_id, text, parse_mode='HTML')
    except: pass

def ask_review(chat_id, srv):
    m = types.InlineKeyboardMarkup().add(*[types.InlineKeyboardButton(f"{i}⭐", callback_data=f"rev_{i}") for i in range(1, 6)])
    send_alert(chat_id, f"💖 <b>Дякуємо за візит!</b>\nЯк вам послуга {srv}? Будь ласка, оцініть нас:", m)

def set_reminders(uid, d, t, srv):
    try:
        dt = datetime.datetime.strptime(f"{d}.{datetime.datetime.now().year} {t}", "%d.%m.%Y %H:%M")
        now = datetime.datetime.now()
        # Нагадування
        for delta, label in [(datetime.timedelta(days=1), "завтра"), (datetime.timedelta(hours=2), "через 2 години")]:
            run_t = dt - delta
            if run_t > now:
                scheduler.add_job(send_alert, 'date', run_date=run_t, args=[uid, f"⏰ <b>Нагадування!</b>\nЧекаємо на вас {label} о {t}."])
        # Відгук через 4 години після початку
        scheduler.add_job(ask_review, 'date', run_date=dt+datetime.timedelta(hours=4), args=[uid, srv])
    except: pass

# --- KEYBOARDS ---
def get_main_kb(uid):
    m = types.InlineKeyboardMarkup(row_width=2)
    u = execute_db("SELECT visits FROM users WHERE user_id=%s", (str(uid),), fetch=True)
    v = u[0][0] if u else 0
    p = "👑 VIP " if v >= 10 else "✨ "
    m.add(
        types.InlineKeyboardButton(f"📅 {p}Записатися", callback_data='u_book'),
        types.InlineKeyboardButton("💎 Прайс", callback_data='u_price'),
        types.InlineKeyboardButton("📋 Мої записи", callback_data='u_my'),
        types.InlineKeyboardButton("🖼 Портфоліо", callback_data='u_port'),
        types.InlineKeyboardButton("📍 Локація", callback_data='u_loc')
    )
    return m

# --- BOT LOGIC ---
@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.from_user.id)
    if is_banned(uid): return bot.send_message(m.chat.id, "❌ Доступ заблоковано.")
    
    execute_db("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET username=%s", (uid, m.from_user.username, m.from_user.username))
    
    if not check_sub(uid):
        mk = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📢 Підписатися на канал", url=config.CHANNEL_LINK))
        mk.add(types.InlineKeyboardButton("✅ Перевірити", callback_data="check_sub"))
        return bot.send_message(m.chat.id, "👋 <b>Вітаємо!</b>\nБудь ласка, підпишіться на наш канал для продовження:", parse_mode='HTML', reply_markup=mk)
    
    bot.send_message(m.chat.id, "🌟 <b>Nail Luxe CRM Pro</b>\nОберіть дію:", parse_mode='HTML', reply_markup=get_main_kb(uid))

@bot.callback_query_handler(func=lambda call: True)
def handle_calls(call):
    uid = str(call.from_user.id)
    if is_banned(uid): return
    
    if call.data == "check_sub":
        if check_sub(uid): start(call.message)
        else: bot.answer_callback_query(call.id, "❌ Ви не підписані!", show_alert=True)

    elif call.data == "u_book":
        s = execute_db("SELECT name, price FROM services", fetch=True)
        m = types.InlineKeyboardMarkup()
        for x in s: m.add(types.InlineKeyboardButton(f"{x[0]} ({x[1]}₴)", callback_data=f"b1_{x[0]}_{x[1]}"))
        m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="to_main"))
        bot.edit_message_text("💅 <b>Оберіть процедуру:</b>", call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=m)

    elif call.data.startswith("b1_"):
        _, srv, prc = call.data.split('_')
        days = execute_db("SELECT DISTINCT date FROM slots WHERE status='free' ORDER BY date", fetch=True)
        if not days: return bot.edit_message_text("😔 Наразі немає вільних вікон.", call.message.chat.id, call.message.message_id, reply_markup=get_main_kb(uid))
        m = types.InlineKeyboardMarkup()
        for d in days: m.add(types.InlineKeyboardButton(d[0], callback_data=f"b2_{d[0]}_{srv}_{prc}"))
        m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="u_book"))
        bot.edit_message_text("📆 <b>Оберіть дату:</b>", call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=m)

    elif call.data.startswith("b2_"):
        _, d, srv, prc = call.data.split('_')
        tms = execute_db("SELECT id, time FROM slots WHERE date=%s AND status='free' ORDER BY time", (d,), fetch=True)
        m = types.InlineKeyboardMarkup()
        for t in tms: m.add(types.InlineKeyboardButton(t[1], callback_data=f"b3_{t[0]}_{srv}_{prc}"))
        m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"b1_{srv}_{prc}"))
        bot.edit_message_text(f"⏰ <b>Час на {d}:</b>", call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=m)

    elif call.data.startswith("b3_"):
        sid, srv, prc = call.data.split('_')[1:]
        msg = bot.send_message(call.message.chat.id, "📞 <b>Введіть Ім'я та Телефон:</b>\n(Або напишіть 'назад')")
        bot.register_next_step_handler(msg, finish_book, sid, srv, prc)

    elif call.data == "u_price":
        s = execute_db("SELECT name, price FROM services", fetch=True)
        txt = "💎 <b>Прайс-лист:</b>\n\n" + "\n".join([f"🔸 {x[0]}: <b>{x[1]}₴</b>" for x in s])
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=get_main_kb(uid))

    elif call.data == "u_loc":
        bot.send_message(call.message.chat.id, "📍 <b>Ми тут:</b>\nвул. Назва Вулиці, 1\nЩодня з 10:00 до 20:00", parse_mode='HTML')
        bot.send_location(call.message.chat.id, 50.4501, 30.5234)

    elif call.data == "u_port":
        mk = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Відкрити Pinterest 📸", url="https://ru.pinterest.com/crystalwithluv/_created/"))
        bot.send_message(call.message.chat.id, "Наші роботи:", reply_markup=mk)

    elif call.data == "u_my":
        r = execute_db("SELECT id, date, time, service_name FROM slots WHERE user_id=%s AND status='booked'", (uid,), fetch=True)
        if not r: return bot.answer_callback_query(call.id, "У вас немає записів.")
        for x in r:
            m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("❌ Скасувати", callback_data=f"can_{x[0]}"))
            bot.send_message(call.message.chat.id, f"🗓 {x[1]} о {x[2]}\n💅 {x[3]}", reply_markup=m)

    elif call.data.startswith("can_"):
        execute_db("UPDATE slots SET status='free', user_id=NULL, username=NULL, phone=NULL, service_name=NULL WHERE id=%s", (call.data.split('_')[1],))
        bot.edit_message_text("✅ Запис скасовано.", call.message.chat.id, call.message.message_id)

    elif call.data == "to_main":
        bot.edit_message_text("🌸 Головне меню:", call.message.chat.id, call.message.message_id, reply_markup=get_main_kb(uid))

    elif call.data.startswith("rev_"):
        bot.edit_message_text("💖 Дякуємо за оцінку!", call.message.chat.id, call.message.message_id)

# --- FINAL STEP ---
def finish_book(m, sid, srv, prc):
    if m.text.lower() == "назад": return start(m)
    if len(re.findall(r'\d', m.text)) < 10:
        msg = bot.send_message(m.chat.id, "❌ <b>Помилка!</b> Введіть коректні дані (напр: Ганна 0951234567):")
        return bot.register_next_step_handler(msg, finish_book, sid, srv, prc)
    
    uid = str(m.from_user.id)
    slot = execute_db("SELECT date, time FROM slots WHERE id=%s", (sid,), fetch=True)[0]
    execute_db("UPDATE slots SET status='booked', user_id=%s, username=%s, phone=%s, service_name=%s, price=%s WHERE id=%s", (uid, m.from_user.username, m.text, srv, prc, sid))
    execute_db("UPDATE users SET visits = visits + 1 WHERE user_id=%s", (uid,))
    
    set_reminders(uid, slot[0], slot[1], srv)
    bot.send_message(m.chat.id, f"✅ <b>Запис підтверджено!</b>\n🗓 {slot[0]} {slot[1]}\n💅 {srv}", parse_mode='HTML', reply_markup=get_main_kb(uid))
    bot.send_message(config.OWNER_ID, f"🔔 <b>Новий запис!</b>\n@{m.from_user.username}\n📞 {m.text}\n🗓 {slot[0]} {slot[1]}")

# --- ADMIN PANEL ---
@bot.message_handler(commands=['admin'])
def admin(m):
    if is_admin(m.from_user.id):
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        kb.add("➕ Додати вікно", "📋 Список записів", "📊 Статистика", "📢 Розсилка", "🚫 Бан", "🏠 Меню")
        bot.send_message(m.chat.id, "🛠 <b>Admin CRM</b>", parse_mode='HTML', reply_markup=kb)

@bot.message_handler(func=lambda m: True)
def admin_logic(m):
    if not is_admin(m.from_user.id): return
    
    if m.text == "➕ Додати вікно":
        msg = bot.send_message(m.chat.id, "Введіть дату та час (напр: <code>30.05 14:00</code>):", parse_mode='HTML')
        bot.register_next_step_handler(msg, add_slot)
    
    elif m.text == "📋 Список записів":
        r = execute_db("SELECT date, time, username, phone, service_name FROM slots WHERE status='booked' ORDER BY date", fetch=True)
        txt = "📋 <b>Записи:</b>\n\n" + "\n".join([f"▪️ {x[0]} {x[1]} - @{x[2]} ({x[4]})" for x in r]) if r else "Порожньо"
        bot.send_message(m.chat.id, txt, parse_mode='HTML')

    elif m.text == "📊 Статистика":
        s = execute_db("SELECT COUNT(*), SUM(price) FROM slots WHERE status='booked'", fetch=True)[0]
        bot.send_message(m.chat.id, f"📈 <b>Каса:</b> {s[1] or 0}₴\n📅 <b>Записів:</b> {s[0]}", parse_mode='HTML')

    elif m.text == "🚫 Бан":
        msg = bot.send_message(m.chat.id, "Введіть ID:")
        bot.register_next_step_handler(msg, lambda ms: execute_db("UPDATE users SET is_banned=TRUE WHERE user_id=%s", (ms.text,)) or bot.send_message(ms.chat.id, "✅ Бан активовано"))

    elif m.text == "📢 Розсилка":
        msg = bot.send_message(m.chat.id, "Введіть текст:")
        bot.register_next_step_handler(msg, lambda ms: [bot.send_message(u[0], ms.text) for u in execute_db("SELECT user_id FROM users", fetch=True)])

    elif m.text == "🏠 Меню": start(m)

def add_slot(m):
    try:
        d, t = m.text.split()
        if not re.match(r'^\d{2}\.\d{2}$', d) or not re.match(r'^\d{2}:\d{2}$', t): raise ValueError
        execute_db("INSERT INTO slots (date, time) VALUES (%s, %s)", (d, t))
        bot.send_message(m.chat.id, "✅ Додано успішно!")
    except:
        msg = bot.send_message(m.chat.id, "❌ Помилка! Формат ДД.ММ ГГ:ХХ:")
        bot.register_next_step_handler(msg, add_slot)

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
