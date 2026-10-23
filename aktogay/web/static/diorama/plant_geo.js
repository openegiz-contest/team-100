/* «Диорама», модуль «фабрика»: общие заготовки для plant.js, plant_feed.js, plant_ship.js.
   Части для ctx.merge (коробки, цилиндры, балки, стены-клинья разреза), барабаны мельниц
   с полосами футеровки (вращение видно), ленты конвейеров, общие пулы на весь модуль —
   по одному вызову отрисовки на пул: ленты (одна склейка, бег руды — сдвиг u у каждой ленты
   ∝ т/ч), вращающиеся части (барабаны, валки, гребки — экземпляры), трубы, лампы, кольца
   приводов, струи руды, неподвижная мелочь (эстакады лент, ж/д путь). Свет неподвижных
   частей запечён (ctx.bake). Схема, не масштаб. */

/* оформление линий: линия 2 — оборудование FLSmidth (факт, паспорт line-2 в Ditto),
   отличается цветом: голубые корпуса, синяя отделка, кольцевые приводы мельниц */
export const STYLE = {
  1: { wall: 0xddd7cb, trim: 0x59606a, roof: 0xa3a9ae, floor: 0xd6d2ca, glass: 0x9cc2d8, shell: 0xc5cacf, head: 0xaeb4ba,
    equip: 0x8d949c, accent: 0x6b737c, cell: 0xb4bbc1, launder: 0x7f878f, crane: 0xf2b500 },
  2: { wall: 0xe4eaf0, trim: 0x2d5f8f, roof: 0x93a5b6, floor: 0xd3d6d6, glass: 0x9cc2d8, shell: 0x6f95ba, head: 0x4f7397,
    equip: 0x6f8fae, accent: 0x2d5f8f, cell: 0x7d9fbf, launder: 0x46698c, crane: 0xf2b500 },
};
export const NB = ' ';

