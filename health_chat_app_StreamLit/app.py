"""Eswatini health trends: chat -> SQL -> a growing dashboard of charts.

Run locally:  double-click run.bat   (or:  streamlit run app.py)
"""
import base64
import json
import os
import re
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

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
PERSIST = not IS_CLOUD   # online, charts live only in the visitor's session (no shared files)

try:
    from PIL import Image
    _icon = Image.open(LOGO_FILE)
except Exception:
    _icon = None

st.set_page_config(page_title="Eswatini Health Trends", page_icon=_icon, layout="wide")


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
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-baseweb="base-input"] { border-radius: 10px; }
[data-testid="stSidebar"] label p { font-size: 0.82rem; opacity: 0.85; }
.avatar { width: 96px; height: 96px; border-radius: 50%; object-fit: cover; display: block;
          margin: 0.3rem 0 0.8rem 0; border: 2px solid rgba(128,128,128,0.35); }
.side-title { font-size: 1.7rem; font-weight: 700; line-height: 1.2; margin: 0.2rem 0 0.3rem 0; }
.byline { font-size: 0.95rem; opacity: 0.75; margin-bottom: 1.3rem; }
.side-settings { font-size: 1.05rem; font-weight: 600; margin-bottom: 0.8rem; }
[data-testid="stMetricValue"] { font-size: 2rem; }
[data-testid="stTextArea"] textarea { font-family: ui-monospace, Consolas, monospace; font-size: 0.85rem; }
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
adv = st.sidebar.expander("Advanced: data and LLM")      # technical settings (bottom)

with adv:
    sources = [SRC_SQLSERVER, SRC_SQLITE]
    default_source = SRC_SQLITE if (IS_CLOUD and DB_FILE.exists()) else SRC_SQLSERVER
    source = st.selectbox("Data source", sources, index=sources.index(default_source),
                          help="Online (Streamlit Cloud) the app cannot reach SQL Server on your PC, "
                               "so it reads the bundled health_indicators.db file instead.")
    use_sqlite = source == SRC_SQLITE
    dialect = "sqlite" if use_sqlite else "sqlserver"

    use_llm_box = st.checkbox("Let the local LLM write the SQL", value=not IS_CLOUD, disabled=use_sqlite,
                              help="Needs Ollama running on this PC and the SQL Server data source. "
                                   "If the LLM output is invalid or off-plan, a built-in template is used.")
    use_llm = use_llm_box and not use_sqlite
    ollama_url = st.text_input("Ollama URL", "http://localhost:11434/api/generate", disabled=not use_llm)
    model = st.text_input("Model", "qwen-8k:latest", disabled=not use_llm)

    conn_str = ""
    if use_sqlite:
        db_label = "health_indicators.db (SQLite)"
        if DB_FILE.exists():
            st.caption("Using the bundled file health_indicators.db (read-only).")
        else:
            st.warning("health_indicators.db was not found next to app.py. Run export_data.py on your PC first.")
    else:
        st.markdown("**SQL Server**")
        server = st.text_input("Server", "127.0.0.1")
        database = st.text_input("Database", "DataAnalysis")
        driver = st.text_input("ODBC driver", "ODBC Driver 17 for SQL Server")
        windows_auth = st.checkbox("Windows authentication", value=True)
        sql_user = sql_pwd = ""
        if not windows_auth:
            sql_user = st.text_input("User")
            sql_pwd = st.text_input("Password", type="password")
        conn_str = (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};TrustServerCertificate=yes;"
            + ("Trusted_Connection=yes;" if windows_auth else f"UID={sql_user};PWD={sql_pwd};")
        )
        db_label = database

    st.markdown("**Breakdown column**")
    try:
        table_cols = list_columns(source, conn_str)
    except Exception as exc:
        table_cols = []
        st.warning(f"Could not read the table's columns: {exc}")
    candidates = ["DIMENSION_VALUE", "DIMENSION", "DIMENSION_DISPLAY", "DIMENSION_CODE", "DIMENSION_TYPE"]
    options = ["(none)"] + table_cols
    default = next((c for c in candidates if c in table_cols), "(none)")
    series_pick = st.selectbox("Column that splits a year into several rows", options,
                               index=options.index(default),
                               help="Draws one line per breakdown (e.g. sex or age). Pick (none) to ignore.")
    series_col = None if series_pick == "(none)" else series_pick
    if table_cols:
        st.caption("Columns: " + ", ".join(table_cols))
    dim_value = st.text_input("Only keep rows where that column equals", "",
                              help="Leave blank for no filter, e.g. type 'Total' to keep a single breakdown.")

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
st.session_state.setdefault("start_year", min_y)
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

    st.selectbox("Start year", YEARS, key="start_year", on_change=_mark_custom)
    st.selectbox("End year", YEARS, key="end_year", on_change=_mark_custom)
    st.selectbox("Select time frame", TIMEFRAMES, key="timeframe", on_change=_apply_timeframe)
    chart_pick = st.selectbox("Select a chart type", [t.capitalize() for t in catalog.CHART_TYPES])
    st.caption("The year range filters every chart instantly. A chart type or years named in your "
               "prompt override these settings (years in a prompt move the range above).")
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
    "use_llm": use_llm, "ollama_url": ollama_url, "model": model,
    "series_col": series_col, "dim_value": dim_value, "conn_str": conn_str,
    "default_chart": chart_pick.lower(), "source": source, "dialect": dialect,
}


