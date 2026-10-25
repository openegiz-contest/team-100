"""Parameter rows and feature rules of the oxide chain (25.10.2026): ore to the heap -> heap leach pad -> PLS pond -> solvent
extraction -> electrowinning -> cathode store.

Plain tuples (key, value, min, max, unit, source, label, note); sim/params.py turns them into table rows before TABLE is built
and merges FEATURES into FEATURE_RULES. Sources are those opened and read on 25.10.2026 (the source column). Where no
source names the number, the label is «assumption» and the note says what the number does. The numbers that were fitted on the
quarterly cathode of the reports carry the label «calc» and the note «fitted» (sim/oxide.py calibrate, 2018-2025, forward test 2026H1).
"""
from __future__ import annotations

S_AR15 = ("KAZ Minerals annual report 2015, PDF p. 46: nine heap leach cells of about 1 000 kt each, irrigation cycle about four months, "
          "oxide grade 0.37 %, 'expected 15 kt per annum cathode output': https://www.kazminerals.com/media/2686/kaz-minerals-plc-annual-report-and-accounts-2015.pdf")
S_AR18 = ("KAZ Minerals annual report 2018, PDF p. 36: 'Copper cathode production from oxide material was 25.7 kt in 2018', oxide grade 0.33 %: "
          "https://www.kazminerals.com/media/12383/ka173_book_web_version.pdf")
S_EIA = ("EIA conclusions KZ19VWF00069171 (24.06.2022) and of 26.10.2023, ecoportal.kz LoadFile/18392 p. 2 and LoadFile/35802 pp. 2, 5-6: heap pad "
         "1 486 861 m2, five lifts (13 m each from the second), cathode 'up to 25 thousand t a year', raffinate circulation 1 500 m3/h: "
         "https://ecoportal.kz/Rubric/RubService/LoadFile/35802")
S_PSI = ("PSI Group, project list: 'Aktogay 25 000 TPA SX/EW plant' (2014-2015): https://minedocs.com/19/Aktogay-PSI-Group-Projects-web-site-03122023.pdf")
S_KAZOX = ("KAZ Minerals quarterly production reports 2018-2026, rows 'Oxide ore to leach pads', 'Grade', 'Copper cathode' of the Aktogay table "
           "(sim/data/kaz_oxide_quarterly.csv, URL of each report in the file); Q4 2024 p. 3 and Q4 2025 p. 3 on cold and seasonal efficiency")
S_TENKE = ("Tenke Fungurume electrowinning, SAIMM 2016 (scielo.org.za/scielo.php?script=sci_arttext&pid=S2225-62532016000600004): stainless "
           "cathodes at 430 A/m2, current efficiency 92 % in the plant (analog, another copper-cobalt plant)")
S_CVERDE = ("Cerro Verde SX-EW, 911Metallurgist (solvent-extraction-and-electrowinning-sx-ew): design 184 A/m2 at 88 % current efficiency, "
            "expansion 250 A/m2 at 90 %, operation up to 370 A/m2 (analog)")
S_EA = ("Activation energy of leaching of copper oxide ore and malachite in acid, 26.7 kJ/mol (Scientia Iranica, article 20161) and 33.2 kJ/mol "
        "(Int. J. Miner. Metall. Mater. 2015, 10.1007/s12613-015-1067-1), abstracts read 25.10.2026 (analog, laboratory)")
S_FARADAY = "Faraday's law: m = M I t CE / (z F), M(Cu) = 63.546 g/mol, z = 2, F = 26.8015 Ah/mol (physics, textbook)"
S_ERA5 = "ERA5 (Open-Meteo) monthly air temperature of Aktogay 2018-2025, sim/data/weather_era5.json, CC BY 4.0"
S_OX = "our rounding"

