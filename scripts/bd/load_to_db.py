#!/usr/bin/env python3
# scripts/bd/load_to_db.py
"""
Загрузка данных из JSON файлов в PostgreSQL
"""

import json
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
from typing import Dict, List, Optional
from config import DB_CONFIG, BD_COMPANIES_DIR

# Для отладки
print(f"📁 Поиск файлов в: {BD_COMPANIES_DIR}")
print(f"📁 Существует: {BD_COMPANIES_DIR.exists()}")


def get_db_connection():
    """Создает соединение с PostgreSQL"""
    return psycopg2.connect(**DB_CONFIG)


def get_or_create_company(conn, data: Dict) -> Optional[int]:
    """Получает ID компании или создает новую"""
    info = data.get("info", {})
    code = info.get("code")
    exchange = info.get("exchange")

    if not code or not exchange:
        return None

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM companies WHERE code = %s AND exchange = %s",
            (code, exchange)
        )
        result = cur.fetchone()

        if result:
            return result[0]

        is_russian = exchange in ["MOEX", "SPB"]

        cur.execute("""
            INSERT INTO companies (
                code, exchange, name, country, currency, 
                sector, industry, sub_industry, description, 
                website, disclosure_link, report_frequency, is_russian
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            code, exchange,
            info.get("name"), info.get("country"), info.get("currency"),
            info.get("sector"), info.get("industry"), info.get("sub_industry"),
            info.get("description"), info.get("site"), info.get("disc_link"),
            info.get("report_frequency"), is_russian
        ))

        company_id = cur.fetchone()[0]
        conn.commit()
        print(f"   🆕 Создана новая компания: {exchange}:{code}")
        return company_id


def load_reports(conn, company_id: int, reports: List[Dict]):
    """Загружает финансовые отчеты"""
    if not reports:
        return

    with conn.cursor() as cur:
        cur.execute("DELETE FROM financial_reports WHERE company_id = %s", (company_id,))

        values = []
        for report in reports:
            if not report.get("year"):
                continue

            values.append((
                company_id,
                report.get("year"),
                report.get("month"),
                report.get("period"),
                report.get("type"),
                report.get("preliminary", False),
                report.get("revenue"),
                report.get("earnings"),
                report.get("ebitda"),
                report.get("ebit"),
                report.get("operating_income"),
                report.get("total_assets"),
                report.get("equity_stock_holders"),
                report.get("total_debt"),
                report.get("net_debt"),
                report.get("cash_and_equiv"),
                report.get("current_assets"),
                report.get("current_liabilities"),
                report.get("long_term_debt"),
                report.get("cfo"),
                report.get("fcf"),
                report.get("capex"),
                report.get("interest_expense"),
                report.get("amortization"),
                report.get("earnings_ps"),
                report.get("ebitda_ps"),
                report.get("fcf_ps"),
                report.get("revenue_ps"),
                report.get("link"),
                report.get("changed_at")
            ))

        if values:
            execute_values(cur, """
                INSERT INTO financial_reports (
                    company_id, year, month, period, report_type, is_preliminary,
                    revenue, earnings, ebitda, ebit, operating_income,
                    total_assets, equity_stock_holders, total_debt, net_debt,
                    cash_and_equiv, current_assets, current_liabilities, long_term_debt,
                    cfo, fcf, capex, interest_expense, amortization,
                    eps, ebitda_ps, fcf_ps, revenue_ps,
                    report_link, changed_at
                ) VALUES %s
            """, values)

            conn.commit()
            print(f"   📄 Загружено {len(values)} отчетов")


def load_ratios(conn, company_id: int, ratios: List[Dict]):
    """Загружает мультипликаторы"""
    if not ratios:
        return

    with conn.cursor() as cur:
        cur.execute("DELETE FROM financial_ratios WHERE company_id = %s", (company_id,))

        values = []
        for ratio in ratios:
            if not ratio.get("year"):
                continue

            values.append((
                company_id,
                ratio.get("year"),
                ratio.get("month"),
                ratio.get("period"),
                ratio.get("type"),
                ratio.get("active", False),
                ratio.get("pe"),
                ratio.get("pbv"),
                ratio.get("ps"),
                ratio.get("pfcf"),
                ratio.get("evebitda"),
                ratio.get("debt_equity"),
                ratio.get("debtebitda"),
                ratio.get("netdebt_ebitda"),
                ratio.get("current_ratio"),
                ratio.get("interest_coverage"),
                ratio.get("roe"),
                ratio.get("roa"),
                ratio.get("roic"),
                ratio.get("ebitda_margin"),
                ratio.get("net_margin"),
                ratio.get("operation_margin"),
                ratio.get("capital"),
                ratio.get("changed_at")
            ))

        if values:
            execute_values(cur, """
                INSERT INTO financial_ratios (
                    company_id, year, month, period, report_type, is_active,
                    pe, pbv, ps, pfcf, evebitda,
                    debt_equity, debtebitda, netdebt_ebitda,
                    current_ratio, interest_coverage,
                    roe, roa, roic,
                    ebitda_margin, net_margin, operation_margin,
                    capital, changed_at
                ) VALUES %s
            """, values)

            conn.commit()
            print(f"   📊 Загружено {len(values)} записей коэффициентов")


def load_dividends(conn, company_id: int, dividends: List[Dict]):
    """Загружает дивиденды с пропуском дубликатов"""
    if not dividends:
        return

    with conn.cursor() as cur:
        # Не удаляем старые записи!
        # Добавляем только новые, пропуская дубликаты

        values = []
        for div in dividends:
            values.append((
                company_id,
                div.get("year"),
                div.get("div_amount"),
                div.get("div_curr", "RUB"),
                div.get("div_percent"),
                div.get("last_buy_date"),
                div.get("reestr_close_date"),
                div.get("last_buy_price"),
                div.get("type"),
                div.get("link"),
                div.get("changed_at")
            ))

        if values:
            # ON CONFLICT DO NOTHING - пропускаем дубликаты без ошибки
            execute_values(cur, """
                INSERT INTO dividends (
                    company_id, year, div_amount, div_currency, div_percent,
                    last_buy_date, reestr_close_date, last_buy_price,
                    div_type, link, changed_at
                ) VALUES %s
                ON CONFLICT (company_id, year, div_type) DO NOTHING
            """, values)

            conn.commit()
            print(f"   💰 Загружено {len(values)} дивидендов (дубликаты пропущены)")


def load_shares(conn, company_id: int, shares: List[Dict]):
    """Загружает количество акций с пропуском дубликатов"""
    if not shares:
        return

    with conn.cursor() as cur:
        values = []
        for share in shares:
            values.append((
                company_id,
                share.get("year"),
                share.get("month", 12),
                share.get("num"),
                share.get("changed_at")
            ))

        if values:
            execute_values(cur, """
                INSERT INTO shares_outstanding (
                    company_id, year, month, shares_count, changed_at
                ) VALUES %s
                ON CONFLICT (company_id, year, month) DO NOTHING
            """, values)

            conn.commit()
            print(f"   📈 Загружено {len(values)} записей об акциях (дубликаты пропущены)")


def load_summary(conn, company_id: int, summary: Dict):
    """Загружает сводную информацию"""
    if not summary:
        return

    with conn.cursor() as cur:
        cur.execute("DELETE FROM company_summary WHERE company_id = %s", (company_id,))

        cur.execute("""
            INSERT INTO company_summary (
                company_id, capital, eps, dividend_yield_12m,
                dividend_yield_3y, dividend_yield_5y, peg,
                graham_target, peter_lynch_target,
                idea_consensus, idea_target, idea_potential, changed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            company_id,
            summary.get("capital"),
            summary.get("eps"),
            summary.get("dividend_yield_12m"),
            summary.get("dividend_yield_3y"),
            summary.get("dividend_yield_5y"),
            summary.get("peg"),
            summary.get("graham_target"),
            summary.get("peter_lynch_target"),
            summary.get("idea_consensus"),
            summary.get("idea_target"),
            summary.get("idea_potential"),
            summary.get("changed_at")
        ))

        conn.commit()
        print(f"   📝 Загружена сводная информация")


