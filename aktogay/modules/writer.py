"""Feature writer: types from setup/things.json, Ditto merge commands, issue things.

One type per feature (numbers float, states and texts str, objects dict);
null, NaN and inf never leave (-1.0 / "" / {} instead), as the platform
notes require. Every write carries x-correlation-id akt-<writer>-<thing>.
"""
from __future__ import annotations

import json
import logging
import math
import os

from .clients import Ditto

log = logging.getLogger("writer")

HERE = os.path.dirname(os.path.abspath(__file__))
THINGS_JSON = os.environ.get("AKT_THINGS") or os.path.join(os.path.dirname(HERE), "setup", "things.json")


def number(value, no_value: float = -1.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return no_value
    if not math.isfinite(v):
        return no_value
    return float(f"{v:.7g}") if abs(v) < 1e7 else round(v, 1)


def clean_object(obj: dict, no_value: float = -1.0) -> dict:
    out = {}
    for k, v in obj.items():
        if v is None:
            continue
        if isinstance(v, dict):
            out[str(k)] = clean_object(v, no_value)
        elif isinstance(v, (bool, int, float)):
            out[str(k)] = number(v, no_value)
        else:
            out[str(k)] = v if isinstance(v, (str, list)) else str(v)
    return out


class Catalog:
    """Feature specs per type from things.json (same file the Thing Models come from)."""

    def __init__(self, path: str | None = None):
        with open(path or THINGS_JSON, encoding="utf-8") as f:
            d = json.load(f)
        self.d = d
        self.ns = d["namespace"]
        self.policy_id = d["policy_id"]
        self.base = d["model_base"]
        self.ver = d["model_version"]
        self.no_value = float(d["no_value"])
        self.types = d["types"]
        self.quant = d["quantities"]
        self.common = d["common_features"]
        self.roles: dict[str, str] = d.get("roles", {})
        self.things = {t["name"]: t for t in d["things"]}
        self._warned: set[tuple[str, str]] = set()

    def tid(self, name: str) -> str:
        return f"{self.ns}:{name}"

    def type_of(self, name: str) -> str | None:
        if name in self.things:
            return self.things[name]["type"]
        prefix = name.rsplit("-", 1)[0]
        return prefix if prefix in self.types else None

    def feature_names(self, typ: str) -> list[str]:
        return list(dict(self.types[typ]["features"], **self.common))

    def spec(self, typ: str, feature: str):
        feats = dict(self.types[typ]["features"], **self.common)
        q = feats.get(feature)
        if q is None:
            return None
        if q == "state":
            return "string", "", tuple(self.types[typ].get("states", ()))
        s = self.quant[q]
        return s["type"], s["unit"], ()

    def coerce(self, typ: str, feature: str, value):
        s = self.spec(typ, feature)
        if s is None:
            return None
        kind, _, states = s
        if kind == "number":
            return number(value, self.no_value)
        if kind == "string":
            v = "" if value is None else str(value)
            if states and v and v not in states and (typ, feature) not in self._warned:
                self._warned.add((typ, feature))
                log.warning("%s.%s: state %r not in %s", typ, feature, v, list(states))
            return v
        return clean_object(value, self.no_value) if isinstance(value, dict) else {}

    def features(self, typ: str, values: dict, run_id: str, sim_time: float, partial: bool = False) -> dict:
        """Ditto /features value: {feature: {properties: {value, unit}}}; all features unless partial."""
        vals = dict(values)
        vals["idSimulationRun"] = run_id
        vals["sim_time"] = sim_time
        names = self.feature_names(typ) if not partial else [k for k in vals if self.spec(typ, k)]
        out = {}
        for f in names:
            kind, unit, _ = self.spec(typ, f)
            out[f] = {"properties": {"value": self.coerce(typ, f, vals.pop(f, None)), "unit": unit}}
        for f in vals:
            if self.spec(typ, f) is None and (typ, f) not in self._warned:
                self._warned.add((typ, f))
                log.warning("%s.%s: not in the model, dropped", typ, f)
        return out

    def thing_body(self, name: str, typ: str, parent: str, name_ru: str, extra_attrs: dict | None = None) -> dict:
        """Body of a dynamic thing (issue-N): policy, definition, attributes, all features at no value."""
        attrs = {"_parents": self.tid(parent), "_isType": False, "type": typ, "name": name_ru, "name_ru": name_ru,
                 "passport": {}, "source": {}, "feeds": [], "fed_by": [], "supplies": [], "ui": {}}
        attrs.update(extra_attrs or {})
        feats = {}
        for f in self.feature_names(typ):
            kind, unit, _ = self.spec(typ, f)
            value = {"number": self.no_value, "string": "", "object": {}}[kind]
            feats[f] = {"properties": {"value": value, "unit": unit}}
        return {"policyId": self.policy_id, "definition": f"{self.base}{typ}-{self.ver}.tm.jsonld",
                "attributes": attrs, "features": feats}


class Writer:
    """Writes features of the module things; dry-run prints instead of sending."""

    def __init__(self, ditto: Ditto | None, catalog: Catalog, writer: str, dry_run: bool = False):
        self.ditto = ditto
        self.cat = catalog
        self.writer = writer
        self.dry_run = dry_run or ditto is None
        self.sent = 0
        self.failed = 0

    def correlation(self, name: str) -> str:
        return f"akt-{self.writer}-{name}"

    def write(self, name: str, values: dict, run_id: str, sim_time: float, partial: bool = False) -> bool:
        typ = self.cat.type_of(name)
        if typ is None:
            log.error("%s: unknown thing", name)
            return False
        feats = self.cat.features(typ, values, run_id, sim_time, partial)
        if self.dry_run:
            print(f"[dry-run] {name} <- {json.dumps(feats, ensure_ascii=False)[:400]}")
            return True
        status, payload = self.ditto.merge_features(self.cat.tid(name), feats, self.correlation(name))
        ok = status in (200, 204)
        self.sent += 1
        if not ok:
            self.failed += 1
            log.warning("merge %s: %s %s", name, status, str(payload)[:160])
        return ok

    def ensure_thing(self, name: str, typ: str, parent: str, name_ru: str, extra_attrs: dict | None = None) -> bool:
        body = self.cat.thing_body(name, typ, parent, name_ru, extra_attrs)
        if self.dry_run:
            print(f"[dry-run] create {name} ({typ}) under {parent}")
            return True
        status, payload = self.ditto.put_thing_if_absent(self.cat.tid(name), body, self.correlation(name))
        if status in (201, 412):
            return True
        log.warning("create %s: %s %s", name, status, str(payload)[:160])
        return False

    def delete_thing(self, name: str) -> bool:
        if self.dry_run:
            print(f"[dry-run] delete {name}")
            return True
        status, _ = self.ditto.delete_thing(self.cat.tid(name), self.correlation(name))
        return status in (204, 404)
