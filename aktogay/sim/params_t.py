"""Parameter rows and feature rules of tier T (24.10.2026): eight slow equipment troubles of the plant and the pit.

The rows are plain tuples (key, value, min, max, unit, source, label, note); sim/params.py turns them into the table rows
before it builds TABLE, and merges FEATURES into FEATURE_RULES. Sources are those marked confirmed in
gaps/facts_round2.md and gaps/SOURCES_thresholds.md; where a source names the risk and not the number, the number is an
assumption and the label says so. The table of the CAT 797F/793F 'Data & System Events' (Scribd, confidential) is NOT used.
"""
from __future__ import annotations

S_ABB_GMD = ("ABB, Remote diagnostic services for gearless mill drives, p. 18: 'a lower limit of 12.5 mm could be defined' for the "
             "air gap, trends with 'predefined alarm and trip limits' (opened 24.10.2026); 12.5 mm is an example in the text, not "
             "a setpoint, numeric alarm/trip limits are not published: https://library.e.abb.com/public/"
             "3b41eb5173848571c125793d00572de5/REMOTE%20DIAGNOSTIC%20SERVICES%20FOR%20GEARLESS%20MILL%20DRIVES.pdf")
S_ZIMROZ = ("Zimroz R., Krol R., Failure analysis of belt conveyor systems for condition monitoring purposes, Gornictwo, Studia i "
            "Materialy no. 36, 2009 (opened 24.10.2026): failures of rollers, drums, gearboxes and the diagnostic methods; no "
            "bearing temperature thresholds: https://www.miningscience.pwr.edu.pl/pdf-59825-3376?filename=3376.pdf")
S_PPI = ("Precision Pulley and Idler, CRP 047-01, p. 1: 'expected to have an average annual failure rate of 3%' - a warranty "
         "assumption of the maker, not field statistics: https://www.ppi-global.com/userdocs/literature/ppi/documents/"
         "crp_047-01_bearingterms.pdf")
S_ANDRITZ = ("ANDRITZ, MPC for SAG mills and flotation circuits, p. 10: with PID control the cell levels 'swing wildly' for up to "
             "2 h after a disturbance: https://www.andritz.com/resource/blob/14766/39b32881f5cf79564ab492e33b47d549/"
             "aa-automation-mpc-sag-mills-flotation-circuits-data.pdf; Valmet, 29.09.2026: flotation performance is highly "
             "sensitive to level fluctuations (qualitative, no numbers): https://www.valmet.com/insights/blogs/flow-control/"
             "2026/maximizing-mineral-recovery-why-stability-is-the-foundation-of-flotation-performance/")
S_OUTOTEC = ("Outotec, Thickening technologies 2011, p. 10: rakes lift automatically on drive pressure, 'an alarm and motor trip at "
             "a higher pressure set point', the drive 'never exceeds the design torque rating' (no numeric set points): "
             "https://d3pcsg2wjq9izr.cloudfront.net/files/40011/download/332960/low_res_Outotec_thickening_18022011.pdf")
S_911 = ("911Metallurgist (training blog, not an OEM norm): alarm at 40 % torque, automatic rake lift / drive stop at 80 %, danger of "
         "'rakes being buried': https://www.911metallurgist.com/blog/mill-feed-thickener/ ; "
         "https://www.911metallurgist.com/blog/thickener-torque-rakes-drive/")
S_OYU = ("BCM NewsWire no. 347, 17.10.2014 (secondary publication): damaged rakes of one of two tailings thickeners at Oyu Tolgoi, "
         "the concentrator ran at about 60 % throughput during the repair: https://www.slideshare.net/slideshow/"
         "17102014-newswire-issue-347/58257500")
S_METSO_F = ("Metso Larox PF brochure, PDF p. 4: cloth changeover 'as little as 30 minutes' with two technicians (best case); Metso "
             "Larox PF services brochure, PDF p. 8: 'filter cloths blind and limit performance': "
             "https://www.processcontrolscorp.com/wp-content/uploads/Metso-Larox-PF-Filter-Brochure-06-08-2026.pdf ; "
             "https://www.metso.com/globalassets/ebook/brochure-larox-pf-services-en-4401.pdf")
