/* «Диорама»: схема расстановки всего рудника Актогай на подиуме.
   Схема, не масштаб: карьер слева, ЦПД и конвейеры, склады руды, две линии
   фабрики, склад концентрата и ж/д справа, хвостохранилище спереди,
   подстанция и ЛЭП сзади. Единицы — условные единицы подиума (у.е.):
   x — вправо, z — к зрителю, y — вверх, верх подиума y = 0.
   Глубина карьера 230 м — факт (pit.passport.depth_m); число уступов,
   их ширина, размеры зданий и машин — схема.
   Ключи — имена вещей Ditto (без «kz.aktogay:»); вещи, которых нет в таблице,
   ставятся по типу, по location / node / task, по _parents, иначе на полку
   «прочее» в углу подиума. */
import * as THREE from '../vendor/three-0.160.0/three.module.min.js';

const D2R = Math.PI / 180;

/* подиум: верх 1500 × 1000 у.е., толщина 150 у.е. (карьер помещается в толщу), тёмная подставка */
export const PLINTH = { w: 1500, d: 1000, h: 150, base: 24 };

/* карьер: эллипс по бровке, 8 уступов схемы на глубину 230 м (факт), спиральный съезд */
export const PIT = {
  cx: -430, cz: -10, rx: 270, rz: 240,
  levels: 8,            // уступов в схеме (реальных ≈ 15 по 15 м [допущение])
  benchesReal: 15,      // для перевода номера уступа из Ditto (feature bench) в уступ схемы
  depth: 120,           // у.е. по вертикали (схема) = 230 м (факт)
  depthM: 230,
  face: 0.03, berm: 0.07,                  // доли радиуса бровки: откос и берма каждого уступа
  theta0: -20 * D2R, dir: 1, turns: 1.15,  // выезд съезда на бровку и спираль вниз
  rampW: 16,
};

/* отвал вскрыши: ступенчатый курган за карьером */
export const DUMP = { x: -330, z: -405, rx: 150, rz: 62, h: 42 };

/* зоны подиума: камеры, подложка, «полка» для неизвестных вещей */
export const ZONES = {
  pit: { x: PIT.cx, z: PIT.cz, r: 280, name: 'Карьер' },
  dump: { x: DUMP.x, z: DUMP.z, r: 160, name: 'Отвал вскрыши' },
  crush: { x0: -110, x1: -30, z0: -190, z1: 135, name: 'ЦПД' },
  stock: { x0: 85, x1: 215, z0: -215, z1: 160, name: 'Склады руды' },
  plant: { x0: 235, x1: 660, z0: -215, z1: 160, name: 'Фабрика' },
  'line-1': { x0: 235, x1: 660, z0: -212, z1: -88, name: 'Фабрика, линия 1' },
  'line-2': { x0: 235, x1: 660, z0: 33, z1: 157, name: 'Фабрика, линия 2' },
  conc: { x0: 628, x1: 702, z0: -75, z1: 20, name: 'Склад концентрата' },
  rail: { x: 718, z0: -500, z1: 500, name: 'Ж/д отгрузка' },
  tails: { x0: -110, x1: 550, z0: 240, z1: 470, name: 'Хвостохранилище' },
  power: { x0: 405, x1: 535, z0: -440, z1: -370, name: 'Подстанция' },
  garage: { x0: -75, x1: 35, z0: -360, z1: -300, name: 'Ремонтный бокс' },
  abk: { x0: 160, x1: 240, z0: -318, z1: -274, name: 'АБК' },
  water: { x0: 610, x1: 690, z0: 250, z1: 320, name: 'Водовод' },
  shelf: { x0: -730, x1: -560, z0: 300, z1: 480, name: 'прочее' },
};

/* Узлы: x, z — центр на подиуме; w, d — размер площадки; h — высота верха (для подписей
   до того, как модуль нарисует узел); r — радиус для круглых (склады, сгустители). */
