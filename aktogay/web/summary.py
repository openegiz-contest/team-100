"""Server-rendered text view of the live stand: GET /summary (HTML, no JavaScript) and GET /summary.json.

The page is built from the same state the interface reads (the cached /api/state: Ditto things written by the simulator and the
modules) and from the files of web/static (scenario catalog, expected results, back-test); it adds nothing of its own. A reader
that cannot run scripts (a text browser, curl, a crawler) sees the situation of the mine, the queue, the modules, the scenarios
with their addresses and the list of all pages. Standard library only; the build is a few milliseconds and is kept per state read.
"""
from __future__ import annotations

import html
import json
import os

PRICE_USD_T = 14539.0      # LME Cu cash 15.10.2026 (sim/params.py econ_cu_price_usd_t)
PAYABLE = 0.955            # share of the copper paid by the buyer (econ_payable)
PERMANENT_THINGS, TYPES = 141, 50   # setup/things.json: permanent things and thing types (tests/test_final25.py keeps it)

# page -> what it shows (one line each); the address is /?view=<id>
VIEWS = [
    ("plan", "Обзор: карта карьера и фабрики с живыми т/ч, складами, людьми и бедами; слои «Техника», «Люди», «Руда», «Вода и энергия»"),
    ("queue", "Все беды по порядку вызова: цена часа, кого звать, из чего цена, измерения и возраст данных, «Позвать» / «Отложить»"),
    ("areas", "Участки: карьер, дробление, склады, линии, флотация, концентрат, вода, энергия, люди"),
    ("forecast", "Прогнозы: на сколько часов хватит руды при остановке карьера, футеровка SAG, медь до конца смены"),
    ("copper", "Путь меди: потоки карьер → концентрат, баланс меди и воды, потери по бедам"),
    ("handover", "Сдача смены: лист из открытых бед, отложенных решений, приборов под подозрением"),
    ("report", "Отчёт смены одной кнопкой, печать и PDF"),
    ("journal", "Журнал: вызовы, решения, причины; поиск и выгрузка CSV"),
    ("economics", "Экономика: опыт «двойник вкл/выкл» на 100 парных сменах, цена часа задержки, торнадо чувствительности"),
    ("calib", "Калибровка: сверка с отчётами KAZ Minerals, 28 кварталов без подгонки, проверка правдоподобия, на чём стоят числа"),
    ("modules", "Модули: что читает и решает каждый, отставание от симулятора, эффект модуля, кто вызывал в «Два сразу»"),
    ("inside", "Изнутри: узлы, сигналы с пометкой «где виден», типовые отказы с источниками"),
    ("replay", "Повтор смены с двойником и без: две ленты по этапам, разница во времени и т Cu"),
    ("howto", "Как проверить: утверждение → где посмотреть → источник; ожидаемый итог сценариев; реестр чисел"),
    ("scenarios", "Сценарии: каталог из 32 «что если», конструктор беды"),
    ("train", "Тренировка: учебные вызовы не пишутся в журнал"),
    ("legend", "Легенда знаков и цветов"),
    ("ore", "Руда: окна прихода твёрдой и мягкой руды, прогноз подачи на 12 ч"),
    ("levers", "Рычаги модели: подача SAG, помол P80, доза собирателя («было → стало»)"),
    ("line1", "Схема линии 1: склад → SAG → циклоны → шаровые → флотация → сгуститель → фильтр"),
    ("line2", "Схема линии 2"),
    ("diorama", "3D-диорама рудника с живыми подписями"),
    ("site", "«Спутник 3D»: снимок Sentinel-2 с рудником"),
    ("tree", "Дерево вещей: иерархия, связи питания"),
    ("text", "Все вещи текстом"),
    ("mech", "Экран механика: мои вызовы и статус"),
    ("unit&id=kz.aktogay:sag-1", "Паспорт вещи (пример SAG-1): у каждого числа источник и метка"),
    ("plan&layer=sat", "Обзор на спутниковом снимке"),
]
API = [
    ("/api/state", "все вещи kz.aktogay из Ditto одним JSON (кэш 3 с)"),
    ("/summary.json", "эта сводка в JSON"),
    ("/api/thing?id=kz.aktogay:site", "одна вещь: признаки, паспорт, источники"),
    ("/api/history?thing=line-1&field=cu_tph&range=2h", "история признака из InfluxDB"),
    ("/api/journal?range=24h", "журнал вызовов и решений"),
    ("/healthz", "процесс жив"),
]


