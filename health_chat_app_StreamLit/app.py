"""Eswatini health trends: chat -> SQL -> a growing dashboard of charts.

Run locally:  double-click run.bat   (or:  streamlit run app.py)
"""
import base64
import hmac
import html
import json
import os
import logging
import re
import sqlite3
import threading
import time
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

import catalog
import helpers
import sqlgen

HERE = Path(__file__).resolve().parent
DASH_FILE = HERE / "dashboard.json"
LOGO_FILE = HERE / "logo.png"
AUTHOR_FILE = HERE / "author.jpg"
DB_FILE = HERE / "health_indicators.db"      # bundled copy of the table, used when deployed online
SQL_LOG_FILE = HERE / "sql_log.sql"          # one SQL log per project
PREFS_FILE = HERE / "ui_prefs.json"          # remembers the Appearance choice
PROJECT_NAME = "Eswatini Health Dashboard"
AUTHOR_NAME = "Nduduzo Dlamini"

SRC_SQLSERVER = "SQL Server (on your PC)"
SRC_SQLITE = "Bundled data file (health_indicators.db)"


def _detect_cloud() -> bool:
    """True when running on Streamlit Community Cloud (override with env HEALTH_APP_CLOUD=1/0)."""
    flag = os.environ.get("HEALTH_APP_CLOUD")
    if flag is not None:
        return flag.strip().lower() in ("1", "true", "yes")
    return HERE.as_posix().startswith("/mount/src") or os.environ.get("HOME") == "/home/appuser"


IS_CLOUD = _detect_cloud()


def _secret(name: str):
    """Read a setting from Streamlit secrets (online) or an environment variable (local)."""
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return value or os.environ.get(name)


DEFAULT_START_YEAR = 2010   # the year range starts here by default
CHART_HEIGHT = 210   # compact charts so the dashboard fits one window
ONLINE_AI_CALLS_PER_SESSION = 25   # protects your API quota on a public app
PERSIST = not IS_CLOUD   # local only: remembers Appearance and writes sql_log.sql next to the app
MAX_CHARTS = 60          # the dashboard is shared, so cap how many charts it can hold
REPORT_MAX_CHARTS = 15   # the AI report covers the newest charts only (keeps the AI request small)
log = logging.getLogger("health_app")   # full error details go to the server log, never to users

try:
    from PIL import Image
    _icon = Image.open(LOGO_FILE)
except Exception:
    _icon = None

st.set_page_config(page_title="Eswatini Health Trends", page_icon=_icon, layout="wide")

# ---- guard: all project files must come from the same version (a common mistake when re-uploading to GitHub)
_REQUIRED = {
    "helpers.py": (helpers, ["split_label", "compute_kpi", "kpi_html", "build_sql_log", "appearance_css",
                             "chart_excel_bytes", "safe_filename", "report_facts", "report_prompt",
                             "fallback_report", "clean_report", "report_docx_bytes", "question_years",
                             "filter_facts_for_question", "attach_comparison"]),
    "catalog.py": (catalog, ["is_count", "CHART_TYPES", "detect_chart_type", "find_indicator"]),
    "sqlgen.py": (sqlgen, ["generate_sql", "is_safe_select", "call_llm", "adapt_sql", "sql_dialect_of"]),
}
_outdated = {f: [n for n in names if not hasattr(mod, n)] for f, (mod, names) in _REQUIRED.items()}
_outdated = {f: miss for f, miss in _outdated.items() if miss}
if _outdated:
    _where = {f: getattr(_REQUIRED[f][0], "__file__", "?") for f in _outdated}
    st.error("These files in your repository are out of date: **" + ", ".join(_outdated) + "**. "
             "Upload the latest version of every project file (app.py, catalog.py, helpers.py, sqlgen.py) "
             "to GitHub, into the SAME folder as app.py, then reboot the app.")
    for _f, _miss in _outdated.items():
        st.caption(f"{_f}: missing {', '.join(_miss)}  ·  loaded from {_where[_f]}")
    st.stop()


# ---------------------------------------------------------------- roles: user (default, no login) and admin
# Admin: log in, edit SQL, remove charts, clear all, download the SQL log, use "Advanced: data and LLM".
# User : no login. Sees charts, downloads Excel per chart, uses the sidebar, asks for an AI report.
# Set ADMIN_PASSWORD in .streamlit/secrets.toml (local) or the app's Secrets (online).
MAX_LOGIN_FAILS = 5
st.session_state.setdefault("role", "user")


def is_admin() -> bool:
    return st.session_state.get("role") == "admin"


def _try_login():
    if is_admin():
        return
    expected = _secret("ADMIN_PASSWORD")
    given = st.session_state.get("admin_pw", "")
    if st.session_state.get("_login_fails", 0) >= MAX_LOGIN_FAILS or not expected:
        return
    if hmac.compare_digest(str(given).encode(), str(expected).encode()):
        st.session_state["role"] = "admin"
        st.session_state["_login_fails"] = 0
    else:
        st.session_state["_login_fails"] = st.session_state.get("_login_fails", 0) + 1
        time.sleep(1)   # slows down guessing
    st.session_state["admin_pw"] = ""


def _logout():
    st.session_state["role"] = "user"


def render_admin_login(box):
    with box:
        if is_admin():
            st.caption("🔓 Admin mode is on")
            st.button("Log out", key="admin_logout", on_click=_logout)
            return
        with st.expander("🔒 Admin login"):
            if not _secret("ADMIN_PASSWORD"):
                if IS_CLOUD:
                    st.caption("Admin login is off: ADMIN_PASSWORD is not set in this app's Secrets.")
                else:
                    st.caption("Admin login is off. Create the file .streamlit/secrets.toml next to app.py with "
                               "the line  ADMIN_PASSWORD = \"your password\"  and restart the app.")
            elif st.session_state.get("_login_fails", 0) >= MAX_LOGIN_FAILS:
                st.error("Too many wrong attempts. Reload the page to try again.")
            else:
                st.text_input("Password", type="password", key="admin_pw", on_change=_try_login)
                st.button("Log in", key="admin_login", on_click=_try_login)
                if st.session_state.get("_login_fails", 0):
                    st.error("Wrong password.")


# ---------------------------------------------------------------- database helpers
def _sqlite():
    """Read-only connection to the bundled data file."""
    return sqlite3.connect(DB_FILE.resolve().as_uri() + "?mode=ro", uri=True)


