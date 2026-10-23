"""Create the Aktogay policy and things in Ditto from things.json, then check the models.

Create if absent (PUT with If-None-Match: *): an existing thing is never
replaced, so live data stays and a second run changes nothing.

  python -I aktogay/setup/setup.py              create what is missing, check models, summary
  python -I aktogay/setup/setup.py --sync       also update definition and attributes that differ
  python -I aktogay/setup/setup.py --probe-all  skeleton probe for every type, not one

Environment: DITTO_URL (default http://localhost:8080), DITTO_USER (ditto),
DITTO_PASSWORD (required), MODELS_URL (model files as seen from here; default
model_base of things.json), WAIT_S (450).
Exit 0 when the policy and every thing exist; with --strict the model check must pass too.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import twins  # noqa: E402

RETRY = {0, 408, 429, 500, 502, 503, 504}
TD_JSON = "application/td+json"
MERGE_JSON = "application/merge-patch+json"


def _parse(raw: bytes):
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text) if text else None
    except ValueError:
        return text


def short(payload, n: int = 160) -> str:
    s = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "..."


class Ditto:
    """Minimal Ditto HTTP client (urllib, no proxies)."""

    def __init__(self, url: str, user: str, password: str, timeout: float = 30.0):
        self.url = url.rstrip("/")
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.timeout = timeout

    def request(self, method: str, path: str, body=None, headers: dict | None = None, retries: int = 10):
        """(status, parsed body); status 0 = no answer. Retries no answer, 408, 429 and 5xx."""
        h = {"Authorization": self.auth}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        status, payload = 0, None
        for attempt in range(retries):
            req = urllib.request.Request(self.url + path, data=data, method=method, headers=h)
            try:
                with self.opener.open(req, timeout=self.timeout) as r:
                    return r.status, _parse(r.read())
            except urllib.error.HTTPError as e:
                status, payload = e.code, _parse(e.read())
            except OSError as e:
                status, payload = 0, str(e)
            if status not in RETRY or attempt == retries - 1:
                break
            time.sleep(3)
        return status, payload


def fetch_json(opener, url: str, timeout: float = 15.0):
    with opener.open(urllib.request.Request(url), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------------------
def wait_ready(d: Ditto, policy_id: str, wait_s: float) -> float:
    """Wait until Ditto answers a policy read (200 or 404)."""
    t0 = time.time()
    while True:
        status, payload = d.request("GET", f"/api/2/policies/{policy_id}", retries=1)
        if status in (200, 404):
            return time.time() - t0
        if status in (401, 403):
            raise SystemExit(f"Ditto refused the credentials: {status} {short(payload)}")
        if time.time() - t0 > wait_s:
            raise SystemExit(f"Ditto not ready after {wait_s:.0f} s: {status} {short(payload)}")
        time.sleep(5)


def ensure_policy(d: Ditto, m: twins.Model, sync: bool) -> str:
    path = f"/api/2/policies/{m.policy_id}"
    body = m.policy_body()
    status, payload = d.request("PUT", path, body, {"If-None-Match": "*"})
    if status == 201:
        return "created"
    if status != 412:
        raise SystemExit(f"policy {m.policy_id}: {status} {short(payload)}")
    if sync:
        status, cur = d.request("GET", path + "/entries")
        strip = lambda e: {k: {kk: vv for kk, vv in v.items() if kk != "importable"} for k, v in (e or {}).items()}  # noqa: E731
        if status == 200 and strip(cur) != strip(body["entries"]):
            status, payload = d.request("PUT", path, body)
            if status in (200, 204):
                return "updated"
            raise SystemExit(f"policy {m.policy_id}: update {status} {short(payload)}")
    return "exists"


def ensure_thing(d: Ditto, m: twins.Model, thing: dict, sync: bool) -> tuple[str, str]:
    """(result, detail): created, exists, updated or failed."""
    tid = m.tid(thing["name"])
    path = f"/api/2/things/{tid}"
    body = m.thing_body(thing)
    hdr = {"x-correlation-id": f"akt-setup-{thing['name']}"}
    status, payload = d.request("PUT", path, body, dict(hdr, **{"If-None-Match": "*"}))
    if status == 201:
        return "created", ""
    if status != 412:
        return "failed", f"{status} {short(payload)}"
    if not sync:
        return "exists", ""
    status, cur = d.request("GET", path + "?fields=definition,attributes")
    if status != 200:
        return "failed", f"read {status} {short(cur)}"
    changed = []
    if cur.get("definition") != body["definition"]:
        status, payload = d.request("PUT", path + "/definition", body["definition"], hdr)
        changed.append(f"definition {status}")
    if cur.get("attributes") != body["attributes"]:
        status, payload = d.request("PUT", path + "/attributes", body["attributes"], hdr)
        changed.append(f"attributes {status}")
    if not changed:
        return "exists", ""
    ok = all(c.endswith(("200", "201", "204")) for c in changed)
    return ("updated" if ok else "failed"), ", ".join(changed)


# ---------------------------------------------------------------------------
def models_check(m: twins.Model, fetch_base: str) -> tuple[int, list[str]]:
    """Every model file is served at fetch_base and equals what things.json gives."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    want = m.all_tms()
    bad = []
    for fname, tm in want.items():
        try:
            if fetch_json(opener, fetch_base + fname) != tm:
                bad.append(f"{fname}: differs from things.json (run gen_tm.py)")
        except (OSError, ValueError) as e:
            bad.append(f"{fname}: {e}")
    return len(want), bad


