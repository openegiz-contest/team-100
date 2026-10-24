import json
import math
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # aktogay/: packages sim, tests
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import params
from sim.params import (FEATURE_RULES, LABELS, RELINE_CALENDAR, RELINE_KINDS, TABLE, Param, ParamSet, Reline,
                        check_param, check_reline)
from sim.state import topology

THINGS_JSON = os.path.join(ROOT, "setup", "things.json")

# Types whose "state" feature was missing from the rules (file 18, gaps) and must now be there.
STATE_TYPES = ("site", "pit", "stockpile", "line", "cyclones", "flot", "rougher", "cleaner", "water", "power",
               "fleet", "thick", "filter", "conc-stock")


class TestTable(unittest.TestCase):
    def test_table_consistent(self):
        self.assertEqual(params.check_table(), [])

    def test_every_param_sourced_labelled_in_range(self):
        """Fails when any Param lacks a source or a label or has its value outside [min, max]."""
        self.assertGreater(len(TABLE), 250)
        for p in TABLE.values():
            self.assertIsInstance(p.source, str, p.key)
            self.assertTrue(p.source.strip(), f"{p.key}: no source")
            self.assertIn(p.label, LABELS, f"{p.key}: label {p.label!r}")
            self.assertTrue(p.unit.strip(), f"{p.key}: no unit")
            self.assertTrue(all(math.isfinite(x) for x in (p.value, p.min, p.max)), p.key)
            self.assertLessEqual(p.min, p.max, p.key)
            self.assertTrue(p.min <= p.value <= p.max, f"{p.key}: {p.value} outside [{p.min}, {p.max}]")
            self.assertEqual(check_param(p), [], p.key)
        for r in RELINE_CALENDAR:
            self.assertIn(r.label, LABELS)
            self.assertIn(r.kind, RELINE_KINDS)
            self.assertTrue(r.source.strip())
            self.assertEqual(check_reline(r), [])

    def test_check_param_catches_bad_rows(self):
        """The row check itself must flag a missing source or label and a value outside the range."""
        good = TABLE["sag_rated_mw"]
        self.assertEqual(check_param(good), [])
        bad_source = Param("sag_x", 1.0, 0.0, 2.0, "MW", "  ", "fact")
        self.assertTrue(any("source" in m for m in check_param(bad_source)))
        bad_label = Param("sag_x", 1.0, 0.0, 2.0, "MW", "doc", "guess")
        self.assertTrue(any("label" in m for m in check_param(bad_label)))
        outside = Param("sag_x", 3.0, 0.0, 2.0, "MW", "doc", "fact")
        self.assertTrue(any("outside" in m for m in check_param(outside)))
        below = Param("sag_x", -1.0, 0.0, 2.0, "MW", "doc", "fact")
        self.assertTrue(any("outside" in m for m in check_param(below)))
        swapped = Param("sag_x", 1.0, 2.0, 0.0, "MW", "doc", "fact")
        self.assertTrue(any("min" in m for m in check_param(swapped)))
        no_unit = Param("sag_x", 1.0, 0.0, 2.0, "", "doc", "fact")
        self.assertTrue(any("unit" in m for m in check_param(no_unit)))
        prefix = Param("zzz_x", 1.0, 0.0, 2.0, "MW", "doc", "fact")
        self.assertTrue(any("prefix" in m for m in check_param(prefix)))
        nan = Param("sag_x", float("nan"), 0.0, 2.0, "MW", "doc", "fact")
        self.assertTrue(any("finite" in m for m in check_param(nan)))
        bad_kind = Reline(2, 2025, 8, 15, "doc", "fact", "overhaul")
        self.assertTrue(any("kind" in m for m in check_reline(bad_kind)))
        self.assertTrue(any("label" in m for m in check_reline(Reline(2, 2025, 8, 15, "doc", "maybe"))))
        self.assertTrue(any("source" in m for m in check_reline(Reline(2, 2025, 8, 15, "", "fact"))))

    def test_changed_rows_carry_url_and_page(self):
        """Rows corrected after the source check (file 18, section 7) must name a URL in their source."""
        for key in ("econ_power_kzt_kwh", "econ_co2_t_mwh", "sag_austin_j", "ore_axb_base", "blk_axb_mean",
                    "sag_f80_mm", "flot_jose_ascu", "flot_grade_pp_ln", "sag_morrell_a", "liner_eta_new",
                    "stock_total_t", "stock_live_frac", "stock_live_t", "cstock_cap_t", "pond_proc_m3_per_line",
                    "conv_length_km", "conv_transit_min", "ore_density_t_m3", "ball_rated_mw", "fleet_payload_t",
                    "crush_power_mw", "sag_e_2017_19_kwh_t", "pit_exc_tph", "water_fresh_hi_m3_t"):
            self.assertIn("http", TABLE[key].source, key)
        self.assertIn("p. 3", TABLE["tgt_q3_2025_ore_kt"].source)
        self.assertNotIn("TODO", TABLE["tgt_q3_2025_ore_kt"].source)
        for p in TABLE.values():
            self.assertNotIn("TODO", p.source, p.key)

    def test_fit_rows(self):
        fit = {k for k, p in TABLE.items() if p.fit}
        self.assertEqual(fit, {"cal_avail", "sag_k", "flot_rinf0_pct", "water_evap_m3h", "pow_other_mw"})

    def test_feature_rules_cover_topology(self):
        # 22 plant types + person, truck, face, road and four instruments of the site passport
        self.assertEqual(len(FEATURE_RULES), 35)            # + drill rigs and dozers + pH meter
        for typ, rules in FEATURE_RULES.items():
            self.assertIn("state_ru", rules, typ)
        types = {t.type for t in topology().values()}
        self.assertTrue(types <= set(FEATURE_RULES), types - set(FEATURE_RULES))
        self.assertEqual(set(FEATURE_RULES) - types, {"batch"})

    def test_state_and_totals_in_rules(self):
        """Every twin type with a state enum has a 'state' rule; line has the run totals (things.json)."""
        for typ in STATE_TYPES:
            self.assertIn("state", FEATURE_RULES[typ], typ)
        for typ in FEATURE_RULES:
            self.assertIn("state", FEATURE_RULES[typ], typ)
        for f in ("cum_cu_t_total", "cum_mwh_total", "cum_m3_total", "cum_usd_total"):
            self.assertIn(f, FEATURE_RULES["line"])

    def test_rules_match_things_json(self):
        """FEATURE_RULES keys per physical type are exactly the features declared in setup/things.json."""
        with open(THINGS_JSON, encoding="utf-8") as f:
            things = json.load(f)
        for typ, rules in FEATURE_RULES.items():
            declared = set(things["types"][typ]["features"])
            self.assertEqual(set(rules), declared, typ)
            if "state" in declared:
                self.assertTrue(things["types"][typ].get("states"), typ)