@st.cache_data(ttl=300, show_spinner=False)
def list_columns(source: str, conn_str: str):
    if source == SRC_SQLITE:
        con = _sqlite()
        try:
            return [r[1] for r in con.execute("PRAGMA table_info(health_indicators)")]
        finally:
            con.close()
    import pyodbc

    conn = pyodbc.connect(conn_str, timeout=10)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_NAME = 'health_indicators' ORDER BY ORDINAL_POSITION")
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


@st.cache_data(ttl=300, show_spinner=False)
def get_year_range(source: str, conn_str: str):
    if source == SRC_SQLITE:
        con = _sqlite()
        try:
            lo, hi = con.execute("SELECT MIN(CAST(STARTYEAR AS INTEGER)), MAX(CAST(STARTYEAR AS INTEGER)) "
                                 "FROM health_indicators WHERE Numeric IS NOT NULL").fetchone()
            return int(lo), int(hi)
        finally:
            con.close()
    import pyodbc

    conn = pyodbc.connect(conn_str, timeout=10)
    try:
        cur = conn.cursor()
        cur.execute("SELECT MIN(TRY_CAST(STARTYEAR AS INT)), MAX(TRY_CAST(STARTYEAR AS INT)) "
                    "FROM health_indicators WHERE Numeric IS NOT NULL")
        lo, hi = cur.fetchone()
        return int(lo), int(hi)
    finally:
        conn.close()


# ---------------------------------------------------------------- sidebar
SIDEBAR_CSS = """
<style>
.block-container { padding-top: 3.8rem !important; padding-bottom: 5rem !important; }
[data-testid="stSidebarUserContent"] { padding-top: 0.5rem; }
[data-testid="stSidebarHeader"] { height: 2.5rem; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.6rem; }
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] { gap: 0.4rem; }
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-baseweb="base-input"] { border-radius: 10px; }
[data-testid="stSidebar"] label p { font-size: 0.8rem; opacity: 0.85; }
.avatar { width: 72px; height: 72px; border-radius: 50%; object-fit: cover; display: block;
          margin: 0 auto 0.5rem auto; border: 2px solid rgba(128,128,128,0.35); }
.side-title { font-size: 1.3rem; font-weight: 700; line-height: 1.2; margin: 0.1rem 0 0.2rem 0; text-align: center; }
.byline { font-size: 0.85rem; opacity: 0.75; margin-bottom: 0.8rem; text-align: center; }
.side-settings { font-size: 1rem; font-weight: 600; margin-bottom: 0.2rem; }
.kpi-label { font-size: 0.82rem; opacity: 0.85; line-height: 1.25; }
.kpi-value { font-size: 1.8rem; font-weight: 600; line-height: 1.25; }
.kpi-unit { font-size: 0.8rem; font-weight: 400; opacity: 0.75; margin-left: 0.45rem; }
.kpi-delta { display: inline-block; font-size: 0.8rem; padding: 0.1rem 0.65rem; border-radius: 1rem; margin: 0.1rem 0; }
.kpi-delta { color: #ffffff; font-weight: 600; }
.kpi-delta.up { background: #188038; }
.kpi-delta.down { background: #d93025; }
.kpi-delta.flat { background: #6b7280; }
.kpi-basis { font-size: 0.75rem; opacity: 0.7; line-height: 1.3; }
.card-title { font-weight: 600; font-size: 0.95rem; line-height: 1.25; padding-top: 0.25rem; }
[data-testid="stTextArea"] textarea { font-family: ui-monospace, Consolas, monospace; font-size: 0.85rem; }
/* the pointer must land on the gear / AI report button itself, never on its label or arrow inside it,
   so a stray browser tip (just the gear symbol) cannot appear */
[data-testid="stPopoverButton"] *, [data-testid="stPopover"] > button * { pointer-events: none !important; }
</style>
"""
st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)


def sidebar_header_html() -> str:
    parts = []
    if AUTHOR_FILE.exists():
        b64 = base64.b64encode(AUTHOR_FILE.read_bytes()).decode()
        parts.append(f'<img class="avatar" src="data:image/jpeg;base64,{b64}" alt="{AUTHOR_NAME}">')
    parts.append(f'<div class="side-title">{PROJECT_NAME}</div>')
    parts.append(f'<div class="byline">By {AUTHOR_NAME}</div>')
    return "".join(parts)


top_box = st.sidebar.container()                          # the visible settings (top)
admin = is_admin()
adv = st.sidebar.expander("Advanced: data and LLM") if admin else None   # admin only
login_box = st.sidebar.container()
render_admin_login(login_box)

# ---- defaults = what every normal user gets. The admin can change them in "Advanced".
LLM_NONE = "None (built-in templates only)"
LLM_LOCAL = "Local Ollama (on your PC)"
LLM_ONLINE = "Online API (OpenAI-compatible)"
source = SRC_SQLITE if (IS_CLOUD and DB_FILE.exists()) else SRC_SQLSERVER
api_key = _secret("LLM_API_KEY")
api_base = _secret("LLM_BASE_URL") or "https://api.groq.com/openai/v1"
api_model = _secret("LLM_MODEL") or "openai/gpt-oss-120b"
ollama_url, model = "http://localhost:11434/api/generate", "qwen-8k:latest"
llm_choice = (LLM_ONLINE if api_key else LLM_NONE) if IS_CLOUD else LLM_LOCAL
server, database, driver = "127.0.0.1", "DataAnalysis", "ODBC Driver 17 for SQL Server"
windows_auth, sql_user, sql_pwd = True, "", ""
dim_value = ""

if admin:
    with adv:
        # --- data source (online the app only uses the bundled file)
        if not IS_CLOUD:
            sources = [SRC_SQLSERVER, SRC_SQLITE]
            source = st.selectbox("Data source", sources,
                                  help="SQL Server is your live table. The bundled file is the copy that gets deployed.")

        # --- AI that writes the SQL / understands unusual requests / writes reports
        if IS_CLOUD:  # no editable URLs or keys online: a visitor could redirect the key to their own server
            st.caption(f"AI: {api_model} (online)" if api_key else "AI: off (no LLM_API_KEY in this app's Secrets)")
        else:
            llm_opts = [LLM_LOCAL, LLM_ONLINE, LLM_NONE]
            llm_choice = st.selectbox("AI for writing SQL", llm_opts,
                                      help="Local uses Ollama on this PC. Online calls a hosted model such as "
                                           "openai/gpt-oss-120b. If the AI fails, a built-in template is used.")
            if llm_choice == LLM_LOCAL:
                ollama_url = st.text_input("Ollama URL", ollama_url)
                model = st.text_input("Model", model)
            elif llm_choice == LLM_ONLINE:
                api_base = st.text_input("API base URL", api_base)
                api_model = st.text_input("Model", api_model)
                if not api_key:
                    api_key = st.text_input("API key", type="password",
                                            help="Or set LLM_API_KEY in .streamlit/secrets.toml or as an environment variable.")
                else:
                    st.caption("API key loaded from secrets / environment.")

