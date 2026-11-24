"""Build 800x480 black/white chart HTML from structured data.

No external URLs or fonts. All text is HTML-escaped. Safe for e-ink + Playwright.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Sequence

WIDTH = 800
HEIGHT = 480
CHART_TYPES = frozenset({"auto", "bar", "line", "hbar", "table"})


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _pick_type(chart_type: str, n: int) -> str:
    kind = (chart_type or "auto").strip().lower()
    if kind not in CHART_TYPES:
        kind = "auto"
    if kind != "auto":
        return kind
    if n <= 8:
        return "bar"
    if n <= 14:
        return "hbar"
    return "table"


def _nice_max(values: Sequence[float]) -> float:
    peak = max(abs(v) for v in values) if values else 1.0
    if peak <= 0:
        return 1.0
    # Round up to a clean scale.
    import math

    exp = math.floor(math.log10(peak))
    base = 10**exp
    for mult in (1, 2, 2.5, 5, 10):
        candidate = mult * base
        if candidate >= peak:
            return candidate
    return peak * 1.1


def _fmt_value(v: float, unit: str) -> str:
    if abs(v - round(v)) < 1e-9:
        text = str(int(round(v)))
    elif abs(v) >= 100:
        text = f"{v:.0f}"
    else:
        text = f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{text}{unit}" if unit else text


def _shell(title: str, subtitle: str, body_html: str, footer: str) -> str:
    sub = f'<div class="sub">{_esc(subtitle)}</div>' if subtitle.strip() else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<style>
  html, body {{ margin: 0; background: #fff; }}
  .panel {{
    width: {WIDTH}px;
    height: {HEIGHT}px;
    background: #fff;
    color: #000;
    font-family: "Arial Narrow", "Franklin Gothic Medium", Arial, sans-serif;
    box-sizing: border-box;
    overflow: hidden;
  }}
  .band {{
    height: 56px;
    background: #000;
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 24px;
    letter-spacing: 0.12em;
  }}
  .brand {{ font-size: 22px; font-weight: 700; }}
  .date {{ font-size: 18px; letter-spacing: 0.1em; }}
  .body {{ padding: 16px 24px 0; }}
  h1 {{
    margin: 0 0 4px;
    font-size: 34px;
    letter-spacing: 0.06em;
    font-weight: 800;
    line-height: 1.1;
  }}
  .sub {{
    margin: 0 0 10px;
    font-size: 16px;
    letter-spacing: 0.08em;
  }}
  .rule {{ height: 4px; background: #000; margin-bottom: 14px; }}
  .footer {{
    margin-top: 8px;
    font-size: 13px;
    letter-spacing: 0.16em;
  }}
  .chart {{
    position: relative;
    height: 300px;
    border-left: 3px solid #000;
    border-bottom: 3px solid #000;
    margin: 0 8px 0 4px;
    box-sizing: border-box;
  }}
  .bars {{
    display: flex;
    align-items: flex-end;
    justify-content: space-around;
    height: 100%;
    padding: 0 8px 0;
    box-sizing: border-box;
  }}
  .col {{
    flex: 1;
    max-width: 72px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-end;
    height: 100%;
    margin: 0 4px;
  }}
  .val {{
    font-size: 14px;
    font-weight: 700;
    margin-bottom: 4px;
    letter-spacing: 0.04em;
  }}
  .bar {{
    width: 100%;
    background: #000;
    min-height: 2px;
  }}
  .lab {{
    margin-top: 6px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-align: center;
    max-width: 100%;
    overflow: hidden;
    white-space: nowrap;
  }}
  .hbars {{ padding: 0; }}
  .hrow {{
    display: flex;
    align-items: center;
    margin: 0 0 10px;
    height: 28px;
  }}
  .hlab {{
    width: 120px;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.04em;
    overflow: hidden;
    white-space: nowrap;
    flex-shrink: 0;
  }}
  .htrack {{
    flex: 1;
    height: 18px;
    border: 2px solid #000;
    box-sizing: border-box;
    margin: 0 10px;
  }}
  .hfill {{ height: 100%; background: #000; }}
  .hval {{
    width: 72px;
    text-align: right;
    font-size: 16px;
    font-weight: 700;
    flex-shrink: 0;
  }}
  .linewrap {{ position: relative; height: 100%; }}
  .linewrap svg {{ display: block; width: 100%; height: 100%; }}
  .xticks {{
    display: flex;
    justify-content: space-between;
    padding: 6px 4px 0;
    font-size: 12px;
    font-weight: 700;
  }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{
    text-align: left;
    font-size: 14px;
    letter-spacing: 0.14em;
    padding: 0 0 8px;
    border-bottom: 2px solid #000;
  }}
  th.num, td.num {{ text-align: right; }}
  td {{
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 0.03em;
    padding: 6px 0;
    border-bottom: 1px solid #000;
  }}
</style>
</head>
<body>
<main class="panel">
  <header class="band">
    <div class="brand">FENNSILL</div>
    <div class="date">{_esc(footer)}</div>
  </header>
  <div class="body">
    <h1>{_esc(title)}</h1>
    {sub}
    <div class="rule"></div>
    {body_html}
  </div>
</main>
</body>
</html>
"""


