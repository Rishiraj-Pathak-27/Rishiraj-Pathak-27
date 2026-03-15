"""
translator.py — Natural-language to SQL translator.

Two strategies are supported:

1. **Rule-based** (zero external dependencies, always available):
   Parses common English patterns and maps them to parameterised SQL templates
   using the live database schema.

2. **LLM-based** (requires ``openai`` package and ``OPENAI_API_KEY`` env var):
   Sends the schema + user query to an OpenAI chat model and extracts the SQL
   from the response.  Only activated when the environment variable is set.
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AGGREGATE_KEYWORDS: dict[str, str] = {
    "count": "COUNT(*)",
    "how many": "COUNT(*)",
    "total": "SUM({col})",
    "sum": "SUM({col})",
    "average": "AVG({col})",
    "avg": "AVG({col})",
    "maximum": "MAX({col})",
    "max": "MAX({col})",
    "minimum": "MIN({col})",
    "min": "MIN({col})",
}

_COMPARISON_PATTERNS: list[tuple[str, str]] = [
    (r"(?:greater|more|higher|above|over) than\s+([\d.]+)", ">"),
    (r"(?:less|lower|below|under) than\s+([\d.]+)", "<"),
    (r"(?:at least|no less than|>=?)\s*([\d.]+)", ">="),
    (r"(?:at most|no more than|<=?)\s*([\d.]+)", "<="),
    (r"(?:equal(?:s)? to|=|is)\s+([\d.]+)", "="),
    (r"(?:not equal to|!=|is not)\s+([\d.]+)", "!="),
]

_ORDER_PATTERNS: list[tuple[str, str]] = [
    (r"(?:order|sort)\s+by\s+(\w+)\s*(desc(?:ending)?)?", ""),
    (r"(?:highest|largest|biggest|most expensive)\s+(\w+)?", "DESC"),
    (r"(?:lowest|smallest|least expensive|cheapest)\s+(\w+)?", "ASC"),
]


def _find_table(query_lower: str, schema: dict) -> str | None:
    """Return the table name most relevant to *query_lower*.

    Priority:
    1. Exact table name present in the query string (longest / earliest wins).
    2. Singular stem of the table name (``employees`` → ``employee``) present.
    3. A column name belonging to the table appears in the query.
    """
    # Pass 1 — exact table name match; prefer longer names and earlier positions
    exact_matches: list[tuple[int, int, str]] = []
    for table in schema:
        if table in query_lower:
            pos = query_lower.index(table)
            exact_matches.append((pos, -len(table), table))
    if exact_matches:
        exact_matches.sort()  # sort by (position, -length) → earliest & longest wins
        return exact_matches[0][2]

    # Pass 2 — singular stem match (remove only the final 's' if present)
    for table in schema:
        stem = table[:-1] if table.endswith("s") else table
        if stem and len(stem) >= 3 and stem in query_lower:
            return table

    # Pass 3 — column name inference
    for word in re.split(r"\W+", query_lower):
        if not word:
            continue
        for table, columns in schema.items():
            for col in columns:
                if col["name"].lower() == word:
                    return table

    return None


def _find_columns(
    query_lower: str, table: str, schema: dict
) -> list[str]:
    """Return column names from *table* that appear in *query_lower*."""
    cols = schema.get(table, [])
    mentioned = [c["name"] for c in cols if c["name"].lower() in query_lower]
    return mentioned


def _build_select_clause(query_lower: str, table: str, schema: dict) -> str:
    """Determine the SELECT clause."""
    # Check for aggregate functions
    for keyword, agg_template in _AGGREGATE_KEYWORDS.items():
        if keyword in query_lower:
            # Try to find a numeric column for sum/avg/max/min
            if "{col}" in agg_template:
                numeric_cols = [
                    c["name"]
                    for c in schema.get(table, [])
                    if any(t in c["type"].upper() for t in ("INT", "REAL", "FLOAT", "NUMERIC"))
                ]
                for col in numeric_cols:
                    if col.lower() in query_lower:
                        return agg_template.format(col=col)
                # Fallback to first numeric column
                if numeric_cols:
                    return agg_template.format(col=numeric_cols[0])
            return agg_template
    return "*"


def _build_where_clause(
    query_lower: str, table: str, schema: dict
) -> tuple[str, list]:
    """Build a WHERE clause and its bind parameters."""
    conditions: list[str] = []
    params: list = []

    cols = {c["name"].lower(): c for c in schema.get(table, [])}

    # Numeric comparisons
    for pattern, operator in _COMPARISON_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            value = match.group(1)
            # Find the nearest column mention before the comparison
            before = query_lower[: match.start()]
            col_found = None
            for col_name in cols:
                if col_name in before:
                    col_found = col_name
                    break  # use the first matching column found
            if col_found:
                conditions.append(f"{col_found} {operator} ?")
                params.append(float(value) if "." in value else int(value))

    # Equality on text columns: "where <col> is <value>" or "<col> = <value>"
    text_eq_pattern = re.compile(
        r"\b(\w+)\s+(?:is|=|equals?|named?|called)\s+['\"]?([a-z0-9 _]+)['\"]?",
        re.IGNORECASE,
    )
    for match in text_eq_pattern.finditer(query_lower):
        col_candidate = match.group(1).lower()
        val_candidate = match.group(2).strip()
        if col_candidate in cols:
            conditions.append(f"{col_candidate} = ?")
            params.append(val_candidate)

    # LIKE match for text columns containing a keyword
    like_pattern = re.compile(
        r"\b(?:containing?|with|like|having)\s+['\"]?([a-z0-9 _]+)['\"]?",
        re.IGNORECASE,
    )
    for match in like_pattern.finditer(query_lower):
        val = match.group(1).strip()
        # Find a text column
        for col_name, col_info in cols.items():
            if "TEXT" in col_info["type"].upper() and col_name in query_lower:
                conditions.append(f"{col_name} LIKE ?")
                params.append(f"%{val}%")
                break

    clause = " AND ".join(conditions)
    return (f"WHERE {clause}" if clause else ""), params


def _build_order_clause(query_lower: str, table: str, schema: dict) -> str:
    """Build an ORDER BY clause if the query asks for ordering."""
    cols = {c["name"].lower() for c in schema.get(table, [])}

    explicit = re.search(
        r"(?:order(?:ed)?|sort(?:ed)?)\s+by\s+(\w+)(?:\s+(asc(?:ending)?|desc(?:ending)?))?",
        query_lower,
    )
    if explicit:
        col = explicit.group(1).lower()
        direction = "DESC" if "desc" in (explicit.group(2) or "").lower() else "ASC"
        if col in cols:
            return f"ORDER BY {col} {direction}"

    # Implicit ordering keywords
    if re.search(r"\b(?:top|highest|largest|most expensive|richest)\b", query_lower):
        numeric = [
            c["name"]
            for c in schema.get(table, [])
            if any(t in c["type"].upper() for t in ("INT", "REAL", "FLOAT", "NUMERIC"))
        ]
        if numeric:
            return f"ORDER BY {numeric[0]} DESC"

    if re.search(r"\b(?:lowest|cheapest|least)\b", query_lower):
        numeric = [
            c["name"]
            for c in schema.get(table, [])
            if any(t in c["type"].upper() for t in ("INT", "REAL", "FLOAT", "NUMERIC"))
        ]
        if numeric:
            return f"ORDER BY {numeric[0]} ASC"

    return ""


def _build_limit_clause(query_lower: str) -> str:
    """Return a LIMIT clause if the query specifies one."""
    match = re.search(
        r"\b(?:top|first|limit|show\s+only|give\s+me)\s+(\d+)\b", query_lower
    )
    if match:
        return f"LIMIT {match.group(1)}"
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def rule_based_translate(
    natural_query: str, schema: dict
) -> tuple[str, list]:
    """
    Convert *natural_query* to SQL using heuristics.

    Returns ``(sql_string, bind_params)``.
    """
    q = natural_query.lower().strip()

    table = _find_table(q, schema)
    if not table:
        return (
            "-- Could not identify a table. Known tables: "
            + ", ".join(schema.keys()),
            [],
        )

    select_clause = _build_select_clause(q, table, schema)
    where_clause, params = _build_where_clause(q, table, schema)
    order_clause = _build_order_clause(q, table, schema)
    limit_clause = _build_limit_clause(q)

    # Handle JOIN hint — "employees and their department"
    join_clause = ""
    if "department" in q and table == "employees":
        join_clause = "JOIN departments ON employees.department_id = departments.id"
        if select_clause == "*":
            select_clause = (
                "employees.*, departments.name AS department_name, "
                "departments.location AS department_location"
            )

    parts = [
        f"SELECT {select_clause}",
        f"FROM {table}",
    ]
    if join_clause:
        parts.append(join_clause)
    if where_clause:
        parts.append(where_clause)
    if order_clause:
        parts.append(order_clause)
    if limit_clause:
        parts.append(limit_clause)

    return " ".join(parts), params


def llm_translate(natural_query: str, schema: dict) -> str:
    """
    Use OpenAI GPT to translate *natural_query* to SQL.

    Requires:
      - ``openai`` package  (``pip install openai``)
      - ``OPENAI_API_KEY`` environment variable

    Returns the SQL string.
    Raises ``RuntimeError`` if the prerequisites are not met.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable is not set. "
            "Either set it or use the rule-based translator."
        )

    try:
        import openai  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "openai package is not installed. Run: pip install openai"
        ) from exc

    # Build a compact schema description for the prompt
    schema_lines = []
    for table, columns in schema.items():
        col_defs = ", ".join(f"{c['name']} {c['type']}" for c in columns)
        schema_lines.append(f"  {table}({col_defs})")
    schema_text = "\n".join(schema_lines)

    system_prompt = (
        "You are an expert SQL assistant. Given a database schema and a natural language "
        "question, return ONLY the SQL query — no explanations, no markdown fences, "
        "no extra text. Use SQLite syntax.\n\n"
        f"Schema:\n{schema_text}"
    )

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": natural_query},
        ],
        temperature=0,
        max_tokens=512,
    )
    sql = response.choices[0].message.content.strip()
    # Strip accidental markdown code fences
    sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s*```$", "", sql)
    return sql


def translate(
    natural_query: str,
    schema: dict,
    *,
    use_llm: bool = False,
) -> tuple[str, list]:
    """
    Translate *natural_query* to SQL.

    Parameters
    ----------
    natural_query:
        The question in plain English.
    schema:
        Database schema as returned by ``database.get_schema()``.
    use_llm:
        If ``True`` **and** ``OPENAI_API_KEY`` is set, delegate to the LLM
        translator; otherwise fall back to the rule-based translator.

    Returns
    -------
    (sql, params)
        *params* is an empty list when the LLM path is used (the LLM embeds
        values directly into the query).
    """
    if use_llm and os.environ.get("OPENAI_API_KEY"):
        sql = llm_translate(natural_query, schema)
        return sql, []
    return rule_based_translate(natural_query, schema)
