#!/usr/bin/env python3
# scripts/universal_ifrs_extractor_fixed.py
"""
ИСПРАВЛЕННАЯ версия экстрактора МСФО с OCR поддержкой
"""

import re
import sys
import json
import hashlib
from pathlib import Path
import pandas as pd
import requests
import time
import shutil

sys.path.append(str(Path(__file__).parent.parent))
from config.paths import RAW_DATA_DIR, PROCESSED_DATA_DIR

try:
    import pdfplumber
    from PIL import Image, ImageEnhance, ImageFilter
    import pytesseract
    from pdf2image import convert_from_path
except ImportError:
    print("❌ pip install pdfplumber pillow pytesseract pdf2image")
    sys.exit(1)

# Настройка пути к Tesseract если нужно
# pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

LLM_URL = "http://localhost:8001/v1/chat/completions"
OCR_CACHE_DIR = Path("cache/ocr_fixed")
OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)

print("🧹 Очистка кэша OCR...")
if OCR_CACHE_DIR.exists():
    shutil.rmtree(OCR_CACHE_DIR)
    OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print("   ✅ Кэш очищен")


def get_page_text_with_ocr(pdf_path: Path, page_num: int, dpi: int = 300) -> str:
    """Извлечение текста со страницы с OCR если нужно"""

    cache_key = hashlib.md5(f"{pdf_path.name}_{page_num}_{dpi}".encode()).hexdigest()
    cache_file = OCR_CACHE_DIR / f"{cache_key}.txt"

    # Проверяем кэш
    if cache_file.exists():
        print(f"     📦 Из кэша: {cache_file.name}")
        return cache_file.read_text(encoding='utf-8')

    # Пробуем pdfplumber сначала
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_num > len(pdf.pages):
                return ""

            page = pdf.pages[page_num - 1]
            text = page.extract_text()

            if text and len(text.strip()) > 50:
                print(f"     📄 pdfplumber: {len(text)} символов")
                cache_file.write_text(text, encoding='utf-8')
                return text
    except Exception as e:
        print(f"     ⚠️ pdfplumber ошибка: {e}")

    # Если не получилось - используем OCR
    print(f"     🔍 OCR стр. {page_num} (DPI={dpi})...")
    try:
        images = convert_from_path(str(pdf_path), first_page=page_num,
                                   last_page=page_num, dpi=dpi)
        if images:
            img = images[0]

            # Предобработка для улучшения OCR
            img = img.convert('L')  # Серый
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0)

            # OCR с русским и английским
            text = pytesseract.image_to_string(img, lang='rus+eng',
                                               config='--psm 6 -c preserve_interword_spaces=1')

            if text.strip():
                print(f"     ✅ OCR: {len(text)} символов")
                cache_file.write_text(text, encoding='utf-8')
                return text
            else:
                print(f"     ⚠️ OCR: текст не распознан")
    except Exception as e:
        print(f"     ❌ OCR ошибка: {e}")

    return ""


