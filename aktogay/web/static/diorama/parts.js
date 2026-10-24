/* «Диорама», разбор машин: чистая логика без three.js (проверяется в node тестом).
   Таблица частей пяти объектов (самосвал CAT 793, экскаватор Hitachi, мельница SAG, дробилка ЦПД, конвейер),
   привязка части к узлу «Изнутри» (inside.json), выбор сигналов узла для части, подсветка части по открытой беде
   и по прогнозу перефутеровки. Данные — только то, что передано аргументами (Ditto, InfluxDB через AKT). */

/* вид объекта по имени вещи Ditto */
export function kindOf(id) {
  const s = String(id || '');
  if (/^truck-/.test(s)) return 'truck';
  if (/^exc-/.test(s)) return 'exc';
  if (/^sag-\d+$/.test(s)) return 'sag';
  if (/^crusher-\d+$/.test(s)) return 'crusher';
  if (/^conveyor-\d+$/.test(s)) return 'conveyor';
  if (/^ball-\d[ab]$/.test(s)) return 'ball';
  if (/^pebble-\d+$/.test(s)) return 'hpgr';
  if (/^flot-\d+$/.test(s)) return 'flot';
  if (/^cyclones-\d+$/.test(s)) return 'cyclones';
  if (/^thick-\d+$/.test(s)) return 'thick';
  if (/^filter-\d+$/.test(s)) return 'filter';
  if (/^pump-\d+$/.test(s)) return 'pump';       // шламовый насос открывается из карточки циклонов и шаровой (вещи у него нет)
  return '';
}

/* Часть: id, подпись, узел «Изнутри» (node) — для самосвала и экскаватора узел зависит от модели (nodeBy),
   sig — подстроки (без регистра) имени сигнала узла или имя признака Ditto, troubles — виды бед, красящие часть,
   explode — смещение при разборе (доли размера модели), cut — убирается в разрезе (мельница). */
