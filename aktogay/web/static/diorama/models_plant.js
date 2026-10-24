/* «Диорама», разбор аппаратов фабрики: низкополигональные модели (код, без загруженных моделей, до ≈ 3,5 тыс. треугольников):
   шаровая мельница (разрез), ВВД (два валка), флотомашина, кассета гидроциклонов, сгуститель, фильтр-пресс, шламовый насос.
   Формат тот же, что в models.js: список групп {part, parts, flip, when, hl}. Строятся только при выборе аппарата (inspect.js)
   и освобождаются при закрытии. Одинаковые формы (цилиндры, бруски) делят одну геометрию, повторы — копии матрицы.
   Размеры — схема, не чертёж. Оси: x вдоль оси/вправо по виду, y вверх, z вправо. */
import * as THREE from '../vendor/three-0.160.0/three.module.min.js';
import { box, beam3 } from './mining_geo.js';

const DK = 0x2c2e31, DM = 0x44484e, STEEL = 0x9aa1a8, LIGHT = 0xc9ced3, OIL = 0x3f6fa8, BLUE = 0x2f6f9f, SHELL = 0x6f8aa3;
const DEG = Math.PI / 180;

/* цилиндр/конус: ось x, y или z, центр c, радиусы r и r2, длина len */
const cyl = (c, r, len, color, axis, seg, r2, extra) => {
  const e = extra || {};
  const g = new THREE.CylinderGeometry(r, r2 == null ? r : r2, len, seg || 10, 1, !!e.open, e.ts || 0, e.tl == null ? Math.PI * 2 : e.tl);
  if (axis === 'x') g.rotateZ(Math.PI / 2); else if (axis === 'z') g.rotateX(Math.PI / 2);
  return { geometry: g, color, position: c };
};
const G = (part, parts, o) => Object.assign({ part, parts, flip: [1, 1, 1], when: 'both' }, o || {});
const rnd = seed => () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };

