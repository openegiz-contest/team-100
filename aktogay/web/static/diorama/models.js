/* «Диорама», разбор машин: подробные низкополигональные модели пяти объектов (код, без загруженных моделей).
   Строятся один раз при первом выборе вида и показываются только у выбранной машины (в обычном виде сцену не утяжеляют).
   Самосвал CAT 793 (6 колёс), экскаватор Hitachi прямая лопата, мельница SAG с кольцевым двигателем, конусная дробилка ЦПД,
   секция ленточного конвейера. Каждая модель — список групп: часть из parts.js, детали для ctx.merge, зеркало (flip) для
   парных деталей, когда показывать (whole — собрано, cut — разрез, both). Размеры — схема. Оси: x вперёд/вдоль оси, y вверх, z вправо. */
import * as THREE from '../vendor/three-0.160.0/three.module.min.js';
import { box, beam, beam3, truckBody, truckBed, excLower, excUpper, excArm } from './mining_geo.js';
import { PLANT_BUILDERS } from './models_plant.js';

const DK = 0x2c2e31, DM = 0x44484e, STEEL = 0x9aa1a8, LIGHT = 0xc9ced3, OIL = 0x3f6fa8;
const V3 = (a) => new THREE.Vector3(a[0], a[1], a[2]);
const DEG = Math.PI / 180;

/* цилиндр с осью по x, y или z: центр (x, y, z), радиус r (r2 — второй торец), длина len */
const cyl = (c, r, len, color, axis, seg, r2, extra) => {
  const e = extra || {};
  const g = new THREE.CylinderGeometry(r, r2 == null ? r : r2, len, seg || 10, 1, !!e.open, e.ts || 0, e.tl == null ? Math.PI * 2 : e.tl);
  if (axis === 'x') g.rotateZ(Math.PI / 2); else if (axis === 'z') g.rotateX(Math.PI / 2);
  return { geometry: g, color, position: c };
};
const own = p => {
  if (p.matrix) return p.matrix.clone();
  const s = p.scale == null ? [1, 1, 1] : (typeof p.scale === 'number' ? [p.scale, p.scale, p.scale] : p.scale);
  const r = p.rotation || [0, 0, 0];
  return new THREE.Matrix4().compose(V3(p.position || [0, 0, 0]), new THREE.Quaternion().setFromEuler(new THREE.Euler(r[0], r[1], r[2])), V3(s));
};
/* сдвиг и поворот вокруг z для набора деталей */
export const xf = (parts, pos, rotZ) => {
  const g = new THREE.Matrix4().compose(V3(pos), new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), rotZ || 0), new THREE.Vector3(1, 1, 1));
  return parts.map(p => ({ geometry: p.geometry, color: p.color, matrix: g.clone().multiply(own(p)) }));
};
const G = (part, parts, o) => Object.assign({ part, parts, flip: [1, 1, 1], when: 'both' }, o || {});

/* ------------------------------------------------------------ самосвал */
function truck(C) {
  const T = truckBody(C), B = truckBed(C);
  const pick = (a, ix) => ix.map(i => a[i]);
  const g = [];
  g.push(G('chassis', pick(T, [0, 1, 3, 4, 5, 6, 10, 11, 12]).concat([box(-5.4, 4.8, 1.0, 1.5, -0.5, 0.5, DM)])));
  const eng = pick(T, [2, 9]).concat([box(3.9, 5.5, 2.4, 3.3, -1.1, 1.1, 0x5a5f66), box(5.6, 6.0, 1.5, 4.2, -1.4, 1.4, LIGHT)]);
  for (let i = 0; i < 4; i++) eng.push(cyl([4.1 + i * 0.5, 3.8, 0], 0.22, 1.0, DK, 'y', 6));
  g.push(G('engine', eng));
  g.push(G('trans', [box(0.9, 3.5, 1.7, 2.9, -0.8, 0.8, 0x6a7078), cyl([3.7, 2.3, 0], 0.9, 0.7, 0x8a9096, 'x', 10), beam3([0.9, 2.3, 0], [-3.0, 2.3, 0], 0.5, DK)]));
  g.push(G('cab', pick(T, [7, 8]).concat([box(3.0, 3.35, 4.75, 5.6, -3.0, -1.4, DM)])));
  const side = (fl) => {
    const w = [], br = [];
    for (const [x, z, wd] of [[3.4, 3.0, 1.15], [-2.9, 2.0, 1.1], [-2.9, 3.3, 1.1]]) {
      w.push(cyl([x, 1.75, z], 1.75, wd, 0x222326, 'z', 10), cyl([x, 1.75, z + (z > 0 ? 0.05 : 0)], 0.8, wd + 0.15, STEEL, 'z', 8));
      br.push(cyl([x, 1.75, z - wd / 2 - 0.2], 1.15, 0.3, 0xb0b4b8, 'z', 10));
    }
    return [w, br];
  };
  const [wr, br] = side();
  g.push(G('wheels', wr), G('wheels', wr.map(p => Object.assign({}, p, { position: [p.position[0], p.position[1], -p.position[2]] })), { flip: [1, 1, -1] }));
  g.push(G('brakes', br), G('brakes', br.map(p => Object.assign({}, p, { position: [p.position[0], p.position[1], -p.position[2]] })), { flip: [1, 1, -1] }));
  g.push(G('body', B));
  return { size: 12.6, esize: 12.6, scale: 2.7, lift: 34, groups: g };
}

