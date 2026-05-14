#!/usr/bin/env python3
# scripts/update_lenta_headers.py
"""
Досбор заголовков Lenta.ru с последней собранной даты по сегодня.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.append(str(Path(__file__).parent.parent))

# Прямой путь к архиву
LENTA_ARCHIVE_DIR = Path("data/lenta_archive")


def get_last_collected_date() -> datetime:
    """Находит последнюю собранную дату"""
    files = sorted(LENTA_ARCHIVE_DIR.glob("*.json"))
    if not files:
        print("❌ Нет файлов в архиве.")
        return None

    last_file = files[-1]
    date_str = last_file.stem  # формат: 2026-03-18
    last_date = datetime.strptime(date_str, '%Y-%m-%d')
    print(f"📅 Последняя собранная дата: {last_date.date()}")
    print(f"   Файл: {last_file.name}")
    return last_date


def main():
    last_date = get_last_collected_date()
    if last_date is None:
        # Укажи дату вручную если нет файлов
        start_date = datetime(2020, 1, 1)
        print(f"   Начинаем с {start_date.date()}")
    else:
        start_date = last_date + timedelta(days=1)

    end_date = datetime.now()
    days = (end_date - start_date).days

    print(f"\n📊 Дней для досбора: {days}")
    print(f"   Период: {start_date.date()} - {end_date.date()}")

    if days <= 0:
        print("✅ Архив актуален!")
        return

    # Запускаем сборщик
    from src.data_collection.collect_lenta_headers import HeaderCollector
    collector = HeaderCollector()
    stats = collector.collect_period(start_date, end_date)

    print(f"\n✅ Досбор завершён!")
    if stats:
        print(f"   Успешно: {stats['success']} дней")
        print(f"   Ошибок: {stats['errors']}")


if __name__ == "__main__":
    main()