use_sqlite = source == SRC_SQLITE
dialect = "sqlite" if use_sqlite else "sqlserver"
use_llm = llm_choice != LLM_NONE and not (llm_choice == LLM_ONLINE and not api_key)
llm_provider = "openai" if llm_choice == LLM_ONLINE else "ollama"

if admin:
    with adv:
        if use_sqlite:
            if DB_FILE.exists():
                st.caption("Using the bundled file health_indicators.db (read-only).")
            else:
                st.warning("health_indicators.db was not found next to app.py. Run export_data.py on your PC first.")
        elif not IS_CLOUD:
            st.markdown("**SQL Server**")
            server = st.text_input("Server", server)
            database = st.text_input("Database", database)
            driver = st.text_input("ODBC driver", driver)
            windows_auth = st.checkbox("Windows authentication", value=windows_auth)
            if not windows_auth:
                sql_user = st.text_input("User")
                sql_pwd = st.text_input("Password", type="password")

conn_str = ""
if use_sqlite:
    db_label = "health_indicators.db (SQLite)"
elif IS_CLOUD:
    db_label = "(no data file)"
else:
    conn_str = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};TrustServerCertificate=yes;"
        + ("Trusted_Connection=yes;" if windows_auth else f"UID={sql_user};PWD={sql_pwd};")
    )
    db_label = database

table_cols, table_cols_error = [], None
try:
    table_cols = list_columns(source, conn_str)
except Exception as exc:
    table_cols_error = exc
candidates = ["DIMENSION_VALUE", "DIMENSION", "DIMENSION_DISPLAY", "DIMENSION_CODE", "DIMENSION_TYPE"]
options = ["(none)"] + table_cols
series_pick = next((c for c in candidates if c in table_cols), "(none)")

if admin:
    with adv:
        st.markdown("**Breakdown column**")
        if table_cols_error:
            st.warning(f"Could not read the table's columns: {table_cols_error}")
        series_pick = st.selectbox("Column that splits a year into several rows", options,
                                   index=options.index(series_pick),
                                   help="Draws one line per breakdown (e.g. sex or age). Pick (none) to ignore.")
        if table_cols:
            st.caption("Columns: " + ", ".join(table_cols))
        dim_value = st.text_input("Only keep rows where that column equals", "",
                                  help="Leave blank for no filter, e.g. type 'Total' to keep a single breakdown.")
series_col = None if series_pick == "(none)" else series_pick

try:
    min_y, max_y = get_year_range(source, conn_str)
except Exception:
    min_y, max_y = 2000, date.today().year

YEARS = list(range(min_y, max_y + 1))
TF_CUSTOM = "Custom (use years above)"
TIMEFRAMES = [TF_CUSTOM, "Last 5 years", "Last 10 years", "Last 15 years", "All years"]
st.session_state["_bounds"] = (min_y, max_y)


def _apply_timeframe():
    """Preset chosen -> move the start/end boxes so they always show the real range."""
    lo_b, hi_b = st.session_state["_bounds"]
    tf = st.session_state["timeframe"]
    if tf == "All years":
        lo, hi = lo_b, hi_b
    elif tf.startswith("Last"):
        lo, hi = max(lo_b, hi_b - int(tf.split()[1]) + 1), hi_b
    else:
        return
    st.session_state["start_year"], st.session_state["end_year"] = lo, hi


def _reset_chart_types():
    """Sidebar chart type applies to EVERY chart. Admin: saved for the shared dashboard. User: this visitor only."""
    new = st.session_state["chart_pick"].lower()
    trend_ids = [e["id"] for e in st.session_state.get("entries", []) if e.get("kind") == "trend"]
    for eid in trend_ids:
        st.session_state[f"type_{eid}"] = new
    if is_admin():
        _store_update(lambda items: [({**it, "chart_type": None} if it.get("kind") == "trend" else it) for it in items])
    else:
        st.session_state["_types"] = {eid: new for eid in trend_ids}


def _reset_labels():
    """Sidebar 'Show data labels' applies to EVERY chart. Admin: saved for the shared dashboard. User: this visitor only."""
    new = bool(st.session_state.get("labels_all"))
    trend_ids = [e["id"] for e in st.session_state.get("entries", []) if e.get("kind") == "trend"]
    for eid in trend_ids:
        st.session_state[f"labels_{eid}"] = new
    if is_admin():
        _store_update(lambda items: [({**it, "show_labels": None} if it.get("kind") == "trend" else it) for it in items])
    else:
        st.session_state["_labels"] = {eid: new for eid in trend_ids}


def _mark_custom():
    st.session_state["timeframe"] = TF_CUSTOM


# a prompt that names years moves the range (applied before the widgets are created)
if "_pending_range" in st.session_state:
    p_lo, p_hi = st.session_state.pop("_pending_range")
    p_lo = min(max(p_lo if p_lo is not None else min_y, min_y), max_y)
    p_hi = min(max(p_hi if p_hi is not None else max_y, min_y), max_y)
    st.session_state["start_year"], st.session_state["end_year"] = min(p_lo, p_hi), max(p_lo, p_hi)
    st.session_state["timeframe"] = TF_CUSTOM
for _k in ("start_year", "end_year"):
    if st.session_state.get(_k) not in YEARS:
        st.session_state.pop(_k, None)
st.session_state.setdefault("start_year", min(max(min_y, DEFAULT_START_YEAR), max_y))
st.session_state.setdefault("end_year", max_y)
st.session_state.setdefault("timeframe", TF_CUSTOM)

if "appearance" not in st.session_state:
    _saved = None
    if PERSIST:
        try:
            _saved = json.loads(PREFS_FILE.read_text(encoding="utf-8")).get("appearance")
        except Exception:
            pass
    st.session_state["appearance"] = _saved if _saved in ("Auto", "Light", "Dark") else "Auto"


def _save_prefs():
    if not PERSIST:
        return
    try:
        PREFS_FILE.write_text(json.dumps({"appearance": st.session_state["appearance"]}), encoding="utf-8")
    except Exception:
        pass


