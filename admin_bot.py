import logging
import os
import psycopg2
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    ConversationHandler,
    CallbackContext,
)

# Загружаем переменные окружения
load_dotenv()

# Параметры для подключения к базе данных
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Токен для админского бота (отличается от основного бота)
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")

# Список ID администраторов, которым разрешен доступ к боту
ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id]

# Определяем состояния диалога
(MAIN_MENU, MANAGE_USERS, MANAGE_QUESTIONS, MANAGE_PROMPTS, 
 ADD_USER, REMOVE_USER, LIST_USERS, SELECT_BUSINESS_TYPE, 
 ADD_BUSINESS_TYPE, ADD_QUESTION_FOR_TYPE, EDIT_QUESTION, EDIT_PROMPT) = range(12)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_connection():
    """Возвращает соединение с базой данных."""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

# --- Проверка администратора ---
def is_admin(user_id):
    """Проверяет, является ли пользователь администратором."""
    return user_id in ADMIN_IDS

# --- Функции для работы с базой данных ---
def get_business_types():
    """Получает список всех типов бизнеса из базы данных."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT DISTINCT business_type FROM users")
    types = [row[0] for row in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    return types

def get_users_by_business_type(business_type):
    """Получает список пользователей для указанного типа бизнеса."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT telegram_id FROM users WHERE business_type = %s", (business_type,))
    users = [row[0] for row in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    return users

def add_user(telegram_id, business_type):
    """Добавляет нового пользователя в базу данных."""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "INSERT INTO users (telegram_id, business_type) VALUES (%s, %s) ON CONFLICT (telegram_id) DO UPDATE SET business_type = %s",
            (telegram_id, business_type, business_type)
        )
        conn.commit()
        success = True
    except Exception as e:
        logger.error(f"Ошибка при добавлении пользователя: {e}")
        conn.rollback()
        success = False
    
    cur.close()
    conn.close()
    
    return success

def remove_user(telegram_id):
    """Удаляет пользователя из базы данных."""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("DELETE FROM users WHERE telegram_id = %s", (telegram_id,))
        deleted = cur.rowcount > 0
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка при удалении пользователя: {e}")
        conn.rollback()
        deleted = False
    
    cur.close()
    conn.close()
    
    return deleted

def get_questions_for_business_type(business_type):
    """Получает список вопросов для указанного типа бизнеса."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        "SELECT id, question_text, question_order FROM questions WHERE business_type = %s ORDER BY question_order",
        (business_type,)
    )
    questions = [(row[0], row[1], row[2]) for row in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    return questions

def add_business_type(business_type):
    """Добавляет новый тип бизнеса и стандартные вопросы для него."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Стандартные вопросы для нового типа бизнеса
    standard_questions = [
        "Что именно вас приятно удивило или впечатлило при посещении?",
        "Какие качества персонала вызвали у вас доверие и помогли почувствовать себя комфортно?",
        "Как изменилось ваше состояние или решилась проблема после обращения?",
        "Почему бы вы порекомендовали нас друзьям или родственникам?"
    ]
    
    try:
        # Добавляем стандартные вопросы для нового типа бизнеса
        for i, question in enumerate(standard_questions):
            cur.execute(
                "INSERT INTO questions (business_type, question_text, question_order) VALUES (%s, %s, %s)",
                (business_type, question, i)
            )
        
        # Добавляем стандартный промпт для нового типа бизнеса
        standard_prompt = "На основе следующих ответов составь отзыв:\n\n{}\n\nСоставь связный, теплый отзыв, будто писал клиент, который остался доволен сервисом."
        cur.execute(
            "INSERT INTO prompts (business_type, prompt_text) VALUES (%s, %s) ON CONFLICT (business_type) DO UPDATE SET prompt_text = %s",
            (business_type, standard_prompt, standard_prompt)
        )
        
        conn.commit()
        success = True
    except Exception as e:
        logger.error(f"Ошибка при добавлении типа бизнеса: {e}")
        conn.rollback()
        success = False
    
    cur.close()
    conn.close()
    
    return success