/* ------------------------------------------------------------ шаровая мельница: разрез */
function ball(C) {
  const R = 11, Ln = 15, N = 24, tsC = 110 * DEG, tlC = 230 * DEG, g = [];
  const shell = cut => cyl([0, 0, 0], R, Ln, SHELL, 'x', N, R, { open: true, ts: cut ? tsC : 0, tl: cut ? tlC : Math.PI * 2 });
  const heads = [cyl([-Ln / 2 - 0.4, 0, 0], R, 0.8, 0x56697c, 'x', N), cyl([Ln / 2 + 0.4, 0, 0], R, 0.8, 0x56697c, 'x', N)];
  g.push(G('shell', [shell(false)].concat(heads), { when: 'whole', hl: 'liner' }));
  g.push(G('shell', [shell(true)].concat(heads), { when: 'cut' }));
  const liner = [cyl([0, 0, 0], R - 0.9, Ln, 0x8d949c, 'x', N, R - 0.9, { open: true, ts: tsC, tl: tlC })];
  for (let i = 0; i < 14; i++) {
    const th = tsC + (i + 0.5) * tlC / 14;
    liner.push({ geometry: new THREE.BoxGeometry(Ln - 1.4, 1.1, 0.8), color: LIGHT, position: [0, (R - 1.4) * Math.sin(th), (R - 1.4) * Math.cos(th)], rotation: [Math.PI / 2 - th, 0, 0] });
  }
  g.push(G('liner', liner, { when: 'cut' }));
  /* загрузка: сегмент пульпы с шарами */
  const sh = new THREE.Shape(), off = 22 * DEG, rc = R - 1.1, half = 60 * DEG;
  for (let i = 0; i <= 10; i++) { const a = -half + 2 * half * i / 10 + off; const px = rc * Math.sin(a), py = -rc * Math.cos(a); if (i === 0) sh.moveTo(px, py); else sh.lineTo(px, py); }
  sh.closePath();
  const bed = new THREE.ExtrudeGeometry(sh, { depth: Ln - 2, bevelEnabled: false }).rotateY(-Math.PI / 2).translate((Ln - 2) / 2, 0, 0);
  const ch = [{ geometry: bed, color: 0x59514a }], r = rnd(11), ball0 = new THREE.IcosahedronGeometry(0.8, 0);
  for (let i = 0; i < 18; i++) {
    const a = off + (r() - 0.5) * 1.4 * half, x = (r() - 0.5) * (Ln - 4);
    ch.push({ geometry: ball0, color: i % 4 ? 0x6b6f75 : 0x8a8f96, position: [x, -(rc - 0.7) * Math.cos(a) + 0.5, (rc - 0.7) * Math.sin(a)] });
  }
  g.push(G('charge', ch, { when: 'cut' }));
  /* кольцевой двигатель (ГМД) */
  const stator = cut => ({ geometry: new THREE.TorusGeometry(R + 1.8, 2.0, 6, 28, cut ? 230 * DEG : Math.PI * 2).rotateZ(cut ? 200 * DEG : 0).rotateY(Math.PI / 2), color: BLUE, position: [0, 0, 0] });
  const poles = cut => {
    const a = [], pole = new THREE.BoxGeometry(3, 0.9, 1.1);
    for (let i = 0; i < 18; i++) {
      const th = i * Math.PI * 2 / 18, deg = th / DEG;
      if (cut && (deg > 340 || deg < 110)) continue;
      a.push({ geometry: pole, color: 0xd8dde2, position: [0, (R + 0.5) * Math.sin(th), (R + 0.5) * Math.cos(th)], rotation: [Math.PI / 2 - th, 0, 0] });
    }
    return a;
  };
  g.push(G('motor', [stator(false)].concat(poles(false)), { when: 'whole' }));
  g.push(G('motor', [stator(true)].concat(poles(true)), { when: 'cut' }));
  /* цапфы и опоры */
  const tr = [];
  for (const s of [-1, 1]) {
    const x = s * (Ln / 2 + 2.6);
    tr.push(cyl([x, 0, 0], 3.0, 3.6, 0x56697c, 'x', 12), box(x - 2.4, x + 2.4, -R - 2.2, -3.0, -3.4, 3.4, C.concrete), box(x - 3.0, x + 3.0, -R - 2.8, -R - 2.2, -4.2, 4.2, DM));
  }
  tr.push(beam3([-Ln / 2 - 6, 3, 0], [-Ln / 2 - 10, 9, 0], 3.2, C.steelDark));
  g.push(G('trunnion', tr));
  return { size: 30, esize: 18, scale: 1.6, lift: 42, groups: g };
}