with top_box:
    st.markdown(sidebar_header_html(), unsafe_allow_html=True)
    st.markdown('<div class="side-settings">⚙️ Settings</div>', unsafe_allow_html=True)

    c_start, c_end = st.columns(2)
    c_start.selectbox("Start year", YEARS, key="start_year", on_change=_mark_custom)
    c_end.selectbox("End year", YEARS, key="end_year", on_change=_mark_custom)
    st.selectbox("Select time frame", TIMEFRAMES, key="timeframe", on_change=_apply_timeframe,
                 help="The year range filters every chart instantly. A chart type or years named in your prompt "
                      "override these settings (years in a prompt move the range).")
    chart_pick = st.selectbox("Select a chart type", [t.capitalize() for t in catalog.CHART_TYPES],
                              key="chart_pick", on_change=_reset_chart_types,
                              help="Applies to every chart on the dashboard. A chart's own ⚙ button can override it "
                                   "until you change this again. A type named in a new prompt is used for that chart.")
    show_labels_all = st.checkbox("Show data labels", key="labels_all", on_change=_reset_labels,
                                  help="Writes the value on every point or bar. Applies to every chart; a chart's own "
                                       "⚙ button can override it until you change this again.")
    per_row = st.selectbox("Charts per row", [1, 2, 3, 4], index=2,
                           help="More charts per row fits more on one screen. Zoom the page in for a larger view.")
    st.radio("Appearance", ["Auto", "Light", "Dark"], key="appearance", horizontal=True,
             format_func=lambda x: {"Auto": "🖥️ Auto", "Light": "☀️ Light", "Dark": "🌙 Dark"}[x],
             on_change=_save_prefs, help="Auto follows your browser's theme.")
    year_lo, year_hi = sorted((st.session_state["start_year"], st.session_state["end_year"]))
    if st.session_state["start_year"] > st.session_state["end_year"]:
        st.warning("Start year is after end year, so they were swapped.")

try:  # the theme Streamlit is really showing (Streamlit 1.46+); otherwise the browser setting is used
    _actual_theme = st.context.theme.type
except Exception:
    _actual_theme = None
_css = helpers.appearance_css(st.session_state["appearance"], _actual_theme)
if _css:
    st.markdown(_css, unsafe_allow_html=True)

CFG = {
    "use_llm": use_llm, "llm_provider": llm_provider, "ollama_url": ollama_url, "model": model,
    "api_base": api_base, "api_model": api_model, "api_key": api_key,
    "series_col": series_col, "dim_value": dim_value, "conn_str": conn_str,
    "default_chart": chart_pick.lower(), "source": source, "dialect": dialect,
    "show_labels": bool(show_labels_all),
}


# ---------------------------------------------------------------- data
def run_query(sql: str) -> pd.DataFrame:
    if CFG["source"] == SRC_SQLITE:
        con = _sqlite()
        deadline = time.time() + 8   # stop runaway queries
        con.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 200000)
        try:
            df = pd.read_sql_query(sql, con)
        finally:
            con.close()
    else:
        import pyodbc

        conn = pyodbc.connect(CFG["conn_str"], timeout=15)
        try:
            cur = conn.cursor()
            cur.execute(sql)
            if cur.description is None:
                return pd.DataFrame()
            cols = [c[0] for c in cur.description]
            df = pd.DataFrame([list(r) for r in cur.fetchall()], columns=cols)
        finally:
            conn.close()
    if {"year", "value"} <= set(df.columns):
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


# ---- the dashboard is SHARED by every visitor and saved in dashboard.json, so charts survive a reload.
STORE_KEYS = ("id", "prompt", "title", "sql", "original_sql", "code", "label", "kind", "chart_type",
              "source", "note", "created", "show_labels")


@st.cache_resource
def _store_lock():
    return threading.Lock()


def _store_read() -> list:
    if not DASH_FILE.exists():
        return []
    try:
        data = json.loads(DASH_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        log.exception("dashboard.json is unreadable; a copy was kept as dashboard.json.bad")
        try:
            DASH_FILE.replace(DASH_FILE.with_suffix(".json.bad"))
        except Exception:
            pass
        return []


def _store_update(change):
    """Read the saved charts, apply change(list) -> list, and write them back safely (one writer at a time)."""
    with _store_lock():
        items = change(_store_read())
        tmp = DASH_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, indent=2), encoding="utf-8")
        os.replace(tmp, DASH_FILE)       # a half-written file can never be seen
        if PERSIST:
            try:
                SQL_LOG_FILE.write_text(helpers.build_sql_log(items, PROJECT_NAME, db_label), encoding="utf-8")
            except Exception:
                log.exception("could not write sql_log.sql")
    st.session_state["_store_stamp"] = None      # reload from the file on the next run


def _store_patch(eid: str, **fields):
    def change(items):
        for it in items:
            if it.get("id") == eid:
                it.update(fields)
        return items
    _store_update(change)


def _store_stamp():
    try:
        stat = DASH_FILE.stat()
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return (0, 0)


@st.cache_data(ttl=600, show_spinner=False, max_entries=300)
def cached_query(sql: str, source: str, conn_str: str) -> pd.DataFrame:
    """Saved charts are re-run from this cache, so a new visitor does not re-query every chart."""
    return run_query(sql)


def sync_dashboard():
    """Every run: if dashboard.json changed (any visitor added/removed/edited a chart), reload it."""
    ss = st.session_state
    stamp = _store_stamp()
    if "entries" in ss and ss.get("_store_stamp") == stamp:
        return
    old = {e["id"]: e for e in ss.get("entries", [])}
    data, ran = ss.get("data", {}), ss.setdefault("_ran_sql", {})
    entries, new_data = [], {}
    for item in _store_read():
        if not isinstance(item, dict) or not item.get("id") or not item.get("sql"):
            continue
        e = old.get(item["id"]) or {"error": None}
        e.update({k: item.get(k) for k in STORE_KEYS})
        eid = e["id"]
        if e.get("kind") == "trend":     # a chart saved on SQL Server must still run on SQLite (and the reverse)
            fixed = False
            for key in ("sql", "original_sql"):
                if e.get(key):
                    e[key], changed = sqlgen.adapt_sql(e[key], e.get("code"), CFG["dialect"],
                                                       CFG["series_col"], CFG["dim_value"])
                    fixed = fixed or changed
            if fixed:
                e["source"] = "template (rebuilt for this database)"
        if data.get(eid) is not None and ran.get(eid) == e["sql"]:
            new_data[eid] = data[eid]
        else:
            try:
                new_data[eid] = cached_query(e["sql"], CFG["source"], CFG["conn_str"])
                e["error"] = None
            except Exception as exc:
                new_data[eid], e["error"] = None, str(exc)    # shown to the admin only
                log.exception("saved chart %s could not be loaded", eid)
            ran[eid] = e["sql"]
        entries.append(e)
    ss["entries"], ss["data"], ss["_store_stamp"] = entries, new_data, stamp


