"""«Изнутри»: what stands inside the ore, the dam, the people, the machines, the plant and the environment, by which signals it is
seen, where each signal is seen, which failures are known and from which source (decision of 23.10.2026, second level, click card).

One table for the page «Изнутри» (`web/static/inside.json`, written by this module, a test keeps it equal to the code). Depth is the
evidence level of the node: A - nodes, signals and failures with a source; B - nodes, failures by analog or assumption; C - only
the general state. Every signal says where it is seen:

  machine     on the machine, seen by the driver or the operator (a gauge, a lamp, a message centre)
  sent        sent to the control room only if the option is connected (telemetry service, data logger download)
  analog      a sheet of another model of the same maker (the stand does not claim it for its own machine)
  dcs         in the plant control system or the dispatch system of the pit
  lab         laboratory or grab sample
  model       a calculation of the twin, not a measurement
  assumption  no source confirms it

Only items marked confirmed in facts_round2.md («Проверка 23.10.2026», «Датчики — проверка 23.10.2026», part C) are given as facts;
items with a stated caveat carry it; an unconfirmed item is an assumption. Nothing here is a number of the model: the live numbers of the page
come from Ditto.

  python -I modules/inside.py --write-json web/static/inside.json
"""
from __future__ import annotations

import json
import sys

WHERE_RU = {
    "machine": "на машине (видит водитель / оператор)",
    "sent": "передаётся, если подключена опция",
    "analog": "аналог другой модели",
    "dcs": "в АСУ ТП или диспетчерской системе",
    "lab": "лаборатория / ручная проба",
    "model": "расчёт двойника (не измерение)",
    "assumption": "допущение: источник не подтверждён",
}
LABELS = ("факт", "вендор", "проект", "аналог", "допущение", "расчёт")
DEPTH_RU = {
    "A": "уровень A: узлы, сигналы и отказы с источником",
    "B": "уровень B: узлы известны, отказы — по аналогу или допущению",
    "C": "уровень C: только общее состояние",
}

U_VESTI = "https://vestisemey.kz/15404/kaz-minerals-aktogay-tsifrovye-i-innovatsionnye-vozmozhnosti-industrialnogo-proizvodstva.html"
U_PEK = "https://ecoportal.kz/Public/PubHearings/LoadFile/111450"
U_EX36 = "https://hitachicm.com.au/wp-content/uploads/2021/05/EX3600-6_KS-EN056T-small.pdf"
U_EX36S = "https://doggett.com/images/doggett-hitachi/Brochures/Mining-EX3600-6.pdf"
U_EX12 = "https://www.mining-portal.ru/uploads/catalog/2fc61b1364eedde3.pdf"
U_793 = "https://www.petersoncat.com/products/new/mining-trucks/793f-tier-4"
U_IMM = "https://www.immersivetechnologies.com/services/ms_pdf/UM1524_KazMinerals.pdf"
U_C9 = "https://pdfs.semanticscholar.org/e654/bd7b9089010efdfa4ebdfd2990cd4ab289c0.pdf"
U_D10 = "https://repositorio.ucsm.edu.pe/items/fa58a36b-11d7-4970-99fe-7c4d93cede31"
U_D375 = "https://www.atlantis-press.com/article/25885175.pdf"
U_DM75 = "https://www.epiroc.com/content/dam/epiroc/rotary-blasthole-drill-rigs/brochures/DM75%20Brochure%20ENG%20A4.pdf"
U_EQ = "https://minedocs.com/33/Kaz-Minerals-equipment-2024.pdf"
U_MANTLE = "https://www.metso.com/insights/case-studies/mining-and-metals/la-caridad-mine-increases-availability-of-primary-crushers/"
U_BELT = "https://www.miningscience.pwr.edu.pl/pdf-59825-3376?filename=3376.pdf"
U_HPGR = "https://scielo.org.za/pdf/jsaimm/v109n1/04.pdf"
U_METSO_HPGR = "https://metso.com/insights/blog/mining-and-metals/why-skewing-is-not-beneficial-for-your-hpgr"
U_GMD = "https://library.e.abb.com/public/3b41eb5173848571c125793d00572de5/REMOTE%20DIAGNOSTIC%20SERVICES%20FOR%20GEARLESS%20MILL%20DRIVES.pdf"
U_Q423 = "https://www.kazminerals.com/media/23062/q4-2023-production-report-final.pdf"
U_KEN = "https://cidra.com/wp-content/uploads/2024/02/BI0614.pdf"
U_CEN = "https://cidra.com/wp-content/uploads/2024/02/BI0566.pdf"
U_PST = "https://cidra.com/wp-content/uploads/2024/02/BI0622.pdf"
U_KSB = "https://www.ksb.com/en-us/solutions/mining/hard-rock-mining"
U_WEIR = "https://www.global.weir/newsroom/global-news/the-importance-of-maintaining-your-slurry-pump/"
U_FLS_BY = "https://prod.flsmidth.com/globalassets/frontify/2024/9/fls_flotationbypass_datasheet_en.pdf"
U_ANDRITZ = "https://www.andritz.com/resource/blob/14766/39b32881f5cf79564ab492e33b47d549/aa-automation-mpc-sag-mills-flotation-circuits-data.pdf"
U_ABB_PH = "https://library.e.abb.com/public/ce5cb93e495f4eafb1b60f98308a7203/AD_ANAINST_001-EN%20Rev%20A.pdf"
U_FLS_TH = "https://fls.com/en/parts-and-services/upgrades-rebuilds-and-exchange/thickeners-and-clarifiers"
U_METSO_FILT = "https://www.metso.com/ru/insights/case-studies/mining-and-metals/pf-plate-pack-expansion-at-aktogay/"
U_ELM = "https://elmc.com/our-offering/filtration-spare-and-wear-parts/filter-cloths/"
U_COURIER = "https://www.metso.com/globalassets/portfolio/brochure-courier-5x-6x-sl-online-analyzers-4924-11-23-en-mng.pdf"
U_TAIL20 = "https://www.kazminerals.com/app/uploads/2025/10/kaz-minerals-plc-tailings-management-july-2020.pdf"
U_BARNARD = "https://onsite.iteca.kz/img/files/amm/2023/doclady_2023/hvostohranilisha/Johan%20Barnard.pdf"
U_ATC = "https://atcwilliams.com/projects/bozshakol-tsf-kazakhstan/"
U_WINTER = "https://kazminerals.com/esg/enhancing-winter-safety-at-aktogay/"
U_NOAA = "https://en.wikipedia.org/wiki/Aktogay,_East_Kazakhstan_Region"
U_Q425 = "https://www.kazminerals.com/app/uploads/2026/02/Q4-2025-Production-report_FINAL_ENG.pdf"
U_H125 = "https://www.kazminerals.com/app/uploads/2025/12/q2-2025-production-report_final.pdf"
U_KURSIV = "https://kz.kursiv.media/2026-08-09/svvo-20-chelovek-evakuirovali-iz-za-chp-na-obogatitelnoi-fabrike-kaz-minerals/"
U_IM21 = "https://im-mining.com/2021/02/25/kaz-minerals-aktogay-expansion-track-first-production-second-concentrator-set-late-2021/"
U_OYU = "https://www.slideshare.net/slideshow/17102014-newswire-issue-347/58257500"


