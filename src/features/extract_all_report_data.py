# src/features/extract_all_report_data.py
"""
Модуль для полного извлечения данных из PDF-отчётов:
- Таблицы
- Текстовые блоки с числами
- Ключевые показатели
- Метаданные
"""

import pandas as pd
import numpy as np
import sys
import re
import json
import os
import warnings
from pathlib import Path
from collections import defaultdict
import pdfplumber
import tabula
import PyPDF2
from datetime import datetime

# Подавляем Java-предупреждения
warnings.filterwarnings("ignore", category=UserWarning, module='tabula')
os.environ['JAVA_TOOL_OPTIONS'] = '-Dorg.slf4j.simpleLogger.defaultLogLevel=error'

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import RAW_DATA_DIR, FEATURES_DIR
from config.companies import TICKERS, TICKER_TO_COMPANY


class FullReportExtractor:
    """Извлекает ВСЕ данные из PDF-отчётов"""

    def __init__(self):
        self.pdf_dir = RAW_DATA_DIR / "reports_pdf"
        self.output_dir = FEATURES_DIR / "report_data"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Паттерны для поиска финансовых показателей (рус/англ)
        self.metric_patterns = {
            # Отчёт о прибылях и убытках
            'revenue': [r'выручка', r'revenue', r'доход', r'income', r'продажи', r'sales'],
            'cost': [r'себестоимость', r'cost', r'expenses', r'расходы'],
            'gross_profit': [r'валовая прибыль', r'gross profit'],
            'operating_profit': [r'операционная прибыль', r'operating profit', r'ebit'],
            'ebitda': [r'ebitda', r'oibda'],
            'net_income': [r'чистая прибыль', r'net income', r'net profit', r'прибыль'],
            'interest_income': [r'процентные доходы', r'interest income'],
            'interest_expense': [r'процентные расходы', r'interest expense'],

            # Баланс
            'assets': [r'активы', r'assets', r'баланс'],
            'current_assets': [r'оборотные активы', r'current assets'],
            'non_current_assets': [r'внеоборотные активы', r'non-current assets'],
            'liabilities': [r'обязательства', r'liabilities'],
            'equity': [r'капитал', r'equity', r'собственные средства'],
            'debt': [r'долг', r'debt', r'займы', r'loans'],
            'cash': [r'денежные средства', r'cash', r'деньги'],
            'receivables': [r'дебиторская задолженность', r'receivables'],
            'payables': [r'кредиторская задолженность', r'payables'],

            # Денежный поток
            'operating_cashflow': [r'операционный денежный поток', r'operating cash flow', r'ocf'],
            'investing_cashflow': [r'инвестиционный денежный поток', r'investing cash flow', r'icf'],
            'financing_cashflow': [r'финансовый денежный поток', r'financing cash flow', r'fcf'],
            'capex': [r'capex', r'капзатраты', r'capital expenditures'],
            'fcf': [r'free cash flow', r'fcf', r'свободный денежный поток'],

            # Показатели эффективности
            'eps': [r'eps', r'прибыль на акцию', r'earnings per share'],
            'roe': [r'roe', r'рентабельность капитала'],
            'roa': [r'roa', r'рентабельность активов'],
            'ros': [r'ros', r'рентабельность продаж'],
            'dividend': [r'дивиденд', r'dividend'],
            'dividend_yield': [r'dividend yield', r'дивидендная доходность'],
            'payout_ratio': [r'payout', r'коэффициент выплат'],

            # Банковские показатели
            'npl': [r'npl', r'просрочка', r'non-performing'],
            'loan_portfolio': [r'кредитный портфель', r'loan portfolio'],
            'deposits': [r'депозиты', r'deposits', r'вклады'],
            'cet1': [r'cet1', r'капитал 1 уровня'],
            'nim': [r'nim', r'процентная маржа', r'interest margin'],
            'cost_income': [r'cost to income', r'cost/income', r'c/i'],

            # Нефтегазовые показатели
            'oil_production': [r'добыча нефти', r'oil production'],
            'gas_production': [r'добыча газа', r'gas production'],
            'refining': [r'переработка', r'refining'],
            'export': [r'экспорт', r'export'],
        }

        # Единицы измерения
        self.unit_patterns = {
            'million': [r'млн', r'mln', r'million'],
            'billion': [r'млрд', r'bln', r'billion'],
            'trillion': [r'трлн', r'trl', r'trillion'],
            'thousand': [r'тыс', r'thousand', r'k'],
            'percent': [r'%', r'percent', r'проц'],
        }

    def extract_all_from_pdf(self, pdf_path):
        """Извлекает ВСЕ данные из PDF"""
        print(f"\n📄 Обработка: {pdf_path.name}")

        result = {
            'filename': pdf_path.name,
            'ticker': self._extract_ticker_from_filename(pdf_path.name),
            'report_type': self._extract_report_type(pdf_path.name),
            'period': self._extract_period(pdf_path.name),
            'extraction_date': datetime.now().isoformat(),
            'tables': [],
            'text_metrics': {},
            'all_numbers': [],
            'metadata': {}
        }

        # 1. Извлекаем текст со всего PDF
        text_data = self._extract_all_text(pdf_path)
        result['metadata']['page_count'] = text_data['page_count']
        result['metadata']['total_chars'] = text_data['total_chars']

        # 2. Ищем все числа в тексте с контекстом
        numbers = self._extract_numbers_with_context(text_data['full_text'])
        result['all_numbers'] = numbers[:100]  # сохраняем первые 100 для примера

        # 3. Ищем ключевые метрики в тексте
        text_metrics = self._find_metrics_in_text(text_data['full_text'])
        result['text_metrics'] = text_metrics

        # 4. Извлекаем таблицы
        tables = self._extract_tables(pdf_path)
        result['tables'] = tables

        # 5. Парсим таблицы и ищем метрики
        table_metrics = self._find_metrics_in_tables(tables)
        result['table_metrics'] = table_metrics

        # 6. Объединяем все найденные метрики
        result['all_metrics'] = self._merge_metrics(text_metrics, table_metrics)

        return result

    def _extract_ticker_from_filename(self, filename):
        """Извлекает тикер из имени файла"""
        parts = filename.split('_')
        return parts[0] if len(parts) > 0 else 'unknown'

    def _extract_report_type(self, filename):
        """Извлекает тип отчёта"""
        parts = filename.split('_')
        if len(parts) > 1:
            return parts[1]
        return 'unknown'

    def _extract_period(self, filename):
        """Извлекает период"""
        parts = filename.split('_')
        if len(parts) > 2:
            return parts[2].replace('.pdf', '')
        return 'unknown'

    def _extract_all_text(self, pdf_path):
        """Извлекает весь текст из PDF"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                full_text = ""
                page_count = len(pdf.pages)

                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    full_text += f"\n--- PAGE {page_num} ---\n{text}\n"

                return {
                    'full_text': full_text,
                    'page_count': page_count,
                    'total_chars': len(full_text)
                }
        except Exception as e:
            print(f"   ❌ Ошибка извлечения текста: {e}")
            return {'full_text': '', 'page_count': 0, 'total_chars': 0}

    def _extract_numbers_with_context(self, text):
        """Извлекает все числа с окружающим контекстом"""
        # Ищем числа (в том числе с разделителями)
        number_pattern = r'(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?)'

        numbers = []
        lines = text.split('\n')

        for i, line in enumerate(lines):
            # Ищем числа в строке
            matches = re.finditer(number_pattern, line)
            for match in matches:
                number_str = match.group(1)
                # Очищаем число
                clean_number = self._clean_number(number_str)

                if clean_number is not None:
                    # Берём контекст (строку до и после)
                    context_before = lines[i - 1] if i > 0 else ""
                    context_after = lines[i + 1] if i < len(lines) - 1 else ""

                    numbers.append({
                        'line_number': i,
                        'raw_number': number_str,
                        'cleaned_number': clean_number,
                        'line': line.strip(),
                        'context_before': context_before.strip(),
                        'context_after': context_after.strip()
                    })

        return numbers

    def _clean_number(self, number_str):
        """Очищает число от разделителей и преобразует в float"""
        try:
            # Убираем пробелы
            cleaned = number_str.replace(' ', '').replace('\xa0', '')
            # Заменяем запятую на точку
            cleaned = cleaned.replace(',', '.')
            # Если есть несколько точек, возможно это разделители
            if cleaned.count('.') > 1:
                cleaned = cleaned.replace('.', '', cleaned.count('.') - 1)
            return float(cleaned)
        except:
            return None

    def _find_metrics_in_text(self, text):
        """Ищет ключевые метрики в тексте"""
        found_metrics = {}

        for metric_key, patterns in self.metric_patterns.items():
            for pattern in patterns:
                # Ищем в тексте паттерн и следующее за ним число
                regex = rf'{pattern}.*?(\d{{1,3}}(?:[.,\s]\d{{3}})*(?:[.,]\d+)?)'
                matches = re.finditer(regex, text, re.IGNORECASE)

                for match in matches:
                    number_str = match.group(1)
                    number = self._clean_number(number_str)

                    if number is not None:
                        # Определяем единицы измерения
                        context = text[max(0, match.start() - 50):match.end() + 50]
                        unit = self._detect_unit(context)

                        found_metrics[metric_key] = {
                            'value': number,
                            'unit': unit,
                            'context': context[:200],
                            'source': 'text'
                        }
                        break  # Берём первое найденное
                if metric_key in found_metrics:
                    break

        return found_metrics

    def _extract_tables(self, pdf_path):
        """Извлекает все таблицы из PDF"""
        try:
            tables = tabula.read_pdf(
                str(pdf_path),
                pages='all',
                multiple_tables=True,
                pandas_options={'header': None}
            )

            result = []
            for i, table in enumerate(tables):
                if not table.empty:
                    # Очищаем таблицу
                    table = table.dropna(how='all').dropna(axis=1, how='all')
                    if not table.empty:
                        # Преобразуем в список словарей для JSON
                        table_data = []
                        for _, row in table.iterrows():
                            row_data = {}
                            for j, val in enumerate(row):
                                if pd.notna(val):
                                    row_data[f'col_{j}'] = str(val)
                            if row_data:
                                table_data.append(row_data)

                        result.append({
                            'table_index': i,
                            'rows': len(table),
                            'cols': len(table.columns),
                            'data': table_data
                        })

            return result
        except Exception as e:
            print(f"   ❌ Ошибка извлечения таблиц: {e}")
            return []

    def _find_metrics_in_tables(self, tables):
        """Ищет метрики в таблицах (ИСПРАВЛЕННАЯ ВЕРСИЯ)"""
        table_metrics = {}

        for table_info in tables:
            if not table_info['data']:
                continue

            # Преобразуем данные таблицы в DataFrame для удобства
            df = pd.DataFrame(table_info['data'])

            # Ищем в каждой ячейке
            for metric_key, patterns in self.metric_patterns.items():
                if metric_key in table_metrics:
                    continue

                for pattern in patterns:
                    # Ищем паттерн в таблице
                    found = False
                    for col in df.columns:
                        # Преобразуем название колонки в строку для поиска
                        col_str = str(col)
                        # Проверяем, что колонка существует и содержит строки
                        if col_str not in df.columns:
                            continue

                        mask = df[col_str].astype(str).str.contains(pattern, case=False, na=False)
                        if mask.any():
                            # Нашли строку с метрикой
                            row_idx = mask[mask].index[0]

                            # Ищем число в этой же строке в других колонках
                            for other_col in df.columns:
                                other_col_str = str(other_col)
                                if other_col_str != col_str:
                                    # Проверяем, что колонка существует
                                    if other_col_str not in df.columns:
                                        continue

                                    val = df.loc[row_idx, other_col_str]
                                    if pd.notna(val):
                                        number = self._extract_number_from_string(val)
                                        if number is not None:
                                            # БЕЗОПАСНОЕ преобразование номера колонки
                                            # Пробуем получить число из названия колонки
                                            try:
                                                if isinstance(col, int):
                                                    col_num = col
                                                elif isinstance(col, str) and col.startswith('col_'):
                                                    col_num = int(col.replace('col_', ''))
                                                else:
                                                    col_num = 0
                                            except:
                                                col_num = 0

                                            try:
                                                if isinstance(other_col, int):
                                                    other_col_num = other_col
                                                elif isinstance(other_col, str) and other_col.startswith('col_'):
                                                    other_col_num = int(other_col.replace('col_', ''))
                                                else:
                                                    other_col_num = 0
                                            except:
                                                other_col_num = 0

                                            table_metrics[metric_key] = {
                                                'value': number,
                                                'row': int(row_idx),
                                                'col': col_num,
                                                'value_col': other_col_num,
                                                'source': 'table'
                                            }
                                            found = True
                                            break
                            if found:
                                break
                    if found:
                        break

        return table_metrics

    def _extract_number_from_string(self, s):
        """Извлекает число из строки"""
        if not isinstance(s, str):
            s = str(s)

        # Ищем число
        match = re.search(r'(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?)', s)
        if match:
            return self._clean_number(match.group(1))
        return None

    def _detect_unit(self, context):
        """Определяет единицы измерения из контекста"""
        context_lower = context.lower()

        for unit, patterns in self.unit_patterns.items():
            for pattern in patterns:
                if pattern in context_lower:
                    return unit

        return 'unknown'

    def _merge_metrics(self, text_metrics, table_metrics):
        """Объединяет метрики из текста и таблиц"""
        merged = {}

        # Сначала добавляем из таблиц (они точнее)
        for key, value in table_metrics.items():
            merged[key] = value

        # Добавляем из текста, если нет в таблицах
        for key, value in text_metrics.items():
            if key not in merged:
                merged[key] = value

        return merged

    def process_all_reports(self):
        """Обрабатывает все PDF-отчёты"""
        print("\n" + "=" * 70)
        print("🚀 ИЗВЛЕЧЕНИЕ ДАННЫХ ИЗ ВСЕХ ОТЧЁТОВ")
        print("=" * 70)

        pdf_files = list(self.pdf_dir.glob("*.pdf"))
        print(f"\n📊 Найдено PDF: {len(pdf_files)}")

        all_results = []

        for pdf_file in pdf_files:
            try:
                result = self.extract_all_from_pdf(pdf_file)
                all_results.append(result)
                print(f"   ✅ Обработан")
            except Exception as e:
                print(f"   ❌ Ошибка обработки {pdf_file.name}: {e}")
                import traceback
                traceback.print_exc()

        # Сохраняем результаты
        if all_results:
            # Сохраняем в JSON (полные данные)
            json_file = self.output_dir / "all_report_data.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)

            # Создаём сводную таблицу метрик
            metrics_summary = []
            for result in all_results:
                summary = {
                    'filename': result['filename'],
                    'ticker': result['ticker'],
                    'report_type': result['report_type'],
                    'period': result['period'],
                    'page_count': result['metadata']['page_count']
                }

                # Добавляем все найденные метрики
                for metric_key, metric_value in result['all_metrics'].items():
                    if isinstance(metric_value, dict):
                        summary[metric_key] = metric_value.get('value')
                    else:
                        summary[metric_key] = metric_value

                metrics_summary.append(summary)

            df = pd.DataFrame(metrics_summary)
            csv_file = self.output_dir / "metrics_summary.csv"
            df.to_csv(csv_file, index=False, encoding='utf-8')

            print(f"\n✅ Данные сохранены:")
            print(f"   JSON (полные): {json_file}")
            print(f"   CSV (сводка): {csv_file}")

            # Статистика
            print(f"\n📊 СТАТИСТИКА:")
            print(f"   Всего отчётов: {len(all_results)}")

            metrics_found = defaultdict(int)
            for result in all_results:
                for metric in result['all_metrics'].keys():
                    metrics_found[metric] += 1

            print(f"\n   Найденные метрики:")
            for metric, count in sorted(metrics_found.items(), key=lambda x: -x[1])[:10]:
                print(f"      {metric}: {count} отчётов")

            return df
        else:
            print("❌ Нет данных для обработки")
            return None


def main():
    extractor = FullReportExtractor()
    extractor.process_all_reports()


if __name__ == "__main__":
    main()