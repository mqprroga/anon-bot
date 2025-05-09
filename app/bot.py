import telebot
from telebot.types import Message
import time
from collections import defaultdict
from datetime import datetime

TOKEN = ''
ADMIN_USERNAME = ''

bot = telebot.TeleBot(TOKEN)

users = {}
banned_users = set()
waiting_list = []
reports = {}
chats = {} 
chat_messages = defaultdict(list)

# ==============================================
# ДЕКОРАТОРЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================

def admin_only(func):
    """Декоратор для проверки прав администратора"""
    def wrapper(message):
        username = message.from_user.username
        if not username or str(username).lower() != ADMIN_USERNAME.lower():
            bot.send_message(message.chat.id, "❌ Доступ запрещен")
            return
        return func(message)
    return wrapper

def format_timestamp(timestamp):
    """Форматирование времени в читаемый вид"""
    return datetime.fromtimestamp(timestamp).strftime('%d.%m.%Y %H:%M:%S')

# ==============================================
# ОСНОВНЫЕ ФУНКЦИИ
# ==============================================

def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    
    if username.lower() in banned_users:
        bot.send_message(user_id, "🚫 Вы заблокированы и не можете использовать бота")
        return
    
    users[user_id] = {
        "state": "none",
        "partner_id": None,
        "chat_id": None,
        "username": username
    }
    
    bot.send_message(
        message.chat.id,
        "👋 Привет! Это анонимный чат.\n"
        "Доступные команды:\n"
        "/find - Найти собеседника\n"
        "/leave - Выйти из чата\n"
        "/report - Пожаловаться на собеседника\n"
        "/help - Помощь"
    )

def show_help(message):
    bot.send_message(
        message.chat.id,
        "📋 Доступные команды:\n"
        "/find - Найти собеседника\n"
        "/leave - Выйти из чата\n"
        "/report - Пожаловаться на собеседника\n"
        "/help - Помощь"
    )

def find_partner(message):
    user_id = message.from_user.id
    username = users.get(user_id, {}).get('username', str(user_id))
    
    if username.lower() in banned_users:
        bot.send_message(user_id, "🚫 Вы заблокированы и не можете использовать бота")
        return
    
    if user_id not in users:
        send_welcome(message)
        return
    
    if users[user_id]["state"] != "none":
        bot.send_message(message.chat.id, "❌ Вы уже в чате или в поиске")
        return
    
    users[user_id]["state"] = "waiting"
    waiting_list.append(user_id)
    
    bot.send_message(message.chat.id, "🔍 Ищем собеседника...")
    try_find_pair()

def try_find_pair():
    while len(waiting_list) >= 2:
        user1 = waiting_list.pop(0)
        user2 = waiting_list.pop(0)
        
        if users[user1]["state"] != "waiting" or users[user2]["state"] != "waiting":
            continue
        
        chat_id = f"{user1}_{user2}_{int(time.time())}"
        chats[chat_id] = {
            "user1": user1,
            "user2": user2,
            "created_at": time.time()
        }

        users[user1].update({"state": "chatting", "partner_id": user2, "chat_id": chat_id})
        users[user2].update({"state": "chatting", "partner_id": user1, "chat_id": chat_id})

        bot.send_message(user1, f"💬 Собеседник найден! (ID чата: {chat_id})\nНачинайте общение.")
        bot.send_message(user2, f"💬 Собеседник найден! (ID чата: {chat_id})\nНачинайте общение.")

def leave_chat(message):
    user_id = message.from_user.id
    
    if user_id not in users or users[user_id]["state"] == "none":
        bot.send_message(user_id, "❌ Вы не в чате")
        return
    
    if users[user_id]["state"] == "waiting":
        waiting_list.remove(user_id)
        users[user_id]["state"] = "none"
        bot.send_message(user_id, "🔎 Поиск остановлен")
        return

    chat_id = users[user_id]["chat_id"]
    partner_id = users[user_id]["partner_id"]

    users[user_id]["state"] = "none"
    users[user_id]["partner_id"] = None
    users[user_id]["chat_id"] = None
    
    bot.send_message(user_id, "✅ Вы вышли из чата")

    if partner_id in users and users[partner_id]["state"] == "chatting":
        bot.send_message(partner_id, "❌ Собеседник покинул чат")
        users[partner_id]["state"] = "none"
        users[partner_id]["partner_id"] = None
        users[partner_id]["chat_id"] = None

