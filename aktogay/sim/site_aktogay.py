"""Site passport of the Aktogay sulphide concentrator: what is where, who answers for it.

This file is site data, not physics. The library (sim/*.py physics, the
thing types of setup/things.json and models/) works for any concentrator with
the same kinds of units; this file and setup/things.json describe Aktogay:
the roster of the shift, the pit fleet by model, excavators and faces, haul
roads, instruments and the person responsible for every node.

Numbers the model computes with (payloads, counts, rates, offsets) are rows
of sim/params.py with value, range, unit, source and label; this file only
names those rows. Labels used below: fact, vendor, project, analog,
assumption, calc (same as the parameter table).

Another site: copy this file to sim/site_<name>.py, change the lists, set
AKT_SITE=<name> and write the things of the site into setup/things.json
(setup/gen_site.py does the generated part). See README_dev.md.
"""
from __future__ import annotations

NAME = "aktogay"
NAMESPACE = "kz.aktogay"
LINES = (1, 2)

# ---------------------------------------------------------------------------
# Sources of the site data (keys of setup/things.json "sources")
# ---------------------------------------------------------------------------
SOURCES = {
    "vesti2024": {
        "doc_ru": "Вести Семей, 06.06.2024: пресс-тур на Актогай (слова начальника карьера)",
        "doc": "Vesti Semey 06.06.2024: press tour of Aktogay (head of the pit)",
        "page": "", "label": "fact",
        "url": "https://vestisemey.kz/15404/kaz-minerals-aktogay-tsifrovye-i-innovatsionnye-vozmozhnosti-"
               "industrialnogo-proizvodstva.html"},
    "im2021": {
        "doc_ru": "International Mining, 25.02.2021: расширение Актогая, вторая фабрика",
        "doc": "International Mining 25.02.2021: Aktogay expansion, second concentrator",
        "page": "", "label": "project",
        "url": "https://im-mining.com/2021/02/25/kaz-minerals-aktogay-expansion-track-first-production-second-"
               "concentrator-set-late-2021/"},
    "im2021_hpgr": {
        "doc_ru": "International Mining, 25.02.2021: ВВД thyssenkrupp POLYCOM линии 2",
        "doc": "International Mining 25.02.2021: thyssenkrupp POLYCOM HPGR of line 2",
        "page": "", "label": "vendor",
        "url": "https://im-mining.com/2021/02/25/kaz-minerals-aktogay-expansion-track-first-production-second-"
               "concentrator-set-late-2021/"},
    "kursiv2026": {
        "doc_ru": "Курсив, 09.08.2026: пожар на участке ВВД фабрики № 1 во время ППР, 20 человек эвакуированы",
        "doc": "Kursiv 09.08.2026: fire at the HPGR of concentrator 1 during maintenance, 20 evacuated",
        "page": "", "label": "fact",
        "url": "https://kz.kursiv.media/2026-08-09/svvo-20-chelovek-evakuirovali-iz-za-chp-na-"
               "obogatitelnoi-fabrike-kaz-minerals/"},
    "kaz_equip2024": {
        "doc_ru": "ТОО «КАЗ Минералз Актогай», 29.02.2024: техническая спецификация (системы пожаротушения), "
                  "перечень техники с бортовыми номерами; перечень не исчерпывающий (копия на minedocs.com)",
        "doc": "KAZ Minerals Aktogay LLC 29.02.2024: specification (fire suppression), equipment list with bort "
               "numbers; the list is not exhaustive (copy on minedocs.com)",
        "page": "", "label": "fact", "url": "https://minedocs.com/33/Kaz-Minerals-equipment-2024.pdf"},
    "cat_spec": {
        "doc_ru": "Caterpillar, паспортная грузоподъёмность 777 и 785 (данные производителя; в этой работе не открыты)",
        "doc": "Caterpillar rated payload of the 777 and 785 (vendor data; not opened in this work)",
        "page": "", "label": "vendor", "url": ""},
    "abb_ph": {
        "doc_ru": "ABB, применение «pH/ORP во флотации медной руды», с. 3: абразив пульпы и накипь от извести (требование вендора к датчику)",
        "doc": "ABB application note, pH/ORP in copper flotation, p. 3: slurry abrasion and lime scale (vendor requirement)",
        "page": "3", "label": "vendor",
        "url": "https://library.e.abb.com/public/ce5cb93e495f4eafb1b60f98308a7203/AD_ANAINST_001-EN%20Rev%20A.pdf"},
    "kaz_ar2020": {
        "doc_ru": "KAZ Minerals, годовой отчёт 2020, с. 61: самосвал 793D Актогая с облегчённым кузовом, 236 т",
        "doc": "KAZ Minerals annual report 2020, p. 61: Aktogay 793D haul truck with lightweight tray, 236 t payload",
        "page": "61", "label": "fact", "url": "https://www.kazminerals.com/media/22033/kaz-minerals-ar-2020.pdf"},
    "specalog793d": {
        "doc_ru": "Caterpillar, Specalog 793D (AEHQ5600-01), с. 1 и 20: мощность 1 801 кВт, масса 383,7 т, подъём кузова 20,25 с, опускание 17,51 с",
        "doc": "Caterpillar 793D Specalog AEHQ5600-01, pp. 1 and 20: 1 801 kW, 383.7 t, body raise 20.25 s, power down 17.51 s",
        "page": "1, 20", "label": "vendor", "url": "https://www.vost-tech.ru/files/catalog/OHT/793d_specalog.pdf"},
    "stand_map": {
        "doc_ru": "Карта стенда (OpenStreetMap, ODbL): карьер way/773805067, дробилка way/773805064; съезд нарисован нами. Длина откатки — расчёт по карте",
        "doc": "Stand map (OpenStreetMap, ODbL): quarry way/773805067, crusher way/773805064; the ramp is drawn by us. Haul length: calculated on the map",
        "page": "", "label": "calc", "url": ""},
    "roster": {
        "doc_ru": "Состав смены по ролям: допущение стенда (открытых данных нет); в карьере за смену "
                  "больше 500 человек и больше 100 машин (Вести Семей, 06.06.2024)",
        "doc": "Shift roster by role: stand assumption; over 500 people and 100 machines per shift in the pit "
               "(Vesti Semey 06.06.2024)",
        "page": "", "label": "assumption", "url": ""},
}

