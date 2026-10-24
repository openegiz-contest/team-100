"""Events: scenario parsing and presets, hidden causes, random visible stops,
calibration downtime, crews (arrival, repair time, queue), copy call policies.

Design: section 2 (randomness from seed and step; hidden causes only in
free run and calib), section 4 "visible random events", "hidden causes",
section 5 (crews, P90, notice delays), section 6 (URL scenario syntax),
section 7 (C1-C4, "Two at once", safety).

Everything here is a pure function of (seed, keys, params) or mutates only
the crew passed in; the plant applies the results.

Scenario text (URL `scenario=`): tokens joined by "+" (a space or comma is
accepted too, since "+" in a query string decodes to a space):
  crusher:N  grid  hard:N  reline:N         announced scenarios C1-C4
  dose:N  cyclone:N  liner:N  oxide:N       hidden causes set explicitly
  trip:N                                    crusher-N lube sensor fault (loud)
  energy:N  reagent:N  leak                 silent causes set explicitly (SAG energy overspend,
                                            collector overdose, small return-water leak)
  icy  fatigue  oil                         tier S of 23.10.2026: ice and snowstorm on the haul roads, tired driver
                                            (assumption), hydraulic oil contamination of the excavator EX01
  roping:N  phdrift:N                       cyclone roping with ball mill overload, scaled pH electrode (scenario only)
  hpgr:2  mantle:N                          uneven HPGR feed / tramp metal (line 2), planned mantle change of a crusher
  sample:N                                  blocked sample line of the on-stream analyser: it keeps its last reading (data age grows)
Constructor of a trouble (feature 24): every token may carry a start and a magnitude, kind[:N][@start_min][=magnitude],
e.g. "crusher:1@90=4.5" = crusher 1 stops 90 model minutes after the start of the scenario (08:00), the repair takes
a median of 4.5 h. The magnitude is in the unit of MAGNITUDE (hours, MW, share, pp), kept inside the min..max of the
parameter row it replaces; a kind without a magnitude (hpgr, startup, sample, oil, winter...) rejects "=".
preset "fork" = dose:1 at scen_fork_dose_h + crusher-2 lube trip at
scen_fork_trip_h; auto defaults to True for fork, False otherwise.

Units: time in model minutes, durations in hours where the name says _h,
travel and notice delays in minutes.
"""
from __future__ import annotations

import math
import re

from .params import TABLE, ParamSet
from .state import (CREW_FOR, MIN_PER_DAY, MIN_PER_H, NO_VALUE, CauseEffects, CrewJob, CrewState,
                    HiddenCause, PlannedCall, ScenarioEvent, ScenarioSpec, normal, u01)

ANNOUNCED = ("crusher", "grid", "hard", "reline")
HIDDEN = ("dose", "cyclone", "liner", "oxide")
# Silent causes: no lab or alarm finds them; free run draws them from their own stream (hc_silent_per_shift),
# the modules find them by balances (energy per t, reagent tank, water). "leak" is site-wide (line 0).
SILENT = ("energy", "reagent", "leak")
SILENT_FOUND_BY = {"energy": "report", "reagent": "audit", "leak": "patrol"}
# Silent causes set only by a scenario (never drawn in free run, so the draws of the others stay as they were):
# balls = grinding media overuse, conc = concentrate grade lost to dilution.
EXTRA = ("balls", "conc", "roping", "phdrift")
COPIES = ("fact", "base", "loud", "no_twin")
POLICIES = ("by_value", "loud", "no_twin")
PRESETS = ("", "fork")
LINES = (1, 2)

# Event kinds accepted in scenario text.
#   water      leak of the return-water pipeline: recycle falls, fresh water hits its cap, ore is cut
#   hpgr_fire  fire at the HPGR of concentrator 1 during maintenance (event of 09.08.2026, scen_fire_line)
#   road:N     ramp to crusher N closed, trucks take a detour
SITE_KINDS = ("grid", "water", "hpgr_fire", "leak", "winter", "dust", "pitstop", "icy", "fatigue", "oil", "leachcold",
              "brake", "track")
LINE_KINDS = ("crusher", "hard", "reline", "trip", "road", "conveyor") + HIDDEN + ("energy", "reagent") + EXTRA + (
    "startup", "hpgr", "mantle", "sample", "gmd", "idler", "froth", "rake", "cloth", "slurry")
HPGR_LINES = (2,)           # the HPGR is in the model on line 2 only (thyssenkrupp POLYCOM, vendor)

# Standard normal 0.90 quantile (P90 of a lognormal = median * exp(Z90 * sigma)).
Z90 = 1.2815515655446004

_EPS = 1e-9   # float tolerance for model-minute comparisons

# Thing where the work is, per issue kind ({n} = line).
_NODE = {
    "crusher": "crusher-{n}", "trip": "crusher-{n}", "hard": "pit", "reline": "sag-{n}",
    "dose": "flot-{n}", "cyclone": "cyclones-{n}", "liner": "sag-{n}", "oxide": "flot-{n}",
    "grid": "power", "safety": "water", "water": "water", "hpgr_fire": "pebble-{n}", "road": "ramp-{n}",
    "energy": "sag-{n}", "reagent": "rougher-{n}", "leak": "water", "balls": "ball-{n}a", "conc": "flot-{n}",
    "startup": "ball-{n}a", "winter": "water", "dust": "water", "conveyor": "conveyor-{n}", "pitstop": "pit",
    "icy": "pit", "fatigue": "fleet", "oil": "exc-1", "roping": "cyclones-{n}", "phdrift": "ph-{n}",
    "hpgr": "pebble-{n}", "mantle": "crusher-{n}", "sample": "analyzer-{n}", "leachcold": "leach-1",
    "gmd": "sag-{n}", "idler": "conveyor-{n}", "froth": "flot-{n}", "rake": "thick-{n}", "cloth": "filter-{n}",
    "slurry": "cyclones-{n}", "brake": "fleet", "track": "exc-1",
}
# Key of the magnitude in ScenarioEvent.data and the parameter that sets it.
_MAG_KEY = {"dose": "drop", "cyclone": "n", "liner": "loss", "oxide": "ascu_pp",
            "energy": "e_frac", "reagent": "over", "leak": "leak_frac", "balls": "over", "conc": "drop_pp",
            "roping": "rope", "phdrift": "ph_bias"}
