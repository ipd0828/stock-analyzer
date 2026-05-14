#!/usr/bin/env python3
# scripts/bd/fetch_company_data.py
"""
Загрузка фундаментальных данных для российских компаний
Включает: reports, ratios, dividends, calendar, disclosure, summary, shares, info
"""

import time
import json
import requests
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
from config import API_TOKEN, BASE_URL, REQUEST_DELAY, DATA_DIR

# Директории
BD_DATA_DIR = DATA_DIR / "bd"
BD_RAW_DIR = BD_DATA_DIR / "raw"
BD_COMPANIES_DIR = BD_RAW_DIR / "companies_data"
BD_COMPANIES_DIR.mkdir(parents=True, exist_ok=True)

# Файлы
RUSSIAN_COMPANIES_FILE = BD_RAW_DIR / "russian_companies.csv"
PROGRESS_FILE = BD_RAW_DIR / "fetch_progress.json"

# Доступные разделы API
AVAILABLE_SECTIONS = [
    "reports",
    "ratios",
    "dividends",
    "calendar",
    "disclosure",
    "summary",
    "shares",
    "info",
    "operations"
]

# Базовый набор
BASE_SECTIONS = ["reports", "ratios", "dividends", "calendar", "disclosure", "shares"]


def load_progress() -> Dict:
    """Загружает прогресс загрузки"""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {
        "completed": [],
        "failed": [],
        "last_index": 0,
        "total_requests": 0,
        "sections_used": BASE_SECTIONS
    }


