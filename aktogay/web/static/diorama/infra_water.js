/* «Диорама», инфраструктура: хвостохранилище и вода.
   Хвостохранилище — чаша с дамбой. Факт (KAZ Minerals, управление
   хвостохранилищами, 07.2020, с. 2–3): наращивание вниз по течению (downstream),
   высота до 23 м, объём 65 → 243 млн м³, класс последствий «Low» (ANCOLD), с 2022 г.
   центральная сгущённая укладка (CTD). Формы чаши и места пьезометров не
   опубликованы — схема и допущения стенда. Пляж намыва хвостов и пруд
   осветлённой воды; уровень пруда — из water.pond_m3 в Ditto. Три пьезометра
   на низовом откосе: столбик давления kpa против уставки S0 sp_kpa, лампа и
   ореол при превышении. Водоводы по линиям схемы LINES: свежая вода (подача
   intake_m3h), оборотная вода от понтонной насосной на пруду (recycle_m3h),
   хвостопроводы от фабрики к дамбе; стрелки бегут со скоростью ∝ расходу.
   Утечка оборотной воды (leak_m3h > 0) — лужа и красное кольцо на водоводе
   (место на схеме условно). */

/* чаша: «стадион» — отрезок оси (cx ± L, cz) и радиус R0 до внутренней бровки гребня */
export const POND = { cx: 215, cz: 350, L: 205, R0: 95 };
/* профиль дамбы: [расстояние до оси, высота, цвет] — от подошвы низового откоса к внутреннему откосу */
const C = { toe: 0x9c9183, slope: 0xa79b8b, berm: 0xb9ae9b, crest: 0xc6bca9, face: 0x958b7e };
const DAM = [[124, 0.06, C.toe], [112, 5.2, C.slope], [112, 5.2, C.berm], [108, 5.2, C.berm], [108, 5.2, C.slope],
  [102, 10, C.slope], [102, 10, C.crest], [95, 10, C.crest], [95, 10, C.face], [90, 8.8, C.face]];
const BEACH = [90, 84, 76, 66, 54, 41, 28, 15, 0];
/* понижение пляжа, где стоит пруд (схема): ближе к низовой дамбе и правому краю */
const LOW = { x: 372, z: 370, ax: 300, az: 118 };
/* точки выпуска хвостов на гребне (концы хвостопроводов) */
const SPIGOT = [[300, 262], [380, 262]];
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const rhoOf = (x, z) => Math.hypot(Math.max(Math.abs(x - POND.cx) - POND.L, 0), z - POND.cz);
function beachY(x, z, rho) {
  const d = Math.min(1, Math.hypot((x - LOW.x) / LOW.ax, (z - LOW.z) / LOW.az));
  const b = 0.5 + 7.8 * Math.pow(d, 1.25);
  const t = clamp((rho - 68) / 22, 0, 1);
  return b + (8.8 - b) * t * t;
}
/* высота дамбы и пляжа в точке (null — вне хвостохранилища) */
export function pondY(x, z) {
  const r = rhoOf(x, z);
  if (r >= DAM[0][0]) return null;
  if (r < 90) return beachY(x, z, r);
  for (let i = 1; i < DAM.length; i++) {
    const [r0, y0] = DAM[i - 1], [r1, y1] = DAM[i];
    if (r >= r1 && r0 > r1) return y0 + (y1 - y0) * (r0 - r) / (r0 - r1);
  }
  return 8.8;
}
/* уровень зеркала пруда (схема): пусто → лужа в понижении, ≈ 2,2 млн м³ — почти до гребня */
const levelOf = m3 => 1.0 + 6.4 * clamp((m3 || 0) / 2.2e6, 0, 1);

