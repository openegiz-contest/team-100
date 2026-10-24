"""Rows of the what-if levers (control of the MODEL, not of the plant): feed rate of each SAG line, grind P80 target,
collector dose. Imported at the end of the row list of sim/params.py. Levers are off by default; a neutral lever leaves
the model unchanged. Sources: gaps/facts_round2.md, sections "Пороги" (R5), "Реагенты — проверка 24.10.2026" (RG1-RG6).
"""
from __future__ import annotations

from .params import Param

S_LEV = "stand lever (what-if control of the model, not of the plant); bounds are a design choice of the stand"
S_R5 = ("Satbayev University repository (Bozshakol plant, daily data 2022-04.2025, regression), table 2 p. 61 and "
        "tables 4-6 p. 62: -1.95 pp Cu recovery per +10 um P80 (plant model); lab -1.2 pp per 10 um (about -7.3 pp over 60 um): "
        "https://repository.satbayev.university/api/files/ep83fzrdl7c6ztx7jeo3dj51w.pdf")
S_RG1 = ("Putra et al., Rekayasa Material, Manufaktur dan Energi 7(1) 2024, pp. 27-34 (plant scale, PT. X Papua, SIBX 5/10/15 g/t: "
         "Cu recovery does not rise with the dose; gangue recovery 7.5 -> 23 -> 88 %): "
         "https://jurnal.umsu.ac.id/index.php/RMME/article/download/16941/10615")


def _p(key, value, lo, hi, unit, source, label, note=""):
    return Param(key, float(value), float(lo), float(hi), unit, source, label, note, False)


ROWS = [
    _p("lev_feed_min_pct", 80, 80, 80, "%", S_LEV, "assumption", "lever: lowest feed rate of a SAG line, % of the nominal line rate"),
    _p("lev_feed_max_pct", 120, 120, 120, "%", S_LEV, "assumption",
       "lever: highest feed rate of a SAG line, % of the nominal line rate (the power limit, liner wear and the "
       "pebble circuit still bind)"),
    _p("lev_p80_min_um", 160, 160, 160, "um", S_LEV + "; " + S_R5, "assumption", "lever: lowest grind P80 target"),
    _p("lev_p80_max_um", 200, 200, 200, "um", S_LEV + "; " + S_R5, "assumption", "lever: highest grind P80 target"),
    _p("lev_p80_pp_10um", 1.2, 1.2, 1.95, "pp", S_R5, "analog",
       "lever: total Cu recovery per 10 um of P80 around flot_p80_ref_um (finer gains, coarser loses): the lab slope of the "
       "Bozshakol study; the plant regression of the same study is lev_p80_pp_plant_10um"),
    _p("lev_p80_pp_plant_10um", 1.95, 1.95, 1.95, "pp", S_R5, "analog",
       "upper end of the shown range: plant regression of Bozshakol, -1.95 pp per +10 um (shown, not used by the model)"),
    _p("lev_dose_min_gt", 15, 15, 15, "g/t", S_LEV, "assumption", "lever: lowest collector dose"),
    _p("lev_dose_max_gt", 40, 40, 40, "g/t", S_LEV, "assumption", "lever: highest collector dose"),
    _p("lev_dose_conc_pp", 1.0, 0.0, 3.0, "pp", S_RG1, "assumption",
       "lever: concentrate grade lost to dilution at +40 % over the optimum dose (qualitative in the source: gangue "
       "recovery rises with the dose; the size is an assumption)"),
    _p("lev_reagent_usd_t", 2000, 1500, 3500, "USD/t", "price of the collector (same basis as reagent_usd_kg); the Volza page "
       "of PAX export prices 1 770-2 000 USD/t (2023) did not open (403) and is not used as a source", "assumption",
       "lever: collector price for the extra (or saved) reagent of the dose lever"),
]
