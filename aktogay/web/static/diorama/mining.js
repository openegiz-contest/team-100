/* «Диорама», модуль «горные работы» (договор — API.md): самосвалы, экскаваторы,
   буровые станки, бульдозеры, забои, ЦПД-1 и ЦПД-2, конвейеры 1 и 2 с весами,
   склады руды, ремонтный бокс, перекрытые дороги и объезды.

   Всё живое — из Ditto (опрос /api/state в app.js):
   * самосвал: state LOADING → HAUL_FULL → QUEUE → DUMP → RETURN / DOWN, location
     (забой, дорога, ЦПД; пусто — ремонт), load_t, cycle_min, sim_time публикации;
     паспорт bort, model, payload_t, duty. Ditto публикует самосвал раз в 30 мин
     модели, поэтому между публикациями машина идёт по циклу модели: фаза из Ditto,
     длительности фаз — допущение стенда (погрузка 3, очередь 2, разгрузка 1 мин,
     рейсы гружёным и порожним делят остаток cycle_min поровну, как в PARAMETERS.md).
     QUEUE без груза — линия не принимает руду: самосвал ждёт у ЦПД. DOWN — в ремонтном боксе;
   * экскаватор: state, tph; забой — паспорт face; ковшей на самосвал — грузоподъёмность
     из паспорта самосвала / ковш (данные производителя, не проверены) × насыпная плотность [допущение];
   * забой: est_cu, hardness / est_axb (оценка блочной модели), blasted_t (размер развала);
   * буровой станок и бульдозер: state, location (DOWN с местом в Ditto — стоит там же, станок
     с опущенной мачтой; без места — у ремонтного бокса); станок — на уступе над своим забоем;
   * ЦПД: state, tph; конвейер: tph / паспорт capacity_tph (бег ленты); весы: state;
     склад: level_t / паспорт live_t (высота конуса); дороги: state OPEN / CLOSED.
   Схема, не масштаб: машины крупнее масштаба, места на уступах — схема. */
import * as THREE from '../vendor/three-0.160.0/three.module.min.js';
import { PIT, pitR, crestS, levelY, PolyCurve } from './layout.js';
import * as G from './mining_geo.js';

const V3 = THREE.Vector3;
/* цикл самосвала, мин модели [допущение стенда: fleet_load_min, fleet_queue_min, fleet_dump_min] */
const LOAD_MIN = 3, QUEUE_MIN = 2, DUMP_MIN = 1;
const PHASES = ['LOADING', 'HAUL_FULL', 'QUEUE', 'DUMP', 'RETURN'];
const RHO = 1.8;          // насыпная плотность взорванной породы, т/м³ [допущение]
/* раскладка на макете (у.е., схема) */
const LANE = 3.3, GAP = 15, QLEN = 32, LOAD_OFF = 2.6;
const CAP = 64;            // самосвалов в экземплярах
const ROADS = ['ramp-1', 'ramp-2', 'road-dump'];
/* объезды перекрытых дорог (x, z; от выезда из карьера к месту разгрузки), схема */
const DETOURS = {
  'ramp-1': [[-166, -122], [-152, -158], [-134, -186], [-119, -178], [-113, -163]],
  'ramp-2': [[-158, -80], [-142, -20], [-140, 40], [-128, 80]],
  'road-dump': [[-160, -150], [-172, -232], [-212, -318], [-262, -372]],
};
const BARRIER_U = { 'ramp-1': 0.62, 'ramp-2': 0.5, 'road-dump': 0.3 };

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const smooth = t => { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); };
const hash01 = s => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 10007) / 10007; };
const yawOf = (dx, dz) => Math.atan2(-dz, dx);
const angLerp = (a, b, t) => { let d = (b - a) % (2 * Math.PI); if (d > Math.PI) d -= 2 * Math.PI; if (d < -Math.PI) d += 2 * Math.PI; return a + d * t; };
const phaseLens = C => { const road = Math.max(0.5, (C - LOAD_MIN - QUEUE_MIN - DUMP_MIN) / 2); return [LOAD_MIN, road, QUEUE_MIN, DUMP_MIN, road]; };
const truckScale = m => /793/.test(m) ? 1 : /785/.test(m) ? 0.88 : /777/.test(m) ? 0.8 : 0.9;
const drillScale = m => /viper|231/i.test(m) ? 1 : /d65/i.test(m) ? 0.93 : /d55/i.test(m) ? 0.86 : 0.9;
const dozerScale = m => /d375/i.test(m) ? 1.03 : /d10/i.test(m) ? 1 : /d9/i.test(m) ? 0.9 : 0.95;

