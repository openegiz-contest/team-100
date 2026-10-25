"""Oxide chain (ore to the heap -> heap leach pad -> PLS pond -> SX -> EW -> cathode store): three troubles for akt-priority.

  leach_cold  «Куча: орошение ниже нормы» (card `leach_cold`): the irrigation of the pad is below the design flow by more than
              `ox_alarm_frac` (frozen lines, the scenario leachcold; a failed pump gives the same signal)
  ew_rect     «Выпрямитель электролиза» (card `ew_rect`): the line current of the tankhouse is gone while the control asks for it
  sx_crud     «Краб в отстойнике SX» (card `sx_crud`): the crud layer of the settler is above the alert limit; extraction and the flow
              the settler can take fall, the PLS pond fills

The module reads only Ditto: leach-1, pls-1, sx-1, ew-1, catstore-1, sxew-1. The expected cathode (`ew-1.cathode_exp_tph`) is what the
chain makes with the pad at full irrigation; the price of a trouble is the cathode below it times the LME price times
`cathode_payable_frac` (cathode is sold as metal, no concentrate deductions: an assumption). The class of all three is money (not S0 / S1);
the decision of the person is recorded, no procedure is invented.
"""
from __future__ import annotations

from . import tiers
from .store import NO_VALUE
from .text import ASSUME, EST, dur, num

KIND = "leach_cold"
KIND_EW = "ew_rect"
KIND_CRUD = "sx_crud"
KINDS = (KIND, KIND_EW, KIND_CRUD)

W_FLOW = "расходомер раствора на кучу [допущение: на фабрике он есть, в открытых данных не назван]"
W_ELEC = "выпрямительный агрегат цеха электролиза (АСУ ТП) [допущение]"
W_SX = "отстойник SX: толщина слоя краба, лаборатория / оператор [допущение]"

# measurements behind the troubles (same form as tiers.EVIDENCE: label, thing, feature, unit, digits, where seen)
tiers.EVIDENCE[KIND] = [
    ("орошение кучи", "leach-1", "irrigation_pct", "% от расчётного", 0, W_FLOW),
    ("ожидаемый катод", "ew-1", "cathode_exp_tph", "т/ч", 2, tiers.W_MODEL),
    ("катод сейчас", "ew-1", "cathode_tph", "т/ч", 2, "учёт катодного цеха [допущение]"),
    ("уровень квартала в отчёте", "sxew-1", "cathode_level_tph", "т/ч", 2, "квартальный отчёт KAZ Minerals"),
    ("температура кучи", "leach-1", "heap_temp_c", "°C", 0, tiers.W_MODEL),
    ("воздух", "water", "air_temp_c", "°C", 0, "метеопост"),
]
tiers.EVIDENCE[KIND_EW] = [
    ("ток линии", "ew-1", "current_ka", "кА", 1, W_ELEC),
    ("ток по заданию", "ew-1", "current_set_ka", "кА", 1, tiers.W_MODEL),
    ("медь в электролите", "ew-1", "electrolyte_cu_t", "т", 1, "расчёт по анализу электролита [допущение]"),
    ("катод сейчас", "ew-1", "cathode_tph", "т/ч", 2, "учёт катодного цеха [допущение]"),
    ("ожидаемый катод", "ew-1", "cathode_exp_tph", "т/ч", 2, tiers.W_MODEL),
]
tiers.EVIDENCE[KIND_CRUD] = [
    ("слой краба", "sx-1", "crud_cm", "см", 1, W_SX),
    ("извлечение", "sx-1", "extraction_pct", "%", 0, "анализы раствора и рафината, лаборатория"),
    ("медь в рафинате", "sx-1", "raff_cu_gl", "г/л", 2, "анализ рафината, лаборатория"),
    ("уровень в пруду PLS", "pls-1", "level_pct", "%", 0, "уровнемер пруда [допущение]"),
    ("ожидаемый катод", "ew-1", "cathode_exp_tph", "т/ч", 2, tiers.W_MODEL),
]


def _price(prm, tph: float) -> float:
    return tph * prm["cu_price_usd_t"] * prm["cathode_payable_frac"]


