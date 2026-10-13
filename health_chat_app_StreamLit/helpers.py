"""Pure helpers: KPI numbers for each chart and the SQL log text (no Streamlit needed)."""
import html
import re
from datetime import datetime

import catalog


def fmt_num(v: float, signed: bool = False, whole: bool = False) -> str:
    a = abs(v)
    decimals = 0 if (whole or a >= 1000) else (1 if a >= 100 else 2)
    return f"{v:+,.{decimals}f}" if signed else f"{v:,.{decimals}f}"


def split_label(label: str):
    """'Estimated malaria incidence (per 1000 population at risk)' -> (name, unit)."""
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", label or "")
    return (m.group(1), m.group(2)) if m else (label or "", "")


def unit_parts(unit: str):
    """Return (is_percent, small_text) for the unit shown next to the big number."""
    if "%" in unit:
        note = re.sub(r"\s*,?\s*%\s*,?\s*", " ", unit).strip(" ,")
        return True, note
    return False, unit


def compute_kpi(view, code: str, label: str = ""):
    """Everything the KPI block needs, in plain words, for the rows currently shown.

    Counts  -> total over the range.      Rates / % / stocks -> latest value.
    Change  -> first year vs last year in the range: absolute and relative %, green up / red down.
    """
    is_count = catalog.is_count(code)
    grouped = view.groupby("year")["value"]
    yearly = (grouped.sum() if is_count else grouped.mean()).dropna().sort_index()
    if yearly.empty:
        return None

    name, unit = split_label(label)
    name = name or code
    percent, unit_note = unit_parts(unit)
    first_y, last_y = int(yearly.index[0]), int(yearly.index[-1])
    first_v, last_v = float(yearly.iloc[0]), float(yearly.iloc[-1])
    whole = is_count and all(abs(x - round(x)) < 1e-9 for x in yearly)

    def num(x, signed=False):
        return fmt_num(x, signed=signed, whole=whole) + ("%" if percent and not signed else "")

    if is_count:
        main = float(yearly.sum())
        period = f"{first_y}" if first_y == last_y else f"{first_y}-{last_y} combined"
        head = f"{name} · {period}"
    else:
        main = last_v
        head = f"{name} · latest ({last_y})"

    out = {"head": head, "value_text": num(main), "unit_text": unit_note if percent else unit,
           "delta_text": None, "direction": None, "delta_tip": "", "basis": ""}
    if len(yearly) >= 2:
        diff = last_v - first_v
        if first_v != 0:
            pct = f"{diff / abs(first_v) * 100:+.1f}%"
        else:
            pct = "n/a" if diff else "0.0%"
        amount = fmt_num(diff, signed=True, whole=whole) + (" pp" if percent else "")
        if diff == 0:
            out["direction"], out["delta_text"] = "flat", f"● no change since {first_y}"
        else:
            out["direction"] = "up" if diff > 0 else "down"
            out["delta_text"] = f"{'▲' if diff > 0 else '▼'} {amount} ({pct}) since {first_y}"
        out["delta_tip"] = (f"Change in the yearly figure from {first_y} to {last_y}. "
                            f"{'pp = percentage points. ' if percent else ''}"
                            f"The percentage in brackets is relative to the {first_y} value.")
        if is_count:
            out["basis"] = f"Total of all years shown. Change compares the yearly figure: {num(first_v)} in {first_y}, {num(last_v)} in {last_y}."
        else:
            out["basis"] = f"Change compares {first_y} ({num(first_v)}) with {last_y} ({num(last_v)})."
    return out


def kpi_html(k: dict, code: str, label: str, extra: str = "") -> str:
    """The big-number block: what it is, its unit, and what the change means."""
    e = html.escape
    parts = [f'<div class="kpi" title="{e(label)} ({e(code)})">',
             f'<div class="kpi-label">{e(k["head"])}</div>',
             f'<div class="kpi-value">{e(k["value_text"])}'
             + (f'<span class="kpi-unit">{e(k["unit_text"])}</span>' if k["unit_text"] else "") + "</div>"]
    if k["delta_text"]:
        parts.append(f'<div class="kpi-delta {k["direction"]}" title="{e(k["delta_tip"])}">{e(k["delta_text"])}</div>')
    else:
        parts.append('<div class="kpi-basis">Only one year in this range, so no change is shown.</div>')
    if k["basis"]:
        parts.append(f'<div class="kpi-basis">{e(k["basis"])}</div>')
    if extra:
        parts.append(f'<div class="kpi-basis">{e(extra)}</div>')
    parts.append("</div>")
    return "".join(parts)


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
