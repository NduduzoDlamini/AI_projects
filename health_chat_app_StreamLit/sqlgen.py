"""Turns a chat prompt into a safe, read-only SQL query (T-SQL for SQL Server, or SQLite for the bundled data file).

Flow:
  1. catalog.py decides the indicator code, year range and chart type.
  2. A deterministic SQL template is built from those values (always valid).
  3. Optionally the local LLM writes the SQL; its output is only accepted if it
     is read-only AND follows the plan (right code, years, columns).
     Otherwise the template is used, so a weak LLM answer can never break a chart.
"""
import json
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
            r"STARTYEAR\s+AS\s+INT(?:EGER)?\)\s*(>=|<=|=|<|>|between)", sql, re.IGNORECASE):
        return False, "year filter not wanted (the sidebar filters years)"
    if re.search(r"\b(avg|sum|count|min|max)\s*\(|\bgroup\s+by\b", sql, re.IGNORECASE):
        return False, "aggregation is not allowed (raw values only)"
    return True, ""


# --------------------------------------------------------------------------
# LLM
# --------------------------------------------------------------------------
SYSTEM_SQL = "Return only one raw read-only SQL SELECT statement. No Markdown, no explanation."


def build_llm_prompt(prompt: str, code: str, label: str, lo, hi, dim: str, series_col=None,
                     dialect: str = "sqlserver") -> str:
    series_col = _safe_col(series_col)
    sqlite = dialect == "sqlite"
    year = _year_expr(dialect)
    if lo is not None and hi is not None:
        year_rule = f"AND {year} BETWEEN {lo} AND {hi}"
    elif lo is not None:
        year_rule = f"AND {year} >= {lo}"
    elif hi is not None:
        year_rule = f"AND {year} <= {hi}"
    else:
        year_rule = "(no year filter)"
    dim_rule = (f"AND [{series_col}] = {_sql_literal(dim)}" if dim and series_col else "(no breakdown filter)")
    value = "CAST(Numeric AS REAL)" if sqlite else "CAST(Numeric AS FLOAT)"
    select_cols = [f"    {year} AS [year],", f"    {value} AS [value]"]
    order = "[year] ASC"
    if series_col:
        select_cols[1] += ","
        select_cols.append(f"    [{series_col}] AS [series]")
        order += ", [series] ASC"
    engine = "SQLite" if sqlite else "Microsoft SQL Server T-SQL"
    return "\n".join([
        f"You are a {engine} query generator.",
        "Table: health_indicators. Use ONLY these columns: GHO_CODE, STARTYEAR, Numeric"
        + (f", {series_col}." if series_col else "."),
        "The table contains Eswatini only: never filter or group by country.",
        f"Output ONLY one raw {engine} SELECT statement: no Markdown, no code fences, no comments, no explanation.",
        "",
        "Fill in this query exactly (keep the column aliases):",
        "SELECT",
        *select_cols,
        "FROM health_indicators",
        f"WHERE GHO_CODE = '{code}'",
        "  AND Numeric IS NOT NULL",
        "  AND " + ("STARTYEAR IS NOT NULL" if sqlite else "TRY_CAST(STARTYEAR AS INT) IS NOT NULL"),
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


def _strip_think(text: str) -> str:
    """Qwen3 and similar models print their reasoning inside <think>...</think>; drop it."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    return re.sub(r"<think>.*\Z", "", text, flags=re.S).strip()


def call_llm(cfg: dict, system: str, prompt: str, timeout: int = 120) -> str:
    """One call to the chosen AI: local Ollama, or any OpenAI-compatible API (Groq, OpenRouter, ...)."""
    import requests

    if cfg.get("llm_provider") == "openai":
        base = (cfg.get("api_base") or "").rstrip("/")
        body = {"model": cfg.get("api_model"), "temperature": 0, "max_tokens": 2000,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if "groq.com" in base and "gpt-oss" in str(cfg.get("api_model")):
            body["reasoning_effort"] = "low"  # gpt-oss thinks first; keep it quick
        r = requests.post(f"{base}/chat/completions", json=body, timeout=timeout,
                          headers={"Authorization": f"Bearer {cfg.get('api_key')}"})
        r.raise_for_status()
        text = _strip_think(r.json()["choices"][0]["message"].get("content") or "")
        if not text:
            raise ValueError("empty answer")
        return text

    r = requests.post(
        cfg["ollama_url"],
        json={"model": cfg["model"], "system": system, "prompt": prompt, "stream": False,
              "options": {"temperature": 0, "num_ctx": 8192}},
        timeout=300,
    )
    r.raise_for_status()
    return _strip_think(r.json()["response"])


def llm_name(cfg: dict) -> str:
    return cfg.get("api_model") if cfg.get("llm_provider") == "openai" else cfg.get("model")


def _why(exc: Exception) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return f"HTTP {status}" if status else exc.__class__.__name__


def pick_indicator_with_llm(prompt: str, cfg: dict):
    """Used only when no keyword matched: let the AI choose from the fixed catalog (its answer is validated)."""
    lines = "\n".join(f"{code} | {label}" for _, code, label in catalog.CATALOG)
    system = ("You map a health question to ONE indicator code from a fixed list. "
              'Reply with JSON only, like {"code": "CODE"}, or {"code": null} if nothing in the list fits.')
    raw = call_llm(cfg, system, f"INDICATORS (code | meaning):\n{lines}\n\nQUESTION: {prompt}")
    m = re.search(r"\{.*?\}", raw, re.S)
    code = json.loads(m.group(0)).get("code") if m else None
    for _, c, label in catalog.CATALOG:
        if c == code:
            return {"code": c, "label": label}
    return None


# --------------------------------------------------------------------------
# Main entry
# --------------------------------------------------------------------------
def generate_sql(prompt: str, cfg: dict) -> dict:
    """Return {'kind','sql','code','label','source','note','chart_type'}."""
    chart_type = catalog.detect_chart_type(prompt, None)  # None = follow the sidebar chart type

    code = catalog.explicit_code(prompt)
    ai_note = ""
    if code:
        ind = {"code": code, "label": f"Indicator {code}"}
    else:
        ind = catalog.find_indicator(prompt)
        if cfg.get("use_llm") and (ind is None or not ind.get("strong")):
            try:
                picked = pick_indicator_with_llm(prompt, cfg)
                if picked:
                    ind = picked
                    ai_note = f"Indicator chosen by the AI ({llm_name(cfg)}) because the keywords were not specific."
            except Exception as exc:
                ai_note = f"AI indicator lookup unavailable ({_why(exc)})."

    if ind is None:
        words = catalog.topic_words(prompt)
        if not words:
            raise ValueError("I couldn't find a health topic in that request. Try e.g. 'malaria trends 2010-2024'.")
        return {
            "kind": "discovery", "sql": discovery_sql(words), "code": "-",
            "label": "No catalog match: showing indicators that contain your words",
            "source": "template", "chart_type": "table",
            "note": (ai_note + " " if ai_note else "")
                    + "Type one of these codes in a new prompt (e.g. 'trend of CODE 2010-2024') to chart it, "
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
        "label": ind["label"], "source": "template", "note": ai_note, "chart_type": chart_type,
        "prompt_years": prompt_years,
    }

    if cfg.get("use_llm"):
        try:
            raw = call_llm(cfg, SYSTEM_SQL,
                           build_llm_prompt(prompt, ind["code"], ind["label"], lo, hi, dim, series_col, dialect))
            sql = clean_sql(raw)
            ok, why = is_safe_select(sql)
            if ok:
                ok, why = follows_plan(sql, ind["code"], lo, hi, dim)
            if ok:
                result.update(sql=sql, source=f"AI ({llm_name(cfg)})")
            else:
                result["note"] = (ai_note + " " if ai_note else "") + f"AI SQL rejected ({why}); the built-in template was used instead."
        except Exception as exc:  # AI offline, key rejected, timeout, bad JSON ...
            result["note"] = (ai_note + " " if ai_note else "") + f"AI unavailable ({_why(exc)}); the built-in template was used."
    return result
