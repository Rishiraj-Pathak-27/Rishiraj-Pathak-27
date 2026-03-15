"""
tests/test_translator.py — Unit tests for the rule-based NL→SQL translator.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make sure the text_to_sql package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from text_to_sql.database import (
    get_schema,
    execute_query,
    format_table,
    setup_sample_database,
)
from text_to_sql.translator import rule_based_translate, translate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tmp_db(tmp_path_factory) -> Path:
    """Return a path to a fully populated temporary SQLite database."""
    db = tmp_path_factory.mktemp("db") / "test.db"
    setup_sample_database(db)
    return db


@pytest.fixture(scope="module")
def schema(tmp_db) -> dict:
    return get_schema(tmp_db)


# ---------------------------------------------------------------------------
# database.py tests
# ---------------------------------------------------------------------------


class TestSetupDatabase:
    def test_tables_created(self, schema):
        assert set(schema.keys()) == {"departments", "employees", "orders", "products"}

    def test_employees_columns(self, schema):
        col_names = {c["name"] for c in schema["employees"]}
        assert {"id", "first_name", "last_name", "email", "salary", "hire_date"} <= col_names

    def test_sample_data_loaded(self, tmp_db):
        cols, rows = execute_query("SELECT COUNT(*) FROM employees", tmp_db)
        assert rows[0][0] >= 10

    def test_products_data_loaded(self, tmp_db):
        cols, rows = execute_query("SELECT COUNT(*) FROM products", tmp_db)
        assert rows[0][0] >= 10


class TestFormatTable:
    def test_empty_rows(self):
        result = format_table(["id", "name"], [])
        assert "no results" in result

    def test_no_columns(self):
        result = format_table([], [])
        assert "no columns" in result

    def test_renders_header_and_separator(self):
        result = format_table(["id", "name"], [(1, "Alice"), (2, "Bob")])
        assert "id" in result
        assert "Alice" in result
        assert "+" in result


# ---------------------------------------------------------------------------
# translator.py — rule_based_translate tests
# ---------------------------------------------------------------------------


class TestRuleBasedTranslate:
    # --- table detection ---

    def test_select_all_employees(self, schema):
        sql, params = rule_based_translate("Show all employees", schema)
        assert "SELECT" in sql.upper()
        assert "employees" in sql.lower()
        assert params == []

    def test_select_all_products(self, schema):
        sql, _ = rule_based_translate("List all products", schema)
        assert "products" in sql.lower()

    def test_unknown_table_comment(self, schema):
        sql, _ = rule_based_translate("What is the weather today?", schema)
        assert sql.startswith("--")

    # --- WHERE clause ---

    def test_salary_greater_than(self, schema):
        sql, params = rule_based_translate(
            "Show employees with salary greater than 80000", schema
        )
        assert "WHERE" in sql.upper()
        assert "salary" in sql.lower()
        assert ">" in sql
        assert 80000 in params

    def test_price_less_than(self, schema):
        sql, params = rule_based_translate(
            "List products with price less than 100", schema
        )
        assert "WHERE" in sql.upper()
        assert "<" in sql
        assert 100 in params

    # --- Aggregate functions ---

    def test_count(self, schema):
        sql, _ = rule_based_translate("How many employees are there?", schema)
        assert "COUNT" in sql.upper()

    def test_average_salary(self, schema):
        sql, _ = rule_based_translate("What is the average salary?", schema)
        assert "AVG" in sql.upper()

    def test_max_salary(self, schema):
        sql, _ = rule_based_translate("What is the maximum salary?", schema)
        assert "MAX" in sql.upper()

    # --- ORDER BY ---

    def test_order_by_salary_desc(self, schema):
        sql, _ = rule_based_translate(
            "Show top 5 employees ordered by salary desc", schema
        )
        assert "ORDER BY" in sql.upper()
        assert "DESC" in sql.upper()

    def test_limit_clause(self, schema):
        sql, _ = rule_based_translate("Show top 3 employees", schema)
        assert "LIMIT 3" in sql.upper()

    # --- JOIN ---

    def test_join_employees_departments(self, schema):
        sql, _ = rule_based_translate(
            "Show employees and their department", schema
        )
        assert "JOIN" in sql.upper()
        assert "departments" in sql.lower()

    # --- translate() wrapper ---

    def test_translate_defaults_to_rule_based(self, schema):
        sql, params = translate("Count products", schema, use_llm=False)
        assert "COUNT" in sql.upper()
        assert "products" in sql.lower()


# ---------------------------------------------------------------------------
# Integration — execute the generated SQL against the real DB
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_select_all_employees_executes(self, tmp_db, schema):
        sql, params = rule_based_translate("Show all employees", schema)
        assert not sql.startswith("--")
        cols, rows = execute_query(sql, tmp_db)
        assert len(rows) >= 10

    def test_count_employees_executes(self, tmp_db, schema):
        sql, params = rule_based_translate("How many employees are there?", schema)
        cols, rows = execute_query(sql, tmp_db)
        assert rows[0][0] >= 10

    def test_salary_filter_executes(self, tmp_db, schema):
        sql, params = rule_based_translate(
            "Show employees with salary greater than 80000", schema
        )
        cols, rows = execute_query(sql, tmp_db, params)
        # All returned employees must have salary > 80000
        salary_idx = cols.index("salary")
        for row in rows:
            assert row[salary_idx] > 80000

    def test_top_5_limit_executes(self, tmp_db, schema):
        sql, params = rule_based_translate(
            "Show top 5 employees ordered by salary desc", schema
        )
        cols, rows = execute_query(sql, tmp_db)
        assert len(rows) <= 5

    def test_join_executes(self, tmp_db, schema):
        sql, params = rule_based_translate(
            "Show employees and their department", schema
        )
        cols, rows = execute_query(sql, tmp_db)
        assert "department_name" in cols