# «Достоверность одним взглядом»: числа взяты из VALIDATION.md (разделы в последней колонке); живая только проверка правдоподобия.
CREDIBILITY = [
    ("Медь в концентрате по 28 кварталам 2018–2024, без подгонки", "средняя ошибка около 2,3 %", "отчёты KAZ Minerals",
     "в допуске 22 квартала из 28; две фабрики 2023–2024: 0,74 %, 8 из 8", "6.1"),
    ("Пять реальных перефутеровок SAG: падение руды линии", "−5,47 % в среднем", "−4,85 % в отчётах",
     "средняя разница 0,91 п.п.; тест слабый: интервалы отчётов шириной 6–8 п.п.", "6.3"),
    ("Удельная энергия SAG на ходу", "6,74 кВт·ч/т", "7,25 измерено (Bradken и KAZ Minerals)", "−7,0 %, допуск ±10 %; проверка слабая", "4"),
    ("Электроэнергия на тонну руды за год", "34,73 кВт·ч/т", "34,9 по отчёту KAZ Minerals за 2024 г.", "−0,4 %, в допуске", "4"),
    ("Вода: забор на тонну руды", "0,580 м³/т", "0,598 по отчёту KAZ Minerals за 2024 г.", "−2,9 %, допуск ±0,030; сверка порядка величины", "4"),
    ("Наклон извлечения по содержанию меди (хвосты)", "4,093 п.п. на ln содержания", "взят у аналога, рудник Josemaria",
     "2023 г. сходится, 2024 г. нет (−0,68 п.п. при допуске ±0,5): вне допуска, показано как есть", "4"),
    ("Доступность агрегатов", "флотация 91,7 %", "91–92 % по проектам-аналогам", "флотация в допуске; измельчение 91,9 % — подгонка, не проверка; дробилка — требование к оборудованию", "6.2"),
    ("Реальные данные флотации (OpenML 43311, железная руда)", "шум расходомеров 1 % близок к реальному", "один завод, 2017 г.",
     "ложных тревог 24–40 в неделю на шесть узлов (двойник 29,8; теория 2,8–5,4); упреждение лаборатории сигналами процесса не показано", "8.15, 8.18"),
    ("Погода Актогая (ERA5, 2018–2025)", "три параметра сценариев приведены к типичным значениям", "реанализ ERA5", "итоги сценариев не изменились", "10.2"),
    ("Какие числа двигают вывод", "из 816 чисел 30 влияют на вывод", "перебор краёв диапазонов", "19 из 30 — допущения, 11 — с источником; их и проверять первыми", "9.4"),
    ('Механизм «часы × цена часа» против 2024 → 2025', 'цена часа линии 13,77 т Cu (двойник)', '13,67 т по отчёту 2025 г. (3,548 кг/т × 3 853 т/ч); руда 2025 г. выросла на 6,5 %',
     'цена часа того же порядка, но совпадение по построению; причины роста отчёт не делит, одними простоями его не объяснить (983 линия-часа — 68 % всех простоев); II кв. 2019: «увеличенная готовность» — цифра группы, у Актогая руда −2,3 % (перефутеровка), для проверки часов не годится', '6.10'),
    ('Устойчивость выигрыша двойника к допущениям', 'среднее положительно во всех прогонах таблицы 9.5; нижняя граница ДИ над нулём во всех, кроме трёх', 'существующие прогоны 8.8–9.2 (seed 1001–1100 и 2001–2100, склад 40/163 кт, твёрдая руда, лаборатория, новичок)',
     'размер зависит от допущений сильнее знака (от 0,31 до 1,19 т за смену); на реальном шуме выигрыш не пересчитан', '9.5'),
    ('Окисленная цепочка: катод по кварталам 2018–2026', 'расчёт кучи: средняя ошибка 10,0 % по 32 кварталам подгонки; вперёд (1 пол. 2026 г.) 9,8 %', 'отчёты KAZ Minerals: катод, руда и содержание на кучи',
     'жёсткая проверка (подгонка до 2024 г.): вперёд около 24 %, хуже эталона «прошлый квартал»; это подгонка четырёх чисел, а не проверка физики; потоки раствора, ванны и выпрямитель — допущения', '6.11'),
]
CRED_LIMITS = [
    "Польза = сэкономленные часы промедления × цена часа: цена часа простоя линии сверена с реальными перефутеровками Актогая (факт, VALIDATION 6.3, 6.8); сэкономленные часы — оценка на модели по опубликованным задержкам людей (VALIDATION 8.17); механизм подтверждает и KAZ Minerals: рост переработки 2025 г. — «reduced maintenance downtime» (сокращение простоев на обслуживании) [факт, Q4 2025, с. 3].",
    "Выигрыш двойника (+0,61 т Cu за смену [95 % ДИ +0,23; +2,18], 100 парных смен) получен на модели против модели; на фабрике он не проверен.",
    "Формула извлечения не лучше константы 87,2 %: ошибка около 1,8 п.п. против 1,40 п.п. по 28 кварталам; в допуске ±0,5 п.п. только 4 квартала из 28.",
    "Вне допуска два числа: извлечение 2024 г. (−0,68 п.п.) и извлечение III кв. 2025 г.; промах не подгоняли.",
]