const L2 = 245;   // сдвиг линии 2 относительно линии 1 по z
const lineNodes = (n, z0) => ({
  [`line-${n}`]: { x: 448, z: z0, w: 425, d: 124, h: 48, zone: `line-${n}` },
  [`sag-${n}`]: { x: 272, z: z0, w: 60, d: 46, h: 44, zone: `line-${n}` },
  [`pebble-${n}`]: { x: 300, z: z0 - 46, w: 46, d: 26, h: 26, zone: `line-${n}` },
  [`ball-${n}a`]: { x: 345, z: z0 - 22, w: 54, d: 30, h: 34, zone: `line-${n}` },
  [`ball-${n}b`]: { x: 345, z: z0 + 22, w: 54, d: 30, h: 34, zone: `line-${n}` },
  [`cyclones-${n}`]: { x: 397, z: z0, w: 30, d: 30, h: 40, zone: `line-${n}` },
  [`flot-${n}`]: { x: 480, z: z0, w: 96, d: 80, h: 24, zone: `line-${n}` },
  [`rougher-${n}`]: { x: 482, z: z0 - 22, w: 96, d: 22, h: 22, zone: `line-${n}` },
  [`cleaner-${n}`]: { x: 474, z: z0 + 22, w: 78, d: 20, h: 20, zone: `line-${n}` },
  [`analyzer-${n}`]: { x: 534, z: z0 + 36, w: 12, d: 12, h: 16, zone: `line-${n}` },
  [`flowmeter-${n}`]: { x: 436, z: z0 - 44, w: 10, d: 10, h: 12, zone: `line-${n}` },
  [`thick-${n}`]: { x: 578, z: z0, r: 30, w: 60, d: 60, h: 16, zone: `line-${n}` },
  [`filter-${n}`]: { x: 634, z: z0, w: 40, d: 46, h: 30, zone: `line-${n}` },
  [`weigher-${n}`]: { x: 40, z: z0, w: 12, d: 12, h: 30, zone: 'crush' },
});
export const NODES = Object.assign({
  site: { x: 0, z: 0, h: 0, zone: 'site' },
  /* at — где стоит человек «у узла» (смотровая площадка на бровке, пульт у дамбы ...) */
  pit: { x: PIT.cx, z: PIT.cz, w: 540, d: 480, h: 0, zone: 'pit', at: [-240, -235] },
  dump: { x: DUMP.x, z: DUMP.z, w: 300, d: 124, h: DUMP.h, zone: 'dump' },
  fleet: { x: -20, z: -330, w: 90, d: 50, h: 22, zone: 'garage' },
  /* АБК: здесь ждут свободные бригады без места в Ditto (схема) */
  abk: { x: 200, z: -296, w: 64, d: 30, h: 16, zone: 'abk', at: [200, -272] },
  'crusher-1': { x: -70, z: -150, w: 60, d: 50, h: 46, zone: 'crush' },
  'crusher-2': { x: -70, z: 95, w: 60, d: 50, h: 46, zone: 'crush' },
  'conveyor-1': { x: 40, z: -150, w: 190, d: 10, h: 30, zone: 'crush' },
  'conveyor-2': { x: 40, z: 95, w: 190, d: 10, h: 30, zone: 'crush' },
  'stockpile-1': { x: 150, z: -150, r: 62, w: 124, d: 124, h: 52, zone: 'stock' },
  'stockpile-2': { x: 150, z: 95, r: 62, w: 124, d: 124, h: 52, zone: 'stock' },
  'conc-stock': { x: 665, z: -28, w: 70, d: 90, h: 26, zone: 'conc' },
  rail: { x: 718, z: 0, w: 14, d: 1000, h: 8, zone: 'rail' },
  power: { x: 470, z: -405, w: 120, d: 64, h: 30, zone: 'power' },
  water: { x: 220, z: 355, w: 660, d: 230, h: 4, zone: 'tails', at: [578, 330] },
  'water-tank': { x: 650, z: 285, r: 22, w: 44, d: 44, h: 18, zone: 'water' },
  'piezo-1': { x: 20, z: 462, w: 8, d: 8, h: 14, zone: 'tails' },
  'piezo-2': { x: 220, z: 462, w: 8, d: 8, h: 14, zone: 'tails' },
  'piezo-3': { x: 420, z: 462, w: 8, d: 8, h: 14, zone: 'tails' },
}, lineNodes(1, -150), lineNodes(2, -150 + L2));