def _ai_budget():
    """Copy of the settings with the online-AI cap applied: returns (cfg, capped)."""
    cfg, capped = dict(CFG), False
    if cfg["use_llm"] and cfg["llm_provider"] == "openai":
        if st.session_state.get("_ai_calls", 0) >= ONLINE_AI_CALLS_PER_SESSION:
            cfg["use_llm"], capped = False, True
        else:
            st.session_state["_ai_calls"] = st.session_state.get("_ai_calls", 0) + 1
    return cfg, capped


def add_chart(prompt: str):
    if len(st.session_state.entries) >= MAX_CHARTS:
        raise ValueError(f"The dashboard already has {MAX_CHARTS} charts. Please ask the admin to remove some.")
    cfg, capped = _ai_budget()
    gen = sqlgen.generate_sql(prompt, cfg)
    if capped:
        gen["note"] = (gen.get("note", "") + " AI limit for this session reached; the built-in template was used.").strip()
    df = run_query(gen["sql"])
    entry = {"id": uuid.uuid4().hex[:8], "prompt": prompt, "title": prompt,
             "original_sql": gen["sql"], "created": datetime.now().strftime("%Y-%m-%d %H:%M"), **gen}
    item = {k: entry.get(k) for k in STORE_KEYS}
    st.session_state.data[entry["id"]] = df                        # keep the result: no second query
    st.session_state.setdefault("_ran_sql", {})[entry["id"]] = entry["sql"]
    st.session_state.setdefault("_my_charts", set()).add(entry["id"])   # this visitor may rename it
    _store_update(lambda items: items + [item])                    # saved for every visitor
    return gen.get("prompt_years")


def _find(eid: str):
    return next((x for x in st.session_state.entries if x["id"] == eid), None)


def run_edited_sql(eid: str, source_label: str = "edited by you"):
    """ADMIN ONLY. Run the SQL typed in a chart's editor, then refresh that chart, the saved dashboard and the SQL log."""
    e = _find(eid)
    if e is None or not is_admin():
        return
    sql = st.session_state.get(f"sql_{eid}", "").strip()
    ok, why = sqlgen.is_safe_select(sql)
    if not ok:
        e["sql_error"] = f"Not run: {why}. Only a single read-only SELECT is allowed."
        return
    try:
        df = run_query(sql)
    except Exception as exc:
        log.exception("admin SQL failed for chart %s", eid)
        e["sql_error"] = f"Query failed: {exc}"
        return
    kind = "trend" if {"year", "value"} <= set(df.columns) else "discovery"
    st.session_state.data[eid] = df
    st.session_state.setdefault("_ran_sql", {})[eid] = sql
    e.update(sql=sql, source=source_label, error=None, sql_error=None, note="", kind=kind)
    _store_patch(eid, sql=sql, source=source_label, note="", kind=kind)


def reset_sql(eid: str):
    e = _find(eid)
    if e and is_admin() and e.get("original_sql"):
        st.session_state[f"sql_{eid}"] = e["original_sql"]
        run_edited_sql(eid, "original SQL restored")


def set_card_type(eid: str):
    """Admin: saved for everyone. User: only changes what this visitor sees."""
    e = _find(eid)
    if not e:
        return
    chosen = st.session_state.get(f"type_{eid}")
    if is_admin():
        _store_patch(eid, chart_type=chosen)
    else:
        st.session_state.setdefault("_types", {})[eid] = chosen


def set_card_labels(eid: str):
    """Admin: saved for everyone. User: only changes what this visitor sees."""
    if not _find(eid):
        return
    chosen = bool(st.session_state.get(f"labels_{eid}"))
    if is_admin():
        _store_patch(eid, show_labels=chosen)
    else:
        st.session_state.setdefault("_labels", {})[eid] = chosen


def can_rename(eid: str) -> bool:
    """Admin: any chart. User: only charts created in this browser session (lost on reload)."""
    return is_admin() or eid in st.session_state.get("_my_charts", set())


def rename_entry(eid: str):
    """The new title is saved for every visitor (and used in the Excel / Word files)."""
    e = _find(eid)
    if e and can_rename(eid):
        new = " ".join(st.session_state.get(f"title_{eid}", "").split())[:150]
        _store_patch(eid, title=new or e["prompt"])


def remove_entry(eid: str):
    if not is_admin():      # ONLY the admin can delete charts
        return
    st.session_state.data.pop(eid, None)
    _store_update(lambda items: [it for it in items if it.get("id") != eid])


def clear_all():
    if not is_admin():
        return
    st.session_state.data = {}
    _store_update(lambda items: [])


# ---------------------------------------------------------------- excel + report
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@st.cache_data(show_spinner=False, max_entries=200)
def cached_excel(title: str, subtitle: str, df: pd.DataFrame, full: pd.DataFrame) -> bytes:
    return helpers.chart_excel_bytes(title, df, subtitle, full)


def excel_button(e: dict, title: str, df: pd.DataFrame, subtitle: str, full: pd.DataFrame = None):
    """Download the rows and columns behind this chart (plus an 'All years' sheet), headed with its title."""
    data = df.dropna(axis=1, how="all")          # skip a breakdown column that is empty
    full = full.dropna(axis=1, how="all") if full is not None else None
    st.download_button("⬇ Excel", data=cached_excel(title, subtitle, data, full),
                       file_name=helpers.safe_filename(title, ".xlsx"), mime=XLSX_MIME,
                       key=f"xlsx_{e['id']}", help="Download this chart's data as an Excel file")


