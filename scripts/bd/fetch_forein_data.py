#!/usr/bin/env python3
# scripts/bd/fetch_foreign_data.py
"""
Загрузка фундаментальных данных для ИНОСТРАННЫХ компаний
"""

import time
import json
import requests
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
from config import API_TOKEN, BASE_URL, REQUEST_DELAY, BD_DATA_DIR

# Директории
BD_RAW_DIR = BD_DATA_DIR
BD_COMPANIES_DIR = BD_RAW_DIR / "companies_data"
BD_COMPANIES_DIR.mkdir(parents=True, exist_ok=True)

# Файлы
FOREIGN_COMPANIES_FILE = BD_RAW_DIR / "foreign_companies.csv"
PROGRESS_FILE = BD_RAW_DIR / "fetch_foreign_progress.json"

# Разделы для загрузки (базовые)
SECTIONS = ["reports", "ratios", "dividends", "shares", "info"]


def load_progress() -> Dict:
    """Загружает прогресс загрузки иностранных компаний"""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {
        "completed": [],
        "failed": [],
        "last_index": 0,
        "total_requests": 0,
        "sections_used": SECTIONS
    }


def save_progress(progress: Dict):
    """Сохраняет прогресс"""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def fetch_company_data(code: str, exchange: str, progress: Dict) -> Optional[Dict]:
    """Загружает данные по иностранной компании"""
    include_str = ",".join(SECTIONS)
    url = f"{BASE_URL}/stocks/{exchange}:{code}"
    params = {
        "api_token": API_TOKEN,
        "include": include_str
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        progress["total_requests"] += 1

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            error_data = response.json()
            if error_data.get("message") == "out_of_limit":
                print("\n❌ Превышен лимит запросов! Остановка...")
                return "LIMIT_EXCEEDED"
            return None
        else:
            print(f"⚠️ Ошибка {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None


def save_company_data(data: Dict, code: str, exchange: str):
    """Сохраняет данные компании"""
    data["_metadata"] = {
        "fetched_at": datetime.now().isoformat(),
        "sections": SECTIONS,
        "source": "FinanceMarker API",
        "type": "foreign"
    }

    filepath = BD_COMPANIES_DIR / f"{exchange}_{code}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


def main():
    print("=" * 70)
    print("🌍 ЗАГРУЗКА ФУНДАМЕНТАЛЬНЫХ ДАННЫХ - ИНОСТРАННЫЕ КОМПАНИИ")
    print("=" * 70)

    # Проверяем наличие файла со списком иностранных компаний
    if not FOREIGN_COMPANIES_FILE.exists():
        print(f"\n❌ Файл {FOREIGN_COMPANIES_FILE} не найден!")
        print("   Сначала запустите get_foreign_companies.py для создания списка")
        return

    companies_df = pd.read_csv(FOREIGN_COMPANIES_FILE)
    print(f"\n🌍 Найдено {len(companies_df)} иностранных компаний")

    # Показываем примеры
    print(f"\n📋 Примеры компаний (первые 10):")
    for _, row in companies_df.head(10).iterrows():
        name = row.get("name", row["code"])
        if len(name) > 50:
            name = name[:47] + "..."
        print(f"   {row['exchange']}:{row['code']} - {name}")

    # Выбор режима
    print("\n" + "=" * 50)
    print("ВЫБЕРИТЕ РЕЖИМ ЗАГРУЗКИ:")
    print("=" * 50)
    print("1. 🧪 ТЕСТОВЫЙ режим (первые 5 компаний)")
    print("2. 🚀 ПОЛНАЯ загрузка (все иностранные компании)")
    print("3. ⏭️ Продолжить предыдущую загрузку")

    choice = input("\nВыберите действие (1-3): ").strip()

    progress = load_progress()
    total = len(companies_df)
    completed_set = set(progress["completed"])
    failed_set = set(progress["failed"])

    if choice == "1":
        # Тестовый режим
        limit = 5
        print(f"\n🧪 ТЕСТОВЫЙ РЕЖИМ: загрузка первых {limit} компаний")
        print("-" * 50)

        for idx, (_, row) in enumerate(companies_df.head(limit).iterrows(), 1):
            code = row["code"]
            exchange = row["exchange"]
            key = f"{exchange}_{code}"

            print(f"[{idx}/{limit}] 📥 {exchange}:{code}...", end=" ", flush=True)

            data = fetch_company_data(code, exchange, progress)

            if data and data != "LIMIT_EXCEEDED":
                save_company_data(data, code, exchange)
                reports = len(data.get("reports", []))
                ratios = len(data.get("ratios", []))
                print(f"✅ (отч:{reports}, коэф:{ratios})")
            else:
                print(f"❌ Ошибка")

            time.sleep(REQUEST_DELAY)

    elif choice == "2":
        # Полная загрузка
        print(f"\n🚀 ПОЛНАЯ ЗАГРУЗКА {total} ИНОСТРАННЫХ КОМПАНИЙ")
        print(f"📦 Разделы: {', '.join(SECTIONS)}")
        print(f"⚠️ ВНИМАНИЕ: Это может занять много времени и запросов!")

        confirm = input("\nПродолжить? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Отменено")
            return

        start_index = progress["last_index"]

        print(f"\n📍 Начинаем с компании #{start_index + 1}")
        print("-" * 50)

        for idx, (_, row) in enumerate(companies_df.iterrows()):
            if idx < start_index:
                continue

            code = row["code"]
            exchange = row["exchange"]
            key = f"{exchange}_{code}"

            if key in completed_set:
                print(f"[{idx + 1}/{total}] ⏭️ Пропускаем {exchange}:{code} (уже есть)")
                continue

            print(f"[{idx + 1}/{total}] 📥 {exchange}:{code}...", end=" ", flush=True)

            data = fetch_company_data(code, exchange, progress)

            if data == "LIMIT_EXCEEDED":
                print("\n⏹️ Остановка из-за превышения лимита")
                break
            elif data:
                save_company_data(data, code, exchange)
                reports = len(data.get("reports", []))
                ratios = len(data.get("ratios", []))
                print(f"✅ (отч:{reports}, коэф:{ratios})")
                completed_set.add(key)
                progress["completed"] = list(completed_set)
            else:
                print(f"❌ Ошибка")
                failed_set.add(key)
                progress["failed"] = list(failed_set)

            progress["last_index"] = idx + 1
            progress["total_requests"] = progress.get("total_requests", 0)
            save_progress(progress)
            time.sleep(REQUEST_DELAY)

        print(f"\n✅ ЗАГРУЗКА ЗАВЕРШЕНА!")
        print(f"   ✅ Успешно: {len(completed_set)}")
        print(f"   ❌ Ошибок: {len(failed_set)}")

    elif choice == "3":
        # Продолжить загрузку
        print(f"\n⏭️ ПРОДОЛЖЕНИЕ ЗАГРУЗКИ")
        print(f"   Загружено: {len(completed_set)} компаний")
        print(f"   Ошибок: {len(failed_set)}")

        start_index = progress["last_index"]

        print(f"\n📍 Продолжаем с компании #{start_index + 1}")
        print("-" * 50)

        for idx, (_, row) in enumerate(companies_df.iterrows()):
            if idx < start_index:
                continue

            code = row["code"]
            exchange = row["exchange"]
            key = f"{exchange}_{code}"

            if key in completed_set:
                continue

            print(f"[{idx + 1}/{total}] 📥 {exchange}:{code}...", end=" ", flush=True)

            data = fetch_company_data(code, exchange, progress)

            if data == "LIMIT_EXCEEDED":
                print("\n⏹️ Остановка из-за превышения лимита")
                break
            elif data:
                save_company_data(data, code, exchange)
                reports = len(data.get("reports", []))
                ratios = len(data.get("ratios", []))
                print(f"✅ (отч:{reports}, коэф:{ratios})")
                completed_set.add(key)
                progress["completed"] = list(completed_set)
                if key in failed_set:
                    failed_set.discard(key)
                    progress["failed"] = list(failed_set)
            else:
                print(f"❌ Ошибка")
                failed_set.add(key)
                progress["failed"] = list(failed_set)

            progress["last_index"] = idx + 1
            save_progress(progress)
            time.sleep(REQUEST_DELAY)

        print(f"\n✅ ЗАГРУЗКА ЗАВЕРШЕНА!")
        print(f"   ✅ Успешно: {len(completed_set)}")
        print(f"   ❌ Ошибок: {len(failed_set)}")

    else:
        print("❌ Неверный выбор")


if __name__ == "__main__":
    main()