# ---------------------------------------------------------------- data
def run_query(sql: str) -> pd.DataFrame:
    if CFG["source"] == SRC_SQLITE:
        con = _sqlite()
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


def write_sql_log():
    """Rewrite the project's single SQL log so it always matches the charts and their current titles."""
    if not PERSIST:
        return
    SQL_LOG_FILE.write_text(
        helpers.build_sql_log(st.session_state.entries, PROJECT_NAME, db_label), encoding="utf-8")


def save_dashboard():
    if not PERSIST:
        return
    keep = ("id", "prompt", "title", "sql", "original_sql", "code", "label", "kind", "chart_type",
            "source", "note", "created")
    DASH_FILE.write_text(
        json.dumps([{k: e.get(k) for k in keep} for e in st.session_state.entries], indent=2),
        encoding="utf-8",
    )
    write_sql_log()


def load_dashboard():
    st.session_state.entries, st.session_state.data = [], {}
    if not PERSIST or not DASH_FILE.exists():
        return
    try:
        saved = json.loads(DASH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    for e in saved:  # re-run only the saved SQL (no LLM calls), so reloads are fast
        try:
            st.session_state.data[e["id"]] = run_query(e["sql"])
            e["error"] = None
        except Exception as exc:
            st.session_state.data[e["id"]] = None
            e["error"] = str(exc)
        st.session_state.entries.append(e)
    write_sql_log()


def add_chart(prompt: str):
    gen = sqlgen.generate_sql(prompt, CFG)
    df = run_query(gen["sql"])
    entry = {"id": uuid.uuid4().hex[:8], "prompt": prompt, "title": prompt, "error": None,
             "original_sql": gen["sql"], "created": datetime.now().strftime("%Y-%m-%d %H:%M"), **gen}
    st.session_state.entries.append(entry)
    st.session_state.data[entry["id"]] = df
    save_dashboard()
    return gen.get("prompt_years")


def _find(eid: str):
    return next((x for x in st.session_state.entries if x["id"] == eid), None)


def run_edited_sql(eid: str, source_label: str = "edited by you"):
    """Run the SQL typed in a chart's editor, then refresh that chart, the saved dashboard and the SQL log."""
    e = _find(eid)
    if e is None:
        return
    sql = st.session_state.get(f"sql_{eid}", "").strip()
    ok, why = sqlgen.is_safe_select(sql)
    if not ok:
        e["sql_error"] = f"Not run: {why}. Only a single read-only SELECT is allowed."
        return
    try:
        df = run_query(sql)
    except Exception as exc:
        e["sql_error"] = f"Query failed: {exc}"
        return
    st.session_state.data[eid] = df
    e.update(sql=sql, source=source_label, error=None, sql_error=None, note="",
             kind="trend" if {"year", "value"} <= set(df.columns) else "discovery")
    save_dashboard()


def reset_sql(eid: str):
    e = _find(eid)
    if e and e.get("original_sql"):
        st.session_state[f"sql_{eid}"] = e["original_sql"]
        run_edited_sql(eid, "original SQL restored")


def rename_entry(eid: str):
    new = st.session_state.get(f"title_{eid}", "").strip()
    for e in st.session_state.entries:
        if e["id"] == eid:
            e["title"] = new or e["prompt"]
    save_dashboard()


def remove_entry(eid: str):
    st.session_state.entries = [e for e in st.session_state.entries if e["id"] != eid]
    st.session_state.data.pop(eid, None)
    save_dashboard()


def clear_all():
    st.session_state.entries, st.session_state.data = [], {}
    save_dashboard()


# ---------------------------------------------------------------- charts
def split_label(label: str):
    """'Estimated malaria incidence (per 1000 population at risk)' -> (name, unit)."""
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", label or "")
    return (m.group(1), m.group(2)) if m else (label or "", "")


def make_figure(df: pd.DataFrame, ctype: str, label: str = ""):
    d = df.copy()
    multi = False
    if "series" in d.columns:
        d["series"] = d["series"].fillna("(none)").astype(str)
        multi = d["series"].nunique() > 1  # one line/colour per breakdown only if there are several
    d = d.sort_values(["year", "series"] if "series" in d.columns else ["year"])
    color = "series" if multi else None
    name, unit = split_label(label)

    if ctype == "pie":
        text = d["year"].astype(str) + ((" - " + d["series"]) if multi else "")
        return px.pie(d.assign(label=text), names="label", values="value")
    if ctype == "bar":
        fig = px.bar(d, x="year", y="value", color=color, barmode="group")
    elif ctype == "area":
        fig = px.area(d, x="year", y="value", color=color)
    elif ctype == "scatter":
        fig = px.scatter(d, x="year", y="value", color=color)
    else:
        fig = px.line(d, x="year", y="value", color=color, markers=True)

    y_title = (unit[:1].upper() + unit[1:]) if unit else (name or "Value")
    fig.update_xaxes(title_text="Year", tickformat="d")
    fig.update_yaxes(title_text=y_title)
    fig.update_traces(hovertemplate=("%{fullData.name}<br>" if multi else "")
                      + "Year %{x}<br>%{y:,.2f}" + (f" {unit}" if unit else "") + "<extra></extra>")
    return fig


def render_card(e: dict):
    df = st.session_state.data.get(e["id"])
    title = e.get("title") or e["prompt"]
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(f"{e['label']}  ·  `{e['code']}`")

        if e.get("error"):
            st.error(f"Query failed: {e['error']}")
        elif df is None or df.empty:
            st.warning("No rows returned. Try another measure, or check the SQL below.")
        elif e["kind"] == "discovery" or not {"year", "value"} <= set(df.columns):
            st.dataframe(df)
            if e.get("note"):
                st.info(e["note"])
        else:
            view = df[df["year"].between(year_lo, year_hi)]  # sidebar range, applied instantly
            if view.empty:
                st.warning(f"No data between {year_lo} and {year_hi} for this indicator. "
                           "Widen the year range in the sidebar.")
            else:
                kpi = helpers.compute_kpi(view, e["code"])
                if kpi:
                    st.metric(kpi["label"], kpi["value"], delta=kpi["delta"], delta_color=kpi["color"])
                    _, unit = split_label(e.get("label", ""))
                    note = " · ".join(x for x in (kpi["basis"], unit) if x)
                    if "series" in view.columns and view["series"].nunique() > 1:
                        note += " · breakdowns are combined; pick one in Advanced for a single series"
                    if note:
                        st.caption(note)
                current = e.get("chart_type") or "line"
                ctype = st.selectbox("Chart type", catalog.CHART_TYPES,
                                     index=catalog.CHART_TYPES.index(current), key=f"type_{e['id']}")
                if ctype != current:
                    e["chart_type"] = ctype
                    save_dashboard()
                st.caption(f"Showing {year_lo}-{year_hi}  ·  {len(view)} data points")
                if ctype == "table":
                    st.dataframe(view)
                else:
                    st.plotly_chart(make_figure(view, ctype, e.get("label", "")), key=f"fig_{e['id']}")

        with st.expander("✏️ Rename chart"):
            st.text_input("Chart title", value=title, key=f"title_{e['id']}",
                          on_change=rename_entry, args=(e["id"],), label_visibility="collapsed")
        with st.expander("SQL used (you can edit it)"):
            st.caption("Dialect: " + ("SQLite" if CFG["dialect"] == "sqlite" else "T-SQL (SQL Server)")
                       + ". Edit the query, then press Run. One read-only SELECT only. "
                         "To chart it, return columns named year and value.")
            st.text_area("SQL", value=e["sql"], key=f"sql_{e['id']}", height=240, label_visibility="collapsed")
            b1, b2, _ = st.columns([1.3, 1.1, 2])
            b1.button("▶ Run edited SQL", key=f"run_{e['id']}", on_click=run_edited_sql, args=(e["id"],))
            if e.get("original_sql") and e["original_sql"].strip() != e["sql"].strip():
                b2.button("↺ Reset", key=f"reset_{e['id']}", on_click=reset_sql, args=(e["id"],))
            if e.get("sql_error"):
                st.error(e["sql_error"])
            st.caption(f"Written by: {e['source']}")
            if e.get("note") and e["kind"] != "discovery":
                st.caption(e["note"])
        st.button("Remove", key=f"rm_{e['id']}", on_click=remove_entry, args=(e["id"],))


# ---------------------------------------------------------------- page
def render_header():
    if LOGO_FILE.exists():
        b64 = base64.b64encode(LOGO_FILE.read_bytes()).decode()
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:16px;margin-bottom:4px">'
            f'<img src="data:image/png;base64,{b64}" style="height:72px">'
            f'<h1 style="margin:0;padding:0">Eswatini health trends</h1></div>',
            unsafe_allow_html=True,
        )
    else:
        st.title("Eswatini health trends")


render_header()
st.caption("Ask for a trend and name the chart type, e.g. *NCD trends line graph*, "
           "*malaria death trends 2010 to 2024 pie chart*. Each question adds a new chart; nothing is replaced.")

if IS_CLOUD and not DB_FILE.exists():
    st.warning("This online copy cannot reach SQL Server on your PC. Add health_indicators.db to the "
               "repository (create it with export_data.py) and redeploy.")

if "entries" not in st.session_state:
    load_dashboard()

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
        st.error(f"Could not build that chart: {exc}")
if needs_rerun:
    st.rerun()

top = st.columns([1, 1.3, 4])
if top[0].button("Clear all charts", disabled=not st.session_state.entries):
    clear_all()
    st.rerun()
top[1].download_button("Download SQL log", data=helpers.build_sql_log(st.session_state.entries, PROJECT_NAME, db_label),
                       file_name="sql_log.sql", mime="text/plain", disabled=not st.session_state.entries)

if not st.session_state.entries:
    st.info("No charts yet. Type a question below to create your first one.")

cols = st.columns(2)
for i, entry in enumerate(reversed(st.session_state.entries)):  # newest first
    with cols[i % 2]:
        render_card(entry)
