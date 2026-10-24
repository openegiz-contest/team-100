"""akt-losses: where copper is lost. Expectation vs measurement per node, CUSUM detector.

Design file 17, section 5 "where copper is lost"; file 19, section 3 B.

Every 5 model minutes, per line: the SAG node (t/h below what the drawn
power allows for the estimated ore), the grind node (P80 above the Bond
expectation) and the flotation node (recovery below the expectation at the
measured feed grade, P80 and the dose the flowmeter shows). The expectation
is this module's own model on block-model estimates and measurements, so
it carries their errors: sigma adds the block error and the analyser noise
in quadrature. The detector is a one-sided CUSUM on z = gap / sigma with a
fast threshold; below 2 sigma the node is "inside noise", above it without
an alarm "unsure".

The module may miss a cause, raise a false alarm or name the wrong role;
the calibration job runs the same code on random shifts and prints the
detection share, false alarms and the cause -> node matrix.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from . import expect as ex
from .batches import all_batches, ore_in_sag
from .cusum import STATUS_RU, OneSidedCusum, status_of, z_score
from .params import Prm
from .store import NO_VALUE, Store
from .text import ANALOG, ASSUME, EST, LIT, batch_ru, cu_tph, num, usd_h

log = logging.getLogger("losses")

LINES = (1, 2)
BALANCE_SPAN_MIN = 90.0    # balances need counters this far apart: the weigher noise of the totalizers
                           # (class 1, each step) is about 0.15 % over 90 min, so the 0.5 % limit holds
MIN_LOSS_CU_TPH = 0.005    # below this an alarm shows as 0,00 t Cu/h: not named as the main loss
NODES = tuple(f"{kind}-{n}" for n in LINES for kind in ("sag", "cyclones", "flot"))
READS = ("site", "line-1", "line-2", "sag-1", "sag-2", "pebble-1", "pebble-2",
         "ball-1a", "ball-1b", "ball-2a", "ball-2b", "cyclones-1", "cyclones-2", "flot-1", "flot-2",
         "rougher-1", "rougher-2", "cleaner-1", "cleaner-2", "stockpile-1", "stockpile-2",
         "thick-1", "thick-2", "filter-1", "filter-2", "conc-stock", "water", "power",
         "crusher-1", "crusher-2", "conveyor-1", "conveyor-2")
READS_TYPES = ("batch",)
# Fields backfilled from InfluxDB after a start (Telegraf names).
BACKFILL_FIELDS = ("feed_tph", "power_kw", "p80_um", "feed_cu", "tail_cu", "conc_cu", "dose_meas_gt", "dose_sp_gt",
                   "state", "pond_m3", "inventory_t", "level_t", "feed_t_total", "underflow_t_total",
                   "intake_m3_total", "loss_m3_total", "tank_t", "tank_in_t_total", "dose_t_total")
KG_PER_T = 1000.0          # unit conversion
G_PER_T = 1e6              # unit conversion: t of reagent per t of ore -> g/t


@dataclass
class NodeResult:
    node: str
    status: str = "no_data"       # loss | unsure | noise | idle | feed | no_data
    z: float = 0.0
    gap_cu_tph: float = 0.0       # positive = loss
    sigma_cu_tph: float = 0.0
    gap_usd_h: float = 0.0
    roles: str = ""               # Russian role names, "; " separated
    role_keys: tuple = ()
    cause: str = ""               # Russian explanation
    detected_at: float = NO_VALUE  # model min when the alarm fired
    detail: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        if self.status in ("loss", "unsure", "noise"):
            return (f"{cu_tph(-self.gap_cu_tph)} ± {num(self.sigma_cu_tph, 2)} · {usd_h(-self.gap_usd_h)} {EST} · "
                    f"{STATUS_RU[self.status]} (z = {num(self.z, 1)}); {self.cause}")
        return STATUS_RU.get(self.status, self.status)


class LossesModule:
    name = "losses"
    thing = "mod-losses"

    def __init__(self, prm: Prm, store: Store, roles: dict[str, str] | None = None):
        self.prm = prm
        self.store = store
        self.roles = roles or {}
        self.tact = prm["tact_losses_min"]
        self.processed = NO_VALUE
        self.results: dict[str, NodeResult] = {}
        self.balances: dict = {}
        self.cusum = {n: OneSidedCusum(prm["cusum_k"], prm["cusum_h"], prm["cusum_fast_z"]) for n in NODES}
        self.detected_at = {n: NO_VALUE for n in NODES}
        self.last_an = {n: None for n in LINES}      # last analyser triple used per line
        self.suspect: dict[str, str] = {}            # instruments whose reading is doubted (thing -> reason)
        self.reagent: dict[int, dict] = {}           # line -> collector tank balance (silent overdose)

    def reset(self) -> None:
        self.suspect = {}
        self.reagent = {}
        self.processed = NO_VALUE
        self.results.clear()
        self.balances.clear()
        for c in self.cusum.values():
            c.reset()
        self.detected_at = {n: NO_VALUE for n in NODES}
        self.last_an = {n: None for n in LINES}

    def role(self, key: str) -> str:
        return self.roles.get(key, key)

    # ------------------------------------------------------------------ inputs
    def _mean(self, name: str, feature: str, t: float, span: float | None = None) -> float:
        return self.store.mean(name, feature, t, self.prm["window_min"] if span is None else span)

    def _detect(self, node: str, z: float, t: float) -> str:
        c = self.cusum[node]
        was = c.alarm
        alarm = c.update(z)
        if alarm and not was:
            self.detected_at[node] = t
        if not alarm:
            self.detected_at[node] = NO_VALUE
        return status_of(z, alarm, self.prm["unsure_z"])

    # ------------------------------------------------------------------ nodes
    def eval_sag(self, t: float, n: int, est_axb: float, feed_cu: float, r_exp: float) -> NodeResult:
        prm = self.prm
        node = f"sag-{n}"
        # kWh/t above the ore: the metallurgist checks load, feed size and liner first (priority.WHO["loss_sag"])
        res = NodeResult(node, role_keys=("shift_metallurgist", "plant_mech"))
        res.roles = "; ".join(self.role(k) for k in res.role_keys)
        st = self.store
        sag = st.get(node)
        if sag is None:
            return res
        state = sag.s("state")
        q = self._mean(node, "feed_tph", t)
        p = self._mean(node, "power_kw", t)
        peb_on = st.s(f"pebble-{n}", "state") != "STOP"
        peb_limit = st.f(f"pebble-{n}", "limit_tph")
        if state in ("STOP", "RELINE") or q == NO_VALUE or p == NO_VALUE or q <= 0.0 or p <= 0.0:
            res.status = "idle"
            res.cause = "мельница стоит" if state in ("STOP", "RELINE") else "нет измерений"
            self.cusum[node].reset()
            return res
        stock_state = st.s(f"stockpile-{n}", "state")
        q_exp = ex.sag_capacity_tph(p, est_axb, prm, peb_on, peb_limit if peb_limit > 0.0 else None)
        if state == "STARVED" or (stock_state in ("EMPTY", "LOW") and q < 0.9 * q_exp):
            res.status = "feed"
            res.cause = "питания со склада не хватает: потеря выше по цепочке, не в мельнице"
            self.cusum[node].reset()
            return res
        sig_rel = math.sqrt((prm["sag_morrell_b"] * prm["blk_err_axb_sigma"]) ** 2
                            + prm["sens_weigher_sigma"] ** 2 + prm["sens_power_sigma"] ** 2)
        gap_q = q_exp - q
        z = z_score(gap_q, sig_rel * q_exp)
        res.z = z
        res.gap_cu_tph = ex.cu_tph(gap_q, feed_cu, r_exp) if gap_q > 0.0 else -ex.cu_tph(-gap_q, feed_cu, r_exp)
        res.sigma_cu_tph = ex.cu_tph(sig_rel * q_exp, feed_cu, r_exp)
        res.gap_usd_h = ex.usd_h(res.gap_cu_tph, prm)
        res.status = self._detect(node, z, t)
        res.detected_at = self.detected_at[node]
        e_meas = p / q
        e_exp = ex.sag_energy_kwh_t(est_axb, prm, peb_on)
        excess = e_meas / e_exp - 1.0 if e_exp > 0.0 else 0.0
        # energy spent above what the ore needs, at the grid (shaft / motor efficiency), USD/h
        energy_usd_h = max(0.0, e_meas - e_exp) * q / 1000.0 / prm["motor_eff"] * prm["power_usd_mwh"]
        # copper is lost only when the SAG is the bottleneck (it draws its setpoint): then more kWh/t means
        # fewer t/h; below it the line is held elsewhere and the overspend is energy only
        limited = p >= prm["sag_limited_frac"] * prm["sag_power_sp_mw"] * 1000.0
        res.cause = (f"тихий перерасход энергии: E {num(e_meas, 2)} против {num(e_exp, 2)} кВт·ч/т по Морреллу на "
                     f"A×b партии {num(est_axb, 0)} ({'+' if excess >= 0 else '−'}{num(abs(100 * excess), 1)} %), "
                     f"лишняя энергия ≈ {usd_h(energy_usd_h)} {EST}; "
                     + (f"мельница на пределе мощности {num(p / 1000.0, 1)} МВт: ожидалось {num(q_exp, 0)} т/ч, "
                        f"измерено {num(q, 0)} — медь теряется" if limited else
                        f"мельница не на пределе мощности ({num(p / 1000.0, 1)} МВт): т/ч держит другое, "
                        f"медь не теряется, только энергия")
                     + f"; причина: перегруз загрузки, крупное питание, износ футеровки или руда твёрже оценки "
                       f"(по P и Q неразличимы; ошибка модели ±{num(100 * prm['model_err_sag'], 0)} % в z не учтена); "
                       f"для масштаба: на Sossego (Vale) автоматическое управление сняло "
                       f"{num(prm['sag_energy_lit_pct'], 2)} % удельного расхода {LIT}")
        if not peb_on:
            res.cause += "; дробление гали стоит (E +6…10 %)"
        res.detail = {"q": q, "q_exp": q_exp, "p_kw": p, "e_meas": e_meas, "e_exp": e_exp, "est_axb": est_axb,
                      "excess": excess, "energy_usd_h": energy_usd_h, "limited": limited}
        return res

    def eval_cyclones(self, t: float, n: int, est_axb: float, feed_cu: float, r_exp: float) -> NodeResult:
        prm = self.prm
        node = f"cyclones-{n}"
        # clogged cyclone: the mill mechanics clear it; a grind regime: the metallurgist (priority.WHO)
        res = NodeResult(node, role_keys=("plant_mech", "shift_metallurgist"))
        res.roles = "; ".join(self.role(k) for k in res.role_keys)
        st = self.store
        q = self._mean(f"sag-{n}", "feed_tph", t)
        p80 = self._mean(node, "p80_um", t)
        balls = [f"ball-{n}a", f"ball-{n}b"]
        kw = 0.0
        for b in balls:
            if st.s(b, "state") == "RUN":
                v = self._mean(b, "power_kw", t)
                kw += v if v != NO_VALUE else 0.0
        if q == NO_VALUE or q <= 0.0 or kw <= 0.0 or p80 == NO_VALUE:
            res.status = "idle" if (q != NO_VALUE and q <= 0.0) or kw <= 0.0 else "no_data"
            res.cause = "линия стоит" if res.status == "idle" else "нет измерений P80"
            self.cusum[node].reset()
            return res
        bwi = ex.bwi_from_axb(est_axb, prm)
        p80_exp = ex.bond_p80_um(q, kw, bwi, prm)
        sig = ex.p80_sigma_um(q, kw, bwi, prm)
        d = p80 - p80_exp
        z = z_score(d, sig)
        slope = prm["flot_p80_pp_10um"] / 10.0
        ref = prm["p80_ref_um"]
        d_r = slope * (max(0.0, p80 - ref) - max(0.0, p80_exp - ref))     # pp of recovery lost
        res.z = z
        res.gap_cu_tph = q * feed_cu * d_r / 1e4
        res.sigma_cu_tph = q * feed_cu * slope * sig / 1e4
        res.gap_usd_h = ex.usd_h(res.gap_cu_tph, prm)
        res.status = self._detect(node, z, t)
        res.detected_at = self.detected_at[node]
        n_run = sum(1 for b in balls if st.s(b, "state") == "RUN")
        res.cause = (f"P80 {num(p80, 0)} мкм против ожидаемых {num(p80_exp, 0)} ± {num(sig, 0)} "
                     f"(Бонд: {n_run} шаровых, {num(kw / 1000.0, 1)} МВт, BWi {num(bwi, 1)} по A×b {num(est_axb, 0)}): "
                     f"засор циклона или режим помола")
        res.detail = {"p80": p80, "p80_exp": p80_exp, "sigma_um": sig, "ball_kw": kw, "bwi": bwi}
        return res

    def eval_flot(self, t: float, n: int, est_ascu: float, batch: str) -> tuple[NodeResult, float, float]:
        """Flotation node; also returns (feed grade used, expected recovery) for the other nodes."""
        prm = self.prm
        node = f"flot-{n}"
        res = NodeResult(node)
        st = self.store
        fl = st.get(node)
        f = st.f(node, "feed_cu")
        tl = st.f(node, "tail_cu")
        c = st.f(node, "conc_cu")
        q = self._mean(f"sag-{n}", "feed_tph", t)
        p80 = self._mean(f"cyclones-{n}", "p80_um", t)
        sp = st.f(f"rougher-{n}", "dose_sp_gt")
        dm = self._mean(f"rougher-{n}", "dose_meas_gt", t)
        dose_ratio = dm / sp if sp > 0.0 and dm != NO_VALUE and dm >= 0.0 else 1.0
        g_default = prm["flot_grade_ref_pct"]
        r_default = prm["flot_rec_ref_pct"]
        if fl is None or fl.s("state") == "STOP" or q == NO_VALUE or q <= 0.0:
            res.status = "idle"
            res.cause = "флотация стоит"
            res.roles = self.role("shift_metallurgist")
            self.cusum[node].reset()
            return res, g_default, r_default
        r_meas, _ = ex.two_product(f, tl, c)
        if r_meas == NO_VALUE:
            res.status = "no_data"
            res.cause = "нет показаний анализатора"
            res.roles = self.role("shift_metallurgist")
            return res, g_default, r_default
        r_exp = ex.total_recovery_pct(q, f, est_ascu, p80, dose_ratio, prm)
        gap = r_exp - r_meas
        sig = math.sqrt(ex.recovery_sigma_pp(f, tl, c, prm) ** 2 + ex.ascu_sigma_pp(prm) ** 2)
        z = z_score(gap, sig)
        triple = (f, tl, c)
        new_reading = (self.last_an[n] != triple)
        if new_reading:
            self.last_an[n] = triple
            status = self._detect(node, z, t)
        else:
            status = status_of(z, self.cusum[node].alarm, prm["unsure_z"])
        res.z = z
        res.status = status
        res.gap_cu_tph = q * f * gap / 1e4
        res.sigma_cu_tph = q * f * sig / 1e4
        res.gap_usd_h = ex.usd_h(res.gap_cu_tph, prm)
        res.detected_at = self.detected_at[node]
        oxide = est_ascu > prm["flot_ascu_ref_pct"] + 1.0
        if oxide:
            res.role_keys = ("shift_geologist", "shift_metallurgist")       # ore changed: the metallurgist changes the regime (T5)
            # the batch by its Russian name ("партия 13"), not the thing id; the value against the mean
            where = f" ({batch_ru('', batch)})" if batch else ""
            why = (f"окисленная руда{where}: ASCu по блочной модели {num(est_ascu, 1)} % при среднем "
                   f"{num(prm['flot_ascu_ref_pct'], 1)} %")
        else:
            res.role_keys = ("kip", "shift_metallurgist")       # the flowmeter first (crew-kip, priority.WHO)
            why = ("дозировка собирателя (расходомер) или реагентный режим; проверить также pH-метр: ручная проба против "
                   "онлайн-показания")
        res.roles = "; ".join(self.role(k) for k in res.role_keys)
        above = tl != NO_VALUE and tl > prm["acs_tail_sp_pct"]
        res.cause = (f"извлечение {num(r_meas, 1)} % против ожидаемых {num(r_exp, 1)} ± {num(sig, 1)} "
                     f"(питание {num(f, 3)} % Cu, хвосты {num(tl, 3)} %, P80 {num(p80, 0) if p80 != NO_VALUE else '—'} мкм, "
                     f"дозировка по расходомеру {num(100 * dose_ratio, 0)} % уставки): {why}"
                     + ("; уставка АСУ по хвостам пересечена" if above else "; уставка АСУ не пересечена"))
        res.detail = {"r_meas": r_meas, "r_exp": r_exp, "sigma_pp": sig, "feed_cu": f, "tail_cu": tl,
                      "conc_cu": c, "q": q, "p80": p80, "dose_ratio": dose_ratio, "est_ascu": est_ascu,
                      "new_reading": new_reading}
        return res, f, r_exp

    # ------------------------------------------------------------------ reagents
    def eval_reagent(self, t: float, n: int) -> dict:
        """Collector tank balance of line n over the balance window: what left the day tank (load cells,
        deliveries booked) against the flowmeter totalizer. An overdose the meter does not show costs money
        and gives no recovery (above the setpoint the recovery does not grow)."""
        prm = self.prm
        out = {"status": "no_data", "excess": NO_VALUE, "usd_h": 0.0, "tank_kg_h": NO_VALUE, "meter_kg_h": NO_VALUE,
               "z": 0.0}
        e = self._ends(f"rougher-{n}", ("tank_t", "tank_in_t_total", "dose_t_total"), t)
        if e is None:
            return out
        span_h = e[0] / 60.0
        d = e[1]
        meter = d["dose_t_total"]
        used = d["tank_in_t_total"] - d["tank_t"]
        if meter <= 0.0 or span_h <= 0.0:
            out["status"] = "idle"
            return out
        sigma = prm["tank_sigma_t"] * 2 ** 0.5
        extra = used - meter
        out.update(excess=extra / meter, z=extra / sigma if sigma > 0 else 0.0,
                   tank_kg_h=used * KG_PER_T / span_h, meter_kg_h=meter * KG_PER_T / span_h,
                   usd_h=max(0.0, extra) * KG_PER_T / span_h * prm["reagent_usd_kg"])
        loss = out["excess"] >= prm["reagent_min_frac"] and out["z"] >= prm["reagent_min_z"]
        out["status"] = "loss" if loss else "noise"
        if not loss:
            out["usd_h"] = 0.0
        sp = self.store.f(f"rougher-{n}", "dose_sp_gt")
        q = self._mean(f"sag-{n}", "feed_tph", t)
        out["true_gt"] = (used * G_PER_T / span_h / q) if q != NO_VALUE and q > 0.0 else NO_VALUE
        out["sp_gt"] = sp
        out["text"] = (f"реагенты линии {n}: из бака ушло {num(out['tank_kg_h'], 0)} кг/ч, расходомер показал "
                       f"{num(out['meter_kg_h'], 0)} кг/ч ({'+' if extra >= 0 else '−'}{num(abs(100 * out['excess']), 0)} %)"
                       + (f"; передозировка собирателя ≈ {num(out['true_gt'], 0)} г/т при уставке {num(sp, 0)} г/т — "
                          f"извлечение от неё не растёт, лишний реагент ≈ {usd_h(out['usd_h'])} {EST} (цена "
                          f"{num(prm['reagent_usd_kg'], 1)} $/кг {ASSUME}); ориентир: на Sungun фабрика давала "
                          f"{num(prm['reagent_ref_gt'], 0)} г/т собирателей против "
                          f"{num(prm['reagent_ref_lab_gt'], 0)} г/т лабораторного оптимума {ANALOG}"
                          if loss else "; в пределах точности весов бака"))
        return out

    # ------------------------------------------------------------------ balances
    def _ends(self, name: str, features: tuple[str, ...], t: float) -> tuple[float, dict] | None:
        """(span in min, {feature: last - first}) between the first and the last point of the balance
        window where all features were published together; None below BALANCE_SPAN_MIN.
        Counters (*_total) are totalizers: every step's weighed rate x dt, so the difference of two
        readings is the exact amount between them however sparse the points are (rate samples 1-20
        min apart missed ramps by 1-20 %). A counter that went down (a restart) cuts the window."""
        cols = [dict(self.store.window(name, f, t, self.prm["balance_window_min"])) for f in features]
        ts = sorted(set(cols[0]).intersection(*cols[1:]))
        if not ts:
            return None
        k = len(ts) - 1
        while k > 0 and all(c[ts[k - 1]] <= c[ts[k]] + 1e-9
                            for f, c in zip(features, cols) if f.endswith("_total")):
            k -= 1
        t0, t1 = ts[k], ts[-1]
        if t1 - t0 < BALANCE_SPAN_MIN - 1e-9:
            return None
        return t1 - t0, {f: c[t1] - c[t0] for f, c in zip(features, cols)}

    def eval_balances(self, t: float) -> dict:
        st = self.store
        prm = self.prm
        out: dict = {"cu_residual_pct": NO_VALUE, "water_residual_pct": NO_VALUE, "conc_residual_pct": NO_VALUE,
                     "power_headroom_mw": NO_VALUE, "power_parts_text": "", "water_leak_m3h": NO_VALUE,
                     "water_leak_usd_h": NO_VALUE}
        # copper: feed = concentrate + tails, at the newest point both things were published for
        # (sag-N and flot-N reach Ditto in separate messages; the weigher noise of two different
        # points alone gave 1-2 %)
        cu_in = cu_out = 0.0
        ok = False
        for n in LINES:
            keys = ((f"sag-{n}", "feed_tph"), (f"flot-{n}", "feed_cu"), (f"flot-{n}", "tail_cu"),
                    (f"flot-{n}", "cu_tph"), (f"flot-{n}", "conc_tph"))
            cols = [dict(st.window(name, feat, t, prm["balance_window_min"])) for name, feat in keys]
            common = set(cols[0]).intersection(*cols[1:])
            if not common:
                continue
            tc = max(common)
            q, f, tl, cu, conc = (c[tc] for c in cols)
            if q <= 0.0:
                continue
            ok = True
            cu_in += q * f / 100.0
            cu_out += cu + max(0.0, q - conc) * tl / 100.0
        if ok and cu_in > 0.0:
            out["cu_residual_pct"] = 100.0 * (cu_in - cu_out) / cu_in
        # water over the balance window: intake (flowmeter totalizer) = water that leaves the circuit
        # (tails pores + cake moisture + evaporation, integrated) + pond change
        w = self._ends("water", ("intake_m3_total", "loss_m3_total", "pond_m3"), t)
        if w is not None and w[1]["intake_m3_total"] > 0.0:
            d = w[1]
            res_m3 = d["intake_m3_total"] - d["loss_m3_total"] - d["pond_m3"]
            out["water_residual_pct"] = 100.0 * res_m3 / d["intake_m3_total"]
            # a leak has no meter: the fresh water taken beyond what left with tails, cake and evaporation
            # (pond unchanged) is the leak, m3/h over the window
            leak = res_m3 / (w[0] / 60.0)
            out["water_leak_m3h"] = leak if leak >= prm["leak_min_m3h"] else 0.0
            out["water_leak_usd_h"] = out["water_leak_m3h"] * prm["water_usd_m3"]
        # concentrate over the balance window, per line: thickener feed = underflow to the filter +
        # inventory change; both flows from belt-weigher totalizers. The cleaner's own concentrate t/h
        # comes from the two-product formula on analyser grades held 15 min (its noise is the
        # analyser's, a few %), so it is not part of a 0.5 % balance.
        conc_in = conc_out = 0.0
        for n in LINES:
            c = self._ends(f"thick-{n}", ("feed_t_total", "underflow_t_total", "inventory_t"), t)
            if c is None:
                continue
            conc_in += c[1]["feed_t_total"]
            conc_out += c[1]["underflow_t_total"] + c[1]["inventory_t"]
        if conc_in > 0.0:
            out["conc_residual_pct"] = 100.0 * (conc_in - conc_out) / conc_in
        # power by parts
        limit = st.f("power", "grid_limit_mw")
        site = st.f("power", "site_mw")
        grind = st.f("power", "grinding_mw")
        cpd = 0.0
        for name in ("crusher-1", "crusher-2", "conveyor-1", "conveyor-2"):
            v = st.f(name, "power_kw")
            cpd += v / 1000.0 if v != NO_VALUE else 0.0
        if limit != NO_VALUE and site != NO_VALUE:
            out["power_headroom_mw"] = limit - site
            other = site - (grind if grind != NO_VALUE else 0.0) - cpd
            out["power_parts_text"] = (f"мельницы {num(grind, 1) if grind != NO_VALUE else '—'} · ЦПД и конвейеры "
                                       f"{num(cpd, 1)} · прочее {num(other, 1)} · итого {num(site, 1)} из "
                                       f"{num(limit, 0)} МВт")
        return out

    # ------------------------------------------------------------------ tact
    def compute(self, t: float) -> dict:
        """One tact at model minute t; returns the features of mod-losses."""
        prm = self.prm
        batches = all_batches(self.store, prm)
        feats: dict = {}
        results: dict[str, NodeResult] = {}
        for n in LINES:
            est_axb, est_cu, est_ascu, bname = ore_in_sag(batches, n, prm)
            fres, feed_cu, r_exp = self.eval_flot(t, n, est_ascu, bname)
            if feed_cu == NO_VALUE or feed_cu <= 0.0:
                feed_cu = est_cu
            sres = self.eval_sag(t, n, est_axb, feed_cu, r_exp)
            cres = self.eval_cyclones(t, n, est_axb, feed_cu, r_exp)
            for r in (sres, cres, fres):
                results[r.node] = r
        self.results = results
        self.balances = self.eval_balances(t)
        self.reagent = {n: self.eval_reagent(t, n) for n in LINES}
        for node in NODES:
            r = results[node]
            feats[f"{node}_gap_cu_tph"] = r.gap_cu_tph
            feats[f"{node}_gap_usd_h"] = r.gap_usd_h
            feats[f"{node}_sigma"] = r.sigma_cu_tph
            feats[f"{node}_status"] = r.status
            feats[f"{node}_status_ru"] = STATUS_RU.get(r.status, r.status)
            feats[f"{node}_roles"] = r.roles
        for n in LINES:
            r = results[f"sag-{n}"]
            feats[f"sag-{n}_e_meas_kwh_t"] = r.detail.get("e_meas", NO_VALUE)
            feats[f"sag-{n}_e_exp_kwh_t"] = r.detail.get("e_exp", NO_VALUE)
            feats[f"sag-{n}_energy_usd_h"] = r.detail.get("energy_usd_h", 0.0) if r.status in ("loss", "unsure") else 0.0
            g = self.reagent[n]
            feats[f"rougher-{n}_reagent_excess_pct"] = 100.0 * g["excess"] if g["excess"] != NO_VALUE else NO_VALUE
            feats[f"rougher-{n}_reagent_usd_h"] = g["usd_h"]
            feats[f"rougher-{n}_reagent_status"] = g["status"]
        feats["silent_text"] = self.silent_text(results)
        self.suspect = self.suspect_sensors(results, t)
        feats["suspect_sensors"] = ",".join(self.suspect)
        feats["suspect_text"] = "; ".join(self.suspect.values()) if self.suspect else \
            "сомнительных показаний не найдено"
        # an alarm that costs no copper (P80 above its expectation but below the reference size) is
        # not the headline "where copper is lost": it goes with the unsure nodes
        losses = [r for r in results.values() if r.status == "loss" and r.gap_cu_tph >= MIN_LOSS_CU_TPH]
        unsure = [r for r in results.values() if r.status == "unsure"
                  or (r.status == "loss" and r.gap_cu_tph < MIN_LOSS_CU_TPH)]
        if losses:
            top = max(losses, key=lambda r: r.gap_usd_h)
            feats["top_node"] = top.node
            feats["top_text"] = f"{self._node_ru(top.node)}: {top.text}; звать: {top.roles}"
        elif unsure:
            top = max(unsure, key=lambda r: abs(r.z))
            feats["top_node"] = top.node
            feats["top_text"] = (f"{self._node_ru(top.node)}: {top.text}"
                                 + ("; отклонение есть, меди оно не стоит" if top.status == "loss" else ""))
        else:
            feats["top_node"] = ""
            feats["top_text"] = "Потерь сверх шума не найдено (все узлы в пределах 2σ)"
        feats.update(self.balances)
        feats["processed_sim_time"] = t
        feats["resend"] = NO_VALUE
        self.processed = t
        return feats

    def suspect_sensors(self, results: dict[str, NodeResult], t: float | None = None) -> dict[str, str]:
        """Instruments whose reading the module doubts: {thing: Russian reason}.

        flowmeter-N: flotation recovery below the expectation (loss, or above 2 sigma) while the
        collector flowmeter shows the setpoint and the ore is not oxidised: the meter may drift
        (its reading is what the expectation used). analyzer-N: no analyser reading on a running line.
        """
        out: dict[str, str] = {}
        for n in LINES:
            r = results.get(f"flot-{n}")
            if r is None:
                continue
            # pH meter: the grab sample against the online reading names the sensor, and the flowmeter is not blamed for it
            lab, onl = self.store.f(f"ph-{n}", "lab_ph"), self.store.mean(f"ph-{n}", "ph", t if t is not None else self._t_last(), 60.0)
            ph_gap = abs(lab - onl) if lab != NO_VALUE and onl != NO_VALUE else 0.0
            if ph_gap >= self.prm["ph_gap_alarm"]:
                out[f"phmeter-{n}"] = (f"pH-метр {n}: ручная проба {num(lab, 2)} против онлайн-показания {num(onl, 2)} — расхождение "
                                       f"{num(ph_gap, 2)}, показание под подозрением, проверить электрод")
                continue
            if r.status in ("loss", "unsure") and r.gap_cu_tph > 0.0 and "kip" in r.role_keys:
                ratio = r.detail.get("dose_ratio", 1.0)
                out[f"flowmeter-{n}"] = (f"расходомер собирателя {n}: извлечение ниже ожидаемого (z = {num(r.z, 1)}) "
                                         f"при дозировке по расходомеру {num(100 * ratio, 0)} % уставки — "
                                         f"показание под подозрением, проверить расходомер")
            elif r.status == "no_data":
                out[f"analyzer-{n}"] = f"анализатор {n}: нет показаний при работающей линии"
            a = self.store.get(f"analyzer-{n}")
            if a is not None and a.s("state") == "SUSPECT" and a.f("age_min") > self.prm["age_stale_an_cycles"] * self.prm["an_cycle_min"]                     and self.store.s(f"flot-{n}", "state") != "STOP" and f"analyzer-{n}" not in out:
                out[f"analyzer-{n}"] = (f"анализатор {n}: последнее показание {num(a.f('age_min'), 0)} мин назад при цикле "
                                        f"{num(self.prm['an_cycle_min'], 0)} мин — пробоотборная линия засорена? хвосты и питание "
                                        f"на экране устарели, проверить линию")
            g = self.reagent.get(n) or {}
            if g.get("status") == "loss" and f"flowmeter-{n}" not in out:
                out[f"flowmeter-{n}"] = (f"расходомер собирателя {n}: показывает меньше, чем ушло из бака "
                                         f"(+{num(100 * g['excess'], 0)} %) — проверить расходомер и насос-дозатор")
        return out

    def _t_last(self) -> float:
        """Model minute of the tact being computed (the windows of the store end there)."""
        return self.processed if self.processed != NO_VALUE else self.store.max_sim_time(("site",))

    def silent_text(self, results: dict[str, NodeResult]) -> str:
        """Silent overspends in one line: SAG energy, collector, water; each with its money."""
        parts = []
        for n in LINES:
            r = results.get(f"sag-{n}")
            if r is not None and r.status in ("loss", "unsure") and r.detail.get("excess", 0.0) > 0.0:
                parts.append(f"перерасход энергии SAG-{n}: E {num(r.detail['e_meas'], 2)} против "
                             f"{num(r.detail['e_exp'], 2)} кВт·ч/т "
                             f"(+{num(100 * r.detail['excess'], 1)} %), энергия ≈ {usd_h(r.detail['energy_usd_h'])} {EST}"
                             + ("" if r.detail.get("limited") else ", медь не теряется"))
            g = self.reagent.get(n) or {}
            if g.get("status") == "loss":
                parts.append(f"перерасход собирателя на линии {n}: +{num(100 * g['excess'], 0)} % к расходомеру, "
                             f"≈ {usd_h(g['usd_h'])} {EST}")
        leak = self.balances.get("water_leak_m3h", NO_VALUE)
        if leak != NO_VALUE and leak > 0.0:
            parts.append(f"вода: невязка баланса ≈ {num(leak, 0)} м³/ч — утечка, свежая вода "
                         f"≈ {usd_h(self.balances['water_leak_usd_h'])} {EST}")
        return "; ".join(parts) if parts else "тихих перерасходов не найдено (энергия SAG, реагенты, вода в норме)"

    @staticmethod
    def _node_ru(node: str) -> str:
        kind, n = node.rsplit("-", 1)
        return {"sag": f"Мельница SAG-{n}", "cyclones": f"Гидроциклоны {n}", "flot": f"Флотация {n}"}.get(kind, node)
