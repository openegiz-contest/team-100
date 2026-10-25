"""Live check of plausibility: invariants of the twin that must hold at every moment.

The page «Калибровка» reads the twin from Ditto, evaluates the list below on the values it sees (web/static/plausibility.js,
once a minute, ✓ / ✗ with the value, the range and the source) and keeps the count of the minutes it has watched. The
list is data (this file writes web/static/plausibility.json); `evaluate` here is the same rule in Python, so a test can
run it on a plant snapshot and on the scenarios and keep the page and the model honest with each other.

A reference is "thing.feature" as published to Ditto. An item is a value
    scale * (sum of terms) [/ (sum of den terms)]
where a term is [coef, ref, ref, ...] (coef times the product of the refs). A check holds when every item that has data is
inside [lo, hi] (None = open). Missing data gives status "na", never a pass.

Groups: balance (what goes in = what goes out, residual in %), limit (hard physical or equipment limit), range
(literature or report range of a quantity). Every check names its source and the label of the source (fact, vendor,
project, analog, calc, assumption) in the sense of sim/params.py.

  python -I aktogay/run.py plausibility --write aktogay/web/static/plausibility.json
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import params as P  # noqa: E402
from sim import site_aktogay as SITE  # noqa: E402

GROUP_RU = {"balance": "баланс", "limit": "предел", "range": "диапазон"}
LINES = SITE.LINES
EPS = 1e-9

# sources (short; the long form is in PARAMETERS.md)
SRC_OVOS = "ОВОС Актогай 2018 (минедокс, таблицы 1.5.1–1.5.2)"
SRC_KAZ_Q = "отчёты KAZ Minerals 2018–2025 (kaz_quarterly.csv, 32 квартала)"
SRC_KAZ_EN = "KAZ Minerals, энергия 2024: 2 033 ГВт·ч на 58,3 Мт руды = 34,9 кВт·ч/т"
SRC_KAZ_W = "KAZ Minerals, вода 2024: 34,852 млн м³ на 58,3 Мт = 0,60 м³/т; проект 0,63–0,99 (ОВОС)"
SRC_SAG28 = "mining-technology.com 02.2018: SAG 28 МВт, шаровые 2 × 22 МВт"
SRC_BRAD = "Bradken + KAZ Minerals 2021, таблица 1 (с. 3) и с. 12: 6,6 проект, 7,25 измерено в сентябре 2017 – марте 2019"
SRC_PEK = "ПЭК ТОО «KAZ Minerals Aktogay» 2023–2024, с. 10: рабочий объём склада 163 000 т"
SRC_AR20 = "KAZ Minerals, годовой отчёт 2020, с. 61: Aktogay 793D, 236 т"
SRC_CAT785 = "Caterpillar, паспорт 785: 136 т (данные производителя)"
SRC_CAT777 = "Caterpillar, паспорт 777: около 90 т (данные производителя, не открыт)"


def _t(coef: float, *refs: str) -> list:
    return [coef, *refs]


def _item(terms: list, den: list | None = None, scale: float = 1.0, name: str = "") -> dict:
    d: dict = {"terms": terms, "scale": scale}
    if den:
        d["den"] = den
    if name:
        d["name"] = name
    return d


def _chk(cid: str, group: str, ru: str, unit: str, items: list, lo, hi, src: str, label: str, note: str = "") -> dict:
    return {"id": cid, "group": group, "ru": ru, "unit": unit, "items": items, "lo": lo, "hi": hi,
            "src": src, "label": label, "note": note}


def build(prm: P.ParamSet | None = None) -> dict:
    """The list of checks with limits from the parameter table (prm or table values)."""
    v = (lambda k: float(prm[k])) if prm is not None else (lambda k: P.TABLE[k].value)
    tol = v("tol_balance_pct")
    out: list[dict] = []

    # ---- balances -------------------------------------------------------------------------------------------
    out.append(_chk(
        "b_cu_line", "balance", "Медь: питание = концентрат + хвосты (по линиям, показания расходомеров и анализаторов)", "%",
        [_item([_t(0.01, f"line-{n}.tph", f"flot-{n}.feed_cu"), _t(-0.01, f"flot-{n}.conc_tph", f"flot-{n}.conc_cu"),
                _t(-0.01, f"line-{n}.tph", f"flot-{n}.tail_cu"), _t(0.01, f"flot-{n}.conc_tph", f"flot-{n}.tail_cu")],
               den=[_t(0.01, f"line-{n}.tph", f"flot-{n}.feed_cu")], scale=100.0, name=f"линия {n}") for n in LINES],
        -tol, tol, "закон сохранения массы; допуск tol_balance_pct (допущение, PARAMETERS.md)", "calc"))
    out.append(_chk(
        "b_cu_mod", "balance", "Медь: невязка модуля потерь за 2 ч модели (весы, расходомеры, анализаторы)", "%",
        [_item([_t(1.0, "mod-losses.cu_residual_pct")], name="модуль")], -tol, tol,
        "закон сохранения массы; считает akt-losses по показаниям приборов", "calc"))
    out.append(_chk(
        "b_water", "balance", "Вода: забор = вода с хвостами + испарение + влага кека + изменение пруда", "%",
        [_item([_t(1.0, "water.residual_pct")], name="шаг модели"), _item([_t(1.0, "mod-losses.water_residual_pct")], name="модуль, 2 ч")],
        -tol, tol, "закон сохранения массы; допуск tol_balance_pct", "calc"))
    out.append(_chk(
        "b_conc", "balance", "Концентрат: питание сгустителя = разгрузка на фильтр + изменение запаса", "%",
        [_item([_t(1.0, "mod-losses.conc_residual_pct")], name="модуль")], -tol, tol,
        "закон сохранения массы; считает akt-losses", "calc"))
    out.append(_chk(
        "b_ore", "balance", "Руда: расход склада = питание SAG (по линиям)", "%",
        [_item([_t(1.0, f"stockpile-{n}.out_tph"), _t(-1.0, f"sag-{n}.feed_tph")], den=[_t(1.0, f"sag-{n}.feed_tph")],
               scale=100.0, name=f"линия {n}") for n in LINES], -5.0, 5.0,
        "реклаймер подаёт на SAG всё, что берёт со склада; допуск 5 %: точки двух вещей уходят в Ditto с разницей в несколько секунд (до 3–4 мин модели при x60), на живой странице расхождение до 2,4 % видно", "assumption"))
    out.append(_chk(
        "b_energy", "balance", "Энергия: нагрузка площадки = измельчение + дробление и ленты + прочее", "МВт",
        [_item([_t(1.0, "power.site_mw"), _t(-1.0, "power.grinding_mw"), _t(-1.0, "power.other_mw"),
                _t(-0.001, "crusher-1.power_kw"), _t(-0.001, "crusher-2.power_kw"),
                _t(-0.001, "conveyor-1.power_kw"), _t(-0.001, "conveyor-2.power_kw")], name="площадка")], -2.0, 2.0,
        "баланс мощности (sim/utilities.power_balance); допуск 2 МВт — шум 1 % у 8 измерителей мощности", "calc"))
    # ---- hard limits ----------------------------------------------------------------------------------------
    out.append(_chk(
        "l_sag", "limit", "Мощность SAG не выше 28 МВт", "МВт",
        [_item([_t(0.001, f"sag-{n}.power_kw")], name=f"SAG {n}") for n in LINES], 0.0, 28.0, SRC_SAG28, "vendor"))
    out.append(_chk(
        "l_ball", "limit", "Мощность шаровой мельницы не выше 22 МВт", "МВт",
        [_item([_t(0.001, f"ball-{n}{s}.power_kw")], name=f"шаровая {n}{s}") for n in LINES for s in "ab"], 0.0, 22.0,
        SRC_SAG28, "vendor"))
    out.append(_chk(
        "l_grid", "limit", "Нагрузка площадки не выше предела сети", "МВт",
        [_item([_t(1.0, "power.site_mw"), _t(-1.0, "power.grid_limit_mw")], name="запас")], None, 0.5,
        "предел сети pow_grid_limit_mw (допущение, PARAMETERS.md); при урезании сети двойник сбрасывает нагрузку", "assumption"))
    out.append(_chk(
        "l_stock", "limit", "Склад руды: не меньше 0 и не больше рабочего объёма", "т",
        [_item([_t(1.0, f"stockpile-{n}.level_t")], name=f"склад {n}") for n in LINES], 0.0, v("stock_total_t"),
        SRC_PEK, "project"))
    out.append(_chk(
        "l_pond", "limit", "Пруд хвостохранилища не отрицателен", "м³",
        [_item([_t(1.0, "water.pond_m3")], name="пруд")], 0.0, None, "физика: объём не бывает отрицательным", "calc"))
    out.append(_chk(
        "l_crusher", "limit", "Производительность дробилки не выше проектной (4 386–5 044 т/ч)", "т/ч",
        [_item([_t(1.0, f"crusher-{n}.tph")], name=f"ЦПД {n}") for n in LINES], 0.0, 5043.9, SRC_OVOS + ", с. 26", "project"))
    # trucks: load against the rated payload of the model (payload rows after the 793D = 236 t correction)
    items = []
    lim = {"CAT 777": 90.0, "CAT 785": 136.0, "CAT 793": 236.0}
    names = []
    for tid, model, _p, _duty, _line in SITE.truck_roster(prm):
        items.append(_item([_t(1.0, f"{tid}.load_t")], name=f"{tid} {model}"))
        names.append(lim[model])
    out.append(_chk(
        "l_truck", "limit", "Загрузка самосвала не выше номинала модели (793D — 236 т)", "т", items, 0.0, 236.0,
        SRC_AR20 + "; 785 — 136 т, 777 — около 90 т (Caterpillar)", "fact",
        note="предел по самосвалу: " + "; ".join(sorted({f"{m} {l:.0f} т" for m, l in lim.items()}))))
    out[-1]["item_hi"] = names
    # ---- ranges of quantities -------------------------------------------------------------------------------
    # the live value of the specific energy is not the energy of the mill's average ore: a starved SAG (stock out, pit stop) shows 10-17 kWh/t
    # for an hour, a hard block 8-9, so the band stays wide (5-11 held in the scenarios of the test). The calibration check against the
    # measured 7.25 (and the design 6.6) is a row of VALIDATION section 4 on the year of the fit (6.74 kWh/t, -7.0 % and +2.1 %), not a live band.
    out.append(_chk(
        "r_sag_e", "range", "Удельная энергия SAG (проект 6,6; измерено 7,25 кВт·ч/т)", "кВт·ч/т",
        [_item([_t(1.0, f"sag-{n}.e_kwh_t")], name=f"SAG {n}") for n in LINES], 5.0, 11.0,
        SRC_BRAD + "; вилка широкая: голодный SAG и твёрдые блоки поднимают кВт·ч/т на часы, вилка A*b 23–96 (Josemaria, PARAMETERS.md) — допущение; "
        "на год подгонки модель даёт 6,74 (VALIDATION, раздел 4)", "vendor"))
    out.append(_chk(
        "r_site_e", "range", "Электроэнергия площадки на тонну руды", "кВт·ч/т",
        [_item([_t(1.0, "power.site_mw")], den=[_t(0.001, "site.tph")], scale=1.0, name="площадка")], 30.0, 45.0, SRC_KAZ_EN + "; верхняя граница выше среднего года: постоянная нагрузка 112 МВт при недогрузке растёт на т", "fact"))
    out.append(_chk(
        "r_water", "range", "Свежая вода на тонну руды", "м³/т",
        [_item([_t(1.0, "water.intake_m3h")], den=[_t(1.0, "site.tph")], name="забор")], 0.50, 1.00, SRC_KAZ_W, "fact"))
    out.append(_chk(
        "r_rec", "range", "Извлечение меди по линии", "%",
        [_item([_t(1.0, f"line-{n}.recovery")], name=f"линия {n}") for n in LINES], 80.0, 91.0, SRC_KAZ_Q + ": 80,9–90,7 %", "fact"))
    out.append(_chk(
        "r_conc", "range", "Содержание меди в концентрате", "% Cu",
        [_item([_t(1.0, f"flot-{n}.conc_cu")], name=f"линия {n}") for n in LINES], 18.0, v("flot_conc_max_pct"),
        SRC_OVOS + ": проект 24,3 %; верхняя граница — стехиометрия халькопирита 34,6 %", "project"))
    out.append(_chk(
        "r_tails", "range", "Медь в хвостах", "% Cu",
        [_item([_t(1.0, f"flot-{n}.tail_cu")], name=f"линия {n}") for n in LINES], 0.03, 0.075,
        "0,41 % × (1 − 87,2 %) = 0,053 % (отчёт 2025); 0,075 % — порог тревоги анализатора", "calc"))
    out.append(_chk(
        "r_p80", "range", "Крупность слива циклонов P80", "мкм",
        [_item([_t(1.0, f"cyclones-{n}.p80_um")], name=f"линия {n}") for n in LINES], 110.0, 230.0,
        "Bradken 2021: 180 мкм; суточные P80 фабрики 120–180 мкм (Satbayev 2025)", "vendor"))
    return {"kind": "akt-plausibility", "version": 1, "checks": out,
            "n": len(out), "groups": {k: sum(1 for c in out if c["group"] == k) for k in GROUP_RU}}


def _prod(refs: list, get) -> float | None:
    x = 1.0
    for r in refs:
        g = get(r)
        if g is None or not isinstance(g, (int, float)) or not math.isfinite(g):
            return None
        x *= g
    return x


def _sum(terms: list, get) -> float | None:
    s = 0.0
    for t in terms:
        p = _prod(t[1:], get)
        if p is None:
            return None
        s += t[0] * p
    return s


def item_value(item: dict, get) -> float | None:
    """Value of one item or None when a number is missing (or a denominator is zero)."""
    num = _sum(item["terms"], get)
    if num is None:
        return None
    if item.get("den"):
        den = _sum(item["den"], get)
        if den is None or abs(den) < 1e-6:
            return None
        num = num / den
    return item.get("scale", 1.0) * num


def evaluate(spec: dict, get) -> list[dict]:
    """[{id, status 'ok'|'bad'|'na', value, name, n, n_bad}] for every check; `get(ref)` returns a number or None."""
    rows = []
    for c in spec["checks"]:
        lo, hi = c["lo"], c["hi"]
        item_hi = c.get("item_hi")
        worst = None
        n = n_bad = 0
        for i, it in enumerate(c["items"]):
            val = item_value(it, get)
            if val is None:
                continue
            n += 1
            h = item_hi[i] if item_hi else hi
            span = (h - lo) if (lo is not None and h is not None) else (abs(h if h is not None else lo) or 1.0)
            over = max(((lo - val) / span) if lo is not None else -1e9, ((val - h) / span) if h is not None else -1e9)
            if over > 1e-9:
                n_bad += 1
            if worst is None or over > worst[0]:
                worst = (over, val, it.get("name", ""))
        if worst is None:
            rows.append({"id": c["id"], "status": "na", "value": None, "name": "", "n": 0, "n_bad": 0})
        else:
            rows.append({"id": c["id"], "status": "bad" if n_bad else "ok", "value": worst[1], "name": worst[2],
                         "n": n, "n_bad": n_bad})
    return rows


def snapshot_getter(snap: dict):
    """get(ref) over a Plant.snapshot() dictionary {thing: {feature: value}}."""
    def get(ref: str):
        thing, _, feat = ref.partition(".")
        v = snap.get(thing, {}).get(feat)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v != -1.0 else None
    return get


def json_text(prm: P.ParamSet | None = None) -> str:
    return json.dumps(build(prm), ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) == 2 and argv[0] == "--write":
        with open(argv[1], "w", encoding="utf-8", newline="\n") as f:
            f.write(json_text())
        return 0
    spec = build()
    print(f"{spec['n']} checks: {spec['groups']}")
    for c in spec["checks"]:
        print(f"  {c['id']:<14} {GROUP_RU[c['group']]:<9} {c['ru']}  [{c['lo']}, {c['hi']}] {c['unit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
