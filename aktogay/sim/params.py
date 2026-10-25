"""Single parameter table of the Aktogay concentrator model.

Every number the model uses lives here with value, range, unit, source and
label. Labels:
  fact       - KAZ Minerals reports and company pages, state bodies, market,
               measured site geometry (OpenStreetMap)
  vendor     - equipment vendor or press release about the Aktogay equipment
               (Bradken whitepaper with Aktogay engineers, drive orders)
  project    - line 2 EIA (OVOS 2018) and the OVOS of the reconstruction
  analog     - similar plant (Bozshakol, Touro, Josemaria) or a published form
  assumption - our choice where no data exists
  calc       - derived from other rows (formula given in the note)

A source string names the document, the page where known, and the URL.
Rows with fit=True are adjusted by sim.calib; ParamSet holds per-run values.
Sources checked 18.10.2026 (file 18): the corrections of its section 7 are
applied here; a note says when a number stays an assumption.

Usage:
  from sim.params import default, value
  prm = default()            # ParamSet with table values
  prm["sag_power_sp_mw"]     # -> 26.0
  python -I run.py params --md PARAMETERS.md
"""
from __future__ import annotations

import argparse
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
    fit: bool = False


# ---- source strings: document, page where known, URL ----
S_KAZ25 = ("KAZ Minerals Q4 2025 production report (FY2025), p. 3: "
           "https://www.kazminerals.com/app/uploads/2026/02/Q4-2025-Production-report_FINAL_ENG.pdf")
S_KAZ24 = ("KAZ Minerals Q4 2024 production report (FY2024), p. 3: "
           "https://www.kazminerals.com/media/23240/q4-2024-production-report_final.pdf")
S_KAZ23 = ("KAZ Minerals Q4 2023 production report (FY2023), p. 3: "
           "https://www.kazminerals.com/media/23062/q4-2023-production-report-final.pdf")
S_KAZQ3 = ("KAZ Minerals Q3 2025 production report, p. 3: "
           "https://www.kazminerals.com/app/uploads/2025/12/q3-2025-production-report_final.pdf")
S_KAZQ1_24 = ("KAZ Minerals Q1 2024 production report, p. 3: "
              "https://www.kazminerals.com/media/23119/q1-2024-production-report-final.pdf")
S_KAZQ2_24 = ("KAZ Minerals Q2 2024 production report, p. 3: "
              "https://www.kazminerals.com/media/23193/q2-2024-production-report-final.pdf")
S_KAZQ3_23 = ("KAZ Minerals Q3 2023 production report, p. 3: "
              "https://www.kazminerals.com/media/22980/q3-2023-production-report-final.pdf")
S_KAZQ2_26 = "KAZ Minerals Q2 2026 production report (11.08.2026)"
S_KAZ_EN = ("KAZ Minerals sustainability: energy (2023, 2024): "
            "https://www.kazminerals.com/sustainability/environment/energy/")
S_KAZ_W = ("KAZ Minerals sustainability: water (2023, 2024): "
           "https://www.kazminerals.com/sustainability/environment/water/")
S_KAZ_CO2 = ("KAZ Minerals ESG: climate change (Scope 2, 2024): "
             "https://www.kazminerals.com/esg/environment/climate-change/")
S_BRAD = ("Bradken + KAZ Minerals Aktogay mill optimisation whitepaper, Oct 2021 (line 1): "
          "https://assets.ctfassets.net/ge6w0nvcjafk/1yRwupkiNkxXwbgGj4fjbN/8ab61ff573592af415efecfe05912a04/"
          "Mill_Optimisation_Whitepaper.pdf")
S_OVOS = ("Aktogay line 2 EIA (OVOS) 2018: "
          "https://minedocs.com/19/Aktogai-Sulphide-Concentrator-Expansion-Project-Environmental-Impact-Assessment-2018.pdf")
S_OVOS_RK = ("OVOS 'Reconstruction of concentrators 1 and 2, stage 1' (ecoportal.kz): "
             "https://ecoportal.kz/Rubric/RubService/LoadFile/9406")
S_SITE15 = ("KAZ Minerals site visit presentation 01.06.2015, slide 28 (Bozshakol fleet, analog): "
            "https://www.kazminerals.com/media/2834/site-visit-presentation-vfinal-010615.pdf")
S_BOZ14 = ("KAZ Minerals Projects Update 11.12.2014 (Bozshakol, analog; opened and checked 24.10.2026: p. 12 gyratory crusher "
           "750 kW, 4 186 t/h; p. 13 overland belt 3.8 km, 1.6 m, 4 880 t/h, 3 640 kW; p. 16 SAG; p. 17 ball mill; p. 18 regrind; "
           "p. 19 thickeners; p. 36): https://www.kazminerals.com/media/2828/projects_update_111214.pdf")
S_CAT785 = ("Cat 785C specification sheet: rated payload 136 t; 18 per line in the Bozshakol analog fleet, "
            + S_SITE15)
S_HITACHI = ("Hitachi EX3600-6 shovel, bucket 21-23 m3 (ritchiespecs): "
             "https://www.ritchiespecs.com/model/hitachi-ex3600-6-shovel")
S_VESTI = ("Vesti Semey 06.06.2024, press tour of Aktogay, words of the head of the pit (2 CAT 777, 18 CAT 785, "
           "17 CAT 793; CAT 793 'more than 240 t'; 5 Hitachi excavators 2 700-3 700 t/h; over 500 people and "
           "100 machines per shift in the pit; pit depth up to 230 m): "
           "https://vestisemey.kz/15404/kaz-minerals-aktogay-tsifrovye-i-innovatsionnye-vozmozhnosti-"
           "industrialnogo-proizvodstva.html")
S_IM21 = ("International Mining 25.02.2021, Aktogay expansion (line 2: FLSmidth main equipment, gyratory crusher, "
          "gearless SAG and ball mills, Wemco flotation; thyssenkrupp POLYCOM HPGR 1 061 t/h, 2 x 1 750 kW): "
          "https://im-mining.com/2021/02/25/kaz-minerals-aktogay-expansion-track-first-production-second-"
          "concentrator-set-late-2021/")
S_KURSIV26 = ("Kursiv 09.08.2026: fire at the HPGR section of concentrator 1 at about 12:00 during planned "
              "maintenance, 20 people evacuated, no injuries, concentrator 2 and the oxide complex ran as usual: "
              "https://kz.kursiv.media/2026-08-09/svvo-20-chelovek-evakuirovali-iz-za-chp-na-obogatitelnoi-"
              "fabrike-kaz-minerals/")
S_KAZEQ = ("KAZ Minerals Aktogay LLC 29.02.2024, specification (fire suppression), equipment list with bort numbers "
           "(trucks HT121 785C, HT136-138 785D, HT141 793D; excavators EX01 EX3600, EX51 ZX870, EX53 EX1200; dozers "
           "DZ01 D9R, DZ21-23 D10T, DZ41-43 D375; drills DR01-04 Sandvik D55, DR12 Epiroc D65, DR31 Pit Viper 231; "
           "not exhaustive): https://minedocs.com/33/Kaz-Minerals-equipment-2024.pdf")
S_CATSPEC = ("Caterpillar rated payloads (vendor data, spec sheets not opened in this work): 777 about 90 t, "
             "785 136 t")
S_AT12 = ("AT Mineral Processing 06/2012: gearless drive order for Aktogay, two 22 MW GMDs for two 28 ft ball mills: "
          "https://www.at-minerals.com/en/artikel/at_2012-06_Gearless_mill_drive_order_in_Kazakhstan-1441931.html")
S_JOSE = ("Josemaria FS 2020 (SRK/Fluor, ALS tests), section 13.6.1 p. 82: "
          "https://minedocs.com/20/Josemaria-Resources-Inc-TR-FS-11052020.pdf")
S_TOURO = ("Touro NI 43-101 2018, table 13.11 p. 13-16 (A*b 31.5-55.3, mean 40.4, design P25 34.0): "
           "https://wp-atalaya-mining-2022.s3.eu-west-2.amazonaws.com/media/2022/08/"
           "NI-43-101-Technical-Report-for-Proyecto-Touro.pdf")
S_SMC = (S_TOURO + "; Josemaria FS 2020, section 13.4.1 p. 70 and table 17-1 p. 135 (A*b 23.1-96.2, mean 40.8, "
         "design P25 32.8), section 17.2.2 p. 140 (SAG F80 137 mm): "
         "https://minedocs.com/20/Josemaria-Resources-Inc-TR-FS-11052020.pdf")
S_AUSTIN = ("Austin 1990, 'A mill power equation for SAG mills', Minerals and Metallurgical Processing 7(1), "
            "pp. 57-63 (form; load term (1 - 1.03 J)); secondary: "
            "https://www.911metallurgist.com/blog/ag-sag-grinding-circuit-automatic-control/")
S_LIHIR = ("Lihir, AusIMM Mill Operators 2024 (JKSimMet); not verified, proceedings > 10 MB not opened: "
           "https://www.ausimm.com/globalassets/conferences-and-events/mill-operators-2024/mills-ops-2024-proceedings-v1.pdf")
S_POWELL = ("Powell et al. 2006 'Selection and design of mill liners', p. 14 (direction only: a new liner can lower "
            "t/h noticeably; no numbers): https://911metallurgist.com/wp-content/uploads/2016/06/SAG-Mill-Liner-Design.pdf")
S_MORRELL = ("Morrell, 'Predicting the specific energy of AG/SAG mills and HPGR', eq. 2 p. 5 (E = K F80^a DWi^b, "
             "constants not published), DWi vs A*b p. 3: "
             "https://911metallurgist.com/wp-content/uploads/2016/07/Predicting-SAG-AG-Mill-and-HPGR-Specific-Energy.pdf; "
             "GMG 2021 Morrell method guideline: https://gmggroup.org/wp-content/uploads/2024/07/"
             "GUIDELINE_The-Morrell-Method-to-Determine-the-Efficiency-of-Industrial-Grinding-Circuits_2021-1.pdf")
S_LME = ("Westmetall, LME Cu cash 15.10.2026: "
         "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash")
S_WB = ("World Bank CMO April 2026, table 1 (Cu 2025: 9 947, 2026: 12 000 USD/t): "
        "https://thedocs.worldbank.org/en/doc/f3138644a1e8e2bb631399ae11d6c408-0050012026/related/CMO-April-2026-Forecasts.pdf")
S_TARIFF = ("Zakon.kz 22.07.2026: single purchaser electricity price 13 -> 16 KZT/kWh from 15.07.2026 (VAT not stated): "
            "https://www.zakon.kz/obshestvo/6525551-tarify-na-elektroenergiyu-v-almaty-i-oblasti-planiruyut-povysit-s-20-avgusta.html; "
            "rfc.kz, single purchaser hourly prices July 2026 (14.97-47.81, mean 26.95 KZT/kWh): "
            "https://rfc.kz/ru/single-purchaser-of-electricity/prices-and-rates/")
S_PINTO = ("Pinto et al. 2025, Scientific Reports 15:21398, 'Specific energy reduction in a semi-autogenous grinding "
           "mill circuit by an automatic control system' (Vale, Sossego), Results: 9.29 -> 8.75 kWh/t (-5.84 %), "
           "productivity +1.90 %, 3 months before / after, cascade and feedforward control (literature, a different "
           "plant): https://pmc.ncbi.nlm.nih.gov/articles/PMC12215483/")
S_VAZIFEH = ("Vazifeh, Jorjani, Bagherian 2010, Trans. Nonferrous Met. Soc. China 20:2371-2378, Sungun rougher: plant "
             "means of 90 operating days Z11 22 g/t + AP407 21 g/t, lab optimum 12 + 11 g/t (section 4.4, p. 2377; "
             "analog, laboratory tests): http://www.ysxbcn.com/down/paperDown.aspx?id=30842")
S_KUJAWA = ("Kujawa (Paterson & Cooke), 'Water Recovery in Mining', AIChE 2016 Industrial Water Use and Reuse "
            "Workshop, slide 20: water loss 0.72 / 0.41 / 0.37 / 0.18 m3/t for conventional / thickened / paste / "
            "filtered tailings, worked example of 100 000 t/d (vendor engineering example, context only): "
            "https://www.aiche.org/sites/default/files/files/docs/conferences/3.2_kujawa_final.pdf")
S_KEGOC = ("KEGOC via Zakon.kz, line outage 14.08.2026 (event only): "
           "https://www.zakon.kz/sobytiia/6528118-blekaut-v-kazakhstane-nazvana-prichina.html")
S_ME58 = ("Order of the Ministry of Energy of Kazakhstan No. 58 (emergency control in the grid), items 21-23, 34, 40: "
          "https://zakon.uchet.kz/rus/docs/V1500010552")
S_OSM = ("OpenStreetMap way/773805065, main conveyor crushing -> plant, 2.45 km (Overpass 18.10.2026, "
         "geometry in aktogay/web/static/plan.json), (c) OpenStreetMap contributors, ODbL 1.0: https://www.openstreetmap.org/way/773805065")
S_STOCK = ("911metallurgist, calculating stockpile capacity (live share of a conical pile with bottom reclaim; the 26.5 % is "
           "one geometry with three outlets, an example): "
           "https://www.911metallurgist.com/blog/calculating-stockpile-capacity/; Ferreira and Luz 2022, RSD 11(6), table 2 "
           "(live volume fraction 17.74 / 17.79 %, one outlet, a sand rig): "
           "https://rsdjournal.org/index.php/rsd/article/download/28908/25055/332357")
S_FLS_GYR = "FLSmidth gyratory crushers (TS 60x113 drive up to 1 000 kW): https://fls.com/equipment/crushing/gyratory-crushers"
S_RAPTOR = ("FLSmidth Raptor cone crusher brochure, p. 9 (Raptor 1100: 549-798 t/h): "
            "https://prod.flsmidth.com/globalassets/frontify/2024/9/raptorconecrusher-miningaggregates_brochure_en.pdf")
S_PEK = ("Production environmental control programme (PEK) of KAZ Minerals Aktogay 2023-2024 (ECO AIR, 2023), "
         "114 pp., read 22.10.2026: https://ecoportal.kz/Public/PubHearings/LoadFile/111450")
S_NOAA = ("NOAA/WMO 1991-2020 monthly normals of Aqtogay (station 36619) and Ayagoz via Wikipedia (secondary source; "
          "mean of the window 15 Nov - 15 Mar: Aktogay -9.05, Ayagoz -11.8 degC; January -13.7 / -15.8): "
          "https://en.wikipedia.org/wiki/Aktogay,_East_Kazakhstan_Region")
S_CHILE_BALLS = ("Perez, Villaseca (CODELCO), Opportunities for ferrous alloys used in copper mining, p. 9 (Chile, 2014: "
                 "SAG about 390 g/t, ball mills about 535 g/t, ball price typically 1 250 USD/t); Cyprus Pima 754 g/t "
                 "(911metallurgist, after Bassarear 1980): "
                 "https://assets.niobium.tech/-/media/niobiumtech/attachments-biblioteca-tecnica/"
                 "nt_opportunities-for-ferrous-alloys-used-in-copper-mining.pdf")
S_BULK = ("bulk-online, overland conveyor belt speeds 3.4-6.0 m/s: "
          "https://www.bulk-online.com/sites/default/files/public/old_images/forum/42300.pdf")
S_RME = ("RME mill relining benchmarking scorecard (2-5 % of the year on relines): "
         "https://www.rmeglobal.com/mill-relining-benchmarking-scorecard/")
S_CHINALCO = ("Metso Outotec case study, Minera Chinalco Peru SAG1 mill liner change: planned 96 h, done in 84 h "
              "(14 % faster; vendor page, one mine, no date): "
              "https://www.metso.com/insights/case-studies/mining-and-metals/minera-chinalco-mill-liner-change-with-less-downtime/")
S_AUSENCO_AV = ("Ausenco, Designing Circuits for High Availability (primary crushing target 75 %, lower because of mine "
                "requirements and truck scheduling): https://ausenco.com/assets/documents/Designing-Circuits-for-High-Availability.pdf")
S_LI24 = ("Li 2024 (Chalmers), table 1 p. 37 (SAG pebbles 16-23 % soft, 22-40 % hard ore; ball mill F80 2.2-2.7 mm): "
          "https://research.chalmers.se/publication/542450/file/542450_Fulltext.pdf")
S_911EXP = ("911metallurgist, grinding circuit expansion (mill setpoint 90-95 % of installed power): "
            "https://www.911metallurgist.com/blog/grinding-circuit-expansion/")
S_SAGMILL = "sagmilling.com, drive efficiency (grid to shaft 0.93-0.97): https://sagmilling.com/articles/1/view/?s=1"
S_CYC = ("Multotec cyclones at Ngezi, 12 units with 9 on: "
         "https://africanreview.com/manufacturing/engineering/multotec-supply-mill-classification-cyclones; "
         "CiDRA BI0455, Copperton 10 units, clogging effect qualitative: https://cidra.com/wp-content/uploads/2024/02/BI0455.pdf")
S_VINNETT = ("Vinnett 2022, PPMP 58(5), table 3 (k 0.24-0.35 1/min, tau 25-38 min, k tau 9-13): "
             "https://www.journalssystem.com/ppmp/pdf-152420-77419?filename=A-sensitivity-analysis-of.pdf")
S_AKHM = ("Akhmetova 2024, master thesis, Satbayev University (Aktogay ore, lab): mass pull 7-13 %, oxidised Cu "
          "0-2.94 % of total Cu (p. 25), collector dose table 16: "
          "https://official.satbayev.university/download/document/39545/2024 МАГ Ахметова А.С..pdf")
S_MYRZ = ("Myrzabekova 2021, master thesis, Satbayev University, table 3.3 (Aktogay BWi sample 17.33 kWh/t, f 10.2): "
          "https://official.satbayev.university/download/document/20864/2021 МАГ Мырзабекова К..pdf")
S_SARCH = ("Sarcheshmeh collector dose study, IJCCE (-2 to -4 pp at -40 % collector): "
           "https://www.ijcce.ac.ir/article_249210.html")
S_FREEPORT = ("911metallurgist, column cleaning circuit (Freeport): cleaner stage recovery 96-98 %: "
              "https://www.911metallurgist.com/blog/size-size-effects-flotation-column-cleaning-circuit/")
S_MS2024 = ("Mining Science 31 (2024) 103-118, p. 12 (thickener underflow 60 % typical): "
            "https://dbc.wroc.pl//Content/140049/mining_science_vol31_2024_103_118.pdf")
S_MCLAN = ("McLanahan, filter press cloth change 10-20 min per cloth: "
           "https://www.mclanahan.com/blog/how-the-quickchange-improves-maintenance-planning-for-filter-press-operations")
S_RGUPS = ("RGUPS, freight wagons built in Kazakhstan, p. 3 (wagon 69.5 t): "
           "https://lib.rgups.ru/site/assets/files/6720/gruzovye_vagony_sozdannye_v_kazakhstane.pdf")
S_KRIST = ("Kristjanpoller 2020, p. 7 (truck availability 0.79-0.93, cycle 20-30 min; Chile analog): "
           "https://ein.org.pl/pdf-158944-85231?filename=Equivalent-availability-i.pdf")
S_SPECALOG = ("Caterpillar 793D Specalog AEHQ5600-01, p. 1 and 20 (engine 3516B 1 801 kW gross, gross machine operating weight "
              "383 749 kg, nominal payload 218 t, body raise 20.25 s, power down 17.51 s, float 19.26 s, top speed 54.3 km/h; "
              "the retarding charts on pp. 23-24 are images): https://www.vost-tech.ru/files/catalog/OHT/793d_specalog.pdf")