/* ------------------------------------------------------------ ВВД: два валка */
function hpgr(C) {
  const Rr = 3.2, W = 4.4, gap = 0.25, xs = Rr + gap, g = [];
  const roll = s => [cyl([s * xs, 0, 0], Rr, W, 0xb8bec4, 'z', 20), cyl([s * xs, 0, 0], Rr + 0.08, 0.5, 0x6a7078, 'z', 20),
    cyl([s * xs, 0, 0], 0.9, W + 3.4, DM, 'z', 8)];
  g.push(G('roll1', roll(-1)), G('roll2', roll(1)));
  /* привод: у каждого валка двигатель и редуктор на противоположных торцах */
  const drives = [];
  for (const [s, z] of [[-1, 1], [1, -1]]) {
    drives.push(cyl([s * xs, 0, z * (W / 2 + 2.6)], 1.6, 1.6, 0x5a5f66, 'z', 10), box(s * xs - 1.5, s * xs + 1.5, -1.5, 1.5, z * (W / 2 + 3.4) - 0.8, z * (W / 2 + 3.4) + 0.8, 0x7d8a96),
      cyl([s * xs + s * 3.4, 0, z * (W / 2 + 5.8)], 1.4, 5.0, BLUE, 'z', 12), box(s * xs, s * xs + s * 3.4, -0.4, 0.4, z * (W / 2 + 4.6) - 0.5, z * (W / 2 + 4.6) + 0.5, DK));
  }
  g.push(G('drives', drives));
  /* гидравлика поджатия подвижного валка */
  const hyd = [];
  for (const z of [-1, 1]) hyd.push(cyl([xs + Rr + 1.4, 0, z * (W / 2 - 0.2)], 0.8, 3.0, OIL, 'x', 8), cyl([xs + Rr + 3.6, 0, z * (W / 2 - 0.2)], 0.35, 2.2, LIGHT, 'x', 6));
  hyd.push(cyl([xs + Rr + 3.2, 2.2, 0], 0.9, 2.0, 0xd8dde2, 'y', 8));
  g.push(G('press', hyd));
  /* бункер питания и металлодетектор */
  const hop = [{ geometry: new THREE.CylinderGeometry(4.6, 1.3, 7, 4, 1, true).rotateY(Math.PI / 4), color: C.concrete, position: [0, Rr + 4.2, 0], scale: [1.35, 1, 0.95] },
    box(-1.8, 1.8, Rr + 7.4, Rr + 8.2, -3.2, 3.2, STEEL)];
  g.push(G('hopper', hop));
  g.push(G('detector', [box(-2.8, 2.8, Rr + 11, Rr + 12.2, -0.9, 0.9, 0xf2b500), box(-3.2, -2.8, Rr + 8.4, Rr + 12.2, -0.6, 0.6, DM), box(2.8, 3.2, Rr + 8.4, Rr + 12.2, -0.6, 0.6, DM)]));
  g.push(G('frame', [box(-xs - Rr - 1.2, xs + Rr + 1.0, -Rr - 1.4, -Rr - 0.4, -W / 2 - 0.6, W / 2 + 0.6, C.steelDark),
    box(-xs - Rr - 1.2, -xs - Rr - 0.2, -Rr - 0.4, Rr + 1.2, -W / 2 - 0.6, -W / 2 + 0.2, DM), box(-xs - Rr - 1.2, -xs - Rr - 0.2, -Rr - 0.4, Rr + 1.2, W / 2 - 0.2, W / 2 + 0.6, DM),
    box(xs + Rr, xs + Rr + 1.0, -Rr - 0.4, Rr + 1.2, -W / 2 - 0.6, -W / 2 + 0.2, DM), box(xs + Rr, xs + Rr + 1.0, -Rr - 0.4, Rr + 1.2, W / 2 - 0.2, W / 2 + 0.6, DM),
    box(-xs - Rr - 1.2, xs + Rr + 1.0, Rr + 1.0, Rr + 1.6, -W / 2 - 0.6, W / 2 + 0.6, DM)]));
  return { size: 21, esize: 14, scale: 2.0, lift: 58, fit: 1.2, tilt: 0.75, groups: g };
}

