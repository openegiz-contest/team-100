"""Twin model of the Aktogay stand, read from things.json.

Builds the WoT Thing Models (gen_tm.py writes them to models/) and the
Ditto bodies of policy and things (setup.py sends them). No network here.

Ditto 3.3.7 maps a Thing Model like this: TM properties -> attributes,
links with rel "tm:submodel" -> features (feature id = instanceName,
feature definition = submodel URL), submodel properties -> feature
properties. Every feature here is {value, unit}: one submodel per
quantity (number with its unit, text, object) and one enum submodel per
type for its states.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TD_CONTEXT = "https://www.w3.org/2022/wot/td/v1.1"
TM_MEDIA = "application/tm+json"
LABELS = ("fact", "vendor", "project", "analog", "assumption", "calc")

# Attribute schema shared by all types (TM properties -> Ditto attributes).
ATTRS = (
    ("_parents", {"type": "string", "title": "Parent thing",
                  "description": "thingId of the parent: the tree and the Telegraf tag parent."}),
    ("_isType", {"type": "boolean", "default": False,
                 "description": "false: an instance, not a type (Grafana OpenTwins app)."}),
    ("type", {"type": "string", "description": "Thing type, same as the model file name."}),
    ("name", {"type": "string", "description": "Display name (Grafana OpenTwins app)."}),
    ("name_ru", {"type": "string", "description": "Name in Russian."}),
    ("passport", {"type": "object",
                  "description": "Passport: key -> {value, unit, src, note}; src is a key of source."}),
    ("source", {"type": "object",
                "description": "Sources: key -> {doc, page, url, label}; label: " + ", ".join(LABELS) + "."}),
    ("responsible", {"type": "object",
                     "description": "Role to call: {role, name_ru, person (thingId of the person twin), person_ru, "
                                    "arrive_min [lo, hi], src, also [{role, name_ru, for_ru}]}."}),
    ("feeds", {"type": "array", "items": {"type": "string"},
               "description": "thingIds this thing feeds with material."}),
    ("fed_by", {"type": "array", "items": {"type": "string"},
                "description": "thingIds feeding this thing (inverse of feeds)."}),
    ("supplies", {"type": "array", "items": {"type": "string"},
                  "description": "thingIds supplied with power or water."}),
    ("ui", {"type": "object", "description": "Layout hints: scheme {col, row, span}."}),
)


class ModelError(ValueError):
    pass


class Model:
    """things.json with lookups; model_base overrides the URL prefix of definitions."""

    def __init__(self, path: str | None = None, model_base: str | None = None):
        self.path = path or os.path.join(HERE, "things.json")
        with open(self.path, encoding="utf-8") as f:
            self.d = json.load(f)
        d = self.d
        self.ns = d["namespace"]
        self.policy_id = d["policy_id"]
        self.subject = d["subject"]
        self.base = (model_base or d["model_base"]).rstrip("/") + "/"
        self.ver = d["model_version"]
        self.no_value = float(d["no_value"])
        self.quant = d["quantities"]
        self.types = d["types"]
        self.service = set(d["service_types"])
        self.sources = d["sources"]
        self.roles = d["roles"]
        self.things = d["things"]
        self.by_name = {t["name"]: t for t in self.things}
        self.check()

    # -- names and URLs --------------------------------------------------
    def tid(self, name: str) -> str:
        return f"{self.ns}:{name}"

    def type_file(self, typ: str) -> str:
        return f"{typ}-{self.ver}.tm.jsonld"

    def q_file(self, q: str) -> str:
        return f"q-{q}-{self.ver}.tm.jsonld"

    def state_file(self, typ: str) -> str:
        return f"state-{typ}-{self.ver}.tm.jsonld"

    def url(self, fname: str) -> str:
        return self.base + fname

    # -- features ----------------------------------------------------------
    def feature_map(self, typ: str) -> dict[str, str]:
        """feature -> submodel file name, type features first, then common ones."""
        out = {}
        feats = dict(self.types[typ]["features"])
        feats.update(self.d["common_features"])
        for f, q in feats.items():
            out[f] = self.state_file(typ) if q == "state" else self.q_file(q)
        return out

    def feature_default(self, typ: str, feature: str) -> dict:
        q = dict(self.types[typ]["features"], **self.d["common_features"])[feature]
        if q == "state":
            return {"value": "", "unit": ""}
        spec = self.quant[q]
        value = {"number": self.no_value, "string": "", "object": {}}[spec["type"]]
        return {"value": value, "unit": spec["unit"]}

    def root_types(self) -> set[str]:
        return {t["type"] for t in self.things if not t.get("parent")}

    # -- Thing Models ----------------------------------------------------
    def type_tm(self, typ: str) -> dict:
        ty = self.types[typ]
        desc = ty["description"]
        if ty.get("states"):
            desc += " States: " + ", ".join(ty["states"]) + "."
        props = {}
        for key, schema in ATTRS:
            if key == "_parents" and typ in self.root_types():
                continue
            if key == "responsible" and typ in self.service:
                continue
            s = json.loads(json.dumps(schema))
            if key == "type":
                s["default"] = typ
            props[key] = s
        links = [{"rel": "tm:submodel", "href": self.url(fname), "type": TM_MEDIA, "instanceName": f}
                 for f, fname in self.feature_map(typ).items()]
        return {
            "@context": TD_CONTEXT,
            "@type": "tm:ThingModel",
            "title": ty["title"],
            "titles": {"en": ty["title"], "ru": ty["title_ru"]},
            "description": desc,
            "version": {"model": self.ver},
            "links": links,
            "properties": props,
        }

    def q_tm(self, q: str) -> dict:
        spec = self.quant[q]
        unit = spec["unit"]
        value = {"type": spec["type"], "default": {"number": self.no_value, "string": "", "object": {}}[spec["type"]]}
        if spec["type"] == "number":
            if unit not in ("", "-"):
                value["unit"] = unit
            value["description"] = f"{self.no_value:g} means no value."
        elif spec["type"] == "string":
            value["description"] = "Empty means no value."
        title = spec["title"] + (f", {unit}" if unit not in ("", "-") else "")
        return self._value_unit_tm(title, value, unit)

    def state_tm(self, typ: str) -> dict:
        ty = self.types[typ]
        value = {"type": "string", "enum": ty["states"], "default": "",
                 "description": "Empty until the first update."}
        return self._value_unit_tm(f"{ty['title']}: state", value, "")

    def _value_unit_tm(self, title: str, value: dict, unit: str) -> dict:
        return {
            "@context": TD_CONTEXT,
            "@type": "tm:ThingModel",
            "title": title,
            "version": {"model": self.ver},
            "properties": {
                "value": value,
                "unit": {"type": "string", "const": unit, "default": unit},
            },
        }

    def all_tms(self) -> dict[str, dict]:
        """file name -> TM for every type, every quantity and every state set."""
        out = {}
        for q in self.quant:
            out[self.q_file(q)] = self.q_tm(q)
        for typ, ty in self.types.items():
            if ty.get("states"):
                out[self.state_file(typ)] = self.state_tm(typ)
            out[self.type_file(typ)] = self.type_tm(typ)
        return out

    # -- Ditto bodies ----------------------------------------------------
    def policy_body(self) -> dict:
        grant = {"grant": ["READ", "WRITE"], "revoke": []}
        return {"entries": {"aktogay": {
            "subjects": {self.subject: {"type": "Ditto user via nginx and the Mosquitto connections"}},
            "resources": {"policy:/": grant, "thing:/": grant, "message:/": grant},
        }}}

    def attributes(self, thing: dict) -> dict:
        name, typ = thing["name"], thing["type"]
        used = []
        passport = {}
        for key, item in thing.get("passport", {}).items():
            value, unit, src = item[0], item[1], item[2]
            entry = {"value": value, "unit": unit, "src": src}
            if len(item) > 3:
                entry["note"] = item[3]
            passport[key] = entry
            used.append(src)
        attrs = {}
        if thing.get("parent"):
            attrs["_parents"] = self.tid(thing["parent"])
        attrs.update({"_isType": False, "type": typ, "name": thing["name_ru"], "name_ru": thing["name_ru"],
                      "passport": passport})
        if typ not in self.service:
            r = thing["responsible"]
            lo, hi, src = self.d["arrive_min"]
            attrs["responsible"] = {
                "role": r["role"], "name_ru": self.roles[r["role"]], "arrive_min": [lo, hi], "src": src,
                "also": [{"role": a, "name_ru": self.roles[a], "for_ru": why} for a, why in r.get("also", [])],
            }
            if r.get("deputy"):
                attrs["responsible"]["deputy"] = self.tid(r["deputy"])
            if r.get("person"):
                attrs["responsible"]["person"] = self.tid(r["person"])
                attrs["responsible"]["person_ru"] = self.by_name[r["person"]]["name_ru"]
            used.append(src)
        attrs["source"] = {k: self.sources[k] for k in dict.fromkeys(used)}
        attrs["feeds"] = [self.tid(n) for n in thing.get("feeds", [])]
        attrs["fed_by"] = [self.tid(t["name"]) for t in self.things if name in t.get("feeds", [])]
        attrs["supplies"] = [self.tid(n) for n in thing.get("supplies", [])]
        attrs["ui"] = thing.get("ui", {})
        return attrs

    def features(self, typ: str) -> dict:
        return {f: {"definition": [self.url(fname)], "properties": self.feature_default(typ, f)}
                for f, fname in self.feature_map(typ).items()}

    def thing_body(self, thing: dict) -> dict:
        typ = thing["type"]
        return {"policyId": self.policy_id, "definition": self.url(self.type_file(typ)),
                "attributes": self.attributes(thing), "features": self.features(typ)}

    # -- consistency -------------------------------------------------------
    def check(self) -> None:
        problems = []
        for typ, ty in self.types.items():
            for f, q in ty["features"].items():
                if q == "state" and not ty.get("states"):
                    problems.append(f"type {typ}: feature {f} needs states")
                elif q != "state" and q not in self.quant:
                    problems.append(f"type {typ}: feature {f}: unknown quantity {q}")
        for s in self.service:
            if s not in self.types:
                problems.append(f"service type {s} not in types")
        for k, s in self.sources.items():
            if s["label"] not in LABELS:
                problems.append(f"source {k}: bad label {s['label']}")
        names = [t["name"] for t in self.things]
        if len(names) != len(set(names)):
            problems.append("duplicate thing names")
        for t in self.things:
            n = t["name"]
            if t["type"] not in self.types:
                problems.append(f"{n}: unknown type {t['type']}")
            for ref in [t.get("parent")] + t.get("feeds", []) + t.get("supplies", []):
                if ref and ref not in self.by_name:
                    problems.append(f"{n}: unknown thing {ref}")
            for key, item in t.get("passport", {}).items():
                if len(item) < 3 or item[2] not in self.sources:
                    problems.append(f"{n}: passport {key}: bad item or source")
            if t["type"] not in self.service:
                r = t.get("responsible") or {}
                for role in [r.get("role")] + [a for a, _ in r.get("also", [])]:
                    if role not in self.roles:
                        problems.append(f"{n}: unknown role {role}")
                person = r.get("person")
                if person and (person not in self.by_name or self.by_name[person]["type"] != "person"):
                    problems.append(f"{n}: responsible person {person} is not a person thing")
        if problems:
            raise ModelError("; ".join(problems))