def sig(name, thing=None, feature=None, unit="", digits=None, where="model", source="", label="", url="", note=""):
    d = {"name": name, "thing": thing, "feature": feature, "unit": unit, "digits": digits, "where": where,
         "source": source, "label": label}
    if url:
        d["url"] = url
    if note:
        d["note"] = note
    return d


def fail(name, stat, source, label, trouble="", url=""):
    d = {"name": name, "stat": stat, "source": source, "label": label, "trouble": trouble}
    if url:
        d["url"] = url
    return d


def node(nid, title, thing, depth, depth_note, what, signals=(), failures=(), troubles=(), limits=""):
    return {"id": nid, "title": title, "thing": thing, "depth": depth, "depth_note": depth_note, "what": what,
            "signals": list(signals), "failures": list(failures), "troubles": list(troubles), "limits": limits}


# ---------------------------------------------------------------------------
# Ore
# ---------------------------------------------------------------------------
ORE = {
    "id": "ore", "title": "Руда", "live": "faces", "depth": "B",
    "intro": ("Из какого забоя идёт руда, сколько в ней меди, насколько она твёрдая и окисленная, и что из этого уже на фабрике. "
              "Содержание в сульфидной руде Актогая падает: 0,50 % в 2023, 0,43 % в 2024, 0,41 % в IV кв. 2025 (KAZ Minerals) [факт]."),
    "note": ("Содержание и твёрдость блока — оценка блочной модели с ошибкой (по аналогу 9–18 % по блоку, Silva и Boisvert 2014); "
             "твёрдость руды Актогая в открытых данных не опубликована — диапазон A×b взят у Touro и Josemaria [аналог]."),
    "nodes": [
        node("ore-faces", "Забои руды (1–3): что копаем", ["face-1", "face-2", "face-3"], "B",
             "Cu и A×b — оценка блочной модели; твёрдость и доля окисленной — аналог и допущение",
             "Три забоя руды работают на две линии: экскаватор копает блок, у блока есть оценка меди, твёрдости (A×b) и окисленной доли (ASCu).",
             signals=[
                 sig("Cu блока по блочной модели", "face-{n}", "est_cu", "% Cu", 2, "model",
                     "блочная модель двойника; средний ряд 0,50 → 0,43 → 0,41 % — KAZ Minerals, отчёты 2024 и IV кв. 2025", "расчёт",
                     U_Q425),
                 sig("Твёрдость блока A×b", "face-{n}", "est_axb", "", 1, "model",
                     "Touro NI 43-101, табл. 13.11 (A×b 31–55); Josemaria FS 2020 (23–96): для Актогая не опубликовано", "аналог"),
                 sig("Класс твёрдости (твёрдая / средняя / мягче базовой)", "face-{n}", "hardness", "", None, "model",
                     "пороги цветовых классов стенда", "допущение"),
                 sig("Доля окисленной меди ASCu партии", None, None, "", None, "lab",
                     "лаборатория Met-LAB есть в проекте (ПЭК, с. 12–13); значения партий — на странице «Руда»", "проект", U_PEK),
                 sig("Взорванный запас забоя", "face-{n}", "blasted_t", "т", 0, "assumption",
                     "график бурения и взрывов не опубликован; уступ 10 м, станки D55 и D65 — ПЭК, с. 40", "допущение", U_PEK),
                 sig("Сколько копает экскаватор забоя", "face-{n}", "tph", "т/ч", 0, "dcs",
                     "диспетчерская система Hexagon (Вести Семей, 06.06.2024); экскаваторы 2 700–3 700 т/ч", "факт", U_VESTI),
             ],
             troubles=["hard_ore", "loss_flot_oxide"],
             limits="двойник видит оценку блока, а не истинную руду; ошибка блочной модели — главная неопределённость цены руды"),
        node("ore-plant", "Что идёт на фабрику сейчас", ["sag-1", "sag-2"], "B",
             "A×b по SAG — расчёт по кВт·ч/т; Cu питания — поточный анализатор (вендор)",
             "Руда из забоев проходит дробилку и склад, дальше её свойства видны по энергии SAG и по анализатору питания флотации.",
             signals=[
                 sig("A×b по расчёту из кВт·ч/т SAG (soft-sensor)", "sag-{n}", "axb_soft", "", 1, "model",
                     "Моррелл: E = K F80^a DWi^b; расчёт по мощности и питанию", "расчёт"),
                 sig("Cu в питании флотации", "flot-{n}", "feed_cu", "% Cu", 3, "dcs",
                     "поточный анализатор Metso Courier: цикл 12–16 мин, на рынке 1–6 %", "вендор", U_COURIER),
                 sig("Энергия SAG на тонну", "sag-{n}", "e_kwh_t", "кВт·ч/т", 2, "dcs",
                     "мощность привода и конвейерные весы питания", "допущение"),
             ],
             troubles=["hard_ore", "loss_flot_oxide", "loss_sag"],
             limits="смену руды видно с задержкой склада (часы) и анализатора (до 15 мин); поэтому металлург получает предупреждение заранее"),
        node("ore-boz", "Смена руды и режим: пример Бозшаколь", None, "B",
             "один пример влияния минералогии; не оценка потери от задержки",
             ("Бозшаколь: извлечение меди 78,5 % (H1 2024) → 73,8 % (H1 2025) из-за сложной минералогии руды. Это пример того, что руда другого "
              "состава требует другого режима; он НЕ говорит, сколько теряется за час задержки."),
             signals=[sig("Извлечение меди, Бозшаколь", None, None, "%", None, "model",
                          "KAZ Minerals, отчёт H1 2025, с. 5: 78,5 % → 73,8 %", "факт", U_H125)],
             troubles=["hard_ore", "loss_flot_oxide"],
             limits="Актогай: извлечение сульфидов 87,7 % (2023), 87,9 % (2024), 87,2 % (IV кв. 2025) — KAZ Minerals; уставки режима на площадке в открытых данных нет"),
    ],
}

