import psycopg2
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    """Возвращает соединение с базой данных."""
    return psycopg2.connect(DATABASE_URL)

# Параметры подключения к базе данных из переменных окружения
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

def get_connection():
    """Возвращает соединение с базой данных."""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def create_tables():
    """Создает таблицы в базе данных, если они не существуют."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Создаем таблицу пользователей
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE,
        business_type TEXT NOT NULL
    )
    """)
    
    # Создаем таблицу вопросов
    cur.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id SERIAL PRIMARY KEY,
        business_type TEXT NOT NULL,
        question_text TEXT NOT NULL,
        question_order INT NOT NULL
    )
    """)
    
    # Создаем таблицу для хранения промптов для разных бизнес-типов
    cur.execute("""
    CREATE TABLE IF NOT EXISTS prompts (
        id SERIAL PRIMARY KEY,
        business_type TEXT UNIQUE NOT NULL,
        prompt_text TEXT NOT NULL
    )
    """)
    
    conn.commit()
    cur.close()
    conn.close()

def check_user(telegram_id):
    """
    Проверяет, есть ли пользователь в базе данных.
    Возвращает business_type если пользователь найден, иначе None.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT business_type FROM users WHERE telegram_id = %s", (telegram_id,))
    result = cur.fetchone()
    
    cur.close()
    conn.close()
    
    return result[0] if result else None

def get_questions(business_type):
    """
    Возвращает список вопросов для указанного типа бизнеса.
    Вопросы сортируются по question_order.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
    SELECT question_text FROM questions 
    WHERE business_type = %s 
    ORDER BY question_order
    """, (business_type,))
    
    questions = [row[0] for row in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    return questions

def get_prompt(business_type):
    """
    Возвращает промпт для указанного типа бизнеса.
    Если промпт не найден, возвращает стандартный промпт.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT prompt_text FROM prompts WHERE business_type = %s", (business_type,))
    result = cur.fetchone()
    
    cur.close()
    conn.close()
    
    if result:
        return result[0]
    else:
        return "На основе следующих ответов составь отзыв для клиники:\n\n{}\n\nСоставь связный, теплый отзыв, будто писал пациент, который только что здесь был вылечен."