class TestCalendar(unittest.TestCase):
    def test_calendar_per_reports(self):
        """Calendar of planned SAG stops per the KAZ reports (file 18, section 2: C015, C016, C017)."""
        by_kind = {}
        for r in RELINE_CALENDAR:
            by_kind.setdefault(r.kind, []).append((r.line, r.year, r.month))
        # the reports name exactly one SAG reline: line 2, August 2025 (Q3 2025 report, p. 3)
        self.assertEqual(by_kind["reline"], [(2, 2025, 8)])
        # planned SAG maintenance named for line 2 in October 2024 (Q4 2024 report, p. 3)
        self.assertEqual(by_kind["sag_service"], [(2, 2024, 10)])
        # planned maintenance without the kind of work: line 1 in H1 2024 (quarter assumed), both lines Dec 2025
        self.assertEqual(sorted(by_kind["stop"]), [(1, 2024, 3), (1, 2025, 12), (2, 2025, 12)])
        for r in RELINE_CALENDAR:
            self.assertTrue(r.day_assumed)
            self.assertIn("http", r.source)
            self.assertIn("p. 3", r.source)
            if r.kind != "reline":
                self.assertIn("assum", r.source)     # the reline is our assumption for these stops
        q1 = [r for r in RELINE_CALENDAR if r.line == 1 and r.year == 2024][0]
        self.assertEqual(q1.label, "assumption")
        self.assertEqual([r.label for r in RELINE_CALENDAR if r.year == 2025], ["fact"] * 3)


