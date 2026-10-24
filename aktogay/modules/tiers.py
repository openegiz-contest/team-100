"""Troubles of tier S (decision of 23.10.2026) for akt-priority: winter road and tired driver in the pit, cyclone roping with ball
mill overload, pH sensor under suspicion, uneven feed of the line 2 HPGR, mantle change of the primary crusher, oil contamination
and failure of an excavator, and the evidence list with the age of every measurement for the trouble card.

Nothing here reads anything but the Store (Ditto / InfluxDB) and the parameter table. Every trouble is built by the same rules:
signal, threshold (a parameter of the site), price (t Cu/h and USD/h, model estimate), who is called, what to do and when it
is closed - the nine points of the readiness card (modules/readiness.py). Where a source names the risk but not the threshold,
the threshold is an assumption and the text says so.
"""
from __future__ import annotations

from . import expect as ex
from .policy import Trouble
from .store import NO_VALUE
from .text import ANALOG, ASSUME, EST, cu_tph, dur, num

LINES = (1, 2)
ORE_EXC = ("exc-1", "exc-2", "exc-3")

# Where a signal can be seen (sensor verification of 23.10.2026, facts_round2): one wording for the whole stand.
W_MACHINE = "на машине (видит водитель / оператор)"
W_SENT = "передаётся, если подключена опция"
W_ANALOG = "аналог другой модели"
W_DCS = "АСУ ТП фабрики (DCS)"
W_HEX = "диспетчерская система карьера (Hexagon)"
W_LAB = "ручная проба / лаборатория"
W_MODEL = "расчёт модели"


# ---------------------------------------------------------------------------
# Pit
# ---------------------------------------------------------------------------
def _ore_capacity(m, running: dict[int, bool], ready: int) -> tuple[float, float]:
    """(deficit t/h, need t/h): what the running lines need from the pit and what the ore excavators that work cannot give."""
    prm = m.prm
    need = prm["line_tph_base"] * sum(1 for n in LINES if running[n])
    return max(0.0, need - prm["pit_exc_max_tph"] * ready), need


def _stock_buffer_h(m, running: dict[int, bool], deficit: float) -> float:
    """Hours the stockpiles of the running lines cover the deficit of the pit."""
    if deficit <= 0.0:
        return 48.0
    level = sum(max(0.0, m.store.f(f"stockpile-{n}", "level_t")) for n in LINES if running[n])
    return min(48.0, level / deficit)


