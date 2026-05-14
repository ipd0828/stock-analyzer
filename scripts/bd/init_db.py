#!/usr/bin/env python3
# scripts/bd/init_db.py
"""
Инициализация базы данных: создание таблиц
"""

import psycopg2
from pathlib import Path
from config import DB_CONFIG


def init_database():
    """Создает таблицы в базе данных"""

    # Читаем SQL схему
    schema_path = Path(__file__).parent / "db_schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    try:
        # Подключаемся к БД
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cur = conn.cursor()

        print("🚀 Инициализация базы данных...")
        print(f"📁 Подключение к {DB_CONFIG['database']}")

        # Выполняем схему
        cur.execute(schema_sql)

        print("✅ Таблицы успешно созданы!")

        # Показываем список таблиц
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)

        tables = cur.fetchall()
        print("\n📊 Созданные таблицы:")
        for table in tables:
            print(f"   • {table[0]}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

    return True


if __name__ == "__main__":
    init_database()