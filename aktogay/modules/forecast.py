"""Forecasts of akt-priority (features 10, 11, 13 of 23.10.2026): ore on the stockpile if the pit stops (the chain
pit -> haul -> crusher -> belt -> stockpile -> SAG), the SAG liner campaign, copper to the end of the shift and day.

Nothing here reads anything but the Store (Ditto / InfluxDB history kept by the module) and the parameter table. Every
number is a model estimate [оценка на модели]; forecasts are shown dashed with "≈" in the interface (UI rules, item 8).

- Stockpile (feature 11, M2): ore that is already on its way (haul, crusher pocket, belt) still arrives, so the SAG
  starves after (level + ore in transit) / SAG draw. The PEK (p. 10) gives the working volume 163 kt = 2 days of
  grinding [проект]; the model keeps only the live part of it, the rest is dead stock [допущение].
- Liner (feature 10): campaign share x = ore ground since the reline (sag.liner_ground_t, a tonnage counter by norm)
  over liner_life_mt; capacity multiplier eta(x) is the piecewise Powell form of the model (direction from the
  literature, numbers ours).
- Copper (feature 13): the rate is the mean of the last hour, the corridor is mean +- z sd of the 5-minute rate over
  3 h on the low side and "all open troubles fixed now" on the high side; the interface adds the copper already made
  in the shift and the day (counters of Ditto / InfluxDB).
"""
from __future__ import annotations

from .lever_advice import liner_feed
from .store import NO_VALUE, Store
from .text import ASSUME, EST, hhmm_day, num

LINES = (1, 2)
T_PER_MT = 1.0e6
MIN_PER_H = 60.0
MIN_PER_DAY = 1440.0
H_PER_DAY = 24.0


def eta(x: float, prm) -> float:
    """Capacity multiplier of the liner campaign share x (same piecewise form as sim/comminution.liner_eta)."""
    pts = ((0.0, prm["liner_eta_new"]), (prm["liner_x_ramp"], 1.0), (prm["liner_x_peak"], prm["liner_eta_peak"]),
           (1.0, prm["liner_eta_end"]))
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y1 if x1 <= x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def eta_curve(prm, n: int = 21) -> list[list[float]]:
    """[[x, eta], ...] for the liner chart of the interface."""
    return [[round(i / (n - 1), 4), round(eta(i / (n - 1), prm), 4)] for i in range(n)]


def stock(store: Store, prm, t: float) -> dict:
    """Hours of ore on the stockpile of each line if the pit stopped now, and the pit-to-SAG chain of times."""
    pit_state = store.s("pit", "state")
    ore_exc = [store.s(e, "state") for e in ("exc-1", "exc-2", "exc-3") if store.get(e) is not None]
    stopped = bool(ore_exc) and all(s == "DOWN" for s in ore_exc)
    lag_min = prm["pit_haul_min"] + prm["conv_travel_min"]
    lines: dict[str, dict] = {}
    for n in LINES:
        level = store.f(f"stockpile-{n}", "level_t")
        out = store.f(f"stockpile-{n}", "out_tph")
        inflow = store.f(f"crusher-{n}", "tph")
        if out == NO_VALUE or out <= 0.0:
            out = store.f(f"sag-{n}", "feed_tph")
        if level == NO_VALUE:
            continue
        transit = max(0.0, inflow if inflow != NO_VALUE else 0.0) * lag_min / MIN_PER_H
        running = out != NO_VALUE and out > 0.0
        hours = (level + transit) / out if running else NO_VALUE
        lines[str(n)] = {
            "level_t": level, "out_tph": out if running else NO_VALUE, "transit_t": transit,
            "hours": hours, "run_out_at": t + hours * MIN_PER_H if hours != NO_VALUE else NO_VALUE,
            "state": store.s(f"stockpile-{n}", "state"),
            "live_pct": 100.0 * level / prm["stock_live_t"] if prm["stock_live_t"] > 0.0 else NO_VALUE,
            "pek_hours": prm["stock_pek_days"] * H_PER_DAY,
        }
    return {"pit_state": pit_state, "pit_stopped": stopped, "lag_min": lag_min, "lines": lines,
            "stages": [{"stage": "карьер → дробилка (откатка)", "min": prm["pit_haul_min"]},
                       {"stage": "дробилка → склад (лента)", "min": prm["conv_travel_min"]}]}


def stock_text(f: dict, t: float) -> str:
    parts = []
    for n in LINES:
        r = f["lines"].get(str(n))
        if r is None:
            continue
        if r["hours"] == NO_VALUE:
            parts.append(f"линия {n}: SAG стоит, склад {num(r['level_t'], 0)} т")
        else:
            parts.append(f"линия {n}: ≈ {num(r['hours'], 1)} ч (до {hhmm_day(r['run_out_at'], t)})")
    if not parts:
        return ""
    head = ("Карьер стоит — склад держит фабрику: " if f["pit_stopped"] else
            "Если карьер встанет сейчас, руды на складе хватит: ")
    return (head + "; ".join(parts) + f" {EST}. Откатка и лента ещё довезут руду (≈ {num(f['lag_min'], 0)} мин). "
            "По ПЭК рабочий объём склада 163 кт = 2 суток измельчения [проект]; в модели живая часть склада "
            f"40 кт {ASSUME}.")