def add_question(business_type, question_text, question_order):
    """Добавляет новый вопрос для указанного типа бизнеса."""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "INSERT INTO questions (business_type, question_text, question_order) VALUES (%s, %s, %s)",
            (business_type, question_text, question_order)
        )
        conn.commit()
        success = True
    except Exception as e:
        logger.error(f"Ошибка при добавлении вопроса: {e}")
        conn.rollback()
        success = False
    
    cur.close()
    conn.close()
    
    return success

def update_question(question_id, new_text):
    """Обновляет текст вопроса."""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "UPDATE questions SET question_text = %s WHERE id = %s",
            (new_text, question_id)
        )
        conn.commit()
        success = True
    except Exception as e:
        logger.error(f"Ошибка при обновлении вопроса: {e}")
        conn.rollback()
        success = False
    
    cur.close()
    conn.close()
    
    return success

def get_prompt(business_type):
    """Получает промпт для указанного типа бизнеса."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT prompt_text FROM prompts WHERE business_type = %s", (business_type,))
    result = cur.fetchone()
    
    cur.close()
    conn.close()
    
    if result:
        return result[0]
    else:
        return "На основе следующих ответов составь отзыв:\n\n{}\n\nСоставь связный, теплый отзыв, будто писал клиент, который остался доволен сервисом."

def update_prompt(business_type, new_prompt):
    """Обновляет промпт для указанного типа бизнеса."""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            "INSERT INTO prompts (business_type, prompt_text) VALUES (%s, %s) ON CONFLICT (business_type) DO UPDATE SET prompt_text = %s",
            (business_type, new_prompt, new_prompt)
        )
        conn.commit()
        success = True
    except Exception as e:
        logger.error(f"Ошибка при обновлении промпта: {e}")
        conn.rollback()
        success = False
    
    cur.close()
    conn.close()
    
    return success

# --- Обработчики команд ---
def start(update: Update, context: CallbackContext) -> int:
    """Начало разговора и проверка прав администратора."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        update.message.reply_text("У вас нет прав для использования этого бота.")
        return ConversationHandler.END
    
    return show_main_menu(update, context)

