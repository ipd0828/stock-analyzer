# scripts/bd/config.py
"""
Конфигурация для работы с API FinanceMarker и PostgreSQL
"""

import os
from pathlib import Path

# -------------------- API Configuration --------------------
API_TOKEN = "gnrbj8wtusgw9uxie0o8w"
BASE_URL = "https://financemarker.ru/api/fm/v2"

# -------------------- Database Configuration --------------------
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "investment_db",
    "user": "investor_nick",
    "password": "1q2A3z4X!@#"  # Замените на ваш пароль
}

# -------------------- Paths --------------------
# Определяем корень проекта
PROJECT_ROOT = Path(__file__).parent.parent.parent
# ВАЖНО: файлы лежат в scripts/data/bd/raw/companies_data/
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
BD_DATA_DIR = SCRIPTS_DIR / "data" / "bd" / "raw"
BD_COMPANIES_DIR = BD_DATA_DIR / "companies_data"
BD_COMPANIES_DIR.mkdir(parents=True, exist_ok=True)


# -------------------- Request Settings --------------------
REQUEST_DELAY = 0.5
MAX_RETRIES = 3

# Для отладки - показываем пути
print(f"🔧 BD_COMPANIES_DIR = {BD_COMPANIES_DIR}")
print(f"🔧 Существует: {BD_COMPANIES_DIR.exists()}")