def pit_troubles(m, t: float, running: dict[int, bool]) -> list[Trouble]:
    """Winter road (S0), tired driver (S0, assumption), oil contamination and failure of an ore excavator."""
    prm, st = m.prm, m.store
    out: list[Trouble] = []
    # ---- T1 winter road: ice, snowstorm, visibility (T-K4: KAZ Minerals names the risk at Aktogay; thresholds are ours)
    vis, grip = st.f("pit", "visibility_m"), st.f("pit", "road_grip")
    restrict = st.f("pit", "road_restrict") == 1.0
    low_vis = vis != NO_VALUE and vis <= prm["pit_vis_min_m"]
    low_grip = grip != NO_VALUE and grip <= prm["pit_grip_min"]
    if (low_vis or low_grip) and not restrict:
        wind, temp = st.f("water", "wind_ms"), st.f("water", "air_temp_c")
        haul, need = st.f("fleet", "haul_tph"), st.f("site", "tph")
        cu_run = sum(m._line_cu(n) for n in LINES if running[n])
        price = ""
        if haul != NO_VALUE and need != NO_VALUE and need > 0.0:
            short = max(0.0, 1.0 - haul / prm["pit_restrict_cycle_mult"] / need)
            price = (f"; цена решения: откатка станет медленнее ещё в {num(prm['pit_restrict_cycle_mult'], 2)} раза "
                     f"{ASSUME}, недодача руды ≈ {num(100 * short, 0)} % ({cu_tph(-cu_run * short)} после выработки склада) "
                     f"{EST} — безопасность людей идёт впереди денег")
        why = []
        if low_vis:
            why.append(f"видимость {num(vis, 0)} м (порог {num(prm['pit_vis_min_m'], 0)} м {ASSUME})")
        if low_grip:
            why.append(f"сцепление {num(grip, 2)} (порог {num(prm['pit_grip_min'], 2)} {ASSUME})")
        out.append(m._tr("pit:road_winter", "pit", "road_winter", 0.0, 0.0, "", t, safety="S0",
                         text=("зимняя дорога в карьере: " + ", ".join(why)
                               + (f", ветер {num(wind, 0)} м/с" if wind != NO_VALUE else "")
                               + (f", воздух {num(temp, 0)} °C" if temp != NO_VALUE else "")
                               + "; KAZ Minerals называет метели и сильный ветер риском ДТП на Актогае; решение — ограничить "
                                 "движение: горный диспетчер → начальник смены карьера → дорожная служба" + price)))
    # ---- T1 tired driver / close approach: only a scenario, the sensor and its source are not confirmed
    if st.f("fleet", "fatigue") == 1.0:
        truck = st.s("fleet", "fatigue_truck") or "самосвал"
        out.append(m._tr("fleet:fatigue", "fleet", "driver_fatigue", 0.0, 0.0, "", t, safety="S0",
                         text=(f"тревога усталости водителя / сближения техники: {truck} {ASSUME} (источник датчика в "
                               f"открытых данных не подтверждён — сценарий); снять машину с рейса, развести технику, "
                               f"заменить водителя: горный диспетчер → начальник смены карьера")))
    # ---- excavators: oil contamination (EX3600-6 sensor) before the failure, failure after it
    ready = sum(1 for e in ORE_EXC if st.get(e) is not None and st.s(e, "state") != "DOWN")
    total = sum(1 for e in ORE_EXC if st.get(e) is not None)
    cu_run = sum(m._line_cu(n) for n in LINES if running[n])
    for e in ORE_EXC:
        if st.get(e) is None:
            continue
        state = st.s(e, "state")
        if state == "DOWN":
            if ready <= 0:
                continue                                  # every excavator stands: the pit-stop trouble owns it
            deficit, need = _ore_capacity(m, running, ready)
            if deficit <= 0.0 or cu_run <= 0.0:
                continue
            buf = _stock_buffer_h(m, running, deficit)
            rate = cu_run * deficit / need
            out.append(m._tr(f"{e}:down", e, "exc_down", rate, buf, "rep_exc_h", t,
                             text=(f"отказ экскаватора: остальные {ready} из {total} дают "
                                   f"{num(prm['pit_exc_max_tph'] * ready, 0)} т/ч при потребности {num(need, 0)}; склад "
                                   f"покрывает недостачу ≈ {dur(buf)}, дальше {cu_tph(-rate)} {EST}; ремонт гидросистемы "
                                   f"≈ {num(prm['rep_exc_h'], 0)} ч (PC3000, не EX3600 {ANALOG}); "
                                   f"перебросить забой на другой экскаватор, вызвать сменного механика")))
            continue
        if st.f(e, "oil_alert") == 1.0:
            deficit, need = _ore_capacity(m, running, max(0, ready - 1))
            if deficit <= 0.0 or cu_run <= 0.0:
                continue
            key = f"{e}:oil"
            age_h = max(0.0, (t - m.first_seen.setdefault(key, t)) / 60.0)
            to_fail = max(0.0, prm["oil_fail_h"] - age_h)
            buf = _stock_buffer_h(m, running, deficit)
            rate = cu_run * deficit / need
            pct = st.f(e, "oil_pct")
            out.append(m._tr(key, e, "oil_contam", rate, to_fail + buf, "rep_oil_h", t,
                             text=(f"загрязнение гидромасла: {num(pct, 0)} % от уровня тревоги датчика на "
                                   f"машине (оператор видит её сам; в диспетчерскую она идёт, если подключена опция Global "
                                   f"e-Service); около 70 % отказов гидросистем — загрязнение рабочей жидкости {ANALOG}; "
                                   f"отказ насоса ≈ через {dur(to_fail)} {ASSUME}, после него и выработки склада "
                                   f"({dur(buf)}) {cu_tph(-rate)} {EST}; вызвать сменного механика: фильтрация, промывка")))
    return out


