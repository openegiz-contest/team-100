/* «Диорама», модуль «фабрика»: склад концентрата и отгрузка — навес с бункерными стенами,
   бурт концентрата (размер ∝ stock_t / паспорт capacity_t из Ditto), фронтальный погрузчик,
   ж/д путь и поезд. Поезд — по паспорту conc-stock.train в Ditto («21 вагон × 70 т, в 06:00
   и 18:00»): подходит к складу перед этим временем модели, вагоны наполняются после него
   (сколько вагонов и тонн — wagons_shift, shipped_t_shift из Ditto), затем уходит. Движение
   поезда и погрузчика — схема. */
import { NB } from './plant_geo.js';

export function buildShip(ctx, K, group) {
  const { THREE, AKT, NODES } = ctx;
  const { box, beam, body } = K;
  const CS = 'conc-stock';
  const has = id => !!AKT.things[id];
  const V = (x, y, z) => new THREE.Vector3(x, y, z);
  const ups = [];

  /* ------------------------------------------------------- навес склада */
  const nc = NODES[CS];                                    // (665, −28)
  const G = ctx.heightAt(nc.x, nc.z);
  const X0 = 634, X1 = 700, Z0 = -72, Z1 = 14, H = 24;
  const cx = (X0 + X1) / 2, cz = (Z0 + Z1) / 2;
  {
    const P = [];
    const wall = 0xdcd8cf, trim = 0x59606a, roof = 0xa3a9ae;
    P.push(box(X1 - X0, 0.4, Z1 - Z0, cx, G, cz, 0xcfcac1));
    P.push(box(X1 - X0, H, 1.6, cx, G, Z0 + 0.8, wall), box(X1 - X0 + 0.4, 2, 2, cx, G + H - 2, Z0 + 0.8, trim));
    P.push(box(1.6, H, Z1 - Z0, X0 + 0.8, G, cz, wall), box(2, 2, Z1 - Z0 + 0.4, X0 + 0.8, G + H - 2, cz, trim));
    P.push(box(X1 - X0 - 3, 3, 0.4, cx, G + H - 7, Z0 + 1.8, 0x9cc2d8));
    /* бункерные (подпорные) стены из бетона внутри */
    P.push(box(X1 - X0 - 4, 6, 2.4, cx, G, Z0 + 2.8, 0xbdb7ac), box(2.4, 6, Z1 - Z0 - 4, X0 + 2.8, G, cz, 0xbdb7ac));
    P.push(box(X1 - X0, 6, 1.4, cx, G, Z1 - 0.7, wall));
    /* кровля над задней частью, каркас над остальной */
    P.push(box(X1 - X0 + 2, 1.2, 32, cx, G + H, Z0 + 16, roof));
    for (const z of [Z0, Z0 + 28, Z0 + 56, Z1]) P.push(beam([X1 - 0.6, G, z], [X1 - 0.6, G + H + 0.6, z], 1.2, trim));
    P.push(beam([X1 - 0.6, G + H + 0.6, Z0], [X1 - 0.6, G + H + 0.6, Z1], 1.2, trim));
    for (const x of [X0 + 1, cx, X1 - 1]) P.push(beam([x, G + H + 0.6, Z0 + 32], [x, G + H + 0.6, Z1], 0.9, trim));
    P.push(beam([X0 + 1, G + H + 0.6, Z1], [X1 - 0.6, G + H + 0.6, Z1], 1.2, trim));
    /* бетонная площадка погрузки между складом и путём */
    P.push(box(14, G, 70, 708, 0, cz, 0xc4bfb5));
    const m = body(P, CS);
    group.add(m);
    ctx.onClick(CS, m);
  }

  /* -------------------------------------------------------- бурт концентрата */
  const pile = (() => {
    const g0 = new THREE.SphereGeometry(1, K.soft ? 14 : 18, 6, 0, Math.PI * 2, 0, Math.PI / 2);
    const g = ctx.merge([{ geometry: g0, color: 0x4a463f }]);
    const P = g.attributes.position, C = g.attributes.color;
    for (let i = 0; i < P.count; i++) {
      const x = P.getX(i), y = P.getY(i), z = P.getZ(i);
      const k = 1 + 0.06 * Math.sin(x * 9.1 + z * 5.3) * (1 - y);
      P.setXYZ(i, x * k, y * (1 + 0.05 * Math.sin(z * 7.7)), z * k);
      const c = 0.9 + 0.18 * (0.5 + 0.5 * Math.sin(x * 23.1 + z * 31.7 + y * 13.3));
      C.setXYZ(i, C.getX(i) * c, C.getY(i) * c, C.getZ(i) * c);
    }
    g.computeVertexNormals();
    const m = new THREE.Mesh(ctx.bake(g), ctx.materials.baked);
    m.name = 'conc-pile';
    m.position.set(cx + 2, G + 0.3, cz + 2);
    group.add(m);
    ctx.onClick(CS, m);
    return m;
  })();
  let pileF = 0.35, pileGoal = 0.35;
  const setPile = f => pile.scale.set(9 + 20 * f, 2 + 15 * f, 12 + 27 * f);
  setPile(pileF);

  /* ------------------------------------------------------------- ж/д путь */
  const RX = NODES.rail ? NODES.rail.x : 718;
  {
    const P = [box(10, 1, 1000, RX, 0, 0, 0x9d958b)];
    for (let z = -497; z <= 497; z += 4.5) P.push(box(7.4, 0.5, 1.4, RX, 1, z, 0x6e5c49));
    P.push(box(0.5, 0.7, 1000, RX - 2.2, 1.5, 0, 0x4b525a), box(0.5, 0.7, 1000, RX + 2.2, 1.5, 0, 0x4b525a));
    K.misc(P);
  }

  /* --------------------------------------------------------------- поезд */
  const pass = String(AKT.pass(CS, 'train') || '');
  const times = [...pass.matchAll(/(\d{1,2}):(\d{2})/g)].map(m => +m[1] * 60 + +m[2]).filter(v => v >= 0 && v < 1440);
  const TIMES = times.length ? times : [360, 1080];
  const NW = Math.max(4, Math.min(40, +((/(\d+)\s*ваг/.exec(pass) || [])[1]) || 21));
  const RAIL_Y = 1.85, PITCH = 13.4;
  const wagonGeo = ctx.merge([
    { geometry: new THREE.BoxGeometry(5.6, 1, 11.4), color: 0x2b2d30, position: [0, 1.9, 0] },
    { geometry: new THREE.BoxGeometry(4.6, 1.6, 3), color: 0x26282b, position: [0, 0.8, -3.8] },
    { geometry: new THREE.BoxGeometry(4.6, 1.6, 3), color: 0x26282b, position: [0, 0.8, 3.8] },
    { geometry: new THREE.BoxGeometry(6, 0.5, 11.6), color: 0x6a3f2c, position: [0, 2.6, 0] },
    { geometry: new THREE.BoxGeometry(0.4, 4.2, 11.6), color: 0x7b4b34, position: [-2.8, 4.9, 0] },
    { geometry: new THREE.BoxGeometry(0.4, 4.2, 11.6), color: 0x7b4b34, position: [2.8, 4.9, 0] },
    { geometry: new THREE.BoxGeometry(5.2, 4.2, 0.4), color: 0x734531, position: [0, 4.9, -5.6] },
    { geometry: new THREE.BoxGeometry(5.2, 4.2, 0.4), color: 0x734531, position: [0, 4.9, 5.6] },
    { geometry: new THREE.BoxGeometry(6.2, 0.5, 0.6), color: 0x9a6a4c, position: [0, 7.1, -5.6] },
    { geometry: new THREE.BoxGeometry(6.2, 0.5, 0.6), color: 0x9a6a4c, position: [0, 7.1, 5.6] },
    { geometry: new THREE.BoxGeometry(0.6, 0.5, 11.8), color: 0x9a6a4c, position: [-2.8, 7.1, 0] },
    { geometry: new THREE.BoxGeometry(0.6, 0.5, 11.8), color: 0x9a6a4c, position: [2.8, 7.1, 0] },
  ]);
  const wagons = new THREE.InstancedMesh(wagonGeo, ctx.materials.vc, NW);
  wagons.name = 'wagons'; wagons.frustumCulled = false;
  const loadGeo = ctx.keep(new THREE.BoxGeometry(5.1, 1, 10.7).translate(0, 0.5, 0));
  const loads = new THREE.InstancedMesh(loadGeo, ctx.mat(0x4a463f), NW);
  loads.name = 'wagon-loads'; loads.frustumCulled = false;
  const loco = new THREE.Mesh(ctx.merge([
    { geometry: new THREE.BoxGeometry(5.8, 1.2, 17), color: 0x2b2d30, position: [0, 2.1, 0] },
    { geometry: new THREE.BoxGeometry(4.6, 1.8, 3.4), color: 0x26282b, position: [0, 0.9, -5.6] },
    { geometry: new THREE.BoxGeometry(4.6, 1.8, 3.4), color: 0x26282b, position: [0, 0.9, 5.6] },
    { geometry: new THREE.BoxGeometry(5.4, 5.2, 12.4), color: 0x2f5f8f, position: [0, 5.3, 1.6] },
    { geometry: new THREE.BoxGeometry(5.8, 6.2, 4), color: 0x2f5f8f, position: [0, 5.8, -6.4] },
    { geometry: new THREE.BoxGeometry(5.9, 1.6, 4.1), color: 0x9cc2d8, position: [0, 7.2, -6.4] },
    { geometry: new THREE.BoxGeometry(5.6, 0.9, 17), color: 0xf2b500, position: [0, 3.4, 0] },
  ]), ctx.materials.vc);
  loco.name = 'loco';
  group.add(wagons, loads, loco);
  for (const m of [wagons, loads, loco]) ctx.onClick(CS, m, { halo: false });
  /* место стоянки: средний вагон у склада */
  const zStand = i => cz - (NW - 1) / 2 * PITCH + i * PITCH;
  const zLoco = () => zStand(0) - PITCH / 2 - 9;
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), p = new THREE.Vector3(), sc = new THREE.Vector3();
  const ease = t => t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t);
  /* фаза поезда в минутах модели относительно ближайшего времени погрузки: null — поезда нет */
  const ARR = 45, DEP = 50;
  const PH = { T: 0, d: 0 };
  const phase = simNow => {
    if (simNow == null || !isFinite(simNow)) return null;
    const m = ((simNow % 1440) + 1440) % 1440;
    for (const T of TIMES) {
      let d = m - T;
      if (d > 720) d -= 1440; else if (d < -720) d += 1440;
      if (d >= -ARR && d <= DEP) { PH.T = T; PH.d = d; return PH; }
    }
    return null;
  };
  const plural = (n, one, few, many) => { const a = Math.abs(n) % 100, b = a % 10; return a > 10 && a < 20 ? many : b === 1 ? one : b >= 2 && b <= 4 ? few : many; };
  let loaded = 0, lastKey = '', fill = 0, shown = true;
  const trainLabelAt = V(RX, 16, 0);
  function placeTrain(ph) {
    if (!ph && !shown) return;                         // поезда нет и уже убран — нечего обновлять
    shown = !!ph;
    let dz = 0, show = !!ph;
    if (ph) {
      if (ph.d < -25) dz = 640 * (1 - ease((ph.d + ARR) / (ARR - 25)));
      else if (ph.d > 25) dz = -760 * ease((ph.d - 25) / (DEP - 25));
    }
    const vis = z => show && z > -494 && z < 494;
    for (let i = 0; i < NW; i++) {
      const z = zStand(i) + dz, v = vis(z);
      m4.compose(p.set(RX, RAIL_Y, z), q.identity(), v ? sc.set(1, 1, 1) : sc.set(0.0001, 0.0001, 0.0001));
      wagons.setMatrixAt(i, m4);
      const f = Math.max(0, Math.min(1, fill - i));
      m4.compose(p.set(RX, RAIL_Y + 3, z), q.identity(), v && f > 0.01 ? sc.set(1, 3.7 * f, 1) : sc.set(0.0001, 0.0001, 0.0001));
      loads.setMatrixAt(i, m4);
    }
    wagons.instanceMatrix.needsUpdate = true; loads.instanceMatrix.needsUpdate = true;
    wagons.visible = loads.visible = show;           // без поезда — ни одного вызова отрисовки
    const zl = zLoco() + dz;
    loco.visible = vis(zl);
    loco.position.set(RX, RAIL_Y, zl);
    trainLabelAt.set(RX, 14, Math.max(-480, Math.min(480, zl)));
  }
  placeTrain(null);
  const trainLabel = ctx.label('plant:train', () => {
    const ph = phase(AKT.simTime);
    if (!ph || !has(CS)) return '';
    const hh = AKT.clock(ph.T);
    if (ph.d < 0) return `Поезд под погрузку · ${hh} модели\n${NW}${NB}${plural(NW, 'вагон', 'вагона', 'вагонов')} по паспорту склада`;
    const w = AKT.num(CS, 'wagons_shift'), t = AKT.num(CS, 'shipped_t_shift');
    return `Отгрузка ${hh} модели · ${AKT.fmt(w)}${NB}ваг. · ${AKT.fmt(t)}${NB}т\nотгружено за смену (Ditto)`;
  }, { thing: CS, prio: 2, at: () => trainLabelAt, title: () => `Поезд: ${pass || 'по паспорту склада концентрата'} (паспорт conc-stock в Ditto); подход, погрузка и уход на макете — схема` });
  void trainLabel;

  /* ------------------------------------------------------ фронтальный погрузчик */
  const loader = new THREE.Mesh(ctx.merge([
    { geometry: new THREE.BoxGeometry(7, 3, 4.4), color: 0xf2b500, position: [-1, 3.4, 0] },
    { geometry: new THREE.BoxGeometry(3, 3.2, 3.6), color: 0xf2b500, position: [-2.6, 6.2, 0] },
    { geometry: new THREE.BoxGeometry(3.1, 1.6, 3.7), color: 0x9cc2d8, position: [-2.6, 6.6, 0] },
    { geometry: new THREE.CylinderGeometry(1.8, 1.8, 5.6, 10), color: 0x222326, position: [-3.4, 1.8, 0], rotation: [Math.PI / 2, 0, 0] },
    { geometry: new THREE.CylinderGeometry(1.8, 1.8, 5.6, 10), color: 0x222326, position: [1.8, 1.8, 0], rotation: [Math.PI / 2, 0, 0] },
    { geometry: new THREE.BoxGeometry(4.4, 0.8, 1), color: 0x2a2a2a, position: [4.6, 3.6, 1.6] },
    { geometry: new THREE.BoxGeometry(4.4, 0.8, 1), color: 0x2a2a2a, position: [4.6, 3.6, -1.6] },
    { geometry: new THREE.BoxGeometry(2.6, 2.6, 5.6), color: 0x5b636c, position: [7.2, 2.4, 0] },
  ]), ctx.materials.vc);
  loader.name = 'loader';
  const LX1 = RX - 10;
  loader.position.set(X1 - 6, G, cz + 10);
  loader.rotation.y = Math.PI;
  group.add(loader);
  ctx.onClick(CS, loader, { halo: false });
  let lt = 0;

  /* ------------------------------------------------------------- подписи */
  ctx.label('plant:' + CS, () => {
    if (!has(CS)) return '';
    const s = AKT.num(CS, 'stock_t'), cap = AKT.pass(CS, 'capacity_t');
    return `${AKT.nameRu(CS)} · ${AKT.fmt(s)}${cap ? NB + 'из' + NB + AKT.fmt(cap) : ''}${NB}т`;
  }, {
    thing: CS, prio: 2, at: V(cx, G + H + 8, Z0 + 10),
    title: () => `${AKT.nameRu(CS)}: ${AKT.stOf(CS)} · запас ${AKT.fmt(AKT.num(CS, 'stock_t'))} т, приход ${AKT.fmt(AKT.num(CS, 'in_tph'))} т/ч (Ditto); вместимость ${AKT.fmt(AKT.pass(CS, 'capacity_t'))} т по паспорту; бурт ∝ запасу (схема)`,
  });

  /* ------------------------------------------------------------- обновление */
  ups.push((state, dt) => {
    if (state.fresh && has(CS)) {
      const s = AKT.num(CS, 'stock_t'), cap = AKT.pass(CS, 'capacity_t') || 20000;
      if (s != null) pileGoal = Math.max(0.04, Math.min(1.05, Math.sqrt(Math.max(0, s) / cap)));
    }
    if (Math.abs(pileGoal - pileF) > 1e-4) { pileF += (pileGoal - pileF) * (1 - Math.exp(-dt * 1.5)); setPile(pileF); }
    const ph = phase(state.simNow);
    const key = ph ? `${ph.T}` : '';
    if (key !== lastKey) { lastKey = key; loaded = 0; fill = 0; }
    if (ph && ph.d >= 0) {
      if (state.fresh) {
        const w = AKT.num(CS, 'wagons_shift');
        loaded = w != null && w > 0 ? Math.min(NW, w) : loaded;
      }
      fill = loaded * Math.max(0, Math.min(1, ph.d / 18));
    } else fill = 0;
    placeTrain(ph);
    /* погрузчик: челнок между буртом и вагонами, пока идёт погрузка */
    const busy = ph && ph.d >= 0 && ph.d <= 18 && loaded > 0 && !state.paused;
    if (busy) lt += dt;
    const u = busy ? 0.5 - 0.5 * Math.cos(lt * Math.PI / 2.4) : 0;
    const lx0 = Math.min(X1 - 6, cx + 2 + (9 + 20 * pileF) + 6);       // у края бурта
    loader.position.x = lx0 + (LX1 - lx0) * u;
    loader.rotation.y = busy ? 0 : Math.PI;
  });

  return { update(state, dt) { for (const f of ups) f(state, dt); } };
}
