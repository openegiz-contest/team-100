# Aktogay model core: developer notes

Model core of the Aktogay sulphide concentrator stand: Python 3.11, standard
library only, deterministic for a given seed. It becomes the simulator
service (`akt-sim`) and the calibration job (`akt-calib`) when moved into the
team repository. The design is file 17 (sections named in each module).

## Layout

```
aktogay/
  run.py              entry point (works with python -I)
  README_dev.md
  sim/
    params.py         parameter table (value, min, max, unit, source, label), ParamSet,
                      reline calendar, feature -> rule list, PARAMETERS.md export
    state.py          dataclasses of the plant state, topology (things, parents, feeds),
                      initial_state(), PlantHooks, deterministic randomness
    comminution.py    crusher, SAG (Morrell energy, Austin power, load), pebble limit,
                      ball mills (Bond), cyclones
    flotation.py      rougher/cleaner kinetics, grade, tails, thickener, filter, concentrate stock
    ore.py            blocks with block-model error, plan, fleet (ready trucks, ore haul), haul,
                      belt, stockpile (draw column + sides), batches
    pit.py            trucks as a state machine on the aggregated haul, faces, haul roads, stripping
    haul.py           truck cycle from a calculation (24.10.2026): load + haul loaded (map distance, power-limited speed of the
                      793D from the Specalog) + queue + dump (body raise/lower) + return; one calibrated factor fleet_speed_eff
    plausibility.py   the 20 invariants of the live check (balances, limits, ranges with sources) -> web/static/plausibility.json;
                      web/static/plausibility.js evaluates them on the state read from Ditto
    fidelity.py       availability against Ausenco, SAG reline events, forward test on 2026, recovery refit, ore spread
                      -> data/fidelity.json (copy in web/static, shown by web/static/fidelity.js on «Калибровка»)
    influence.py      which parameters can change the conclusions: read counter + one-at-a-time screening -> data/influence.json
    people.py         people of the shift: FREE / TRAVEL / WORK / OFF, location, free time
    utilities.py      power balance, load shedding, water balance with pond, leak and fresh-water cap,
                      money, CO2
    wear.py           tier T of 24.10.2026: eight equipment troubles (gmd, idler, froth, rake, cloth, slurry, brake, track), scenario only;
                      rows in params_t.py (module rows in modules/params_t.py); cards in modules/readiness_t.py, scenarios_t.py, inside_t.py, tiers_t.py
    params_lev.py     rows of the what-if levers (lev_*); the levers themselves live in plant.py (set_levers), service.py (control.lever)
    events.py         scenario parsing and presets, hidden causes, random stops,
                      calib downtime, crews, copy call policies; tier S tokens (icy, fatigue, oil, roping:N,
                      phdrift:N, hpgr:2, mantle:N)
    sensors.py        noise, analyser, lab, control-system tails alarm, instruments (analysers,
                      weighers, flowmeters, piezometers), measured features, state_ru words
    site_aktogay.py   site passport: people, trucks by model, excavators, faces, roads, instruments,
                      the person responsible for each kind of node (library vs site, see below)
    plant.py          Plant (one copy, step order) and CopySet (fact/base/loud/no_twin)
    backtest.py       quarterly back-test 2018-2025 on the KAZ Minerals reports (data/kaz_quarterly.csv -> data/backtest_q.json)
    calib.py          2025 fit (availability, K, R0), 2024 fit (other load, evaporation),
                      2024 and 2023 checks without refit, 2025 site check, reline quarter,
                      quarters, balances, 7 days
    calib_report.py   akt-calib: calibration rows + trial summary -> validation-calib (Ditto HTTP)
    data/trial_n100.json   summary of `trial --n 100 --no-twin` (seeds 1001-1100), shown in ?view=calib
    replay.py         replay file «с двойником / без» from the stored rows of trial_n100.json (web/static/replay.json)
    verify.py         expected shift result of every catalog scenario (copies база / по $ / по громкости / без двойника, t Cu and $ by 20:00,
                      key moments, seed, code hash) computed by the same code as the stand -> web/static/verify.json; tests/test_doc_claims.py keeps it
                      equal to the script output and checks the scenario tables of SUBMISSION and VALIDATION against fresh CopySet runs
    detect_eval.py    the module «Где теряется медь» on hidden causes x lines x sizes x 25 seeds: detection share, delay, node/role matrix, false
                      alarms of control runs -> web/static/detect_eval.json (VALIDATION 8.14)
    cusum_eval.py     false alarms of the CUSUM against the stated 0.95 a week: Monte Carlo, free-run residuals, threshold curve -> web/static/cusum_eval.json (8.15)
    stock_sens.py     two readings of the PEK sentence about the ore stockpile (live 40 kt or 163 kt): scenarios under both -> sim/data/stock_sens.json (8.16)
    paramstat.py      labels of the parameter tables: fact / vendor / analog / project / calc / assumption (web/static/params_summary.json)
    publish.py        feature snapshots -> MQTT -> Ditto (catalog from setup/things.json, rate budget)
    service.py        akt-sim: Plant / CopySet in model time, commands from the control thing,
                      batches as things, baseline and validation-sim, barrier (optional)
    trial.py          on/off trial of the issue queue: "by value" vs "by loudness" vs "as now"
                      (fair baseline, default), paired seeds
  modules/
    tiers.py          troubles of tier S (winter road, tired driver, roping, pH sensor, HPGR, mantle, oil, excavator down)
                      and the evidence list with the age of every measurement of an issue card
    inside.py         the page «Изнутри»: nodes, signals with the place where each is seen, failures with sources, depth A/B/C;
                      writes web/static/inside.json (a test keeps it equal)
    readiness.py      the nine points of every new trouble; writes web/static/readiness.json and final_docs/READINESS.md
    scenarios.py      catalog of scenarios (what should happen, how to check) and the constructor of a trouble; writes web/static/scenarios.json
    apidoc.py         web/API.md (HTTP API and, per module, inputs, outputs, tests) and web/static/modules.json (live table of «Как проверить»)
  setup/
    things.json       types (library) and things of the site; gen=site things are generated
    gen_site.py       writes the generated things and responsible.person from sim/site_<name>.py
    gen_tm.py         models/*.tm.jsonld from things.json; setup.py creates the things in Ditto
  docker/sim.Dockerfile   image aktogay/sim:local (service by default); compose services akt-sim
                          and akt-calib (one shot: calib --quick --publish; own tag aktogay/calib:local, two services must not build one tag)
  tests/              unittest; one file per module, plus support.py and mod_support.py
```