_MAG_PARAM = {"dose": "hc_dose_drop", "cyclone": "hc_cyclone_n", "liner": "hc_liner_eta_loss",
              "oxide": "hc_oxide_ascu_pp", "energy": "hc_energy_frac", "reagent": "hc_reagent_over",
              "leak": "hc_leak_frac", "balls": "hc_balls_frac", "conc": "hc_conc_drop_pp",
              "roping": "hc_rope_sev", "phdrift": "hc_ph_drift"}
# Median repair time after arrival per issue kind (other kinds: crew_dose_fix_h).
_WORK_PARAM = {"crusher": "crush_repair_h", "trip": "crew_trip_fix_h", "lube_trip": "crew_trip_fix_h",
               "conveyor": "conv_repair_h", "mantle": "crush_mantle_h", "hpgr": "peb_hpgr_fix_h", "sample": "sens_an_clean_h",
               "dose": "crew_dose_fix_h", "water": "water_leak_fix_h"}

# Magnitude of a trouble set by the constructor: kind -> (slot, parameter row that it replaces). Slot "hours" =
# duration of the event, "work" = median repair time after arrival (and the duration), anything else = key of
# ScenarioEvent.data. The value stays inside min..max of the row.
MAGNITUDE = {
    "crusher": ("work", "crush_repair_h"), "trip": ("work", "crew_trip_fix_h"), "conveyor": ("work", "conv_repair_h"),
    "mantle": ("work", "crush_mantle_h"), "reline": ("hours", "liner_reline_h"), "pitstop": ("hours", "scen_pitstop_h"),
    "icy": ("hours", "scen_icy_h"), "fatigue": ("hours", "scen_fatigue_h"), "dust": ("hours", "scen_dust_h"),
    "leachcold": ("hours", "scen_leach_h"),
    "road": ("hours", "pit_road_close_h"), "hpgr_fire": ("hours", "scen_fire_h"),
    "grid": ("limit_mw", "pow_c2_limit_mw"), "hard": ("axb", "ore_axb_hard"), "water": ("leak_frac", "water_leak_frac"),
    "dose": ("drop", "hc_dose_drop"), "cyclone": ("n", "hc_cyclone_n"), "liner": ("loss", "hc_liner_eta_loss"),
    "oxide": ("ascu_pp", "hc_oxide_ascu_pp"), "energy": ("e_frac", "hc_energy_frac"), "reagent": ("over", "hc_reagent_over"),
    "leak": ("leak_frac", "hc_leak_frac"), "balls": ("over", "hc_balls_frac"), "conc": ("drop_pp", "hc_conc_drop_pp"),
    "roping": ("rope", "hc_rope_sev"), "phdrift": ("ph_bias", "hc_ph_drift"),
    # tier T: the magnitude is the work of the person after the arrival, hours (data["fix_h"])
    "gmd": ("fix_h", "w_gmd_fix_h"), "idler": ("fix_h", "w_idler_fix_h"), "froth": ("fix_h", "w_froth_fix_h"),
    "rake": ("fix_h", "w_rake_fix_h"), "cloth": ("fix_h", "w_cloth_fix_h"), "slurry": ("fix_h", "w_slurry_fix_h"),
    "brake": ("fix_h", "w_brake_fix_h"), "track": ("fix_h", "w_track_fix_h"),
}
_RE_TOKEN = re.compile(r"^([a-z_]+(?::\d+)?)(?:@(\d+(?:\.\d+)?))?(?:=(-?\d+(?:\.\d+)?))?$")


def split_token(tok: str) -> tuple[str, float | None, float | None]:
    """'crusher:1@90=4.5' -> ('crusher:1', 90.0, 4.5); a token without modifiers -> (tok, None, None).
    A token that does not fit the pattern is returned as it is (the parser names it unknown)."""
    m = _RE_TOKEN.match(tok)
    if not m:
        return tok, None, None
    return (m.group(1), float(m.group(2)) if m.group(2) is not None else None,
            float(m.group(3)) if m.group(3) is not None else None)



# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------
def issue_for(kind: str, line: int) -> tuple[str, str, str]:
    """(issue key, node thingId, crew thingId) of an issue kind on a line.

    Issue key "crusher:1" ("grid" for site-wide kinds); crew "" when no crew
    fixes it (grid, hard ore, reline, oxide ore, safety: a call goes to a role).
    """
    issue = f"{kind}:{line}" if line else kind
    node = _NODE.get(kind, kind).format(n=line)
    crew = CREW_FOR.get("lube_trip" if kind == "trip" else kind, "")
    return issue, node, crew


def _magnitude(kind: str, prm: ParamSet) -> float:
    """Hidden cause size in kind units (eta loss, clogged count, dose drop share, ASCu pp)."""
    return prm[_MAG_PARAM[kind]]


