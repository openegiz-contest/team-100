"""Troubles of tier T (24.10.2026) for akt-priority: eight slow equipment troubles, each with a monitored signal that moves
for hours before the consequence: gearless drive air gap of the SAG, idler bearing temperature of the conveyor, level swing of
the flotation cells, rake torque of the thickener, cycle time of the filter, discharge pressure of the cyclone feed pump, brake
oil temperature of the truck HT141 (VIMS) and track tension of the shovel EX01.

Same rules as tiers.py: nothing but the Store (Ditto / InfluxDB) and the parameter table; signal, threshold (a parameter of the
site), price (t Cu/h and USD/h, model estimate), who is called, what to do and when it is closed (the nine points of
modules/readiness.py). Where a source names the risk and not the number the threshold is an assumption or an example, and the
text says so. The slurry pump has no vibration zones of ISO 10816: that standard excludes slurry pumps.
"""
from __future__ import annotations

from . import expect as ex
from . import tiers
from .policy import Trouble
from .store import NO_VALUE
from .text import ANALOG, ASSUME, EST, cu_tph, dur, num

LINES = (1, 2)
EXAMPLE = "[пример]"

# who answers (crew, roles): the same table in priority.WHO, the person twins in sim/site_aktogay.DECISION_PERSON
WHO = {
    "gmd_gap": ("", ("kip", "power_engineer")),                       # drive service: air gap of the gearless drive
    "idler_hot": ("", ("crusher_mech", "plant_mech")),                # conveyor crew: change the idler
    "froth_swing": ("", ("kip", "shift_metallurgist")),               # level loop, valve, sensor
    "rake_torque": ("", ("plant_mech", "plant_shift_manager")),       # rakes, feed density
    "cloth_blind": ("", ("plant_mech", "plant_shift_manager")),       # filter cloth
    "pump_cavit": ("", ("plant_mech", "grinding_operator")),          # cyclone feed pump
    "brake_hot": ("", ("shift_mechanic", "mine_dispatcher")),         # brakes of the truck
    "track_tension": ("", ("shift_mechanic", "mine_dispatcher")),     # track tension of the shovel
}
SHORT_RU = {"gmd_gap": "воздушный зазор ГБП", "idler_hot": "перегрев ролика", "froth_swing": "колебания уровня",
            "rake_torque": "момент граблин", "cloth_blind": "ткань слепнет", "pump_cavit": "кавитация насоса",
            "brake_hot": "перегрев тормозов", "track_tension": "натяжение гусениц"}
KIND_READY = {"gmd_gap": "gmd_gap", "idler_hot": "idler_hot", "froth_swing": "froth_swing", "rake_torque": "rake_torque",
              "cloth_blind": "cloth_blind", "pump_cavit": "pump_cavit", "brake_hot": "brake_hot", "track_tension": "track_tension"}
# the node of the trouble kind, for the 3D highlight and the card: kind -> (thing template, part id of the diorama)
NODE = {"gmd_gap": "sag-{n}", "idler_hot": "conveyor-{n}", "froth_swing": "flot-{n}", "rake_torque": "thick-{n}",
        "cloth_blind": "filter-{n}", "pump_cavit": "cyclones-{n}", "brake_hot": "fleet", "track_tension": "exc-1"}

W_DCS = tiers.W_DCS
W_MACHINE = tiers.W_MACHINE
W_HEX = tiers.W_HEX