export function kit(ctx) {
  const { THREE } = ctx;
  const V = (x, y, z) => new THREE.Vector3(x, y, z);
  const UP = V(0, 1, 0);
  const soft = !!ctx.soft;
  const SEG = soft ? 14 : 18;

  /* ---------------------------------------------------------------- части */
  const part = (geometry, color, position, rotation) => ({ geometry, color, position, rotation });
  /* коробка w × h × d, основание на высоте y */
  const box = (w, h, d, x, y, z, color, ry) => part(new THREE.BoxGeometry(w, h, d), color, [x, y + h / 2, z], ry ? [0, ry, 0] : null);
  /* вертикальный цилиндр (усечённый конус при rTop), основание на y */
  const cyl = (r, h, x, y, z, color, seg, rTop) => part(new THREE.CylinderGeometry(rTop == null ? r : rTop, r, h, seg || SEG, 1), color, [x, y + h / 2, z]);
  /* цилиндр вдоль x, центр (x, y, z): радиус r у конца −x, rEnd у конца +x */
  const cylX = (r, len, x, y, z, color, seg, rEnd) => part(new THREE.CylinderGeometry(rEnd == null ? r : rEnd, r, len, seg || SEG, 1), color, [x, y, z], [0, 0, -Math.PI / 2]);
  /* цилиндр вдоль z, центр (x, y, z): радиус r у конца −z, rEnd у конца +z */
  const cylZ = (r, len, x, y, z, color, seg, rEnd) => part(new THREE.CylinderGeometry(rEnd == null ? r : rEnd, r, len, seg || SEG, 1), color, [x, y, z], [Math.PI / 2, 0, 0]);
  /* балка квадратного сечения t между точками a и b ([x, y, z]) */
  const beam = (a, b, t, color, t2) => {
    const A = V(a[0], a[1], a[2]), B = V(b[0], b[1], b[2]);
    const d = B.clone().sub(A), len = Math.max(0.01, d.length());
    const q = new THREE.Quaternion().setFromUnitVectors(UP, d.normalize());
    return { geometry: new THREE.BoxGeometry(t, len, t2 || t), color, matrix: new THREE.Matrix4().compose(A.add(B).multiplyScalar(0.5), q, V(1, 1, 1)) };
  };
  /* стена в плоскости z-y толщиной t (по x от x до x + t): контур [[z, y], ...] — боковые стены разреза */
  const wallX = (pts, x, t, color) => {
    const sh = new THREE.Shape(pts.map(([z, y]) => new THREE.Vector2(z, y)));
    const g = new THREE.ExtrudeGeometry(sh, { depth: t, bevelEnabled: false, curveSegments: 1 }).rotateY(-Math.PI / 2).translate(x + t, 0, 0);
    return { geometry: g, color, position: [0, 0, 0] };
  };
  /* кольцо прямоугольного сечения вокруг оси y: радиусы r0..r1, высота h, основание y */
  const ring = (r0, r1, h, x, y, z, color, seg) => {
    const g = new THREE.LatheGeometry([new THREE.Vector2(r0, 0), new THREE.Vector2(r1, 0), new THREE.Vector2(r1, h), new THREE.Vector2(r0, h), new THREE.Vector2(r0, 0)], seg || 28);
    return { geometry: g, color, position: [x, y, z] };
  };
  /* то же кольцо вокруг оси x (статор кольцевого привода мельницы), центр (x, y, z), ширина w */
  const ringX = (r0, r1, w, x, y, z, color, seg) => {
    const g = new THREE.LatheGeometry([new THREE.Vector2(r0, -w / 2), new THREE.Vector2(r1, -w / 2), new THREE.Vector2(r1, w / 2), new THREE.Vector2(r0, w / 2), new THREE.Vector2(r0, -w / 2)], seg || 28)
      .rotateZ(-Math.PI / 2);
    return { geometry: g, color, position: [x, y, z] };
  };
  /* неподвижный корпус: склейка частей, свет запечён, один вызов отрисовки */
  const body = (parts, name, double) => {
    const m = new THREE.Mesh(ctx.bake(ctx.merge(parts)), double ? ctx.materials.bakedDouble : ctx.materials.baked);
    m.name = name || '';
    return m;
  };
  /* полосы по окружности вокруг оси (ось 'x' или 'z' через начало координат): затемнить нечётные сектора */
  const stripes = (g, axis, count, k, rMin) => {
    const P = g.attributes.position, C = g.attributes.color;
    for (let i = 0; i < P.count; i += 3) {
      let a = 0, b = 0;
      for (let j = 0; j < 3; j++) {
        if (axis === 'x') { a += P.getY(i + j); b += P.getZ(i + j); } else { a += P.getX(i + j); b += P.getY(i + j); }
      }
      a /= 3; b /= 3;
      if (Math.hypot(a, b) < rMin) continue;
      const s = Math.floor((Math.atan2(b, a) + Math.PI) / (2 * Math.PI) * count);
      if (s % 2) for (let j = 0; j < 3; j++) C.setXYZ(i + j, C.getX(i + j) * k, C.getY(i + j) * k, C.getZ(i + j) * k);
    }
    C.needsUpdate = true;
    return g;
  };
  /* барабан мельницы вдоль x, центр в начале координат: обечайка R × L, конусные крышки, цапфы,
     у SAG — бутара; полосы футеровки делают вращение заметным. Цвета — яркость (цвет линии даёт
     экземпляр), рисовать Ламбертом с цветами вершин. */
  const drum = (R, L, o) => {
    const seg = soft ? 16 : 22, hd = o.head, rt = o.trunnion, tl = o.tl;
    const P = [
      cylX(R, L, 0, 0, 0, 0xffffff, seg),
      cylX(rt, hd, -L / 2 - hd / 2, 0, 0, 0xd8d8d8, seg, R),
      cylX(R, hd, L / 2 + hd / 2, 0, 0, 0xd8d8d8, seg, rt),
      cylX(R + 0.45, 0.9, -L / 2 + 0.45, 0, 0, 0xb4b4b4, seg),
      cylX(R + 0.45, 0.9, L / 2 - 0.45, 0, 0, 0xb4b4b4, seg),
      cylX(R + 0.3, 0.6, 0, 0, 0, 0xb4b4b4, seg),
      cylX(rt * 0.82, tl, -L / 2 - hd - tl / 2, 0, 0, 0xa0a0a0, 12),
      cylX(rt * 0.82, tl, L / 2 + hd + tl / 2, 0, 0, 0xa0a0a0, 12),
    ];
    if (o.trommel) P.push(cylX(rt * 0.8, o.trommel, L / 2 + hd + tl + o.trommel / 2, 0, 0, 0xc8c8c8, 12));
    return stripes(ctx.merge(P), 'x', o.stripes || 12, 0.78, 0.55 * R);
  };

  /* ------------------------------------------------------------------ пулы */
  const pools = { pipes: [], lamps: [], bands: [], streams: [], belts: [], spins: new Map(), misc: [] };
  /* труба по ломаной pts ([[x, y, z], ...]) радиуса r; edge — ребро потока 'a>b' (путь беды до меди) */
  const pipe = (pts, r, edge, id) => { for (let i = 1; i < pts.length; i++) pools.pipes.push({ a: pts[i - 1], b: pts[i], r: r || 1, edge: edge || '', id: id || '' }); };
  /* лампа состояния: id — вещь; kind(AKT) → 'run' | 'warn' | 'alarm' | 'off' (по умолчанию — по состоянию вещи) */
  const lamp = (id, at, kind, size) => pools.lamps.push({ id, at, kind: kind || null, size: size || 1.6 });
  /* светящееся кольцо привода мельницы вокруг оси x */
  const band = (id, at, R) => pools.bands.push({ id, at, R });
  /* струя руды или пульпы: сверху вниз, top — [x, y, z], bottom() — высота низа, on() — течёт ли */
  const stream = (top, bottom, w, color, on) => { const s = { top, bottom, w, color, on, cur: 0 }; pools.streams.push(s); return s; };
  /* неподвижная мелочь без своей карточки (эстакады питающих лент, течки) — одна склейка */
  const misc = parts => { for (const p of parts) pools.misc.push(p); };
  /* лента конвейера от a до b шириной w: id — вещь для щелчка; set(v у.е./с, loaded) и tint(свечение)
     — по опросу Ditto; бег руды считает пул (все ленты — одна склейка, один вызов отрисовки) */
  const belt = (a, b, w, o) => {
    o = o || {};
    const B = { a, b, w, rep: o.rep || 14, id: o.id || '', v: 0, target: 0, loaded: true, glow: '', phase: 0, dirtyV: true, dirtyC: true };
    pools.belts.push(B);
    return {
      set(v, loaded) { B.target = v; if (!!loaded !== B.loaded) { B.loaded = !!loaded; B.dirtyV = true; } },
      tint(kind) { if (kind !== B.glow) { B.glow = kind; B.dirtyC = true; } },
    };
  };
  /* вращающаяся или меняющая размер часть (экземпляр): kind — вид (одна геометрия на вид), make() →
     {geometry, material}; it: id, pos [x, y, z], axis 'x' | 'y' | 'z', dir, s [sx, sy, sz], color */
  const spin = (kind, make, it) => {
    if (!pools.spins.has(kind)) pools.spins.set(kind, { make, items: [] });
    const o = Object.assign({ axis: 'x', dir: 1, s: [1, 1, 1], color: 0xffffff, angle: 0, w: 0, target: 0, dirty: true }, it);
    pools.spins.get(kind).items.push(o);
    return o;
  };
  /* рама конвейера: стрингеры вдоль ленты и стойки до земли через каждые every у.е. */
  const trestle = (P, a, b, w, every, color) => {
    const A = V(a[0], a[1], a[2]), B = V(b[0], b[1], b[2]);
    const len = A.distanceTo(B), side = V(-(B.z - A.z), 0, B.x - A.x).normalize();
    const off = (p, s, dy) => [p.x + side.x * s, p.y + dy, p.z + side.z * s];
    P.push(beam(off(A, w / 2 + 0.4, -0.5), off(B, w / 2 + 0.4, -0.5), 0.9, color, 1.4));
    P.push(beam(off(A, -w / 2 - 0.4, -0.5), off(B, -w / 2 - 0.4, -0.5), 0.9, color, 1.4));
    const n = Math.max(1, Math.floor(len / every));
    for (let i = 1; i <= n; i++) {
      const f = i / (n + 1), p = A.clone().lerp(B, f);
      const g = ctx.heightAt(p.x, p.z);
      if (p.y - g < 3) continue;
      const l = off(p, w / 2 + 0.4, -1), r = off(p, -w / 2 - 0.4, -1);
      P.push(beam([l[0], g, l[2]], l, 0.8, color), beam([r[0], g, r[2]], r, 0.8, color));
      P.push(beam(l, r, 0.6, color));
      if (p.y - g > 10) P.push(beam([l[0], g + 1, l[2]], [r[0], (p.y + g) / 2, r[2]], 0.5, color));
    }
    return P;
  };

  return {
    THREE, V, SEG, soft, STYLE, NB,
    part, box, cyl, cylX, cylZ, beam, wallX, ring, ringX, body, stripes, drum,
    belt, trestle, pools, pipe, lamp, band, stream, misc, spin,
  };
}

