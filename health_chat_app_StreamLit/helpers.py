"""Pure helpers: KPI numbers for each chart and the SQL log text (no Streamlit needed)."""
from datetime import datetime

import catalog


def fmt_num(v: float, signed: bool = False, whole: bool = False) -> str:
    a = abs(v)
    decimals = 0 if (whole or a >= 1000) else (1 if a >= 100 else 2)
    return f"{v:+,.{decimals}f}" if signed else f"{v:,.{decimals}f}"


def compute_kpi(view, code: str):
    """KPI for the rows currently shown (already filtered to the sidebar year range).

    Counts  -> total over the range.      Rates / % / stocks -> latest value.
    Delta   -> change from the first to the last year in the range (absolute and %): green up, red down.
    """
    is_count = catalog.is_count(code)
    grouped = view.groupby("year")["value"]
    yearly = (grouped.sum() if is_count else grouped.mean()).dropna().sort_index()
    if yearly.empty:
        return None

    first_y, last_y = int(yearly.index[0]), int(yearly.index[-1])
    first_v, last_v = float(yearly.iloc[0]), float(yearly.iloc[-1])
    whole = is_count and all(abs(x - round(x)) < 1e-9 for x in yearly)

    if is_count:
        main = float(yearly.sum())
        label = f"Total, {first_y}" if first_y == last_y else f"Total, {first_y}-{last_y}"
    else:
        main = last_v
        label = f"Latest value ({last_y})"

    delta, color, basis = None, "off", ""
    if len(yearly) >= 2:
        diff = last_v - first_v
        if first_v != 0:
            pct = f"{diff / abs(first_v) * 100:+.1f}%"
        else:
            pct = "n/a" if diff else "0.0%"
        delta = f"{fmt_num(diff, signed=True, whole=whole)} ({pct})"
        if diff != 0:
            color = "normal"  # rising = green, dropping = red (always, whatever the indicator)
        basis = (f"Change from {first_y} ({fmt_num(first_v, whole=whole)}) "
                 f"to {last_y} ({fmt_num(last_v, whole=whole)})")
    return {"label": label, "value": fmt_num(main, whole=whole), "delta": delta,
            "color": color, "basis": basis, "is_count": is_count}


def build_sql_log(entries, project: str, database: str) -> str:
    """One plain .sql file: a commented heading + the SQL for every chart on the dashboard."""
    line = "-- " + "=" * 70
    out = [line, f"-- {project} - SQL log",
           f"-- Updated  : {datetime.now():%Y-%m-%d %H:%M}",
           f"-- Database : {database}",
           f"-- Charts   : {len(entries)}", line, ""]
    for i, e in enumerate(entries, 1):
        title = " ".join((e.get("title") or e["prompt"]).split())
        prompt = " ".join(e["prompt"].split())
        out += [
            "-- " + "-" * 70,
            f"-- [{i}] {title}",
            f"-- Prompt    : {prompt}",
            f"-- Indicator : {e.get('code', '-')} - {e.get('label', '')}",
            f"-- Created   : {e.get('created') or 'unknown'}",
            f"-- SQL by    : {e.get('source', '')}",
            "-- " + "-" * 70,
            e["sql"].strip(),
            "",
        ]
    return "\n".join(out) + "\n"


_FLIP = ("html { filter: invert(1) hue-rotate(180deg); } "
         "img, video, canvas { filter: invert(1) hue-rotate(180deg); }")


def appearance_css(choice: str, actual=None) -> str:
    """CSS for the Auto / Light / Dark switch.

    Auto  -> nothing (Streamlit follows the browser/OS theme).
    Light / Dark -> flip the page's colours when the theme currently shown is the other one.
    `actual` is the theme Streamlit is rendering ('light'/'dark'); if unknown we use the browser's
    prefers-color-scheme media query instead. Images are flipped back so the logo keeps its colours.
    """
    if choice not in ("Light", "Dark"):
        return ""
    want = choice.lower()
    if actual in ("light", "dark"):
        return f"<style>{_FLIP}</style>" if actual != want else ""
    other = "light" if want == "dark" else "dark"
    return f"<style>@media (prefers-color-scheme: {other}) {{ {_FLIP} }}</style>"
