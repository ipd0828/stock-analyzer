#!/usr/bin/env python3
# scripts/bd/get_companies_list.py
"""
Получение списка компаний с FinanceMarker API
"""

import time
import json
import requests
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from config import API_TOKEN, BASE_URL, REQUEST_DELAY, DATA_DIR

# Директория для данных
BD_DATA_DIR = DATA_DIR / "bd"
BD_RAW_DIR = BD_DATA_DIR / "raw"
BD_RAW_DIR.mkdir(parents=True, exist_ok=True)

# Файлы для сохранения состояния
STATE_FILE = BD_RAW_DIR / "fetch_state.json"
ALL_COMPANIES_FILE = BD_RAW_DIR / "all_companies.csv"
RUSSIAN_COMPANIES_FILE = BD_RAW_DIR / "russian_companies.csv"


def load_state() -> Dict:
    """Загружает состояние предыдущей загрузки"""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "offset": 0,
        "page": 1,
        "companies": [],
        "total_requests": 0,
        "last_update": None,
        "completed": False
    }


def save_state(state: Dict):
    """Сохраняет текущее состояние"""
    state["last_update"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def make_request(url: str, params: Dict, state: Dict) -> Optional[Dict]:
    """Делает запрос с обновлением состояния"""
    try:
        response = requests.get(url, params=params, timeout=30)
        state["total_requests"] += 1

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            error_data = response.json()
            if error_data.get("message") == "out_of_limit":
                print(f"\n❌ Превышен лимит запросов!")
            return None
        else:
            print(f"\n⚠️ Ошибка {response.status_code}")
            return None

    except Exception as e:
        print(f"\n❌ Ошибка запроса: {e}")
        return None


def fetch_companies_batch(limit: int = 100, max_pages: int = None) -> List[Dict]:
    """
    Загружает компании порциями с возможностью продолжения
    """
    state = load_state()

    # Если загрузка уже завершена, не продолжаем
    if state.get("completed"):
        print("✅ Загрузка уже завершена!")
        return state["companies"]

    start_offset = state["offset"]
    start_page = state["page"]
    companies = state["companies"].copy()

    print("=" * 70)
    print("🌍 СБОР КОМПАНИЙ С FINANCEMARKER")
    print(f"📊 Режим: {'ПРОДОЛЖЕНИЕ' if start_offset > 0 else 'НАЧАЛО'}")
    print(f"📍 Старт с offset={start_offset}, страница {start_page}")
    print("=" * 70)
    print()

    offset = start_offset
    page = start_page

    while True:
        # Проверка лимита страниц
        if max_pages and page > max_pages:
            print(f"\n⏹️ Достигнут лимит страниц: {max_pages}")
            break

        url = f"{BASE_URL}/stocks"
        params = {
            "api_token": API_TOKEN,
            "limit": limit,
            "offset": offset
        }

        print(f"📄 Страница {page}: offset={offset}, limit={limit}", end=" ", flush=True)

        data = make_request(url, params, state)

        if data is None:
            print("❌ Ошибка, остановка")
            break

        if not isinstance(data, list):
            print(f"❌ Неожиданный формат: {type(data)}")
            break

        batch_count = len(data)
        companies.extend(data)

        print(f"✅ +{batch_count} (всего: {len(companies)})")

        # Обновляем состояние
        state["companies"] = companies
        state["offset"] = offset
        state["page"] = page
        save_state(state)

        # Сохраняем CSV после каждой страницы
        save_companies_to_csv(companies)

        # Если получили меньше limit — это последняя страница
        if batch_count < limit:
            print(f"\n🏁 Достигнут конец списка")
            state["completed"] = True
            save_state(state)
            break

        offset += limit
        page += 1
        time.sleep(REQUEST_DELAY)

    return companies


def save_companies_to_csv(companies: List[Dict]):
    """Сохраняет компании в CSV"""
    if not companies:
        return

    df = pd.DataFrame(companies)

    # Добавляем полный код
    df["full_code"] = df["exchange"] + ":" + df["code"]

    # Определяем российские компании
    russian_exchanges = ["MOEX", "SPB"]
    df["is_russian"] = df["exchange"].isin(russian_exchanges)

    # Сохраняем полный список
    df.to_csv(ALL_COMPANIES_FILE, index=False, encoding="utf-8")

    # Сохраняем отдельно российские
    russian_df = df[df["is_russian"] == True]
    if len(russian_df) > 0:
        russian_df.to_csv(RUSSIAN_COMPANIES_FILE, index=False, encoding="utf-8")

    russian_count = len(russian_df)
    print(f"\n💾 ПРОМЕЖУТОЧНОЕ СОХРАНЕНИЕ:")
    print(f"   Всего: {len(df)} компаний")
    print(f"   Российских: {russian_count}")
    print(f"   Файлы: {ALL_COMPANIES_FILE.name}, {RUSSIAN_COMPANIES_FILE.name}")


def print_summary(companies: List[Dict]):
    """Выводит итоговую статистику"""
    if not companies:
        print("❌ Нет данных")
        return

    df = pd.DataFrame(companies)

    # Добавляем флаг российских для статистики
    russian_exchanges = ["MOEX", "SPB"]
    df["is_russian"] = df["exchange"].isin(russian_exchanges)

    print("\n" + "=" * 70)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 70)

    print(f"\n🏢 ВСЕГО: {len(df)} компаний")

    # По биржам
    print(f"\n📈 ПО БИРЖАМ:")
    exchange_counts = df["exchange"].value_counts()
    for exchange, count in exchange_counts.items():
        marker = "🇷🇺" if exchange in ["MOEX", "SPB"] else "🌍"
        print(f"   {marker} {exchange}: {count}")

    # Российские компании
    russian_df = df[df["is_russian"] == True]
    if len(russian_df) > 0:
        print(f"\n🇷🇺 РОССИЙСКИЕ КОМПАНИИ: {len(russian_df)}")
        print("   Первые 15:")
        for _, row in russian_df.head(15).iterrows():
            name = row.get("name", row["code"])
            if len(name) > 45:
                name = name[:42] + "..."
            print(f"      • {row['exchange']}:{row['code']:<10} {name}")