ROWS = [
    # ---- ore to the heap (the facts of the reports, per quarter, are in the file; here only the cut-off)
    ("ox_idle_ore_tph", 100, 20, 400, "t/h", S_KAZOX, "assumption",
     "the stacker counts as idle below this placing rate (2020 Q2: 36 kt in a quarter = 17 t/h); only sets the state of oxfeed-1"),
    # ---- heap leach: kinetics of the cohorts (fitted on the quarterly cathode)
    ("ox_rmax", 0.435, 0.20, 0.90, "-", S_KAZOX, "calc",
     "leachable share of the contained copper (what dissolves on the scale of years; the rest is not leached by the pad); fitted"),
    ("ox_th_d", 548.0, 30.0, 1500.0, "d", S_KAZOX, "calc",
     "time constant of the leaching of a cohort in days at 20 degC (thermal days); fitted. 2020 Q2: 36 kt of fresh ore and 5.4 kt of cathode "
     "from the ore placed earlier (re-irrigation, report of Q2 2020, p. 3) show that most of the cathode comes from old ore"),
    ("ox_ea_app_jmol", 6320, 3000, 35000, "J/mol", S_KAZOX + "; " + S_EA, "calc",
     "apparent activation energy against the AIR temperature; fitted. The laboratory value is 27-33 kJ/mol (analog); the fit gives about a fifth of it, "
     "because the pad is much warmer than the air in winter (raffinate, snow, mass): this is the damping of the pad, not the chemistry"),
    ("ox_heap_tau_d", 8.0, 2.0, 40.0, "d", S_OX, "assumption", "lag of the pad temperature behind the air temperature, days"),
    ("ox_m0_t", 40400, 20000, 200000, "t", S_KAZOX, "calc",
     "leachable copper in the pad on 01.01.2018 (placed before 2018, nothing is published); fitted"),
    ("ox_irr_m3h", 1500, 1200, 1800, "m3/h", S_EIA, "project", "raffinate circulation of the pads (EIA: 'recycling of raffinate 1 500 m3/h')"),
    ("ox_pad_tau_h", 2.0, 0.5, 6.0, "h", S_OX, "assumption", "delay of the solution between the dissolution and the drain of the pad to the PLS pond"),
    # ---- ponds
    ("ox_pls_v_m3", 12000, 6000, 20000, "m3", S_OX, "assumption", "volume of the PLS pond at the level set point (8 h of the flow)"),
    ("ox_pls_vmax_m3", 20000, 15000, 30000, "m3", S_OX, "assumption", "volume at which the PLS pond spills; irrigation is then cut to the SX flow"),
    ("ox_raff_v_m3", 6000, 3000, 12000, "m3", S_OX, "assumption", "volume of the raffinate pond (kept constant, make-up water is not modelled)"),
    ("ox_pond_tau_h", 4.0, 1.0, 12.0, "h", S_OX, "assumption", "time constant of the level control of the PLS pond (the SX feed follows the level)"),
    ("ox_sx_q_cap", 1.25, 1.0, 1.6, "-", S_OX, "assumption", "maximum SX feed flow as a multiple of the irrigation flow"),
    # ---- solvent extraction
    ("ox_sx_eta", 0.95, 0.90, 0.98, "-", "extraction of copper from PLS in two or three stages is usually 90-98 % (not verified against an open source: label assumption)",
     "assumption", "share of the copper of the PLS taken by the organic phase; the rest goes back to the pad with the raffinate"),
    # ---- electrowinning
    ("ox_ew_gpah", 63.546 / (2 * 26.8015), 1.18, 1.19, "g/Ah", S_FARADAY, "calc", "copper deposited per ampere-hour at 100 % current efficiency"),
    ("ox_ew_cells", 72, 40, 120, "-", S_PSI, "assumption",
     "cells of the tankhouse in series; the number is not published, chosen so that 25 kt a year need about 300 A/m2"),
    ("ox_ew_cath_n", 60, 40, 80, "-", S_OX, "assumption", "cathodes per cell"),
    ("ox_ew_cath_m2", 1.0, 0.8, 1.3, "m2", S_OX, "assumption", "area of one face of a cathode; the plate has two faces"),
    ("ox_ew_ce", 0.92, 0.88, 0.95, "-", S_TENKE + "; " + S_CVERDE, "analog", "current efficiency of the tankhouse (Tenke 92 % plant, Cerro Verde 88-90 %)"),
    ("ox_ew_design_kty", 25.0, 15.0, 26.0, "kt/y", S_EIA + "; " + S_PSI + "; " + S_AR18, "project",
     "design cathode of the tankhouse; the EIA says 'up to 25 thousand t a year', 25.7 kt were made in 2018"),
    ("ox_ew_overload", 1.32, 1.0, 1.5, "-", S_TENKE + "; " + S_CVERDE, "assumption",
     "rectifier limit as a multiple of the design current; the reports show quarters above the design (7.6 kt in Q3 2021 = 30 kt a year)"),
    ("ox_ew_v_cell", 2.0, 1.8, 2.4, "V", "cell voltage of copper electrowinning 1.9-2.2 V (not verified against an open source)", "assumption",
     "voltage per cell; with the current efficiency it gives the energy per tonne of cathode"),
    ("ox_ew_el_m3", 400, 150, 800, "m3", S_OX, "assumption", "volume of the electrolyte of the tankhouse"),
    ("ox_ew_el_gl", 45, 35, 55, "g/L", S_OX, "assumption", "copper in the rich electrolyte at the set point"),
    ("ox_ew_emax_frac", 1.30, 1.10, 1.6, "-", S_OX, "assumption", "copper in the electrolyte at which the strip stops, as a multiple of the set point"),
    ("ox_ew_tau_h", 1.0, 0.25, 4.0, "h", S_OX, "assumption", "time constant of the current control (electrolyte inventory back to the set point)"),
    # ---- cathode store and shipping
    ("ox_store_cap_t", 300, 100, 1000, "t", S_OX, "assumption", "cathode store"),
    ("ox_store_high_frac", 0.8, 0.5, 0.95, "-", S_OX, "assumption", "store is HIGH above this share"),
    ("ox_ship_batch_t", 60, 20, 120, "t", S_OX, "assumption", "cathode in a convoy or a wagon load; shipped when the store holds a load (about a day of output)"),
    ("ox_store_t0", 90, 0, 300, "t", S_OX, "assumption", "cathode in the store at the start of a run"),
    ("ox_low_frac", 0.10, 0.05, 0.20, "-", S_OX, "assumption", "sxew-1 is LOW when the cathode is below the expected one by more than this share"),
    # ---- troubles of the chain (scenarios ewtrip and sxcrud)
    ("ox_rect_fix_h", 2.0, 0.5, 8.0, "h", S_OX, "assumption", "restart of a tripped rectifier by the electrician after the arrival"),
    ("ox_rect_auto_h", 8.0, 2.0, 24.0, "h", S_OX, "assumption", "the rectifier is found and restarted by itself this long after the trip if nobody is called"),
    ("ox_crud_ok_cm", 0.5, 0.2, 1.0, "cm", S_OX, "assumption", "crud layer in the settler with the plant in order"),
    ("ox_crud_alert_cm", 3.0, 1.5, 6.0, "cm", S_OX, "assumption", "crud layer at which the operator is told"),
    ("ox_crud_crit_cm", 8.0, 4.0, 15.0, "cm", S_OX, "assumption", "crud layer at which the extraction is at its worst"),
    ("ox_crud_rise_h", 5.0, 1.0, 12.0, "h", S_OX, "assumption", "hours from the normal layer to the alert"),
    ("ox_crud_fail_h", 6.0, 1.0, 12.0, "h", S_OX, "assumption", "hours from the alert to the worst layer"),
    ("ox_crud_fix_h", 3.0, 1.0, 8.0, "h", S_OX, "assumption", "removal of crud (treatment of the organic phase) after the arrival"),
    ("ox_crud_eta_frac", 0.60, 0.3, 0.9, "-", S_OX, "assumption", "extraction as a share of the normal one at the worst layer"),
    ("ox_crud_q_frac", 0.50, 0.2, 0.9, "-", S_OX, "assumption", "SX feed flow that the settler can take, as a share of the normal one, at the worst layer"),
]

