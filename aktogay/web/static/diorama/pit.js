/* «Диорама»: карьер, спиральный съезд, отвал вскрыши и технологические дороги.
   Карьер — ступенчатая воронка (8 уступов схемы на 230 м, глубина — факт,
   уступы — схема), съезд вырезан в бортах, цвета пород по глубине (те же
   слои, что на срезе подиума). Дороги — ленты по поверхности; их осевые
   линии — кривые для самосвалов (PolyCurve, параметр по длине):
     'spiral'                съезд от дна (u = 0) до выезда на бровку (u = 1)
     'ramp-1', 'ramp-2'      выезд → разгрузка у ЦПД-1 / ЦПД-2 (вещи road в Ditto)
     'road-dump'             выезд → верх отвала вскрыши
     'garage'                выезд → ремонтный бокс
     'face-N'                от места погрузки у забоя по берме до съезда
     'haul:face-N:<дорога>'  весь гружёный рейс: забой → съезд → дорога → разгрузка
   Порожний рейс — та же кривая в обратную сторону (u → 1 − u).
   Свет запечён в цвета вершин (ctx.bake, плоское затенение), без карт теней. */
import * as THREE from '../vendor/three-0.160.0/three.module.min.js';
import {
  PIT, DUMP, PolyCurve, pitR, crestS, toeS, levelY, stepH, rampAt, rampNear, dumpH, FLOOR_S, rampAngle, angDiff,
} from './layout.js';

/* слои пород по глубине у.е. (верх подиума 0, низ −150): общие для бортов карьера и среза подиума */
export const STRATA = [
  [0, 0xc2ad84],      // степь, суглинок
  [-7, 0xc79c6b],     // зона окисления (охра)
  [-30, 0xb48c6c],    // окисленные и смешанные руды
  [-58, 0xa49b8f],    // вмещающие породы
  [-92, 0x8e9297],    // сульфидные руды (серые)
  [-150, 0x80858b],
];
export function strataColor(y, out) {
  out = out || new THREE.Color();
  let i = 0;
  while (i < STRATA.length - 1 && y < STRATA[i + 1][0]) i++;
  return out.setHex(STRATA[i][1]);
}
const hash = (a, b) => { const s = Math.sin(a * 127.1 + b * 311.7) * 43758.5453; return s - Math.floor(s); };

