# API стенда «Актогай»: HTTP интерфейса и модули

Файл пишет `aktogay/modules/apidoc.py`, руками не правится; тест сверяет его с кодом. Правило стенда (п. 6.2 положения): интерфейс и модули читают только Ditto и InfluxDB; писать они могут только в свои вещи.

## HTTP API интерфейса (akt-web)

| Запрос | Что делает |
|---|---|
| `GET /healthz` | процесс жив; в Ditto не ходит |
| `GET /api/state` | все вещи `kz.aktogay:*` из Ditto (поиск, `size(200)`), кэш 1 с |
| `GET /api/thing?id=` | сырой JSON одной вещи |
| `GET /api/history?thing=&field=&range=&run=` | точки InfluxDB по `sim_time` (поля `value_<признак>_properties_value`) |
| `GET /api/journal?range=&run=` | строки `journal.last` из InfluxDB |
| `POST /api/scenario {id, preset?, kip?, safety?, auto?, speed?, seed?}` | `control.scenario`. `id` — токены через «+»; у токена может быть старт и величина: `crusher:1@90=4.5` (через 90 мин модели после 08:00, ремонт 4,5 ч; конструктор беды), `seed` — номер прогона |
| `POST /api/cancel, /api/reset {seed}, /api/speed {value}` | `control.cancel`, `control.reset`, `control.speed` |
| `POST /api/lever {feed_1, feed_2, p80_um, dose_gt, reset}` | `control.lever` (what-if levers of the model, not of the plant) |
| `POST /api/call {issue, role, text, via?}, /api/snooze {issue, role, reason}` | `journal.last` (action `call` или `snooze`) |
| `POST /api/remind {issue, role, text, next?}` | `journal.last` (action `remind` или `next`) |
| `POST /api/mech {issue, status, person?, text?}` | `journal.mech`: статус вызванного с экрана механика (`accepted`, `enroute`, `onsite`, `help`, `done`); модуль очереди читает его и показывает в жизненном цикле беды |

Каждая команда пишется merge-патчем на `/features` с заголовком `x-correlation-id: akt-web-<вещь>`; `seq` растёт на 1 от текущего значения в Ditto, поэтому повтор не исполняется дважды.

## Модули

| Модуль | Читает | Пишет | Тест | Живой статус |
|---|---|---|---|---|
| **akt-sim** — Симулятор фабрики | команды `control`, `journal` | все физические вещи, `site` | `tests/test_service.py`, `tests/test_plant.py` | `site.heartbeat` |
| **akt-losses** — Где теряется медь | 32 вещей фабрики, партии; InfluxDB (окна) | `mod-losses` | `tests/test_mod_losses.py`, `tests/test_cusum.py` | `mod-losses.processed_sim_time` |
| **akt-ore** — Какая руда идёт | 21 вещей карьера и склада, партии; InfluxDB (окна) | `mod-ore` | `tests/test_mod_ore.py`, `tests/test_ore.py` | `mod-ore.processed_sim_time` |
| **akt-priority** — Очередь бед | 43 вещей, `mod-losses`, `mod-ore`, `journal` | `mod-priority`, `issue-N` | `tests/test_mod_priority.py`, `tests/test_policy.py` | `mod-priority.processed_sim_time` |
| **akt-calib** — Калибровка и опыт «вкл/выкл» | своя копия модели | `validation-calib` | `tests/test_calib_report.py`, `tests/test_calib.py` | `validation-calib.state` |
| **akt-web** — Интерфейс | Ditto (поиск), InfluxDB (история) | `control`, `journal` | `tests/test_web.py`, `tests/test_ui22.py` | страница отвечает |
| **akt-setup** — Создание вещей | `models/*.tm.jsonld`, `things.json` | вещи `kz.aktogay:*` | `tests/test_twins.py`, `tests/test_site.py` | `validation-setup.things_ok` |

Живой статус каждого модуля — на странице «Как проверить» (раздел «Модули: живой статус»): время последнего такта в модельном времени, сколько секунд назад Ditto получил запись, тот ли прогон.

### akt-sim — Симулятор фабрики