EVIDENCE = {
    "gmd_gap": [("воздушный зазор ГБП", "sag-{n}", "gmd_gap_mm", "мм", 1, "диагностика привода (ABB, удалённая диагностика) / " + W_DCS),
                ("питание SAG", "sag-{n}", "feed_tph", "т/ч", 0, "конвейерные весы"),
                ("мощность SAG", "sag-{n}", "power_kw", "кВт", 0, W_DCS)],
    "idler_hot": [("температура подшипника ролика", "conveyor-{n}", "idler_temp_c", "°C", 0, "тепловизор / датчики на ленте [допущение]"),
                  ("сигнал защиты ленты", "conveyor-{n}", "fault", "", 0, W_DCS),
                  ("производительность", "conveyor-{n}", "tph", "т/ч", 0, "конвейерные весы")],
    "froth_swing": [("размах уровня ячеек", "flot-{n}", "level_swing_pct", "%", 1, W_DCS + " (уровнемеры ячеек)"),
                    ("извлечение по линии", "flot-{n}", "recovery", "%", 1, "поточный анализатор (цикл 12–16 мин)"),
                    ("хвосты", "flot-{n}", "tail_cu", "% Cu", 3, "поточный анализатор")],
    "rake_torque": [("момент граблин", "thick-{n}", "rake_torque_pct", "%", 0, W_DCS + " (давление/момент привода)"),
                    ("запас в сгустителе", "thick-{n}", "inventory_t", "т", 0, "расчёт по весам [допущение]"),
                    ("плотность слива", "thick-{n}", "solids_pct", "%", 1, "плотномер")],
    "cloth_blind": [("время цикла фильтрации", "filter-{n}", "cycle_pct", "%", 0, W_DCS + " (циклы пресса)"),
                    ("производительность по кеку", "filter-{n}", "cake_tph", "т/ч", 1, W_DCS),
                    ("влажность кека", "filter-{n}", "moisture_pct", "%", 1, "лаборатория / анализатор влажности")],
    "pump_cavit": [("давление нагнетания насоса", "cyclones-{n}", "pump_head_pct", "%", 0, W_DCS + " (манометр нагнетания)"),
                   ("давление питания циклонов", "cyclones-{n}", "pressure_kpa", "кПа", 0, W_DCS),
                   ("P80 перелива", "cyclones-{n}", "p80_um", "мкм", 0, "анализатор крупности")],
    "brake_hot": [("температура масла тормозов", "fleet", "brake_oil_c", "°C", 0, W_MACHINE + "; VIMS, если подключена"),
                  ("самосвалов на ходу", "fleet", "trucks_ready", "шт.", 0, W_HEX),
                  ("вывоз", "fleet", "haul_tph", "т/ч", 0, W_HEX)],
    "track_tension": [("давление натяжения гусениц", "exc-1", "track_press_pct", "%", 0, W_MACHINE + "; в диспетчерскую — при опции"),
                      ("состояние экскаватора", "exc-1", "state", "", 0, W_HEX),
                      ("копает", "exc-1", "tph", "т/ч", 0, W_HEX)],
}


def _age_h(m, key: str, t: float) -> float:
    return max(0.0, (t - m.first_seen.setdefault(key, t)) / 60.0)


def _grade(m, n: int, t: float) -> float:
    return tiers._grade(m, n, t)


