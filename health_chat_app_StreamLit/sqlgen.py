"""Turns a chat prompt into a safe, read-only SQL query (T-SQL for SQL Server, or SQLite for the bundled data file).

Flow:
  1. catalog.py decides the indicator code, year range and chart type.
  2. A deterministic SQL template is built from those values (always valid).
  3. Optionally the local LLM writes the SQL; its output is only accepted if it
     is read-only AND follows the plan (right code, years, columns).
     Otherwise the template is used, so a weak LLM answer can never break a chart.
"""
import re

import catalog

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|merge|exec|execute|grant|revoke|"
    r"into|openrowset|opendatasource|waitfor|shutdown|xp_\w*|sp_\w*)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _sql_literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _safe_col(name):
    """Only plain column names are allowed (they come from INFORMATION_SCHEMA, but be safe)."""
    return name if name and re.fullmatch(r"[A-Za-z0-9_]+", name) else None


def _year_expr(dialect: str) -> str:
    return "CAST(STARTYEAR AS INTEGER)" if dialect == "sqlite" else "TRY_CAST(STARTYEAR AS INT)"


def _conditions(lo, hi, dim, series_col=None, dialect="sqlserver"):
    year = _year_expr(dialect)
    conds = ["Numeric IS NOT NULL",
             "STARTYEAR IS NOT NULL" if dialect == "sqlite" else "TRY_CAST(STARTYEAR AS INT) IS NOT NULL"]
    if lo is not None and hi is not None:
        conds.append(f"{year} BETWEEN {lo} AND {hi}")
    elif lo is not None:
        conds.append(f"{year} >= {lo}")
    elif hi is not None:
        conds.append(f"{year} <= {hi}")
    if dim and series_col:
        conds.append(f"[{series_col}] = {_sql_literal(dim)}")
    return conds


def template_sql(code: str, lo, hi, dim: str = "", series_col=None, dialect: str = "sqlserver") -> str:
    """Raw observations, no averaging. [series] lets the app draw one line per breakdown."""
    series_col = _safe_col(series_col)
    conds = "\n  AND ".join(_conditions(lo, hi, dim, series_col, dialect))
    value = "CAST(Numeric AS REAL)" if dialect == "sqlite" else "CAST(Numeric AS FLOAT)"
    cols = f"    {_year_expr(dialect)} AS [year],\n    {value} AS [value]"
    order = "[year] ASC"
    if series_col:
        cols += f",\n    [{series_col}] AS [series]"
        order += ", [series] ASC"
    return (
        "SELECT\n" + cols + "\n"
        "FROM health_indicators\n"
        f"WHERE GHO_CODE = {_sql_literal(code)}\n"
        f"  AND {conds}\n"
        f"ORDER BY {order};"
    )


def discovery_sql(words) -> str:
    likes = " OR ".join(
        f"GHO_CODE LIKE '%{w}%' OR GHO_DISPLAY LIKE '%{w}%'" for w in words  # words are [a-z]+ only
    )
    return (
        "SELECT DISTINCT GHO_CODE, GHO_DISPLAY\n"
        "FROM health_indicators\n"
        f"WHERE {likes}\n"
        "ORDER BY GHO_CODE;"
    )


def clean_sql(raw: str) -> str:
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("```")]
    return "\n".join(lines).strip()


def is_safe_select(sql: str):
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1]
    if not s:
        return False, "empty SQL"
    if ";" in s:
        return False, "multiple statements"
    if "--" in s or "/*" in s:
        return False, "comments are not allowed"
    if not re.match(r"(?is)^\s*(select|with)\b", s):
        return False, "not a SELECT"
    m = FORBIDDEN.search(s)
    if m:
        return False, f"forbidden keyword '{m.group(0)}'"
    return True, ""


def follows_plan(sql: str, code: str, lo, hi, dim: str):
    if code not in sql:
        return False, "wrong indicator code"
    for y in (lo, hi):
        if y is not None and str(y) not in sql:
            return False, "year filter missing"
    if dim and dim not in sql:
        return False, "dimension filter missing"
    if not re.search(r"\bas\s+\[?year\]?", sql, re.IGNORECASE):
        return False, "missing 'year' column"
    if not re.search(r"\bas\s+\[?value\]?", sql, re.IGNORECASE):
        return False, "missing 'value' column"
    if lo is None and hi is None and re.search(
            r"STARTYEAR\s+AS\s+INT\)\s*(>=|<=|=|<|>|between)", sql, re.IGNORECASE):
        return False, "year filter not wanted (the sidebar filters years)"
    if re.search(r"\b(avg|sum|count|min|max)\s*\(|\bgroup\s+by\b", sql, re.IGNORECASE):
        return False, "aggregation is not allowed (raw values only)"
    return True, ""