S_AR20 = ("KAZ Minerals annual report 2020, p. 61 (PDF p. 63), photo caption: 'Aktogay 793D haul truck with lightweight "
          "tray, 236 t payload': https://www.kazminerals.com/media/22033/kaz-minerals-ar-2020.pdf")
S_793F = ("Caterpillar 793F brochure PEDJ0470-01 (2020), p. 5: '12.9 kph / 8 mph on 10% grade' (marketing figure, the speed "
          "of gear 1; 793F, not 793D): https://mujstroj.zeppelin.cz/fileadmin/helios_files/JPG/ToM/OHT/793F/"
          "793F_PEDJ0470-01_Product_Brochure_2020.pdf")
S_MAP = ("stand map web/static/plan.json (OpenStreetMap quarry way/773805067 and crusher way/773805064, ODbL; the ramp "
         "polyline is drawn by us): length of face -> ramp -> crusher, 'расчёт по карте'")
S_AZO = ("AZoMining 20.01.2026, 'Optimizing Slurry Analysis to Maximize Mineral Recovery' (Thermo Fisher, sponsored): six streams "
         "of a concentrator on one analyser, 1 min each, 'total measurement cycle time is 8 minutes': "
         "https://www.azomining.com/Article.aspx?ArticleID=1908")
S_SKOURIES = ("Skouries NI 43-101 July 2011, p. 63 (17.3 coarse ore stockpile): 'live capacity of 21,000 t, about 33% of total volume'; "
              "three apron feeders (two duty, one standby); Constancia (Ausenco): 'design live capacity of 16 hours': "
              "https://www.eldoradogold.com/sites/eldorado-gold/files/eldorado/assets/growth-projects/skouries/skouries-technical-report-july-2011.pdf")
S_SILVA = ("Silva and Boisvert 2014 (block grade error: Cu about 9 % monthly to 18 % per block): "
           "https://www.scielo.org.za/scielo.php?pid=S2225-62532014000300017&script=sci_arttext")
S_MILHDBK = ("reliabilityanalytics.com, maintainability theory (lognormal repair times; MIL-HDBK-338 example sigma_ln "
             "about 1.1): https://reliabilityanalytics.com/blog/2011/09/03/maintainability-theory/")
S_IPB = ("repository.ipb.ac.id, crusher MTTR about 5.5 h (weak source): "
         "https://repository.ipb.ac.id/handle/123456789/174360?show=full")
S_METSO_AN = ("Metso Courier 5X/6X SL analyser brochure, p. 12 (sigma 1-6 %, cycle 12-16 min): "
              "https://www.metso.com/globalassets/portfolio/brochure-courier-5x-6x-sl-online-analyzers-4924-11-23-en-mng.pdf")
S_REMES = ("Remes et al., Minerals Engineering 2007, p. 3 (accuracy of on-stream analysis 'can vary between 1% and 10%'; a zero-mean random "
           "error, not a bias, p. 8): https://skoge.folk.ntnu.no/prost/proceedings/npc07/TKK/TKK01.pdf")
S_METSO_WP = ("Metso whitepaper, p. 6 (lab composite every 6 h, analyser 5-6 min): "
              "https://metso.com/contentassets/fef70fdec0d64edb8c7809bc86a0bbbf/whitepaper")
S_GOST_LAB = "GOST R 56856-2016, table 1 (lab Cu assay: about 7 % relative at 0.35 % Cu; tails 5-17 %)"
S_OIML = "OIML R 50-1 (1997), table 1 (belt weighers, class 1): https://www.oiml.org/en/files/pdf_r/r050-1-e97.pdf"
S_IEC = "IEC 62053-22 (electricity meters, class 0.2S / 0.5S)"
S_PSI = "Metso PSI 500i particle size analyser (vendor accuracy)"
S_NIST = ("NIST e-Handbook 6.3.2 (control chart rules; 2 consecutive cycles is stricter than WECO 2 of 3): "
          "https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc32.htm")
S_EH = ("Endress+Hauser, in-situ flowmeter verification (minutes): "
        "https://www.wwdmag.com/home/article/10933751/endresshauser-inc-how-to-perform-in-situ-verification-of-a-flowmeter")
S_SCSE = ("SMC Testing, SCSE note p. 2 (blend by specific energy, not by A*b): "
          "https://www.smctesting.com/documents/A_New_Way_of_Representing_A_and_b_Parameters_from_JK_Drop-Weight_and_SMC_Tests_The_SCSE.pdf")
S_JK = ("Kojovic et al., SAG 2019 p. 3; SAGDesign ore hardness comparison p. 5 (JK classes: A*b 38-43 moderately hard): "
        "https://sagdesign.com/wp-content/uploads/2021/01/14.-Comparison-of-Ore-Hardness-Measurements.pdf")
S_TAILS = "settled copper tailings, dry density 1.4-1.5 t/m3 (literature range; no Aktogay figure)"
S_KAZ_WINTER = ("KAZ Minerals ESG, Enhancing winter safety at Aktogay (opened 23.10.2026, page undated): winter conditions "
                "increase the risk of road accidents, snowstorms and strong winds; no thresholds or lengths: "
                "https://kazminerals.com/esg/enhancing-winter-safety-at-aktogay/")
S_ERA5 = ("ERA5 hourly reanalysis (ECMWF / Copernicus C3S) through the Open-Meteo Historical Weather API, 2018-2025, 70 128 h at "
          "46.95 N 79.93 E, our calculation of 24.10.2026 (VALIDATION.md 10.2; label: fact ERA5/Open-Meteo, calculation); data licence "
          "CC BY 4.0, 'Weather data by Open-Meteo.com': https://open-meteo.com/en/licence")
S_HITACHI36 = ("Hitachi EX3600-6 brochure KS-EN056T, p. 11 (contamination sensor alerts the operator; Global e-Service needs the "
               "optional DTU and a contract, p. 11): https://hitachicm.com.au/wp-content/uploads/2021/05/EX3600-6_KS-EN056T-small.pdf")
S_ABDU = ("Abduazizov et al., Mining of Mineral Deposits 20(2), 2026, p. 31 and 33 (working fluid contamination is about 70 % of "
          "hydraulic failures; MTTR 57.45 h belongs to the PC3000, not to the EX3600): "
          "https://pdfs.semanticscholar.org/e654/bd7b9089010efdfa4ebdfd2990cd4ab289c0.pdf")
S_CIDRA_KEN = ("CiDRA with Rio Tinto Kennecott, Comminution 2014, p. 12: closed-loop grinding control prevents ball mill overload "
               "and hydrocyclone roping: https://cidra.com/wp-content/uploads/2024/02/BI0614.pdf")
S_CIDRA_CEN = ("CiDRA, Centinela (97 000 t/day), p. 3: heavy roping of battery 3 stopped one rougher flotation line for about 6 h "
               "(May 2014): https://cidra.com/wp-content/uploads/2024/02/BI0566.pdf")
S_ABB_PH = ("ABB application note, pH/ORP measurement in copper flotation, p. 3: abrasion by slurry particles and build-up of lime "
            "scale are the hazards of the sensor (vendor requirement, no failure statistics): "
            "https://library.e.abb.com/public/ce5cb93e495f4eafb1b60f98308a7203/AD_ANAINST_001-EN%20Rev%20A.pdf")
S_METSO_HPGR = ("Metso blog, Why skewing is not beneficial for your HPGR, 31.01.2022 (read through WebFetch, not checked against "
                "the HTML): feed size segregation gives an uneven pressure profile and skew; tramp metal is not 'seen' by the HPGR "
                "pressure; the HPGR of line 2 is a thyssenkrupp POLYCOM, so this is an analog (another maker): "
                "https://metso.com/insights/blog/mining-and-metals/why-skewing-is-not-beneficial-for-your-hpgr")
S_METSO_MANTLE = ("Metso, La Caridad mine increases availability of primary crushers (10.03.2023): a mantle change takes about 60 h, "
                  "75 000-100 000 t of ore are not crushed in that time (another mine, a smaller crusher): "
                  "https://www.metso.com/insights/case-studies/mining-and-metals/la-caridad-mine-increases-availability-of-primary-crushers/")
S_NOV1 = ("Human-in-the-loop experiment on a laboratory mock-up plant (arXiv 2509.06657v1, p. 23 expert = more than one year at "
          "the plant; p. 29 detection 261.798 s experts vs 433.982 s novices; p. 30 SD 56.155 vs 105.556 s; recovery time "
          "the same, 30.716 vs 30.612 s; analog, not a mine): https://arxiv.org/pdf/2509.06657v1")
S_NOV2 = ("NRC SHEEP / HuREX data, CNS simulator, 36 licensed operators of Korean NPPs against 36 student operators "
          "(ML24151A634, table 7 p. 14, table 8 p. 15, sample p. 10): SI-diagnosis EOC students 1/20, operators 0/17; "
          "RP-step omission students 14/2958, operators 3/3038; IG-indicator EOC 19/1754 against 10/1786; "
          "https://www.nrc.gov/docs/ML2415/ML24151A634.pdf (analog, a different industry, tiny samples)")
S_NOV3 = ("THERP table 20-16 as in EPRI 'Task 12: Fire HRA' slides (NRC ML19212A732, slide 47): stress modifier skilled / "
          "novice optimum 1/1, moderately high 2/4, extremely high 5/10 (the slides, not NUREG/CR-1278 itself): "
          "https://www.nrc.gov/docs/ML1921/ML19212A732.pdf")
S_OX = ("KAZ Minerals Q4 2024 production report, p. 3: cathode -25 % against Q3 2024 'due to lower volumes of ore placed on the leach pads and colder conditions' (https://minedocs.com/28/Kaz_Minerals-QR-Q42024.pdf); Q4 2025 report p. 3: the cathode line 'continued to leach at a seasonally lower efficiency', cathode 15.3 kt of the 225.7 kt of Aktogay in 2025 ("
          "https://www.kazminerals.com/app/uploads/2026/02/Q4-2025-Production-report_FINAL_ENG.pdf); quarterly cathode of all reports: sim/data/kaz_quarterly.csv")
S_D2 = "design section 2"
S_D3 = "design section 3"
S_D4 = "design section 4"
S_D5 = "design section 5"
S_D6 = "design section 6"
S_D7 = "design section 7"
S_D9 = "design section 9"
S_D10 = "design section 10"


def _p(key, value, lo, hi, unit, source, label, note="", fit=False):
    return Param(key, float(value), float(lo), float(hi), unit, source, label, note, fit)


# Derived base numbers (labelled calc in the table below).
_LINE_TPH = 62.1e6 / 2.0 / 8059.0                    # t/h per line, 2025
_SAG_E = 26000.0 / _LINE_TPH                         # kWh/t
_DWI = 100.0 * 2.66 / 35.0                           # kWh/m3
_SAG_K = _SAG_E / (130.0 ** 0.2 * _DWI ** 0.8)       # Morrell scale
_RINF0 = 87.2 / 97.0 / (1.0 - math.exp(-3.5)) * 100.0  # rougher R_inf, %
_FEED25 = 220.3e3 / (62.1e6 * 0.872) * 100.0         # % Cu: Cu in concentrate / (ore x recovery), 2025
_GRADE_PP_LN_MAX = 100.0 - 87.2                      # pp per ln(g / g0) if tails stayed constant: 100 - R0
_PORE_W = 1.0 / 1.45 - 1.0 / 2.66                    # m3 pore water per t settled tails solids
_FEED_END_MM = 20.41 * 9.96                          # feed-end wear between intermediate relines, mm
_H24 = 366 * 24.0                                    # h in 2024
_MILL_GRID_MW = 2 * (26.0 + 2 * 20.5) / 0.96         # both lines, grid side
_CC_MW = 2 * 0.75 + 2 * 3.64                         # crushers + conveyors
# Per running line: line 2 EIA electricity 827 514 MWh/yr over 8 059 h, minus mills (grid), crusher, conveyor.
_LINE_AUX_MW = 827514.0 / 8059.0 - (26.0 + 2 * 20.5) / 0.96 - 0.75 - 3.64
_OTHER_MW = (2033e3 - 58.3e6 * (_MILL_GRID_MW + _CC_MW + 2 * _LINE_AUX_MW) / (2 * _LINE_TPH)) / _H24
_Y24 = 0.0043 * 0.879 / 0.243                        # concentrate yield of 2024, t per t ore
_CONC_MOIST_T = _Y24 * 0.08 / 0.92                   # m3 per t ore
_EVAP = (34.852e6 - 58.3e6 * (_PORE_W * (1.0 - _Y24) + _CONC_MOIST_T)) / _H24
_RELINE_Q = (7697.0 / 8077.0 - 1.0) * 100.0                # line 2 tonnes Q3 vs Q2 2025, %
_RELINE_ALL_H = 2208.0 - 7697.0 / 8077.0 * 2184.0         # whole Q3/Q2 rate drop as hours of Q3
# Ball charge alone (ore ground out) over the mixed charge at J0 25 %, Jb 12 %, per m3 of charge;
# voids 0.4, steel 7.8 t/m3, ore 2.66 t/m3, slurry 1.8 t/m3 in the voids of the working charge.
_BALL_DENS = 0.6 * 7.8 / ((12 * (0.6 * 7.8 + 0.4 * 1.8) + 13 * (0.6 * 2.66 + 0.4 * 1.8)) / 25)
# Ore stockpile: OVOS working volume 163 kt; the live part over the bottom reclaim is a share of it.
_STOCK_TOTAL_T = 163000.0
_STOCK_LIVE_FRAC = 40000.0 / _STOCK_TOTAL_T          # 0.245: the 40 kt live stock of design sections 3 and 7
_CONV_KM = 2.504                                     # main conveyor of concentrator 2, PEK p. 18 (OSM: 2.45 km)
_CO2_T_MWH = 2308e3 / (13.06e9 / 3.6e3)              # Scope 2 kt CO2 / group electricity PJ -> MWh, 2024
_FRESH_HI = 73512.92 / (25.0e6 / 8059.0 * 24.0)      # OVOS-18 fresh water m3/d over the design t/d