# ---------------------------------------------------------------------------
# Dam
# ---------------------------------------------------------------------------
DAM = {
    "id": "dam", "title": "Дамба", "live": "dam", "depth": "B",
    "intro": ("Хвостохранилище Актогая в работе с 2017 г.: наращивание вниз по течению (downstream), максимальная высота 23 м, объём 65 млн м³ "
              "(2020) с планом 243 млн м³, класс последствий «Low» по ANCOLD, независимая экспертиза в июле 2019, с 2022 г. — центральная "
              "сгущённая укладка (CTD) [факт: отчёт KAZ Minerals, июль 2020, с. 2–3]."),
    "note": "Число и места пьезометров, уставка тревоги и оборотная вода в открытых данных не опубликованы — в двойнике это допущения.",
    "nodes": [
        node("dam-body", "Дамба и пруд", ["water"], "B",
             "паспорт дамбы — факт; пруд, баланс и уставки — допущения двойника",
             "Дамба хвостохранилища и пруд оборотной воды: давление в теле дамбы (пьезометры), объём пруда, невязка водного баланса.",
             signals=[
                 sig("Показание дамбы (пьезометр, модель)", "water", "piezo_kpa", "кПа", 0, "model",
                     "модель пруда; пьезометры П-1…П-3 ниже", "допущение"),
                 sig("Объём пруда", "water", "pond_m3", "м³", 0, "model", "объём держится регулятором, начальный — допущение",
                     "допущение"),
                 sig("Невязка водного баланса", "water", "residual_pct", "%", 1, "model",
                     "забор − потери с хвостами, кеком и испарением − изменение пруда; забор группы 0,60 м³/т (KAZ Minerals, 2024)", "расчёт"),
             ],
             troubles=["dam_alarm", "water_short"],
             limits="состояние тела дамбы между пьезометрами, трещины и фильтрация не видны ни одному датчику двойника"),
        node("dam-piezo", "Пьезометры дамбы (П-1…П-3)", ["piezo-1", "piezo-2", "piezo-3"], "B",
             "число и места пьезометров на Актогае не опубликованы",
             "Три пьезометра в теле дамбы (допущение по числу): давление поровой воды, уровень, уставка безопасности. Тревога — класс S0.",
             signals=[
                 sig("Давление поровой воды", "piezo-{n}", "kpa", "кПа", 0, "dcs", "пьезометры дамбы; число — допущение", "допущение"),
                 sig("Уровень воды в теле дамбы", "piezo-{n}", "level_m", "м", 1, "model", "кПа / 9,81", "расчёт"),
                 sig("Уставка тревоги S0", "piezo-{n}", "sp_kpa", "кПа", 0, "assumption", "уставка безопасности стенда", "допущение"),
                 sig("Тревога", "piezo-{n}", "alarm", "", 0, "dcs", "давление не ниже уставки", "допущение"),
             ],
             troubles=["dam_alarm"],
             limits="застрявший или дрейфующий пьезометр скроет опасность: поэтому пьезометры входят в таблицу приборов с возрастом данных"),
        node("dam-season", "Сезонные риски хвостов", ["water"], "B",
             "риски общие для хвостохранилищ KAZ Minerals; Актогай отдельно в источнике не назван",
             ("Дождь, таяние снега, лёд, насосы и контроль фильтрации — сезонные эффекты, которые нужно держать в голове эксплуатации "
              "хвостов KAZ Minerals (доклад технического директора, AMM Astana 2023, слайд 11) [факт]. На Бозшаколе зимой возврат "
              "осветлённой воды затруднён: ниже −10 °C более трёх месяцев в году (ATC Williams) [аналог]."),
             signals=[
                 sig("Температура воздуха", "water", "air_temp_c", "°C", 0, "assumption",
                     "нормы 1991–2020, ст. Актогай: окно 15.11–15.03 в среднем −9,05 °C; метеопост площадки не назван", "аналог", U_NOAA),
                 sig("Пляж сух (пыление)", "water", "beach_dry_pct", "%", 0, "assumption",
                     "пороги ветра и сухости не найдены", "допущение"),
                 sig("Зима: возврат воды снижен", "water", "winter", "", 0, "assumption",
                     "доля потери возврата 3 % — допущение; лёд в прудах — качественный аналог", "допущение", U_ATC),
             ],
             failures=[
                 fail("Лёд в пруду, замерзание труб", "качественно, процент не найден", "Caijiaying, Mount Wright, Бозшаколь (ATC Williams)",
                      "аналог", "water_short", U_ATC),
                 fail("Пыление сухого пляжа", "порог ветра — допущение", "приказ МЗ РК № ДСМ-70 (текст не проверен)", "допущение",
                      "tailings_dust"),
             ],
             troubles=["tailings_dust", "water_short"],
             limits="зима в модели меняет водный баланс, а не переработку (в Q1 2019 сульфидные фабрики работали на проектной переработке)"),
    ],
}

# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------
PEOPLE_IDS = ["person-crusher-mech", "person-mill-mech", "person-metallurgist", "person-power", "person-kip", "person-geologist",
              "person-water", "person-dispatcher", "person-shift-head", "person-mine-head", "person-road", "person-pit-mech",
              "person-grind-op"]
PEOPLE = {
    "id": "people", "title": "Люди", "live": "people", "depth": "B",
    "intro": ("Где люди, в каком статусе, по какому наряду-допуску работают и кто вместо. На предприятии около 3 500 работников; в карьере "
              "за смену больше 500 человек и больше 100 единиц техники (Вести Семей, 06.06.2024) [факт]."),
    "note": "Роли и состав смены стенда — допущение: штатное расписание не опубликовано; названия ролей общие для рудников.",
    "nodes": [
        node("people-shift", "Люди смены", PEOPLE_IDS, "B",
             "13 ролей смены — допущение; статус и место двойника — расчёт",
             "Каждый человек — вещь в двойнике: свободен, в пути, на работе, вне работы (эвакуирован); где он, и когда освободится.",
             signals=[
                 sig("Статус", PEOPLE_IDS, "state", "", None, "model", "двойник человека по вызовам; не слежение за людьми", "допущение"),
                 sig("Где находится", PEOPLE_IDS, "location", "", None, "model", "узел вызова или дежурное место", "допущение"),
                 sig("Наряд-допуск: узел работы", PEOPLE_IDS, "permit", "", None, "model",
                     "Правила № 348 от 30.12.2014, пп. 12 и 63", "факт"),
                 sig("Свободен с", PEOPLE_IDS, "free_at", "", None, "model", "конец текущей работы по расчёту двойника", "допущение"),
             ],
             troubles=["startup_zone", "hpgr_fire", "road_winter", "driver_fatigue"],
             limits="двойник не следит за конкретными людьми: это роли смены, нужные для вызова; реальные табельные данные не подключены"),
        node("people-permit", "Наряд-допуск: кто недоступен", ["person-mill-mech", "person-crusher-mech"], "B",
             "правило — норма Правил № 348; список людей смены — допущение",
             ("Человек, который работает внутри оборудования по наряду-допуску, недоступен для вызова до конца работ (пп. 12 и 63 "
              "Правил № 348). Двойник показывает его в статусе «на работе» с узлом наряда и предлагает следующего по цепочке."),
             signals=[sig("Узел наряда-допуска", ["person-mill-mech", "person-crusher-mech"], "permit", "", None, "model",
                          "Правила № 348, пп. 12, 63, 315, 316", "факт")],
             troubles=["startup_zone"],
             limits="текст приказа читался по кодам пунктов; конкретная форма наряда на Актогае — регламент площадки"),
        node("people-chain", "Кто вместо: цепочка вызова", ["person-dispatcher", "person-mine-head", "person-road"], "B",
             "цепочка карьера — допущение (в источниках только риск, не штатная схема)",
             ("Основной → заместитель → начальник смены. В карьере: горный диспетчер → начальник смены карьера → дорожная служба "
              "(зимняя дорога); сменный механик → горный диспетчер → начальник смены карьера (экскаватор)."),
             signals=[sig("Статус звена цепочки", ["person-dispatcher", "person-mine-head", "person-road", "person-pit-mech"], "state", "",
                          None, "model", "двойник человека", "допущение")],
             troubles=["road_winter", "driver_fatigue", "oil_contam"],
             limits="кто реально следующий, решает смена; двойник предлагает порядок"),
    ],
}