def generate_report(question: str):
    """A general report, or (if a question is typed) a report that answers that question from the charts."""
    question = " ".join((question or "").split())[:300]
    qy = helpers.question_years(question)
    lo, hi = (min([year_lo] + qy), max([year_hi] + qy)) if qy else (year_lo, year_hi)   # years named in the question
    facts = helpers.report_facts(st.session_state.entries, st.session_state.data, lo, hi)
    if not facts:
        st.warning("There is no chart data to report on yet. Ask for a chart first.")
        return
    facts, found = helpers.filter_facts_for_question(facts, question)    # only charts about the question
    if not found:
        st.warning(f"None of the charts on the dashboard are about \"{question}\". Ask for a chart on that topic "
                   "first (for example 'HIV new infections 2010-2024'), then ask your question again.")
        return
    trimmed = len(facts) > REPORT_MAX_CHARTS
    facts = facts[-REPORT_MAX_CHARTS:]       # newest charts
    helpers.attach_comparison(facts, question)        # the numbers are worked out here, not by the AI
    cfg, capped = _ai_budget()
    text, by, note = "", "built-in summary (no AI)", ""
    if cfg["use_llm"]:
        try:
            with st.spinner("The AI is writing your report..."):
                raw = sqlgen.call_llm(cfg, helpers.REPORT_SYSTEM,
                                      helpers.report_prompt(facts, question, lo, hi), timeout=180)
            text = helpers.clean_report(raw)
            by = f"AI ({sqlgen.llm_name(cfg)})"
        except Exception as exc:
            log.exception("AI report failed")
            note = "The AI was not available, so a built-in summary was written instead."
            if is_admin():
                note += f" ({sqlgen._why(exc)})"
    elif capped:
        note = "The AI limit for this session was reached, so a built-in summary was written instead."
    if not text:
        text = helpers.fallback_report(facts, lo, hi, question)
    if trimmed:
        note = (note + " " if note else "") + f"The report covers the {REPORT_MAX_CHARTS} newest charts."
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    meta = f"Eswatini · years {lo}-{hi} · written by {by} · {when} · check the figures before sharing"
    st.session_state["report"] = {"text": text, "by": by, "note": note, "years": f"{lo}-{hi}", "when": when,
                                  "question": question, "charts": [f["title"] for f in facts],
                                  "docx": helpers.report_docx_bytes(text, meta, facts)}


def render_report_button(holder):
    pop = holder.popover("📝 AI report") if hasattr(holder, "popover") else holder.expander("📝 AI report")
    with pop:
        st.caption("Ask a question about the charts, or leave it empty for a general report.")
        question = st.text_input("Your question (optional)", key="report_focus", max_chars=300,
                                 placeholder="e.g. How was HIV in 2024 compared to 2022?")
        if st.button("Generate report", key="report_go", disabled=not st.session_state.entries):
            generate_report(question)


def render_report():
    rep = st.session_state.get("report")
    if not rep:
        return
    with st.container(border=True):
        st.markdown(rep["text"])
        st.caption(f"Years {rep['years']} · written by {rep['by']} · {rep['when']}. "
                   "Check the figures before sharing.")
        if rep.get("question"):
            st.caption("Charts used: " + "; ".join(rep.get("charts", [])))
        if rep["note"]:
            st.caption(rep["note"])
        c1, c2, c3, _ = _columns([1.7, 1.5, 0.9, 5])
        c1.download_button("⬇ Word (.docx)", data=rep["docx"], file_name="health_report.docx", mime=DOCX_MIME,
                           key="report_docx", help="The report plus a data table for every chart")
        c2.download_button("⬇ Markdown", data=rep["text"].encode("utf-8"),
                           file_name="health_report.md", mime="text/markdown", key="report_dl")
        c3.button("Hide", key="report_hide", on_click=lambda: st.session_state.pop("report", None))


# ---------------------------------------------------------------- charts
split_label = helpers.split_label


def make_figure(df: pd.DataFrame, ctype: str, label: str = "", show_labels: bool = False):
    d = df.copy()
    multi = False
    if "series" in d.columns:
        d["series"] = d["series"].fillna("(none)").astype(str)
        multi = d["series"].nunique() > 1  # one line/colour per breakdown only if there are several
    d = d.sort_values(["year", "series"] if "series" in d.columns else ["year"])
    color = "series" if multi else None
    name, unit = split_label(label)
    compact = dict(height=CHART_HEIGHT, margin=dict(l=6, r=6, t=26 if multi else 8, b=6), font=dict(size=11),
                   legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title_text=""))

    if ctype == "pie":
        text = d["year"].astype(str) + ((" - " + d["series"]) if multi else "")
        fig = px.pie(d.assign(label=text), names="label", values="value")
        if show_labels:
            fig.update_traces(texttemplate="%{value:,.2~f} (%{percent})", textposition="auto")
        fig.update_layout(**compact)
        return fig
    if ctype == "bar":
        fig = px.bar(d, x="year", y="value", color=color, barmode="group")
    elif ctype == "area":
        fig = px.area(d, x="year", y="value", color=color)
    elif ctype == "scatter":
        fig = px.scatter(d, x="year", y="value", color=color)
    else:
        fig = px.line(d, x="year", y="value", color=color, markers=True)

    y_title = (unit[:1].upper() + unit[1:]) if unit else (name or "Value")
    fig.update_layout(**compact)
    fig.update_xaxes(title_text=None, tickformat="d")
    fig.update_yaxes(title_text=y_title, title_font=dict(size=10))
    fig.update_traces(hovertemplate=("%{fullData.name}<br>" if multi else "")
                      + "Year %{x}<br>%{y:,.2f}" + (f" {unit}" if unit else "") + "<extra></extra>")
    if show_labels:
        fig.update_traces(texttemplate="%{y:,.2~f}", textfont=dict(size=9), cliponaxis=False,
                          textposition="outside" if ctype == "bar" else "top center")
        if ctype in ("line", "area", "scatter"):
            fig.update_traces(mode={"line": "lines+markers+text", "area": "lines+text", "scatter": "markers+text"}[ctype])
        fig.update_layout(margin=dict(l=6, r=6, t=34 if multi else 18, b=6))
    return fig


def _columns(spec, gap=None):
    kw = {"vertical_alignment": "center"}
    if gap:
        kw["gap"] = gap
    try:
        return st.columns(spec, **kw)
    except TypeError:  # older Streamlit
        return st.columns(spec)