def clean_text(text: str) -> str:
    """Очистка текста"""
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r'[^\w\s.,\-()"«»%]', '', text, flags=re.UNICODE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_numbers_from_text(text: str, year1: str, year2: str, page_num: int) -> pd.DataFrame:
    """Извлечение чисел с специальной обработкой первой строки"""

    lines = text.split('\n')
    rows = []

    # Сначала ищем строку с "Выручка" и обрабатываем её отдельно
    for idx, line in enumerate(lines):
        if 'выручка' in line.lower():
            print(f"     🔍 Найдена строка с ВЫРУЧКОЙ: {line[:150]}...")

            # Извлекаем ВСЕ числа из строки
            all_numbers = re.findall(r'[\d\s()]+', line)
            clean_numbers = []
            for num_str in all_numbers:
                num_str = num_str.strip()
                if num_str and re.search(r'\d{3,}', num_str):
                    # Очищаем от пробелов
                    clean_num = num_str.replace(' ', '').replace('\xa0', '')
                    if clean_num.startswith('(') and clean_num.endswith(')'):
                        clean_num = '-' + clean_num[1:-1]
                    try:
                        val = int(clean_num)
                        if abs(val) > 100000:  # Только большие числа
                            clean_numbers.append(val)
                    except ValueError:
                        pass

            print(f"     🔢 Найдено чисел: {clean_numbers}")

            if len(clean_numbers) >= 2:
                # Берем два самых больших числа (обычно это годовые totals)
                sorted_nums = sorted(clean_numbers, reverse=True)
                val1 = sorted_nums[0]
                val2 = sorted_nums[1]

                # Если есть 4 числа (поквартально), берем последние два
                if len(clean_numbers) >= 4:
                    # Проверяем, не поквартальные ли это данные
                    if abs(clean_numbers[-1]) > 100000 and abs(clean_numbers[-2]) > 100000:
                        val1 = clean_numbers[-1]
                        val2 = clean_numbers[-2]

                clean_name = "Выручка от продаж"
                rows.append({
                    'raw_name': clean_name,
                    'original_line': line.strip()[:300],
                    f"{year1} (млн руб)": val1,
                    f"{year2} (млн руб)": val2,
                    'page': page_num,
                    'line_id': f"p{page_num}_l{idx:04d}"
                })
                print(f"     ✅ ВЫРУЧКА ИЗВЛЕЧЕНА: {val1:,} | {val2:,}")

    # Обычная обработка остальных строк
    for idx, line in enumerate(lines):
        original_line = line
        line = line.strip()

        if not line or len(line) < 10:
            continue

        # Пропускаем уже обработанную выручку
        if 'выручка' in line.lower():
            continue

        # Пропускаем заголовки
        if re.match(r'^(консолидированный|отчет|statement|примечания|содержание|оглавление|пао|заключение)',
                    line.lower()):
            if not re.search(r'\d{4,}', line):
                continue

        # Паттерн 1: название ... число ... число
        parts = re.split(r'\s{3,}', line)
        if len(parts) >= 3:
            name = ' '.join(parts[:-2]).strip()
            val1_str = parts[-2].strip()
            val2_str = parts[-1].strip()

            val1_str = val1_str.replace(' ', '').replace('\xa0', '')
            val2_str = val2_str.replace(' ', '').replace('\xa0', '')

            if val1_str.startswith('(') and val1_str.endswith(')'):
                val1_str = '-' + val1_str[1:-1]
            if val2_str.startswith('(') and val2_str.endswith(')'):
                val2_str = '-' + val2_str[1:-1]

            try:
                val1 = int(val1_str)
                val2 = int(val2_str)

                if abs(val1) < 100_000_000_000 and abs(val2) < 100_000_000_000:
                    if name and len(name) > 3:
                        clean_name = re.sub(r'^[\d\s\-—_,.()\'\"|;]+', '', name).strip()

                        if clean_name and not clean_name.isdigit():
                            if not any(r['raw_name'] == clean_name for r in rows):
                                rows.append({
                                    'raw_name': clean_name,
                                    'original_line': original_line.strip()[:300],
                                    f"{year1} (млн руб)": val1,
                                    f"{year2} (млн руб)": val2,
                                    'page': page_num,
                                    'line_id': f"p{page_num}_l{idx:04d}"
                                })
                                continue
            except (ValueError, TypeError):
                pass

        # Паттерн 2: ищем группы цифр
        numbers_in_line = re.findall(r'([\d\s()]+)', line)
        valid_numbers = []
        for num_str in numbers_in_line:
            num_str = num_str.strip()
            if num_str and re.search(r'\d{3,}', num_str):
                clean_num = num_str.replace(' ', '').replace('\xa0', '')
                if clean_num.startswith('(') and clean_num.endswith(')'):
                    clean_num = '-' + clean_num[1:-1]
                try:
                    int(clean_num)
                    valid_numbers.append((num_str, clean_num))
                except ValueError:
                    pass

        if len(valid_numbers) >= 2:
            val1_str = valid_numbers[-2][1]
            val2_str = valid_numbers[-1][1]

            try:
                val1 = int(val1_str)
                val2 = int(val2_str)

                if abs(val1) > 100000 and abs(val2) > 100000:
                    second_last_num_text = valid_numbers[-2][0]
                    pos = line.rfind(second_last_num_text)
                    if pos > 0:
                        name = line[:pos].strip()
                        clean_name = re.sub(r'^[\d\s\-—_,.()\'\"|;]+', '', name).strip()
                        clean_name = re.sub(
                            r'\s*\d{1,2}\s+(декабря|января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября)\s*$',
                            '', clean_name, flags=re.IGNORECASE).strip()
                        clean_name = re.sub(r'\s*\(\d[\d\s]*\d\)\s*$', '', clean_name).strip()

                        if clean_name and len(clean_name) > 3 and not clean_name.isdigit():
                            if not any(r['raw_name'] == clean_name for r in rows):
                                rows.append({
                                    'raw_name': clean_name,
                                    'original_line': original_line.strip()[:300],
                                    f"{year1} (млн руб)": val1,
                                    f"{year2} (млн руб)": val2,
                                    'page': page_num,
                                    'line_id': f"p{page_num}_l{idx:04d}"
                                })
            except (ValueError, TypeError):
                pass

    if rows:
        df = pd.DataFrame(rows)
        print(f"     📊 Извлечено показателей: {len(df)}")

        # Проверяем выручку
        revenue_rows = df[df['raw_name'].str.contains('выручка', case=False, na=False)]
        if not revenue_rows.empty:
            print(f"     ✅ ВЫРУЧКА в результате!")

        return df

    return pd.DataFrame()


