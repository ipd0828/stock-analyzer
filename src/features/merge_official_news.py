# src/features/merge_official_news.py

"""
Объединение официальных новостей всех компаний
Обработка смешанных форматов дат
"""

import pandas as pd
from pathlib import Path
import sys
import re

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR, PROCESSED_DATA_DIR


def parse_russian_date(date_str):
    """Парсит русскую дату вида '11 марта 2026' или '11 марта 2026, 23:20'"""
    if not date_str or pd.isna(date_str):
        return None

    months = {
        'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
        'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
        'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12'
    }

    date_str = str(date_str).strip()
    # Убираем кавычки, если есть
    date_str = date_str.strip('"').strip("'")
    # Убираем время, если есть
    date_str = date_str.split(',')[0].strip()

    for month_rus, month_num in months.items():
        if month_rus in date_str:
            parts = re.findall(r'(\d+)', date_str)
            if len(parts) >= 2:
                day = parts[0].zfill(2)
                year = parts[1]
                return f"{year}-{month_num}-{day}"
    return None


def parse_iso_date(date_str):
    """Парсит ISO дату вида '2026-03-22'"""
    if not date_str or pd.isna(date_str):
        return None
    try:
        return pd.to_datetime(str(date_str).strip(), format='%Y-%m-%d', errors='coerce')
    except:
        return None