def liner(store: Store, prm, t: float) -> dict:
    """Liner campaign of each SAG: share used, capacity multiplier now / at the peak / at the end, days to the end."""
    out: dict[str, dict] = {}
    life_t = prm["liner_life_mt"] * T_PER_MT
    for n in LINES:
        ground = store.f(f"sag-{n}", "liner_ground_t")
        if ground == NO_VALUE:
            continue
        q = store.f(f"sag-{n}", "feed_tph")
        q = q if q != NO_VALUE and q > 0.0 else prm["line_tph_base"]
        x = min(1.0, ground / life_t)
        per_day = q * H_PER_DAY * prm["fc_avail"]
        days_end = max(0.0, (life_t - ground) / per_day)
        x_peak = prm["liner_x_peak"]
        days_peak = max(0.0, (x_peak * life_t - ground) / per_day) if x < x_peak else NO_VALUE
        e_now, e_peak, e_end = eta(x, prm), prm["liner_eta_peak"], prm["liner_eta_end"]
        cu = store.f(f"line-{n}", "cu_tph")
        cu = cu if cu != NO_VALUE and cu > 0.0 else NO_VALUE
        out[str(n)] = {
            "ground_mt": ground / T_PER_MT, "life_mt": prm["liner_life_mt"], "share": x,
            "eta_now": e_now, "eta_peak": e_peak, "eta_end": e_end,
            "tph_now": q, "tph_end": q * e_end / e_now if e_now > 0.0 else NO_VALUE,
            "drop_from_peak_pct": 100.0 * (e_end / e_peak - 1.0),
            "days_to_end": days_end, "end_at": t + days_end * MIN_PER_DAY,
            "days_to_peak": days_peak,
            "reline_h": prm["liner_reline_h"],
            "reline_cu_t": cu * prm["liner_reline_h"] if cu != NO_VALUE else NO_VALUE,
            "wear_mm": store.f(f"sag-{n}", "liner_wear_mm"),
            "lever": liner_feed(n, e_now, e_peak, prm),
        }
    return {"lines": out, "curve": eta_curve(prm), "x_peak": prm["liner_x_peak"], "x_ramp": prm["liner_x_ramp"]}


def liner_text(f: dict, t: float) -> str:
    parts = []
    for n in LINES:
        r = f["lines"].get(str(n))
        if r is None:
            continue
        parts.append(f"SAG-{n}: наработка {num(r['ground_mt'], 1)} из {num(r['life_mt'], 0)} Мт, перефутеровку "
                     f"планировать через ≈ {num(r['days_to_end'], 0)} сут, к концу кампании т/ч "
                     f"{num(r['drop_from_peak_pct'], 1)} % от пика")
    if not parts:
        return ""
    return ("; ".join(parts) + f" {EST}. Длина кампании 30 Мт {ASSUME} (10–18 мес.); факт: перефутеровки SAG в IV кв. 2023 "
            "на обеих линиях и в III кв. 2025 на линии 2 (отчёты KAZ Minerals).")


def copper(store: Store, prm, t: float, open_loss_cu_tph: float) -> dict:
    """Rate of copper in concentrate, its corridor and the hours to the end of the shift and of the day."""
    win = store.window("site", "cu_tph", t, prm["fc_sigma_window_min"])
    short = store.window("site", "cu_tph", t, prm["fc_rate_window_min"])
    if len(short) < 3:
        cur = store.f("site", "cu_tph")
        if cur == NO_VALUE:
            return {}
        mean, sd = cur, 0.0
    else:
        mean = sum(v for _t, v in short) / len(short)
        vals = [v for _t, v in win] or [mean]
        m2 = sum(vals) / len(vals)
        sd = (sum((v - m2) ** 2 for v in vals) / max(1, len(vals) - 1)) ** 0.5
    z = prm["fc_z"]
    plan_rate = prm["plan_cu_day_t"] / H_PER_DAY
    lo = max(0.0, mean - z * sd)
    hi = mean + max(0.0, open_loss_cu_tph)
    shift_len = prm["shift_h"] * MIN_PER_H
    start = prm["shift_start_h"] * MIN_PER_H
    into = (t - start) % shift_len
    h_shift = (shift_len - into) / MIN_PER_H
    h_day = (MIN_PER_DAY - ((t - start) % MIN_PER_DAY)) / MIN_PER_H
    return {"rate_tph": mean, "rate_lo_tph": lo, "rate_hi_tph": max(hi, mean), "sd_tph": sd,
            "open_loss_cu_tph": max(0.0, open_loss_cu_tph), "plan_rate_tph": plan_rate,
            "plan_day_t": prm["plan_cu_day_t"], "plan_shift_t": prm["plan_cu_day_t"] * prm["shift_h"] / H_PER_DAY,
            "h_shift": h_shift, "h_day": h_day, "shift_end_at": t + h_shift * MIN_PER_H, "day_end_at": t + h_day * MIN_PER_H,
            "z": z}


def copper_text(f: dict, t: float) -> str:
    if not f:
        return ""
    rem = f["rate_tph"] * f["h_shift"]
    lo, hi = f["rate_lo_tph"] * f["h_shift"], f["rate_hi_tph"] * f["h_shift"]
    return (f"До конца смены ещё ≈ {num(rem, 0)} т Cu (коридор {num(lo, 0)}–{num(hi, 0)}) при темпе "
            f"{num(f['rate_tph'], 1)} т/ч {EST}; низ — разброс темпа за 3 ч, верх — если закрыть сейчас беды, которые уже теряют медь. "
            f"Ориентир — средние сутки 2025 г.: {num(f['plan_day_t'], 0)} т Cu (факт KAZ Minerals, расчёт).")


def build(store: Store, prm, t: float, open_loss_cu_tph: float) -> dict:
    """The forecast object of mod-priority.forecast and the texts."""
    st = stock(store, prm, t)
    ln = liner(store, prm, t)
    cu = copper(store, prm, t, open_loss_cu_tph)
    return {"t": t, "stock": st, "liner": ln, "copper": cu,
            "texts": {"stock": stock_text(st, t), "liner": liner_text(ln, t), "copper": copper_text(cu, t)}}
