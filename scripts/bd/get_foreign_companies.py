#!/usr/bin/env python3
# scripts/bd/get_foreign_companies.py
"""
Получение списка иностранных компаний из уже загруженного all_companies.csv
"""

import pandas as pd
from pathlib import Path
from config import BD_DATA_DIR  # Исправлено: BD_DATA_DIR, а не BD_RAW_DIR

# Файлы
ALL_COMPANIES_PATH = BD_DATA_DIR / "all_companies.csv"
FOREIGN_COMPANIES_PATH = BD_DATA_DIR / "foreign_companies.csv"


def main():
    print("=" * 70)
    print("🌍 ПОЛУЧЕНИЕ СПИСКА ИНОСТРАННЫХ КОМПАНИЙ")
    print("=" * 70)

    # Проверяем, существует ли файл all_companies.csv
    if not ALL_COMPANIES_PATH.exists():
        print(f"❌ Файл {ALL_COMPANIES_PATH} не найден!")
        print("   Сначала запустите get_companies_list.py для получения списка всех компаний")
        return

    # Загружаем полный список
    df = pd.read_csv(ALL_COMPANIES_PATH)
    print(f"📁 Загружен файл: {ALL_COMPANIES_PATH}")
    print(f"   Всего компаний: {len(df)}")

    # Фильтруем иностранные (не российские)
    foreign_df = df[df["is_russian"] == False].copy()

    # Сохраняем
    FOREIGN_COMPANIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    foreign_df.to_csv(FOREIGN_COMPANIES_PATH, index=False, encoding="utf-8")

    print(f"\n✅ Сохранено: {FOREIGN_COMPANIES_PATH}")
    print(f"   Количество иностранных компаний: {len(foreign_df)}")

    # Показываем статистику по биржам
    print(f"\n📊 РАСПРЕДЕЛЕНИЕ ПО БИРЖАМ:")
    exchange_counts = foreign_df["exchange"].value_counts()
    for exchange, count in exchange_counts.head(15).items():
        print(f"   {exchange}: {count} компаний")

    # Показываем примеры
    print(f"\n📋 ПРИМЕРЫ (первые 15):")
    for _, row in foreign_df.head(15).iterrows():
        name = row.get("name", row["code"])
        if len(name) > 50:
            name = name[:47] + "..."
        print(f"   {row['exchange']}:{row['code']} - {name}")

    # Проверяем, есть ли российские в файле (должно быть 0)
    russian_check = foreign_df[foreign_df["is_russian"] == True]
    if len(russian_check) > 0:
        print(f"\n⚠️ ВНИМАНИЕ: Найдено {len(russian_check)} российских компаний в файле!")
        print("   Проверьте фильтрацию.")


if __name__ == "__main__":
    main()