def merge_official_news():
    print("=" * 70)
    print("🚀 ОБЪЕДИНЕНИЕ ОФИЦИАЛЬНЫХ НОВОСТЕЙ")
    print("=" * 70)

    all_dfs = []

    # 1. СБЕР
    file_path = RAW_DATA_DIR / "sber_official_news/sber_official_news_with_text.csv"
    if file_path.exists():
        df = pd.read_csv(file_path)
        print(f"\n✅ СБЕР: {len(df)} записей")

        df['date'] = df['date_raw'].apply(parse_russian_date)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')

        df_clean = pd.DataFrame({
            'ticker': 'SBER',
            'company': 'Сбер',
            'date': df['date'],
            'title': df.get('title', ''),
            'text': df.get('text', ''),
            'url': df.get('url', ''),
            'source': 'sber_official',
        })
        all_dfs.append(df_clean)
        print(f"   С текстом: {df_clean['text'].notna().sum()}")
        print(f"   С датой: {df_clean['date'].notna().sum()}")

    # 2. ГАЗПРОМ
    file_path = RAW_DATA_DIR / "gazprom_official_news/gazprom_official_news_with_text.csv"
    if file_path.exists():
        df = pd.read_csv(file_path)
        print(f"\n✅ ГАЗПРОМ: {len(df)} записей")

        # Функция для универсального парсинга даты
        def parse_gazp_date(val):
            if pd.isna(val):
                return None
            val_str = str(val).strip()
            # Если строка начинается с кавычки - это русская дата
            if val_str.startswith('"') or val_str.startswith("'"):
                return parse_russian_date(val_str)
            # Если формат YYYY-MM-DD
            if re.match(r'^\d{4}-\d{2}-\d{2}$', val_str):
                return val_str
            # Иначе пробуем как русскую
            return parse_russian_date(val_str)

        df['date_str'] = df['date_normalized'].apply(parse_gazp_date)
        df['date'] = pd.to_datetime(df['date_str'], errors='coerce')

        print(f"   Примеры дат после парсинга: {df['date_str'].dropna().head(5).tolist()}")

        df_clean = pd.DataFrame({
            'ticker': 'GAZP',
            'company': 'Газпром',
            'date': df['date'],
            'title': df.get('title', ''),
            'text': df.get('text', ''),
            'url': df.get('url', ''),
            'source': 'gazprom_official',
        })
        all_dfs.append(df_clean)
        print(f"   С текстом: {df_clean['text'].notna().sum()}")
        print(f"   С датой: {df_clean['date'].notna().sum()}")

    # 3. ЛУКОЙЛ
    file_path = RAW_DATA_DIR / "lukoil_official_news/lukoil_official_news_with_text.csv"
    if file_path.exists():
        df = pd.read_csv(file_path)
        print(f"\n✅ ЛУКОЙЛ: {len(df)} записей")

        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')

        df_clean = pd.DataFrame({
            'ticker': 'LKOH',
            'company': 'Лукойл',
            'date': df['date'],
            'title': df.get('title', ''),
            'text': df.get('text', ''),
            'url': df.get('url', ''),
            'source': 'lukoil_official',
        })
        all_dfs.append(df_clean)
        print(f"   С текстом: {df_clean['text'].notna().sum()}")
        print(f"   С датой: {df_clean['date'].notna().sum()}")

    # 4. НОВАТЭК
    file_path = RAW_DATA_DIR / "novatek_official_news/novatek_official_news_all.csv"
    if file_path.exists():
        df = pd.read_csv(file_path)
        print(f"\n✅ НОВАТЭК: {len(df)} записей")

        if 'date_normalized' in df.columns:
            df['date'] = pd.to_datetime(df['date_normalized'], errors='coerce')

        df_clean = pd.DataFrame({
            'ticker': 'NVTK',
            'company': 'Новатэк',
            'date': df['date'],
            'title': df.get('title', ''),
            'text': df.get('text', ''),
            'url': df.get('url', ''),
            'source': 'novatek_official',
        })
        all_dfs.append(df_clean)
        print(f"   С текстом: {df_clean['text'].notna().sum()}")
        print(f"   С датой: {df_clean['date'].notna().sum()}")

    # 5. ВТБ
    file_path = RAW_DATA_DIR / "vtb_official_news/vtb_official_news_all.csv"
    if file_path.exists():
        df = pd.read_csv(file_path)
        print(f"\n✅ ВТБ: {len(df)} записей")

        if 'date_normalized' in df.columns:
            df['date'] = pd.to_datetime(df['date_normalized'], errors='coerce')

        df_clean = pd.DataFrame({
            'ticker': 'VTBR',
            'company': 'ВТБ',
            'date': df['date'],
            'title': df.get('title', ''),
            'text': df.get('text', ''),
            'url': df.get('url', ''),
            'source': 'vtb_official',
        })
        all_dfs.append(df_clean)
        print(f"   С текстом: {df_clean['text'].notna().sum()}")
        print(f"   С датой: {df_clean['date'].notna().sum()}")

    # Объединяем всё
    if all_dfs:
        merged = pd.concat(all_dfs, ignore_index=True)

        # Сортируем по дате
        merged = merged.sort_values('date').reset_index(drop=True)

        print("\n" + "=" * 70)
        print("📊 ИТОГИ ОБЪЕДИНЕНИЯ")
        print("=" * 70)
        print(f"   Всего записей: {len(merged)}")

        print(f"\n📊 ПО КОМПАНИЯМ:")
        for ticker in merged['ticker'].unique():
            df_ticker = merged[merged['ticker'] == ticker]
            with_text = df_ticker['text'].notna().sum()
            with_date = df_ticker['date'].notna().sum()
            print(f"   {ticker}: {len(df_ticker)} новостей (с текстом: {with_text}, с датой: {with_date})")

        # Статистика по годам
        merged_with_date = merged[merged['date'].notna()].copy()
        merged_with_date['year'] = merged_with_date['date'].dt.year
        print(f"\n📊 ПО ГОДАМ:")
        for year in sorted(merged_with_date['year'].dropna().unique()):
            count = (merged_with_date['year'] == year).sum()
            print(f"   {int(year)}: {count}")

        # Сохраняем
        output_file = PROCESSED_DATA_DIR / "official_news_all.csv"
        merged.to_csv(output_file, index=False, encoding='utf-8')

        print(f"\n📁 Сохранено: {output_file}")
        print(f"   Размер: {len(merged)} записей")

        return merged
    else:
        print("\n❌ Нет данных для объединения")
        return None


if __name__ == "__main__":
    merge_official_news()