def line_troubles(m, n: int, running_n: bool, sag_down: bool, t: float) -> list[Trouble]:
    """gmd, idler, froth, rake, cloth, slurry of line n (run only while the line runs)."""
    prm, st = m.prm, m.store
    out: list[Trouble] = []
    if not running_n:
        return out
    cu = m._line_cu(n)
    q = st.f(f"sag-{n}", "feed_tph")
    grade = _grade(m, n, t)
    # ---- gmd: air gap of the gearless drive of the SAG closes (ABB remote diagnostics; 12.5 mm is an example)
    gap = st.f(f"sag-{n}", "gmd_gap_mm")
    if gap != NO_VALUE and gap <= prm["wt_gmd_gap_alert_mm"] and not sag_down:
        key = f"sag-{n}:gmd"
        to_fail = max(0.0, prm["wt_gmd_fail_h"] - _age_h(m, key, t))
        out.append(m._tr(key, f"sag-{n}", "gmd_gap", cu, to_fail, "rep_gmd_h", t, loud=False,
                         text=(f"воздушный зазор безредукторного привода SAG-{n} {num(gap, 1)} мм при нижнем пределе "
                               f"{num(prm['wt_gmd_gap_alert_mm'], 1)} мм (ABB называет 12,5 мм примером предела, а не уставкой "
                               f"{EXAMPLE}); если не вмешаться, защита отключит привод через ≈ {dur(to_fail)} {ASSUME}, "
                               f"мельница встанет ≈ на {num(prm['wt_gmd_repair_h'], 0)} ч ({cu_tph(-cu)}) {EST}; до этого привод "
                               f"держит подачу ниже; дежурный КИПиА с сервисом привода проверяет зазор по диагностике, "
                               f"механик не вскрывает без наряда")))
    # ---- idler: bearing of a conveyor idler overheats before the belt stops (fire risk)
    temp = st.f(f"conveyor-{n}", "idler_temp_c")
    if temp != NO_VALUE and temp >= prm["wt_idler_temp_alert_c"] and st.f(f"conveyor-{n}", "fault") != 1.0:
        key = f"conveyor-{n}:idler"
        to_fail = max(0.0, prm["wt_idler_fail_h"] - _age_h(m, key, t))
        buf = m._stock_hours(n, inflow_stops=True)
        out.append(m._tr(key, f"conveyor-{n}", "idler_hot", cu, to_fail + buf, "rep_idler_h", t, loud=False,
                         text=(f"перегрев подшипника ролика конвейера {n}: {num(temp, 0)} °C при пороге "
                               f"{num(prm['wt_idler_temp_alert_c'], 0)} °C {ASSUME}; горячий ролик — риск возгорания ленты; "
                               f"если не заменить, ленту остановят через ≈ {dur(to_fail)}, склад держит SAG ещё ≈ {dur(buf)}, "
                               f"дальше {cu_tph(-cu)} {EST}; ролики и ленты — частый класс отказов конвейеров "
                               f"(Zimroz, Król {ANALOG}), гарантийная доля отказов роликов "
                               f"{num(100 * prm['wt_idler_rate_yr'], 0)} % в год — допущение изготовителя; "
                               f"механик ЦПД с бригадой: найти ролик по тепловизору, заменить")))
    # ---- froth: level swing of the flotation cells (ANDRITZ: up to 2 h; Valmet: sensitive to level swings)
    swing = st.f(f"flot-{n}", "level_swing_pct")
    if swing != NO_VALUE and swing >= prm["wt_froth_swing_alert_pct"] and q > 0.0:
        span = prm["wt_froth_swing_alert_pct"] - prm["wt_froth_swing_ok_pct"]
        pp = prm["wt_froth_pp"] * min(1.5, max(0.0, (swing - prm["wt_froth_swing_ok_pct"]) / span)) if span > 0.0 else 0.0
        rate = ex.cu_tph(q, grade, pp)
        out.append(m._tr(f"flot-{n}:froth", f"flot-{n}", "froth_swing", rate, 0.0, "rep_froth_h", t, loud=False,
                         text=(f"колебания уровня в ячейках флотации линии {n}: размах {num(swing, 1)} % при пороге "
                               f"{num(prm['wt_froth_swing_alert_pct'], 0)} % {ASSUME}; ANDRITZ: при ПИД-регулировании уровни "
                               f"«раскачиваются» до 2 ч, Valmet: флотация чувствительна к колебаниям уровня (чисел нет); "
                               f"извлечение ниже на ≈ {num(pp, 1)} п.п. ({cu_tph(-rate)}) {EST}; дежурный КИПиА проверяет "
                               f"контур уровня: клапан, датчик, настройку, металлург — режим")))
    # ---- rake: torque of the thickener rake grows (Outotec: alarm then trip; 40/80 % are an example)
    tq = st.f(f"thick-{n}", "rake_torque_pct")
    if tq != NO_VALUE and tq >= prm["wt_rake_torque_alert_pct"]:
        key = f"thick-{n}:rake"
        to_fail = max(0.0, prm["wt_rake_fail_h"] - _age_h(m, key, t))
        rate = cu * (1.0 - prm["wt_rake_q_frac"])
        out.append(m._tr(key, f"thick-{n}", "rake_torque", rate, to_fail, "rep_rake_h", t, loud=False,
                         text=(f"момент граблин сгустителя {n} {num(tq, 0)} % от расчётного при тревоге "
                               f"{num(prm['wt_rake_torque_alert_pct'], 0)} % и подъёме/останове {num(prm['wt_rake_torque_crit_pct'], 0)} % "
                               f"{EXAMPLE} (пример из учебного блога 911Metallurgist, не норматив; Outotec описывает порядок: "
                               f"тревога, затем отключение привода, чисел не даёт); если не снизить плотность питания, граблины "
                               f"засыпает через ≈ {dur(to_fail)} {ASSUME}: линия теряет ≈ {num(100 * (1 - prm['wt_rake_q_frac']), 0)} % "
                               f"производительности (на Оюу-Толгое ≈ 60 % держали на время ремонта {ANALOG}), "
                               f"{cu_tph(-rate)} {EST}; механик фабрики: поднять граблины, снизить плотность питания")))
    # ---- cloth: blinding or damage of the filter cloth lengthens the filtration cycle
    cyc = st.f(f"filter-{n}", "cycle_pct")
    if cyc != NO_VALUE and cyc >= prm["wt_cloth_cycle_alert_pct"]:
        share = max(0.0, 1.0 - 100.0 / cyc)
        full = st.f(f"thick-{n}", "hours_to_full")
        buf = full if full != NO_VALUE and full >= 0.0 else 12.0
        rate = cu * share
        out.append(m._tr(f"filter-{n}:cloth", f"filter-{n}", "cloth_blind", rate, buf, "rep_cloth_h", t, loud=False,
                         text=(f"ткань фильтра линии {n} слепнет: цикл фильтрации {num(cyc, 0)} % от новой ткани при пороге "
                               f"{num(prm['wt_cloth_cycle_alert_pct'], 0)} % {ASSUME}; производительность пресса падает на "
                               f"≈ {num(100 * share, 0)} %, сгуститель заполнится через ≈ {dur(buf)}, дальше "
                               f"{cu_tph(-rate)} {EST}; Metso: ткани «слепнут» и ограничивают производительность, замена "
                               f"ткани «от 30 минут» — лучший случай изготовителя; механик фабрики: заменить или промыть ткань")))
    # ---- slurry: cavitation / worn impeller of the cyclone feed pump
    head = st.f(f"cyclones-{n}", "pump_head_pct")
    if head != NO_VALUE and head <= prm["wt_slurry_head_alert_pct"] and q > 0.0:
        span = 100.0 - prm["wt_slurry_head_crit_pct"]
        share = prm["wt_slurry_q_frac"] * min(1.0, max(0.0, (100.0 - head) / span)) if span > 0.0 else 0.0
        rate = cu * share
        out.append(m._tr(f"cyclones-{n}:pump", f"cyclones-{n}", "pump_cavit", rate, 0.0, "rep_slurry_h", t, loud=False,
                         text=(f"падает напор насоса питания циклонов линии {n}: {num(head, 0)} % от нормы при пороге "
                               f"{num(prm['wt_slurry_head_alert_pct'], 0)} % {ASSUME} — кавитация или износ колеса; подача "
                               f"линии ниже на ≈ {num(100 * share, 0)} % ({cu_tph(-rate)}) {EST}; зоны вибрации ISO 10816 "
                               f"для пульповых насосов не применяются (стандарт их исключает); ресурс колеса в случаях Weir "
                               f"{num(prm['wt_slurry_life_h'], 0)} ч — пример вендора, не норма; механик фабрики: проверить "
                               f"уровень в зумпфе, заменить колесо")))
    return out