def report_user(message):
    user_id = message.from_user.id
    
    if user_id not in users or users[user_id]["state"] != "chatting":
        bot.send_message(user_id, "❌ Вы можете пожаловаться только на текущего собеседника")
        return
    
    partner_id = users[user_id]["partner_id"]
    reports[partner_id] = reports.get(partner_id, 0) + 1
    
    if reports[partner_id] >= 3:  # После 3 жалоб блокируем пользователя
        bot.send_message(partner_id, "🚫 Вы были заблокированы из-за жалоб")
        leave_chat_by_id(partner_id)
    
    bot.send_message(user_id, "✅ Жалоба отправлена. Спасибо!")
    leave_chat(message)

def forward_message(message):
    user_id = message.from_user.id
    chat_info = users[user_id]
    
    if chat_info["state"] != "chatting" or chat_info["partner_id"] not in users:
        bot.send_message(user_id, "❌ Собеседник покинул чат")
        users[user_id]["state"] = "none"
        return
    
    partner_id = chat_info["partner_id"]
    chat_id = chat_info["chat_id"]

    if message.content_type == 'text':
        chat_messages[chat_id].append({
            "sender": user_id,
            "type": "text",
            "content": message.text,
            "timestamp": time.time()
        })
    else:
        if message.content_type == 'photo':
            content = message.photo[-1].file_id
        elif message.content_type in ['video', 'document', 'audio', 'voice', 'sticker']:
            content = getattr(message, message.content_type).file_id
        
        chat_messages[chat_id].append({
            "sender": user_id,
            "type": message.content_type,
            "content": content,
            "timestamp": time.time()
        })

    try:
        if message.content_type == 'text':
            bot.send_message(partner_id, message.text)
        elif message.content_type == 'photo':
            bot.send_photo(partner_id, message.photo[-1].file_id)
        elif message.content_type == 'video':
            bot.send_video(partner_id, message.video.file_id)
        elif message.content_type == 'document':
            bot.send_document(partner_id, message.document.file_id)
        elif message.content_type == 'audio':
            bot.send_audio(partner_id, message.audio.file_id)
        elif message.content_type == 'voice':
            bot.send_voice(partner_id, message.voice.file_id)
        elif message.content_type == 'sticker':
            bot.send_sticker(partner_id, message.sticker.file_id)
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")
        leave_chat_by_id(partner_id)
        bot.send_message(user_id, "❌ Собеседник покинул чат")
        users[user_id]["state"] = "none"

def leave_chat_by_id(user_id):
    if user_id not in users:
        return
    
    if users[user_id]["state"] == "waiting":
        if user_id in waiting_list:
            waiting_list.remove(user_id)
    elif users[user_id]["state"] == "chatting":
        partner_id = users[user_id]["partner_id"]
        if partner_id in users and users[partner_id]["state"] == "chatting":
            bot.send_message(partner_id, "❌ Собеседник покинул чат")
            users[partner_id]["state"] = "none"
            users[partner_id]["partner_id"] = None
            users[partner_id]["chat_id"] = None
    
    users[user_id]["state"] = "none"
    users[user_id]["partner_id"] = None
    users[user_id]["chat_id"] = None

# ==============================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ
# ==============================================

@bot.message_handler(commands=['start', 'help', 'find', 'leave', 'report', 'stats', 'history', 'chat_id', 'ban', 'unban'])
def handle_commands(message):
    command = message.text.split()[0].lower()
    
    if command == '/start':
        send_welcome(message)
    elif command == '/help':
        show_help(message)
    elif command == '/find':
        find_partner(message)
    elif command == '/leave':
        leave_chat(message)
    elif command == '/report':
        report_user(message)
    elif command == '/stats':
        admin_stats(message)
    elif command == '/history':
        chat_history(message)
    elif command == '/chat_id':
        get_chat_ids(message)
    elif command == '/ban':
        ban_user(message)
    elif command == '/unban':
        unban_user(message)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    
    if user_id not in users:
        send_welcome(message)
        return
    
    if users[user_id]["state"] != "chatting":
        bot.send_message(user_id, "ℹ️ Используйте команды для навигации (/help)")
        return
    
    forward_message(message)

@bot.message_handler(content_types=['photo', 'video', 'document', 'audio', 'voice', 'sticker'])
def handle_media(message):
    user_id = message.from_user.id
    
    if user_id not in users or users[user_id]["state"] != "chatting":
        return
    
    forward_message(message)

# ==============================================
# АДМИН-ФУНКЦИИ
# ==============================================

@admin_only
def unban_user(message):
    """Разблокировка пользователя по юзернейму"""
    if len(message.text.split()) < 2:
        bot.send_message(message.chat.id, "ℹ️ Использование: /unban <username>")
        return
    
    username = message.text.split()[1].lower().strip('@')
    if username in banned_users:
        banned_users.remove(username)
        bot.send_message(message.chat.id, f"✅ Пользователь @{username} разблокирован")
    else:
        bot.send_message(message.chat.id, f"ℹ️ Пользователь @{username} не был заблокирован")