COPY_NAMES = {"base": "база (смена без сценария)", "fact": "факт (со сценарием)", "loud": "очередь «кто громче»", "no_twin": "без двойника"}
COPY_NAMES_FORK = {"base": "база (смена без бед)", "fact": "с двойником («по $»)", "loud": "по громкости", "no_twin": "без двойника, как сейчас"}


def _sg(v) -> str:
    """Signed number with a decimal comma and a true minus."""
    return ("−" + _num(-v, 2)) if v < 0 else ("+" + _num(v, 2))


def _v(thing, feature, default=None):
    f = ((thing or {}).get("features") or {}).get(feature) or {}
    v = (f.get("properties") or {}).get("value")
    return default if v is None else v


def _clock(m) -> str:
    try:
        m = int(round(float(m)))
    except (TypeError, ValueError):
        return "—"
    return "%02d:%02d" % ((m // 60) % 24, m % 60)


def _num(x, d=0) -> str:
    try:
        return f"{float(x):,.{d}f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return "—"


def _usd(x) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "—"
    return "$%s тыс." % _num(x / 1000.0, 1) if abs(x) >= 1000 else "$%s" % _num(x)


def _load(static: str, name: str):
    try:
        with open(os.path.join(static, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _plausibility(spec, th) -> tuple[int, int, int]:
    """(ok, bad, no data) of the invariants of plausibility.json on the live values (the rule of web/static/plausibility.js)."""
    def get(ref):
        name, _, feat = ref.partition(".")
        v = _v(th.get(name), feat)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v != -1 else None

    def prod(refs):
        x = 1.0
        for r in refs:
            g = get(r)
            if g is None:
                return None
            x *= g
        return x

    def total(terms):
        s = 0.0
        for t in terms:
            p = prod(t[1:])
            if p is None:
                return None
            s += t[0] * p
        return s

    ok = bad = na = 0
    for c in (spec or {}).get("checks", []):
        worst_bad = False
        seen = False
        for i, it in enumerate(c["items"]):
            num = total(it["terms"])
            if num is None:
                continue
            if it.get("den"):
                d = total(it["den"])
                if d is None or abs(d) < 1e-6:
                    continue
                num /= d
            v = (it.get("scale") if it.get("scale") is not None else 1.0) * num
            seen = True
            hi = c["item_hi"][i] if c.get("item_hi") else c.get("hi")
            lo = c.get("lo")
            span = (hi - lo) if (lo is not None and hi is not None) else (abs(hi if hi is not None else lo) or 1.0)
            over = max((lo - v) / span if lo is not None else -1e9, (v - hi) / span if hi is not None else -1e9)
            if over > 1e-9:
                worst_bad = True
        if not seen:
            na += 1
        elif worst_bad:
            bad += 1
        else:
            ok += 1
    return ok, bad, na


def build(state: dict, static: str) -> dict:
    th = {t["thingId"].split(":", 1)[-1]: t for t in state.get("things", [])}
    site = th.get("site")
    t_now = _v(site, "sim_time")
    run = _v(site, "idSimulationRun", "")
    name_ru = lambda n: ((th.get(n) or {}).get("attributes") or {}).get("name_ru") or n   # noqa: E731
    out: dict = {"title": "Стенд «Актогай»: сводка текстом", "state_read_at": state.get("now")}
    out["now"] = {"model_time": _clock(t_now), "model_minute": t_now, "state": _v(site, "state_ru", ""), "speed": _v(site, "speed"),
                  "speed_fact": _v(site, "speed_fact"), "run": run, "seed": _v(site, "seed"), "scenario": _v(site, "scenario", ""),
                  "things_in_ditto": state.get("count", len(th)), "permanent_things": PERMANENT_THINGS, "thing_types": TYPES}
    # oxide branch: ore -> heap -> PLS -> SX -> EW -> cathode store, live values of the chain of twins
    ox = [("oxfeed-1", "Руда на кучу", "cu_tph", "т Cu/ч в руде", ("ore_tph", "т руды/ч")),
          ("leach-1", "Куча выщелачивания", "leach_cu_tph", "т Cu/ч растворяется", ("inventory_cu_t", "т Cu лежит в куче")),
          ("pls-1", "Пруд PLS", "pls_gl", "г/л Cu в растворе", ("level_pct", "% объёма")),
          ("sx-1", "Экстракция SX", "transfer_cu_tph", "т Cu/ч перенесено", ("extraction_pct", "% извлечение")),
          ("ew-1", "Электролиз EW", "cathode_tph", "т/ч катода (Фарадей)", ("current_ka", "кА ток")),
          ("catstore-1", "Склад катода", "stock_t", "т катода на складе", ("in_tph", "т/ч приход"))]
    out["oxide"] = [{"thing": n, "name": nm, "state": _v(th.get(n), "state_ru") or _v(th.get(n), "state", ""), "value": _v(th.get(n), f), "unit": u,
                     "extra": _v(th.get(n), xf), "extra_unit": xu} for n, nm, f, u, (xf, xu) in ox if n in th]
    # contribution of each module: the paired 100-shift experiment (exp23.json, VALIDATION 8.17), a model estimate
    try:
        sym = json.load(open(os.path.join(static, "exp23.json"), encoding="utf-8")).get("sym") or {}
        main = json.load(open(os.path.join(static, "exp23.json"), encoding="utf-8")).get("main") or {}
        out["module_effect"] = {"total": main.get("cu"), "mod-losses": sym.get("detection"), "mod-priority": sym.get("order")}
    except (OSError, ValueError):
        out["module_effect"] = None
    # issues of this run
    issues = []
    for n, t in th.items():
        if n.startswith("issue-") and _v(t, "idSimulationRun") == run and _v(t, "status") not in (None, "RESOLVED"):
            issues.append((n, t))
    issues.sort(key=lambda x: (_v(x[1], "rank", 99) if _v(x[1], "rank", 99) >= 0 else 99, x[0]))
    rows = []
    for n, t in issues:
        rows.append({"id": n, "rank": _v(t, "rank"), "node": name_ru(_v(t, "node", "")) if _v(t, "node") else "", "kind": _v(t, "kind"),
                     "status": _v(t, "status_ru") or _v(t, "status"), "safety": _v(t, "safety_class", ""), "loss_usd_h": _v(t, "loss_usd_h"),
                     "delay_cost_usd_h": _v(t, "delay_cost_usd"), "call": _v(t, "responsible", ""), "text": _v(t, "text", ""),
                     "why": _v(t, "choice_text", "") or _v(t, "evidence_text", ""), "closure": _v(t, "closure", "")})
    out["first_trouble"] = rows[0] if rows else None
    out["queue"] = rows[:7]
    out["queue_total"] = len(rows)
    mp = th.get("mod-priority")
    out["queue_text"] = _v(mp, "queue_text", "")
    out["order_text"] = _v(mp, "order_text", "")
    # six tiles
    cu, tph = _v(site, "cu_tph"), _v(site, "tph")
    recs = [x for x in (_v(th.get("line-1"), "recovery"), _v(th.get("line-2"), "recovery")) if isinstance(x, (int, float)) and x > 0]
    loss = sum(r["loss_usd_h"] for r in rows if isinstance(r["loss_usd_h"], (int, float)) and r["loss_usd_h"] > 0 and r["status"] != "вызвана")
    out["tiles"] = [
        {"name": "Теряем сейчас", "value": _usd(loss) + "/ч" if loss > 0 else "нет", "note": "по открытым бедам, расчёт модели"},
        {"name": "Медь в концентрат", "value": _num(cu, 1) + " т/ч", "note": "сумма двух линий"},
        {"name": "Руда на фабрику", "value": _num(tph) + " т/ч", "note": "обе линии"},
        {"name": "Извлечение меди", "value": (_num(sum(recs) / len(recs), 1) + " %") if recs else "—", "note": "среднее по линиям"},
        {"name": "Электросеть", "value": "%s из %s МВт" % (_num(_v(site, "power_mw")), _num(_v(th.get("power"), "grid_limit_mw"))), "note": "нагрузка площадки и лимит сети"},
        {"name": "Стоимость меди", "value": ("≈ " + _usd(float(cu) * PRICE_USD_T * PAYABLE) + "/ч") if isinstance(cu, (int, float)) else "—",
         "note": "выручка по цене LME 14 539 $/т, 95,5 % оплаты"},
    ]
    # modules
    mods = []
    for key, title, last in (("mod-losses", "Где теряется медь", "top_text"), ("mod-ore", "Какая руда идёт", "fc_text"), ("mod-priority", "Очередь бед", "order_text")):
        p = _v(th.get(key), "processed_sim_time")
        lag = (float(t_now) - float(p)) if isinstance(p, (int, float)) and p >= 0 and isinstance(t_now, (int, float)) else None
        if lag is not None and lag < 0:                      # a value left from the previous run: this run has not counted yet
            lag = None
        mods.append({"module": key, "title": title, "processed_at": _clock(p) if lag is not None else None, "lag_min": lag,
                     "last_decision": _v(th.get(key), last, "")})
    out["modules"] = mods
    ml = th.get("mod-losses")
    findings = []
    for node in ("sag-1", "cyclones-1", "flot-1", "sag-2", "cyclones-2", "flot-2"):
        findings.append({"node": name_ru(node), "status": _v(ml, node + "_status_ru", ""), "gap_cu_t_h": _v(ml, node + "_gap_cu_tph"),
                         "gap_usd_h": _v(ml, node + "_gap_usd_h")})
    out["losses"] = {"top": _v(ml, "top_text", ""), "silent": _v(ml, "silent_text", ""), "nodes": findings}
    # scenario and its effect
    base = th.get("baseline")
    sr = _v(base, "shift_result")
    sc = _v(site, "scenario", "")
    eff = None
    if isinstance(sr, dict) and sr.get("run") == run and sr.get("kind") in ("scenario", "shift"):
        c = sr.get("copies") or {}
        eff = {"kind": sr["kind"], "at": _clock(sr.get("t_min")), "copies_cu_t": {k: (v or {}).get("cu_t") for k, v in c.items()},
               "diff_cu_t": {k: (v or {}).get("cu_t") for k, v in (sr.get("diff") or {}).items()}, "fork": sr.get("fork"), "policy": sr.get("policy")}
    out["scenario"] = {"active": sc, "base_to_fact": eff,
                       "cancel": "кнопка «Остановить сценарий…» в синей рамке справа или POST /api/cancel; «Сбросить 08:00» — новый прогон"}
    # all scenarios with the expected result computed beforehand
    cat = _load(static, "scenarios.json") or {}
    ver = _load(static, "verify.json") or {}
    exp = {}
    for r in ver.get("runs", []):
        exp.setdefault(r["id"], r)
    scen = []
    for s in cat.get("scenarios", []):
        r = exp.get(s["id"])
        e = None
        if r:
            d = r["diff"]["fact"]
            e = {"cu_t": d["cu_t"], "usd": d["usd"]}
            if r.get("fork"):
                e = dict(e, twin_minus_no_twin_cu_t=(r.get("fork_cu_t") or {}).get("total_cu_t"))
        url = "/?preset=fork&run=1" if s["id"] == "fork" else "/?scenario=%s&run=1" % s["id"]
        scen.append({"id": s["id"], "name": s["name"], "what": s.get("what", ""), "first": s.get("first", ""), "start": url,
                     "start_api": 'POST /api/scenario {"id":"%s"}' % s["id"] if s["id"] != "fork" else 'POST /api/scenario {"id":"fork","preset":"fork","kip":1}',
                     "cancel": "POST /api/cancel", "expected_by_20_00": e})
    out["scenarios"] = scen
    out["views"] = [{"url": "/?view=" + v, "shows": d} for v, d in VIEWS]
    out["api"] = [{"url": u, "shows": d} for u, d in API]
    # calibration headline
    calib = {"state": _v(th.get("validation-calib"), "state", "")}
    try:
        rep = json.loads(_v(th.get("validation-calib"), "report_json", "") or "null")
    except ValueError:
        rep = None
    if isinstance(rep, dict) and isinstance(rep.get("rows"), list):
        rows_ = rep["rows"]
        calib["rows"] = len(rows_)
        calib["in_tolerance"] = sum(1 for r in rows_ if r.get("ok") is True)
        calib["out_of_tolerance"] = sum(1 for r in rows_ if r.get("ok") is False)
        calib["no_tolerance"] = sum(1 for r in rows_ if r.get("ok") is None)
    bt = (_load(static, "backtest_q.json") or {}).get("summary", {}).get("all")
    if bt:
        calib["backtest"] = {"quarters": bt["n"], "copper_in_tolerance": bt["cu_ok"], "recovery_in_tolerance": bt["rec_ok"],
                             "copper_mean_abs_error_pct": bt["cu_mae_pct"], "recovery_mae_pp": bt["rec_mae_pp"], "constant_mae_pp": bt["const_mae_pp"]}
    ok, bad, na = _plausibility(_load(static, "plausibility.json"), th)
    calib["plausibility"] = {"ok": ok, "bad": bad, "no_data": na, "total": ok + bad + na}
    out["calibration"] = calib
    out["credibility"] = {"rows": [dict(zip(("what", "model", "reference", "verdict", "section"), r)) for r in CREDIBILITY],
                          "limits": CRED_LIMITS, "plausibility_live": calib["plausibility"], "details": "VALIDATION.md; все строки калибровки — /?view=calib"}
    return out


def _e(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def render_html(d: dict) -> str:
    n = d["now"]
    o = []
    a = o.append
    a('<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">')
    a("<title>Актогай — сводка стенда текстом</title>")
    a("<style>body{font:16px/1.45 system-ui,Segoe UI,Arial,sans-serif;max-width:60rem;margin:1rem auto;padding:0 1rem;color:#1d2330}"
      "table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:.25rem .5rem;text-align:left;vertical-align:top}"
      "th{background:#f3eee6}code{background:#eef0f4;padding:0 .2rem}h2{margin-top:1.6rem}</style></head><body>")
    a("<h1>Стенд «Актогай»: сводка текстом</h1>")
    a("<p>Сводка собрана на сервере из тех же данных двойника (Ditto и InfluxDB), что читает интерфейс; JavaScript не нужен. "
      'Интерфейс с картой и 3D — <a href="/">главная страница</a>. Данные: <a href="/summary.json">/summary.json</a>, '
      '<a href="/api/state">/api/state</a>.</p>')
    a("<h2>Сейчас</h2><ul>")
    a("<li>Время модели: <b>%s</b>, состояние: %s, скорость ×%s (факт ×%s)</li>" % (_e(n["model_time"]), _e(n["state"]), _e(_num(n["speed"])), _e(_num(n["speed_fact"]))))
    a("<li>Прогон: %s, seed %s; сценарий: %s</li>" % (_e(n["run"]), _e(_num(n["seed"])), _e(n["scenario"] or "нет, обычная смена")))
    a("<li>В двойнике %s вещей сейчас (%s постоянных вещей %s типов, остальное — партии руды и беды)</li></ul>" % (_e(n["things_in_ditto"]), _e(n["permanent_things"]), _e(n["thing_types"])))
    if d.get("oxide"):
        a("<h2>Окисленная ветка сейчас: руда → куча → раствор → экстракция → электролиз → катод</h2><p>Живые значения цепочки двойников из Ditto; "
          'схема — <a href="/?view=copper">/?view=copper</a> (раздел «Окисленная цепочка»). Катод — расчёт по закону Фарадея, не замер; кинетика кучи подогнана на катоде 32 кварталов 2018–2025 гг. (VALIDATION 6.11).</p>'
          "<table><tr><th>Звено</th><th>Состояние</th><th>Главное</th><th>Ещё</th></tr>")
        for x in d["oxide"]:
            val = "—" if not isinstance(x["value"], (int, float)) else _num(x["value"], 2)
            ext = "—" if not isinstance(x["extra"], (int, float)) else _num(x["extra"], 1)
            a("<tr><td>%s</td><td>%s</td><td>%s %s</td><td>%s %s</td></tr>" % (_e(x["name"]), _e(x["state"]), _e(val), _e(x["unit"]), _e(ext), _e(x["extra_unit"])))
        a("</table>")
    a("<h2>Достоверность одним взглядом</h2><p>Что проверено по реальным данным и насколько близко. Модель подогнана на 2025 г.; здесь то, что в подгонке не участвовало, и пределы. Подробности — <code>VALIDATION.md</code> (раздел в последней колонке; сводная таблица — в начале раздела 1), все строки калибровки — "
      '<a href="/?view=calib">/?view=calib</a>.</p>'
      "<ul><li><b>Проверено на данных, которых модель не видела:</b> медь в концентрате по 28 кварталам 2018–2024 (около 2,3 %) и вперёд на I–II кв. 2026 г.; "
      "вода 2023 г.; пять перефутеровок SAG (тест слабый); шум датчиков и ложные тревоги — на чужом открытом наборе (железная руда).</li>"
      "<li><b>Подогнано, не проверка:</b> готовность линии, энергия SAG и предельное извлечение на 2025 г.; «прочая» нагрузка и испарение на 2024 г.; кинетика кучи окисленной ветки.</li>"
      '<li><b>Не доказано:</b> формула извлечения не лучше константы; выигрыш двойника — оценка на модели; датчики стенда синтетические.</li></ul><table><tr><th>Что</th><th>Модель</th><th>Эталон</th><th>Итог</th><th>Раздел</th></tr>')
    for x in d["credibility"]["rows"]:
        a("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (_e(x["what"]), _e(x["model"]), _e(x["reference"]), _e(x["verdict"]), _e(x["section"])))
    pl = d["credibility"]["plausibility_live"]
    a("</table><p>Проверка правдоподобия на живых значениях (балансы меди, воды, массы, энергии, пределы оборудования): выполнено <b>%s из %s</b>, нарушено %s, нет данных %s.</p><p><b>Пределы:</b></p><ul>" % (_e(pl["ok"]), _e(pl["total"]), _e(pl["bad"]), _e(pl["no_data"])))
    for t in d["credibility"]["limits"]:
        a("<li>%s</li>" % _e(t))
    a("</ul>")
    me = d.get("module_effect")
    if me and me.get("mod-losses") and me.get("mod-priority") and me.get("total"):
        iv = lambda c: "%s [%s; %s]" % (_sg(c["mean"]), _sg(c["ci95"][0]), _sg(c["ci95"][1]))  # noqa: E731
        a("<h2>Модули: вклад каждого (опыт на 100 парных сменах, оценка на модели)</h2><table><tr><th>Модуль</th><th>Сравнение</th><th>т Cu за смену [95 %% ДИ]</th></tr>"
          "<tr><td>все вместе</td><td>двойник − «как сейчас»</td><td>%s</td></tr>"
          "<tr><td>«Где теряется медь» (mod-losses)</td><td>находка тихой потери есть / нет, порядок тот же</td><td>%s</td></tr>"
          "<tr><td>«Очередь бед» (mod-priority)</td><td>порядок «по $» / «по громкости», находка та же</td><td>%s (почти целиком одна смена-выброс)</td></tr>"
          "<tr><td>«Какая руда идёт» (mod-ore)</td><td>без двойника твёрдость узнают при выемке / только на SAG</td><td>0 / +0,58 [+0,40; +0,82]</td></tr></table>"
          "<p>Разложение одного парного опыта (VALIDATION 8.17, п. 4), а не три отдельных опыта. Страница с таблицей: "
          '<a href="/?view=modules">/?view=modules</a>.</p>' % (_e(iv(me["total"])), _e(iv(me["mod-losses"])), _e(iv(me["mod-priority"]))))
    a("<h2>Беда № 1</h2>")
    f = d["first_trouble"]
    if f:
        a("<p><b>%s</b> — %s (%s)</p><ul><li>Цена: теряем %s в час; час промедления вызова ≈ %s</li><li>Кого звать: %s</li><li>Что видно по измерениям: %s</li>%s</ul>" % (
            _e(f["node"] or f["kind"]), _e(f["text"]), _e(f["status"]), _e(_usd(f["loss_usd_h"]) if isinstance(f["loss_usd_h"], (int, float)) and f["loss_usd_h"] >= 0 else "в деньгах не считаем"),
            _e(_usd(f["delay_cost_usd_h"]) if isinstance(f["delay_cost_usd_h"], (int, float)) and f["delay_cost_usd_h"] >= 0 else "—"), _e(f["call"]),
            _e(f["why"] or d["order_text"] or "порядок по классу беды и ожидаемым потерям за 12 ч"), ("<li>%s</li>" % _e(f["closure"])) if f["closure"] else ""))
    else:
        a("<p>Открытых бед нет: все узлы работают, потерь сверх шума не найдено.</p>")
    a("<h2>Очередь бед (первые 7 из %s)</h2>" % _e(d["queue_total"]))
    if d["queue"]:
        a("<table><tr><th>№</th><th>Узел</th><th>Состояние</th><th>Теряем в час</th><th>Кого звать</th></tr>")
        for r in d["queue"]:
            a("<tr><td>%s</td><td>%s%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (_e(_num(r["rank"]) if isinstance(r["rank"], (int, float)) and r["rank"] < 90 else "—"), _e(r["node"]),
                                                                                     (" [%s]" % _e(r["safety"])) if r["safety"] else "", _e(r["status"]),
                                                                                     _e(_usd(r["loss_usd_h"]) if isinstance(r["loss_usd_h"], (int, float)) and r["loss_usd_h"] >= 0 else "—"), _e(r["call"])))
        a("</table>")
        if d["order_text"]:
            a("<p>%s</p>" % _e(d["order_text"]))
    a("<h2>Шесть плиток площадки</h2><table><tr><th>Показатель</th><th>Значение</th><th>Что это</th></tr>")
    for t in d["tiles"]:
        a("<tr><td>%s</td><td><b>%s</b></td><td>%s</td></tr>" % (_e(t["name"]), _e(t["value"]), _e(t["note"])))
    a("</table><h2>Модули</h2><table><tr><th>Модуль</th><th>Посчитано на</th><th>Отставание</th><th>Последнее решение</th></tr>")
    for m in d["modules"]:
        a("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (_e(m["title"]), _e(m["processed_at"] or "ещё не считал"), _e(("%s мин" % _num(m["lag_min"])) if m["lag_min"] is not None else "—"), _e(str(m["last_decision"])[:400])))
    a("</table><h2>Где теряется медь</h2><p>%s</p><table><tr><th>Узел</th><th>Статус</th><th>Разрыв, т Cu/ч</th><th>Разрыв, $/ч</th></tr>" % _e(d["losses"]["top"]))
    for x in d["losses"]["nodes"]:
        a("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (_e(x["node"]), _e(x["status"]), _e(_num(x["gap_cu_t_h"], 2)), _e(_num(x["gap_usd_h"]))))
    a("</table>")
    if d["losses"]["silent"]:
        a("<p>Тихие потери: %s</p>" % _e(d["losses"]["silent"]))
    sc = d["scenario"]
    a("<h2>Сценарий и его эффект</h2><p>Активный сценарий: <b>%s</b>. Отмена: %s.</p>" % (_e(sc["active"] or "нет"), _e(sc["cancel"])))
    e = sc["base_to_fact"]
    if e:
        nm = COPY_NAMES_FORK if e.get("fork") else COPY_NAMES
        a("<p>«База → факт» на %s модели, медь в концентрате с 08:00, т Cu: %s.</p><p>Эффект (копия минус база): %s.</p>" % (
            _e(e["at"]), _e("; ".join("%s %s" % (nm.get(k, k), _num(v, 2)) for k, v in e["copies_cu_t"].items())),
            _e("; ".join("%s %s т Cu" % (nm.get(k, k), _sg(v)) for k, v in e["diff_cu_t"].items() if isinstance(v, (int, float))))))
        p = e.get("policy") or {}
        if p.get("mode") in ("module", "fallback"):
            a("<p>Копия «по $» шла по вызовам модуля: %s из %s вызовов — модуля (режим: %s).</p>" % (_e(_num(p.get("n_module"))), _e(_num(p.get("n_calls"))), _e(p["mode"])))
    else:
        a("<p>Копий «база → факт» сейчас нет: идёт обычная смена.</p>")
    a("<h2>Все сценарии</h2><p>Запуск: адрес открывается в браузере с JavaScript; без него (curl) — командой <code>POST</code> из колонки «Запуск»; через 1–2 минуты сценарий виден в блоках «Беда № 1», «Очередь бед» и «Сценарий и его эффект» этой страницы (1 минута = 1 час модели). Отмена — <code>POST /api/cancel</code>. «Ожидаемо» — посчитано заранее тем же кодом "
      "(seed 42, к 20:00, т Cu и $: факт − база), оценка на модели.</p><table><tr><th>Сценарий</th><th>Что происходит</th><th>Запуск</th><th>Ожидаемо</th></tr>")
    for s in d["scenarios"]:
        ex = s["expected_by_20_00"]
        extext = ("%s т Cu, %s" % (_sg(ex["cu_t"]), ("−" + _usd(-ex["usd"])) if ex["usd"] < 0 else ("+" + _usd(ex["usd"])) if ex["usd"] > 0 else "0")) if ex else "—"
        if ex and ex.get("twin_minus_no_twin_cu_t") is not None:
            extext += "; двойник против «без двойника» %s т Cu" % _sg(ex["twin_minus_no_twin_cu_t"])
        a('<tr><td>%s<br><code>%s</code></td><td>%s</td><td><a href="%s">%s</a><br><code>%s</code></td><td>%s</td></tr>' % (
            _e(s["name"]), _e(s["id"]), _e(s["what"]), _e(s["start"]), _e(s["start"]), _e(s["start_api"]), _e(extext)))
    a("</table><h2>Все страницы интерфейса</h2><ul>")
    for v in d["views"]:
        a('<li><a href="%s"><code>%s</code></a> — %s</li>' % (_e(v["url"]), _e(v["url"]), _e(v["shows"])))
    a("</ul><h2>Достоверность модели</h2><ul>")
    c = d["calibration"]
    if "rows" in c:
        a("<li>Калибровка по отчётам KAZ Minerals 2025 и проверка 2023–2024 (состояние: %s): %s строк, в допуске %s, вне допуска %s, без допуска %s</li>" % (_e(c["state"]), _e(c["rows"]), _e(c["in_tolerance"]), _e(c["out_of_tolerance"]), _e(c["no_tolerance"])))
    b = c.get("backtest")
    if b:
        a("<li>Проверка по кварталам 2018–2024 без подгонки: %s кварталов; медь в допуске в %s, извлечение в допуске в %s; ошибка извлечения %s п.п. (константа 87,2 %% — %s п.п.)</li>" % (
            _e(b["quarters"]), _e(b["copper_in_tolerance"]), _e(b["recovery_in_tolerance"]), _e(_num(b["recovery_mae_pp"], 2)), _e(_num(b["constant_mae_pp"], 2))))
    p = c["plausibility"]
    a("<li>Проверка правдоподобия (балансы меди, воды, массы, энергии, пределы оборудования) на живых значениях: выполнено %s из %s, нарушено %s, нет данных %s</li></ul>" % (_e(p["ok"]), _e(p["total"]), _e(p["bad"]), _e(p["no_data"])))
    a("<h2>Данные и API</h2><ul>")
    for x in d["api"]:
        a('<li><a href="%s"><code>%s</code></a> — %s</li>' % (_e(x["url"]), _e(x["url"]), _e(x["shows"])))
    a("</ul></body></html>")
    return "".join(o)