_ROWS = [
    # ---------------- economics ----------------
    _p("econ_cu_price_usd_t", 14539, 10000, 15000, "USD/t", S_LME + "; range: " + S_WB, "fact",
       "LME cash 15.10.2026; range 10 000-15 000 USD/t spans WB CMO 2025-2026 and design section 5"),
    _p("econ_payable_frac", 0.955, 0.95, 0.96, "-", S_KAZ25 + "; Q4 2024 p. 3", "calc",
       "calculated from the reports: payable / contained copper 0.9549 (2023), 0.9552 (2024), 0.9551 (2025); matches the rule "
       "'grade less 1 unit' at 22.2 % Cu (hypothesis, the contracts are not published)"),
    _p("econ_power_kzt_kwh", 16, 16, 27, "KZT/kWh", S_TARIFF, "fact",
       "single purchaser price by press (Zakon.kz 22.07.2026: 13 -> 16 from 15.07.2026, VAT not stated); "
       "range up to the July 2026 hourly mean 26.95 on rfc.kz"),
    _p("econ_kzt_per_usd", 500, 450, 560, "KZT/USD", S_D5, "assumption"),
    _p("econ_water_usd_m3", 0.30, 0.10, 1.00, "USD/m3", S_D5, "assumption"),
    _p("econ_co2_t_mwh", round(_CO2_T_MWH, 2), 0.6, 0.8, "t/MWh", S_KAZ_EN + "; " + S_KAZ_CO2, "calc",
       "grid CO2 factor: group Scope 2 2 308 kt CO2 / group electricity 13.06 PJ (3 628 GWh), 2024 = 0.636, "
       "rounded to 0.64; range 0.6-0.8"),

    # ---------------- calendar, time, run control ----------------
    _p("cal_hours_run", 8059, 7800, 8300, "h/yr", S_OVOS + ", p. 26", "project",
       "0.92 x 8760 design hours; 3 102 t/h = 25 Mt / 8 059 h is a calc, OVOS itself gives 3 100-3 600 t/h"),
    _p("cal_avail", 0.92, 0.85, 0.97, "-", S_OVOS + ", p. 25", "project",
       "mill line availability; fitted per year so annual tonnes match the report", fit=True),
    _p("cal_line_tph", _LINE_TPH, 3500, 4200, "t/h", S_D4, "calc",
       "62.1 Mt / 2 lines / 8059 h; per line by the report: 30.9 and 31.2 Mt / 8 059 design hours = 3 835 and "
       "3 870 t/h (tonnes are fact, hours are design)"),
    _p("cal_shift_h", 12, 12, 12, "h", S_OVOS + ", p. 26", "project", "2 shifts x 12 h"),
    _p("cal_shift_start_h", 8, 6, 9, "h", S_D2, "assumption", "shifts start 08:00 and 20:00"),
    _p("cal_step_live_min", 1, 1, 1, "min", S_D2, "assumption"),
    _p("cal_step_calib_min", 10, 5, 30, "min", S_D4, "assumption"),
    _p("cal_checkpoint_min", 5, 5, 5, "min", S_D2, "assumption", "module tact and publish checkpoint"),
    _p("cal_warmup_from_h", 6, 6, 6, "h", S_D2, "assumption"),
    _p("cal_warmup_to_h", 8, 8, 8, "h", S_D2, "assumption"),
    _p("cal_seed", 42, 1, 1000, "-", S_D2, "assumption"),
    _p("cal_batch_keep_h", 2, 1, 4, "h", S_D3, "assumption", "batch thing deleted 2 h after DONE"),
    _p("cal_stop_h_lo", 4, 2, 8, "h", S_D4, "assumption", "calib: line stop length, uniform low"),
    _p("cal_stop_h_hi", 24, 12, 48, "h", S_D4, "assumption", "calib: line stop length, uniform high"),

    # ---------------- report targets (calibration and checks) ----------------
    _p("tgt_2025_ore_mt", 62.1, 62.1, 62.1, "Mt", S_KAZ25, "fact", "sulphide ore processed"),
    _p("tgt_2025_grade_pct", 0.41, 0.41, 0.41, "% Cu", S_KAZ25, "fact", "rounded to 0.01 %"),
    _p("tgt_2025_feed_pct", _FEED25, 0.405, 0.415, "% Cu", S_KAZ25, "calc",
       "220.3 kt / (62.1 Mt x 87.2 %): model feed grade of the 2025 fit, inside the rounding of 0.41"),
    _p("tgt_2025_rec_pct", 87.2, 87.2, 87.2, "%", S_KAZ25, "fact"),
    _p("tgt_2025_cu_kt", 220.3, 220.3, 220.3, "kt", S_KAZ25, "fact", "copper in concentrate"),
    _p("tgt_2025_payable_kt", 210.4, 210.4, 210.4, "kt", S_KAZ25, "fact", "payable copper in concentrate"),
    _p("tgt_2024_ore_mt", 58.3, 58.3, 58.3, "Mt", S_KAZ24, "fact", "input of the 2024 fit and check"),
    _p("tgt_2024_grade_pct", 0.43, 0.43, 0.43, "% Cu", S_KAZ24, "fact", "rounded to 0.01 %; check input"),
    _p("tgt_2024_rec_pct", 87.9, 87.9, 87.9, "%", S_KAZ24, "fact"),
    _p("tgt_2024_cu_kt", 221.0, 221.0, 221.0, "kt", S_KAZ24, "fact"),
    _p("tgt_2024_energy_gwh", 2033, 2033, 2033, "GWh", S_KAZ_EN, "fact",
       "electricity only, whole site (7.32 PJ); fit target"),
    _p("tgt_2024_water_mm3", 34.852, 34.852, 34.852, "Mm3", S_KAZ_W, "fact", "water intake; fit target"),
    _p("tgt_2023_energy_gwh", 1950, 1950, 1950, "GWh", S_KAZ_EN, "fact",
       "7.02 PJ; gives the 2023 ore of the 2023 check"),
    _p("tgt_2023_water_mm3", 32.803, 32.803, 32.803, "Mm3", S_KAZ_W, "fact"),
    _p("tgt_2023_grade_pct", 0.50, 0.50, 0.50, "% Cu", S_KAZ23, "fact",
       "rounded to 0.01 %; check input (0.52 % was the first half of 2023 only)"),
    _p("tgt_2023_rec_pct", 87.7, 87.7, 87.7, "%", S_KAZ23, "fact"),
    _p("tgt_q3_2025_ore_kt", 15859, 15859, 15859, "kt", S_KAZQ3, "fact"),
    _p("tgt_q3_2025_grade_pct", 0.40, 0.40, 0.40, "% Cu", S_KAZQ3, "fact"),
    _p("tgt_q3_2025_rec_pct", 86.1, 86.1, 86.1, "%", S_KAZQ3, "fact"),
    _p("tgt_q2_2025_rec_pct", 89.1, 89.1, 89.1, "%", S_KAZQ3, "fact", "grade of Q2 2025 not in sources yet"),
    _p("tgt_q2_2025_l2_kt", 8077, 8077, 8077, "kt", S_KAZQ3, "fact", "line 2 ore processed, Q2 2025"),
    _p("tgt_q3_2025_l2_kt", 7697, 7697, 7697, "kt", S_KAZQ3, "fact",
       "line 2, Q3 2025; the report names a SAG reline at Sulphide 2 in August"),
    _p("tgt_q2_2025_hours", 2184, 2184, 2184, "h", S_D4, "calc", "91 d x 24 h"),
    _p("tgt_q3_2025_hours", 2208, 2208, 2208, "h", S_D4, "calc", "92 d x 24 h"),
    _p("tgt_reline_q_pct", _RELINE_Q, _RELINE_Q, _RELINE_Q, "%", S_KAZQ3, "calc",
       "line 2 tonnes Q3 vs Q2 2025: 7 697 / 8 077 - 1 = -4.7 %; as hours about -127 h of Q3"),
    _p("tgt_q2_2026_ore_mt", 16.18, 16.18, 16.18, "Mt", S_KAZQ2_26, "fact", "no recovery line in 2026 reports"),
    _p("tgt_q2_2026_grade_pct", 0.41, 0.41, 0.41, "% Cu", S_KAZQ2_26, "fact"),

    # ---------------- check tolerances ----------------
    _p("tol_rec_pp", 0.5, 0.5, 0.5, "pp", S_D4, "assumption"),
    _p("tol_cu_frac", 0.02, 0.02, 0.02, "-", S_D4, "assumption"),
    _p("tol_energy_frac", 0.03, 0.03, 0.03, "-", S_D4, "assumption"),
    _p("tol_water_frac", 0.05, 0.05, 0.05, "-", S_D4, "assumption"),
    _p("tol_reline_pp", 1.5, 1.5, 1.5, "pp", S_D4, "assumption"),
    _p("tol_balance_pct", 0.5, 0.5, 0.5, "%", S_D10, "assumption", "balance residual limit"),

    # ---------------- pit, blocks, fleet ----------------
    _p("pit_block_t", 15000, 10000, 30000, "t", S_D3 + "; " + S_OVOS_RK + ", p. 35", "assumption",
       "one block = one ore batch; 3.3-3.9 h of one crusher at its OVOS rate"),
    _p("pit_plan_h", 12, 8, 24, "h", S_D3, "assumption", "batch created when its block enters the plan"),
    _p("pit_exc_count", 3, 3, 4, "-", S_VESTI + "; " + S_SITE15, "assumption",
       "excavators on ore: 3 of the 5 Hitachi of the pit (5 is fact, the split is ours; Bozshakol 2015 had 4)"),
    _p("pit_exc_bucket_m3", 21, 21, 23, "m3", S_HITACHI, "vendor", "Hitachi EX3600-6, 21-23 m3"),
    _p("pit_exc_tph", 2600, 2500, 3000, "t/h", S_OVOS_RK + ", p. 35", "calc",
       "nominal ore rate per excavator: 2 crushers x 3 805-4 566 t/h over 3 excavators = 2 500-3 000 t/h"),
    _p("pit_exc_max_tph", 3000, 2600, 3400, "t/h", S_D4 + "; " + S_VESTI, "assumption",
       "regulator headroom per excavator; inside the 2 700-3 700 t/h stated for the Hitachi of the pit"),
    _p("pit_haul_min", 30, 20, 45, "min", S_D4, "assumption", "excavator to crusher, no single trucks"),
    _p("fleet_trucks", 37, 30, 40, "-", S_VESTI, "fact",
       "2 CAT 777 + 18 CAT 785 + 17 CAT 793 at 06.06.2024 (was 36 by the Bozshakol analog, " + S_SITE15 + ")"),
    _p("fleet_payload_t", 136, 136, 136, "t", S_CAT785, "vendor", "Cat 785 rated payload (not 140)"),
    _p("fleet_kio", 0.85, 0.75, 0.93, "-", S_D4 + "; " + S_KRIST, "assumption",
       "truck availability; 0.79-0.93 at a Chilean mine (analog)"),
    _p("fleet_trip_min", 30, 20, 40, "min", S_D4 + "; " + S_KRIST, "calc",
       "mean cycle of the two ore routes = the reference of the 2025 fit; since 24.10.2026 a result of sim/haul.py "
       "(fleet_speed_eff is calibrated to it), not an input; analog 20-30 min"),
    _p("fleet_redraw_h", 1, 1, 1, "h", S_D4, "assumption", "each truck ready with fleet_kio, drawn hourly"),
    _p("fleet_n_777", 2, 2, 2, "-", S_VESTI, "fact", "CAT 777 trucks at 06.06.2024; the 2026 fleet is not confirmed"),
    _p("fleet_n_785", 18, 18, 18, "-", S_VESTI, "fact", "CAT 785 trucks at 06.06.2024"),
    _p("fleet_n_793", 17, 17, 17, "-", S_VESTI, "fact", "CAT 793 trucks at 06.06.2024"),
    _p("fleet_payload_777_t", 90, 85, 95, "t", S_CATSPEC, "vendor", "CAT 777 rated payload; not verified here"),
    _p("fleet_payload_793_t", 236, 218, 240, "t", S_AR20, "fact",
       "Aktogay 793D with lightweight tray, 236 t payload (annual report 2020, p. 61); the press tour's 'more than 240 t' "
       "is the 240 short tons (218 t) of the Specalog rating; 240 t was used before 24.10.2026"),
    _p("fleet_ore_785", 6, 0, 18, "-", S_D4, "assumption",
       "CAT 785 on ore (3 per line), the rest on waste: with the 17 CAT 793 the ore haul per cycle is "
       "17 x 240 + 6 x 136 = 4 896 t, the former aggregate of 36 x 136 t"),
    _p("fleet_ore_793", 17, 0, 17, "-", S_D4, "assumption", "all CAT 793 on ore (9 line 1, 8 line 2)"),
    _p("fleet_load_min", 3, 2, 5, "min", S_D4, "assumption", "truck cycle: loading at the face"),
    _p("fleet_queue_min", 2, 0, 5, "min", S_D4, "assumption", "truck cycle: queue at the crusher or dump; Bozshakol (neighbour mine of KAZ Minerals, Hexagon, im-mining.com 28.03.2025): waiting at the shovel 3-5 min fell to 1-1.5 min, below 2: label kept"),
    _p("fleet_body_raise_s", 20.25, 20.25, 20.25, "s", S_SPECALOG, "vendor", "793D body raise, high idle, p. 20"),
    _p("fleet_body_lower_s", 17.51, 17.51, 17.51, "s", S_SPECALOG, "vendor",
       "793D body power down, high idle, p. 20 (float lower 19.26 s)"),
    _p("fleet_spot_min", 0.5, 0.2, 1.0, "min", S_D4, "assumption", "positioning at the crusher pocket or the dump, before the raise"),
    _p("fleet_nom_payload_793_t", 218, 218, 218, "t", S_SPECALOG, "vendor", "793D nominal payload (240 short tons)"),
    _p("fleet_gmw_793_t", 383.749, 383.749, 383.749, "t", S_SPECALOG, "vendor",
       "793D gross machine operating weight, 846 000 lb; empty mass = this - nominal payload"),
    _p("fleet_power_793_kw", 1801, 1801, 1801, "kW", S_SPECALOG, "vendor", "3516B HD EUI gross; net 1 743 kW"),
    _p("fleet_vmax_kmh", 54.3, 54.3, 54.3, "km/h", S_SPECALOG, "vendor", "793D top speed loaded, gear 6 (gear 1: 11.8 km/h)"),
    _p("fleet_eta_drive", 0.85, 0.75, 0.90, "-", S_793F, "assumption",
       "share of the gross engine power at the wheels on a ramp; 0.89 reproduces 12.9 km/h on 10 % of the 793F brochure "
       "(rolling resistance 3 %), 0.85 kept for the lower net power"),
    _p("fleet_rr", 0.03, 0.02, 0.05, "-", S_D4, "assumption", "rolling resistance of the haul road, fraction of the weight; the 793D Specalog p. 29 rule (total resistance = grade % + 1 % per 10 kg/t) fixes the form, not the 3 % of the Aktogay road: label kept"),
    _p("fleet_v_empty_kmh", 35.0, 25.0, 45.0, "km/h", S_SPECALOG, "assumption",
       "empty return speed down the ramp (retarder and speed limit); the 793D top speed is 54.3 km/h"),
    _p("fleet_speed_eff", 0.516, 0.35, 1.0, "-", S_D4, "assumption",
       "the ONE calibrated factor: real average speed over the calculated speed (curves, acceleration, speed limits, dust, "
       "waiting for the shovel); value from sim/haul.calibrate so that the mean ore cycle is the 30 min of the 2025 fit"),
    _p("fleet_ramp_km_1", 2.216, 2.216, 2.216, "km", S_MAP, "calc",
       "face-1 -> ramp-1 (1.946 km) -> crusher-1, polyline of the stand map; the straight line is 2.128 km"),
    _p("fleet_ramp_km_2", 2.700, 2.700, 2.700, "km", S_MAP, "calc",
       "face-2 -> ramp-2 (2.411 km) -> crusher-2; the straight line is 2.591 km"),
    _p("fleet_waste_km", 1.515, 1.515, 1.515, "km", S_MAP, "calc", "face-4 -> road-dump, polyline of the stand map"),
    _p("fleet_rise_m_1", 120, 100, 160, "m", S_D4 + "; bench 10 m: " + S_PEK, "assumption",
       "ore face of line 1 on bench 12 (site file, assumption) x 10 m; the pit is up to 230 m deep (fact)"),
    _p("fleet_rise_m_2", 110, 90, 150, "m", S_D4 + "; bench 10 m: " + S_PEK, "assumption", "ore face of line 2 on bench 11 x 10 m"),
    _p("fleet_rise_m_w", 65, 40, 100, "m", S_D4 + "; bench 10 m: " + S_PEK, "assumption", "stripping faces on benches 6-7 x 10 m"),
    _p("pit_exc_waste_count", 2, 0, 2, "-", S_VESTI, "calc",
       "5 Hitachi excavators (fact) - 3 on ore = 2 on stripping (the split is an assumption)"),
    _p("pit_exc_waste_tph", 3000, 2700, 3700, "t/h", S_VESTI, "fact",
       "stripping excavator rate, inside the 2 700-3 700 t/h stated per excavator; held to the waste haul"),
    _p("pit_road_detour", 1.4, 1.1, 2.0, "-", S_D4, "assumption",
       "truck cycle multiplier while the ramp of a line is closed (detour); haul length is not published"),
    _p("pit_road_close_h", 2, 0.5, 8, "h", S_D4, "assumption", "scenario road:N, ramp of line N closed"),
    _p("scen_pitstop_h", 8, 2, 24, "h", S_D4 + "; " + S_PEK + ", p. 10 (ore stockpile 163 kt = 2 days of grinding)",
       "assumption",
       "scenario pitstop: every ore excavator stands this long (blast clearance, weather or a fault; the cause and the "
       "length are not published); the stockpile then carries the plant"),
    _p("conv_repair_h", 2.0, 1.0, 4.0, "h", S_D5, "assumption",
       "median repair of a stopped main conveyor after the crew arrives (scenario conveyor:N); no Aktogay figure. Analogs verified "
       "24.10.2026 (copper mine, Peru, 3 years of history, ucsm.edu.pe thesis p. 60-61): damaged belt 1.44 h (5 events) and 1.69 h "
       "(13 events, primary crushing belt), drive 2.62 h (5), idlers and frame 0.70 h (10), mean over the 37 events 1.5 h; vendor "
       "case of a belt cover repair 'back up and running within two hours' (Devcon). 2.0 h sits inside the analog range; the "
       "value stays an assumption because modules/scenarios.py mirrors this row"),
    _p("pit_drill_holes_shift", 8, 4, 20, "1/shift", S_D4 + "; " + S_KAZEQ, "assumption",
       "blast holes per rig and shift; 6 rigs x 8 x pit_drill_t_hole about equals the dig of a shift "
       "(ore 7 706 + waste about 3 000 t/h); rigs and models are fact, the rate is ours"),
    _p("pit_drill_t_hole", 8 * 9 * 10 * 2.66, 1000, 3000, "t", S_PEK + ", p. 40 (bench height 10 m)", "calc",
       "rock per hole: burden 8 m x spacing 9 m x bench 10 m x 2.66 t/m3 = 1 915 t (bench height is a project fact, "
       "pattern is assumed); only the blasted stock depends on it"),
    _p("pit_drill_move_min", 10, 5, 20, "min", S_D4, "assumption", "rig moves to the next hole"),
    _p("pit_drill_kio", 0.85, 0.7, 0.95, "-", S_D4, "assumption", "drill rig and dozer ready share, drawn hourly"),
    _p("pit_face_blasted_t0", 100000, 20000, 300000, "t", S_D4, "assumption",
       "blasted rock at a face at the snapshot (about 1.5 days of one excavator)"),
    _p("pit_face_blasted_max_t", 200000, 50000, 500000, "t", S_D4, "assumption",
       "above this the rig of the face waits (IDLE): enough blasted rock ahead"),
    _p("blk_axb_mean", 35, 32.8, 40.8, "-", S_SMC, "assumption",
       "block-model A*b mean: no open Aktogay A*b; 35 sits between the design P25 of the analogs (Touro 34.0, "
       "Josemaria 32.8) and their sample means (40.4, 40.8)"),
    _p("blk_axb_cv", 0.10, 0.05, 0.20, "-", S_D4, "assumption", "block-to-block spread of the estimate"),
    _p("blk_axb_lo", 24, 24, 27, "-", S_D7, "assumption", "clamp"),
    _p("blk_axb_hi", 45, 40, 47, "-", S_D7, "assumption", "clamp"),
    _p("blk_cu_mean_pct", 0.41, 0.32, 0.50, "% Cu", S_KAZ25 + "; " + S_KAZ24 + "; " + S_KAZ23, "fact",
       "feed grade: 0.50 (2023), 0.43 (2024), 0.41 % (2025) by the reports; resource grade 0.32 % (Q2-24, p. 3); "
       "set per year in calib"),
    _p("blk_cu_cv", 0.10, 0.05, 0.15, "-", S_D4, "assumption", "feed 0.32-0.50 % Cu"),
    _p("blk_cu_lo_frac", 0.33 / 0.41, 0.33 / 0.41, 0.33 / 0.41, "-", S_D4, "assumption",
       "clamp as a share of blk_cu_mean_pct: 0.33 % Cu at 0.41 %; scales with the year grade"),
    _p("blk_cu_hi_frac", 0.50 / 0.41, 0.50 / 0.41, 0.50 / 0.41, "-", S_D4, "assumption",
       "clamp as a share of blk_cu_mean_pct: 0.50 % Cu at 0.41 %; scales with the year grade"),
    _p("blk_ascu_mean_pct", 5.0, 2.0, 10.0, "% of Cu", S_D4 + "; " + S_AKHM, "assumption",
       "acid-soluble Cu share of total Cu; Aktogay lab samples show oxidised Cu 0-2.94 % of Cu (Akhmetova 2024 "
       "p. 25): 5 % is above that"),
    _p("blk_ascu_sd_pp", 1.5, 0.5, 3.0, "pp", S_D4, "assumption"),
    _p("blk_err_axb_sigma", 0.12, 0.065, 0.15, "-", S_D4 + "; " + S_MORRELL, "assumption",
       "true = est x lognormal(0, sigma); Morrell p. 3: A*b error not below 6.5 %"),
    _p("blk_err_cu_sigma", 0.05, 0.03, 0.18, "-", S_D4 + "; " + S_SILVA, "assumption",
       "relative; literature 9 % (monthly) to 18 % (per block)"),
    _p("blk_err_ascu_pp", 1.0, 0.5, 2.0, "pp", S_D4, "assumption", "additive"),
    _p("blk_plan_on", 0, 0, 1, "flag", S_D4, "assumption",
       "1 = mine-plan variability on: slow changes of grade, hardness and ASCu from one stretch of the pit to the next "
       "(quarter-to-quarter spread). Off in the paired runs (shift trials, quarterly back-test), where it cancels or only adds "
       "noise; on in the spread check (sim/fidelity.py)"),
    _p("blk_plan_len_blocks", 500, 100, 1000, "blocks", S_D4, "assumption",
       "blocks between two knots of the slow mine-plan variability (500 x 15 kt = 7.5 Mt, about two months)"),
    _p("blk_plan_sigma_cu", 0.059, 0.0, 0.20, "-", S_KAZ25, "calc",
       "slow lognormal sigma of the block Cu; calibrated so that the quarter-to-quarter spread of the quarter-mean grade "
       "equals the reported one (SD of the change of ln grade over the 28 test quarters)"),
    _p("blk_plan_sigma_axb", 0.06, 0.0, 0.15, "-", S_D4, "assumption",
       "slow lognormal sigma of A*b along the mine plan; no quarterly hardness is published, the value is a choice"),
    _p("blk_plan_sigma_ascu_pp", 1.86, 0.0, 3.0, "pp", S_D4, "assumption",
       "slow sd of the acid-soluble Cu share along the mine plan; sets the unexplained quarterly spread of recovery "
       "(-1.043 pp per pp ASCu); calibrated to the SD of the reported recovery residual"),
    _p("ore_density_t_m3", 2.66, 2.6, 2.77, "t/m3", S_BRAD, "vendor",
       "design specific gravity 2.66 (bulk 1.6), Bradken sample 2.69; OVOS-18 states 2.77 for the ore (page not "
       "located): kept at the Bradken design value used by the Aktogay engineers, 2.77 is the range top; DWi and "
       "the pore-water row use this value"),
    _p("ore_axb_base", 35, 32.8, 40.8, "-", S_SMC, "assumption",
       "no open Aktogay A*b: between the design P25 (32.8-34.0) and the sample means (40.4-40.8) of the analogs"),
    _p("ore_bwi_base", 19.4, 17.33, 20.9, "kWh/t", S_BRAD + "; " + S_MYRZ, "vendor",
       "Bradken average 19.4, design 20.9; Aktogay sample 17.33 (Myrzabekova 2021)"),
    _p("ore_axb_hard", 27, 24, 30, "-", S_D7, "assumption", "scenario hard:N; Aktogay f = 10.2 'very strong' (Myrzabekova)"),
    _p("ore_bwi_hard", 20.9, 20.9, 20.9, "kWh/t", S_BRAD, "vendor", "design value"),
    _p("ore_axb_blend", 40, 38, 45, "-", S_D7 + "; " + S_SCSE, "assumption",
       "soft partner for 50/50 blend; the model blends A*b linearly, SMC recommends blending by specific energy"),
    _p("ore_blend_frac", 0.5, 0.3, 0.7, "-", S_D7, "assumption", "hard share after blending"),
    _p("ui_axb_soft", 38, 38, 38, "-", S_D6 + "; " + S_JK, "assumption",
       "colour class 'softer than the base ore' at A*b >= 38 (not 'soft': JK classes put 38-43 at moderately hard)"),
    _p("ui_axb_hard", 30, 30, 30, "-", S_D6 + "; " + S_JK, "assumption", "colour class 'harder than the base ore' below 30"),

    # ---------------- crusher, conveyor ----------------
    _p("crush_cap_tph", 4386, 4386, 5043.9, "t/h", S_OVOS + ", p. 26", "project",
       "4 386-5 043.9 t/h is the design rate of the coarse-crushing AREA with the irregularity factor 1.15 (25 Mt / 5 700 h = 4 386; "
       "x 1.15 = 5 043.9), not a crusher nameplate; no crusher nameplate was found. In the model the crusher has only "
       "533 t/h of headroom over the mill (4 386 - 3 853), so the stock refills slowly and the cost of crusher troubles is "
       "probably overstated"),
    _p("crush_kio", 0.78, 0.78, 0.78, "-", S_OVOS + ", p. 25-26", "project",
       "equipment utilisation ratio of coarse crushing = 285 of 365 days (a share of days, not of hours); the design hours are "
       "285 d x 2 shifts x 10 h = 5 700 h = 65.1 % of the hours of a year; the 0.92 of the other areas and the 1.15 "
       "irregularity factor are in the same table"),
    _p("crush_power_mw", 0.75, 0.75, 1.0, "MW", S_FLS_GYR + "; " + S_BOZ14, "vendor",
       "TS 60x113 drive up to 1 000 kW (FLSmidth); 750 kW from the Bozshakol 2014 update, p. 12 (analog; Aktogay's own crusher "
       "drive is not published)"),
    _p("crush_plan_every_d", 28, 14, 56, "d", S_D3 + "; " + S_AUSENCO_AV, "assumption",
       "calib and free run only: a planned maintenance window of the primary crusher (greasing, bolts, liner check) comes once in this "
       "many days at a random time; the stockpile carries the mill meanwhile"),
    _p("crush_plan_h", 8, 4, 12, "h", S_D3 + "; " + S_AUSENCO_AV, "assumption", "length of that window"),
    _p("crush_plan_wait_d", 3, 1, 7, "d", S_D3, "assumption",
       "planned crusher work is done while the mill of the line stands (the pile carries the mill only about 3 h at the draw column); "
       "if no mill stop comes in this many days it is done anyway"),
    _p("crush_stop_per_day", 1.0, 0.5, 2.0, "1/d", S_D3 + "; " + S_AUSENCO_AV, "assumption",
       "short stoppages of the crusher (oversize rock in the pocket, rock breaker, blocked pocket), a Poisson stream"),
    _p("crush_stop_min", 20, 10, 40, "min", S_D3 + "; " + S_AUSENCO_AV, "assumption", "length of a short stoppage (calib run)"),
    _p("crush_lube_kpa", 250, 200, 300, "kPa", S_D3, "assumption", "normal lube pressure"),
    _p("crush_lube_noise_kpa", 5, 2, 10, "kPa", S_D4, "assumption"),
    _p("crush_lube_trip_kpa", 150, 120, 180, "kPa", S_D4, "assumption", "protection trip below"),
    _p("crush_repair_h", 3, 2, 6, "h", S_D7 + "; " + S_IPB, "assumption",
       "median after arrival; P90 5 h; analog MTTR about 5.5 h (weak source), range 3-6 h"),
    _p("conv_length_km", _CONV_KM, _CONV_KM, _CONV_KM, "km", S_PEK + ", p. 18 (concentrator 2: 2 504 m; concentrator 1 "
       "about 2.5 km, p. 10); cross-check " + S_OSM, "project",
       "main conveyor crushing -> plant (the 3.8 km of the design file was the Bozshakol belt)"),
    _p("conv_belt_m", 1.6, 1.6, 1.6, "m", S_BOZ14, "analog",
       "Bozshakol overland belt, p. 13 (the Bozshakol belt is 3.8 km, Aktogay's is 2.5 km); belt width of Aktogay not published"),
    _p("conv_cap_tph", 4880, 4880, 4880, "t/h", S_BOZ14, "analog",
       "Bozshakol overland belt, p. 13 (4 880 t/h, 5 m/s at most; 3.8 km against Aktogay's 2.5 km); the code does not read this row"),
    _p("conv_power_mw", 3.64, 3.64, 3.64, "MW", S_BOZ14, "analog",
       "Bozshakol 3.8 km belt drive, p. 13 (3 640 kW); Aktogay's drive power is not in open sources, kept as the upper "
       "estimate for the 2.5 km belt"),
    _p("conv_speed_ms", 4.5, 3.4, 6.0, "m/s", S_D3 + "; " + S_BULK, "assumption", "overland belts run 3.4-6.0 m/s"),
    _p("conv_transit_min", _CONV_KM * 1000 / 4.5 / 60, _CONV_KM * 1000 / 6.0 / 60, _CONV_KM * 1000 / 3.4 / 60,
       "min", S_PEK + ", p. 18", "calc", "2.504 km / 4.5 m/s = 9.3 min (the 14 min of the design file was 3.8 km)"),

    # ---------------- ore stockpile ----------------
    _p("stock_total_t", _STOCK_TOTAL_T, _STOCK_TOTAL_T, _STOCK_TOTAL_T, "t", S_OVOS_RK + ", p. 58", "project",
       "working volume of the ore stockpile, about 2 days of one line"),
    _p("stock_live_frac", _STOCK_LIVE_FRAC, 0.17, 0.34, "-", S_STOCK + "; " + S_SKOURIES, "assumption",
       "PEK 163 kt is the working volume of the WHOLE pile (2 days of grinding), not the live stock; the live part is this "
       "share. Verified analogs 24.10.2026: Skouries 33 % of the total (live = 24 h of production), Constancia 16 h live; "
       "here 40 kt = 24.5 % = 11.8 h of one line. "
       "The PEK p. 10 names three belt feeders (FE-104, FE-105, FE-106) under the stockpile; the 26.5 % example of "
       "911metallurgist (three outlets, one geometry) would give about 43 kt; Ferreira and Luz 2022, table 2, give 17.74 / "
       "17.79 % for one outlet in a sand rig; Skouries 33 % with 3 feeders. 0.245 keeps the 40 kt live stock of design "
       "sections 3 and 7; the value is an assumption"),
    _p("stock_live_t", _STOCK_TOTAL_T * _STOCK_LIVE_FRAC, _STOCK_TOTAL_T * 0.17, _STOCK_TOTAL_T * 0.30, "t",
       S_OVOS_RK + ", p. 58; " + S_STOCK, "calc",
       "live capacity = stock_total_t x stock_live_frac = 163 000 x 0.245 = 40 000 t; the rest of the 163 kt is "
       "dead stock on the sides"),
    _p("stock_column_frac", 0.30, 0.20, 0.40, "-", S_D3 + "; " + S_STOCK, "assumption",
       "draw column share of live stock (live share of the whole pile: 17.74 / 17.79 % for one outlet, Ferreira and Luz 2022, "
       "table 2; 26.5 % for three outlets in one geometry, 911metallurgist)"),
    _p("stock_exchange_tau_h", 24, 12, 48, "h", S_D3 + "; " + S_STOCK, "assumption",
       "sides to column exchange; 163 000 t / 3 853 t/h = 42 h of one line [calc]"),
    _p("stock_reg_high_frac", 0.85, 0.80, 0.90, "-", S_D4, "assumption", "above: pit cuts mining"),
    _p("stock_reg_low_frac", 0.20, 0.10, 0.30, "-", S_D4, "assumption", "below: pit mines at max"),
    _p("stock_low_frac", 0.15, 0.10, 0.20, "-", S_D3, "assumption", "LOW state"),
    _p("stock_full_frac", 0.99, 0.97, 1.0, "-", S_D3, "assumption", "FULL state"),
    _p("stock_empty_t", 200, 0, 500, "t", S_D3, "assumption", "EMPTY state"),
    _p("stock1_t0", 11600, 8000, 16000, "t", S_D7, "assumption",
       "live stock at the moment of the event (08:00 snapshot), not a capacity; gives 3 h 00 min at base t/h"),
    _p("stock2_t0", 30000, 20000, 36000, "t", S_D7, "assumption",
       "live stock at the moment of the event (08:00 snapshot), not a capacity; gives 7 h 47 min"),

    # ---------------- SAG mill ----------------
    _p("sag_diam_ft", 40, 40, 40, "ft", S_BRAD + "; " + S_PEK + ", p. 10 (drum 12.2 m = 40 ft)", "vendor",
       "drum diameter; the PEK gives 12.2 m for concentrator 1, which is the same 40 ft"),
    _p("sag_len_ft", 26, 26, 26, "ft", S_BRAD + "; " + S_PEK + ", p. 10 (drum length 7.6 m = 24.9 ft)", "vendor",
       "drum length of the vendor sheet; the PEK says 7.6 m (4 % shorter, not refitted: sag_k absorbs it, passports show the PEK figure)"),
    _p("sag_rated_mw", 28, 28, 28, "MW", S_BRAD, "vendor", "gearless drive"),
    _p("sag_power_sp_mw", 26.0, 24.0, 27.5, "MW", S_D4 + "; " + S_911EXP, "assumption",
       "shaft setpoint, 93 % of 28 MW (90-95 % of installed is usual); Aktogay drew about 22 MW in 2017-2019 "
       "(Bradken p. 12: 7.25 kWh/t x 3 012 t/h, calc)"),
    _p("sag_power_sigma", 0.02, 0.01, 0.03, "-", S_D4, "assumption", "relative power fluctuation"),
    _p("sag_speed_pct", 76, 70, 80, "% crit", S_BRAD, "vendor", "design nominal (Table 1)"),
    _p("sag_load0_pct", 25, 20, 35, "% vol", S_BRAD, "vendor", "J0 = Bradken Table 1 expected total load 25 % (max 35 %)"),
    _p("sag_ball_load_pct", 12, 12, 16, "% vol", S_BRAD, "vendor",
       "ball charge (max 16 %); it stays when the ore is ground out: load floor of a turning mill"),
    _p("sag_ball_dens_mult", _BALL_DENS, 1.0, 1.5, "-", S_AUSTIN, "assumption",
       "ball charge alone over the mixed charge at J0, per m3: 0.6 x 7.8 / ((12 x 5.40 + 13 x 2.32) / 25) "
       "(voids 0.4, steel 7.8, ore 2.66, slurry 1.8 t/m3); ground-out power = this x f(Jb) / f(J0), "
       "about 70 % of P0 with the Austin load term"),
    _p("sag_tau_min", 5, 3, 10, "min", S_D4, "assumption",
       "mill load inertia; the mean residence of the ore in the SAG is 4.2-4.8 min (about 311 t of ore / 3 853 t/h at J 25 %, "
       "Jb 12 %, Bradken) [calc], and a residence time is not the time constant of the load"),
    _p("sag_starved_frac", 0.95, 0.90, 0.98, "-", S_D4, "assumption", "STARVED if feed below share of capacity"),
    _p("sag_f80_mm", 130, 128, 137, "mm", S_SMC, "assumption",
       "no Aktogay F80: between Touro 128 and Josemaria 137 mm (section 17.2.2 p. 140)"),
    _p("sag_morrell_a", 0.2, 0.07, 0.2, "-", S_MORRELL, "assumption",
       "F80 exponent of Morrell eq. 2 (constants not published); GMG-2021 puts the F80 influence at about "
       "0.07-0.13, so 0.2 is the strong end; sensitivity 0.1-0.2. Cadia Hill JKMRC (p. I-45) A*b 32.1-37.8 and Briggs 2025 (p. 4) A*b 30-40 "
       "agree with the model's A*b 35 and 27, but they say nothing on the exponents: label kept"),
    _p("sag_morrell_b", 0.8, 0.7, 1.0, "-", S_MORRELL, "assumption",
       "DWi exponent of Morrell eq. 2 (constants not published); by Mia it would be 1.0; Cadia and Briggs A*b values do not fix it: label kept"),
    _p("sag_k", _SAG_K, 0.40, 0.60, "-", S_D4, "calc",
       "E_SAG = K F80^a DWi^b = 6.75 kWh/t at 26.0 MW and 3853 t/h (A*b 35, rho 2.66, F80 130 mm)", fit=True),
    _p("sag_e_base_kwh_t", _SAG_E, 6.0, 7.5, "kWh/t", S_D4, "calc", "26.0 MW / 3853 t/h"),
    _p("sag_e_design_kwh_t", 6.6, 6.6, 6.6, "kWh/t", S_BRAD + " Table 1 p. 03", "vendor", "design reference"),
    _p("sag_e_2017_19_kwh_t", 7.25, 7.25, 7.25, "kWh/t", S_BRAD + " p. 12", "vendor",
       "mean Sep 2017 - Mar 2019 (publication 2021) while t/h rose from about 2 343 to 3 012; the 22 MW of the "
       "design file is 7.25 x 3 012 (calc); the gap to 6.75 is attributed to mine-to-mill (assumption)"),
    _p("sag_austin_j", 1.03, 1.03, 1.03, "-", S_AUSTIN, "analog",
       "f(J) = J (1 - 1.03 J) (Austin 1990); 0.937 of the design file belongs to the Bond/Rowland ball-mill formula"),
    _p("sag_austin_a", 0.1, 0.1, 0.1, "-", S_AUSTIN, "analog", "g(phi) = phi (1 - a / 2^(b - c phi))"),
    _p("sag_austin_b", 9, 9, 9, "-", S_AUSTIN, "analog"),
    _p("sag_austin_c", 10, 10, 10, "-", S_AUSTIN, "analog"),
    _p("liner_wear_mm_mt", 20.41, 20.41, 20.41, "mm/Mt", S_BRAD + " p. 05", "vendor",
       "feed-end zone only, OEM liner set of 2017; counter by norm"),
    _p("liner_feed_end_mm", _FEED_END_MM, 20.41 * 8.52, 250, "mm", S_BRAD, "assumption",
       "feed end is changed at intermediate relines (Bradken); interval = liner set life 8.52-9.96 Mt x 20.41 "
       "mm/Mt; the wear counter restarts there; downtime of these relines is inside cal_avail"),
    _p("liner_life_mt", 30, 20, 45, "Mt", S_D4 + "; " + S_KAZQ3_23, "assumption",
       "liner campaign, 10-18 months; a reline brought forward by two months on wear is reported (Q3 2023)"),
    _p("liner_eta_new", 0.96, 0.95, 0.97, "-", S_POWELL, "assumption",
       "new liner: t/h 3-5 % lower is our number; Powell 2006 gives the direction only"),
    _p("liner_x_ramp", 0.10, 0.05, 0.20, "-", S_POWELL, "assumption", "campaign share to reach eta 1; shape assumed"),
    _p("liner_eta_peak", 1.03, 1.00, 1.05, "-", S_POWELL, "assumption", "peak late in campaign; our number"),
    _p("liner_x_peak", 0.70, 0.50, 0.85, "-", S_POWELL, "assumption", "shape assumed"),
    _p("liner_eta_end", 0.98, 0.95, 1.00, "-", S_POWELL, "assumption", "flattened profile at end; our number"),
    _p("liner_x0", 0.10, 0.0, 1.0, "-", S_D4, "assumption", "live snapshot campaign share (eta = 1.0)"),
    _p("liner_reline_h", 84, 72, _RELINE_ALL_H, "h", S_CHINALCO + "; " + S_RME, "analog",
       "full SAG reline, 3.5 days: the verified case of Minera Chinalco Peru (84 h done, 96 h planned; one vendor case of "
       "another copper mine), 2.1-3.8 % of the year on relines against the RME 2-5 %; was 96 h (assumption) until 24.10.2026, "
       "which overstated the drop of the ore of a line in the five reported relines (-6.3 % against -4.8 %); not taken from the "
       "Q3 2025 quarter, whose change is not the net reline effect (file 05, s. 1.2); max = the whole line 2 "
       "Q3/Q2 2025 rate drop as hours (126.8 h)"),

    # ---------------- pebble crushing ----------------
    _p("peb_frac_base", 0.15, 0.10, 0.23, "-", S_D4 + "; " + S_LI24, "assumption",
       "pebbles per t SAG feed at A*b 35; analog 16-23 % for soft ore. Cadia Hill industrial survey 23.07.1998 (JKMRC, p. I-50 table 3): "
       "23 % of new feed (design 35 %): the top of the range, above 0.15, so the label stays"),
    _p("peb_frac_hard", 0.25, 0.20, 0.40, "-", S_D4 + "; " + S_LI24 + "; Cadia Hill JKMRC report (smctesting.com publication id 175), p. I-50 table 3: "
       "pebbles 23 % of new feed in the industrial survey, 35 % in the design", "analog",
       "at A*b 27, linear in A*b; analog 22-40 % for hard ore; Cadia 23-35 % lies inside the range 0.20-0.40 (the slope in A*b is ours)"),
    _p("peb_limit_tph", 740, 682, 792, "t/h", S_OVOS + ", p. 26; " + S_RAPTOR, "assumption",
       "node 682-792 t/h (OVOS); for scale: a cone crusher of the Raptor 1100 class does 549-798 t/h (FLSmidth p. 9); "
       "the cone crusher type of Aktogay is not confirmed by any source"),
    _p("peb_hpgr_l2_tph", 1061, 1061, 1061, "t/h", S_IM21, "vendor",
       "thyssenkrupp POLYCOM HPGR of line 2: the pebble circuit of line 2 takes min(peb_limit_tph, this) "
       "(Plant.peb_limit_tph); above the cones, so the cones stay the limit and the HPGR load is feed / this"),
    _p("peb_hpgr_l2_kw", 3500, 3500, 3500, "kW", S_IM21, "vendor",
       "2 x 1 750 kW drives of the line 2 HPGR; shown as pebble-2 hpgr_kw = this x HPGR load, a part of "
       "pow_line_aux_mw (not added to the site load twice)"),
    _p("peb_warn_frac", 0.95, 0.90, 0.98, "-", S_D4, "assumption", "LIMIT state"),
    _p("peb_stop_e_med", 1.06, 1.06, 1.06, "-", S_LIHIR, "analog", "E_SAG x when pebble crusher stops; not verified"),
    _p("peb_stop_e_hard", 1.10, 1.10, 1.10, "-", S_LIHIR, "analog", "not verified"),
    _p("peb_kio", 0.92, 0.92, 0.92, "-", S_OVOS + ", p. 25", "project", "random stops: free run and calib"),
    _p("peb_stop_h_lo", 1, 1, 1, "h", S_D4, "assumption"),
    _p("peb_stop_h_hi", 4, 4, 4, "h", S_D4, "assumption"),

    # ---------------- ball mills ----------------
    _p("ball_rated_mw", 22, 22, 22, "MW", S_AT12, "vendor",
       "two 22 MW gearless drives for the two 28 ft ball mills of Aktogay (drive order 2012)"),
    _p("ball_power_mw", 20.5, 19.5, 21.5, "MW", S_D4, "assumption", "shaft, 93 % of 22, load-driven"),
    _p("ball_per_line", 2, 2, 2, "-", S_BRAD, "vendor", "28 x 44 ft"),
    _p("ball_f80_um", 2500, 1500, 3500, "um", S_LI24, "analog",
       "ball circuit feed F80; 2.2-2.7 mm for hard ore (table 1 p. 37), top of the typical range"),
    _p("ball_p80_target_um", 180, 170, 190, "um", S_BRAD, "vendor", "flotation feed P80"),
    _p("ball_p80_min_um", 120, 100, 150, "um", S_D4, "assumption",
       "finest cyclone overflow P80 of an under-loaded circuit: classification limits the overflow, Bond "
       "energy is capped there; analog design grinds 125-200 um (Touro, Josemaria, Casino)"),

    # ---------------- cyclones ----------------
    _p("cyc_total", 14, 10, 14, "-", S_D3 + "; " + S_CYC, "assumption", "analogs: Ngezi 12 (9 on), Copperton 10"),
    _p("cyc_open", 10, 8, 12, "-", S_D3 + "; " + S_CYC, "assumption"),
    _p("cyc_clog_p80_um", 12, 8, 20, "um", S_D4 + "; " + S_CYC, "assumption",
       "per clogged cyclone; the effect is known only qualitatively"),
    _p("cyc_clog_dp_frac", 0.03, 0.01, 0.05, "-", S_D4, "assumption", "pressure rise per clogged cyclone"),
    _p("cyc_pressure_kpa", 80, 60, 110, "kPa", S_D4, "assumption", "base pressure, scales (Q/open)^2"),
    _p("cyc_upset_frac", 0.25, 0.15, 0.35, "-", S_D4, "assumption", "UPSET if |dp/p0| above"),

    # ---------------- flotation ----------------
    _p("flot_rinf0_pct", _RINF0, 88, 96, "%", S_D4, "calc",
       "R0': total R = 87.2 % at base (R_c 97 %, k tau 3.5)", fit=True),
    _p("flot_grade_pp_ln", 4.093, 0.0, _GRADE_PP_LN_MAX, "pp", S_JOSE, "analog",
       "total R += 4.093 ln(g / g0): Josemaria RecCu = 95.89 + 4.093 ln(%Cu) - 1.043 ASCu is a total (final) "
       "recovery fitted on ALS samples (the block-model version of the report uses 0.696); applied on "
       "R_inf / (k_base c_base); max 12.8 = 100 - R0 if tails stayed constant"),
    _p("flot_jose_ascu", 1.043, 0.5, 1.5, "pp/pp", S_JOSE, "assumption",
       "total R -= 1.043 (ASCu - ASCu0) per pp of ASCu as a share of total Cu; the unit of ASCu in the Josemaria "
       "regression (share of ore mass or share of total Cu) is not confirmed (report > 10 MB not opened), so "
       "moving the coefficient here is an assumption; applied on R_inf / (k_base c_base); sensitivity 0.5-1.5"),
    _p("flot_grade_ref_pct", 0.41, 0.41, 0.41, "% Cu", S_KAZ25, "fact", "g0"),
    _p("flot_ascu_ref_pct", 5.0, 2.0, 10.0, "% of Cu", S_D4 + "; " + S_AKHM, "assumption",
       "ASCu0; Aktogay lab samples: oxidised Cu 0-2.94 % of total Cu"),
    _p("flot_ktau0", 3.5, 2.5, 4.5, "-", S_D4 + "; " + S_VINNETT, "assumption",
       "k tau at base residence; Vinnett 2022 gives k tau 9-13 for roughers, so 3.5 is a cautious value"),
    _p("flot_tau0_min", 30, 20, 40, "min", S_D4 + "; " + S_VINNETT, "assumption",
       "residence at cal_line_tph; literature 25-38 min"),
    _p("flot_p80_ref_um", 180, 180, 180, "um", S_BRAD, "vendor"),
    _p("flot_p80_pp_10um", 0.3, 0.1, 1.95, "pp", S_D4, "assumption",
       "per 10 um above 180; the value is an assumption (no source for the slope at Aktogay); the analog Bozshakol gives 0.79-1.95 (laboratory 0.79-1.22, plant regression 1.95), see modules grind_pp_10um; the range reaches the analog"),
    _p("flot_dose_sp_gt", 25, 20, 30, "g/t", S_OVOS, "project", "xanthate 0.025 kg/t"),
    _p("flot_dose_ref_deficit", 0.40, 0.40, 0.40, "-", S_D4, "assumption", "under-dose share for flot_dose_pp"),
    _p("flot_dose_pp", 3.5, 2.0, 4.0, "pp", S_D4 + "; " + S_SARCH + "; " + S_AKHM, "assumption",
       "total R loss at 40 % under-dose, linear; -2 to -4 pp at Sarcheshmeh, Aktogay lab table 16"),
    _p("flot_pull0_pct", 7, 5, 13, "%", S_D3 + "; " + S_AKHM, "assumption",
       "rougher mass pull at g0; Aktogay lab rougher + scavenger 7-13 %"),
    _p("clean_r0_pct", 97, 95, 98.5, "%", S_D3 + "; " + S_FREEPORT, "assumption",
       "cleaner stage recovery; 96-98 % at a column cleaner circuit (analog). Copper World PFS 2023 (laboratory, p. 1-5): cleaner 93 %, rougher 97 %: "
       "below the range 95-98.5, so the label stays"),
    _p("clean_pp_10pp", 1.0, 0.5, 2.0, "pp", S_D4, "assumption",
       "per 10 pp of rougher mass pull above flot_pull0_pct; no source for the slope"),
    _p("flot_conc0_pct", 24.3, 24.3, 24.3, "% Cu", S_OVOS + ", table 1.5.1 p. 26; " + S_OVOS_RK + ", p. 57", "project",
       "concentrate grade (OVOS-18 table 1.5.2 p. 29 gives 16-20 %); 24.3 % at 83.8 % recovery in OVOS-RK"),
    _p("flot_conc_slope", 0.5, 0.2, 1.0, "-", S_D4, "assumption", "grade = 24.3 - 0.5 (R - R0); no source, calibrate"),
    _p("flot_rec_ref_pct", 87.2, 87.2, 87.2, "%", S_KAZ25, "fact", "R0"),
    _p("flot_delay_min", 15, 10, 20, "min", S_D4, "assumption", "transport delay; analog about 20 min"),
    _p("flot_tau_min", 20, 10, 30, "min", S_D4, "assumption", "first-order lag; analog 24-41 min"),
    _p("flot_design_rec_pct", 83.8, 83.8, 83.8, "%", S_OVOS_RK + ", p. 57", "project", "reference only"),
    _p("flot_design_tail_pct", 0.059, 0.059, 0.059, "% Cu", S_OVOS_RK + ", p. 57", "project", "reference only"),

    # ---------------- thickener, filter, concentrate stock ----------------
    _p("thick_cap_t", 340, 250, 450, "t", S_D3 + "; " + S_OVOS_RK + ", p. 108; " + S_MS2024, "assumption",
       "about 6 h of output: 6 h x 48-58 t/h = 290-350 t"),
    _p("thick_uf_solids_pct", 60, 55, 65, "%", S_D3 + "; " + S_MS2024, "assumption", "60 % typical"),
    _p("thick_feed_solids_pct", 25, 15, 35, "%", S_D4, "assumption", "cleaner concentrate pulp"),
    _p("thick_t0", 40, 0, 340, "t", S_D6, "assumption", "snapshot inventory"),
    _p("thick_high_frac", 0.80, 0.70, 0.90, "-", S_D3, "assumption", "HIGH state"),
    _p("filt_presses", 2, 2, 2, "-", S_OVOS + ", p. 24-25; " + S_OVOS_RK + ", p. 67", "project", "2 presses per plant"),
    _p("filt_press_tph", 35, 30, 45, "t/h", S_D3, "assumption",
       "project node 38.6-44.82 t/h per 25 Mt/yr is below 2025 output"),
    _p("filt_moist_pct", 8, 8, 8, "%", S_OVOS + ", p. 24-25", "project"),
    _p("filt_moist_sigma_pp", 0.3, 0.1, 0.5, "pp", S_D4, "assumption"),
    _p("filt_cloth_every_h", 12, 12, 12, "h", S_D4, "assumption", "one press per shift"),
    _p("filt_cloth_h", 1, 0.5, 2, "h", S_D4 + "; " + S_MCLAN, "assumption",
       "one press out for a cloth change; 10-20 min per cloth (vendor), a press has many"),
    _p("filt_design_lo_tph", 38.6, 38.6, 38.6, "t/h", S_OVOS + ", p. 26", "project", "reference"),
    _p("filt_design_hi_tph", 44.82, 44.82, 44.82, "t/h", S_OVOS + ", p. 26", "project", "reference"),
    _p("cstock_cap_t", 20000, 15000, 30000, "t", S_D3 + "; " + S_OVOS_RK + ", pp. 56, 67, 148, 153", "assumption",
       "OVOS-RK: each concentrator has its own store and loading point; the model keeps one combined store for "
       "both lines (the sum of the two); 20 kt wet for the two together is an assumption"),
    _p("cstock_high_frac", 0.80, 0.70, 0.90, "-", S_D4, "assumption"),
    _p("cstock_t0", 8000, 0, 20000, "t", S_D4, "assumption", "snapshot stock"),
    _p("cstock_train_wagons", 21, 21, 21, "-", S_D4 + "; " + S_OVOS_RK + ", p. 108", "assumption",
       "2 x 21 x 70 = 2 940 t/d against about 2 760-2 890 t/d of wet concentrate: 2-6 % margin"),
    _p("cstock_wagon_t", 70, 69.5, 70, "t", S_D4 + "; " + S_RGUPS, "assumption", "wagons built in Kazakhstan carry 69.5 t"),
    _p("cstock_train1_h", 6, 6, 6, "h", S_D4, "assumption"),
    _p("cstock_train2_h", 18, 18, 18, "h", S_D4, "assumption"),

    # ---------------- water ----------------
    _p("water_tails_solids_pct", 68, 65, 70, "%", S_OVOS, "project",
       "discharge pulp (0.47 m3/t); reference: water above the pore water bleeds back to the pond"),
    _p("water_tails_dry_t_m3", 1.45, 1.4, 1.5, "t/m3", S_TAILS, "analog", "no Aktogay figure"),
    _p("water_tails_m3_t", _PORE_W, 0.29, 0.34, "m3/t", S_D4, "calc",
       "pore water locked in settled tails: 1 / 1.45 - 1 / 2.66 (ore density)"),
    _p("water_recycle_m3_t", 2.7, 2.4, 3.0, "m3/t", S_OVOS, "project"),
    _p("water_proc_m3_t", 3.3, 3.0, 3.6, "m3/t", S_OVOS, "calc", "recycle 2.7 + fresh 0.6"),
    _p("water_fresh_lo_m3_t", 0.63, 0.63, 0.63, "m3/t", S_OVOS + ", table 1.5.2 p. 29", "project",
       "reference; two OVOS tables differ"),
    _p("water_fresh_hi_m3_t", round(_FRESH_HI, 2), 0.83, 0.99, "m3/t", S_OVOS + ", p. 145", "calc",
       "reference: 73 512.92 m3/d over 25 Mt / 8 059 h x 24 = 0.99 m3/t (0.83 in the design file was rounded "
       "from another table)"),
    _p("water_intake_2024_m3_t", 0.60, 0.60, 0.60, "m3/t", S_KAZ_W, "fact", "reference"),
    _p("water_evap_m3h", _EVAP, 500, 2500, "m3/h", S_D4, "calc",
       "pond evaporation and seepage; table value from the 2024 intake 34.852 Mm3 at 58.3 Mt, "
       "refitted on 2024 by calib", fit=True),
    _p("pond_proc_m3_per_line", 56000, 56000, 56000, "m3", S_OVOS + ", p. 145", "project",
       "reference only: process-water pond of one concentrator, about 7 h of turnover; not the pond of the model"),
    _p("pond_m3_0", 1.25e6, 1.0e6, 1.5e6, "m3", S_D4, "assumption",
       "snapshot of the tailings return-water (decant) pond of the model, not the 56 000 m3 process-water pond "
       "of a plant; no source for its volume: 1.0-1.5 Mm3 is 10-16 days of the 2024 intake (95 200 m3/d)"),
    _p("pond_lo_m3", 1.0e6, 1.0e6, 1.0e6, "m3", S_D4, "assumption", "regulator band (decant pond, assumption)"),
    _p("pond_hi_m3", 1.5e6, 1.5e6, 1.5e6, "m3", S_D4, "assumption", "regulator band (decant pond, assumption)"),
    _p("pond_reg_h", 48, 12, 96, "h", S_D4, "assumption",
       "recycle regulator time constant; one node stands in for the thickener overflow, the process-water pond and the tailings pond "
       "(the plant has three; no volumes or regulator rules are published)"),
    _p("pond_piezo_kpa0", 120, 100, 140, "kPa", S_D4, "assumption", "at pond_m3_0"),
    _p("pond_piezo_kpa_mm3", 40, 20, 60, "kPa/Mm3", S_D4, "assumption", "slope a"),
    _p("pond_piezo_sp_kpa", 150, 140, 170, "kPa", S_D4, "assumption", "safety setpoint (S0)"),
    _p("pond_piezo_noise_kpa", 1.0, 0.5, 2.0, "kPa", S_D4, "assumption"),
    _p("pond_piezo_off1_kpa", -4, -20, 5, "kPa", S_D4, "assumption",
       "piezometer P-1 against the dam reading of the model (positions and number of piezometers not published)"),
    _p("pond_piezo_off2_kpa", 0, -20, 5, "kPa", S_D4, "assumption", "piezometer P-2: the reading of the model"),
    _p("pond_piezo_off3_kpa", -10, -20, 5, "kPa", S_D4, "assumption", "piezometer P-3, lower on the dam"),
    _p("water_leak_frac", 0.10, 0.05, 0.30, "-", S_D4, "assumption",
       "scenario water: share of the pond return lost through a leak of the return-water pipeline"),
    _p("water_intake_cap_m3h", 2 * 73512.92 / 24.0, 5000, 8000, "m3/h", S_OVOS + ", p. 145", "calc",
       "fresh-water supply: 73 512.92 m3/d of one concentrator (OVOS-18) x 2 / 24 h; the same supply for line 1 "
       "is an assumption; above it the process lacks water and the ore is cut"),
    _p("water_leak_fix_h", 3, 1, 6, "h", S_D4, "assumption", "median repair of a return-water leak by crew-water"),
    _p("water_reg_min", 15, 5, 60, "min", S_D4, "assumption",
       "time constant of the ore cut that keeps the fresh-water intake at its supply cap"),

    # ---------------- power ----------------
    _p("pow_grid_limit_mw", 300, 250, 330, "MW", S_D3 + "; " + S_KAZ_EN + "; " + S_OVOS + ", PDF p. 224", "assumption",
       "normal limit: 2024 mean 231 MW (2023: 223 MW) plus about 30 %; line 2 is fed by 2 x 100/125 MVA"),
    _p("pow_motor_eff", 0.96, 0.94, 0.97, "-", S_D4 + "; " + S_MORRELL + "; " + S_SAGMILL, "assumption",
       "grid = shaft / 0.96; GMG-2021 PDF p. 24 gives 0.97 for a gearless drive, grid to shaft 0.93-0.97"),
    _p("pow_other_mw", _OTHER_MW, 30, 80, "MW", S_D4, "calc",
       "site part that runs with or without the lines: oxide plant, water supply, workshops, site; table "
       "value from the 2024 electricity 2033 GWh at 58.3 Mt and 3853 t/h per line after mills, crushers, "
       "conveyors and pow_line_aux_mw of running lines; refitted on 2024 by calib", fit=True),
    _p("pow_line_aux_mw", _LINE_AUX_MW, 15, 40, "MW", S_OVOS + ": line 2 electricity 827 514 MWh/yr", "calc",
       "per running line: flotation, pebble cones and HPGR, regrind, pumps, thickener, filter; stops with "
       "the line; 827 514 MWh / 8 059 h - mills (grid) - crusher - conveyor"),
    _p("pow_tx_mva", 125, 100, 125, "MVA", S_OVOS + ", p. 12 and PDF p. 224", "project",
       "500/220 kV substation Aktogay -> two 220 kV lines -> 220/35 kV substation, 2 x 100/125 MVA"),
    _p("pow_c2_limit_mw", 218, 180, 240, "MW", S_KEGOC, "assumption",
       "depth is an assumption: after ball-2b and the 15 MW feeder the site is near 210 MW, about 8 MW "
       "of headroom as in design section 7 C2"),
    _p("pow_c2_h", 2, 1, 4, "h", S_KEGOC + "; " + S_ME58, "assumption",
       "duration is an assumption; automatic load shedding lasts up to 20 min, then dispatcher restrictions "
       "without an MW norm (order No. 58, items 22, 34, 40)"),
    _p("pow_shed_other_mw", 15, 0, 20, "MW", S_D7, "assumption", "load-shedding feeder, category 2; no source"),
    _p("pow_reserve_mw", 10, 5, 15, "MW", S_D7, "assumption", "headroom after shedding; call may use part"),
    _p("pow_call_use_mw", 5, 0, 10, "MW", S_D7, "assumption", "headroom given to SAG-2 after call"),

    # ---------------- crews and issues ----------------
    _p("crew_arrive_lo_min", 20, 20, 20, "min", S_D5, "assumption"),
    _p("crew_arrive_hi_min", 40, 40, 40, "min", S_D5, "assumption"),
    _p("crew_sigma_ln", 0.4, 0.3, 1.0, "-", S_D5 + "; " + S_MILHDBK, "assumption",
       "lognormal repair time; P90 = 1.67 x median; the MIL-HDBK-338 example has sigma_ln about 1.1"),
    _p("crew_kip", 1, 1, 2, "-", S_D7, "assumption", "I&C technicians on shift"),
    _p("crew_cpd", 1, 1, 2, "-", S_D3, "assumption", "crusher mechanics teams on shift"),
    _p("crew_mill", 1, 1, 2, "-", S_D3, "assumption", "plant mechanics teams on shift"),
    _p("crew_water", 1, 1, 2, "-", S_D4, "assumption",
       "tailings and return-water teams on shift (pipelines, pump stations); led by the tailings engineer"),
    _p("crew_dose_arrive_min", 30, 20, 40, "min", S_D7, "assumption"),
    _p("crew_dose_fix_h", 0.5, 0.3, 0.8, "h", S_D7 + "; " + S_EH, "assumption",
       "median; P90 0.8 h; a built-in flowmeter verification itself takes minutes"),
    _p("crew_trip_fix_h", 3, 2, 6, "h", S_D7, "assumption", "lube trip sensor check; P90 5 h; range 3-6 h"),
    _p("crew_late_p", 0.15, 0.0, 0.30, "-", S_D5, "assumption",
       "free run: share of calls where the called person gets the message late (phone, radio, far away)"),
    _p("crew_late_min", 45, 30, 90, "min", S_D5, "assumption", "extra travel of such a late call"),
    _p("crew_remind_min", 10, 5, 20, "min", S_D5, "assumption",
       "arrival after a reminder ('not arrived - remind'); the next person of the trade: crew_arrive_lo..hi"),
    _p("crew_person_decision_h", 0.5, 0.25, 1.0, "h", S_D5, "assumption",
       "a person called for a decision without a crew (grid, blend, water, fire) is busy at the node"),
    # ---- novice parameterised from data (experiment of 24.10.2026, VALIDATION 8.9); used by sim/trial.py only
    _p("nov_detect_mult", 1.658, 1.0, 2.6, "-", S_NOV1, "analog",
       "time to see a trouble: novice / expert = 433.982 / 261.798 s = 1.658; range 1.03-2.62 from the group means "
       "+-1 SD (the number of participants is not in the pages read); a mock-up of an oil and gas facility, not a mine; "
       "multiplies only the people's own seeing and reacting, never the physics (ore arriving at the SAG, a lab sample)"),
    _p("nov_detect_sigma_ln", 0.112, 0.0, 0.25, "-", S_NOV1, "calc",
       "extra log-spread of the novice's seeing time (mean kept): sqrt(ln((1 + cv_n^2) / (1 + cv_e^2))), "
       "cv = SD / mean = 0.243 novices, 0.214 experts"),
    _p("nov_p_diag", 0.05, 0.009, 0.236, "-", S_NOV2, "analog",
       "a wrong diagnosis (the wrong crew or node is called first): students 1/20 = 0.05, Wilson 95 % 0.009-0.236; "
       "licensed operators 0/17 (upper bound 0.18); tiny samples, a nuclear simulator; the expert copy keeps 0"),
    _p("nov_p_step", 0.00473, 0.00099, 0.0079, "-", S_NOV2, "analog",
       "omission of one procedure step: students 14/2958 = 0.00473 (Wilson 0.0028-0.0079), licensed operators "
       "3/3038 = 0.00099; the low end of the range is the operators' rate"),
    _p("nov_steps", 10, 5, 20, "-", S_D5, "assumption",
       "steps of one call (find the trouble, name the crew, state the place, hand over, check the answer ...) "
       "that can be skipped; no source for the count"),
    _p("nov_stress_mult", 2.0, 1.0, 4.0, "-", S_NOV3, "analog",
       "both error probabilities x this at moderately high stress; THERP novice / skilled = 4 / 2 = 2, novice against "
       "optimum 4 (the upper end)"),
    _p("nov_stress_open", 2, 2, 3, "-", S_NOV3, "assumption",
       "moderately high stress = at least this many open troubles (this one included) when the call is made"),
    _p("issue_notice_lo_min", 5, 5, 5, "min", S_D5, "assumption", "loud issue noticed by alarm"),
    _p("issue_notice_hi_min", 15, 15, 15, "min", S_D5, "assumption"),
    _p("issue_horizon_h", 12, 12, 12, "h", S_OVOS + ", p. 26", "project", "to shift end, at most 12 h"),

    # ---------------- hidden causes ----------------
    _p("hc_per_shift", 1.0, 0.5, 2.0, "1/shift", S_D4, "assumption", "free run and calib only; one at a time"),
    _p("hc_found_lo_h", 4, 4, 4, "h", S_D4 + "; " + S_METSO_WP, "assumption", "lab finds the cause; lab composites every 6 h"),
    _p("hc_found_hi_h", 6, 6, 6, "h", S_D4 + "; " + S_METSO_WP, "assumption"),
    _p("hc_liner_wear_mult", 1.5, 1.2, 2.0, "-", S_D4 + "; " + S_KAZQ3_23, "assumption",
       "true wear rate x; a reline brought forward by two months on wear is reported"),
    _p("hc_liner_eta_loss", 0.04, 0.02, 0.06, "-", S_D4, "assumption", "SAG t/h loss while active"),
    _p("hc_cyclone_n", 1, 1, 2, "-", S_D4, "assumption", "clogged cyclones"),
    _p("hc_dose_drop", 0.40, 0.25, 0.50, "-", S_D7, "assumption", "true collector dose fall"),
    _p("hc_dose_ramp_min", 30, 15, 60, "min", S_D7, "assumption"),
    _p("hc_oxide_ascu_pp", 2.0, 1.0, 3.0, "pp", S_D4 + "; " + S_AKHM, "assumption",
       "ASCu above block estimate; Aktogay samples show oxidised Cu 0-2.94 % of Cu"),
    _p("hc_silent_per_shift", 0.5, 0.0, 1.5, "1/shift", S_D4, "assumption",
       "free run only: silent causes without a lab signal (SAG energy overspend, collector overdose, small "
       "return-water leak); own draw stream, one at a time; the draws of hc_per_shift do not change"),
    _p("hc_energy_frac", 0.10, 0.05, 0.15, "-", S_D4 + "; " + S_PINTO, "assumption",
       "SAG specific energy above what the ore needs (charge overload, coarse feed); size is ours, chosen so the "
       "module sees it within about an hour against the 12 % block-model error of A*b; at Sossego "
       "control lowered E by 5.84 % (literature, another plant)"),
    _p("hc_reagent_over", 0.40, 0.20, 0.60, "-", S_D7 + "; " + S_VAZIFEH, "assumption",
       "true collector dose above the setpoint while the flowmeter reads the setpoint; no recovery gain above "
       "the setpoint (dose_penalty_pp is 0 there); Sungun plant dosed 43 g/t of collectors against a 23 g/t lab "
       "optimum (analog, reference only)"),
    _p("hc_leak_frac", 0.03, 0.01, 0.06, "-", S_D4 + "; " + S_KUJAWA, "assumption",
       "silent return-water leak: share of the pond return lost, small enough to stay below the intake cap "
       "(no ore cut); seen only in the water balance"),
    # ---- features 5, 9, 14, 15, 8 (22.10.2026): season, weather, ball overuse, concentrate grade, start-up with people
    _p("season_winter_from_doy", 319, 305, 335, "day", "Bozshakol TSF, ATC Williams: decant water recovery in winter "
       "with temperature below -10 C for more than three months a year (analog, atcwilliams.com/projects/"
       "bozshakol-tsf-kazakhstan, opened 23.10.2026)", "assumption",
       "winter starts on this day of the year (15 Nov); the run takes the date of the model clock (AKT_SEASON=auto)"),
    _p("season_winter_to_doy", 74, 60, 90, "day", "same", "assumption", "winter ends on this day of the year (15 Mar)"),
    _p("winter_return_frac", 0.03, 0.01, 0.15, "-", "Bozshakol TSF (analog): winter return of decant water is "
       "difficult; the share is ours, no source gives it (Caijiaying, Mount Wright: ice in the ponds, no percentage)", "assumption",
       "winter: share of the pond return that does not reach the process (ice, frozen sections); the water stays in the pond. "
       "The winter touches the water balance only, not throughput or recovery (KAZ Minerals Q1 2019 p. 1: both sulphide "
       "plants at design throughput in winter)"),
    _p("wx_temp_winter_c", -10, -12, -9, "degC", S_NOAA, "analog",
       "mean air temperature of the winter window 15 Nov - 15 Mar (NOAA normals 1991-2020, Aktogay -9.05, Ayagoz "
       "-11.8; the former -15 was the January mean of Ayagoz)"),
    _p("wx_temp_summer_c", 18, 10, 25, "degC", "climate of East Kazakhstan, our rounding", "assumption",
       "mean air temperature outside winter"),
    _p("wx_temp_amp_c", 6, 2, 10, "degC", "our rounding", "assumption", "daily half-swing of the air temperature"),
    _p("wx_wind_mean_ms", 4.5, 3.0, 7.0, "m/s", "our rounding", "assumption", "mean wind speed at the tailings"),
    _p("wx_wind_sigma_ms", 2.2, 1.0, 3.5, "m/s", "our rounding", "assumption", "hourly spread of the wind speed"),
    _p("beach_dry_summer_pct", 55, 30, 80, "%", "our rounding", "assumption",
       "share of the tailings beach that is dry outside winter"),
    _p("beach_dry_winter_pct", 5, 0, 20, "%", "our rounding", "assumption", "dry beach in winter (snow, ice)"),
    _p("scen_dust_h", 6, 2, 12, "h", "our rounding", "assumption", "scenario dust: length of the windy dry spell"),
    _p("scen_leach_h", 8, 2, 12, "h", "our rounding", "assumption", "scenario leachcold: length of the cold spell on the leach pad"),
    _p("ox_cold_frac", 0.25, 0.10, 0.40, "-", S_OX, "analog",
       "share by which the cathode output falls below the level of the quarter during the scenario leachcold; the size is the fall of Q4 2024 against Q3 2024 (-25 %, a fact for that year, from fewer ore on the pads and colder conditions); applying it to a spell of hours is our choice"),
    _p("scen_dust_wind_ms", 11, 10, 20, "m/s", S_ERA5, "calc",
       "scenario dust: wind in the spell; fact: ERA5/Open-Meteo, calculation: median of the hourly wind in the 26 dusting events of 2018-2025 "
       "(dry 3 days, T above 0, no snow, wind 10 m/s or more) is 10.8, 90th percentile 12.2, hourly maximum 15.6 m/s; the earlier 14 m/s "
       "(an assumption) was reached for 3 h in 8 years and stays a rare maximum, not the typical event (VALIDATION.md 10.2)"),
    _p("scen_dust_dry_pct", 85, 60, 100, "%", "our rounding", "assumption", "scenario dust: dry beach in the spell"),
    _p("ball_media_gt", 800, 600, 1000, "g/t", S_CHILE_BALLS, "analog",
       "grinding media consumption per tonne of ore at the line; no Aktogay figure: analogs 754 g/t (Cyprus Pima, SAG + balls) "
       "and 925 g/t (Chile 2014, 390 + 535); HPGR of line 2 may lower it, unknown"),
    _p("hc_balls_frac", 0.25, 0.10, 0.50, "-", S_D4, "assumption",
       "silent overuse of grinding media above the norm (wrong charge, wear of the lifters); scenario balls:N"),
    _p("sens_balls_sigma", 0.03, 0.01, 0.06, "-", S_D4, "assumption",
       "relative noise of the daily media consumption reading (scale of the charge feeder)"),
    _p("hc_conc_drop_pp", 2.5, 1.0, 5.0, "pp", S_D4 + "; CommoFlow 26.08.2026: concentrates below 20 % Cu get a larger "
       "deduction (vendor blog)", "assumption",
       "concentrate grade lost to dilution in the cleaner (froth with gangue); same copper, more mass; scenario conc:N"),
    _p("scen_startup_after_min", 60, 45, 120, "min", S_D5, "assumption",
       "scenario startup: minutes after the mill stops until somebody gives the start command while people are inside"),
    _p("scen_startup_work_h", 3.0, 1.5, 6.0, "h", S_D5, "assumption",
       "scenario startup: length of the repair inside the ball mill (as rep_ball_h of the modules)"),
    _p("scen_startup_h", 1.0, 0.25, 2.0, "h", S_D5, "assumption",
       "scenario startup: how long the start command stays on unless the shift head cancels it by a call"),

    # ---------------- tier S of 23.10.2026: winter road, driver, cyclone roping, pH sensor, HPGR, mantle, oil ----------------
    # T1: the winter now touches the pit (haul speed), not the throughput of the plant (KAZ Minerals Q1 2019 p. 1)
    _p("scen_icy_h", 6, 2, 12, "h", S_KAZ_WINTER, "assumption",
       "scenario icy: length of the ice and snowstorm spell on the haul roads (KAZ Minerals names the risk, not its length)"),
    _p("scen_icy_wind_ms", 11, 10, 25, "m/s", S_ERA5, "calc",
       "scenario icy: sustained wind in the spell ('snowstorms and strong winds' - KAZ Minerals, Enhancing winter safety at Aktogay); "
       "fact: ERA5/Open-Meteo, calculation (proxy of a snowstorm: snowfall at T below 0 with wind 10 m/s or gusts 15 m/s): median 10.2, "
       "90th percentile 13.1 m/s, hourly mean wind of 16 m/s or more did not occur in 8 years (maximum 15.6), gusts of 16 m/s or more "
       "126 h a year; the earlier 16 m/s reads as a gust (VALIDATION.md 10.2)"),
    _p("scen_icy_temp_c", -5, -25, -5, "degC", S_ERA5, "calc",
       "scenario icy: air temperature in the spell; fact: ERA5/Open-Meteo, calculation: ice proxy hours median -1.9, snowstorm proxy "
       "median -4.5 (10th percentile -9.7), drifting-snow proxy minimum -8.2; T of -14 or below together with wind 10 m/s or more "
       "was 3 h in 8 years. The earlier -14 (January mean of Aktogay -13.7, NOAA 1991-2020) stays a 'severe frost' variant: "
       "`run.py trial --set scen_icy_temp_c=-14`; the stand has no separate scenario for it (VALIDATION.md 10.2)"),
    _p("pit_vis_clear_m", 10000, 5000, 20000, "m", "our rounding", "assumption", "visibility on the haul roads in clear weather"),
    _p("pit_vis_icy_m", 120, 40, 300, "m", S_KAZ_WINTER, "assumption", "visibility in the snowstorm spell (no figure in the source)"),
    _p("pit_grip_clear", 0.80, 0.60, 0.90, "-", "our rounding", "assumption",
       "tyre-road friction index of a dry haul road (index 0..1, not a measured coefficient)"),
    _p("pit_grip_winter", 0.55, 0.30, 0.75, "-", S_KAZ_WINTER, "assumption",
       "friction index of a haul road in the winter season with patches of ice"),
    _p("pit_grip_icy", 0.30, 0.10, 0.50, "-", S_KAZ_WINTER, "assumption", "friction index in the ice and snowstorm spell"),
    _p("pit_winter_cycle_mult", 1.0, 1.0, 1.15, "-", S_KAZ_WINTER, "assumption",
       "truck cycle multiplier in the winter season alone: 1 (no slowdown), because the sulphide plants ran at design throughput "
       "in winter (KAZ Minerals Q1 2019 p. 1); the season changes the road state (friction, visibility), the slowdown comes with "
       "the snowstorm spell (scenario icy)"),
    _p("pit_icy_cycle_mult", 1.20, 1.0, 1.60, "-", S_KAZ_WINTER, "assumption",
       "truck cycle multiplier in the ice and snowstorm spell (drivers slow down by themselves)"),
    _p("pit_restrict_cycle_mult", 1.12, 1.0, 1.50, "-", S_KAZ_WINTER, "assumption",
       "extra truck cycle multiplier while the traffic restriction is in force (speed limit): the price of the safety decision"),
    _p("pit_vis_min_m", 150, 50, 400, "m", S_KAZ_WINTER, "assumption",
       "threshold of the module: visibility at or below this on the haul roads is a hazard (set per site from its road rules)"),
    _p("pit_grip_min", 0.40, 0.20, 0.60, "-", S_KAZ_WINTER, "assumption",
       "threshold of the module: friction index at or below this is a hazard (set per site)"),
    _p("scen_fatigue_h", 1.0, 0.25, 4.0, "h", "our rounding", "assumption",
       "scenario fatigue: how long the alert of a tired driver / close approach stays on unless the dispatcher acts"),
    # excavator hydraulic oil contamination (EX01 Hitachi EX3600-6 has a contamination sensor, brochure p. 11)
    _p("pit_oil_start_pct", 40, 10, 70, "%", S_HITACHI36, "assumption",
       "contamination of the hydraulic oil as % of the alert level of the on-machine sensor, normal state"),
    _p("pit_oil_alert_pct", 100, 100, 100, "%", S_HITACHI36, "vendor", "the sensor alerts the operator at this level (by definition)"),
    _p("pit_oil_rise_h", 3.0, 1.0, 8.0, "h", S_ABDU, "assumption",
       "scenario oil: hours from the normal state to the alert level (the rate of contamination is not published)"),
    _p("pit_oil_fail_h", 8.0, 2.0, 24.0, "h", S_ABDU, "assumption",
       "scenario oil: hours from the alert to the failure of a hydraulic pump when nobody acts (about 70 % of hydraulic failures are "
       "contamination - Abduazizov 2026; the time is ours)"),
    _p("pit_oil_repair_h", 57.45, 20.0, 100.0, "h", S_ABDU, "analog",
       "repair of the hydraulic system after the failure: 57.45 h is the mean time to repair of the PC3000 (Komatsu) in the source, "
       "another model than the EX3600"),
    _p("pit_oil_fix_h", 2.0, 0.5, 6.0, "h", "our rounding", "assumption",
       "service of the oil (filtration, flushing) by the shift mechanic after the call; no OEM figure"),
    # T2: cyclone roping and ball mill overload (Kennecott, CiDRA; Centinela)
    _p("cyc_circ_base_pct", 250, 150, 400, "%", "our rounding", "assumption",
       "circulating load of a closed SAG-ball circuit in normal operation (typical range; Aktogay figure not published)"),
    _p("hc_rope_sev", 1.0, 0.3, 1.0, "-", S_CIDRA_KEN, "assumption", "scenario roping:N: severity at full development, 0..1"),
    _p("cyc_rope_ramp_min", 40, 10, 120, "min", S_CIDRA_KEN, "assumption", "roping develops over this time after the start"),
    _p("cyc_rope_p80_um", 45, 20, 100, "um", S_CIDRA_KEN, "assumption", "extra P80 of the cyclone overflow at full roping"),
    _p("cyc_rope_dp_frac", 0.25, 0.05, 0.60, "-", S_CIDRA_KEN, "assumption", "extra cyclone feed pressure at full roping, share"),
    _p("cyc_rope_circ_frac", 0.45, 0.10, 1.00, "-", S_CIDRA_KEN, "assumption", "extra circulating load at full roping, share"),
    _p("ball_rope_over_pct", 12, 3, 25, "%", S_CIDRA_KEN, "assumption", "ball mill draw above its rating at full roping (overload), %"),
    _p("cyc_rope_escalate_h", 1.5, 0.5, 4.0, "h", S_CIDRA_CEN, "assumption",
       "hours of roping without a decision after which the flotation feels it (heavy roping of one battery stopped a rougher line)"),
    _p("cyc_rope_flot_pp", 3.0, 1.0, 6.0, "pp", S_CIDRA_CEN, "assumption",
       "recovery loss of the line while a rougher line stands after heavy roping (one stopped line of several; the share is ours)"),
    _p("cyc_rope_flot_h", 6.0, 3.0, 8.0, "h", S_CIDRA_CEN, "analog",
       "length of the rougher line stop after heavy roping: about 6 h at Centinela (CiDRA, May 2014)"),
    # T3: pH sensor of the rougher flotation (ABB: abrasion and lime scale are the failure causes)
    _p("sens_an_clean_h", 0.5, 0.25, 2.0, "h", S_METSO_AN, "assumption",
       "scenario sample:N: cleaning of a blocked sample line of the on-stream analyser by the I&C technician (Metso Metrics names "
       "sample line blockage as a typical problem, no frequency, no repair time)"),
    _p("flot_ph_sp", 10.8, 9.5, 11.5, "pH", S_ABB_PH, "assumption",
       "pH setpoint of the rougher (lime control); the Aktogay value is not published"),
    _p("flot_ph_pp_unit", 2.0, 0.5, 4.0, "pp/pH", S_ABB_PH, "assumption",
       "total recovery lost per pH unit the real pH is above the setpoint (slurry over-limed while the sensor reads the setpoint)"),
    _p("hc_ph_drift", 0.6, 0.3, 1.2, "pH", S_ABB_PH, "assumption",
       "scenario phdrift: how far the real pH is above the reading when the electrode is scaled or worn"),
    _p("sens_ph_sigma", 0.05, 0.02, 0.15, "pH", S_ABB_PH, "assumption", "noise of the pH reading"),
    _p("sens_ph_lab_every_h", 4, 2, 8, "h", S_ABB_PH, "assumption", "grab sample with a hand-held pH meter (check of the online sensor)"),
    _p("sens_ph_lab_sigma", 0.08, 0.03, 0.20, "pH", S_ABB_PH, "assumption", "error of the hand-held pH meter"),
    _p("sens_ph_suspect_gap", 0.30, 0.15, 0.60, "pH", S_ABB_PH, "assumption",
       "the pH meter is published as SUSPECT when the grab sample differs from its reading by this much (the accuracy of a "
       "hand-held meter is about 0.1)"),
    # T4: HPGR of line 2, uneven feed (segregation), tramp metal
    _p("peb_hpgr_uneven_eff", 0.50, 0.30, 0.90, "-", S_METSO_HPGR, "assumption",
       "share of the HPGR throughput kept at full skew (the controller lowers the pressure and the feed); the real value is unknown"),
    _p("peb_hpgr_skew_pct", 12, 4, 25, "%", S_METSO_HPGR, "assumption",
       "roll gap skew at full uneven feed, % of the mean gap (the controller of the source intervenes at a few millimetres)"),
    _p("peb_hpgr_kwdiff_pct", 18, 5, 40, "%", S_METSO_HPGR, "assumption", "difference of the two drives' power at full skew, %"),
    _p("peb_hpgr_ramp_min", 20, 5, 60, "min", S_METSO_HPGR, "assumption", "uneven feed develops over this time"),
    _p("peb_hpgr_tramp_after_h", 2.0, 0.5, 6.0, "h", S_METSO_HPGR, "assumption",
       "hours of uneven feed without a repair after which tramp metal reaches the rolls and the metal detector stops the HPGR"),
    _p("peb_hpgr_stop_h", 4.0, 1.0, 12.0, "h", S_METSO_HPGR, "assumption", "HPGR stop after the metal detector trips (inspection of the studs)"),
    _p("peb_hpgr_fix_h", 1.5, 0.5, 4.0, "h", S_METSO_HPGR, "assumption", "median repair after the crew arrives (feed chute, cheek plates)"),
    _p("peb_hpgr_skew_alarm_pct", 6, 2, 12, "%", S_METSO_HPGR, "assumption", "threshold of the module: skew at or above this"),
    # C11: change of the mantle of the primary gyratory crusher
    _p("crush_mantle_h", 60, 24, 100, "h", S_METSO_MANTLE, "analog",
       "stop of the primary crusher for a mantle change: about 60 h at La Caridad (Metso case, 75-100 kt of ore not crushed); "
       "Aktogay figure not published"),

    # ---------------- sensors and control rule ----------------
    _p("sens_an_cycle_min", 15, 8, 16, "min", S_METSO_AN + "; " + S_AZO, "vendor",
       "on-stream analyser: vendor 12-16 min for a Courier 5X/6X SL (p. 12); a six-stream central analyser measures every stream "
       "once in 8 min (AZoMining, verified 24.10.2026), so 8 min is the lower bound; 15 min sits in the vendor interval"),
    _p("sens_an_feed_sigma", 0.03, 0.01, 0.06, "-", S_METSO_AN, "vendor",
       "relative; vendor: relative standard deviation 3-6 % for minor concentrations (the feed, 0.4 % Cu, is minor), 1-4 % for major ones; "
       "3 % is the better end of the minor figure"),
    _p("sens_an_tail_sigma", 0.05, 0.03, 0.10, "-", S_METSO_AN + "; " + S_REMES, "vendor",
       "relative; vendor: 3-6 % for minor concentrations (the tails, 0.05 % Cu, are minor); the upper edge 10 % is Remes et al. 2007 "
       "(1-10 %, random error); 5 % is inside the vendor interval. The analyser class of the Aktogay installation is not published"),
    _p("sens_an_conc_sigma", 0.03, 0.01, 0.06, "-", S_METSO_AN, "vendor",
       "relative; vendor: 1-4 % for major concentrations (the concentrate, 20-30 % Cu, is major); 3 % is inside, 6 % is the minor-concentration figure"),
    _p("sens_lab_every_h", 4, 4, 12, "h", S_D4 + "; " + S_METSO_WP, "assumption",
       "lab composites of rougher tails every 6 h at the vendor example (Metso whitepaper p. 6, one customer) and one composite "
       "per shift at Caraiba (NI 43-101 s. 17.6, analog); the value stays 4 h, the range is 4-12 h"),
    _p("sens_lab_delay_h", 2, 2, 2, "h", S_D4, "assumption",
       "lab result delay; only the titration is published (Cu concentrate, 12-15 min per titrator, Nucomat datasheet p. 6, "
       "verified 24.10.2026): sample preparation, queue and shift hand-over are not, so 2-24 h stay a sensitivity range (tornado)"),
    _p("sens_lab_sigma", 0.015, 0.01, 0.07, "-", S_D4 + "; " + S_GOST_LAB, "assumption",
       "relative; GOST R 56856-2016 table 1 gives about 7 % at 0.35 % Cu (tails 5-17 %): 1.5 % is optimistic"),
    _p("sens_weigher_sigma", 0.01, 0.005, 0.02, "-", S_D4 + "; " + S_OIML, "assumption", "relative; belt weigher class 1"),
    _p("sens_power_sigma", 0.003, 0.001, 0.005, "-", S_D4 + "; " + S_IEC, "assumption", "relative; meter class 0.2S-0.5S"),
    _p("sens_p80_sigma_um", 5, 3, 8, "um", S_D4 + "; " + S_PSI, "assumption"),
    _p("sens_dose_sigma", 0.02, 0.01, 0.04, "-", S_D4, "assumption", "dose flowmeter, relative"),
    _p("acs_tail_sp_pct", 0.075, 0.065, 0.090, "% Cu", S_D4 + "; " + S_OVOS_RK + ", p. 57", "assumption",
       "constant tails alarm setpoint; base tails 0.052-0.053 % (2024 balance), design 0.059 %; calib tunes to "
       "<= 1 false alarm per week. Philex (industrial, Jameson, 1996): tails 0.046-0.055 % Cu, in line with our 0.053 % for Aktogay 2025 [calc]; "
       "the source gives normal tails, not an alarm setpoint: label kept"),
    _p("acs_cycles", 2, 2, 2, "-", S_D4 + "; " + S_NIST, "assumption",
       "consecutive analyser cycles above setpoint; stricter than the WECO 2-of-3 rule"),

    # ---------------- scenario presets ----------------
    _p("scen_end_h", 20, 20, 20, "h", S_D2, "assumption", "auto pause at shift end"),
    _p("scen_fork_dose_h", 8.0, 8.0, 8.0, "h", S_D7, "assumption", "silent issue start"),
    _p("scen_fork_trip_h", 9 + 20 / 60, 9.0, 10.0, "h", S_D7, "assumption", "crusher-2 lube trip at 09:20"),
    _p("scen_fork_lab_h", 14.0, 12.0, 16.0, "h", S_D7, "assumption", "lab finds silent issue, no-twin copy"),
    _p("scen_fork_found_h", 9.25, 8.5, 12.0, "h", S_D7, "assumption",
       "module finds silent issue (seed 42 run, 09:15); used for the 'loud first' copy"),
    _p("scen_safety_min", 10, 10, 10, "min", S_D7, "assumption", "piezometer alarm after start"),
    _p("scen_hard_lead_h", 2.0, 1.0, 3.0, "h", S_D7, "assumption", "hard block dug after scenario start"),
    _p("asis_rope_see_min", 45, 30, 90, "min", S_D7, "assumption",
       "trial, copy 'как сейчас': the shift sees cyclone roping on the screens (circulating load) this long after the start; "
       "the call follows asis_notice_min later"),
    _p("asis_mantle_see_min", 10, 5, 20, "min", S_D7, "assumption",
       "trial, copy 'как сейчас': the shift sees a mantle change of the crusher this long after the start (the plant alarm "
       "calls it earlier; the twin of the symmetric base uses the alarm too)"),
    _p("scen_fire_line", 1, 1, 2, "-", S_KURSIV26, "fact", "scenario hpgr_fire: HPGR of concentrator 1"),
    _p("scen_fire_people", 20, 20, 20, "-", S_KURSIV26, "fact", "people evacuated (text of the S0 issue)"),
    _p("scen_fire_safety_h", 2, 0.5, 6, "h", S_D7, "assumption",
       "S0 while the area is evacuated and the fire is out (the press gives no duration)"),
    _p("scen_fire_h", 8, 2, 24, "h", S_D7, "assumption",
       "pebble circuit of the line down after the fire (inspection, repair); duration not published"),

    # ---------------- added by flotation ----------------
    _p("flot_reag_tank_t", 8.0, 4.0, 20.0, "t", S_D4, "assumption",
       "collector day tank of a line on load cells (no published size); refilled by deliveries"),
    _p("flot_reag_refill_frac", 0.25, 0.10, 0.50, "-", S_D4, "assumption",
       "the tank is refilled to full when it falls below this share; each delivery is booked (t)"),
    _p("sens_tank_sigma_t", 0.008, 0.004, 0.02, "t", S_D4, "assumption",
       "load cells of the day tank, about 0.1 % of its capacity, per reading"),
    _p("flot_conc_max_pct", 34.6, 30.0, 34.6, "% Cu", "CuFeS2 stoichiometry: Cu 63.55 / 183.5 g/mol",
       "assumption", "cap of the grade line at pure chalcopyrite"),

    # ---------------- added by events and sensors ----------------
    _p("scen_trip_lube_kpa", 100, 0, 140, "kPa", S_D7, "assumption",
       "faulty lube sensor reading in the fork preset (below crush_lube_trip_kpa)"),
    _p("sens_flow_sigma", 0.01, 0.005, 0.03, "-", S_D4, "assumption", "water and pulp flowmeters, relative"),
    _p("sens_an_stale_cycles", 2, 1, 4, "-", S_D4, "assumption",
       "analyser reading older than this many cycles: instrument state SUSPECT"),

    # ---------------- added by plant ----------------
    _p("sens_lab_find_frac", 0.15, 0.10, 0.25, "-", S_D5, "assumption",
       "lab tails above the expectation at the lab feed grade that reveal a flotation loss (dose drift +27 %)"),
    _p("sens_lab_find_ascu_pp", 1.5, 1.0, 2.5, "pp", S_D5, "assumption",
       "lab ASCu above the block-model estimate of the feed that reveals oxidised ore"),
    _p("scen_piezo_over_kpa", 5, 1, 20, "kPa", S_D7, "assumption",
       "safety scenario: dam piezometer reading above pond_piezo_sp_kpa"),
    _p("cal_draw_chunk_h", 168, 24, 720, "h", S_D2, "assumption",
       "horizon of lazily drawn pebble stop windows; drawn from the run origin, results do not depend on it"),

    # ---------------- added by calib ----------------
    _p("tol_fit_frac", 0.005, 0.001, 0.01, "-", S_D4, "assumption",
       "fit rows: relative tolerance of ore, SAG P/Q, 2024 electricity and water; ore match of 2024, 2023"),
    _p("tol_fit_rec_pp", 0.1, 0.05, 0.2, "pp", S_D4, "assumption", "fit row: 2025 recovery"),
    _p("cal_fit_runs", 4, 2, 6, "-", S_D4, "assumption", "max annual runs per fit (joint secant)"),
    _p("cal_secant_trust", 5.0, 2.0, 10.0, "-", S_D4, "assumption",
       "secant slope used only within [1/x, x] of the structural slope, else the structural slope"),
    _p("cal_quick_step_min", 30, 10, 60, "min", S_D4, "assumption", "calib --quick step (tests)"),
    _p("cal_q_warmup_d", 14, 7, 30, "d", S_D4, "assumption",
       "quarter run starts this many days before the quarter (stockpile, lags, block pipeline)"),
    _p("cal_week_days", 7, 7, 7, "d", S_D10, "assumption", "free-run check length"),
    _p("cal_week_step_min", 5, 1, 10, "min", S_D10, "assumption",
       "free-run check step (module tact cal_checkpoint_min)"),
    _p("tol_week_stock_lo_pct", 10, 10, 10, "%", S_D10, "assumption",
       "free-run check: stockpile level band low, % of stock_live_t"),
    _p("tol_week_stock_hi_pct", 90, 90, 90, "%", S_D10, "assumption",
       "free-run check: stockpile level band high, % of stock_live_t"),
    _p("tol_week_false_alarms", 1, 1, 1, "1/week", S_D4, "assumption",
       "ACS tails alarms with no hidden cause on the line, both lines"),
    _p("cal_budget_s", 240, 240, 240, "s", S_D9, "assumption", "make akt-calib wall time limit"),
    _p("tol_week_resets", 1, 1, 1, "-", S_D10, "assumption",
       "free-run check: shift resets may differ by the edge shift at the run end"),
    _p("cal_alarm_lags", 3, 2, 5, "-", S_D4, "assumption",
       "flotation lags (flot_tau_min) after a hidden cause ends during which an ACS alarm is still its own"),
    _p("tol_grade_round_pct", 0.005, 0.005, 0.005, "% Cu", S_KAZ25, "calc",
       "half of the last digit of a report grade (0.01 % Cu): model feed grade rows"),
]