# ---------------------------------------------------------------------------
# People of the shift (one twin per role on duty; crews book through them)
#   id, role (things.json roles), Russian name, crew thing or "", home node
# ---------------------------------------------------------------------------
PEOPLE = (
    ("person-crusher-mech", "crusher_mech", "Механик ЦПД", "crew-cpd", "crusher-1"),
    ("person-mill-mech", "plant_mech", "Механик фабрики (мельницы)", "crew-mill", "line-1"),
    ("person-metallurgist", "shift_metallurgist", "Металлург смены", "", "flot-1"),
    ("person-power", "power_engineer", "Дежурный энергетик", "", "power"),
    ("person-kip", "kip", "Дежурный КИПиА", "crew-kip", "line-1"),
    ("person-geologist", "shift_geologist", "Геолог смены", "", "pit"),
    ("person-water", "tailings_engineer", "Технолог хвостов и оборотной воды", "crew-water", "water"),
    ("person-dispatcher", "mine_dispatcher", "Горный диспетчер", "", "pit"),
    ("person-shift-head", "plant_shift_manager", "Начальник смены фабрики", "", "line-1"),
    # added 23.10.2026 (tier S): roles of the pit and the grinding control room. Names of the roles are common to mines;
    # that they stand on the Aktogay shift is an assumption (the roster by role is not published)
    ("person-mine-head", "mine_shift_head", "Начальник смены карьера", "", "pit"),
    ("person-road", "road_service", "Дорожная служба карьера", "", "ramp-1"),
    ("person-pit-mech", "shift_mechanic", "Сменный механик карьера", "", "exc-1"),
    ("person-grind-op", "grinding_operator", "Оператор пульта измельчения", "", "sag-1"),
)
# Chain of responsibility (main -> deputy -> shift head): the deputy is a colleague of a neighbouring trade on the
# same shift; the last link is the shift head. Roster and links are an assumption of the stand (no public data).
DEPUTY = {
    "person-crusher-mech": "person-mill-mech", "person-mill-mech": "person-crusher-mech",
    "person-kip": "person-power", "person-power": "person-kip",
    "person-metallurgist": "person-geologist", "person-geologist": "person-metallurgist",
    "person-water": "person-metallurgist", "person-dispatcher": "person-geologist",
    "person-mine-head": "person-dispatcher", "person-road": "person-mine-head",
    "person-pit-mech": "person-crusher-mech", "person-grind-op": "person-metallurgist",
}
SHIFT_HEAD = "person-shift-head"
# Chain of a trouble kind when it differs from main -> deputy -> shift head of the plant (the pit has its own head).
# The winter road: mine dispatcher -> head of the pit shift -> road service (T-K4: KAZ Minerals names the risk, not the roster).
CHAIN_BY_KIND = {
    "road_winter": ("person-dispatcher", "person-mine-head", "person-road"),
    "driver_fatigue": ("person-dispatcher", "person-mine-head"),
    "oil_contam": ("person-pit-mech", "person-dispatcher", "person-mine-head"),
    "exc_down": ("person-pit-mech", "person-dispatcher", "person-mine-head"),
}
# Excavators with a confirmed on-machine oil contamination sensor: the EX3600-6 brochure (p. 11); the other models' lists are not
# confirmed in the sources, so the twin publishes -1 for them (source check of 23.10.2026).
OIL_SENSOR = ("exc-1",)
# Truck of the fatigue alert (scenario fatigue): bort number of the equipment list of 29.02.2024 (CAT 793D).
FATIGUE_BORT = "HT141"
# Who goes when a decision without a crew is called (issue kind -> person).
DECISION_PERSON = {
    "grid": "person-power", "hard": "person-geologist", "pit": "person-dispatcher", "piezo": "person-water",
    "reline": "person-dispatcher", "water": "person-water", "hpgr_fire": "person-power",
    "road": "person-dispatcher", "found": "person-metallurgist",
    # SAG kWh/t above the ore: the metallurgist checks load, feed size and liner (mechanics for a liner)
    "energy": "person-metallurgist", "liner": "person-metallurgist",
    # grinding media overuse and a concentrate grade below the norm: the metallurgist checks the charge and the cleaner
    "balls": "person-metallurgist", "conc": "person-metallurgist",
    "startup": "person-shift-head",           # cancels the start command given while people are inside a mill
    "icy": "person-dispatcher",               # restricts the traffic on the haul roads
    "leachcold": "person-metallurgist",       # the metallurgist of the oxide complex looks at the pad (no procedure published)
    "fatigue": "person-dispatcher",           # takes the driver off the trip / separates the machines
    "oil": "person-pit-mech",                 # filters and flushes the hydraulic oil of the excavator
    "roping": "person-grind-op",              # the grinding operator reduces the feed / opens the cyclones
    # tier T of 24.10.2026: who goes to the unit (the roles are an assumption of the stand)
    "gmd": "person-kip", "froth": "person-kip", "idler": "person-crusher-mech",
    "rake": "person-mill-mech", "cloth": "person-mill-mech", "slurry": "person-mill-mech",
    "brake": "person-pit-mech", "track": "person-pit-mech",
}
# Person who answers for a node, by thing type (attribute responsible.person).
TYPE_PERSON = {
    "site": "person-dispatcher", "pit": "person-dispatcher", "exc": "person-dispatcher",
    "fleet": "person-dispatcher", "truck": "person-dispatcher", "road": "person-dispatcher",
    "drill": "person-dispatcher", "dozer": "person-dispatcher",
    "stockpile": "person-dispatcher", "face": "person-geologist", "batch": "person-geologist",
    "crusher": "person-crusher-mech", "conveyor": "person-crusher-mech", "weigher": "person-crusher-mech",
    "line": "person-metallurgist", "flot": "person-metallurgist", "rougher": "person-metallurgist",
    "cleaner": "person-metallurgist", "thick": "person-metallurgist", "conc-stock": "person-metallurgist",
    "analyzer": "person-metallurgist", "sag": "person-mill-mech", "pebble": "person-mill-mech",
    "ball": "person-mill-mech", "cyclones": "person-mill-mech", "filter": "person-mill-mech",
    "flowmeter": "person-kip", "water": "person-water", "piezometer": "person-water", "power": "person-power",
    "phmeter": "person-kip", "leach": "person-metallurgist", "sxew": "person-metallurgist",
}
CREW_PERSON = {"crew-kip": "person-kip", "crew-cpd": "person-crusher-mech", "crew-mill": "person-mill-mech",
               "crew-water": "person-water"}

