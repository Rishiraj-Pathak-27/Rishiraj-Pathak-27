"""
database.py — SQLite database setup, schema introspection, and query execution.
"""

import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "sample.db"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Return a connection to the SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def setup_sample_database(db_path: Path = DB_PATH) -> None:
    """Create and populate the sample database with demo tables."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS departments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL UNIQUE,
            location   TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS employees (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name    TEXT    NOT NULL,
            last_name     TEXT    NOT NULL,
            email         TEXT    NOT NULL UNIQUE,
            salary        REAL    NOT NULL,
            hire_date     TEXT    NOT NULL,
            department_id INTEGER REFERENCES departments(id)
        );

        CREATE TABLE IF NOT EXISTS products (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT    NOT NULL UNIQUE,
            category TEXT    NOT NULL,
            price    REAL    NOT NULL,
            stock    INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS orders (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id  INTEGER REFERENCES employees(id),
            product_id   INTEGER REFERENCES products(id),
            quantity     INTEGER NOT NULL,
            order_date   TEXT    NOT NULL,
            total_amount REAL    NOT NULL
        );
        """
    )
    conn.commit()

    # Only seed data when all application tables are empty to avoid duplicates
    cursor.execute("SELECT COUNT(*) FROM employees")
    if cursor.fetchone()[0] == 0:
        cursor.executescript(
            """
            INSERT INTO departments (name, location) VALUES
                ('Engineering',  'New York'),
                ('Marketing',    'San Francisco'),
                ('Sales',        'Chicago'),
                ('HR',           'Boston'),
                ('Finance',      'Dallas');

            INSERT INTO employees
                (first_name, last_name, email, salary, hire_date, department_id) VALUES
                ('Alice',   'Johnson',  'alice@example.com',   95000, '2020-03-15', 1),
                ('Bob',     'Smith',    'bob@example.com',     72000, '2019-07-22', 2),
                ('Carol',   'Williams', 'carol@example.com',   88000, '2021-01-10', 1),
                ('David',   'Brown',    'david@example.com',   65000, '2018-11-05', 3),
                ('Emma',    'Davis',    'emma@example.com',    91000, '2022-06-30', 1),
                ('Frank',   'Miller',   'frank@example.com',   54000, '2017-09-18', 4),
                ('Grace',   'Wilson',   'grace@example.com',   78000, '2020-12-01', 2),
                ('Henry',   'Moore',    'henry@example.com',   62000, '2019-04-14', 3),
                ('Ivy',     'Taylor',   'ivy@example.com',     83000, '2021-08-20', 5),
                ('Jack',    'Anderson', 'jack@example.com',    97000, '2016-02-28', 1);

            INSERT INTO products (name, category, price, stock) VALUES
                ('Laptop Pro',      'Electronics', 1299.99, 50),
                ('Wireless Mouse',  'Electronics',   29.99, 200),
                ('Standing Desk',   'Furniture',    499.99, 30),
                ('Office Chair',    'Furniture',    349.99, 45),
                ('Notebook Pack',   'Stationery',    12.99, 500),
                ('Monitor 27"',     'Electronics',  399.99, 80),
                ('Keyboard',        'Electronics',   79.99, 150),
                ('Headphones',      'Electronics',  149.99, 100),
                ('Whiteboard',      'Office',       129.99, 25),
                ('Coffee Maker',    'Appliances',    89.99, 60);

            INSERT INTO orders
                (employee_id, product_id, quantity, order_date, total_amount) VALUES
                (1, 1, 1, '2024-01-05', 1299.99),
                (2, 2, 3, '2024-01-12',   89.97),
                (3, 3, 1, '2024-01-18',  499.99),
                (4, 5, 5, '2024-02-03',   64.95),
                (5, 6, 2, '2024-02-10',  799.98),
                (1, 7, 1, '2024-02-14',   79.99),
                (6, 4, 1, '2024-02-20',  349.99),
                (7, 8, 2, '2024-03-01',  299.98),
                (8, 9, 1, '2024-03-07',  129.99),
                (9, 10,1, '2024-03-15',   89.99);
            """
        )
        conn.commit()

    conn.close()


def get_schema(db_path: Path = DB_PATH) -> dict[str, list[dict[str, str]]]:
    """
    Return a dict mapping each table name to a list of column descriptors.

    Example:
        {
            "employees": [
                {"name": "id",         "type": "INTEGER"},
                {"name": "first_name", "type": "TEXT"},
                ...
            ],
            ...
        }
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [row["name"] for row in cursor.fetchall()]

    schema: dict[str, list[dict[str, str]]] = {}
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")  # noqa: S608 — table names from schema, not user input
        schema[table] = [
            {"name": col["name"], "type": col["type"]} for col in cursor.fetchall()
        ]
    conn.close()
    return schema


def execute_query(
    sql: str, db_path: Path = DB_PATH, params: list | None = None
) -> tuple[list[str], list[tuple[Any, ...]]]:
    """
    Execute *sql* (with optional *params*) and return (column_names, rows).

    Raises ``sqlite3.Error`` on failure.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(sql, params or [])
    columns = [description[0] for description in (cursor.description or [])]
    rows = [tuple(row) for row in cursor.fetchall()]
    conn.close()
    return columns, rows


def format_table(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    """Render query results as a plain-text table."""
    if not columns:
        return "(no columns returned)"
    if not rows:
        return "(no results)"

    col_widths = [len(c) for c in columns]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header = (
        "|"
        + "|".join(f" {col:<{col_widths[i]}} " for i, col in enumerate(columns))
        + "|"
    )
    lines = [separator, header, separator]
    for row in rows:
        lines.append(
            "|"
            + "|".join(f" {str(val):<{col_widths[i]}} " for i, val in enumerate(row))
            + "|"
        )
    lines.append(separator)
    return "\n".join(lines)