def site_troubles(m, t: float, running: dict[int, bool]) -> list[Trouble]:
    """brake of the truck HT141 and track tension of the shovel EX01."""
    prm, st = m.prm, m.store
    out: list[Trouble] = []
    cu_run = sum(m._line_cu(n) for n in LINES if running[n])
    # ---- brake: oil temperature of the brakes; the alert comes after the limit is held (a threshold with a time delay)
    temp = st.f("fleet", "brake_oil_c")
    if temp != NO_VALUE and temp > 0.0:
        held = st.mean("fleet", "brake_oil_c", t, prm["wt_brake_hold_min"])
        if held != NO_VALUE and held >= prm["wt_brake_oil_alert_c"]:
            key = "fleet:brake"
            to_fail = max(0.0, prm["wt_brake_fail_h"] - _age_h(m, key, t))
            haul, total, need = st.f("fleet", "haul_tph"), st.f("fleet", "trucks_total"), st.f("site", "tph")
            rate, buf, price = 0.0, 48.0, ""
            if haul != NO_VALUE and total != NO_VALUE and total > 0.0 and need != NO_VALUE and need > 0.0:
                deficit = max(0.0, need - (haul - haul / total))
                rate = cu_run * deficit / need if cu_run > 0.0 else 0.0
                buf = tiers._stock_buffer_h(m, running, deficit)
                price = (f"; без этого самосвала откатка даёт {num(haul - haul / total, 0)} т/ч при потребности "
                         f"{num(need, 0)} ({cu_tph(-rate)} после выработки склада ≈ {dur(buf)}) {EST}" if deficit > 0.0 else
                         f"; без этого самосвала откатки хватает — потери меди не ожидаем {EST}")
            out.append(m._tr(key, "fleet", "brake_hot", rate, to_fail + buf, "rep_brake_h", t, loud=False, safety="S0",
                             text=(f"перегрев масла тормозов самосвала HT141 (CAT 793D, "
                                   f"236 т): {num(held, 0)} °C держится {dur(prm['wt_brake_hold_min'] / 60.0)} при пороге "
                                   f"{num(prm['wt_brake_oil_alert_c'], 0)} °C {ASSUME} (порог с выдержкой времени — принцип "
                                   f"системы событий изготовителя, чисел из неё не берём; сигнал на 793F — VIMS, "
                                   f"аналог {ANALOG}); безопасность водителя идёт впереди денег; если не остановить, снимем машину с рейса через ≈ {dur(to_fail)}"
                                   + price + "; сменный механик: остановить, проверить тормоза и охлаждение, горный диспетчер "
                                             "перераспределяет рейсы")))
    # ---- track: pressure of the track tension of the EX3600 (travel stops automatically at a preset pressure)
    pr = st.f("exc-1", "track_press_pct")
    if pr != NO_VALUE and pr >= prm["wt_track_press_alert_pct"] and st.s("exc-1", "state") != "DOWN":
        key = "exc-1:track"
        to_fail = max(0.0, prm["wt_track_fail_h"] - _age_h(m, key, t))
        ready = sum(1 for e in tiers.ORE_EXC if st.get(e) is not None and st.s(e, "state") != "DOWN")
        deficit, need = tiers._ore_capacity(m, running, max(0, ready - 1))
        buf = tiers._stock_buffer_h(m, running, deficit)
        rate = cu_run * deficit / need if need > 0.0 and cu_run > 0.0 else 0.0
        out.append(m._tr(key, "exc-1", "track_tension", rate, to_fail + buf, "rep_track_h", t, loud=False,
                         text=(f"давление натяжения гусениц экскаватора EX01 {num(pr, 0)} % от уровня автостопа при пороге "
                               f"{num(prm['wt_track_press_alert_pct'], 0)} % {ASSUME}; на EX3600-6 ход останавливается "
                               f"автоматически при заданном давлении аккумуляторов (проспект Hitachi, с. 7; уровень не "
                               f"опубликован); экскаватор не сможет перейти к следующему забою — "
                               f"через ≈ {dur(to_fail)} {ASSUME}, дальше {cu_tph(-rate)} после выработки склада "
                               f"({dur(buf)}) {EST}; сменный механик: ослабить и выставить натяжение")))
    return out
