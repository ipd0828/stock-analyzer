# scripts/filter_forum_comments_by_date.py

"""
Фильтрация комментариев форума по дате
Оставляет только записи с 1 января 2020 года до настоящего момента
"""

import pandas as pd
from pathlib import Path
import sys
from datetime import datetime
from dateutil import parser as date_parser

# Пути
INPUT_FILE = Path("/home/ipd0828-777/PycharmProjects/stockanalyser_2/data/raw/forum_comments/forum_comments_all.csv")
OUTPUT_FILE = Path(
    "/home/ipd0828-777/PycharmProjects/stockanalyser_2/data/raw/forum_comments/forum_comments_filtered_2020plus.csv")
BACKUP_FILE = Path(
    "/home/ipd0828-777/PycharmProjects/stockanalyser_2/data/raw/forum_comments/forum_comments_all_backup.csv")

START_DATE = datetime(2020, 1, 1)
END_DATE = datetime.now()


def parse_date(date_str):
    """Парсит дату из разных форматов, включая ISO 8601 с часовым поясом"""
    if pd.isna(date_str) or not date_str:
        return None

    date_str = str(date_str).strip()

    # Используем dateutil для ISO формата с часовым поясом
    try:
        dt = date_parser.parse(date_str)
        # Преобразуем в naive datetime (без часового пояса)
        return dt.replace(tzinfo=None)
    except:
        pass

    # Формат YYYY-MM-DD
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except:
        pass

    # Формат YYYY-MM-DD HH:MM:SS
    try:
        return datetime.strptime(date_str.split()[0], '%Y-%m-%d')
    except:
        pass

    # Формат DD.MM.YYYY
    try:
        return datetime.strptime(date_str, '%d.%m.%Y')
    except:
        pass

    # Формат DD.MM.YYYY HH:MM:SS
    try:
        return datetime.strptime(date_str.split()[0], '%d.%m.%Y')
    except:
        pass

    return None


def filter_comments():
    """Фильтрует комментарии по дате"""

    print("=" * 70)
    print("📊 ФИЛЬТРАЦИЯ КОММЕНТАРИЕВ ПО ДАТЕ")
    print(f"   Период: {START_DATE.strftime('%Y-%m-%d')} - {END_DATE.strftime('%Y-%m-%d')}")
    print("=" * 70)

    # Проверяем существование файла
    if not INPUT_FILE.exists():
        print(f"❌ Файл не найден: {INPUT_FILE}")
        return

    # Создаём резервную копию
    if not BACKUP_FILE.exists():
        print(f"📁 Создаём резервную копию...")
        import shutil
        shutil.copy2(INPUT_FILE, BACKUP_FILE)
        print(f"   ✅ Резервная копия: {BACKUP_FILE}")

    # Загружаем данные
    print(f"\n📚 Загрузка данных из {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE)
    print(f"   Всего записей: {len(df):,}")

    # Показываем примеры дат
    print(f"\n📅 Примеры дат в исходных данных:")
    for col in ['datetime', 'date_raw', 'date']:
        if col in df.columns and df[col].notna().any():
            print(f"   {col}: {df[col].dropna().iloc[0][:50]}")

    # Определяем, какая колонка с датой
    date_col = None
    for col in ['datetime', 'date_raw', 'date']:
        if col in df.columns:
            date_col = col
            print(f"\n   ✅ Используем колонку: {date_col}")
            break

    if date_col is None:
        print("❌ Не найдена колонка с датой!")
        return

    # Парсим даты
    print(f"\n🔄 Парсинг дат...")
    df['parsed_date'] = df[date_col].apply(parse_date)

    # Считаем успешность парсинга
    parsed_count = df['parsed_date'].notna().sum()
    print(f"   Успешно распарсено: {parsed_count:,} ({parsed_count / len(df) * 100:.1f}%)")

    # Показываем примеры распарсенных дат
    if parsed_count > 0:
        print(f"\n   Примеры распарсенных дат:")
        for i, date in enumerate(df['parsed_date'].dropna().head(5)):
            print(f"      {date}")

    # Фильтруем
    print(f"\n🎯 Фильтрация записей после {START_DATE.strftime('%Y-%m-%d')}...")
    filtered_df = df[df['parsed_date'] >= START_DATE].copy()

    print(f"   Осталось после фильтрации: {len(filtered_df):,} ({len(filtered_df) / len(df) * 100:.1f}%)")

    # Если есть отфильтрованные данные, показываем статистику
    if len(filtered_df) > 0:
        print(f"\n📊 СТАТИСТИКА ПО ГОДАМ:")
        filtered_df['year'] = filtered_df['parsed_date'].dt.year
        for year in sorted(filtered_df['year'].unique()):
            count = (filtered_df['year'] == year).sum()
            print(f"   {year}: {count:,}")

        # Сохраняем результат
        filtered_df = filtered_df.drop(columns=['parsed_date', 'year'])
        filtered_df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8')

        print(f"\n✅ Сохранено: {OUTPUT_FILE}")
        print(f"   Размер: {len(filtered_df):,} записей")

        # Статистика по компаниям
        if 'ticker' in filtered_df.columns:
            print(f"\n📊 ПО КОМПАНИЯМ:")
            for ticker in filtered_df['ticker'].unique():
                count = (filtered_df['ticker'] == ticker).sum()
                print(f"   {ticker}: {count:,}")
    else:
        print(f"\n❌ Нет записей после {START_DATE.strftime('%Y-%m-%d')}")
        print(f"   Возможно, все даты в файле старые или формат даты не распознан")
        print(f"   Проверьте формат даты в исходном файле")

    return filtered_df


def main():
    """Основная функция"""
    df = filter_comments()

    print("\n" + "=" * 70)
    print("🎉 ФИЛЬТРАЦИЯ ЗАВЕРШЕНА!")
    print("=" * 70)
    if df is not None and len(df) > 0:
        print(f"\n💡 Теперь можно запускать классификацию на отфильтрованных данных:")
        print(f"   python src/llama_classifier/classify_batch_advanced.py --full")
        print(f"\n   Или использовать отфильтрованный файл:")
        print(f"   {OUTPUT_FILE}")


if __name__ == "__main__":
    main()