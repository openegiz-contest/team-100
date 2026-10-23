"""HTTP clients: Ditto (things API) and InfluxDB 2 (Flux). Standard library only.

The modules read only these two sources (contest rule 6.2): the simulator
is not reachable from here. Writes go through Ditto merge commands with a
constant x-correlation-id per writer and thing, so Telegraf keeps one
series per thing (design file 17, section 2).
"""
from __future__ import annotations

import base64
import csv
import io
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("clients")

RETRY = {0, 408, 429, 500, 502, 503, 504}
MERGE_JSON = "application/merge-patch+json"


def _parse(raw: bytes):
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text) if text else None
    except ValueError:
        return text


class Ditto:
    """Minimal Ditto HTTP client (urllib, no proxies)."""

    def __init__(self, url: str, user: str, password: str, timeout: float = 15.0):
        self.url = url.rstrip("/")
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.timeout = timeout

    def request(self, method: str, path: str, body=None, headers: dict | None = None, retries: int = 3,
                raw: bytes | None = None):
        """(status, parsed body); status 0 = no answer. Retries no answer, 408, 429 and 5xx."""
        h = {"Authorization": self.auth}
        data = raw
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
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
            time.sleep(1.0 + attempt)
        return status, payload

    # -- reads ---------------------------------------------------------------
    def search(self, ns: str, fields: str = "thingId,attributes,features", size: int = 200) -> list[dict]:
        """All things of a namespace (search index; eventually consistent)."""
        flt = 'like(thingId,"' + ns + ':*")'

        def path_for(cursor: str | None) -> str:
            option = f"size({size})" + (f",cursor({cursor})" if cursor else "")
            return "/api/2/search/things?" + urllib.parse.urlencode({"filter": flt, "fields": fields,
                                                                     "option": option})

        items: list[dict] = []
        cursor = None
        while True:
            status, payload = self.request("GET", path_for(cursor))
            if status != 200 or not isinstance(payload, dict):
                log.warning("search %s: %s %s", ns, status, str(payload)[:160])
                return items
            items.extend(payload.get("items", []))
            cursor = payload.get("cursor")
            if not cursor:
                return items

    def get_thing(self, tid: str, fields: str | None = None):
        q = f"?fields={urllib.parse.quote(fields)}" if fields else ""
        return self.request("GET", f"/api/2/things/{tid}{q}")

    # -- writes ----------------------------------------------------------------
    def merge_features(self, tid: str, features: dict, correlation: str):
        """PATCH merge on /features: only the given features change; definitions stay."""
        raw = json.dumps(features, ensure_ascii=False, separators=(",", ":")).encode()
        return self.request("PATCH", f"/api/2/things/{tid}/features", raw=raw,
                            headers={"Content-Type": MERGE_JSON, "x-correlation-id": correlation})

    def put_thing_if_absent(self, tid: str, body: dict, correlation: str):
        """201 created, 412 exists, else error."""
        return self.request("PUT", f"/api/2/things/{tid}", body,
                            {"If-None-Match": "*", "x-correlation-id": correlation})

    def delete_thing(self, tid: str, correlation: str):
        return self.request("DELETE", f"/api/2/things/{tid}", headers={"x-correlation-id": correlation})


class Influx:
    """InfluxDB 2 Flux client over HTTP (annotated CSV disabled, plain CSV)."""

    def __init__(self, url: str, token: str, org: str = "opentwins", bucket: str = "default",
                 timeout: float = 20.0):
        self.url = url.rstrip("/")
        self.token = token
        self.org = org
        self.bucket = bucket
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.timeout = timeout

    def query(self, flux: str, retries: int = 2) -> list[dict]:
        """Rows of all result tables as dicts (numbers converted); [] on error."""
        q = urllib.parse.urlencode({"org": self.org})
        req = urllib.request.Request(f"{self.url}/api/v2/query?{q}", data=flux.encode(), method="POST",
                                     headers={"Authorization": f"Token {self.token}",
                                              "Content-Type": "application/vnd.flux",
                                              "Accept": "application/csv"})
        for attempt in range(retries):
            try:
                with self.opener.open(req, timeout=self.timeout) as r:
                    return parse_csv(r.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as e:
                log.warning("flux %s: %s", e.code, e.read()[:200])
                if e.code < 500:
                    return []
            except OSError as e:
                log.warning("flux: %s", e)
            time.sleep(1.0)
        return []

    def history(self, run_id: str, things: list[str], fields: list[str], since: str = "-6h",
                ns: str = "kz.aktogay") -> list[dict]:
        """Points of `things` x `fields` of one run, pivoted: one row per (thing, time) with the fields.

        Returns rows {"thingId", "_time", <field>...} sorted by time, field keys as in Telegraf
        (value_<feature>_properties_value). Only points with a sim_time field.
        """
        if not things or not fields:
            return []
        tids = ", ".join(f'"{ns}:{t}"' for t in things)
        flds = ", ".join(f'"{f}"' for f in sorted(set(fields) | {"value_sim_time_properties_value"}))
        flux = (
            f'from(bucket:"{self.bucket}") |> range(start:{since}) '
            f'|> filter(fn:(r) => r._measurement == "mqtt_consumer" and r.idSimulationRun == "{run_id}") '
            f'|> filter(fn:(r) => contains(value: r.thingId, set: [{tids}])) '
            f'|> filter(fn:(r) => contains(value: r._field, set: [{flds}])) '
            f'|> keep(columns: ["_time", "_field", "_value", "thingId"]) '
            f'|> pivot(rowKey: ["_time", "thingId"], columnKey: ["_field"], valueColumn: "_value") '
            f'|> sort(columns: ["_time"])'
        )
        return [r for r in self.query(flux) if "value_sim_time_properties_value" in r]


def _num(s: str):
    if s == "" or s is None:
        return s
    try:
        if s.lower() in ("true", "false"):
            return s.lower() == "true"
        v = float(s)
        return v
    except ValueError:
        return s


def parse_csv(text: str) -> list[dict]:
    """Plain (non-annotated) Flux CSV: blocks separated by blank lines, each with its own header."""
    rows: list[dict] = []
    header: list[str] | None = None
    for rec in csv.reader(io.StringIO(text)):
        if not rec or all(c == "" for c in rec):
            header = None
            continue
        if header is None:
            header = rec
            continue
        if len(rec) != len(header):
            continue
        d = {}
        for k, v in zip(header, rec):
            if k in ("", "result", "table"):
                continue
            d[k] = _num(v) if k not in ("_time", "_start", "_stop", "thingId", "idSimulationRun") else v
        rows.append(d)
    return rows