def probe(d: Ditto, m: twins.Model, typ: str, name: str) -> tuple[bool, str]:
    """Create a thing with only a definition; Ditto must build attributes and features from the TM."""
    tid = m.tid(name)
    path = f"/api/2/things/{tid}"
    d.request("DELETE", path)
    status, payload = d.request("PUT", path, {"policyId": m.policy_id, "definition": m.url(m.type_file(typ))},
                                {"If-None-Match": "*", "x-correlation-id": f"akt-setup-{name}"})
    if status != 201:
        return False, f"create {status} {short(payload)}"
    try:
        problems = []
        status, thing = d.request("GET", path)
        attrs = (thing or {}).get("attributes", {}) if status == 200 else {}
        feats = (thing or {}).get("features", {}) if status == 200 else {}
        want_attrs = list(m.type_tm(typ)["properties"])
        missing = [k for k in want_attrs if k not in attrs]
        if missing:
            problems.append("attributes missing: " + ",".join(missing))
        if attrs.get("type") != typ or attrs.get("_isType") is not False:
            problems.append("attribute defaults type/_isType wrong")
        want_f = m.feature_map(typ)
        if set(feats) != set(want_f):
            problems.append(f"features {len(feats)} of {len(want_f)}")
        for f, fname in want_f.items():
            g = feats.get(f, {})
            if g.get("definition") != [m.url(fname)] or g.get("properties") != m.feature_default(typ, f):
                problems.append(f"feature {f}: {short(g, 80)}")
                break
        status, td = d.request("GET", path, headers={"Accept": TD_JSON})
        td_ok = status == 200 and isinstance(td, dict) and td.get("title") == m.types[typ]["title"]
        if not td_ok:
            problems.append(f"TD {status} {short(td, 80)}")
        f0 = next(iter(want_f))
        status_f, ftd = d.request("GET", f"{path}/features/{f0}", headers={"Accept": TD_JSON})
        if status_f != 200 or not isinstance(ftd, dict) or "value" not in ftd.get("properties", {}):
            problems.append(f"feature TD {status_f} {short(ftd, 80)}")
        info = (f"skeleton {len(attrs)} attributes, {len(feats)} features; "
                f"TD {status}: {len((td or {}).get('properties', {})) if td_ok else 0} properties, "
                f"{len((td or {}).get('links', [])) if td_ok else 0} links; feature TD {status_f}")
        return not problems, info + ("" if not problems else "; " + "; ".join(problems))
    finally:
        d.request("DELETE", path)


def td_check(d: Ditto, m: twins.Model) -> tuple[int, list[str]]:
    """Thing Description of one thing per type through Ditto: it fetches and parses the type TM."""
    first = {}
    for t in m.things:
        first.setdefault(t["type"], t["name"])
    bad = []
    for typ, name in first.items():
        status, td = d.request("GET", f"/api/2/things/{m.tid(name)}", headers={"Accept": TD_JSON})
        ok = (status == 200 and isinstance(td, dict) and td.get("title") == m.types[typ]["title"]
              and len(td.get("links", [])) == 1 + len(m.feature_map(typ)))   # type link + one per feature
        if not ok:
            bad.append(f"{name}: {status} {short(td, 80)}")
    return len(first), bad