def _bars(labels: Sequence[str], values: Sequence[float], unit: str) -> str:
    peak = _nice_max(values)
    cols = []
    for lab, val in zip(labels, values):
        pct = max(0.0, min(100.0, (abs(val) / peak) * 100.0))
        cols.append(
            f'<div class="col">'
            f'<div class="val">{_esc(_fmt_value(val, unit))}</div>'
            f'<div class="bar" style="height:{pct:.1f}%"></div>'
            f'<div class="lab">{_esc(lab)}</div>'
            f"</div>"
        )
    return f'<div class="chart"><div class="bars">{"".join(cols)}</div></div>'


def _hbars(labels: Sequence[str], values: Sequence[float], unit: str) -> str:
    peak = _nice_max(values)
    rows = []
    for lab, val in zip(labels, values):
        pct = max(0.0, min(100.0, (abs(val) / peak) * 100.0))
        rows.append(
            f'<div class="hrow">'
            f'<div class="hlab">{_esc(lab)}</div>'
            f'<div class="htrack"><div class="hfill" style="width:{pct:.1f}%"></div></div>'
            f'<div class="hval">{_esc(_fmt_value(val, unit))}</div>'
            f"</div>"
        )
    return f'<div class="hbars">{"".join(rows)}</div>'


def _line(labels: Sequence[str], values: Sequence[float], unit: str) -> str:
    peak = _nice_max(values)
    n = len(values)
    w, h, pad = 740, 260, 16
    if n == 1:
        points = [(w / 2, h - pad - (abs(values[0]) / peak) * (h - 2 * pad))]
    else:
        points = []
        for i, val in enumerate(values):
            x = pad + (i / (n - 1)) * (w - 2 * pad)
            y = h - pad - (abs(val) / peak) * (h - 2 * pad)
            points.append((x, y))
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#000"/>' for x, y in points
    )
    # Show up to 8 tick labels to avoid clutter.
    step = max(1, (n + 7) // 8)
    tick_html = "".join(
        f"<span>{_esc(lab)}</span>" if (i % step == 0 or i == n - 1) else "<span></span>"
        for i, lab in enumerate(labels)
    )
    ymax = _esc(_fmt_value(peak, unit))
    return (
        f'<div class="chart linewrap">'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
        f'<text x="8" y="18" font-size="14" font-weight="700">{ymax}</text>'
        f'<polyline fill="none" stroke="#000" stroke-width="4" points="{poly}"/>'
        f"{dots}"
        f"</svg>"
        f'<div class="xticks">{tick_html}</div>'
        f"</div>"
    )


def _table(labels: Sequence[str], values: Sequence[float], unit: str) -> str:
    rows = "".join(
        f"<tr><td>{_esc(lab)}</td><td class=\"num\">{_esc(_fmt_value(val, unit))}</td></tr>"
        for lab, val in zip(labels, values)
    )
    unit_h = f" ({_esc(unit)})" if unit else ""
    return (
        "<table>"
        f"<thead><tr><th>LABEL</th><th class=\"num\">VALUE{unit_h}</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def render_chart_html(
    *,
    title: str,
    labels: Sequence[str],
    values: Sequence[float],
    chart_type: str = "auto",
    unit: str = "",
    subtitle: str = "",
) -> str:
    """Return a finished self-contained 800x480 HTML page."""
    if len(labels) != len(values) or not labels:
        raise ValueError("labels and values must be non-empty and the same length.")
    kind = _pick_type(chart_type, len(labels))
    if kind == "bar":
        body = _bars(labels, values, unit)
    elif kind == "line":
        body = _line(labels, values, unit)
    elif kind == "hbar":
        body = _hbars(labels, values, unit)
    else:
        body = _table(labels, values, unit)
    footer = datetime.now(timezone.utc).strftime("%b %d").upper()
    return _shell(title, subtitle, body, footer)