from . import params_t  # noqa: E402  (tier T rows, 24.10.2026)
_ROWS.extend(_p(*_r) for _r in params_t.ROWS)

from . import params_lev as _params_lev  # noqa: E402  - rows of the what-if levers (after Param and _p exist)
_ROWS.extend(_params_lev.ROWS)

TABLE: dict[str, Param] = {}
for _row in _ROWS:
    if _row.key in TABLE:
        raise ValueError("duplicate parameter key: " + _row.key)
    TABLE[_row.key] = _row


# What the report says about a planned SAG stop; the model treats every kind as a SAG stop of
# liner_reline_h with a new liner afterwards (that is an assumption for the last two kinds).
RELINE_KINDS = ("reline", "sag_service", "stop")


@dataclass(frozen=True)
class Reline:
    """Planned SAG stop from the report calendar.

    kind: "reline" when the report names a SAG reline, "sag_service" when it
    names planned SAG maintenance, "stop" when it names planned maintenance of
    the plant without the kind of work (the SAG reline is then our assumption).
    label: evidence for the event and its month ("fact" by the report,
    "assumption" when the quarter itself is our choice). The day of month is
    always an assumption (day_assumed).
    """
    line: int
    year: int
    month: int
    day: int
    source: str
    label: str
    kind: str = "reline"
    day_assumed: bool = True