def _day_start(t_min: float) -> float:
    """Model minute of 00:00 of the day that holds t_min."""
    return math.floor(t_min / MIN_PER_DAY) * MIN_PER_DAY


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
def _tokens(text: str | None) -> list[str]:
    """Normalised, de-duplicated scenario tokens in the given order."""
    if not text:
        return []
    out: list[str] = []
    for part in str(text).replace(",", " ").replace("+", " ").split():
        tok = part.strip().lower()
        if tok and tok not in out:
            out.append(tok)
    return out


def _parse_token(tok: str) -> tuple[str, int]:
    """'crusher:1' -> ('crusher', 1); 'grid' -> ('grid', 0). ValueError when unknown."""
    kind, sep, arg = tok.partition(":")
    if kind in SITE_KINDS:
        if sep and arg not in ("", "0"):
            raise ValueError(f"scenario token takes no line: {tok}")
        return kind, 0
    if kind in LINE_KINDS:
        if not arg:
            raise ValueError(f"scenario token needs a line, e.g. {kind}:1: {tok}")
        try:
            line = int(arg)
        except ValueError:
            raise ValueError(f"bad line in scenario token: {tok}") from None
        if line not in LINES:
            raise ValueError(f"line must be one of {LINES}: {tok}")
        if kind == "hpgr" and line not in HPGR_LINES:
            raise ValueError(f"the HPGR is in the model on line 2 only: {tok}")
        return kind, line
    raise ValueError(f"unknown scenario token: {tok}")


def _event(kind: str, line: int, t_min: float, prm: ParamSet, mag: float | None = None) -> ScenarioEvent:
    """ScenarioEvent with its parameters from the table (see parse_scenario); mag replaces the default size."""
    issue, node, crew = issue_for(kind, line)
    data: dict = {"issue": issue, "node": node, "crew": crew}
    dur = NO_VALUE
    if kind == "hpgr_fire":
        line = int(prm["scen_fire_line"])                  # site-wide token, the line is the fact of 09.08.2026
        data["node"] = _NODE[kind].format(n=line)
        data["people"] = prm["scen_fire_people"]
        data["safety_h"] = prm["scen_fire_safety_h"]
        dur = prm["scen_fire_h"]
    elif kind == "water":
        data["leak_frac"] = prm["water_leak_frac"]
    elif kind == "road":
        dur = prm["pit_road_close_h"]
    elif kind == "pitstop":
        dur = prm["scen_pitstop_h"]
    elif kind == "conveyor":
        dur = prm["conv_repair_h"]
    elif kind == "icy":
        dur = prm["scen_icy_h"]
    elif kind == "fatigue":
        dur = prm["scen_fatigue_h"]
    elif kind == "mantle":
        dur = prm["crush_mantle_h"]
    if kind == "crusher":
        dur = prm["crush_repair_h"]
    elif kind == "grid":
        dur = prm["pow_c2_h"]
        data["limit_mw"] = prm["pow_c2_limit_mw"]
    elif kind == "hard":
        data.update(axb=prm["ore_axb_hard"], bwi=prm["ore_bwi_hard"], lead_h=prm["scen_hard_lead_h"])
    elif kind == "reline":
        dur = prm["liner_reline_h"]
    elif kind == "trip":
        dur = prm["crew_trip_fix_h"]
        # Sensor fault: the reading sits at scen_trip_lube_kpa, below the trip setpoint.
        data["bias_kpa"] = prm["scen_trip_lube_kpa"] - prm["crush_lube_kpa"]
    elif kind == "dust":
        dur = prm["scen_dust_h"]
    elif kind == "leachcold":
        dur = prm["scen_leach_h"]
    elif kind in HIDDEN or kind in SILENT or kind in EXTRA:
        data[_MAG_KEY[kind]] = _magnitude(kind, prm)
    elif kind == "safety":
        data["flag"] = "piezo"
    if mag is not None:
        if kind not in MAGNITUDE:
            raise ValueError(f"scenario token {kind} takes no magnitude")
        slot, key = MAGNITUDE[kind]
        row = TABLE[key]
        v = min(max(float(mag), row.min), row.max)
        if slot in ("hours", "work"):
            dur = v
            if slot == "work":
                data["work_h"] = v
        else:
            data[slot] = v
    return ScenarioEvent(kind, line, float(t_min), float(dur), data)