/* линии схемы (x, z): подача воды, хвостопроводы, ЛЭП, ж/д — по ним модули строят трубы и провода */
export const LINES = {
  'pipe-fresh': [[750, 300], [690, 296], [650, 285], [612, 210], [600, 160]],
  'pipe-recycle': [[400, 405], [420, 300], [520, 200], [560, 160]],
  'pipe-tails-1': [[520, -100], [560, -40], [560, 120], [480, 200], [380, 245]],
  'pipe-tails-2': [[520, 150], [470, 200], [300, 245]],
  'power-line': [[750, -455], [640, -440], [535, -420]],
  'power-feed-1': [[420, -372], [380, -300], [350, -215]],
  'power-feed-2': [[460, -372], [600, -260], [610, 30]],
  'power-crush': [[405, -400], [100, -330], [-40, -180]],
  rail: [[718, -500], [718, 500]],
  'feed-1': [[150, -150], [205, -150], [250, -150]],
  'feed-2': [[150, 95], [205, 95], [250, 95]],
  'conveyor-1': [[-40, -150], [40, -150], [150, -150]],
  'conveyor-2': [[-40, 95], [40, 95], [150, 95]],
};

/* углы забоев (градусы, от +x к +z); уступ — из Ditto (feature bench) */
const FACE_ANG = { 'face-1': 160, 'face-2': 105, 'face-3': 225, 'face-4': 60, 'face-5': 275 };

