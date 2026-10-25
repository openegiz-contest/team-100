"""Plant state: dataclasses shared by all sim modules, plus helpers.

Conventions (all modules):
  time      model minutes since run origin (00:00 of day 0), float
  flows     t/h (dry solids unless named wet), m3/h for water
  power     kW inside units (power_kw), MW in site balances
  grades    % Cu; ASCu in % of total Cu; recovery in %
  energy    kWh/t specific, MWh cumulative
  money     USD
  "no value" in published features is -1.0 (never None/NaN)

Truth vs measured: unit dataclasses hold the true model values. Noise and
delays are applied by sim.sensors when features are published. Fields
marked "truth" must never be published to modules (only validation-sim).

Randomness depends only on (seed, step, stream): use u01 / normal / rng_at.
"""
from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass, field

MIN_PER_H = 60.0
MIN_PER_DAY = 1440.0
NO_VALUE = -1.0

# ---------------------------------------------------------------------------
# Deterministic randomness from (seed, step, stream)
# ---------------------------------------------------------------------------
_MASK = (1 << 64) - 1


def _splitmix(x: int) -> int:
    x = (x + 0x9E3779B97F4A7C15) & _MASK
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & _MASK
    return x ^ (x >> 31)


def stream_id(name: str) -> int:
    """Stable integer id of a named random stream (crc32, independent of hash seed)."""
    return zlib.crc32(name.encode("utf-8"))


def u01(seed: int, step: int, stream: str, k: int = 0) -> float:
    """Uniform number in (0, 1) from (seed, step, stream, k). Pure function."""
    x = _splitmix(int(seed) & _MASK)
    x = _splitmix(x ^ (int(step) & _MASK))
    x = _splitmix(x ^ stream_id(stream))
    x = _splitmix(x ^ (int(k) & _MASK))
    return ((x >> 11) + 0.5) / float(1 << 53)


def normal(seed: int, step: int, stream: str, k: int = 0) -> float:
    """Standard normal from (seed, step, stream, k) via Box-Muller."""
    a = u01(seed, step, stream, 2 * k)
    b = u01(seed, step, stream, 2 * k + 1)
    return math.sqrt(-2.0 * math.log(a)) * math.cos(2.0 * math.pi * b)