## How the modules fit together

```
params ──► every module (numbers only from ParamSet; no literals)
state  ──► every module (dataclasses, initial_state, u01/normal/rng_at)

plant.Plant.step(dt):
  events  (due scenario events, hidden causes, pebble stops, downtime, crews, people)
  ore     (plan, fleet, regulator, dig, haul -> pocket); pit (trucks, faces, roads, stripping)
  comminution.crusher_step -> ore.convey_step (belt -> stockpile)
  ore.feed_props -> comminution.sag_step -> ore.reclaim_step
  comminution.ball_step -> cyclone_step -> flotation.flotation_step
  flotation thickener/filter/conc_stock -> utilities.power_balance, water_step
  sensors (analyser, lab) -> counters (utilities.value_usd) -> clock, shifts, hooks
calib -> Plant only (annual runs in mode "calib")
```

Rules shared by all modules:

- Units in names and docstrings: t/h, kW inside units, MW in balances, %,
  um, min (model time), h for durations in parameters.
- Every number comes from `sim/params.py`. New number = new row with value,
  min, max, unit, source and label (fact / vendor / project / analog /
  assumption / calc). `python -I aktogay/run.py params --check` must say ok.
- Randomness only from `state.u01 / normal / rng_at(seed, step, stream)`.
  Never `random.random()` or `hash()` of strings.
- Unit functions mutate only the state objects passed in. Truth fields
  (marked "truth" in `state.py`) never go to published features.
- Published values are float or str; "no value" is -1.0.

## Constructor of a trouble (sim/events.py)

A scenario token may carry a start and a magnitude: `kind[:N][@start_min][=magnitude]`, tokens joined by `+`, e.g.
`crusher:1@90=4.5+dose:2@120=0.3+grid=200`. `@` is model minutes after the start of the scenario (08:00), up to 20:00;
`=` replaces the default size of the trouble by the value of the table `events.MAGNITUDE` (kind -> slot, parameter row):
hours of the event or median repair time after arrival (`crusher`, `trip`, `conveyor`, `mantle`, `reline`, `pitstop`,
`icy`, `fatigue`, `dust`, `road`, `hpgr_fire`), MW (`grid`), A*b (`hard`), share (`water`, `leak`, `dose`, `liner`,
`energy`, `reagent`, `balls`), pp (`oxide`, `conc`), pH (`phdrift`), severity (`roping`), clogged cyclones (`cyclone`).
The value is kept inside `min..max` of its row; a kind without a magnitude (`hpgr`, `startup`, `sample`, `oil`,
`winter`) rejects `=`. The label of the run (`site.scenario`) keeps the bare kinds; the whole token stays in
`control.scenario.id`. `POST /api/scenario {id, seed}` writes it into `control` (seed -> `control.scenario.seed`).
`modules/scenarios.py` lists the nodes and ranges for the page «Сценарии» and a test compares them with the table.

## Run (from the folder that contains `aktogay/`)

```
python -I aktogay/run.py test                  # all unit tests
python -I aktogay/run.py test test_ore.py      # one file
python -I aktogay/run.py params --check        # table consistency
python -I aktogay/run.py params --md PARAMETERS.md
python -I aktogay/run.py calib --quick         # fast calibration table + calib.json
python -I aktogay/run.py calib --out calib.json   # full: step 10 min, about 4 min
python -I aktogay/run.py service --dry-run --duration 30 --speed 1200   # service without MQTT
python -I aktogay/run.py trial --n 100 --no-twin --library tier_s --jobs 5 --out trial.json   # main trial, symmetric base, about 6 min
python -I aktogay/sim/data/exp24/run_exp24.py    # the ten runs of VALIDATION 8.17 (about 55 min, 4 processes, below normal priority)
python -I aktogay/run.py exp24 --write aktogay/sim/data/experiment_24.json   # summary of exp24/*.json (and ladder/, nov24/)
python -I aktogay/scripts/reline_check.py       # per-day drop of the five reported SAG relines, regression, line-hours (VALIDATION 6.3, 6.8)
python -I aktogay/scripts/rec_baselines.py      # recovery baselines over backtest_q.json (VALIDATION 6.5)
python -I aktogay/run.py verify --write aktogay/web/static/verify.json --jobs 3   # expected scenario results; rerun after any change of the model (the test fails on a stale file)
python -I aktogay/run.py detect_eval --seeds 25 --jobs 4 --write aktogay/web/static/detect_eval.json   # about 10 min, below normal priority
python -I aktogay/run.py cusum_eval --jobs 4 --write aktogay/web/static/cusum_eval.json   # about 5 min
python -I aktogay/run.py stock_sens --jobs 4 --write aktogay/sim/data/stock_sens.json   # about 5 min
python -I aktogay/scripts/check_numbers.py [--list]   # every headline number of README, SUBMISSION and the presentation is in web/static/claims.json
python -I aktogay/scripts/measure_scenarios.py --out FILE.json   # on a running stand: time to the first trouble and whom to call, all catalog scenarios
python -I aktogay/run.py replay --write aktogay/web/static/replay.json        # replay of the trial shifts (no new trial)
python -I aktogay/run.py paramstat --write aktogay/web/static/params_summary.json   # labels of the parameter tables
python -I aktogay/run.py plausibility --write aktogay/web/static/plausibility.json   # invariants of the live check
python -I aktogay/run.py haul --calibrate      # parts of the truck cycle of every route and fleet_speed_eff for the 30 min reference
python -I aktogay/run.py backtest --jobs 4 && python -I aktogay/run.py fidelity --jobs 4   # then copy data/fidelity.json to web/static/
python -I aktogay/run.py influence --jobs 4   # about 60 min: every read model row, both edges, recovery refit family; copy data/influence.json to web/static/
python -I aktogay/modules/scenarios.py --write-json aktogay/web/static/scenarios.json
python -I aktogay/modules/apidoc.py --write-md aktogay/web/API.md --write-json aktogay/web/static/modules.json
python -I aktogay/setup/gen_site.py            # generated things of the site into setup/things.json
python -I aktogay/setup/gen_tm.py              # then the Thing Models
```

