# 🧠 Text-to-SQL Natural Language Interface

A lightweight, self-contained Python application that lets you query a SQL database using plain English.

No mandatory external dependencies — the rule-based translator works entirely with the Python standard library. An optional LLM mode (OpenAI GPT) is available for more complex queries.

---

## ✨ Features

| Feature | Description |
|---|---|
| **Rule-based translator** | Handles SELECT, WHERE, GROUP BY, ORDER BY, LIMIT, JOINs and aggregate functions using pattern matching |
| **LLM translator** | Delegates to OpenAI GPT-4o-mini when `OPENAI_API_KEY` is set |
| **Sample database** | Auto-generated SQLite DB with `employees`, `departments`, `products`, and `orders` tables |
| **Interactive REPL** | Coloured CLI with built-in schema explorer and example queries |
| **Parameterised queries** | Bind parameters are used to prevent SQL injection in the rule-based path |

---

## 🚀 Quick Start

```bash
# 1 — Clone / navigate to the project
cd text_to_sql

# 2 — (Optional) create a virtual environment
python -m venv .venv && source .venv/bin/activate

# 3 — Run the interactive CLI (no dependencies needed)
python app.py
```

The first run creates `sample.db` automatically.

---

## 💡 Example Queries

```
NL-SQL> Show all employees
NL-SQL> List employees with salary greater than 80000
NL-SQL> How many products are there?
NL-SQL> Show top 5 employees ordered by salary desc
NL-SQL> What is the average salary?
NL-SQL> Show employees and their department
NL-SQL> List products with price less than 100
NL-SQL> Show orders with total_amount greater than 500
```

---

## 🗄️ Database Schema

```
departments  (id, name, location)
employees    (id, first_name, last_name, email, salary, hire_date, department_id)
products     (id, name, category, price, stock)
orders       (id, employee_id, product_id, quantity, order_date, total_amount)
```

Type `.schema` in the REPL to see the full schema at any time.

---

## 🤖 LLM Mode (Optional)

Set your OpenAI API key and pass `--llm` to use GPT-4o-mini for translation:

```bash
export OPENAI_API_KEY="sk-..."
python app.py --llm
```

Install the optional dependency:

```bash
pip install openai
```

---

## ⚙️ CLI Options

```
python app.py [--llm] [--db PATH] [--no-exec]

  --llm        Use OpenAI GPT (requires OPENAI_API_KEY)
  --db PATH    Custom database path (default: sample.db)
  --no-exec    Show generated SQL without executing it
```

---

## 🧪 Running Tests

```bash
pip install pytest
pytest ../tests/test_translator.py -v
```

---

## 📂 Project Structure

```
text_to_sql/
├── app.py            # Interactive CLI entry point
├── database.py       # SQLite setup, schema introspection, query execution
├── translator.py     # Natural-language → SQL (rule-based + LLM)
├── requirements.txt  # Optional dependencies
└── README.md         # This file

tests/
└── test_translator.py  # Unit + integration tests
```

---

## 🔒 Security Notes

- The rule-based translator uses **parameterised queries** (bind parameters) to prevent SQL injection.
- The LLM translator produces SQL that is executed read-only; no DDL or DML statements are issued from user input.
- The `OPENAI_API_KEY` is read from the environment and never written to disk.