S_WEIR = ("Weir Minerals Warman AH brochure, PDF p. 7 (case: NPSHa 3.16 m, NPSHr 3.30 m, 'Is pump cavitating? Yes'); Technical "
          "Bulletin 36, PDF p. 3: impeller life 1 300 -> 2 000 h (gold, NZ), 4 200 -> 7 800 h (bauxite slurry, alumina refinery) - "
          "case studies of a vendor, not typical values, not Aktogay: https://www.global.weir/globalassets/resources/product-pdfs/"
          "warman/warman-ah-pumps-brochure.pdf ; https://www.global.weir/globalassets/resources/product-pdfs/warman/"
          "warman-pumps---wrt-impeller-and-throatbush-combination---technical-bulletin-36.pdf. ISO 10816-7:2009 s.1 (p. 2) excludes "
          "'solids handling, slurry and submersible pumps': its vibration zones are NOT applied to slurry pumps")
S_VIMS = ("Peterson CAT, 793F Tier 4, Standard Equipment, Gauge/Indicators: transmission fluid, brake oil, torque converter oil and "
          "engine coolant temperature, VIMS message centre (analog of the 793F: https://www.petersoncat.com/products/new/"
          "mining-trucks/793f-tier-4); Aktogay runs the 793D, 236 t payload with a lightweight tray (KAZ Minerals AR 2020, p. 61: "
          "https://www.kazminerals.com/media/22033/kaz-minerals-ar-2020.pdf). Only the principle 'a threshold with a time delay' "
          "is taken from the maker's event system; no temperature numbers are used")
S_EX3600 = ("Hitachi EX3600-6 brochure KS-EN056T, p. 7: track tension by nitrogen accumulators, 'Travel is automatically stopped if "
            "accumulator pressure exceeds a preset level' (the preset level is not published): "
            "https://hitachicm.com.au/wp-content/uploads/2021/05/EX3600-6_KS-EN056T-small.pdf")
S_OURS = "our rounding"
S_SITE = "setting of the site (set from its own regulations)"