export const KINDS = {
  truck: {
    ru: 'Самосвал CAT 793', node: 'm-cat793', mode: 'explode',
    whole: [],
    parts: [
      { id: 'chassis', ru: 'Рама и мосты', sig: [], troubles: [], explode: [0, -0.35, 0] },
      { id: 'engine', ru: 'Двигатель', sig: ['охлаж', 'ож двигателя', 'давление масла', 'топлива'], troubles: [], explode: [0.9, 0.35, 0] },
      { id: 'trans', ru: 'Трансмиссия', sig: ['трансмисс', 'передач', 'гидротрансформатор'], troubles: [], explode: [0.1, 0.55, 0] },
      { id: 'brakes', ru: 'Тормоза', sig: ['тормоз'], troubles: ['road_winter', 'brake_hot'], explode: [-0.3, -0.1, 0.9] },
      { id: 'wheels', ru: 'Колёса (6)', sig: ['vims', 'цикл рейса'], troubles: ['road_winter'], explode: [0, 0, 1.1] },
      { id: 'cab', ru: 'Кабина', sig: ['vims', 'message center'], troubles: ['driver_fatigue'], explode: [0.7, 1.0, -0.4] },
      { id: 'body', ru: 'Кузов', sig: ['груз на борту'], troubles: ['fleet_short'], explode: [-0.8, 1.1, 0] },
    ],
  },
  exc: {
    ru: 'Экскаватор Hitachi', node: 'm-ex3600', mode: 'explode', nodeBy: { 'exc-1': 'm-ex3600', 'exc-5': 'm-ex1200', other: 'm-ex-other' },
    whole: ['exc_down'],
    parts: [
      { id: 'tracks', ru: 'Ходовая (гусеницы)', sig: ['гусениц', 'натяжение'], troubles: ['track_tension'], explode: [0, -0.9, 0] },
      { id: 'swing', ru: 'Поворотный механизм', sig: ['e-p control', 'поворот'], troubles: [], explode: [0, -0.35, 0] },
      { id: 'pumps', ru: 'Гидронасосы', sig: ['гидромасл', 'насос', 'e-p control', 'oil_pct', 'oil_alert'], troubles: ['oil_contam'], explode: [-0.9, 0.2, 0.6] },
      { id: 'cylinders', ru: 'Гидроцилиндры', sig: ['гидромасл', 'oil_pct', 'oil_alert', 'рабочей жидкости'], troubles: ['oil_contam'], explode: [0.6, 0.7, 0.9] },
      { id: 'engine', ru: 'Двигатель', sig: ['давление масла двигателя', 'ож', 'топлива'], troubles: [], explode: [-1.0, 0.7, -0.6] },
      { id: 'cab', ru: 'Кабина и надстройка', sig: ['индикаторы кабины', 'указатели'], troubles: [], explode: [0.5, 1.3, -0.8] },
      { id: 'boom', ru: 'Стрела и рукоять', sig: ['копает', 'tph'], troubles: [], explode: [0.9, 0.5, 0] },
      { id: 'bucket', ru: 'Ковш', sig: ['копает', 'tph'], troubles: [], explode: [1.5, 0.1, 0] },
    ],
  },
  sag: {
    ru: 'Мельница SAG', node: 'p-sag', mode: 'cut',
    whole: ['sag_stop'],
    parts: [
      { id: 'shell', ru: 'Барабан', sig: ['питание'], troubles: [], explode: [0, 0, 0] },
      { id: 'liner', ru: 'Футеровка', sig: ['тоннаж', 'liner_ground_t'], troubles: ['reline'], forecast: 'liner', explode: [0, 0, 0] },
      { id: 'charge', ru: 'Загрузка (руда, шары)', sig: ['питание', 'feed_tph'], troubles: [], explode: [0, 0, 0] },
      { id: 'motor', ru: 'Кольцевой двигатель (ГМД)', sig: ['гмд', 'мощность', 'зазор'], troubles: ['gmd_gap'], explode: [0, 0, 0] },
      { id: 'chute', ru: 'Загрузочная течка', sig: ['питание', 'feed_tph'], troubles: [], explode: [0, 0, 0] },
      { id: 'trommel', ru: 'Бутара (грохот)', sig: [], troubles: [], explode: [0, 0, 0] },
    ],
  },
  crusher: {
    ru: 'Конусная дробилка ЦПД', node: 'p-crusher', mode: 'cut',
    whole: ['crusher_stop'],
    parts: [
      { id: 'mantle', ru: 'Мантия и конус', sig: ['замена брони', 'service'], troubles: ['crusher_mantle'], explode: [0, 0.9, 0] },
      { id: 'concave', ru: 'Броня чаши', sig: ['замена брони', 'service'], troubles: ['crusher_mantle'], explode: [0, 0.4, 0] },
      { id: 'shaft', ru: 'Эксцентриковый вал', sig: ['давление масла'], troubles: ['lube_trip'], explode: [0, -0.2, 0] },
      { id: 'lube', ru: 'Маслосистема', sig: ['давление масла', 'lube_kpa'], troubles: ['lube_trip'], explode: [0.8, -0.3, 0] },
      { id: 'frame', ru: 'Корпус и фундамент', sig: [], troubles: [], explode: [0, -0.6, 0] },
      { id: 'hopper', ru: 'Приёмный бункер', sig: ['производительность', 'tph'], troubles: [], explode: [0, 1.5, 0] },
    ],
  },
  conveyor: {
    ru: 'Ленточный конвейер', node: 'p-conveyor', mode: 'explode',
    whole: ['conveyor_stop'],
    parts: [
      { id: 'belt', ru: 'Лента', sig: ['производительность'], troubles: [], explode: [0, 0.5, 0] },
      { id: 'idlers', ru: 'Ролики', sig: ['температура подшипника'], troubles: ['idler_hot'], explode: [0, -0.2, 0] },
      { id: 'drive', ru: 'Привод и редуктор', sig: ['защиты'], troubles: ['conveyor_stop'], explode: [0.9, 0, 0] },
      { id: 'frame', ru: 'Став и опоры', sig: [], troubles: [], explode: [0, -0.8, 0] },
    ],
  },
  ball: {
    ru: 'Шаровая мельница', node: 'p-grind', mode: 'cut',
    whole: ['ball_stop'],
    parts: [
      { id: 'shell', ru: 'Барабан', sig: [], troubles: [], explode: [0, 0, 0] },
      { id: 'liner', ru: 'Футеровка', sig: [], troubles: [], explode: [0, 0, 0] },
      { id: 'charge', ru: 'Шаровая загрузка и пульпа', sig: ['нагрузка шаровой', 'power_pct'], troubles: ['ball_stop'], explode: [0, 0, 0] },
      { id: 'motor', ru: 'Кольцевой двигатель (ГМД) и привод', sig: ['нагрузка шаровой', 'power_pct'], troubles: ['ball_stop'], explode: [0, 0, 0] },
      { id: 'trunnion', ru: 'Цапфы, подшипники, питатель', sig: [], troubles: [], explode: [0, 0, 0] },
    ],
  },
  hpgr: {
    ru: 'ВВД (пресс валкового измельчения)', node: 'p-hpgr', mode: 'explode',
    whole: ['hpgr_fire', 'pebble_stop'],
    parts: [
      { id: 'roll1', ru: 'Валок 1 (неподвижный)', sig: ['перекос зазора', 'разница мощности'], troubles: ['hpgr_uneven'], explode: [-0.7, 0, 0] },
      { id: 'roll2', ru: 'Валок 2 (подвижный)', sig: ['перекос зазора', 'разница мощности'], troubles: ['hpgr_uneven'], explode: [0.7, 0, 0] },
      { id: 'drives', ru: 'Приводы валков (2 × 1 750 кВт)', sig: ['мощность двух приводов', 'разница мощности'], troubles: ['hpgr_uneven', 'hpgr_fire'], explode: [0, 0, 0.9] },
      { id: 'press', ru: 'Гидравлика поджатия', sig: [], troubles: [], explode: [1.1, 0, 0] },
      { id: 'hopper', ru: 'Питающий бункер', sig: ['перекос зазора'], troubles: ['hpgr_uneven'], explode: [0, 0.6, 0] },
      { id: 'detector', ru: 'Металлодетектор', sig: ['металлодетектор'], troubles: ['hpgr_uneven'], explode: [0, 1.0, 0] },
      { id: 'frame', ru: 'Рама', sig: [], troubles: [], explode: [0, -0.5, 0] },
    ],
  },
  flot: {
    ru: 'Флотомашина', node: 'p-flot', mode: 'cut',
    whole: [],
    parts: [
      { id: 'tank', ru: 'Чан (камера)', sig: ['извлечение'], troubles: ['loss_flot', 'froth_swing'], explode: [0, 0, 0] },
      { id: 'rotor', ru: 'Ротор', sig: [], troubles: ['reagent_over'], explode: [0, 0, 0] },
      { id: 'stator', ru: 'Статор', sig: [], troubles: [], explode: [0, 0, 0] },
      { id: 'launder', ru: 'Пенный жёлоб', sig: ['извлечение'], troubles: ['conc_low', 'loss_flot_oxide'], explode: [0, 0, 0] },
      { id: 'drive', ru: 'Привод механизма', sig: [], troubles: [], explode: [0, 0, 0] },
      { id: 'level', ru: 'Датчик уровня', sig: ['уровень ячеек', 'размах уровня'], troubles: ['froth_swing'], explode: [0, 0, 0] },
    ],
  },
  cyclones: {
    ru: 'Кассета гидроциклонов', node: 'p-grind', mode: 'explode',
    whole: [],
    parts: [
      { id: 'cyclones', ru: 'Гидроциклоны (корпуса)', sig: ['циркулирующая', 'p80'], troubles: ['roping', 'grind_coarse'], explode: [0, 0.2, 0] },
      { id: 'apex', ru: 'Пески: насадки (апекс)', sig: ['циркулирующая'], troubles: ['roping'], explode: [0, -0.8, 0] },
      { id: 'distributor', ru: 'Питающий коллектор', sig: ['давление питания', 'напор насоса'], troubles: ['pump_cavit'], explode: [0, -0.3, 0] },
      { id: 'overflow', ru: 'Слив: сливные патрубки', sig: ['p80'], troubles: ['loss_cyclones', 'grind_coarse'], explode: [0, 0.9, 0] },
      { id: 'frame', ru: 'Рама', sig: [], troubles: [], explode: [0, -0.5, 0] },
    ],
  },
  thick: {
    ru: 'Сгуститель концентрата', node: 'p-thick', mode: 'cut',
    whole: [],
    parts: [
      { id: 'tank', ru: 'Чан с конусом и слоем осадка', sig: ['запас в сгустителе', 'inventory_t'], troubles: ['thick_high', 'thick_full'], explode: [0, 0, 0] },
      { id: 'rake', ru: 'Граблины', sig: ['момент граблин'], troubles: ['rake_torque'], explode: [0, 0, 0] },
      { id: 'drive', ru: 'Привод граблин (крутящий момент)', sig: ['крутящий момент', 'момент граблин'], troubles: ['rake_torque'], explode: [0, 0, 0] },
      { id: 'feedwell', ru: 'Питающий колодец', sig: [], troubles: [], explode: [0, 0, 0] },
      { id: 'launder', ru: 'Сливной жёлоб', sig: [], troubles: [], explode: [0, 0, 0] },
    ],
  },
  filter: {
    ru: 'Фильтр-пресс', node: 'p-filter', mode: 'explode',
    whole: ['filter_stop'],
    parts: [
      { id: 'plates', ru: 'Фильтровальные плиты', sig: ['прессов в работе', 'кек'], troubles: ['filter_one', 'filter_stop'], explode: [0, 0.5, 0] },
      { id: 'cloth', ru: 'Фильтровальное полотно', sig: ['влажность кека', 'цикл фильтрации'], troubles: ['filter_one', 'cloth_blind'], explode: [0, 1.1, 0] },
      { id: 'ram', ru: 'Гидроцилиндр и маслостанция', sig: [], troubles: ['filter_stop'], explode: [0.7, 0, 0.3] },
      { id: 'frame', ru: 'Станина и неподвижная плита', sig: [], troubles: [], explode: [-0.3, -0.4, 0] },
    ],
  },
  pump: {
    ru: 'Шламовый насос', node: 'p-pumps', mode: 'explode',
    whole: [],
    parts: [
      { id: 'casing', ru: 'Корпус (улитка)', sig: ['износа насоса'], troubles: [], explode: [-0.9, 0.2, 0] },
      { id: 'impeller', ru: 'Рабочее колесо', sig: ['кавитация', 'кпд', 'напор насоса'], troubles: ['pump_cavit'], explode: [-0.4, 0.8, 0] },
      { id: 'gland', ru: 'Сальник (уплотнение вала)', sig: ['сальник'], troubles: [], explode: [0.1, 0.9, 0] },
      { id: 'bearings', ru: 'Подшипниковый узел', sig: ['подшипники'], troubles: [], explode: [0.6, 0.5, 0] },
      { id: 'base', ru: 'Двигатель и рама', sig: [], troubles: [], explode: [0.3, -0.5, 0] },
    ],
  },
};

