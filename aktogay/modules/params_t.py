"""Rows of the analysis modules for tier T (24.10.2026): thresholds and prices of eight slow equipment troubles.

Plain tuples (key, value, min, max, unit, source, label, note); modules/params.py makes Param rows of them. The modules never import
the simulator, so the numbers repeat the simulator rows (sim/params_t.py) with the same sources and labels: a threshold of a
site is set here, the size of an effect is only the module's estimate of the price.
"""
from __future__ import annotations

S_GMD = ("ABB, Remote diagnostic services for gearless mill drives, p. 18: 'a lower limit of 12.5 mm could be defined', trends with "
         "'predefined alarm and trip limits' (example in the text, numeric limits are not published)")
S_ZK = "Zimroz, Krol, Failure analysis of belt conveyor systems, Gornictwo 36, 2009 (no temperature thresholds); PPI CRP 047-01 p. 1 (3 % a year: warranty assumption)"
S_AND = "ANDRITZ MPC for SAG mills and flotation circuits, p. 10 (levels swing for up to 2 h); Valmet 29.09.2026 (qualitative)"
S_OUT = "Outotec, Thickening technologies 2011, p. 10 (alarm, then motor trip; no numbers); 911Metallurgist example 40 % / 80 % (not a norm); BCM NewsWire 17.10.2014 (Oyu Tolgoi, about 60 % throughput)"
S_MET = "Metso Larox PF brochure p. 4 (cloth change 'as little as 30 minutes', best case), Larox PF services brochure p. 8 (cloths blind)"
S_WEIR = "Weir Warman AH brochure p. 7 and Technical Bulletin 36 p. 3 (case studies); ISO 10816-7 s.1 excludes slurry pumps, its zones are not used"
S_VIMS = "Peterson CAT 793F Gauge/Indicators (analog of the 793D, VIMS); KAZ Minerals AR 2020 p. 61 (793D, 236 t); only the principle 'a threshold with a time delay'"
S_EXC = "Hitachi EX3600-6 brochure KS-EN056T p. 7 (track tension by accumulators, travel stops automatically at a preset pressure)"

ROWS = [
    ("wt_gmd_gap_alert_mm", 12.5, 8, 18, "mm", S_GMD, "analog", "alert limit of the air gap: the 12.5 mm of the ABB example, set per site"),
    ("wt_gmd_fail_h", 4, 1, 12, "h", S_GMD, "assumption", "hours from the alert to the trip of the drive if nobody acts"),
    ("wt_gmd_repair_h", 12, 4, 48, "h", S_GMD, "assumption", "the SAG stands this long after the trip"),
    ("rep_gmd_h", 4, 1, 12, "h", S_GMD, "assumption", "check and re-setting of the air gap by the drive service"),
    ("wt_idler_temp_alert_c", 85, 60, 110, "degC", S_ZK, "assumption", "alert limit of the idler bearing temperature (no published threshold)"),
    ("wt_idler_fail_h", 6, 1, 24, "h", S_ZK, "assumption", "hours from the alert to the stop of the belt"),
    ("rep_idler_h", 1.5, 0.5, 4, "h", S_ZK, "assumption", "change of an idler by the conveyor crew"),
    ("wt_idler_rate_yr", 0.03, 0.01, 0.10, "1/yr", S_ZK, "assumption", "expected share of idler bearings failing a year: the maker's warranty assumption"),
    ("wt_froth_swing_alert_pct", 8, 4, 15, "%", S_AND, "assumption", "alert limit of the level swing of the flotation cells"),
    ("wt_froth_swing_ok_pct", 2, 1, 4, "%", S_AND, "assumption", "level swing with the loop in order"),
    ("wt_froth_pp", 1.2, 0.3, 3, "pp", S_AND, "assumption", "recovery lost at the alert level of the swing"),
    ("rep_froth_h", 1.0, 0.3, 3, "h", S_AND, "assumption", "retuning of the level loop by the I&C technician"),
    ("wt_rake_torque_alert_pct", 40, 30, 60, "%", S_OUT, "analog", "alarm torque of the rake: 40 % of the design torque in the 911Metallurgist example"),
    ("wt_rake_torque_crit_pct", 80, 60, 95, "%", S_OUT, "analog", "lift / stop torque: 80 % in the same example"),
    ("wt_rake_fail_h", 4, 1, 12, "h", S_OUT, "assumption", "hours from the alarm to buried rakes"),
    ("wt_rake_q_frac", 0.60, 0.4, 0.9, "-", S_OUT, "analog", "throughput kept while a thickener is repaired: about 60 % at Oyu Tolgoi"),
    ("wt_rake_repair_h", 24, 6, 72, "h", S_OUT, "assumption", "repair of buried rakes (the length is not published)"),
    ("rep_rake_h", 2, 0.5, 6, "h", S_OUT, "assumption", "lifting the rakes and cutting the feed density"),
    ("wt_cloth_cycle_alert_pct", 125, 110, 160, "%", S_MET, "assumption", "alert limit of the filtration cycle time against a new cloth"),
    ("wt_cloth_cycle_crit_pct", 160, 130, 250, "%", S_MET, "assumption", "cycle time with a blind cloth"),
    ("rep_cloth_h", 0.5, 0.5, 4, "h", S_MET, "analog", "cloth changeover: 30 minutes is the best case of the maker"),
    ("wt_slurry_head_alert_pct", 90, 80, 97, "%", S_WEIR, "assumption", "alert limit of the discharge pressure of the cyclone feed pump"),
    ("wt_slurry_head_crit_pct", 75, 50, 90, "%", S_WEIR, "assumption", "discharge pressure with a worn impeller"),
    ("wt_slurry_q_frac", 0.30, 0.1, 0.5, "-", S_WEIR, "assumption", "share of the line feed lost at the critical pressure"),
    ("wt_slurry_life_h", 2000, 1300, 7800, "h", S_WEIR, "analog", "impeller life in the Weir case studies (not a norm)"),
    ("rep_slurry_h", 4, 1, 12, "h", S_WEIR, "assumption", "impeller change or sump level correction"),
    ("wt_brake_oil_alert_c", 115, 95, 140, "degC", S_VIMS, "assumption", "alert limit of the brake oil temperature of the truck"),
    ("wt_brake_hold_min", 10, 2, 30, "min", S_VIMS, "assumption", "the alert comes after the temperature stays above the limit this long (a threshold with a time delay)"),
    ("wt_brake_fail_h", 1.5, 0.5, 6, "h", S_VIMS, "assumption", "hours from the alert to taking the truck off the haul"),
    ("wt_brake_repair_h", 8, 2, 24, "h", S_VIMS, "assumption", "the truck stands this long after it was taken off"),
    ("rep_brake_h", 3, 1, 8, "h", S_VIMS, "assumption", "inspection and cooling of the brakes by the shift mechanic"),
    ("wt_track_press_alert_pct", 90, 70, 98, "%", S_EXC, "assumption", "alert limit of the track tension pressure, % of the preset auto-stop level"),
    ("wt_track_fail_h", 3, 1, 12, "h", S_EXC, "assumption", "hours from the alert to the auto-stop of the travel"),
    ("wt_track_repair_h", 6, 1, 24, "h", S_EXC, "assumption", "the shovel stands this long after the auto-stop"),
    ("rep_track_h", 2, 0.5, 6, "h", S_EXC, "assumption", "release and setting of the track tension"),
]
