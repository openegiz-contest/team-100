"""«Изнутри»: signals, failures and trouble kinds of tier T (24.10.2026), added to the nodes by modules/inside.py.

Each entry adds to an existing node (key = node id): the monitored signal with the place where it is seen, the failure class
with its source and label, and the trouble kind. Depth and sources are those of the readiness cards (modules/readiness_t.py).
"""
from __future__ import annotations

U_GMD = "https://library.e.abb.com/public/3b41eb5173848571c125793d00572de5/REMOTE%20DIAGNOSTIC%20SERVICES%20FOR%20GEARLESS%20MILL%20DRIVES.pdf"
U_BELT = "https://www.miningscience.pwr.edu.pl/pdf-59825-3376?filename=3376.pdf"
U_PPI = "https://www.ppi-global.com/userdocs/literature/ppi/documents/crp_047-01_bearingterms.pdf"
U_ANDRITZ = "https://www.andritz.com/resource/blob/14766/39b32881f5cf79564ab492e33b47d549/aa-automation-mpc-sag-mills-flotation-circuits-data.pdf"
U_OUTOTEC = "https://d3pcsg2wjq9izr.cloudfront.net/files/40011/download/332960/low_res_Outotec_thickening_18022011.pdf"
U_METSO = "https://www.metso.com/globalassets/ebook/brochure-larox-pf-services-en-4401.pdf"
U_WEIR = "https://www.global.weir/globalassets/resources/product-pdfs/warman/warman-ah-pumps-brochure.pdf"
U_793 = "https://www.petersoncat.com/products/new/mining-trucks/793f-tier-4"
U_EX36 = "https://hitachicm.com.au/wp-content/uploads/2021/05/EX3600-6_KS-EN056T-small.pdf"


def _sig(name, thing, feature, unit, digits, where, source, label, url="", note=""):
    d = {"name": name, "thing": thing, "feature": feature, "unit": unit, "digits": digits, "where": where, "source": source,
         "label": label}
    if url:
        d["url"] = url
    if note:
        d["note"] = note
    return d


def _fail(name, stat, source, label, trouble="", url=""):
    d = {"name": name, "stat": stat, "source": source, "label": label, "trouble": trouble}
    if url:
        d["url"] = url
    return d


EXTRA = {
    "p-sag": {
        "signals": [_sig("Воздушный зазор ГМД, мм", "sag-{n}", "gmd_gap_mm", "мм", 1, "dcs",
                         "ABB: нижний предел зазора «could be defined» (пример 12,5 мм), тренды с alarm и trip limits", "вендор", U_GMD,
                         "12,5 мм — пример из текста, не уставка; на Актогае подключение услуги не подтверждено")],
        "failures": [_fail("Сужение воздушного зазора: защита отключает привод", "пример предела 12,5 мм; частота не найдена",
                           "ABB, удалённая диагностика ГМД, с. 18", "вендор", "gmd_gap", U_GMD)],
        "troubles": ["gmd_gap"],
    },
    "p-conveyor": {
        "signals": [_sig("Температура подшипника ролика, °C", "conveyor-{n}", "idler_temp_c", "°C", 0, "dcs",
                         "тепловизор или датчики на ленте; порог — допущение", "допущение", U_BELT)],
        "failures": [_fail("Перегрев подшипника ролика: риск возгорания ленты", "3 % в год — гарантийное допущение изготовителя роликов",
                           "PPI, CRP 047-01, с. 1; Zimroz, Król 2009", "допущение", "idler_hot", U_PPI)],
        "troubles": ["idler_hot"],
    },
    "p-flot": {
        "signals": [_sig("Размах уровня ячеек, %", "flot-{n}", "level_swing_pct", "%", 1, "dcs",
                         "уровнемеры ячеек в АСУ ТП; размах считается по тренду", "допущение", U_ANDRITZ)],
        "failures": [],
        "troubles": ["froth_swing"],
    },
    "p-thick": {
        "signals": [_sig("Момент привода граблин, % расчётного", "thick-{n}", "rake_torque_pct", "%", 0, "dcs",
                         "Outotec: тревога, затем отключение привода по давлению; 40/80 % — пример учебного блога", "вендор", U_OUTOTEC,
                         "числовых уставок вендор не даёт")],
        "failures": [],
        "troubles": ["rake_torque"],
    },
    "p-filter": {
        "signals": [_sig("Цикл фильтрации, % новой ткани", "filter-{n}", "cycle_pct", "%", 0, "dcs",
                         "циклы пресса в АСУ ТП; ткань слепнет и ограничивает производительность (Metso)", "вендор", U_METSO)],
        "failures": [_fail("Ткань слепнет; замена «от 30 минут»", "30 минут — лучший случай", "Metso, Larox PF, с. 4 и 8", "вендор",
                           "cloth_blind", U_METSO)],
        "troubles": ["cloth_blind"],
    },
    "p-grind": {
        "signals": [_sig("Напор насоса питания циклонов, % нормы", "cyclones-{n}", "pump_head_pct", "%", 0, "dcs",
                         "давление нагнетания насоса; зоны ISO 10816 для пульповых насосов не применяются", "допущение", U_WEIR)],
        "failures": [_fail("Кавитация и износ колеса пульпового насоса", "ресурс колеса 1 300 → 2 000 ч и 4 200 → 7 800 ч (случаи Weir)",
                           "Weir, Warman AH, с. 7; Technical Bulletin 36, с. 3", "вендор", "pump_cavit", U_WEIR)],
        "troubles": ["pump_cavit"],
    },
    "m-cat793": {
        "signals": [_sig("Температура масла тормозов самосвала HT141, °C", "fleet", "brake_oil_c", "°C", 0, "analog",
                         "CAT 793F: указатель температуры масла тормозов и VIMS (аналог); принцип «порог с выдержкой времени»", "вендор",
                         U_793, "это 793F, а не 793D; числовые пороги не используются")],
        "failures": [],
        "troubles": ["brake_hot"],
    },
    "m-ex3600": {
        "signals": [_sig("Давление натяжения гусениц, % уровня автостопа", "exc-1", "track_press_pct", "%", 0, "machine",
                         "проспект EX3600-6, с. 7: ход останавливается автоматически при заданном давлении аккумуляторов", "вендор", U_EX36,
                         "уровень не опубликован; в диспетчерскую — при опции Global e-Service")],
        "failures": [],
        "troubles": ["track_tension"],
    },
}


def apply(groups) -> None:
    """Add the entries of EXTRA to the nodes of the groups (once)."""
    by_id = {nd["id"]: nd for g in groups for nd in g["nodes"]}
    for nid, add in EXTRA.items():
        nd = by_id[nid]
        have = {s["name"] for s in nd["signals"]}
        nd["signals"].extend(s for s in add["signals"] if s["name"] not in have)
        have = {f["name"] for f in nd["failures"]}
        nd["failures"].extend(f for f in add["failures"] if f["name"] not in have)
        nd["troubles"].extend(t for t in add["troubles"] if t not in nd["troubles"])