def reset_state():
    """Сбрасывает состояние для новой загрузки"""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    print("✅ Состояние сброшено")


def show_state():
    """Показывает текущее состояние"""
    state = load_state()
    print(f"\n📊 ТЕКУЩЕЕ СОСТОЯНИЕ:")
    print(f"   Загружено компаний: {len(state['companies'])}")
    print(f"   Последний offset: {state['offset']}")
    print(f"   Страница: {state['page']}")
    print(f"   Всего запросов: {state['total_requests']}")
    print(f"   Последнее обновление: {state.get('last_update', 'Нет')}")
    print(f"   Загрузка завершена: {state.get('completed', False)}")

    if len(state['companies']) > 0:
        print(f"\n   Последние 5 загруженных компаний:")
        for comp in state['companies'][-5:]:
            print(f"      • {comp.get('exchange')}:{comp.get('code')}")


def main():
    print("=" * 70)
    print("📡 УПРАВЛЕНИЕ ЗАГРУЗКОЙ КОМПАНИЙ")
    print("=" * 70)
    print()
    print("1. Начать новую загрузку (первые 10 страниц = 1000 компаний)")
    print("2. Продолжить предыдущую загрузку")
    print("3. Загрузить всё (осторожно, много запросов)")
    print("4. Сбросить состояние и начать заново")
    print("5. Показать текущее состояние")

    choice = input("\nВыберите действие (1-5): ").strip()

    if choice == "1":
        print("\n🚀 Начинаем тестовую загрузку (до 10 страниц)...")
        companies = fetch_companies_batch(limit=100, max_pages=10)
        print_summary(companies)

    elif choice == "2":
        state = load_state()
        if state["offset"] == 0 and state["page"] == 1 and not state.get("completed"):
            print("\n⚠️ Нет сохраненного состояния. Начинаем новую загрузку...")
            companies = fetch_companies_batch(limit=100, max_pages=10)
        else:
            print(f"\n🚀 Продолжаем с offset={state['offset']}, страница {state['page']}")
            companies = fetch_companies_batch(limit=100)
        print_summary(companies)

    elif choice == "3":
        print("\n⚠️ ВНИМАНИЕ! Это может занять много времени и запросов.")
        confirm = input("Продолжить? (y/n): ").strip().lower()
        if confirm == 'y':
            companies = fetch_companies_batch(limit=100)
            print_summary(companies)
        else:
            print("Отменено")

    elif choice == "4":
        reset_state()
        print("\n🚀 Начинаем новую загрузку...")
        companies = fetch_companies_batch(limit=100, max_pages=10)
        print_summary(companies)

    elif choice == "5":
        show_state()

    else:
        print("❌ Неверный выбор")


if __name__ == "__main__":
    main()