_CLOSE_X_HTML = """
<div style="display:flex;justify-content:flex-end;margin:0;padding:0">
  <button id="x" type="button" title="Close" aria-label="Close settings"
    style="border:0;background:transparent;color:#9aa0a6;font:600 18px/1 sans-serif;cursor:pointer;
           padding:2px 6px;border-radius:6px">&#10005;</button>
</div>
<script>
  const b = document.getElementById("x");
  b.onmouseenter = () => b.style.color = "#ff4b4b";
  b.onmouseleave = () => b.style.color = "#9aa0a6";
  // The pointer moving into this little frame never reaches the page, so the page never learns that it left
  // the gear button and its hover tip stays on screen. Tell the page the pointer left, so tips only show
  // while a button is really hovered.
  function hideTips() {
    try {
      window.parent.document.querySelectorAll('[data-testid="stPopover"] button, button[data-testid="stPopoverButton"]')
        .forEach(btn => {
          btn.dispatchEvent(new MouseEvent("mouseout", {bubbles: true, relatedTarget: null}));
          btn.dispatchEvent(new MouseEvent("mouseleave", {bubbles: false, relatedTarget: null}));
        });
    } catch (err) { /* sandboxed: nothing to do */ }
  }
  hideTips();
  setTimeout(hideTips, 250);
  document.documentElement.addEventListener("mouseenter", hideTips);
  b.onclick = () => {
    try {
      const d = window.parent.document;
      // clicking the open popover's own button toggles it shut
      const t = d.querySelector('[data-testid="stPopover"] button[aria-expanded="true"]')
             || d.querySelector('button[data-testid="stPopoverButton"][aria-expanded="true"]');
      if (t) {
        t.click();
        if (t.blur) t.blur();
        hideTips();
        setTimeout(hideTips, 150);
        return;
      }
      d.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", code: "Escape", keyCode: 27, bubbles: true}));
      hideTips();
    } catch (err) { /* sandboxed: nothing to do */ }
  };
  // take the X out of the layout: float it in the popover's top padding so it uses no vertical space
  try {
    const fe = window.frameElement;
    const box = fe.closest('[data-testid="stElementContainer"]') || fe.closest('.element-container');
    if (box) {
      const gap = parseFloat(getComputedStyle(box.parentElement).rowGap) || 16;
      for (let n = fe.parentElement; n && n !== box; n = n.parentElement) {
        n.style.height = "0"; n.style.minHeight = "0"; n.style.overflow = "visible";
      }
      Object.assign(box.style, {position: "sticky", top: "1rem", height: "0", minHeight: "0",
                                margin: "0 0 -" + gap + "px 0", zIndex: "20", overflow: "visible"});
      Object.assign(fe.style, {position: "absolute", top: "-16px", right: "-6px", width: "34px", height: "28px"});
    }
  } catch (err) { /* keeps the normal layout */ }
</script>
"""


_HOVER_TIPS_HTML = """
<script>
  (function () {
    const w = window.parent;
    w.__hoverTips = %s;
    if (w.__hoverTipsOn) return;
    w.__hoverTipsOn = true;
    const code = `
      (function () {
        function apply() {
          const tips = window.__hoverTips || {};
          document.querySelectorAll('[data-testid="stPopover"] button, button[data-testid="stPopoverButton"]')
            .forEach(function (btn) {
              const txt = (btn.innerText || "").trim();
              const tip = txt.indexOf("\u2699") >= 0 ? tips.gear : (txt.indexOf("AI report") >= 0 ? tips.report : "");
              // clear any stray tip (for example just the gear symbol) left on the label, the arrow or a wrapper
              btn.querySelectorAll("[title]").forEach(function (el) { el.removeAttribute("title"); });
              btn.querySelectorAll("svg title").forEach(function (el) { el.remove(); });
              let up = btn.parentElement;
              for (let i = 0; up && i < 6; i++, up = up.parentElement) {
                if (up.hasAttribute("title")) up.removeAttribute("title");
              }
              if (tip && btn.getAttribute("aria-expanded") !== "true") {
                if (btn.title !== tip) btn.title = tip;
              } else if (btn.hasAttribute("title")) {
                btn.removeAttribute("title");     // no tip while the settings are open
              }
            });
        }
        let queued = false;
        function soon() { if (queued) return; queued = true; requestAnimationFrame(function () { queued = false; apply(); }); }
        apply();
        new MutationObserver(soon).observe(document.body, {childList: true, subtree: true,
                                                           attributes: true, attributeFilter: ["aria-expanded", "title"]});
      })();`;
    const s = w.document.createElement("script");
    s.textContent = code;
    w.document.head.appendChild(s);
  })();
</script>
"""


def install_hover_tips():
    """Hover tips for the gear and AI report buttons. They use the browser's own tip, so they show only while the
    pointer is on that button and go away when it leaves or the settings open (Streamlit's own tip can get stuck)."""
    tips = {"gear": "Chart type, data labels, rename, SQL, remove" if is_admin()
                    else "Chart type, data labels (and rename, for charts you made)",
            "report": "Write a short report from the charts on the dashboard"}
    try:
        components.html(_HOVER_TIPS_HTML % json.dumps(tips), height=0)
    except Exception:
        pass


def close_popover_x():
    """A small X at the top-right of a popover that closes it (Streamlit has no built-in close button)."""
    try:
        components.html(_CLOSE_X_HTML, height=30)
    except Exception:
        pass