# ---------------------------------------------------------------------------
# Plant
# ---------------------------------------------------------------------------
def _grade(m, n: int, t: float) -> float:
    g = m.store.mean(f"flot-{n}", "feed_cu", t, m.prm["window_min"])
    return g if g != NO_VALUE and g > 0.0 else m.prm["flot_grade_ref_pct"]


def line_troubles(m, n: int, running_n: bool, sag_down: bool, t: float) -> list[Trouble]:
    """Cyclone roping with ball mill overload, pH sensor under suspicion, uneven feed of the HPGR (line 2)."""
    prm, st = m.prm, m.store
    out: list[Trouble] = []
    if not running_n or sag_down:
        return out
    q = st.f(f"sag-{n}", "feed_tph")
    grade = _grade(m, n, t)
    # ---- T2 cyclone roping and ball mill overload (T-F2 Kennecott; C13 Centinela)
    cy = f"cyclones-{n}"
    circ = st.mean(cy, "circ_load_pct", t, 15.0)
    balls = [b for b in (f"ball-{n}a", f"ball-{n}b") if st.s(b, "state") == "RUN"]
    over = max((st.f(b, "power_pct") for b in balls), default=NO_VALUE)
    p80 = st.mean(cy, "p80_um", t, prm["window_min"])
    coarse = p80 != NO_VALUE and p80 - prm["p80_ref_um"] > prm["p80_alarm_um"]
    if (q > 0.0 and circ != NO_VALUE and circ >= prm["rope_circ_alarm_pct"]
            and ((over != NO_VALUE and over >= prm["ball_overload_pct"]) or coarse)):
        key = f"{cy}:rope"
        age_h = max(0.0, (t - m.first_seen.setdefault(key, t)) / 60.0)
        pp = prm["flot_p80_pp_10um"] * max(0.0, p80 - prm["p80_ref_um"]) / 10.0 if p80 != NO_VALUE else 0.0
        esc = age_h >= prm["rope_escalate_h"]
        if esc:
            pp += prm["rope_flot_pp"]
        rate = ex.cu_tph(q, grade, pp)
        left = max(0.0, prm["rope_escalate_h"] - age_h)
        out.append(m._tr(key, cy, "roping", rate, 0.0, "rep_rope_h", t, loud=False,
                         text=(f"канатирование и перегрузка шаровой: циркулирующая нагрузка "
                               f"{num(circ, 0)} % (порог {num(prm['rope_circ_alarm_pct'], 0)} % {ASSUME}), нагрузка шаровой "
                               f"{num(over, 0) if over != NO_VALUE else '—'} % от номинала, P80 "
                               f"{num(p80, 0) if p80 != NO_VALUE else '—'} мкм; извлечение ниже на ≈ {num(pp, 1)} п.п. "
                               f"({cu_tph(-rate)}) {EST}; "
                               + (f"тяжёлое канатирование уже {dur(age_h)}: флотация теряет ещё "
                                  f"{num(prm['rope_flot_pp'], 0)} п.п. (на Centinela одна нитка рафинёрной флотации стояла "
                                  f"≈ {num(prm['rope_flot_h'], 0)} ч {ANALOG}); " if esc else
                                  f"если не решить за {dur(left)}, флотация потеряет ещё {num(prm['rope_flot_pp'], 0)} п.п. "
                                  f"{ASSUME}; ")
                               + "оператор помола снижает подачу и открывает циклоны, металлург проверяет режим")))
    # ---- T3 pH sensor under suspicion: the grab sample against the online reading (T-T1: scale and abrasion)
    ph = f"ph-{n}"
    lab, sp = st.f(ph, "lab_ph"), st.f(ph, "sp_ph")
    reading = st.mean(ph, "ph", t, 60.0)
    if lab != NO_VALUE and reading != NO_VALUE and abs(lab - reading) >= prm["ph_gap_alarm"] and sp != NO_VALUE:
        off = abs(lab - sp)
        pp = prm["ph_pp_unit"] * off
        rate = ex.cu_tph(q, grade, pp)
        age = st.f(ph, "age_min")
        out.append(m._tr(f"{ph}:suspect", ph, "sensor_ph", rate, 0.0, "rep_ph_h", t, loud=False,
                         text=(f"под подозрением: онлайн-показание {num(reading, 2)} (держится на уставке "
                               f"{num(sp, 1)}), ручная проба {num(lab, 2)} {('— ' + dur(age / 60.0) + ' назад') if age != NO_VALUE else ''}; "
                               f"расхождение {num(abs(lab - reading), 2)} при пороге {num(prm['ph_gap_alarm'], 2)} {ASSUME}; "
                               f"электрод в накипи извести или изношен (требование вендора ABB), регулятор извести идёт за "
                               f"ложным показанием: реальный pH выше уставки ≈ на {num(off, 1)}, извлечение ниже на "
                               f"≈ {num(pp, 1)} п.п. ({cu_tph(-rate)}) {EST}; дежурный КИПиА чистит и поверяет электрод, "
                               f"металлург подтверждает пробой")))
    # ---- T4 uneven feed of the HPGR (line 2; analog: Metso on feed segregation, tramp metal)
    pb = f"pebble-{n}"
    if st.f(pb, "hpgr_tph") > 0.0:
        skew, kwd = st.f(pb, "hpgr_skew_pct"), st.f(pb, "hpgr_kw_diff_pct")
        metal = st.f(pb, "metal_alarm") == 1.0
        if metal or (skew != NO_VALUE and skew >= prm["hpgr_skew_alarm_pct"]) or (
                kwd != NO_VALUE and kwd >= prm["hpgr_kwdiff_alarm_pct"]):
            limit = st.f(pb, "limit_tph")
            if metal:
                loss_tph = prm["line_tph_base"] * prm["pebble_stop_loss_frac"]
            else:
                loss_tph = max(0.0, prm["line_tph_base"] - (limit if limit > 0.0 else prm["hpgr_limit_nominal_tph"])
                               / prm["peb_frac_base"])
            rate = ex.cu_tph(loss_tph, grade, prm["flot_rec_ref_pct"])
            key = f"{pb}:uneven"
            age_h = max(0.0, (t - m.first_seen.setdefault(key, t)) / 60.0)
            out.append(m._tr(key, pb, "hpgr_uneven", rate, 0.0, "rep_hpgr_h", t, loud=False,
                             text=(("металлодетектор перед ВВД сработал, пресс остановлен: осмотр шпилек и валков, "
                                    if metal else
                                    f"неравномерное питание ВВД линии 2: перекос зазора валков {num(skew, 0)} % (порог "
                                    f"{num(prm['hpgr_skew_alarm_pct'], 0)} % {ASSUME}), разница мощности двух приводов "
                                    f"{num(kwd, 0)} %, предел круга гали {num(limit, 0)} т/ч; ")
                                   + f"потеря ≈ {num(loss_tph, 0)} т/ч SAG ({cu_tph(-rate)}) {EST}; причина — сегрегация "
                                     f"питания по крупности; чужеродный металл пресс «не чувствует» по давлению, нужен "
                                     f"металлодетектор (Metso, 2022 {ANALOG}); "
                                   + ("" if metal else f"неустранённое неравномерное питание {dur(age_h)} — через "
                                                       f"{num(prm['hpgr_tramp_after_h'], 1)} ч возможен металл в валках {ASSUME}; ")
                                   + "механик фабрики с бригадой: загрузочный желоб, боковые щёки")))
    return out