FEATURES = {
    "oxfeed": {"state": "NORMAL/IDLE: IDLE while the placing rate is below ox_idle_ore_tph",
               "ore_tph": "oxide ore placed on the pads now, t/h = quarter ore of the reports / hours of the quarter",
               "grade_pct": "copper grade of the placed ore, % (reports)",
               "cu_tph": "contained copper placed, t/h", "quarter_ore_kt": "oxide ore placed in the quarter, kt (reports, kaz_oxide_quarterly.csv)",
               "placed_t_total": "ore placed since the start of the run, t"},
    "leach": {"state": "NORMAL/COLD: COLD while the scenario leachcold lasts (frozen irrigation lines, cold pad)",
              "quarter_cathode_kt": "cathode of the model quarter, kt, from the reports (kaz_quarterly.csv); a date after 2025 takes the same quarter of 2025",
              "level_tph": "quarter cathode / hours of the quarter (reported level, for the comparison with the model)",
              "cold_frac": "share of the irrigation lost while COLD (ox_cold_frac)",
              "irrigation_m3h": "raffinate on the pads, m3/h", "irrigation_pct": "irrigation as % of ox_irr_m3h",
              "heap_temp_c": "temperature of the pad, degC (lagged air temperature)",
              "k_factor": "Arrhenius factor of the rate against 20 degC at the apparent activation energy",
              "leach_cu_tph": "copper dissolved in the pad now, t/h", "leach_exp_tph": "the same with full irrigation (expected)",
              "inventory_cu_t": "leachable copper left in the pad, t", "recovery_pct": "share of the leachable copper placed since 2018 that is already dissolved, %",
              "pls_gl": "copper of the solution leaving the pad, g/L"},
    "plspond": {"state": "NORMAL/HIGH/FULL/LOW by the volume of the PLS pond", "volume_m3": "volume", "level_pct": "volume / ox_pls_vmax_m3, %",
                "pls_gl": "copper in the pond, g/L", "in_m3h": "flow from the pad", "out_m3h": "flow to SX",
                "raff_gl": "copper of the raffinate pond (irrigation solution), g/L", "hours_to_full": "(vmax - volume) / (in - out), -1 when it does not fill"},
    "sx": {"state": "NORMAL/CRUD/DOWN: CRUD above the alert layer of the settler", "feed_m3h": "PLS to SX, m3/h",
           "extraction_pct": "copper taken from the PLS, % (ox_sx_eta x crud and strip limits)", "transfer_cu_tph": "copper moved to the electrolyte, t/h",
           "raff_cu_gl": "copper in the raffinate leaving SX, g/L", "crud_cm": "crud layer in the settler, cm"},
    "ew": {"state": "NORMAL/LIMIT/TRIP: LIMIT at the rectifier limit, TRIP when the rectifier is out",
           "current_ka": "line current, kA", "current_set_ka": "current asked by the control, kA", "voltage_v": "cell voltage, V",
           "current_density_am2": "current density on the cathode faces, A/m2", "cathode_tph": "copper deposited now, t/h (Faraday)",
           "cathode_exp_tph": "expected cathode with the chain in order, t/h", "power_mw": "tankhouse power, MW (inside pow_other_mw)",
           "kwh_t": "energy per tonne of cathode, kWh/t", "electrolyte_cu_t": "copper in the electrolyte, t"},
    "catstore": {"state": "NORMAL/HIGH/FULL", "stock_t": "cathode in the store, t", "in_tph": "cathode in", "shipped_t_total": "shipped since the start, t",
                 "shipments_n": "loads shipped since the start", "hours_to_full": "(capacity - stock) / in, -1 when it does not fill"},
    "sxew": {"state": "NORMAL/LOW: LOW while the cathode is below the expected one by ox_alarm_frac",
             "cathode_tph": "cathode of the tankhouse now, t/h (model, Faraday)",
             "cathode_level_tph": "reported level of the quarter, t/h = quarter cathode of the reports / hours",
             "cathode_t_total": "integrated since the start of the run", "year": "year of the model quarter", "quarter": "quarter (1-4)",
             "model_dev_pct": "expected cathode against the reported level of the quarter, % (the back-test error of the day)"},
}
