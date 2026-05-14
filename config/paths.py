# config/paths.py
import os
from pathlib import Path

# Корневая директория проекта
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# Базовые директории
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
FEATURES_DIR = DATA_DIR / "features"
ML_DATASET_DIR = DATA_DIR / "ml_dataset"
DEBUG_DIR = DATA_DIR / "debug"  # <-- ДОБАВЛЯЕМ ЭТУ СТРОКУ

# Сырые данные
LENTA_ARCHIVE_DIR = RAW_DATA_DIR / "lenta_archive"
MOEX_RAW_DIR = RAW_DATA_DIR / "moex"

# Обработанные данные
MARKET_ARTICLES_DIR = PROCESSED_DATA_DIR / "market_articles"
FULL_TEXTS_DIR = PROCESSED_DATA_DIR / "full_texts"
SENTIMENT_DIR = PROCESSED_DATA_DIR / "sentiment"

# Признаки
LENTA_FEATURES_FILE = FEATURES_DIR / "lenta_daily_features.csv"
MOEX_FEATURES_FILE = FEATURES_DIR / "moex_daily_features.csv"

# Финальный датасет
ML_DATASET_FILE = ML_DATASET_DIR / "final_ml_dataset.csv"

# Создаём все директории при импорте
for dir_path in [DATA_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR, FEATURES_DIR,
                 ML_DATASET_DIR, DEBUG_DIR, LENTA_ARCHIVE_DIR, MOEX_RAW_DIR,
                 MARKET_ARTICLES_DIR, FULL_TEXTS_DIR, SENTIMENT_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)


# Функция для тестирования (оставляем как есть)
def test_paths():
    """Функция для тестирования создания путей"""
    print("🔧 Тестирование конфигурации путей...")

    print(f"📁 Корень проекта: {PROJECT_ROOT}")
    print(f"\n📂 Базовые директории:")
    print(f"   data/: {DATA_DIR}")
    print(f"   raw/: {RAW_DATA_DIR}")
    print(f"   processed/: {PROCESSED_DATA_DIR}")
    print(f"   features/: {FEATURES_DIR}")
    print(f"   ml_dataset/: {ML_DATASET_DIR}")
    print(f"   debug/: {DEBUG_DIR}")  # <-- ДОБАВИЛИ В ВЫВОД

    print(f"\n📂 Сырые данные:")
    print(f"   lenta_archive/: {LENTA_ARCHIVE_DIR}")
    print(f"   moex/: {MOEX_RAW_DIR}")  # <-- ТЕПЕРЬ ДОЛЖНО РАБОТАТЬ

    print(f"\n📂 Обработанные данные:")
    print(f"   market_articles/: {MARKET_ARTICLES_DIR}")
    print(f"   full_texts/: {FULL_TEXTS_DIR}")
    print(f"   sentiment/: {SENTIMENT_DIR}")

    print(f"\n📂 Файлы с признаками:")
    print(f"   lenta_features: {LENTA_FEATURES_FILE}")
    print(f"   moex_features: {MOEX_FEATURES_FILE}")

    print(f"\n📂 Финальный датасет:")
    print(f"   {ML_DATASET_FILE}")

    print(f"\n🔨 Директории уже созданы при импорте")

    # Проверка записи
    test_file = DATA_DIR / "test_write.txt"
    try:
        test_file.write_text("Тест записи")
        print(f"✅ Запись работает: {test_file}")
        test_file.unlink()
    except Exception as e:
        print(f"❌ Проблема с записью: {e}")

    print(f"\n✨ Тест завершён!")

    # Возвращаем словарь со всеми путями
    return {
        'PROJECT_ROOT': PROJECT_ROOT,
        'MOEX_RAW_DIR': MOEX_RAW_DIR,
        # ... остальные пути
    }


if __name__ == "__main__":
    test_paths()