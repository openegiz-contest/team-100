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
    people.py         people of the shift: FREE / TRAVEL / WORK / OFF, location, free time
    utilities.py      power balance, load shedding, water balance with pond, leak and fresh-water cap,
                      money, CO2
    events.py         scenario parsing and presets, hidden causes, random stops,
                      calib downtime, crews, copy call policies
    sensors.py        noise, analyser, lab, control-system tails alarm, instruments (analysers,
                      weighers, flowmeters, piezometers), measured features, state_ru words
    site_aktogay.py   site passport: people, trucks by model, excavators, faces, roads, instruments,
                      the person responsible for each kind of node (library vs site, see below)
    plant.py          Plant (one copy, step order) and CopySet (fact/base/loud/no_twin)
    calib.py          2025 fit (availability, K, R0), 2024 fit (other load, evaporation),
                      2024 and 2023 checks without refit, 2025 site check, reline quarter,
                      quarters, balances, 7 days
    calib_report.py   akt-calib: calibration rows + trial summary -> validation-calib (Ditto HTTP)
    data/trial_n100.json   summary of `trial --n 100 --no-twin` (seeds 1001-1100), shown in ?view=calib
    publish.py        feature snapshots -> MQTT -> Ditto (catalog from setup/things.json, rate budget)
    service.py        akt-sim: Plant / CopySet in model time, commands from the control thing,
                      batches as things, baseline and validation-sim, barrier (optional)
    trial.py          on/off trial of the issue queue: "by value" vs "by loudness" vs "as now"
                      (fair baseline, default), paired seeds
  setup/
    things.json       types (library) and things of the site; gen=site things are generated
    gen_site.py       writes the generated things and responsible.person from sim/site_<name>.py
    gen_tm.py         models/*.tm.jsonld from things.json; setup.py creates the things in Ditto
  docker/sim.Dockerfile   image aktogay/sim:local (service by default); compose services akt-sim
                          and akt-calib (one shot: calib --quick --publish)
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

## Run (from the folder that contains `aktogay/`)

```
python -I aktogay/run.py test                  # all unit tests
python -I aktogay/run.py test test_ore.py      # one file
python -I aktogay/run.py params --check        # table consistency
python -I aktogay/run.py params --md PARAMETERS.md
python -I aktogay/run.py calib --quick         # fast calibration table + calib.json
python -I aktogay/run.py calib --out calib.json   # full: step 10 min, about 4 min
python -I aktogay/run.py service --dry-run --duration 30 --speed 1200   # service without MQTT
python -I aktogay/run.py trial --n 100 --no-twin --jobs 5 --out trial.json   # about 3 min
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
and `road:N` (ramp of line N closed, trucks on a detour). Silent causes `energy:N` (SAG kWh/t +10 %), `reagent:N` (collector +40 % while the
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
cut and reline 10 min after the start, `--asis-notice`; hard ore when it
reaches the SAG, `scen_hard_lead_h` later). A grid call is repeated until the
SAG of the shed line gets the headroom (and the plant latches it,
`Plant._c2_call`). `--no-asis` gives the old baseline where nobody takes those
decisions (it overstated the gain). Result of 22.10.2026 (N 100, seeds
1001-1100, `sim/data/trial_n100.json`): twin in all +1.26 t Cu per shift
[95 % BCa +1.06; +1.52], 93 % of shifts better, none worse; order alone
+0.08 [+0.05; +0.23] [model estimate]. `--set`, `--hidden-mult`, `--mag` are
the sensitivity options.

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
- SAG reline 96 h is an assumption (RME benchmark), not the Q3 2025 quarter
  change, so the reline check is no longer closed on itself.
- SAG: J0 25 % (Bradken); the 12 % ball charge stays when the ore grinds out
  (power floor about 69 % of P0); under a power cap below that the control
  slows the mill. A stopped mill keeps its charge. Bond energy is capped at
  `ball_p80_min_um` (cyclones limit the overflow on small feed).
- Block draws are mean-preserving lognormals; the Cu clamp band scales with
  the year grade.
- Tails lock their pore water only (0.31 m3/t at dry 1.45 t/m3, SG 2.66).

## Known gaps (TODO)

- 2023 ore is not in the sources: the 2023 check derives it from the 2023
  electricity; add the KAZ FY2023 figure to make the 2023 water check independent.
- Feed-end changes at intermediate relines only restart the wear counter;
  their downtime sits inside the fitted availability.
- Quarter grades other than Q3 2025 are not in the sources yet.
- Stop days within the month are assumptions; the reports name one SAG
  reline (line 2, August 2025) and one planned SAG maintenance (line 2,
  October 2024); the other calendar stops are planned maintenance whose kind
  of work is not disclosed (`RELINE_CALENDAR`, field `kind`).
- Daily load profile (Zenodo) and GeoMet block distribution are not wired yet.
- Haul length, ramps, number and places of the dam piezometers, the return
  water pipeline and the shift roster by role are not published: they are
  assumptions of the site file (labelled so). The truck fleet is the one of
  06.06.2024; the 2026 fleet is not confirmed.
- Detection rate, false alarms and the cause -> node matrix need the losses
  module; they are added to `calib` later.
