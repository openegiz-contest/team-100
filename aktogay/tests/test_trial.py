"""On/off trial (sim/trial.py): shift design, stand-in policy, statistics, one paired shift."""
import json
import math
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import events as ev  # noqa: E402
from sim import trial  # noqa: E402
from sim.params import default  # noqa: E402
from sim.state import NO_VALUE  # noqa: E402
from tests.support import prm  # noqa: E402

CFG = dict(trial.DEFAULTS, n=1, jobs=1, boot=200)
CFG_NONE = dict(CFG, twin_human="none")          # the asymmetric base of VALIDATION 8.8 (the twin sees a loud trouble at its start)


class TestDesign(unittest.TestCase):
    def test_draw_shift_deterministic_and_valid(self):
        a, b = trial.draw_shift(1001, CFG), trial.draw_shift(1001, CFG)
        self.assertEqual(a, b)
        counts = {2: 0, 3: 0}
        for seed in range(1001, 1061):
            s = trial.draw_shift(seed, CFG)
            counts[len(s.troubles)] += 1
            nodes = [t.node for t in s.troubles]
            self.assertEqual(len(nodes), len(set(nodes)), nodes)
            old = trial.draw_shift(seed, CFG_NONE)
            self.assertEqual([t.issue for t in old.troubles], [t.issue for t in s.troubles])      # same draw, only the finding time differs
            for t, t_old in zip(s.troubles, old.troubles):
                self.assertTrue(8 * 60 <= t.t_start_min <= 18 * 60)
                self.assertEqual(t.hidden, t.kind in trial.HIDDEN)
                if t.hidden:
                    self.assertGreater(t.t_found_min, t.t_start_min)       # the module's finding time (symmetric base)
                    self.assertAlmostEqual(t_old.t_found_min, t.t_start_min + CFG["detect_min"])     # --twin-human none: start + detect_min
                if t.kind in ("crusher", "trip"):
                    self.assertIn(f"stock{t.line}_t0", s.overrides)
            self.assertEqual(s.overrides["crew_sigma_ln"], 0.4)
        self.assertGreater(counts[2], counts[3])
        self.assertGreater(counts[3], 5)

    def test_miss_draw(self):
        cfg = dict(CFG, miss=1.0)
        s = next(trial.draw_shift(seed, cfg) for seed in range(1001, 1100)
                 if any(t.hidden for t in trial.draw_shift(seed, cfg).troubles))
        for t in s.troubles:
            if t.hidden:
                self.assertTrue(t.missed)
                self.assertEqual(t.t_found_min, NO_VALUE)


class TestPolicy(unittest.TestCase):
    def test_rank_fallback_money_order(self):
        p = prm()
        now = 9 * 60 + 20
        dose = {"issue": "dose:1", "kind": "dose", "crew": "crew-kip", "safety": "", "loss_cu_tph": 0.55,
                "hours_to_loss": 0.0, "repair_h": 0.5, "arrive_h": 0.5, "crew_free_at_min": NO_VALUE,
                "t_known_min": 9 * 60 + 15}
        trip = {"issue": "trip:2", "kind": "trip", "crew": "crew-kip", "safety": "", "loss_cu_tph": 13.7,
                "hours_to_loss": 7.8, "repair_h": 3.0, "arrive_h": 0.5, "crew_free_at_min": NO_VALUE,
                "t_known_min": 9 * 60 + 20}
        order = [t["issue"] for t in trial.rank_fallback([trip, dose], now, p)]
        self.assertEqual(order, ["dose:1", "trip:2"])            # the stock covers the trip repair
        trip_short = dict(trip, hours_to_loss=0.5)
        order = [t["issue"] for t in trial.rank_fallback([dose, trip_short], now, p)]
        self.assertEqual(order, ["trip:2", "dose:1"])            # stock runs out first: crusher first
        safety = dict(dose, issue="piezo", crew="", safety="S0", loss_cu_tph=0.0)
        grid = dict(dose, issue="grid", crew="", loss_cu_tph=3.0)
        order = [t["issue"] for t in trial.rank_fallback([trip_short, dose, grid, safety], now, p)]
        self.assertEqual(order[:2], ["piezo", "grid"])

    def test_load_rank(self):
        fn, name = trial.load_rank()
        self.assertTrue(callable(fn))
        self.assertIn("rank", name)
        p = prm()
        now = 9 * 60 + 20
        dose = {"issue": "dose:1", "kind": "dose", "line": 1, "node": "flot-1", "crew": "crew-kip", "hidden": True,
                "safety": "", "loss_cu_tph": 0.55, "loss_usd_h": 7600.0, "hours_to_loss": 0.0, "repair_h": 0.5,
                "repair_p90_h": 0.8, "arrive_h": 0.5, "crew_free_at_min": NO_VALUE,
                "crew_slots_free_min": [NO_VALUE], "t_known_min": 9 * 60 + 15}
        trip = dict(dose, issue="trip:2", kind="trip", line=2, node="crusher-2", hidden=False, loss_cu_tph=13.7,
                    loss_usd_h=190000.0, hours_to_loss=7.8, repair_h=3.0, repair_p90_h=5.0, t_known_min=now)
        order = fn([trip, dose], now, p, 1)
        self.assertEqual(sorted(order), ["dose:1", "trip:2"])
        self.assertEqual(order[0], "dose:1")                     # the stock covers the trip repair