/* ------------------------------------------------------------ флотомашина: разрез */
function flot(C) {
  const R = 6.5, H = 8, N = 20, ts = 100 * DEG, tl = 200 * DEG, g = [];
  const wall = cut => cyl([0, H / 2, 0], R, H, 0x6f8aa3, 'y', N, R, { open: true, ts: cut ? ts : 0, tl: cut ? tl : Math.PI * 2 });
  const floor = cyl([0, -0.2, 0], R, 0.4, 0x56697c, 'y', N);
  g.push(G('tank', [wall(false), floor], { when: 'whole' }));
  /* в разрезе: стенка без сектора, пульпа и слой пены на уровне */
  g.push(G('tank', [wall(true), floor, cyl([0, 2.8, 0], R - 0.2, 5.4, 0x4a5560, 'y', N, R - 0.2, { ts, tl: 2 * Math.PI - tl }),
    cyl([0, 6.1, 0], R - 0.2, 1.2, 0xd9c9a0, 'y', N, R - 0.2, { ts, tl: 2 * Math.PI - tl })], { when: 'cut' }));
  /* пенный жёлоб по периметру */
  g.push(G('launder', [cyl([0, H - 0.6, 0], R + 1.6, 1.4, 0x56697c, 'y', N, R + 1.6, { open: true }),
    { geometry: new THREE.RingGeometry(R, R + 1.6, N).rotateX(Math.PI / 2), color: 0x56697c, position: [0, H - 1.3, 0] },
    box(R + 1.4, R + 5, H - 2.0, H - 1.0, -1, 1, 0x56697c)]));
  /* ротор и статор */
  const rotor = [cyl([0, 4.4, 0], 0.35, 8.4, STEEL, 'y', 8), cyl([0, 1.5, 0], 1.7, 0.5, 0xb0b6bc, 'y', 12, 1.2)];
  const blade = new THREE.BoxGeometry(1.3, 1.0, 0.25);
  for (let i = 0; i < 6; i++) { const a = i * Math.PI / 3; rotor.push({ geometry: blade, color: 0xb0b6bc, position: [1.8 * Math.cos(a), 1.6, 1.8 * Math.sin(a)], rotation: [0, -a, 0] }); }
  g.push(G('rotor', rotor));
  const stator = [cyl([0, 1.3, 0], 2.8, 1.8, 0x44484e, 'y', 12, 2.8, { open: true })], vane = new THREE.BoxGeometry(0.2, 1.8, 0.9);
  for (let i = 0; i < 8; i++) { const a = i * Math.PI / 4; stator.push({ geometry: vane, color: 0x44484e, position: [3.0 * Math.cos(a), 1.3, 3.0 * Math.sin(a)], rotation: [0, -a, 0] }); }
  g.push(G('stator', stator));
  /* привод на мосту */
  g.push(G('drive', [box(-R - 0.5, R + 0.5, H + 0.2, H + 0.8, -0.8, 0.8, C.steelDark), box(-1.5, 1.5, H + 0.8, H + 3.0, -1.5, 1.5, BLUE), cyl([0, H + 3.6, 0], 0.9, 1.2, 0x5a5f66, 'y', 8)]));
  /* датчик уровня: штанга с поплавком над пеной */
  g.push(G('level', [cyl([3.4, H + 0.6, 0], 0.22, 3.6, LIGHT, 'y', 6), cyl([3.4, H - 1.6, 0], 0.7, 0.6, 0xf2b500, 'y', 8), box(2.9, 3.9, H + 2.2, H + 2.9, -0.5, 0.5, 0xf2b500)]));
  return { size: 17, esize: 10, scale: 2.5, lift: 30, groups: g };
}