def normalize_names_hybrid(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Финальная версия нормализации с фильтрацией мусора"""

    if df_raw.empty:
        return pd.DataFrame()

    print(f"\n📋 Нормализация {len(df_raw)} показателей...")

    # Сначала фильтруем явный мусор
    garbage_patterns = [
        r'^ликвидных торговых площадках',
        r'^предприятий$',
        r'^организациях$',
        r'^совместных предприятий$',
        r'^трудовой деятельности$',
        r'^реклассифицирован в состав',
        r'^стоимости, изменения которой',
        r'^в приобретенных организациях$',
        r'^I lpouce$',
        r'^и тепловой энергии$',
        r'^нефтегазопереработки$',
        r'^межсегментные',
    ]

    # Фильтруем DataFrame
    mask_garbage = pd.Series(False, index=df_raw.index)
    for pattern in garbage_patterns:
        mask_garbage |= df_raw['raw_name'].str.contains(pattern, case=False, na=False, regex=True)

    df_filtered = df_raw[~mask_garbage].copy()

    removed_count = len(df_raw) - len(df_filtered)
    if removed_count > 0:
        print(f"   🗑️ Удалено мусорных строк: {removed_count}")
        print("   Удаленные строки:")
        for _, row in df_raw[mask_garbage].iterrows():
            print(f"      - {row['raw_name'][:80]}")

    # Расширенный словарь стандартных названий
    standard_mapping = {
        # Активы
        'денежные средства и их эквиваленты': 'Денежные средства и их эквиваленты',
        'краткосрочные финансовые активы': 'Краткосрочные финансовые активы',
        'дебиторская задолженность и предоплата': 'Дебиторская задолженность и предоплата',
        'дебиторская задолженность': 'Дебиторская задолженность и предоплата',
        'товарно-материальные запасы': 'Запасы',
        'запасы': 'Запасы',
        'ндс к возмещению': 'НДС к возмещению',
        'прочие оборотные активы': 'Прочие оборотные активы',
        'основные средства': 'Основные средства',
        'активы в форме права пользования': 'Активы в форме права пользования',
        'гудвил': 'Гудвил',
        'инвестиции в ассоциированные': 'Инвестиции в ассоциированные организации и совместные предприятия',
        'долгосрочная дебиторская задолженность': 'Долгосрочная дебиторская задолженность и предоплата',
        'долгосрочные финансовые активы': 'Долгосрочные финансовые активы',
        'отложенный налоговый актив': 'Отложенный налоговый актив',
        'прочие внеоборотные активы': 'Прочие внеоборотные активы',
        'итого активы': 'Итого активы',
        'итого внеоборотные активы': 'Итого внеоборотные активы',
        'итого оборотные активы': 'Итого оборотные активы',

        # Обязательства
        'кредиторская задолженность': 'Кредиторская задолженность, оценочные и прочие обязательства',
        'задолженность по текущему налогу': 'Задолженность по текущему налогу на прибыль',
        'задолженность по налогам': 'Задолженность по налогам и сборам, кроме налога на прибыль',
        'краткосрочные кредиты': 'Краткосрочные кредиты и займы',
        'долгосрочные кредиты': 'Долгосрочные кредиты и займы, векселя к уплате',
        'долгосрочной задолженности': 'Долгосрочная задолженность по кредитам и займам',
        'оценочные обязательства': 'Оценочные обязательства',
        'отложенное налоговое обязательство': 'Отложенное налоговое обязательство',
        'долгосрочные обязательства по аренде': 'Долгосрочные обязательства по аренде',
        'прочие долгосрочные обязательства': 'Прочие долгосрочные обязательства',
        'итого обязательства': 'Итого обязательства',
        'итого краткосрочные обязательства': 'Итого краткосрочные обязательства',
        'итого долгосрочные обязательства': 'Итого долгосрочные обязательства',

        # Капитал
        'уставный капитал': 'Уставный капитал',
        'выкупленные собственные акции': 'Выкупленные собственные акции',
        'бессрочные облигации': 'Бессрочные облигации',
        'нераспределенная прибыль': 'Нераспределенная прибыль и прочие резервы',
        'неконтролирующая доля': 'Неконтролирующая доля участия',
        'неконтролирующей доле': 'Неконтролирующая доля участия',
        'итого капитал': 'Итого капитал',
        'итого обязательства и капитал': 'Итого обязательства и капитал',

        # Прибыли и убытки
        'выручка от продаж': 'Выручка от продаж',
        'выручка': 'Выручка от продаж',
        'операционные расходы': 'Операционные расходы',
        'прибыль от продаж': '(Убыток) / прибыль от продаж',
        'убыток от продаж': '(Убыток) / прибыль от продаж',
        'убыток) прибыль от продаж': '(Убыток) / прибыль от продаж',
        'прибыль (убыток) от продаж': '(Убыток) / прибыль от продаж',
        'финансовые доходы': 'Финансовые доходы',
        'финансовые расходы': 'Финансовые расходы',
        'доля в прибыли': 'Доля в прибыли ассоциированных организаций и совместных предприятий',
        'прибыль до налогообложения': 'Прибыль до налогообложения',
        'убыток до налогообложения': '(Убыток) / прибыль до налогообложения',
        'расходы по текущему налогу': 'Расходы по текущему налогу на прибыль',
        'расходы) доходы по отложенному налогу': '(Расходы) / доходы по отложенному налогу на прибыль',
        'доходы по отложенному налогу': '(Расходы) / доходы по отложенному налогу на прибыль',
        'расходы по отложенному налогу': '(Расходы) / доходы по отложенному налогу на прибыль',
        'налог на прибыль': 'Налог на прибыль',
        'прибыль за год': 'Прибыль за год',
        'убыток за год': '(Убыток) / прибыль за год',
        'прибыль (убыток) за год': '(Убыток) / прибыль за год',
        'совокупный доход за год': 'Совокупный доход за год',
        'прочий совокупный доход': 'Итого прочий совокупный доход за год',
        'акционерам пао': 'Прибыль, приходящаяся на акционеров ПАО «Газпром»',
        'акционерам пао газпром': 'Прибыль, приходящаяся на акционеров ПАО «Газпром»',

        # Денежные потоки
        'чистые денежные средства от операционной': 'Чистые денежные средства от операционной деятельности',
        'чистые денежные средства от инвестиционной': 'Чистые денежные средства от инвестиционной деятельности',
        'чистые денежные средства, использованные в финансовой': 'Чистые денежные средства, использованные в финансовой деятельности',
        'чистые денежные средства, использованные в инвестиционной': 'Чистые денежные средства, использованные в инвестиционной деятельности',
        'капитальные вложения': 'Капитальные вложения',
        'капитализированные и уплаченные проценты': 'Капитализированные и уплаченные проценты',
        'уплаченные проценты': 'Уплаченные проценты',
        'полученные проценты': 'Полученные проценты',
        'уплаченные дивиденды': 'Уплаченные дивиденды',
        'поступления от продажи дочерних': 'Поступления от продажи дочерних организаций',
        'поступления от ассоциированных': 'Поступления от ассоциированных организаций и совместных предприятий',
        'поступления по долгосрочным кредитам': 'Поступления по долгосрочным кредитам и займам',
        'поступления по краткосрочным кредитам': 'Поступления по краткосрочным кредитам и займам',
        'погашение краткосрочных кредитов': 'Погашение краткосрочных кредитов и займов',
        'погашение долгосрочной задолженности': 'Погашение долгосрочной задолженности по кредитам и займам',
        'погашение обязательств по аренде': 'Погашение обязательств по аренде',
        'выпуск бессрочных облигаций': 'Выпуск бессрочных облигаций',
        'платежи, связанные с выпуском': 'Платежи, связанные с выпуском бессрочных облигаций',
        'увеличение денежных средств': 'Увеличение денежных средств и их эквивалентов',
        'денежные средства и их эквиваленты на начало': 'Денежные средства и их эквиваленты на начало отчетного года',
        'денежные средства и их эквиваленты на конец': 'Денежные средства и их эквиваленты на конец отчетного года',
        'амортизация': 'Амортизация',
        'чистые финансовые доходы': 'Чистые финансовые доходы/(расходы)',
        'чистое изменение займов выданных': 'Чистое изменение займов выданных',
        'вложения в ассоциированные': 'Вложения в ассоциированные организации и совместные предприятия',
        'приобретение неконтролирующих': 'Приобретение неконтролирующих долей участия в дочерних организациях',
        'поступления от продажи': 'Поступления от продажи основных средств и прочих внеоборотных активов',
        'размещение денежных средств': 'Размещение денежных средств на долгосрочных банковских депозитах',
        'поступления денежных средств при закрытии': 'Поступления денежных средств при закрытии долгосрочных банковских депозитов',
        'курсовые разницы': 'Курсовые разницы',
        'влияние изменения обменного курса': 'Влияние изменения обменного курса на денежные средства и их эквиваленты',
        'убыток от операций хеджирования': 'Убыток от операций хеджирования, за вычетом налога',
        'прочее': 'Прочие денежные потоки',
        'приобретение дочерних организаций': 'Приобретение дочерних организаций за вычетом денежных средств',
    }

    # Исправление типичных ошибок OCR
    ocr_fixes = {
        'денежные': 'денежные',
        'задолженность': 'задолженность',
        'задолженности': 'задолженности',
        'матсриальные': 'материальные',
        'инвсстиции': 'инвестиции',
        'нсконтролирующей': 'неконтролирующей',
        'влюжения': 'вложения',
        'постушения': 'поступления',
        'совокупный': 'совокупный',
        'вычстом': 'вычетом',
        'эквиваленты': 'эквиваленты',
        'эквивалентов': 'эквивалентов',
        'обесценения': 'обесценения',
        'составс': 'составе',
        'канитализированные': 'капитализированные',
        'предприятий': 'предприятий',
        'налогу ha': 'налогу на',
        'приобретенных организациях': 'приобретенных организациях',
    }

    def normalize_single_name(raw_name: str) -> str:
        if not raw_name:
            return raw_name

        name = clean_text(raw_name)
        name_lower = name.lower()

        # Исправление OCR ошибок
        for wrong, correct in ocr_fixes.items():
            name_lower = name_lower.replace(wrong, correct)

        # Поиск в словаре
        for key, standard_name in standard_mapping.items():
            if key in name_lower:
                return standard_name

        # Очистка от номеров и спецсимволов в начале и конце
        cleaned = re.sub(r'^[\d\s\-—_,.()\'\"|]+', '', name).strip()
        cleaned = re.sub(r'[\s\-—_,.()\'\"|]+$', '', cleaned).strip()

        # Если после очистки осталось что-то осмысленное
        if cleaned and len(cleaned) > 3 and not cleaned.isdigit():
            # Обрезаем слишком длинные названия
            if len(cleaned) > 100:
                cleaned = cleaned[:100] + '...'
            return cleaned

        return name if name else "Неизвестный показатель"

    # Применяем нормализацию к отфильтрованным данным
    df_curated = df_filtered.copy()
    df_curated['Показатель'] = df_curated['raw_name'].apply(normalize_single_name)

    # Показываем результаты нормализации
    print("\n📊 Результаты нормализации:")

    changed = 0
    unchanged = 0
    for _, row in df_curated.iterrows():
        if row['raw_name'] != row['Показатель']:
            if changed < 10:  # Показываем первые 10 изменений
                print(f"   {row['raw_name'][:50]:50} → {row['Показатель'][:50]}")
            changed += 1
        else:
            unchanged += 1

    if changed > 10:
        print(f"   ... и еще {changed - 10} изменений")
    print(f"   ✅ Изменено: {changed}, без изменений: {unchanged}")

    # Группируем по нормализованному названию
    df_curated = df_curated.groupby('Показатель', as_index=False).first()
    df_curated['parsing_status'] = 'ok'

    # Формируем итоговые колонки
    cols = ['Показатель', 'parsing_status', 'line_id', 'page']
    cols += [c for c in df_curated.columns if 'млн руб' in c]
    cols = [c for c in cols if c in df_curated.columns]

    print(f"   📊 Итоговых показателей: {len(df_curated)}")

    return df_curated[cols]


def main():
    print("\n" + "=" * 70)
    print("📊 ЭКСТРАКТОР МСФО С OCR ПОДДЕРЖКОЙ")
    print("=" * 70)

    input_dir = RAW_DATA_DIR / "gazp_reports"
    output_dir = PROCESSED_DATA_DIR / "gazp_universal_fixed"

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = list(input_dir.glob("*.pdf"))
    if not pdf_files:
        print("❌ PDF файлы не найдены в", input_dir)
        return

    print(f"📁 Найдено {len(pdf_files)} файлов")

    for pdf_file in sorted(pdf_files):
        print(f"\n{'=' * 70}")
        print(f"📑 {pdf_file.name}")
        print(f"{'=' * 70}")

        # Определяем годы
        years = re.findall(r'20(\d{2})', pdf_file.name)
        if len(years) >= 1:
            year1 = f"20{years[0]}"
            year2 = str(int(year1) - 1)
        else:
            year1, year2 = "2021", "2020"

        print(f"   📅 Годы: {year1} и {year2}")

        # Сначала найдем страницы с таблицами через OCR нескольких страниц
        print("   🔍 Поиск страниц с отчетами...")

        report_pages = []

        # Проверяем страницы 8-15
        for page_num in range(1, 21):
            text = get_page_text_with_ocr(pdf_file, page_num, dpi=300)  # Низкое разрешение для скорости

            if text:
                text_lower = text.lower()
                # Ищем ключевые слова отчетов
                if any(kw in text_lower for kw in [
                    'бухгалтерский баланс', 'отчет о финансовом положении',
                    'отчет о совокупном доходе', 'отчет о прибылях и убытках',
                    'отчет о движении денежных средств'
                ]):
                    report_pages.append(page_num)
                    print(f"   📄 Стр. {page_num}: найдена таблица")

        if not report_pages:
            print("   ⚠️ Страницы с отчетами не найдены, пробуем 9-11")
            report_pages = [9, 10, 11]

        print(f"   📍 Обрабатываем страницы: {report_pages}")

        # Извлекаем данные с высоким разрешением
        all_data = []
        for page_num in report_pages:
            print(f"\n   --- Страница {page_num} ---")
            text = get_page_text_with_ocr(pdf_file, page_num, dpi=300)

            if text:
                df_page = extract_numbers_from_text(text, year1, year2, page_num)
                if not df_page.empty:
                    all_data.append(df_page)

        if not all_data:
            print("   ❌ Данные не извлечены")
            continue

        # Объединяем данные
        df_all = pd.concat(all_data, ignore_index=True)
        df_all = df_all.drop_duplicates(subset=['raw_name', 'page'])

        print(f"\n   📊 Всего показателей: {len(df_all)}")

        # Сохраняем сырые данные
        raw_file = output_dir / f"{pdf_file.stem}_RAW.xlsx"
        df_all.to_excel(raw_file, index=False)
        print(f"   💾 RAW: {raw_file}")

        # Нормализация
        print("\n   🔄 Нормализация...")
        df_normalized = normalize_names_hybrid(df_all)

        # Сохраняем результат
        final_file = output_dir / f"{pdf_file.stem}_NORMALIZED.xlsx"
        df_normalized.to_excel(final_file, index=False)
        print(f"   ✅ Результат: {final_file}")
        print(f"   📊 Показателей: {len(df_normalized)}")

        # Ключевые показатели
        print("\n   🔑 Ключевые показатели:")
        key_indicators = ['Выручка от продаж', 'Прибыль за год', 'Итого активы',
                          'Итого обязательства', 'Денежные средства и их эквиваленты']

        for indicator in key_indicators:
            found = df_normalized[df_normalized['Показатель'].str.contains(
                indicator, case=False, na=False)]
            if not found.empty:
                for _, row in found.iterrows():
                    year1_col = f"{year1} (млн руб)"
                    year2_col = f"{year2} (млн руб)"
                    val1 = row.get(year1_col, 'N/A')
                    val2 = row.get(year2_col, 'N/A')
                    print(f"      ✅ {row['Показатель']}: {val1:,} | {val2:,}")
            else:
                print(f"      ❌ {indicator}: НЕ НАЙДЕН")

    print("\n" + "=" * 70)
    print("✅ ГОТОВО!")
    print(f"📁 Результаты: {output_dir}")
    print("=" * 70)


if __name__ == "__main__":
    main()