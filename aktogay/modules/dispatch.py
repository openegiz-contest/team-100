"""Dispatcher helpers of akt-priority: chain of responsibility (main -> deputy -> shift head), work permit,
hourly tariff, price of a choice, review of the shift's calls.

Features 1-4 and 6 of the list of 22.10.2026. Nothing here reads anything but the Store (Ditto / InfluxDB) and the
parameter table; the texts are Russian and every number is a model estimate or carries its label.

- Work permit (nariad-dopusk): MIR RK order no. 348 of 30.12.2014, item 12 (permits for work of raised danger) and
  item 63 (work inside a mill by permit): a person who works inside equipment by a permit cannot be called to
  another place until the work ends. The simulator publishes it as person.permit = the node of the work.
- Chain: the main person of the issue (WHO table), his deputy (responsible.deputy of the person thing, a stand
  assumption) and the shift head (the person with the role plant_shift_manager).
- Tariff: flat 16 KZT/kWh (fact; zonal tariffs of final consumers were abolished in 2018); the night / day / peak
  structure is a what-if scenario (tariff_zones_on = 1), project / assumption.
"""
from __future__ import annotations

from typing import Callable

from .store import NO_VALUE, Store
from .text import ASSUME, EST, hhmm_day, num, usd, signed

HEAD_ROLE = "plant_shift_manager"
BAND_RU = {"night": "ночь", "day": "день", "peak": "пик"}


# ---------------------------------------------------------------------------
# Tariff by the hour (assumption of the structure; the mean is the model's price)
# ---------------------------------------------------------------------------
def _in_band(h: float, a: float, b: float) -> bool:
    return (a <= h < b) if a < b else (h >= a or h < b)


def tariff_band(hour: float, prm) -> str:
    if _in_band(hour, prm["tariff_peak_from_h"], prm["tariff_peak_to_h"]):
        return "peak"
    if _in_band(hour, prm["tariff_night_from_h"], prm["tariff_night_to_h"]):
        return "night"
    return "day"


def zones_on(prm) -> bool:
    """Peak / night structure is a what-if scenario (tariff_zones_on = 1): zonal tariffs of final consumers were
    abolished (order no. 445 of 29.12.2017), so by default the price is flat 16 KZT/kWh all day."""
    return bool(prm["tariff_zones_on"])


def tariff_mult(hour: float, prm) -> float:
    """Price at this hour against the daily mean (the mean over 24 h is exactly 1); 1 all day while zones are off."""
    if not zones_on(prm):
        return 1.0
    raw = {"night": prm["tariff_night_mult"], "day": prm["tariff_day_mult"], "peak": prm["tariff_peak_mult"]}
    mean = sum(raw[tariff_band(h + 0.5, prm)] for h in range(24)) / 24.0
    return raw[tariff_band(hour, prm)] / mean


def tariff_info(t_min: float, prm) -> dict:
    hour = (t_min % 1440.0) / 60.0
    if not zones_on(prm):
        kzt = prm["tariff_kzt_kwh_mean"]
        return {"band": "flat", "band_ru": "плоский", "mult": 1.0, "kzt_kwh": kzt,
                "text": (f"Тариф: плоский {num(kzt, 0)} тг/кВт·ч весь день (факт: зонные тарифы для потребителей "
                         f"отменены с 2018 г., приказ № 445; «пик и ночь» — только сценарий «что если», проект/допущение)")}
    band = tariff_band(hour, prm)
    mult = tariff_mult(hour, prm)
    kzt = prm["tariff_kzt_kwh_mean"] * mult
    return {"band": band, "band_ru": BAND_RU[band], "mult": mult, "kzt_kwh": kzt,
            "text": (f"Сценарий «что если»: тариф сейчас {BAND_RU[band]} ×{num(mult, 2)} ≈ {num(kzt, 1)} тг/кВт·ч "
                     f"(среднесуточный 16 тг/кВт·ч — факт; деление на пик и ночь — {ASSUME})")}


# ---------------------------------------------------------------------------
# People and the chain of responsibility
# ---------------------------------------------------------------------------
def person_info(store: Store, name: str, t: float, node_ru: Callable[[str], str]) -> dict:
    s = store.get(name)
    if s is None:
        return {"person": name, "name": name, "state": "UNKNOWN", "permit": "", "busy_until": NO_VALUE,
                "available": False, "where": ""}
    state = s.s("state") or "FREE"
    free = s.f("free_at")
    loc = s.s("task") or s.s("location")
    permit = s.s("permit")
    busy = free if (state in ("WORK", "TRAVEL") and free != NO_VALUE and free > t) else NO_VALUE
    return {"person": name, "name": str(s.attrs.get("name_ru") or name), "state": state, "permit": permit,
            "busy_until": busy, "available": state == "FREE", "where": node_ru(loc) if loc else "",
            "node": loc}


def _head(store: Store) -> str:
    for s in store.of_type("person"):
        if (s.attrs.get("responsible") or {}).get("role") == HEAD_ROLE:
            return s.name
    return ""


# Deputies of the stand's roster (stand assumption; the same table as sim/site_aktogay.DEPUTY, a test keeps them equal).
# The thing attribute responsible.deputy wins when a person thing carries it.
DEPUTY_DEFAULT = {
    "person-crusher-mech": "person-mill-mech", "person-mill-mech": "person-crusher-mech",
    "person-kip": "person-power", "person-power": "person-kip",
    "person-metallurgist": "person-geologist", "person-geologist": "person-metallurgist",
    "person-water": "person-metallurgist", "person-dispatcher": "person-geologist",
    "person-mine-head": "person-dispatcher", "person-road": "person-mine-head",
    "person-pit-mech": "person-crusher-mech", "person-grind-op": "person-metallurgist",
}