/* ------------------------------------------------------------ кассета гидроциклонов */
function cyclones(C) {
  const g = [], n = 6, Rc = 4.6, cy = [], ap = [], ov = [], di = [];
  const body = new THREE.CylinderGeometry(1.5, 1.5, 2.4, 8), cone = new THREE.CylinderGeometry(1.5, 0.45, 5.2, 8), apex = new THREE.CylinderGeometry(0.5, 0.5, 0.8, 6),
    finder = new THREE.CylinderGeometry(0.7, 0.7, 1.4, 8), inlet = new THREE.BoxGeometry(1.8, 0.9, 0.9);
  for (let i = 0; i < n; i++) {
    const a = i * 2 * Math.PI / n, x = Rc * Math.cos(a), z = Rc * Math.sin(a);
    cy.push({ geometry: body, color: 0xd9a21b, position: [x, 7.4, z] }, { geometry: cone, color: 0xd9a21b, position: [x, 3.6, z] },
      { geometry: inlet, color: 0xb0b6bc, position: [x - 0.9 * Math.sin(a) - 0.6 * Math.cos(a), 7.9, z + 0.9 * Math.cos(a) - 0.6 * Math.sin(a)], rotation: [0, -a, 0] });
    ap.push({ geometry: apex, color: 0x6a7078, position: [x, 0.7, z] });
    ov.push({ geometry: finder, color: LIGHT, position: [x, 9.1, z] }, beam3([x, 9.9, z], [0, 9.9, 0], 0.7, LIGHT));
    di.push(beam3([x * 0.45, 7.9, z * 0.45], [x - 0.9 * Math.sin(a), 7.9, z + 0.9 * Math.cos(a)], 0.7, C.steelDark));
  }
  g.push(G('cyclones', cy));
  g.push(G('apex', ap.concat([box(-Rc - 2, Rc + 2, -0.9, 0.0, -Rc - 2, Rc + 2, C.steelDark)])));
  g.push(G('overflow', ov.concat([cyl([0, 10.6, 0], 1.0, 1.6, LIGHT, 'y', 8), cyl([4.6, 11.4, 0], 0.8, 9.2, LIGHT, 'x', 8)])));
  g.push(G('distributor', di.concat([cyl([0, 7.0, 0], 1.3, 2.6, 0x56697c, 'y', 10), cyl([0, 3.2, 0], 0.9, 6.0, 0x56697c, 'y', 8), cyl([0, 0.6, 0], 1.4, 0.5, STEEL, 'y', 10)])));
  g.push(G('frame', [box(-Rc - 2.4, -Rc - 1.8, 0, 9.8, -Rc - 2.4, -Rc - 1.8, DM), box(Rc + 1.8, Rc + 2.4, 0, 9.8, -Rc - 2.4, -Rc - 1.8, DM), box(-Rc - 2.4, -Rc - 1.8, 0, 9.8, Rc + 1.8, Rc + 2.4, DM), box(Rc + 1.8, Rc + 2.4, 0, 9.8, Rc + 1.8, Rc + 2.4, DM),
    box(-Rc - 2.4, Rc + 2.4, 5.2, 5.6, -Rc - 2.4, -Rc - 1.8, DM), box(-Rc - 2.4, Rc + 2.4, 5.2, 5.6, Rc + 1.8, Rc + 2.4, DM)]));
  return { size: 15, esize: 11, scale: 2.6, lift: 36, tilt: 0.6, groups: g };
}