export function build(ctx) {
  const { scene, AKT, layout, colors: C, glowColors: GC } = ctx;
  const keep = ctx.keep;
  const root = new THREE.Group(); root.name = 'mining'; scene.add(root);
  const WHITE = new THREE.Color(1, 1, 1);

  /* материалы: свои для экземпляров (общие с обычными мешами дают смену программ на каждом вызове) */
  const matInst = keep(new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true }));
  const matPlain = keep(new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true }));
  const matLamp = keep(new THREE.MeshBasicMaterial({ color: 0xffffff }));
  const matDust = keep(new THREE.MeshBasicMaterial({ color: 0xd9cdb5, transparent: true, opacity: 0.4, depthWrite: false }));
  const inst = (geo, mat, n, name) => {
    const m = new THREE.InstancedMesh(geo, mat, n);
    m.count = 0; m.frustumCulled = false; m.name = name;
    m.boundingSphere = new THREE.Sphere(new V3(0, 0, 0), 8000);     // экземпляры движутся: сфера на весь макет (для щелчка)
    m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    for (let i = 0; i < n; i++) m.setColorAt(i, WHITE);
    root.add(m);
    return m;
  };
  const ZERO = new THREE.Matrix4().makeScale(0, 0, 0);
  const baked = (parts, name) => { const m = new THREE.Mesh(ctx.bake(ctx.merge(parts)), ctx.materials.baked); m.name = name; root.add(m); return m; };

  /* --------------------------------------------------------- glow helper */
  const GLOW_K = { issue: 0.55, alarm: 0.55, chain: 0.45, focus: 0.25 };
  const glowCol = {}; for (const k of Object.keys(GLOW_K)) glowCol[k] = new THREE.Color(GC[k]);
  let pulse = 0;
  /* цвет экземпляра: основа base, свечение вещи (беда пульсирует) */
  const tint = (id, base, out) => {
    out.copy(base);
    const g = ctx.glowOf(id);
    if (!g || !glowCol[g]) return out;
    const k = g === 'issue' ? 0.3 + 0.45 * pulse : GLOW_K[g];
    return out.lerp(glowCol[g], k);
  };

  /* ------------------------------------------------------- static: ЦПД, конвейеры, склады, бокс */
  const N = ctx.NODES;
  const plants = [1, 2].map(n => {
    const cr = N[`crusher-${n}`], nx = cr.x, nz = cr.z, y0 = ctx.heightAt(nx, nz);
    const crusher = baked(G.crusherParts(C, nx, nz, y0), `crusher-${n}`);
    ctx.onClick(`crusher-${n}`, crusher);
    /* конвейер: от перегрузочного узла ЦПД к вершине конуса склада (линия схемы conveyor-N) */
    const line = ctx.LINES[`conveyor-${n}`];
    const sp = N[`stockpile-${n}`];
    const xa = line[0][0], xb = sp.x - 4, z = line[0][1];
    const ya = ctx.heightAt(xa, z) + 2.6, yb = ya + (xb - xa) * 0.3;
    const yAt = x => ya + (x - xa) * (yb - ya) / (xb - xa);
    const conv = baked(G.conveyorParts(C, xa, ya, xb, yb, z, (x, zz) => ctx.heightAt(x, zz)), `conveyor-${n}`);
    ctx.onClick(`conveyor-${n}`, conv);
    const len = Math.hypot(xb - xa, yb - ya);
    const tex = ctx.beltTexture(); tex.repeat.set(len / 16, 1);
    const beltMat = keep(new THREE.MeshBasicMaterial({ map: tex, color: ctx.litColor(0xffffff) }));
    const belt = new THREE.Mesh(keep(new THREE.PlaneGeometry(len, 3.9).rotateX(-Math.PI / 2)), beltMat);
    belt.position.set((xa + xb) / 2, (ya + yb) / 2 + 0.05, z); belt.rotation.z = Math.atan2(yb - ya, xb - xa); belt.name = `belt-${n}`;
    root.add(belt);
    ctx.onClick(`conveyor-${n}`, belt);
    /* весы на ленте (узел weigher-N) */
    const wn = N[`weigher-${n}`], wx = wn ? wn.x : 40, wy = yAt(wx);
    const weigher = baked(G.weigherParts(C, wx, wy, z), `weigher-${n}`);
    ctx.onClick(`weigher-${n}`, weigher);
    /* конус склада */
    const sy = ctx.heightAt(sp.x, sp.z);
    const cone = new THREE.Mesh(keep(G.coneGeometry()), ctx.mat(C.oreLight));
    cone.position.set(sp.x, sy, sp.z); cone.scale.setScalar(0.5); cone.name = `stockpile-${n}`;
    root.add(cone);
    ctx.onClick(`stockpile-${n}`, cone);
    return {
      n, nx, nz, y0, z, xa, xb, ya, yb, wx, wy, sp, sy, tex, cone, coneS: 0.5, coneT: 0.5, speed: 0, run: false, mantleA: 0,
      hopper: new V3(nx + G.HOPPER, y0, nz), lampAt: new V3(nx + 18.6, y0 + 26.4, nz - 16.6),
    };
  });
  /* основания складов (неизвлекаемый остаток, схема) */
  baked(plants.map(p => ({ geometry: new THREE.CylinderGeometry(57, 70, 3.2, 24, 1), color: C.ore, position: [p.sp.x, p.sy + 1.1, p.sp.z] })), 'stock-bases');
  const shopY = ctx.heightAt(2, -350);
  const shop = baked(G.shopParts(C, shopY), 'fleet-shop');
  ctx.onClick('fleet', shop);

  /* -------------------------------------------- дороги: объезды и шлагбаумы */
  const ribbon = (pts, width, color) => {
    const pos = [], col = [], c = new THREE.Color(color), hw = width / 2;
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i - 1], b = pts[i], dx = b.x - a.x, dz = b.z - a.z, l = Math.hypot(dx, dz) || 1, nx = -dz / l * hw, nz = dx / l * hw;
      const q = [[a.x - nx, a.y, a.z - nz], [b.x - nx, b.y, b.z - nz], [b.x + nx, b.y, b.z + nz], [a.x - nx, a.y, a.z - nz], [b.x + nx, b.y, b.z + nz], [a.x + nx, a.y, a.z + nz]];
      for (const p of q) { pos.push(p[0], p[1], p[2]); col.push(c.r, c.g, c.b); }
    }
    const g = keep(new THREE.BufferGeometry());
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    g.computeVertexNormals();
    return ctx.bake(g, { flip: 'up' });
  };
  const roads = {};
  for (const r of ROADS) {
    const rc = ctx.pathFor(r);
    if (!rc) continue;
    const start = rc.points[0], end = rc.points[rc.points.length - 1];
    let detour = null, mesh = null;
    if (DETOURS[r]) {
      const ctl = [new V3(start.x, 0, start.z)].concat(DETOURS[r].map(([x, z]) => new V3(x, 0, z)), [new V3(end.x, 0, end.z)]);
      const cr = new THREE.CatmullRomCurve3(ctl, false, 'centripetal', 0.5);
      const flat = cr.getSpacedPoints(Math.max(10, Math.ceil(cr.getLength() / 5)));
      const pts = flat.map(p => new V3(p.x, ctx.heightAt(p.x, p.z) + 0.75, p.z));
      pts[pts.length - 1].copy(end);
      detour = new PolyCurve(pts);
      mesh = new THREE.Mesh(ribbon(pts.map(p => new V3(p.x, p.y - 0.28, p.z)), 11, 0xb9aa90), ctx.materials.bakedDouble);
      mesh.visible = false; mesh.name = 'detour-' + r;
      root.add(mesh);
    }
    roads[r] = { curve: rc, start, end, detour, mesh, closed: false };
  }
  const barrierM = inst(keep(new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0)), matPlain, 5 * ROADS.length, 'barriers');
  barrierM.count = 5 * ROADS.length;
  {
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), p = new V3(), t = new V3(), s = new V3(), red = new THREE.Color(0xd8433a), wh = new THREE.Color(0xf4f1ea);
    ROADS.forEach((r, ri) => {
      const R = roads[r];
      for (let k = 0; k < 5; k++) {
        if (!R) { barrierM.setMatrixAt(ri * 5 + k, ZERO); continue; }
        R.curve.getPoint(BARRIER_U[r], p); R.curve.getTangent(BARRIER_U[r], t); t.y = 0; t.normalize();
        const off = (k - 2) * 2.9;
        p.x += -t.z * off; p.z += t.x * off;
        q.setFromAxisAngle(new V3(0, 1, 0), yawOf(t.x, t.z));
        m.compose(p, q, s.set(1.3, 1.7, 2.5));
        R.barrier = R.barrier || [];
        R.barrier[k] = m.clone();
        barrierM.setMatrixAt(ri * 5 + k, ZERO);
        barrierM.setColorAt(ri * 5 + k, k % 2 ? wh : red);
      }
    });
  }

  /* ---------------------------------------------------------------- trucks */
  const truckBodyM = inst(ctx.merge(G.truckBody(C)), matInst, CAP, 'trucks');
  const truckBedM = inst(ctx.merge(G.truckBed(C)), matInst, CAP, 'truck-beds');
  const truckLoadM = inst(keep(G.truckLoad()), matPlain, CAP, 'truck-loads');
  const MACH = CAP + 40;
  const blobM = inst(ctx.blobGeometry, ctx.blobMaterial(0.3), MACH, 'machine-shadows');
  blobM.renderOrder = 1;
  const truckIds = [];
  const pickTruck = hit => truckIds[hit.instanceId];
  ctx.onClick(pickTruck, truckBodyM, { halo: false });
  ctx.onClick(pickTruck, truckBedM, { halo: false });
  /* самосвалы, станки, бульдозеры и забои рисуются экземплярами — заняты по типу с самого начала */
  ctx.claim(id => ['truck', 'drill', 'dozer', 'face'].includes(AKT.type(id)));
  const trucks = new Map();
  const ORE_C = new THREE.Color(C.ore), WASTE_C = new THREE.Color(C.waste);

  /* ---------------------------------------------------------- excavators */
  const excGeo = {};
  for (const k of ['shovel', 'backhoe']) excGeo[k] = { lower: ctx.merge(G.excLower(C, k)), upper: ctx.merge(G.excUpper(C, k)), arm: ctx.merge(G.excArm(C, k)) };
  const lumpM = inst(keep(G.lump()), matPlain, 12, 'bucket-loads');
  /* модель экскаватора: форма и ковш. EX01 — Hitachi EX3600 по перечню техники ТОО «КАЗ Минералз Актогай»
     от 29.02.2024 (факт). Ковши, м³ — данные производителя Hitachi, в этой работе не проверены. */
  const excModel = id => {
    const m = String(AKT.pass(id, 'model') || ''), bort = String(AKT.pass(id, 'bort') || AKT.shortName(id));
    if (/ZX\s*870/i.test(m)) return { kind: 'backhoe', s: 0.74, m3: 4.5, dump: 1.55, text: `Hitachi ZX870 (паспорт Ditto)` };
    if (/EX\s*1200/i.test(m)) return { kind: 'backhoe', s: 0.84, m3: 6.5, dump: 1.55, text: `Hitachi EX1200 (паспорт Ditto)` };
    if (/EX\s*3600/i.test(m)) return { kind: 'shovel', s: 1, m3: 22, text: 'Hitachi EX3600 (паспорт Ditto)' };
    if (bort === 'EX01') return { kind: 'shovel', s: 1, m3: 22, text: 'Hitachi EX3600 — перечень техники 29.02.2024 (факт)' };
    return { kind: 'shovel', s: 1, m3: 22, text: `${m || 'Hitachi'}: модель в Ditto не указана, форма и ковш — как у EX3600 [допущение]` };
  };
  /* экскаватор: узел из трёх мешей (подсветку ядро делает само); создаётся, когда вещь появилась в Ditto */
  const excs = [];
  const makeExc = (id, k) => {
    const md = excModel(id), rig = G.EXC_RIG[md.kind];
    const g = new THREE.Group(); g.scale.setScalar(md.s); g.name = id;
    const lower = new THREE.Mesh(excGeo[md.kind].lower, ctx.materials.vc);
    const upper = new THREE.Mesh(excGeo[md.kind].upper, ctx.materials.vc); upper.position.y = rig.ring;
    const arm = new THREE.Mesh(excGeo[md.kind].arm, ctx.materials.vc); arm.position.set(rig.boom[0], rig.boom[1], 0);
    upper.add(arm); g.add(lower, upper); root.add(g);
    for (const m of [lower, upper, arm]) ctx.onClick(id, m);
    const dumpA = md.dump != null ? md.dump : rig.dump;
    /* вылет ковша над кузовом (у.е. от оси поворота) */
    const ca = Math.cos(dumpA), sa = Math.sin(dumpA);
    const reach = (rig.boom[0] + rig.bucket[0] * ca - rig.bucket[1] * sa) * md.s;
    const e = {
      id, k, md, rig, g, lower, upper, arm, dumpA, reach, face: '', E: new V3(), digYaw: 0, yaw: 0, alpha: rig.rest,
      st: '', tph: null, placed: '', t0: new V3(1, 0, 0), out: new V3(0, 0, 1), waste: false, passT: null, passK: -1, idleT: hash01(id) * 10, moveT: 0,
      top: new V3(), pile: null,
    };
    /* подпись: бортовой номер и т/ч из Ditto (вблизи); отклонение — всегда */
    const at = () => e.top, title = () => excTitle(e);
    lbl(id, () => AKT.deviates(id) ? '' : `${AKT.shortName(id)} · ${AKT.fmt(e.tph)} т/ч`, { thing: id, prio: 4, maxDist: 1900, at, title });
    lbl(id + ':dev', () => devText(id), { thing: id, prio: 4, at, title });
    excs.push(e);
    return e;
  };

  /* ---------------------------------------------------- drills, dozers, faces */
  const drillBodyM = inst(ctx.merge(G.drillBody(C)), matInst, 16, 'drills');
  const drillMastM = inst(ctx.merge(G.drillMast()), matInst, 16, 'drill-masts');
  const dozerM = inst(ctx.merge(G.dozerBody(C)), matInst, 16, 'dozers');
  const pileM = inst(keep(G.pileGeometry()), matPlain, 12, 'face-piles');
  const drillIds = [], dozerIds = [], faceIds = [];
  ctx.onClick(hit => drillIds[hit.instanceId], drillBodyM, { halo: false });
  ctx.onClick(hit => drillIds[hit.instanceId], drillMastM, { halo: false });
  ctx.onClick(hit => dozerIds[hit.instanceId], dozerM, { halo: false });
  ctx.onClick(hit => faceIds[hit.instanceId], pileM, { halo: false });
  const drills = new Map(), dozers = new Map(), faces = new Map();

  /* ----------------------------------------------- crushers: mantles, lamps, ore, dust */
  const mantleM = inst(keep(G.mantle()), matPlain, 2, 'mantles'); mantleM.count = 2;
  for (let i = 0; i < 2; i++) mantleM.setColorAt(i, new THREE.Color(C.steel));
  const lampM = inst(keep(new THREE.OctahedronGeometry(1)), matLamp, 8, 'lamps'); lampM.count = 6;
  const streamM = inst(keep(new THREE.BoxGeometry(1.7, 1, 1.7).translate(0, -0.5, 0)), matPlain, 2, 'ore-streams'); streamM.count = 2;
  for (let i = 0; i < 2; i++) streamM.setColorAt(i, new THREE.Color(C.ore));
  const DUST_N = 32;
  const dustM = inst(keep(G.lump()), matDust, DUST_N, 'dust'); dustM.count = DUST_N; dustM.renderOrder = 3;
  const dust = []; for (let i = 0; i < DUST_N; i++) { dust.push({ p: new V3(), t: 9, life: 1, size: 1 }); dustM.setMatrixAt(i, ZERO); }
  let dustNext = 0;
  const puff = (x, y, z, size, life) => { const d = dust[dustNext]; dustNext = (dustNext + 1) % DUST_N; d.p.set(x, y, z); d.t = 0; d.life = life || 1.2; d.size = size || 3; };

  /* --------------------------------------------------------------- labels */
  const lbl = (key, text, o) => ctx.label('mining:' + key, text, o);
  const devText = id => AKT.deviates(id) && !(AKT.MACHINE_CATS.has(AKT.cat(id)) && AKT.stopped(AKT.st(id))) ? `${AKT.shortName(id)} · ${AKT.stOf(id)}` : '';
  const truckLabels = new Set();
  for (const p of plants) {
    const cid = `crusher-${p.n}`, kid = `conveyor-${p.n}`, wid = `weigher-${p.n}`, sid = `stockpile-${p.n}`;
    lbl(cid, () => {
      if (!AKT.things[cid]) return '';
      const s = AKT.st(cid);
      return `Дробилка ЦПД-${p.n} · ${AKT.fmt(AKT.num(cid, 'tph'))} т/ч${s && s !== 'RUN' ? ' · ' + AKT.stOf(cid) : ''}`;
    }, { thing: cid, prio: 2, at: new V3(p.nx - 4, p.y0 + 34, p.nz),
      title: () => `${AKT.nameRu(cid)}: ${AKT.stOf(cid)} · ${AKT.fmt(AKT.num(cid, 'tph'))} т/ч (Ditto) · ${AKT.pass(cid, 'kind') || ''}` });
    lbl(kid, () => {
      if (!AKT.things[kid]) return '';
      const s = AKT.st(kid);
      return `${AKT.nameRu(kid)} · ${AKT.fmt(AKT.num(kid, 'tph'))} т/ч${s && s !== 'RUN' ? ' · ' + AKT.stOf(kid) : ''}`;
    }, { thing: kid, prio: 3, maxDist: 1500, at: new V3(p.xa + 50, p.ya + 50 * 0.3 + 4, p.z),
      title: () => `${AKT.nameRu(kid)}: ${AKT.fmt(AKT.num(kid, 'tph'))} т/ч из ${AKT.fmt(AKT.pass(kid, 'capacity_tph'))} т/ч по паспорту (Ditto); бег ленты на макете ∝ т/ч` });
    lbl(wid, () => AKT.things[wid] && AKT.deviates(wid) || AKT.stopped(AKT.st(wid)) ? `${AKT.nameRu(wid)} · ${AKT.stOf(wid)}` : '', { thing: wid, prio: 6, kind: 'small', at: new V3(p.wx, p.wy + 4.5, p.z) });
    lbl(sid, () => !AKT.things[sid] ? '' : `${AKT.nameRu(sid)} · ${AKT.fmt(AKT.num(sid, 'level_t'))} т`, {
      thing: sid, prio: 2, at: () => p.labelAt || null,
      title: () => `${AKT.nameRu(sid)}: ${AKT.fmt(AKT.num(sid, 'level_t'))} т (Ditto) · живой объём ${AKT.fmt(AKT.pass(sid, 'live_t'))} т — допущение стенда · высота конуса на макете ∝ запасу`,
    });
    p.labelAt = new V3(p.sp.x, p.sy + 30, p.sp.z);
  }
  lbl('fleet', () => {
    if (!AKT.things.fleet) return '';
    const r = AKT.num('fleet', 'trucks_ready'), t = AKT.num('fleet', 'trucks_total');
    const rep = {}; for (const n of Object.keys(AKT.things)) { const c = AKT.cat(n); if (AKT.MACHINE_CATS.has(c) && AKT.stopped(AKT.st(n))) rep[c] = (rep[c] || 0) + 1; }
    const parts = [['truck', 'самосв.'], ['drill', 'буровых'], ['dozer', 'бульд.'], ['exc', 'экск.']].filter(([c]) => rep[c]).map(([c, w]) => `${rep[c]} ${w}`);
    return r == null || t == null ? AKT.nameRu('fleet') : `Самосвалы: готовы ${AKT.fmt(r)} из ${AKT.fmt(t)}${parts.length ? '\n◆ в ремонте: ' + parts.join(', ') : ''}`;
  }, { thing: 'fleet', prio: 4, at: new V3(2, shopY + 24, G.SHOP.bayZ),
    title: () => `${AKT.nameRu('fleet')}: ${AKT.stOf('fleet')} · готовы ${AKT.fmt(AKT.num('fleet', 'trucks_ready'))} из ${AKT.fmt(AKT.num('fleet', 'trucks_total'))} (Ditto) · неисправные стоят у ремонтного бокса` });
  ctx.note('самосвалы между опросами Ditto идут по циклу модели: погрузка 3, очередь 2, разгрузка 1 мин [допущение] · забой: зеленее — выше Cu (оценка блочной модели), темнее — крепче');

  /* ------------------------------------------------------- per-poll state */
  const nm = v => AKT.name(String(v || ''));
  let wasteFaces = [], oreFaces = [];
  const lastLineFace = {};
  const lineOf = id => {
    const s = String(AKT.pass(id, 'duty') || '') + ' ' + String(AKT.val(id, 'duty') || '');
    const m = /ЦПД-(\d)|линия\s*(\d)/i.exec(s);
    return m ? +(m[1] || m[2]) : 1;
  };
  const endOfRoad = r => { const l = nm(AKT.pass(r, 'leads_to')); return /^crusher-\d$/.test(l) ? l : (/^ramp-(\d)$/.test(r) ? 'crusher-' + r.slice(5) : 'dump'); };
  const defaultLineFace = line => {
    for (const e of excs) if (new RegExp(`ЦПД-${line}`).test(String(AKT.pass(e.id, 'duty') || ''))) { const f = layout.excFace(e.id); if (f) return f; }
    return oreFaces[line - 1] || oreFaces[0] || '';
  };
  /* забой: место погрузки, направление выезда, развал (по экскаватору забоя) */
  const faceInfo = new Map();
  const faceSpot = fid => {
    const f = layout.face(fid);
    if (!f) return null;
    const key = `${f.level}:${f.angle.toFixed(4)}`;
    const old = faceInfo.get(fid);
    if (old && old.key === key) return old;
    const spur = ctx.pathFor(fid);
    const t0 = spur ? spur.getTangent(0, new V3()) : f.tangent.clone();
    t0.y = 0; t0.normalize();
    const fi = { key, f, t0, out: f.out.clone(), y: f.y, pos: f.pos.clone(), spurLen: spur ? spur.len : 0 };
    faceInfo.set(fid, fi);
    return fi;
  };
  /* рейсы: кривая забой → разгрузка (по объезду, если дорога перекрыта) */
  const haulCache = new Map();
  const haulOf = (face, road) => {
    const closed = !!(roads[road] && roads[road].closed);
    const fi = faceSpot(face);
    const key = `${face}|${road}|${fi ? fi.key : ''}|${closed}`;
    if (haulCache.has(key)) return haulCache.get(key);
    const base = ctx.pathFor(`haul:${face}:${road}`);
    if (!base) return null;
    let H = base;
    if (closed && roads[road].detour) {
      const st = roads[road].start, pts = base.points;
      let cut = pts.length - roads[road].curve.points.length;
      for (let i = pts.length - 1; i >= Math.max(0, cut - 4); i--) if (Math.hypot(pts[i].x - st.x, pts[i].z - st.z) < 0.6) { cut = i; break; }
      H = PolyCurve.concat(new PolyCurve(pts.slice(0, Math.max(1, cut))), roads[road].detour);
    }
    const end = H.getPoint(1, new V3()), tEnd = H.getTangent(1, new V3()); tEnd.y = 0; tEnd.normalize();
    const info = { H, Lh: H.len, end, tEnd, face, road };
    haulCache.set(key, info);
    return info;
  };
  /* места разгрузки: у бункера ЦПД (задом к бункеру) или на отвале */
  const dumpPose = (T, slot, outP) => {
    const I = T.info, s = T.s;
    let away;
    if (T.endKey !== 'dump') {
      const p = plants.find(x => `crusher-${x.n}` === T.endKey) || plants[0];
      away = tv1.set(I.end.x - p.hopper.x, 0, I.end.z - p.hopper.z).normalize();
      outP.copy(p.hopper).addScaledVector(away, 4 + G.TRUCK.L / 2 * s);
      const lat = slot === 0 ? 0 : (slot % 2 ? 1 : -1) * 8.5 * Math.ceil(slot / 2);
      outP.x += -away.z * lat; outP.z += away.x * lat;
      outP.y = 1.6;
    } else {
      away = tv1.copy(I.tEnd).negate();
      outP.copy(I.end).addScaledVector(I.tEnd, 12 - 2 - G.TRUCK.L / 2 * s);
      const lat = slot === 0 ? 0 : (slot % 2 ? 1 : -1) * 9.5 * Math.ceil(slot / 2);
      outP.x += -away.z * lat; outP.z += away.x * lat;
      outP.y = ctx.heightAt(outP.x, outP.z) + 0.3;
    }
    return away;
  };
  /* ремонтный бокс: три бокса, потом стоянка перед ним (схема) */
  const SLOTS = [];
  for (const x of G.SHOP.bays) SLOTS.push({ x, z: G.SHOP.bayZ, yaw: yawOf(0, -1) });
  for (const z of [-322, -309]) for (let x = -68; x <= 32; x += 14) SLOTS.push({ x, z, yaw: yawOf(0, 1) });
  const slotPos = (k, out) => {
    const s = SLOTS[k] || { x: -68 + 14 * ((k - SLOTS.length) % 8), z: -296 + 12 * Math.floor((k - SLOTS.length) / 8), yaw: yawOf(0, 1) };
    out.set(s.x, ctx.heightAt(s.x, s.z), s.z);
    return s.yaw;
  };
  /* место у дороги или забоя для бульдозера и станка */
  const nearRoad = (r, u, side, out, dir) => {
    const c = ctx.pathFor(r);
    if (!c) return false;
    c.getPoint(u, out); c.getTangent(u, dir); dir.y = 0; dir.normalize();
    out.x += -dir.z * side; out.z += dir.x * side; out.y = ctx.heightAt(out.x, out.z);
    return true;
  };

  function fresh(state) {
    const fids = AKT.ofType('face');
    wasteFaces = fids.filter(f => /вскрыш/i.test(String(AKT.pass(f, 'kind') || '')));
    oreFaces = fids.filter(f => !wasteFaces.includes(f));
    for (const r of ROADS) if (roads[r]) {
      const s = AKT.things[r] ? AKT.st(r) : 'OPEN';
      const closed = !!s && s !== 'OPEN';
      roads[r].closed = closed;
      if (roads[r].mesh) roads[r].mesh.visible = closed;
      const ri = ROADS.indexOf(r);
      for (let k = 0; k < 5; k++) barrierM.setMatrixAt(ri * 5 + k, closed && roads[r].barrier ? roads[r].barrier[k] : ZERO);
    }
    barrierM.instanceMatrix.needsUpdate = true;

    /* самосвалы */
    const ids = AKT.ofType('truck').slice(0, CAP);
    for (const id of ids) {
      const loc = nm(AKT.val(id, 'location'));
      if (AKT.st(id) === 'LOADING' && /^face-/.test(loc)) lastLineFace[AKT.pass(id, 'duty') && /вскрыш/i.test(String(AKT.pass(id, 'duty'))) ? 0 : lineOf(id)] = loc;
    }
    truckIds.length = 0;
    let wi = 0, down = 0;
    ids.forEach((id, i) => {
      let T = trucks.get(id);
      if (!T) {
        T = { id, frac: hash01(id), pos: new V3(), prevT: new V3(), off: new V3(), q: new THREE.Quaternion(), has: false, prevD: 0, tilt: 0, load: 0,
          top: new V3(), bed: new V3(), st: '', tpub: null, dpub: null, cycle: 0, x0: 0, face: '', d: 0, phase: '', p: 0, slot: 0, dumped: false };
        trucks.set(id, T);
      }
      T.i = i; truckIds[i] = id;
      T.model = String(AKT.pass(id, 'model') || ''); T.s = truckScale(T.model);
      T.payload = AKT.pass(id, 'payload_t') || 136;
      T.waste = /вскрыш/i.test(String(AKT.pass(id, 'duty') || AKT.val(id, 'duty') || ''));
      T.line = T.waste ? 0 : lineOf(id);
      const st = AKT.st(id), loc = nm(AKT.val(id, 'location'));
      const cycle = AKT.num(id, 'cycle_min') || AKT.pass(id, 'cycle_min') || 30;
      const tpub = AKT.num(id, 'sim_time') ?? AKT.simTime ?? 0;
      const faceList = T.waste ? wasteFaces : oreFaces;
      /* забой: где грузится сейчас (Ditto); иначе — забой своей линии, где грузятся её самосвалы (вся линия
         возит из одного забоя, как в модели); вскрышные — по очереди на забои вскрыши */
      if (st === 'LOADING' && /^face-/.test(loc) && AKT.things[loc]) T.face = loc;
      else if (!T.waste && lastLineFace[T.line] && T.phase !== 'HAUL_FULL' && T.phase !== 'QUEUE' && T.phase !== 'DUMP') T.face = lastLineFace[T.line];
      else if (!T.face || !faceList.includes(T.face)) T.face = T.waste ? (wasteFaces[wi % Math.max(1, wasteFaces.length)] || '') : (lastLineFace[T.line] || defaultLineFace(T.line));
      if (T.waste && st !== 'DOWN') wi++;
      T.road = T.waste ? 'road-dump' : `ramp-${T.line}`;
      if ((st === 'HAUL_FULL' || st === 'RETURN') && roads[loc]) T.road = loc;
      T.endKey = endOfRoad(T.road);
      T.idleQueue = st === 'QUEUE' && !((AKT.num(id, 'load_t') || 0) > 0);
      T.info = T.face && roads[T.road] ? haulOf(T.face, T.road) : null;
      T.down = st === 'DOWN' || !T.info || !PHASES.includes(st);
      T.shopSlot = T.down ? down++ : -1;
      if (st !== T.st || tpub !== T.dpub || cycle !== T.cycle) {
        const k = PHASES.indexOf(st), lens = phaseLens(cycle);
        /* a new reading from Ditto: when the truck, by the model clock, is already in the phase the reading names,
           it goes on from where it is (no restart of the cycle, no jump); otherwise it is put into that phase */
        let kept = false;
        if (k >= 0 && T.cycle === cycle && T.dpub != null && clock != null && T.tpub != null) {
          let x = (((T.x0 + (clock - T.tpub)) % cycle) + cycle) % cycle, j = 0;
          while (j < 4 && x >= lens[j]) { x -= lens[j]; j++; }
          if (j === k) { let s0 = 0; for (let m = 0; m < k; m++) s0 += lens[m]; T.x0 = s0 + x; T.tpub = clock; kept = true; }
        }
        T.st = st; T.dpub = tpub; T.cycle = cycle;
        if (!kept) {
          T.tpub = tpub;
          if (k >= 0) { let x = 0; for (let j = 0; j < k; j++) x += lens[j]; T.x0 = x + (0.12 + 0.76 * T.frac) * lens[k]; }
        }
      }
      T.loadC = T.waste ? WASTE_C : ORE_C;
      truckLoadM.setColorAt(i, T.loadC);
      if (!truckLabels.has(id)) {
        truckLabels.add(id);
        lbl(id, () => devText(id), { thing: id, prio: 6, kind: 'small', maxDist: 1700, at: () => T.top,
          title: () => `${AKT.nameRu(id)}: ${AKT.stOf(id)} · груз ${AKT.fmt(AKT.num(id, 'load_t'))} т · паспорт ${AKT.fmt(T.payload)} т (Ditto)` });
      }
    });
    truckBodyM.count = truckBedM.count = truckLoadM.count = ids.length;
    if (truckLoadM.instanceColor) truckLoadM.instanceColor.needsUpdate = true;

    /* экскаваторы: место у забоя рассчитано так, чтобы ковш доставал до кузова */
    for (const id of AKT.ofType('exc')) if (!excs.some(x => x.id === id)) makeExc(id, excs.length);
    for (const e of excs) {
      e.st = AKT.st(e.id); e.tph = AKT.num(e.id, 'tph');
      e.face = layout.excFace(e.id) || '';
      e.waste = !!e.face && /вскрыш/i.test(String(AKT.pass(e.face, 'kind') || ''));
      const fi = e.face ? faceSpot(e.face) : null;
      const key = fi ? fi.key + e.face : 'none';
      if (e.placed !== key) {
        e.placed = key;
        if (fi) {
          const bed = tv1.copy(fi.pos).addScaledVector(fi.out, -LOAD_OFF).addScaledVector(fi.t0, G.TRUCK.bed[0]);
          const w = tv2.copy(fi.out).multiplyScalar(0.35).addScaledVector(fi.t0, -0.94).normalize();
          e.E.copy(bed).addScaledVector(w, e.reach); e.E.y = fi.y;
          const dig = tv2.copy(fi.out).multiplyScalar(0.5).addScaledVector(fi.t0, -0.87).normalize();
          e.digYaw = yawOf(dig.x, dig.z);
          e.t0.copy(fi.t0); e.out.copy(fi.out);
          e.pile = { p: e.E.clone().addScaledVector(dig, 10.5 * e.md.s), yaw: yawOf(fi.t0.x, fi.t0.z) };
          e.pile.p.y = fi.y;
        } else {
          e.E.set(PIT.cx + 12 * e.k, levelY(PIT.levels), PIT.cz + 8 * e.k); e.digYaw = 0; e.pile = null;
        }
        e.yaw = e.digYaw;
        e.g.position.copy(e.E); e.lower.rotation.y = e.digYaw;
      }
    }
    /* забои: развал у экскаватора, цвет — Cu и крепость (оценка блочной модели) */
    faceIds.length = 0;
    fids.slice(0, 12).forEach((fid, i) => {
      faceIds[i] = fid;
      let F = faces.get(fid);
      if (!F) { F = { id: fid, p: new V3(), yaw: 0, base: new THREE.Color(), top: new V3() }; faces.set(fid, F); lbl(fid, () => devText(fid) ? `${AKT.nameRu(fid)} · ${AKT.stOf(fid)}` : '', { thing: fid, prio: 6, kind: 'small', at: () => F.top, title: () => faceTitle(fid) }); }
      const e = excs.find(x => x.face === fid);
      const fi = faceSpot(fid);
      F.ok = true;
      if (e && e.pile) { F.p.copy(e.pile.p); F.yaw = e.pile.yaw; }
      else if (fi) { F.p.copy(fi.f.wall).addScaledVector(fi.out, -4); F.yaw = yawOf(fi.t0.x, fi.t0.z); }
      else F.ok = false;
      const bl = AKT.num(fid, 'blasted_t');
      F.size = clamp(Math.cbrt(Math.max(0, bl == null ? 60000 : bl) / 100000), 0.45, 1.4);
      faceColor(fid, F.base);
      F.top.copy(F.p); F.top.y += 6 * F.size + 2;
    });
    pileM.count = faceIds.length;
    let k = 0;
    for (const fid of faceIds) {
      const F = faces.get(fid);
      tq.setFromAxisAngle(UP, F.yaw);
      tm.compose(F.p, tq, ts.set(9 * F.size, 4.2 * F.size, 4.6 * F.size));
      pileM.setMatrixAt(k++, F.ok ? tm : ZERO);
    }
    pileM.instanceMatrix.needsUpdate = true;

    /* буровые станки: верхний уступ над забоем, по ходу отработки; бульдозеры — у места из Ditto */
    drillIds.length = 0; dozerIds.length = 0;
    const perFace = {};
    let shopK = down;
    AKT.ofType('drill').slice(0, 16).forEach((id, i) => {
      drillIds[i] = id;
      let D = drills.get(id);
      if (!D) {
        D = { id, p: new V3(), dir: new V3(1, 0, 0), mast: 0, ph: hash01(id) * 6, top: new V3(), placed: '', paint: new THREE.Color(C.drill) };
        drills.set(id, D);
        lbl(id, () => devText(id), { thing: id, prio: 7, kind: 'small', at: () => D.top });
      }
      D.st = AKT.st(id); D.s = drillScale(String(AKT.pass(id, 'model') || ''));
      const fid = nm(AKT.val(id, 'location') || AKT.pass(id, 'face'));
      const kk = perFace[fid] = (perFace[fid] || 0) + 1;
      const key = fid + ':' + kk + ':' + (faceInfo.get(fid) || {}).key;
      if (D.placed !== key) { D.placed = key; if (!drillSpot(fid, kk - 1, D)) { D.yaw = slotPos(shopK++, D.p); D.dir.set(Math.cos(D.yaw), 0, -Math.sin(D.yaw)); } }
    });
    AKT.ofType('dozer').slice(0, 16).forEach((id, i) => {
      dozerIds[i] = id;
      let Z = dozers.get(id);
      const model = String(AKT.pass(id, 'model') || '');
      if (!Z) {
        Z = { id, p: new V3(), dir: new V3(1, 0, 0), ph: hash01(id) * 6, top: new V3(), placed: '', paint: new THREE.Color(/komatsu/i.test(model) ? C.komatsu : C.cat) };
        dozers.set(id, Z);
        lbl(id, () => devText(id), { thing: id, prio: 7, kind: 'small', at: () => Z.top });
      }
      Z.st = AKT.st(id);
      Z.s = dozerScale(model);
      const loc = nm(AKT.val(id, 'location') || AKT.pass(id, 'place'));
      const key = loc + ':' + i + ':' + ((faceInfo.get(loc) || {}).key || '');
      if (Z.placed !== key) { Z.placed = key; if (!dozerSpot(loc, i, Z)) { const yaw = slotPos(shopK++, Z.p); Z.dir.set(Math.cos(yaw), 0, -Math.sin(yaw)); } }
    });
    drillBodyM.count = drillMastM.count = drillIds.length;
    dozerM.count = dozerIds.length;
    recolor();
  }

  const faceColor = (fid, out) => {
    const cu = AKT.num(fid, 'est_cu'), kind = String(AKT.pass(fid, 'kind') || '');
    if (/вскрыш/i.test(kind) || cu == null) out.setHex(C.waste);
    else out.setHex(0x8f8b85).lerp(tc1.setHex(0x3e8c72), clamp((cu - 0.2) / 0.4, 0, 1));
    const hard = String(AKT.val(fid, 'hardness') || ''), axb = AKT.num(fid, 'est_axb');
    const k = /тв[её]рд/i.test(hard) || (axb != null && axb < 30) ? 0.74 : /мягк/i.test(hard) || (axb != null && axb >= 38) ? 1.1 : 1;
    out.multiplyScalar(k); out.r = Math.min(1, out.r); out.g = Math.min(1, out.g); out.b = Math.min(1, out.b);
    return out;
  };
  const faceTitle = fid => {
    const cu = AKT.num(fid, 'est_cu'), hard = AKT.val(fid, 'hardness'), bl = AKT.num(fid, 'blasted_t');
    return `${AKT.nameRu(fid)}: ${AKT.stOf(fid)}${cu != null ? ` · Cu ${AKT.f2(cu)} % — оценка блочной модели` : ''}${hard ? ` · крепость: ${hard}` : ''}${bl != null ? ` · взорвано ${AKT.fmt(bl)} т` : ''} (Ditto)`;
  };
  const passesFor = (e, payload) => Math.max(1, Math.ceil(payload / (e.md.m3 * RHO)));
  const excTitle = e => {
    const per = {};
    for (const T of trucks.values()) if (!per[T.model] && T.model) per[T.model] = T.payload;
    const pass = Object.keys(per).sort().map(m => `${m} — ${passesFor(e, per[m])}`).join(', ');
    return `${AKT.nameRu(e.id)} — ${e.md.text} · ${AKT.stOf(e.id)} ${AKT.fmt(e.tph)} т/ч (Ditto)${e.face ? ' · ' + AKT.nameRu(e.face) : ''}`
      + (pass ? ` · ковшей на самосвал: ${pass} — оценка: грузоподъёмность из паспорта / ковш ${AKT.fmt(e.md.m3)} м³ (данные производителя, не проверены) × ${AKT.f1(RHO)} т/м³ [допущение]` : '');
  };
  function drillSpot(fid, k, D) {
    const fi = faceInfo.get(fid) || faceSpot(fid);
    if (!fi) return false;
    const f = fi.f, Ld = Math.max(0, f.level - 1), s = Ld > 0 ? crestS(Ld) + PIT.berm * 0.4 : 1.05, yL = levelY(Ld);
    const sgn = Math.sign(fi.t0.x * f.tangent.x + fi.t0.z * f.tangent.z) || 1;
    for (let t = 0; t < 10; t++) {
      const dist = 20 + 19 * k + 13 * t, th = f.angle - sgn * dist / (pitR(f.angle) * s), R = pitR(th);
      const x = PIT.cx + s * R * Math.cos(th), z = PIT.cz + s * R * Math.sin(th), y = ctx.heightAt(x, z);
      if (Ld === 0 || Math.abs(y - yL) < 0.8) {
        D.p.set(x, y, z); D.dir.set(Math.sin(th) * sgn, 0, -Math.cos(th) * sgn); D.yaw = yawOf(D.dir.x, D.dir.z);
        return true;
      }
    }
    return false;
  }
  function dozerSpot(loc, i, Z) {
    if (/^face-/.test(loc)) {
      const fi = faceSpot(loc);
      if (!fi) return false;
      for (let t = 0; t < 8; t++) {
        const p = tv1.copy(fi.pos).addScaledVector(fi.out, -3.5).addScaledVector(fi.t0, -(36 + 10 * t));
        const y = ctx.heightAt(p.x, p.z);
        if (Math.abs(y - fi.y) < 0.8) { Z.p.set(p.x, y, p.z); Z.dir.copy(fi.t0).negate(); return true; }
      }
      return false;
    }
    if (loc === 'road-dump' && roads[loc]) {
      const R = roads[loc], c = R.curve, end = c.points[c.points.length - 1];
      c.getTangent(1, Z.dir); Z.dir.y = 0; Z.dir.normalize();
      Z.p.copy(end).addScaledVector(Z.dir, 8); Z.p.x += -Z.dir.z * 14; Z.p.z += Z.dir.x * 14; Z.p.y = ctx.heightAt(Z.p.x, Z.p.z);
      return true;
    }
    if (roads[loc] || ctx.pathFor(loc)) return nearRoad(loc, 0.45 + 0.1 * (i % 3), 11, Z.p, Z.dir);
    const p = loc ? layout.pos(loc) : null;
    if (!p) return false;
    Z.p.copy(p).add(tv1.set(14, 0, 10)); Z.p.y = ctx.heightAt(Z.p.x, Z.p.z);
    return true;
  }

  /* цвета экземпляров: окраска и свечение (после опроса; беда пульсирует каждый кадр) */
  let anyPulse = false;
  function recolor() {
    anyPulse = false;
    const chk = id => { if (ctx.glowOf(id) === 'issue') anyPulse = true; };
    truckIds.forEach((id, i) => { chk(id); tint(id, WHITE, tc1); truckBodyM.setColorAt(i, tc1); truckBedM.setColorAt(i, tc1); });
    drillIds.forEach((id, i) => { chk(id); const D = drills.get(id); tint(id, D.paint, tc1); drillBodyM.setColorAt(i, tc1); drillMastM.setColorAt(i, tc1); });
    dozerIds.forEach((id, i) => { chk(id); const Z = dozers.get(id); tint(id, Z.paint, tc1); dozerM.setColorAt(i, tc1); });
    faceIds.forEach((id, i) => { chk(id); tint(id, faces.get(id).base, tc1); pileM.setColorAt(i, tc1); });
    for (const m of [truckBodyM, truckBedM, drillBodyM, drillMastM, dozerM, pileM]) if (m.instanceColor) m.instanceColor.needsUpdate = true;
  }

  /* ------------------------------------------------------------- temporaries */
  const UP = new V3(0, 1, 0);
  const tv1 = new V3(), tv2 = new V3(), tv3 = new V3(), P = new V3(), Tg = new V3(), F = new V3(), Rr = new V3(), Uu = new V3();
  const tm = new THREE.Matrix4(), tm2 = new THREE.Matrix4(), tm3 = new THREE.Matrix4(), basis = new THREE.Matrix4();
  const tq = new THREE.Quaternion(), qT = new THREE.Quaternion(), ts = new V3(), tc1 = new THREE.Color();
  const hingeT = new THREE.Matrix4().makeTranslation(G.TRUCK.hinge[0], G.TRUCK.hinge[1], 0);
  const hingeI = new THREE.Matrix4().makeTranslation(-G.TRUCK.hinge[0], -G.TRUCK.hinge[1], 0);
  const bedC = new THREE.Matrix4().makeTranslation(G.TRUCK.bed[0], G.TRUCK.bed[1], 0);
  const groups = new Map();
  const grp = k => { let a = groups.get(k); if (!a) { a = []; groups.set(k, a); } return a; };
  const faceLoad = new Map();

  /* ориентация по направлению движения (с уклоном) */
  const orient = (fwd, q) => {
    F.copy(fwd); F.y = clamp(F.y, -0.3, 0.3); F.normalize();
    Rr.crossVectors(F, UP).normalize(); Uu.crossVectors(Rr, F);
    basis.makeBasis(F, Uu, Rr);
    return q.setFromRotationMatrix(basis);
  };

  /* Часы движения машин, мин модели: идут со скоростью модели (simRate) и мягко подтягиваются к state.simNow.
     Ядро продлевает время модели не дальше 2,5 с после опроса; при медленном ответе Ditto машины шли бы
     рывками, поэтому часы идут дальше сами (не дольше 15 с после удачного опроса), а новый опрос догоняется плавно. */
  let clock = null;
  function tick(state, dt) {
    const target = state.simNow;
    if (target == null) return clock;
    if (clock == null || Math.abs(target - clock) > 30) { clock = target; return clock; }
    const since = AKT.polled ? Date.now() / 1000 - AKT.polled : 0;
    if (!state.paused && since < 15) clock += dt * state.simRate;
    const err = target - clock;
    if (err > 0 || since < 2.5 || state.paused) clock += err * (1 - Math.exp(-2.5 * dt));
    return clock;
  }

  function frameTrucks(state, dt) {
    const now = tick(state, dt);
    for (const a of groups.values()) a.length = 0;
    faceLoad.clear();
    /* 1. фаза цикла */
    for (const id of truckIds) {
      const T = trucks.get(id);
      if (T.down) { T.phase = 'DOWN'; continue; }
      if (T.idleQueue) { T.phase = 'QUEUE'; T.p = 1; }
      else {
        const lens = phaseLens(T.cycle);
        let x = T.x0 + ((now == null ? T.tpub : now) - T.tpub);
        x = ((x % T.cycle) + T.cycle) % T.cycle;
        let k = 0; while (k < 4 && x >= lens[k]) { x -= lens[k]; k++; }
        T.phase = PHASES[k]; T.p = clamp(x / lens[k], 0, 1);
      }
      const L = T.info.Lh;
      if (T.phase === 'LOADING') { T.d = 0; T.dir = 1; grp('f:' + T.face).push(T); }
      else if (T.phase === 'HAUL_FULL') { T.d = (L - QLEN) * smooth(T.p); T.dir = 1; if (L - T.d < QLEN + 70) grp('e:' + T.endKey).push(T); }
      else if (T.phase === 'QUEUE') { T.d = L - QLEN * (1 - T.p); T.dir = 1; grp('e:' + T.endKey).push(T); }
      else if (T.phase === 'DUMP') { T.d = L; T.dir = 1; grp('d:' + T.endKey).push(T); }
      else { T.d = L * (1 - smooth(T.p)); T.dir = -1; if (T.d < 80) grp('f:' + T.face).push(T); }
      T.slot = 0;
    }
    /* 2. очередь у разгрузки и у забоя: не наезжать друг на друга */
    for (const [k, a] of groups) {
      if (!a.length) continue;
      if (k[0] === 'e') {
        const dumping = (groups.get('d:' + k.slice(2)) || []).length > 0;
        for (const T of a) T.e = T.info.Lh - T.d;
        a.sort((x, y) => x.e - y.e);
        let prev = dumping ? GAP * 0.6 - GAP : -GAP;
        for (const T of a) { T.e = Math.max(T.e, prev + GAP); prev = T.e; T.d = T.info.Lh - T.e; }
      } else if (k[0] === 'd') {
        a.sort((x, y) => y.p - x.p);
        a.forEach((T, i) => { T.slot = i; });
      } else {
        a.sort((x, y) => (x.phase === 'LOADING' ? -1 : 1) - (y.phase === 'LOADING' ? -1 : 1) || (x.phase === 'LOADING' ? y.p - x.p : x.d - y.d));
        let prev = -GAP;
        a.forEach((T, i) => {
          T.slot = i;
          if (i > 0 && T.phase === 'LOADING') T.dir = -1;
          T.d = Math.max(T.d, prev + GAP); prev = T.d;
        });
        if (a[0].phase === 'LOADING') faceLoad.set(a[0].face, a[0]);
      }
    }
    /* 3. место, поворот, кузов, груз */
    const fast = state.simRate > 300;
    const kq = 1 - Math.exp(-9 * dt), ko = Math.exp(-7 * dt), kt = 1 - Math.exp(-10 * dt);
    let mi = 0;
    for (const id of truckIds) {
      const T = trucks.get(id), i = T.i;
      let tilt = 0, load = 0;
      if (T.phase === 'DOWN') {
        const yaw = slotPos(T.shopSlot, P);
        F.set(Math.cos(yaw), 0, -Math.sin(yaw));
      } else if (T.phase === 'DUMP') {
        const away = dumpPose(T, T.slot, P);
        F.copy(away);
        const p = T.p;
        tilt = p < 0.25 ? 0 : p < 0.55 ? 0.9 * smooth((p - 0.25) / 0.3) : p < 0.8 ? 0.9 : 0.9 * (1 - smooth((p - 0.8) / 0.2));
        load = p < 0.4 ? 1 : 1 - smooth((p - 0.4) / 0.3);
        if (p > 0.42 && !T.dumped && !state.paused) {
          T.dumped = true;
          if (T.endKey !== 'dump') { const pl = plants.find(x => `crusher-${x.n}` === T.endKey); if (pl) puff(pl.hopper.x, pl.hopper.y + 2, pl.hopper.z, 5.5, 1.6); }
          else puff(P.x + F.x * 9, P.y + 1.5, P.z + F.z * 9, 6, 1.6);
        }
      } else {
        const I = T.info, H = I.H, u = clamp(T.d / I.Lh, 0, 1);
        H.getPoint(u, P); H.getTangent(u, Tg);
        let rx = -Tg.z, rz = Tg.x; const rl = Math.hypot(rx, rz) || 1; rx /= rl; rz /= rl;
        const lane = T.dir > 0 ? LANE : -LANE;
        const w = (T.phase === 'LOADING' && T.slot === 0) ? 0 : smooth(T.d / 20);
        const fi = faceInfo.get(T.face);
        const lox = fi ? -fi.out.x * LOAD_OFF : rx * lane, loz = fi ? -fi.out.z * LOAD_OFF : rz * lane;
        P.x += rx * lane * w + lox * (1 - w); P.z += rz * lane * w + loz * (1 - w);
        /* кривые pit.js подняты: над лентой дороги на 0,3, над бермой забоя на 0,8 */
        P.y -= fi && T.d < fi.spurLen ? 0.3 + 0.5 * smooth((fi.spurLen - T.d) / 12) : 0.3;
        F.copy(Tg).multiplyScalar(T.dir);
        if (T.phase === 'HAUL_FULL' || (T.phase === 'QUEUE' && !T.idleQueue)) load = 1;
        if (T.phase === 'LOADING' && T.slot === 0) {
          const e = excs.find(x => x.face === T.face);
          const n = e ? passesFor(e, T.payload) : 1;
          T.nVis = clamp(Math.floor((LOAD_MIN / Math.max(1e-6, state.simRate)) / 0.42), 1, n);
          load = Math.min(1, Math.floor(T.p * T.nVis + 0.35) / T.nVis);
        }
        if (T.phase !== 'DUMP') T.dumped = false;
      }
      orient(F, qT);
      /* разрывы пути (смена дороги, место разгрузки, очередь) — плавно; далёкий скачок — сразу */
      if (!T.has || fast) { T.has = true; T.off.set(0, 0, 0); T.pos.copy(P); T.q.copy(qT); }
      else {
        const jump = P.distanceTo(T.prevT), expect = Math.abs(T.d - T.prevD) + 1.5;
        if (jump > 160) { T.off.set(0, 0, 0); T.q.copy(qT); }
        else if (jump > expect + 1.5) T.off.copy(T.pos).sub(P);
        T.off.multiplyScalar(ko);
        T.pos.copy(P).add(T.off);
        T.q.slerp(qT, kq);
      }
      T.prevT.copy(P); T.prevD = T.d;
      T.tilt += (tilt - T.tilt) * kt;
      T.load += (load - T.load) * (load > T.load ? 1 - Math.exp(-14 * dt) : kt);
      /* матрицы */
      tm.compose(T.pos, T.q, ts.setScalar(T.s));
      truckBodyM.setMatrixAt(i, tm);
      tm2.multiplyMatrices(tm, hingeT).multiply(tm3.makeRotationZ(T.tilt)).multiply(hingeI);
      truckBedM.setMatrixAt(i, tm2);
      if (T.load > 0.03) {
        const f = T.load, k = 0.7 + 0.3 * f;
        tm3.makeScale(4.3 * k, 2.7 * f, 3.05 * k);
        tm2.multiply(bedC).multiply(tm3);
        truckLoadM.setMatrixAt(i, tm2);
      } else truckLoadM.setMatrixAt(i, ZERO);
      tq.setFromAxisAngle(UP, Math.atan2(-F.z, F.x));
      tv1.set(T.pos.x, T.pos.y + 0.35, T.pos.z);
      blobM.setMatrixAt(mi++, tm.compose(tv1, tq, ts.set(G.TRUCK.L * T.s * 1.05, 1, G.TRUCK.W * T.s * 1.35)));
      T.top.copy(T.pos); T.top.y += G.TRUCK.top * T.s;
      T.bed.set(G.TRUCK.bed[0] * T.s, (G.TRUCK.bed[1] + 1.2) * T.s, 0).applyQuaternion(T.q).add(T.pos);
    }
    truckBodyM.instanceMatrix.needsUpdate = true; truckBedM.instanceMatrix.needsUpdate = true; truckLoadM.instanceMatrix.needsUpdate = true;
    return mi;
  }

  function frameExcavators(state, dt, mi) {
    let li = 0;
    const run = !state.paused;
    for (const e of excs) {
      const R = e.rig;
      pose.yaw = e.digYaw; pose.a = R.rest; pose.loaded = false;
      const T = faceLoad.get(e.face);
      if (e.st === 'DIG' && T && T.phase === 'LOADING') {
        const n = T.nVis || 1, pp = T.p * n;
        let k = Math.floor(pp), q = pp - k;
        if (k >= n) { k = n - 1; q = 0.999; }
        cyclePose(e, q, yawOf(T.bed.x - e.E.x, T.bed.z - e.E.z));
        if (q > 0.6 && q < 0.7 && run && (e.passT !== T || e.passK !== k)) { e.passT = T; e.passK = k; puff(T.bed.x, T.bed.y + 2.5, T.bed.z, 2.6, 0.9); }
      } else if (e.st === 'DIG') {
        if (run) e.idleT += dt;
        cyclePose(e, (e.idleT / 3.6) % 1, e.digYaw + 0.75);
      }
      if (e.st === 'MOVE') { if (run) e.moveT += dt; e.g.position.copy(e.E).addScaledVector(e.t0, -3 * Math.sin(e.moveT * 0.5)); }
      else e.g.position.copy(e.E);
      e.yaw = angLerp(e.yaw, pose.yaw, 1 - Math.exp(-14 * dt));
      e.alpha += (pose.a - e.alpha) * (1 - Math.exp(-14 * dt));
      e.upper.rotation.y = e.yaw; e.arm.rotation.z = e.alpha;
      e.g.updateMatrixWorld(true);
      if (pose.loaded) {
        e.arm.localToWorld(tv1.set(R.bucket[0], R.bucket[1] + 0.9, 0));
        tm.compose(tv1, tq.identity(), ts.set(1.7, 1.0, 1.9).multiplyScalar(e.md.s));
        lumpM.setMatrixAt(li, tm); lumpM.setColorAt(li, e.waste ? WASTE_C : ORE_C);
        li++;
      }
      e.top.copy(e.E); e.top.y += 14 * e.md.s;
      tq.setFromAxisAngle(UP, e.digYaw);
      blobM.setMatrixAt(mi++, tm.compose(tv1.set(e.g.position.x, e.E.y + 0.3, e.g.position.z), tq, ts.set(14 * e.md.s, 1, 11 * e.md.s)));
    }
    lumpM.count = li;
    lumpM.instanceMatrix.needsUpdate = true;
    if (lumpM.instanceColor) lumpM.instanceColor.needsUpdate = true;
    return mi;
  }
  /* один ход ковша: копание → поворот к кузову → разгрузка → обратно; q ∈ [0, 1); итог — в pose */
  const pose = { yaw: 0, a: 0, loaded: false };
  function cyclePose(e, q, dumpYaw) {
    const R = e.rig, dg = e.digYaw;
    if (q < 0.35) { pose.yaw = dg; pose.a = R.dig0 + (R.dig1 - R.dig0) * smooth(q / 0.35); pose.loaded = q > 0.24; return; }
    if (q < 0.6) { const t = smooth((q - 0.35) / 0.25); pose.yaw = angLerp(dg, dumpYaw, t); pose.a = R.dig1 + (e.dumpA - R.dig1) * t; pose.loaded = true; return; }
    if (q < 0.72) { pose.yaw = dumpYaw; pose.a = e.dumpA + 0.08 * Math.sin((q - 0.6) / 0.12 * Math.PI); pose.loaded = q < 0.64; return; }
    const t = smooth((q - 0.72) / 0.28);
    pose.yaw = angLerp(dumpYaw, dg, t); pose.a = e.dumpA + (R.dig0 - e.dumpA) * t; pose.loaded = false;
  }

  function frameSmall(state, dt, mi) {
    const run = !state.paused;
    drillIds.forEach((id, i) => {
      const D = drills.get(id);
      if (run && D.st !== 'DOWN' && D.st !== 'IDLE') D.ph += dt;
      const mast = D.st === 'DOWN' ? 1.45 : 0;
      D.mast += (mast - D.mast) * (1 - Math.exp(-3 * dt));
      tv1.copy(D.p);
      if (D.st === 'MOVING') tv1.addScaledVector(D.dir, 2.5 * Math.sin(D.ph * 0.7));
      if (D.st === 'DRILLING') {
        tv1.y += 0.06 * Math.sin(D.ph * 40);
        if (run && D.ph - (D.puffAt || 0) > 0.55) { D.puffAt = D.ph; tv2.set(G.DRILL.mast[0], 0, G.DRILL.mast[2]).multiplyScalar(D.s).applyAxisAngle(UP, D.yaw).add(D.p); puff(tv2.x, tv2.y + 0.8, tv2.z, 2.2, 1.1); }
      }
      tq.setFromAxisAngle(UP, D.yaw);
      tm.compose(tv1, tq, ts.setScalar(D.s));
      drillBodyM.setMatrixAt(i, tm);
      tm2.copy(tm).multiply(tm3.makeTranslation(G.DRILL.mast[0], G.DRILL.mast[1], G.DRILL.mast[2])).multiply(tm3.makeRotationZ(D.mast));
      drillMastM.setMatrixAt(i, tm2);
      D.top.copy(D.p); D.top.y += (D.mast > 0.7 ? 7 : G.DRILL.top) * D.s;
      blobM.setMatrixAt(mi++, tm.compose(tv2.set(tv1.x, D.p.y + 0.3, tv1.z), tq, ts.set(12 * D.s, 1, 7.5 * D.s)));
    });
    dozerIds.forEach((id, i) => {
      const Z = dozers.get(id);
      if (run && Z.st === 'WORK') Z.ph += dt;
      tv1.copy(Z.p);
      if (Z.st === 'WORK') { tv1.addScaledVector(Z.dir, 4.5 * Math.sin(Z.ph * 0.9)); tv1.y = ctx.heightAt(tv1.x, tv1.z); }
      tq.setFromAxisAngle(UP, yawOf(Z.dir.x, Z.dir.z));
      dozerM.setMatrixAt(i, tm.compose(tv1, tq, ts.setScalar(Z.s)));
      Z.top.copy(tv1); Z.top.y += 6 * Z.s;
      blobM.setMatrixAt(mi++, tm.compose(tv2.set(tv1.x, tv1.y + 0.3, tv1.z), tq, ts.set(9.5 * Z.s, 1, 7 * Z.s)));
    });
    drillBodyM.instanceMatrix.needsUpdate = true; drillMastM.instanceMatrix.needsUpdate = true; dozerM.instanceMatrix.needsUpdate = true;
    return mi;
  }

  const LAMP = { run: new THREE.Color(GC.run), warn: new THREE.Color(GC.warn), alarm: new THREE.Color(GC.alarm), off: new THREE.Color(0x50555c) };
  const lampOf = id => { if (!AKT.things[id]) return LAMP.off; const s = AKT.st(id); return AKT.stopped(s) ? LAMP.alarm : (s === 'RUN' || s === 'OK' || s === 'NORMAL') ? LAMP.run : LAMP.warn; };
  function framePlants(state, dt) {
    const run = !state.paused;
    plants.forEach((p, i) => {
      const cid = `crusher-${p.n}`, kid = `conveyor-${p.n}`, sid = `stockpile-${p.n}`;
      if (state.fresh) {
        const tph = AKT.num(cid, 'tph') || 0, s = AKT.st(cid);
        p.run = tph > 1 && !AKT.stopped(s);
        const ktph = AKT.num(kid, 'tph') || 0, cap = AKT.pass(kid, 'capacity_tph') || 4880;
        p.speed = AKT.stopped(AKT.st(kid)) ? 0 : clamp(ktph / cap, 0, 1.3);
        const lvl = AKT.num(sid, 'level_t'), live = AKT.pass(sid, 'live_t') || 40000;
        p.coneT = lvl == null ? 0.5 : Math.max(0.08, Math.cbrt(clamp(lvl / live, 0, 1.3)));
        lampM.setColorAt(i * 3, lampOf(cid)); lampM.setColorAt(i * 3 + 1, lampOf(kid)); lampM.setColorAt(i * 3 + 2, lampOf(`weigher-${p.n}`));
        if (lampM.instanceColor) lampM.instanceColor.needsUpdate = true;
      }
      if (run && p.run) p.mantleA += dt * 7;
      tq.setFromAxisAngle(UP, p.mantleA);
      tm.makeRotationX(p.run ? 0.07 : 0); tm2.makeRotationFromQuaternion(tq).multiply(tm);
      tm2.setPosition(p.hopper.x, p.hopper.y + 0.15, p.hopper.z);
      mantleM.setMatrixAt(i, tm2);
      if (run) p.tex.offset.x = (p.tex.offset.x - dt * 0.9 * p.speed) % 1;
      p.coneS += (p.coneT - p.coneS) * (1 - Math.exp(-2 * dt));
      p.cone.scale.setScalar(p.coneS);
      p.labelAt.set(p.sp.x, p.sy + 52 * p.coneS + 5, p.sp.z);
      const topY = p.sy + 52 * p.coneS, drop = p.yb - 0.6 - topY;
      streamM.setMatrixAt(i, p.speed > 0.01 && drop > 0.5 ? tm.compose(tv1.set(p.xb + 1.2, p.yb - 0.6, p.z), tq.identity(), ts.set(1, drop, 1)) : ZERO);
      const blink = state.paused ? 1 : 0.85 + 0.15 * Math.sin(state.t * 5 + i);
      lampM.setMatrixAt(i * 3, tm.compose(p.lampAt, tq.identity(), ts.setScalar(1.1 * blink)));
      lampM.setMatrixAt(i * 3 + 1, tm.compose(tv1.set(p.xb + 0.4, p.yb + 2.5, p.z + 3.4), tq, ts.setScalar(0.9)));
      lampM.setMatrixAt(i * 3 + 2, tm.compose(tv1.set(p.wx, p.wy + 3.9, p.z), tq, ts.setScalar(0.7)));
    });
    mantleM.instanceMatrix.needsUpdate = true; streamM.instanceMatrix.needsUpdate = true; lampM.instanceMatrix.needsUpdate = true;
  }

  function frameDust(dt) {
    for (let i = 0; i < DUST_N; i++) {
      const d = dust[i];
      if (d.t >= d.life) { if (d.t < 8) { d.t = 9; dustM.setMatrixAt(i, ZERO); } continue; }
      d.t += dt;
      const k = d.t / d.life, s = d.size * (0.5 + 0.9 * k) * (1 - k * k);
      tv1.copy(d.p); tv1.y += 2.5 * k;
      dustM.setMatrixAt(i, s > 0.05 ? tm.compose(tv1, tq.identity(), ts.set(s, s * 0.7, s)) : ZERO);
    }
    dustM.instanceMatrix.needsUpdate = true;
  }

  /* ?perf=1: проверка из консоли — самосвалы, экскаваторы, сцена */
  if (AKT.params.get('perf') === '1') window.__dioMining = { THREE, trucks, excs, drills, dozers, faces, scene, camera: ctx.camera, heightAt: ctx.heightAt };

  return {
    update(state, dt) {
      if (state.fresh) fresh(state);
      if (anyPulse) { pulse = 0.5 + 0.5 * Math.sin(state.t * 4.2); recolor(); }
      let mi = frameTrucks(state, dt);
      mi = frameExcavators(state, dt, mi);
      mi = frameSmall(state, dt, mi);
      blobM.count = mi;
      blobM.instanceMatrix.needsUpdate = true;
      framePlants(state, dt);
      frameDust(dt);
    },
    destroy() { scene.remove(root); if (window.__dioMining) delete window.__dioMining; },
  };
}