RELINE_CALENDAR: tuple[Reline, ...] = (
    Reline(1, 2024, 3, 15,
           S_KAZQ1_24 + ": planned maintenance of the quarter, 'including a SAG mill reline'; the quarter is the report's, "
           "the month and the day are assumed (line 1 tonnes rose in Q2: 6 921 vs 6 751 kt)",
           "fact", "reline"),
    Reline(2, 2024, 10, 15,
           S_KAZ24 + ": planned SAG maintenance at Sulphide 2 in October 2024, line 2 tonnes -4 % (7 244 vs 7 572 "
           "kt); 'reline' is not the report's word; day assumed",
           "fact", "sag_service"),
    Reline(2, 2025, 8, 15,
           S_KAZQ3 + ": SAG reline at Sulphide 2 in August 2025, named in the report; day assumed",
           "fact", "reline"),
    Reline(1, 2025, 12, 5,
           S_KAZ25 + ": planned maintenance at both concentrators in December 2025, kind of work not disclosed; "
           "SAG reline and day are assumptions",
           "fact", "stop"),
    Reline(2, 2025, 12, 15,
           S_KAZ25 + ": planned maintenance at both concentrators in December 2025, kind of work not disclosed; "
           "SAG reline and day are assumptions",
           "fact", "stop"),
)