/* Пулы → по одному InstancedMesh или склейке: трубы (путь беды до меди — синие), лампы (работает —
   голубые, внимание — жёлтые, стоит — красные, беда — пульс), кольца приводов, струи руды, ленты,
   вращающиеся части, неподвижная мелочь. */
export function finishPools(ctx, K, group) {
  const { THREE, AKT } = ctx;
  const { pools } = K;
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3(), c = new THREE.Color();
  const UP = new THREE.Vector3(0, 1, 0), d = new THREE.Vector3();
  const AX = { x: new THREE.Vector3(1, 0, 0), y: new THREE.Vector3(0, 1, 0), z: new THREE.Vector3(0, 0, 1) };
  const LAMP = { run: new THREE.Color(ctx.glowColors.run), warn: new THREE.Color(ctx.glowColors.warn), alarm: new THREE.Color(ctx.glowColors.alarm), off: new THREE.Color(0x55606a) };
  const ISSUE = new THREE.Color(ctx.glowColors.issue), CHAIN = new THREE.Color(ctx.glowColors.chain), WHITE = new THREE.Color(0xffffff);
  /* свечение экземпляра: беда, остановка — красное; путь беды до меди — синее; выбор — светлее */
  const glowTint = (col, id) => {
    const g = id ? ctx.glowOf(id) : '';
    if (g === 'issue' || g === 'alarm') col.lerp(ISSUE, 0.45);
    else if (g === 'chain') col.lerp(CHAIN, 0.4);
    else if (g === 'focus') col.lerp(WHITE, 0.25);
    return col;
  };

  /* неподвижная мелочь */
  if (pools.misc.length) { const m = K.body(pools.misc, 'plant-misc'); group.add(m); }

  /* трубы */
  let pipes = null;
  if (pools.pipes.length) {
    const g = ctx.keep(new THREE.CylinderGeometry(1, 1, 1, 6, 1, true));
    pipes = new THREE.InstancedMesh(g, ctx.mat(0xffffff), pools.pipes.length);
    pipes.name = 'plant-pipes'; pipes.frustumCulled = false;
    pools.pipes.forEach((o, i) => {
      const a = new THREE.Vector3(...o.a), b = new THREE.Vector3(...o.b);
      d.subVectors(b, a); const len = d.length();
      q.setFromUnitVectors(UP, d.normalize());
      m4.compose(p.addVectors(a, b).multiplyScalar(0.5), q, s.set(o.r, len, o.r));
      pipes.setMatrixAt(i, m4);
      pipes.setColorAt(i, c.setHex(0x9aa1a8));
    });
    group.add(pipes);
    ctx.onClick(hit => { const o = pools.pipes[hit.instanceId]; return o ? (o.id || (o.edge ? o.edge.split('>')[0] : '')) : ''; }, pipes, { halo: false });
  }
  /* лампы */
  let lamps = null;
  if (pools.lamps.length) {
    const g = ctx.keep(new THREE.OctahedronGeometry(1, 0));
    lamps = new THREE.InstancedMesh(g, ctx.keep(new THREE.MeshBasicMaterial({ color: 0xffffff })), pools.lamps.length);
    lamps.name = 'plant-lamps'; lamps.frustumCulled = false;
    pools.lamps.forEach((o, i) => {
      m4.compose(p.set(o.at[0], o.at[1], o.at[2]), q.identity(), s.set(o.size, o.size * 1.25, o.size));
      lamps.setMatrixAt(i, m4);
      lamps.setColorAt(i, LAMP.off);
    });
    group.add(lamps);
    ctx.onClick(hit => (pools.lamps[hit.instanceId] || {}).id || '', lamps, { halo: false });
  }
  /* кольца приводов */
  let bands = null;
  if (pools.bands.length) {
    const g = ctx.keep(new THREE.TorusGeometry(1, 0.06, 4, K.soft ? 24 : 32).rotateY(Math.PI / 2));
    bands = new THREE.InstancedMesh(g, ctx.keep(new THREE.MeshBasicMaterial({ color: 0xffffff })), pools.bands.length);
    bands.name = 'plant-bands'; bands.frustumCulled = false;
    pools.bands.forEach((o, i) => {
      m4.compose(p.set(o.at[0], o.at[1], o.at[2]), q.identity(), s.set(o.R, o.R, o.R));
      bands.setMatrixAt(i, m4);
      bands.setColorAt(i, LAMP.off);
    });
    group.add(bands);
    ctx.onClick(hit => (pools.bands[hit.instanceId] || {}).id || '', bands, { halo: false });
  }
  /* струи */
  let streams = null;
  if (pools.streams.length) {
    const g = ctx.keep(new THREE.BoxGeometry(1, 1, 1).translate(0, -0.5, 0));
    streams = new THREE.InstancedMesh(g, ctx.keep(new THREE.MeshBasicMaterial({ color: 0xffffff })), pools.streams.length);
    streams.name = 'plant-streams'; streams.frustumCulled = false;
    pools.streams.forEach((o, i) => {
      streams.setColorAt(i, ctx.litColor(o.color, new THREE.Vector3(0.4, 0.5, 0.75).normalize()));
      m4.compose(p.set(o.top[0], o.top[1], o.top[2]), q.identity(), s.set(0.0001, 0.0001, 0.0001));
      streams.setMatrixAt(i, m4);
    });
    group.add(streams);
  }

  /* ленты: одна склейка; атлас — сверху лента с рудой, снизу пустая; u сдвигается у каждой ленты */
  let belts = null, beltUv = null, beltU0 = null, beltCol = null;
  const LIT = ctx.litColor(0xffffff, new THREE.Vector3(0, 1, 0));
  if (pools.belts.length) {
    const atlas = document.createElement('canvas'); atlas.width = 128; atlas.height = 64;
    const x = atlas.getContext('2d');
    x.fillStyle = '#30343a'; x.fillRect(0, 0, 128, 64);
    const ore = ['#8a7865', '#6f5d4c', '#a48f75', '#7d7a72'];
    for (let i = 0; i < 30; i++) { x.fillStyle = ore[i % ore.length]; x.beginPath(); x.ellipse((i * 37) % 128 + 3, 6 + (i * 13) % 20, 4 + (i % 3), 3 + (i % 2), (i % 5) * 0.6, 0, 2 * Math.PI); x.fill(); }
    x.fillStyle = '#3b4047'; for (let i = 0; i < 128; i += 16) x.fillRect(i, 32, 3, 32);
    const tex = ctx.keep(new THREE.CanvasTexture(atlas));
    tex.wrapS = THREE.RepeatWrapping; tex.wrapT = THREE.ClampToEdgeWrapping; tex.colorSpace = THREE.SRGBColorSpace;
    const across = [[-0.5, 0.55], [-0.28, 0], [0.28, 0], [0.5, 0.55]];
    const pos = [], uv = [], col = [], idx = [], owner = [];
    for (const B of pools.belts) {
      const A = new THREE.Vector3(...B.a), E = new THREE.Vector3(...B.b);
      const dd = E.clone().sub(A), len = dd.length();
      const side = new THREE.Vector3(-dd.z, 0, dd.x).normalize();
      B.i0 = pos.length / 3;
      for (const [P, u] of [[A, 0], [E, len / B.rep]]) {
        for (let i = 0; i < 4; i++) {
          const [f, h] = across[i];
          pos.push(P.x + side.x * f * B.w, P.y + h, P.z + side.z * f * B.w);
          uv.push(u, 0); col.push(LIT.r, LIT.g, LIT.b); owner.push(B);
        }
      }
      for (let i = 0; i < 3; i++) idx.push(B.i0 + i, B.i0 + 4 + i, B.i0 + i + 1, B.i0 + i + 1, B.i0 + 4 + i, B.i0 + 5 + i);
    }
    const g = ctx.keep(new THREE.BufferGeometry());
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    beltUv = new THREE.Float32BufferAttribute(uv, 2); beltUv.setUsage(THREE.DynamicDrawUsage);
    beltCol = new THREE.Float32BufferAttribute(col, 3); beltCol.setUsage(THREE.DynamicDrawUsage);
    g.setAttribute('uv', beltUv); g.setAttribute('color', beltCol);
    g.setIndex(idx);
    g.computeVertexNormals();
    beltU0 = uv.filter((_, i) => i % 2 === 0);
    belts = new THREE.Mesh(g, ctx.keep(new THREE.MeshBasicMaterial({ map: tex, vertexColors: true })));
    belts.name = 'plant-belts';
    group.add(belts);
    ctx.onClick(hit => { const B = hit.face ? owner[hit.face.a] : null; return B ? B.id : ''; }, belts, { halo: false });
  }

  /* вращающиеся части: по InstancedMesh на вид */
  const spins = [];
  for (const [kind, sp] of pools.spins) {
    const { geometry, material } = sp.make();
    const im = new THREE.InstancedMesh(geometry, material, sp.items.length);
    im.name = 'plant-' + kind; im.frustumCulled = false;
    sp.items.forEach((o, i) => im.setColorAt(i, glowTint(c.setHex(o.color), '')));
    group.add(im);
    ctx.onClick(hit => (sp.items[hit.instanceId] || {}).id || '', im, { halo: false });
    spins.push({ im, items: sp.items });
  }

  const lampKind = id => {
    if (!AKT.things[id]) return 'off';
    const st = AKT.st(id);
    if (AKT.stopped(st)) return 'alarm';
    return AKT.cls(st) === 'st-yellow' ? 'warn' : 'run';
  };
  const lampState = pools.lamps.map(() => 'off');
  let pulse = false;

  function fresh(state) {
    if (pipes) {
      pools.pipes.forEach((o, i) => {
        const chain = o.edge && state.chainEdges.has(o.edge);
        const src = o.edge ? o.edge.split('>')[0] : o.id;
        const g = src ? ctx.glowOf(src) : '';
        c.setHex(0x9aa1a8);
        if (chain) c.lerp(CHAIN, 0.75);
        else if (g === 'issue' || g === 'alarm') c.lerp(ISSUE, 0.45);
        pipes.setColorAt(i, c);
      });
      pipes.instanceColor.needsUpdate = true;
    }
    if (lamps) {
      pulse = false;
      pools.lamps.forEach((o, i) => {
        let k = o.kind ? o.kind(AKT) : lampKind(o.id);
        if (k !== 'off' && state.issueNodes.has(o.id)) { k = 'issue'; pulse = true; }
        lampState[i] = k;
        lamps.setColorAt(i, k === 'issue' ? ISSUE : LAMP[k] || LAMP.off);
      });
      lamps.instanceColor.needsUpdate = true;
    }
    if (bands) {
      pools.bands.forEach((o, i) => {
        const st = AKT.st(o.id), g = ctx.glowOf(o.id);
        let col = !AKT.things[o.id] ? LAMP.off : AKT.stopped(st) ? LAMP.alarm : LAMP.run;
        if (g === 'issue') col = ISSUE; else if (g === 'chain' && col === LAMP.run) col = CHAIN;
        bands.setColorAt(i, col);
      });
      bands.instanceColor.needsUpdate = true;
    }
    for (const sp of spins) {
      sp.items.forEach((o, i) => sp.im.setColorAt(i, glowTint(c.setHex(o.color), o.id)));
      sp.im.instanceColor.needsUpdate = true;
    }
  }
  function frame(state, dt) {
    if (lamps && pulse) {
      const k = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(state.t * 4.2));
      pools.lamps.forEach((o, i) => { if (lampState[i] === 'issue') lamps.setColorAt(i, c.copy(LAMP.off).lerp(ISSUE, k)); });
      lamps.instanceColor.needsUpdate = true;
    }
    if (streams) {
      let changed = false;
      pools.streams.forEach((o, i) => {
        let on = false;
        try { on = !!o.on(state); } catch (e) { on = false; }
        const goal = on ? 1 : 0;
        if (Math.abs(o.cur - goal) > 1e-3 || o.dirty !== false) {
          o.cur += (goal - o.cur) * (1 - Math.exp(-dt * 4));
          if (Math.abs(o.cur - goal) < 0.01) o.cur = goal;
          const len = Math.max(0.01, o.top[1] - o.bottom());
          const w = o.w * o.cur;
          m4.compose(p.set(o.top[0], o.top[1], o.top[2]), q.identity(), w > 0.01 ? s.set(w, len, w) : s.set(0.0001, 0.0001, 0.0001));
          streams.setMatrixAt(i, m4);
          o.dirty = goal > 0;          // пока течёт, низ струи может двигаться (уровень склада)
          changed = true;
        }
      });
      if (changed) streams.instanceMatrix.needsUpdate = true;
    }
    if (belts) {
      let uvCh = false, colCh = false;
      const kk = 1 - Math.exp(-dt * 2.5);
      for (const B of pools.belts) {
        const goal = state.paused ? 0 : B.target;
        B.v += (goal - B.v) * kk;
        if (Math.abs(B.v) > 1e-3) { B.phase = (B.phase - B.v * dt / B.rep) % 1000; B.dirtyV = true; }
        if (B.dirtyV) {
          const v0 = B.loaded ? 0.52 : 0.02;
          for (let j = 0; j < 8; j++) beltUv.setXY(B.i0 + j, beltU0[B.i0 + j] + B.phase, v0 + 0.46 * (j % 4) / 3);
          B.dirtyV = false; uvCh = true;
        }
        if (B.dirtyC) {
          c.copy(LIT);
          if (B.glow === 'issue' || B.glow === 'alarm') c.lerp(ISSUE, 0.5); else if (B.glow === 'chain') c.lerp(CHAIN, 0.5);
          for (let j = 0; j < 8; j++) beltCol.setXYZ(B.i0 + j, c.r, c.g, c.b);
          B.dirtyC = false; colCh = true;
        }
      }
      if (uvCh) beltUv.needsUpdate = true;
      if (colCh) beltCol.needsUpdate = true;
    }
    const kw = 1 - Math.exp(-dt * 0.9);
    for (const sp of spins) {
      let ch = false;
      sp.items.forEach((o, i) => {
        const goal = state.paused ? 0 : o.target;
        o.w += (goal - o.w) * kw;
        if (Math.abs(o.w) > 1e-4) { o.angle = (o.angle + o.dir * o.w * dt) % (2 * Math.PI); o.dirty = true; }
        if (!o.dirty) return;
        q.setFromAxisAngle(AX[o.axis], o.angle);
        m4.compose(p.set(o.pos[0], o.pos[1], o.pos[2]), q, s.set(o.s[0], o.s[1], o.s[2]));
        sp.im.setMatrixAt(i, m4);
        o.dirty = false; ch = true;
      });
      if (ch) sp.im.instanceMatrix.needsUpdate = true;
    }
  }
  return {
    update(state, dt) { if (state.fresh) fresh(state); frame(state, dt); },
  };
}
