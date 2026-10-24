/* Russian names for what the twins carry in English: feature keys, passport keys,
   units, thing types, states per type, issue kinds and object keys. The data in
   Ditto keep English identifiers (code); every view shows them through these. */
'use strict';
(function () {
  const FEAT = {
    state: 'состояние', status: 'статус', speed: 'скорость модели', speed_fact: 'скорость модели, факт',
    seed: 'номер прогона', tph: 'производительность', cu_tph: 'медь в концентрате',
    power_mw: 'мощность из сети', water_m3h: 'забор свежей воды', scenario: 'сценарий',
    heartbeat: 'метка времени (пауза)', degraded: 'потери сообщений (1 — да)',
    mining_tph: 'добыча', next_block: 'следующий блок', plan_text: 'план блоков', hard_in_plan: 'твёрдая руда в плане (1 — да)',
    block: 'партия в работе', bench: 'уступ',
    location: 'где', tonnes_left: 'осталось по весам', pit_t: 'ещё в карьере', cu_meas: 'медь по лаборатории',
    axb_soft: 'твёрдость по датчику, A×b', power_kw: 'мощность', lube_kpa: 'давление масла',
    level_t: 'запас', in_tph: 'приход', out_tph: 'расход', hours_left: 'хватит на',
    recovery: 'извлечение', cum_cu_t: 'медь за смену', cum_mwh: 'энергия за смену', cum_m3: 'вода за смену',
    cum_usd: 'ценность за смену', cum_cu_t_total: 'медь за прогон', cum_mwh_total: 'энергия за прогон',
    cum_m3_total: 'вода за прогон', cum_usd_total: 'ценность за прогон',
    power_limit_kw: 'предел мощности', feed_tph: 'питание', speed_pct: 'скорость вращения', load_pct: 'загрузка',
    e_kwh_t: 'удельная энергия', liner_wear_mm: 'износ футеровки',
    p80_um: 'крупность помола (P80)', pressure_kpa: 'давление', open_count: 'циклонов в работе',
    feed_cu: 'медь в руде', tail_cu: 'медь в хвостах', conc_cu: 'медь в концентрате', conc_tph: 'концентрат',
    stage_recovery: 'извлечение операции', mass_pull_pct: 'выход пены', rconc_cu: 'Cu в черновом концентрате',
    residence_min: 'время флотации', dose_sp_gt: 'собиратель, уставка', dose_meas_gt: 'собиратель, расходомер',
    intake_m3h: 'забор свежей воды', recycle_m3h: 'оборотная вода', tails_loss_m3h: 'вода с хвостами',
    evap_m3h: 'испарение и фильтрация', pond_m3: 'объём пруда', residual_pct: 'невязка баланса воды', piezo_kpa: 'пьезометр дамбы',
    grid_limit_mw: 'лимит сети', site_mw: 'потребление площадки', grinding_mw: 'мельницы из сети',
    grinding_shaft_mw: 'мельницы на валу', other_mw: 'прочая нагрузка', shed_mw: 'отключено', headroom_mw: 'запас мощности',
    task: 'задача', free_at: 'освободится',
    exc_total: 'экскаваторов всего', exc_ready: 'экскаваторов готово', trucks_total: 'самосвалов всего',
    trucks_ready: 'самосвалов готово', truck_kio_shift: 'доля времени самосвалов в работе за смену', haul_tph: 'вывозка',
    limit_tph: 'предел', underflow_tph: 'разгрузка', inventory_t: 'запас', solids_pct: 'твёрдое в разгрузке',
    overflow_m3h: 'слив', hours_to_full: 'заполнится через', presses_on: 'прессов в работе', cake_tph: 'кек, сухой',
    feed_t_total: 'питание, счётчик весов', underflow_t_total: 'разгрузка, счётчик весов',
    intake_m3_total: 'забор воды, счётчик', loss_m3_total: 'уход воды из оборота, счётчик',
    moisture_pct: 'влажность кека', stock_t: 'запас', shipped_t_shift: 'отгружено за смену', wagons_shift: 'вагонов за смену',
    node: 'узел', kind: 'вид', safety_class: 'класс безопасности', loss_usd_h: 'потери, когда идут (≈)',
    loss_from: 'потери начнутся', loss_shift_usd: 'потери за 12 ч', delay_cost_usd: 'час промедления (≈)',
    call_by: 'позвать до', rank: 'место в очереди', responsible: 'кто отвечает', text: 'разбор и совет модуля',
    queue_text: 'очередь', order_text: 'порядок по деньгам', alarm_order_text: 'порядок «кто громче»',
    auto_call: 'автовызов', processed_sim_time: 'модуль посчитал на', resend: 'запрос повтора точки',
    top_node: 'узел главной потери', top_text: 'главная потеря', cu_residual_pct: 'невязка баланса меди',
    water_residual_pct: 'невязка баланса воды', conc_residual_pct: 'невязка баланса концентрата',
    power_headroom_mw: 'запас мощности', power_parts_text: 'мощность по частям',
    next_hard_axb: 'A×b ближайшей твёрдой', fc_text: 'прогноз', layers_l1: 'слои склада 1', layers_l2: 'слои склада 2',
    check_text: 'сбылось ли', hit_rate: 'доля сбывшихся', last: 'последняя запись', cancel: 'отмена', reset: 'сброс',
    tm_fetch_ok: 'модели TM читаются (1 — да)', tm_types: 'типов TM', things_ok: 'вещей на месте',
    truth_log: 'журнал скрытых причин', shifts_done: 'смен посчитано', shifts_total: 'смен всего',
    report_json: 'отчёт калибровки', shift_result: 'итог смены', cum_cu_t_base: 'база: медь за смену',
    cum_mwh_base: 'база: энергия за смену', cum_m3_base: 'база: вода за смену', cum_usd_base: 'база: ценность за смену',
    alt_loud_cum_cu_t: 'по громкости: медь за смену', alt_notwin_cum_cu_t: 'без двойника: медь за смену',
    alt_loud_cum_usd: 'по громкости: ценность за смену', alt_notwin_cum_usd: 'без двойника: ценность за смену',
    idSimulationRun: 'прогон', sim_time: 'значения на (время модели)',
    holes_shift: 'скважин за смену', est_cu: 'медь по блоку (≈)', est_axb: 'твёрдость по блоку, A×b (≈)', blasted_t: 'взорвано', hardness: 'твёрдость',
    sp_kpa: 'уставка тревоги', sp_gt: 'уставка', dose_gt: 'расход собирателя', kpa: 'давление', level_m: 'уровень воды', alarm: 'тревога (1 — да)',
    cycle_mult: 'замедление рейса', trucks_on: 'самосвалов на дороге', load_t: 'груз', cycle_min: 'рейс', duty: 'работа', total_t: 'счётчик',
    age_min: 'возраст пробы', trucks_ore: 'самосвалов на руде', waste_tph: 'вскрыша', state_ru: 'состояние словами', status_ru: 'статус словами',
    tank_t: 'бак собирателя (весы)', tank_in_t_total: 'привезено в бак, счётчик', dose_t_total: 'расходомер собирателя, счётчик',
    eta: 'ждём к (время модели)', escalation: 'не прибыл', chain: 'цепочка ответственности', chain_text: 'кто занят и кого звать вместо',
    choice_text: 'цена выбора бригады', permit_text: 'наряд-допуск', permit: 'наряд-допуск (узел)', start_cmd: 'команда на пуск',
    balls_gt: 'расход шаров, г/т', deviations: 'отклонения', deviations_text: 'отклонения (хроника)', decisions: 'вызовы смены против порядка модели',
    review_text: 'А если бы позвали иначе?', liner_ground_t: 'наработка футеровки с перефутеровки, т', checklist: 'что делать', closure: 'как закроется', hpgr_tph: 'ВВД: номинал, т/ч', hpgr_load_pct: 'ВВД: загрузка, %', hpgr_kw: 'ВВД: мощность, кВт', forecast: 'прогнозы: склад, футеровка, медь', forecast_text: 'прогнозы словами', tariff: 'тариф', tariff_text: 'тариф сейчас', season_text: 'зима',
    air_temp_c: 'температура воздуха, °C', wind_ms: 'ветер, м/с', beach_dry_pct: 'сухой пляж, %', winter: 'зима (1 — включена)', handover: 'лист сдачи смены', handover_text: 'сдача смены',
    handover_draft_text: 'что передать сейчас', escalations: 'журнал «не прибыл»', silent_text: 'тихие перерасходы',
    water_leak_m3h: 'утечка по балансу воды (≈)', water_leak_usd_h: 'утечка, $/ч (≈)',
    leak_m3h: 'утечка (счётчика нет)', short_m3h: 'нехватка воды', cut_tph: 'снижение питания из-за воды', intake_cap_m3h: 'предел забора', reline_until_min: 'перефутеровка до',
    /* tier S (23.10.2026): winter road, excavator oil, tired driver, mantle change, roping, HPGR, pH meter, evidence */
    visibility_m: 'видимость на откатке, м', road_grip: 'сцепление дорог (индекс 0…1)', haul_speed_pct: 'скорость откатки к сухой дороге, %',
    road_restrict: 'ограничение движения введено (1 — да)', oil_pct: 'загрязнение масла, % от уровня тревоги',
    gmd_gap_mm: 'воздушный зазор привода, мм', idler_temp_c: 'температура подшипника ролика, °C', level_swing_pct: 'размах уровня ячеек, %',
    rake_torque_pct: 'момент граблин, % расчётного', cycle_pct: 'цикл фильтрации, % новой ткани', pump_head_pct: 'напор насоса питания циклонов, % нормы',
    brake_oil_c: 'температура масла тормозов, °C', brake_truck: 'самосвал с горячими тормозами', track_press_pct: 'натяжение гусениц, % уровня автостопа',
    oil_alert: 'тревога датчика масла (1 — да)', fatigue: 'оповещение об усталости водителя (1 — да)', fatigue_truck: 'машина в оповещении',
    service: 'плановая замена брони (1 — идёт)', service_left_h: 'до конца замены брони, ч', circ_load_pct: 'циркулирующая нагрузка, %',
    power_pct: 'нагрузка привода, % номинала', hpgr_skew_pct: 'ВВД: перекос валков, %', hpgr_kw_diff_pct: 'ВВД: разница мощности приводов, %',
    metal_alarm: 'металлодетектор сработал (1 — да)', ph: 'pH онлайн', sp_ph: 'pH, уставка', lab_ph: 'pH, ручная проба',
    evidence: 'измерения и возраст данных', evidence_text: 'измерения словами', notify_text: 'также сообщить',
    suspect_sensors: 'приборы под подозрением', suspect_text: 'приборы под подозрением (словами)',
  };
  const NODE = { 'sag-1': 'SAG-1', 'sag-2': 'SAG-2', 'cyclones-1': 'циклоны 1', 'cyclones-2': 'циклоны 2', 'flot-1': 'флотация 1', 'flot-2': 'флотация 2' };
  const LOSS_PART = { gap_cu_tph: 'разрыв, т Cu/ч', gap_usd_h: 'разрыв, $/ч', sigma: 'σ, т Cu/ч', status: 'вывод', roles: 'кого звать' };
  AKT.featRu = (name, f) => {
    if (FEAT[f]) return FEAT[f];
    let m = /^(sag|cyclones|flot)-([12])_(gap_cu_tph|gap_usd_h|sigma|status|roles)$/.exec(f);
    if (m) return `${NODE[m[1] + '-' + m[2]]}: ${LOSS_PART[m[3]]}`;
    m = /^sag-([12])_(e_meas_kwh_t|e_exp_kwh_t|energy_usd_h)$/.exec(f);
    if (m) return `SAG-${m[1]}: ${{ e_meas_kwh_t: 'кВт·ч/т измерено', e_exp_kwh_t: 'кВт·ч/т по руде (≈)', energy_usd_h: 'лишняя энергия, $/ч (≈)' }[m[2]]}`;
    m = /^rougher-([12])_reagent_(excess_pct|usd_h|status)$/.exec(f);
    if (m) return `реагенты линии ${m[1]}: ${{ excess_pct: 'бак против расходомера, %', usd_h: 'перерасход, $/ч (≈)', status: 'вывод' }[m[2]]}`;
    m = /^fc_tph_h(\d+)$/.exec(f);
    if (m) return `прогноз т/ч, час ${m[1]}`;
    m = /^next_hard_eta(_early)?_h_l([12])$/.exec(f);
    if (m) return `твёрдая руда, линия ${m[2]}: ${m[1] ? 'раньше через' : 'ожидаемо через'}`;
    m = /^(.+)_([a-z_0-9]+?)_base$/.exec(f);
    if (m && name === 'baseline') {
      for (const thing of Object.keys(AKT.things).sort((a, b) => b.length - a.length)) {
        if (f.startsWith(thing + '_') && f.endsWith('_base')) {
          const feat = f.slice(thing.length + 1, -5);
          return `база (без сценария): ${AKT.nameRu(thing)} — ${FEAT[feat] || tokensRu(feat)}`;
        }
      }
    }
    return tokensRu(f);
  };
  /* keys no table knows yet (new thing types): word by word, "speed_kmh" -> "скорость, км/ч" */
  const TOK = { speed: 'скорость', load: 'загрузка', loaded: 'гружёный', payload: 'груз', state: 'состояние', status: 'статус',
    role: 'роль', task: 'задача', called: 'позван', call: 'вызов', busy: 'занят', free: 'свободен', at: 'у', location: 'где',
    target: 'куда', from: 'откуда', to: 'куда', route: 'маршрут', trip: 'рейс', trips: 'рейсов', count: 'число', total: 'всего',
    level: 'уровень', pressure: 'давление', temp: 'температура', temperature: 'температура', flow: 'расход', value: 'значение',
    alarm: 'тревога', limit: 'предел', fault: 'неисправность', fire: 'пожар', smoke: 'дым', water: 'вода', pipe: 'водовод',
    leak: 'утечка', eta: 'прибудет', lat: 'широта', lon: 'долгота', name: 'имя', shift: 'смена', person: 'человек',
    crew: 'бригада', truck: 'самосвал', trucks: 'самосвалов', face: 'забой', road: 'дорога', sensor: 'датчик',
    piezo: 'пьезометр', hpgr: 'HPGR', on: 'включено', cycle: 'цикл', queue: 'очередь', wait: 'ожидание', dist: 'расстояние',
    distance: 'расстояние', next: 'следующий', last: 'последний', since: 'с', until: 'до', by: 'до', exc: 'экскаватор',
    excavator: 'экскаватор', ready: 'готово', time: 'время', hours: 'часы', age: 'возраст данных', battery: 'заряд',
    signal: 'сигнал', depth: 'глубина', height: 'высота', elevation: 'отметка', bench: 'уступ', grade: 'содержание',
    ore: 'руда', waste: 'вскрыша', haul: 'вывозка', dump: 'отвал', fuel: 'топливо', rpm: 'обороты', power: 'мощность',
    current: 'ток', voltage: 'напряжение', vibration: 'вибрация', gap: 'зазор', roll: 'валок', rolls: 'валки', force: 'усилие',
    gas: 'газ', co: 'CO', people: 'люди', evac: 'эвакуация', evacuated: 'эвакуировано', zone: 'зона', intake: 'забор',
    pond: 'пруд', well: 'скважина', wells: 'скважин', pump: 'насос', pumps: 'насосов', tank: 'ёмкость', min: 'мин',
    tph: 'т/ч', kmh: 'км/ч', kpa: 'кПа', m3h: 'м³/ч', m3: 'м³', pct: '%', kw: 'кВт', mw: 'МВт', c: '°C', t: 'т', h: 'ч', m: 'м', km: 'км',
    s: 'с', usd: '$', x: 'x', y: 'y', z: 'высота', id: '№', type: 'тип', kind: 'вид', note: 'примечание', text: 'текст' };
  const UNIT_TOK = new Set(['т/ч', 'км/ч', 'кПа', 'м³/ч', 'м³', '%', 'кВт', 'МВт', '°C', 'т', 'ч', 'м', 'км', 'с', '$', 'мин']);
  function tokensRu(f) {
    const parts = String(f).split('_').filter(Boolean);
    if (!parts.length || !parts.some(p => TOK[p])) return f;
    const words = [], units = [];
    for (const p of parts) { const r = TOK[p] ?? p; (UNIT_TOK.has(r) && words.length ? units : words).push(r); }
    return words.join(' ') + (units.length ? ', ' + units.join(' ') : '');
  }
  AKT.tokensRu = tokensRu;
  const UNIT = { 't/h': 'т/ч', kW: 'кВт', MW: 'МВт', kPa: 'кПа', '%': '%', '% Cu': '% Cu', um: 'мкм', t: 'т', h: 'ч',
    min: 'мин', 'm3/h': 'м³/ч', m3: 'м³', MWh: 'МВт·ч', USD: '$', 'USD/h': '$/ч', 'g/t': 'г/т', mm: 'мм',
    'kWh/t': 'кВт·ч/т', x: '×', s: 'с', '-': '', 'kg/t': 'кг/т', km: 'км', 'KZT/kWh': 'тг/кВт·ч', m: 'м',
    'm/s': 'м/с', 'm3/t': 'м³/т', Mm3: 'млн м³', Mt: 'млн т', 't/MWh': 'т/МВт·ч', 'USD/t': '$/т', '% of Cu': '% от Cu', kt: 'тыс. т',
    'km/h': 'км/ч', kmh: 'км/ч', pct: '%', kpa: 'кПа', kw: 'кВт', mw: 'МВт', tph: 'т/ч', m3h: 'м³/ч', degC: '°C', C: '°C', '°C': '°C',
    bar: 'бар', MPa: 'МПа', V: 'В', A: 'А', kV: 'кВ', ppm: 'млн⁻¹', 'L/s': 'л/с', 'l/s': 'л/с', 'mm/s': 'мм/с', rpm: 'об/мин',
    people: 'чел.', persons: 'чел.', pcs: 'шт.', count: 'шт.', deg: '°', GWh: 'ГВт·ч', d: 'сут.', day: 'сут.' };
  AKT.unitRu = u => (u in UNIT ? UNIT[u] : (u || ''));
  const PASS = { base_tph: 'базовая производительность', belt_m: 'ширина ленты', block_t: 'масса блока',
    cake_moisture_pct: 'влажность кека', capacity_t: 'вместимость', capacity_tph: 'производительность',
    co2_factor: 'выброс CO₂ на 1 МВт·ч', conc_cu_pct: 'Cu в концентрате', cu_price: 'цена меди (LME)', design_ref: 'по проекту',
    dig_tph: 'производительность', drive_kw: 'мощность привода', drive_mw: 'мощность привода', equipment: 'оборудование',
    grade_2025_pct: 'Cu в руде, 2025', grid: 'сеть', intake_2024_mm3: 'забор воды, 2024', kind: 'тип', kio: 'КИО',
    length_km: 'длина', limit_mw: 'лимит', limit_tph: 'предел', limit_tph_per_press: 'предел одного пресса',
    live_t: 'активный запас', mass_pull_pct: 'выход пены', model: 'модель', node_tph: 'проектная нагрузка узла',
    ore_2025_mt: 'руда переработана, 2025', payable_share_pct: 'оплачиваемая доля меди', power_mw: 'мощность',
    power_tariff: 'тариф на электроэнергию', presses: 'прессов', recovery_2025_pct: 'извлечение, 2025',
    recycle_m3_t: 'оборотная вода на 1 т', residence_min: 'время флотации', scheme: 'схема', shifts: 'смены',
    shipping: 'отгрузка', size: 'размер', speed_crit_pct: 'скорость, % от критической', speed_ms: 'скорость ленты',
    stage_recovery_pct: 'извлечение операции', tact_min: 'такт', tails_solids_pct: 'твёрдое в хвостах',
    trade: 'специальность', train: 'поезд', travel_min: 'время в пути', trip_min: 'рейс самосвала',
    truck_kio: 'КИО самосвалов', truck_t: 'грузоподъёмность', trucks: 'самосвалов', underflow_solids_pct: 'твёрдое в разгрузке',
    units: 'всего', units_on: 'в работе', writer: 'кто пишет', xanthate_kg_t: 'расход ксантогената',
    block: 'блок', line: 'линия', tonnes: 'масса', est_cu: 'медь по блоку (≈)', est_axb: 'твёрдость по блоку, A×b (≈)',
    est_ascu: 'кислоторастворимая Cu (оценка блока)' };
  AKT.passKeyRu = k => PASS[k] || tokensRu(k);
  const TYPE = { site: 'площадка', pit: 'карьер', exc: 'экскаватор', batch: 'партия руды', crusher: 'дробилка ЦПД',
    conveyor: 'конвейер', stockpile: 'склад руды', line: 'линия фабрики', sag: 'мельница SAG', ball: 'шаровая мельница',
    cyclones: 'гидроциклоны', flot: 'флотация', rougher: 'основная и контрольная флотация', cleaner: 'перечистка',
    water: 'хвосты и вода', power: 'энергоснабжение', crew: 'бригада', fleet: 'парк карьера', pebble: 'дробление гали',
    thick: 'сгуститель', filter: 'фильтр', 'conc-stock': 'склад концентрата', leach: 'куча выщелачивания', sxew: 'SX-EW, катод', 'mod-losses': 'модуль «Где теряется медь»',
    'mod-ore': 'модуль «Какая руда идёт»', 'mod-priority': 'модуль «Очередь бед»', issue: 'беда', control: 'пульт модели',
    journal: 'журнал смены', 'validation-setup': 'проверка установки', 'validation-sim': 'журнал правды симулятора',
    'validation-calib': 'калибровка и проверка', baseline: 'копии модели', person: 'человек', worker: 'работник',
    sensor: 'датчик', piezometer: 'пьезометр', piezo: 'пьезометр', truck: 'самосвал', excavator: 'экскаватор', face: 'забой',
    road: 'дорога', hpgr: 'пресс дробления гали (HPGR)', phmeter: 'pH-метр флотации', analyzer: 'анализатор', weigher: 'конвейерные весы', flowmeter: 'расходомер', dozer: 'бульдозер', drill: 'буровой станок', piezometer: 'пьезометр', 'water-trouble': 'беда с водой', pipe: 'водовод', well: 'скважина', pump: 'насос' };
  AKT.typeRu = t => TYPE[t] || (t ? tokensRu(String(t).replace(/-/g, '_')) : t);
  /* states that read differently by type (the shared table is in app.js) */
  const ST_TYPE = {
    'validation-calib': { WAITING: 'ожидание', RUNNING: 'считается', DONE: 'готово', FAILED: 'ошибка' },
    batch: { PLANNED: 'в плане', DIG: 'копается', BELT: 'в пути к складу', IN_STOCK: 'на складе', DONE: 'переработана' },
    crew: { WORK: 'работает', TRAVEL: 'в пути', FREE: 'свободна', OFF: 'нет на смене' },
    site: { RUN: 'идёт', PAUSED: 'пауза', WARMUP: 'прогрев' },
    person: { WORK: 'работает', TRAVEL: 'в пути', FREE: 'свободен', OFF: 'не на смене', BUSY: 'занят', CALLED: 'позван' },
    truck: { IDLE: 'стоит без работы', MOVE: 'едет', DOWN: 'в ремонте', WAIT: 'ждёт погрузки' },
    issue: { OPEN: 'не позвали', CALLED: 'позвали', IN_WORK: 'чинят', SNOOZED: 'отложено', RESOLVED: 'устранено' },
    road: { OPEN: 'открыта', CLOSED: 'закрыта' }, face: { ACTIVE: 'в работе', FLOODED: 'подтоплен' },
    drill: { DRILLING: 'бурит', MOVING: 'переезд', IDLE: 'ждёт', DOWN: 'в ремонте' }, dozer: { WORK: 'работает', IDLE: 'ждёт', DOWN: 'в ремонте' },
    phmeter: { OK: 'исправен', DRIFT: 'дрейф подтверждён', SUSPECT: 'под подозрением' },
    exc: { DIG: 'копает', MOVE: 'переезд', IDLE: 'простой', DOWN: 'отказ, ремонт' },
  };
  AKT.stRuType = (s, name) => {
    /* a belt that stands only because no ore comes (no trip signal) is waiting, not broken */
    if (s === 'STOP' && AKT.type(name) === 'conveyor' && AKT.raw(name, 'fault') === 0) return 'ждёт руду'; const t = ST_TYPE[AKT.type(name)] || (AKT.cat ? ST_TYPE[AKT.cat(name)] : null); return t && t[s] ? t[s] : null; };
  AKT.batchStRu = s => s ? (ST_TYPE.batch[s] || AKT.stRu(s)) : '—';
  const KIND = { crusher_stop: 'дробилка стоит', lube_trip: 'защита по маслу', conveyor_stop: 'конвейер стоит',
    reline: 'перефутеровка', sag_stop: 'мельница стоит', pebble_stop: 'дробление гали стоит', ball_stop: 'шаровая стоит',
    filter_one: 'один пресс', filter_stop: 'фильтр стоит', thick_high: 'сгуститель полон на 80 %', thick_full: 'сгуститель полон',
    loss_sag: 'перерасход энергии SAG', loss_cyclones: 'потери в циклонах', loss_flot: 'потери во флотации',
    reagent_over: 'перерасход собирателя', water_leak: 'утечка воды по балансу', startup_zone: 'пуск при людях в мельнице',
    tailings_dust: 'пыление пляжа хвостохранилища', grind_coarse: 'помол крупнее нормы', conc_low: 'Cu в концентрате ниже нормы',
    loss_flot_oxide: 'окисленная руда', cstock_high: 'склад концентрата почти полон', cstock_full: 'склад концентрата полон', fleet_short: 'нехватка самосвалов', pit_stop: 'карьер не подаёт руду',
    grid_limited: 'сеть урезала мощность', dam_alarm: 'пьезометр дамбы', hard_ore: 'твёрдая руда',
    water: 'беда с водой', water_short: 'не хватает воды', water_trouble: 'беда с водой', pipe_leak: 'порыв водовода',
    intake_low: 'мало свежей воды', pond_low: 'пруд мелеет', pond_high: 'пруд переполняется', piezo_alarm: 'пьезометр дамбы',
    hpgr_fire: 'пожар на прессе дробления гали', fire: 'пожар', hpgr_stop: 'пресс дробления гали стоит', truck_down: 'самосвал сломан',
    leach_cold: 'холодное выщелачивание', exc_down: 'отказ экскаватора', face_flooded: 'забой подтоплен', road_closed: 'дорога закрыта', person_injured: 'травма',
    road_winter: 'зимняя дорога', driver_fatigue: 'усталость водителя', roping: 'канатирование', sensor_ph: 'pH-метр под подозрением',
    hpgr_uneven: 'неравномерное питание ВВД', crusher_mantle: 'замена брони', oil_contam: 'загрязнение масла',
    gmd_gap: 'воздушный зазор привода SAG', idler_hot: 'перегрев ролика конвейера', froth_swing: 'колебания уровня флотации',
    rake_torque: 'момент граблин сгустителя', cloth_blind: 'ткань фильтра слепнет', pump_cavit: 'кавитация насоса циклонов',
    brake_hot: 'перегрев тормозов самосвала', track_tension: 'натяжение гусениц экскаватора' };
  /* the title of an issue card: what is wrong, in plain words */
  const KIND_TITLE = { loss_sag: '{n}: тихий перерасход энергии', reagent_over: '{n}: перерасход собирателя',
    startup_zone: '{n}: пуск при людях внутри', tailings_dust: 'Пыление пляжа хвостохранилища', grind_coarse: '{n}: помол крупнее нормы',
    conc_low: '{n}: Cu в концентрате ниже нормы',
    water_leak: 'Утечка воды: видна только по балансу', loss_flot: '{n} теряет медь в хвостах', loss_cyclones: '{n}: крупный помол уходит на флотацию',
    crusher_stop: '{n} стоит', lube_trip: '{n}: сработала защита по маслу', conveyor_stop: '{n} стоит', sag_stop: '{n} стоит', pebble_stop: '{n} стоит',
    ball_stop: '{n} стоит', filter_one: '{n}: работает один пресс из двух', filter_stop: '{n} стоит', thick_high: '{n} заполнен на 80 %', thick_full: '{n} полон',
    cstock_high: 'Склад концентрата почти полон', cstock_full: 'Склад концентрата полон', fleet_short: 'Не хватает самосвалов', pit_stop: 'Карьер не подаёт руду',
    grid_limited: 'Сеть урезала мощность', dam_alarm: 'Дамба хвостохранилища: давление воды выше нормы', piezo_alarm: 'Дамба хвостохранилища: давление воды выше нормы',
    hard_ore: 'Идёт твёрдая руда', water: 'Беда с водой', water_short: 'Не хватает воды', water_trouble: 'Беда с водой', pipe_leak: 'Порыв водовода',
    intake_low: 'Мало свежей воды', pond_low: 'Пруд хвостохранилища мелеет', pond_high: 'Пруд хвостохранилища переполняется',
    hpgr_fire: 'Пожар на прессе дробления гали', fire: 'Пожар', hpgr_stop: 'Пресс дробления гали стоит', truck_down: 'Самосвал сломан',
    leach_cold: 'Куча выщелачивания: катод ниже нормы', exc_down: '{n}: отказ', face_flooded: '{n} подтоплен', road_closed: '{n} закрыта', person_injured: 'Травма человека', reline: '{n}: перефутеровка',
    road_winter: 'Зимняя дорога: ограничить движение', driver_fatigue: 'Усталость водителя (допущение)', roping: '{n}: канатирование',
    sensor_ph: '{n} под подозрением', hpgr_uneven: '{n}: перекос ВВД', crusher_mantle: '{n}: замена брони', oil_contam: '{n}: загрязнение масла',
    gmd_gap: '{n}: зазор привода', idler_hot: '{n}: перегрев ролика', froth_swing: '{n}: колебания уровня', rake_torque: '{n}: момент граблин',
    cloth_blind: '{n}: ткань слепнет', pump_cavit: '{n}: кавитация насоса', brake_hot: 'Перегрев тормозов самосвала', track_tension: '{n}: натяжение гусениц' };
  AKT.kindTitle = (k, nodeName) => {
    const t = KIND_TITLE[k];
    if (t) return t.replace('{n}', nodeName || 'Узел');
    return (nodeName ? nodeName + ': ' : '') + (KIND[k] || (/^[a-z0-9_]+$/.test(String(k || '')) ? tokensRu(k) : k) || 'беда');
  };
  AKT.kindRu = k => KIND[k] || (/^[a-z0-9_]+$/.test(String(k || '')) ? tokensRu(k) : k);
  const LOSS_STATUS = { loss: 'потери', unsure: 'не уверен', noise: 'в пределах точности', idle: 'стоит', feed: 'нет питания',
    no_data: 'нет данных' };
  AKT.lossStatusRu = s => LOSS_STATUS[s] || s;
  const OBJ = { seq: '№', id: 'сценарий', preset: 'набор', kip: 'бригад КИПиА', auto: 'автовызов', safety: 'учебная тревога',
    speed: 'скорость', value: 'значение', seed: 'номер прогона', start: 'старт', run: 'прогон', sim_time: 'время модели',
    t_wall: 'время на часах', issue: 'беда', action: 'действие', role: 'роль', text: 'текст', node: 'узел' };
  AKT.objKeyRu = k => { if (OBJ[k]) return OBJ[k]; const r = AKT.keyRu ? AKT.keyRu(k) : k; return r === k ? tokensRu(k) : r; };
  const SRC = { assume: 'Допущение стенда (список: aktogay/PARAMETERS.md)', calc: 'Расчёт из других величин (см. примечание)',
    stand: 'Код стенда (aktogay/)' };
  AKT.srcDoc = (key, s) => (s && (s.doc_ru || SRC[key] || s.doc)) || SRC[key] || '';
  /* features that hold a model minute (shown as a clock with the day) */
  AKT.TIME_FEATS = new Set(['sim_time', 'call_by', 'free_at', 'loss_from', 'processed_sim_time', 'resend']);
})();
