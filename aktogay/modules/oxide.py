"""Oxide line (heap leach -> SX-EW -> cathode): the trouble «Куча выщелачивания: холодное выщелачивание» (card of readiness
`leach_cold`). The module reads only Ditto: `leach-1` (state, cold_frac, level_tph) and `sxew-1` (cathode_tph, quarter, year).

The cathode output of the twin is the quarterly figure of the production reports (a fact of the quarter, not a
measurement), so the signal is "the output is below the level of the quarter by more than `ox_alarm_frac`". The price is the
lost cathode t/h x LME x `cathode_payable_frac` (cathode sold at the LME price, no concentrate deductions: an assumption).
The class of the trouble is money (not S0 / S1); the decision of the metallurgist is recorded, no procedure is invented.
"""
from __future__ import annotations

from . import tiers
from .store import NO_VALUE
from .text import ASSUME, EST, num

KIND = "leach_cold"

# measurements behind the trouble (same form as tiers.EVIDENCE: label, thing, feature, unit, digits, where seen)
tiers.EVIDENCE[KIND] = [
    ("выпуск катода сейчас", "sxew-1", "cathode_tph", "т/ч", 2, "отчётная цифра квартала, не замер: на фабрике — учёт катодного цеха [допущение]"),
    ("уровень квартала", "sxew-1", "cathode_level_tph", "т/ч", 2, "квартальный отчёт KAZ Minerals"),
    ("падение против уровня", "leach-1", "cold_frac", "доля", 2, tiers.W_MODEL),
    ("воздух", "water", "air_temp_c", "°C", 0, "метеопост"),
]


def troubles(m, t: float) -> list:
    """The trouble when the cathode output is below the level of the quarter by more than ox_alarm_frac."""
    st, prm = m.store, m.prm
    frac = st.f("leach-1", "cold_frac")
    lvl = st.f("leach-1", "level_tph")
    if frac == NO_VALUE or lvl == NO_VALUE or lvl <= 0.0 or frac < prm["ox_alarm_frac"]:
        return []
    lost = lvl * frac                                          # cathode t/h below the level of the quarter
    usd = lost * prm["cu_price_usd_t"] * prm["cathode_payable_frac"]
    text = (f"выпуск катода ниже уровня квартала на {num(100 * frac, 0)} % ({num(lvl, 2)} → {num(lvl - lost, 2)} т/ч, "
            f"{num(lost, 2)} т/ч меди) {EST}; холодное выщелачивание на куче: в отчётах 4 кв. 2024 г. катод упал на 25 % "
            f"«из-за меньших объёмов руды на площадках и более холодных условий» [факт, другой год]; цена — катод по LME без "
            f"вычетов концентрата {ASSUME} ≈ ${num(usd, 0)}/ч; порог "
            f"{num(100 * prm['ox_alarm_frac'], 0)} % {ASSUME}")
    return [m._tr("leach-1:cold", "leach-1", KIND, 0.0, 0.0, "rep_decision_h", t, loud=False, usd_extra_h=usd, text=text)]