/* ------------------------------------------------------------ pit math */
const F = PIT.face, B = PIT.berm, N = PIT.levels;
/* радиус бровки в направлении θ: эллипс с лёгкой неровностью */
export function pitR(th) {
  const c = Math.cos(th), s = Math.sin(th);
  const re = (PIT.rx * PIT.rz) / Math.sqrt((PIT.rz * c) ** 2 + (PIT.rx * s) ** 2);
  return re * (1 + 0.035 * Math.sin(3 * th + 0.6) + 0.02 * Math.cos(5 * th - 0.3));
}
export const crestS = L => 1 - L * (F + B);                 // бровка уступа L (0 — верх карьера)
export const toeS = L => crestS(L - 1) - F;                 // подошва откоса уступа L
export const bermS = L => crestS(L) + B / 2;                // середина бермы уступа L
export const levelY = L => -PIT.depth * L / N;
export const FLOOR_S = crestS(N);
/* высота ступенчатого профиля по доле радиуса s (1 — бровка, 0 — центр) */
export function stepH(s) {
  if (s >= 1) return 0;
  for (let L = 1; L <= N; L++) {
    if (s >= toeS(L)) return levelY(L - 1) + (levelY(L) - levelY(L - 1)) * (crestS(L - 1) - s) / F;
    if (s >= crestS(L)) return levelY(L);
  }
  return levelY(N);
}
/* точка съезда: t = 0 — выезд на бровку, t = 1 — дно */
export function rampAt(t) {
  const th = PIT.theta0 + PIT.dir * PIT.turns * 2 * Math.PI * t;
  const s = 1 + B / 2 - (1 - FLOOR_S) * t;
  const R = pitR(th);
  return { th, s, R, x: PIT.cx + s * R * Math.cos(th), z: PIT.cz + s * R * Math.sin(th), y: -PIT.depth * t };
}
/* полярные координаты точки подиума относительно карьера */
export function pitPolar(x, z) {
  const dx = x - PIT.cx, dz = z - PIT.cz;
  const th = Math.atan2(dz, dx);
  return { th, s: Math.hypot(dx, dz) / pitR(th) };
}
/* съезд на этом угле: ближайший виток, {t, s} или null */
export function rampNear(th, s) {
  const per = PIT.turns * 2 * Math.PI;
  let best = null;
  const base = ((th - PIT.theta0) * PIT.dir) % (2 * Math.PI);
  for (let k = -1; k <= Math.ceil(PIT.turns) + 1; k++) {
    const t = (base + 2 * Math.PI * k) / per;
    if (t < -0.02 || t > 1.02) continue;
    const tt = Math.max(0, Math.min(1, t));
    const rs = 1 + B / 2 - (1 - FLOOR_S) * tt;
    if (!best || Math.abs(rs - s) < Math.abs(best.s - s)) best = { t: tt, s: rs };
  }
  return best;
}
/* высота отвала вскрыши: три яруса по ≈ 14 у.е. */
export function dumpH(x, z) {
  const e = Math.hypot((x - DUMP.x) / DUMP.rx, (z - DUMP.z) / DUMP.rz);
  if (e >= 1) return 0;
  const k = DUMP.h / 3;
  if (e <= 0.5) return 3 * k;
  if (e <= 0.6) return 3 * k - k * (e - 0.5) / 0.1;
  if (e <= 0.72) return 2 * k;
  if (e <= 0.82) return 2 * k - k * (e - 0.72) / 0.1;
  if (e <= 0.9) return k;
  return k - k * (e - 0.9) / 0.1;
}
/* высота земли в точке подиума: уступы карьера (без выемки съезда), отвал, иначе 0 */
export function groundAt(x, z) {
  const p = pitPolar(x, z);
  if (p.s < 1) return stepH(p.s);
  return dumpH(x, z);
}
/* уступ схемы по номеру уступа из Ditto (feature bench) */
export const benchLevel = b => (typeof b === 'number' && isFinite(b) && b > 0)
  ? Math.max(1, Math.min(N, Math.round(b * N / PIT.benchesReal))) : Math.ceil(N / 2);
/* угол съезда на уступе L */
export const rampAngle = L => PIT.theta0 + PIT.dir * PIT.turns * 2 * Math.PI * (L / N);
const angDiff = (a, b) => { let d = (a - b) % (2 * Math.PI); if (d > Math.PI) d -= 2 * Math.PI; if (d < -Math.PI) d += 2 * Math.PI; return d; };
export { angDiff };

/* ------------------------------------------------------------ PolyCurve */
/* Ломаная с параметризацией по длине: getPoint(u) == getPointAt(u), u ∈ [0, 1]. */
export class PolyCurve extends THREE.Curve {
  constructor(points) {
    super();
    this.points = points.filter((p, i) => i === 0 || p.distanceToSquared(points[i - 1]) > 1e-6);
    if (this.points.length === 1) this.points.push(this.points[0].clone());
    this.cum = [0];
    for (let i = 1; i < this.points.length; i++) this.cum.push(this.cum[i - 1] + this.points[i].distanceTo(this.points[i - 1]));
    this.len = this.cum[this.cum.length - 1];
  }
  _seg(d) {
    let lo = 1, hi = this.cum.length - 1;
    while (lo < hi) { const m = (lo + hi) >> 1; if (this.cum[m] < d) lo = m + 1; else hi = m; }
    return lo;
  }
  getPoint(u, target = new THREE.Vector3()) {
    const d = Math.max(0, Math.min(1, u)) * this.len;
    const i = this._seg(d), a = this.points[i - 1], b = this.points[i];
    const seg = this.cum[i] - this.cum[i - 1];
    return target.lerpVectors(a, b, seg > 0 ? (d - this.cum[i - 1]) / seg : 0);
  }
  getPointAt(u, target) { return this.getPoint(u, target); }
  getTangent(u, target = new THREE.Vector3()) {
    const d = Math.max(0, Math.min(1, u)) * this.len;
    const i = this._seg(d);
    return target.subVectors(this.points[i], this.points[i - 1]).normalize();
  }
  getTangentAt(u, target) { return this.getTangent(u, target); }
  getLength() { return this.len; }
  getLengths(div) { const out = []; for (let i = 0; i <= (div || 200); i++) out.push(this.len * i / (div || 200)); return out; }
  /* точка на расстоянии d у.е. от начала (d < 0 — от конца) */
  at(d, target) { return this.getPoint((d < 0 ? this.len + d : d) / (this.len || 1), target); }
  reversed() { return new PolyCurve(this.points.slice().reverse()); }
  static concat(...curves) { return new PolyCurve([].concat(...curves.filter(Boolean).map(c => c.points))); }
}