def parse_scenario(text: str, t0_min: float, prm: ParamSet, preset: str = "",
                   kip: int | None = None, safety: bool = False,
                   auto: bool | None = None) -> ScenarioSpec:
    """Build a ScenarioSpec starting at t0_min (model minute of 08:00 of the run day).

    crusher:N -> ScenarioEvent("crusher", N, t0, duration_h=crush_repair_h)
    grid      -> ScenarioEvent("grid", 0, t0, pow_c2_h, {"limit_mw": pow_c2_limit_mw})
    hard:N    -> ScenarioEvent("hard", N, t0, data={"axb": ore_axb_hard, "bwi": ore_bwi_hard,
                                                    "lead_h": scen_hard_lead_h})
    reline:N  -> ScenarioEvent("reline", N, t0, liner_reline_h)
    dose:N    -> ScenarioEvent("dose", N, t0, data={"drop": hc_dose_drop})
    cyclone:N -> ScenarioEvent("cyclone", N, t0, data={"n": hc_cyclone_n})
    liner:N   -> ScenarioEvent("liner", N, t0, data={"loss": hc_liner_eta_loss})
    oxide:N   -> ScenarioEvent("oxide", N, t0, data={"ascu_pp": hc_oxide_ascu_pp})
    trip:N    -> ScenarioEvent("trip", N, t0, crew_trip_fix_h, {"bias_kpa": ...})
    water     -> ScenarioEvent("water", 0, t0, data={"leak_frac": water_leak_frac}) (until crew-water repairs)
    hpgr_fire -> ScenarioEvent("hpgr_fire", scen_fire_line, t0, scen_fire_h,
                               {"people": scen_fire_people, "safety_h": scen_fire_safety_h})
    road:N    -> ScenarioEvent("road", N, t0, pit_road_close_h)
    conveyor:N -> ScenarioEvent("conveyor", N, t0, conv_repair_h): the main belt of line N trips, the crew of the
                 crusher repairs it; the stockpile carries the SAG meanwhile
    pitstop   -> ScenarioEvent("pitstop", 0, t0, scen_pitstop_h): every ore excavator stands (DOWN) for that long
    preset "fork": dose:1 at day start + scen_fork_dose_h and
      ScenarioEvent("trip", 2, day start + scen_fork_trip_h, crew_trip_fix_h)
      (crusher-2 lube sensor fault: lube_bias drives the reading below trip;
      data["bias_kpa"] = scen_trip_lube_kpa - crush_lube_kpa, kPa).
    safety -> ScenarioEvent("safety", 0, t0 + scen_safety_min) (piezometer above setpoint).
    Every event also carries data "issue", "node" and "crew" (see issue_for).
    Events are sorted by start time (stable: text order at equal times);
    a repeated (kind, line) is kept once. kip defaults to crew_kip.
    A token naming a preset ("fork", as the button "Два сразу" and the address
    ?scenario=fork send it) selects that preset; with another preset given it
    is a ValueError.
    A token may carry a start and a magnitude, kind[:N][@minutes after t0][=magnitude] (MAGNITUDE, split_token);
    the scenario text (site.scenario) keeps the bare kinds.
    Unknown token, line outside 1..2, unknown preset or kip < 1 -> ValueError.
    """
    preset_n = (preset or "").strip().lower()
    if preset_n not in PRESETS:
        raise ValueError(f"unknown preset: {preset}")
    named = [tok for tok in _tokens(text) if tok in PRESETS and tok]
    for tok in named:
        if preset_n and preset_n != tok:
            raise ValueError(f"scenario token {tok} conflicts with preset {preset_n}")
        preset_n = tok
    text = " ".join(tok for tok in _tokens(text) if tok not in named)
    t0 = float(t0_min)
    events: list[ScenarioEvent] = []
    seen: set[tuple[str, int]] = set()
    if preset_n == "fork":
        day0 = _day_start(t0)
        events.append(_event("dose", 1, day0 + prm["scen_fork_dose_h"] * MIN_PER_H, prm))
        events.append(_event("trip", 2, day0 + prm["scen_fork_trip_h"] * MIN_PER_H, prm))
        seen.update({("dose", 1), ("trip", 2)})
    tokens = _tokens(text)
    norm: list[str] = []
    end = _day_start(t0) + prm["scen_end_h"] * MIN_PER_H
    for tok in tokens:
        base, delay, mag = split_token(tok)
        kind, line = _parse_token(base)
        key = f"{kind}:{line}" if line else kind
        if key not in norm:
            norm.append(key)
        if (kind, line) in seen:
            continue
        seen.add((kind, line))
        if delay is not None and t0 + delay >= end - _EPS:
            raise ValueError(f"scenario token starts after the end of the scenario shift: {tok}")
        events.append(_event(kind, line, t0 + (delay or 0.0), prm, mag))
    if safety:
        events.append(_event("safety", 0, t0 + prm["scen_safety_min"], prm))
    events.sort(key=lambda e: e.t_start_min)

    kip_n = int(prm["crew_kip"]) if kip is None else int(kip)
    if kip_n < 1:
        raise ValueError(f"kip must be >= 1: {kip}")
    auto_b = (preset_n == "fork") if auto is None else bool(auto)
    return ScenarioSpec(text="+".join(norm), preset=preset_n, kip=kip_n, safety=bool(safety),
                        auto=auto_b, t0_min=t0, events=events)


def scenario_label(spec: ScenarioSpec | None, hidden: bool = True) -> str:
    """Scenario text for site.scenario, e.g. "fork+safety" or "hard:1+grid".

    hidden=False drops hidden-cause tokens (dose, cyclone, liner, oxide), so
    the measured snapshot does not reveal them; the truth snapshot keeps them.
    """
    if spec is None:
        return ""
    parts = [spec.preset] if spec.preset else []
    for tok in _tokens(spec.text):
        if hidden or tok.partition(":")[0] not in HIDDEN + SILENT + EXTRA:
            parts.append(tok)
    if spec.safety:
        parts.append("safety")
    return "+".join(parts)


def preset_causes(spec: ScenarioSpec, prm: ParamSet) -> list[HiddenCause]:
    """Hidden causes set by the scenario (preset=True), one per dose/cyclone/liner/oxide event.

    magnitude: dose -> hc_dose_drop, cyclone -> hc_cyclone_n, liner -> hc_liner_eta_loss,
    oxide -> hc_oxide_ascu_pp (value from the event data when present).
    t_end_min stays NO_VALUE until a crew fixes it.
    """
    out = []
    for e in spec.events:
        if e.kind not in HIDDEN and e.kind not in SILENT and e.kind not in EXTRA:
            continue
        mag = float(e.data.get(_MAG_KEY[e.kind], _magnitude(e.kind, prm)))
        out.append(HiddenCause(e.kind, e.line, e.t_start_min, mag, preset=True))
    return out