/* узел «Изнутри» для вещи */
export function nodeOf(id) {
  const k = kindOf(id), K = KINDS[k];
  if (!K) return '';
  if (K.nodeBy) return K.nodeBy[id] || K.nodeBy.other || K.node;
  return K.node;
}

export const partsOf = kind => (KINDS[kind] ? KINDS[kind].parts : []);
export const partById = (kind, pid) => partsOf(kind).find(p => p.id === pid) || null;

/* сигналы узла (inside.json: groups[].nodes[]) для части: совпадение подстроки в имени или признаке; без совпадений — пусто */
export function findNode(D, nodeId) {
  for (const g of (D && D.groups) || []) for (const nd of g.nodes || []) if (nd.id === nodeId) return nd;
  return null;
}
export function partSignals(D, kind, id, partId) {
  const part = partById(kind, partId), nd = findNode(D, nodeOf(id));
  if (!part || !nd) return [];
  const keys = part.sig.map(s => s.toLowerCase());
  return (nd.signals || []).filter(s => {
    const hay = `${s.name || ''} ${s.feature || ''}`.toLowerCase();
    return keys.some(k => hay.includes(k));
  });
}

/* метка доказательности по полю where сигнала */
export const EVIDENCE = {
  machine: 'на машине',
  sent: 'передаётся, если подключена опция',
  analog: 'аналог другой модели',
  dcs: 'в диспетчерской системе',
  lab: 'лаборатория / ручная проба',
  model: 'расчёт модели',
  assumption: 'допущение',
};
export const evidenceRu = where => EVIDENCE[where] || String(where || '');