def crusher_mantle(m, n: int, stock_h: float, t: float) -> Trouble | None:
    """Planned mantle change of the primary crusher (C11): the crusher stands about 60 h, the stockpile carries the SAG."""
    prm, st = m.prm, m.store
    cr = f"crusher-{n}"
    if st.s(cr, "state") != "STOP" or st.f(cr, "service") != 1.0:
        return None
    left = st.f(cr, "service_left_h")
    cap = prm["crush_cap_tph"]
    h = prm["rep_mantle_h"]
    own = cap * h / 1000.0
    cu = m._line_cu(n)
    return m._tr(f"{cr}:mantle", cr, "crusher_mantle", cu, stock_h, "rep_mantle_h", t,
                 text=(f"плановая замена брони дробилки {n}: дробилка стоит, до конца ≈ "
                       f"{dur(left) if left != NO_VALUE else '—'}; склад линии кормит SAG ≈ {dur(stock_h)}, дальше линия "
                       f"встанет ({cu_tph(-cu)}) {EST}; за {num(h, 0)} ч не раздроблено бы ≈ {num(own, 0)} кт руды по "
                       f"паспорту дробилки (Metso, La Caridad: ≈ {num(prm['mantle_ref_kt_lo'], 0)}–"
                       f"{num(prm['mantle_ref_kt_hi'], 0)} кт за ≈ {num(h, 0)} ч — другой рудник {ANALOG}); работа "
                       f"внутри дробилки — по наряду-допуску; перед остановкой заполнить склад"))