# ---------------------------------------------------------------------------
# Random events (free run and calib only)
# ---------------------------------------------------------------------------
def _shift_raw_causes(seed: int, s: int, prm: ParamSet, lines: tuple[int, ...],
                      silent: bool = False) -> list[HiddenCause]:
    """Candidate hidden causes of shift s before the one-at-a-time rule, sorted by start.

    Count = int(hc_per_shift) plus one more with probability frac(hc_per_shift);
    start uniform in the shift; kind uniform over HIDDEN; line uniform over
    `lines`; found by the lab U(hc_found_lo_h, hc_found_hi_h) after start.
    silent=True: rate hc_silent_per_shift, kinds SILENT, stream "hc2" (the "hc" draws stay as they
    were); "leak" is site-wide (line 0); found_by from SILENT_FOUND_BY (report, audit, patrol).
    """
    stream, kinds = ("hc2", SILENT) if silent else ("hc", HIDDEN)
    rate = max(0.0, prm["hc_silent_per_shift" if silent else "hc_per_shift"])
    n = int(rate) + (1 if u01(seed, s, stream, 0) < rate - int(rate) else 0)
    if n == 0 or not lines:
        return []
    shift = prm["cal_shift_h"] * MIN_PER_H
    s0 = prm["cal_shift_start_h"] * MIN_PER_H + s * shift
    lo, hi = prm["hc_found_lo_h"] * MIN_PER_H, prm["hc_found_hi_h"] * MIN_PER_H
    out = []
    for j in range(n):
        k = 1 + 4 * j
        start = s0 + shift * u01(seed, s, stream, k)
        kind = kinds[min(len(kinds) - 1, int(u01(seed, s, stream, k + 1) * len(kinds)))]
        line = lines[min(len(lines) - 1, int(u01(seed, s, stream, k + 2) * len(lines)))]
        if kind in SITE_KINDS:
            line = 0
        found = start + lo + (hi - lo) * u01(seed, s, stream, k + 3)
        out.append(HiddenCause(kind, int(line), start, _magnitude(kind, prm),
                               t_found_min=found, t_end_min=found,
                               found_by=SILENT_FOUND_BY.get(kind, "lab") if silent else "lab"))
    out.sort(key=lambda c: c.t_start_min)
    return out


def draw_hidden_causes(seed: int, t0_min: float, t1_min: float, prm: ParamSet,
                       lines: tuple[int, ...] = (1, 2), silent: bool = False) -> list[HiddenCause]:
    """Random hidden causes in [t0, t1): about hc_per_shift per shift, one at a time.

    Per shift index s (start cal_shift_start_h, length cal_shift_h): with
    probability min(1, hc_per_shift) a cause starts at a uniform time in the
    shift (rates above 1 add more candidates), kind uniform over HIDDEN, line
    uniform over `lines`; it is found by the lab after U(hc_found_lo_h,
    hc_found_hi_h) and ends when found (t_end = t_found, found_by "lab").
    A candidate that would start before the previous cause ends is dropped,
    so at most one cause is active and the mean rate is a little below
    hc_per_shift (about 0.91 per shift at 1.0 with 4-6 h causes).
    Draws from (seed, s, "hc"). The result does not depend on the window:
    a cause belongs to [t0, t1) when its start does (requires
    hc_found_hi_h <= cal_shift_h, true for the whole table range).
    silent=True draws the silent causes (SILENT, hc_silent_per_shift, stream "hc2"): free run only.
    """
    t0, t1 = float(t0_min), float(t1_min)
    if t1 <= t0:
        return []
    lines = tuple(lines)
    shift = prm["cal_shift_h"] * MIN_PER_H
    origin = prm["cal_shift_start_h"] * MIN_PER_H
    s_first = math.floor((t0 - origin) / shift)
    s_last = math.floor((t1 - origin) / shift)

    # Walk back to a shift whose first candidate starts after every candidate
    # of the shift before it has ended: the chain state there is "no cause".
    s = s_first
    cur = _shift_raw_causes(seed, s, prm, lines, silent)
    for _ in range(10000):
        prev = _shift_raw_causes(seed, s - 1, prm, lines, silent)
        if not cur or not prev or cur[0].t_start_min >= max(c.t_end_min for c in prev):
            break
        s -= 1
        cur = prev

    out: list[HiddenCause] = []
    last_end = -math.inf
    for k in range(s, s_last + 1):
        for c in _shift_raw_causes(seed, k, prm, lines, silent):
            if c.t_start_min < last_end:
                continue
            last_end = c.t_end_min
            if t0 <= c.t_start_min < t1:
                out.append(c)
    return out


def _active(c: HiddenCause, t_min: float) -> bool:
    return c.t_start_min <= t_min and (c.t_end_min == NO_VALUE or t_min < c.t_end_min)