def render_card(e: dict):
    df = st.session_state.data.get(e["id"])
    title = e.get("title") or e["prompt"]
    # this visitor's own choice, else the chart's saved type, else the sidebar's
    current = st.session_state.get("_types", {}).get(e["id"]) or e.get("chart_type") or CFG["default_chart"]
    if current not in catalog.CHART_TYPES:
        current = "line"
    # data labels: this visitor's own choice (users only), else the chart's saved choice, else the sidebar's
    mine = {} if is_admin() else st.session_state.get("_labels", {})
    show = mine.get(e["id"])
    if show is None:
        show = e.get("show_labels")
    if show is None:
        show = CFG["show_labels"]
    show = bool(show)
    st.session_state[f"labels_{e['id']}"] = show
    with st.container(border=True):
        c_title, c_opt = _columns([6, 1.4])
        c_title.markdown(f'<div class="card-title">{html.escape(title)}</div>', unsafe_allow_html=True)

        # everything secondary lives behind the card's ⚙ button, so the card stays small
        holder = c_opt.popover("⚙") if hasattr(c_opt, "popover") else c_opt.expander("⚙")
        with holder:
            if hasattr(c_opt, "popover"):
                close_popover_x()
            ctype = st.selectbox("Chart type", catalog.CHART_TYPES, index=catalog.CHART_TYPES.index(current),
                                 key=f"type_{e['id']}", on_change=set_card_type, args=(e["id"],))
            if ctype != "table" and e.get("kind") != "discovery":
                st.checkbox("Show data labels", key=f"labels_{e['id']}", on_change=set_card_labels, args=(e["id"],))
            if can_rename(e["id"]):
                st.text_input("Title", value=title, key=f"title_{e['id']}", max_chars=150,
                              on_change=rename_entry, args=(e["id"],))
            if is_admin():   # SQL is never rendered for normal users
                st.markdown("**SQL (you can edit it)**")
                st.caption("Dialect: " + ("SQLite" if CFG["dialect"] == "sqlite" else "T-SQL (SQL Server)")
                           + ". One read-only SELECT. To chart it, return columns named year and value.")
                st.text_area("SQL", value=e["sql"], key=f"sql_{e['id']}", height=220, label_visibility="collapsed")
                b1, b2 = st.columns(2)
                b1.button("▶ Run edited SQL", key=f"run_{e['id']}", on_click=run_edited_sql, args=(e["id"],))
                if e.get("original_sql") and e["original_sql"].strip() != e["sql"].strip():
                    b2.button("↺ Reset", key=f"reset_{e['id']}", on_click=reset_sql, args=(e["id"],))
                if e.get("sql_error"):
                    st.error(e["sql_error"])
                st.caption(f"Written by: {e['source']}")
                if e.get("note") and e["kind"] != "discovery":
                    st.caption(e["note"])
                st.button("🗑 Remove chart", key=f"rm_{e['id']}", on_click=remove_entry, args=(e["id"],))

        if e.get("error"):
            st.error(f"Query failed: {e['error']}" if is_admin() else "This chart could not be loaded right now.")
        elif df is None or df.empty:
            st.warning("No rows returned. Try another measure" + (", or check the SQL (⚙)." if is_admin() else "."))
        elif e["kind"] == "discovery" or not {"year", "value"} <= set(df.columns):
            st.dataframe(df, height=CHART_HEIGHT)
            if e.get("note"):
                st.caption(e["note"])
            excel_button(e, title, df, "Indicators that match your search")
        else:
            view = df[df["year"].between(year_lo, year_hi)]  # sidebar range, applied instantly
            if view.empty:
                st.warning(f"No data between {year_lo} and {year_hi}. Widen the year range in the sidebar.")
            else:
                kpi = helpers.compute_kpi(view, e["code"], e.get("label", ""))
                if kpi:
                    extra = ("Breakdowns are combined; pick one in Advanced for a single series."
                             if "series" in view.columns and view["series"].nunique() > 1 else "")
                    st.markdown(helpers.kpi_html(kpi, e["code"], e.get("label", ""), extra), unsafe_allow_html=True)
                if ctype == "table":
                    st.dataframe(view, height=CHART_HEIGHT)
                else:
                    st.plotly_chart(make_figure(view, ctype, e.get("label", ""), show), key=f"fig_{e['id']}")
                excel_button(e, title, view,
                             f"{e.get('label', '')} ({e['code']}) · years {year_lo}-{year_hi}".strip(), full=df)


# ---------------------------------------------------------------- page
def header_html() -> str:
    logo = ""
    if LOGO_FILE.exists():
        b64 = base64.b64encode(LOGO_FILE.read_bytes()).decode()
        logo = f'<img src="data:image/png;base64,{b64}" style="height:48px">'
    return (f'<div class="hdr-row-marker" style="display:flex;align-items:center;gap:12px">{logo}'
            f'<h1 style="margin:0;padding:0;font-size:1.7rem">Eswatini health trends</h1></div>')


sync_dashboard()

if is_admin():   # back-up button lives in the same Advanced section
    with adv:
        st.markdown("**Saved dashboard**")
        st.caption("Charts are saved on the server in dashboard.json and shared by all visitors. On Streamlit "
                   "Community Cloud that file is reset when the app is rebooted or redeployed. Download the "
                   "backup and commit it to GitHub to keep the charts permanently.")
        st.download_button("Download dashboard.json", data=json.dumps(_store_read(), indent=2),
                           file_name="dashboard.json", mime="application/json", key="dash_backup")

# header buttons: shrink their columns to the button width so they sit close together on the right
st.markdown("""<style>
div[data-testid="stHorizontalBlock"]:has(.hdr-row-marker) { gap: 0.5rem !important; }
div[data-testid="stHorizontalBlock"]:has(.hdr-row-marker) > div[data-testid="stColumn"]:not(:first-child),
div[data-testid="stHorizontalBlock"]:has(.hdr-row-marker) > div[data-testid="column"]:not(:first-child) {
    flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }
div[data-testid="stHorizontalBlock"]:has(.hdr-row-marker) > div:first-child { flex: 1 1 0 !important; }
</style>""", unsafe_allow_html=True)
if is_admin():
    head, btn_report, btn_clear, btn_log = _columns([10, 1.5, 1.0, 1.0], gap="small")
else:
    head, btn_report = _columns([6, 1.8], gap="small")
head.markdown(header_html(), unsafe_allow_html=True)
render_report_button(btn_report)
if is_admin():
    if btn_clear.button("Clear all", disabled=not st.session_state.entries):
        clear_all()
        st.rerun()
    btn_log.download_button("SQL log", data=helpers.build_sql_log(st.session_state.entries, PROJECT_NAME, db_label),
                            file_name="sql_log.sql", mime="text/plain", disabled=not st.session_state.entries,
                            help="Download the SQL behind every chart, with each chart's heading")
st.caption("Ask for a trend and name the chart type, e.g. *NCD trends line graph* or "
           "*malaria deaths 2010 to 2024 pie chart*. Each question adds a chart; nothing is replaced.")

if IS_CLOUD and not DB_FILE.exists():
    st.warning("This online copy cannot reach SQL Server on your PC. Add health_indicators.db to the "
               "repository (create it with export_data.py) and redeploy." if is_admin()
               else "The data is not available right now. Please try again later.")

prompt = st.chat_input("e.g. Show me HIV prevalence 2005-2022 as a bar chart")
needs_rerun = False
if prompt:
    try:
        with st.spinner("Generating SQL and fetching data..."):
            years = add_chart(prompt)
        if years and (years[0] is not None or years[1] is not None):
            st.session_state["_pending_range"] = years  # moves the sidebar range on the next run
        needs_rerun = True
    except Exception as exc:
        log.exception("could not build a chart for prompt %r", prompt)
        if is_admin() or isinstance(exc, ValueError):   # ValueError = a friendly message from sqlgen
            st.error(f"Could not build that chart: {exc}")
        else:   # database errors can contain the SQL text, so users only get a generic message
            st.error("Could not build that chart right now. Try rephrasing, e.g. 'malaria trends 2010-2024'.")
if needs_rerun:
    st.rerun()

render_report()

if not st.session_state.entries:
    st.info("No charts yet. Type a question below to create your first one.")

cols = st.columns(per_row)
for i, entry in enumerate(reversed(st.session_state.entries)):  # newest first
    with cols[i % per_row]:
        render_card(entry)

install_hover_tips()