export function buildPit(ctx) {
  const { scene, AKT, layout } = ctx;
  const N = PIT.levels, D = PIT.depth, W = PIT.rampW;
  const group = new THREE.Group(); group.name = 'pit';
  scene.add(group);
  const mat = ctx.materials.bakedDouble;
  const c = new THREE.Color(), road = new THREE.Color(0xa69680), roadSide = new THREE.Color(0x8c7f6d);

  /* ---------------------------------------------------- terrain (polar grid) */
  const A = 144;
  const rings = [{ s: 1, y: 0, k: 'crest' }];
  for (let L = 1; L <= N; L++) {
    const y = levelY(L), t = toeS(L);
    rings.push({ s: t, y, k: 'toe' }, { s: t - PIT.berm / 3, y, k: 'berm' }, { s: t - 2 * PIT.berm / 3, y, k: 'berm' }, { s: crestS(L), y, k: 'crest' });
  }
  rings.push({ s: FLOOR_S * 0.62, y: levelY(N), k: 'floor' }, { s: FLOOR_S * 0.28, y: levelY(N), k: 'floor' }, { s: 0, y: levelY(N), k: 'floor' });
  const rampY = (th, s, R) => {
    const rn = rampNear(th, s);
    if (!rn) return null;
    const half = (W / 2 + 4) / R;
    return Math.abs(s - rn.s) < half ? -D * rn.t - 0.6 : null;
  };
  /* высота земли в карьере с выемкой съезда: для машин на дорогах и людей */
  const heightAt = (x, z) => {
    const dx = x - PIT.cx, dz = z - PIT.cz, th = Math.atan2(dz, dx), R = pitR(th), s = Math.hypot(dx, dz) / R;
    if (s >= 1.06) return dumpH(x, z);
    const h = stepH(s), r = rampY(th, s, R);
    return r == null ? h : Math.min(h, r);
  };
  {
    const pos = [], col = [], idx = [];
    for (let r = 0; r < rings.length; r++) {
      const ring = rings[r];
      for (let a = 0; a <= A; a++) {
        const th = 2 * Math.PI * (a % A) / A, R = pitR(th);
        let y = ring.y;
        const ry = rampY(th, ring.s, R);
        if (ry != null) y = Math.min(y, ry);
        pos.push(PIT.cx + ring.s * R * Math.cos(th), y, PIT.cz + ring.s * R * Math.sin(th));
        strataColor(y, c);
        const k = ring.k === 'crest' ? 1.1 : ring.k === 'toe' ? 0.84 : ring.k === 'floor' ? 0.9 : 1.0;
        const n = 0.93 + 0.12 * hash(a % A, r);
        if (ry != null && ry <= ring.y + 0.01) c.lerp(road, 0.6);
        col.push(c.r * k * n, c.g * k * n, c.b * k * n);
      }
    }
    const row = A + 1;
    for (let r = 0; r < rings.length - 1; r++) for (let a = 0; a < A; a++) {
      const p0 = r * row + a, p1 = p0 + 1, p3 = p0 + row, p2 = p3 + 1;
      idx.push(p0, p2, p1, p0, p3, p2);
    }
    const g = ctx.keep(new THREE.BufferGeometry());
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    g.setIndex(idx);
    const m = new THREE.Mesh(ctx.bake(g, { flip: 'up' }), mat); m.name = 'pit-terrain';
    group.add(m);
    ctx.onClick('pit', m, { halo: false });
  }

  /* -------------------------------------------- spiral ramp: road + skirts */
  /* лента дороги: pts [{x, y, z, nx, nz}] — ось и нормаль в плане; борта вниз на sideDrop.
     Материал двусторонний с плоским затенением, поэтому порядок обхода не важен. */
  const ribbon = (pts, width, sideDrop, top, side) => {
    const pos = [], col = [];
    const quad = (a, b, d, e, cc) => { for (const p of [a, b, d, a, d, e]) { pos.push(p[0], p[1], p[2]); col.push(cc.r, cc.g, cc.b); } };
    const hw = width / 2;
    for (let i = 1; i < pts.length; i++) {
      const p = pts[i - 1], q = pts[i];
      const pL = [p.x - p.nx * hw, p.y, p.z - p.nz * hw], pR = [p.x + p.nx * hw, p.y, p.z + p.nz * hw];
      const qL = [q.x - q.nx * hw, q.y, q.z - q.nz * hw], qR = [q.x + q.nx * hw, q.y, q.z + q.nz * hw];
      quad(pL, qL, qR, pR, top);
      quad(pL, [pL[0], p.y - sideDrop, pL[2]], [qL[0], q.y - sideDrop, qL[2]], qL, side);
      quad(pR, qR, [qR[0], q.y - sideDrop, qR[2]], [pR[0], p.y - sideDrop, pR[2]], side);
    }
    const g = ctx.keep(new THREE.BufferGeometry());
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    g.computeVertexNormals();
    return g;
  };
  const spiralPts = [];
  {
    const T = 240;
    for (let i = 0; i <= T; i++) {
      const r = rampAt(i / T);
      spiralPts.push({ x: r.x, y: r.y + 0.5, z: r.z, nx: Math.cos(r.th), nz: Math.sin(r.th) });
    }
    const m = new THREE.Mesh(ctx.bake(ribbon(spiralPts, W, 16, road, roadSide), { flip: 'up' }), ctx.materials.bakedDouble); m.name = 'pit-ramp';
    group.add(m);
    ctx.onClick('pit', m, { halo: false });
  }

  /* ------------------------------------------------------- waste dump */
  {
    const tiers = [1, 0.9, 0.82, 0.72, 0.6, 0.5, 0.3, 0];
    const AA = 72, pos = [], col = [], idx = [];
    const waste = new THREE.Color(0xbcab90);
    for (let r = 0; r < tiers.length; r++) for (let a = 0; a <= AA; a++) {
      const th = 2 * Math.PI * (a % AA) / AA, e = tiers[r];
      const x = DUMP.x + DUMP.rx * e * Math.cos(th), z = DUMP.z + DUMP.rz * e * Math.sin(th);
      const y = e >= 1 ? 0 : dumpH(DUMP.x + DUMP.rx * Math.min(0.999, e) * Math.cos(th), DUMP.z + DUMP.rz * Math.min(0.999, e) * Math.sin(th));
      pos.push(x, y, z);
      const k = [0.86, 1.08, 0.88, 1.08, 0.88, 1.1, 1.04, 1.0][r] * (0.94 + 0.1 * hash(a % AA, r + 40));
      col.push(waste.r * k, waste.g * k, waste.b * k);
    }
    const row = AA + 1;
    for (let r = 0; r < tiers.length - 1; r++) for (let a = 0; a < AA; a++) {
      const p0 = r * row + a, p1 = p0 + 1, p3 = p0 + row, p2 = p3 + 1;
      idx.push(p0, p2, p1, p0, p3, p2);
    }
    const g = ctx.keep(new THREE.BufferGeometry());
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    g.setIndex(idx);
    const m = new THREE.Mesh(ctx.bake(g, { flip: 'up' }), mat); m.name = 'waste-dump';
    group.add(m);
    ctx.onClick('road-dump', m, { halo: false });
  }

  /* ------------------------------------------------- surface haul roads */
  const E = rampAt(0);
  const ROADS = {
    'ramp-1': [[E.x, E.z], [-166, -122], [-140, -146], [-112, -150]],
    'ramp-2': [[E.x, E.z], [-160, -124], [-128, -126], [-112, -98], [-110, -20], [-112, 50], [-112, 95]],
    'road-dump': [[E.x, E.z], [-188, -140], [-205, -215], [-232, -290], [-265, -345], [-300, -386], [-326, -400]],
    garage: [[E.x, E.z], [-166, -122], [-130, -190], [-92, -268], [-60, -318], [-40, -330]],
  };
  const curves = new Map();
  const roadMeshes = {};
  /* высота дороги на отвал: ровный подъём от подошвы до верха (по земле — 0) */
  const roadY = (x, z, prev) => {
    const e = Math.hypot((x - DUMP.x) / DUMP.rx, (z - DUMP.z) / DUMP.rz);
    return e < 1 ? Math.max(prev || 0, DUMP.h * Math.min(1, (1 - e) / 0.5)) : 0;
  };
  for (const [name, ctl] of Object.entries(ROADS)) {
    const cr = new THREE.CatmullRomCurve3(ctl.map(([x, z]) => new THREE.Vector3(x, 0, z)), false, 'centripetal', 0.5);
    const n = Math.max(8, Math.ceil(cr.getLength() / 6));
    const flat = cr.getSpacedPoints(n);
    const pts = [];
    let prev = 0;
    for (let i = 0; i < flat.length; i++) {
      const p = flat[i], a = flat[Math.max(0, i - 1)], b = flat[Math.min(flat.length - 1, i + 1)];
      const tx = b.x - a.x, tz = b.z - a.z, l = Math.hypot(tx, tz) || 1;
      const y = name === 'road-dump' ? roadY(p.x, p.z, prev) : 0;
      prev = y;
      pts.push({ x: p.x, y: y + 0.45, z: p.z, nx: -tz / l, nz: tx / l });
    }
    const rm = ctx.keep(new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }));   // свой: цвет ∝ состоянию дороги
    const m = new THREE.Mesh(ctx.bake(ribbon(pts, 14, name === 'road-dump' ? 46 : 3, road, roadSide), { flip: 'up' }), rm); m.name = 'road-' + name;
    group.add(m);
    roadMeshes[name] = { mesh: m, mat: rm, pts };
    if (AKT.things[name]) ctx.onClick(name, m, { halo: true });
    curves.set(name, new PolyCurve(pts.map(p => new THREE.Vector3(p.x, p.y + 0.3, p.z))));
  }
  const spiralUp = new PolyCurve(spiralPts.slice().reverse().map(p => new THREE.Vector3(p.x, p.y + 0.3, p.z)));
  curves.set('spiral', spiralUp);

  /* --------------------------------------------- face spurs, full hauls */
  /* подъезд к забою: кривая кэшируется по уступу и углу забоя (забой в Ditto может переехать) */
  const spurs = new Map();
  const spur = faceId => {
    const f = layout.face(faceId);
    if (!f) return null;
    const ck = `${faceId}|${f.level}:${f.angle.toFixed(3)}:${f.s.toFixed(3)}`;
    if (spurs.has(ck)) return spurs.get(ck);
    const r = spurBuild(f);
    if (spurs.size > 64) spurs.clear();
    spurs.set(ck, r);
    return r;
  };
  const spurBuild = f => {
    const L = f.level, thJ = rampAngle(L), d = angDiff(thJ, f.angle);
    const steps = Math.max(2, Math.ceil(Math.abs(d) / (3 * Math.PI / 180)));
    const pts = [];
    for (let i = 0; i <= steps; i++) {
      const th = f.angle + d * i / steps, R = pitR(th), s = f.s;
      pts.push(new THREE.Vector3(PIT.cx + s * R * Math.cos(th), f.y + 0.8, PIT.cz + s * R * Math.sin(th)));
    }
    const j = rampAt(L / N);
    pts.push(new THREE.Vector3(j.x, j.y + 0.8, j.z));
    return { curve: new PolyCurve(pts), level: L, key: `${L}:${f.angle.toFixed(3)}` };
  };
  const spiralFrom = L => {
    const T = Math.max(2, Math.ceil(80 * L / N)), pts = [];
    for (let i = 0; i <= T; i++) { const r = rampAt((L / N) * (1 - i / T)); pts.push(new THREE.Vector3(r.x, r.y + 0.8, r.z)); }
    return new PolyCurve(pts);
  };
  const hauls = new Map();
  function resolvePath(name) {
    if (curves.has(name)) return curves.get(name);
    if (/^face-/.test(name)) { const s = spur(name); return s ? s.curve : null; }
    const m = /^haul:([^:]+):(.+)$/.exec(name);
    if (m) {
      const roadC = curves.get(m[2]) || null;
      const s = spur(m[1]);
      if (!s) return roadC;
      const key = name + '|' + s.key;
      if (!hauls.has(key)) hauls.set(key, PolyCurve.concat(s.curve, spiralFrom(s.level), roadC));
      return hauls.get(key);
    }
    return null;
  }

  /* ------------------------------------------------------------ labels */
  ctx.label('pit', () => `Карьер · добыча ${AKT.fmt(AKT.num('pit', 'mining_tph'))} т/ч · глубина ${AKT.fmt(AKT.pass('pit', 'depth_m') || PIT.depthM)} м (факт)`, {
    at: new THREE.Vector3(PIT.cx - 40, 8, PIT.cz - PIT.rz - 18), prio: 4,
    title: () => `Карьер: ${AKT.stOf('pit')} · добыча ${AKT.fmt(AKT.num('pit', 'mining_tph'))} т/ч (Ditto) · глубина 230 м — факт, уступы и съезд — схема`,
  });
  ctx.label('dump', () => `Отвал вскрыши · ${AKT.fmt(AKT.num('fleet', 'waste_tph'))} т/ч`, {
    thing: 'road-dump', at: new THREE.Vector3(DUMP.x, DUMP.h + 10, DUMP.z), prio: 7,
    title: () => `Отвал вскрыши (схема): вскрыша ${AKT.fmt(AKT.num('fleet', 'waste_tph'))} т/ч — парк карьера в Ditto`,
  });
  /* дороги подписываются, только когда не открыты (ISA-101: норма не привлекает взгляд) */
  for (const name of Object.keys(roadMeshes)) if (AKT.things[name]) {
    const mid = roadMeshes[name].pts[Math.floor(roadMeshes[name].pts.length * 0.55)];
    ctx.label('road:' + name, () => { const s = AKT.st(name); return s && s !== 'OPEN' ? `${AKT.nameRu(name)}: ${AKT.stOf(name)}` : ''; },
      { thing: name, at: new THREE.Vector3(mid.x, mid.y + 6, mid.z), prio: 3 });
  }

  /* ------------------------------------------------------------ update */
  const RED = 0xe0574f, AMBER = 0xe0b04f;
  function update(state) {
    if (!state.fresh) return;
    for (const name of Object.keys(roadMeshes)) {
      const s = AKT.things[name] ? AKT.st(name) : 'OPEN';
      const col = !s || s === 'OPEN' ? 0xffffff : (AKT.stopped(s) || s === 'CLOSED' ? RED : AMBER);
      roadMeshes[name].mat.color.setHex(col);
    }
  }
  return { group, heightAt, resolvePath, curves, update, exit: new THREE.Vector3(E.x, 0.5, E.z) };
}
