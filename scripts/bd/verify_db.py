#!/usr/bin/env python3
# scripts/bd/verify_db.py
"""
Проверка загруженных данных в PostgreSQL
"""

import psycopg2
from config import DB_CONFIG


def verify_database():
    """Проверяет количество записей в таблицах"""

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        print("=" * 70)
        print("📊 СТАТИСТИКА БАЗЫ ДАННЫХ")
        print("=" * 70)

        # Компании
        cur.execute("SELECT COUNT(*) FROM companies")
        companies_count = cur.fetchone()[0]
        print(f"\n🏢 Компаний: {companies_count}")

        if companies_count > 0:
            cur.execute("""
                SELECT code, name, sector 
                FROM companies 
                LIMIT 10
            """)
            print("\n   Примеры компаний:")
            for row in cur.fetchall():
                print(f"      • {row[0]} - {row[1][:40]} ({row[2]})")

        # Отчеты
        cur.execute("SELECT COUNT(*) FROM financial_reports")
        reports_count = cur.fetchone()[0]
        print(f"\n📄 Финансовых отчетов: {reports_count}")

        # Коэффициенты
        cur.execute("SELECT COUNT(*) FROM financial_ratios")
        ratios_count = cur.fetchone()[0]
        print(f"📊 Записей коэффициентов: {ratios_count}")

        # Дивиденды
        cur.execute("SELECT COUNT(*) FROM dividends")
        dividends_count = cur.fetchone()[0]
        print(f"💰 Дивидендов: {dividends_count}")

        # Акции
        cur.execute("SELECT COUNT(*) FROM shares_outstanding")
        shares_count = cur.fetchone()[0]
        print(f"📈 Записей об акциях: {shares_count}")

        # Сводка
        cur.execute("SELECT COUNT(*) FROM company_summary")
        summary_count = cur.fetchone()[0]
        print(f"📝 Сводных записей: {summary_count}")

        # Проверка данных по Газпрому
        print("\n" + "=" * 70)
        print("🔍 ПРОВЕРКА ДАННЫХ ПО ГАЗПРОМУ")
        print("=" * 70)

        cur.execute("""
            SELECT c.code, fr.year, fr.revenue, fr.earnings, fr.eps
            FROM financial_reports fr
            JOIN companies c ON c.id = fr.company_id
            WHERE c.code = 'GAZP' AND fr.period = 'Y' AND fr.report_type = 'МСФО'
            ORDER BY fr.year DESC
            LIMIT 5
        """)

        print("\n   Последние 5 лет (МСФО):")
        for row in cur.fetchall():
            print(f"      {row[0]} {row[1]}: выручка={row[2]:,.0f}, прибыль={row[3]:,.0f}, EPS={row[4]:.2f}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    verify_database()