def cause_effects(causes: list[HiddenCause], line: int, t_min: float, prm: ParamSet) -> CauseEffects:
    """Combined effect of causes active on `line` at t_min (t_start <= t < t_end or t_end NO_VALUE).

    liner:   sag_eta_mult *= 1 - magnitude; liner_wear_mult = hc_liner_wear_mult
    cyclone: clogged += int(magnitude) (total capped at cyc_open)
    dose:    dose_ratio *= 1 - magnitude * min(1, (t - t_start) / hc_dose_ramp_min)
    oxide:   ascu_add_pp += magnitude
    energy:  sag_e_mult *= 1 + magnitude (SAG kWh/t above what the ore needs)
    reagent: dose_ratio *= 1 + magnitude * ramp (overdose; the flowmeter keeps reading the setpoint)
    leak:    leak_frac += magnitude (site-wide: line 0)
    Unknown kind -> ValueError.
    """
    fx = CauseEffects()
    for c in causes:
        if c.line != line or not _active(c, t_min):
            continue
        if c.kind == "liner":
            fx.sag_eta_mult *= max(0.0, 1.0 - c.magnitude)
            fx.liner_wear_mult = max(fx.liner_wear_mult, prm["hc_liner_wear_mult"])
        elif c.kind == "cyclone":
            fx.clogged += max(0, int(round(c.magnitude)))
        elif c.kind == "dose":
            ramp = prm["hc_dose_ramp_min"]
            share = 1.0 if ramp <= 0.0 else min(1.0, max(0.0, (t_min - c.t_start_min) / ramp))
            fx.dose_ratio *= max(0.0, 1.0 - c.magnitude * share)
        elif c.kind == "oxide":
            fx.ascu_add_pp += c.magnitude
        elif c.kind == "energy":
            fx.sag_e_mult *= 1.0 + max(0.0, c.magnitude)
        elif c.kind == "reagent":
            ramp = prm["hc_dose_ramp_min"]
            share = 1.0 if ramp <= 0.0 else min(1.0, max(0.0, (t_min - c.t_start_min) / ramp))
            fx.dose_ratio *= 1.0 + max(0.0, c.magnitude) * share
        elif c.kind == "leak":
            fx.leak_frac += max(0.0, c.magnitude)
        elif c.kind == "balls":
            fx.balls_mult *= 1.0 + max(0.0, c.magnitude)
        elif c.kind == "conc":
            fx.conc_drop_pp += max(0.0, c.magnitude)
        elif c.kind == "roping":
            ramp = prm["cyc_rope_ramp_min"]
            share = 1.0 if ramp <= 0.0 else min(1.0, max(0.0, (t_min - c.t_start_min) / ramp))
            fx.rope = max(fx.rope, max(0.0, c.magnitude) * share)
            if t_min - c.t_start_min >= prm["cyc_rope_escalate_h"] * MIN_PER_H:
                fx.rope_flot_pp = max(fx.rope_flot_pp, prm["cyc_rope_flot_pp"])    # heavy roping nobody stopped
        elif c.kind == "phdrift":
            fx.ph_bias += max(0.0, c.magnitude)
        else:
            raise ValueError("unknown hidden cause kind: " + str(c.kind))
    fx.clogged = min(fx.clogged, int(prm["cyc_open"]))
    return fx


def _origin(t_min: float) -> float:
    """Fixed start of a renewal sequence: model origin, or the day start for negative times."""
    return 0.0 if t_min >= 0.0 else _day_start(t_min)


def draw_pebble_stops(seed: int, line: int, t0_min: float, t1_min: float,
                      prm: ParamSet) -> list[tuple[float, float]]:
    """Pebble crusher stop windows (start, end) in [t0, t1), model minutes.

    Durations U(peb_stop_h_lo, peb_stop_h_hi); gaps exponential with mean
    chosen so that the stopped share is 1 - peb_kio:
      mean_gap = mean_stop * peb_kio / (1 - peb_kio)   (28.75 h at 0.92 and 2.5 h).
    Draws from (seed, k, "peb-<line>") with k = stop number counted from the
    model origin, so windows do not depend on t0. Returns every window that
    overlaps [t0, t1), not clipped (the plant tests start <= t < end).
    """
    t0, t1 = float(t0_min), float(t1_min)
    kio = prm["peb_kio"]
    if t1 <= t0 or kio >= 1.0:
        return []
    lo, hi = prm["peb_stop_h_lo"] * MIN_PER_H, prm["peb_stop_h_hi"] * MIN_PER_H
    if hi <= 0.0:
        return []
    mean_gap = 0.5 * (lo + hi) * max(0.0, kio) / (1.0 - kio)
    stream = f"peb-{line}"
    out = []
    t = _origin(t0)
    k = 0
    while t < t1:
        start = t - mean_gap * math.log(u01(seed, k, stream, 0))
        if start >= t1:
            break
        end = start + lo + (hi - lo) * u01(seed, k, stream, 1)
        if end > t0:
            out.append((start, end))
        t = end
        k += 1
    return out