# ---------------------------------------------------------------------------
# Evidence: every measurement of a trouble card with the age of its data (T3)
# ---------------------------------------------------------------------------
# (label, thing, feature, unit, digits, where)
EVIDENCE: dict[str, list[tuple]] = {
    "road_winter": [("видимость на откатке", "pit", "visibility_m", "м", 0, "метеопост / дорожный пост [допущение]"),
                    ("сцепление (индекс 0…1)", "pit", "road_grip", "", 2, "оценка по циклам самосвалов [допущение]"),
                    ("ветер", "water", "wind_ms", "м/с", 0, "метеопост"),
                    ("воздух", "water", "air_temp_c", "°C", 0, "метеопост"),
                    ("скорость откатки к сухой дороге", "pit", "haul_speed_pct", "%", 0, W_HEX)],
    "driver_fatigue": [("тревога усталости / сближения", "fleet", "fatigue", "", 0, "датчик в кабине — допущение"),
                       ("самосвалов на ходу", "fleet", "trucks_ready", "шт.", 0, W_HEX)],
    "roping": [("циркулирующая нагрузка", "cyclones-{n}", "circ_load_pct", "%", 0, W_DCS + " (расчёт по расходам и плотности)"),
               ("давление питания циклонов", "cyclones-{n}", "pressure_kpa", "кПа", 0, W_DCS),
               ("P80 перелива", "cyclones-{n}", "p80_um", "мкм", 0, "анализатор крупности"),
               ("нагрузка шаровой 1", "ball-{n}a", "power_pct", "%", 0, W_DCS),
               ("нагрузка шаровой 2", "ball-{n}b", "power_pct", "%", 0, W_DCS),
               ("извлечение по линии", "flot-{n}", "recovery", "%", 1, "поточный анализатор (цикл 12–16 мин)")],
    "sensor_ph": [("pH онлайн", "ph-{n}", "ph", "pH", 2, "онлайн-электрод"),
                  ("pH ручная проба", "ph-{n}", "lab_ph", "pH", 2, W_LAB),
                  ("уставка pH", "ph-{n}", "sp_ph", "pH", 1, W_DCS),
                  ("извлечение по линии", "flot-{n}", "recovery", "%", 1, "поточный анализатор (цикл 12–16 мин)")],
    "hpgr_uneven": [("перекос зазора валков", "pebble-{n}", "hpgr_skew_pct", "%", 0, "датчики положения валков"),
                    ("разница мощности приводов", "pebble-{n}", "hpgr_kw_diff_pct", "%", 0, W_DCS),
                    ("металлодетектор", "pebble-{n}", "metal_alarm", "", 0, "металлодетектор на питании [допущение]"),
                    ("предел круга гали", "pebble-{n}", "limit_tph", "т/ч", 0, W_DCS),
                    ("питание SAG", "sag-{n}", "feed_tph", "т/ч", 0, "конвейерные весы")],
    "crusher_mantle": [("состояние дробилки", "crusher-{n}", "state", "", 0, W_DCS),
                       ("до конца замены", "crusher-{n}", "service_left_h", "ч", 1, "план работ"),
                       ("запас склада", "stockpile-{n}", "level_t", "т", 0, "расчёт по весам [допущение]")],
    "oil_contam": [("загрязнение масла", "{node}", "oil_pct", "%", 0, W_MACHINE + "; " + W_SENT),
                   ("тревога датчика", "{node}", "oil_alert", "", 0, W_MACHINE + "; " + W_SENT),
                   ("копает", "{node}", "tph", "т/ч", 0, W_HEX)],
    "exc_down": [("состояние", "{node}", "state", "", 0, W_HEX),
                 ("добыча карьера", "pit", "mining_tph", "т/ч", 0, W_HEX)],
}
# generic evidence by thing type for the older troubles: (label, feature, unit, digits)
BY_TYPE: dict[str, list[tuple]] = {
    "crusher": [("производительность", "tph", "т/ч", 0), ("давление масла", "lube_kpa", "кПа", 0)],
    "conveyor": [("производительность", "tph", "т/ч", 0), ("сигнал защиты", "fault", "", 0)],
    "stockpile": [("запас", "level_t", "т", 0), ("часов запаса", "hours_left", "ч", 1)],
    "sag": [("питание", "feed_tph", "т/ч", 0), ("мощность", "power_kw", "кВт", 0), ("кВт·ч/т", "e_kwh_t", "", 2)],
    "pebble": [("нагрузка круга гали", "load_pct", "%", 0)],
    "ball": [("мощность", "power_kw", "кВт", 0)],
    "cyclones": [("P80 перелива", "p80_um", "мкм", 0), ("давление", "pressure_kpa", "кПа", 0)],
    "flot": [("извлечение", "recovery", "%", 1), ("хвосты", "tail_cu", "% Cu", 3), ("питание", "feed_cu", "% Cu", 3)],
    "rougher": [("доза собирателя", "dose_meas_gt", "г/т", 1)],
    "thick": [("запас", "inventory_t", "т", 0), ("часов до полного", "hours_to_full", "ч", 1)],
    "filter": [("прессов", "presses_on", "шт.", 0), ("производительность", "cake_tph", "т/ч", 0)],
    "conc-stock": [("запас", "stock_t", "т", 0), ("часов до полного", "hours_to_full", "ч", 1)],
    "water": [("пруд", "pond_m3", "м³", 0), ("невязка", "residual_pct", "%", 1), ("пьезометр", "piezo_kpa", "кПа", 0)],
    "power": [("лимит сети", "grid_limit_mw", "МВт", 0), ("нагрузка", "site_mw", "МВт", 0)],
    "pit": [("добыча", "mining_tph", "т/ч", 0)],
    "fleet": [("самосвалов на ходу", "trucks_ready", "шт.", 0), ("вывоз", "haul_tph", "т/ч", 0)],
    "person": [("состояние", "state", "", 0)],
}
# Features whose measurement is older than the publication: the analyser (cycle 12-16 min) and the grab sample of pH publish the age
# of the sample itself; the grades and the recovery of the flotation thing are the analyser's readings.
AN_FEATURES = ("feed_cu", "tail_cu", "conc_cu", "recovery", "cu_tph", "conc_tph")