class TestStats(unittest.TestCase):
    def test_wilson(self):
        lo, hi = trial.wilson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.2775, places=3)
        lo, hi = trial.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=3)
        self.assertAlmostEqual(hi, 0.7634, places=3)

    def test_wilcoxon_exact(self):
        # textbook pairs: all positive differences, n = 6 -> W+ = 21, p = 2 / 64
        r = trial.wilcoxon([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        self.assertEqual(r["method"], "exact")
        self.assertAlmostEqual(r["w_plus"], 21.0)
        self.assertAlmostEqual(r["p"], 2 / 64)
        r = trial.wilcoxon([1.0, -1.0, 2.0, -2.0, 0.0])
        self.assertIn("normal", r["method"])
        self.assertAlmostEqual(r["w_plus"], 5.0)                 # ties: ranks 1.5, 1.5, 3.5, 3.5
        self.assertGreater(r["p"], 0.5)
        self.assertEqual(trial.wilcoxon([0.0, 0.0])["n"], 0)

    def test_wilcoxon_normal_matches_exact_for_large_n(self):
        rng = random.Random(3)
        xs = [rng.gauss(0.3, 1.0) for _ in range(40)]
        exact = trial.wilcoxon(xs)
        self.assertEqual(exact["method"], "exact")
        tied = xs + [xs[0]]                                  # one tie forces the normal approximation
        approx = trial.wilcoxon(tied)
        self.assertIn("normal", approx["method"])
        self.assertLess(abs(math.log(max(exact["p"], 1e-6)) - math.log(max(approx["p"], 1e-6))), 1.0)

    def test_summarize_and_bootstrap(self):
        rng = random.Random(1)
        xs = [rng.gauss(0.8, 1.36) for _ in range(100)]
        s = trial.summarize(xs, 2000, random.Random(2))
        self.assertEqual(s["n"], 100)
        lo, hi = s["ci95_mean_bca"]
        self.assertLess(lo, s["mean"])
        self.assertGreater(hi, s["mean"])
        self.assertLess(hi - lo, 1.0)
        self.assertAlmostEqual(s["p0"] + s["p_minus"] + s["p_plus"], 1.0)
        self.assertTrue(0 <= s["p_minus_ci95_wilson"][0] <= s["p_minus"] <= s["p_minus_ci95_wilson"][1] <= 1)
        self.assertEqual(trial.percentile(sorted(xs), 0.0), min(xs))
        self.assertEqual(trial.percentile(sorted(xs), 1.0), max(xs))
        same = trial.summarize([0.0] * 5, 200, random.Random(0))
        self.assertEqual(same["ci95_mean_bca"], [0.0, 0.0])


class TestShift(unittest.TestCase):
    def test_one_paired_shift(self):
        cfg = dict(CFG, no_twin=True)
        row = trial.run_shift((1001, cfg))
        self.assertEqual(set(row["cu_t_2000"]), {"by_value", "by_loud", "base", "no_twin"})
        for name, v in row["cu_t_2000"].items():
            self.assertTrue(math.isfinite(v) and v > 0, name)
            self.assertGreater(row["cu_t_0800"][name], v)              # the night adds copper
        self.assertAlmostEqual(row["d_cu_t"], row["cu_t_2000"]["by_value"] - row["cu_t_2000"]["by_loud"])
        self.assertIn(row["n_troubles"], (2, 3))
        for tr in row["troubles"]:
            self.assertTrue(tr["issue"] in row["bookings"]["by_value"] or tr["kind"] in trial.DECISION
                            or tr["missed"], tr)
        self.assertLessEqual(row["loss_cu_t_2000"]["by_value"], row["loss_cu_t_2000"]["no_twin"] + 5.0)

    def test_fair_baseline_is_the_default(self):
        """Without the twin people still take the hard-ore, grid and reline decisions, only later
        (asis); --no-asis brings back the old baseline where nobody takes them."""
        self.assertTrue(trial.DEFAULTS["asis"])
        self.assertEqual(trial.DEFAULTS["asis_notice_min"], 10.0)
        seed = next(s for s in range(1001, 1100)                  # a deep cut: a ball mill is shed
                    if trial.draw_shift(s, CFG).overrides.get("pow_c2_limit_mw", 999.0) < 210.0)
        row = trial.run_shift((seed, dict(CFG, no_twin=True)))
        grid = next(t for t in row["troubles"] if t["kind"] == "grid")
        rec = row["bookings"]["no_twin"].get(grid["issue"])
        self.assertIsNotNone(rec)
        self.assertEqual(rec["by"], "operator")
        self.assertGreaterEqual(rec["t_call_min"], grid["t_start_min"] + 10.0 - 1e-6)
        row_old = trial.run_shift((seed, dict(CFG, no_twin=True, asis=False)))
        self.assertNotIn(grid["issue"], row_old["bookings"]["no_twin"])
        self.assertGreaterEqual(row["cu_t_2000"]["no_twin"], row_old["cu_t_2000"]["no_twin"] - 1e-6)

    def test_run_trial_small(self):
        doc = trial.run_trial(dict(CFG, n=2, seed0=1003))
        self.assertEqual(doc["n"], 2)
        self.assertIn("d_cu_t_2000", doc["summary"])
        self.assertEqual(doc["summary"]["d_cu_t_2000"]["n"], 2)
        text = trial.format_report(doc)
        self.assertIn("Wilcoxon", text)
        self.assertIn("by_value", text)


class _FakePlant:
    """Just enough of a plant for the controller rules that do not step the model."""

    def __init__(self):
        self.prm = default()
        self._loud = {}


def _controller(mode, **cfg):
    return trial.Controller(_FakePlant(), [], mode, dict(CFG, **cfg), 1001, None)


def _trouble(kind="crusher", start=600.0, hidden=False):
    return trial.Trouble(kind + ":1", kind, 1, "crusher-1", "crew-cpd", start, hidden,
                         t_found_min=start + 75.0 if hidden else NO_VALUE)


class TestNoviceFromData(unittest.TestCase):
    """VALIDATION 8.9: the novice is parameterised from the open works (rows nov_* of the table), not by a rule of ours."""

    def test_parameters_have_sources_ranges_and_labels(self):
        from sim.params import TABLE
        for key, value, label in (("nov_detect_mult", 1.658, "analog"), ("nov_p_diag", 0.05, "analog"),
                                  ("nov_p_step", 0.00473, "analog"), ("nov_stress_mult", 2.0, "analog"),
                                  ("nov_steps", 10, "assumption"), ("nov_detect_sigma_ln", 0.112, "calc")):
            r = TABLE[key]
            self.assertAlmostEqual(r.value, value, places=6)
            self.assertEqual(r.label, label)
            self.assertLessEqual(r.min, r.value)
            self.assertGreaterEqual(r.max, r.value)
            self.assertTrue(r.source.strip())
        self.assertAlmostEqual(433.982 / 261.798, TABLE["nov_detect_mult"].value, places=3)         # arXiv 2509.06657, p. 29
        self.assertAlmostEqual(TABLE["nov_p_diag"].min, 0.0089, places=3)                            # Wilson 95 % of 1/20
        self.assertAlmostEqual(TABLE["nov_p_diag"].max, 0.2361, places=3)
        self.assertAlmostEqual(14 / 2958, TABLE["nov_p_step"].value, places=5)                       # NRC ML24151A634, table 7
        self.assertAlmostEqual(3 / 3038, TABLE["nov_p_step"].min, places=5)
        cv_n, cv_e = 105.556 / 433.982, 56.155 / 261.798
        self.assertAlmostEqual(math.sqrt(math.log((1 + cv_n ** 2) / (1 + cv_e ** 2))), TABLE["nov_detect_sigma_ln"].value, places=3)

    def test_only_the_people_part_of_the_time_is_scaled(self):
        k = _controller("novice_det")
        k.plant.prm = k.plant.prm.copy(nov_detect_sigma_ln=0.0)
        m = k.plant.prm["nov_detect_mult"]
        cr = _trouble("crusher", 600.0)                               # alarm notice 5-15 min after the start: all of it is people
        self.assertAlmostEqual(k.nov_seen_at(cr) - 600.0, m * (k.seen_at(cr) - 600.0))
        grid = trial.Trouble("grid", "grid", 0, "power", "", 600.0, False)           # 10 min to decide
        self.assertAlmostEqual(k.nov_seen_at(grid) - 600.0, m * 10.0)
        hard = trial.Trouble("hard:1", "hard", 1, "pit", "", 600.0, False)           # 2 h of ore on the way is physics, 10 min is people
        self.assertAlmostEqual(k.nov_seen_at(hard) - 600.0, k.plant.prm["scen_hard_lead_h"] * 60.0 + m * 10.0)
        rope = trial.Trouble("roping:1", "roping", 1, "cyclones-1", "", 600.0, True)  # 45 min on the screens + 10 min
        self.assertAlmostEqual(k.nov_seen_at(rope) - 600.0, m * 55.0)
        dose = _trouble("dose", hidden=True)                          # the laboratory, not the people
        self.assertEqual(k.human_min(dose), 0.0)

    def test_spread_keeps_the_mean_and_is_common_to_the_copies(self):
        k = _controller("novice_det")
        cr = _trouble("crusher", 600.0)
        xs = []
        for seed in range(1001, 1401):
            k.seed = seed
            xs.append((k.nov_seen_at(cr) - 600.0) / (k.seen_at(cr) - 600.0))
        self.assertAlmostEqual(sum(xs) / len(xs), k.plant.prm["nov_detect_mult"], delta=0.03)       # mean preserved
        self.assertGreater(max(xs) - min(xs), 0.5)                                                  # a real spread
        k2 = _controller("novice_r")
        k2.seed = k.seed
        self.assertEqual(k.nov_seen_at(cr), k2.nov_seen_at(cr))

    def test_slips_follow_the_rows_and_stress_doubles_them(self):
        k = _controller("novice_err")
        p = k.plant.prm
        tr = _trouble("crusher", 600.0)
        n_dx = n_step = 0
        n = 4000
        for seed in range(1, n + 1):
            k.seed = seed
            lost = k.nov_slip_min(tr, 700.0, True)                    # nothing else is open: no stress
            self.assertTrue(lost == 0.0 or 20.0 <= lost <= 80.0, lost)
            n_dx += u01_below(seed, "nov-dx:" + tr.issue, p["nov_p_diag"])
            n_step += u01_below(seed, "nov-st:" + tr.issue, 1 - (1 - p["nov_p_step"]) ** p["nov_steps"])
        self.assertAlmostEqual(n_dx / n, 0.05, delta=0.012)
        self.assertAlmostEqual(n_step / n, 1 - (1 - 0.00473) ** 10, delta=0.01)                     # 4.6 % of the calls
        other = _trouble("grid", 650.0)
        other.issue = "grid"
        k.troubles = [tr, other]
        lost_stress = sum(1 for seed in range(1, n + 1) if (setattr(k, "seed", seed) or k.nov_slip_min(tr, 700.0, True)) > 0.0)
        k.troubles = [tr]
        lost_calm = sum(1 for seed in range(1, n + 1) if (setattr(k, "seed", seed) or k.nov_slip_min(tr, 700.0, True)) > 0.0)
        self.assertGreater(lost_stress, 1.6 * lost_calm)                                            # two open troubles: x2 on both
        self.assertEqual(_controller("novice_twin").nov_slip_min(tr, 700.0, False) >= 0.0, True)

    def test_twin_with_a_novice_has_no_diagnosis_slip(self):
        k = _controller("novice_twin", twin_human="none")
        tr = _trouble("crusher", 600.0)
        for seed in range(1, 600):
            k.seed = seed
            k._nov_ready.clear()
            k.troubles = [tr]
            k._prepare_novice_twin(700.0)
            ready = k._nov_ready[tr.issue]
            self.assertTrue(abs(ready - (600.0 + trial.EPS)) < 1e-9 or 620.0 - 1e-6 < ready < 640.0 + 1e-6, ready)   # a step slip only: +20..40 min
        # the same draw as in the novice: a step skipped is skipped on any path
        a, b = _controller("novice_r"), _controller("novice_twin", twin_human="none")
        for seed in range(1, 300):
            a.seed = b.seed = seed
            self.assertEqual(a.nov_slip_min(tr, 700.0, False), b.nov_slip_min(tr, 700.0, False))

    def test_hidden_losses_stay_with_the_laboratory(self):
        k = trial.Controller(_FakePlant(), [_trouble("dose", 600.0, hidden=True)], "novice_r", dict(CFG), 1001, None)
        booked = []
        k._book = lambda tr, t: booked.append(tr.issue)
        k.tact(1400.0)
        self.assertEqual(booked, [])

    def test_a_shift_with_the_new_copies_keeps_the_expert_and_the_twin_unchanged(self):
        base = dict(CFG_NONE, library="tier_s")        # the twin that sees a loud trouble at its start: it calls before both
        seed = 1004                                                    # hard ore and a protection trip
        a = trial.run_shift((seed, dict(base, copies=["base", "by_value", "no_twin", "novice"])))       # the same 1-minute cycle as with the new copies
        b = trial.run_shift((seed, dict(base, copies=["base", "by_value", "no_twin", "nov_det", "nov_err", "nov_r", "nov_twin"])))
        for name in ("base", "no_twin", "by_value"):
            self.assertEqual(a["cu_t_2000"][name], b["cu_t_2000"][name], name)
        self.assertLessEqual(b["cu_t_2000"]["nov_r"], b["cu_t_2000"]["no_twin"] + 1e-6)           # slower to see: not better
        self.assertLessEqual(b["cu_t_2000"]["nov_det"], b["cu_t_2000"]["no_twin"] + 1e-6)
        self.assertEqual(b["cu_t_2000"]["nov_err"], b["cu_t_2000"]["no_twin"])                    # no slip on this seed: the same as the expert
        self.assertGreater(b["cu_t_2000"]["nov_twin"], b["cu_t_2000"]["nov_r"])
        call = {n: b["bookings"][n]["trip:2"]["t_call_min"] for n in ("no_twin", "nov_r", "nov_twin")}
        self.assertGreater(call["nov_r"], call["no_twin"])                                         # the novice calls later than the expert
        self.assertLess(call["nov_twin"], call["no_twin"])                                         # the twin calls earlier than both


def u01_below(seed, key, p):
    from sim.state import u01
    return 1 if u01(seed, 0, key) < p else 0


class TestAlarmFloodInTrial(unittest.TestCase):
    def test_counting_does_not_change_the_shift(self):
        cfg = dict(CFG, library="tier_s", copies=["no_twin", "by_value"])
        a = trial.run_shift((1001, cfg))
        b = trial.run_shift((1001, dict(cfg, alarms=["no_twin", "by_value"])))
        self.assertEqual(a["cu_t_2000"], b["cu_t_2000"])
        self.assertEqual(a["cu_t_0800"], b["cu_t_0800"])
        self.assertNotIn("alarm_flood_2000", a)
        f = b["alarm_flood_2000"]["no_twin"]
        self.assertGreater(f["events"], 5)                           # one protection trip is a chain of nodes, not one alarm
        self.assertEqual(f["main"], 1)
        self.assertEqual(f["issues"], b["n_troubles"])
        self.assertLess(f["per_10min"], f["isa_per_10min"])          # below the ISA orientation: no flood claimed


class TestExperiment23(unittest.TestCase):
    def test_defaults_keep_the_22_10_behaviour(self):
        """Everything of the experiment of 24.10 stays at its default except the base: since 24.10 evening the default is the
        symmetric one (twin_human same, VALIDATION 8.17); --twin-human none gives the 8.8 behaviour back."""
        d = trial.DEFAULTS
        self.assertIsNone(d["copies"])
        self.assertIsNone(d["crews"])
        self.assertEqual(d["call_delay_min"], 0.0)
        self.assertEqual(d["compliance"], 1.0)
        self.assertEqual((d["twin_human"], d["asis_hard"]), ("same", "dig"))
        k = _controller("value", twin_human="none")
        tr = _trouble()
        self.assertAlmostEqual(k.known_at(tr), 600.0 + trial.EPS)
        self.assertEqual(k.delay_of(tr), 0.0)

    def test_call_delay_applies_to_the_chosen_kinds_only(self):
        k = _controller("value", call_delay_min=60.0, delay_kinds=["dose"], twin_human="none")
        self.assertEqual(k.delay_of(_trouble("crusher")), 0.0)
        dose = _trouble("dose", hidden=True)
        self.assertEqual(k.delay_of(dose), 60.0)
        self.assertAlmostEqual(k.known_at(dose), 600.0 + 75.0 + 60.0)
        k_all = _controller("value", call_delay_min=30.0, twin_human="none")
        self.assertAlmostEqual(k_all.known_at(_trouble("crusher")), 600.0 + 30.0 + trial.EPS)
        ks = _controller("value", call_delay_min=60.0, delay_kinds=["dose"])        # symmetric base: the card is read after the delay, too
        self.assertAlmostEqual(ks.known_at(dose), 600.0 + 75.0 + 60.0 + ev.notice_delay_min(ks.seed, dose.issue, ks.plant.prm))

    def test_no_detection_copy_sees_what_people_see(self):
        k = _controller("value_nd")
        dose = _trouble("dose", hidden=True)
        self.assertEqual(k.known_at(dose), math.inf)              # the quiet loss stays with laboratory and tails alarm
        cr = _trouble("crusher")
        self.assertGreaterEqual(k.known_at(cr), 600.0 + k.plant.prm["issue_notice_lo_min"])
        self.assertLessEqual(k.known_at(cr), 600.0 + k.plant.prm["issue_notice_hi_min"])
        grid = trial.Trouble("grid", "grid", 0, "power", "", 600.0, False)
        self.assertAlmostEqual(k.known_at(grid), 610.0)
        hard = trial.Trouble("hard:1", "hard", 1, "pit", "", 600.0, False)
        self.assertAlmostEqual(k.known_at(hard), 600.0 + k.plant.prm["scen_hard_lead_h"] * 60.0 + 10.0)

    def test_compliance_draw_is_shared_and_monotone(self):
        tr = _trouble("crusher")
        lo, hi = _controller("value", compliance=0.5), _controller("value", compliance=0.75)
        self.assertTrue(_controller("value").followed(tr))
        for seed in range(1001, 1040):
            lo.seed = hi.seed = seed
            if lo.followed(tr):
                self.assertTrue(hi.followed(tr))                  # the same draw: a higher share follows a superset
        shares = []
        for q in (0.5, 0.75):
            k = _controller("value", compliance=q)
            n = 0
            for seed in range(1001, 1201):
                k.seed = seed
                n += k.followed(tr)
            shares.append(n / 200)
        self.assertTrue(0.4 < shares[0] < 0.6 and 0.65 < shares[1] < 0.85, shares)
        ignored = _controller("value", compliance=0.0)
        self.assertAlmostEqual(ignored.known_at(tr), ignored.seen_at(tr))

    def test_novice_waits_for_the_crew_to_arrive(self):
        a, b = _trouble("crusher", 600.0), _trouble("trip", 610.0)
        b.issue, b.node, b.crew = "trip:2", "crusher-2", "crew-kip"
        k = trial.Controller(_FakePlant(), [b, a], "novice", dict(CFG), 1001, None)
        booked = []

        def fake_book(tr, t):
            booked.append(tr.issue)
            k.booked[tr.issue] = {"t_call_min": t, "t_arrive_min": t + 30.0, "t_done_min": t + 90.0}

        k._book = fake_book
        k.plant._loud = {a.issue: 1.0, b.issue: 2.0}
        t = 640.0                                                   # both seen; a appeared first
        k.tact(t)
        self.assertEqual(booked, ["crusher:1"])
        self.assertEqual(k.plant._loud, {})                          # the own call of the plant at the alarm is off
        k.tact(t + 10.0)
        self.assertEqual(booked, ["crusher:1"])                      # the crew of the first has not arrived yet
        k.tact(t + 31.0)
        self.assertEqual(booked, ["crusher:1", "trip:2"])

    def test_library_and_modes(self):
        self.assertEqual(set(trial.MODE_OF.values()) - {"asis"}, {"value", "loud", "novice", "value_nd", "novice_det",
                                                                   "novice_err", "novice_r", "novice_twin"})
        with self.assertRaises(ValueError):
            trial.Controller(_FakePlant(), [], "nope", dict(CFG), 1, None)
        with self.assertRaises(ValueError):
            trial.run_shift((1001, dict(CFG, copies=["base", "ghost"])))

    def test_slopes_holm_and_linear_contrast(self):
        rows = [[{"seed": s, "y": 2.0 * x + s} for s in (1, 2, 3)] for x in (0.0, 1.0, 2.0)]
        sl = trial._slopes(rows, [0.0, 1.0, 2.0], lambda r: r["y"])
        self.assertEqual(len(sl), 3)
        for v in sl:
            self.assertAlmostEqual(v, 2.0)
        self.assertEqual(trial._holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])
        r = {"cu_t_2000": {"a": 3.0, "b": 1.0, "c": NO_VALUE}}
        self.assertEqual(trial._lin([r], {"a": 1.0, "b": -1.0}, "cu"), [2.0])
        self.assertEqual(trial._lin([r], {"a": 1.0, "c": -1.0}, "cu"), [])        # a missing value drops the shift

    def test_aggregate_on_synthetic_runs(self):
        import json
        import tempfile

        def row(seed, ob, od, cl, tw, nv):
            cu = {"no_twin": ob, "value_nd": od, "by_loud": cl, "by_value": tw, "novice": nv, "base": 330.0}
            return {"seed": seed, "n_troubles": 2, "shared_crew": seed % 2 == 0, "n_hidden": seed % 2,
                    "troubles": [{"kind": "crusher"}], "cu_t_2000": cu, "cu_t_0800": cu,
                    "usd_2000": {k: x * 100.0 for k, x in cu.items()},
                    "kwh_per_t_cu_2000": {k: 50.0 for k in cu}, "rec_pct_2000": {k: 87.0 for k in cu},
                    "down_min_2000": {k: dict.fromkeys(trial.DOWN_NODES, 10.0) for k in cu},
                    "loss_cu_t_2000": {k: 330.0 - x for k, x in cu.items() if k != "base"}}

        rows = [row(s, 300.0, 300.1, 301.0, 301.2, 299.0) for s in range(1, 21)]
        doc = {"shifts": rows, "seeds": [1, 20], "config": {}}
        with tempfile.TemporaryDirectory() as d:
            for tag in ("main_full", "crews1"):
                with open(os.path.join(d, tag + ".json"), "w", encoding="utf-8") as f:
                    json.dump(doc, f)
            out = trial.aggregate(d)
        pairs = out["b3_d1"]["main_full"]["pairs"]
        self.assertAlmostEqual(pairs["twin-expert"]["cu"]["mean"], 1.2)
        self.assertAlmostEqual(pairs["expert-novice"]["cu"]["mean"], 1.0)
        self.assertTrue(out["b3_d1"]["main_full"]["order_twin_gt_expert_gt_novice"])
        c = out["b4"]["1"]["contrasts_cu"]
        self.assertAlmostEqual(c["detection"]["mean"], 0.5 * (1.0 + 1.2 - 0.0 - 0.1))
        self.assertAlmostEqual(c["interaction"]["mean"], (1.2 - 1.0) - (0.1 - 0.0))
        self.assertIn("crews2", out["files_missing"])

    def test_experiment_shift_has_new_copies_crews_and_metrics(self):
        cfg = dict(CFG, copies=["base", "by_value", "no_twin", "novice", "value_nd"], crews=2, library="tier_s")
        row = trial.run_shift((1001, cfg))
        self.assertEqual(set(row["cu_t_2000"]), {"base", "by_value", "no_twin", "novice", "value_nd"})
        self.assertEqual(row["d_cu_t"], NO_VALUE)                 # no by_loud copy in this run
        for name in row["cu_t_2000"]:
            self.assertGreater(row["kwh_per_t_cu_2000"][name], 0.0)
            self.assertEqual(set(row["down_min_2000"][name]), set(trial.DOWN_NODES))
            self.assertLessEqual(max(row["down_min_2000"][name].values()), 2 * 720.0 + 1e-6)
        self.assertLessEqual(max(row["down_min_2000"]["base"].values()), 1e-6)    # no troubles, nothing stands
        self.assertGreater(sum(row["down_min_2000"]["no_twin"].values()), 0.0)
        with self.assertRaises(KeyError):
            trial._val(row, "no_twin", "nope")
        doc = trial.run_trial(dict(cfg, n=1, seed0=1001))
        self.assertEqual(doc["summary"], {})
        self.assertIn("no by_value", trial.format_report(doc))


def _shift_tr(kind, start=600.0, hidden=False, found=None, line=1):
    issue, node, crew = ev.issue_for(kind, line)
    return trial.Trouble(issue, kind, 0 if kind in ev.SITE_KINDS else line, node, crew, start, hidden,
                         t_found_min=NO_VALUE if found is None else found)


class TestSymmetricBase(unittest.TestCase):
    """VALIDATION 8.17: the twin is added to the people. With --twin-human same (default) it sees no earlier than they do,
    except where the module's finding time was measured; --twin-human none keeps the base of 8.8."""

    SEEDS = range(1001, 1011)

    def test_constants_come_from_the_module_evaluation(self):
        with open(os.path.join(ROOT, "web", "static", "detect_eval.json"), encoding="utf-8") as f:
            d = json.load(f)
        for kind, mag in (("dose", "0.4"), ("cyclone", "1.0")):
            row = d["by_cause_magnitude"][kind][mag]
            self.assertEqual(trial.MODULE_FIND[kind], (row["latency_median_min"], row["latency_p90_min"]), kind)
        self.assertEqual(set(trial.MODULE_FIND), {"dose", "cyclone"})
        p = default()                                                  # the magnitudes the numbers were measured at are the defaults of the trial
        self.assertAlmostEqual(p["hc_dose_drop"], 0.4)
        self.assertEqual(p["hc_cyclone_n"], 1)
        self.assertEqual(trial.IMMEDIATE, ("crusher", "trip", "grid", "reline"))
        self.assertEqual(trial.DEFAULTS["twin_human"], "same")
        self.assertEqual(trial.DEFAULTS["asis_hard"], "dig")

    def test_finding_time_follows_the_measured_median_and_p90(self):
        for kind, (med, p90) in trial.MODULE_FIND.items():
            tr = _shift_tr(kind, 600.0, True)
            xs = sorted(trial.found_min(seed, CFG, tr) - 600.0 for seed in range(1, 2001))
            self.assertAlmostEqual(xs[1000], med, delta=2.0, msg=kind)
            self.assertAlmostEqual(xs[1799], p90, delta=3.0, msg=kind)
            self.assertEqual(trial.found_min(7, CFG, tr), trial.found_min(7, CFG, tr))        # one draw per (seed, issue)
            self.assertEqual(trial.found_min(7, CFG_NONE, tr), 600.0 + CFG["detect_min"])
        other = _shift_tr("roping", 600.0, True)                                              # not measured: start + detect_min
        self.assertEqual(trial.found_min(7, CFG, other), 600.0 + CFG["detect_min"])

    def test_loud_kinds_are_known_at_the_people_minute(self):
        for kind in trial.IMMEDIATE:
            tr = _shift_tr(kind)
            for mode in ("value", "loud"):
                for seed in self.SEEDS:
                    k = _controller(mode)
                    k.seed = seed
                    self.assertEqual(k.known_at(tr), k.seen_at(tr), (kind, mode, seed))
                    if kind in ("crusher", "trip"):
                        self.assertAlmostEqual(k.known_at(tr), 600.0 + ev.notice_delay_min(seed, tr.issue, k.plant.prm))
                    else:
                        self.assertAlmostEqual(k.known_at(tr), 610.0)                          # asis_notice_min after the start

    def test_the_twin_is_never_later_than_the_people(self):
        cfg = dict(CFG, library="tier_s")
        n = 0
        for seed in self.SEEDS:
            shift = trial.draw_shift(seed, cfg)
            k = trial.Controller(_FakePlant(), shift.troubles, "value", cfg, seed, None)
            for tr in shift.troubles:
                self.assertLessEqual(k.known_at(tr), k.seen_at(tr) + 1e-9, (seed, tr.issue))
                n += 1
        self.assertGreater(n, 20)

    def test_roping_ph_drift_and_hpgr_are_seen_with_the_people(self):
        for kind in ("phdrift", "hpgr", "roping"):
            tr = _shift_tr(kind, 600.0, True, found=675.0, line=2 if kind == "hpgr" else 1)
            for seed in self.SEEDS:
                k = _controller("value")
                k.seed = seed
                self.assertEqual(k.known_at(tr), k.seen_at(tr), (kind, seed))
                self.assertTrue(math.isfinite(k.known_at(tr)))

    def test_mantle_hard_ore_dose_and_cyclone(self):
        prm = default()
        for seed in self.SEEDS:
            k = _controller("value")
            k.seed = seed
            mantle = _shift_tr("mantle")
            self.assertAlmostEqual(k.known_at(mantle), 600.0 + ev.notice_delay_min(seed, mantle.issue, prm))      # the plant alarm
            self.assertLess(k.known_at(mantle), k.seen_at(mantle))
            hard = _shift_tr("hard")
            self.assertAlmostEqual(k.known_at(hard), 610.0)                                                      # the same notice
            self.assertAlmostEqual(k.seen_at(hard), 600.0 + prm["scen_hard_lead_h"] * 60.0 + 10.0)              # the people act at the dig
            for kind in ("dose", "cyclone"):
                tr = _shift_tr(kind, 600.0, True, found=trial.found_min(seed, CFG, _shift_tr(kind, 600.0, True)))
                self.assertAlmostEqual(k.known_at(tr), tr.t_found_min + ev.notice_delay_min(seed, tr.issue, prm))   # the card is read like an alarm
                missed = _shift_tr(kind, 600.0, True)
                self.assertEqual(k.known_at(missed), math.inf)                                                   # missed by the module

    def test_none_keeps_the_base_of_8_8(self):
        for mode in ("value", "loud"):
            k = _controller(mode, twin_human="none")
            for kind in ("crusher", "trip", "grid", "reline", "mantle", "hard"):
                self.assertAlmostEqual(k.known_at(_shift_tr(kind)), 600.0 + trial.EPS, msg=kind)
            self.assertAlmostEqual(k.known_at(_shift_tr("dose", 600.0, True, found=675.0)), 675.0)
        k = _controller("value", twin_human="none")
        self.assertLess(k.known_at(_shift_tr("trip")), k.seen_at(_shift_tr("trip")))

    def test_the_plant_alarm_is_silenced_for_the_twin_copy_only(self):
        tr = _shift_tr("crusher")
        for human, mode, left in (("same", "value", 0), ("none", "value", 1), ("same", "loud", 1), ("same", "asis", 1)):
            k = _controller(mode, twin_human=human)
            k.troubles = [tr]
            k.plant._loud = {tr.issue: 1.0}
            k.tact(tr.t_start_min - 1.0)                               # nothing is known yet: only the silencing is looked at
            self.assertEqual(len(k.plant._loud), left, (human, mode))
        # the delay of the twin's call is not the people's: the copy "as now" keeps its alarm (E14)
        k = _controller("asis", call_delay_min=10.0)
        k.troubles = [tr]
        k.plant._loud = {tr.issue: 1.0}
        k.tact(tr.t_start_min - 1.0)
        self.assertEqual(len(k.plant._loud), 1)
        k = _controller("loud", call_delay_min=10.0)
        k.troubles = [tr]
        k.plant._loud = {tr.issue: 1.0}
        k.tact(tr.t_start_min - 1.0)
        self.assertEqual(len(k.plant._loud), 0)                        # the twin's copy with a delay still books the call itself

    def test_the_call_delay_does_not_silence_the_copy_as_now(self):
        """E14: with --call-delay 10 the copy "как сейчас" silenced its own alarm and never called (seed 1001, trip:2: 198.8 t Cu
        against 318.1 t). The delay belongs to the twin's call; the people's call is the same with and without it."""
        cfg = dict(CFG, copies=["base", "no_twin"])
        a = trial.run_shift((1001, cfg))
        b = trial.run_shift((1001, dict(cfg, call_delay_min=10.0)))
        self.assertIn("trip:2", a["bookings"]["no_twin"])
        self.assertIn("trip:2", b["bookings"]["no_twin"])
        self.assertEqual(a["bookings"]["no_twin"]["trip:2"], b["bookings"]["no_twin"]["trip:2"])
        self.assertEqual(a["cu_t_2000"]["no_twin"], b["cu_t_2000"]["no_twin"])

    def test_hard_ore_seen_at_the_sag_is_never_before_the_dig(self):
        for seed, library in ((1001, "base"), (1004, "tier_s")):
            cfg = dict(CFG, copies=["base", "no_twin"], library=library)
            dig = trial.run_shift((seed, dict(cfg, asis_hard="dig")))
            sag = trial.run_shift((seed, dict(cfg, asis_hard="sag")))
            hard = [t["issue"] for t in dig["troubles"] if t["kind"] == "hard"]
            self.assertTrue(hard, seed)
            for issue in hard:
                self.assertIn(issue, dig["bookings"]["no_twin"])
                if issue in sag["bookings"]["no_twin"]:                # finite: the block reached the SAG inside the window
                    self.assertGreaterEqual(sag["bookings"]["no_twin"][issue]["t_call_min"],
                                            dig["bookings"]["no_twin"][issue]["t_call_min"], (seed, issue))
            self.assertLessEqual(sag["cu_t_2000"]["no_twin"], dig["cu_t_2000"]["no_twin"] + 1e-6)     # seeing it later is not better

    def test_the_symmetric_base_runs_on_a_one_minute_cycle(self):
        """With a 5-minute cycle the twin copy would book a loud trouble up to 5 minutes after the people (and the plant's alarm) do,
        i.e. behind them by construction (seed 1001: +0.16 against +0.81 t Cu at 1 minute). `--twin-human same` therefore forces the
        cycle of `fine_tact_min`, whatever `tact_min` says; with `none` the twin is ahead of the people anyway."""
        cfg = dict(CFG, copies=["base", "by_value", "no_twin"], library="tier_s", tact_min=5.0)
        self.assertEqual(cfg.get("twin_human", trial.DEFAULTS["twin_human"]), "same")
        for seed in (1001, 1004):
            row = trial.run_shift((seed, cfg))
            n = 0
            for issue, ex in row["bookings"]["no_twin"].items():
                tw = row["bookings"]["by_value"].get(issue)
                if tw is None or issue.split(":")[0] not in trial.IMMEDIATE:
                    continue
                n += 1
                self.assertLessEqual(tw["t_call_min"], ex["t_call_min"] + 1e-6, (seed, issue))      # never behind the people
            self.assertGreater(n, 0, seed)

    def test_options_reach_the_result_config(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "t.json")
            self.assertEqual(trial.main(["--n", "1", "--jobs", "1", "--boot", "200", "--twin-human", "none", "--asis-hard", "sag",
                                         "--copies", "base,by_value,no_twin", "--out", out]), 0)
            with open(out, encoding="utf-8") as f:
                doc = json.load(f)
        self.assertEqual((doc["config"]["twin_human"], doc["config"]["asis_hard"]), ("none", "sag"))
        doc = trial.run_trial(dict(CFG, copies=["base", "by_value", "no_twin"]))
        self.assertEqual((doc["config"]["twin_human"], doc["config"]["asis_hard"]), ("same", "dig"))
        self.assertIn("twin-human same", trial.format_report(doc))


if __name__ == "__main__":
    unittest.main()