def write_validation(d: Ditto, m: twins.Model, values: dict) -> str:
    """Merge changed values into validation-setup (single writer: this script)."""
    if "validation-setup" not in m.by_name:
        return "not declared"
    tid = m.tid("validation-setup")
    status, cur = d.request("GET", f"/api/2/things/{tid}/features")
    if status != 200:
        return f"read failed {status}"
    patch = {k: {"properties": {"value": v}} for k, v in values.items()
             if (cur.get(k) or {}).get("properties", {}).get("value") != v}
    if not patch:
        return "unchanged"
    status, payload = d.request("PATCH", f"/api/2/things/{tid}/features", patch,
                                {"Content-Type": MERGE_JSON, "x-correlation-id": "akt-setup-validation-setup"})
    return f"written ({', '.join(patch)})" if status in (200, 204) else f"write failed {status} {short(payload)}"


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sync", action="store_true", help="update definition and attributes that differ")
    ap.add_argument("--probe-all", action="store_true", help="skeleton probe for every type")
    ap.add_argument("--strict", action="store_true", help="exit 1 when the model check fails")
    a = ap.parse_args(argv)

    t0 = time.time()
    try:
        m = twins.Model()
    except (OSError, ValueError, KeyError) as e:
        print(f"things.json: {e}", file=sys.stderr)
        return 2
    password = os.environ.get("DITTO_PASSWORD")
    if not password:
        print("DITTO_PASSWORD is not set", file=sys.stderr)
        return 2
    d = Ditto(os.environ.get("DITTO_URL", "http://localhost:8080"), os.environ.get("DITTO_USER", "ditto"), password)
    fetch_base = os.environ.get("MODELS_URL", m.base).rstrip("/") + "/"
    print(f"akt-setup: {len(m.things)} things of {len(m.types)} types, Ditto {d.url}, models {m.base}")

    waited = wait_ready(d, m.policy_id, float(os.environ.get("WAIT_S", "450")))
    print(f"Ditto ready after {waited:.1f} s")
    print(f"policy {m.policy_id}: {ensure_policy(d, m, a.sync)}")

    results: dict[str, str] = {}
    for thing in m.things:
        res, detail = ensure_thing(d, m, thing, a.sync)
        results[thing["name"]] = res
        if res != "exists":
            print(f"  {res:8} {m.tid(thing['name'])} {detail}".rstrip())

    n_files, bad_files = models_check(m, fetch_base)
    print(f"models: {n_files - len(bad_files)} of {n_files} files at {fetch_base} match things.json")
    for b in bad_files[:10]:
        print("  " + b)
    probe_types = list(m.types) if a.probe_all else [m.d["probe"]["type"]]
    probe_ok = True
    for typ in probe_types:
        name = m.d["probe"]["name"] + ("-" + typ if a.probe_all else "")
        ok, info = probe(d, m, typ, name)
        probe_ok &= ok
        print(f"probe {m.tid(name)} ({typ}): {'ok' if ok else 'FAILED'}: {info}")
    n_td, bad_td = td_check(d, m)
    print(f"TD through Ditto: {n_td - len(bad_td)} of {n_td} types ok")
    for b in bad_td[:10]:
        print("  " + b)
    tm_ok = not bad_files and probe_ok and not bad_td

    present = sum(1 for r in results.values() if r in ("created", "exists", "updated"))
    v = write_validation(d, m, {"tm_fetch_ok": 1.0 if tm_ok else 0.0, "tm_types": float(n_td),
                                "things_ok": float(present)})
    print(f"validation-setup: {v}")

    by_type: dict[str, int] = {}
    for t in m.things:
        if results[t["name"]] != "failed":
            by_type[t["type"]] = by_type.get(t["type"], 0) + 1
    counts = {r: sum(1 for x in results.values() if x == r) for r in ("created", "exists", "updated", "failed")}
    print("by type: " + ", ".join(f"{k} {n}" for k, n in by_type.items()))
    print(f"things: {present} of {len(m.things)} present (created {counts['created']}, existing {counts['exists']}, "
          f"updated {counts['updated']}, failed {counts['failed']}); models {'ok' if tm_ok else 'NOT OK'}; "
          f"{time.time() - t0:.1f} s")
    if present != len(m.things) or (a.strict and not tm_ok):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