/* ------------------------------------------------------------ экскаватор */
function excavator(C) {
  const L = excLower(C, 'shovel'), U = excUpper(C, 'shovel'), A = excArm(C, 'shovel');
  const ring = 3.0, up = (parts) => xf(parts, [0, ring, 0], 0);
  const g = [];
  const sp = [cyl([-4.6, 1.2, 3.0], 1.2, 0.9, DM, 'z', 8), cyl([4.6, 1.2, 3.0], 1.2, 0.9, DM, 'z', 8), cyl([-4.6, 1.2, -3.0], 1.2, 0.9, DM, 'z', 8), cyl([4.6, 1.2, -3.0], 1.2, 0.9, DM, 'z', 8)];
  g.push(G('tracks', L.slice(0, 5).concat(sp)));
  g.push(G('swing', [L[5], { geometry: new THREE.TorusGeometry(2.4, 0.25, 6, 18).rotateX(Math.PI / 2), color: STEEL, position: [0, ring + 0.25, 0] }, cyl([1.4, ring + 1.0, 0], 0.9, 1.6, 0x6a7078, 'y', 8)]));
  const pumps = [box(-3.2, -0.8, ring + 0.2, ring + 0.6, -2.4, 2.4, DM)];
  for (const z of [-1.5, 0, 1.5]) pumps.push(cyl([-2.0, ring + 1.5, z], 0.75, 2.4, OIL, 'x', 8), cyl([-0.7, ring + 1.5, z], 0.95, 0.5, LIGHT, 'x', 8));
  g.push(G('pumps', pumps));
  const cyls = up([U[9], U[10]]).concat(xf([beam(0, 0, 4.2, -1.0, 0.55, -1.2, -0.7, STEEL), beam(0, 0, 4.2, -1.0, 0.55, 0.7, 1.2, STEEL)], [7.2, 4.4 + ring, 0], 0));
  g.push(G('cylinders', cyls));
  g.push(G('engine', [box(-4.4, -1.4, ring + 0.4, ring + 3.0, -2.6, 0.6, 0x5a5f66), box(-3.8, -2.6, ring + 3.0, ring + 4.2, 1.2, 2.2, DM), U[3] && up([U[3]])[0]].filter(Boolean)));
  g.push(G('cab', up([U[0], U[1], U[2], U[4], U[5], U[6], U[7]])));
  const armT = xf(A, [7.5, 7.0 + ring, 0], 0.4);
  g.push(G('boom', up([U[8]]).concat(armT.slice(0, 1))));
  g.push(G('bucket', armT.slice(1)));
  return { size: 20, esize: 9, scale: 2.3, lift: 40, groups: g };
}