class TestDerived(unittest.TestCase):
    """calc rows must follow from the rows they are derived from."""

    def v(self, k):
        return TABLE[k].value

    def test_line_rate(self):
        q = self.v("tgt_2025_ore_mt") * 1e6 / 2 / self.v("cal_hours_run")
        self.assertAlmostEqual(self.v("cal_line_tph"), q, places=6)
        self.assertAlmostEqual(q, 3853, delta=1)

    def test_sag_energy_and_k(self):
        e = self.v("sag_power_sp_mw") * 1000 / self.v("cal_line_tph")
        self.assertAlmostEqual(self.v("sag_e_base_kwh_t"), e, places=6)
        dwi = 100 * self.v("ore_density_t_m3") / self.v("ore_axb_base")
        k = e / (self.v("sag_f80_mm") ** self.v("sag_morrell_a") * dwi ** self.v("sag_morrell_b"))
        self.assertAlmostEqual(self.v("sag_k"), k, places=9)

    def test_austin_coefficient_per_source(self):
        """Austin 1990 load term (1 - 1.03 J); the Bond/Rowland 0.937 is no longer used."""
        p = TABLE["sag_austin_j"]
        self.assertEqual((p.value, p.label), (1.03, "analog"))
        self.assertIn("Austin 1990", p.source)
        self.assertIn("http", p.source)

    def test_analog_ranges_and_assumptions(self):
        """A*b and F80 of the analogs are ranges, not point values: our numbers are assumptions inside them."""
        for key in ("ore_axb_base", "blk_axb_mean", "sag_f80_mm"):
            p = TABLE[key]
            self.assertEqual(p.label, "assumption", key)
            self.assertIn("Touro", p.source)
            self.assertIn("Josemaria", p.source)
        self.assertEqual((TABLE["ore_axb_base"].min, TABLE["ore_axb_base"].max), (32.8, 40.8))
        self.assertEqual((TABLE["sag_f80_mm"].min, TABLE["sag_f80_mm"].max), (128, 137))
        for key in ("liner_eta_new", "liner_eta_peak", "liner_eta_end", "liner_x_ramp", "liner_x_peak"):
            self.assertEqual(TABLE[key].label, "assumption", key)
        self.assertEqual(TABLE["sag_morrell_a"].label, "assumption")
        self.assertIn("GMG", TABLE["sag_morrell_a"].source)

    def test_flotation_terms_per_source(self):
        """Josemaria regression is a total recovery; the ASCu unit is unconfirmed, so that term is an assumption."""
        g = TABLE["flot_grade_pp_ln"]
        self.assertEqual((g.value, g.label), (4.093, "analog"))
        self.assertIn("total", g.note)
        a = TABLE["flot_jose_ascu"]
        self.assertEqual((a.value, a.label), (1.043, "assumption"))
        self.assertIn("not confirmed", a.note)
        self.assertEqual(TABLE["flot_ascu_ref_pct"].unit, "% of Cu")

    def test_rougher_r_inf(self):
        r = self.v("flot_rinf0_pct") * (1 - math.exp(-self.v("flot_ktau0"))) * self.v("clean_r0_pct") / 100
        self.assertAlmostEqual(r, self.v("flot_rec_ref_pct"), places=6)

    def test_power_parts(self):
        mills = 2 * (self.v("sag_power_sp_mw") + self.v("ball_per_line") * self.v("ball_power_mw"))
        grid = mills / self.v("pow_motor_eff")
        cc = 2 * self.v("crush_power_mw") + 2 * self.v("conv_power_mw")
        site = grid + cc + 2 * self.v("pow_line_aux_mw") + self.v("pow_other_mw")
        self.assertAlmostEqual(grid, 139.58, delta=0.01)
        self.assertAlmostEqual(cc, 8.78, delta=0.01)
        self.assertAlmostEqual(site, 260.0, delta=0.1)
        self.assertLess(site, self.v("pow_grid_limit_mw"))

    def test_line_aux_from_eia(self):
        """Per running line: line 2 EIA electricity per operating hour minus mills, crusher, conveyor."""
        per_line = 827514.0 / self.v("cal_hours_run")
        mills = (self.v("sag_power_sp_mw") + 2 * self.v("ball_power_mw")) / self.v("pow_motor_eff")
        aux = per_line - mills - self.v("crush_power_mw") - self.v("conv_power_mw")
        self.assertAlmostEqual(self.v("pow_line_aux_mw"), aux, places=9)
        self.assertAlmostEqual(aux, 28.5, delta=0.05)

    def test_2024_other_load_consistent(self):
        """Table other load: 2024 electricity at 58.3 Mt and the base rate (all three published);
        the line part runs only while its line runs, the site part all year."""
        per_line = (self.v("sag_power_sp_mw") + 2 * self.v("ball_power_mw")) / self.v("pow_motor_eff") \
            + self.v("crush_power_mw") + self.v("conv_power_mw") + self.v("pow_line_aux_mw")
        hours = self.v("tgt_2024_ore_mt") * 1e6 / 2 / self.v("cal_line_tph")
        gwh = (2 * per_line * hours + self.v("pow_other_mw") * 366 * 24) / 1000
        self.assertAlmostEqual(gwh, self.v("tgt_2024_energy_gwh"), delta=0.5)
        self.assertNotIn("tgt_2023_ore_mt", TABLE)        # 2023 ore is not in the sources

    def test_water_and_belt(self):
        pore = 1 / self.v("water_tails_dry_t_m3") - 1 / self.v("ore_density_t_m3")
        self.assertAlmostEqual(self.v("water_tails_m3_t"), pore, places=9)
        self.assertTrue(0.29 <= pore <= 0.34)
        s = self.v("water_tails_solids_pct")
        self.assertGreater((100 - s) / s, pore)           # discharge water above the pores returns to the pond
        y = self.v("tgt_2024_grade_pct") * self.v("tgt_2024_rec_pct") / 100 / self.v("flot_conc0_pct")
        moist = self.v("filt_moist_pct") / (100 - self.v("filt_moist_pct"))
        ore = self.v("tgt_2024_ore_mt") * 1e6
        evap = (self.v("tgt_2024_water_mm3") * 1e6 - ore * (pore * (1 - y) + y * moist)) / (366 * 24)
        self.assertAlmostEqual(self.v("water_evap_m3h"), evap, places=6)
        # belt: main conveyor 2 504 m by the PEK p. 18 (OSM 2.45 km as a cross-check) at 4.5 m/s, about 9 min
        # (the 14 min of the design file was the 3.8 km Bozshakol belt)
        self.assertEqual(self.v("conv_length_km"), 2.504)
        self.assertEqual(TABLE["conv_length_km"].label, "project")
        self.assertIn("p. 18", TABLE["conv_length_km"].source)
        self.assertIn("openstreetmap", TABLE["conv_length_km"].source.lower())
        self.assertAlmostEqual(self.v("conv_transit_min"),
                               self.v("conv_length_km") * 1000 / self.v("conv_speed_ms") / 60, places=9)
        self.assertAlmostEqual(self.v("conv_transit_min"), 9.27, delta=0.01)
        # fresh water reference: OVOS 73 512.92 m3/d over the design 25 Mt / 8 059 h
        self.assertAlmostEqual(self.v("water_fresh_hi_m3_t"), 0.99, places=9)
        self.assertEqual(self.v("pond_proc_m3_per_line"), 56000)
        self.assertIn("decant", TABLE["pond_m3_0"].note)

    def test_stockpile_capacity_per_ovos(self):
        """Live stock = OVOS working volume 163 kt x live share; the 40 kt of the design file is the live part."""
        self.assertEqual(self.v("stock_total_t"), 163000)
        self.assertEqual(TABLE["stock_total_t"].label, "project")
        self.assertAlmostEqual(self.v("stock_live_t"), self.v("stock_total_t") * self.v("stock_live_frac"), places=6)
        self.assertAlmostEqual(self.v("stock_live_t"), 40000, places=6)
        self.assertTrue(0.17 <= self.v("stock_live_frac") <= 0.30)
        self.assertEqual(TABLE["stock_live_t"].label, "calc")
        for key in ("stock1_t0", "stock2_t0"):
            self.assertIn("moment of the event", TABLE[key].note)

    def test_economics_per_source(self):
        t = TABLE["econ_power_kzt_kwh"]
        self.assertEqual((t.value, t.min, t.max, t.label), (16, 16, 27, "fact"))
        self.assertIn("zakon.kz", t.source)
        c = TABLE["econ_co2_t_mwh"]
        self.assertEqual((c.value, c.label), (0.64, "calc"))
        self.assertAlmostEqual(2308e3 / (13.06e9 / 3.6e3), 0.636, delta=0.001)
        self.assertEqual(TABLE["fleet_payload_t"].value, 136)
        self.assertEqual(TABLE["ball_rated_mw"].label, "vendor")
        self.assertIn("at-minerals", TABLE["ball_rated_mw"].source)
        self.assertNotIn("not found", TABLE["ball_rated_mw"].note)
        self.assertEqual((TABLE["crush_power_mw"].min, TABLE["crush_power_mw"].max), (0.75, 1.0))
        d = TABLE["ore_density_t_m3"]
        self.assertEqual((d.value, d.label), (2.66, "vendor"))
        self.assertIn("2.77", d.note)

    def test_feed_grade_and_slope(self):
        cu = self.v("tgt_2025_ore_mt") * self.v("tgt_2025_feed_pct") / 100 * self.v("tgt_2025_rec_pct") / 100
        self.assertAlmostEqual(cu * 1e3, self.v("tgt_2025_cu_kt"), places=6)
        self.assertLess(abs(self.v("tgt_2025_feed_pct") - self.v("tgt_2025_grade_pct")),
                        self.v("tol_grade_round_pct"))
        # grade slope: Josemaria total-recovery coefficient (analog); constant tails is only the upper bound
        g = TABLE["flot_grade_pp_ln"]
        self.assertEqual((g.value, g.label), (4.093, "analog"))
        self.assertAlmostEqual(g.max, 100 - self.v("flot_rec_ref_pct"), places=9)
        self.assertAlmostEqual(self.v("liner_feed_end_mm"), self.v("liner_wear_mm_mt") * 9.96, places=9)

    def test_ball_charge_rows(self):
        self.assertEqual(self.v("sag_load0_pct"), 25.0)                      # Bradken total load
        self.assertEqual(self.v("sag_ball_load_pct"), 12.0)                  # Bradken ball charge
        dens = 0.6 * 7.8 / ((12 * (0.6 * 7.8 + 0.4 * 1.8) + 13 * (0.6 * 2.66 + 0.4 * 1.8)) / 25)
        self.assertAlmostEqual(self.v("sag_ball_dens_mult"), dens, places=12)

    def test_scenario_timings(self):
        q = self.v("cal_line_tph")
        self.assertAlmostEqual(self.v("stock1_t0") / q, 3.0, delta=0.02)          # C1: 3 h 00 min
        self.assertAlmostEqual((self.v("stock_live_t") - self.v("stock1_t0")) / q, 7.37, delta=0.02)  # C4
        self.assertAlmostEqual(self.v("stock2_t0") / q, 7.79, delta=0.02)          # fork: 7 h 47 min

    def test_reline_hours_not_from_the_check_quarter(self):
        """Reline downtime is an assumption; the whole Q3/Q2 rate drop is only its upper bound."""
        r = TABLE["liner_reline_h"]
        self.assertEqual(r.label, "assumption")
        whole = self.v("tgt_q3_2025_hours") - (1 + self.v("tgt_reline_q_pct") / 100) * self.v("tgt_q2_2025_hours")
        self.assertAlmostEqual(r.max, whole, places=6)
        self.assertLess(r.value, r.max)


