/* 3D view of the site (three.js r160, vendored). Plan metres x east, y north
   become three.js (x, height, -y). Ground: the Sentinel-2 image with the pit
   cut out; the pit: terraced cone from the OSM outline, 230 m deep (fact);
   plants, stockpiles, conveyors, tailings, power line from plan.json; things
   from Ditto (state colours, t/h, levels, trucks, people, sensors). Every
   number is HTML text over the scene; light scene, no shadows, one draw loop
   at <= 30 fps that also runs on software WebGL. */
import * as THREE from './vendor/three-0.160.0/three.module.min.js';

const PIT_ID = 'way/773805067';
const PIT_DEPTH = 230;          // m, fact (KAZ Minerals); benches and slope are a scheme
const BENCHES = 12;
const LINE_BLD = { 'line-1': 'way/1347766933', 'line-2': 'way/1347766934', 'crusher-1': 'way/773805064' };
const COLORS = { 'st-grey': 0xc9cdd3, 'st-yellow': 0xe8a000, 'st-red': 0xc62828, 'st-soon': 0xf1dca0 };
const NB = ' ';

export async function create(AKT, stage, opts, onFail) {
  const fmt = AKT.fmt, f1 = AKT.f1, f2 = AKT.f2, esc = AKT.esc;
  const plan = await AKT.loadPlan();
  let sat = null;
  try { sat = await AKT.get('/sat/aktogay_s2.json'); } catch (e) { sat = null; }

  /* ---------------------------------------------------------------- DOM */
  stage.innerHTML = '';
  const bar = document.createElement('div'); bar.id = 's3-bar';
  bar.innerHTML = `<span class="seg" role="group" aria-label="Камера"><button data-cam="site">Площадка</button><button data-cam="pit">Карьер</button><button data-cam="plant">Фабрика</button></span>
 <span class="s3-hint">Перетащите — повернуть · правая кнопка — сдвинуть · колесо — ближе/дальше · стрелки и +/− с клавиатуры (0 — вид по умолчанию) · щелчок по объекту — карточка</span>
 <div class="s3-sub" id="s3-view">Вся площадка: карьер, дробилки, склады руды, фабрика, хвостохранилище и ЛЭП. Серое работает как надо, цвет — только у отклонений; ≈ — расчёт модели.</div><span id="s3-trucks" hidden></span>`;
  stage.appendChild(bar);
  const wrap = document.createElement('div'); wrap.id = 's3-wrap'; stage.appendChild(wrap);
  const canvas = document.createElement('canvas'); canvas.id = 's3-canvas'; canvas.setAttribute('aria-label', '3D-вид площадки Актогай: стрелки — повернуть и наклонить, плюс и минус — масштаб, 0 — вид по умолчанию'); canvas.setAttribute('role', 'img'); canvas.tabIndex = 0;
  wrap.appendChild(canvas);
  const layer = document.createElement('div'); layer.className = 's3-labels'; wrap.appendChild(layer);
  const attr = document.createElement('div'); attr.className = 's3-attr';
  attr.innerHTML = `<a href="${esc(plan.license_url)}" target="_blank" rel="license noopener">${esc(plan.attribution)}, ODbL</a>`
    + (sat ? ` · <a href="${esc(sat.licence.terms_url)}" target="_blank" rel="license noopener">${esc(sat.licence.attribution)}</a>` : '');
  wrap.appendChild(attr);

  /* ----------------------------------------------------------- renderer */
  /* программный WebGL (SwiftShader, llvmpipe): сцена считается процессором и без ограничения отнимала у стенда 3 ядра
     из 8 при 30 кадрах/с (23.10); на нём 8 кадров/с */
  let frameMs = 33;
  try {
    const pc = document.createElement('canvas');
    const gl = pc.getContext('webgl2') || pc.getContext('webgl');
    if (gl) {
      const ext = gl.getExtension('WEBGL_debug_renderer_info');
      const name = String(ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER));
      if (/swiftshader|llvmpipe|software|basic render/i.test(name)) frameMs = 120;
      const lose = gl.getExtension('WEBGL_lose_context'); if (lose) lose.loseContext();
    }
  } catch (e) { /* проба необязательна */ }
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'low-power', preserveDrawingBuffer: false });
  renderer.setPixelRatio(1);
  renderer.shadowMap.enabled = false;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xe4ecf3);
  const camera = new THREE.PerspectiveCamera(45, 1, 20, 80000);
  scene.add(new THREE.HemisphereLight(0xffffff, 0xb9ab95, 2.2));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4); sun.position.set(-3000, 6000, 3000); scene.add(sun);
  const disposables = [];
  const keep = o => { disposables.push(o); return o; };
  const V = (x, y, h) => new THREE.Vector3(x, h, -y);
  const pickables = [];

  /* ------------------------------------------------------------ ground */
  const B = sat ? sat.bounds_plan_m : { x0: -7200, y0: -4600, x1: 10000, y1: 7600 };
  const W = B.x1 - B.x0, H = B.y1 - B.y0;
  const uvOf = (x, y) => [(x - B.x0) / W, (y - B.y0) / H];
  const pitIt = plan.layers.quarry.find(it => it.id === PIT_ID);
  const pit = pitIt ? pitIt.pts.map(p => [p[0], p[1]]) : null;
  const pc = pit ? [pit.reduce((s, p) => s + p[0], 0) / pit.length, pit.reduce((s, p) => s + p[1], 0) / pit.length] : [3466, 3191];
  let tex = null;
  if (sat) {
    tex = keep(new THREE.TextureLoader().load('sat/' + sat.image, () => { dirty = true; }));
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.generateMipmaps = false; tex.minFilter = THREE.LinearFilter; tex.magFilter = THREE.LinearFilter;
    tex.wrapS = tex.wrapT = THREE.ClampToEdgeWrapping;
  }
  const groundMat = keep(new THREE.MeshLambertMaterial(tex ? { map: tex } : { color: 0xd9cfbd }));
  {
    const shape = new THREE.Shape([new THREE.Vector2(B.x0, B.y0), new THREE.Vector2(B.x1, B.y0), new THREE.Vector2(B.x1, B.y1), new THREE.Vector2(B.x0, B.y1)]);
    if (pit) shape.holes.push(new THREE.Path(pit.map(p => new THREE.Vector2(p[0], p[1]))));
    const g = keep(new THREE.ShapeGeometry(shape));
    setUv(g);
    const m = new THREE.Mesh(g, groundMat); m.rotation.x = -Math.PI / 2; scene.add(m);
  }
  function setUv(g) {
    const pos = g.attributes.position, uv = new Float32Array(pos.count * 2);
    for (let i = 0; i < pos.count; i++) { const [u, v] = uvOf(pos.getX(i), pos.getY(i)); uv[2 * i] = u; uv[2 * i + 1] = v; }
    g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  }

  /* --------------------------------------------------------------- pit */
  const STEP = 0.80 / BENCHES, BENCH = STEP * 0.42;
  const sTop = i => 1 - i * STEP, dAt = i => -PIT_DEPTH * i / BENCHES;
  /* scale of a point along the ray from the pit centre: 1 on the OSM outline, 0 in the centre */
  function scaleAt(x, y) {
    if (!pit) return 2;
    const dx = x - pc[0], dy = y - pc[1], r = Math.hypot(dx, dy);
    if (r < 1e-6) return 0;
    const ux = dx / r, uy = dy / r;
    let best = Infinity;
    for (let i = 0; i < pit.length; i++) {
      const a = pit[i], b = pit[(i + 1) % pit.length];
      const ex = b[0] - a[0], ey = b[1] - a[1];
      const den = ux * ey - uy * ex;
      if (Math.abs(den) < 1e-9) continue;
      const ax = a[0] - pc[0], ay = a[1] - pc[1];
      const t = (ax * ey - ay * ex) / den, w = (ax * uy - ay * ux) / den;
      if (t > 0 && w >= 0 && w <= 1) best = Math.min(best, t);
    }
    return isFinite(best) ? r / best : 2;
  }
  /* ground height at a plan point: 0 outside the pit, the terraces inside */
  function heightAt(x, y) {
    const s = scaleAt(x, y);
    if (s >= 1) return 0;
    for (let i = 0; i < BENCHES; i++) {
      const sb = sTop(i) - BENCH, sn = sTop(i + 1);
      if (s >= sb) return dAt(i);
      if (s >= sn) return dAt(i) + (dAt(i + 1) - dAt(i)) * (sb - s) / (sb - sn);
    }
    return dAt(BENCHES);
  }
  if (pit) {
    const ring = (s, d) => pit.map(p => [pc[0] + (p[0] - pc[0]) * s, pc[1] + (p[1] - pc[1]) * s, d]);
    const pos = [], uv = [], col = [];
    const tri = (a, b, c, shade) => { for (const p of [a, b, c]) { pos.push(p[0], p[2], -p[1]); const [u, v] = uvOf(p[0], p[1]); uv.push(u, v); col.push(shade, shade, shade * 0.97); } };
    const band = (r1, r2, shade) => { for (let k = 0; k < r1.length; k++) { const k2 = (k + 1) % r1.length; tri(r1[k], r1[k2], r2[k2], shade); tri(r1[k], r2[k2], r2[k], shade); } };
    for (let i = 0; i < BENCHES; i++) {
      const fade = 1 - 0.28 * i / BENCHES;
      const top = ring(sTop(i), dAt(i)), inner = ring(sTop(i) - BENCH, dAt(i)), next = ring(sTop(i + 1), dAt(i + 1));
      band(top, inner, 1.0 * fade);
      band(inner, next, 0.66 * fade);
    }
    const bottom = ring(sTop(BENCHES), dAt(BENCHES)), cc = [pc[0], pc[1], dAt(BENCHES)];
    for (let k = 0; k < bottom.length; k++) tri(bottom[k], bottom[(k + 1) % bottom.length], cc, 0.7);
    const g = keep(new THREE.BufferGeometry());
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, keep(new THREE.MeshLambertMaterial(tex ? { map: tex, vertexColors: true, side: THREE.DoubleSide } : { color: 0xc8b48e, vertexColors: true, side: THREE.DoubleSide })));
    m.userData.thing = 'pit'; pickables.push(m); scene.add(m);
  }

  /* --------------------------------------------------- flat OSM layers */
  const flat = (pts, h, color, opacity, thing) => {
    const g = keep(new THREE.ShapeGeometry(new THREE.Shape(pts.map(p => new THREE.Vector2(p[0], p[1])))));
    const m = new THREE.Mesh(g, keep(new THREE.MeshLambertMaterial({ color, transparent: opacity < 1, opacity, depthWrite: opacity >= 1, side: THREE.DoubleSide })));
    m.rotation.x = -Math.PI / 2; m.position.y = h;
    if (thing) { m.userData.thing = thing; pickables.push(m); }
    scene.add(m); return m;
  };
  for (const it of plan.layers.tailings) flat(it.pts, 1.5, it.id === 'way/773805070' ? 0x6fa8dc : 0xaab8c6, it.id === 'way/773805070' ? 0.62 : 0.35, 'water');
  for (const it of plan.layers.reservoir) flat(it.pts, 2, 0x5b9bd5, 0.75, 'water');
  for (const it of (plan.layers.water || [])) flat(it.pts, 2, 0x5b9bd5, 0.75, null);

  /* ----------------------------------------------------------- buildings */
  const stateMeshes = {};   // thing -> [mesh]
  const addState = (name, mesh) => { (stateMeshes[name] = stateMeshes[name] || []).push(mesh); mesh.userData.thing = name; pickables.push(mesh); };
  const extrude = (pts, h, color) => {
    const g = keep(new THREE.ExtrudeGeometry(new THREE.Shape(pts.map(p => new THREE.Vector2(p[0], p[1]))), { depth: h, bevelEnabled: false }));
    const m = new THREE.Mesh(g, keep(new THREE.MeshLambertMaterial({ color }))); m.rotation.x = -Math.PI / 2; scene.add(m); return m;
  };
  const byId = {};
  for (const k of Object.keys(plan.layers)) for (const it of plan.layers[k]) byId[it.id] = it;
  for (const [name, id] of Object.entries(LINE_BLD)) if (byId[id]) addState(name, extrude(byId[id].pts, name.startsWith('line') ? 42 : 30, COLORS['st-grey']));
  for (const it of plan.layers.building) if (!Object.values(LINE_BLD).includes(it.id)) extrude(it.pts, 14, 0xb3b8bf);
  for (const it of plan.layers.substation) { const m = extrude(it.pts, 6, 0xd0d3d8); m.userData.thing = 'power'; pickables.push(m); }
  const box = (name, x, y, w, d, h, color) => {
    const g = keep(new THREE.BoxGeometry(w, h, d));
    const m = new THREE.Mesh(g, keep(new THREE.MeshLambertMaterial({ color })));
    m.position.copy(V(x, y, heightAt(x, y) + h / 2)); scene.add(m);
    if (name) addState(name, m);
    return m;
  };
  const anchor = n => { const a = plan.anchors[n]; return a ? (a.xy || (a.path ? a.path[Math.floor(a.path.length / 2)] : null)) : AKT.pos(n); };
  if (!byId[LINE_BLD['crusher-1']]) { const a = anchor('crusher-1'); box('crusher-1', a[0], a[1], 60, 40, 30, COLORS['st-grey']); }
  { const a = anchor('crusher-2'); if (a) box('crusher-2', a[0], a[1], 60, 40, 30, COLORS['st-grey']); }
  { const a = anchor('conc-stock'); if (a) box('conc-stock', a[0], a[1], 140, 60, 18, COLORS['st-grey']); }

  /* ----------------------------------------------------------- stockpiles */
  const piles = {};
  for (const n of ['stockpile-1', 'stockpile-2']) {
    const a = anchor(n); if (!a) continue;
    const ring = new THREE.Mesh(keep(new THREE.RingGeometry(165, 172, 48)), keep(new THREE.MeshBasicMaterial({ color: 0x7a6a4a, side: THREE.DoubleSide })));
    ring.rotation.x = -Math.PI / 2; ring.position.copy(V(a[0], a[1], 1)); scene.add(ring);
    const cone = new THREE.Mesh(keep(new THREE.ConeGeometry(1, 1, 40)), keep(new THREE.MeshLambertMaterial({ color: 0x9c8462 })));
    cone.position.copy(V(a[0], a[1], 0)); scene.add(cone);
    cone.userData.thing = n; pickables.push(cone);
    piles[n] = cone;
  }

  /* ------------------------------------------------------------ conveyors */
  const oreTex = (() => {
    const c = document.createElement('canvas'); c.width = 64; c.height = 16;
    const x = c.getContext('2d');
    x.fillStyle = '#3a3f47'; x.fillRect(0, 0, 64, 16);
    const ore = ['#8e63c7', '#6f5a45', '#a58b6a', '#c9b3e6'];
    for (let i = 0; i < 9; i++) { x.fillStyle = ore[i % ore.length]; x.beginPath(); x.ellipse(4 + i * 7, 5 + (i % 3) * 3, 3, 2.2, 0, 0, 2 * Math.PI); x.fill(); }
    return c;
  })();
  const belts = {};
  const postGeo = keep(new THREE.BoxGeometry(3, 16, 3)), postMat = keep(new THREE.MeshLambertMaterial({ color: 0x8a8f98 }));
  const ribbon =(path, width, h) => {
    const pos = [], uv = [], idx = [];
    let dist = 0;
    for (let i = 0; i < path.length; i++) {
      const p = path[i], prev = path[Math.max(0, i - 1)], next = path[Math.min(path.length - 1, i + 1)];
      const dx = next[0] - prev[0], dy = next[1] - prev[1], L = Math.hypot(dx, dy) || 1;
      const nx = -dy / L * width / 2, ny = dx / L * width / 2;
      if (i > 0) dist += Math.hypot(p[0] - path[i - 1][0], p[1] - path[i - 1][1]);
      pos.push(p[0] + nx, h, -(p[1] + ny), p[0] - nx, h, -(p[1] - ny));
      uv.push(dist / 50, 0, dist / 50, 1);
      if (i > 0) { const b = 2 * (i - 1); idx.push(b, b + 1, b + 2, b + 1, b + 3, b + 2); }
    }
    const g = keep(new THREE.BufferGeometry());
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    g.setIndex(idx); g.computeVertexNormals();
    return g;
  };
  for (const [n, path, sag] of [['conveyor-1', plan.anchors['conveyor-1'].path], ['conveyor-2', plan.anchors['conveyor-2'].path],
    ['stockpile-1', plan.anchors['stockpile-1'].to_sag, 'sag-1'], ['stockpile-2', plan.anchors['stockpile-2'].to_sag, 'sag-2']]) {
    if (!path) continue;
    const t = keep(new THREE.CanvasTexture(oreTex));
    t.wrapS = THREE.RepeatWrapping; t.wrapT = THREE.ClampToEdgeWrapping; t.colorSpace = THREE.SRGBColorSpace;
    const mat = keep(new THREE.MeshBasicMaterial({ map: t, side: THREE.DoubleSide }));
    const m = new THREE.Mesh(ribbon(path, 16, 16), mat); scene.add(m);
    m.userData.thing = sag ? sag : n; pickables.push(m);
    /* posts every 120 m */
    for (let i = 1; i < path.length; i++) {
      const L = Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]);
      for (let d = 60; d < L; d += 120) {
        const f = d / L, x = path[i - 1][0] + (path[i][0] - path[i - 1][0]) * f, y = path[i - 1][1] + (path[i][1] - path[i - 1][1]) * f;
        const p = new THREE.Mesh(postGeo, postMat); p.position.copy(V(x, y, 8)); scene.add(p);
      }
    }
    belts[n] = { tex: t, mat, sag, speed: 0, stopped: false };
  }

  /* ------------------------------------------------------------ power line */
  {
    const pyGeo = keep(new THREE.BoxGeometry(6, 40, 6)), pyMat = keep(new THREE.MeshLambertMaterial({ color: 0x7d838c }));
    const wireMat = keep(new THREE.LineBasicMaterial({ color: 0x55595f }));
    const inside = p => p[0] > B.x0 && p[0] < B.x1 && p[1] > B.y0 && p[1] < B.y1;
    for (const it of plan.layers.power_line) {
      const tops = [];
      for (let i = 0; i < it.pts.length; i++) {
        const p = it.pts[i];
        if (i > 0) {
          const q = it.pts[i - 1], L = Math.hypot(p[0] - q[0], p[1] - q[1]), n = Math.floor(L / 380);
          for (let k = 1; k <= n; k++) { const f = k / (n + 1); tops.push([q[0] + (p[0] - q[0]) * f, q[1] + (p[1] - q[1]) * f]); }
        }
        tops.push(p);
      }
      const pts3 = [];
      for (const p of tops.filter(inside)) {
        const m = new THREE.Mesh(pyGeo, pyMat); m.position.copy(V(p[0], p[1], 20)); m.userData.thing = 'power'; pickables.push(m); scene.add(m);
        pts3.push(V(p[0], p[1], 38));
      }
      if (pts3.length > 1) scene.add(new THREE.Line(keep(new THREE.BufferGeometry().setFromPoints(pts3)), wireMat));
    }
  }

  /* ---------------------------------------------------------- excavators */
  const excGeo = keep(new THREE.BoxGeometry(40, 24, 30)), boomGeo = keep(new THREE.BoxGeometry(50, 6, 6));
  const machines = {};
  const machine = (name, x, y) => {
    const g = new THREE.Group();
    const mat = keep(new THREE.MeshLambertMaterial({ color: 0xf2b600 }));
    const body = new THREE.Mesh(excGeo, mat); body.position.y = 12; g.add(body);
    const boom = new THREE.Mesh(boomGeo, mat); boom.position.set(38, 26, 0); boom.rotation.z = -0.5; g.add(boom);
    g.position.copy(V(x, y, heightAt(x, y)));
    body.userData.thing = name; boom.userData.thing = name; pickables.push(body, boom);
    scene.add(g); machines[name] = { g, mat };
    return g;
  };
  for (const n of AKT.ofType('exc')) { const a = anchor(n); if (a) machine(n, a[0], a[1]); }

  /* -------------------------------------------------------------- trucks */
  const truckGeo = keep(new THREE.BoxGeometry(30, 14, 16)), loadGeo = keep(new THREE.BoxGeometry(18, 8, 14));
  const truckMat = keep(new THREE.MeshLambertMaterial({ color: 0xe0a800 })), loadMat = keep(new THREE.MeshLambertMaterial({ color: 0x7a5f45 }));
  const truckRed = keep(new THREE.MeshLambertMaterial({ color: 0xff6e63 }));
  const trucks = [];        // {g, load, name?, target?, route, phase}
  const mkTruck = () => {
    const g = new THREE.Group();
    const body = new THREE.Mesh(truckGeo, truckMat); body.position.y = 7; g.add(body);
    const load = new THREE.Mesh(loadGeo, loadMat); load.position.set(-4, 17, 0); g.add(load);
    scene.add(g); return { g, body, load };
  };
  /* scheme routes: excavator -> pit rim towards the crusher -> crusher, heights from the terraces */
  const sample = (a, b, step) => { const L = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.max(1, Math.ceil(L / step)), out = []; for (let i = 0; i <= n; i++) out.push([a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n]); return out; };
  const routes = [];
  const buildRoutes = () => {
    routes.length = 0;
    const crushers = ['crusher-1', 'crusher-2'].map(anchor).filter(Boolean);
    const excs = AKT.ofType('exc').filter(n => AKT.st(n) !== 'DOWN' && AKT.st(n) !== 'STOP').map(anchor).filter(Boolean);
    for (const e of (excs.length ? excs : [pc])) {
      const c = crushers.slice().sort((p, q) => Math.hypot(p[0] - e[0], p[1] - e[1]) - Math.hypot(q[0] - e[0], q[1] - e[1]))[0] || [3618, 1580];
      const s = scaleAt(c[0], c[1]);
      const rim = s > 0 && isFinite(s) ? [pc[0] + (c[0] - pc[0]) / s * 1.02, pc[1] + (c[1] - pc[1]) / s * 1.02] : c;
      const pts = sample(e, rim, 40).concat(sample(rim, c, 60).slice(1)).map(p => V(p[0], p[1], heightAt(p[0], p[1]) + 1));
      let len = 0; const cum = [0];
      for (let i = 1; i < pts.length; i++) { len += pts[i].distanceTo(pts[i - 1]); cum.push(len); }
      routes.push({ pts, cum, len });
    }
  };
  const along = (r, f, out) => {
    const d = f * r.len;
    let i = 1; while (i < r.cum.length - 1 && r.cum[i] < d) i++;
    const a = r.pts[i - 1], b = r.pts[i], seg = r.cum[i] - r.cum[i - 1] || 1;
    out.lerpVectors(a, b, Math.max(0, Math.min(1, (d - r.cum[i - 1]) / seg)));
    return Math.atan2(-(b.z - a.z), b.x - a.x);
  };

  /* -------------------------------------------- other things from Ditto */
  const xGeo = {
    person: keep(new THREE.CylinderGeometry(7, 7, 26, 12)), sensor: keep(new THREE.SphereGeometry(9, 12, 8)),
    piezo: keep(new THREE.ConeGeometry(10, 26, 10)), face: keep(new THREE.CylinderGeometry(28, 28, 3, 20)),
    'water-trouble': keep(new THREE.SphereGeometry(16, 14, 10)), fire: keep(new THREE.ConeGeometry(18, 46, 12)),
    hpgr: keep(new THREE.BoxGeometry(50, 30, 40)), exc: excGeo, other: keep(new THREE.OctahedronGeometry(12)),
  };
  const xColor = { person: 0x2f6f4f, sensor: 0xffffff, piezo: 0x3a7fc1, face: 0xd9822b, 'water-trouble': 0x3a7fc1, fire: 0xff5a1f, hpgr: 0xc9cdd3, exc: 0xf2b600, other: 0x9aa0a8 };
  const extras = {};          // name -> {m, cat}
  const xroads = {};

  /* --------------------------------------------------------- HTML labels */
  const labels = [];          // {key, el, pos (Vector3), prio, text(), title(), st, w, h, shown}
  const addLabel = (key, pos, prio, text, title, st, href) => {
    const el = document.createElement('a');
    el.className = 's3l'; el.href = href || `?view=unit&id=${AKT.id(st || key)}`;
    layer.appendChild(el);
    const L = { key, el, pos, prio, text, title, st, w: 0, h: 0, last: '' };
    labels.push(L); return L;
  };
  const stw = (n, normal) => { const s = AKT.st(n); return s && !(normal || ['RUN', 'NORMAL']).includes(s) ? ` ${AKT.stRu(s, n)}` : ''; };
  const top = (n, h) => { const a = anchor(n); return a ? V(a[0], a[1], heightAt(a[0], a[1]) + h) : null; };
  const L0 = [
    ['line-1', top('line-1', 60), 1, () => `Линия 1${stw('line-1')} · ${AKT.vsBase('line-1', 'tph', fmt, 50)} т/ч`, () => `Линия 1: ${AKT.stOf('line-1')} · ${fmt(AKT.num('line-1', 'tph'))} т/ч · ${f1(AKT.num('line-1', 'cu_tph'))} т Cu/ч · извлечение ${f1(AKT.num('line-1', 'recovery'))} %`],
    ['line-2', top('line-2', 60), 1, () => `Линия 2${stw('line-2')} · ${AKT.vsBase('line-2', 'tph', fmt, 50)} т/ч`, () => `Линия 2: ${AKT.stOf('line-2')} · ${fmt(AKT.num('line-2', 'tph'))} т/ч · ${f1(AKT.num('line-2', 'cu_tph'))} т Cu/ч · извлечение ${f1(AKT.num('line-2', 'recovery'))} %`],
    ['crusher-1', top('crusher-1', 45), 2, () => `Дробилка 1${stw('crusher-1')} · ${AKT.vsBase('crusher-1', 'tph', fmt, 50)} т/ч`, () => `Дробилка 1: ${AKT.stOf('crusher-1')}`],
    ['crusher-2', top('crusher-2', 45), 2, () => `Дробилка 2${stw('crusher-2')} · ${AKT.vsBase('crusher-2', 'tph', fmt, 50)} т/ч`, () => `Дробилка 2 (схема): ${AKT.stOf('crusher-2')}`],
    ['stockpile-1', top('stockpile-1', 70), 3, () => `Склад 1${stw('stockpile-1')} · ${AKT.vsBase('stockpile-1', 'level_t', fmt, 200)} т`, () => `Склад руды 1 (схема): ${AKT.stOf('stockpile-1')} · запас на ${AKT.durH(AKT.num('stockpile-1', 'hours_left'))}`],
    ['stockpile-2', top('stockpile-2', 70), 3, () => `Склад 2${stw('stockpile-2')} · ${AKT.vsBase('stockpile-2', 'level_t', fmt, 200)} т`, () => `Склад руды 2 (схема): ${AKT.stOf('stockpile-2')} · запас на ${AKT.durH(AKT.num('stockpile-2', 'hours_left'))}`],
    ['conveyor-1', V(1500, 1245, 24), 4, () => `Конв. 1 · ${AKT.vsBase('conveyor-1', 'tph', fmt, 50)} т/ч`, () => `Конвейер 1: ${AKT.stOf('conveyor-1')}`],
    ['conveyor-2', V(2900, 1250, 24), 4, () => `Конв. 2 · ${AKT.vsBase('conveyor-2', 'tph', fmt, 50)} т/ч`, () => `Конвейер 2: ${AKT.stOf('conveyor-2')}`],
    ['pit', V(pc[0], pc[1] + 900, 30), 5, () => `Карьер${stw('pit')} · ${fmt(AKT.num('pit', 'mining_tph'))} т/ч · глубина 230 м (факт)`, () => `Карьер: ${AKT.stOf('pit')} · добыча ${fmt(AKT.num('pit', 'mining_tph'))} т/ч`],
    ['power', top('power', 50), 4, () => `ЛЭП · ${AKT.vsBase('power', 'site_mw', fmt, 2)}/${fmt(AKT.num('power', 'grid_limit_mw'))} МВт${AKT.st('power') === 'LIMITED' ? ' ЛИМИТ' : ''}`, () => `Энергоснабжение: ${AKT.stOf('power')}`],
    ['water', V(1215, -1024, 20), 6, () => `Хвостохранилище${stw('water')} · ${f2((AKT.num('water', 'pond_m3') || 0) / 1e6)} млн м³ (д)`, () => `Хвосты и вода: ${AKT.stOf('water')} · забор ${fmt(AKT.num('water', 'intake_m3h'))} м³/ч · оборот ${fmt(AKT.num('water', 'recycle_m3h'))} м³/ч`],
    ['conc-stock', top('conc-stock', 35), 7, () => `Концентрат · ${AKT.vsBase('conc-stock', 'stock_t', fmt, 50)} т`, () => `Склад концентрата (схема): ${AKT.stOf('conc-stock')} · из ${fmt(AKT.pass('conc-stock', 'capacity_t'))} т`],
  ];
  for (const [k, p, pr, t, ti] of L0) if (p) addLabel(k, p, pr, t, ti, k);
  for (const n of AKT.ofType('exc')) { const p = top(n, 45); if (p) addLabel(n, p, 6, () => AKT.levelOf(n) ? `${AKT.LV_GLYPH[AKT.levelOf(n)]} Экскаватор ${n.slice(-1)}${stw(n, ['DIG'])} · ${fmt(AKT.num(n, 'tph'))} т/ч` : '', () => `Экскаватор ${n.slice(-1)} (место — схема): ${AKT.stOf(n)}`, n); }
  const issueLabels = {};
  const extraLabels = {};

  /* ---------------------------------------------------------- camera */
  const PRESETS = {
    site: { t: [1700, 1900, 0], dist: 9800, az: 0.0, el: 1.08 },
    pit: { t: [pc[0], pc[1], -110], dist: 3600, az: -0.35, el: 0.62 },
    plant: { t: [1350, 900, 0], dist: 2900, az: 0.25, el: 0.55 },
  };
  const cam = { t: new THREE.Vector3(), dist: 9000, az: 0, el: 0.9 };
  const setPreset = (k) => {
    const p = PRESETS[k]; cam.t.copy(V(p.t[0], p.t[1], p.t[2])); cam.dist = p.dist; cam.az = p.az; cam.el = p.el;
    bar.querySelectorAll('[data-cam]').forEach(b => b.classList.toggle('on', b.dataset.cam === k));
    const sub = document.getElementById('s3-view');
    if (sub) sub.textContent = { site: 'Вся площадка: карьер, дробилки, склады руды, фабрика, хвостохранилище и ЛЭП.', pit: 'Карьер: экскаваторы, самосвалы на съездах, дробилки у карьера.', plant: 'Фабрика: склады руды, две линии помола и флотации, склад концентрата.' }[k] + ' Серое работает как надо, цвет — только у отклонений; ≈ — расчёт модели.';
    dirty = true;
  };
  const applyCam = () => {
    const ce = Math.cos(cam.el);
    camera.position.set(cam.t.x + cam.dist * ce * Math.sin(cam.az), cam.t.y + cam.dist * Math.sin(cam.el), cam.t.z + cam.dist * ce * Math.cos(cam.az));
    camera.lookAt(cam.t);
  };
  bar.querySelectorAll('[data-cam]').forEach(b => b.addEventListener('click', () => setPreset(b.dataset.cam)));

  /* --------------------------------------------------------- controls */
  let drag = null, dirty = true;
  const onDown = ev => { canvas.setPointerCapture(ev.pointerId); drag = { x: ev.clientX, y: ev.clientY, x0: ev.clientX, y0: ev.clientY, pan: ev.button === 2 || ev.shiftKey }; };
  const onMove = ev => {
    if (!drag) return;
    const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y; drag.x = ev.clientX; drag.y = ev.clientY;
    if (drag.pan) {
      const k = cam.dist * 0.0012;
      const right = new THREE.Vector3(Math.cos(cam.az), 0, -Math.sin(cam.az)), fwd = new THREE.Vector3(-Math.sin(cam.az), 0, -Math.cos(cam.az));
      cam.t.addScaledVector(right, -dx * k).addScaledVector(fwd, dy * k);
    } else {
      cam.az -= dx * 0.006; cam.el = Math.max(0.12, Math.min(1.5, cam.el + dy * 0.005));
    }
    bar.querySelectorAll('[data-cam]').forEach(b => b.classList.remove('on'));
    dirty = true;
  };
  const onUp = ev => {
    if (!drag) return;
    const click = Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) < 4 && !drag.pan;
    drag = null;
    if (click) pick(ev);
  };
  const onWheel = ev => { ev.preventDefault(); cam.dist = Math.max(250, Math.min(30000, cam.dist * Math.exp(ev.deltaY * 0.0012))); dirty = true; };
  const onCtx = ev => ev.preventDefault();
  /* keyboard: arrows turn and tilt, +/- zoom, 0 — the default view */
  const onKey = ev => {
    const k = ev.key;
    if (k === 'ArrowLeft') cam.az += 0.08; else if (k === 'ArrowRight') cam.az -= 0.08;
    else if (k === 'ArrowUp') cam.el = Math.min(1.5, cam.el + 0.06); else if (k === 'ArrowDown') cam.el = Math.max(0.12, cam.el - 0.06);
    else if (k === '+' || k === '=') cam.dist = Math.max(250, cam.dist / 1.2); else if (k === '-' || k === '_') cam.dist = Math.min(30000, cam.dist * 1.2);
    else if (k === '0') { setPreset('site'); ev.preventDefault(); return; }
    else return;
    ev.preventDefault(); bar.querySelectorAll('[data-cam]').forEach(b => b.classList.remove('on')); dirty = true;
  };
  canvas.addEventListener('keydown', onKey);
  canvas.addEventListener('pointerdown', onDown); canvas.addEventListener('pointermove', onMove);
  canvas.addEventListener('pointerup', onUp); canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('contextmenu', onCtx);
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  function pick(ev) {
    const r = canvas.getBoundingClientRect();
    ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObjects(pickables, false).find(h => h.object.userData.thing);
    if (hit && AKT.things[hit.object.userData.thing]) location.href = `?view=unit&id=${AKT.id(hit.object.userData.thing)}`;
  }
  canvas.addEventListener('webglcontextlost', ev => { ev.preventDefault(); stop(); if (onFail) onFail('потерян контекст WebGL'); });

  /* ----------------------------------------------------------- update */
  const colorOf = n => COLORS[AKT.levelCls(n)] || COLORS['st-grey'];
  function update() {
    const chain = AKT.scenarioChain();
    for (const n in stateMeshes) for (const m of stateMeshes[n]) {
      m.material.color.setHex(colorOf(n));
      m.material.emissive.setHex(chain.has(n) ? (AKT.hatchOn() ? 0x1f5fbf : 0xe8a000) : 0x000000);
      m.material.emissiveIntensity = chain.has(n) ? 0.35 : 0;
    }
    for (const n in piles) {
      const lvl = AKT.num(n, 'level_t'), live = AKT.pass(n, 'live_t') || 40000;
      const r = 170 * Math.sqrt(Math.max(0.03, Math.min(1, (lvl || 0) / live))), h = Math.max(6, r * 0.5);
      piles[n].scale.set(r, h, r); piles[n].position.y = h / 2;
      piles[n].material.emissive.setHex(chain.has(n) ? (AKT.hatchOn() ? 0x1f5fbf : 0xe8a000) : 0); piles[n].material.emissiveIntensity = chain.has(n) ? 0.35 : 0;
    }
    for (const n in belts) {
      const b = belts[n];
      const tph = b.sag ? (AKT.num(n, 'out_tph') ?? AKT.num(b.sag, 'feed_tph')) : AKT.num(n, 'tph');
      const st = b.sag ? AKT.st(b.sag) : AKT.st(n);
      b.stopped = AKT.stopped(st) || (tph != null && tph < 1);
      b.speed = b.stopped ? 0 : 0.25 + 1.6 * Math.min(1, (tph || 0) / 4880);   // texture repeats per second ∝ t/h
      b.mat.color.setHex(b.stopped ? 0xc62828 : (chain.has(n) ? (AKT.hatchOn() ? 0x9fc0f0 : 0xf1dca0) : 0xffffff));
    }
    for (const n in machines) { const lv = AKT.levelOf(n); machines[n].mat.color.setHex(lv === 1 ? 0xc62828 : lv ? 0xe8a000 : 0xb9bec6); }
    updateTrucks();
    updateExtras(chain);
    updateIssues();
    for (const L of labels) {
      const t = L.text();
      if (t !== L.last) { L.el.textContent = t; L.last = t; L.w = 0; }
      L.el.style.display = t ? '' : 'none';
      const ti = (L.title ? L.title() : t) + ' · нажмите — карточка';
      if (L.el.title !== ti) L.el.title = ti;
      const cls = `s3l ${L.issue ? 'lv-' + AKT.issueLevel(L.st) : (L.st ? AKT.levelCls(L.st) : 'st-grey')}${L.st && AKT.hatchOn() && chain.has(L.st) ? ' scen' : ''}${L.extra ? ' s3x' : ''}${L.issue ? ' s3i' : ''}`;
      if (L.el.className !== cls) L.el.className = cls;
    }
    dirty = true;
  }

  function updateTrucks() {
    const things = Object.keys(AKT.things).filter(n => AKT.cat(n) === 'truck' && AKT.pos(n));
    const info = document.getElementById('s3-trucks');
    if (things.length) {
      /* trucks from Ditto: drawn where the twin says, smoothed between polls */
      while (trucks.length > things.length) { const t = trucks.pop(); scene.remove(t.g); }
      things.forEach((n, i) => {
        if (!trucks[i]) trucks.push(Object.assign(mkTruck(), {}));
        const t = trucks[i], p = AKT.pos(n);
        t.name = n; t.target = V(p[0], p[1], heightAt(p[0], p[1]) + 1); t.route = null;
        if (!t.placed) { t.g.position.copy(t.target); t.placed = true; }
        const s = AKT.st(n);
        t.body.material = AKT.stopped(s) ? truckRed : truckMat;
        t.load.visible = /LOAD|HAUL|FULL/.test(s) || AKT.num(n, 'payload_t') > 0 || AKT.num(n, 'load_t') > 0;
        t.body.userData.thing = n; if (!pickables.includes(t.body)) pickables.push(t.body);
      });
      const moving = things.filter(n => !AKT.stopped(AKT.st(n))).length;
      if (info) info.textContent = `самосвалы из Ditto: ${things.length}, в работе ${moving}`;
      return;
    }
    /* no truck things: a scheme of the haul from the fleet twin numbers */
    const ready = AKT.num('fleet', 'trucks_ready'), total = AKT.num('fleet', 'trucks_total'), haul = AKT.num('fleet', 'haul_tph');
    const n = Math.max(0, Math.min(40, Math.round(ready || 0)));
    if (!routes.length || routes.stamp !== AKT.ofType('exc').map(AKT.st).join()) { buildRoutes(); routes.stamp = AKT.ofType('exc').map(AKT.st).join(); }
    while (trucks.length > n) { const t = trucks.pop(); scene.remove(t.g); }
    while (trucks.length < n) { const t = mkTruck(); t.phase = trucks.length; trucks.push(t); }
    trucks.forEach((t, i) => { t.name = null; t.target = null; t.route = routes[i % routes.length]; t.phase = (i / Math.max(1, n)) * 2; t.body.material = truckMat; });
    haulSpeed = haul != null && haul > 0 ? 1 : 0;
    if (info) info.textContent = `схема движения по данным парка: самосвалов готово ${fmt(ready)} из ${fmt(total)}, вывозка ${fmt(haul)} т/ч`;
  }
  let haulSpeed = 1;

  function updateExtras(chain) {
    const seen = new Set();
    for (const x of AKT.extras()) {
      if (x.cat === 'truck') continue;
      const n = x.name;
      if (x.path && !xroads[n]) {
        const pts = x.path.map(p => V(p[0], p[1], heightAt(p[0], p[1]) + 2));
        const line = new THREE.Line(keep(new THREE.BufferGeometry().setFromPoints(pts)), keep(new THREE.LineBasicMaterial({ color: 0x8d6e3f })));
        scene.add(line); xroads[n] = line;
      }
      if (!x.pos) continue;
      seen.add(n);
      let o = extras[n];
      const cat = xGeo[x.cat] ? x.cat : 'other';
      if (!o) {
        const m = new THREE.Mesh(xGeo[cat], keep(new THREE.MeshLambertMaterial({ color: xColor[cat] })));
        m.userData.thing = n; pickables.push(m); scene.add(m);
        o = extras[n] = { m, cat };
        if (['piezo', 'sensor', 'water-trouble', 'fire', 'hpgr', 'face', 'other', 'exc'].includes(x.cat)) {
          const L = addLabel('x:' + n, new THREE.Vector3(), 8, () => xText(n), () => `${AKT.nameRu(n)} (${AKT.typeRu(AKT.type(n))}): ${AKT.stOf(n)}`, n);
          L.extra = true; extraLabels[n] = L;
        }
      }
      const hgt = { person: 13, sensor: 9, piezo: 13, face: 2, 'water-trouble': 16, fire: 23, hpgr: 15, exc: 12, other: 12 }[cat] || 10;
      o.target = V(x.pos[0], x.pos[1], heightAt(x.pos[0], x.pos[1]) + hgt);
      if (!o.placed) { o.m.position.copy(o.target); o.placed = true; }
      const s = AKT.st(n);
      { const lv = cat === 'person' ? 0 : AKT.levelOf(n); o.m.material.color.setHex(lv === 1 ? 0xc62828 : lv ? 0xe8a000 : (cat === 'person' ? 0x454b53 : xColor[cat])); }
      o.m.material.emissive.setHex(chain.has(n) ? (AKT.hatchOn() ? 0x1f5fbf : 0xe8a000) : 0); o.m.material.emissiveIntensity = chain.has(n) ? 0.5 : 0;
      if (extraLabels[n]) extraLabels[n].pos.copy(o.target).add(new THREE.Vector3(0, 30, 0));
    }
    for (const n in extras) if (!seen.has(n)) {
      scene.remove(extras[n].m); pickables.splice(pickables.indexOf(extras[n].m), 1); delete extras[n];
      if (extraLabels[n]) { extraLabels[n].el.remove(); labels.splice(labels.indexOf(extraLabels[n]), 1); delete extraLabels[n]; }
    }
  }
  const xText = n => {
    const t = AKT.thing(n); if (!t) return n;
    /* ISA-101: things in the norm carry no label (tooltip only); a deviation shows its glyph and value */
    const lv = AKT.levelOf(n);
    if (!lv) return '';
    if (AKT.cat(n) === 'piezo') return `${AKT.LV_GLYPH[lv]} ${AKT.nameRu(n).replace(/^Пьезометр дамбы /, '')} · ${f1(AKT.num(n, 'kpa'))} кПа (тревога от ${fmt(AKT.num(n, 'sp_kpa') || 150)})`;
    const f = Object.keys(t.features || {}).find(k => typeof AKT.raw(n, k) === 'number' && AKT.raw(n, k) !== -1 && !['sim_time', 'x', 'y', 'x_m', 'y_m', 'lat', 'lon', 'heartbeat', 'seq'].includes(k));
    const name = AKT.nameRu(n);
    return `${name.length > 18 ? name.slice(0, 17) + '…' : name}${f ? ' · ' + AKT.valText(n, f) : (AKT.st(n) ? ' · ' + AKT.stOf(n) : '')}`;
  };
  function updateIssues() {
    const seen = new Set();
    for (const n of AKT.issues()) {
      if (AKT.rankNo(n) == null) continue;      // rank 99: called, in work — in the panel, not on the scene
      const node = AKT.name(AKT.val(n, 'node') || '');
      let a = node ? (anchor(node) || AKT.pos(node)) : null;
      if (!a && /^(sag|ball|cyclones|flot|rougher|cleaner|thick|filter|pebble)-[12]/.test(node)) a = anchor('line-' + node.match(/-([12])/)[1]);
      if (!a) continue;
      seen.add(n);
      let L = issueLabels[n];
      if (!L) { L = addLabel('i:' + n, new THREE.Vector3(), AKT.rankNo(n) === 1 ? -1 : 0, () => AKT.rankNo(n) == null ? '' : `${AKT.rankSign(n)} ${AKT.nameRu(AKT.issueNode(n))} · ${AKT.issuePrice(n)}`, () => `Беда ${AKT.rankSign(n)}: ${AKT.issueTitle(n)} · ${AKT.issueMoney(n)} · позвать ${AKT.roleAcc(AKT.roleFirst(AKT.issueRole(n)))}`, n); L.issue = true; issueLabels[n] = L; L.el.href = AKT.href('?view=queue'); }
      L.pos.copy(V(a[0], a[1], heightAt(a[0], a[1]) + 95));
    }
    for (const n in issueLabels) if (!seen.has(n)) { issueLabels[n].el.remove(); labels.splice(labels.indexOf(issueLabels[n]), 1); delete issueLabels[n]; }
  }

  /* ----------------------------------------------- labels: place, avoid */
  const OFFS = [[0, 0], [0, -22], [0, 22], [0, -44], [0, 44], [70, 0], [-70, 0], [0, -66], [0, 66]];
  const tmp = new THREE.Vector3();
  function placeLabels(w, h) {
    const placed = [];
    const hit = b => placed.some(p => b.x0 < p.x1 + 2 && b.x1 + 2 > p.x0 && b.y0 < p.y1 + 2 && b.y1 + 2 > p.y0);
    const order = labels.slice().sort((a, b) => a.prio - b.prio);
    for (const L of order) {
      tmp.copy(L.pos).project(camera);
      const vis = tmp.z < 1 && tmp.z > -1 && Math.abs(tmp.x) < 1.1 && Math.abs(tmp.y) < 1.1;
      if (!vis) { if (L.shown !== false) { L.el.style.display = 'none'; L.shown = false; } continue; }
      if (L.shown === false) { L.el.style.display = ''; L.shown = true; }
      if (!L.w) { L.w = L.el.offsetWidth; L.h = L.el.offsetHeight; }
      const px = (tmp.x + 1) / 2 * w, py = (1 - tmp.y) / 2 * h;
      let ok = null;
      for (const [dx, dy] of OFFS) {
        let x0 = px - L.w / 2 + dx, y0 = py - L.h - 4 + dy;
        x0 = Math.max(2, Math.min(w - L.w - 2, x0)); y0 = Math.max(2, Math.min(h - L.h - 22, y0));
        const b = { x0, y0, x1: x0 + L.w, y1: y0 + L.h };
        if (!hit(b)) { ok = b; break; }
      }
      if (!ok) { L.el.style.visibility = 'hidden'; continue; }
      L.el.style.visibility = '';
      placed.push(ok);
      L.el.style.transform = `translate(${Math.round(ok.x0)}px,${Math.round(ok.y0)}px)`;
    }
  }

  /* --------------------------------------------------------------- loop */
  let raf = 0, last = 0, lastLabels = 0, alive = true, size = [0, 0];
  const resize = () => {
    const w = Math.max(200, wrap.clientWidth), h = Math.max(200, wrap.clientHeight);
    if (w === size[0] && h === size[1]) return;
    size = [w, h];
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); dirty = true;
  };
  const ro = new ResizeObserver(resize); ro.observe(wrap);
  const t0 = performance.now();
  const frame = now => {
    if (!alive) return;
    raf = requestAnimationFrame(frame);
    if (document.hidden || now - last < frameMs) return;
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    for (const n in belts) if (belts[n].speed) { belts[n].tex.offset.x -= belts[n].speed * dt; dirty = true; }
    const tt = (now - t0) / 1000;
    for (const t of trucks) {
      if (t.target) { t.g.position.lerp(t.target, 0.08); dirty = true; continue; }
      if (!t.route) continue;
      const u = ((t.phase + tt / 45 * haulSpeed) % 2 + 2) % 2;          // 0..1 loaded to the crusher, 1..2 empty back
      const f = u < 1 ? u : 2 - u;
      const ang = along(t.route, f, t.g.position);
      t.g.rotation.y = u < 1 ? ang : ang + Math.PI;
      t.load.visible = u < 1;
      dirty = true;
    }
    for (const n in extras) { const o = extras[n]; if (o.target && o.m.position.distanceToSquared(o.target) > 1) { o.m.position.lerp(o.target, 0.1); dirty = true; } }
    if (!dirty) return;
    dirty = false;
    applyCam();
    renderer.render(scene, camera);
    if (now - lastLabels > 90) { lastLabels = now; placeLabels(size[0], size[1]); }
  };
  const stop = () => { alive = false; cancelAnimationFrame(raf); };

  /* --------------------------------------------------------------- start */
  resize();
  const focus = opts && opts.focus ? AKT.name(opts.focus) : '';
  const fp = focus ? (anchor(focus) || AKT.pos(focus)) : null;
  if (fp) { setPreset('plant'); cam.t.copy(V(fp[0], fp[1], heightAt(fp[0], fp[1]))); cam.dist = 1500; bar.querySelectorAll('[data-cam]').forEach(b => b.classList.remove('on')); }
  else setPreset('site');
  update();
  raf = requestAnimationFrame(frame);

  return {
    update,
    highlight(node) {
      const a = node ? (anchor(node) || AKT.pos(node) || (/[12]$/.test(node) ? anchor('line-' + node.slice(-1)) : null)) : null;
      if (!a) return;
      cam.t.copy(V(a[0], a[1], heightAt(a[0], a[1]))); cam.dist = Math.min(cam.dist, 2500); dirty = true;
    },
    destroy() {
      stop(); ro.disconnect();
      canvas.removeEventListener('pointerdown', onDown); canvas.removeEventListener('pointermove', onMove);
      canvas.removeEventListener('pointerup', onUp); canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('contextmenu', onCtx); canvas.removeEventListener('keydown', onKey);
      for (const d of disposables) { try { d.dispose(); } catch (e) { /* already gone */ } }
      renderer.dispose();
      try { renderer.forceContextLoss(); } catch (e) { /* ignore */ }
    },
  };
}