def ban_user(message):
    """Блокировка пользователя по юзернейму"""
    if len(message.text.split()) < 2:
        bot.send_message(message.chat.id, "ℹ️ Использование: /ban <username>")
        return
    
    username = message.text.split()[1].lower().strip('@')
    banned_users.add(username)
    for user_id, data in users.items():
        if data.get('username', '').lower() == username:
            if data['state'] == 'chatting':
                partner_id = data['partner_id']
                if partner_id in users:
                    bot.send_message(partner_id, "❌ Собеседник был заблокирован")
                    users[partner_id]['state'] = 'none'
                    users[partner_id]['partner_id'] = None
                    users[partner_id]['chat_id'] = None
            
            bot.send_message(user_id, "🚫 Вы были заблокированы администратором")
            users[user_id]['state'] = 'none'
            if user_id in waiting_list:
                waiting_list.remove(user_id)
    
    bot.send_message(message.chat.id, f"✅ Пользователь @{username} заблокирован")

def admin_stats(message):
    active_users = sum(1 for u in users.values() if u["state"] in ["chatting", "waiting"])
    
    stats = [
        "✨ 📊 Админ-статистика 📊 ✨",
        "",
        f"👥 Всего пользователей: {len(users)}",
        f"🔍 В поиске: {len(waiting_list)}",
        f"💬 В активных чатах: {active_users - len(waiting_list)}",
        f"📂 Всего чатов: {len(chats)}",
        f"🚫 Заблокированных: {len(banned_users)}",
        "",
        "⚡ Последние 10 пользователей:"
    ]
    
    for uid, data in list(users.items())[-10:]:
        status = "💬 в чате" if data["state"] == "chatting" else "🔍 в поиске" if data["state"] == "waiting" else "💤 не активен"
        banned = " (🚫)" if data.get('username', '').lower() in banned_users else ""
        stats.append(f"👤 {data.get('username', uid)}{banned} (ID: {uid}): {status}")
    
    bot.send_message(message.chat.id, "\n".join(stats))

@admin_only
def chat_history(message):
    if len(message.text.split()) < 2:
        bot.send_message(message.chat.id, "ℹ️ Использование: /history <chat_id>")
        return
    
    chat_id = message.text.split()[1]
    
    if chat_id not in chat_messages:
        bot.send_message(message.chat.id, "❌ Чат не найден")
        return
    
    history = [
        f"📝 История чата {chat_id}",
        f"👥 Участники: {chats[chat_id]['user1']} и {chats[chat_id]['user2']}",
        f"🕰 Создан: {format_timestamp(chats[chat_id]['created_at'])}",
        "",
        "Последние 30 сообщений:",
        "======================="
    ]
    
    for msg in chat_messages[chat_id][-30:]:
        sender = users.get(msg["sender"], {}).get("username", msg["sender"])
        time_str = format_timestamp(msg["timestamp"])
        content = msg["content"] if msg["type"] == "text" else f"[{msg['type']}]"
        history.append(f"{time_str} {sender}: {content}")
    
    # Разбиваем сообщение на части если оно слишком длинное
    msg_text = "\n".join(history)
    for i in range(0, len(msg_text), 4096):
        bot.send_message(message.chat.id, msg_text[i:i+4096])

@admin_only
def get_chat_ids(message):
    if not chats:
        bot.send_message(message.chat.id, "❌ Нет созданных чатов")
        return
    
    chat_list = [
        "📂 Список всех чатов:",
        "====================="
    ]
    
    for chat_id, chat_data in sorted(chats.items(), key=lambda x: x[1]['created_at'], reverse=True):
        user1 = users.get(chat_data['user1'], {}).get('username', chat_data['user1'])
        user2 = users.get(chat_data['user2'], {}).get('username', chat_data['user2'])
        chat_list.append(
            f"🆔 {chat_id}\n"
            f"👤 Участники: {user1} и {user2}\n"
            f"🕰 {format_timestamp(chat_data['created_at'])}\n"
            f"💬 Сообщений: {len(chat_messages.get(chat_id, []))}\n"
            "-----------------------------"
        )
    
    # Отправляем первые 10 чатов чтобы не перегружать
    msg_text = "\n".join(chat_list[:10])
    bot.send_message(message.chat.id, msg_text)

# ==============================================
# ЗАПУСК БОТА
# ==============================================

if __name__ == '__main__':
    print("✨ Бот запущен...")
    bot.infinity_polling()