# ---------------------------------------------------------------------------
# Machines
# ---------------------------------------------------------------------------
MACHINES = {
    "id": "machines", "title": "Машины", "live": "machines", "depth": "A",
    "intro": ("Экскаваторы, самосвалы, бульдозеры и буровые карьера. У каждой машины своя глубина: A — лист сигналов и отказы с источником "
              "(EX3600, EX1200, самосвалы CAT 793), B — типовые отказы класса по аналогу (D10T, D375), C — только общее состояние (буровые)."),
    "note": ("Сигнал показан с пометкой, где он виден: на машине (видит водитель или оператор), «передаётся, если подключена опция» или "
             "«аналог другой модели». Ни один лист сигналов не переносится на машину другой модели."),
    "nodes": [
        node("m-ex3600", "EX01 Hitachi EX3600-6 (экскаватор руды)", ["exc-1"], "A",
             "лист проспекта EX3600-6; наличие опций на Актогае не подтверждено",
             "Гидравлический экскаватор EX01 (бортовой номер из перечня техники 29.02.2024). Показания и защиты — по проспекту модели EX3600-6.",
             signals=[
                 sig("Загрязнение гидромасла (датчик загрязнения)", "exc-1", "oil_pct", "% от уровня тревоги", 0, "machine",
                     "Hitachi EX3600-6, проспект KS-EN056T, с. 11: «Alerts the operator of excessive contaminants in the oil»", "вендор",
                     U_EX36, "в источнике слова hydraulic нет — «масло» вообще; у остальных экскаваторов датчик не подтверждён"),
                 sig("Тревога датчика загрязнения", "exc-1", "oil_alert", "", 0, "sent",
                     "Global e-Service (рабочая информация и положение) требует опцию DTU и контракт; в ряде регионов недоступен (с. 11)",
                     "вендор", U_EX36),
                 sig("Натяжение гусениц: азотные аккумуляторы, автостоп хода при превышении давления", None, None, "", None, "machine",
                     "проспект EX3600-6, с. 7: «Travel is automatically stopped if accumulator pressure exceeds a preset level»", "вендор",
                     U_EX36, "датчик давления в тексте прямо не назван — описана защитная функция"),
                 sig("E-P Control: нагрузка двигателя и насосов", None, None, "", None, "machine",
                     "проспект, с. 4: «senses load demand and controls engine and pump output»", "вендор", U_EX36),
                 sig("Индикаторы кабины: давление и уровень ОЖ, температура топлива, давление масла двигателя, засорение воздушного фильтра, "
                     "загрязнение насосов", None, None, "", None, "machine",
                     "EX3600-6 (diesel), стандартная комплектация, американская редакция, с. 28; список «Standard»", "вендор", U_EX36S,
                     "лампы и зуммеры в кабине (местный контроль), не телеметрия"),
                 sig("Температура гидромасла и сигнал перегрева", None, None, "", None, "machine",
                     "тот же список: «Hydraulic oil temperature gauge», «Hydraulic oil overheat»", "вендор", U_EX36S),
                 sig("Журнал параметров двигателя и гидравлики (DLU)", None, None, "", None, "sent",
                     "DLU непрерывно записывает параметры; выгрузка на ПК; спутниковая передача — опция по лицензии страны", "вендор",
                     U_EX36S),
                 sig("Копает, т/ч", "exc-1", "tph", "т/ч", 0, "dcs",
                     "диспетчерская система Hexagon (Вести Семей, 06.06.2024)", "факт", U_VESTI),
             ],
             failures=[
                 fail("Загрязнение рабочей жидкости — причина отказов гидросистем", "≈ 70 % отказов гидросистем",
                      "Abduazizov и др., Mining of Mineral Deposits 20(2), 2026, с. 31 (в источнике — парк другого рудника)", "аналог",
                      "oil_contam", U_C9),
                 fail("Ремонт после отказа гидросистемы", "57,45 ч (MTTR электрогидравлики PC3000, не EX3600)", "та же работа, табл. 2, с. 33",
                      "аналог", "exc_down", U_C9),
             ],
             troubles=["oil_contam", "exc_down"],
             limits="состав EX3600-6 (4 механизма поворота, 8 насосов) не переносится на другие модели Актогая"),
        node("m-ex1200", "EX53 Hitachi EX1200-6 (экскаватор вскрыши)", ["exc-5"], "A",
             "лист каталога EX1200-6 (рус., KS-EN112); списки зависят от страны поставки",
             "Экскаватор EX53 (бортовой номер из перечня техники). Контроль — индикаторы и указатели, а не телеметрия.",
             signals=[
                 sig("Указатели: температура ОЖ двигателя, уровень топлива", None, None, "", None, "machine",
                     "каталог EX1200-6, раздел «Система контроля», с. 16", "вендор", U_EX12),
                 sig("Предупреждающие индикаторы: уровень воды в радиаторе, уровень масла и давление масла двигателя, уровень топлива, "
                     "уровень рабочей жидкости гидросистемы, засорение воздушного фильтра, давление масла в коробке передач насосов",
                     None, None, "", None, "machine", "каталог, с. 16; в источнике «в коробке передач насосов», не «привода»", "вендор", U_EX12,
                     "индикаторы и лампы, а не показания датчиков"),
                 sig("Блок регистрации данных DLU", None, None, "", None, "sent",
                     "DLU непрерывно регистрирует параметры двигателя и гидросистемы (с. 16); MIC Mining (с. 13); данные скачиваются на "
                     "ПК или КПК, спутник — опция", "вендор", U_EX12),
                 sig("Состояние и производительность", "exc-5", "state", "", None, "dcs", "диспетчерская система Hexagon", "факт", U_VESTI),
             ],
             failures=[],
             troubles=[],
             limits=("не переносить на EX3600-6: у EX1200-6 два мотора поворота и три насоса, у EX3600-6 — четыре и восемь; "
                     "таблица отказов PC3000 к EX1200 не относится")),
        node("m-ex-other", "EX02, EX03 и EX51: остальные экскаваторы", ["exc-2", "exc-3", "exc-4"], "C",
             "модель EX02 и EX03 не названа, EX51 — ZX870; листов сигналов в источниках нет",
             "Пять экскаваторов Hitachi по 2 700–3 700 т/ч (Вести Семей, 06.06.2024); три работают на руде, два на вскрыше (деление — допущение).",
             signals=[sig("Состояние и производительность", ["exc-2", "exc-3", "exc-4"], "state", "", None, "dcs",
                          "диспетчерская система Hexagon", "факт", U_VESTI),
                      sig("Копает, т/ч", ["exc-2", "exc-3", "exc-4"], "tph", "т/ч", 0, "dcs", "Hexagon", "факт", U_VESTI)],
             troubles=["exc_down", "pit_stop"],
             limits="показывается общее состояние; узлы и отказы этих машин в открытых данных не найдены"),
        node("m-cat793", "Самосвалы CAT 793 (17 машин, HT141 CAT 793D)", ["truck-21"], "A",
             "лист 793F Tier 4 — другая модель, чем 793D Актогая; VIMS на Актогае подтверждена",
             ("17 самосвалов CAT 793 грузоподъёмностью более 240 т (Вести Семей, 06.06.2024). На самосвалах Актогая работает VIMS: "
              "телеметрия подтверждена данными проекта Immersive Technologies."),
             signals=[
                 sig("Панель приборов: температура масла трансмиссии, масла тормозов, ОЖ двигателя, масла гидротрансформатора, уровень топлива",
                     None, None, "", None, "analog", "CAT 793F Tier 4, стандартная комплектация, «Gauge Panel» (страница дилера Peterson Cat)",
                     "вендор", U_793, "это 793F, а не 793D; указатели в кабине, не телеметрия"),
                 sig("Указатель передачи; VIMS Message Center with Advisor; индикатор уровня DEF", None, None, "", None, "analog",
                     "та же страница: отдельные строки стандартной комплектации", "вендор", U_793),
                 sig("Многоточечный контроль давления масла (Multi-Point Oil Pressure Sensing)", None, None, "", None, "analog",
                     "та же страница, раздел Power Train", "вендор", U_793),
                 sig("VIMS: нарушающие смены, превышение оборотов, ошибки выбора передачи", None, None, "", None, "sent",
                     "Immersive Technologies, Актогай: −31 % «abusive shifts», −75,7 % превышений оборотов, −45,4 % ошибок выбора "
                     "передач (данные VIMS; периоды окт 2021–фев 2022 и окт 2022–фев 2023)", "вендор", U_IMM,
                     "VIMS подтверждена; полный перечень каналов Актогая не опубликован"),
                 sig("Цикл рейса, мин", "truck-21", "cycle_min", "мин", 0, "dcs", "диспетчерская система Hexagon", "факт", U_VESTI),
                 sig("Груз на борту, т", "truck-21", "load_t", "т", 0, "model", "модель рейса двойника", "допущение"),
             ],
             failures=[],
             troubles=["fleet_short", "road_winter", "driver_fatigue"],
             limits="частоты отказов самосвалов Актогая в открытых данных нет; двойник показывает рейс и готовность, не износ узлов"),
        node("m-trucks-other", "Самосвалы CAT 785 (18) и CAT 777 (2)", ["truck-03", "truck-04"], "C",
             "листов сигналов нет; HT121 — 785C, HT136–HT138 — 785D (перечень техники)",
             "Основная масса парка: 18 CAT 785 и 2 CAT 777 (Вести Семей, 06.06.2024); парк на 2026 г. не подтверждён.",
             signals=[sig("Состояние и рейс", ["truck-03", "truck-04"], "state", "", None, "dcs", "диспетчерская система Hexagon", "факт", U_VESTI)],
             troubles=["fleet_short"],
             limits="только общее состояние"),
        node("m-d10t", "Бульдозеры CAT D10T (DZ21–DZ23): типовые отказы класса", ["dozer-21", "dozer-22", "dozer-23"], "B",
             "доли остановок — диссертация о парке D10T другой компании (юг Перу)",
             "Три D10T и один D9R работают на забоях и дорогах. Типовые остановки класса машин — по аналогу; своих данных по Актогаю нет.",
             signals=[sig("Состояние", ["dozer-21", "dozer-22", "dozer-23"], "state", "", None, "dcs", "Hexagon", "факт", U_EQ)],
             failures=[
                 fail("Двигатель", "19,2 % остановок · 27,7 % времени", "UCSM Арекипа, Villanueva Villena, табл. 4–5", "аналог", "", U_D10),
                 fail("Электрика", "18,5 % · 20,7 %", "там же", "аналог", "", U_D10),
                 fail("Гидравлика", "18,4 % · 12,0 %", "там же", "аналог", "", U_D10),
                 fail("Кабина", "16,2 % · 11,1 %", "там же", "аналог", "", U_D10),
                 fail("GET (режущая кромка и зубья)", "8,7 % · 8,0 %", "там же", "аналог", "", U_D10),
                 fail("Ходовая", "6,9 % · 6,8 %", "там же", "аналог", "", U_D10),
                 fail("Силовая передача", "4,8 % · 6,7 %", "там же", "аналог", "", U_D10),
                 fail("Наработка на отказ парка", "116,8 ч (2016) → 59,4 ч (2023)", "там же, раздел MTBF", "аналог", "", U_D10),
             ],
             limits="проценты — доли числа и времени остановок парка в Перу; на Актогае не измерены"),
        node("m-d375", "Бульдозеры Komatsu D375 (DZ41–DZ43): типовые отказы", ["dozer-41", "dozer-42", "dozer-43"], "B",
             "северный климат (Якутия) — аналог по условиям",
             "Три Komatsu D375 на вскрыше и отвале. Данных по Актогаю нет.",
             signals=[sig("Состояние", ["dozer-41", "dozer-42", "dozer-43"], "state", "", None, "dcs", "Hexagon", "факт", U_EQ)],
             failures=[fail("Отказы за период наблюдения (сравнение двух моделей)", "301 отказ у D-375A против 172 у D-375A5",
                            "Ishkov, Zedgenizov, AIME 2017, табл. I (Якутия)", "аналог", "", U_D375)],
             limits="число отказов за период разных моделей, а не интенсивность; страницы 264–265 из первоначальной выписки не проверены"),
        node("m-drills", "Буровые станки (6): D55, D65, Pit Viper 231", ["drill-01", "drill-02", "drill-03", "drill-04", "drill-12", "drill-31"], "C",
             "модели — перечень техники; листа сигналов ровно этих станков нет",
             "Sandvik D55 (DR01–DR04), Epiroc D65 (DR12), Pit Viper 231 (DR31). Показано только общее состояние.",
             signals=[
                 sig("Состояние и забой", ["drill-01", "drill-02", "drill-03", "drill-04", "drill-12", "drill-31"], "state", "", None,
                     "dcs", "перечень техники ТОО «КАЗ Минералз Актогай», 29.02.2024 (список не исчерпывающий)", "факт", U_EQ),
                 sig("Глубина и скорость проходки, обороты и давление (момент), подача и удержание, давление воздуха, уровень воды, "
                     "инклинометры", None, None, "", None, "analog",
                     "Epiroc DM75, брошюра, пакет RCS Lite/Basic, с. 6 (зеркало epiroc.com); это серия DM, не Pit Viper 231", "вендор",
                     U_DM75, "экран станка (RCS 5); передача данных — пакеты Connected и NAV"),
             ],
             troubles=[],
             limits="для PV-231 лист сигналов не открылся; для D55 тоже: отказы буровых в двойнике не моделируются"),
    ],
}