After a change to the model or to `modules/policy.py`, run the trial again and
copy `config, policy, n, seeds, notes, summary, cuts, loss_vs_base_cu_t_2000,
seconds` of trial.json into `sim/data/trial_n100.json` (the per-shift rows
stay out); the stand shows that file. Same seeds give the same numbers.

## Simulator service (akt-sim)

`sim/service.py` runs the plant in model time and publishes every physical
thing and live batch through `sim/publish.py` (command merge, so the feature
definitions from the Thing Models stay) with `idSimulationRun` and
`sim_time`. Points go out at every checkpoint (5 model min) and, at x60 and
below, between checkpoints as the rate budget allows (default 20 msg/s with
a ramp after connect: a point of about 55 messages takes about 3 s, so at
x60 a point lands every 3-4 model minutes, and above x60 the model waits
for the publisher: `site.speed_fact` tells the achieved speed, about x80 on
this stack). Warm-up 06:00 -> 08:00 publishes every 20 model minutes under
`site.state` WARMUP. The copies of a scenario (base, loud, no_twin) go only
to the `baseline` thing; `validation-sim.truth_log` after a hidden cause ends.
The site passport things keep the budget: people and instruments (17) go out
at checkpoints only, trucks, faces and roads (45) in rotation, a sixth at each
checkpoint (each one every 30 model minutes); the first point of a run, a
cancel and a pause carry every thing. A checkpoint is then about 75 messages
(was 55). `baseline.shift_result` of a free run carries the summary of the
current `idSimulationRun` only (the hook stores the run with the summary).
A call of an issue thing (`journal.last.issue = "issue-7"`, `auto_call`)
becomes a call at its node through `mod-priority.issue_map`; the plant finds
the issue there and books the crew (people twins follow the crew).

Tier S of 23.10.2026 (scenario tokens, all with a card of readiness in `modules/readiness.py`): `icy` (ice and snowstorm on
the haul roads for `scen_icy_h`: visibility, friction index, haul speed in `pit.*`; the season alone changes the road state but
not the throughput; the decision `Plant.call("pit")` restricts the traffic and closes the S0 trouble), `fatigue` (alert of a tired
driver of HT141, assumption), `oil` (hydraulic oil contamination of EX01, `exc-1.oil_pct` rising over `pit_oil_rise_h`; the pump
fails `pit_oil_fail_h` after the alert unless the shift mechanic is called, then the excavator is DOWN `pit_oil_repair_h`),
`roping:N` (cause kind `roping`: cyclone P80, pressure and circulating load up, ball mill draw above rating, after
`cyc_rope_escalate_h` the flotation loses `cyc_rope_flot_pp` for `cyc_rope_flot_h`; ended by a decision of the grinding operator),
`phdrift:N` (cause kind `phdrift`: the pH reading stays on the setpoint, the real pH is higher by `hc_ph_drift`, the grab sample
`ph-N.lab_ph` shows it; the I&C crew cleans the electrode), `hpgr:2` (uneven feed of the line 2 HPGR: skew and drive power difference
grow over `peb_hpgr_ramp_min`, the pebble circuit limit falls; after `peb_hpgr_tramp_after_h` without a repair the metal detector
trips and the HPGR stands `peb_hpgr_stop_h`), `mantle:N` (planned mantle change of crusher N, `crusher.service` = 1, about
`crush_mantle_h`). `roping` and `phdrift` are cause kinds set only by a scenario (never drawn in free run). The trial takes the
money kinds of the tier through `trial --library tier_s` (roping, phdrift, hpgr, mantle); the default library, and so the N = 100
summary, is unchanged.