# Feature -> rule, per thing type (design section 4: every feature has a rule).
FEATURE_RULES: dict[str, dict[str, str]] = {
    "site": {
        "state": "RUN/PAUSED/WARMUP (service: run control)",
        "speed": "service: requested model speed", "speed_fact": "service: achieved speed",
        "seed": "run seed", "tph": "sum of line t/h", "cu_tph": "sum of line Cu in concentrate t/h",
        "power_mw": "power.site_mw", "water_m3h": "water.intake_m3h", "scenario": "active scenario text",
        "heartbeat": "service: wall clock tick in pause", "degraded": "service: barrier timeout flag",
        "lever_on": "1 while a what-if lever (control of the model, not of the plant) is in force on the fact copy",
        "lever_feed_1": "lever: feed rate of SAG line 1, % of the nominal line rate (100 = neutral)",
        "lever_feed_2": "lever: feed rate of SAG line 2, % of the nominal line rate (100 = neutral)",
        "lever_p80_um": "lever: grind P80 target, um (-1 = off)", "lever_dose_gt": "lever: collector dose, g/t (-1 = off)",
    },
    "pit": {
        "state": "RUN/STOP",
        "mining_tph": "fleet.mining_tph", "next_block": "next block number in plan",
        "plan_text": "12 h plan of blocks per line", "hard_in_plan": "1 if est A*b < ui_axb_hard in plan",
        "visibility_m": "visibility on the haul roads (pit_vis_clear_m; a snowstorm spell lowers it to pit_vis_icy_m)",
        "road_grip": "friction index of the haul roads 0..1 (dry, winter season with ice, snowstorm spell)",
        "haul_speed_pct": "haul speed against the dry road, % (100 / truck cycle multiplier of weather and restriction)",
        "road_restrict": "1 while the traffic restriction (speed limit) is in force after the decision of the mine dispatcher",
    },
    "exc": {"state": "DIG/MOVE/IDLE/DOWN", "tph": "dig rate", "block": "batch being dug", "bench": "bench number",
            "oil_pct": "hydraulic oil contamination, % of the alert level of the on-machine sensor (EX3600-6 has one); -1 where "
                       "no source confirms a sensor",
            "oil_alert": "1 from the alert level of the sensor (the operator sees it; transmitted only with the optional "
                         "Global e-Service), -1 without a sensor"},
    "batch": {
        "state": "PLANNED/DIG/BELT/IN_STOCK/DONE by the last tonne: DIG while any is in the pit, BELT while any "
                 "is in transit, IN_STOCK when all is on the stockpile",
        "location": "current parent thing",
        "tonnes_left": "t not yet fed to SAG (weigher accounting)", "pit_t": "t still in the pit (not dug)",
        "cu_meas": "lab feed Cu of the sample taken while the batch led the SAG feed",
        "axb_soft": "soft sensor A*b from SAG P and Q",
    },
    "crusher": {"state": "RUN/STOP/SLOW", "tph": "min(pocket, capacity, stock room)",
                "power_kw": "crush_power_mw when RUN", "lube_kpa": "norm + noise; trip below setpoint",
                "service": "1 while the planned change of the mantle stops the crusher (scenario mantle:N)",
                "service_left_h": "hours to the end of the mantle change (plan), -1 when none"},
    "conveyor": {"state": "RUN/STOP", "tph": "= crusher t/h", "power_kw": "conv_power_mw when RUN",
                 "fault": "1 while the belt is tripped (scenario conveyor:N, crew-cpd repairs); 0 when it stands only because no ore comes"},
    "stockpile": {"state": "NORMAL/LOW/EMPTY/FULL: LOW below stock_low_frac, EMPTY below stock_empty_t, FULL at "
                           "stock_full_frac of stock_live_t",
                  "level_t": "column + sides", "in_tph": "belt delivery", "out_tph": "SAG draw",
                  "hours_left": "level / (out - in) when falling, else -1"},
    "line": {"state": "RUN/LIMITED/STOP: STOP while the SAG is RELINE or STOP, LIMITED under a power cap or with "
                      "one ball mill",
             "tph": "SAG fresh feed", "cu_tph": "Cu in concentrate", "recovery": "flot recovery",
             "cum_cu_t": "shift Cu", "cum_mwh": "shift energy", "cum_m3": "shift water intake share",
             "cum_usd": "shift value: payable Cu - energy - water",
             "cum_cu_t_total": "run total of cum_cu_t (never reset)", "cum_mwh_total": "run total of cum_mwh",
             "cum_m3_total": "run total of cum_m3", "cum_usd_total": "run total of cum_usd",
             "balls_gt": "grinding media consumption of the line (scale reading), g/t of ore"},
    "sag": {"state": "RUN/STARVED/LIMITED_GRID/RELINE/STOP",
            "power_kw": "Austin form of load and speed (shaft), not below the ball-charge draw",
            "power_limit_kw": "min(rated, grid cap)", "feed_tph": "Q = min(stock, eta P / E, pebble limit)",
            "speed_pct": "setpoint; lowered when a power cap is below the ball-charge draw",
            "load_pct": "mass balance, tau 5 min; not below the ball charge; kept in STOP",
            "e_kwh_t": "power / Q",
            "axb_soft": "A*b back-solved from E",
            "liner_wear_mm": "feed-end counter by norm 20.41 mm/Mt; restarts at feed-end changes and relines",
            "liner_ground_t": "ore ground since the last reline, t (tonnage counter by norm, restarts at a reline); "
                              "the module forecasts the liner campaign from it"},
    "ball": {"state": "RUN/STOP", "power_kw": "ball_power_mw when RUN",
             "start_cmd": "1 while a start command is on although people may be inside (scenario startup)",
             "e_kwh_t": "power x running mills / Q (each running mill grinds Q / n)",
             "power_pct": "motor draw as % of the rating: 100 in normal grinding, up by ball_rope_over_pct at full cyclone "
                          "roping (overload), 0 while the mill stands"},
    "cyclones": {"state": "NORMAL/UPSET: UPSET if |dp/p0| above cyc_upset_frac",
                 "p80_um": "Bond grind (not finer than ball_p80_min_um) + 12 um per clogged unit",
                 "pressure_kpa": "p0 (Q/open)^2 x clog rise",
                 "open_count": "open units (clog not visible)",
                 "circ_load_pct": "circulating load of the ball mill circuit (underflow / fresh feed), cyc_circ_base_pct, "
                                  "up by cyc_rope_circ_frac at full roping"},
    "flot": {"state": "RUN/UPSET/STOP",
             "feed_cu": "analyser", "tail_cu": "analyser", "conc_cu": "analyser", "recovery": "R_r x R_c",
             "cu_tph": "Cu in concentrate", "conc_tph": "concentrate solids"},
    "rougher": {"state": "RUN/UPSET/STOP",
                "feed_tph": "line Q", "stage_recovery": "R_inf (1 - exp(-k tau))",
                "mass_pull_pct": "7 % x g / g0", "rconc_cu": "rougher concentrate grade",
                "residence_min": "tau0 x Q0 / Q", "dose_sp_gt": "setpoint", "dose_meas_gt": "flowmeter reading",
                "tank_t": "collector day tank, load cells (noise sens_tank_sigma_t)",
                "tank_in_t_total": "deliveries into the tank since the start (booked, exact)",
                "dose_t_total": "flowmeter totalizer: reading x Q x dt since the start"},
    "cleaner": {"state": "RUN/UPSET/STOP",
                "feed_tph": "rougher concentrate", "stage_recovery": "97 % - 1 pp per 10 pp extra pull",
                "conc_cu": "24.3 - 0.5 (R - R0 - feed-grade gain)", "conc_tph": "g R / grade",
                "tail_cu": "cleaner tails grade"},
    "water": {"state": "NORMAL/LOW/SHORT/ALARM: ALARM at piezo_kpa >= pond_piezo_sp_kpa, SHORT while the fresh "
                       "water is at its supply cap and the ore is cut, LOW below pond_lo_m3",
              "intake_m3h": "process - recycle (not above water_intake_cap_m3h)",
              "recycle_m3h": "pond return delivered + thickener overflow",
              "tails_loss_m3h": "0.31 m3/t pore water of settled tails", "evap_m3h": "fitted",
              "pond_m3": "integrated",
              "residual_pct": "balance closure", "piezo_kpa": "a x pond + noise",
              "intake_m3_total": "intake flowmeter totalizer since the start (noisy rate x dt)",
              "loss_m3_total": "tails pores + concentrate moisture + evaporation, integrated (a leak is not "
                               "metered: it shows as the balance residual)",
              "leak_m3h": "return water lost through a pipeline leak: truth only, measured -1 (no meter on a leak)",
              "air_temp_c": "weather: season mean + daily swing", "wind_ms": "weather: hourly draw",
              "beach_dry_pct": "dry share of the tailings beach (season, wind spell)",
              "winter": "1 while the winter return loss is on (season or scenario winter)",
              "short_m3h": "process water missing above the intake cap",
              "cut_tph": "ore held back on both lines for lack of water",
              "intake_cap_m3h": "fresh-water supply cap"},
    "power": {"state": "NORMAL/LIMITED: LIMITED while the grid limit is below the normal limit",
              "grid_limit_mw": "300 or scenario", "site_mw": "mills (grid) + crushers + conveyors + other",
              "grinding_mw": "mills from grid", "grinding_shaft_mw": "mills on shaft",
              "other_mw": "fitted site part + pow_line_aux_mw per running line",
              "shed_mw": "load shedding", "headroom_mw": "limit - site",
              "shed_text": "connections shed by the automatic load shedding, in order (codes)"},
    "crew": {"state": "FREE/TRAVEL/WORK/OFF", "task": "issue node", "free_at": "model minute when free"},
    "fleet": {"state": "NORMAL/SHORT: SHORT when haul_tph is below the mining need",
              "exc_total": "count (ore and stripping)", "exc_ready": "not DOWN", "trucks_total": "37 by model",
              "trucks_ready": "each truck ready with fleet_kio, drawn hourly", "truck_kio_shift": "shift mean ready share",
              "haul_tph": "ready ore trucks x payload x 60 / cycle", "mining_tph": "min(excavators, haul, regulator)",
              "trucks_ore": "ready trucks on ore", "waste_tph": "stripping rate (waste trucks and excavators)",
              "fatigue": "1 while the alert of a tired driver / close approach of a truck is on (scenario fatigue; "
                         "assumption: no confirmed source for the sensor)",
              "fatigue_truck": "bort number and model of the truck in the alert, empty when none"},
    "pebble": {"state": "RUN/LIMIT/STOP", "feed_tph": "p(A*b) x Q", "limit_tph": "740 (line 2: min with its HPGR 1 061)",
               "load_pct": "feed / limit", "fire": "1 while a fire at the HPGR of the circuit is not out",
               "hpgr_tph": "rated HPGR throughput (line 2: peb_hpgr_l2_tph; line 1: no published rating, -1)",
               "hpgr_load_pct": "feed / hpgr_tph (line 2), -1 on line 1",
               "hpgr_kw": "peb_hpgr_l2_kw x min(1, feed / hpgr_tph), 0 while the circuit stands, -1 on line 1",
               "hpgr_skew_pct": "roll gap skew of the HPGR, % of the mean gap (line 2), 0 in normal feed, -1 on line 1",
               "hpgr_kw_diff_pct": "difference of the power of the two HPGR drives, % (line 2), -1 on line 1",
               "metal_alarm": "1 when the metal detector in front of the HPGR tripped (line 2), -1 on line 1"},
    "person": {"state": "FREE/TRAVEL/WORK/OFF: OFF while evacuated or off shift",
               "location": "thing where the person is (home node when free)", "task": "node of the job or decision",
               "free_at": "model minute when free",
               "permit": "node of the work permit (nariad-dopusk) while the person works inside equipment, else empty"},
    "truck": {"state": "LOADING/HAUL_FULL/QUEUE/DUMP/RETURN/DOWN: cycle phase, QUEUE while its line digs nothing",
              "location": "face, road or crusher", "load_t": "payload on board", "cycle_min": "trip time now",
              "duty": "ore line N or waste"},
    "face": {"state": "ACTIVE/IDLE/DOWN by its excavator", "block": "batch being dug",
             "est_cu": "block-model Cu of the block", "est_axb": "block-model A*b", "hardness": "class by A*b",
             "bench": "bench number", "tph": "dig rate",
             "blasted_t": "blasted rock ready to dig: + drill rigs (holes x t per hole), - excavator"},
    "drill": {"state": "DRILLING/MOVING/IDLE/DOWN: IDLE while its face holds pit_face_blasted_max_t",
              "location": "face drilled", "holes_shift": "holes drilled this shift"},
    "dozer": {"state": "WORK/IDLE/DOWN", "location": "face or road it works on"},
    "road": {"state": "OPEN/CLOSED", "trucks_on": "trucks on the road now", "cycle_mult": "trip time multiplier"},
    "analyzer": {"state": "OK/DRIFT/SUSPECT: SUSPECT when the reading is stale or the section stands",
                 "feed_cu": "reading", "tail_cu": "reading", "conc_cu": "reading", "age_min": "minutes since reading"},
    "weigher": {"state": "OK/DRIFT/SUSPECT", "tph": "belt weigher", "total_t": "totalizer since the start"},
    "phmeter": {"state": "OK/DRIFT/SUSPECT: SUSPECT when the grab sample differs from the reading by sens_ph_suspect_gap; DRIFT once "
                         "a pH drift is confirmed (the electrode is scaled by lime or worn)",
                "ph": "online reading; the control holds it at the setpoint, so a scaled electrode still reads the setpoint",
                "sp_ph": "setpoint (flot_ph_sp)", "lab_ph": "last grab sample with a hand-held meter (check value)",
                "age_min": "minutes since the grab sample (the online reading is continuous)"},
    "flowmeter": {"state": "OK/DRIFT/SUSPECT: DRIFT once a collector dose drift is confirmed, SUSPECT while the "
                           "tails alarm is on and the meter reads the setpoint",
                  "dose_gt": "reading", "sp_gt": "setpoint"},
    "piezometer": {"state": "OK/DRIFT/SUSPECT", "kpa": "pore pressure", "level_m": "kPa / 9.81",
                   "sp_kpa": "safety setpoint (S0)", "alarm": "1 at or above the setpoint"},
    "thick": {"state": "NORMAL/HIGH/FULL: HIGH at thick_high_frac of thick_cap_t, FULL at the capacity",
              "feed_tph": "cleaner concentrate", "underflow_tph": "min(in + inv / dt, filter cap)",
              "inventory_t": "integrated", "solids_pct": "underflow", "overflow_m3h": "feed water - underflow water",
              "hours_to_full": "(cap - inv) / (in - out)",
              "feed_t_total": "feed weigher totalizer since the start (noisy rate x dt)",
              "underflow_t_total": "underflow weigher totalizer since the start (noisy rate x dt)"},
    "filter": {"state": "RUN/ONE/STOP: ONE while one press changes cloth",
               "presses_on": "2, or 1 during cloth change", "cake_tph": "dry cake", "moisture_pct": "8 % + noise",
               "limit_tph": "presses_on x 35"},
    "leach": {"state": "NORMAL/COLD: COLD while the scenario leachcold lasts (cold spell on the heap leach pad)",
              "quarter_cathode_kt": "cathode of the model quarter, kt, from the reports (kaz_quarterly.csv); a date after 2025 takes the same quarter of 2025",
              "level_tph": "quarter cathode / hours of the quarter; the reported quarters already hold the season",
              "cold_frac": "0 in NORMAL, ox_cold_frac in COLD"},
    "sxew": {"state": "NORMAL/LOW: LOW while the leach pad is COLD",
             "cathode_tph": "level_tph x (1 - cold_frac); a quarterly figure of the reports, not a measurement",
             "cathode_level_tph": "level_tph of the quarter", "cathode_t_total": "integrated since the start of the run",
             "year": "year of the quarter used", "quarter": "quarter 1..4"},
    "conc-stock": {"state": "NORMAL/HIGH/FULL: HIGH at cstock_high_frac of cstock_cap_t, FULL at the capacity",
                   "stock_t": "integrated, wet", "in_tph": "cake / (1 - moisture)",
                   "shipped_t_shift": "trains at 06:00 and 18:00", "wagons_shift": "wagons loaded",
                   "hours_to_full": "(cap - stock) / net in"},
}
for _t, _fe in params_t.FEATURES.items():
    FEATURE_RULES[_t].update(_fe)