Модель Актогая в модельном времени: считает фабрику, карьер и людей смены, публикует в Ditto каждую вещь и партию. Код: `aktogay/sim/service.py`.

- **Вход из Ditto:** MQTT-события Ditto `control.*` (сценарий, скорость, сброс, отмена); `journal.last` (вызов, напоминание); `mod-priority.issue_map`, `mod-priority.auto_call` (вызов беды как бригады на узле; в «Два сразу» по ним идёт копия «по $», `AKT_FACT_POLICY=module`)
- **Вход из InfluxDB:** не читает
- **Выход:** все физические вещи (`crusher-N`, `sag-N`, `line-N`, `water`, `power`, людей, технику) и партии; `site` (`sim_time`, `speed_fact`, `scenario`, `heartbeat`); `baseline`, `validation-sim` (для режима проверки)
- **Тест:** `tests/test_service.py`, `tests/test_plant.py`, `tests/test_publish.py`, `tests/test_events.py`
- **Живой статус:** `site.heartbeat` (страница «Как проверить»)

### akt-losses — Где теряется медь

Ожидание по своей модели (Моррелл, Бонд, кинетика флотации) против измерений: находит скрытые и тихие потери по узлам, балансы меди и воды. Код: `aktogay/modules/losses.py`.

- **Вход из Ditto:** `site`, `line-1`, `line-2`, `sag-1`, `sag-2`, `pebble-1`, `pebble-2`, `ball-1a`, `ball-1b`, `ball-2a`, `ball-2b`, `cyclones-1`, `cyclones-2`, `flot-1`, `flot-2`, `rougher-1`, `rougher-2`, `cleaner-1`, `cleaner-2`, `stockpile-1`, `stockpile-2`, `thick-1`, `thick-2`, `filter-1`, `filter-2`, `conc-stock`, `water`, `power`, `crusher-1`, `crusher-2`, `conveyor-1`, `conveyor-2` и партии `batch`
- **Вход из InfluxDB:** Flux по HTTP: дозаполнение окон после старта (поля `feed_tph`, `power_kw`, `p80_um`, `feed_cu`, `tail_cu`, `conc_cu`, `dose_meas_gt`, `dose_sp_gt` и др.)
- **Выход:** `mod-losses` (62 признаков: `sag-1_gap_cu_tph`, `sag-1_gap_usd_h`, `sag-1_sigma`, `sag-1_status`, `sag-1_status_ru`, `sag-1_roles` …)
- **Тест:** `tests/test_mod_losses.py`, `tests/test_cusum.py`, `tests/test_mod_expect.py`, `tests/test_silent.py`
- **Живой статус:** `mod-losses.processed_sim_time` (страница «Как проверить»)

### akt-ore — Какая руда идёт

Слои склада, прогноз подачи на 12 ч и приход твёрдой руды к мельнице; «сбылось ли» по факту. Код: `aktogay/modules/ore.py`.

- **Вход из Ditto:** `site`, `pit`, `exc-1`, `exc-2`, `exc-3`, `fleet`, `crusher-1`, `crusher-2`, `conveyor-1`, `conveyor-2`, `stockpile-1`, `stockpile-2`, `sag-1`, `sag-2`, `pebble-1`, `pebble-2`, `power`, `line-1`, `line-2`, `flot-1`, `flot-2` и партии `batch`
- **Вход из InfluxDB:** Flux по HTTP: дозаполнение окон (`feed_tph`, `axb_soft`, `level_t`, `in_tph`, `out_tph`, `state`) и история прогноза для «сбылось ли»
- **Выход:** `mod-ore` (24 признаков: `next_hard_eta_early_h_l1`, `next_hard_eta_early_h_l2`, `next_hard_eta_h_l1`, `next_hard_eta_h_l2`, `next_hard_axb`, `fc_tph_h1` …)
- **Тест:** `tests/test_mod_ore.py`, `tests/test_ore.py`
- **Живой статус:** `mod-ore.processed_sim_time` (страница «Как проверить»)

### akt-priority — Очередь бед

Беды из состояний и находок, порядок вызова по деньгам и классам (люди, экология, деньги), кого звать и запасной, цена беды и её состав, жизненный цикл беды, прогнозы, лист сдачи смены. Код: `aktogay/modules/priority.py`.

