"""Background live updates Artiphact runs after an AI starts a job.

Example: user tells Claude "keep NFL scores up to date on my panel" → Claude
calls start_live_update → this worker refreshes the e-ink on a timer.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connector"))
sys.path.insert(0, str(ROOT / "templates"))

from intake import intake_page  # noqa: E402

JOBS_PATH = Path(os.environ.get("ARTIPHACT_LIVE_JOBS", ROOT / "connector" / "live_jobs.json"))
ESPN_NFL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"


def load_jobs() -> dict:
    if not JOBS_PATH.is_file():
        return {"jobs": []}
    try:
        data = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"jobs": []}
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        return {"jobs": []}
    return data


def save_jobs(data: dict):
    JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    JOBS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


SUPPORTED_KINDS = {"nfl_scores", "counter"}


def upsert_job(*, kind: str, interval_sec: int, title: str = "") -> dict:
    kind = kind.strip().lower()
    if kind not in SUPPORTED_KINDS:
        raise ValueError("Supported live kinds: nfl_scores, counter")
    # Counter can tick fast; scoreboards stay at least once a minute.
    lo = 5 if kind == "counter" else 60
    interval_sec = max(lo, min(int(interval_sec), 3600))
    data = load_jobs()
    prev = next((j for j in data["jobs"] if j.get("kind") == kind), None)
    jobs = [j for j in data["jobs"] if j.get("kind") != kind]
    job = {
        "kind": kind,
        "interval_sec": interval_sec,
        "title": title or ("Counter" if kind == "counter" else kind),
        "enabled": True,
        "last_run": 0,
        "count": int((prev or {}).get("count") or 0),
    }
    jobs.append(job)
    data["jobs"] = jobs
    save_jobs(data)
    return job


def stop_job(kind: str | None = None) -> int:
    data = load_jobs()
    if kind:
        kind = kind.strip().lower()
        before = len(data["jobs"])
        data["jobs"] = [j for j in data["jobs"] if j.get("kind") != kind]
        save_jobs(data)
        return before - len(data["jobs"])
    n = len(data["jobs"])
    data["jobs"] = []
    save_jobs(data)
    return n


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "ArtiphactLive/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def render_nfl_html(payload: dict) -> str:
    events = payload.get("events") or []
    rows = []
    for event in events[:12]:
        name = escape(str(event.get("name") or "Game"))
        status = ""
        competitions = event.get("competitions") or []
        if competitions:
            status = escape(str((competitions[0].get("status") or {}).get("type", {}).get("shortDetail") or ""))
            teams = competitions[0].get("competitors") or []
            parts = []
            for team in teams:
                abbrev = escape(str((team.get("team") or {}).get("abbreviation") or "?"))
                score = escape(str(team.get("score") or "0"))
                parts.append(f"{abbrev} {score}")
            line = "  ·  ".join(parts) if parts else name
        else:
            line = name
        rows.append(f"<div class='game'><div class='line'>{line}</div><div class='meta'>{status}</div></div>")
    body = "\n".join(rows) or "<div class='game'>No games right now.</div>"
    stamp = time.strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:800px;height:480px;background:#fff;color:#000;font-family:Georgia,serif;overflow:hidden}}
.wrap{{padding:22px 28px;box-sizing:border-box;height:480px}}
h1{{margin:0 0 4px;font-size:34px;letter-spacing:.06em}}
.sub{{margin:0 0 16px;font-size:14px}}
.game{{border-top:2px solid #000;padding:8px 0}}
.line{{font-size:22px}}
.meta{{font-size:14px;margin-top:2px}}
</style></head><body><div class="wrap">
<h1>NFL SCORES</h1>
<p class="sub">Updated {escape(stamp)} · Artiphact live</p>
{body}
</div></body></html>"""


def render_counter_html(n: int, title: str = "Counter") -> str:
    stamp = time.strftime("%H:%M:%S")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:800px;height:480px;background:#fff;color:#000;
font-family:Georgia,serif;overflow:hidden}}
.wrap{{display:flex;flex-direction:column;justify-content:center;align-items:center;
height:480px;box-sizing:border-box;padding:24px}}
h1{{margin:0;font-size:28px;letter-spacing:.12em;text-transform:uppercase}}
.num{{margin:18px 0 0;font-size:180px;line-height:1;font-weight:700}}
.sub{{margin:16px 0 0;font-size:18px}}
</style></head><body><div class="wrap">
<h1>{escape(title or "Counter")}</h1>
<div class="num">{n}</div>
<p class="sub">Artiphact live · {escape(stamp)}</p>
</div></body></html>"""


def run_job(job: dict) -> dict:
    kind = job.get("kind")
    if kind == "nfl_scores":
        data = fetch_json(ESPN_NFL)
        html = render_nfl_html(data)
        return intake_page(html=html, title=job.get("title") or "NFL scores", source="live-nfl", push=True)
    if kind == "counter":
        n = int(job.get("count") or 0) + 1
        job["count"] = n
        html = render_counter_html(n, str(job.get("title") or "Counter"))
        return intake_page(html=html, title=job.get("title") or "Counter", source="live-counter", push=True)
    raise ValueError(f"Unknown job kind: {kind}")


def tick_once() -> int:
    data = load_jobs()
    now = time.time()
    ran = 0
    changed = False
    for job in data["jobs"]:
        if not job.get("enabled", True):
            continue
        kind = job.get("kind")
        lo = 5 if kind == "counter" else 60
        interval = max(lo, int(job.get("interval_sec") or 300))
        last = float(job.get("last_run") or 0)
        if now - last < interval:
            continue
        try:
            result = run_job(job)
            print(f"live_job {job.get('kind')}: {result}", flush=True)
            job["last_run"] = now
            job["last_ok"] = True
            job["last_error"] = ""
            ran += 1
            changed = True
        except Exception as exc:
            job["last_ok"] = False
            job["last_error"] = str(exc)[:200]
            job["last_run"] = now
            changed = True
            print(f"live_job error {job.get('kind')}: {exc}", flush=True)
    if changed:
        save_jobs(data)
    return ran


def watch_loop(poll_sec: float = 5.0):
    print("Artiphact live jobs worker started", flush=True)
    while True:
        try:
            tick_once()
        except Exception as exc:
            print(f"live_jobs loop: {exc}", flush=True)
        time.sleep(poll_sec)


if __name__ == "__main__":
    watch_loop()