# ---------------------------------------------------------------------------
# Plant
# ---------------------------------------------------------------------------
PLANT = {
    "id": "plant", "title": "Фабрика", "live": "plant", "depth": "A",
    "intro": ("Аппараты двух линий: дробилка, конвейер, склад, ВВД, SAG, шаровые, циклоны, насосы, флотация, сгуститель, фильтр. "
              "Узлы и режимы — из проекта и вендоров; отказы — по аналогу, если для Актогая данных нет."),
    "note": "Мощность фабрик по руде: ОФ-1 30,0 и ОФ-2 27,5 Мт/год (ПЭК, с. 8 и 15) [проект]; режим работы фабрик в ПЭК не указан.",
    "nodes": [
        node("p-crusher", "Первичная дробилка ЦПД (1, 2)", ["crusher-1", "crusher-2"], "A",
             "замена мантии — кейс Metso; давление масла и защита — допущение",
             "Гирационная дробилка у карьера (линия 2 — 63 × 89 дюймов, ОВОС): руда идёт на конвейер и склад.",
             signals=[
                 sig("Производительность", "crusher-{n}", "tph", "т/ч", 0, "dcs", "конвейерные весы; проект 4 386–5 044 т/ч (ОВОС)", "проект"),
                 sig("Давление масла (защита)", "crusher-{n}", "lube_kpa", "кПа", 0, "dcs", "датчик и цепь защиты; уставка 150 кПа",
                     "допущение"),
                 sig("Плановое обслуживание: замена брони", "crusher-{n}", "service", "", 0, "dcs", "план работ ЦПД", "допущение"),
             ],
             failures=[
                 fail("Замена мантии: остановка и недодробленная руда", "≈ 60 ч · 75–100 тыс. т руды не раздроблено",
                      "Metso, кейс La Caridad, 10.03.2023 (другой рудник, меньшая дробилка)", "вендор", "crusher_mantle", U_MANTLE),
                 fail("Останов по давлению масла", "частота не найдена", "паспорт дробилки; уставка — допущение", "допущение", "lube_trip"),
             ],
             troubles=["crusher_stop", "lube_trip", "crusher_mantle"],
             limits="время замены на Актогае не опубликовано; 60 ч — аналог"),
        node("p-conveyor", "Главный конвейер (1, 2) и весы", ["conveyor-1", "conveyor-2", "weigher-1", "weigher-2"], "B",
             "длина ленты ОФ-2 2 504 м — ПЭК; отказы — аналог угольных шахт",
             "Наземный магистральный конвейер до склада; на конвейере автоматические весы (ПЭК, с. 10 и 18).",
             signals=[
                 sig("Производительность по весам", "conveyor-{n}", "tph", "т/ч", 0, "dcs", "автоматические весы на ленте (ПЭК, с. 10)",
                     "проект", U_PEK),
                 sig("Сигнал защиты (отключение ленты)", "conveyor-{n}", "fault", "", 0, "dcs", "защита привода в АСУ ТП", "допущение"),
             ],
             failures=[fail("Входная (коническая) ступень редуктора привода — более половины проблем приводов",
                            ">50 % проблем приводов (подземные угольные шахты)",
                            "Zimroz, Król, 2009, с. 261: относится к входной ступени редуктора, не ко всем зубчатым колёсам", "аналог",
                            "conveyor_stop", U_BELT)],
             troubles=["conveyor_stop"],
             limits="статус «подтверждено частично»: цитата другого типа привода и другой отрасли"),
        node("p-hpgr", "ВВД (пресс валкового измельчения) линии 2", ["pebble-2"], "A",
             "POLYCOM 1 061 т/ч, 2 × 1 750 кВт — вендор; ВВД линии 1 в модели нет (рейтинг не опубликован)",
             ("На линии 2 стоит ВВД thyssenkrupp POLYCOM 1 061 т/ч, 2 × 1 750 кВт (International Mining, 25.02.2021) [вендор]. 09.08.2026 "
              "пожар на участке ВВД фабрики № 1 во время ППР: 20 человек эвакуированы [факт]."),
             signals=[
                 sig("Мощность двух приводов", "pebble-2", "hpgr_kw", "кВт", 0, "dcs", "токи и мощность приводов", "вендор", U_IM21),
                 sig("Перекос зазора валков", "pebble-2", "hpgr_skew_pct", "%", 1, "dcs", "датчики положения валков [допущение: состав приборов]",
                     "допущение"),
                 sig("Разница мощности приводов", "pebble-2", "hpgr_kw_diff_pct", "%", 1, "dcs", "токи двух приводов", "допущение"),
                 sig("Металлодетектор перед ВВД", "pebble-2", "metal_alarm", "", 0, "dcs",
                     "Metso (2022): металл пресс по давлению не «чувствует», нужен металлодетектор", "аналог", U_METSO_HPGR),
             ],
             failures=[
                 fail("Неравномерное питание: сегрегация по крупности даёт перекос", "качественно",
                      "Metso, блог, 31.01.2022 (прочитан через WebFetch, не сверен с HTML); другой изготовитель", "аналог", "hpgr_uneven",
                      U_METSO_HPGR),
                 fail("Ресурс бандажей валков", "12 000 ч — проектная оценка, не измерение",
                      "Rule, Minnaar, Sauermann, JSAIMM 2009, с. 27 (платина)", "аналог", "", U_HPGR),
                 fail("Пожар на участке ВВД фабрики № 1", "09.08.2026 ≈ 12:00, 20 эвакуированы", "Курсив, 09.08.2026", "факт",
                      "hpgr_fire", U_KURSIV),
             ],
             troubles=["hpgr_uneven", "hpgr_fire", "pebble_stop"],
             limits="доля потери при перекосе и срок до металла в валках — допущения двойника"),
        node("p-sag", "Мельница SAG и безредукторный привод (1, 2)", ["sag-1", "sag-2"], "A",
             "SAG 28 МВт и безредукторные приводы — вендор; удалённая диагностика ГМД — платформа ABB",
             ("SAG 28 МВт, две шаровые по 22 МВт на линию (mining-technology, 2018) [вендор]. Перефутеровка SAG на Актогае: IV кв. 2023 "
              "на обеих сульфидных линиях (перенесена из III кв.) [факт]."),
             signals=[
                 sig("Мощность привода", "sag-{n}", "power_kw", "кВт", 0, "dcs", "АСУ ТП, привод 28 МВт", "вендор"),
                 sig("Питание SAG", "sag-{n}", "feed_tph", "т/ч", 0, "dcs", "конвейерные весы питания мельницы", "допущение"),
                 sig("Тоннаж с последней перефутеровки", "sag-{n}", "liner_ground_t", "т", 0, "dcs", "счётчик по весам; износ 20,41 мм/Мт — Bradken",
                     "вендор"),
                 sig("ГМД: воздушный зазор, эксцентриситет, деформация статора, движение полюсов, температуры обмоток и охлаждения",
                     None, None, "", None, "sent",
                     "ABB, удалённая диагностика безредукторных приводов, PDF с. 16–18", "вендор", U_GMD,
                     "платформа ABB; что услуга подключена на Актогае, не подтверждено"),
             ],
             failures=[fail("Плановая перефутеровка и потеря переработки", "IV кв. 2023: Sulphide 1 −5 % (7 001 против 7 394 кт)",
                            "KAZ Minerals, отчёт IV кв. 2023, с. 2–3", "факт", "reline", U_Q423)],
             troubles=["reline", "sag_stop", "loss_sag"],
             limits="скрытый ускоренный износ и толщина футеровки двойником не видны"),
        node("p-grind", "Шаровые мельницы и гидроциклоны (1, 2)", ["ball-1a", "ball-1b", "ball-2a", "ball-2b", "cyclones-1", "cyclones-2"], "A",
             "канатирование — вендор и Kennecott/Centinela; пороги — допущение",
             ("Две шаровые мельницы на линию в замкнутом цикле с гидроциклонами. Канатирование циклонов и перегрузка шаровой — "
              "известный режим (Kennecott); тяжёлое канатирование остановило нитку рафинёрной флотации на ≈ 6 ч (Centinela)."),
             signals=[
                 sig("Нагрузка шаровой, % от номинала", "ball-{n}a", "power_pct", "%", 0, "dcs", "АСУ ТП; перегрузка — выше номинала", "допущение"),
                 sig("Циркулирующая нагрузка", "cyclones-{n}", "circ_load_pct", "%", 0, "dcs", "расчёт по расходам и плотности", "допущение"),
                 sig("Давление питания циклонов", "cyclones-{n}", "pressure_kpa", "кПа", 0, "dcs", "АСУ ТП", "допущение"),
                 sig("P80 перелива", "cyclones-{n}", "p80_um", "мкм", 0, "dcs",
                     "анализатор крупности; CiDRA PST: обновление раз в 4 с против 3–9 мин у обычных систем и «обычно 2 ч с задержкой "
                     "12–24 ч» у лаборатории", "вендор", U_PST),
             ],
             failures=[
                 fail("Канатирование, перегрузка шаровой", "управление помолом предотвращает (Kennecott)", "CiDRA, Comminution 2014, с. 12",
                      "вендор", "roping", U_KEN),
                 fail("Тяжёлое канатирование: нитка рафинёрной флотации", "≈ 6 ч остановки (Centinela, май 2014)", "CiDRA, с. 3", "вендор",
                      "roping", U_CEN),
             ],
             troubles=["roping", "grind_coarse", "ball_stop", "loss_cyclones"],
             limits="лаборатория с задержкой 12–24 ч скрывает потери; потеря после канатирования у Актогая не измерена"),
        node("p-pumps", "Насосы пульпы и оборотной воды", None, "B",
             "отдельных вещей в двойнике нет; отказы — вендорные кейсы",
             "Питающий насос гидроциклонов и насосы оборотной воды. В двойнике они входят в состояние линии и водяной баланс.",
             signals=[sig("Подшипники, сальник, кавитация, КПД, ресурс износа насоса", None, None, "", None, "sent",
                          "Weir Synertrex / NEXT Insight для насосов Warman: «when installed»", "вендор", U_WEIR,
                          "платформа; что она стоит на насосах Актогая, не подтверждено")],
             failures=[fail("Преждевременный отказ питающего насоса гидроциклонов", "1 600–1 800 ч наработки",
                            "KSB, кейс BHP Olympic Dam (тип насоса не указан)", "вендор", "", U_KSB)],
             troubles=["water_short"],
             limits="только общее состояние через линию и воду"),
        node("p-flot", "Флотация, pH и реагенты (1, 2)", ["flot-1", "flot-2", "ph-1", "ph-2"], "B",
             "отказы датчиков — требования вендора; Wemco линии 2 — вендор",
             "Основная и перечистная флотация; pH держится известью, собиратель дозируется расходомером.",
             signals=[
                 sig("Извлечение", "flot-{n}", "recovery", "%", 1, "dcs", "двухпродуктовая формула по анализатору", "расчёт"),
                 sig("pH онлайн", "ph-{n}", "ph", "pH", 2, "dcs", "онлайн-электрод; регулятор извести держит его на уставке", "допущение"),
                 sig("pH ручной пробой", "ph-{n}", "lab_ph", "pH", 2, "lab", "переносной pH-метр; периодичность — допущение", "допущение"),
                 sig("Уровень ячеек: байпас Multi-Sense (автономный контур комплекта FLS), камера пены Smart Vision", None, None, "", None, "sent",
                     "FLS: datasheet Flotation Bypass System (2023) и страница Smart Vision", "вендор", U_FLS_BY,
                     "платформа/опция; что она стоит на Актогае, не подтверждено; ведомость WEMCO 300 м³ не открылась"),
             ],
             failures=[
                 fail("Электрод pH: абразив пульпы и накипь от извести", "частоты не публикуются", "ABB, с. 3 (требование вендора к датчику TB556)",
                      "вендор", "sensor_ph", U_ABB_PH),
                 fail("Колебания уровня ячеек до 2 ч при ПИД-регулировании", "до 2 ч", "ANDRITZ, Forbes и Gough, MPC, с. 10", "вендор", "",
                      U_ANDRITZ),
             ],
             troubles=["loss_flot", "reagent_over", "sensor_ph", "conc_low", "loss_flot_oxide"],
             limits="pH-метр врёт молча: онлайн-значение держится на уставке, обнаруживает только контрольная проба"),
        node("p-thick", "Сгуститель концентрата (1, 2)", ["thick-1", "thick-2"], "B",
             "апгрейд привода — кейс FLS другой фабрики; повреждение граблин — вторичная публикация",
             "Сгуститель принимает концентрат перечистки и питает фильтр; при полном сгустителе линия держит только то, что берёт фильтр.",
             signals=[
                 sig("Запас в сгустителе", "thick-{n}", "inventory_t", "т", 0, "model", "баланс по весам; ёмкость 340 т — допущение", "допущение"),
                 sig("Крутящий момент привода граблин", None, None, "", None, "sent",
                     "FLS: апгрейд привода «increases torque measurement»; предел кейса — момент привода (чужая фабрика)", "вендор", U_FLS_TH,
                     "тип прибора и вывод (местный или дистанционный) не указаны"),
             ],
             failures=[fail("Повреждение граблин сгустителя: фабрика ≈ 60 % производительности на время ремонта", "≈ 60 %",
                            "BCM NewsWire 17.10.2014, Oyu Tolgoi (вторичная публикация)", "аналог", "", U_OYU)],
             troubles=["thick_high", "thick_full"],
             limits="подтверждено частично: нет данных о приборах, это KPI апгрейдов"),
        node("p-filter", "Фильтр-прессы концентрата (1, 2)", ["filter-1", "filter-2"], "B",
             "кейс Metso по Актогаю — вендор; ресурс полотна — кейс Element",
             ("Два пресса на линию; Metso увеличила площадь плит с 72 до 96 м² за 9 дней, «на 25 % выросло производство концентрата» "
              "(Актогай, 09.03.2021) [вендор]; замечание: 72 → 96 м² — это +33 % площади, расхождение страница не объясняет."),
             signals=[
                 sig("Прессов в работе", "filter-{n}", "presses_on", "", 0, "dcs", "состояние прессов", "допущение"),
                 sig("Кек, т/ч", "filter-{n}", "cake_tph", "т/ч", 1, "dcs", "весы кека", "допущение"),
                 sig("Влажность кека", "filter-{n}", "moisture_pct", "%", 1, "lab", "ОВОС: влажность 8 %", "проект"),
             ],
             failures=[fail("Ресурс полотна: пробное полотно выдержало 2 255 циклов, больше OEM", "2 255 циклов",
                            "Element, кейс VPA 15 (медный концентрат, Центральная Европа)", "вендор", "filter_one", U_ELM)],
             troubles=["filter_one", "filter_stop"],
             limits="смена полотна двойником моделируется окнами; фактический ресурс на Актогае не публикуется"),
        node("p-analyzers", "Анализаторы и лаборатория (1, 2)", ["analyzer-1", "analyzer-2"], "B",
             "цикл анализатора — вендор Metso; лаборатория Met-LAB — проект",
             ("Поточный анализатор: питание, хвосты, концентрат. Цикл 12 мин на 12 проб, 16 мин на 18 потоков (Metso Courier 5X/6X). "
              "Лабораторный ситовой анализ: «обычно 2 ч с задержкой 12–24 ч» (CiDRA); Met-LAB есть в проекте (ПЭК, с. 12–13)."),
             signals=[
                 sig("Cu в питании, хвостах и концентрате", "analyzer-{n}", "feed_cu", "% Cu", 3, "dcs", "Metso Courier, цикл 12–16 мин",
                     "вендор", U_COURIER),
                 sig("Возраст последнего цикла анализатора", "analyzer-{n}", "age_min", "мин", 0, "dcs",
                     "засорение пробоотборных линий ищут по аналитике (Metso Metrics)", "вендор"),
             ],
             failures=[fail("Засорение пробоотборных линий", "типичная проблема, частот нет", "Metso Metrics, брошюра, с. 8 (маркетинг вендора)",
                            "вендор", "")],
             troubles=["sensor_ph"],
             limits="анализатор старше трёх циклов считается устаревшим; метод анализа (XRF) в проверенном тексте не разбирался"),
    ],
}