def draw_crusher_stops(seed: int, line: int, t0_min: float, t1_min: float,
                       prm: ParamSet) -> tuple[list[float], list[tuple[float, float]]]:
    """Own stops of the primary crusher in [t0, t1), model minutes (calib run): (planned starts, short stops).

    Counted from the model origin, so the draws do not depend on t0:
      planned maintenance: crush_plan_h of work per crush_plan_every_d days; the list holds the time it falls due (random
        inside its period); the plant does it while the mill of the line stands (crush_plan_wait_d);
      short stoppages: Poisson stream crush_stop_per_day per day, each crush_stop_min: (start, end).
    The liner change of the crusher (crush_mantle_h, once a year) is not drawn here: it goes into the SAG reline of the line.
    """
    t0, t1 = float(t0_min), float(t1_min)
    planned: list[float] = []
    shorts: list[tuple[float, float]] = []
    if t1 <= t0:
        return planned, shorts
    stream = f"crw-{line}"
    per = prm["crush_plan_every_d"] * MIN_PER_DAY
    dur = prm["crush_plan_h"] * MIN_PER_H
    if per > 0.0 and dur > 0.0:
        k = int(max(0.0, t0 - per - MIN_PER_DAY) // per)
        while k * per < t1:
            a = k * per + (per - dur) * u01(seed, k, stream, 0)
            if a + MIN_PER_DAY > t0 and a < t1:
                planned.append(a)
            k += 1
    rate = prm["crush_stop_per_day"]
    length = prm["crush_stop_min"]
    if rate > 0.0 and length > 0.0:
        mean_gap = MIN_PER_DAY / rate
        t = 0.0
        k = 0
        while t < t1:
            a = t - mean_gap * math.log(u01(seed, k, stream, 2))
            if a >= t1:
                break
            if a + length > t0:
                shorts.append((a, a + length))
            t = a + length
            k += 1
    return planned, shorts


def _merge(windows: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Sorted union of windows (overlapping ones joined; touching ones kept apart)."""
    out: list[tuple[float, float]] = []
    for a, b in sorted(windows):
        if out and a < out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _complement(windows: list[tuple[float, float]], t0: float, t1: float) -> list[tuple[float, float]]:
    """Parts of [t0, t1) outside the sorted, disjoint windows."""
    out = []
    t = t0
    for a, b in windows:
        if a > t:
            out.append((t, min(a, t1)))
        t = max(t, b)
        if t >= t1:
            break
    if t < t1:
        out.append((t, t1))
    return [(a, b) for a, b in out if b > a]


def _map_free(free: list[tuple[float, float]], xa: float, xb: float) -> list[tuple[float, float]]:
    """Map [xa, xb) on the joined free-time axis back to model time (split at fixed windows)."""
    out = []
    cum = 0.0
    for a, b in free:
        length = b - a
        lo, hi = max(xa, cum), min(xb, cum + length)
        if hi > lo:
            out.append((a + lo - cum, a + hi - cum))
        cum += length
        if cum >= xb:
            break
    return out


def draw_line_downtime(seed: int, line: int, t0_min: float, t1_min: float, availability: float,
                       fixed: list[tuple[float, float]], prm: ParamSet) -> list[tuple[float, float]]:
    """Calib: line stop windows so that stopped share of [t0, t1) = 1 - availability.

    `fixed` windows (relines) count towards the stopped share and are
    returned too (unchanged; overlapping ones are joined); extra stops of
    U(cal_stop_h_lo, cal_stop_h_hi) hours are drawn until they cover the
    rest, then scaled by one factor so the share is exact. They are spread
    over the free time with random gaps (exponential spacings normalised to
    the slack), without overlap; a stop that would cross a fixed window is
    split around it. Sorted by start. Draws from (seed, k, "down-<line>").
    Fixed windows alone above the target -> only the fixed windows.
    """
    t0, t1 = float(t0_min), float(t1_min)
    if t1 <= t0:
        return []
    fx = _merge([(float(a), float(b)) for a, b in fixed if b > a and b > t0 and a < t1])
    fixed_in = sum(min(b, t1) - max(a, t0) for a, b in fx)
    target = (1.0 - min(1.0, max(0.0, float(availability)))) * (t1 - t0)
    free = _complement(fx, t0, t1)
    free_len = sum(b - a for a, b in free)
    extra = min(target - fixed_in, free_len)
    out = list(fx)
    lo, hi = prm["cal_stop_h_lo"] * MIN_PER_H, prm["cal_stop_h_hi"] * MIN_PER_H
    if extra > _EPS and hi > 0.0:
        stream = f"down-{line}"
        durs: list[float] = []
        total = 0.0
        while total < extra:
            d = lo + (hi - lo) * u01(seed, len(durs), stream, 0)
            durs.append(d)
            total += d
        scale = extra / total
        durs = [d * scale for d in durs]
        weights = [-math.log(u01(seed, k, stream, 1)) for k in range(len(durs) + 1)]
        wsum = sum(weights)
        slack = free_len - extra
        gaps = [slack * w / wsum for w in weights]
        x = gaps[0]
        for i, d in enumerate(durs):
            out.extend(_map_free(free, x, x + d))
            x += d + gaps[i + 1]
    out.sort()
    return out


# ---------------------------------------------------------------------------
# Crews
# ---------------------------------------------------------------------------
def repair_hours(seed: int, key: str, median_h: float, prm: ParamSet) -> float:
    """Repair time after arrival, h: median * exp(crew_sigma_ln * N(0, 1)) from (seed, 0, key)."""
    return median_h * math.exp(prm["crew_sigma_ln"] * normal(seed, 0, key, 0))


def p90_hours(median_h: float, prm: ParamSet) -> float:
    """P90 of the lognormal repair time, h: median * exp(1.2816 * crew_sigma_ln)."""
    return median_h * math.exp(Z90 * prm["crew_sigma_ln"])


def arrival_min(seed: int, key: str, prm: ParamSet) -> float:
    """Travel time of a free crew, min: U(crew_arrive_lo_min, crew_arrive_hi_min) from (seed, 0, key)."""
    lo, hi = prm["crew_arrive_lo_min"], prm["crew_arrive_hi_min"]
    return lo + (hi - lo) * u01(seed, 0, key, 2)


def notice_delay_min(seed: int, key: str, prm: ParamSet) -> float:
    """Delay before a loud issue is noticed by alarm without a call, min:
    U(issue_notice_lo_min, issue_notice_hi_min) from (seed, 0, key)."""
    lo, hi = prm["issue_notice_lo_min"], prm["issue_notice_hi_min"]
    return lo + (hi - lo) * u01(seed, 0, key, 3)


def work_median_h(issue_kind: str, prm: ParamSet) -> float:
    """Median repair time by issue kind, h: crusher -> crush_repair_h, trip -> crew_trip_fix_h,
    dose -> crew_dose_fix_h; other kinds -> crew_dose_fix_h. An issue key ("crusher:1") works too."""
    kind = str(issue_kind).partition(":")[0].strip().lower()
    return prm[_WORK_PARAM.get(kind, "crew_dose_fix_h")]


def _teams(crew: CrewState) -> int:
    """Number of teams; slot_free_min is extended to match."""
    n = max(1, int(crew.count))
    if len(crew.slot_free_min) < n:
        crew.slot_free_min.extend([NO_VALUE] * (n - len(crew.slot_free_min)))
    return n


def _refresh(crew: CrewState, t_min: float) -> None:
    """Set state, task and free_at_min of the crew at t_min from its open jobs."""
    work = sorted((j for j in crew.jobs if j.t_arrive_min <= t_min < j.t_done_min),
                  key=lambda j: j.t_arrive_min)
    travel = sorted((j for j in crew.jobs if j.t_call_min <= t_min < j.t_arrive_min),
                    key=lambda j: j.t_arrive_min)
    if work:
        crew.state = "WORK"
        crew.task = ",".join(dict.fromkeys(j.node for j in work))
    elif travel:
        crew.state = "TRAVEL"
        crew.task = travel[0].node
    else:
        crew.state = "FREE"
        crew.task = ""
    slots = crew.slot_free_min[:_teams(crew)]
    if any(s == NO_VALUE or s <= t_min for s in slots):
        crew.free_at_min = NO_VALUE
    else:
        crew.free_at_min = min(slots)


def crew_call(crew: CrewState, call: PlannedCall, arrive_min: float, work_h: float) -> CrewJob:
    """Book a job on the first free team of `crew`.

    start = max(call.t_min, earliest slot_free_min); arrive = start + arrive_min;
    done = arrive + work_h * 60; the slot is busy until done. Appends the job,
    updates task / free_at_min / state (TRAVEL for the job on its way, WORK
    when another job of the crew is in progress). Returns the job.
    arrive_min in min, work_h in h.
    """
    n = _teams(crew)
    best, best_t = 0, math.inf
    for i in range(n):
        s = crew.slot_free_min[i]
        free_t = call.t_min if s == NO_VALUE else max(call.t_min, s)
        if free_t < best_t - _EPS:
            best, best_t = i, free_t
    arrive = best_t + max(0.0, arrive_min)
    done = arrive + max(0.0, work_h) * MIN_PER_H
    job = CrewJob(call.issue, call.node, float(call.t_min), arrive, done)
    crew.slot_free_min[best] = done
    crew.jobs.append(job)
    _refresh(crew, call.t_min)
    return job


def crew_step(crew: CrewState, t_min: float, dt_min: float) -> list[CrewJob]:
    """Update crew state at t_min; returns jobs finished in (t - dt, t].

    Finished jobs leave crew.jobs once returned (a job finished earlier but
    never returned, e.g. after a skipped call, is returned too).
    WORK when a job has arrived and is not done, TRAVEL when on the way
    (or queued behind a busy team), FREE otherwise; task = node of the
    current job (nodes joined by "," when several teams work); free_at_min =
    earliest slot end in the future or NO_VALUE.
    """
    done = sorted((j for j in crew.jobs if j.t_done_min <= t_min + _EPS), key=lambda j: j.t_done_min)
    if done:
        crew.jobs = [j for j in crew.jobs if j.t_done_min > t_min + _EPS]
    n = _teams(crew)
    for i in range(n):
        s = crew.slot_free_min[i]
        if s != NO_VALUE and s <= t_min + _EPS:
            crew.slot_free_min[i] = NO_VALUE
    _refresh(crew, t_min)
    return done


def _planned(kind: str, line: int, t_min: float, seed: int, prm: ParamSet) -> PlannedCall:
    """Call with work_h from repair_hours keyed by the issue (same in every copy)."""
    issue, node, crew = issue_for(kind, line)
    return PlannedCall(float(t_min), node, crew, issue,
                       repair_hours(seed, issue, work_median_h(kind, prm), prm))


def fork_policies(spec: ScenarioSpec, prm: ParamSet, seed: int) -> dict[str, list[PlannedCall]]:
    """Call schedules of the "Two at once" copies (design section 7).

    "by_value": dose:1 called at scen_fork_found_h (module finding), trip:2 at
                trip + notice delay, so the single I&C technician goes to
                flotation first; offline stand-in for the priority module;
    "loud":     silent issue found at scen_fork_found_h, but trip:2 is called
                first (at trip + notice delay) and dose:1 at the same minute after it
                (or at the finding, if that is later);
    "no_twin":  trip:2 at trip + notice delay; dose:1 at scen_fork_lab_h.
    Both issues need crew-kip; queueing is done by crew_call. Each list is
    sorted by t_min and its order is the booking order at equal times.
    work_h drawn with repair_hours from the same keys in all copies; the
    notice delay uses notice_delay_min(seed, "trip:2"). A spec without a
    trip or dose event gives lists with the calls that remain.
    """
    trip = next((e for e in spec.events if e.kind == "trip"), None)
    dose = next((e for e in spec.events if e.kind == "dose"), None)
    day0 = _day_start(spec.t0_min)
    t_found = day0 + prm["scen_fork_found_h"] * MIN_PER_H
    t_lab = day0 + prm["scen_fork_lab_h"] * MIN_PER_H
    t_trip = NO_VALUE
    if trip is not None:
        t_trip = trip.t_start_min + notice_delay_min(seed, issue_for("trip", trip.line)[0], prm)

    def trip_at(t):
        return [_planned("trip", trip.line, t, seed, prm)] if trip is not None else []

    def dose_at(t):
        return [_planned("dose", dose.line, t, seed, prm)] if dose is not None else []

    loud_dose_t = t_found if trip is None else max(t_found, t_trip)
    out = {
        "by_value": dose_at(t_found) + trip_at(t_trip),
        "loud": trip_at(t_trip) + dose_at(loud_dose_t),
        "no_twin": trip_at(t_trip) + dose_at(t_lab),
    }
    for calls in out.values():
        calls.sort(key=lambda c: c.t_min)
    return out
