#!/usr/bin/env python3
# scripts/bd/retry_failed.py
"""
Повторная загрузка компаний, которые завершились с ошибкой
"""

import time
import json
import requests
import pandas as pd
from pathlib import Path
from typing import Dict, Optional
from config import API_TOKEN, BASE_URL, REQUEST_DELAY, DATA_DIR

# ДИРЕКТОРИИ - исправлено на правильный путь
BD_DATA_DIR = DATA_DIR / "bd" / "raw"  # scripts/data/bd/raw
BD_COMPANIES_DIR = BD_DATA_DIR / "companies_data"
PROGRESS_FILE = BD_DATA_DIR / "fetch_progress.json"
RUSSIAN_COMPANIES_FILE = BD_DATA_DIR / "russian_companies.csv"

# Создаем директорию, если её нет
BD_COMPANIES_DIR.mkdir(parents=True, exist_ok=True)

# Разделы для загрузки
SECTIONS = ["reports", "ratios", "dividends", "calendar", "disclosure", "shares"]


def load_progress() -> Dict:
    """Загружает прогресс"""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {"failed": [], "completed": [], "total_requests": 0, "last_index": 0}


def save_progress(progress: Dict):
    """Сохраняет прогресс"""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def fetch_company_data(code: str, exchange: str, progress: Dict) -> Optional[Dict]:
    """Загружает данные по компании"""
    url = f"{BASE_URL}/stocks/{exchange}:{code}"
    params = {
        "api_token": API_TOKEN,
        "include": ",".join(SECTIONS)
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        progress["total_requests"] = progress.get("total_requests", 0) + 1

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
    filepath = BD_COMPANIES_DIR / f"{exchange}_{code}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


def get_failed_companies() -> pd.DataFrame:
    """Получает список компаний, которые нужно перезагрузить"""
    if not RUSSIAN_COMPANIES_FILE.exists():
        print(f"❌ Файл {RUSSIAN_COMPANIES_FILE} не найден!")
        return pd.DataFrame()

    # Загружаем список всех российских компаний
    companies_df = pd.read_csv(RUSSIAN_COMPANIES_FILE)

    # Загружаем прогресс
    progress = load_progress()
    failed_codes = set(progress.get("failed", []))
    completed_codes = set(progress.get("completed", []))

    # Получаем уже загруженные файлы
    existing_files = set()
    for filepath in BD_COMPANIES_DIR.glob("*.json"):
        name = filepath.stem
        existing_files.add(name)

    print(f"\n📁 Найдено файлов в папке: {len(existing_files)}")
    print(f"📊 По прогрессу: успешно={len(completed_codes)}, ошибок={len(failed_codes)}")

    # Находим компании, которые нужно перезагрузить
    failed_companies = []
    for _, row in companies_df.iterrows():
        code = row["code"]
        exchange = row["exchange"]
        key = f"{exchange}_{code}"

        # Если в списке ошибок или файла нет
        if key in failed_codes or key not in existing_files:
            failed_companies.append(row)

    return pd.DataFrame(failed_companies)


def main():
    print("=" * 70)
    print("🔄 ПОВТОРНАЯ ЗАГРУЗКА ОШИБОЧНЫХ КОМПАНИЙ")
    print("=" * 70)

    # Проверяем директории
    print(f"\n📁 Рабочая директория: {BD_COMPANIES_DIR}")
    print(f"📁 Файл прогресса: {PROGRESS_FILE}")

    # Получаем список компаний для повторной загрузки
    failed_df = get_failed_companies()

    if failed_df.empty:
        print("\n✅ Нет компаний для повторной загрузки!")
        return

    print(f"\n📊 Найдено {len(failed_df)} компаний для повторной загрузки:")
    for _, row in failed_df.head(20).iterrows():
        name = row.get("name", row["code"])[:50]
        print(f"   • {row['exchange']}:{row['code']} - {name}")

    if len(failed_df) > 20:
        print(f"   ... и еще {len(failed_df) - 20}")

    print("\n" + "-" * 50)
    confirm = input("\nНачать повторную загрузку? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Отменено")
        return

    progress = load_progress()
    total = len(failed_df)
    success_count = 0

    print(f"\n🚀 Начинаем повторную загрузку ({total} компаний)")
    print("⚠️ Если закончится лимит, скрипт остановится")
    print("-" * 50)

    for idx, (_, row) in enumerate(failed_df.iterrows(), 1):
        code = row["code"]
        exchange = row["exchange"]
        key = f"{exchange}_{code}"

        print(f"[{idx}/{total}] 📥 {exchange}:{code}...", end=" ", flush=True)

        data = fetch_company_data(code, exchange, progress)

        if data == "LIMIT_EXCEEDED":
            print("\n⏹️ Остановка из-за превышения лимита")
            break
        elif data:
            save_company_data(data, code, exchange)
            reports = len(data.get("reports", []))
            ratios = len(data.get("ratios", []))
            print(f"✅ (отч:{reports}, коэф:{ratios})")

            # Обновляем прогресс
            if key in progress.get("failed", []):
                progress["failed"].remove(key)
            if key not in progress.get("completed", []):
                progress["completed"].append(key)

            success_count += 1
        else:
            print(f"❌ Снова ошибка")
            if key not in progress.get("failed", []):
                progress["failed"].append(key)

        # Обновляем прогресс
        save_progress(progress)
        time.sleep(REQUEST_DELAY)

    print("\n" + "=" * 70)
    print("📊 РЕЗУЛЬТАТЫ ПОВТОРНОЙ ЗАГРУЗКИ")
    print("=" * 70)
    print(f"   ✅ Успешно перезагружено: {success_count}/{total}")
    print(f"   ❌ Осталось ошибок: {len(progress.get('failed', []))}")
    print(f"\n📁 Данные сохранены в: {BD_COMPANIES_DIR}")


if __name__ == "__main__":
    main()