/* ------------------------------------------------------------ сгуститель: разрез */
function thick(C) {
  const R = 14, H = 4.2, N = 24, ts = 110 * DEG, tl = 200 * DEG, g = [];
  const wall = cut => cyl([0, H / 2 + 1.6, 0], R, H, 0x8a929a, 'y', N, R, { open: true, ts: cut ? ts : 0, tl: cut ? tl : Math.PI * 2 });
  const cone = cut => cyl([0, 0.8, 0], 2, 1.6, 0x56697c, 'y', N, R, { open: true, ts: cut ? ts : 0, tl: cut ? tl : Math.PI * 2 });
  const rest = 2 * Math.PI - tl;
  g.push(G('tank', [wall(false), cone(false), cyl([0, H + 1.6, 0], R, 0.2, 0xbfc5cb, 'y', N)], { when: 'whole' }));
  g.push(G('tank', [wall(true), cone(true), cyl([0, H, 0], R - 0.2, 0.3, 0x6d8aa0, 'y', N, R - 0.2, { ts, tl: rest }),
    cyl([0, 2.2, 0], R - 0.6, 1.2, 0x5a4a3a, 'y', N, R - 0.6, { ts, tl: rest })], { when: 'cut' }));
  /* граблины: ступица, две фермы, лопасти под углом */
  const rk = [cyl([0, 3.4, 0], 0.5, 6.6, STEEL, 'y', 8), cyl([0, 1.3, 0], 1.2, 0.8, DM, 'y', 8)], blade = new THREE.BoxGeometry(1.8, 0.7, 0.2);
  for (const s of [-1, 1]) {
    rk.push(beam3([0, 1.6, 0], [s * (R - 1.2), 2.0, 0], 0.5, C.steelDark));
    for (let i = 1; i <= 5; i++) rk.push({ geometry: blade, color: LIGHT, position: [s * i * (R - 1.6) / 5.2, 1.5 + i * 0.07, 0.4], rotation: [0, 0.6 * s, 0.35] });
  }
  g.push(G('rake', rk));
  /* мост и привод с редуктором (там измеряется момент) */
  g.push(G('drive', [box(-R - 0.5, R + 0.5, H + 1.8, H + 2.4, -0.7, 0.7, C.steelDark), cyl([0, H + 3.4, 0], 1.7, 2.0, BLUE, 'y', 12), cyl([2.4, H + 3.0, 0], 0.9, 1.5, 0x5a5f66, 'y', 8), box(-2.0, 2.0, H + 2.4, H + 2.8, -1.4, 1.4, DM)]));
  g.push(G('feedwell', [cyl([0, H + 0.4, 0], 2.6, 3.0, 0x6a7078, 'y', 12, 2.6, { open: true }), beam3([-R - 3, H + 2.4, 0], [-1.8, H + 1.6, 0], 1.0, C.steelDark)]));
  g.push(G('launder', [cyl([0, H + 1.2, 0], R + 0.7, 0.8, 0x56697c, 'y', N, R + 0.7, { open: true }), { geometry: new THREE.RingGeometry(R - 0.2, R + 0.7, N).rotateX(Math.PI / 2), color: 0x56697c, position: [0, H + 0.8, 0] }]));
  return { size: 30, esize: 14, scale: 1.7, lift: 26, groups: g };
}

/* ------------------------------------------------------------ фильтр-пресс */
function filter(C) {
  const g = [], np = 14, step = 1.0, L = np * step, x0 = -L / 2, pw = 6, ph = 6;
  const plate = new THREE.BoxGeometry(0.55, ph, pw), cloth = new THREE.BoxGeometry(0.1, ph - 0.4, pw - 0.4), lug = new THREE.BoxGeometry(0.62, 0.5, 0.5), pl = [], cl = [];
  for (let i = 0; i < np; i++) {
    const x = x0 + (i + 0.5) * step;
    pl.push({ geometry: plate, color: 0xd8dde2, position: [x, ph / 2 + 2.4, 0] }, { geometry: lug, color: DM, position: [x, ph + 2.4, pw / 2 + 0.2] });
    cl.push({ geometry: cloth, color: 0xe9e2c8, position: [x + 0.31, ph / 2 + 2.4, 0] });
  }
  g.push(G('plates', pl));
  g.push(G('cloth', cl));
  const fr = [box(x0 - 2.6, x0 - 1.2, 2.0, ph + 3.2, -pw / 2 - 0.2, pw / 2 + 0.2, 0x4a6a8a), cyl([x0 - 1.9, ph + 3.2, 0], 0.7, 1.2, LIGHT, 'x', 8)];
  for (const s of [-1, 1]) fr.push(box(x0 - 2, -x0 + 2.2, ph + 1.8, ph + 2.4, s * (pw / 2 + 0.7), s * (pw / 2 + 1.2), C.steelDark), box(x0 - 2, x0 - 1.6, 0, 2.4, s * (pw / 2 + 0.2), s * (pw / 2 + 1.4), DM), box(-x0 + 1.6, -x0 + 2, 0, 2.4, s * (pw / 2 + 0.2), s * (pw / 2 + 1.4), DM));
  fr.push(box(x0 - 2.6, -x0 + 2.4, 1.6, 2.0, -pw / 2 - 1.4, pw / 2 + 1.4, DM));
  g.push(G('frame', fr));
  /* гидравлика: подвижная плита, цилиндр, шток, маслостанция */
  g.push(G('ram', [box(-x0 + 0.2, -x0 + 0.8, 2.0, ph + 3.0, -pw / 2 - 0.2, pw / 2 + 0.2, 0x4a6a8a), cyl([-x0 + 2.8, ph / 2 + 2.4, 0], 1.2, 3.6, OIL, 'x', 12), cyl([-x0 + 1.4, ph / 2 + 2.4, 0], 0.5, 1.4, LIGHT, 'x', 8),
    box(-x0 + 3.2, -x0 + 6.4, 1.6, 4.6, pw / 2 + 2, pw / 2 + 5, OIL), beam3([-x0 + 4.8, 3.2, pw / 2 + 2], [-x0 + 3.2, ph / 2 + 2.2, 0.8], 0.4, DK)]));
  return { size: 22, esize: 12, scale: 2.0, lift: 34, fit: 1.05, tilt: 0.6, groups: g };
}

