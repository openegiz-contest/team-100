"""akt-ore: which ore is coming. Stockpile window model, 12 h forecast, hindsight check.

Design file 17, section 3 ("the stockpile is not FIFO") and section 5
("which ore is coming"). Every 15 model minutes:

- Its own stockpile model per line on block-model estimates: a draw column
  (about 30 % of the live stock, ideally mixed) over the feeders and the
  sides that exchange with the column slowly (tau 24 h). Fresh ore lands
  in the column, so a new batch reaches the SAG before the old ore on the
  sides. Masses are scaled to the measured level every tact.
- Arrival window of every batch: "earlier" when its share of the feed
  reaches 10 %, "expected" at 50 % (or the peak share), "late" when the
  share falls back below 10 %.
- 12 h forecast per hour: t/h, t Cu/h, USD/h from the planned batches
  (dig at the mining rate, haul 30 min, belt 14 min) through the pile model
  and the SAG energy of the blend (energies add by tonnes; A*b is not averaged).
- Hindsight ("did it come true"): when the soft-sensor A*b of the SAG
  (median over 45 min) drops below the midpoint between the base and the
  estimated hard ore, the arrival is on record; it is a hit when it falls
  inside the window. The block error (sigma 12 %) makes misses expected.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from . import expect as ex
from .batches import BatchView, all_batches
from .params import Prm
from .store import NO_VALUE, Store, as_float
from .text import EST, batch_ru, dur, hhmm_day, num, signed

log = logging.getLogger("ore")

LINES = (1, 2)
READS = ("site", "pit", "exc-1", "exc-2", "exc-3", "fleet", "crusher-1", "crusher-2", "conveyor-1", "conveyor-2",
         "stockpile-1", "stockpile-2", "sag-1", "sag-2", "pebble-1", "pebble-2", "power", "line-1", "line-2",
         "flot-1", "flot-2")
READS_TYPES = ("batch",)
BACKFILL_FIELDS = ("feed_tph", "axb_soft", "level_t", "in_tph", "out_tph", "state", "layers_l1", "layers_l2")
REST = "rest"
STEP_MIN = 5.0


@dataclass
class PileModel:
    """Draw column and sides of one stockpile; masses in t per batch key."""
    column: dict = field(default_factory=dict)
    sides: dict = field(default_factory=dict)
    props: dict = field(default_factory=dict)      # key -> (A*b, Cu %)

    def copy(self) -> "PileModel":
        return PileModel(dict(self.column), dict(self.sides), dict(self.props))

    def column_mass(self) -> float:
        return sum(self.column.values())

    def total(self) -> float:
        return self.column_mass() + sum(self.sides.values())

    def add(self, key: str, tonnes: float, axb: float, cu: float) -> None:
        if tonnes <= 0.0:
            return
        self.column[key] = self.column.get(key, 0.0) + tonnes
        self.props[key] = (axb, cu)

    def _take(self, d: dict, tonnes: float) -> dict:
        m = sum(d.values())
        if m <= 0.0 or tonnes <= 0.0:
            return {}
        f = min(1.0, tonnes / m)
        out = {}
        for k in list(d):
            x = d[k] * f
            out[k] = x
            d[k] -= x
            if d[k] < 1e-6:
                del d[k]
        return out

    def draw(self, tonnes: float) -> dict:
        """Remove tonnes from the column (sides when the column is empty); returns what left per key."""
        out = self._take(self.column, tonnes)
        short = tonnes - sum(out.values())
        if short > 1e-6:
            for k, v in self._take(self.sides, short).items():
                out[k] = out.get(k, 0.0) + v
        return out

    def exchange(self, tonnes: float) -> None:
        """Swap tonnes between column and sides (both compositions move)."""
        if tonnes <= 0.0:
            return
        x = min(tonnes, self.column_mass(), sum(self.sides.values()))
        if x <= 0.0:
            return
        from_c = self._take(self.column, x)
        from_s = self._take(self.sides, x)
        for k, v in from_c.items():
            self.sides[k] = self.sides.get(k, 0.0) + v
        for k, v in from_s.items():
            self.column[k] = self.column.get(k, 0.0) + v

    def spill(self, column_target: float) -> None:
        """Excess column mass slides to the sides (proportionally)."""
        excess = self.column_mass() - column_target
        if excess > 1e-6:
            for k, v in self._take(self.column, excess).items():
                self.sides[k] = self.sides.get(k, 0.0) + v

    def scale_to(self, total: float) -> None:
        m = self.total()
        if total < 0.0 or m <= 0.0:
            return
        f = total / m
        for d in (self.column, self.sides):
            for k in list(d):
                d[k] *= f

    def shares(self) -> dict:
        m = self.column_mass()
        return {k: v / m for k, v in self.column.items()} if m > 0.0 else {}

    def mix(self, prm: Prm) -> tuple[list, float]:
        """([(share, A*b)], Cu %) of the column (base ore when empty)."""
        sh = self.shares()
        if not sh:
            return [(1.0, prm["ore_axb_base"])], prm["flot_grade_ref_pct"]
        mixes = [(s, self.props.get(k, (prm["ore_axb_base"], prm["flot_grade_ref_pct"]))[0]) for k, s in sh.items()]
        cu = sum(s * self.props.get(k, (0.0, prm["flot_grade_ref_pct"]))[1] for k, s in sh.items())
        return mixes, cu


@dataclass
class Forecast:
    batch: str
    line: int
    made_at: float
    early: float          # model min
    expected: float
    late: float
    tph_fc: float
    axb: float
    done: bool = False
    hit: bool = False
    text: str = ""
    t_arrived: float = NO_VALUE   # model min the soft sensor saw it
    tph_min: float = NO_VALUE     # lowest 1 h mean SAG feed since the arrival (compared with tph_fc)
    tph_done: bool = False


@dataclass
class Layer:
    batch: str
    block: str
    line: int
    axb: float
    cu: float
    cls: str
    tonnes: float
    state: str
    early: float = NO_VALUE
    expected: float = NO_VALUE
    late: float = NO_VALUE
    share_now: float = 0.0
    tph_at: float = NO_VALUE


class OreModule:
    name = "ore"
    thing = "mod-ore"

    def __init__(self, prm: Prm, store: Store):
        self.prm = prm
        self.store = store
        self.tact = prm["tact_ore_min"]
        self.processed = NO_VALUE
        self.last_t = NO_VALUE
        self.piles: dict[int, PileModel] = {}
        self.seen: dict[str, str] = {}          # batch -> last state
        self.newest: dict[int, str] = {}        # line -> batch key that receives the inflow
        self.forecasts: dict[str, Forecast] = {}
        self.hard_now: dict[int, bool] = {n: False for n in LINES}
        self.hits = 0
        self.misses = 0
        self.last_check = ""
        self.layers: dict[int, list[Layer]] = {n: [] for n in LINES}
        self.hourly: list[tuple[float, float, float]] = []   # (tph, cu_tph, usd_h) per hour
        self.next_hard: dict[int, Layer | None] = {n: None for n in LINES}
        self.arrived: set[str] = set()          # batches that once led the SAG feed: no longer "coming"

    def reset(self) -> None:
        self.__init__(self.prm, self.store)

    # ------------------------------------------------------------------ pile upkeep
    def _init_pile(self, n: int, batches: list[BatchView]) -> PileModel:
        prm = self.prm
        level = max(0.0, self.store.f(f"stockpile-{n}", "level_t", 0.0))
        pile = PileModel()
        c_target = prm["stock_column_frac"] * prm["stock_live_t"]
        in_stock = [b for b in batches if b.line == n and b.state == "IN_STOCK"]
        column_mass = min(level, c_target)
        known = sum(b.tonnes_left for b in in_stock)
        if in_stock and known > 0.0:
            # newest batches sit in the column, the oldest on the sides
            left = column_mass
            for b in reversed(in_stock):
                take = min(b.tonnes_left, left)
                if take > 0.0:
                    pile.add(b.name, take, b.est_axb, b.est_cu)
                    left -= take
                rest = b.tonnes_left - take
                if rest > 0.0:
                    pile.sides[b.name] = pile.sides.get(b.name, 0.0) + rest
                    pile.props[b.name] = (b.est_axb, b.est_cu)
            if left > 0.0:
                pile.add(REST, left, prm["ore_axb_base"], prm["flot_grade_ref_pct"])
        else:
            pile.add(REST, column_mass, prm["ore_axb_base"], prm["flot_grade_ref_pct"])
        side_rest = level - pile.total()
        if side_rest > 0.0:
            pile.sides[REST] = pile.sides.get(REST, 0.0) + side_rest
            pile.props[REST] = (prm["ore_axb_base"], prm["flot_grade_ref_pct"])
        return pile

    def _advance_pile(self, n: int, pile: PileModel, dt_min: float, batches: list[BatchView]) -> None:
        prm = self.prm
        st = self.store
        c_target = prm["stock_column_frac"] * prm["stock_live_t"]
        in_tph = max(0.0, st.f(f"stockpile-{n}", "in_tph", 0.0))
        out_tph = max(0.0, st.f(f"stockpile-{n}", "out_tph", 0.0))
        for b, share in self._arriving(n, batches):
            pile.add(b.name if b else REST, share * in_tph * dt_min / 60.0,
                     b.est_axb if b else prm["ore_axb_base"], b.est_cu if b else prm["flot_grade_ref_pct"])
        pile.draw(out_tph * dt_min / 60.0)
        pile.exchange(pile.column_mass() * dt_min / (prm["stock_exchange_tau_h"] * 60.0))
        pile.spill(c_target)
        level = st.f(f"stockpile-{n}", "level_t")
        if level != NO_VALUE:
            pile.scale_to(level)

    @staticmethod
    def _queue(n: int, batches: list[BatchView]) -> list[BatchView]:
        """Batches of line n still to arrive (BELT, DIG, PLANNED) in the order the pit sends them:
        the plan order of pit.plan_text (a scenario block is inserted, so its number says nothing),
        batches already on the way first, the number as the last key."""
        rank = {"BELT": 0, "DIG": 1, "PLANNED": 2}
        mine = [b for b in batches if b.line == n and b.state in rank]
        return sorted(mine, key=lambda b: (rank[b.state], b.plan_pos, b.number))

    def _arriving(self, n: int, batches: list[BatchView]) -> list[tuple[BatchView | None, float]]:
        """[(batch, share)] of the stockpile inflow now: the batch whose tail is on the road or belt
        (BELT), else the batches being dug (a hard block and its blend partner share it), else the
        newest batch in the pile, else base ore (None)."""
        q = self._queue(n, batches)
        belt = [b for b in q if b.state == "BELT"]
        if belt:
            return [(belt[0], 1.0)]
        dig = [b for b in q if b.state == "DIG"]
        if dig:
            return [(b, 1.0 / len(dig)) for b in dig]
        arrived = [b for b in batches if b.line == n and b.state == "IN_STOCK"]
        return [(arrived[-1], 1.0)] if arrived else [(None, 1.0)]

    # ------------------------------------------------------------------ forecast
    def _schedule(self, n: int, t: float, batches: list[BatchView]) -> list[tuple[float, float, BatchView, float]]:
        """[(start, end, batch, tonnes)] arrival at the stockpile of line n, model min, t still to come.

        BELT: the tail of a dug batch, at most what the road and belt hold (rate x lag), arrives
        within the lag. DIG: pit_t (published by the simulator) is still to dig at the rate, plus
        what is on the way; the window ends a lag after the last dug tonne. PLANNED: queued after
        the batches ahead in the plan order (not by batch number). Without pit_t the whole block is
        assumed, which would push the window later at every tact.
        """
        prm = self.prm
        st = self.store
        rate = st.f(f"stockpile-{n}", "in_tph", 0.0)
        if rate <= 0.0:
            rate = prm["exc_dig_tph"]
        lag = prm["pit_haul_min"] + prm["conv_travel_min"]
        on_way = rate * lag / 60.0
        out = []
        t_free = t                       # when the excavator of this line is free for the next planned batch
        for b in self._queue(n, batches):
            size = b.tonnes if b.tonnes > 0.0 else prm["pit_block_t"]
            if b.state == "BELT":
                tonnes = min(on_way, b.tonnes_left if b.tonnes_left > 0.0 else on_way)
                out.append((t, t + lag, b, tonnes))
            elif b.state == "DIG":
                in_pit = b.pit_t if b.pit_t != NO_VALUE else size
                dig_min = in_pit / rate * 60.0
                tonnes = in_pit + min(on_way, max(0.0, size - in_pit))
                out.append((t, t + lag + dig_min, b, tonnes))
                t_free = max(t_free, t + dig_min)
            else:
                dig_min = size / rate * 60.0
                out.append((t_free + lag, t_free + lag + dig_min, b, size))
                t_free += dig_min
        return out

    def _forecast_line(self, n: int, t: float, batches: list[BatchView]) -> tuple[list, dict]:
        """Forward run of one line; returns ([(tph, cu_tph)] per step, {batch: [(t, share)]})."""
        prm = self.prm
        st = self.store
        pile = self.piles[n].copy()
        c_target = prm["stock_column_frac"] * prm["stock_live_t"]
        horizon = prm["ore_horizon_h"] * 60.0
        sched = self._schedule(n, t, batches)
        for _, _, b, _ in sched:
            pile.props[b.name] = (b.est_axb, b.est_cu)
        in_rate = max(0.0, st.f(f"stockpile-{n}", "in_tph", 0.0))
        p_lim = st.f(f"sag-{n}", "power_limit_kw")
        p_sp = prm["sag_power_sp_mw"] * 1000.0
        if p_lim > 0.0:
            p_sp = min(p_sp, p_lim)
        running = st.s(f"sag-{n}", "state") not in ("STOP", "RELINE")
        peb_on = st.s(f"pebble-{n}", "state") != "STOP"
        peb_limit = st.f(f"pebble-{n}", "limit_tph")
        level = pile.total()
        series: list[tuple[float, float]] = []
        shares: dict[str, list[tuple[float, float]]] = {}
        r_base = prm["flot_rec_ref_pct"]
        tt = t
        while tt < t + horizon - 1e-9:
            # inflow: scheduled batches covering this step, else base ore at the mining rate
            inflow = 0.0
            for s0, s1, b, tonnes_all in sched:
                ov = max(0.0, min(s1, tt + STEP_MIN) - max(s0, tt))
                if ov > 0.0:
                    tonnes = tonnes_all * ov / max(1e-9, s1 - s0)
                    pile.add(b.name, tonnes, b.est_axb, b.est_cu)
                    inflow += tonnes
            if inflow <= 0.0 and in_rate > 0.0 and not any(s0 <= tt + STEP_MIN and s1 > tt for s0, s1, _, _ in sched):
                base = in_rate * STEP_MIN / 60.0
                if not any(s0 > tt for s0, _, _, _ in sched):
                    pile.add(REST, base, prm["ore_axb_base"], prm["flot_grade_ref_pct"])
            mixes, cu = pile.mix(prm)
            cap = ex.sag_mix_capacity_tph(p_sp, mixes, prm, peb_on, peb_limit if peb_limit > 0.0 else None) \
                if running else 0.0
            avail = pile.total() * 60.0 / STEP_MIN
            q = min(cap, avail)
            pile.draw(q * STEP_MIN / 60.0)
            pile.exchange(pile.column_mass() * STEP_MIN / (prm["stock_exchange_tau_h"] * 60.0))
            pile.spill(c_target)
            series.append((q, ex.cu_tph(q, cu, r_base)))
            for k, s in pile.shares().items():
                shares.setdefault(k, []).append((tt + STEP_MIN, s))
            tt += STEP_MIN
        del level
        return series, shares

    def _window(self, pts: list[tuple[float, float]]) -> tuple[float, float, float]:
        """(early, expected, late) model min from a share series; NO_VALUE when never above the early share."""
        prm = self.prm
        lo, hi = prm["ore_early_share"], prm["ore_expected_share"]
        early = expected = late = NO_VALUE
        peak_t, peak_s = NO_VALUE, 0.0
        for tt, s in pts:
            if early == NO_VALUE and s >= lo:
                early = tt
            if early != NO_VALUE and expected == NO_VALUE and s >= hi:
                expected = tt
            if s > peak_s:
                peak_s, peak_t = s, tt
        if early == NO_VALUE:
            return early, expected, late
        if expected == NO_VALUE:
            expected = peak_t
        for tt, s in pts:
            if tt > expected and s < lo:
                late = tt
                break
        if late == NO_VALUE:
            late = pts[-1][0] if pts else expected
        return early, expected, late

    # ------------------------------------------------------------------ hindsight
    def _check(self, t: float) -> None:
        prm = self.prm
        st = self.store
        for n in LINES:
            pend = sorted((f for f in self.forecasts.values() if f.line == n and not f.done),
                          key=lambda f: f.expected)
            axb_med = st.median(f"sag-{n}", "axb_soft", t, prm["ore_soft_median_min"])
            running = st.s(f"sag-{n}", "state") == "RUN"
            for f in pend:
                thr = 0.5 * (prm["ore_axb_base"] + f.axb)
                arrived = axb_med != NO_VALUE and axb_med < thr and running
                if arrived and not self.hard_now[n]:
                    self.hard_now[n] = True
                    f.done = True
                    f.t_arrived = t
                    f.hit = f.early <= t <= f.late
                    f.text = self._check_text(f, t)
                    self.hits += int(f.hit)
                    self.misses += int(not f.hit)
                    self.last_check = f.text
                    break
                if t > f.late + prm["ore_check_miss_h"] * 60.0:
                    f.done = True
                    f.hit = False
                    f.tph_done = True
                    f.text = (f"Прогноз от {hhmm_day(f.made_at, f.made_at)}: твёрдая ({batch_ru('', f.batch)}) в "
                              f"{hhmm_day(f.early, f.made_at)}–{hhmm_day(f.expected, f.made_at)}. Факт: к "
                              f"{hhmm_day(t, f.made_at)} мягкий датчик A×b твёрдой руды не увидел — мимо {EST}")
                    self.misses += 1
                    self.last_check = f.text
            # t/h of an arrived hard batch: the lowest 1 h mean feed while it leads the feed, compared
            # with the forecast t/h (also the lowest hour of its window), until the window ends
            for f in self.forecasts.values():
                if f.line != n or f.t_arrived == NO_VALUE or f.tph_done:
                    continue
                q1 = st.mean(f"sag-{n}", "feed_tph", t, 60.0)
                if q1 != NO_VALUE and q1 > 0.0 and running:
                    f.tph_min = q1 if f.tph_min == NO_VALUE else min(f.tph_min, q1)
                if t >= max(f.late, f.t_arrived + 60.0) or not self.hard_now[n]:
                    f.tph_done = True
                f.text = self._check_text(f, t)
                self.last_check = f.text
            if axb_med != NO_VALUE and axb_med >= 0.5 * (prm["ore_axb_base"] + prm["ore_axb_hard"]) + 1.0:
                self.hard_now[n] = False

    @staticmethod
    def _check_text(f: Forecast, t: float) -> str:
        """Hindsight line: window vs arrival, then forecast t/h vs the lowest measured hour."""
        day0 = f.made_at
        text = (f"Прогноз от {hhmm_day(f.made_at, day0)}: твёрдая ({batch_ru('', f.batch)}) в "
                f"{hhmm_day(f.early, day0)}–{hhmm_day(f.expected, day0)} (не позже {hhmm_day(f.late, day0)}). "
                f"Факт: пришла в {hhmm_day(f.t_arrived, day0)}" + (" — сбылось" if f.hit else " — мимо окна"))
        if f.tph_fc > 0.0 and f.tph_min != NO_VALUE:
            err = (f.tph_min - f.tph_fc) / f.tph_fc * 100.0
            text += (f"; т/ч: прогноз {num(f.tph_fc, 0)}, факт — минимум часа {num(f.tph_min, 0)}"
                     + (f" (ошибка {signed(err, 1)} %)" if f.tph_done else f" к {hhmm_day(t, day0)}, ещё идёт"))
        return text + f" {EST}"

    def restore(self, rows: list[dict]) -> int:
        """Recover earlier forecasts of hard batches from mod-ore history rows (layers_l* strings)."""
        n_new = 0
        for r in sorted(rows, key=lambda x: as_float(x.get("value_sim_time_properties_value"))):
            made = as_float(r.get("value_sim_time_properties_value"))
            for n in LINES:
                raw = r.get(f"value_layers_l{n}_properties_value")
                if not isinstance(raw, str) or not raw.startswith("["):
                    continue
                try:
                    layers = json.loads(raw)
                except ValueError:
                    continue
                for L in layers:
                    if not isinstance(L, dict) or L.get("cls") != "Т" or L.get("batch") in self.forecasts:
                        continue
                    if as_float(L.get("exp")) == NO_VALUE or as_float(L.get("early")) == NO_VALUE:
                        continue
                    self.forecasts[L["batch"]] = Forecast(
                        L["batch"], n, made, float(L["early"]), float(L["exp"]), float(L.get("late", L["exp"])),
                        as_float(L.get("tph_at"), 0.0), as_float(L.get("axb"), self.prm["ore_axb_hard"]))
                    n_new += 1
        return n_new

    # ------------------------------------------------------------------ tact
    def compute(self, t: float) -> dict:
        prm = self.prm
        st = self.store
        batches = all_batches(st, prm)
        if not self.piles:
            for n in LINES:
                self.piles[n] = self._init_pile(n, batches)
        elif self.last_t != NO_VALUE and t > self.last_t:
            for n in LINES:
                self._advance_pile(n, self.piles[n], t - self.last_t, batches)
        self.last_t = t

        hourly_sum = [[0.0, 0.0, 0] for _ in range(int(prm["ore_horizon_h"]))]
        feats: dict = {}
        texts = []
        for n in LINES:
            series, shares = self._forecast_line(n, t, batches)
            for i, (q, cu) in enumerate(series):
                h = int(i * STEP_MIN // 60)
                if h < len(hourly_sum):
                    hourly_sum[h][0] += q
                    hourly_sum[h][1] += cu
                    hourly_sum[h][2] += 1 if n == LINES[0] else 0     # steps per hour, lines are summed
            now_shares = self.piles[n].shares()
            layers: list[Layer] = []
            by_name = {b.name: b for b in batches if b.line == n}
            keys = [k for k in dict.fromkeys(list(self.piles[n].column) + list(self.piles[n].sides) + list(shares))
                    if k != REST]
            for k in keys:
                b = by_name.get(k)
                axb, cu = self.piles[n].props.get(k, (b.est_axb if b else prm["ore_axb_base"],
                                                      b.est_cu if b else prm["flot_grade_ref_pct"]))
                tonnes = self.piles[n].column.get(k, 0.0) + self.piles[n].sides.get(k, 0.0)
                if b is None and tonnes <= 0.0:
                    continue
                L = Layer(k, b.block if b else "", n, axb, cu, ex.ore_class(axb, prm), tonnes,
                          b.state if b else "DONE", share_now=now_shares.get(k, 0.0))
                pts = shares.get(k, [])
                if now_shares.get(k, 0.0) >= prm["ore_expected_share"]:
                    L.early = L.expected = t
                    L.late = self._window(pts)[2] if pts else t
                elif pts:
                    L.early, L.expected, L.late = self._window(pts)
                if L.expected != NO_VALUE:
                    # t/h while the batch dominates the feed: the lowest hour between expected and late
                    i0 = max(0, int((L.expected - t) // STEP_MIN))
                    i1 = min(len(series) - 1, int(((L.late if L.late != NO_VALUE else L.expected) - t) // STEP_MIN))
                    if i0 < len(series):
                        L.tph_at = min(series[i][0] for i in range(i0, max(i0, i1) + 1))
                layers.append(L)
            layers.sort(key=lambda L: (L.expected if L.expected != NO_VALUE else 1e9, L.batch))
            self.layers[n] = layers
            for L in layers:
                if L.share_now >= prm["ore_expected_share"]:
                    self.arrived.add(L.batch)
            for f in self.forecasts.values():
                if f.done and f.t_arrived != NO_VALUE:
                    self.arrived.add(f.batch)
            hard = [L for L in layers if L.cls == "Т" and L.expected != NO_VALUE and L.expected > t
                    and L.share_now < prm["ore_expected_share"] and L.batch not in self.arrived]
            nh = hard[0] if hard else None
            self.next_hard[n] = nh
            if nh is not None:
                feats[f"next_hard_eta_early_h_l{n}"] = max(0.0, (nh.early - t) / 60.0)
                feats[f"next_hard_eta_h_l{n}"] = max(0.0, (nh.expected - t) / 60.0)
                if nh.batch not in self.forecasts:
                    self.forecasts[nh.batch] = Forecast(nh.batch, n, t, nh.early, nh.expected, nh.late,
                                                        nh.tph_at if nh.tph_at != NO_VALUE else 0.0, nh.axb)
                q_now = st.f(f"sag-{n}", "feed_tph")
                texts.append(f"линия {n}: твёрдая руда {batch_ru(nh.block, nh.batch)} (A×b {num(nh.axb, 0)}, «Т») "
                             f"раньше — через {dur((nh.early - t) / 60.0)} ({hhmm_day(nh.early, t)}), ожидаемо — "
                             f"{dur((nh.expected - t) / 60.0)} ({hhmm_day(nh.expected, t)}): "
                             f"{num(q_now, 0) if q_now != NO_VALUE else '—'} → ≈ "
                             f"{num(nh.tph_at, 0) if nh.tph_at != NO_VALUE else '—'} т/ч")
            else:
                feats[f"next_hard_eta_early_h_l{n}"] = NO_VALUE
                feats[f"next_hard_eta_h_l{n}"] = NO_VALUE
                texts.append(f"линия {n}: твёрдой руды в плане на 12 ч нет")
            feats[f"layers_l{n}"] = json.dumps([{
                "batch": L.batch, "block": L.block, "cls": L.cls, "axb": round(L.axb, 1), "cu": round(L.cu, 3),
                "t": round(L.tonnes), "state": L.state, "in_sag": round(L.share_now, 3),
                "early": L.early, "exp": L.expected, "late": L.late,
                "window": (f"{hhmm_day(L.early, t)}–{hhmm_day(L.expected, t)}" if L.early != NO_VALUE else ""),
                "tph_at": L.tph_at} for L in layers], ensure_ascii=False, separators=(",", ":"))
        hard_axb = [self.next_hard[n].axb for n in LINES if self.next_hard[n] is not None]
        feats["next_hard_axb"] = min(hard_axb) if hard_axb else NO_VALUE
        self.hourly = []
        for h, (q, cu, k) in enumerate(hourly_sum, start=1):
            tph = q / k if k else NO_VALUE
            cut = cu / k if k else NO_VALUE
            feats[f"fc_tph_h{h}"] = tph
            self.hourly.append((tph, cut, ex.usd_h(cut, prm) if cut != NO_VALUE else NO_VALUE))
        valid_h = [(h, x[0]) for h, x in enumerate(self.hourly, start=1) if x[0] != NO_VALUE]
        if valid_h:
            lo_h, lo_v = min(valid_h, key=lambda x: x[1])
            head = (f"Прогноз на 12 ч {EST}: {num(valid_h[0][1], 0)} т/ч в первый час, минимум {num(lo_v, 0)} т/ч "
                    f"в {hhmm_day(t + lo_h * 60.0, t)}; Cu {num(self.hourly[0][1], 1)} т/ч")
        else:
            head = f"Прогноз на 12 ч {EST}: нет данных"
        feats["fc_text"] = head + "; " + "; ".join(texts)

        self._check(t)
        n_checks = self.hits + self.misses
        feats["hit_rate"] = 100.0 * self.hits / n_checks if n_checks else NO_VALUE
        feats["check_text"] = ((self.last_check + " · ") if self.last_check else "") + \
            (f"сбылось {self.hits} из {n_checks}" if n_checks else "проверок ещё не было: твёрдая партия до SAG не дошла")
        feats["processed_sim_time"] = t
        feats["resend"] = NO_VALUE
        self.processed = t
        return feats