def troubles(m, t: float) -> list:
    """The three troubles of the chain."""
    st, prm = m.store, m.prm
    out = []
    exp = st.f("ew-1", "cathode_exp_tph")
    # ---- leach_cold: irrigation of the pad below the design flow
    irr = st.f("leach-1", "irrigation_pct")
    lexp = st.f("leach-1", "leach_exp_tph")
    if irr != NO_VALUE and lexp != NO_VALUE and lexp > 0.0 and 100.0 - irr >= 100.0 * prm["ox_alarm_frac"]:
        frac = 1.0 - irr / 100.0
        lost = lexp * frac                                         # cathode t/h that the pad does not give while it is cold
        usd = _price(prm, lost)
        air = st.f("water", "air_temp_c")
        text = (f"орошение кучи {num(irr, 0)} % от расчётного при пороге {num(100 * (1 - prm['ox_alarm_frac']), 0)} % {ASSUME}: "
                f"растворение меди упало примерно на {num(100 * frac, 0)} % ({num(lexp, 2)} → {num(lexp - lost, 2)} т/ч меди) {EST}, "
                f"катод снизится через часы (запас: дренаж кучи, пруд PLS, электролит); в отчётах 4 кв. 2024 г. катод упал на 25 % "
                f"«из-за меньших объёмов руды на площадках и более холодных условий» [факт, другой год]"
                + (f"; воздух {num(air, 0)} °C" if air != NO_VALUE else "")
                + f"; цена — катод по LME без вычетов концентрата {ASSUME} ≈ ${num(usd, 0)}/ч")
        out.append(m._tr("leach-1:cold", "leach-1", KIND, 0.0, 0.0, "rep_decision_h", t, loud=False, usd_extra_h=usd, text=text))
    # ---- ew_rect: no line current while the control asks for it
    cur, setc = st.f("ew-1", "current_ka"), st.f("ew-1", "current_set_ka")
    if (cur != NO_VALUE and setc != NO_VALUE and setc > 0.0 and exp != NO_VALUE and exp > 0.0
            and cur <= prm["ox_rect_floor_frac"] * setc):
        e_cu = st.f("ew-1", "electrolyte_cu_t")
        e_max = prm["ox_ew_emax_frac"] * prm["ox_ew_e_t"]
        tr = st.f("sx-1", "transfer_cu_tph")
        to_fail = max(0.0, (e_max - e_cu) / tr) if e_cu != NO_VALUE and tr != NO_VALUE and tr > 0.05 else 0.0
        usd = _price(prm, exp)
        text = (f"выпрямитель электролиза не даёт ток: {num(cur, 1)} кА при задании {num(setc, 1)} кА; катод {num(exp, 2)} → 0 т/ч "
                f"(по Фарадею ≈ 1,19 г меди на А·ч на ванну × ванны × выход по току) {EST}; медь копится в электролите: до предела "
                f"≈ {dur(to_fail)} {ASSUME}, затем экстракция встаёт и раствор идёт по кругу куча → SX → куча; после пуска ток "
                f"идёт к пределу выпрямителя и выпуск частично нагоняется; цена — катод по LME без вычетов концентрата {ASSUME} "
                f"≈ ${num(usd, 0)}/ч; дежурный электрик: причина отключения, пуск")
        out.append(m._tr("ew-1:rect", "ew-1", KIND_EW, 0.0, to_fail, "rep_ew_h", t, loud=False, usd_extra_h=usd, text=text))
    # ---- sx_crud: crud layer of the settler above the alert limit
    crud = st.f("sx-1", "crud_cm")
    if crud != NO_VALUE and crud >= prm["ox_crud_alert_cm"] and exp != NO_VALUE and exp > 0.0:
        ext = st.f("sx-1", "extraction_pct")
        share = max(0.0, 1.0 - ext / (100.0 * prm["ox_sx_eta"])) if ext != NO_VALUE else 0.0
        htf = st.f("pls-1", "hours_to_full")
        to_fail = htf if htf != NO_VALUE and htf >= 0.0 else 0.0
        raff = st.f("sx-1", "raff_cu_gl")
        usd = _price(prm, exp * share)
        text = (f"краб в отстойнике SX {num(crud, 1)} см при пороге {num(prm['ox_crud_alert_cm'], 1)} см {ASSUME}: извлечение "
                f"{num(ext, 0)} % (норма {num(100 * prm['ox_sx_eta'], 0)} %), медь в рафинате "
                f"{num(raff, 2)} г/л, отстойник пропускает меньше раствора; недоизвлечённая медь возвращается на кучу с рафинатом, "
                f"выпуск катода ниже ≈ на {num(100 * share, 0)} % ({num(exp * share, 2)} т/ч) {EST}"
                + (f"; пруд PLS заполнится через ≈ {dur(to_fail)}, дальше орошение режут" if to_fail > 0.0 else "")
                + f"; цена — катод по LME без вычетов концентрата {ASSUME} ≈ ${num(usd, 0)}/ч; "
                f"металлург смены: снять краб, проверить органику")
        out.append(m._tr("sx-1:crud", "sx-1", KIND_CRUD, 0.0, to_fail, "rep_crud_h", t, loud=False, usd_extra_h=usd, text=text))
    return out
