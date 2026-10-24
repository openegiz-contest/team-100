"""Machine-readable lever suggestion of an advice that changes the regime (liner wear / SAG overload -> reduce the feed,
coarse grind -> grind target, cyclone roping -> reduce the feed).

The module only ADVISES: it never writes a lever. The issue card shows the button "Применить совет в модели" when the
issue carries a lever; one click sends it to /api/lever (the dispatcher's decision, a control of the MODEL, not of the plant).
The shape is fixed (a Ditto merge overwrites every leaf): name "" = no lever.
"""
from __future__ import annotations

from .text import ASSUME, num

EMPTY = {"name": "", "line": 0.0, "value": -1.0, "unit": "", "label": "", "reason": ""}
FEED_ADVICE = ("loss_sag", "roping")             # kinds whose advice is "reduce the feed"


def _line(node: str) -> int:
    tail = node.rpartition("-")[2][:1]
    return int(tail) if tail.isdigit() else 0


def liner_feed(n: int, eta_now: float, eta_peak: float, prm) -> dict:
    """Forecast of the liner campaign (page "Прогнозы"): past the peak the capacity of the SAG falls with the wear; the
    advice is to lower the feed of the line a little instead of running the mill at the power limit."""
    if eta_now is None or eta_now >= eta_peak * 0.98:
        return dict(EMPTY)
    v = float(prm["lev_adv_feed_pct"])
    return {"name": "feed", "line": float(n), "value": v, "unit": "% номинала",
            "label": f"Подача линии {n} = {num(v, 0)} % номинала",
            "reason": (f"футеровка SAG-{n} за пиком: производительность мельницы {num(100 * eta_now, 0)} % против "
                       f"{num(100 * eta_peak, 0)} % на пике; снизить подачу до {num(v, 0)} % номинала {ASSUME} — управление "
                       f"моделью, не фабрикой; на фабрике решает металлург")}


def suggest(tr, prm) -> dict:
    """Lever of the advice of trouble `tr` (modules.policy.Trouble), or EMPTY."""
    n = _line(tr.node)
    if n not in (1, 2):
        return dict(EMPTY)
    if tr.kind == "grind_coarse":
        v = float(prm["p80_ref_um"])
        return {"name": "p80_um", "line": 0.0, "value": v, "unit": "мкм",
                "label": f"Цель помола P80 = {num(v, 0)} мкм",
                "reason": (f"помол крупнее нормы: цель по помолу вернёт P80 к {num(v, 0)} мкм (вендор); подача SAG "
                           f"снизится ровно настолько, чтобы шаровые держали этот помол (подача выше номинала, заданная рычагом, возвращается к 100 %) — управление моделью, не фабрикой; "
                           f"на фабрике решает металлург")}
    if tr.kind in FEED_ADVICE:
        v = float(prm["lev_adv_rope_feed_pct" if tr.kind == "roping" else "lev_adv_feed_pct"])
        why = ("канатирование и перегрузка шаровой" if tr.kind == "roping" else
               "перерасход энергии SAG (перегруз, износ футеровки, крупное питание)")
        return {"name": "feed", "line": float(n), "value": v, "unit": "% номинала",
                "label": f"Подача линии {n} = {num(v, 0)} % номинала",
                "reason": (f"{why}: снизить подачу линии {n} до {num(v, 0)} % номинала {ASSUME} — управление моделью, "
                           f"не фабрикой; на фабрике решает металлург")}
    return dict(EMPTY)
