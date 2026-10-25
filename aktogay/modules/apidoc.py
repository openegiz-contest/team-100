"""API.md of the stand: the HTTP interface of akt-web and, for every module, what it reads (Ditto things, InfluxDB), what it
writes, which test keeps it (design notes of 22.10.2026). The text and `web/static/modules.json` (the live table on the
page «Как проверить») are written from the code: the lists of things come from the READS of the modules and the features
from `setup/things.json`, so they cannot drift; a test keeps both files equal to this module.

  python -I aktogay/modules/apidoc.py --write-md aktogay/web/API.md --write-json aktogay/web/static/modules.json
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import losses, ore, priority  # noqa: E402
from modules.params import default  # noqa: E402

LEAD_MIN = int(default()["handover_btn_lead_min"])

with open(os.path.join(ROOT, "setup", "things.json"), encoding="utf-8") as _f:
    TYPES = json.load(_f)["types"]


def feats(type_name: str) -> list[str]:
    return list(TYPES[type_name]["features"].keys())


def compact(names) -> str:
    return ", ".join(f"`{n}`" for n in names)


HTTP = (
    ("GET", "/healthz", "процесс жив; в Ditto не ходит"),
    ("GET", "/api/state", "все вещи `kz.aktogay:*` из Ditto (поиск, `size(200)`), кэш 1 с"),
    ("GET", "/api/thing?id=", "сырой JSON одной вещи"),
    ("GET", "/api/history?thing=&field=&range=&run=", "точки InfluxDB по `sim_time` (поля `value_<признак>_properties_value`)"),
    ("GET", "/api/journal?range=&run=", "строки `journal.last` из InfluxDB"),
    ("POST", "/api/scenario {id, preset?, kip?, safety?, auto?, speed?, seed?}",
     "`control.scenario`. `id` — токены через «+»; у токена может быть старт и величина: `crusher:1@90=4.5` "
     "(через 90 мин модели после 08:00, ремонт 4,5 ч; конструктор беды), `seed` — номер прогона"),
    ("POST", "/api/cancel, /api/reset {seed}, /api/speed {value}", "`control.cancel`, `control.reset`, `control.speed`"),
    ("POST", "/api/lever {feed_1, feed_2, p80_um, dose_gt, reset}", "`control.lever` (what-if levers of the model, not of the plant)"),
    ("POST", "/api/call {issue, role, text, via?}, /api/snooze {issue, role, reason}", "`journal.last` (action `call` или `snooze`)"),
    ("POST", "/api/remind {issue, role, text, next?}", "`journal.last` (action `remind` или `next`)"),
    ("POST", "/api/mech {issue, status, person?, text?}",
     "`journal.mech`: статус вызванного с экрана механика (`accepted`, `enroute`, `onsite`, `help`, `done`); модуль очереди "
     "читает его и показывает в жизненном цикле беды"),
)

MODULES = (
    {"id": "akt-sim", "title": "Симулятор фабрики", "rs": "команды `control`, `journal`", "ws": "все физические вещи, `site`", "code": "aktogay/sim/service.py", "thing": "site", "live": "heartbeat",
     "what": "Модель Актогая в модельном времени: считает фабрику, карьер и людей смены, публикует в Ditto каждую вещь и партию.",
     "reads": ["MQTT-события Ditto `control.*` (сценарий, скорость, сброс, отмена)", "`journal.last` (вызов, напоминание)",
               "`mod-priority.issue_map`, `mod-priority.auto_call` (вызов беды как бригады на узле; в «Два сразу» по ним идёт копия «по $», `AKT_FACT_POLICY=module`)"],
     "influx": "не читает",
     "writes": ["все физические вещи (`crusher-N`, `sag-N`, `line-N`, `water`, `power`, людей, технику) и партии",
                "`site` (`sim_time`, `speed_fact`, `scenario`, `heartbeat`)", "`baseline`, `validation-sim` (для режима проверки)"],
     "tests": ["tests/test_service.py", "tests/test_plant.py", "tests/test_publish.py", "tests/test_events.py"]},
    {"id": "akt-losses", "title": "Где теряется медь", "rs": f"{len(losses.READS)} вещей фабрики, партии; InfluxDB (окна)", "ws": "`mod-losses`", "code": "aktogay/modules/losses.py", "thing": "mod-losses",
     "live": "processed_sim_time",
     "what": "Ожидание по своей модели (Моррелл, Бонд, кинетика флотации) против измерений: находит скрытые и тихие потери по "
             "узлам, балансы меди и воды.",
     "reads": [compact(losses.READS) + " и партии `batch`"],
     "influx": "Flux по HTTP: дозаполнение окон после старта (поля " + compact(losses.BACKFILL_FIELDS[:8]) + " и др.)",
     "writes": ["`mod-losses` (" + str(len(feats("mod-losses"))) + " признаков: " + compact(feats("mod-losses")[:6]) + " …)"],
     "tests": ["tests/test_mod_losses.py", "tests/test_cusum.py", "tests/test_mod_expect.py", "tests/test_silent.py"]},
    {"id": "akt-ore", "title": "Какая руда идёт", "rs": f"{len(ore.READS)} вещей карьера и склада, партии; InfluxDB (окна)", "ws": "`mod-ore`", "code": "aktogay/modules/ore.py", "thing": "mod-ore", "live": "processed_sim_time",
     "what": "Слои склада, прогноз подачи на 12 ч и приход твёрдой руды к мельнице; «сбылось ли» по факту.",
     "reads": [compact(ore.READS) + " и партии `batch`"],
     "influx": "Flux по HTTP: дозаполнение окон (" + compact(ore.BACKFILL_FIELDS[:6]) + ") и история прогноза для «сбылось ли»",
     "writes": ["`mod-ore` (" + str(len(feats("mod-ore"))) + " признаков: " + compact(feats("mod-ore")[:6]) + " …)"],
     "tests": ["tests/test_mod_ore.py", "tests/test_ore.py"]},
    {"id": "akt-priority", "title": "Очередь бед", "rs": f"{len(priority.READS)} вещей, `mod-losses`, `mod-ore`, `journal`", "ws": "`mod-priority`, `issue-N`", "code": "aktogay/modules/priority.py", "thing": "mod-priority",
     "live": "processed_sim_time",
     "what": "Беды из состояний и находок, порядок вызова по деньгам и классам (люди, экология, деньги), кого звать и запасной, "
             "цена беды и её состав, жизненный цикл беды, прогнозы, лист сдачи смены.",
     "reads": [compact(priority.READS) + " и партии `batch`", "`mod-losses`, `mod-ore` (ждёт их `processed_sim_time`)",
               "`journal.last` (принять / отложить / напомнить), `journal.mech` (статус вызванного), `control.scenario.auto`"],
     "influx": "не читает (окна копит из опроса Ditto)",
     "writes": ["`mod-priority` (" + str(len(feats("mod-priority"))) + " признаков: " + compact(feats("mod-priority")[:6]) + " …, "
                f"`handover_btn` — кнопка «Сдать смену» за {LEAD_MIN} мин до конца смены; `alarm_flood` — события-тревоги смены "
                "(узел ушёл в ненорму) против бед в очереди и одной на главном, нижняя оценка)",
                "`issue-N` (" + str(len(feats("issue"))) + " признаков: " + compact(feats("issue")[:5]) + " …, `lifecycle`, `cost`, `checklist`, `closure`)"],
     "tests": ["tests/test_mod_priority.py", "tests/test_policy.py", "tests/test_forecast.py", "tests/test_features22.py",
               "tests/test_tier_s.py", "tests/test_readiness.py", "tests/test_scenarios.py", "tests/test_flood.py"]},
    {"id": "akt-calib", "title": "Калибровка и опыт «вкл/выкл»", "rs": "своя копия модели", "ws": "`validation-calib`", "code": "aktogay/sim/calib_report.py", "thing": "validation-calib",
     "live": "state",
     "what": "Разовая задача: таблица калибровки, проверка по кварталам и итог опыта на 100 парных сменах — в Ditto для страницы «Калибровка».",
     "reads": ["ничего из Ditto; считает на своей копии модели (код симулятора)"], "influx": "не читает",
     "writes": ["`validation-calib` (`state`, `shifts_done`, `shifts_total`, `report_json`)"],
     "tests": ["tests/test_calib_report.py", "tests/test_calib.py", "tests/test_backtest.py", "tests/test_trial.py"]},
    {"id": "akt-web", "title": "Интерфейс", "rs": "Ditto (поиск), InfluxDB (история)", "ws": "`control`, `journal`", "code": "aktogay/web/server.py", "thing": "", "live": "",
     "what": "Статические страницы и HTTP-прокси к Ditto и InfluxDB; единственные записи — команды `control` и `journal`.",
     "reads": ["Ditto (поиск вещей раз в 2 с)"], "influx": "Flux: история признаков и журнал вызовов",
     "writes": ["`control.scenario`, `control.speed`, `control.reset`, `control.cancel`", "`journal.last`, `journal.mech`"],
     "tests": ["tests/test_web.py", "tests/test_ui22.py", "tests/test_inside_ui.py"]},
    {"id": "akt-setup", "title": "Создание вещей", "rs": "`models/*.tm.jsonld`, `things.json`", "ws": "вещи `kz.aktogay:*`", "code": "aktogay/setup/setup.py", "thing": "validation-setup", "live": "things_ok",
     "what": "Из моделей типов (WoT Thing Models) создаёт политику и вещи Ditto, если их ещё нет.",
     "reads": ["файлы моделей `models/*.tm.jsonld` (через akt-models)", "`setup/things.json`"], "influx": "не читает",
     "writes": ["вещи `kz.aktogay:*` и `validation-setup`"], "tests": ["tests/test_twins.py", "tests/test_site.py"]},
)


def modules_json() -> str:
    out = []
    for m in MODULES:
        out.append({k: m[k] for k in ("id", "title", "code", "thing", "live", "what", "rs", "ws", "reads", "influx", "writes", "tests")})
    return json.dumps({"modules": out}, ensure_ascii=False, indent=1) + "\n"


def md_text() -> str:
    t = ["# API стенда «Актогай»: HTTP интерфейса и модули\n",
         "Файл пишет `aktogay/modules/apidoc.py`, руками не правится; тест сверяет его с кодом. Правило стенда (п. 6.2 положения): "
         "интерфейс и модули читают только Ditto и InfluxDB; писать они могут только в свои вещи.\n",
         "## HTTP API интерфейса (akt-web)\n", "| Запрос | Что делает |", "|---|---|"]
    for method, path, what in HTTP:
        t.append(f"| `{method} {path}` | {what} |")
    t.append("\nКаждая команда пишется merge-патчем на `/features` с заголовком `x-correlation-id: akt-web-<вещь>`; `seq` растёт на 1 от "
             "текущего значения в Ditto, поэтому повтор не исполняется дважды.\n")
    t.append("## Модули\n")
    t.append("| Модуль | Читает | Пишет | Тест | Живой статус |\n|---|---|---|---|---|")
    for m in MODULES:
        live = f"`{m['thing']}.{m['live']}`" if m["thing"] else "страница отвечает"
        t.append(f"| **{m['id']}** — {m['title']} | {m['rs']} | {m['ws']} | {', '.join('`' + x + '`' for x in m['tests'][:2])} | {live} |")
    t.append("\nЖивой статус каждого модуля — на странице «Как проверить» (раздел «Модули: живой статус»): время последнего такта в модельном "
             "времени, сколько секунд назад Ditto получил запись, тот ли прогон.\n")
    for m in MODULES:
        t.append(f"### {m['id']} — {m['title']}\n")
        t.append(f"{m['what']} Код: `{m['code']}`.\n")
        t.append("- **Вход из Ditto:** " + "; ".join(m["reads"]))
        t.append("- **Вход из InfluxDB:** " + m["influx"])
        t.append("- **Выход:** " + "; ".join(m["writes"]))
        t.append("- **Тест:** " + ", ".join(f"`{x}`" for x in m["tests"]))
        t.append("- **Живой статус:** " + (f"`{m['thing']}.{m['live']}` (страница «Как проверить»)" if m["thing"] else "запрос `/healthz`; страница работает, пока приходит `/api/state`"))
        t.append("")
    return "\n".join(t) + "\n"


def main(argv: list[str] | None = None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    done = False
    while a:
        k = a.pop(0)
        path = a.pop(0) if a else ""
        if k == "--write-md" and path:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(md_text())
            done = True
        elif k == "--write-json" and path:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(modules_json())
            done = True
        else:
            print("usage: apidoc.py [--write-md PATH] [--write-json PATH]")
            return 2
    if not done:
        print(f"ok: {len(MODULES)} modules, {len(HTTP)} http rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