# Every type also carries its state as a Russian word for display (the machine code stays in "state").
for _rules in FEATURE_RULES.values():
    _rules["state_ru"] = "state in Russian words (display)"


class ParamSet:
    """Mutable copy of table values for one run (calibration overrides)."""

    __slots__ = ("_v", "_memo")

    def __init__(self, overrides: dict[str, float] | None = None):
        self._memo: dict = {}
        self._v = {k: p.value for k, p in TABLE.items()}
        for k, v in (overrides or {}).items():
            self.set(k, v)

    def __getitem__(self, key: str) -> float:
        return self._v[key]

    def __contains__(self, key: str) -> bool:
        return key in self._v

    def get(self, key: str, default: float | None = None) -> float | None:
        return self._v.get(key, default)

    def set(self, key: str, value: float) -> None:
        if key not in TABLE:
            raise KeyError("unknown parameter: " + key)
        self._v[key] = float(value)
        if self._memo:
            self._memo = {}                      # derived results (sim/haul.py) are valid for one set of values

    def memo(self, key, fn):
        """Result of fn() kept until any value of this set changes (derived numbers computed every step)."""
        try:
            return self._memo[key]
        except KeyError:
            v = self._memo[key] = fn()
            return v

    def copy(self, **overrides: float) -> "ParamSet":
        out = ParamSet()
        out._v = dict(self._v)
        for k, v in overrides.items():
            out.set(k, v)
        return out

    def overrides(self) -> dict[str, float]:
        """Keys whose value differs from the table."""
        return {k: v for k, v in self._v.items() if v != TABLE[k].value}

    def as_dict(self) -> dict[str, float]:
        return dict(self._v)


