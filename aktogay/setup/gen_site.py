"""Write the generated part of setup/things.json from the site passport sim/site_<name>.py.

Library vs site: the thing types ("types", "quantities") are the library; the
things of a site are its passport. Hand-written things (plant units with their
own passports) stay as they are; the things that follow from the site file
(people of the shift, extra excavators, faces, haul roads, trucks, instruments)
are generated here and marked "gen": "site", so a second run replaces them and
changes nothing else. Every non-service thing gets responsible.person (the
person twin who answers for it, site.TYPE_PERSON). Sources of the site file
are merged into "sources".

  python -I aktogay/setup/gen_site.py            rewrite setup/things.json (then run gen_tm.py)
  python -I aktogay/setup/gen_site.py --check    exit 1 if things.json is not current
  AKT_SITE=<name> selects sim/site_<name>.py (default aktogay).
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
THINGS = os.path.join(HERE, "things.json")
GEN = "site"


def load_site(name: str | None = None):
    name = name or os.environ.get("AKT_SITE", "aktogay")
    return importlib.import_module(f"sim.site_{name}")


def _tbl(key: str):
    from sim.params import TABLE
    return TABLE[key]


def _num(key: str) -> float:
    v = _tbl(key).value
    return int(v) if float(v).is_integer() else round(v, 4)


def _src_of(key: str) -> str:
    """things.json source key for a parameter row by its label."""
    label = _tbl(key).label
    return {"fact": "vesti2024", "vendor": "cat_spec", "assumption": "assume", "calc": "calc"}.get(label, "assume")


def _bort_item(bort: tuple[str, str, str]) -> list:
    """Passport item of a bort number: the company list (fact) or a conditional number."""
    number, model, label = bort
    if label == "fact":
        return [number, "", "kaz_equip2024", f"{model}; перечень техники не исчерпывающий"]
    return [number, "", "assume", f"номер условный ({model}): в перечне техники 29.02.2024 его нет"]


def generated_things(s) -> list[dict]:
    """Things that follow from the site file, in a stable order."""
    out: list[dict] = []
    crew_ru = {"crew-kip": "Бригада КИПиА", "crew-cpd": "Бригада механиков ЦПД", "crew-mill": "Бригада механиков фабрики",
               "crew-water": "Бригада хвостового хозяйства"}
    for pid, role, ru, crew, home in s.PEOPLE:
        out.append({"name": pid, "type": "person", "name_ru": ru, "parent": "site",
                    "responsible": {"role": role, **({"deputy": s.DEPUTY[pid]} if pid in getattr(s, "DEPUTY", {}) else {})},
                    "passport": {
                        "role": [ru, "", "roster"],
                        "crew": [crew_ru.get(crew, "— (решения, без бригады)"), "", "roster"],
                        "home": [home, "", "roster", "где человек, когда свободен"],
                        "shift_h": [12, "h", "ovos_26", "2 смены по 12 ч"],
                        "pit_people_shift": ["> 500", "чел.", "vesti2024",
                                             "в карьере за смену; роли и состав смены стенда — допущение"]}})
    for eid, duty, face in s.EXCAVATORS:
        if duty != "waste":
            continue
        bort = getattr(s, "EXC_BORT", {}).get(eid)
        out.append({"name": eid, "type": "exc",
                    "name_ru": f"Экскаватор {bort[0] if bort else eid.split('-')[-1]} (вскрыша)",
                    "parent": "pit", "responsible": {"role": "mine_dispatcher"},
                    "passport": {**({"bort": _bort_item(bort)} if bort else {}),
                                 "model": [bort[1] if bort else "Hitachi", "",
                                           "kaz_equip2024" if bort and bort[2] == "fact" else "vesti2024",
                                           "на карьере 5 экскаваторов Hitachi"],
                                 "rate_tph": ["2700-3700", "t/h", "vesti2024", "по словам начальника карьера"],
                                 "dig_tph": [_num("pit_exc_waste_tph"), "t/h", _src_of("pit_exc_waste_tph"),
                                             "на вскрыше, не больше, чем вывозят самосвалы вскрыши"],
                                 "duty": ["вскрыша (3 из 5 — на руде, деление — допущение)", "", "assume"],
                                 "face": [face, "", "assume"]}})
    for fid, exc, kind, bench in s.FACES:
        ru = f"Забой {fid.split('-')[-1]}" + (" (вскрыша)" if kind == "waste" else "")
        out.append({"name": fid, "type": "face", "name_ru": ru, "parent": "pit",
                    "responsible": {"role": "shift_geologist", "also": [["mine_dispatcher", "экскаватор и самосвалы"]]},
                    "passport": {"excavator": [exc, "", "assume"],
                                 "kind": ["руда" if kind == "ore" else "вскрыша", "", "assume"],
                                 "bench": [bench, "-", "assume",
                                           "горизонты не опубликованы; глубина карьера до 230 м (факт, vesti2024)"],
                                 "grade": ["оценка блочной модели по блоку в работе", "", "geomet"]}})
    for rid, ru, line in s.ROADS:
        out.append({"name": rid, "type": "road", "name_ru": ru, "parent": "pit",
                    "responsible": {"role": "mine_dispatcher"},
                    "passport": {"leads_to": [f"crusher-{line}" if line else "отвал вскрыши", "", "assume"],
                                 "length": ["нет открытых данных", "", "assume", "длина откатки и съезды не опубликованы"],
                                 "detour_mult": [_num("pit_road_detour"), "-", "assume",
                                                 "цикл самосвала при закрытом съезде (объезд)"]}})
    roster = s.truck_roster()
    borts = s.truck_borts() if hasattr(s, "truck_borts") else {}
    for tid, model, p_key, duty, line in roster:
        n = tid.split("-")[-1]
        bort = borts.get(tid)
        ru = f"Самосвал {bort[0]} ({bort[1]})" if bort else f"Самосвал {n} ({model})"
        out.append({"name": tid, "type": "truck", "name_ru": ru, "parent": "fleet",
                    "responsible": {"role": "mine_dispatcher"},
                    "passport": {**({"bort": _bort_item(bort)} if bort else {}),
                                 "model": [model, "", "vesti2024", "парк на 06.06.2024: 2 CAT 777, 18 CAT 785, 17 CAT 793"],
                                 "payload_t": [_num(p_key), "t", _src_of(p_key), _tbl(p_key).note],
                                 "duty": [f"руда, ЦПД-{line}" if duty == "ore" else "вскрыша", "", "assume",
                                          "деление парка руда / вскрыша — допущение"],
                                 "cycle_min": [_num("fleet_trip_min"), "min", "assume"]}})
    for did, bort, model, face in getattr(s, "DRILLS", ()):
        out.append({"name": did, "type": "drill", "name_ru": f"Буровой станок {bort} ({model})", "parent": "pit",
                    "responsible": {"role": "mine_dispatcher"},
                    "passport": {"bort": [bort, "", "kaz_equip2024", "перечень техники не исчерпывающий"],
                                 "model": [model, "", "kaz_equip2024"],
                                 "face": [face, "", "assume", "забой, который станок обуривает"],
                                 "holes_shift": [_num("pit_drill_holes_shift"), "1/shift", "assume"],
                                 "t_per_hole": [round(_num("pit_drill_t_hole")), "t", "calc", _tbl("pit_drill_t_hole").note]}})
    for zid, bort, model, place in getattr(s, "DOZERS", ()):
        out.append({"name": zid, "type": "dozer", "name_ru": f"Бульдозер {bort} ({model})", "parent": "pit",
                    "responsible": {"role": "mine_dispatcher"},
                    "passport": {"bort": [bort, "", "kaz_equip2024", "перечень техники не исчерпывающий"],
                                 "model": [model, "", "kaz_equip2024"],
                                 "place": [place, "", "assume", "где работает: зачистка забоя, дорога, отвал"]}})
    inst_pass = {
        "analyzer": {"kind": ["поточный анализатор (питание, хвосты, концентрат)", "", "assume"],
                     "cycle_min": [_num("sens_an_cycle_min"), "min", "assume", "производитель: 12–16 мин"],
                     "tail_sigma_pct": [round(100 * _tbl("sens_an_tail_sigma").value, 1), "%", "assume"]},
        "weigher": {"kind": ["конвейерные весы, класс 1", "", "assume"],
                    "sigma_pct": [round(100 * _tbl("sens_weigher_sigma").value, 1), "%", "assume"]},
        "flowmeter": {"kind": ["расходомер собирателя (ксантогенат)", "", "assume"],
                      "dose_sp_gt": [_num("flot_dose_sp_gt"), "g/t", "ovos"],
                      "sigma_pct": [round(100 * _tbl("sens_dose_sigma").value, 1), "%", "assume"]},
        "piezometer": {"kind": ["пьезометр дамбы хвостохранилища", "", "assume",
                                "число и места пьезометров не опубликованы"],
                       "sp_kpa": [_num("pond_piezo_sp_kpa"), "kPa", "assume", "уставка безопасности S0"]},
    }
    for iid, typ, parent, ru in s.INSTRUMENTS:
        pas = dict(inst_pass[typ])
        if typ == "piezometer":
            key = s.PIEZO_OFFSET[iid]
            pas["offset_kpa"] = [_num(key), "kPa", "assume", "относительно показания дамбы в модели"]
        out.append({"name": iid, "type": typ, "name_ru": ru, "parent": parent,
                    "responsible": {"role": "tailings_engineer" if typ == "piezometer" else "kip"},
                    "passport": pas})
    for t in out:
        t["gen"] = GEN
    return out


def person_of(thing: dict, s) -> str:
    if thing["type"] == "person":
        return thing["name"]
    if thing["type"] == "crew":
        return s.CREW_PERSON.get(thing["name"], "")
    return s.TYPE_PERSON.get(thing["type"], "")


def build(d: dict, s) -> dict:
    """things.json with the generated things replaced and responsible.person set."""
    d = json.loads(json.dumps(d))
    for k, v in s.SOURCES.items():
        d["sources"][k] = v
    service = set(d["service_types"])
    hand = [t for t in d["things"] if t.get("gen") != GEN]
    # bort numbers of hand-written units (ore excavators) from the site file
    for t in hand:
        bort = getattr(s, "EXC_BORT", {}).get(t["name"])
        if bort and t["type"] == "exc":
            t["passport"] = {"bort": _bort_item(bort), **{k: v for k, v in t["passport"].items() if k != "bort"}}
            t["name_ru"] = f"Экскаватор {bort[0]}"
    gen = generated_things(s)
    names = {t["name"] for t in hand}
    gen = [t for t in gen if t["name"] not in names]
    # generated things go after the last hand-written physical thing (before the service things)
    k = max((i for i, t in enumerate(hand) if t["type"] not in service), default=len(hand) - 1) + 1
    things = hand[:k] + gen + hand[k:]
    for t in things:
        if t["type"] in service:
            continue
        p = person_of(t, s)
        if p:
            t.setdefault("responsible", {})["person"] = p
    d["things"] = things
    return d


# ---------------------------------------------------------------------------
# Compact writer: one entry per line, like the hand-written file
# ---------------------------------------------------------------------------
def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def render(d: dict) -> str:
    lines = ["{"]
    keys = list(d)
    for i, key in enumerate(keys):
        last = i == len(keys) - 1
        v = d[key]
        comma = "" if last else ","
        if key in ("quantities", "sources", "types", "roles") and isinstance(v, dict):
            lines.append(f"  {_j(key)}: {{")
            items = list(v.items())
            for j, (k2, v2) in enumerate(items):
                lines.append(f"    {_j(k2)}: {_j(v2)}" + ("" if j == len(items) - 1 else ","))
            lines.append("  }" + comma)
        elif key in ("things", "_doc") and isinstance(v, list):
            lines.append(f"  {_j(key)}: [")
            for j, item in enumerate(v):
                lines.append(f"    {_j(item)}" + ("" if j == len(v) - 1 else ","))
            lines.append("  ]" + comma)
        else:
            lines.append(f"  {_j(key)}: {_j(v)}{comma}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--path", default=THINGS)
    a = ap.parse_args(argv)
    with open(a.path, encoding="utf-8") as f:
        text = f.read()
    s = load_site()
    out = render(build(json.loads(text), s))
    if a.check:
        ok = out == text
        print("things.json is current" if ok else "things.json differs from the site file (run gen_site.py)")
        return 0 if ok else 1
    with open(a.path, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    d = json.loads(out)
    n_gen = sum(1 for t in d["things"] if t.get("gen") == GEN)
    print(f"things.json: {len(d['things'])} things ({n_gen} generated from sim/site_{s.NAME}.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
