#!/usr/bin/env python3
"""
app.py — Interactive Text-to-SQL CLI

Usage
-----
    python app.py [--llm] [--db PATH]

Options
-------
    --llm       Use OpenAI GPT instead of the rule-based translator.
                Requires OPENAI_API_KEY environment variable.
    --db PATH   Path to the SQLite database file (default: sample.db in this
                directory).
    --no-exec   Translate to SQL without executing it.

Built-in commands
-----------------
    .schema         Show the database schema
    .tables         List all tables
    .examples       Print example natural-language queries
    .help           Print this help text
    .quit / .exit   Exit the application
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Ensure the package directory is importable when run directly
sys.path.insert(0, str(Path(__file__).parent))

from database import DB_PATH, format_table, get_schema, execute_query, setup_sample_database
from translator import translate


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_BOLD = "\033[1m"
_GREEN = "\033[92m"
_CYAN = "\033[96m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_RESET = "\033[0m"


def _c(text: str, *codes: str) -> str:
    """Wrap *text* in ANSI codes if stdout is a TTY."""
    if sys.stdout.isatty():
        return "".join(codes) + text + _RESET
    return text


def _print_banner() -> None:
    banner = r"""
  ______            __     __           _____  ____  __
 /_  __/__  _  ____/ /_   / /____      / ___/ / __ \/ /
  / / / _ \| |/_/ __/  _ / __/ _ \    \__ \ / / / / /
 / / /  __/>  </ /_   ___  __/  __/  ___/ // /_/ / /___
/_/  \___/_/|_|\__/   __/\__/\___/  /____/ \___\_\____/

"""
    print(_c(banner, _CYAN, _BOLD))
    print(_c("  Natural Language → SQL Interface", _BOLD))
    print(_c("  Type .help for available commands\n", _YELLOW))


def _print_schema(schema: dict) -> None:
    for table, columns in schema.items():
        print(_c(f"\n  TABLE: {table}", _BOLD, _CYAN))
        for col in columns:
            print(f"    • {col['name']:20s} {_c(col['type'], _YELLOW)}")


def _print_examples() -> None:
    examples = [
        "Show all employees",
        "List employees with salary greater than 80000",
        "Count products",
        "Show top 5 employees ordered by salary desc",
        "Show employees and their department",
        "List products with price less than 100",
        "What is the average salary of employees?",
        "Show orders with total_amount greater than 500",
        "List all departments",
        "Show products in category Electronics",
    ]
    print(_c("\n  Example queries:", _BOLD))
    for ex in examples:
        print(f"    {_c('▸', _GREEN)} {ex}")
    print()


def _print_help() -> None:
    print(_c("\n  Built-in commands:", _BOLD))
    commands = [
        (".schema",   "Show the full database schema"),
        (".tables",   "List all table names"),
        (".examples", "Print example natural-language queries"),
        (".help",     "Show this help message"),
        (".quit",     "Exit the application"),
    ]
    for cmd, desc in commands:
        print(f"    {_c(cmd, _CYAN):<30s}  {desc}")
    print()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(
    db_path: Path = DB_PATH,
    use_llm: bool = False,
    execute: bool = True,
) -> None:
    """Run the interactive REPL."""
    # Ensure the sample database exists
    setup_sample_database(db_path)
    schema = get_schema(db_path)

    _print_banner()

    mode_label = (
        _c("LLM (OpenAI)", _GREEN) if use_llm else _c("Rule-based", _CYAN)
    )
    print(f"  Translator : {mode_label}")
    print(f"  Database   : {_c(str(db_path), _YELLOW)}")
    print(f"  Execution  : {'enabled' if execute else 'disabled (--no-exec)'}\n")

    prompt = _c("NL-SQL> ", _BOLD, _GREEN)

    while True:
        try:
            raw = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n" + _c("Goodbye!", _CYAN))
            break

        if not raw:
            continue

        # Built-in commands
        cmd = raw.lower()
        if cmd in (".quit", ".exit", "quit", "exit"):
            print(_c("Goodbye!", _CYAN))
            break
        elif cmd == ".help":
            _print_help()
            continue
        elif cmd == ".schema":
            _print_schema(schema)
            print()
            continue
        elif cmd == ".tables":
            print(_c("\n  Tables:", _BOLD))
            for t in schema:
                print(f"    • {t}")
            print()
            continue
        elif cmd == ".examples":
            _print_examples()
            continue

        # Translation
        try:
            sql, params = translate(raw, schema, use_llm=use_llm)
        except (RuntimeError, ImportError) as exc:
            print(_c(f"\n  [Translation error] {exc}\n", _RED))
            continue

        print(_c("\n  Generated SQL:", _BOLD))
        print(f"  {_c(sql, _GREEN)}")
        if params:
            print(f"  {_c('Parameters:', _YELLOW)} {params}")

        if execute and not sql.startswith("--"):
            print()
            try:
                columns, rows = execute_query(sql, db_path, params or [])
                table_str = format_table(columns, rows)
                # Indent every line
                for line in table_str.splitlines():
                    print(f"  {line}")
                print(f"\n  {_c(f'{len(rows)} row(s) returned', _YELLOW)}\n")
            except sqlite3.Error as exc:
                print(_c(f"\n  [SQL error] {exc}\n", _RED))
        else:
            print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Text-to-SQL natural language interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Use OpenAI GPT for translation (requires OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        type=Path,
        default=DB_PATH,
        help="Path to the SQLite database (default: sample.db)",
    )
    parser.add_argument(
        "--no-exec",
        action="store_true",
        help="Only show generated SQL without executing it",
    )
    args = parser.parse_args()

    run(db_path=args.db, use_llm=args.llm, execute=not args.no_exec)


if __name__ == "__main__":
    main()
