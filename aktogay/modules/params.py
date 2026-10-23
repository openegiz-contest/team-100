"""Parameter table of the analysis modules (design file 17, sections 4 and 5; file 19, section 3).

The modules keep their own table: they never import the simulator. The
formulas are the published ones (Morrell, Bond, first-order flotation
kinetics, two-product formula); the numbers come from the same sources as
the stand's PARAMETERS.md, so the expectation differs from the simulator
only by what the modules cannot know: block-model error, measurement noise
and hidden causes.

Labels: fact, vendor, project, analog, assumption, calc (as in the stand).

  from modules.params import default
  prm = default()
  prm["cusum_h"]            # -> 6.5
  python -I modules/params.py --check
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass

LABELS = ("fact", "vendor", "project", "analog", "assumption", "calc")


@dataclass(frozen=True)
class Param:
    key: str
    value: float
    min: float
    max: float
    unit: str
    source: str
    label: str
    note: str = ""


S_KAZ25 = "KAZ Minerals Q4 2025 production report (FY2025), p. 3"
S_BRAD = "Bradken + KAZ Minerals Aktogay mill optimisation whitepaper, Oct 2021 (line 1)"
S_OVOS = "Aktogay line 2 EIA (OVOS) 2018"
S_SMC = "Touro NI 43-101 2018, table 13.11; Josemaria FS 2020, sections 13.4.1 and 17.2.2"
S_MORRELL = "Morrell, 'Predicting the specific energy of AG/SAG mills and HPGR', eq. 2 (E = K F80^a DWi^b)"
S_JOSE = "Josemaria FS 2020, section 13.6.1 p. 82 (grade and ASCu slopes on total recovery)"
S_LIHIR = "Lihir, AusIMM Mill Operators 2024 (pebble crusher stop: +6 % / +10 % E_SAG); not verified"
S_LME = "Westmetall, LME Cu cash 15.10.2026; range: World Bank CMO April 2026"
S_NIST = "NIST/SEMATECH e-Handbook 6.3.2.3 (CUSUM, k = 0.5, h chosen for ARL)"
S_D4 = "design file 17, section 4"
S_COMMO = ("CommoFlow 26.08.2026 (vendor blog, opened 23.10.2026): payable 96.5 % of contained copper or the grade "
           "less one unit, whichever is less favourable to the seller")
S_MIR = ("MIR RK order no. 348 of 30.12.2014, items 12, 63, 315, 316, 326 (opened 23.10.2026): work permit, work inside "
         "a mill by permit, sign 'Do not switch on! People are working!'")
S_D5 = "design file 17, section 5"
S_D7 = "design file 17, section 7"
S_E19 = "evidence map file 19, section 3"
S_METSO = "Metso Courier on-stream analyser: cycle 12-16 min, precision 1-6 %"
S_IVESON = "Iveson, Galvin 2024, Minerals Engineering 212 (two-product recovery error propagation)"
S_REZAEI = "Rezaei Dashtaki et al. 2025, Sci Rep 15:4565 (repair times lognormal)"
S_GOPAL = "Gopalakrishnan 2018, PhD Chalmers (order robustness, 70 % threshold is ours)"
S_HSE = "HSE CHIS6 (priority by consequence and response time); Parsa et al. 2022"
S_TARIFF = "Zakon.kz 22.07.2026: single purchaser electricity price 16 KZT/kWh from 15.07.2026 (same row as the model)"
S_PINTO = ("Pinto et al. 2025, Scientific Reports 15:21398 (Vale, Sossego SAG): 9.29 -> 8.75 kWh/t, -5.84 %, "
           "productivity +1.90 % after cascade and feedforward control; literature, another plant")
S_VAZIFEH = ("Vazifeh, Jorjani, Bagherian 2010, Trans. Nonferrous Met. Soc. China 20:2371, section 4.4 p. 2377: Sungun "
             "plant Z11 22 g/t + AP407 21 g/t (means of 90 operating days), lab optimum 12 + 11 g/t; analog")
S_KUJAWA = ("Kujawa (Paterson & Cooke), AIChE 2016 Water Recovery in Mining, slide 20: tailings water loss 0.72 / 0.41 / "
            "0.37 / 0.18 m3/t (vendor engineering example; context only)")
S_PLOCHER = ("Plocher et al. 2011 'Effective Shift Handover' (Honeywell, ENGEN refinery, simulator, 10 operator pairs): "
             "logged items 57.48 -> 76.11 % (p < 0.02), recall 42.10 -> 51.06 % (p = 0.12); literature, context only")


def _p(key, value, lo, hi, unit, source, label, note=""):
    return Param(key, float(value), float(lo), float(hi), unit, source, label, note)


# Derived constants (calc rows use them).
_LINE_TPH = 62.1e6 / 2 / 8059                       # 3852.7 t/h per line
_SAG_P0_KW = 26000.0
_SAG_E = _SAG_P0_KW / _LINE_TPH                     # 6.748 kWh/t
_DWI_BASE = 100.0 * 2.66 / 35.0                     # 7.6 kWh/m3
_SAG_K = _SAG_E / (130.0 ** 0.2 * _DWI_BASE ** 0.8)  # Morrell K at the 2025 operating point
_K_BASE = 1.0 - math.exp(-3.5)                      # rougher kinetics share at base residence
_C_BASE = 0.97                                      # cleaner stage recovery, fraction
_RINF0 = 87.2 / (_K_BASE * _C_BASE)                 # 92.70 %: R_inf giving 87.2 % total

PARAMS: tuple[Param, ...] = (
    # ---- operating point and SAG (section 4) ----
    _p("line_tph_base", _LINE_TPH, 3500, 4200, "t/h", S_KAZ25 + "; " + S_OVOS + " p. 26 (8059 h)", "calc",
       "62.1 Mt / 2 lines / 8059 h"),
    _p("sag_power_sp_mw", 26.0, 24.0, 27.5, "MW", S_D4, "assumption", "shaft setpoint, 93 % of 28"),
    _p("sag_rated_mw", 28, 28, 28, "MW", S_BRAD, "vendor", "gearless drive"),
    _p("sag_e_base_kwh_t", _SAG_E, 6.0, 7.5, "kWh/t", S_D4, "calc", "26.0 MW / 3853 t/h"),
    _p("sag_f80_mm", 130, 128, 137, "mm", S_SMC, "assumption"),
    _p("sag_morrell_a", 0.2, 0.07, 0.2, "-", S_MORRELL, "assumption"),
    _p("sag_morrell_b", 0.8, 0.7, 1.0, "-", S_MORRELL, "assumption"),
    _p("sag_k", _SAG_K, 0.40, 0.60, "-", S_D4, "calc", "K such that E = 6.748 kWh/t at A*b 35, F80 130 mm"),
    _p("ore_density_t_m3", 2.66, 2.6, 2.77, "t/m3", S_BRAD, "vendor"),
    _p("ore_axb_base", 35, 32.8, 40.8, "-", S_SMC, "assumption", "block-model mean"),
    _p("ore_axb_hard", 27, 24, 30, "-", S_D7, "assumption", "hard ore of scenario C3"),
    _p("ore_bwi_base", 19.4, 17.3, 20.9, "kWh/t", S_BRAD, "vendor"),
    _p("ore_bwi_hard", 20.9, 20.9, 20.9, "kWh/t", S_BRAD, "vendor", "design value"),
    _p("peb_frac_base", 0.15, 0.10, 0.23, "-", S_D4, "assumption", "pebbles per t of fresh feed at A*b 35"),
    _p("peb_frac_hard", 0.25, 0.20, 0.40, "-", S_D4, "assumption", "at A*b 27"),
    _p("peb_limit_tph", 740, 682, 792, "t/h", S_OVOS + " p. 26", "assumption"),
    _p("peb_stop_e_med", 1.06, 1.06, 1.06, "-", S_LIHIR, "analog"),
    _p("peb_stop_e_hard", 1.10, 1.10, 1.10, "-", S_LIHIR, "analog"),
    _p("motor_eff", 0.96, 0.94, 0.97, "-", S_D4, "assumption", "grid = shaft / 0.96"),
    # ---- ball mills and cyclones ----
    _p("ball_power_mw", 20.5, 19.5, 21.5, "MW", S_D4, "assumption", "shaft, 93 % of 22 (Bozshakol analog)"),
    _p("ball_per_line", 2, 2, 2, "-", S_BRAD, "vendor"),
    _p("ball_f80_um", 2500, 1500, 3500, "um", S_D4, "analog"),
    _p("ball_p80_min_um", 120, 100, 150, "um", S_D4, "assumption", "cyclone overflow floor"),
    _p("p80_ref_um", 180, 180, 180, "um", S_BRAD, "vendor", "flotation feed P80 target"),
    # ---- flotation (section 4) ----
    _p("flot_tau0_min", 30, 20, 40, "min", S_D4, "assumption", "rougher residence at base t/h"),
    _p("flot_ktau0", 3.5, 2.5, 4.5, "-", S_D4, "assumption", "k tau at base residence"),
    _p("flot_rinf0_pct", _RINF0, 88, 96, "%", S_D4, "calc", "R_inf giving 87.2 % total at base"),
    _p("flot_grade_pp_ln", 4.093, 0.0, 6.0, "pp", S_JOSE, "analog", "total R per ln(g / g0)"),
    _p("flot_grade_ref_pct", 0.41, 0.41, 0.41, "% Cu", S_KAZ25, "fact", "g0"),
    _p("flot_jose_ascu", 1.043, 0.5, 1.5, "pp/pp", S_JOSE, "assumption", "total R per pp of ASCu"),
    _p("flot_ascu_ref_pct", 5.0, 2.0, 10.0, "% of Cu", S_D4, "assumption"),
    _p("flot_p80_pp_10um", 0.3, 0.1, 0.5, "pp", S_D4, "assumption", "R loss per 10 um above 180"),
    _p("flot_dose_pp", 3.5, 2.0, 4.0, "pp", S_D7, "assumption", "R loss at 40 % under-dose"),
    _p("flot_dose_ref_deficit", 0.40, 0.40, 0.40, "-", S_D7, "assumption"),
    _p("flot_dose_sp_gt", 25, 20, 30, "g/t", S_OVOS, "project", "xanthate 0.025 kg/t"),
    _p("flot_pull0_pct", 7, 5, 13, "%", S_D4, "assumption", "rougher mass pull at g0"),
    _p("clean_r0_pct", 97, 95, 98.5, "%", S_D4, "assumption"),
    _p("clean_pp_10pp", 1.0, 0.5, 2.0, "pp", S_D4, "assumption", "cleaner R loss per 10 pp extra pull"),
    _p("flot_conc0_pct", 24.3, 24.3, 24.3, "% Cu", S_OVOS, "project"),
    _p("flot_conc_slope", 0.5, 0.2, 1.0, "-", S_D4, "assumption", "grade = 24.3 - 0.5 (R - R0)"),
    _p("flot_rec_ref_pct", 87.2, 87.2, 87.2, "%", S_KAZ25, "fact", "R0"),
    _p("flot_conc_max_pct", 34.6, 30.0, 34.6, "% Cu", "CuFeS2 stoichiometry", "calc"),
    _p("flot_delay_min", 15, 10, 20, "min", S_D4, "assumption", "transport delay; the expectation window covers it"),
    _p("flot_tau_min", 20, 10, 30, "min", S_D4, "assumption", "first-order lag"),
    _p("acs_tail_sp_pct", 0.075, 0.065, 0.090, "% Cu", S_D4, "assumption", "control-system tails alarm setpoint"),
    # ---- what the modules cannot know: block error and noise (section 4) ----
    _p("blk_err_axb_sigma", 0.12, 0.065, 0.15, "-", S_D4 + "; " + S_MORRELL, "assumption",
       "lognormal error of the block-model A*b"),
    _p("blk_err_cu_sigma", 0.05, 0.03, 0.18, "-", S_D4, "assumption", "relative error of the block Cu"),
    _p("blk_err_ascu_pp", 1.0, 0.5, 2.0, "pp", S_D4, "assumption", "additive error of the block ASCu"),
    _p("sens_an_cycle_min", 15, 12, 16, "min", S_D4 + "; " + S_METSO, "assumption", "on-stream analyser cycle"),
    _p("sens_an_feed_sigma", 0.03, 0.01, 0.06, "-", S_D4 + "; " + S_METSO, "assumption", "relative"),
    _p("sens_an_tail_sigma", 0.05, 0.03, 0.10, "-", S_D4 + "; " + S_METSO, "assumption", "relative"),
    _p("sens_an_conc_sigma", 0.03, 0.01, 0.06, "-", S_D4 + "; " + S_METSO, "assumption", "relative"),
    _p("sens_weigher_sigma", 0.01, 0.005, 0.02, "-", S_D4, "assumption", "belt weigher, relative"),
    _p("sens_power_sigma", 0.003, 0.001, 0.005, "-", S_D4, "assumption", "power meter, relative"),
    _p("sens_p80_sigma_um", 5, 3, 8, "um", S_D4, "assumption", "P80 analyser, absolute"),
    _p("model_err_sag", 0.08, 0.05, 0.10, "-", S_MORRELL, "analog",
       "circuit model error, 1 SD, shown in text, not in z (bias, not noise)"),
    _p("model_err_rec_pp", 1.0, 0.5, 3.0, "pp", S_E19, "assumption", "recovery model error, shown in text"),
    # ---- detector (file 19, section 3 B) ----
    _p("cusum_k", 0.5, 0.25, 1.0, "-", S_NIST, "analog", "reference value, half the shift to find"),
    _p("cusum_h", 6.5, 4.0, 8.0, "-", S_NIST + "; " + S_E19, "calc",
       "decision interval for 6 monitors: about 0.95 false alarms a week with the fast threshold"),
    _p("cusum_fast_z", 3.5, 3.0, 4.0, "-", S_E19, "assumption", "one-cycle threshold"),
    _p("unsure_z", 2.0, 1.5, 2.5, "-", S_D5, "assumption", "below: 'inside noise'; above without alarm: 'unsure'"),
    _p("window_min", 45, 30, 60, "min", S_D5, "assumption", "expectation window (3 analyser cycles)"),
    _p("hist_min", 120, 60, 180, "min", S_D5, "assumption", "history kept per thing, model min"),
    _p("balance_window_min", 120, 45, 180, "min", S_D5, "assumption",
       "concentrate and water balances: totalizer differences and the inventory change over this window "
       "(1 % weigher noise per step falls to about 0.1-0.3 %; at least 60 min between counters)"),
    _p("tact_losses_min", 5, 5, 5, "min", S_D5, "assumption"),
    _p("tact_ore_min", 15, 15, 15, "min", S_D5, "assumption"),
    _p("tact_priority_min", 5, 5, 5, "min", S_D5, "assumption"),
    # ---- money (section 5) ----
    _p("cu_price_usd_t", 14539, 10000, 15000, "USD/t", S_LME, "fact", "LME cash 15.10.2026; band 10 000-15 000"),
    _p("cu_price_lo_usd_t", 10000, 10000, 10000, "USD/t", S_LME, "fact", "band low"),
    _p("cu_price_hi_usd_t", 15000, 15000, 15000, "USD/t", S_LME, "fact", "band high"),
    _p("payable_frac", 0.955, 0.90, 0.97, "-", S_KAZ25, "calc", "210.4 / 220.3 kt payable in concentrate"),
    # ---- ore forecast (section 3 'stockpile is not FIFO', section 5) ----
    _p("pit_block_t", 15000, 10000, 30000, "t", S_D4, "assumption", "one block = one batch"),
    _p("pit_haul_min", 30, 20, 45, "min", S_D4, "assumption", "face to crusher"),
    _p("conv_travel_min", 14, 10, 20, "min", S_D4, "calc", "3.8 km / 4.5 m/s"),
    _p("exc_dig_tph", 2600, 2000, 3000, "t/h", S_D4, "assumption", "one excavator"),
    _p("stock_live_t", 40000, 30000, 50000, "t", S_D4, "assumption", "live capacity of a stockpile"),
    _p("stock_column_frac", 0.30, 0.20, 0.40, "-", S_D4, "assumption", "draw column share of the live stock"),
    _p("stock_exchange_tau_h", 24, 12, 48, "h", S_D4, "assumption", "sides <-> column exchange time"),
    _p("ore_axb_hard_max", 30, 28, 32, "-", S_D5, "assumption", "class T (hard) below"),
    _p("ore_axb_soft_min", 38, 36, 40, "-", S_D5, "assumption", "class M (soft) at or above"),
    _p("ore_early_share", 0.10, 0.05, 0.20, "-", S_D5, "assumption", "'earlier': share of the batch in the feed"),
    _p("ore_expected_share", 0.50, 0.40, 0.60, "-", S_D5, "assumption", "'expected': share in the feed"),
    _p("ore_horizon_h", 12, 12, 12, "h", S_D5, "assumption"),
    _p("ore_check_miss_h", 2, 1, 4, "h", S_D5, "assumption", "hours after the window before a forecast counts as missed"),
    _p("ore_soft_median_min", 45, 30, 60, "min", S_D5, "assumption", "median window of the soft sensor for the check"),
    # ---- queue (section 5; file 19 section 3 A) ----
    _p("q_horizon_h", 12, 12, 12, "h", S_D5 + "; " + S_E19, "assumption", "sliding horizon across the shift boundary"),
    _p("q_samples", 200, 200, 1000, "-", S_E19, "assumption", "arrival, repair and LME samples"),
    _p("q_sigma_ln", 0.4, 0.3, 1.0, "-", S_D5 + "; " + S_REZAEI, "assumption", "lognormal repair time"),
    _p("q_arrive_lo_min", 20, 20, 20, "min", S_D5, "assumption"),
    _p("q_arrive_hi_min", 40, 40, 40, "min", S_D5, "assumption"),
    _p("q_robust_min", 0.70, 0.5, 0.9, "-", S_GOPAL, "assumption", "below: 'order does not matter'"),
    _p("q_defer_p_max", 0.10, 0.05, 0.20, "-", S_E19, "assumption", "'can wait' only if P(stock ends before repair) <= this"),
    _p("q_band1_min", 3, 3, 3, "min", S_HSE, "analog", "time-to-consequence bands <3 / 3-15 / 15-60 / >60"),
    _p("q_band2_min", 15, 15, 15, "min", S_HSE, "analog"),
    _p("q_band3_min", 60, 60, 60, "min", S_HSE, "analog"),
    _p("q_snooze_h", 1.0, 0.5, 2.0, "h", S_D5, "assumption", "'disagree' silences the advice for this long"),
    _p("q_issue_keep_h", 2.0, 1.0, 4.0, "h", S_D5, "assumption", "resolved issue thing deleted after this (as batches)"),
    _p("q_max_enum", 5, 3, 6, "-", S_E19, "assumption", "enumerate all orders up to this many issues"),
    _p("rep_crusher_h", 3, 2, 6, "h", S_D7, "assumption", "median repair after arrival; P90 5 h"),
    _p("rep_lube_trip_h", 3, 2, 6, "h", S_D7, "assumption", "lube sensor and trip circuit check"),
    _p("rep_dose_h", 0.5, 0.3, 0.8, "h", S_D7, "assumption", "collector flowmeter"),
    _p("rep_cyclone_h", 1.0, 0.5, 2.0, "h", S_D5, "assumption", "clogged cyclone"),
    _p("rep_pebble_h", 2.0, 1.0, 4.0, "h", S_D5, "assumption"),
    _p("rep_ball_h", 4.0, 2.0, 8.0, "h", S_D5, "assumption"),
    _p("rep_sag_h", 4.0, 2.0, 8.0, "h", S_D5, "assumption"),
    _p("rep_conveyor_h", 2.0, 1.0, 4.0, "h", S_D5, "assumption"),
    _p("rep_filter_h", 1.0, 0.5, 2.0, "h", S_D4, "assumption", "cloth change"),
    _p("rep_grid_h", 2.0, 1.0, 4.0, "h", S_D7, "assumption", "grid restriction length"),
    _p("rep_decision_h", 0.5, 0.25, 1.0, "h", S_D5, "assumption", "a role decides (blend, dispatch), no crew"),
    _p("rep_train_h", 6.0, 3.0, 12.0, "h", S_D4, "assumption", "concentrate stock: next train"),
    _p("rep_water_h", 3.0, 1.0, 6.0, "h", S_D5, "assumption", "repair of a return-water pipeline leak (crew-water)"),
    _p("water_usd_m3", 0.30, 0.10, 1.00, "USD/m3", S_D5, "assumption", "fresh water price (same as the model)"),
    _p("shed_feeder_mw", 15.0, 0.0, 20.0, "MW", S_D7, "assumption",
       "category-2 feeder of the other load: sheds without copper loss (same as the model)"),
    _p("pebble_stop_loss_frac", 0.08, 0.06, 0.10, "-", S_LIHIR, "analog", "t/h loss while the pebble crusher stands"),
    _p("ball_stop_loss_frac", 0.50, 0.3, 0.5, "-", S_D4, "calc", "one ball mill: 1925 of 3853 t/h"),
    _p("shift_start_h", 8, 6, 9, "h", S_D4, "assumption", "shifts start 08:00 and 20:00"),
    # ---- silent overspends (energy, reagents, water), handover, escalation
    _p("power_usd_mwh", 16.0 / 500.0 * 1000.0, 25.0, 60.0, "USD/MWh", S_TARIFF + "; KZT/USD 500 (assumption)", "calc",
       "16 KZT/kWh / 500 KZT per USD = 32 USD/MWh (VAT not stated)"),
    _p("sag_limited_frac", 0.97, 0.95, 0.99, "-", S_D5, "assumption",
       "the SAG is the bottleneck (t/h lost to more kWh/t) when it draws at least this share of its setpoint"),
    _p("sag_energy_lit_pct", 5.84, 5.84, 5.84, "%", S_PINTO, "analog",
       "reference only, shown as literature: what control took off E at another plant"),
    _p("reagent_usd_kg", 2.0, 1.5, 3.5, "USD/kg", S_D5, "assumption",
       "collector (xanthate) price: no Aktogay contract published"),
    _p("reagent_min_frac", 0.10, 0.05, 0.20, "-", S_D5, "assumption",
       "tank against flowmeter above this share is an overdose (with z >= reagent_min_z)"),
    _p("reagent_min_z", 3.0, 2.0, 4.0, "-", S_D5, "assumption", "excess over the load-cell noise of two readings"),
    _p("tank_sigma_t", 0.008, 0.004, 0.02, "t", S_D4, "assumption", "load cells of the collector day tank (as the model)"),
    _p("reagent_ref_gt", 43, 43, 43, "g/t", S_VAZIFEH, "analog",
       "Sungun plant collectors 22 + 21 g/t against a 23 g/t lab optimum: reference only, not our setpoint"),
    _p("reagent_ref_lab_gt", 23, 23, 23, "g/t", S_VAZIFEH, "analog", "Sungun lab optimum 12 + 11 g/t: reference only"),
    _p("leak_min_m3h", 150, 50, 300, "m3/h", S_D5 + "; " + S_KUJAWA, "assumption",
       "water balance residual above this is named a leak (noise of the totalizers about 15 m3/h)"),
    _p("esc_after_min", 15, 10, 30, "min", S_D5, "assumption", "not arrived by ETA + this: remind or call the next one"),
    _p("remind_eta_min", 10, 5, 20, "min", S_D5, "assumption", "expected arrival after a reminder (as the model)"),
    _p("handover_am_h", 7.5, 7.0, 8.0, "h", S_D5 + "; " + S_PLOCHER, "assumption", "handover sheet before the 08:00 shift"),
    _p("handover_pm_h", 19.5, 19.0, 20.0, "h", S_D5 + "; " + S_PLOCHER, "assumption", "handover sheet before the 20:00 shift"),
    # ---- features 1-9, 14, 15 (22.10.2026): hourly tariff, winter, grind, concentrate grade, grinding media, dust
    _p("tariff_kzt_kwh_mean", 16.0, 16.0, 27.0, "KZT/kWh", S_TARIFF, "fact", "mean price (same row as the model)"),
    _p("tariff_night_mult", 0.70, 0.5, 1.0, "-", "structure of the zonal tariff not confirmed (KEGOC page 16 not opened: "
       "certificate error)", "assumption", "night price against the day price before normalising the day to the mean"),
    _p("tariff_day_mult", 1.00, 1.0, 1.0, "-", "same", "assumption", "day price (reference)"),
    _p("tariff_peak_mult", 1.40, 1.0, 2.0, "-", "same", "assumption", "evening peak price against the day price"),
    _p("tariff_night_from_h", 23, 20, 24, "h", "same", "assumption", "night band starts"),
    _p("tariff_night_to_h", 7, 5, 9, "h", "same", "assumption", "night band ends"),
    _p("tariff_peak_from_h", 18, 16, 20, "h", "same", "assumption", "peak band starts"),
    _p("tariff_peak_to_h", 22, 20, 24, "h", "same", "assumption", "peak band ends"),
    _p("winter_water_mult", 1.5, 1.0, 3.0, "-", "Bozshakol TSF, ATC Williams (analog): decant water recovery in winter "
       "below -10 C for more than three months a year", "assumption",
       "winter: the price of a water trouble (more fresh water, heating, ice) against summer"),
    _p("winter_repair_mult", 1.5, 1.0, 2.5, "-", "same", "assumption", "winter: repair of a water trouble takes longer (frost)"),
    _p("winter_freeze_air_c", -10, -30, 0, "degC", "same: -10 C", "analog", "below this air temperature pipes freeze"),
    _p("p80_alarm_um", 15, 8, 30, "um", S_D4, "assumption",
       "measured P80 above the flotation reference (180 um) by this much is a grind trouble (analyser noise 5 um)"),
    _p("conc_norm_pct", 22.5, 20.0, 25.0, "% Cu", S_COMMO + "; the Kazakhstan contract minimum is not found", "assumption",
       "concentrate grade norm of the buyer; the line gives 24.3 % Cu, 23 % with one ball mill"),
    _p("conc_penalty_usd_dmt_pp", 25.0, 5.0, 60.0, "USD/dmt/pp", S_COMMO, "assumption",
       "buyer deduction per dry tonne of concentrate per percentage point below the norm (extra treatment charge and freight "
       "of the diluted mass); no contract published"),
    _p("conc_window_min", 60, 30, 120, "min", S_D5, "assumption", "mean of the concentrate analyser over this window"),
    _p("ball_norm_gt", 600, 300, 1000, "g/t", "no Aktogay figure published (analog, order of magnitude)", "assumption",
       "norm of grinding media consumption (same row as the model)"),
    _p("ball_usd_kg", 1.2, 0.8, 2.0, "USD/kg", "no contract published", "assumption", "price of grinding balls"),
    _p("ball_over_min_frac", 0.08, 0.05, 0.20, "-", S_D5, "assumption",
       "consumption above the norm by this share (mean of the window) is an overuse: a deviation, not a trouble"),
    _p("ball_window_min", 60, 30, 180, "min", S_D5, "assumption", "mean of the scale reading over this window"),
    _p("dust_wind_ms", 10.0, 6.0, 14.0, "m/s", "wind threshold of beach dusting is not found", "assumption",
       "wind above this over a dry beach lifts dust"),
    _p("dust_dry_pct", 60.0, 30.0, 90.0, "%", "same", "assumption", "dry beach share above this"),
    _p("rep_dust_h", 2.0, 1.0, 6.0, "h", S_D5, "assumption", "wetting the beach, moving the discharge to wet sections"),
    _p("dust_pm10_max_mg_m3", 0.3, 0.3, 0.3, "mg/m3", "order of the Ministry of Health RK no. DSM-70 of 02.08.2022 "
       "(text not read: the file has no text layer)", "assumption", "maximum single PM10 limit, shown for scale"),
    _p("permit_ref", 63, 63, 63, "-", S_MIR, "fact", "item of the Safety Rules for processing plants: work inside a mill by permit"),
    _p("review_min_fork_usd", 50.0, 10.0, 500.0, "USD", S_D5, "assumption",
       "a call that costs less than this against the best order is not a mistake (as the order test of the queue)"),
    _p("shift_h", 12, 12, 12, "h", S_OVOS + " p. 26", "project"),
)


class Prm(dict):
    """Parameter values by key; copy(**overrides) gives a changed copy."""

    def copy(self, **overrides) -> "Prm":
        p = Prm(self)
        for k, v in overrides.items():
            if k not in p:
                raise KeyError(k)
            p[k] = float(v)
        return p


def default() -> Prm:
    return Prm({p.key: p.value for p in PARAMS})


def check() -> list[str]:
    """Consistency of the table: unique keys, value within range, known label."""
    problems = []
    seen = set()
    for p in PARAMS:
        if p.key in seen:
            problems.append(f"{p.key}: duplicate")
        seen.add(p.key)
        if not (p.min - 1e-9 <= p.value <= p.max + 1e-9):
            problems.append(f"{p.key}: {p.value} outside [{p.min}, {p.max}]")
        if p.label not in LABELS:
            problems.append(f"{p.key}: label {p.label}")
        if not p.source:
            problems.append(f"{p.key}: no source")
    return problems


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    problems = check()
    if "--md" in argv:
        rows = ["| key | value | min | max | unit | label | source | note |", "|---|---|---|---|---|---|---|---|"]
        for p in PARAMS:
            rows.append(f"| {p.key} | {p.value:.6g} | {p.min:.6g} | {p.max:.6g} | {p.unit} | {p.label} | "
                        f"{p.source} | {p.note} |")
        print("\n".join(rows))
    for pr in problems:
        print("NOT OK " + pr)
    if not problems:
        print(f"ok: {len(PARAMS)} parameters")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