/* обход «стадиона» одной и той же сеткой: [точка оси, нормаль] — для колец с общей топологией */
function loop(M, K) {
  const { cx, cz, L } = POND, out = [];
  for (let i = 0; i < M; i++) out.push([cx - L + 2 * L * i / M, cz, 0, -1]);
  for (let j = 0; j < K; j++) { const a = -Math.PI / 2 + Math.PI * j / K; out.push([cx + L, cz, Math.cos(a), Math.sin(a)]); }
  for (let i = 0; i < M; i++) out.push([cx + L - 2 * L * i / M, cz, 0, 1]);
  for (let j = 0; j < K; j++) { const a = Math.PI / 2 + Math.PI * j / K; out.push([cx - L, cz, Math.cos(a), Math.sin(a)]); }
  return out;
}

export function buildWater(ctx, kit, glow) {
  const { THREE, AKT, scene } = ctx;
  const group = new THREE.Group(); group.name = 'infra-water'; scene.add(group);
  const ground = (x, z) => { const p = pondY(x, z); const h = ctx.heightAt(x, z); return p == null ? h : Math.max(h, p); };
  const LP = loop(24, 16), N = LP.length;
  const col = new THREE.Color(), c2 = new THREE.Color();

  /* кольца сетки → геометрия с цветами вершин (индексы — четырёхугольники между соседними кольцами) */
  const rings = (list, yOf, colOf) => {
    const pos = [], cols = [], idx = [];
    list.forEach((rg, r) => {
      for (const [px, pz, nx, nz] of LP) {
        const x = px + nx * rg.rho, z = pz + nz * rg.rho, y = yOf(rg, x, z);
        pos.push(x, y, z);
        colOf(rg, x, z, y, col); cols.push(col.r, col.g, col.b);
      }
      if (r > 0) for (let i = 0; i < N; i++) {
        const a = (r - 1) * N + i, b = (r - 1) * N + (i + 1) % N, c = r * N + i, d = r * N + (i + 1) % N;
        idx.push(a, b, d, a, d, c);
      }
    });
    const g = ctx.keep(new THREE.BufferGeometry());
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(cols, 3));
    g.setIndex(idx);
    return g;
  };
  /* дамба: подсвечивается ядром при беде у воды (onClick с ореолом) */
  const damGeo = rings(DAM.map(([rho, y, c]) => ({ rho, y, c })), rg => rg.y, (rg, x, z, y, out) => {
    const n = 0.95 + 0.07 * Math.sin(x * 0.21 + z * 0.13);
    out.setHex(rg.c).multiplyScalar(n);
  });
  const dam = new THREE.Mesh(ctx.bake(damGeo, { flip: 'up' }), ctx.materials.bakedDouble); dam.name = 'tails-dam';
  group.add(dam);
  ctx.onClick('water', dam);
  /* пляж намыва: сухой светлый песок, ниже — влажный серый, у выпусков — свежая пульпа */
  const DRY = 0xe2d8c2, WET = 0xbab3a3, SLURRY = 0xa29b8f;
  const beachGeo = rings(BEACH.map(rho => ({ rho })), (rg, x, z) => beachY(x, z, rg.rho), (rg, x, z, y, out) => {
    out.setHex(WET).lerp(c2.setHex(DRY), clamp((y - 1.5) / 5.5, 0, 1));
    let s = 0;
    for (const [sx, sz] of SPIGOT) s = Math.max(s, Math.exp(-Math.hypot((x - sx) * 0.6, z - sz) / 26));
    out.lerp(c2.setHex(SLURRY), 0.75 * s);
    out.multiplyScalar(0.97 + 0.05 * Math.sin(x * 0.37 + z * 0.29));
  });
  const beach = new THREE.Mesh(ctx.bake(beachGeo, { flip: 'up' }), ctx.materials.bakedDouble); beach.name = 'tails-beach';
  group.add(beach);
  ctx.onClick('water', beach, { halo: false });

  /* зеркало пруда: одна плоскость на всю чашу, пляж выше уровня закрывает её сам */
  const wpos = [], wuv = [], widx = [];
  for (const [px, pz, nx, nz] of LP) { const x = px + nx * 92, z = pz + nz * 92; wpos.push(x, 0, z); wuv.push(x / 70, z / 70); }
  for (const [px, pz] of LP) { wpos.push(px, 0, pz); wuv.push(px / 70, pz / 70); }
  for (let i = 0; i < N; i++) { const a = i, b = (i + 1) % N, c = N + i, d = N + (i + 1) % N; widx.push(a, b, d, a, d, c); }
  const wg = ctx.keep(new THREE.BufferGeometry());
  wg.setAttribute('position', new THREE.Float32BufferAttribute(wpos, 3));
  wg.setAttribute('uv', new THREE.Float32BufferAttribute(wuv, 2));
  wg.setIndex(widx);
  const ripple = (() => {
    const cv = document.createElement('canvas'); cv.width = cv.height = 128;
    const x = cv.getContext('2d');
    x.fillStyle = '#e9eef0'; x.fillRect(0, 0, 128, 128);
    let s = 97;
    const rnd = () => { s = (s * 16807) % 2147483647; return s / 2147483647; };
    for (let i = 0; i < 70; i++) {
      x.strokeStyle = `rgba(255,255,255,${0.35 + 0.5 * rnd()})`; x.lineWidth = 1 + rnd() * 1.5;
      const y0 = rnd() * 128, x0 = rnd() * 128, l = 8 + rnd() * 22;
      x.beginPath(); x.moveTo(x0, y0); x.quadraticCurveTo(x0 + l / 2, y0 - 2, x0 + l, y0); x.stroke();
    }
    const t = ctx.keep(new THREE.CanvasTexture(cv));
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
    return t;
  })();
  const waterMat = ctx.keep(new THREE.MeshBasicMaterial({ color: ctx.litColor(0x7fb3c4), map: ripple, side: THREE.DoubleSide }));
  const water = new THREE.Mesh(wg, waterMat); water.name = 'tails-pond';
  water.position.y = levelOf(AKT.num('water', 'pond_m3') ?? 1.25e6);
  group.add(water);
  ctx.onClick('water', water, { halo: false });
  /* кольцо беды у воды — на зеркале пруда (понижение пляжа), не в середине чаши */
  glow.anchor('water', LOW.x - 20, 0, LOW.z - 2, 66);

  /* ------------------------------------------------ водоводы и хвостопроводы */
  const LIFT = 1.9, TRESTLE = 8.6, PR = 1.7;
  /* высота трубы: на опорах над землёй, в чаше — на эстакаде выше зеркала пруда */
  const pipeY = (x, z) => { const g = ground(x, z); return rhoOf(x, z) < 95 ? Math.max(g + LIFT, TRESTLE) : g + LIFT; };
  const PIPES = [
    { k: 'pipe-fresh', color: 0x6d9fc2, arrow: 0x1f78d1, ext: null },
    { k: 'pipe-recycle', color: 0x5f9aa0, arrow: 0x0f9aa3, ext: null },
    { k: 'pipe-tails-1', color: 0x8e877b, arrow: 0xb06a28, ext: [380, 266] },
    { k: 'pipe-tails-2', color: 0x8e877b, arrow: 0xb06a28, ext: [300, 266] },
  ];
  const pipeParts = kit.list(), curves = {};
  for (const P of PIPES) {
    const ln = ctx.LINES[P.k]; if (!ln) continue;
    const ctl = ln.slice(); if (P.ext) ctl.push(P.ext);
    const pts = [];
    for (let i = 0; i < ctl.length; i++) {
      const [x, z] = ctl[i];
      if (i > 0) {
        const [px, pz] = ctl[i - 1], n = Math.max(1, Math.ceil(Math.hypot(x - px, z - pz) / 6));
        for (let k = 1; k < n; k++) { const xx = px + (x - px) * k / n, zz = pz + (z - pz) * k / n; pts.push(new THREE.Vector3(xx, pipeY(xx, zz), zz)); }
      }
      pts.push(new THREE.Vector3(x, pipeY(x, z), z));
    }
    const cv = new ctx.PolyCurve(pts);
    curves[P.k] = cv;
    pipeParts.raw(new THREE.TubeGeometry(cv, Math.max(4, Math.ceil(cv.len / 6)), PR, 6, false), P.color);
    /* опоры: стойка и шпала каждые ≈ 16 у.е. */
    for (let d = 4; d < cv.len - 2; d += 16) {
      const p = cv.at(d), g = ground(p.x, p.z), h = p.y - PR - g;
      if (h > 0.3) pipeParts.box(p.x, g, p.z, 0.9, h, 0.9, 0x6b6f74);
      pipeParts.box(p.x, Math.max(g, p.y - PR - 0.8), p.z, 2.6, 0.7, 2.6, 0x7b7f84);
    }
  }
  /* выпуски хвостов на пляж: короткий патрубок вниз и веер пульпы уже окрашен в пляже */
  for (const [sx, sz] of SPIGOT) pipeParts.box(sx - 0.8, ground(sx, sz + 4), sz + 2, 1.6, pipeY(sx, sz) - ground(sx, sz + 4), 1.6, 0x8e877b);

  /* насосная свежей воды и резервуар (зона «Водовод»; схема) */
  const WX = 655, WZ = 284, wy = ctx.heightAt(WX, WZ);
  pipeParts.cyl(WX, wy, WZ, 15, 13, 0xe9ecee).cone(WX, wy + 13, WZ, 15.6, 3.2, 0xc9ced3)
    .box(WX + 14.6, wy, WZ - 2, 1.0, 13.5, 2.2, 0x8b939b)                       // лестница
    .box(WX - 15.4, wy + 2.2, WZ + 0.0, 1.4, 1.4, 6, 0x6d9fc2);
  const HX = 627, HZ = 307, hy = ctx.heightAt(HX, HZ);
  pipeParts.box(HX, hy, HZ, 22, 8.5, 12, 0xdfe3e6).box(HX, hy + 8.5, HZ, 23.4, 1.3, 13.4, 0x4f79a6)
    .box(HX - 4, hy, HZ + 6.05, 4, 5.4, 0.3, 0x56636f).box(HX + 6, hy + 4.4, HZ + 6.05, 7, 1.6, 0.3, 0x7fa6c2);
  /* понтон оборотной воды на пруду (стоит на зеркале, движется с уровнем) */
  const bargeL = kit.list();
  bargeL.box(0, -1.2, 0, 24, 2.8, 14, 0x7c8996).box(-2, 1.6, -1, 12, 6.2, 9, 0xe6e9ec).box(-2, 7.8, -1, 13, 1, 10, 0x4f79a6)
    .box(7.5, 1.6, 2.5, 3, 2.6, 3, 0x2f6fb2).box(7.5, 1.6, -3, 3, 2.6, 3, 0x2f6fb2).hcyl(-2, 3.8, 4.6, 1.0, 9, 0x5f9aa0)
    .box(0, 1.6, 6.6, 24, 1.1, 0.4, 0xd8342a);
  const barge = bargeL.mesh(); barge.name = 'recycle-barge';
  const BX = 400, BZ = 405;
  barge.position.set(BX, water.position.y, BZ);
  group.add(barge);
  ctx.onClick('water', barge, { halo: false });

  const pipes = pipeParts.mesh(); pipes.name = 'water-pipes';
  group.add(pipes);
  ctx.onClick('water', pipes, { halo: false });
  /* пятна-тени под резервуаром и насосной */
  for (const [x, z, w, d] of [[WX + 3, WZ + 3, 40, 40], [HX + 2, HZ + 2, 30, 20]]) {
    const b = ctx.blob(w, d, 0.22); b.position.set(x, ctx.heightAt(x, z) + 0.15, z); group.add(b);
  }

  /* ------------------------------------------------------------ пьезометры */
  const PIEZO = ['piezo-1', 'piezo-2', 'piezo-3'].filter(id => ctx.NODES[id]);
  const GH = 16;                              // высота шкалы (схема): верх шкалы = 1,3 × уставка
  const piezo = PIEZO.map(id => {
    const n = ctx.NODES[id], x = n.x, z = n.z, y = ground(x, z);
    const L = kit.list();
    L.box(x, y - 0.4, z, 4, 1.2, 4, 0xbdb8ae)                     // бетонная площадка
      .cyl(x - 1.3, y + 0.8, z, 0.85, 12, 0xb9c0c7)                // пьезометрическая труба
      .cyl(x - 1.3, y + 12.8, z, 1.3, 1.2, 0x5b636b)                // оголовок
      .box(x + 2.1, y + 0.8, z, 0.6, GH + 1.6, 0.6, 0x5b636b)       // стойка шкалы
      .box(x + 2.1, y + 1.6, z + 0.5, 2.8, GH, 0.5, 0xf4f4f1)       // шкала
      .box(x + 2.1, y + 1.6 + GH / 1.3 - 0.25, z + 0.85, 3.6, 0.5, 0.35, 0xd8342a);   // уставка S0
    const m = L.mesh(); m.name = id;
    group.add(m);
    ctx.onClick(id, m);
    return { id, x, y, z };
  });
  /* столбики давления (по экземпляру на пьезометр) и лампы */
  const fill = new THREE.InstancedMesh(ctx.keep(new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0)), ctx.keep(new THREE.MeshBasicMaterial({ color: 0xffffff })), Math.max(1, piezo.length));
  fill.name = 'piezo-fill'; fill.frustumCulled = false; group.add(fill);
  const LAMPS = [{ k: 'pump', x: HX + 9, z: HZ - 4, y: hy + 10.6 }, { k: 'barge', x: BX - 2, z: BZ - 1, dy: 9.6 }]
    .concat(piezo.map(p => ({ k: p.id, x: p.x - 1.3, z: p.z, y: p.y + 14.6 })));
  const lamps = new THREE.InstancedMesh(ctx.keep(new THREE.SphereGeometry(1.15, 10, 8)), ctx.keep(new THREE.MeshBasicMaterial({ color: 0xffffff })), LAMPS.length);
  lamps.name = 'water-lamps'; lamps.frustumCulled = false; group.add(lamps);
  /* лужа утечки на оборотном водоводе (место условно) */
  const leakAt = curves['pipe-recycle'] ? curves['pipe-recycle'].getPointAt(0.66) : null;
  const puddle = new THREE.Mesh(ctx.keep(new THREE.CircleGeometry(1, 28).rotateX(-Math.PI / 2)),
    ctx.keep(new THREE.MeshBasicMaterial({ color: ctx.litColor(0x6aa6c4), transparent: true, opacity: 0.88, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })));
  puddle.visible = false; puddle.renderOrder = 1;
  if (leakAt) { puddle.position.set(leakAt.x + 3, ground(leakAt.x, leakAt.z) + 0.25, leakAt.z + 2); group.add(puddle); }

  /* --------------------------------------------------------------- стрелки потока */
  const arrows = [];
  for (const P of PIPES) {
    const cv = curves[P.k]; if (!cv) continue;
    const n = Math.max(2, Math.round(cv.len / 34));
    for (let i = 0; i < n; i++) arrows.push({ k: P.k, cv, u0: i / n, color: P.arrow });
  }
  const arrowGeo = ctx.keep(new THREE.ConeGeometry(1.5, 4.6, 6).rotateZ(-Math.PI / 2));
  const arrowMesh = new THREE.InstancedMesh(arrowGeo, ctx.keep(new THREE.MeshBasicMaterial({ color: 0xffffff })), Math.max(1, arrows.length));
  arrowMesh.name = 'water-arrows'; arrowMesh.frustumCulled = false; group.add(arrowMesh);
  const flow = { 'pipe-fresh': 0, 'pipe-recycle': 0, 'pipe-tails-1': 0, 'pipe-tails-2': 0 };
  const phase = { 'pipe-fresh': 0, 'pipe-recycle': 0, 'pipe-tails-1': 0, 'pipe-tails-2': 0 };

  /* --------------------------------------------------------------- подписи */
  const NB = ' ';
  const v = (n, f, d) => { const x = AKT.num(n, f); return x == null ? '—' : `${AKT.fmt(x, d || 0)}${NB}${AKT.unitRu(AKT.unit(n, f)) || ''}`.trim(); };
  const has = n => !!AKT.things[n];
  ctx.label('infra:water', () => {
    if (!has('water')) return '';
    const st = AKT.st('water'), bad = st && st !== 'NORMAL';
    /* объём пруда — допущение стенда (регулятор держит его у середины полосы, поэтому число почти не меняется) */
    return `Хвостохранилище · пруд ${v('water', 'pond_m3')} (д)${bad ? ' · ' + AKT.stOf('water').toLowerCase() : ''}\nоборотная вода ${v('water', 'recycle_m3h')}`;
  }, {
    thing: 'water', prio: 2, at: new THREE.Vector3(250, 12, 330),
    title: () => `Хвосты и вода (Ditto): пруд ${v('water', 'pond_m3')}, оборотная вода ${v('water', 'recycle_m3h')}, с хвостами уходит ${v('water', 'tails_loss_m3h')}, испарение и фильтрация ${v('water', 'evap_m3h')}. Объём пруда и форма чаши — допущения стенда; уровень на макете — схема`,
  });
  ctx.label('infra:intake', () => {
    if (!has('water')) return '';
    const s = AKT.num('water', 'short_m3h');
    return `Свежая вода · ${v('water', 'intake_m3h')} из ${AKT.fmt(AKT.num('water', 'intake_cap_m3h'))}${NB}м³/ч${s > 0 ? ` · не хватает ${v('water', 'short_m3h')}` : ''}`;
  }, {
    thing: 'water', prio: 3, at: new THREE.Vector3(WX, wy + 17, WZ),
    title: () => `Подача свежей воды (Ditto): ${v('water', 'intake_m3h')}; предел подачи ${v('water', 'intake_cap_m3h')} — расчёт по ОВОС-2018, с. 145 (на две фабрики), для линии 1 — допущение. Внешний водовод ≈ 27 км от Жузагаша — по данным прессы (mining-technology.com, 2018), на макете не показан`,
  });
  ctx.label('infra:leak', () => {
    const l = has('water') ? AKT.num('water', 'leak_m3h') : null;
    return l > 0 ? `Утечка оборотной воды · ${v('water', 'leak_m3h')}\nместо на схеме условно` : '';
  }, { thing: 'water', prio: 1, at: leakAt ? new THREE.Vector3(leakAt.x, leakAt.y + 8, leakAt.z) : null });
  /* в норме подпись пьезометра уступает место (ISA-101); выше S0 или близко к ней — важна, как беда */
  const piezoLabel = (p, loud) => {
    const short = () => { const m = /П-?\d+/.exec(AKT.nameRu(p.id)); return m ? m[0] : AKT.shortName(p.id); };
    return ctx.label('infra:' + p.id, () => {
      if (!has(p.id)) return '';
      const k = AKT.num(p.id, 'kpa'), sp = AKT.num(p.id, 'sp_kpa');
      const over = k != null && sp != null && k >= sp;
      return `${short()} · ${v(p.id, 'kpa')}${over ? ' · выше S0' : ''}\nS0 ${v(p.id, 'sp_kpa')} ${AKT.ASSUME}`;
    }, {
      thing: p.id, prio: loud ? 1 : 6, kind: 'small', at: new THREE.Vector3(p.x + 2, p.y + GH + 3, p.z),
      title: () => `${AKT.nameRu(p.id)}: ${v(p.id, 'kpa')} при уставке безопасности S0 ${v(p.id, 'sp_kpa')} (Ditto). Число и места пьезометров не опубликованы, уставка — допущение стенда`,
    });
  };
  const piezoLabels = piezo.map(p => ({ id: p.id, p, h: piezoLabel(p, false), hidden: false, loud: false }));

  /* ---------------------------------------------------------------- update */
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(), pp = new THREE.Vector3(), tg = new THREE.Vector3();
  const X = new THREE.Vector3(1, 0, 0), cc = new THREE.Color();
  const GREY = 0x9aa1a8;
  let levelGoal = water.position.y, leak = 0, lampCol = {}, piezoState = [];
  const LAMP = { run: 0x3fd0ff, off: 0x7d858c, warn: 0xffb020, alarm: 0xff3a2a };
  function fresh(state) {
    if (has('water')) {
      levelGoal = levelOf(AKT.num('water', 'pond_m3'));
      flow['pipe-fresh'] = (AKT.num('water', 'intake_m3h') || 0) / 6000;
      flow['pipe-recycle'] = (AKT.num('water', 'recycle_m3h') || 0) / 20000;
      leak = AKT.num('water', 'leak_m3h') || 0;
      const short = (AKT.num('water', 'short_m3h') || 0) > 0;
      lampCol.pump = flow['pipe-fresh'] > 0 ? (short ? LAMP.warn : LAMP.run) : LAMP.off;
      lampCol.barge = flow['pipe-recycle'] > 0 ? (leak > 0 ? LAMP.warn : LAMP.run) : LAMP.off;
    }
    /* хвостопроводы: поток ∝ переработке линии (руда в питании мельницы), без подписи числа */
    for (const n of [1, 2]) {
      const t = AKT.num(`line-${n}`, 'tph') ?? AKT.num(`sag-${n}`, 'feed_tph');
      flow[`pipe-tails-${n}`] = (t || 0) / 4000;
    }
    piezoState = piezo.map(p => {
      const k = AKT.num(p.id, 'kpa'), sp = AKT.num(p.id, 'sp_kpa') || AKT.pass(p.id, 'sp_kpa') || null;
      const alarm = (AKT.num(p.id, 'alarm') || 0) > 0 || (k != null && sp != null && k >= sp) || AKT.stopped(AKT.st(p.id));
      const near = !alarm && k != null && sp != null && k >= 0.9 * sp;
      return { k, sp, alarm, near };
    });
    piezo.forEach((p, i) => {
      const s = piezoState[i];
      const f = s.k != null && s.sp ? clamp(s.k / (1.3 * s.sp), 0.02, 1) : 0.02;
      m4.compose(pp.set(p.x + 2.1, p.y + 1.6, p.z + 1.0), q.identity(), sc.set(1.3, GH * f, 0.5));
      fill.setMatrixAt(i, m4);
      fill.setColorAt(i, cc.setHex(s.alarm ? 0xe0342a : s.near ? 0xe8a000 : 0x2f86d6));
      lampCol[p.id] = s.alarm ? LAMP.alarm : s.near ? LAMP.warn : GREY;
    });
    fill.instanceMatrix.needsUpdate = true; if (fill.instanceColor) fill.instanceColor.needsUpdate = true;
    LAMPS.forEach((l, i) => lamps.setColorAt(i, cc.setHex(lampCol[l.k] || GREY)));
    if (lamps.instanceColor) lamps.instanceColor.needsUpdate = true;
    puddle.visible = leak > 0 && !!leakAt;
    if (puddle.visible) { const r = clamp(5 + Math.sqrt(leak) * 0.32, 6, 22); puddle.scale.set(r, 1, r * 0.8); }
  }
  /* подписи пьезометров: в норме — только вблизи (ISA-101), при превышении — всегда */
  function labelsFor(state) {
    piezoLabels.forEach((L, i) => {
      const s = piezoState[i] || {};
      const loud = !!(s.alarm || s.near);
      if (loud !== L.loud) { L.loud = loud; L.h = piezoLabel(L.p, loud); L.hidden = false; }
      const hide = !s.alarm && !s.near && state.camDist > 1500;
      if (hide !== L.hidden) { L.hidden = hide; L.h.hide(hide); }
    });
  }
  function frame(state, dt) {
    if (state.fresh) fresh(state);
    labelsFor(state);
    /* уровень пруда плавно к цели; понтон — на зеркале или на пляже, если пруд ушёл */
    water.position.y += (levelGoal - water.position.y) * Math.min(1, dt * 1.5);
    const by = Math.max(water.position.y, beachY(BX, BZ, rhoOf(BX, BZ)) + 1.0);
    barge.position.y = by + 0.35 * Math.sin(state.t * 1.3);
    if (!state.paused) ripple.offset.x = (ripple.offset.x + dt * 0.012) % 1;
    /* лампы: понтон движется */
    LAMPS.forEach((l, i) => {
      const y = l.k === 'barge' ? barge.position.y + l.dy : l.y;
      const pulse = (lampCol[l.k] === LAMP.alarm) ? 1 + 0.35 * Math.sin(state.t * 6) : 1;
      m4.compose(pp.set(l.x, y, l.z), q.identity(), sc.set(pulse, pulse, pulse));
      lamps.setMatrixAt(i, m4);
    });
    lamps.instanceMatrix.needsUpdate = true;
    /* стрелки по трубам: скорость ∝ расходу из Ditto; нет расхода — стоят серыми */
    for (const k in phase) if (!state.paused) phase[k] = (phase[k] + dt * (4 + 30 * Math.min(2, flow[k])) ) % 1e6;
    arrows.forEach((a, i) => {
      const f = flow[a.k];
      const u = ((a.u0 + phase[a.k] / a.cv.len) % 1 + 1) % 1;
      a.cv.getPointAt(u, pp); a.cv.getTangentAt(u, tg);
      pp.y += PR + 1.5;
      q.setFromUnitVectors(X, tg);
      m4.compose(pp, q, sc.set(1, 1, 1));
      arrowMesh.setMatrixAt(i, m4);
      if (state.fresh) arrowMesh.setColorAt(i, cc.setHex(f > 0.001 ? a.color : GREY));
    });
    arrowMesh.instanceMatrix.needsUpdate = true;
    if (state.fresh && arrowMesh.instanceColor) arrowMesh.instanceColor.needsUpdate = true;
    /* ореолы: пьезометр выше S0, утечка */
    piezo.forEach((p, i) => {
      if (!piezoState[i] || !piezoState[i].alarm) return;
      glow.halo(p.x - 1.3, p.y + 15, p.z, 0xff3a2a, true);
      glow.ring(p.x, p.y + 0.4, p.z, 10, 0xff3324, true);
    });
    if (leak > 0 && leakAt) { glow.ring(puddle.position.x, puddle.position.y + 0.3, puddle.position.z, 16, 0xff3324, true); glow.halo(leakAt.x, leakAt.y + 4, leakAt.z, 0xff3a2a, true); }
  }
  /* начальные цвета экземпляров (до первого опроса) */
  arrows.forEach((a, i) => arrowMesh.setColorAt(i, cc.setHex(GREY)));
  fresh({});
  /* поверхность для колец на земле: в чаше — не ниже зеркала пруда */
  const surface = (x, z) => { const g = ground(x, z); return rhoOf(x, z) < 92 ? Math.max(g, water.position.y) : g; };
  return { update: frame, ground, surface, curves };
}