/* Подсветка: openKinds — множество видов открытых бед (по вещи или по её узлу), forecast — {share, days_to_end} из прогноза.
   Результат для части: '' | 'warn' | 'issue'. Прогноз перефутеровки: ближе 14 суток или наработка от 90 %. */
export const LINER_NEAR_DAYS = 14, LINER_NEAR_SHARE = 0.9;
export function linerNear(fc) {
  if (!fc) return false;
  if (typeof fc.days_to_end === 'number' && fc.days_to_end >= 0 && fc.days_to_end <= LINER_NEAR_DAYS) return true;
  return typeof fc.share === 'number' && fc.share >= LINER_NEAR_SHARE;
}
export function highlightOf(kind, partId, openKinds, forecast) {
  const part = partById(kind, partId);
  if (!part) return '';
  const open = openKinds instanceof Set ? openKinds : new Set(openKinds || []);
  if (part.troubles.some(t => open.has(t))) return 'issue';
  if (part.forecast === 'liner' && linerNear(forecast)) return 'warn';
  return '';
}
/* вся машина стоит / отказ: кольцо под моделью */
export function wholeAlarm(kind, openKinds) {
  const K = KINDS[kind], open = openKinds instanceof Set ? openKinds : new Set(openKinds || []);
  return !!K && K.whole.some(t => open.has(t));
}
/* смещение части при разборе: масштаб k от 0 (собрано) до 1 (разобрано); size — размер модели */
export function explodeOffset(part, k, size) {
  const e = part.explode || [0, 0, 0];
  return [e[0] * size * k, e[1] * size * k, e[2] * size * k];
}

/* кнопка разбора: «Разобрать» / «Собрать» или «Разрез» / «Убрать разрез» */
export const modeOf = kind => (KINDS[kind] ? KINDS[kind].mode : 'explode');
export const toggleText = (kind, on) => (modeOf(kind) === 'cut' ? (on ? 'Убрать разрез' : 'Разрез') : (on ? 'Собрать' : 'Разобрать'));
