-- scripts/bd/db_schema.sql
-- Схема базы данных для хранения фундаментальной информации

-- Создание базы данных (выполняется один раз вручную)
-- CREATE DATABASE investment_db;
-- \c investment_db;

-- ============================================================
-- ТАБЛИЦА: Компании
-- ============================================================
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    full_code VARCHAR(30) GENERATED ALWAYS AS (exchange || ':' || code) STORED,
    name VARCHAR(200),
    country VARCHAR(100),
    currency VARCHAR(10),
    sector VARCHAR(100),
    industry VARCHAR(200),
    sub_industry VARCHAR(200),
    description TEXT,
    website VARCHAR(200),
    disclosure_link VARCHAR(200),
    report_frequency VARCHAR(10),
    is_russian BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, exchange)
);

-- ============================================================
-- ТАБЛИЦА: Финансовые отчеты (reports)
-- ============================================================
CREATE TABLE IF NOT EXISTS financial_reports (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER,
    period VARCHAR(20),
    report_type VARCHAR(50),
    is_preliminary BOOLEAN DEFAULT FALSE,

    -- Доходы и расходы
    revenue NUMERIC(20, 4),
    earnings NUMERIC(20, 4),
    ebitda NUMERIC(20, 4),
    ebit NUMERIC(20, 4),
    operating_income NUMERIC(20, 4),

    -- Баланс
    total_assets NUMERIC(20, 4),
    equity_stock_holders NUMERIC(20, 4),
    total_debt NUMERIC(20, 4),
    net_debt NUMERIC(20, 4),
    cash_and_equiv NUMERIC(20, 4),
    current_assets NUMERIC(20, 4),
    current_liabilities NUMERIC(20, 4),
    long_term_debt NUMERIC(20, 4),

    -- Денежные потоки
    cfo NUMERIC(20, 4),
    fcf NUMERIC(20, 4),
    capex NUMERIC(20, 4),

    -- Прочее
    interest_expense NUMERIC(20, 4),
    amortization NUMERIC(20, 4),

    -- На акцию
    eps NUMERIC(20, 4),
    ebitda_ps NUMERIC(20, 4),
    fcf_ps NUMERIC(20, 4),
    revenue_ps NUMERIC(20, 4),

    -- Источники
    report_link TEXT,
    changed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, year, month, period, report_type)
);

-- ============================================================
-- ТАБЛИЦА: Мультипликаторы (ratios)
-- ============================================================
CREATE TABLE IF NOT EXISTS financial_ratios (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER,
    period VARCHAR(20),
    report_type VARCHAR(50),
    is_active BOOLEAN DEFAULT FALSE,

    -- Ценовые мультипликаторы
    pe NUMERIC(20, 4),
    pbv NUMERIC(20, 4),
    ps NUMERIC(20, 4),
    pfcf NUMERIC(20, 4),

    -- Стоимостные
    evebitda NUMERIC(20, 4),

    -- Долговые
    debt_equity NUMERIC(20, 4),
    debtebitda NUMERIC(20, 4),
    netdebt_ebitda NUMERIC(20, 4),
    current_ratio NUMERIC(20, 4),
    interest_coverage NUMERIC(20, 4),

    -- Рентабельность
    roe NUMERIC(20, 4),
    roa NUMERIC(20, 4),
    roic NUMERIC(20, 4),

    -- Маржинальность
    ebitda_margin NUMERIC(20, 4),
    net_margin NUMERIC(20, 4),
    operation_margin NUMERIC(20, 4),

    -- Прочее
    capital NUMERIC(20, 4),
    changed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, year, month, period, report_type)
);

-- ============================================================
-- ТАБЛИЦА: Дивиденды
-- ============================================================
CREATE TABLE IF NOT EXISTS dividends (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    div_amount NUMERIC(20, 4),
    div_currency VARCHAR(50),
    div_percent NUMERIC(20, 4),
    last_buy_date DATE,
    reestr_close_date DATE,
    last_buy_price NUMERIC(20, 4),
    div_type VARCHAR(50),
    link TEXT,
    changed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, year, div_type)
);

-- ============================================================
-- ТАБЛИЦА: Количество акций
-- ============================================================
CREATE TABLE IF NOT EXISTS shares_outstanding (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER,
    shares_count NUMERIC(20, 4),
    changed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, year, month)
);

-- ============================================================
-- ТАБЛИЦА: Сводная информация
-- ============================================================
CREATE TABLE IF NOT EXISTS company_summary (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    capital NUMERIC(20, 4),
    eps NUMERIC(20, 4),
    dividend_yield_12m NUMERIC(20, 4),
    dividend_yield_3y NUMERIC(20, 4),
    dividend_yield_5y NUMERIC(20, 4),
    peg NUMERIC(20, 4),
    graham_target NUMERIC(20, 4),
    peter_lynch_target NUMERIC(20, 4),
    idea_consensus VARCHAR(50),
    idea_target NUMERIC(20, 4),
    idea_potential NUMERIC(20, 4),
    changed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id)
);

-- ============================================================
-- Индексы
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_financial_reports_company ON financial_reports(company_id);
CREATE INDEX IF NOT EXISTS idx_financial_reports_year ON financial_reports(year);
CREATE INDEX IF NOT EXISTS idx_financial_ratios_company ON financial_ratios(company_id);
CREATE INDEX IF NOT EXISTS idx_dividends_company ON dividends(company_id);
CREATE INDEX IF NOT EXISTS idx_shares_company ON shares_outstanding(company_id);

-- ============================================================
-- Функция обновления updated_at
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_companies_updated_at ON companies;
CREATE TRIGGER update_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