# ---------------------------------------------------------------------------
# Pit: trucks by model, excavators, faces, haul roads
# ---------------------------------------------------------------------------
# model, parameter row of the count, of the payload and of the trucks on ore ("" = none); ore trucks
# alternate line 1, line 2, the rest of the model hauls waste. Counts: fact 06.06.2024 (vesti2024);
# split ore / waste: assumption chosen so that the ore haul per cycle equals the former aggregate
# (36 x 136 t = 4 896 t).
TRUCK_MODELS = (
    ("CAT 777", "fleet_n_777", "fleet_payload_777_t", ""),
    ("CAT 785", "fleet_n_785", "fleet_payload_t", "fleet_ore_785"),
    ("CAT 793", "fleet_n_793", "fleet_payload_793_t", "fleet_ore_793"),
)
# Excavators: id, duty (ore: feeds a crusher, its line by number; waste: stripping), face.
EXCAVATORS = (
    ("exc-1", "ore", "face-1"),
    ("exc-2", "ore", "face-2"),
    ("exc-3", "ore", "face-3"),
    ("exc-4", "waste", "face-4"),
    ("exc-5", "waste", "face-5"),
)
# Bort numbers and models by the company equipment list of 29.02.2024 (kaz_equip2024, "the list is not
# exhaustive"): thing -> (bort number, model, label). Units the list does not name get a conditional
# number ("номер условный"); the fleet size stays the one of the 2024 press tour (37 trucks, 5 excavators).
EXC_BORT = {
    "exc-1": ("EX01", "Hitachi EX3600", "fact"),
    "exc-2": ("EX02", "Hitachi (модель не названа)", "номер условный"),
    "exc-3": ("EX03", "Hitachi (модель не названа)", "номер условный"),
    "exc-4": ("EX51", "Hitachi ZX870", "fact"),
    "exc-5": ("EX53", "Hitachi EX1200", "fact"),
}
# Trucks with a bort number in the list: (model of the roster, place within the model) -> (bort, model).
TRUCK_BORT_FACT = {
    ("CAT 785", 0): ("HT121", "CAT 785C"),
    ("CAT 785", 1): ("HT136", "CAT 785D"),
    ("CAT 785", 2): ("HT137", "CAT 785D"),
    ("CAT 785", 3): ("HT138", "CAT 785D"),
    ("CAT 793", 0): ("HT141", "CAT 793D"),
}
# Drill rigs (fact: kaz_equip2024): id, bort, model, face it drills (assumption).
DRILLS = (
    ("drill-01", "DR01", "Sandvik D55", "face-1"),
    ("drill-02", "DR02", "Sandvik D55", "face-2"),
    ("drill-03", "DR03", "Sandvik D55", "face-3"),
    ("drill-04", "DR04", "Sandvik D55", "face-4"),
    ("drill-12", "DR12", "Epiroc D65", "face-5"),
    ("drill-31", "DR31", "Epiroc Pit Viper 231", "face-1"),
)
# Dozers (fact: kaz_equip2024): id, bort, model, where it works (assumption).
DOZERS = (
    ("dozer-01", "DZ01", "CAT D9R", "ramp-1"),
    ("dozer-21", "DZ21", "CAT D10T", "face-1"),
    ("dozer-22", "DZ22", "CAT D10T", "face-2"),
    ("dozer-23", "DZ23", "CAT D10T", "face-3"),
    ("dozer-41", "DZ41", "Komatsu D375", "face-4"),
    ("dozer-42", "DZ42", "Komatsu D375", "face-5"),
    ("dozer-43", "DZ43", "Komatsu D375", "road-dump"),
)
# Faces: id, excavator, kind, bench number (assumption: horizons are not published; pit depth up to 230 m, fact).
FACES = (
    ("face-1", "exc-1", "ore", 12),
    ("face-2", "exc-2", "ore", 11),
    ("face-3", "exc-3", "ore", 13),
    ("face-4", "exc-4", "waste", 6),
    ("face-5", "exc-5", "waste", 7),
)
# Haul roads: id, Russian name, line it leads to (0: waste dump).
ROADS = (
    ("ramp-1", "Съезд к ЦПД-1", 1),
    ("ramp-2", "Съезд к ЦПД-2", 2),
    ("road-dump", "Дорога на отвал вскрыши", 0),
)

# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------
# id, type, parent node, Russian name
INSTRUMENTS = tuple(
    item for n in LINES for item in (
        (f"analyzer-{n}", "analyzer", f"flot-{n}", f"Анализатор хвостов и питания {n}"),
        (f"weigher-{n}", "weigher", f"conveyor-{n}", f"Конвейерные весы {n}"),
        (f"flowmeter-{n}", "flowmeter", f"rougher-{n}", f"Расходомер собирателя {n}"),
    )
) + (
    ("piezo-1", "piezometer", "water", "Пьезометр дамбы П-1"),
    ("piezo-2", "piezometer", "water", "Пьезометр дамбы П-2"),
    ("piezo-3", "piezometer", "water", "Пьезометр дамбы П-3"),
    ("ph-1", "phmeter", "rougher-1", "pH-метр флотации 1"),
    ("ph-2", "phmeter", "rougher-2", "pH-метр флотации 2"),
)
# piezometer -> parameter row of its offset from the dam reading of the model (assumption)
PIEZO_OFFSET = {"piezo-1": "pond_piezo_off1_kpa", "piezo-2": "pond_piezo_off2_kpa", "piezo-3": "pond_piezo_off3_kpa"}


def truck_roster(prm=None) -> list[tuple[str, str, str, str, int]]:
    """(id, model, payload row, duty, line) for every truck in TRUCK_MODELS order.

    Within a model the ore trucks come first and alternate line 1, line 2; the rest haul waste.
    Counts from prm (a ParamSet) or the table values.
    """
    from .params import TABLE

    def val(key: str) -> float:
        return float(prm[key]) if prm is not None else TABLE[key].value

    out = []
    i = 1
    for model, n_key, p_key, ore_key, *_ in TRUCK_MODELS:
        n = int(round(val(n_key)))
        n_ore = min(n, int(round(val(ore_key)))) if ore_key else 0
        for j in range(n):
            duty, line = ("ore", 1 + j % 2) if j < n_ore else ("waste", 0)
            out.append((f"truck-{i:02d}", model, p_key, duty, line))
            i += 1
    return out


def truck_borts(prm=None) -> dict[str, tuple[str, str, str]]:
    """truck id -> (bort number, model, label): the numbers of the equipment list where it names one
    (label "fact"), else a conditional number HT2NN ("номер условный") with the model of the roster."""
    out = {}
    seen: dict[str, int] = {}
    for tid, model, _p, _duty, _line in truck_roster(prm):
        j = seen.get(model, 0)
        seen[model] = j + 1
        fact = TRUCK_BORT_FACT.get((model, j))
        if fact:
            out[tid] = (fact[0], fact[1], "fact")
        else:
            out[tid] = (f"HT2{tid[-2:]}", model, "номер условный")
    return out


def fatigue_truck(prm=None) -> tuple[str, str, str]:
    """(thing id, bort number, model) of the truck in the fatigue alert: HT141 CAT 793D of the equipment list, else the first
    ore truck of the roster."""
    borts = truck_borts(prm)
    for tid, (bort, model, _label) in borts.items():
        if bort == FATIGUE_BORT:
            return tid, bort, model
    tid = next(iter(borts))
    return tid, borts[tid][0], borts[tid][1]