/* ------------------------------------------------------------ мельница SAG */
function sag(C) {
  const R = 14, Ln = 18, tsC = 110 * DEG, tlC = 230 * DEG, N = 28;
  const shell = (cut) => cyl([0, 0, 0], R, Ln, 0x6f8aa3, 'x', N, R, { open: true, ts: cut ? tsC : 0, tl: cut ? tlC : Math.PI * 2 });
  const g = [];
  const heads = [cyl([-Ln / 2 - 0.4, 0, 0], R, 0.8, 0x56697c, 'x', N), cyl([Ln / 2 + 0.4, 0, 0], R, 0.8, 0x56697c, 'x', N)];
  g.push(G('shell', [shell(false)].concat(heads), { when: 'whole', hl: 'liner' }));
  g.push(G('shell', [shell(true)].concat(heads), { when: 'cut' }));
  /* футеровка: внутренний барабан и подъёмные планки */
  const liner = [cyl([0, 0, 0], R - 1.0, Ln, 0x8d949c, 'x', N, R - 1.0, { open: true, ts: tsC, tl: tlC })];
  for (let i = 0; i < 20; i++) {
    const th = tsC + (i + 0.5) * tlC / 20;
    liner.push({ geometry: new THREE.BoxGeometry(Ln - 1.6, 1.4, 0.9), color: 0xc9ced3, position: [0, (R - 1.6) * Math.sin(th), (R - 1.6) * Math.cos(th)], rotation: [Math.PI / 2 - th, 0, 0] });
  }
  g.push(G('liner', liner, { when: 'cut' }));
  /* загрузка: сегмент по хорде, вытянутый вдоль оси, с кусками руды и шарами */
  const sh = new THREE.Shape();
  const off = 22 * DEG, rc = R - 1.3, half = 62 * DEG;
  for (let i = 0; i <= 12; i++) { const a = -half + 2 * half * i / 12 + off; const px = rc * Math.sin(a), py = -rc * Math.cos(a); if (i === 0) sh.moveTo(px, py); else sh.lineTo(px, py); }
  sh.closePath();
  const bed = new THREE.ExtrudeGeometry(sh, { depth: Ln - 2.4, bevelEnabled: false }).rotateY(-Math.PI / 2).translate((Ln - 2.4) / 2, 0, 0);
  const ch = [{ geometry: bed, color: C.ore }];
  let seed = 7; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  for (let i = 0; i < 16; i++) {
    const a = off + (rnd() - 0.5) * 1.9 * half * 0.8, x = (rnd() - 0.5) * (Ln - 5);
    ch.push({ geometry: new THREE.IcosahedronGeometry(0.55 + rnd() * 0.5, 0), color: i % 3 ? 0x6b6f75 : C.oreLight, position: [x, -(rc - 0.9) * Math.cos(a) + 0.8, (rc - 0.9) * Math.sin(a)] });
  }
  g.push(G('charge', ch, { when: 'cut' }));
  /* кольцевой двигатель (ГМД): статор и полюса ротора */
  const stator = (cut) => ({ geometry: new THREE.TorusGeometry(R + 2.0, 2.3, 8, 36, cut ? 230 * DEG : Math.PI * 2).rotateZ(cut ? 200 * DEG : 0).rotateY(Math.PI / 2), color: 0x2f6f9f, position: [0, 0, 0] });
  const poles = (cut) => {
    const a = [];
    for (let i = 0; i < 24; i++) {
      const th = i * Math.PI * 2 / 24, deg = th / DEG;
      if (cut && (deg > 340 || deg < 110)) continue;
      a.push({ geometry: new THREE.BoxGeometry(3.4, 1.0, 1.2), color: 0xd8dde2, position: [0, (R + 0.6) * Math.sin(th), (R + 0.6) * Math.cos(th)], rotation: [Math.PI / 2 - th, 0, 0] });
    }
    return a;
  };
  g.push(G('motor', [stator(false)].concat(poles(false)), { when: 'whole' }));
  g.push(G('motor', [stator(true)].concat(poles(true)), { when: 'cut' }));
  /* загрузочная течка и бутара */
  g.push(G('chute', [cyl([-Ln / 2 - 2.2, 0, 0], 4.2, 3.2, 0x56697c, 'x', 12), beam3([-Ln / 2 - 9, 11, 0], [-Ln / 2 - 2.2, 1.5, 0], 3.4, C.steelDark), box(-Ln / 2 - 12, -Ln / 2 - 7, 10, 12.5, -3.4, 3.4, C.steelLight)]));
  const tr = [cyl([Ln / 2 + 2.2, 0, 0], 4.2, 3.2, 0x56697c, 'x', 12), cyl([Ln / 2 + 8.5, -0.5, 0], 6.2, 9.0, 0x7d8a96, 'x', 14, 6.2, { open: true })];
  for (let i = 0; i < 4; i++) tr.push(cyl([Ln / 2 + 4.6 + i * 2.6, -0.5, 0], 6.45, 0.4, C.steelDark, 'x', 14));
  tr.push(box(Ln / 2 + 4.5, Ln / 2 + 13, -9.5, -6.5, -4.5, 4.5, C.steelDark));
  g.push(G('trommel', tr));
  return { size: 36, esize: 20, scale: 1.45, lift: 44, groups: g };
}

