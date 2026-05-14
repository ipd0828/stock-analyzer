# config/settings.py
from datetime import datetime
from pathlib import Path
import sys

# Добавляем корень проекта для импорта paths
sys.path.append(str(Path(__file__).parent.parent))
from config import PROJECT_ROOT, DATA_DIR

# ========== ПЕРИОД СБОРА ==========
START_DATE = datetime(2020, 1, 1)
END_DATE = datetime.now()

# ========== НАСТРОЙКИ ЗАДЕРЖЕК ==========
REQUEST_DELAY = 1  # Задержка между запросами в секундах
SELENIUM_TIMEOUT = 30  # Таймаут для Selenium
MAX_RETRIES = 3  # Количество попыток при ошибках

# ========== НАСТРОЙКИ БРАУЗЕРА ==========
CHROME_OPTIONS = {
    "headless": True,
    "no_sandbox": True,
    "disable_dev_shm_usage": True,
    "disable_gpu": True,
    "window_size": "1920,1080"
}

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ========== НАСТРОЙКИ МОДЕЛЕЙ ==========
SENTIMENT_MODEL = "blanchefort/rubert-base-cased-sentiment"
BATCH_SIZE = 32  # Для обработки пачками
MAX_TEXT_LENGTH = 512  # Максимальная длина текста для модели

# ========== НАСТРОЙКИ ЛОГИРОВАНИЯ ==========
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
SAVE_DEBUG_LOGS = True  # Сохранять ли отладочные логи

# ========== ФЛАГИ ДЛЯ ОТЛАДКИ ==========
DEBUG_MODE = False  # Включать ли подробный вывод
TEST_MODE = False  # Режим тестирования (обрабатывать только несколько дней)
TEST_DAYS = 5  # Количество дней для тестового режима


def test_settings():
    """Тестирование настроек"""
    print("🔧 Тестирование конфигурации настроек...")

    print(f"\n📅 Период сбора данных:")
    print(f"   Начало: {START_DATE.strftime('%Y-%m-%d')}")
    print(f"   Конец: {END_DATE.strftime('%Y-%m-%d')}")
    print(f"   Всего дней: {(END_DATE - START_DATE).days}")

    print(f"\n⏱️ Настройки таймингов:")
    print(f"   REQUEST_DELAY: {REQUEST_DELAY} сек")
    print(f"   SELENIUM_TIMEOUT: {SELENIUM_TIMEOUT} сек")
    print(f"   MAX_RETRIES: {MAX_RETRIES}")

    print(f"\n🌐 Настройки браузера:")
    print(f"   Headless: {CHROME_OPTIONS['headless']}")
    print(f"   Window size: {CHROME_OPTIONS['window_size']}")

    print(f"\n🤖 Настройки ML моделей:")
    print(f"   SENTIMENT_MODEL: {SENTIMENT_MODEL}")

    print(f"\n📝 Настройки логирования:")
    print(f"   LOG_LEVEL: {LOG_LEVEL}")

    print(f"\n🐛 Режимы отладки:")
    print(f"   DEBUG_MODE: {DEBUG_MODE}")
    print(f"   TEST_MODE: {TEST_MODE}")

    print(f"\n🔍 Проверка доступности paths.py...")
    try:
        from config import DATA_DIR
        print(f"   ✅ paths.py импортирован, DATA_DIR = {DATA_DIR}")
    except ImportError as e:
        print(f"   ❌ Ошибка импорта paths.py: {e}")

    print(f"\n" + "=" * 50)
    print("✅ Тестирование настроек завершено!")
    print("=" * 50)

    return {
        'START_DATE': START_DATE,
        'END_DATE': END_DATE,
        'REQUEST_DELAY': REQUEST_DELAY,
        'SELENIUM_TIMEOUT': SELENIUM_TIMEOUT,
        'MAX_RETRIES': MAX_RETRIES,
        'CHROME_OPTIONS': CHROME_OPTIONS,
        'USER_AGENT': USER_AGENT,
        'SENTIMENT_MODEL': SENTIMENT_MODEL,
        'BATCH_SIZE': BATCH_SIZE,
        'MAX_TEXT_LENGTH': MAX_TEXT_LENGTH,
        'LOG_LEVEL': LOG_LEVEL,
        'SAVE_DEBUG_LOGS': SAVE_DEBUG_LOGS,
        'DEBUG_MODE': DEBUG_MODE,
        'TEST_MODE': TEST_MODE,
        'TEST_DAYS': TEST_DAYS
    }


if __name__ == "__main__":
    settings = test_settings()

    # Проверяем импорт
    print(f"\n📦 Проверка импорта:")
    try:
        from config import REQUEST_DELAY, START_DATE, END_DATE

        print(f"   ✅ Переменные успешно импортируются")
        print(f"   REQUEST_DELAY = {REQUEST_DELAY}")
        print(f"   START_DATE = {START_DATE.strftime('%Y-%m-%d')}")
    except ImportError as e:
        print(f"   ❌ Ошибка импорта: {e}")