/* ------------------------------------------------------------ шламовый насос */
function pump(C) {
  const g = [];
  /* корпус-улитка (ось по x), всасывание спереди, напор вверх */
  g.push(G('casing', [cyl([0, 4, 0], 3.4, 2.8, 0x56697c, 'x', 16, 3.4, { open: true }), cyl([-1.5, 4, 0], 3.4, 0.4, 0x56697c, 'x', 16), cyl([-2.6, 4, 0], 1.6, 2.0, 0x6a7078, 'x', 10), cyl([-3.9, 4, 0], 2.0, 0.5, STEEL, 'x', 10),
    cyl([0.6, 7.6, 1.7], 1.2, 3.4, 0x6a7078, 'y', 10), cyl([0.6, 9.5, 1.7], 1.9, 0.5, STEEL, 'y', 10)]));
  const imp = [cyl([0.4, 4, 0], 2.6, 0.3, 0xb0b6bc, 'x', 14), cyl([-0.9, 4, 0], 1.6, 0.3, 0xb0b6bc, 'x', 14, 1.6, { open: true }), cyl([0.9, 4, 0], 0.8, 1.0, 0x8d949c, 'x', 8)], vane = new THREE.BoxGeometry(1.4, 0.25, 1.6);
  for (let i = 0; i < 5; i++) { const a = i * 2 * Math.PI / 5; imp.push({ geometry: vane, color: 0xd8dde2, position: [-0.2, 4 + 1.5 * Math.sin(a), 1.5 * Math.cos(a)], rotation: [a, 0, 0] }); }
  g.push(G('impeller', imp));
  g.push(G('gland', [cyl([2.4, 4, 0], 1.3, 1.2, 0xd9a21b, 'x', 12), cyl([3.2, 4, 0], 1.6, 0.4, STEEL, 'x', 12)]));
  g.push(G('bearings', [cyl([5.0, 4, 0], 1.5, 3.2, DM, 'x', 12), cyl([4.0, 4, 0], 0.5, 8, STEEL, 'x', 8), cyl([6.9, 4, 0], 0.55, 1.2, STEEL, 'x', 8), box(4.2, 5.8, 1.4, 2.6, -1.0, 1.0, DK)]));
  g.push(G('base', [box(-2, 17, 0, 1.2, -3.2, 3.2, C.steelDark), cyl([12, 4, 0], 2.4, 7, BLUE, 'x', 14), cyl([8.4, 4, 0], 1.4, 1.0, STEEL, 'x', 10), box(10, 14, 1.2, 1.8, -2.0, 2.0, DM), box(1.5, 3.5, 1.2, 2.4, -2.2, 2.2, DM), box(3.8, 6.4, 1.2, 2.0, -2.2, 2.2, DM)]));
  return { size: 17, esize: 9, scale: 2.5, lift: 24, tilt: 0.6, groups: g };
}

export const PLANT_BUILDERS = { ball, hpgr, flot, cyclones, thick, filter, pump };
