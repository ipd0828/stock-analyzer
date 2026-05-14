# config/companies.py
import sys
from pathlib import Path

# Добавляем корень проекта для импорта
sys.path.append(str(Path(__file__).parent.parent))


def test_companies():
    """Тестирование конфигурации компаний"""
    print("🔧 Тестирование конфигурации компаний...")

    # ========== КОМПАНИИ ДЛЯ ОТСЛЕЖИВАНИЯ ==========
    COMPANIES = {
        "Сбер": ["сбер", "сбера", "сбербанк", "sber"],
        "Лукойл": ["лукойл", "лукойла", "lukoil"],
        "Газпром": ["газпром", "газпрома", "gazprom"],
        "Новатэк": ["новатэк", "новатэка", "novatek", "ямал спг", "ямал lng", "арктик спг", "арктик lng"],
        "ВТБ": ["втб", "vtb"]
    }

    print(f"\n📊 Компании для отслеживания:")
    for company, keywords in COMPANIES.items():
        print(f"   {company}: {len(keywords)} ключевых слов")
        print(f"      keywords: {keywords}")

    # ========== ТИКЕРЫ НА MOEX ==========
    TICKERS = ["SBER", "LKOH", "GAZP", "NVTK", "VTBR"]

    print(f"\n📈 Тикеры на MOEX:")
    for ticker in TICKERS:
        print(f"   {ticker}")

    # ========== СООТВЕТСТВИЕ ТИКЕРОВ И КОМПАНИЙ ==========
    TICKER_TO_COMPANY = {
        "SBER": "Сбер",
        "LKOH": "Лукойл",
        "GAZP": "Газпром",
        "NVTK": "Новатэк",
        "VTBR": "ВТБ"
    }

    print(f"\n🔗 Соответствие тикеров и компаний:")
    for ticker, company in TICKER_TO_COMPANY.items():
        print(f"   {ticker} → {company}")

    # ========== ПРОВЕРКА СОГЛАСОВАННОСТИ ==========
    print(f"\n🔍 Проверка согласованности данных:")

    # Проверка 1: Все ли компании из COMPANIES есть в TICKER_TO_COMPANY
    companies_in_mapping = set(TICKER_TO_COMPANY.values())
    all_companies = set(COMPANIES.keys())

    missing_in_mapping = all_companies - companies_in_mapping
    if missing_in_mapping:
        print(f"   ❌ Компании отсутствуют в TICKER_TO_COMPANY: {missing_in_mapping}")
    else:
        print(f"   ✅ Все компании есть в TICKER_TO_COMPANY")

    # Проверка 2: Все ли тикеры из TICKERS есть в TICKER_TO_COMPANY
    tickers_in_mapping = set(TICKER_TO_COMPANY.keys())
    all_tickers = set(TICKERS)

    missing_tickers = all_tickers - tickers_in_mapping
    if missing_tickers:
        print(f"   ❌ Тикеры отсутствуют в TICKER_TO_COMPANY: {missing_tickers}")
    else:
        print(f"   ✅ Все тикеры есть в TICKER_TO_COMPANY")

    # Проверка 3: Нет ли дубликатов
    if len(TICKERS) != len(set(TICKERS)):
        print(f"   ❌ Есть дубликаты в TICKERS")
    else:
        print(f"   ✅ Нет дубликатов в TICKERS")

    if len(COMPANIES) != len(set(COMPANIES.keys())):
        print(f"   ❌ Есть дубликаты в COMPANIES")
    else:
        print(f"   ✅ Нет дубликатов в COMPANIES")

    # ========== ИНДЕКСЫ ДЛЯ ОТСЛЕЖИВАНИЯ ==========
    INDICES = ["IMOEX", "RTSI", "MOEXOG", "MOEXFN", "MOEXMM", "MOEXCN"]

    print(f"\n📊 Индексы для отслеживания:")
    for index in INDICES:
        print(f"   {index}")

    # ========== СОБИРАЕМ ВСЕ В ОДИН СЛОВАРЬ ==========
    companies_config = {
        'COMPANIES': COMPANIES,
        'TICKERS': TICKERS,
        'TICKER_TO_COMPANY': TICKER_TO_COMPANY,
        'INDICES': INDICES
    }

    print(f"\n" + "=" * 50)
    print("✅ Тестирование компаний завершено!")
    print("=" * 50)

    return companies_config


# Экспортируем все переменные для использования в других файлах
COMPANIES = {
    "Сбер": ["сбер", "сбера", "сбербанк", "sber"],
    "Лукойл": ["лукойл", "лукойла", "lukoil"],
    "Газпром": ["газпром", "газпрома", "gazprom"],
    "Новатэк": ["новатэк", "новатэка", "novatek", "ямал спг", "ямал lng", "арктик спг", "арктик lng"],
    "ВТБ": ["втб", "vtb"]
}

TICKERS = ["SBER", "LKOH", "GAZP", "NVTK", "VTBR"]

TICKER_TO_COMPANY = {
    "SBER": "Сбер",
    "LKOH": "Лукойл",
    "GAZP": "Газпром",
    "NVTK": "Новатэк",
    "VTBR": "ВТБ"
}

INDICES = ["IMOEX", "RTSI"]

if __name__ == "__main__":
    config = test_companies()

    # Дополнительная проверка: можно ли импортировать
    print(f"\n📦 Проверка импорта:")
    try:
        from config import COMPANIES, TICKERS, TICKER_TO_COMPANY, INDICES

        print(f"   ✅ Все переменные успешно импортируются")
        print(f"   COMPANIES: {list(COMPANIES.keys())}")
        print(f"   TICKERS: {TICKERS}")
        print(f"   INDICES: {INDICES}")
    except ImportError as e:
        print(f"   ❌ Ошибка импорта: {e}")