def save_progress(progress: Dict):
    """Сохраняет прогресс"""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def fetch_company_data(code: str, exchange: str, sections: List[str], progress: Dict) -> Optional[Dict]:
    """Загружает данные по компании с указанными разделами"""
    include_str = ",".join(sections)
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
                print("❌ Превышен лимит запросов!")
            return None
        else:
            print(f"⚠️ Ошибка {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None


def save_company_data(data: Dict, code: str, exchange: str, sections: List[str]):
    """Сохраняет данные компании с указанием загруженных разделов"""
    data["_metadata"] = {
        "fetched_at": datetime.now().isoformat(),
        "sections": sections,
        "source": "FinanceMarker API"
    }

    filepath = BD_COMPANIES_DIR / f"{exchange}_{code}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


def print_company_summary(data: Dict, code: str, exchange: str):
    """Выводит краткую сводку по загруженной компании"""
    info = data.get("info", {})
    name = info.get("name", code)

    reports_count = len(data.get("reports", []))
    ratios_count = len(data.get("ratios", []))
    dividends_count = len(data.get("dividends", []))

    print(f"📊 {exchange}:{code} - {name[:40]}")
    print(f"   📄 Отчетов: {reports_count}, 📈 Коэф: {ratios_count}, 💰 Див: {dividends_count}")


def test_mode(companies_df: pd.DataFrame, sections: List[str], limit: int = 5):
    """Тестовый режим: загружает первые N компаний для проверки"""
    print(f"\n🧪 ТЕСТОВЫЙ РЕЖИМ: загрузка первых {limit} компаний")
    print(f"📦 Разделы: {', '.join(sections)}")
    print("-" * 50)

    results = []
    for idx, (_, row) in enumerate(companies_df.head(limit).iterrows()):
        code = row["code"]
        exchange = row["exchange"]

        print(f"\n[{idx + 1}/{limit}] 📥 Загрузка {exchange}:{code}...")

        data = fetch_company_data(code, exchange, sections, {"total_requests": 0})

        if data:
            filepath = save_company_data(data, code, exchange, sections)
            print_company_summary(data, code, exchange)
            print(f"   💾 Сохранено: {filepath.name}")
            results.append({"code": code, "exchange": exchange, "status": "success"})
        else:
            print(f"   ❌ Ошибка загрузки")
            results.append({"code": code, "exchange": exchange, "status": "failed"})

        time.sleep(REQUEST_DELAY)

    return results


def continue_loading(companies_df: pd.DataFrame, progress: Dict, sections: List[str]):
    """Продолжает загрузку: сначала недогруженные, потом ошибки"""
    total = len(companies_df)
    completed_set = set(progress["completed"])
    failed_set = set(progress["failed"])

    # Сначала загружаем ошибочные компании
    retry_list = []
    for idx, (_, row) in enumerate(companies_df.iterrows()):
        code = row["code"]
        exchange = row["exchange"]
        key = f"{exchange}_{code}"
        if key in failed_set:
            retry_list.append((idx, row))

    if retry_list:
        print(f"\n🔄 Найдено {len(retry_list)} компаний с ошибками для повторной загрузки")
        print("-" * 50)

        for retry_idx, (orig_idx, row) in enumerate(retry_list, 1):
            code = row["code"]
            exchange = row["exchange"]
            key = f"{exchange}_{code}"

            print(f"[{retry_idx}/{len(retry_list)}] 📥 ПОВТОР: {exchange}:{code}...", end=" ", flush=True)

            data = fetch_company_data(code, exchange, sections, progress)

            if data:
                save_company_data(data, code, exchange, sections)
                reports = len(data.get("reports", []))
                ratios = len(data.get("ratios", []))
                print(f"✅ (отч:{reports}, коэф:{ratios})")
                completed_set.add(key)
                failed_set.discard(key)
            else:
                print(f"❌ Снова ошибка")

            progress["completed"] = list(completed_set)
            progress["failed"] = list(failed_set)
            progress["last_index"] = orig_idx + 1
            save_progress(progress)
            time.sleep(REQUEST_DELAY)

    # Затем проверяем, нет ли компаний, которые не загружены (пропуски)
    all_company_keys = set()
    for _, row in companies_df.iterrows():
        all_company_keys.add(f"{row['exchange']}_{row['code']}")

    missing_keys = all_company_keys - completed_set - failed_set

    if missing_keys:
        print(f"\n⚠️ Найдено {len(missing_keys)} пропущенных компаний")
        for idx, (_, row) in enumerate(companies_df.iterrows()):
            key = f"{row['exchange']}_{row['code']}"
            if key in missing_keys:
                print(f"   📥 {row['exchange']}:{row['code']}...", end=" ", flush=True)

                data = fetch_company_data(row["code"], row["exchange"], sections, progress)

                if data:
                    save_company_data(data, row["code"], row["exchange"], sections)
                    reports = len(data.get("reports", []))
                    ratios = len(data.get("ratios", []))
                    print(f"✅ (отч:{reports}, коэф:{ratios})")
                    completed_set.add(key)
                else:
                    print(f"❌ Ошибка")
                    failed_set.add(key)

                progress["completed"] = list(completed_set)
                progress["failed"] = list(failed_set)
                save_progress(progress)
                time.sleep(REQUEST_DELAY)

    print(f"\n✅ ЗАГРУЗКА ЗАВЕРШЕНА!")
    print(f"   Успешно: {len(completed_set)}")
    print(f"   Ошибок: {len(failed_set)}")


def full_load(companies_df: pd.DataFrame, sections: List[str], load_name: str):
    """Полная загрузка всех компаний"""
    print(f"\n🚀 {load_name}")
    print(f"📦 Разделы: {', '.join(sections)}")
    print(f"📊 Компаний: {len(companies_df)}")

    confirm = input("\nПродолжить? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Отменено")
        return

    progress = load_progress()
    total = len(companies_df)
    start_index = progress["last_index"]
    completed_set = set(progress["completed"])

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

        data = fetch_company_data(code, exchange, sections, progress)

        if data:
            save_company_data(data, code, exchange, sections)
            reports = len(data.get("reports", []))
            ratios = len(data.get("ratios", []))
            print(f"✅ (отч:{reports}, коэф:{ratios})")
            completed_set.add(key)
            progress["completed"] = list(completed_set)
        else:
            print(f"❌ Ошибка")
            progress["failed"].append(key)

        progress["last_index"] = idx + 1
        progress["sections_used"] = sections
        save_progress(progress)
        time.sleep(REQUEST_DELAY)

    print(f"\n✅ ЗАГРУЗКА ЗАВЕРШЕНА!")
    print(f"   Успешно: {len(completed_set)}")
    print(f"   Ошибок: {len(progress['failed'])}")


def main():
    print("=" * 70)
    print("📥 ЗАГРУЗКА ФУНДАМЕНТАЛЬНЫХ ДАННЫХ")
    print("=" * 70)

    # Загружаем список российских компаний
    if not RUSSIAN_COMPANIES_FILE.exists():
        print("❌ Файл с российскими компаниями не найден!")
        print("   Сначала запустите get_companies_list.py")
        return

    companies_df = pd.read_csv(RUSSIAN_COMPANIES_FILE)
    print(f"\n🇷🇺 Загружено {len(companies_df)} российских компаний")

    # Выбор режима
    print("\n" + "=" * 50)
    print("ВЫБЕРИТЕ РЕЖИМ ЗАГРУЗКИ:")
    print("=" * 50)
    print("1. 🧪 ТЕСТОВЫЙ режим (первые 5 компаний, базовые разделы)")
    print("2. 🚀 ПОЛНАЯ загрузка (все 254 компании, базовые разделы)")
    print("3. 📦 ПОЛНАЯ загрузка + ВСЕ разделы (больше данных, больше запросов)")
    print("4. ⏭️ Продолжить предыдущую загрузку")
    print("5. 🔧 Настроить разделы вручную")

    choice = input("\nВыберите действие (1-5): ").strip()

    if choice == "1":
        results = test_mode(companies_df, BASE_SECTIONS, limit=5)
        print("\n" + "=" * 50)
        print("📊 РЕЗУЛЬТАТЫ ТЕСТА:")
        success = sum(1 for r in results if r["status"] == "success")
        print(f"   ✅ Успешно: {success}/5")

    elif choice == "2":
        full_load(companies_df, BASE_SECTIONS, "ПОЛНАЯ ЗАГРУЗКА")

    elif choice == "3":
        full_load(companies_df, AVAILABLE_SECTIONS, "ПОЛНАЯ ЗАГРУЗКА СО ВСЕМИ РАЗДЕЛАМИ")

    elif choice == "4":
        progress = load_progress()
        sections = progress.get("sections_used", BASE_SECTIONS)

        print(f"\n⏭️ ПРОДОЛЖЕНИЕ ЗАГРУЗКИ")
        print(f"   Загружено: {len(progress['completed'])} компаний")
        print(f"   Разделы: {', '.join(sections)}")

        continue_loading(companies_df, progress, sections)

    elif choice == "5":
        print("\n🔧 ДОСТУПНЫЕ РАЗДЕЛЫ:")
        for i, section in enumerate(AVAILABLE_SECTIONS, 1):
            print(f"   {i}. {section}")

        print("\nВведите номера разделов через запятую (например: 1,2,3,4,5)")
        sections_input = input("> ").strip()

        if sections_input.lower() == 'all':
            sections = AVAILABLE_SECTIONS
        else:
            indices = [int(x.strip()) for x in sections_input.split(',')]
            sections = [AVAILABLE_SECTIONS[i - 1] for i in indices if 1 <= i <= len(AVAILABLE_SECTIONS)]

        print(f"\n✅ Выбраны разделы: {', '.join(sections)}")
        results = test_mode(companies_df, sections, limit=3)

    else:
        print("❌ Неверный выбор")


if __name__ == "__main__":
    main()