# --------------------------------------------------------------------------
# LLM
# --------------------------------------------------------------------------
def build_llm_prompt(prompt: str, code: str, label: str, lo, hi, dim: str, series_col=None) -> str:
    series_col = _safe_col(series_col)
    if lo is not None and hi is not None:
        year_rule = f"AND TRY_CAST(STARTYEAR AS INT) BETWEEN {lo} AND {hi}"
    elif lo is not None:
        year_rule = f"AND TRY_CAST(STARTYEAR AS INT) >= {lo}"
    elif hi is not None:
        year_rule = f"AND TRY_CAST(STARTYEAR AS INT) <= {hi}"
    else:
        year_rule = "(no year filter)"
    dim_rule = (f"AND [{series_col}] = {_sql_literal(dim)}" if dim and series_col else "(no breakdown filter)")
    select_cols = ["    TRY_CAST(STARTYEAR AS INT) AS [year],", "    CAST(Numeric AS FLOAT) AS [value]"]
    order = "[year] ASC"
    if series_col:
        select_cols[1] += ","
        select_cols.append(f"    [{series_col}] AS [series]")
        order += ", [series] ASC"
    return "\n".join([
        "You are a Microsoft SQL Server T-SQL generator for the database DataAnalysis.",
        "Table: health_indicators. Use ONLY these columns: GHO_CODE, STARTYEAR, Numeric"
        + (f", {series_col}." if series_col else "."),
        "The table contains Eswatini only: never filter or group by country.",
        "Output ONLY one raw T-SQL SELECT statement: no Markdown, no code fences, no comments, no explanation.",
        "",
        "Fill in this query exactly (keep the column aliases):",
        "SELECT",
        *select_cols,
        "FROM health_indicators",
        f"WHERE GHO_CODE = '{code}'",
        "  AND Numeric IS NOT NULL",
        "  AND TRY_CAST(STARTYEAR AS INT) IS NOT NULL",
        f"  {year_rule}",
        f"  {dim_rule}",
        f"ORDER BY {order};",
        "",
        f"Indicator meaning: {label}",
        "Return the raw rows. Never use AVG, SUM, COUNT or GROUP BY. Never add a year condition.",
        "Drop the lines written in parentheses. Do not add anything else.",
        "",
        "USER REQUEST:",
        prompt,
    ])


def call_ollama(url: str, model: str, prompt: str, timeout: int = 300) -> str:
    import requests

    r = requests.post(
        url,
        json={
            "model": model,
            "system": "Return only one raw read-only Microsoft T-SQL SELECT statement. No Markdown.",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "num_ctx": 8192},
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["response"]


# --------------------------------------------------------------------------
# Main entry
# --------------------------------------------------------------------------
def generate_sql(prompt: str, cfg: dict) -> dict:
    """Return {'kind','sql','code','label','source','note','chart_type'}."""
    chart_type = catalog.detect_chart_type(prompt, cfg.get("default_chart") or "line")

    code = catalog.explicit_code(prompt)
    if code:
        ind = {"code": code, "label": f"Indicator {code}"}
    else:
        ind = catalog.find_indicator(prompt)

    if ind is None:
        words = catalog.topic_words(prompt)
        if not words:
            raise ValueError("I couldn't find a health topic in that request. Try e.g. 'malaria trends 2010-2024'.")
        return {
            "kind": "discovery", "sql": discovery_sql(words), "code": "-",
            "label": "No catalog match: showing indicators that contain your words",
            "source": "template", "chart_type": "table",
            "note": "Type one of these codes in a new prompt (e.g. 'trend of CODE 2010-2024') to chart it, "
                    "or add it to catalog.py.",
        }

    # Years named in the prompt move the sidebar range (the app does that). The SQL itself always
    # fetches ALL years, so the sidebar range can filter the charts instantly without re-querying.
    prompt_years = catalog.year_bounds(prompt)
    lo = hi = None
    dialect = cfg.get("dialect") or "sqlserver"
    series_col = _safe_col(cfg.get("series_col"))
    dim = (cfg.get("dim_value") or "").strip() if series_col else ""
    result = {
        "kind": "trend", "sql": template_sql(ind["code"], lo, hi, dim, series_col, dialect), "code": ind["code"],
        "label": ind["label"], "source": "template", "note": "", "chart_type": chart_type,
        "prompt_years": prompt_years,
    }

    if cfg.get("use_llm") and dialect == "sqlserver":  # the LLM prompt is written for T-SQL
        try:
            raw = call_ollama(cfg["ollama_url"], cfg["model"],
                              build_llm_prompt(prompt, ind["code"], ind["label"], lo, hi, dim, series_col))
            sql = clean_sql(raw)
            ok, why = is_safe_select(sql)
            if ok:
                ok, why = follows_plan(sql, ind["code"], lo, hi, dim)
            if ok:
                result.update(sql=sql, source="LLM")
            else:
                result["note"] = f"LLM SQL rejected ({why}); the built-in template was used instead."
        except Exception as exc:  # Ollama offline, timeout, bad JSON ...
            result["note"] = f"LLM unavailable ({exc.__class__.__name__}); the built-in template was used."
    return result
