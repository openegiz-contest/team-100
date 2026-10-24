"""Honest summary of the labels of the parameter tables (FEATURES_22.md, Д4): how many numbers of the model and of the
modules are a fact, a vendor figure, an analog, a project figure, a calculation or an assumption. The page «Калибровка»
shows it (`web/static/params_summary.json`), VALIDATION.md quotes it in «Чего модель не умеет», a test keeps both equal
to the tables.

  python -I aktogay/run.py paramstat --write aktogay/web/static/params_summary.json

Counts are over the rows of `sim/params.py` (the model) and `modules/params.py` (the analysis modules; they keep their own
table). The tier S statement (63 of the 78 new rows are assumptions) is quoted from README_dev.md of 23.10.2026: the rows
of the tier sit in both tables and are not marked as a group in the code, so the count is not recomputed here.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import params as mparams  # noqa: E402
from sim import params as sparams  # noqa: E402

ORDER = ("fact", "vendor", "analog", "project", "calc", "assumption")
RU = {"fact": "факт", "vendor": "вендор", "analog": "аналог", "project": "проект", "calc": "расчёт", "assumption": "допущение"}
MEANING = {
    "fact": "отчёт компании или открытые данные: число взято как есть",
    "vendor": "паспорт или проспект поставщика оборудования",
    "analog": "число другой фабрики или рудника, взято как ориентир",
    "project": "проектный документ (ОВОС 2018, ПЭК)",
    "calc": "посчитано из других чисел таблицы или отчётов",
    "assumption": "источника нет: число выбрано нами, диапазон правдоподобия записан в таблице",
}
TIER_S = {"rows": 78, "assumptions": 63, "source": "README_dev.md, запись 23.10.2026 (строки уровня S: зимняя дорога, канатирование, pH-метр, ВВД линии 2, замена брони, масло EX01)"}
# What the model cannot do, one line each; VALIDATION.md, «Чего модель не умеет», repeats them with the numbers
LIMITS = (
    "Формула извлечения не лучше константы: на квартальной проверке 2018–2024 ошибка 1,76 п.п. против 1,40 п.п. у постоянных 87,2 %; "
    "переподгонка на 2018–2021 гг. хуже вдвое (2,1–2,3 п.п. на 2023–2025), поэтому оставлена подгонка 2025 г.",
    "Большая часть чисел — допущения: см. таблицу выше; из 78 новых строк уровня S допущениями стоят 63. Сколько из них способно изменить вывод опыта — ниже.",
    "Реальных журналов смен нет: датчики синтетические, опыт «вкл/выкл» сравнивает модель с моделью, частоты и размеры бед — допущения.",
    "Извлечение 2024 г. вне допуска (−0,68 п.п.); объяснения (перенос запаса, сезонность) даны после факта и проверкой не являются (VALIDATION 6.9); разгон второй фабрики 2021–2022 гг. в модели не воспроизведён.",
    "Доступность дробилки — требование к оборудованию, а не проверка: чтобы пропустить руду 2025 г., ей нужны 70–81 % часов года при 65,1 % по проекту ОВОС (КИО 0,78 — доля суток, не часов); измельчение подогнано, флотация (92 %) в пределах 91–92 %.",
    "Откатка считается по карте стенда и паспорту 793D, но доля расчётной скорости (0,52) подобрана так, чтобы рейс остался прежним, 30 мин.",
    "Перефутеровка SAG 84 ч (аналог: кейс Metso, Minera Chinalco Peru) — см. VALIDATION 6.3: падение руды линии в пяти событиях из отчётов.",
    "Деньги — валовая стоимость меди по цене 15.10.2026 без затрат на ремонт, запчасти и работу людей.",
)


def _count(rows) -> dict:
    out = {k: 0 for k in ORDER}
    for r in rows:
        out[r.label] += 1
    return out


def build() -> dict:
    sim = _count(sparams.TABLE.values())
    mod = _count(mparams.PARAMS)
    total = {k: sim[k] + mod[k] for k in ORDER}
    n = sum(total.values())
    return {
        "labels": [{"key": k, "ru": RU[k], "meaning": MEANING[k], "sim": sim[k], "modules": mod[k], "total": total[k],
                    "pct": round(100.0 * total[k] / n, 1)} for k in ORDER],
        "sim_rows": sum(sim.values()), "modules_rows": sum(mod.values()), "rows": n,
        "assumption_pct": round(100.0 * total["assumption"] / n, 1),
        "fitted_rows": sum(1 for r in sparams.TABLE.values() if getattr(r, "fit", False)),
        "tier_s": TIER_S,
        "limits": list(LIMITS),
        "files": {"sim": "aktogay/sim/params.py", "modules": "aktogay/modules/params.py", "table": "aktogay/PARAMETERS.md"},
    }


def json_text() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--write":
        with open(argv[1], "w", encoding="utf-8", newline="\n") as f:
            f.write(json_text())
        return 0
    d = build()
    print(f"{d['rows']} rows ({d['sim_rows']} model + {d['modules_rows']} modules); assumptions {d['assumption_pct']} %")
    for x in d["labels"]:
        print(f"  {x['ru']:<10} {x['total']:>4}  {x['pct']:>5} %")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