def rng_at(seed: int, step: int, stream: str) -> random.Random:
    """random.Random seeded from a string (sha512 based, stable across runs)."""
    return random.Random(f"{int(seed)}:{int(step)}:{stream}")


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------
@dataclass
class Clock:
    t_min: float = 0.0        # model minutes since origin (00:00 of day 0)
    step: int = 0             # step counter; key for randomness
    dt_min: float = 1.0       # current step, min
    year: int = 2026          # calendar label (calib runs set the report year)
    origin_doy: int = 0       # day of year (0-based) of the origin

    def hour(self) -> float:
        """Hour of day, 0..24."""
        return (self.t_min % MIN_PER_DAY) / MIN_PER_H

    def day(self) -> int:
        return int(self.t_min // MIN_PER_DAY)

    def doy(self) -> float:
        """Fractional day of year (0-based)."""
        return self.origin_doy + self.t_min / MIN_PER_DAY

    def shift_index(self, start_h: float = 8.0, shift_h: float = 12.0) -> int:
        """Index of the current shift; shift 0 starts at start_h on day 0."""
        return int(math.floor((self.t_min - start_h * MIN_PER_H) / (shift_h * MIN_PER_H)))

    def hhmm(self) -> str:
        h = self.hour()
        return f"{int(h):02d}:{int(round((h % 1) * 60)) % 60:02d}"


# ---------------------------------------------------------------------------
# Ore
# ---------------------------------------------------------------------------
@dataclass
class OreProps:
    cu_pct: float = 0.0       # % Cu
    ascu_pct: float = 0.0     # acid-soluble Cu, % of total Cu
    axb: float = 0.0          # SMC A*b, -
    bwi: float = 0.0          # Bond ball work index, kWh/t

    def copy(self) -> "OreProps":
        return OreProps(self.cu_pct, self.ascu_pct, self.axb, self.bwi)


@dataclass
class Batch:
    """One pit block followed from plan to SAG (thing batch-NNNN)."""
    batch_id: str             # "batch-0001"
    block_no: int
    line: int                 # destination line 1 or 2
    tonnes: float             # t, block size
    est: OreProps             # block-model estimate (visible to modules)
    true: OreProps            # truth (sim only)
    state: str = "PLANNED"    # PLANNED | DIG | BELT | IN_STOCK | DONE
    location: str = "pit"     # thingId of current parent
    dug_t: float = 0.0        # t dug so far
    tonnes_left: float = 0.0  # t not yet fed to SAG (weigher accounting)
    stock_mark_t: float = NO_VALUE  # stockpile cum_out_t at which the batch is DONE
    t_created_min: float = NO_VALUE
    t_dig_min: float = NO_VALUE
    t_belt_min: float = NO_VALUE
    t_stock_min: float = NO_VALUE
    t_sag_min: float = NO_VALUE     # first reached SAG feed (truth, mixing)
    t_done_min: float = NO_VALUE
    cu_meas: float = NO_VALUE       # lab Cu of batch, %
    t_lab_min: float = NO_VALUE     # when cu_meas arrived (the batch thing is kept cal_batch_keep_h after it)
    axb_soft: float = NO_VALUE      # soft-sensor A*b while in SAG feed
    tag: str = ""                   # "hard", "blend", "initial" or ""


@dataclass
class Parcel:
    """Ore in transit (haul road, crusher pocket or belt)."""
    batch_id: str
    tonnes: float             # t
    t_ready_min: float        # model minute it reaches the next node


# ---------------------------------------------------------------------------
# Pit and fleet
# ---------------------------------------------------------------------------
@dataclass
class ExcavatorState:
    name: str                 # "exc-1"
    line: int                 # line it feeds now (exc-3 swings); 0 for stripping
    state: str = "DIG"        # DIG | MOVE | IDLE | DOWN
    tph: float = 0.0          # t/h dug
    block: str = ""           # batch id being dug
    bench: int = 1
    down_until_min: float = NO_VALUE
    duty: str = "ore"         # "ore" (PlantState.excavators) | "waste" (PlantState.waste_excavators)
    oil_pct: float = 0.0      # truth: hydraulic oil contamination, % of the alert level of the on-machine sensor
    oil_event_min: float = NO_VALUE   # scenario oil: model minute the contamination starts to rise
    oil_fix_min: float = NO_VALUE     # model minute the oil service (called) is done


@dataclass
class TruckState:
    """One haul truck: a state machine on top of the aggregated haul (no truck physics)."""
    name: str                 # "truck-01"
    model: str                # "CAT 793"
    payload_t: float          # rated payload, t
    duty: str                 # "ore" | "waste"
    line: int                 # crusher line of an ore truck, 0 for waste
    k: int                    # index of its hourly readiness draw (stream "fleet")
    phase_min: float = 0.0    # offset of its cycle, min (trucks spread over the cycle)
    ready: bool = True
    state: str = "LOADING"    # LOADING | HAUL_FULL | QUEUE | DUMP | RETURN | DOWN
    location: str = ""        # face, road or crusher thing
    load_t: float = 0.0
    cycle_min: float = 0.0


@dataclass
class FaceState:
    name: str                 # "face-1"
    excavator: str
    kind: str                 # "ore" | "waste"
    bench: int = 1
    state: str = "IDLE"       # ACTIVE | IDLE | DOWN
    block: str = ""
    tph: float = 0.0
    blasted_t: float = 0.0    # blasted rock ready to dig (drills add, the excavator takes)


@dataclass
class DrillState:
    """Blast-hole drill rig: a state machine that keeps the blasted stock of its face."""
    name: str                 # "drill-01"
    model: str
    face: str
    k: int                    # index of its hourly readiness draw (stream "drill")
    ready: bool = True
    state: str = "DRILLING"   # DRILLING | MOVING | IDLE | DOWN
    holes_shift: float = 0.0  # holes drilled in the current shift
    shift_idx: int = -1
    ready_hour: int = -1      # model hour of the last readiness draw (the draw is hourly: cached, same value)


@dataclass
class DozerState:
    name: str                 # "dozer-01"
    model: str
    place: str                # face or road it works on
    k: int                    # index of its hourly readiness draw (stream "dozer")
    state: str = "WORK"       # WORK | IDLE | DOWN
    ready_hour: int = -1      # model hour of the last readiness draw (the draw is hourly: cached, same value)
    ready: bool = True


@dataclass
class RoadState:
    name: str                 # "ramp-1"
    line: int                 # 0: waste dump road
    state: str = "OPEN"       # OPEN | CLOSED
    closed_until_min: float = NO_VALUE
    trucks_on: int = 0


@dataclass
class PersonState:
    """A person of the shift; crews book through the person of their trade."""
    name: str                 # "person-kip"
    role: str
    crew: str = ""            # crew thing the person works in, "" for decision roles
    home: str = "site"        # thing where the person is when free
    state: str = "FREE"       # FREE | TRAVEL | WORK | OFF
    location: str = ""
    task: str = ""
    free_at_min: float = NO_VALUE
    duty_node: str = ""       # decision duty (no crew): where, until when
    duty_until_min: float = NO_VALUE
    off_until_min: float = NO_VALUE   # evacuated / off shift until


@dataclass
class FleetState:
    state: str = "NORMAL"     # NORMAL | SHORT
    exc_total: int = 0
    exc_ready: int = 0
    trucks_total: int = 0
    trucks_ready: int = 0
    truck_kio_shift: float = 0.0   # mean ready share this shift
    haul_tph: float = 0.0          # trucks_ready x payload x trips/h
    mining_tph: float = 0.0
    kio_sum: float = 0.0           # accumulator for truck_kio_shift
    kio_n: int = 0
    last_draw_h: int = -1          # model hour of last Binomial draw
    fatigue: bool = False          # alert of a tired driver / close approach (scenario fatigue)
    fatigue_truck: str = ""


@dataclass
class PitState:
    state: str = "RUN"        # RUN | STOP
    mining_tph: float = 0.0
    next_block_no: int = 1
    plan: dict[int, list[str]] = field(default_factory=lambda: {1: [], 2: []})   # batch ids in dig order
    plan_text: str = ""
    hard_in_plan: bool = False
    blend: dict[int, bool] = field(default_factory=lambda: {1: False, 2: False})  # C3 response
    haul: dict[int, list[Parcel]] = field(default_factory=lambda: {1: [], 2: []})  # to crusher pocket
    target_tph: dict[int, float] = field(default_factory=lambda: {1: 0.0, 2: 0.0})  # regulator output
    visibility_m: float = 10000.0     # haul roads: visibility, m (weather)
    road_grip: float = 0.8            # haul roads: friction index 0..1 (weather)
    cycle_mult: float = 1.0           # truck cycle multiplier of weather and restriction (set by the plant each step)
    restrict_until_min: float = NO_VALUE   # traffic restriction (speed limit) in force until this minute


# ---------------------------------------------------------------------------
# Crushing, conveying, stockpile
# ---------------------------------------------------------------------------
@dataclass
class CrusherState:
    name: str                 # "crusher-1"
    line: int
    state: str = "RUN"        # RUN | STOP | SLOW
    tph: float = 0.0
    power_kw: float = 0.0
    lube_kpa: float = 0.0
    lube_bias_kpa: float = 0.0          # truth: sensor fault offset (scenario "trip")
    pocket: list[Parcel] = field(default_factory=list)   # dumped, waiting
    fault: str = ""           # cause of STOP: "", "scenario", "lube_trip", "mantle" (planned mantle change)
    fault_until_min: float = NO_VALUE   # repair end (set by crew model)
    service_until_min: float = NO_VALUE   # planned end of the mantle change (scenario mantle:N)


@dataclass
class ConveyorState:
    name: str                 # "conveyor-1"
    line: int
    state: str = "RUN"        # RUN | STOP
    tph: float = 0.0
    power_kw: float = 0.0
    belt: list[Parcel] = field(default_factory=list)
    weighed_t_total: float = 0.0   # belt weigher totalizer since the start (weighed rate x dt)
    fault: str = ""                # "" | "scenario": belt tripped (scenario conveyor:N); the crusher then has no room
    fault_until_min: float = NO_VALUE


@dataclass
class StockpileState:
    name: str                 # "stockpile-1"
    line: int
    state: str = "NORMAL"     # NORMAL | LOW | EMPTY | FULL
    level_t: float = 0.0
    in_tph: float = 0.0
    out_tph: float = 0.0
    hours_left: float = NO_VALUE
    column: dict[str, float] = field(default_factory=dict)   # batch id -> t, ideally mixed
    sides: dict[str, float] = field(default_factory=dict)    # batch id -> t, slow exchange
    cum_in_t: float = 0.0
    cum_out_t: float = 0.0
    feed_batch: str = ""      # batch with the largest share of the last SAG draw (lab sample booking)


# ---------------------------------------------------------------------------
# Grinding
# ---------------------------------------------------------------------------
@dataclass
class SagState:
    name: str                 # "sag-1"
    line: int
    state: str = "RUN"        # RUN | STARVED | LIMITED_GRID | RELINE | STOP
    power_kw: float = 0.0     # shaft
    power_limit_kw: float = 0.0
    power_sp_kw: float = 0.0  # control setpoint (shaft)
    feed_tph: float = 0.0     # fresh feed = throughput Q
    speed_pct: float = 0.0
    load_pct: float = 0.0
    e_kwh_t: float = 0.0
    axb_soft: float = NO_VALUE
    liner_wear_mm: float = 0.0   # published counter (by norm)
    liner_ground_t: float = 0.0  # published counter: ore ground since the last reline, t (tonnage counter, by norm)
    liner_x: float = 0.0         # truth: campaign share used
    eta: float = 1.0             # truth: liner efficiency multiplier
    reline_until_min: float = NO_VALUE
    feed_ore: OreProps = field(default_factory=OreProps)   # truth blend now in feed


@dataclass
class PebbleState:
    name: str                 # "pebble-1"
    line: int
    state: str = "RUN"        # RUN | LIMIT | STOP
    feed_tph: float = 0.0
    limit_tph: float = 0.0
    load_pct: float = 0.0
    stop_until_min: float = NO_VALUE
    hpgr_tph: float = 0.0       # rated HPGR throughput of the circuit (line 2: thyssenkrupp POLYCOM, vendor), 0 = not in the model
    hpgr_load_pct: float = 0.0  # feed / hpgr_tph
    hpgr_kw: float = 0.0        # HPGR drive power now: rated 2 x 1 750 kW x load, 0 when the circuit stands
    hpgr_eff: float = 1.0       # truth: share of the HPGR throughput kept (uneven feed / skew lowers it)
    hpgr_skew_pct: float = 0.0  # roll gap skew, % of the mean gap
    hpgr_kw_diff_pct: float = 0.0   # difference of the power of the two drives, %
    metal_alarm: bool = False   # metal detector in front of the HPGR tripped


@dataclass
class BallState:
    name: str                 # "ball-1a"
    line: int
    state: str = "RUN"        # RUN | STOP
    power_kw: float = 0.0     # shaft
    e_kwh_t: float = 0.0
    start_cmd: float = 0.0    # 1 while a start command is on (scenario startup: people may be inside)
    overload_pct: float = 0.0  # truth: draw above the rating, % (cyclone roping)


@dataclass
class CycloneState:
    name: str                 # "cyclones-1"
    line: int
    state: str = "NORMAL"     # NORMAL | UPSET
    p80_um: float = 0.0
    p80_grind_um: float = 0.0  # Bond result before cyclone effects
    pressure_kpa: float = 0.0
    open_count: int = 0
    clogged: int = 0           # truth: clogged but "open" units
    rope: float = 0.0          # truth: roping severity 0..1 (scenario roping:N)
    circ_load_pct: float = 0.0  # circulating load of the ball mill circuit, %


# ---------------------------------------------------------------------------
# Flotation and concentrate handling
# ---------------------------------------------------------------------------
@dataclass
class RougherState:
    name: str                 # "rougher-1"
    line: int
    state: str = "RUN"        # RUN | UPSET | STOP
    feed_tph: float = 0.0
    stage_recovery: float = 0.0   # %
    mass_pull_pct: float = 0.0
    rconc_cu: float = 0.0         # % Cu
    residence_min: float = 0.0
    dose_sp_gt: float = 0.0
    dose_meas_gt: float = 0.0
    dose_true_gt: float = 0.0     # truth
    tank_t: float = 0.0           # collector day tank, t (load cells; NO noise here, sensors add it)
    tank_in_t_total: float = 0.0  # deliveries into the tank since the start, t (booked)
    dose_t_total: float = 0.0     # flowmeter totalizer: reading x Q x dt, t


@dataclass
class CleanerState:
    name: str                 # "cleaner-1"
    line: int
    state: str = "RUN"
    feed_tph: float = 0.0     # rougher concentrate, t/h
    stage_recovery: float = 0.0   # %
    conc_cu: float = 0.0
    conc_tph: float = 0.0
    tail_cu: float = 0.0


@dataclass
class FlotState:
    """Section summary flot-N (parent of rougher-N and cleaner-N)."""
    name: str                 # "flot-1"
    line: int
    state: str = "RUN"        # RUN | UPSET | STOP
    feed_cu: float = 0.0
    tail_cu: float = 0.0
    conc_cu: float = 0.0
    recovery: float = 0.0     # % (lagged)
    cu_tph: float = 0.0
    conc_tph: float = 0.0
    history: list[tuple[float, float, float]] = field(default_factory=list)  # (t_min, R %, grade %) for delay
    rec_lag: float = 0.0      # first-order lag state, %
    grade_lag: float = 0.0


@dataclass
class ThickenerState:
    name: str                 # "thick-1"
    line: int
    state: str = "NORMAL"     # NORMAL | HIGH | FULL
    feed_tph: float = 0.0
    underflow_tph: float = 0.0
    inventory_t: float = 0.0
    solids_pct: float = 0.0
    overflow_m3h: float = 0.0
    hours_to_full: float = NO_VALUE
    feed_t_total: float = 0.0       # weigher totalizers since the start (each step's weighed rate x dt)
    underflow_t_total: float = 0.0


@dataclass
class FilterState:
    name: str                 # "filter-1"
    line: int
    state: str = "RUN"        # RUN | ONE | STOP
    presses_on: int = 0
    cake_tph: float = 0.0     # dry
    moisture_pct: float = 0.0
    limit_tph: float = 0.0


@dataclass
class LeachState:
    """Heap leach pad of the oxide line (sim/oxide.py): one state, the cathode level of the quarter."""
    name: str = "leach-1"
    state: str = "NORMAL"     # NORMAL | COLD
    quarter_cathode_kt: float = 0.0
    level_tph: float = 0.0
    cold_frac: float = 0.0


@dataclass
class SxewState:
    """SX-EW plant of the oxide line: cathode t/h (a quarterly figure of the reports, not a measurement)."""
    name: str = "sxew-1"
    state: str = "NORMAL"     # NORMAL | LOW
    cathode_tph: float = 0.0
    cathode_level_tph: float = 0.0
    cathode_t_total: float = 0.0
    year: float = 0.0
    quarter: float = 0.0


@dataclass
class ConcStockState:
    name: str = "conc-stock"
    state: str = "NORMAL"     # NORMAL | HIGH | FULL
    stock_t: float = 0.0      # wet
    in_tph: float = 0.0       # wet
    shipped_t_shift: float = 0.0
    wagons_shift: int = 0
    hours_to_full: float = NO_VALUE
    last_train_h: int = -1    # absolute model hour of last train


# ---------------------------------------------------------------------------
# Sensors (per line)
# ---------------------------------------------------------------------------
@dataclass
class AnalyzerState:
    """On-stream analyser: one reading per cycle, values hold until the next."""
    last_t_min: float = NO_VALUE
    feed_cu: float = NO_VALUE
    tail_cu: float = NO_VALUE
    conc_cu: float = NO_VALUE
    above_count: int = 0      # consecutive cycles with tail_cu above ACS setpoint
    alarm: bool = False
    blocked: bool = False     # truth: the sample line is blocked, the analyser keeps its last reading (scenario sample:N)


@dataclass
class PhState:
    """pH sensor of the rougher: the control holds the reading at the setpoint; a scaled electrode reads low, so the real pH
    is above the reading (truth bias) and a grab sample with a hand-held meter shows it."""
    reading: float = NO_VALUE        # online reading (held at the setpoint by the control)
    bias: float = 0.0                # truth: real pH minus reading
    lab_ph: float = NO_VALUE         # last grab sample
    lab_t_min: float = NO_VALUE      # model minute of the grab sample
    lab_idx: int = -1                # index of the grab sample interval
    confirmed: bool = False          # drift found (call of the module)


@dataclass
class LabResult:
    t_sample_min: float
    t_ready_min: float
    feed_cu: float
    ascu_pct: float
    tail_cu: float
    batch_id: str = ""        # batch that dominated the SAG feed at sampling time


@dataclass
class LabState:
    pending: list[LabResult] = field(default_factory=list)
    last: LabResult | None = None
    next_sample_min: float = NO_VALUE


# ---------------------------------------------------------------------------
# Line
# ---------------------------------------------------------------------------
@dataclass
class LineState:
    n: int
    state: str = "RUN"        # RUN | LIMITED | STOP
    tph: float = 0.0
    cu_tph: float = 0.0
    recovery: float = 0.0
    cum_cu_t: float = 0.0     # shift counters (reset by the plant at every shift start)
    cum_mwh: float = 0.0
    cum_m3: float = 0.0
    cum_usd: float = 0.0
    cum_cu_t_total: float = 0.0   # run totals of the same quantities, never reset (things.json line.cum_*_total)
    cum_mwh_total: float = 0.0
    cum_m3_total: float = 0.0
    cum_usd_total: float = 0.0
    balls_gt: float = 0.0     # grinding media consumption, g/t of ore (truth; the reading is noisy)
    crusher: CrusherState | None = None
    conveyor: ConveyorState | None = None
    stockpile: StockpileState | None = None
    sag: SagState | None = None
    pebble: PebbleState | None = None
    balls: list[BallState] = field(default_factory=list)
    cyclones: CycloneState | None = None
    rougher: RougherState | None = None
    cleaner: CleanerState | None = None
    flot: FlotState | None = None
    thick: ThickenerState | None = None
    filter: FilterState | None = None
    analyzer: AnalyzerState = field(default_factory=AnalyzerState)
    lab: LabState = field(default_factory=LabState)
    ph: PhState = field(default_factory=PhState)
    down_windows: list[tuple[float, float]] = field(default_factory=list)  # calib: planned stops


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
@dataclass
class WaterState:
    state: str = "NORMAL"     # NORMAL | LOW | ALARM
    intake_m3h: float = 0.0
    recycle_m3h: float = 0.0
    tails_loss_m3h: float = 0.0
    evap_m3h: float = 0.0
    pond_m3: float = 0.0
    residual_pct: float = 0.0
    piezo_kpa: float = 0.0
    proc_m3h: float = 0.0          # water to process
    pond_in_m3h: float = 0.0
    pond_return_m3h: float = 0.0
    thick_overflow_m3h: float = 0.0
    conc_moist_m3h: float = 0.0
    intake_m3_total: float = 0.0    # intake flowmeter totalizer since the start (measured rate x dt)
    loss_m3_total: float = 0.0      # water that leaves: tails pores + concentrate moisture + evaporation
                                    # + pipeline leak, m3
    leak_m3h: float = 0.0           # return water lost through a pipeline leak (scenario water)
    short_m3h: float = 0.0          # process water missing above the fresh-water cap
    demand_m3h: float = 0.0         # fresh water the process would take without the cap
    intake_cap_m3h: float = 0.0
    cut_tph: float = 0.0            # ore held back on both lines for lack of water (set by the plant)
    air_temp_c: float = 0.0         # weather (sim/utilities.weather)
    wind_ms: float = 0.0
    beach_dry_pct: float = 0.0
    winter: float = 0.0             # 1 while the winter return loss is on


@dataclass
class WaterFlows:
    """Inputs of the water balance for one step."""
    ore_tph: float = 0.0           # both lines, t/h
    tails_tph: float = 0.0         # tails solids, t/h
    cake_tph: float = 0.0          # dry concentrate cake, t/h
    cake_moist_pct: float = 0.0
    thick_overflow_m3h: float = 0.0
    leak_frac: float = 0.0         # share of the pond return lost through a pipeline leak
    winter_frac: float = 0.0       # share of the pond return that does not reach the process (winter ice)


@dataclass
class PowerState:
    state: str = "NORMAL"     # NORMAL | LIMITED
    grid_limit_mw: float = 0.0
    site_mw: float = 0.0
    grinding_mw: float = 0.0       # mills from grid
    grinding_shaft_mw: float = 0.0
    cc_mw: float = 0.0             # crushers + conveyors
    other_mw: float = 0.0          # site part + line part of running lines
    shed_mw: float = 0.0
    headroom_mw: float = 0.0
    shed: list[str] = field(default_factory=list)   # shed units and feeders
    line_aux_mw: float = 0.0       # line part of other_mw (running lines x pow_line_aux_mw)


@dataclass
class PowerLoads:
    """Inputs of the power balance for one step (shaft kW from units)."""
    sag_kw: dict[int, float] = field(default_factory=dict)
    ball_kw: dict[str, float] = field(default_factory=dict)
    crusher_kw: dict[int, float] = field(default_factory=dict)
    conveyor_kw: dict[int, float] = field(default_factory=dict)


@dataclass
class ShedPlan:
    """Load-shedding decision for a grid limit."""
    balls_off: list[str] = field(default_factory=list)       # ball mill names
    other_shed_mw: float = 0.0
    sag_cap_kw: dict[int, float] = field(default_factory=dict)  # shaft power cap per line


# ---------------------------------------------------------------------------
# Crews, hidden causes, scenarios, counters
# ---------------------------------------------------------------------------
@dataclass
class CrewJob:
    issue: str                # issue id or node name
    node: str                 # thingId where the work is
    t_call_min: float
    t_arrive_min: float
    t_done_min: float


@dataclass
class CrewState:
    name: str                 # "crew-kip"
    role: str                 # "kip" | "crusher_mech" | "plant_mech" | "tailings_engineer"
    count: int = 1            # people (teams) available in parallel
    state: str = "FREE"       # FREE | TRAVEL | WORK | OFF
    task: str = ""
    free_at_min: float = NO_VALUE   # earliest model minute a team is free (NO_VALUE when free now)
    slot_free_min: list[float] = field(default_factory=list)  # per team: busy until
    jobs: list[CrewJob] = field(default_factory=list)


@dataclass
class PlannedCall:
    """A call to a crew at a given model minute (button, module or copy policy)."""
    t_min: float
    node: str                 # thingId where the work is, e.g. "crusher-2"
    crew: str                 # "crew-kip" | "crew-cpd" | "crew-mill" | "crew-water"
    issue: str                # issue key, e.g. "trip:2", "dose:1", "crusher:1"
    work_h: float = NO_VALUE  # repair time after arrival, h (NO_VALUE: drawn by events)
    src: str = ""             # who called, for Plant.call_log ("" = the way it is booked: plan, alarm)


@dataclass
class HiddenCause:
    kind: str                 # "liner" | "cyclone" | "dose" | "oxide" | silent: "energy" | "reagent" | "leak"
    line: int
    t_start_min: float
    magnitude: float          # kind units: eta loss, clogged count, dose drop share, ASCu pp
    t_found_min: float = NO_VALUE
    t_end_min: float = NO_VALUE
    found_by: str = ""        # "lab", "acs", "module", "crew", "report", "audit", "patrol"
    preset: bool = False      # set by a scenario, not drawn


@dataclass
class CauseEffects:
    """Combined effect of active hidden causes on one line at one moment."""
    sag_eta_mult: float = 1.0       # SAG capacity multiplier
    sag_e_mult: float = 1.0         # SAG specific energy multiplier (overload, coarse feed)
    liner_wear_mult: float = 1.0    # true wear rate multiplier
    clogged: int = 0                # clogged cyclones
    dose_ratio: float = 1.0         # true / setpoint collector dose (> 1: overdose, no recovery gain)
    leak_frac: float = 0.0          # silent return-water leak (site-wide, taken from line 0 causes)
    ascu_add_pp: float = 0.0        # ASCu above estimate
    balls_mult: float = 1.0         # grinding media consumption multiplier (silent overuse)
    conc_drop_pp: float = 0.0       # concentrate grade lost to dilution, pp
    rope: float = 0.0               # cyclone roping severity 0..1 (ramps up after the start)
    rope_flot_pp: float = 0.0       # recovery loss after heavy roping that nobody stopped, pp
    ph_bias: float = 0.0            # real pH above the pH reading (scaled electrode)


@dataclass
class ScenarioEvent:
    kind: str                 # crusher | grid | hard | reline | dose | cyclone | liner | oxide | trip | safety
    line: int                 # 0 for site-wide
    t_start_min: float
    duration_h: float = NO_VALUE
    data: dict = field(default_factory=dict)


@dataclass
class ScenarioSpec:
    text: str = ""            # "crusher:1+grid"
    preset: str = ""          # "" | "fork"
    kip: int = 1
    safety: bool = False
    auto: bool = False
    t0_min: float = 0.0
    events: list[ScenarioEvent] = field(default_factory=list)


@dataclass
class Counters:
    ore_t: float = 0.0
    cu_feed_t: float = 0.0
    cu_conc_t: float = 0.0
    conc_t: float = 0.0
    tails_cu_t: float = 0.0
    energy_mwh: float = 0.0
    water_intake_m3: float = 0.0
    water_recycle_m3: float = 0.0
    usd: float = 0.0
    co2_t: float = 0.0
    minutes: float = 0.0

    def add(self, other: "Counters") -> None:
        for k in self.__dataclass_fields__:
            setattr(self, k, getattr(self, k) + getattr(other, k))


@dataclass
class TruthEntry:
    """Line of validation-sim.truth_log (written after the cause is fixed)."""
    t_min: float
    kind: str
    line: int
    text: str
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Whole plant
# ---------------------------------------------------------------------------
@dataclass
class PlantState:
    clock: Clock
    seed: int
    mode: str                 # "free" | "scenario" | "calib"
    run_id: str = ""
    site_state: str = "RUN"   # RUN | PAUSED | WARMUP
    pit: PitState = field(default_factory=PitState)
    excavators: list[ExcavatorState] = field(default_factory=list)
    fleet: FleetState = field(default_factory=FleetState)
    batches: dict[str, Batch] = field(default_factory=dict)
    next_batch_no: int = 1
    lines: list[LineState] = field(default_factory=list)   # index 0 -> line 1
    conc_stock: ConcStockState = field(default_factory=ConcStockState)
    leach: LeachState = field(default_factory=LeachState)
    sxew: SxewState = field(default_factory=SxewState)
    water: WaterState = field(default_factory=WaterState)
    power: PowerState = field(default_factory=PowerState)
    crews: dict[str, CrewState] = field(default_factory=dict)
    causes: list[HiddenCause] = field(default_factory=list)
    scenario: ScenarioSpec | None = None
    shift: Counters = field(default_factory=Counters)
    total: Counters = field(default_factory=Counters)
    line_shift: dict[int, Counters] = field(default_factory=lambda: {1: Counters(), 2: Counters()})
    truth_log: list[TruthEntry] = field(default_factory=list)
    flags: dict[str, float] = field(default_factory=dict)  # e.g. "piezo": 1.0, "fire": line
    waste_excavators: list[ExcavatorState] = field(default_factory=list)   # stripping, not in the ore path
    trucks: list[TruckState] = field(default_factory=list)
    faces: dict[str, FaceState] = field(default_factory=dict)
    roads: dict[str, RoadState] = field(default_factory=dict)
    people: dict[str, PersonState] = field(default_factory=dict)
    drills: list[DrillState] = field(default_factory=list)
    dozers: list[DozerState] = field(default_factory=list)
    wear: dict[str, dict] = field(default_factory=dict)   # tier T: key "gmd:1" -> {t0, fix, failed} (scenario only)

    # what-if levers (control of the model, off = empty): feed_1, feed_2 (% of the nominal line rate), p80_um (grind target),
    # dose_gt (collector dose). Set by Plant.set_levers only; a neutral value is never stored.
    levers: dict[str, float] = field(default_factory=dict)

    def line(self, n: int) -> LineState:
        return self.lines[n - 1]


class PlantHooks:
    """Callbacks from Plant.step; the service layer overrides them.

    Default methods do nothing. Hooks must not change the state.
    """

    def on_step(self, st: PlantState) -> None:
        pass

    def on_checkpoint(self, st: PlantState) -> None:
        """Every cal_checkpoint_min model minutes (publish point T)."""

    def on_batch(self, st: PlantState, batch: Batch) -> None:
        """Batch changed state or was created/deleted."""

    def on_truth(self, st: PlantState, entry: TruthEntry) -> None:
        """Hidden cause start/end, for validation-sim only."""

    def on_shift_end(self, st: PlantState, summary: dict) -> None:
        """Shift counters before reset (free run) or at auto pause (scenario)."""


# ---------------------------------------------------------------------------
# Topology (design section 3): things, parents, feeds, responsible roles
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ThingInfo:
    thing_id: str             # without namespace, e.g. "sag-1"
    type: str                 # one of params.FEATURE_RULES keys
    parents: tuple[str, ...]
    feeds: tuple[str, ...] = ()
    role: str = ""


def topology() -> dict[str, ThingInfo]:
    """Permanent physical things of the stand (batches and service things excluded)."""
    t: dict[str, ThingInfo] = {}

    def add(tid, typ, parents, feeds=(), role=""):
        t[tid] = ThingInfo(tid, typ, tuple(parents), tuple(feeds), role)

    add("site", "site", (), role="shift_supervisor")
    add("pit", "pit", ("site",), ("exc-1", "exc-2", "exc-3"), "mine_dispatcher")
    for i in (1, 2, 3):
        add(f"exc-{i}", "exc", ("pit",), ("fleet",), "mine_dispatcher")
    add("fleet", "fleet", ("pit",), ("crusher-1", "crusher-2"), "mine_dispatcher")
    for n in (1, 2):
        add(f"crusher-{n}", "crusher", ("site",), (f"conveyor-{n}",), "crusher_mech")
        add(f"conveyor-{n}", "conveyor", ("site",), (f"stockpile-{n}",), "crusher_mech")
        add(f"stockpile-{n}", "stockpile", ("site",), (f"sag-{n}",), "mine_dispatcher")
        add(f"line-{n}", "line", ("site",), (), "plant_shift_manager")
        add(f"sag-{n}", "sag", (f"line-{n}",), (f"pebble-{n}", f"cyclones-{n}"), "grinding_operator")
        add(f"pebble-{n}", "pebble", (f"line-{n}",), (f"sag-{n}",), "grinding_operator")
        add(f"ball-{n}a", "ball", (f"line-{n}",), (f"cyclones-{n}",), "plant_mech")
        add(f"ball-{n}b", "ball", (f"line-{n}",), (f"cyclones-{n}",), "plant_mech")
        add(f"cyclones-{n}", "cyclones", (f"line-{n}",),
            (f"ball-{n}a", f"ball-{n}b", f"rougher-{n}"), "control_operator")
        add(f"flot-{n}", "flot", (f"line-{n}",), (), "shift_metallurgist")
        add(f"rougher-{n}", "rougher", (f"flot-{n}",), (f"cleaner-{n}", "water"), "shift_metallurgist")
        add(f"cleaner-{n}", "cleaner", (f"flot-{n}",), (f"thick-{n}", "water"), "shift_metallurgist")
        add(f"thick-{n}", "thick", (f"line-{n}",), (f"filter-{n}", "water"), "plant_shift_manager")
        add(f"filter-{n}", "filter", (f"line-{n}",), ("conc-stock",), "plant_shift_manager")
    add("conc-stock", "conc-stock", ("site",), (), "plant_shift_manager")
    add("leach-1", "leach", ("site",), ("sxew-1",), "shift_metallurgist")
    add("sxew-1", "sxew", ("site",), (), "shift_metallurgist")
    add("water", "water", ("site",), ("line-1", "line-2"), "tailings_engineer")
    add("power", "power", ("site",), (), "power_engineer")
    # a crew answers through the person who leads it (site CREW_PERSON, modules/priority.CREW_LEAD)
    add("crew-kip", "crew", ("site",), (), "kip")
    add("crew-cpd", "crew", ("site",), (), "crusher_mech")
    add("crew-mill", "crew", ("site",), (), "plant_mech")
    add("crew-water", "crew", ("site",), (), "tailings_engineer")
    # site passport: people, pit fleet, faces, roads, instruments (sim/site_<name>.py)
    s = site()
    for pid, role, _ru, _crew, _home in s.PEOPLE:
        add(pid, "person", ("site",), (), role)
    for eid, duty, _face in s.EXCAVATORS:
        if eid not in t:
            add(eid, "exc", ("pit",), ("fleet",) if duty == "ore" else (), "mine_dispatcher")
    for fid, _exc, _kind, _bench in s.FACES:
        add(fid, "face", ("pit",), (), "shift_geologist")
    for rid, _ru, _line in s.ROADS:
        add(rid, "road", ("pit",), (), "mine_dispatcher")
    for tid, _model, _pkey, _duty, _line in s.truck_roster():
        add(tid, "truck", ("fleet",), (), "mine_dispatcher")
    for did, _bort, _model, _face in getattr(s, "DRILLS", ()):
        add(did, "drill", ("pit",), (), "mine_dispatcher")
    for zid, _bort, _model, _place in getattr(s, "DOZERS", ()):
        add(zid, "dozer", ("pit",), (), "mine_dispatcher")
    for iid, typ, parent, _ru in s.INSTRUMENTS:
        add(iid, typ, (parent,), (), "tailings_engineer" if typ == "piezometer" else "kip")
    return t


_SITE = None


def site():
    """Site passport module sim/site_<AKT_SITE> (default aktogay): people, fleet, faces, roads, instruments."""
    global _SITE
    if _SITE is None:
        import importlib
        import os
        name = os.environ.get("AKT_SITE", "aktogay").strip() or "aktogay"
        _SITE = importlib.import_module(f".site_{name}", __package__)
    return _SITE


# Which crew fixes which node kind (design section 5).
CREW_FOR = {
    "lube_trip": "crew-kip", "dose": "crew-kip", "sensor": "crew-kip",
    "crusher": "crew-cpd", "conveyor": "crew-cpd",
    "sag": "crew-mill", "ball": "crew-mill", "pebble": "crew-mill", "filter": "crew-mill",
    "cyclone": "crew-mill", "liner": "crew-mill",
    "reagent": "crew-kip",          # collector overdose: the flowmeter reads low, the pump gives more
    "leak": "crew-water",           # silent return-water leak, found by the water balance
    "water": "crew-water",          # return-water pipeline: the tailings and water team, not the mill mechanics
    "startup": "crew-mill",         # mill under repair with people inside: the mill crew
    "phdrift": "crew-kip",          # scaled pH electrode: the I&C technician cleans and calibrates it
    "hpgr": "crew-mill",            # uneven HPGR feed / tramp metal: the mill crew
    "mantle": "crew-cpd",           # planned mantle change of the primary crusher
    "sample": "crew-kip",           # blocked sample line of the analyser: the I&C technician cleans it
}


# ---------------------------------------------------------------------------
# Initial state at the warm-up start (06:00) from parameters
# ---------------------------------------------------------------------------
def base_ore(prm) -> OreProps:
    return OreProps(prm["blk_cu_mean_pct"], prm["blk_ascu_mean_pct"], prm["ore_axb_base"], prm["ore_bwi_base"])


def batch_name(no: int) -> str:
    return f"batch-{no:04d}"


def feed_end_wear_mm(wear_mm: float, prm) -> float:
    """SAG feed-end wear counter, mm: wear since the last feed-end change.

    The feed end is changed at intermediate relines every liner_feed_end_mm
    of wear (Bradken), so the counter restarts there: wear mod liner_feed_end_mm.
    """
    cap = prm["liner_feed_end_mm"]
    w = max(0.0, wear_mm)
    return math.fmod(w, cap) if cap > 0.0 else w


def hpgr_tph(prm, line: int) -> float:
    """Rated HPGR throughput of the pebble circuit of `line`, t/h: line 2 has the thyssenkrupp POLYCOM (1 061 t/h, vendor);
    line 1 has an HPGR section too (fire of 09.08.2026) but no published rating: 0 = not in the model."""
    return float(prm["peb_hpgr_l2_tph"]) if line == 2 else 0.0


def peb_limit_tph(prm, line: int) -> float:
    """Throughput limit of the pebble circuit of `line`, t/h: the cone crushers (peb_limit_tph); on line 2 also
    below the HPGR (min of both, so the cones stay the limit while they are the smaller)."""
    h = hpgr_tph(prm, line)
    return min(float(prm["peb_limit_tph"]), h) if h > 0.0 else float(prm["peb_limit_tph"])


def initial_state(prm, seed: int | None = None, mode: str = "free", t0_min: float | None = None,
                  year: int = 2026, origin_doy: int = 0) -> PlantState:
    """Base-case plant at t0 (default 06:00 of day 0), all units at design values.

    No physics runs here: steady values are copied from the table so
    that step() starts from a consistent point. Each stockpile holds one
    "initial" batch with base ore (estimate = truth).
    """
    seed = int(prm["cal_seed"] if seed is None else seed)
    t0 = prm["cal_warmup_from_h"] * MIN_PER_H if t0_min is None else t0_min
    st = PlantState(clock=Clock(t_min=t0, dt_min=prm["cal_step_live_min"], year=year, origin_doy=origin_doy),
                    seed=seed, mode=mode)
    q = prm["cal_line_tph"]
    ore = base_ore(prm)
    sag_kw = prm["sag_power_sp_mw"] * 1000.0
    ball_kw = prm["ball_power_mw"] * 1000.0
    ball_ids = ("a", "b")
    rec = prm["flot_rec_ref_pct"]
    grade_c = prm["flot_conc0_pct"]
    g = prm["blk_cu_mean_pct"]
    conc_tph = q * g * rec / 100.0 / grade_c
    tail = g * (1 - rec / 100.0) / (1 - conc_tph / q)
    # rougher concentrate and cleaner tails grades by the same mass balance as flotation_step
    pull = prm["flot_pull0_pct"]
    r_rough = rec / prm["clean_r0_pct"] * 100.0
    rconc_cu = g * r_rough / pull
    clean_feed = q * pull / 100.0
    clean_tail = 100.0 * q * g / 100.0 * (r_rough - rec) / 100.0 / (clean_feed - conc_tph)
    for n in (1, 2):
        b = Batch(batch_name(st.next_batch_no), 0, n, prm[f"stock{n}_t0"], ore.copy(), ore.copy(),
                  state="IN_STOCK", location=f"stockpile-{n}", dug_t=prm[f"stock{n}_t0"],
                  tonnes_left=prm[f"stock{n}_t0"], stock_mark_t=prm[f"stock{n}_t0"], t_created_min=t0,
                  tag="initial")
        st.batches[b.batch_id] = b
        st.next_batch_no += 1
        level = prm[f"stock{n}_t0"]
        col = min(level, prm["stock_column_frac"] * prm["stock_live_t"])
        ln = LineState(
            n=n, tph=q, cu_tph=q * g / 100.0 * rec / 100.0, recovery=rec,
            crusher=CrusherState(f"crusher-{n}", n, tph=q, power_kw=prm["crush_power_mw"] * 1000.0,
                                 lube_kpa=prm["crush_lube_kpa"]),
            conveyor=ConveyorState(f"conveyor-{n}", n, tph=q, power_kw=prm["conv_power_mw"] * 1000.0),
            stockpile=StockpileState(f"stockpile-{n}", n, level_t=level, in_tph=q, out_tph=q,
                                     column={b.batch_id: col}, sides={b.batch_id: level - col},
                                     cum_in_t=level),
            sag=SagState(f"sag-{n}", n, power_kw=sag_kw, power_limit_kw=prm["sag_rated_mw"] * 1000.0,
                         power_sp_kw=sag_kw, feed_tph=q, speed_pct=prm["sag_speed_pct"],
                         load_pct=prm["sag_load0_pct"], e_kwh_t=sag_kw / q, axb_soft=ore.axb,
                         liner_x=prm["liner_x0"], liner_ground_t=prm["liner_x0"] * prm["liner_life_mt"] * 1.0e6,
                         liner_wear_mm=feed_end_wear_mm(
                             prm["liner_x0"] * prm["liner_life_mt"] * prm["liner_wear_mm_mt"], prm),
                         feed_ore=ore.copy()),
            pebble=PebbleState(f"pebble-{n}", n, feed_tph=prm["peb_frac_base"] * q, limit_tph=peb_limit_tph(prm, n),
                               load_pct=100.0 * prm["peb_frac_base"] * q / peb_limit_tph(prm, n),
                               hpgr_tph=hpgr_tph(prm, n),
                               hpgr_load_pct=(100.0 * prm["peb_frac_base"] * q / hpgr_tph(prm, n)
                                              if hpgr_tph(prm, n) > 0.0 else 0.0),
                               hpgr_kw=(prm["peb_hpgr_l2_kw"] * min(1.0, prm["peb_frac_base"] * q / hpgr_tph(prm, n))
                                        if hpgr_tph(prm, n) > 0.0 else 0.0)),
            # each running mill grinds q / (mills running)
            balls=[BallState(f"ball-{n}{s}", n, power_kw=ball_kw, e_kwh_t=ball_kw * len(ball_ids) / q)
                   for s in ball_ids],
            cyclones=CycloneState(f"cyclones-{n}", n, p80_um=prm["ball_p80_target_um"],
                                  p80_grind_um=prm["ball_p80_target_um"], pressure_kpa=prm["cyc_pressure_kpa"],
                                  open_count=int(prm["cyc_open"]), circ_load_pct=prm["cyc_circ_base_pct"]),
            rougher=RougherState(f"rougher-{n}", n, feed_tph=q, mass_pull_pct=prm["flot_pull0_pct"],
                                 residence_min=prm["flot_tau0_min"], dose_sp_gt=prm["flot_dose_sp_gt"],
                                 dose_meas_gt=prm["flot_dose_sp_gt"], dose_true_gt=prm["flot_dose_sp_gt"],
                                 stage_recovery=r_rough, rconc_cu=rconc_cu, tank_t=prm["flot_reag_tank_t"]),
            cleaner=CleanerState(f"cleaner-{n}", n, stage_recovery=prm["clean_r0_pct"], conc_cu=grade_c,
                                 conc_tph=conc_tph, feed_tph=clean_feed, tail_cu=clean_tail),
            flot=FlotState(f"flot-{n}", n, feed_cu=g, tail_cu=tail, conc_cu=grade_c, recovery=rec,
                           cu_tph=q * g / 100.0 * rec / 100.0, conc_tph=conc_tph, rec_lag=rec, grade_lag=grade_c),
            ph=PhState(reading=prm["flot_ph_sp"], lab_ph=prm["flot_ph_sp"], lab_t_min=t0),
            thick=ThickenerState(f"thick-{n}", n, feed_tph=conc_tph, underflow_tph=conc_tph,
                                 inventory_t=prm["thick_t0"], solids_pct=prm["thick_uf_solids_pct"]),
            filter=FilterState(f"filter-{n}", n, presses_on=int(prm["filt_presses"]), cake_tph=conc_tph,
                               moisture_pct=prm["filt_moist_pct"],
                               limit_tph=prm["filt_presses"] * prm["filt_press_tph"]),
        )
        st.lines.append(ln)
        # Pipeline already full at t0: haul road and belt carry base ore at q.
        haul_min, belt_min = prm["pit_haul_min"], prm["conv_transit_min"]
        pipe_t = q * (haul_min + belt_min) / MIN_PER_H
        pb = Batch(batch_name(st.next_batch_no), 0, n, pipe_t, ore.copy(), ore.copy(), state="BELT",
                   location=f"conveyor-{n}", dug_t=pipe_t, tonnes_left=pipe_t, t_created_min=t0,
                   t_dig_min=t0, t_belt_min=t0, tag="initial")
        st.batches[pb.batch_id] = pb
        st.next_batch_no += 1
        for minutes, queue in ((haul_min, st.pit.haul[n]), (belt_min, ln.conveyor.belt)):
            k = 0
            while k < minutes:
                share = min(1.0, minutes - k)
                queue.append(Parcel(pb.batch_id, q / MIN_PER_H * share, t0 + k))
                k += 1
    n_exc = int(prm["pit_exc_count"])
    for i in range(1, n_exc + 1):
        st.excavators.append(ExcavatorState(f"exc-{i}", line=1 if i == 1 else 2 if i == 2 else 1,
                                            tph=prm["pit_exc_tph"], oil_pct=prm["pit_oil_start_pct"]))
    s = site()
    for eid, duty, _face in s.EXCAVATORS[n_exc:n_exc + int(prm["pit_exc_waste_count"])]:
        if duty == "waste":
            st.waste_excavators.append(ExcavatorState(eid, line=0, tph=prm["pit_exc_waste_tph"], duty="waste",
                                                      block=""))
    roster = s.truck_roster(prm)
    from . import haul
    trip = {n: haul.cycle_min(prm, n) for n in (0, 1, 2)}
    by_duty: dict[tuple[str, int], int] = {}
    for _tid, _m, _pk, duty, line in roster:
        by_duty[(duty, line)] = by_duty.get((duty, line), 0) + 1
    seen: dict[tuple[str, int], int] = {}
    for k, (tid, model, p_key, duty, line) in enumerate(roster):
        j = seen.get((duty, line), 0)
        seen[(duty, line)] = j + 1
        # trucks of one route spread evenly over the cycle
        st.trucks.append(TruckState(tid, model, prm[p_key], duty, line, k,
                                    phase_min=trip[line] * j / by_duty[(duty, line)], cycle_min=trip[line]))
    exc_bench = {}
    for fid, exc, kind, bench in s.FACES:
        st.faces[fid] = FaceState(fid, exc, kind, int(bench), blasted_t=prm["pit_face_blasted_t0"])
        exc_bench[exc] = int(bench)
    for k, (did, _bort, model, face) in enumerate(getattr(s, "DRILLS", ())):
        st.drills.append(DrillState(did, model, face, k))
    for k, (zid, _bort, model, place) in enumerate(getattr(s, "DOZERS", ())):
        st.dozers.append(DozerState(zid, model, place, k))
    for e in st.excavators + st.waste_excavators:
        e.bench = exc_bench.get(e.name, e.bench)
    for rid, _ru, line in s.ROADS:
        st.roads[rid] = RoadState(rid, int(line))
    for pid, role, _ru, crew, home in s.PEOPLE:
        st.people[pid] = PersonState(pid, role, crew, home, location=home)
    n_trucks = len(st.trucks) if st.trucks else int(prm["fleet_trucks"])
    st.fleet = FleetState(exc_total=n_exc + len(st.waste_excavators), exc_ready=n_exc + len(st.waste_excavators),
                          trucks_total=n_trucks, trucks_ready=int(round(n_trucks * prm["fleet_kio"])),
                          truck_kio_shift=prm["fleet_kio"])
    if st.trucks:
        ore_t = sum(tr.payload_t for tr in st.trucks if tr.duty == "ore")
        st.fleet.haul_tph = sum(tr.payload_t * MIN_PER_H / tr.cycle_min for tr in st.trucks if tr.duty == "ore") * prm["fleet_kio"]
    else:
        st.fleet.haul_tph = (st.fleet.trucks_ready * prm["fleet_payload_t"] * MIN_PER_H
                             / haul.mean_ore_cycle_min(prm))
    st.conc_stock = ConcStockState(stock_t=prm["cstock_t0"])
    st.water = WaterState(pond_m3=prm["pond_m3_0"], piezo_kpa=prm["pond_piezo_kpa0"],
                          evap_m3h=prm["water_evap_m3h"], intake_cap_m3h=prm["water_intake_cap_m3h"])
    aux = len(st.lines) * prm["pow_line_aux_mw"]            # both lines run at the snapshot
    st.power = PowerState(grid_limit_mw=prm["pow_grid_limit_mw"], other_mw=prm["pow_other_mw"] + aux,
                          line_aux_mw=aux)
    for name, role, key in (("crew-kip", "kip", "crew_kip"), ("crew-cpd", "crusher_mech", "crew_cpd"),
                            ("crew-mill", "plant_mech", "crew_mill"),
                            ("crew-water", "tailings_engineer", "crew_water")):
        cnt = int(prm[key])
        st.crews[name] = CrewState(name, role, count=cnt, slot_free_min=[NO_VALUE] * cnt)
    return st