def show_main_menu(update: Update, context: CallbackContext) -> int:
    """Показывает главное меню администратора."""
    keyboard = [
        [InlineKeyboardButton("👥 Управление пользователями", callback_data="manage_users")],
        [InlineKeyboardButton("❓ Управление вопросами", callback_data="manage_questions")],
        [InlineKeyboardButton("📝 Управление промптами", callback_data="manage_prompts")],
        [InlineKeyboardButton("❌ Выход", callback_data="exit")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        update.message.reply_text("🔧 Панель администратора:", reply_markup=reply_markup)
    else:
        update.callback_query.edit_message_text("🔧 Панель администратора:", reply_markup=reply_markup)
    
    return MAIN_MENU

def main_menu_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор в главном меню."""
    query = update.callback_query
    query.answer()
    
    if query.data == "manage_users":
        return show_user_management(update, context)
    elif query.data == "manage_questions":
        return show_question_management(update, context)
    elif query.data == "manage_prompts":
        return show_prompt_management(update, context)
    elif query.data == "exit":
        query.edit_message_text("Выход из панели администратора.")
        return ConversationHandler.END
    else:
        return show_main_menu(update, context)

# --- Управление пользователями ---
def show_user_management(update: Update, context: CallbackContext) -> int:
    """Показывает меню управления пользователями."""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить пользователя", callback_data="add_user")],
        [InlineKeyboardButton("➖ Удалить пользователя", callback_data="remove_user")],
        [InlineKeyboardButton("📋 Список пользователей", callback_data="list_users")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.callback_query.edit_message_text("👥 Управление пользователями:", reply_markup=reply_markup)
    
    return MANAGE_USERS

def user_management_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор в меню управления пользователями."""
    query = update.callback_query
    query.answer()
    
    if query.data == "add_user":
        business_types = get_business_types()
        
        if not business_types:
            # Если типов бизнеса нет, предлагаем создать новый
            keyboard = [
                [InlineKeyboardButton("➕ Добавить тип бизнеса", callback_data="add_business_type")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back_to_user_management")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text("Нет доступных типов бизнеса. Сначала добавьте тип бизнеса:", reply_markup=reply_markup)
            return SELECT_BUSINESS_TYPE
        
        # Формируем клавиатуру с типами бизнеса
        keyboard = []
        for btype in business_types:
            keyboard.append([InlineKeyboardButton(btype, callback_data=f"select_type:{btype}")])
        
        keyboard.append([InlineKeyboardButton("➕ Добавить новый тип", callback_data="add_business_type")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_user_management")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("Выберите тип бизнеса для нового пользователя:", reply_markup=reply_markup)
        
        return SELECT_BUSINESS_TYPE
    
    elif query.data == "remove_user":
        query.edit_message_text("Введите Telegram ID пользователя, которого хотите удалить:")
        return REMOVE_USER
    
    elif query.data == "list_users":
        return show_user_list(update, context)
    
    elif query.data == "back_to_main":
        return show_main_menu(update, context)
    
    return MANAGE_USERS

def show_user_list(update: Update, context: CallbackContext) -> int:
    """Показывает список пользователей по типам бизнеса."""
    business_types = get_business_types()
    
    if not business_types:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_user_management")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.callback_query.edit_message_text("Нет зарегистрированных пользователей.", reply_markup=reply_markup)
        return LIST_USERS
    
    message_text = "📋 Список пользователей по типам бизнеса:\n\n"
    
    for btype in business_types:
        users = get_users_by_business_type(btype)
        message_text += f"📌 {btype} ({len(users)} пользователей):\n"
        
        for user_id in users:
            message_text += f"   - ID: {user_id}\n"
        
        message_text += "\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_user_management")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    
    return LIST_USERS

def business_type_selection_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор типа бизнеса."""
    query = update.callback_query
    query.answer()
    
    if query.data == "add_business_type":
        query.edit_message_text("Введите название нового типа бизнеса:")
        return ADD_BUSINESS_TYPE  # Переходим в состояние ADD_BUSINESS_TYPE
    
    elif query.data == "back_to_user_management":
        return show_user_management(update, context)
    
    elif query.data.startswith("select_type:"):
        business_type = query.data.split(":", 1)[1]
        context.user_data["selected_business_type"] = business_type
        
        query.edit_message_text(f"Выбран тип бизнеса: {business_type}\nВведите Telegram ID нового пользователя:")
        return ADD_USER
    
    return SELECT_BUSINESS_TYPE

def add_business_type_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает добавление нового типа бизнеса."""
    business_type = update.message.text.strip()
    
    if add_business_type(business_type):
        context.user_data["selected_business_type"] = business_type
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить пользователя", callback_data="add_user_for_new_type")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_user_management")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            f"✅ Тип бизнеса '{business_type}' успешно добавлен со стандартными вопросами.",
            reply_markup=reply_markup
        )
        return SELECT_BUSINESS_TYPE  # Возвращаемся в SELECT_BUSINESS_TYPE
    else:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_user_management")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "❌ Не удалось добавить тип бизнеса. Пожалуйста, попробуйте еще раз.",
            reply_markup=reply_markup
        )
        return SELECT_BUSINESS_TYPE

def add_user_for_new_type_handler(update: Update, context: CallbackContext) -> int:
    """Переход к добавлению пользователя после создания нового типа бизнеса."""
    query = update.callback_query
    query.answer()
    
    business_type = context.user_data.get("selected_business_type")
    query.edit_message_text(f"Выбран тип бизнеса: {business_type}\nВведите Telegram ID нового пользователя:")
    
    return ADD_USER

def add_user_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает добавление нового пользователя."""
    try:
        telegram_id = int(update.message.text.strip())
        business_type = context.user_data.get("selected_business_type")
        
        if add_user(telegram_id, business_type):
            update.message.reply_text(f"✅ Пользователь с ID {telegram_id} успешно добавлен к типу бизнеса '{business_type}'.")
        else:
            update.message.reply_text("❌ Не удалось добавить пользователя. Пожалуйста, попробуйте еще раз.")
    
    except ValueError:
        update.message.reply_text("❌ Ошибка: Telegram ID должен быть числом. Пожалуйста, попробуйте еще раз.")
    
    # Возвращаемся к меню управления пользователями
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_user_management")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    return MANAGE_USERS

def remove_user_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает удаление пользователя."""
    try:
        telegram_id = int(update.message.text.strip())
        
        if remove_user(telegram_id):
            update.message.reply_text(f"✅ Пользователь с ID {telegram_id} успешно удален.")
        else:
            update.message.reply_text(f"❌ Пользователь с ID {telegram_id} не найден.")
    
    except ValueError:
        update.message.reply_text("❌ Ошибка: Telegram ID должен быть числом. Пожалуйста, попробуйте еще раз.")
    
    # Возвращаемся к меню управления пользователями
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_user_management")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    return MANAGE_USERS

def user_list_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор в списке пользователей."""
    query = update.callback_query
    query.answer()
    
    if query.data == "back_to_user_management":
        return show_user_management(update, context)
    
    return LIST_USERS

# --- Управление вопросами ---
def show_question_management(update: Update, context: CallbackContext) -> int:
    """Показывает меню управления вопросами."""
    business_types = get_business_types()
    
    if not business_types:
        keyboard = [
            [InlineKeyboardButton("➕ Добавить тип бизнеса", callback_data="add_business_type")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.callback_query.edit_message_text(
            "Нет доступных типов бизнеса. Сначала добавьте тип бизнеса:",
            reply_markup=reply_markup
        )
        return SELECT_BUSINESS_TYPE
    
    # Формируем клавиатуру с типами бизнеса
    keyboard = []
    for btype in business_types:
        keyboard.append([InlineKeyboardButton(btype, callback_data=f"question_type:{btype}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.callback_query.edit_message_text("Выберите тип бизнеса для управления вопросами:", reply_markup=reply_markup)
    
    return MANAGE_QUESTIONS

def question_management_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор в меню управления вопросами."""
    query = update.callback_query
    query.answer()
    
    if query.data == "back_to_main":
        return show_main_menu(update, context)
    
    elif query.data.startswith("question_type:"):
        business_type = query.data.split(":", 1)[1]
        context.user_data["selected_business_type"] = business_type
        
        return show_questions_for_type(update, context, business_type)
    
    return MANAGE_QUESTIONS

def show_questions_for_type(update: Update, context: CallbackContext, business_type) -> int:
    """Показывает список вопросов для указанного типа бизнеса."""
    questions = get_questions_for_business_type(business_type)
    
    message_text = f"❓ Вопросы для типа бизнеса '{business_type}':\n\n"
    
    if not questions:
        message_text += "Вопросы не найдены."
    else:
        for q_id, text, order in questions:
            message_text += f"{order+1}. {text} [ID: {q_id}]\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить вопрос", callback_data="add_question")],
        [InlineKeyboardButton("✏️ Редактировать вопрос", callback_data="edit_question")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_question_management")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    
    return MANAGE_QUESTIONS

def question_action_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает действия с вопросами."""
    query = update.callback_query
    query.answer()
    
    if query.data == "add_question":
        business_type = context.user_data.get("selected_business_type")
        questions = get_questions_for_business_type(business_type)
        next_order = len(questions)
        
        query.edit_message_text(f"Введите текст нового вопроса для типа бизнеса '{business_type}':")
        context.user_data["next_question_order"] = next_order
        
        return ADD_QUESTION_FOR_TYPE
    
    elif query.data == "edit_question":
        query.edit_message_text("Введите ID вопроса, который хотите отредактировать:")
        return EDIT_QUESTION
    
    elif query.data == "back_to_question_management":
        return show_question_management(update, context)
    
    return MANAGE_QUESTIONS

def add_question_for_type_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает добавление нового вопроса."""
    question_text = update.message.text.strip()
    business_type = context.user_data.get("selected_business_type")
    question_order = context.user_data.get("next_question_order", 0)
    
    if add_question(business_type, question_text, question_order):
        update.message.reply_text(f"✅ Вопрос успешно добавлен для типа бизнеса '{business_type}'.")
    else:
        update.message.reply_text("❌ Не удалось добавить вопрос. Пожалуйста, попробуйте еще раз.")
    
    # Возвращаемся к списку вопросов
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_question_type")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    return MANAGE_QUESTIONS

def edit_question_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает ввод ID вопроса для редактирования."""
    try:
        question_id = int(update.message.text.strip())
        context.user_data["edit_question_id"] = question_id
        
        update.message.reply_text("Введите новый текст вопроса:")
        return EDIT_QUESTION
    
    except ValueError:
        update.message.reply_text("❌ Ошибка: ID вопроса должен быть числом. Пожалуйста, попробуйте еще раз.")
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_question_type")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
        return MANAGE_QUESTIONS

def update_question_text_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает ввод нового текста вопроса."""
    question_id = context.user_data.get("edit_question_id")
    new_text = update.message.text.strip()
    
    if update_question(question_id, new_text):
        update.message.reply_text(f"✅ Текст вопроса с ID {question_id} успешно обновлен.")
    else:
        update.message.reply_text(f"❌ Не удалось обновить вопрос с ID {question_id}. Пожалуйста, проверьте ID и попробуйте еще раз.")
    
    # Возвращаемся к списку вопросов
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_question_type")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    return MANAGE_QUESTIONS

def back_to_question_type_handler(update: Update, context: CallbackContext) -> int:
    """Возвращается к списку вопросов для выбранного типа бизнеса."""
    query = update.callback_query
    query.answer()
    
    business_type = context.user_data.get("selected_business_type")
    return show_questions_for_type(update, context, business_type)

# --- Управление промптами ---
def show_prompt_management(update: Update, context: CallbackContext) -> int:
    """Показывает меню управления промптами."""
    business_types = get_business_types()
    
    if not business_types:
        keyboard = [
            [InlineKeyboardButton("➕ Добавить тип бизнеса", callback_data="add_business_type")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.callback_query.edit_message_text(
            "Нет доступных типов бизнеса. Сначала добавьте тип бизнеса:",
            reply_markup=reply_markup
        )
        return SELECT_BUSINESS_TYPE
    
    # Формируем клавиатуру с типами бизнеса
    keyboard = []
    for btype in business_types:
        keyboard.append([InlineKeyboardButton(btype, callback_data=f"prompt_type:{btype}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.callback_query.edit_message_text("Выберите тип бизнеса для управления промптом:", reply_markup=reply_markup)
    
    return MANAGE_PROMPTS

def prompt_management_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор в меню управления промптами."""
    query = update.callback_query
    query.answer()
    
    if query.data == "back_to_main":
        return show_main_menu(update, context)
    
    elif query.data.startswith("prompt_type:"):
        business_type = query.data.split(":", 1)[1]
        context.user_data["selected_business_type"] = business_type
        
        return show_prompt_for_type(update, context, business_type)
    
    return MANAGE_PROMPTS

def show_prompt_for_type(update: Update, context: CallbackContext, business_type) -> int:
    """Показывает промпт для указанного типа бизнеса."""
    prompt_text = get_prompt(business_type)
    
    message_text = f"📝 Промпт для типа бизнеса '{business_type}':\n\n{prompt_text}"
    
    keyboard = [
        [InlineKeyboardButton("✏️ Редактировать промпт", callback_data="edit_prompt")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_prompt_management")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    
    return MANAGE_PROMPTS

def prompt_action_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает действия с промптами."""
    query = update.callback_query
    query.answer()
    
    if query.data == "edit_prompt":
        business_type = context.user_data.get("selected_business_type")
        prompt_text = get_prompt(business_type)
        
        query.edit_message_text(
            f"Введите новый текст промпта для типа бизнеса '{business_type}':\n\n"
            f"Текущий промпт:\n{prompt_text}\n\n"
            f"Примечание: Используйте '{{}}' для вставки ответов пользователя."
        )
        
        return EDIT_PROMPT
    
    elif query.data == "back_to_prompt_management":
        return show_prompt_management(update, context)
    
    return MANAGE_PROMPTS

def edit_prompt_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает редактирование промпта."""
    new_prompt = update.message.text.strip()
    business_type = context.user_data.get("selected_business_type")
    
    if update_prompt(business_type, new_prompt):
        update.message.reply_text(f"✅ Промпт для типа бизнеса '{business_type}' успешно обновлен.")
    else:
        update.message.reply_text(f"❌ Не удалось обновить промпт. Пожалуйста, попробуйте еще раз.")
    
    # Возвращаемся к меню управления промптами
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_prompt_management")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    return MANAGE_PROMPTS

def back_to_prompt_management_handler(update: Update, context: CallbackContext) -> int:
    """Возвращается к списку типов бизнеса для управления промптами."""
    query = update.callback_query
    query.answer()
    
    return show_prompt_management(update, context)

def cancel(update: Update, context: CallbackContext) -> int:
    """Отменяет текущую операцию и завершает диалог."""
    update.message.reply_text("Операция отменена. Диалог завершен.")
    return ConversationHandler.END

def main():
    """Основная функция для запуска бота."""
    updater = Updater(ADMIN_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Создаем хендлер для диалога
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_handler, pattern="^(manage_users|manage_questions|manage_prompts|exit)$")
            ],
            MANAGE_USERS: [
                CallbackQueryHandler(user_management_handler, pattern="^(add_user|remove_user|list_users|back_to_main)$"),
                CallbackQueryHandler(user_list_handler, pattern="^back_to_user_management$")
            ],
            SELECT_BUSINESS_TYPE: [
                CallbackQueryHandler(business_type_selection_handler, pattern="^(add_business_type|back_to_user_management|select_type:.+)$"),
                CallbackQueryHandler(add_user_for_new_type_handler, pattern="^add_user_for_new_type$"),
                MessageHandler(Filters.text & ~Filters.command, add_business_type_handler)
            ],
            ADD_BUSINESS_TYPE: [
                MessageHandler(Filters.text & ~Filters.command, add_business_type_handler)
            ],
            ADD_USER: [
                MessageHandler(Filters.text & ~Filters.command, add_user_handler)
            ],
            REMOVE_USER: [
                MessageHandler(Filters.text & ~Filters.command, remove_user_handler)
            ],
            LIST_USERS: [
                CallbackQueryHandler(user_list_handler, pattern="^back_to_user_management$")
            ],
            MANAGE_QUESTIONS: [
                CallbackQueryHandler(question_management_handler, pattern="^(back_to_main|question_type:.+)$"),
                CallbackQueryHandler(question_action_handler, pattern="^(add_question|edit_question|back_to_question_management)$"),
                CallbackQueryHandler(back_to_question_type_handler, pattern="^back_to_question_type$")
            ],
            ADD_QUESTION_FOR_TYPE: [
                MessageHandler(Filters.text & ~Filters.command, add_question_for_type_handler)
            ],
            EDIT_QUESTION: [
                MessageHandler(Filters.text & ~Filters.command, update_question_text_handler)
            ],
            MANAGE_PROMPTS: [
                CallbackQueryHandler(prompt_management_handler, pattern="^(back_to_main|prompt_type:.+)$"),
                CallbackQueryHandler(prompt_action_handler, pattern="^(edit_prompt|back_to_prompt_management)$"),
                CallbackQueryHandler(back_to_prompt_management_handler, pattern="^back_to_prompt_management$")
            ],
            EDIT_PROMPT: [
                MessageHandler(Filters.text & ~Filters.command, edit_prompt_handler)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    dp.add_handler(conv_handler)
    
    # Запускаем бота
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