def default() -> ParamSet:
    return ParamSet()


def value(key: str) -> float:
    return TABLE[key].value


_PREFIX_USE = (
    ("w_", "wear (tier T), modules"),
    ("econ_", "economics (utilities)"), ("cal_", "plant, calib"), ("tgt_", "calib"), ("tol_", "calib"),
    ("pit_", "ore"), ("fleet_", "ore"), ("blk_", "ore"), ("ore_", "ore, comminution"), ("ui_", "web"),
    ("crush_", "comminution, ore"), ("conv_", "ore"), ("stock", "ore"), ("sag_", "comminution"),
    ("liner_", "comminution"), ("peb_", "comminution, events"), ("ball_", "comminution"),
    ("cyc_", "comminution"), ("flot_", "flotation"), ("clean_", "flotation"), ("thick_", "flotation"),
    ("filt_", "flotation"), ("cstock_", "flotation"), ("water_", "utilities"), ("pond_", "utilities"),
    ("pow_", "utilities"), ("crew_", "events"), ("nov_", "trial (novice policy)"), ("ox_", "oxide line (sim/oxide.py)"), ("issue_", "events, modules"), ("hc_", "events"),
    ("sens_", "sensors"), ("acs_", "sensors"), ("scen_", "events, plant"),
    ("lev_", "levers (plant, service)"), ("asis_", "trial (the copy as now)"),
    ("season_", "utilities, plant"), ("winter_", "utilities"), ("wx_", "utilities"), ("beach_", "utilities"),
)


def used_in(key: str) -> str:
    for prefix, where in _PREFIX_USE:
        if key.startswith(prefix):
            return where
    return ""


def check_param(p: Param) -> list[str]:
    """Problems of one row: label, unit, source, finite value inside [min, max], known prefix."""
    problems = []
    if p.label not in LABELS:
        problems.append(f"{p.key}: bad label {p.label!r}")
    if not isinstance(p.unit, str) or not p.unit.strip():
        problems.append(f"{p.key}: unit required")
    if not isinstance(p.source, str) or not p.source.strip():
        problems.append(f"{p.key}: source required")
    if not all(math.isfinite(x) for x in (p.value, p.min, p.max)):
        problems.append(f"{p.key}: value, min or max not finite")
    else:
        if p.min > p.max:
            problems.append(f"{p.key}: min {p.min} above max {p.max}")
        if not (p.min <= p.value <= p.max):
            problems.append(f"{p.key}: value {p.value} outside [{p.min}, {p.max}]")
    if not used_in(p.key):
        problems.append(f"{p.key}: unknown prefix")
    return problems


def check_reline(r: Reline) -> list[str]:
    """Problems of one calendar entry: label, kind, source, line, month."""
    problems = []
    where = f"reline {r.line} {r.year}-{r.month:02d}"
    if r.label not in LABELS:
        problems.append(f"{where}: bad label {r.label!r}")
    if r.kind not in RELINE_KINDS:
        problems.append(f"{where}: bad kind {r.kind!r}")
    if not isinstance(r.source, str) or not r.source.strip():
        problems.append(f"{where}: source required")
    if r.line not in (1, 2) or not 1 <= r.month <= 12 or not 1 <= r.day <= 31:
        problems.append(f"{where}: bad line, month or day")
    return problems


def check_table() -> list[str]:
    """Return a list of problems (empty when the table is consistent)."""
    problems = []
    for p in _ROWS:
        problems += check_param(p)
    for r in RELINE_CALENDAR:
        problems += check_reline(r)
    return problems


def _fmt(x: float) -> str:
    if x == int(x) and abs(x) < 1e7:
        return str(int(x))
    return f"{x:.6g}"


def markdown_rows() -> list[str]:
    """Rows of the PARAMETERS.md table (header included)."""
    rows = [
        "| Key | Value | Min | Max | Unit | Label | Fit | Used in | Source | Note |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for p in _ROWS:
        rows.append(
            f"| `{p.key}` | {_fmt(p.value)} | {_fmt(p.min)} | {_fmt(p.max)} | {p.unit} | {p.label} | "
            f"{'yes' if p.fit else ''} | {used_in(p.key)} | {p.source} | {p.note} |"
        )
    return rows


def markdown(with_modules: bool = True) -> str:
    """PARAMETERS.md: the simulator table, the SAG stop calendar, the feature rules and (when the
    modules package is importable, as in the repository) the table of the analysis modules.

    Passport entries with the source "assume" (label assumption) point to this file.
    """
    lines = ["# PARAMETERS", "",
             "Generated by `python -I aktogay/run.py params --md aktogay/PARAMETERS.md` from `sim/params.py`"
             " and `modules/params.py`. Do not edit by hand; `tests/test_params.py` checks that it is current.",
             "", "Labels: fact (company reports), vendor, project (OVOS 2018), analog, assumption, calc. "
             "Passport entries of the twins with the source \"assume\" are the assumption rows below.", "",
             "## Simulator (sim/params.py)", ""]
    lines += markdown_rows()
    lines += ["", "## SAG stop calendar (relines and planned maintenance)", "",
              "| Line | Date | Kind | Label | Source |", "|---|---|---|---|---|"]
    for r in RELINE_CALENDAR:
        lines.append(f"| {r.line} | {r.year}-{r.month:02d}-{r.day:02d} | {r.kind} | {r.label} | {r.source} |")
    lines += ["", "## Feature rules", "", "| Type | Feature | Rule |", "|---|---|---|"]
    for t, feats in FEATURE_RULES.items():
        for f, rule in feats.items():
            lines.append(f"| {t} | `{f}` | {rule} |")
    if with_modules:
        try:
            from modules import params as mparams
        except ImportError:
            mparams = None
        if mparams is not None:
            lines += ["", "## Analysis modules (modules/params.py: akt-losses, akt-ore, akt-priority)", "",
                      "| Key | Value | Min | Max | Unit | Label | Source | Note |", "|---|---|---|---|---|---|---|---|"]
            for p in mparams.PARAMS:
                lines.append(f"| `{p.key}` | {_fmt(p.value)} | {_fmt(p.min)} | {_fmt(p.max)} | {p.unit} | {p.label} | "
                             f"{p.source} | {p.note} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Aktogay parameter table")
    ap.add_argument("--md", help="write PARAMETERS.md to this path")
    ap.add_argument("--check", action="store_true", help="print table problems")
    a = ap.parse_args(argv)
    if a.md:
        with open(a.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(markdown())
        print(f"wrote {a.md}: {len(_ROWS)} parameters")
    probs = check_table()
    if a.check or not a.md:
        print("\n".join(probs) if probs else f"ok: {len(_ROWS)} parameters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