Commands come as Ditto twin events on MQTT (`opentwins/twin/events/kz.aktogay/<thing>`):
`control.scenario {seq, id, preset, kip, auto, safety, speed}`, `control.speed
{seq, value}` (0 = pause, heartbeat every 2 s), `control.reset {seq, seed}`
(08:00, x60), `control.cancel {seq}`; `journal.last {seq, action: call,
issue}` and `mod-priority.auto_call {seq, issue}` book a crew on the fact
copy. A seq seen before is ignored. Scenario ids besides `crusher:N`, `grid`,
`hard:N`, `reline:N`, `trip:N`, `fork` and the hidden causes: `water`
(return-water pipeline leak: fresh water at its cap, ore cut, crew-water —
the tailings and water team led by person-water — repairs), `hpgr_fire` (fire at the HPGR of concentrator 1 as on 09.08.2026:
S0, pebble circuit of line 1 down, mill mechanic evacuated, line 2 runs on)
and `road:N` (ramp of line N closed, trucks on a detour), `conveyor:N` (the main belt of line N trips: `conveyor.fault` = 1, the crusher stands with an empty belt, crew-cpd repairs it in `conv_repair_h`; the stockpile carries the SAG) and `pitstop` (every ore excavator is DOWN for `scen_pitstop_h`: the chain pit -> haul -> crusher -> belt -> stockpile -> SAG shows when each line starves; the module raises `pit_stop`, called person: the mine dispatcher). Silent causes `energy:N` (SAG kWh/t +10 %), `reagent:N` (collector +40 % while the
flowmeter reads the setpoint) and `leak` (3 % of the pond return, no meter): also drawn in free run from their
own stream (`hc_silent_per_shift`); found only by the module balances. Scenario tokens of 23.10.2026: `winter` (return water 3 % lower, label in the header, `water.winter`; the season of a
run follows the host date unless `AKT_SEASON=winter|summer`), `dust` (windy dry beach for `scen_dust_h`), `startup:N` (planned
repair inside ball mill NA by the mill crew, work permit `person.permit`, start command `ball.start_cmd` after
`scen_startup_after_min`), silent causes set only by a scenario (never drawn in free run, so the free-run draws stay):
`balls:N` (grinding media g/t, `line.balls_gt`) and `conc:N` (concentrate grade lost to dilution). A journal call may carry
`via: deputy|head`: the crew gets one more team for that job (`Plant.call(via=...)`). `journal.last {action: remind | next}`
moves the arrival of a late called person (`Plant.remind`); late calls (`crew_late_p`) only on the live copy
(free run, training scenarios except "Two at once"). In compose the service sits on the
network `simnet` and sees only Mosquitto (`DITTO_URL` enables HTTP polling of
`control` where that is wanted). `AKT_BARRIER=mod-losses,mod-ore,mod-priority`
makes the model wait at every checkpoint for `processed_sim_time` of the
modules (60 s, then `site.degraded` = 1); off by default.

## On/off trial (sim/trial.py)

Paired shifts (seeds 1001...) with 2-3 troubles from the library of the
evidence map; copies "by value" (modules/policy.py through an adapter, the
stand-in money rule when the module is absent), "by loudness", optional
"no twin" and "base" share every draw (repair, arrival, notice from
(seed, issue)). Prints mean, median, SD, P10/P90, bootstrap 95 % CI (BCa),
p0, p-, Wilson intervals, the Wilcoxon test and cuts; writes JSON. Oxidised
ore is not in the library (no crew can end a preset oxide cause).

"No twin" is the fair baseline "as now" by default: people take the same
operating decisions without the twin, only when they see the trouble (grid
cut and reline 10 min after the start, `--asis-notice`; hard ore at the start
of digging, about 2 h after the start of the trouble, `--asis-hard dig`, or
when the block reaches the SAG, `--asis-hard sag`; a loud trouble by its alarm, 5-15 min). A grid call is repeated until the
SAG of the shed line gets the headroom (and the plant latches it,
`Plant._c2_call`). `--no-asis` gives the old baseline where nobody takes those
decisions (it overstated the gain).

Symmetric base (24.10.2026 evening, VALIDATION 8.17, `--twin-human same`, default): the twin is an addition to the people and knows a
trouble no later than they do (minimum of the two times); a loud trouble with a crew is known at the people's minute, silent dose and
cyclone troubles at the time the module measured (`web/static/detect_eval.json`, `trial.MODULE_FIND`) plus reading the card as an alarm,
roping, pH drift and HPGR skew at the people's minute. The cycle is forced to `fine_tact_min` (1 min) for every copy. `--twin-human none`
is the base of 8.8 (the twin sees a loud trouble in its first minute); the trial of 22.10.2026 is reproduced only with it.
Result of 22.10.2026 (N 100, seeds 1001-1100, `sim/data/trial_n100.json`): twin in all +1.26 t Cu per shift
[95 % BCa +1.06; +1.52], 93 % of shifts better, none worse; order alone
+0.08 [+0.05; +0.23] [model estimate; historical, library without tier S, asymmetric base]. Current main result (experiment of
24.10.2026, full library, symmetric base, `sim/data/experiment_24.json`, VALIDATION.md 8.17): twin minus as-now +0.61 t Cu per shift
[+0.23; +2.18], median +0.09, without the largest shift (seed 1066) +0.26; hard ore seen by the people only at the SAG:
+1.19 [+0.77; +2.81]. The earlier +1.07 [+0.89; +1.31] (`experiment_23.json`, 8.8) is kept as history. The pages read `web/static/exp23.json`
(`run.py exp23 --write`, built from both files). `--set`, `--hidden-mult`, `--mag` are the sensitivity options.

## Library vs site passport

The library is what any concentrator of this kind shares: the physics of
`sim/` (comminution, flotation, ore path, utilities, sensors, events, plant,
pit, people), the thing types and quantities of `setup/things.json` (`types`,
`quantities`, and the Thing Models in `models/` generated from them), and the
modules of `modules/`. The site passport is Aktogay itself:

- `sim/site_aktogay.py`: people of the shift and who answers for which kind
  of node, trucks by model (counts and payloads are parameter rows), ore and
  stripping excavators, faces, haul roads, instruments, piezometer offsets;
  bort numbers, drill rigs (DR01-DR04 Sandvik D55, DR12 Epiroc D65, DR31 Pit
  Viper 231) and dozers (DZ01 D9R, DZ21-DZ23 D10T, DZ41-DZ43 D375) by the
  company equipment list of 29.02.2024 (not exhaustive; trucks HT121, HT136-
  HT138, HT141, excavators EX01, EX51, EX53 are named there, the other units
  carry a conditional number); fleet size stays 37 trucks / 5 excavators of
  the 2024 press tour;
- `setup/things.json`: `sources`, `roles` and `things` (hand-written plant
  units with their passports; the `gen: site` things are written by
  `setup/gen_site.py` from the site file, together with
  `responsible.person` of every node);
- the site rows of `sim/params.py`: report targets (`tgt_*`), line rate and
  stockpile, equipment ratings (`sag_*`, `ball_*`, `crush_*`, `peb_*`),
  grid and water (`pow_*`, `water_*`, `pond_*`), the fleet (`fleet_*`,
  `pit_*`) — every row with value, range, unit, source and label.

Line 2 is not a copy of line 1 in the passport: FLSmidth package, gearless
mills, Wemco cells, thyssenkrupp POLYCOM HPGR 1 061 t/h 2 x 1 750 kW (vendor,
`peb_hpgr_l2_*`), gyratory 63 x 89 in by OVOS. Where no line-specific number
is published the physics uses the same rows for both lines.

How to add another site (no second site is built here):

1. Copy `sim/site_aktogay.py` to `sim/site_<name>.py`; change the lists
   (people and their crews, trucks by model with their parameter rows,
   excavators, faces, roads, instruments, `TYPE_PERSON`). Keep the thing ids
   of the plant units (`crusher-N`, `sag-N`, ...): the physics and the
   modules address them by these names.
2. Add the site rows to `sim/params.py` (or a copy of the table): new rows
   for new numbers, never a literal in code; `run.py params --check` must
   say ok. Fit rows (`fit=True`) are refitted by `run.py calib` on the
   site's own reports (`tgt_*`).
3. Write the site's `setup/things.json`: same `types` and `quantities`, its
   own `namespace`, `sources`, `roles` and hand-written plant things with
   their passports; then `AKT_SITE=<name> python -I aktogay/setup/gen_site.py`
   adds the generated things and `setup/gen_tm.py` the models.