# ---------------------------------------------------------------------------
# Environment and data
# ---------------------------------------------------------------------------
ENV = {
    "id": "env", "title": "Среда и данные", "live": "env", "depth": "B",
    "intro": ("Погода и дороги карьера (температура, ветер, видимость, сцепление) и данные: у каждого измерения — возраст и пометка "
              "«под подозрением»."),
    "note": "Нормы — факт-аналог (станция Aqtogay 36619, NOAA 1991–2020); пороги тревоги — допущение площадки.",
    "nodes": [
        node("env-weather", "Погода и дороги карьера", ["pit", "water"], "B",
             "нормы температуры — NOAA; видимость и сцепление — допущение, прямых измерений в источниках нет",
             ("Зимой на откатке риск ДТП растёт: метели и сильный ветер (KAZ Minerals ESG) [факт]. В двойнике зима меняет состояние дороги "
              "(сцепление, видимость), а замедление откатки приходит со штормовым окном; переработку фабрики сезон сам по себе не замедляет."),
             signals=[
                 sig("Температура воздуха", "water", "air_temp_c", "°C", 0, "assumption",
                     "нормы 1991–2020 (Aqtogay 36619): январь −13,7, июль 24,6 °C", "аналог", U_NOAA),
                 sig("Ветер", "water", "wind_ms", "м/с", 0, "assumption", "метеопост площадки не назван", "допущение"),
                 sig("Видимость на откатке", "pit", "visibility_m", "м", 0, "assumption", "порог тревоги 150 м — допущение", "допущение", U_WINTER),
                 sig("Сцепление (индекс 0…1)", "pit", "road_grip", "", 2, "assumption", "оценка по циклам самосвалов", "допущение"),
                 sig("Скорость откатки к сухой дороге", "pit", "haul_speed_pct", "%", 0, "dcs", "циклы самосвалов в Hexagon", "допущение"),
                 sig("Ограничение движения введено", "pit", "road_restrict", "", 0, "dcs", "решение горного диспетчера", "допущение"),
             ],
             failures=[fail("Рост риска ДТП зимой: метели и сильный ветер", "качественно, чисел нет",
                            "KAZ Minerals ESG, Enhancing winter safety at Aktogay", "факт", "road_winter", U_WINTER)],
             troubles=["road_winter", "driver_fatigue", "tailings_dust"],
             limits="сезон по умолчанию не режет переработку (Q1 2019: обе сульфидные фабрики на проектной переработке)"),
        node("env-data", "Данные: приборы, возраст, подозрения", ["analyzer-1", "analyzer-2", "weigher-1", "weigher-2", "flowmeter-1", "flowmeter-2",
                                                                    "ph-1", "ph-2", "piezo-1", "piezo-2", "piezo-3"], "B",
             "список приборов — двойник; возраст данных — из Ditto",
             ("У каждого измерения в карточке беды: значение, где оно видно, возраст данных (когда опубликовано и сколько лет замеру) и "
              "пометка «под подозрением». Анализатор — цикл 12–16 мин; ручная проба pH — раз в несколько часов; весы — непрерывно."),
             signals=[
                 sig("Состояние прибора (исправен / дрейф / под подозрением)", ["analyzer-1", "analyzer-2", "flowmeter-1", "flowmeter-2", "ph-1", "ph-2"],
                     "state", "", None, "model", "модуль «Где теряется медь» и сам прибор", "расчёт"),
                 sig("Возраст замера анализатора", "analyzer-{n}", "age_min", "мин", 0, "dcs", "минуты с последнего цикла", "вендор", U_COURIER),
                 sig("Возраст ручной пробы pH", "ph-{n}", "age_min", "мин", 0, "lab", "минуты с последней пробы", "допущение"),
             ],
             troubles=["sensor_ph", "loss_flot"],
             limits="возраст публикации — модельное время с последнего обновления вещи в Ditto; у машин карьера значения обновляются по очереди"),
    ],
}