class TestParamSet(unittest.TestCase):
    def test_copy_and_overrides(self):
        a = params.default()
        b = a.copy(sag_k=0.55)
        self.assertEqual(a["sag_k"], TABLE["sag_k"].value)
        self.assertEqual(b["sag_k"], 0.55)
        self.assertEqual(b.overrides(), {"sag_k": 0.55})
        with self.assertRaises(KeyError):
            b.set("no_such_key", 1.0)
        self.assertIsInstance(ParamSet({"cal_avail": 0.9})["cal_avail"], float)

    def test_markdown(self):
        rows = params.markdown_rows()
        self.assertEqual(len(rows), len(TABLE) + 2)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "PARAMETERS.md")
            self.assertEqual(params.main(["--md", path]), 0)
            with open(path, "rb") as f:
                data = f.read()
        self.assertNotIn(b"\r\n", data)
        for k in TABLE:
            self.assertIn(k.encode(), data)
        text = data.decode("utf-8")
        self.assertIn("| Kind |", text)
        self.assertIn("sag_service", text)

    def test_parameters_md_in_repo_is_current(self):
        """aktogay/PARAMETERS.md (the list the passports' source "assume" points to) matches the tables."""
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "PARAMETERS.md")
        self.assertTrue(os.path.isfile(path), "aktogay/PARAMETERS.md missing: python -I aktogay/run.py params "
                                              "--md aktogay/PARAMETERS.md")
        with open(path, encoding="utf-8", newline="") as f:
            have = f.read()
        self.assertEqual(have, params.markdown(), "PARAMETERS.md is stale: regenerate it")
        self.assertIn("balance_window_min", have)          # the modules' table is there too


if __name__ == "__main__":
    unittest.main()