ROWS = [
    # ---- gmd: air gap of the gearless mill drive of the SAG (ABB remote diagnostics)
    ("w_gmd_gap_ok_mm", 20, 15, 30, "mm", S_ABB_GMD, "assumption", "healthy air gap reading of the drive; the nominal gap is not published"),
    ("w_gmd_gap_alert_mm", 12.5, 8, 18, "mm", S_ABB_GMD, "analog",
     "example lower limit of the air gap from the ABB text (example, not an OEM setpoint); a site sets its own alarm limit"),
    ("w_gmd_gap_crit_mm", 9, 5, 12, "mm", S_ABB_GMD, "assumption", "air gap at which the protection trips the drive (trip limits are not published)"),
    ("w_gmd_rise_h", 3, 1, 8, "h", S_ABB_GMD, "assumption", "hours from the start of the deviation to the alert limit"),
    ("w_gmd_fail_h", 4, 1, 12, "h", S_ABB_GMD, "assumption", "hours from the alert limit to the trip if nobody acts"),
    ("w_gmd_fix_h", 4, 1, 12, "h", S_ABB_GMD, "assumption", "check and re-setting of the gap by the drive service after arrival"),
    ("w_gmd_derate", 0.10, 0.0, 0.25, "-", S_ABB_GMD, "assumption", "share of the SAG feed lost while the gap closes (power held back by the drive)"),
    ("w_gmd_repair_h", 12, 4, 48, "h", S_ABB_GMD, "assumption", "the SAG stands this long after the trip if nobody was called before"),
    # ---- idler: bearing of a conveyor idler overheats (fire risk)
    ("w_idler_temp_ok_c", 45, 30, 60, "degC", S_ZIMROZ, "assumption", "bearing temperature of a healthy idler in operation (thermal camera / sensor)"),
    ("w_idler_temp_alert_c", 85, 60, 110, "degC", S_ZIMROZ, "assumption", "alert limit of the bearing temperature (no published threshold; set per site)"),
    ("w_idler_temp_crit_c", 120, 90, 160, "degC", S_ZIMROZ, "assumption", "temperature at which the belt is stopped by the fire protection (assumption)"),
    ("w_idler_rise_h", 4, 1, 12, "h", S_ZIMROZ, "assumption", "hours from the start of the heating to the alert limit"),
    ("w_idler_fail_h", 6, 1, 24, "h", S_ZIMROZ, "assumption", "hours from the alert to the stop of the belt if the idler is not changed"),
    ("w_idler_fix_h", 1.5, 0.5, 4, "h", S_ZIMROZ, "assumption", "change of an idler by the conveyor crew after arrival"),
    ("w_idler_rate_yr", 0.03, 0.01, 0.10, "1/yr", S_PPI, "assumption",
     "expected share of idler bearings failing per year: the maker's warranty assumption, not field statistics"),
    # ---- froth: oscillation of the flotation cell level
    ("w_froth_swing_ok_pct", 2, 1, 4, "%", S_ANDRITZ, "assumption", "swing of the cell level (peak to peak, % of the controlled span) with the loop in order"),
    ("w_froth_swing_alert_pct", 8, 4, 15, "%", S_ANDRITZ, "assumption", "alert limit of the level swing (no published number; set per site)"),
    ("w_froth_rise_h", 1.0, 0.5, 2.0, "h", S_ANDRITZ, "analog", "the levels 'swing wildly' for up to 2 h after a disturbance (ANDRITZ); hours to the alert limit"),
    ("w_froth_pp", 1.2, 0.3, 3.0, "pp", S_ANDRITZ, "assumption", "recovery lost at the alert level of swing (Valmet: sensitive to level swings, no number)"),
    ("w_froth_fix_h", 1.0, 0.3, 3.0, "h", S_ANDRITZ, "assumption", "retuning of the level loop / valve check by the I&C technician after arrival"),
    # ---- rake: torque of the thickener rake
    ("w_rake_torque_ok_pct", 25, 10, 35, "%", S_911, "assumption", "rake torque in normal operation, % of the design torque"),
    ("w_rake_torque_alert_pct", 40, 30, 60, "%", S_911, "analog", "alarm torque: 40 % in the 911Metallurgist example (not a norm); set per thickener"),
    ("w_rake_torque_crit_pct", 80, 60, 95, "%", S_911, "analog",
     "automatic lift / stop of the drive: 80 % in the 911Metallurgist example; Outotec states the architecture (alarm, then trip), no numbers"),
    ("w_rake_rise_h", 3, 1, 8, "h", S_OUTOTEC, "assumption", "hours from the start of the torque growth to the alarm"),
    ("w_rake_fail_h", 4, 1, 12, "h", S_OUTOTEC, "assumption", "hours from the alarm to buried rakes if the feed density is not cut"),
    ("w_rake_q_frac", 0.60, 0.4, 0.9, "-", S_OYU, "analog", "throughput kept while a tailings thickener is repaired (about 60 % at Oyu Tolgoi, 2014)"),
    ("w_rake_fix_h", 2, 0.5, 6, "h", S_OUTOTEC, "assumption", "lifting the rakes and cutting the feed density after arrival"),
    ("w_rake_repair_h", 24, 6, 72, "h", S_OYU, "assumption", "repair of buried rakes if nobody was called before (the length is not published)"),
    # ---- cloth: blinding or damage of the filter cloth
    ("w_cloth_cycle_ok_pct", 100, 100, 100, "%", S_METSO_F, "calc", "filtration cycle time with a new cloth = 100 %"),
    ("w_cloth_cycle_alert_pct", 125, 110, 160, "%", S_METSO_F, "assumption", "alert limit of the cycle time against a new cloth"),
    ("w_cloth_cycle_crit_pct", 160, 130, 250, "%", S_METSO_F, "assumption", "cycle time with a blind cloth: the capacity of the press is 100 / this value"),
    ("w_cloth_rise_h", 4, 2, 24, "h", S_METSO_F, "assumption", "hours from the start of blinding to the alert limit"),
    ("w_cloth_fail_h", 6, 2, 48, "h", S_METSO_F, "assumption", "hours from the alert limit to the blind cloth"),
    ("w_cloth_fix_h", 0.5, 0.5, 4, "h", S_METSO_F, "analog", "changeover of a cloth after arrival: 30 minutes is the best case of the maker"),
    # ---- slurry: cavitation / worn impeller of the cyclone feed pump
    ("w_slurry_head_ok_pct", 100, 100, 100, "%", S_WEIR, "calc", "discharge pressure of the pump = 100 % of normal"),
    ("w_slurry_head_alert_pct", 90, 80, 97, "%", S_WEIR, "assumption", "alert limit of the discharge pressure (no vibration zones of ISO 10816 for slurry pumps)"),
    ("w_slurry_head_crit_pct", 75, 50, 90, "%", S_WEIR, "assumption", "discharge pressure with a badly worn impeller or heavy cavitation"),
    ("w_slurry_rise_h", 5, 1, 24, "h", S_WEIR, "assumption", "hours from the start of the loss of head to the alert limit"),
    ("w_slurry_fail_h", 4, 1, 24, "h", S_WEIR, "assumption", "hours from the alert limit to the critical head"),
    ("w_slurry_q_frac", 0.30, 0.1, 0.5, "-", S_WEIR, "assumption", "share of the line feed lost at the critical head (cyclone feed falls)"),
    ("w_slurry_fix_h", 4, 1, 12, "h", S_WEIR, "assumption", "impeller change or sump level correction after arrival"),
    ("w_slurry_life_h", 2000, 1300, 7800, "h", S_WEIR, "analog", "impeller life in the Weir case studies (1 300 -> 2 000 h gold, 4 200 -> 7 800 h bauxite); not a norm"),
    # ---- brake: brake / transmission oil temperature of the CAT 793D (VIMS)
    ("w_brake_oil_ok_c", 90, 60, 110, "degC", S_VIMS, "assumption", "brake oil temperature of a loaded truck in normal haul"),
    ("w_brake_oil_alert_c", 115, 95, 140, "degC", S_VIMS, "assumption", "alert limit with a time delay (set from the maker's regulations of the fleet)"),
    ("w_brake_oil_crit_c", 135, 110, 170, "degC", S_VIMS, "assumption", "temperature at which the truck is taken off the haul"),
    ("w_brake_rise_h", 2, 0.5, 6, "h", S_VIMS, "assumption", "hours from the start of the heating to the alert limit"),
    ("w_brake_fail_h", 1.5, 0.5, 6, "h", S_VIMS, "assumption", "hours from the alert limit to taking the truck off if the driver is not stopped"),
    ("w_brake_share", 0.30, 0.0, 0.6, "-", S_VIMS, "assumption", "share of the cycle of this truck lost while it is throttled (the rest of the fleet is unchanged)"),
    ("w_brake_fix_h", 3, 1, 8, "h", S_VIMS, "assumption", "inspection and cooling of the brakes by the shift mechanic after arrival"),
    ("w_brake_repair_h", 8, 2, 24, "h", S_VIMS, "assumption", "truck stands this long after it was taken off if nobody was called before"),
    ("w_brake_payload_t", 236, 236, 236, "t", S_VIMS, "fact", "payload of the Aktogay 793D with a lightweight tray (AR 2020 p. 61)"),
    # ---- track: track tension of the EX3600 (auto-stop of the travel)
    ("w_track_press_ok_pct", 60, 30, 80, "%", S_EX3600, "assumption", "accumulator pressure of the track tension, % of the preset auto-stop level"),
    ("w_track_press_alert_pct", 90, 70, 98, "%", S_EX3600, "assumption", "alert limit before the travel is stopped (the preset level is not published)"),
    ("w_track_press_crit_pct", 100, 100, 100, "%", S_EX3600, "vendor", "the travel stops automatically at the preset level (brochure p. 7), 100 % by definition"),
    ("w_track_rise_h", 4, 1, 12, "h", S_EX3600, "assumption", "hours from the start of the growth to the alert limit"),
    ("w_track_fail_h", 3, 1, 12, "h", S_EX3600, "assumption", "hours from the alert limit to the auto-stop of the travel"),
    ("w_track_fix_h", 2, 0.5, 6, "h", S_EX3600, "assumption", "release and setting of the track tension after arrival"),
    ("w_track_repair_h", 6, 1, 24, "h", S_EX3600, "assumption", "the shovel stands (cannot walk to the next face) this long after the auto-stop if nobody was called before"),
]

# Feature -> rule, per thing type (merged into sim.params.FEATURE_RULES).
FEATURES = {
    "sag": {"gmd_gap_mm": "air gap of the gearless drive, mm (healthy w_gmd_gap_ok_mm)"},
    "conveyor": {"idler_temp_c": "bearing temperature of the hottest idler, degC (thermal scan; healthy w_idler_temp_ok_c)"},
    "flot": {"level_swing_pct": "swing of the cell level, % of the controlled span (healthy w_froth_swing_ok_pct)"},
    "thick": {"rake_torque_pct": "rake torque, % of the design torque (healthy w_rake_torque_ok_pct)"},
    "filter": {"cycle_pct": "filtration cycle time, % of a new cloth (100 = new; blinding raises it)"},
    "cyclones": {"pump_head_pct": "discharge pressure of the cyclone feed pump, % of normal (cavitation, a worn impeller lower it)"},
    "fleet": {"brake_oil_c": "brake oil temperature of the truck HT141 (CAT 793D, VIMS), degC",
              "brake_truck": "bort number of the truck whose brake oil is shown"},
    "exc": {"track_press_pct": "accumulator pressure of the track tension, % of the preset auto-stop level (EX3600-6 only, -1 elsewhere)"},
}