GROUPS = [ORE, DAM, PEOPLE, MACHINES, PLANT, ENV]
try:
    from . import inside_t as _inside_t
except ImportError:          # run as a script: python -I modules/inside.py
    import importlib.util as _iu
    import os as _os
    _sp = _iu.spec_from_file_location("inside_t", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "inside_t.py"))
    _inside_t = _iu.module_from_spec(_sp)
    _sp.loader.exec_module(_inside_t)
_inside_t.apply(GROUPS)       # tier T of 24.10.2026: signals, failures and trouble kinds of eight more units


def data() -> dict:
    return {"groups": GROUPS, "where_ru": WHERE_RU, "labels": list(LABELS), "depth_ru": DEPTH_RU}


def json_text() -> str:
    return json.dumps(data(), ensure_ascii=False, indent=1) + "\n"


def problems() -> list[str]:
    out = []
    ids = set()
    for g in GROUPS:
        for n in g["nodes"]:
            if n["id"] in ids:
                out.append(f"duplicate node {n['id']}")
            ids.add(n["id"])
            if n["depth"] not in DEPTH_RU:
                out.append(f"{n['id']}: depth")
            for s in n["signals"]:
                if s["where"] not in WHERE_RU:
                    out.append(f"{n['id']}: where {s['where']}")
                if s["label"] not in LABELS:
                    out.append(f"{n['id']}: label {s['label']}")
                if bool(s["thing"]) != bool(s["feature"]):
                    out.append(f"{n['id']}: thing and feature go together: {s['name']}")
            for f in n["failures"]:
                if f["label"] not in LABELS:
                    out.append(f"{n['id']}: failure label {f['label']}")
    return out


def main(argv: list[str] | None = None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    bad = problems()
    if bad:
        print("NOT OK " + "; ".join(bad))
        return 1
    if a[:1] == ["--write-json"] and len(a) > 1:
        with open(a[1], "w", encoding="utf-8", newline="\n") as f:
            f.write(json_text())
        return 0
    print(f"ok: {len(GROUPS)} groups, {sum(len(g['nodes']) for g in GROUPS)} nodes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