def process_company_file(conn, filepath: Path):
    """Обрабатывает один JSON файл с отдельными транзакциями для каждой таблицы"""
    print(f"\n📄 {filepath.name}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Получаем или создаем компанию (отдельная транзакция)
    company_id = get_or_create_company(conn, data)
    if not company_id:
        print(f"   ⚠️ Не удалось определить компанию")
        return

    # Загружаем каждую таблицу в отдельной транзакции
    # Так ошибка в одной не помешает другим

    try:
        load_reports(conn, company_id, data.get("reports", []))
    except Exception as e:
        print(f"   ⚠️ Ошибка при загрузке отчетов: {e}")
        conn.rollback()

    try:
        load_ratios(conn, company_id, data.get("ratios", []))
    except Exception as e:
        print(f"   ⚠️ Ошибка при загрузке коэффициентов: {e}")
        conn.rollback()

    try:
        load_dividends(conn, company_id, data.get("dividends", []))
    except Exception as e:
        print(f"   ⚠️ Ошибка при загрузке дивидендов: {e}")
        conn.rollback()

    try:
        load_shares(conn, company_id, data.get("shares", []))
    except Exception as e:
        print(f"   ⚠️ Ошибка при загрузке акций: {e}")
        conn.rollback()

    try:
        load_summary(conn, company_id, data.get("summary", {}))
    except Exception as e:
        print(f"   ⚠️ Ошибка при загрузке сводки: {e}")
        conn.rollback()


def main():
    print("=" * 70)
    print("📥 ЗАГРУЗКА ДАННЫХ В POSTGRESQL")
    print("=" * 70)

    json_files = list(BD_COMPANIES_DIR.glob("MOEX_*.json"))
    print(f"\n📁 Найдено {len(json_files)} файлов с данными компаний")

    if not json_files:
        print("❌ Нет файлов для обработки")
        return

    try:
        conn = get_db_connection()
        print("✅ Подключение к PostgreSQL установлено")

        for i, filepath in enumerate(json_files, 1):
            print(f"\n[{i}/{len(json_files)}]", end=" ")
            try:
                process_company_file(conn, filepath)
            except Exception as e:
                print(f"   ❌ Ошибка: {e}")
                conn.rollback()  # <-- Добавьте эту строку
                continue

        print("\n" + "=" * 70)
        print("✅ ЗАГРУЗКА ЗАВЕРШЕНА!")

    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()