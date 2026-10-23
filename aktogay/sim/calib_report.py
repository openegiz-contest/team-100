"""Calibration report for the stand: the thing validation-calib in Ditto.

akt-calib (compose service, image aktogay/sim:local) is the only writer of
validation-calib (design section 2: one writer per thing). It runs
`run.py calib --quick --publish`:

  1. state RUNNING, shifts_done 0, shifts_total = N of the trial summary;
  2. the calibration (sim/calib.py, table printed as before);
  3. state DONE (FAILED when no row was computed), report_json, shifts_done.

report_json is one JSON text: the calibration rows (group, name, model,
report, unit, tol, ok, note), errors, seconds, and the summary of the on/off
trial of the issue queue (sim/trial.py, file sim/data/trial_n100.json: config,
statistics, cuts; the per-shift rows stay out). The trial is not recomputed
here: 100 shifts take about 3 min on 3 processes, so the stand shows the file
written by `run.py trial --n 100 --no-twin`; the same seeds give the same
numbers.

Writes go to Ditto HTTP as merge patches on /features (definitions stay),
header x-correlation-id akt-calib-validation-calib, so Telegraf keeps one
series for this writer. Ditto may answer 503 for a while after start: every
write is retried. A failed write is printed and does not change the exit
code of the calibration (always 0).

Environment: DITTO_URL (http://ditto-nginx:80), DITTO_USER (ditto),
DITTO_PASSWORD.
"""
from __future__ import annotations

import base64
import json
import math
import os
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TRIAL_DEFAULT = os.path.join(HERE, "data", "trial_n100.json")
NS = "kz.aktogay"
THING = "validation-calib"
ROW_KEYS = ("group", "name", "model", "report", "unit", "tol", "ok", "note")
TRIAL_KEYS = ("config", "policy", "n", "seeds", "notes", "summary", "cuts", "loss_vs_base_cu_t_2000", "seconds",
              "command")
MAX_REPORT_BYTES = 60_000           # Ditto keeps a thing below 100 kB; InfluxDB strings below 64 kB


def load_trial(path: str | None) -> dict | None:
    """Trial summary (keys of TRIAL_KEYS) or None when the file is absent or broken."""
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        print(f"trial summary not read ({path}): {e}")
        return None
    if not isinstance(doc, dict) or "summary" not in doc:
        print(f"trial summary not read ({path}): no 'summary'")
        return None
    return {k: doc[k] for k in TRIAL_KEYS if k in doc}


def _round(x, nd: int = 6):
    """Rounded copy; NaN and infinities become None (JSON has no such numbers)."""
    if isinstance(x, float):
        return round(x, nd) if math.isfinite(x) else None
    if isinstance(x, list):
        return [_round(v, nd) for v in x]
    if isinstance(x, dict):
        return {k: _round(v, nd) for k, v in x.items()}
    return x


def build_report(calib: dict, trial: dict | None) -> dict:
    """The document stored in validation-calib.report_json (compact, rounded)."""
    rows = [{k: r.get(k) for k in ROW_KEYS} for r in calib.get("rows", [])]
    doc = {
        "kind": "akt-calib",
        "version": 1,
        "seed": calib.get("seed"),
        "quick": bool(calib.get("quick", False)),
        "seconds": (calib.get("seconds") or {}).get("total"),
        "errors": list(calib.get("errors", [])),
        "rows": rows,
        "fitted": calib.get("fitted", {}),
        "trial": trial,
    }
    doc = _round(doc)
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(text.encode("utf-8")) > MAX_REPORT_BYTES and trial is not None:
        doc["trial"] = {k: v for k, v in trial.items() if k != "cuts"}
    return doc


def report_text(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def trial_n(trial: dict | None) -> float:
    try:
        return float(trial["n"]) if trial else 0.0
    except (KeyError, TypeError, ValueError):
        return 0.0


class DittoWriter:
    """Merge patches on kz.aktogay:validation-calib/features over Ditto HTTP."""

    def __init__(self, url: str, user: str, password: str, tries: int = 20, pause_s: float = 3.0,
                 timeout_s: float = 15.0):
        self.url = url.rstrip("/")
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.tries, self.pause_s, self.timeout_s = tries, pause_s, timeout_s
        self.run = "akt-calib-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

    @classmethod
    def from_env(cls) -> "DittoWriter":
        return cls(os.environ.get("DITTO_URL", "http://ditto-nginx:80"), os.environ.get("DITTO_USER", "ditto"),
                   os.environ.get("DITTO_PASSWORD", ""))

    def patch(self, values: dict) -> bool:
        feats = {k: {"properties": {"value": v}} for k, v in values.items()}
        feats["idSimulationRun"] = {"properties": {"value": self.run}}
        body = json.dumps(feats, ensure_ascii=False, allow_nan=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url}/api/2/things/{NS}:{THING}/features", data=body, method="PATCH",
            headers={"Authorization": self.auth, "Content-Type": "application/merge-patch+json",
                     "x-correlation-id": f"akt-calib-{THING}"})
        last = ""
        for i in range(self.tries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                    r.read()
                return True
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}"
                if e.code not in (408, 429, 502, 503, 504):
                    break
            except (urllib.error.URLError, OSError) as e:
                last = str(e)
            if i + 1 < self.tries:
                time.sleep(self.pause_s)
        print(f"validation-calib not written: {last}")
        return False


def publish_start(writer: DittoWriter, trial: dict | None) -> bool:
    return writer.patch({"state": "RUNNING", "shifts_done": 0.0, "shifts_total": trial_n(trial), "sim_time": -1.0})


def publish_done(writer: DittoWriter, calib: dict, trial: dict | None) -> bool:
    doc = build_report(calib, trial)
    state = "DONE" if doc["rows"] else "FAILED"
    n = trial_n(doc.get("trial"))
    ok = writer.patch({"state": state, "report_json": report_text(doc), "shifts_done": n, "shifts_total": n,
                       "sim_time": -1.0})
    if ok:
        print(f"validation-calib: {state}, {len(doc['rows'])} rows, trial N {n:.0f}, run {writer.run}")
    return ok