/* ------------------------------------------------------------ дробилка ЦПД */
function crusher(C) {
  const ts = 100 * DEG, tl = 200 * DEG, g = [];
  const shell = (cut) => cyl([0, 7, 0], 8.2, 10, 0x6f8aa3, 'y', 20, 8.2, { open: true, ts: cut ? ts : 0, tl: cut ? tl : Math.PI * 2 });
  const base = [box(-10, 10, 0, 2, -10, 10, C.concrete)];
  g.push(G('frame', [shell(false)].concat(base), { when: 'whole', hl: 'mantle' }));
  g.push(G('frame', [shell(true)].concat(base), { when: 'cut' }));
  g.push(G('concave', [cyl([0, 8.2, 0], 7.4, 8.4, 0x8a929a, 'y', 20, 4.4, { open: true, ts, tl })], { when: 'cut' }));
  g.push(G('mantle', [cyl([0, 8.6, 0], 2.6, 10.5, 0xb0b6bc, 'y', 14, 4.6)], { when: 'cut' }));
  g.push(G('shaft', [cyl([0, 8, 0], 0.7, 19, DK, 'y', 8), cyl([0, 3.4, 0], 2.0, 3.0, DM, 'y', 10)], { when: 'cut' }));
  g.push(G('lube', [box(10.5, 14.5, 0, 3.2, -2.2, 2.2, OIL), beam3([10.5, 1.6, 0], [2.2, 3.0, 0], 0.7, STEEL), cyl([12.5, 3.6, 0], 0.7, 0.8, LIGHT, 'y', 8)]));
  const hop = [cyl([0, 15.8, 0], 10, 5.4, C.concrete, 'y', 16, 8.2, { open: true }),
    { geometry: new THREE.BoxGeometry(17.6, 1.0, 1.2), color: DK, position: [0, 13.4, 0] },
    { geometry: new THREE.BoxGeometry(1.2, 1.0, 17.6), color: DK, position: [0, 13.4, 0] }];
  g.push(G('hopper', hop));
  return { size: 26, esize: 20, scale: 1.7, lift: 40, groups: g };
}

/* ------------------------------------------------------------ конвейер */
function conveyor(C) {
  const Ln = 36, h = Ln / 2, g = [];
  const fr = [box(-h, h, 2.7, 3.1, -2.7, -2.2, C.steel), box(-h, h, 2.7, 3.1, 2.2, 2.7, C.steel)];
  for (let x = -h + 3; x <= h - 3; x += 9) fr.push(box(x - 0.3, x + 0.3, 0, 2.7, -2.6, -2.2, C.steelDark), box(x - 0.3, x + 0.3, 0, 2.7, 2.2, 2.6, C.steelDark), box(x - 0.3, x + 0.3, 1.0, 1.3, -2.6, 2.6, C.steelDark));
  fr.push(cyl([-h, 3.2, 0], 1.2, 4.2, STEEL, 'z', 10));
  g.push(G('frame', fr));
  const id = [];
  for (let x = -h + 2; x < h - 1; x += 3) {
    id.push(cyl([x, 3.45, 0], 0.32, 1.9, DM, 'z', 6));
    for (const s of [-1, 1]) id.push({ geometry: new THREE.CylinderGeometry(0.32, 0.32, 1.5, 6).rotateX(Math.PI / 2), color: DM, position: [x, 3.75, s * 1.55], rotation: [s * 0.4, 0, 0] });
  }
  for (let x = -h + 4; x < h - 1; x += 6) id.push(cyl([x, 1.5, 0], 0.3, 4.0, DM, 'z', 6));
  g.push(G('idlers', id));
  g.push(G('belt', [box(-h, h, 3.9, 4.05, -2.0, 2.0, C.belt), box(-h, h, 4.05, 4.5, -1.2, 1.2, C.ore), box(-h, h, 1.85, 2.0, -2.0, 2.0, C.belt)]));
  g.push(G('drive', [cyl([h, 3.2, 0], 1.5, 4.2, 0xb0b6bc, 'z', 12), box(h + 1.6, h + 4.8, 1.6, 3.6, -1.4, 1.4, 0x2f6f9f), box(h + 0.8, h + 1.7, 2.0, 3.4, -0.9, 0.9, 0x5a5f66), cyl([h + 0.5, 3.2, 2.4], 0.5, 1.0, DK, 'z', 6)]));
  return { size: 36, esize: 12, scale: 1.4, lift: 30, groups: g };
}

/* аппараты фабрики (models_plant.js): шаровая, ВВД, флотомашина, гидроциклоны, сгуститель, фильтр-пресс, шламовый насос */
export const BUILDERS = { truck, exc: excavator, sag, crusher, conveyor, ...PLANT_BUILDERS };