def _fmt(v, digits: int) -> str:
    if v == NO_VALUE or v is None:
        return "нет данных"
    return num(float(v), digits)


def evidence(m, tr: Trouble, t: float, suspects: dict | None = None) -> dict:
    """Measurements behind a trouble: value, unit, where it is seen, and the age of the data.

    age_pub_min: model minutes since the thing was published to Ditto (what the screen shows is this old);
    age_meas_min: age of the sample itself where the instrument has a cycle (analyser, grab sample), else -1;
    suspect: the instrument is doubted (state SUSPECT or DRIFT, or the data are older than the limit)."""
    st, prm = m.store, m.prm
    suspects = suspects or {}
    try:
        n = int(tr.node.rpartition("-")[2][:1])
    except ValueError:
        n = 0
    spec = EVIDENCE.get(tr.kind)
    rows: list[tuple] = []
    if spec is not None:
        for label, thing, feat, unit, dig, where in spec:
            rows.append((label, thing.format(n=n, node=tr.node), feat, unit, dig, where))
    else:
        snap = st.get(tr.node)
        typ = snap.type if snap is not None else ""
        where = W_HEX if typ in ("pit", "fleet", "exc", "truck", "person") else W_DCS
        rows.append(("состояние узла", tr.node, "state_ru", "", 0, where))
        for label, feat, unit, dig in BY_TYPE.get(typ, ()):
            rows.append((label, tr.node, feat, unit, dig, where))
    items = []
    stale = prm["age_stale_dcs_min"]
    for label, thing, feat, unit, dig, where in rows:
        snap = st.get(thing)
        if snap is None:
            continue
        raw = snap.values.get(feat)
        if isinstance(raw, str):
            text = raw or "—"
            val = NO_VALUE
        else:
            val = snap.f(feat)
            text = _fmt(val, dig)
        pub = (t - snap.sim_time) if snap.sim_time != NO_VALUE else NO_VALUE
        meas = NO_VALUE
        an_state = ""
        if snap.type == "analyzer":
            meas = snap.f("age_min")
        elif snap.type in ("flot", "cleaner") and feat in AN_FEATURES:      # grades and recovery come from the on-stream analyser
            an = st.get("analyzer-" + thing.rpartition("-")[2][:1])
            if an is not None:
                meas, an_state = an.f("age_min"), an.s("state")
        elif snap.type == "phmeter" and feat == "lab_ph":
            meas = snap.f("age_min")
        state = snap.s("state")
        doubted = thing in suspects or state in ("SUSPECT", "DRIFT") or an_state == "SUSPECT"
        if snap.type == "phmeter":                 # the grab sample against the online reading (T-T1): both readings are doubted
            lab, onl = snap.f("lab_ph"), snap.f("ph")
            doubted = feat in ("ph", "lab_ph") and (doubted or (lab != NO_VALUE and onl != NO_VALUE
                                                                 and abs(lab - onl) >= prm["ph_gap_alarm"]))
        old = pub != NO_VALUE and pub > stale
        if meas != NO_VALUE and snap.type == "phmeter" and meas > prm["age_stale_lab_h"] * 60.0:
            old = True
        items.append({"label": label, "thing": thing, "feature": feat, "value": val if val != NO_VALUE else None,
                      "text": text, "unit": unit, "where": where,
                      "age_pub_min": round(pub, 1) if pub != NO_VALUE else None,
                      "age_meas_min": round(meas, 1) if meas != NO_VALUE else None,
                      "suspect": bool(doubted), "old": bool(old)})
    n_susp = sum(1 for i in items if i["suspect"] or i["old"])
    return {"items": items, "n_suspect": n_susp,
            "text": "; ".join(f"{i['label']}: {i['text']}{(' ' + i['unit']) if i['unit'] else ''}"
                              + (f" (данные {num(i['age_pub_min'], 0)} мин назад)" if i["age_pub_min"] is not None else "")
                              + (" — под подозрением" if i["suspect"] else "")
                              for i in items)}