def _deputy(store: Store, person: str) -> str:
    s = store.get(person)
    d = str(((s.attrs.get("responsible") or {}).get("deputy") if s else "") or "")
    d = d.split(":", 1)[1] if ":" in d else d
    return d or DEPUTY_DEFAULT.get(person, "")


# Chain of a trouble kind when it is not main -> deputy -> shift head of the plant (the pit has its own head of shift and a
# road service). The same table as sim/site_aktogay.CHAIN_BY_KIND, a test keeps them equal (T-K4: the risk is named by KAZ
# Minerals, the roster is a stand assumption).
CHAIN_BY_KIND = {
    "road_winter": ("person-dispatcher", "person-mine-head", "person-road"),
    "driver_fatigue": ("person-dispatcher", "person-mine-head"),
    "oil_contam": ("person-pit-mech", "person-dispatcher", "person-mine-head"),
    "exc_down": ("person-pit-mech", "person-dispatcher", "person-mine-head"),
}


def build_chain(store: Store, main: str, node: str, t: float, node_ru: Callable[[str], str],
                job_started: bool = False, kind: str = "") -> dict:
    """Chain main -> deputy -> shift head for an issue at `node`.

    available: the person is free. A person already working at this very node counts as present (the job is his).
    pick: the first available link (the main one when he is free), else the one who frees first.
    via: "" when the main person goes, "deputy" or "head" when the pick is a later link.
    text: empty when the main person is free and nothing needs saying; otherwise names who is busy (and why) and
    whom to call."""
    names: list[str] = []
    custom = [n for n in CHAIN_BY_KIND.get(kind, ()) if store.get(n) is not None]
    for n in (custom if custom else (main, _deputy(store, main), _head(store))):
        if n and n not in names:
            names.append(n)
    items = [person_info(store, n, t, node_ru) for n in names]
    for it in items:
        if it["state"] == "WORK" and it.get("node") == node:
            it["available"] = True
    if not items:
        return {"items": [], "pick": "", "via": "", "text": ""}
    pick = next((it for it in items if it["available"]), None)
    if pick is None:
        pick = min(items, key=lambda it: it["busy_until"] if it["busy_until"] != NO_VALUE else 1e12)
    via = "" if pick is items[0] else ("head" if pick["person"] in (_head(store), "person-mine-head") else "deputy")
    first = items[0]
    text = ""
    if not first["available"] and not job_started:
        why = []
        if first["state"] == "OFF":
            why.append("нет на смене или эвакуирован")
        elif first["permit"]:
            until = f" до {hhmm_day(first['busy_until'], t)}" if first["busy_until"] != NO_VALUE else ""
            why.append(f"занят по наряду-допуску на {node_ru(first['permit'])}{until} — выйти из зоны работ до окончания "
                       f"нельзя (п. 12, 63 Правил № 348)")
        elif first["state"] in ("WORK", "TRAVEL"):
            until = f" до {hhmm_day(first['busy_until'], t)}" if first["busy_until"] != NO_VALUE else ""
            why.append(f"занят на другой работе{until}")
        text = f"{first['name']}: " + "; ".join(why)
        if pick is not first:
            tail = "свободен" if pick["available"] else (
                f"освободится в {hhmm_day(pick['busy_until'], t)}" if pick["busy_until"] != NO_VALUE else "занят")
            role = "заместитель " if via == "deputy" else ""
            text += f" → предложить: {role}{pick['name']} ({tail})"
        else:
            text += " → других свободных нет, ждать окончания работ"
    chain_line = " → ".join(f"{it['name']} ({'свободен' if it['available'] else 'занят'})" for it in items)
    return {"items": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in it.items()
                       if k in ("person", "name", "state", "permit", "busy_until", "available", "where")}
                      for it in items],
            "pick": pick["person"], "via": via, "text": text, "line": chain_line}


# ---------------------------------------------------------------------------
# Price of a choice and shift review
# ---------------------------------------------------------------------------
def choice_text(a_name: str, b_name: str, loss: dict, a_id: str, b_id: str, prm, crew_ru: str,
                two_lines: bool) -> str:
    """One free crew, two troubles: the model's loss over the horizon for each first call and the price of the
    wrong choice. loss: trouble id -> (USD, t Cu) when it is called first (policy.first_choice_losses)."""
    la, lb = loss[a_id], loss[b_id]
    gap_usd, gap_cu = lb[0] - la[0], lb[1] - la[1]
    where = "на двух линиях" if two_lines else "в двух узлах"
    head = f"Бригада одна ({crew_ru}), беды {where}. "
    if abs(gap_usd) < max(prm["review_min_fork_usd"], 0.01 * abs(la[0])):
        return head + f"Кого отправить первым — почти равно: разница меньше {usd(prm['review_min_fork_usd'])} {EST}"
    return (head + f"Сначала «{a_name}»: потери за {num(prm['q_horizon_h'], 0)} ч ≈ {usd(la[0])}; "
            f"сначала «{b_name}»: ≈ {usd(lb[0])}; цена неверного выбора ≈ {usd(gap_usd)} / "
            f"{signed(gap_cu, 2)} т Cu {EST}")