4. Run the stand with `AKT_SITE=<name>` (simulator) and the new
   `setup/things.json` (`AKT_THINGS` for the simulator, the file for
   akt-setup and akt-modules); `run.py test` checks topology, features and
   things.json against each other (the counts in the tests are Aktogay's).

`python -I -m ...` does not see local packages (isolated mode drops the
current folder from `sys.path`), hence `run.py`. Plain discovery also works,
with or without `-t`: every test file puts `aktogay/` on `sys.path` first:
`python -I -m unittest discover -s aktogay/tests` (or `... -t aktogay`).

Slow tests (full calibration, 7 model days) run only with `AKT_SLOW=1`
(PowerShell: `$env:AKT_SLOW = "1"`).

Tests of not yet implemented functions are skipped, not failed (decorator
`needs_impl`); they become active as soon as the stub is replaced.

## Long run: what keeps the Ditto cluster up (23.10)

Incident of 23.10 (times UTC). Evidence, from `docker logs` and the Windows System log:

- 16:49:59 on: every JVM (policies, things-search, connectivity, gateway, things) logs "Scheduled sending of
  heartbeat was delayed", 2 s at first, then 15 s, 100 s (gateway), 570 s (things-search); the things service
  writes 27 000 log lines a minute until 16:49 and about 10 a minute after; gateway "Ask timed out after 30000 ms";
  16:53:21 "Marking node as UNREACHABLE" for four members. The stand had been using 2.0 of the 4 vCPU of the
  Docker VM (things 110 %, gateway 36 %, connectivity 20 %, search 15 %, mongodb 7 %) with nothing but its own
  reading; a headless Chrome with software WebGL ran on the same host, and the host was on battery.
- 17:03:27 the host went to sleep (Kernel-Power 42, "Critical Battery Trigger Met" 17:02:53), system time jumped
  from 17:03:52 to 17:15:35. Logs of gateway, things-search, connectivity, mongodb and nginx are empty from 17:03:44
  to 17:15:51: the whole VM stood still for 12 minutes.
- 17:16:22 on wake: "heartbeat interval is growing too large ... 47387 millis", every member UNREACHABLE, the split
  brain resolver waits its 8 s, downs the minority, the JVMs exit with code 0 (`akka.coordinated-shutdown.exit-jvm=on`),
  Docker restarts them (17:16:32 mongodb, 17:16:41 things, 17:16:51 connectivity, 17:17:26 gateway), healthy again
  within 2 minutes. This is the recovery the template describes in its own compose comments; no OOM, no crash.
  A host that sleeps cannot be helped by any failure detector setting short of 12 minutes, and a pause that long
  would blind the cluster to a real failure, so the template's Akka settings stay as they are.

So the restarts had a host cause (sleep) behind a stack with no CPU margin. What our services did to the margin,
and what changed:

| where | before | now |
|---|---|---|
| `modules/main.py` | whole twin (150 things, 0.4-0.5 MB) read every poll, a read took 1-3 s, back to back: 110 % of a core in things, 36 % in gateway | the 62 bulk things nobody reads (37 trucks, dozers, drills, faces, ramps, road, validation-*, baseline) are left out of the filter (`SEARCH_SKIP`, `search_filter`); a cheap read of the site clock (run, sim_time) each `POLL_S`, the twin is read when the clock moved and settled (`AKT_SETTLE_S` 2 s after the first change; a point is published over about 3 s), again after `AKT_RETRY_S` while a point is incomplete, at least every `AKT_MAX_AGE_S`; a read never takes more than `AKT_DUTY` of the wall time (`PollGate`) |
| `web/server.py` | each tab polled `/api/state` every 2 s, each answer waited for its own whole read under a lock (1 s cache): with a page open 30 whole reads a minute on top of the modules | one thread reads the twin while somebody asks and all tabs get the last read as ready bytes: the 88 live things every `AKT_STATE_REFRESH_S` (3 s), the 62 things published in rotation (trucks, faces, ramps, drills, dozers, dump road, validation-calib) every `AKT_STATE_SLOW_S` (10 s); older than `AKT_STATE_STALE_S` (30 s) the tab is told "no link"; journal and history answers from InfluxDB are cached `AKT_INFLUX_CACHE_S` (5 s) |
| `web/static/diorama/core.js`, `site3d.js` | the 3D diorama on software WebGL (a browser without a graphics card; headless Chrome with `--disable-gpu`) took 4.1 cores at 30 frames a second; the scheme pages and the text pages take 0.1-0.2 | the diorama starts in its light mode when WebGL is software (8 frames a second, lower resolution: 0.9 cores), the button gives the full look back, a choice made by hand is remembered; the satellite 3D view (3.2 cores) draws 8 frames a second on software WebGL |
| `sim/service.py` | a batch delete went out 4 times; the 3 after the one that worked each failed in Ditto with ThingNotAccessible, a WARN with a stack and dead letters (the "batch-0021 could not be found" lines) | `BATCH_DELETE_REPEATS = 1` |

Batches. `batch-00NN` are made and deleted by akt-sim alone (`modify /` with policyId when the plant makes one,
again at the next 2 checkpoints and once per model hour; `delete /` when the plant drops it); akt-setup must not create
them (numbers restart at 0001 in every process; the first point of a process deletes 0001..0099). Merges to a batch
that Ditto does not have appear only after a Ditto restart (the cold cluster cannot load the thing for a minute,
17:17:52-17:18:01 in the incident) and stop by themselves at the next hourly re-create; the sim never writes to a
batch after it deleted it (`tests/test_load.py`).

Overlay `compose.yml` (the template files are untouched), each line with its reason:

- `logging: json-file, max-size 20m, max-file 3` on every long-running service: the things log was 10 GB after a
  day (it is not rotated by default); with rotation a day costs at most 60 MB per service.
- `LOG_LEVEL_APPLICATION: WARN` on policies, things, things-search, connectivity, gateway: INFO of `org.eclipse.ditto`
  wrote three lines per retrieved thing and two per command (260 lines/s, 220 MB/h in things alone); akka and
  cluster messages (Unreachable, SBR, shutdown) use other loggers and stay.
- `cpu_shares: 4096` on the five Ditto services, mongodb and mosquitto: when something else on the machine wants
  the CPU (a browser rendering WebGL in software on the same VM, the case on a contest VM), these get four times
  the weight of an ordinary process, so the cluster heartbeat is not starved first.
- `akt-modules` environment: the four poll knobs above, set to their defaults so they are visible.

Not changed, deliberately: Akka failure detector, SBR, heaps and memory limits of the template (see its comments).

Measured on the 4 vCPU / 5.9 GiB Docker VM, free run x60, AC power (CPU of the containers, mean over 45 s, no browser):
before things 110 %, gateway 36 %, connectivity 20 %, things-search 15 %, mongodb 7 % (sum 200 % of 400 %);
after things 43 %, gateway 11 %, connectivity 20 %, things-search 15 %, mongodb 6-15 % (sum 116 %). The twin is read
about 1 500 times a minute by the modules (90 things, once per published point) instead of about 1 800 plus 4 500
for an open page, and the 62 rotation things cost the most per read. 10-minute smoke with a GPU-less headless Chrome
(`--disable-gpu`) cycling plan, diorama, satellite 3D and line pages, re-loaded every 2 minutes: no restart, Ditto GET of
a thing p95 177 ms (max 264 ms), `/api/state` at most 28 ms, InfluxDB query at most 298 ms, the interface never showed
"нет связи с двойником". Peaks seen: things 139 % of a core (560 of 768 MiB), connectivity 640 of 896 MiB, gateway 517
of 768 MiB. The contest VM (8 vCPU, 16 GiB) has twice the CPU and more than twice the memory of this one. The first
3 minutes after a cold start of the Ditto services are heavier (JIT, caches; the ramp of the publisher): on the first
deploy of 23.10 a page opened at that moment waited 15 s once; a page opened after those minutes did not.

Operational requirements (for the README): the machine must not sleep or hibernate while the stand runs (a stopped
clock is seen by Akka as 12 minutes without heartbeats); at least 4 vCPU and 6 GiB for Docker (measured peak below),
the template's contest VM has 8 vCPU and 16 GiB; a browser on the same machine takes CPU from the stand.

## What-if levers and equipment troubles (24.10.2026)

Levers (`?view=levers`, «Пульт модели» → «Рычаги модели»): SAG feed per line 80-120 % of the line rate, grind P80 target 160-200 um,
collector dose 15-40 g/t. They steer the model, not the plant: off by default (a neutral value is not stored, the model stays
byte-identical), clamped to the `lev_*` rows, reset with a scenario cancel. `POST /api/lever {feed_1, feed_2, p80_um, dose_gt, reset}`
writes `control.lever` into Ditto, `akt-sim` applies it to the fact copy only; the first lever of a free run starts the base copy of
the same minute without levers, so «база / с рычагами / разница» is the usual copy difference. The advice button
(`modules/lever_advice.py`, `web/static/lever.js`) only posts the same call; the modules never write levers.
P80 slope: lab 1.2 pp per 10 um (Bozshakol composite), plant regression 1.95 pp (both shown); reagent price is an assumption
(`lev_reagent_usd_t`); the Volza / ITB / ScienceDirect pages did not open (`gaps/facts_round2.md`, «Реагенты»).
Troubles of tier T are scenario tokens (never drawn in free run, so the N = 100 summary is unchanged): signal ramps from normal to
alert, the consequence follows unless the called role fixes it; thresholds are examples or assumptions as labelled in the cards.

## Parallel work

Each component owns its files; nobody edits another component's file. Shared
files `params.py` and `state.py` change only by adding rows or fields
(tell the others). The acceptance numbers in the tests come from design
sections 4 and 7: base line 3853 t/h, E_SAG 6.75 kWh/t, P80 179 um,
recovery 87.2 %, tails 0.053 % Cu, site 260 of 300 MW (other load = site
part 54.6 MW fitted on 2024 + 28.5 MW per running line), C1 stock 3 h 00 min,
C2 210 of 218 MW, C3 2960 t/h, C4 -99 MW (mills 70 + line part 28.5),
fork tails 0.068 % below the 0.075 % alarm.

Calibration choices (design section 4, revised):
- 2025 feed grade 0.4068 % = 220.3 kt / (62.1 Mt x 87.2 %) (`tgt_2025_feed_pct`);
  the report grade 0.41 % is rounded. 2024 and 2023 checks use the report grades.
- Other load and pond evaporation are fitted on 2024 (ore, electricity and
  water all published); 2023 ore is not in the sources, so the 2023 check
  takes it from the 2023 electricity. The other load has a site part (fitted)
  and a line part (`pow_line_aux_mw`, from the line 2 EIA electricity) that
  stops with its line.
- Grade term: Josemaria 4.093 pp per ln(g / g0) on total recovery (analog),
  ASCu -1.043 pp per pp on total recovery; both enter R_inf divided by
  k_base c_base. The grade-recovery line of the concentrate does not trade
  the feed-grade gain. With this slope the 2024 recovery check misses
  (-0.7 pp) and 2023 holds; the constant-tails bound 12.8 would pass 2024 and
  miss 2023 (+1.8 pp). No single grade slope explains both years.
- SAG reline is 84 h (24.10.2026; analog: Minera Chinalco Peru, Metso Outotec case study, 84 h done against 96 h planned; one vendor case);
  it was 96 h (assumption, RME benchmark). It is not taken from the Q3 2025 quarter change, so the reline check is not closed on itself.
- SAG: J0 25 % (Bradken); the 12 % ball charge stays when the ore grinds out
  (power floor about 69 % of P0); under a power cap below that the control
  slows the mill. A stopped mill keeps its charge. Bond energy is capped at
  `ball_p80_min_um` (cyclones limit the overflow on small feed).
- Block draws are mean-preserving lognormals; the Cu clamp band scales with
  the year grade.
- Tails lock their pore water only (0.31 m3/t at dry 1.45 t/m3, SG 2.66).

## Modules keep up with the simulator (24.10)

Seen on the stand under load: `mod-losses` and `mod-priority` stood 80-100 model minutes behind the site, and a stopped
crusher had an empty queue for about 75 model minutes. Cause: a tact waited for the newest point that ANY thing showed
(`floor(max sim_time)`), and a point is published over 3-4 s, so under load a read almost never found that point complete;
the module skipped the cycle and the next read met the next half-published point. `mod-priority` also waited for the exact
point of `mod-losses`/`mod-ore`. Now (`modules/main.py`):

- `Runner._span` / `due`: the point of a tact is the newest one EVERY thing of the module's reads has reached
  (`floor(min sim_time)` on the module's tact); older points are skipped, not replayed; the newer one, still being
  published, sets `incomplete` so the next read comes after `AKT_RETRY_S`. One tact per module per cycle: the work per cycle is bounded.
- `priority_point`: `mod-priority` computes at the newest point not past `mod-losses.processed` and not past
  `mod-ore.processed + 10` (the 15-min tact of the ore module); it never waits for an exact point.
- `watch_lag`: one WARNING a minute while a module is more than 30 model minutes behind the site.
- The interface shows the lag: `AKT.moduleLag()` (site `sim_time` minus `processed_sim_time` of each module) on the page
  «Модули» and, above 20 model minutes, as a chip in the context line.

Measured at x60, free run and scenarios, `processed_sim_time` against the site (model minutes), sampled every 4-6 s:

| | median | p95 | max |
|---|---|---|---|
| before (one module, 100 s, no extra load) | 60 | 100 | 105 |
| after (same stand, 100 s) | 10 | 20 | 25 |
| after, scenario `crusher:1` from the click | trouble of the crusher in the queue 61 s after the click (16 s after the shift starts), model 08:10 | | |

What is left (10-20 model minutes) is the read cycle: settle 2 s + a read of 1-3 s + the duty rest (`AKT_DUTY` 0.3): a
read every 6-12 s; shortening it costs Ditto CPU, which is what the 23.10 incident was about.

## Shell scripts for the repository sync

`aktogay/scripts/akt-check.sh`, `akt-preflight.sh`, `akt-urls.sh` must be executable in the repository (the Windows
working copy cannot carry the bit): after copying the folder into the Team Repository run
`git update-index --chmod=+x aktogay/scripts/akt-check.sh aktogay/scripts/akt-preflight.sh aktogay/scripts/akt-urls.sh`.
The Makefile calls them as `bash <script>`, so a repository without the bit still works.

## Known gaps (TODO)

- Tier S (23.10.2026): the thresholds of the new troubles (visibility 150 m, friction 0.40, circulating load 320 %, skew 6 %, pH gap
  0.3, oil failure 8 h after the alert) and the size of their effects are assumptions of the stand (63 of the 78 new parameter rows; two of the 64 of 23.10.2026, scen_icy_wind_ms and scen_icy_temp_c, became calc on 24.10.2026, VALIDATION 10.2);
  the sources name the risks, not the numbers. The trial library has the money kinds of the tier as an opt-in (`--library tier_s`),
  the N = 100 summary in `sim/data/trial_n100.json` was not recomputed for them. A blocked analyser sample line (`sample:N`) is a
  deviation without a price; the tired driver (`fatigue`) is a scenario, its sensor is not confirmed by any source.
- 2023 ore is not in the sources: the 2023 check derives it from the 2023
  electricity; add the KAZ FY2023 figure to make the 2023 water check independent.
- Feed-end changes at intermediate relines only restart the wear counter;
  their downtime sits inside the fitted availability.
- Quarter grades, ore and recovery of 2018-2025 are in `sim/data/kaz_quarterly.csv` (32 reports, URL and page per row);
  the back-test of the 28 quarters outside the 2025 fit is `sim/backtest.py` (`run.py backtest`, result
  `sim/data/backtest_q.json`, VALIDATION.md 6.1). The SAG stop calendar still holds 2024-2025 only.
- Stop days within the month are assumptions; the reports name one SAG
  reline (line 2, August 2025) and one planned SAG maintenance (line 2,
  October 2024); the other calendar stops are planned maintenance whose kind
  of work is not disclosed (`RELINE_CALENDAR`, field `kind`).
- Daily load profile (Zenodo) and GeoMet block distribution are not wired yet.
- Number and places of the dam piezometers, the return water pipeline and the shift roster by role are not published: they are
  assumptions of the site file (labelled so). The truck fleet is the one of 06.06.2024; the 2026 fleet is not confirmed.
- Haulage (24.10.2026): the cycle is calculated per route by `sim/haul.py` from the map distance (`plan.json`, label «расчёт по карте»),
  the 793D Specalog (power, weight, body times) and the 236 t payload of the annual report 2020. Still open: the speed on the ramp is
  power limited by formula (the retarding and rimpull charts of the Specalog are images and were not read as numbers), `fleet_speed_eff`
  (0.516) is calibrated to the former 30 min cycle, `pit_haul_min` (dig to crusher lag, 30 min) is still a constant shared with the
  modules table, the 785 and 777 trucks use the cycle of the 793D.
- Ore stockpile (24.10.2026): the model reads the PEK «рабочий объём 163 000 т» as the whole pile and keeps 40 kt live (`stock_live_t`,
  assumption). If «рабочий» means live, the twin benefit of the main trial on the symmetric base goes from +0.61 [+0.23; +2.18] to +0.59 [+0.21; +2.32] t Cu per shift (hard ore at the SAG: +1.19 to +1.06) and
  the losses of C1, belt, mantle change and pit stop vanish (VALIDATION 8.16, `sim/stock_sens.py`, `sim/data/stock_sens*.json`). Not decided:
  a stockpile passport or a daily level log is needed. The seed 42 table of scenario results is one run; C1 loses -15.2 t Cu on average over 10 seeds.
- Detector (24.10.2026): `cusum_h` is an assumption, not a calculation: 2.8 false alarms a week for independent z (5.4 with the fast threshold),
  about 30 a week on the residuals of the twin, flat in h (VALIDATION 8.15). A detector on the change of the residual or an ore-error term in sigma is not built.
- Crusher availability (24.10.2026): "in work" is the hour meter (crushed ore / rated rate), 80.8 % at 4 386 t/h and 70.2 % at 5 044 t/h
  (OVOS range; the range is the design rate of the crushing area with the factor 1.15, not a crusher nameplate, and no nameplate was found)
  against 65.1 % of the hours of a year in the OVOS design (285 d x 2 shifts x 10 h; KIO 0.78 is a share of days) and 70-75 % in the Ausenco
  design basis: a requirement of the reported ore on the equipment, with no tolerance verdict (VALIDATION 6.2); own stops (short stoppages, planned maintenance while the mill stands, liner change
  inside the first SAG reline of the year) exist only in the calib run (`Plant._crusher_own_stops`, rows `crush_plan_*`, `crush_stop_*`), and the 2025
  fit answers with cal_avail 0.9298 (0.9225 before). VALIDATION 6.2.
- `liner_reline_h` was 96 h and overstated the drop of the ore of a line in the five reported SAG relines (-6.3 % against -4.8 %, VALIDATION
  6.3); changed to 84 h (Minera Chinalco, actual) on 24.10.2026 in `sim/params.py`, `modules/params.py`, `modules/scenarios.py` and the texts (-5.5 %). The same holds for `conv_repair_h`, `w_idler_fix_h` and `w_slurry_fix_h`, whose
  notes now carry the verified analogs (D1, D4) but whose value and label cannot change here.
- Mine-plan variability of the ore (`blk_plan_*`) is off by default and used only in the spread check of `sim/fidelity.py`.
- Detection rate, false alarms and the cause -> node matrix need the losses
  module; they are added to `calib` later.