/* ------------------------------------------------------------ layout */
/* Раскладка для текущего списка вещей. pos(id) — точка на земле (y — высота земли или уступа),
   top(id) — точка над узлом для подписи, face(id) — забой на уступе, around(id, i, n) — места
   вокруг узла для нескольких вещей. Кэш по опросу: refresh() вызывает ядро после каждого опроса. */
export function makeLayout(AKT) {
  const V = (x, y, z) => new THREE.Vector3(x, y, z);
  const name = v => AKT.name(String(v || ''));
  let paths = null;                     // pathFor из ядра (дороги карьера, ЛЭП ...)
  let cache = new Map(), faceCache = new Map(), shelf = new Map();

  const nodeOf = id => NODES[id] || null;
  const excFace = exc => {
    for (const f of AKT.ofType('face')) if (name(AKT.pass(f, 'excavator')) === exc) return f;
    const m = /-(\d+)$/.exec(exc); return m && AKT.things['face-' + m[1]] ? 'face-' + m[1] : null;
  };
  function face(id) {
    if (faceCache.has(id)) return faceCache.get(id);
    let f = null;
    if (AKT.things[id] || FACE_ANG[id] != null) {
      const L = benchLevel(AKT.num(id, 'bench') ?? AKT.pass(id, 'bench'));
      const i = Math.max(0, AKT.ofType('face').indexOf(id));
      let th = (FACE_ANG[id] != null ? FACE_ANG[id] : 40 + 67 * i) * D2R;
      /* не на съезде: отодвинуть от точки съезда на этом уступе */
      const dr = angDiff(th, rampAngle(L));
      if (Math.abs(dr) < 40 * D2R) th = rampAngle(L) + Math.sign(dr || 1) * 40 * D2R;
      const R = pitR(th), s = bermS(L), y = levelY(L);
      const c = Math.cos(th), sn = Math.sin(th);
      f = {
        id, level: L, angle: th, s, y,
        pos: V(PIT.cx + s * R * c, y, PIT.cz + s * R * sn),                         // середина бермы
        wall: V(PIT.cx + toeS(L) * R * c, y, PIT.cz + toeS(L) * R * sn),            // подошва откоса (забой)
        out: V(c, 0, sn),                                                            // наружу, к стенке
        tangent: V(-sn, 0, c),                                                       // вдоль бермы
      };
    }
    faceCache.set(id, f);
    return f;
  }
  function shelfPos(id) {
    if (!shelf.has(id)) {
      const z = ZONES.shelf, i = shelf.size, cols = 6;
      shelf.set(id, V(z.x0 + 15 + (i % cols) * 28, 0, z.z0 + 15 + Math.floor(i / cols) * 28));
    }
    return shelf.get(id).clone();
  }
  const ROAD = /^(ramp-\d+|road-[a-z0-9-]+)$/;
  /* где стоит человек у узла: node.at, иначе перед узлом (край площадки к зрителю) */
  function stand(id) {
    const n = nodeOf(id);
    if (n && n.at) return V(n.at[0], groundAt(n.at[0], n.at[1]), n.at[1]);
    if (n && n.d) { const z = n.z + n.d / 2 + 8; return V(n.x, groundAt(n.x, z), z); }
    if (/^face-/.test(id)) { const f = face(id); if (f) return f.pos.clone().addScaledVector(f.tangent, 14); }
    return resolve(id, 9);
  }
  function resolve(id, depth) {
    if (!id) return null;
    const n = nodeOf(id);
    if (n) return V(n.x, groundAt(n.x, n.z), n.z);
    if (/^face-/.test(id) || AKT.type(id) === 'face') { const f = face(id); return f ? f.pos.clone() : null; }
    if (ROAD.test(id) || AKT.cat(id) === 'road') {
      const c = paths && paths(id);
      if (c) return c.getPoint(0.5);
    }
    if (depth > 3 || !AKT.things[id]) return null;
    const cat = AKT.cat(id), type = AKT.type(id);
    if (type === 'exc' || cat === 'exc') { const f = excFace(id); return f ? face(f).pos.clone() : V(PIT.cx, levelY(N), PIT.cz); }
    if (/^(mod-|validation-)/.test(type) || ['baseline', 'control', 'journal'].includes(type)) return null;
    /* по ссылкам: где стоит, к какому узлу относится; люди — у узла (stand), не в нём */
    const human = cat === 'person' || cat === 'crew';
    const keys = cat === 'truck' ? ['location'] : ['location', 'node', 'at', 'place', 'face', 'task', 'target'];
    for (const k of keys) {
      let v = AKT.val(id, k);
      if (v == null && k !== 'location') v = AKT.pass(id, k);
      const r = typeof v === 'string' ? name(v) : '';
      if (r && r !== id && (nodeOf(r) || AKT.things[r])) { const p = human ? stand(r) : resolve(r, depth + 1); if (p) return p; }
    }
    if (cat === 'truck') return resolve('fleet', depth + 1);          // нет места (ремонт) — в ремонтном боксе
    if (human) { const h = name(AKT.pass(id, 'home')); if (h) { const p = stand(h); if (p) return p; } }
    if (cat === 'crew') return stand('abk');                          // бригада без места — у АБК
    const par = AKT.parent(id);
    if (par && par !== 'site' && par !== id) { const p = resolve(par, depth + 1); if (p) return p; }
    return shelfPos(id);
  }
  const L = {
    PLINTH, PIT, DUMP, ZONES, NODES, LINES,
    node: nodeOf,
    face,
    excFace,
    /* точка на земле, где стоит вещь (копия вектора) */
    pos(id) {
      id = name(id);
      if (!cache.has(id)) cache.set(id, resolve(id, 0));
      const p = cache.get(id);
      return p ? p.clone() : null;
    },
    /* где стоит человек у узла (node.at или перед узлом) */
    stand(id) { const p = stand(name(id)); return p ? p.clone() : null; },
    /* точка над вещью для подписи: верх узла из таблицы или +lift */
    top(id, lift) {
      const p = L.pos(id); if (!p) return null;
      const n = nodeOf(name(id));
      p.y += (n && n.h != null ? n.h : 10) + (lift || 0);
      return p;
    },
    /* i-е из n мест вокруг узла (спираль), для нескольких вещей в одном месте */
    around(id, i, n, step) {
      const p = L.pos(id); if (!p) return null;
      if (!n || n <= 1) return p;
      const r = (step || 14) * Math.sqrt(i + 0.6), a = 2.39996 * i;
      p.x += r * Math.cos(a); p.z += r * Math.sin(a); p.y = groundAt(p.x, p.z);
      return p;
    },
    zone: k => ZONES[k] || null,
    zoneOf: id => { const n = nodeOf(name(id)); return n ? n.zone : null; },
    line: k => LINES[k] ? LINES[k].map(([x, z]) => V(x, groundAt(x, z), z)) : null,
    groundAt,
    refresh() { cache = new Map(); faceCache = new Map(); },
    attachPaths(fn) { paths = fn; cache = new Map(); },
  };
  return L;
}