- **Вход из Ditto:** `site`, `pit`, `exc-1`, `exc-2`, `exc-3`, `fleet`, `crusher-1`, `crusher-2`, `conveyor-1`, `conveyor-2`, `stockpile-1`, `stockpile-2`, `line-1`, `line-2`, `sag-1`, `sag-2`, `pebble-1`, `pebble-2`, `ball-1a`, `ball-1b`, `ball-2a`, `ball-2b`, `cyclones-1`, `cyclones-2`, `flot-1`, `flot-2`, `rougher-1`, `rougher-2`, `cleaner-1`, `cleaner-2`, `thick-1`, `thick-2`, `filter-1`, `filter-2`, `conc-stock`, `water`, `power`, `crew-kip`, `crew-cpd`, `crew-mill`, `crew-water`, `ph-1`, `ph-2` и партии `batch`; `mod-losses`, `mod-ore` (ждёт их `processed_sim_time`); `journal.last` (принять / отложить / напомнить), `journal.mech` (статус вызванного), `control.scenario.auto`
- **Вход из InfluxDB:** не читает (окна копит из опроса Ditto)
- **Выход:** `mod-priority` (23 признаков: `queue_text`, `order_text`, `alarm_order_text`, `auto_call`, `issue_map`, `handover` …, `handover_btn` — кнопка «Сдать смену» за 60 мин до конца смены; `alarm_flood` — события-тревоги смены (узел ушёл в ненорму) против бед в очереди и одной на главном, нижняя оценка); `issue-N` (28 признаков: `status`, `status_ru`, `node`, `kind`, `safety_class` …, `lifecycle`, `cost`, `checklist`, `closure`)
- **Тест:** `tests/test_mod_priority.py`, `tests/test_policy.py`, `tests/test_forecast.py`, `tests/test_features22.py`, `tests/test_tier_s.py`, `tests/test_readiness.py`, `tests/test_scenarios.py`, `tests/test_flood.py`
- **Живой статус:** `mod-priority.processed_sim_time` (страница «Как проверить»)

### akt-calib — Калибровка и опыт «вкл/выкл»

Разовая задача: таблица калибровки, проверка по кварталам и итог опыта на 100 парных сменах — в Ditto для страницы «Калибровка». Код: `aktogay/sim/calib_report.py`.

- **Вход из Ditto:** ничего из Ditto; считает на своей копии модели (код симулятора)
- **Вход из InfluxDB:** не читает
- **Выход:** `validation-calib` (`state`, `shifts_done`, `shifts_total`, `report_json`)
- **Тест:** `tests/test_calib_report.py`, `tests/test_calib.py`, `tests/test_backtest.py`, `tests/test_trial.py`
- **Живой статус:** `validation-calib.state` (страница «Как проверить»)

### akt-web — Интерфейс

Статические страницы и HTTP-прокси к Ditto и InfluxDB; единственные записи — команды `control` и `journal`. Код: `aktogay/web/server.py`.

- **Вход из Ditto:** Ditto (поиск вещей раз в 2 с)
- **Вход из InfluxDB:** Flux: история признаков и журнал вызовов
- **Выход:** `control.scenario`, `control.speed`, `control.reset`, `control.cancel`; `journal.last`, `journal.mech`
- **Тест:** `tests/test_web.py`, `tests/test_ui22.py`, `tests/test_inside_ui.py`
- **Живой статус:** запрос `/healthz`; страница работает, пока приходит `/api/state`

### akt-setup — Создание вещей

Из моделей типов (WoT Thing Models) создаёт политику и вещи Ditto, если их ещё нет. Код: `aktogay/setup/setup.py`.

- **Вход из Ditto:** файлы моделей `models/*.tm.jsonld` (через akt-models); `setup/things.json`
- **Вход из InfluxDB:** не читает
- **Выход:** вещи `kz.aktogay:*` и `validation-setup`
- **Тест:** `tests/test_twins.py`, `tests/test_site.py`
- **Живой статус:** `validation-setup.things_ok` (страница «Как проверить»)

