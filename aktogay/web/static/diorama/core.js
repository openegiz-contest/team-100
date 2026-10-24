/* «Диорама» (?view=diorama): весь рудник Актогай как макет на подиуме.
   Ядро: подиум со срезом пород, свет, камера с пресетами «Весь рудник /
   Карьер / Фабрика / Хвосты», вращение и сдвиг мышью и пальцами, слой
   HTML-подписей без наложений (с выносками), привязка к данным Ditto
   (опрос /api/state в app.js, раз в 2 с), клик — карточка вещи, свечение
   бед и пути беды до меди, полупрозрачные блоки для вещей без подробной
   модели. Карьер и дороги — pit.js, расстановка — layout.js; машины,
   фабрика и инфраструктура — модули mining.js, plant.js, infra.js
   (договор — API.md). Без карт теней (пятна-тени), ≤ 30 кадров/с,
   работает на программном WebGL (SwiftShader). Числа — HTML-текст. */
import * as THREE from '../vendor/three-0.160.0/three.module.min.js';
import { makeLayout, PLINTH, PIT, ZONES, NODES, LINES, PolyCurve, pitPolar, pitR, rampAt } from './layout.js';
import { buildPit, STRATA } from './pit.js';

/* модули-строители: файл и подпись для сообщений */
const MODULES = [['mining', 'горные работы'], ['plant', 'фабрика'], ['infra', 'инфраструктура'], ['inspect', 'разбор машин']];
const NB = ' ';
const BG = 0xeef1f4;
const FRAME_MS = 32;                       // не чаще ≈ 30 кадров/с
let FRAME_MS_LITE = 66;                    // лёгкий режим: ≈ 15 кадров/с; на программном WebGL ≈ 8 (ниже, когда это известно)
const LITE_FPS = 20;                       // ниже этого числа кадров в секунду лёгкий режим включается сам
const FOV = 30;

/* Цвета макета: реальные цвета техники и материалов (sRGB). */
export const PALETTE = {
  cat: 0xf2b500, catBlack: 0x2a2a2a, hitachi: 0xef7a1a, komatsu: 0xf1c40f, drill: 0xf2be1a,
  tire: 0x222326, steel: 0x8d949c, steelDark: 0x4b525a, steelLight: 0xbfc5cb, white: 0xf2f2ef, black: 0x26282b,
  concrete: 0xcfcbc3, wall: 0xe4e1da, cladding: 0x6f8aa3, roof: 0x9ea7b1, glass: 0x9cc2d8,
  ore: 0x8a7865, oreLight: 0xa48f75, waste: 0xbcab90, conc: 0x4a463f, copper: 0xb87333,
  water: 0x6ea9c6, pond: 0x86b8c4, beach: 0xd9d1bf, froth: 0xbca96c, slurry: 0x7d7a72,
  belt: 0x30343a, rail: 0x5a514a, sleeper: 0x6e5c49, wagon: 0x7b4b34, person: 0xff7a1a, helmet: 0xffffff,
  road: 0xa69680, steppe: 0xc7b48c,
};
/* свечение: беда (пульсирует), остановка, путь беды до меди, выбранный узел, «работает», внимание */
export const GLOW = { issue: 0xe8a000, alarm: 0xc62828, chain: 0xf0c060, focus: 0xffffff, run: 0x48c8ff, warn: 0xffb020, scen: 0x48a0ff };   // синий — только для учебного сценария
/* цвета состояний ISA-101 (как на плане): серый — норма, жёлтый — отклонение, красный — стоит */
export const ST_COLORS = { 'st-grey': 0xc3c8cf, 'st-yellow': 0xe8a000, 'st-red': 0xc62828, 'st-soon': 0xf1dca0 };

/* пресеты камеры: цель, радиус кадра (у.е.), азимут и высота взгляда (рад) */
const CAMS = [
  ['all', 'Весь рудник', { t: [25, -45, 25], r: 665, az: -0.26, el: 0.8 }],
  ['pit', 'Карьер', { t: [PIT.cx + 10, -60, PIT.cz + 10], r: 300, az: -0.38, el: 0.86 }],
  ['plant', 'Фабрика', { t: [455, 0, -35], r: 255, az: 0.3, el: 0.72 }],
  ['tails', 'Хвосты', { t: [285, 0, 328], r: 290, az: 0.1, el: 0.9 }],
];
const MOD_SKIP = /^(site|batch|issue|mod-.*|validation-.*|baseline|control|journal)$/;

export async function create(AKT, stage, opts, onFail) {
  opts = opts || {};
  const tStart = performance.now();
  const marks = { core: Math.round(tStart) };                 // время загрузки по шагам (мс от начала страницы)
  const esc = AKT.esc;
  const disposables = [];
  const keep = o => { if (o && o.dispose) disposables.push(o); return o; };

  /* ---------------------------------------------------------------- DOM */
  stage.innerHTML = '';
  const bar = document.createElement('div'); bar.id = 'dio-bar';
  /* одна строка над холстом: пресеты камеры, «Пояснения» (обозначения, допущения модулей) — по кнопке */
  bar.innerHTML = `<span class="seg" role="group" aria-label="Камера">${CAMS.map(([k, t]) => `<button data-cam="${k}">${t}</button>`).join('')}</span>
 <button type="button" class="dio-more" aria-expanded="false" aria-controls="dio-sub">Пояснения</button>
 <span class="dio-hint">мышь: вращать · правая кнопка / Shift: сдвиг · колесо: масштаб · щелчок — карточка</span><span id="dio-perf"></span>
 <div class="dio-sub" id="dio-sub" hidden><span class="dio-key k-issue"></span>беда или отклонение · <span class="dio-key k-chain"></span>путь беды до меди · <span class="dio-key k-ghost"></span>вещь без подробной модели · числа — измерены, «≈» — расчёт модели · схема, машины крупнее масштаба; глубина карьера 230${NB}м — факт · мышь: вращать, правая кнопка или Shift — сдвиг, колесо — масштаб, двойной щелчок — приблизить, щелчок по объекту — карточка<span id="dio-notes"></span></div>`;
  stage.appendChild(bar);
  {
    const more = bar.querySelector('.dio-more'), sub = bar.querySelector('.dio-sub');
    let open = false;
    try { open = localStorage.getItem('dio-notes-open') === '1'; } catch (e) { /* хранилище необязательно */ }
    const apply = () => { sub.hidden = !open; more.setAttribute('aria-expanded', String(open)); };
    apply();
    more.addEventListener('click', () => { open = !open; apply(); try { localStorage.setItem('dio-notes-open', open ? '1' : '0'); } catch (e) { /* необязательно */ } });
  }
  /* лёгкий режим (В5): ниже разрешение, ≈ 15 кадров/с, без пульсации, подписи реже; сам включается при fps < 20,
     кнопкой — в любой момент (выбор помнит браузер, ?lite=1 / ?lite=0 — на один раз). Внешний вид иначе прежний. */
  const liteBtn = document.createElement('button'); liteBtn.type = 'button'; liteBtn.className = 'dio-lite-btn';
  liteBtn.textContent = 'Лёгкий режим'; liteBtn.setAttribute('aria-pressed', 'false');
  liteBtn.title = 'Меньше нагрузка на слабом компьютере: ниже разрешение, реже обновление, без пульсации';
  const liteNote = document.createElement('span'); liteNote.className = 'dio-lite'; liteNote.hidden = true;
  { const more = bar.querySelector('.dio-more'); more.after(liteBtn); liteBtn.after(liteNote); }
  const wrap = document.createElement('div'); wrap.id = 'dio-wrap'; stage.appendChild(wrap);
  const canvas = document.createElement('canvas'); canvas.id = 'dio-canvas';
  canvas.setAttribute('role', 'img'); canvas.setAttribute('aria-label', 'Диорама: рудник и фабрика Актогай, схема на подиуме');
  wrap.appendChild(canvas);
  const layer = document.createElement('div'); layer.className = 'dio-labels'; wrap.appendChild(layer);
  const SVGNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(SVGNS, 'svg'); svg.setAttribute('class', 'dio-leaders'); svg.setAttribute('aria-hidden', 'true');
  const leadPath = document.createElementNS(SVGNS, 'path'); leadPath.setAttribute('class', 'dio-lead');
  const dotPath = document.createElementNS(SVGNS, 'path'); dotPath.setAttribute('class', 'dio-dot');
  svg.appendChild(leadPath); svg.appendChild(dotPath); layer.appendChild(svg);
  const scaleNote = document.createElement('div'); scaleNote.className = 'dio-scale'; scaleNote.textContent = 'схема, машины крупнее масштаба';
  /* свежесть данных техники карьера: машины публикуются по очереди, не каждой точкой */
  const freshEl = document.createElement('div'); freshEl.className = 'dio-fresh'; freshEl.hidden = true;
  scaleNote.appendChild(freshEl);
  wrap.appendChild(scaleNote);
  const notesEl = bar.querySelector('#dio-notes'), perfEl = bar.querySelector('#dio-perf');
  const showPerf = AKT.params.get('perf') === '1';

  /* ----------------------------------------------------------- renderer */
  /* программный WebGL (SwiftShader, llvmpipe): без сглаживания, плотность пикселей 1 */
  let soft = false, gpuName = '';
  try {
    const pc = document.createElement('canvas');
    const gl = pc.getContext('webgl2') || pc.getContext('webgl');
    if (gl) {
      const ext = gl.getExtension('WEBGL_debug_renderer_info');
      gpuName = String(ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER));
      soft = /swiftshader|llvmpipe|software|basic render/i.test(gpuName);
      if (soft) FRAME_MS_LITE = 120;
      const lose = gl.getExtension('WEBGL_lose_context'); if (lose) lose.loseContext();
    }
  } catch (e) { /* проба необязательна */ }
  /* ?q=0.7 — плотность пикселей холста вручную (проверка скорости), иначе 1 на программном WebGL */
  const qParam = parseFloat(AKT.params.get('q'));
  /* на программном WebGL — не больше ≈ 0,8 млн пикселей холста (1920 × 1080: плотность ≈ 0,82), иначе 1 */
  const SOFT_PX = 800000;
  const softRatio = () => Math.max(0.6, Math.min(1, Math.sqrt(SOFT_PX / Math.max(1, wrap.clientWidth * wrap.clientHeight))));
  let pixelRatio = qParam > 0.2 && qParam <= 2 ? qParam : (soft ? Math.round(softRatio() * 100) / 100 : Math.min(1.5, window.devicePixelRatio || 1));
  const pixelRatio0 = pixelRatio;
  let lite = false, liteChoice = null;            // liteChoice: null = само по fps, '1' = включён, '0' = выключен руками
  try { liteChoice = localStorage.getItem('dio-lite'); } catch (e) { /* хранилище необязательно */ }
  if (AKT.params.get('lite') === '1' || AKT.params.get('lite') === '0') liteChoice = AKT.params.get('lite');
  let setLite = () => { /* ниже, когда есть холст */ };
  /* холст нужного размера до создания контекста: смена размера буфера на SwiftShader стоит ≈ 0,5 с */
  canvas.width = Math.floor(Math.max(200, wrap.clientWidth) * pixelRatio); canvas.height = Math.floor(Math.max(200, wrap.clientHeight) * pixelRatio);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: !soft, powerPreference: 'high-performance', preserveDrawingBuffer: false });
  /* плотность пикселей ведём сами: буфер холста = размер × pixelRatio, у three.js плотность 1 (одна смена буфера, не две) */
  renderer.shadowMap.enabled = false;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(BG);
  /* без тумана: сетка пола тает к краям сама (туман стоит каждому пикселю каждого материала) */
  const camera = new THREE.PerspectiveCamera(FOV, 1, 10, 20000);
  /* камера: текущее положение плавно догоняет цель (пресет, мышь, клик в панели) */
  const cur = { t: new THREE.Vector3(), dist: 3000, az: -0.5, el: 0.7 };
  const goal = { t: new THREE.Vector3(), dist: 3000, az: -0.5, el: 0.7 };
  let camMoved = true, ghostDirty = true;

  /* -------------------------------------------------------------- light */
  const LIGHT = {
    sky: 0xfdfbf6, ground: 0xb3a894, hemi: 1.9,
    sun: { color: 0xfff5e6, i: 2.0, pos: [-600, 1000, 450] }, fill: { color: 0xdbe6ff, i: 0.55, pos: [700, 380, -650] },
  };
  const hemiL = new THREE.HemisphereLight(LIGHT.sky, LIGHT.ground, LIGHT.hemi); scene.add(hemiL);
  const sun = new THREE.DirectionalLight(LIGHT.sun.color, LIGHT.sun.i); sun.position.set(...LIGHT.sun.pos); scene.add(sun);
  const fill = new THREE.DirectionalLight(LIGHT.fill.color, LIGHT.fill.i); fill.position.set(...LIGHT.fill.pos); scene.add(fill);
  /* Запечённый свет: та же формула, что у MeshLambertMaterial с плоским затенением (r160: полусфера + 2 направленных,
     делённые на π), но посчитанная один раз в цвета вершин. Такие меши рисуются MeshBasicMaterial — на программном
     WebGL это в разы дешевле на пиксель. Для неподвижных поверхностей: подиум, карьер, площадки, здания. */
  const Lsky = new THREE.Color(LIGHT.sky), Lground = new THREE.Color(LIGHT.ground);
  const Lsun = new THREE.Color(LIGHT.sun.color).multiplyScalar(LIGHT.sun.i), Lfill = new THREE.Color(LIGHT.fill.color).multiplyScalar(LIGHT.fill.i);
  const Dsun = new THREE.Vector3(...LIGHT.sun.pos).normalize(), Dfill = new THREE.Vector3(...LIGHT.fill.pos).normalize();
  const lightOf = (n, out) => {
    out.copy(Lground).lerp(Lsky, 0.5 * n.y + 0.5).multiplyScalar(LIGHT.hemi);
    const a = Math.max(0, n.dot(Dsun)), b = Math.max(0, n.dot(Dfill));
    out.r += Lsun.r * a + Lfill.r * b; out.g += Lsun.g * a + Lfill.g * b; out.b += Lsun.b * a + Lfill.b * b;
    return out.multiplyScalar(1 / Math.PI);
  };

  /* ---------------------------------------------------- shared helpers */
  const matCache = new Map();
  /* материал Ламберта по цвету (общий, плоское затенение); o: {flat, emissive, ei, opacity, side, vc} */
  const mat = (hex, o) => {
    o = o || {};
    const key = `${hex}|${o.flat !== false}|${o.emissive || 0}|${o.ei == null ? 1 : o.ei}|${o.opacity == null ? 1 : o.opacity}|${o.side || 0}|${!!o.vc}`;
    if (!matCache.has(key)) {
      matCache.set(key, keep(new THREE.MeshLambertMaterial({
        color: hex, flatShading: o.flat !== false, emissive: o.emissive || 0, emissiveIntensity: o.ei == null ? 1 : o.ei,
        transparent: o.opacity != null && o.opacity < 1, opacity: o.opacity == null ? 1 : o.opacity,
        side: o.side || THREE.FrontSide, vertexColors: !!o.vc,
      })));
    }
    return matCache.get(key);
  };
  const materials = {};
  for (const k of Object.keys(PALETTE)) materials[k] = mat(PALETTE[k]);
  materials.vc = mat(0xffffff, { vc: true });                          // цвета вершин (склеенные части, ctx.merge)
  materials.vcDouble = mat(0xffffff, { vc: true, side: THREE.DoubleSide });
  materials.lampRun = mat(0x23303c, { emissive: GLOW.run, ei: 1 });    // горящий индикатор «работает»
  materials.lampWarn = mat(0x3a2a10, { emissive: GLOW.warn, ei: 1 });
  materials.lampAlarm = mat(0x3c1414, { emissive: GLOW.alarm, ei: 1 });

  const composeMatrix = (p, r, s) => {
    const m = new THREE.Matrix4();
    const pos = p ? (p.isVector3 ? p : new THREE.Vector3(p[0], p[1], p[2])) : new THREE.Vector3();
    const q = new THREE.Quaternion();
    if (r) q.setFromEuler(r.isEuler ? r : new THREE.Euler(r[0] || 0, r[1] || 0, r[2] || 0));
    const sc = s == null ? new THREE.Vector3(1, 1, 1) : (typeof s === 'number' ? new THREE.Vector3(s, s, s) : (s.isVector3 ? s : new THREE.Vector3(s[0], s[1], s[2])));
    return m.compose(pos, q, sc);
  };
  /* склейка частей в одну геометрию с цветами вершин: [{geometry, color, position, rotation, scale | matrix}] */
  const merge = parts => {
    const pos = [], nor = [], col = [];
    const v = new THREE.Vector3(), nm = new THREE.Matrix3(), c = new THREE.Color();
    for (const p of parts) {
      let g = p.geometry;
      if (g.index) g = g.toNonIndexed();
      if (!g.attributes.normal) g.computeVertexNormals();
      const m = p.matrix || composeMatrix(p.position, p.rotation, p.scale);
      nm.getNormalMatrix(m);
      const P = g.attributes.position, N = g.attributes.normal, C = g.attributes.color;
      if (p.color != null) c.set(p.color);
      for (let i = 0; i < P.count; i++) {
        v.fromBufferAttribute(P, i).applyMatrix4(m); pos.push(v.x, v.y, v.z);
        v.fromBufferAttribute(N, i).applyMatrix3(nm).normalize(); nor.push(v.x, v.y, v.z);
        if (p.color == null && C) col.push(C.getX(i), C.getY(i), C.getZ(i)); else col.push(c.r, c.g, c.b);
      }
      if (g !== p.geometry) g.dispose();
    }
    const out = keep(new THREE.BufferGeometry());
    out.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    out.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
    out.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    return out;
  };
  /* Запекание света в цвета вершин: geometry (любая) -> новая неиндексированная с атрибутом color = цвет × свет.
     o.color — цвет (hex), иначе атрибут color геометрии; o.flip: 'up' — нормаль вверх (рельеф, кровли),
     'out' — от точки o.center (стены, баки), иначе как есть. Рисовать с materials.baked / bakedDouble. */
  const bake = (geometry, o) => {
    o = o || {};
    let g = geometry.index ? geometry.toNonIndexed() : geometry;
    if (g !== geometry) { keep(g); geometry.dispose(); }
    if (!g.attributes.normal || o.recompute || g !== geometry) g.computeVertexNormals();
    const P = g.attributes.position, N = g.attributes.normal, C = g.attributes.color;
    const out = new Float32Array(P.count * 3), n = new THREE.Vector3(), l = new THREE.Color(), base = new THREE.Color(o.color != null ? o.color : 0xffffff);
    const ctr = o.center ? (o.center.isVector3 ? o.center : new THREE.Vector3(o.center[0], o.center[1], o.center[2])) : null;
    const f = new THREE.Vector3();
    for (let i = 0; i < P.count; i++) {
      n.fromBufferAttribute(N, i);
      if (o.flip === 'up' && n.y < 0) n.negate();
      else if (o.flip === 'out' && ctr) { f.fromBufferAttribute(P, i).sub(ctr); f.y = 0; if (n.dot(f) < 0) n.negate(); }
      lightOf(n, l);
      const r = (o.color == null && C) ? C.getX(i) : base.r, gg = (o.color == null && C) ? C.getY(i) : base.g, b = (o.color == null && C) ? C.getZ(i) : base.b;
      out[3 * i] = r * l.r; out[3 * i + 1] = gg * l.g; out[3 * i + 2] = b * l.b;
    }
    g.setAttribute('color', new THREE.BufferAttribute(out, 3));
    return g;
  };
  /* меш с материалом палитры -> запечённый (статичные части): цвет материала в вершины, материал baked */
  const bakeMesh = (mesh, o) => {
    const m = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
    const color = m && m.color ? m.color.getHex() : 0xffffff;
    mesh.geometry = bake(mesh.geometry, Object.assign({ color }, o || {}));
    mesh.material = m && m.side === THREE.DoubleSide ? materials.bakedDouble : materials.baked;
    return mesh;
  };
  materials.baked = keep(new THREE.MeshBasicMaterial({ vertexColors: true }));
  materials.bakedDouble = keep(new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }));
  /* цвет поверхности с нормалью n под тем же светом (для MeshBasicMaterial без цветов вершин) */
  const litColor = (hex, n) => new THREE.Color(hex).multiply(lightOf(n || new THREE.Vector3(0, 1, 0), new THREE.Color()));

  /* текстуры на холсте: мягкое пятно (тени), шум степи, лента с рудой */
  const canvasTex = (w, h, draw, srgb) => {
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    draw(c.getContext('2d'), w, h);
    const t = keep(new THREE.CanvasTexture(c));
    if (srgb) t.colorSpace = THREE.SRGBColorSpace;
    return t;
  };
  const blobTex = canvasTex(64, 64, (x, w, h) => {
    const g = x.createRadialGradient(w / 2, h / 2, 2, w / 2, h / 2, w / 2);
    g.addColorStop(0, 'rgba(0,0,0,0.85)'); g.addColorStop(0.55, 'rgba(0,0,0,0.45)'); g.addColorStop(1, 'rgba(0,0,0,0)');
    x.fillStyle = g; x.fillRect(0, 0, w, h);
  });
  const blobGeometry = keep(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2));
  const blobMats = new Map();
  const blobMaterial = (opacity) => {
    const k = Math.round((opacity == null ? 0.3 : opacity) * 100);
    if (!blobMats.has(k)) blobMats.set(k, keep(new THREE.MeshBasicMaterial({ color: 0x000000, map: blobTex, transparent: true, opacity: k / 100, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })));
    return blobMats.get(k);
  };
  materials.blob = blobMaterial(0.3);
  /* пятно-тень под вещью: w × d у.е., ставит вызывающий (mesh.position) */
  const blob = (w, d, opacity) => { const m = new THREE.Mesh(blobGeometry, blobMaterial(opacity)); m.scale.set(w, 1, d); m.renderOrder = 1; return m; };
  const beltCanvas = (() => {
    const c = document.createElement('canvas'); c.width = 128; c.height = 32;
    const x = c.getContext('2d');
    x.fillStyle = '#30343a'; x.fillRect(0, 0, 128, 32);
    const ore = ['#8a7865', '#6f5d4c', '#a48f75', '#7d7a72'];
    for (let i = 0; i < 26; i++) { x.fillStyle = ore[i % ore.length]; x.beginPath(); x.ellipse((i * 37) % 128 + 3, 6 + (i * 13) % 20, 4 + (i % 3), 3 + (i % 2), (i % 5) * 0.6, 0, 2 * Math.PI); x.fill(); }
    return c;
  })();
  /* текстура ленты с рудой: u — вдоль ленты (повтор), сдвиг offset.x ∝ т/ч делает модуль */
  const beltTexture = () => {
    const t = keep(new THREE.CanvasTexture(beltCanvas));
    t.wrapS = THREE.RepeatWrapping; t.wrapT = THREE.ClampToEdgeWrapping; t.colorSpace = THREE.SRGBColorSpace;
    return t;
  };

  /* ------------------------------------------------------- layout, pads */
  const layout = makeLayout(AKT);
  /* площадки (отсыпка, бетон) под зонами: высота верха, цвет */
  const PADS = [
    ['crush', 1.4, 0xcbbfa8], ['stock', 1.4, 0xc2b398], ['plant', 1.6, 0xd2cfc8], ['conc', 1.9, 0xcbc6bc],
    ['power', 1.4, 0xcfd1cc], ['garage', 1.4, 0xccc5b7], ['abk', 1.4, 0xd0ccc3], ['water', 1.4, 0xd0ccc2],
  ].filter(([z]) => ZONES[z] && ZONES[z].x0 != null).map(([z, h, c]) => ({ zone: z, h, c, ...ZONES[z] }));
  let pitHeight = (x, z) => layout.groundAt(x, z);
  /* высота поверхности: площадки, уступы карьера с выемкой съезда, отвал, иначе 0 */
  const heightAt = (x, z) => {
    let h = null;
    for (const p of PADS) if (x >= p.x0 && x <= p.x1 && z >= p.z0 && z <= p.z1) h = Math.max(h == null ? -1e9 : h, p.h);
    return h != null ? h : pitHeight(x, z);
  };

  /* ------------------------------------------------- floor and plinth */
  const W = PLINTH.w, D = PLINTH.d, H = PLINTH.h, BASE = PLINTH.base;
  const floorY = -(H + BASE) - 0.5;
  {
    /* пол — цвет фона (без отдельной плоскости: на программном WebGL каждый пиксель на счету) и светлая сетка,
       которая сама тает к краям (цвета вершин, без тумана: туман стоит ≈ 3 мс кадра на SwiftShader) */
    const gp = [], gcol = [], bg = new THREE.Color(BG), lc = new THREE.Color(0xc4ccd5), lc2 = new THREE.Color(0xd6dce3), cc = new THREE.Color();
    const EXT = 5200, STEP = 100, SEG = 650;
    const fade = (x, z, base) => cc.copy(base).lerp(bg, THREE.MathUtils.smoothstep(Math.hypot(x, z), 1500, EXT));
    for (let k = -EXT; k <= EXT; k += STEP) {
      const base = (k / STEP) % 5 === 0 ? lc : lc2;
      for (let s = -EXT; s < EXT; s += SEG) {
        for (const [x0, z0, x1, z1] of [[k, s, k, s + SEG], [s, k, s + SEG, k]]) {
          if (Math.hypot(x0, z0) > EXT && Math.hypot(x1, z1) > EXT) continue;
          gp.push(x0, floorY, z0, x1, floorY, z1);
          fade(x0, z0, base); gcol.push(cc.r, cc.g, cc.b); fade(x1, z1, base); gcol.push(cc.r, cc.g, cc.b);
        }
      }
    }
    const gg = keep(new THREE.BufferGeometry());
    gg.setAttribute('position', new THREE.Float32BufferAttribute(gp, 3)); gg.setAttribute('color', new THREE.Float32BufferAttribute(gcol, 3));
    const grid = new THREE.LineSegments(gg, keep(new THREE.LineBasicMaterial({ vertexColors: true }))); grid.name = 'grid'; scene.add(grid);
    /* мягкая тень подиума на полу: непрозрачная рамка вокруг подставки, цвет вершин от тени к фону
       (прозрачная текстура на всю площадь стоила ≈ 6 мс кадра) */
    const sx = 46, sz = -34, iw = (W + 22) / 2, id = (D + 22) / 2, spread = 150;
    const dark = new THREE.Color(BG).lerp(new THREE.Color(0x1b2430), 0.42);
    const ring = (cx, cz, w, d) => [[cx - w, cz - d], [cx + w, cz - d], [cx + w, cz + d], [cx - w, cz + d]];
    /* от кромки подставки (тёмное) к сдвинутому от света краю (фон): с тёмной стороны тень шире */
    const inner = ring(0, 0, iw, id), outer = ring(sx, sz, iw + spread, id + spread);
    const sp = [], scol = [];
    for (let i = 0; i < 4; i++) {
      const a = inner[i], b = inner[(i + 1) % 4], A2 = outer[i], B2 = outer[(i + 1) % 4];
      for (const [p, c] of [[a, dark], [A2, bg], [B2, bg], [a, dark], [B2, bg], [b, dark]]) { sp.push(p[0], floorY + 0.3, p[1]); scol.push(c.r, c.g, c.b); }
    }
    const sg0 = keep(new THREE.BufferGeometry());
    sg0.setAttribute('position', new THREE.Float32BufferAttribute(sp, 3)); sg0.setAttribute('color', new THREE.Float32BufferAttribute(scol, 3));
    const sh = new THREE.Mesh(sg0, keep(new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }))); sh.name = 'plinth-shadow'; scene.add(sh);
  }
  {
    /* верх подиума: степь с отверстием карьера по бровке */
    const A = 144, ring = [];
    for (let a = 0; a < A; a++) {
      const th = 2 * Math.PI * a / A, R = pitR(th);
      ring.push(new THREE.Vector2(PIT.cx + R * Math.cos(th), -(PIT.cz + R * Math.sin(th))));
    }
    const shape = new THREE.Shape([new THREE.Vector2(-W / 2, D / 2), new THREE.Vector2(W / 2, D / 2), new THREE.Vector2(W / 2, -D / 2), new THREE.Vector2(-W / 2, -D / 2)]);
    shape.holes.push(new THREE.Path(ring));
    const g = keep(new THREE.ShapeGeometry(shape, 1)).rotateX(-Math.PI / 2);
    /* ровный цвет степи без текстуры: выборка текстуры на всю площадь стоила ≈ 5 мс кадра на SwiftShader */
    const top = new THREE.Mesh(g, keep(new THREE.MeshBasicMaterial({ color: litColor(PALETTE.steppe).multiplyScalar(0.955) })));
    top.name = 'plinth-top'; scene.add(top);

    /* срез подиума: слои пород (как в бортах карьера, схема) с неровными границами */
    const pos = [], col = [], c = new THREE.Color();
    const SEG = 36;
    const sides = [
      [[-W / 2, D / 2], [W / 2, D / 2]], [[W / 2, D / 2], [W / 2, -D / 2]], [[W / 2, -D / 2], [-W / 2, -D / 2]], [[-W / 2, -D / 2], [-W / 2, D / 2]],
    ];
    const bands = [];
    for (let i = 0; i < STRATA.length - 1; i++) bands.push([STRATA[i][0], i + 1 < STRATA.length - 1 ? STRATA[i + 1][0] : -H, STRATA[i][1]]);
    const wob = (b, u, sd) => (b <= 0 || b >= bands.length) ? 0 : 2.4 * Math.sin(u * 9.1 + b * 1.7 + sd) + 1.3 * Math.sin(u * 23.3 + b * 0.9 + 2 * sd);
    sides.forEach(([a, b], sd) => {
      for (let k = 0; k < SEG; k++) {
        const u0 = k / SEG, u1 = (k + 1) / SEG;
        const x0 = a[0] + (b[0] - a[0]) * u0, z0 = a[1] + (b[1] - a[1]) * u0, x1 = a[0] + (b[0] - a[0]) * u1, z1 = a[1] + (b[1] - a[1]) * u1;
        bands.forEach(([yt, yb, hex], bi) => {
          const t0 = yt + wob(bi, u0, sd), t1 = yt + wob(bi, u1, sd), b0 = yb + wob(bi + 1, u0, sd), b1 = yb + wob(bi + 1, u1, sd);
          c.setHex(hex);
          const shade = 1 - 0.12 * ((-(yt + yb) / 2) / H) + 0.03 * Math.sin(k * 1.7 + bi);
          const q = [[x0, t0, z0], [x0, b0, z0], [x1, b1, z1], [x0, t0, z0], [x1, b1, z1], [x1, t1, z1]];
          for (const p of q) { pos.push(p[0], p[1], p[2]); col.push(c.r * shade, c.g * shade, c.b * shade); }
        });
      }
    });
    const sg = keep(new THREE.BufferGeometry());
    sg.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    sg.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    sg.computeVertexNormals();
    scene.add(new THREE.Mesh(bake(sg, { flip: 'out', center: [0, 0, 0] }), materials.bakedDouble));
    /* тёмная подставка с кромкой: только боковые грани (верх скрыт подиумом, низ не виден) */
    const sideBox = (w, h, d) => {
      const b = new THREE.BoxGeometry(w, h, d), idx = b.index.array, keepIdx = [];
      for (const gr of b.groups) if (gr.materialIndex !== 2 && gr.materialIndex !== 3) for (let i = gr.start; i < gr.start + gr.count; i++) keepIdx.push(idx[i]);
      b.setIndex(keepIdx); b.clearGroups();
      return b;
    };
    const base = merge([
      { geometry: sideBox(W + 22, BASE, D + 22), position: [0, -H - BASE / 2, 0], color: 0x2f343b },
      { geometry: sideBox(W + 12, 3, D + 12), position: [0, -H - 1.4, 0], color: 0x434951 },
    ]);
    scene.add(new THREE.Mesh(bake(base), materials.baked));
    /* площадки зон: одна склеенная геометрия */
    const padGeo = merge(PADS.map(p => ({ geometry: new THREE.BoxGeometry(p.x1 - p.x0, p.h + 1, p.z1 - p.z0), position: [(p.x0 + p.x1) / 2, (p.h - 1) / 2, (p.z0 + p.z1) / 2], color: p.c })));
    const pads = new THREE.Mesh(bake(padGeo), materials.baked); pads.name = 'pads'; scene.add(pads);
  }

  /* --------------------------------------------- labels (HTML layer) */
  const labels = [], labelsByKey = new Map();
  let labelOrder = null, labelsDirty = true, textsDirty = true;
  const GLOW_CLS = { issue: 'g-issue', alarm: 'g-alarm', chain: 'g-chain', focus: 'g-focus', scen: 'g-scen' };
  const textOf = L => { try { return typeof L.text === 'function' ? (L.text() ?? '') : (L.text ?? ''); } catch (e) { console.error(e); return ''; } };
  const titleOf = L => { try { return typeof L.title === 'function' ? (L.title() ?? '') : (L.title ?? ''); } catch (e) { return ''; } };
  /* Подпись: key — уникальный ключ; text — строка или функция (вызывается после каждого опроса;
     '' — скрыть; '\n' — вторая строка мелким шрифтом); o: {thing, at (Vector3 или функция), lift,
     prio (0 — всегда видна, больше — уступает), kind ('' | 'zone' | 'plate' | 'small' | 'issue'),
     title, href, maxDist, minDist, align ('above' | 'center'), cls} */
  function label(key, text, o) {
    o = o || {};
    if (labelsByKey.has(key)) labelsByKey.get(key).remove();
    const thing = o.thing !== undefined ? (o.thing ? AKT.name(o.thing) : null) : (AKT.things[key] ? key : null);
    const kind = o.kind || '';
    const href = o.href !== undefined ? o.href : (thing ? `?view=unit&id=${AKT.id(thing)}` : null);
    const el = document.createElement(href && kind !== 'zone' ? 'a' : 'span');
    if (el.tagName === 'A') {
      el.href = AKT.href(href);
      const cat = thing ? AKT.cat(thing) : '';
      if (cat === 'person' || cat === 'crew') el.setAttribute('data-person', thing);
    }
    el.className = 'dl'; el.style.display = 'none';          // показывает раскладка (placeLabels)
    layer.appendChild(el);
    const L = {
      key, el, text, title: o.title, thing, at: o.at || null, lift: o.lift || 0, prio: o.prio == null ? 5 : o.prio, kind,
      maxDist: o.maxDist || 0, minDist: o.minDist || 0, align: o.align || (kind === 'zone' || kind === 'plate' ? 'center' : 'above'),
      cls: o.cls || '', last: null, lastTitle: null, lastCls: '', w: 0, h: 0, vis: 'none', idx: 0, hidden: false, href,
    };
    const handle = {
      el,
      set(t) { L.text = t; refreshLabel(L); labelsDirty = true; },
      setAt(v) { L.at = v; labelsDirty = true; },
      setTitle(t) { L.title = t; refreshLabel(L); },
      hide(h) { L.hidden = !!h; labelsDirty = true; },
      remove() { el.remove(); const i = labels.indexOf(L); if (i >= 0) labels.splice(i, 1); labelsByKey.delete(key); labelOrder = null; labelsDirty = true; },
    };
    L.handle = handle;
    labels.push(L); labelsByKey.set(key, handle); labelOrder = null;
    refreshLabel(L);
    labelsDirty = true;
    return handle;
  }
  function refreshLabel(L) {
    let full0 = String(textOf(L));
    /* a scenario is running: under the name of a node that differs from the run without it, «было → стало» */
    const chg = full0 && L.thing && !['zone', 'plate'].includes(L.kind) && AKT.prop ? AKT.prop.short(L.thing) : '';
    if (chg) full0 = full0.split('\n')[0] + '\n' + chg;
    /* ISA-101: in the norm a label is one line (name and the main number); the second line only for a deviation
       or a trouble — the rest is in the tooltip */
    const lvT = L.thing && AKT.things[L.thing] && !['zone', 'plate', 'issue'].includes(L.kind) ? AKT.levelOf(L.thing) : 0;
    const t = L.kind !== 'issue' && !lvT && !chg && full0.includes('\n') ? full0.split('\n')[0] : full0;
    if (t !== L.last) {
      L.last = t; L.w = 0;
      const lines = t.split('\n');
      if (lines.length === 1) L.el.textContent = t;
      else {
        L.el.textContent = '';
        lines.forEach((s, i) => { const sp = document.createElement('span'); sp.className = i ? 'dl-sub' : 'dl-main'; sp.textContent = s; L.el.appendChild(sp); });
      }
    }
    const ti = titleOf(L);
    const full = (ti || full0.replace(/\n/g, ' · ')) + (L.el.tagName === 'A' ? ' · нажмите — карточка' : '');
    if (full !== L.lastTitle) { L.lastTitle = full; L.el.title = full; }
    let st = '';
    if (L.thing && AKT.things[L.thing] && L.kind !== 'zone' && L.kind !== 'plate' && L.kind !== 'issue') {
      st = AKT.levelCls(L.thing);
    }
    if (L.kind === 'issue' && L.thing && AKT.things[L.thing]) st = 'lv-' + AKT.issueLevel(L.thing);
    const g = L.thing ? GLOW_CLS[glowKind(L.thing)] || '' : '';
    const cls = `dl${L.kind ? ' k-' + L.kind : ''}${st ? ' ' + st : ''}${g ? ' ' + g : ''}${L.cls ? ' ' + L.cls : ''}`;
    if (cls !== L.lastCls) { L.lastCls = cls; L.el.className = cls; L.w = 0; }
  }

  /* раскладка подписей: по важности, у каждой — 11 мест вокруг точки, без наложений; выноски */
  const OFFS = [[0, 0], [0, -1], [0.62, -0.5], [-0.62, -0.5], [0, -2], [0.62, 0.62], [-0.62, 0.62], [0, 1.45], [1.15, 0], [-1.15, 0], [0, -3]];
  let BOTTOM = 24;                   // нижняя полоса холста — под надписью «схема, …» и свежестью данных техники
  const prj = new THREE.Vector3();
  let size = { w: 0, h: 0 };
  function anchorOf(L) {
    let p = null;
    if (typeof L.at === 'function') { try { p = L.at(); } catch (e) { p = null; } } else if (L.at) p = L.at;
    if (!p && L.thing) p = layout.top(L.thing);
    if (!p) return null;
    if (L.lift) { prj.copy(p); prj.y += L.lift; return prj; }
    return prj.copy(p);
  }
  function placeLabels() {
    const w = size.w, h = size.h;
    BOTTOM = Math.max(24, scaleNote.offsetHeight + 8);
    if (!labelOrder) labelOrder = labels.slice().sort((a, b) => a.prio - b.prio || (a.key < b.key ? -1 : 1));
    const todo = [];
    for (const L of labelOrder) {
      let show = !L.hidden && L.last !== '' && !(L.maxDist && cur.dist > L.maxDist) && !(L.minDist && cur.dist < L.minDist);
      let px = 0, py = 0;
      if (show) {
        const a = anchorOf(L);
        if (!a) show = false;
        else {
          a.project(camera);
          /* подпись вещи за краем кадра не прижимается к краю (беды — прижимаются: их видно всегда) */
          const edge = L.prio <= 0 ? 1.05 : 0.97;
          if (a.z > 1 || a.z < -1 || Math.abs(a.x) > edge || Math.abs(a.y) > edge) show = false;
          else { px = (a.x + 1) / 2 * w; py = (1 - a.y) / 2 * h; }
        }
      }
      if (!show) { if (L.vis !== 'none') { L.el.style.display = 'none'; L.vis = 'none'; } continue; }
      if (L.vis === 'none') { L.el.style.display = ''; L.vis = 'shown'; }
      todo.push({ L, px, py });
    }
    for (const o of todo) if (!o.L.w) { o.L.w = o.L.el.offsetWidth; o.L.h = o.L.el.offsetHeight; }
    const placed = [];
    const hit = b => { for (const p of placed) if (b.x0 < p.x1 + 3 && b.x1 + 3 > p.x0 && b.y0 < p.y1 + 2 && b.y1 + 2 > p.y0) return true; return false; };
    let lead = '', dots = '';
    for (const { L, px, py } of todo) {
      const lw = L.w, lh = L.h;
      const bx = px - lw / 2, by = L.align === 'center' ? py - lh / 2 : py - lh - 7;
      const sx = lw * 0.6 + 6, sy = lh + 3;
      let ok = null, idx = -1;
      const order = L.idx ? [L.idx].concat(OFFS.map((_, i) => i).filter(i => i !== L.idx)) : OFFS.map((_, i) => i);
      for (const i of order) {
        let x0 = bx + OFFS[i][0] * sx, y0 = by + OFFS[i][1] * sy;
        x0 = Math.max(2, Math.min(w - lw - 2, x0)); y0 = Math.max(2, Math.min(h - lh - BOTTOM, y0));
        const b = { x0, y0, x1: x0 + lw, y1: y0 + lh };
        if (!hit(b)) { ok = b; idx = i; break; }
      }
      if (!ok && L.prio <= 0) {
        const x0 = Math.max(2, Math.min(w - lw - 2, bx)), y0 = Math.max(2, Math.min(h - lh - BOTTOM, by));
        ok = { x0, y0, x1: x0 + lw, y1: y0 + lh }; idx = 0;
      }
      if (!ok) { if (L.vis !== 'hidden') { L.el.style.visibility = 'hidden'; L.vis = 'hidden'; } continue; }
      if (L.vis !== 'shown') { L.el.style.visibility = ''; L.vis = 'shown'; }
      L.idx = idx;
      placed.push(ok);
      const tf = `translate(${Math.round(ok.x0)}px,${Math.round(ok.y0)}px)`;
      if (L.tf !== tf) { L.tf = tf; L.el.style.transform = tf; }
      if (L.align !== 'center') {
        dots += `M${(px - 2.2).toFixed(1)} ${py.toFixed(1)}a2.2 2.2 0 1 0 4.4 0a2.2 2.2 0 1 0 -4.4 0`;
        const cx = Math.max(ok.x0, Math.min(ok.x1, px)), cy = Math.max(ok.y0, Math.min(ok.y1, py));
        if (Math.hypot(cx - px, cy - py) > 9) lead += `M${px.toFixed(1)} ${py.toFixed(1)}L${cx.toFixed(1)} ${cy.toFixed(1)}`;
      }
    }
    leadPath.setAttribute('d', lead); dotPath.setAttribute('d', dots);
  }

  /* ------------------------------------------- bindings, glow, picking */
  const pickables = [];
  let clickHook = null;              // inspect.js: щелчок по машине открывает разбор (hook(ev) -> true, если обработан)
  const binds = new Map();           // id -> [{mesh, base, assigned}]
  const claimedSet = new Set(), claimFns = [];
  const claim = x => {
    if (typeof x === 'function') claimFns.push(x);
    else for (const id of [].concat(x)) if (id) claimedSet.add(AKT.name(String(id)));
    ghostDirty = true;
  };
  const claimed = id => claimedSet.has(id) || claimFns.some(f => { try { return !!f(id); } catch (e) { return false; } });
  /* клик по мешу — карточка вещи; id — имя вещи или функция (hit) => имя (для InstancedMesh: hit.instanceId);
     o.halo (по умолчанию true): ядро подсвечивает меш по состоянию вещи (беда, остановка, путь до меди, выбор) */
  function onClick(id, mesh, o) {
    o = o || {};
    if (!mesh) return;
    mesh.userData.dio = { id };
    if (!pickables.includes(mesh)) pickables.push(mesh);
    if (typeof id === 'string' && id) {
      const n = AKT.name(id);
      claimedSet.add(n); ghostDirty = true;
      if (o.halo !== false) { if (!binds.has(n)) binds.set(n, []); binds.get(n).push({ mesh, base: mesh.material, assigned: mesh.material }); }
    }
  }
  const variants = new Map(), pulsing = [], GLOW_ISSUE = new THREE.Color(GLOW.issue);
  const variant = (base, kind) => {
    if (!base || !kind) return base;
    const k = base.uuid + '|' + kind;
    if (variants.has(k)) return variants.get(k);
    const m = keep(base.clone());
    if (m.emissive) { m.emissive.setHex(GLOW[kind]); m.emissiveIntensity = kind === 'chain' ? 0.42 : kind === 'scen' ? 0.5 : kind === 'focus' ? 0.25 : 0.6; }
    else if (m.color) m.color.lerp(new THREE.Color(GLOW[kind]), kind === 'focus' ? 0.2 : 0.5);   // запечённый: оттенок
    if (kind === 'issue') pulsing.push({ m, base: base.color ? base.color.clone() : null });
    variants.set(k, m);
    return m;
  };
  let focusId = '';
  const derived = { issues: [], issueNodes: new Set(), chain: new Set(), chainEdges: new Set(), scen: new Set() };
  /* свечение вещи: 'issue' (беда в очереди), 'alarm' (состояние «стоит»), 'chain' (ниже по потоку от беды до меди),
     'focus' (выбрана), '' — нет */
  function glowKind(id) {
    if (!id) return '';
    if (derived.issueNodes.has(id)) return 'issue';
    if (AKT.things[id] && AKT.stopped(AKT.st(id))) return 'alarm';
    if (derived.scen.has(id)) return 'scen';
    if (derived.chain.has(id)) return 'chain';
    if (focusId && id === focusId) return 'focus';
    return '';
  }
  /* the modules know «chain»: a node of a running scenario is on the way of the consequences for them too */
  function glowOf(id) { const g = glowKind(id); return g === 'scen' ? 'chain' : g; }
  function applyGlow() {
    for (const [id, list] of binds) {
      const kind = glowKind(id);
      for (const b of list) {
        if (b.mesh.material !== b.assigned) b.base = b.mesh.material;     // модуль сменил материал сам
        const m = Array.isArray(b.base) ? b.base.map(x => variant(x, kind)) : variant(b.base, kind);
        b.mesh.material = m; b.assigned = m;
      }
    }
  }
  function derive() {
    const issues = AKT.issues().map(n => ({ id: n, node: AKT.name(String(AKT.val(n, 'node') || '')), rank: AKT.num(n, 'rank'), usdH: AKT.num(n, 'loss_usd_h'), st: AKT.st(n) }))
      .filter(i => i.node);
    const issueNodes = new Set(issues.map(i => i.node)), chain = new Set(), chainEdges = new Set();
    for (const i of issues) {
      const waterish = /^(water|piezo)/.test(i.node) || ['water-trouble', 'piezo'].includes(AKT.cat(i.node));
      const q = [i.node], seen = new Set([i.node]);
      while (q.length) {
        const n = q.shift();
        for (const f of AKT.feeds(n)) {
          if (f === 'water' && !waterish) continue;
          chainEdges.add(n + '>' + f);
          if (!seen.has(f)) { seen.add(f); q.push(f); if (!issueNodes.has(f)) chain.add(f); }
        }
      }
    }
    /* a running scenario: the nodes that differ from the run without it (Ditto: baseline) glow blue */
    const scen = AKT.prop && AKT.cmpOpen && AKT.cmpOpen() ? AKT.prop.affected() : new Set();
    Object.assign(derived, { issues, issueNodes, chain, chainEdges, scen });
  }

  /* ----------------------------------------------------------- paths */
  const lineCache = new Map();
  const sampleLine = (pts2, lift) => {
    const out = [];
    for (let i = 0; i < pts2.length; i++) {
      const [x, z] = pts2[i];
      if (i > 0) {
        const [px, pz] = pts2[i - 1], n = Math.max(1, Math.ceil(Math.hypot(x - px, z - pz) / 8));
        for (let k = 1; k < n; k++) { const xx = px + (x - px) * k / n, zz = pz + (z - pz) * k / n; out.push(new THREE.Vector3(xx, heightAt(xx, zz) + lift, zz)); }
      }
      out.push(new THREE.Vector3(x, heightAt(x, z) + lift, z));
    }
    return new PolyCurve(out);
  };
  let pit = null;
  /* кривая по имени (PolyCurve, параметр по длине): дороги карьера из pit.js ('spiral', 'ramp-1', 'ramp-2',
     'road-dump', 'garage', 'face-N', 'haul:face-N:<дорога>') и линии схемы LINES из layout.js (по земле + lift) */
  function pathFor(name, o) {
    if (!name) return null;
    if (pit) { const c = pit.resolvePath(name); if (c) return c; }
    if (LINES[name]) {
      const lift = o && o.lift != null ? o.lift : 1;
      const k = name + '|' + lift;
      if (!lineCache.has(k)) lineCache.set(k, sampleLine(LINES[name], lift));
      return lineCache.get(k);
    }
    return null;
  }
  /* путь человека или машины между вещами (имена или Vector3) по поверхности; из карьера — по съезду */
  function route(a, b, o) {
    const lift = o && o.lift != null ? o.lift : 2;
    const P = v => (v && v.isVector3) ? v.clone() : (v ? (layout.stand(v) || layout.pos(v)) : null);
    const pa = P(a), pb = P(b);
    if (!pa || !pb) return null;
    const pts = [];
    const inPit = p => pitPolar(p.x, p.z).s < 0.995;
    const tOf = p => Math.max(0, Math.min(1, -p.y / PIT.depth));
    const add = (x, z, y) => pts.push(new THREE.Vector3(x, y == null ? heightAt(x, z) + lift : y, z));
    const straight = (p, q) => {
      const n = Math.max(1, Math.ceil(Math.hypot(q.x - p.x, q.z - p.z) / 8));
      for (let i = pts.length ? 1 : 0; i <= n; i++) add(p.x + (q.x - p.x) * i / n, p.z + (q.z - p.z) * i / n);
    };
    const spiral = (t0, t1) => {
      const n = Math.max(2, Math.ceil(Math.abs(t1 - t0) * 160));
      for (let i = 1; i <= n; i++) { const r = rampAt(t0 + (t1 - t0) * i / n); add(r.x, r.z, r.y + 0.5 + lift); }
    };
    const ex = rampAt(0), exit = new THREE.Vector3(ex.x, 0, ex.z);
    let cur = pa;
    if (inPit(pa)) { const t = tOf(pa), r = rampAt(t); straight(pa, new THREE.Vector3(r.x, r.y, r.z)); spiral(t, 0); cur = exit; }
    if (inPit(pb)) {
      const t = tOf(pb), r = rampAt(t);
      if (cur !== exit) straight(cur, exit);
      spiral(0, t); straight(new THREE.Vector3(r.x, r.y, r.z), pb);
    } else straight(cur, pb);
    return new PolyCurve(pts);
  }

  /* ------------------------------------------------------------ notes */
  const note = text => {
    const sp = document.createElement('span'); sp.className = 'dio-note'; sp.textContent = ' · ' + text; notesEl.appendChild(sp);
    return { set(t) { sp.textContent = t ? ' · ' + t : ''; }, remove() { sp.remove(); } };
  };

  /* ------------------------------------------------------------- ctx */
  const ctx = {
    THREE, AKT, scene, camera, layout, PLINTH, PIT, ZONES, NODES, LINES, PolyCurve,
    heightAt, materials, colors: PALETTE, glowColors: GLOW, stColors: ST_COLORS, mat, merge, bake, bakeMesh, litColor, blob, blobGeometry, blobMaterial,
    beltTexture, keep, label, pathFor, route, onClick, claim, claimed, glowOf, note, soft,
    wrap, flyTo: (p, d) => flyTo(p, d), fitDist: r => fitDist(r), rayAt: ev => { setNdc(ev); return ray; }, pickId: ev => pickId(ev), setClickHook: f => { clickHook = f; },
    stateColor: id => ST_COLORS[AKT.levelCls(id)] || ST_COLORS['st-grey'],
    get camDist() { return cur.dist; },
  };

  /* --------------------------------------------------------------- pit */
  marks.scene = Math.round(performance.now());
  /* части сцены по модулям (для замеров ?perf=1): новые дети сцены после build помечаются именем модуля */
  const tagNew = (before, name) => { for (const o of scene.children) if (!before.has(o)) o.userData.mod = o.userData.mod || name; };
  let before = new Set(scene.children);
  pit = buildPit(ctx);
  tagNew(before, 'pit');
  pitHeight = pit.heightAt;
  marks.pit = Math.round(performance.now());
  layout.attachPaths(n => pathFor(n));

  /* ---------------------------------------------------------- modules */
  const mods = [{ name: 'pit', ru: 'карьер', impl: pit }];
  /* модули грузятся параллельно, строятся по порядку; ошибка одного не останавливает остальные */
  const loaded = await Promise.all(MODULES.map(([file]) => import(`./${file}.js`).catch(e => ({ error: e }))));
  for (let i = 0; i < MODULES.length; i++) {
    const [file, ru] = MODULES[i], m = loaded[i];
    try {
      if (m && m.error) throw m.error;
      before = new Set(scene.children);
      const impl = m && typeof m.build === 'function' ? await m.build(ctx) : null;
      tagNew(before, file);
      if (impl) mods.push({ name: file, ru, impl });
    } catch (e) {
      console.error(e);
      note(`часть сцены «${ru}» не построилась: ${e && e.message ? e.message : e}`);
    }
  }

  marks.modules = Math.round(performance.now());

  /* ---------------------------------------- core labels: zones, issues */
  label('plate', 'Актогай: карьер и обогатительная фабрика · схема', { kind: 'plate', prio: 8, at: new THREE.Vector3(0, -H * 0.42, D / 2 + 1), href: null });
  const ZONE_LABELS = ['crush', 'stock', 'plant', 'conc', 'rail', 'tails', 'power', 'garage', 'abk'];
  for (const k of ZONE_LABELS) {
    const z = ZONES[k]; if (!z) continue;
    const at = z.x0 != null ? new THREE.Vector3((z.x0 + z.x1) / 2, 2, z.z1 + 6) : new THREE.Vector3(z.x, 2, z.z1 - 40);
    label('zone:' + k, z.name, { kind: 'zone', prio: 9, at, href: null, maxDist: k === 'abk' || k === 'garage' ? 2000 : 0 });
  }
  const issueLabels = new Map();
  function updateIssueLabels() {
    const seen = new Set();
    for (const i of derived.issues) {
      const id = i.id;
      /* ранг 99 у модуля — беда уже в работе, вне очереди: без подписи на макете (она есть в панели) */
      if (AKT.rankNo(id) == null) continue;
      seen.add(id);
      if (issueLabels.has(id)) continue;
      issueLabels.set(id, label('issue:' + id, () => {
        if (AKT.rankNo(id) == null) return '';
        const node = AKT.issueNode(id);
        return `${AKT.rankSign(id)} ${AKT.placeRu(node)} · ${AKT.issuePrice(id)}\n${AKT.issueMain(id).text}`;
      }, {
        thing: id, kind: 'issue', prio: AKT.rankNo(id) === 1 ? -1 : 0, href: AKT.href('?view=queue'),
        at: () => { const node = AKT.issueNode(id); return node ? layout.top(node, 26) : null; },
        title: () => `Беда ${AKT.rankSign(id)}: ${AKT.issueTitle(id)} · ${AKT.issueMain(id).text} · позвать ${AKT.roleAcc(AKT.roleFirst(AKT.issueRole(id)))}`,
      }));
    }
    for (const [id, h] of issueLabels) if (!seen.has(id)) { h.remove(); issueLabels.delete(id); }
  }

  /* -------------------------------------- ghosts: things without a model */
  /* Вещь из Ditto, которую не нарисовал ни один модуль (claim / onClick), видна полупрозрачным блоком
     в своём месте по layout; цвет — состояние. Один InstancedMesh на все. */
  const GHOST_MAX = 400;
  /* свет запечён в единичный куб (экземпляры только сдвигаются и растягиваются), цвет экземпляра — состояние */
  const ghostGeo = bake(keep(new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0)));
  const ghostMat = keep(new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.62, depthWrite: false }));
  const ghost = new THREE.InstancedMesh(ghostGeo, ghostMat, GHOST_MAX);
  ghost.count = 0; ghost.frustumCulled = false; ghost.renderOrder = 2; ghost.name = 'ghosts';
  scene.add(ghost);
  const ghostIds = [], ghostPos = new Map(), ghostLabels = new Map();
  onClick(hit => ghostIds[hit.instanceId], ghost, { halo: false });
  const CAT_SIZE = { truck: [12, 8, 7], exc: [15, 13, 12], dozer: [9, 6, 6], drill: [6, 15, 6], person: [5, 11, 5], crew: [8, 8, 8],
    face: [16, 1.5, 16], road: [10, 1.5, 10], piezo: [4, 12, 4], sensor: [6, 8, 6], 'water-trouble': [10, 6, 10], fire: [10, 14, 10], hpgr: [20, 14, 16], other: [8, 8, 8] };
  const TYPE_H = { line: 1.2, water: 3 };
  const ghostSize = id => {
    const n = NODES[id], t = AKT.type(id);
    if (n) { const w = n.w || (n.r ? 2 * n.r : 20), d = n.d || (n.r ? 2 * n.r : 20); return [w, TYPE_H[t] || Math.max(2, n.h || 10), d]; }
    return CAT_SIZE[AKT.cat(id)] || CAT_SIZE.other;
  };
  /* главное число заготовки: первое из списка, у которого в Ditto есть единица измерения */
  const PRIMARY = ['tph', 'feed_tph', 'level_t', 'stock_t', 'cake_tph', 'p80_um', 'recovery', 'kpa', 'site_mw', 'pond_m3', 'power_kw'];
  const ghostPrio = id => {
    const t = AKT.type(id), c = AKT.cat(id);
    if (t === 'line') return 1;
    if (['crusher', 'stockpile', 'conc-stock', 'water', 'power', 'conveyor'].includes(t)) return 2;
    if (['sag', 'ball', 'flot', 'thick', 'filter', 'pebble', 'cyclones', 'rougher', 'cleaner'].includes(t)) return 3;
    if (c === 'exc') return 4;
    if (c === 'person' || c === 'crew') return 5;
    return NODES[id] ? 6 : 7;
  };
  const ghostText = id => {
    const c = AKT.cat(id);
    if (c === 'person') return AKT.personLabel(AKT.personInfo(id));
    if (c === 'crew') { const s = AKT.st(id); return `${AKT.shortName(id)}${s && s !== 'FREE' ? ' · ' + AKT.stOf(id) : ''}`; }
    const dev = AKT.deviates(id);
    if (AKT.QUIET_CATS.has(c) && !NODES[id] && !dev) return '';
    /* machines in repair: one summary at the fleet («в ремонте: …»), not a label each */
    if (AKT.MACHINE_CATS.has(c) && AKT.stopped(AKT.st(id))) return '';
    const f = PRIMARY.find(k => AKT.num(id, k) != null && AKT.unit(id, k));
    return `${AKT.shortName(id)}${f ? ' · ' + AKT.valText(id, f) : ''}${dev || AKT.stopped(AKT.st(id)) ? ' · ' + AKT.stOf(id) : ''}`;
  };
  const gm = new THREE.Matrix4(), gq = new THREE.Quaternion(), gs = new THREE.Vector3(), gp = new THREE.Vector3(), gc = new THREE.Color();
  function updateGhosts() {
    const ids = Object.keys(AKT.things).filter(id => !MOD_SKIP.test(AKT.type(id)) && !claimed(id)).sort(AKT.cmpNames);
    const groups = new Map(), pos = new Map();
    for (const id of ids) {
      const p = layout.pos(id); if (!p) continue;
      pos.set(id, p);
      if (NODES[id]) continue;
      const k = Math.round(p.x / 4) + ':' + Math.round(p.z / 4);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(id);
    }
    for (const g of groups.values()) if (g.length > 1) g.forEach((id, i) => {
      const p = pos.get(id), r = 11 * Math.sqrt(i + 0.6), a = 2.39996 * i;
      p.x += r * Math.cos(a); p.z += r * Math.sin(a); p.y = heightAt(p.x, p.z);
    });
    ghostIds.length = 0;
    let i = 0;
    for (const [id, p] of pos) {
      if (i >= GHOST_MAX) break;
      const [w, h, d] = ghostSize(id);
      const y = NODES[id] ? Math.max(p.y, heightAt(p.x, p.z)) : p.y;
      gm.compose(gp.set(p.x, y, p.z), gq, gs.set(w, h, d));
      ghost.setMatrixAt(i, gm);
      const c = AKT.cat(id);
      gc.setHex(c === 'person' ? PALETTE.person : (ST_COLORS[AKT.levelCls(id)] || ST_COLORS['st-grey']));
      const gl = glowKind(id);
      if (gl === 'scen') gc.lerp(new THREE.Color(GLOW.scen), 0.5); else if (gl === 'issue' || gl === 'alarm') gc.lerp(new THREE.Color(GLOW.issue), 0.5); else if (gl === 'chain') gc.lerp(new THREE.Color(GLOW.chain), 0.45);
      ghost.setColorAt(i, gc);
      ghostIds[i] = id;
      ghostPos.set(id, new THREE.Vector3(p.x, y + h, p.z));
      if (!ghostLabels.has(id)) {
        const cat = AKT.cat(id);
        ghostLabels.set(id, label('ghost:' + id, () => ghostText(id), {
          thing: id, prio: ghostPrio(id), at: () => ghostPos.get(id) || null, lift: 3,
          kind: NODES[id] && ghostPrio(id) <= 3 ? '' : 'small',
          maxDist: ghostPrio(id) <= 3 ? 0 : (cat === 'person' || cat === 'crew' ? 2600 : 1900),
        }));
      }
      i++;
    }
    ghost.count = i;
    ghost.instanceMatrix.needsUpdate = true;
    if (ghost.instanceColor) ghost.instanceColor.needsUpdate = true;
    ghost.computeBoundingSphere();
    for (const [id, h] of ghostLabels) if (!ghostIds.includes(id)) { h.remove(); ghostLabels.delete(id); ghostPos.delete(id); }
    ghostDirty = false;
  }

  /* ----------------------------------------------------------- camera */
  const fitDist = r => {
    const v = THREE.MathUtils.degToRad(FOV) / 2, hz = Math.atan(Math.tan(v) * Math.max(0.3, camera.aspect));
    return r / Math.sin(Math.min(v, hz));
  };
  const LIM = { dmin: 90, dmax: 6000, elmin: 0.16, elmax: 1.45 };
  function setPreset(k, instant) {
    const c = CAMS.find(x => x[0] === k) || CAMS[0], p = c[2];
    goal.t.set(p.t[0], p.t[1], p.t[2]); goal.dist = fitDist(p.r); goal.az = p.az; goal.el = p.el;
    if (instant) { cur.t.copy(goal.t); cur.dist = goal.dist; cur.az = goal.az; cur.el = goal.el; }
    bar.querySelectorAll('[data-cam]').forEach(b => b.classList.toggle('on', b.dataset.cam === c[0]));
    camMoved = true;
  }
  /* пресет в адресе (?cam=pit): перезагрузка открывает тот же вид */
  const rememberCam = k => { try { const q = new URLSearchParams(location.search); q.set('cam', k); q.delete('focus'); history.replaceState(null, '', '?' + q.toString()); } catch (e) { /* адрес необязателен */ } };
  const clearPreset = () => bar.querySelectorAll('[data-cam]').forEach(b => b.classList.remove('on'));
  function flyTo(p, dist) {
    goal.t.copy(p); if (dist) goal.dist = Math.max(LIM.dmin, Math.min(LIM.dmax, dist));
    clearPreset(); camMoved = true;
  }
  const clampTarget = () => {
    goal.t.x = Math.max(-W / 2 - 150, Math.min(W / 2 + 150, goal.t.x));
    goal.t.z = Math.max(-D / 2 - 150, Math.min(D / 2 + 150, goal.t.z));
    goal.t.y = Math.max(-PIT.depth, Math.min(60, goal.t.y));
  };
  function stepCamera(dt) {
    const k = 1 - Math.exp(-dt * 7);
    const close = cur.t.distanceToSquared(goal.t) < 0.01 && Math.abs(cur.dist - goal.dist) < 0.05 && Math.abs(cur.az - goal.az) < 1e-4 && Math.abs(cur.el - goal.el) < 1e-4;
    if (!close) {
      cur.t.lerp(goal.t, k); cur.dist += (goal.dist - cur.dist) * k; cur.az += (goal.az - cur.az) * k; cur.el += (goal.el - cur.el) * k;
      camMoved = true;
    }
    if (!camMoved) return false;
    const ce = Math.cos(cur.el);
    camera.position.set(cur.t.x + cur.dist * ce * Math.sin(cur.az), cur.t.y + cur.dist * Math.sin(cur.el), cur.t.z + cur.dist * ce * Math.cos(cur.az));
    camera.lookAt(cur.t);
    camera.near = Math.max(4, cur.dist / 40); camera.far = cur.dist * 3 + 9000; camera.updateProjectionMatrix();

    return true;
  }
  bar.querySelectorAll('[data-cam]').forEach(b => b.addEventListener('click', () => { setPreset(b.dataset.cam); rememberCam(b.dataset.cam); }));

  /* --------------------------------------------------------- controls */
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2(), plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), tmpV = new THREE.Vector3();
  const setNdc = ev => { const r = canvas.getBoundingClientRect(); ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1); ray.setFromCamera(ndc, camera); };
  const pointers = new Map();
  let drag = null, pinch = null;
  const onDown = ev => {
    canvas.setPointerCapture(ev.pointerId);
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 }; drag = null;
    } else drag = { x: ev.clientX, y: ev.clientY, x0: ev.clientX, y0: ev.clientY, pan: ev.button === 2 || ev.shiftKey, moved: false };
  };
  const pan = (dx, dy) => {
    const k = cur.dist * 0.00115;
    const right = tmpV.set(Math.cos(cur.az), 0, -Math.sin(cur.az));
    goal.t.addScaledVector(right, -dx * k);
    /* вперёд по земле — от камеры; на пологом взгляде шаг длиннее */
    const f = dy * k / Math.max(0.35, Math.sin(cur.el));
    goal.t.x += -Math.sin(cur.az) * f; goal.t.z += -Math.cos(cur.az) * f;
    clampTarget();
  };
  let hoverAt = 0;
  const onMove = ev => {
    if (pointers.has(ev.pointerId)) pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (pinch && pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y), mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      if (pinch.d > 0 && d > 0) { goal.dist = Math.max(LIM.dmin, Math.min(LIM.dmax, goal.dist * pinch.d / d)); }
      pan(mx - pinch.mx, my - pinch.my);
      pinch = { d, mx, my }; clearPreset(); camMoved = true;
      return;
    }
    if (drag) {
      const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y; drag.x = ev.clientX; drag.y = ev.clientY;
      if (Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) > 4) drag.moved = true;
      if (!drag.moved) return;
      if (drag.pan) pan(dx, dy);
      else {
        goal.az -= dx * 0.0055; goal.el = Math.max(LIM.elmin, Math.min(LIM.elmax, goal.el + dy * 0.0045));
        cur.az = goal.az; cur.el = goal.el;
      }
      clearPreset(); camMoved = true;
      return;
    }
    /* подсказка под указателем: имя и состояние вещи */
    const now = performance.now();
    if (now - hoverAt < 120) return;
    hoverAt = now;
    const id = pickId(ev);
    canvas.style.cursor = id ? 'pointer' : '';
    const t = id ? `${AKT.nameRu(id)}: ${AKT.stOf(id)} · нажмите — карточка` : '';
    if (canvas.title !== t) canvas.title = t;
  };
  const onUp = ev => {
    pointers.delete(ev.pointerId);
    if (pointers.size < 2) pinch = null;
    if (!drag) return;
    const click = !drag.moved && !drag.pan && ev.button === 0;
    drag = null;
    if (click) {
      if (clickHook) { let used = false; try { used = !!clickHook(ev); } catch (e) { console.error(e); } if (used) return; }
      const id = pickId(ev);
      if (!id) return;
      const cat = AKT.cat(id);
      if ((cat === 'person' || cat === 'crew') && AKT.personCard) AKT.personCard.open(id, ev.clientX, ev.clientY);
      else location.href = AKT.href(`?view=unit&id=${AKT.id(id)}`);
    }
  };
  const onWheel = ev => {
    ev.preventDefault();
    const old = goal.dist;
    goal.dist = Math.max(LIM.dmin, Math.min(LIM.dmax, goal.dist * Math.exp(ev.deltaY * 0.0011)));
    /* приближение к точке под указателем */
    setNdc(ev); plane.constant = -goal.t.y;
    if (ray.ray.intersectPlane(plane, tmpV)) { goal.t.addScaledVector(tmpV.sub(goal.t), 1 - goal.dist / old); clampTarget(); }
    clearPreset(); camMoved = true;
  };
  const onDbl = ev => {
    setNdc(ev);
    const h = ray.intersectObjects(pickables, false)[0];
    let p = h ? h.point.clone() : null;
    if (!p) { plane.constant = 0; if (ray.ray.intersectPlane(plane, tmpV)) p = tmpV.clone(); }
    if (p) { flyTo(p, goal.dist * 0.55); clampTarget(); }
  };
  const onCtx = ev => ev.preventDefault();
  function pickId(ev) {
    setNdc(ev);
    const hits = ray.intersectObjects(pickables, false);
    for (const h of hits) {
      const d = h.object.userData.dio; if (!d) continue;
      let id = d.id;
      if (typeof id === 'function') { try { id = id(h); } catch (e) { id = null; } }
      if (id && AKT.things[AKT.name(id)]) return AKT.name(id);
    }
    return null;
  }
  canvas.addEventListener('pointerdown', onDown); canvas.addEventListener('pointermove', onMove);
  canvas.addEventListener('pointerup', onUp); canvas.addEventListener('pointercancel', onUp);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('dblclick', onDbl); canvas.addEventListener('contextmenu', onCtx);

  /* ----------------------------------------------------------- state */
  /* то, что получают модули в update(state, dt); fresh = true один кадр после каждого опроса Ditto */
  const state = {
    AKT, fresh: true, t: 0, dt: 0, simNow: null, simRate: 0, paused: true, stale: false,
    issues: derived.issues, issueNodes: derived.issueNodes, chain: derived.chain, chainEdges: derived.chainEdges,
    focus: '', camDist: 0, glowOf,
  };
  const simRate = () => { const f = AKT.num('site', 'speed_fact'); return f != null && f > 0 ? f / 60 : 0; };   // мин модели в секунду

  /* «данные техники обновляются раз в ~N мин модели · обновлено M с назад»: N — разброс времени модели
     у самосвалов (они идут в Ditto по очереди), M — сколько секунд назад Ditto получил самое свежее */
  function updateFresh() {
    const ids = AKT.ofType('truck').concat(AKT.ofType('exc'), AKT.ofType('drill'), AKT.ofType('dozer'));
    const ts = ids.map(n => AKT.num(n, 'sim_time')).filter(v => v != null && v >= 0);
    const ages = ids.map(n => AKT.modifiedAge(n)).filter(v => v != null);
    if (!ts.length || !ages.length) { freshEl.hidden = true; return; }
    const site = AKT.num('site', 'sim_time');
    const spread = Math.max(...ts) - Math.min(...ts), lag = site != null ? Math.max(0, site - Math.min(...ts)) : null;
    const every = Math.max(5, Math.ceil((spread + 5) / 5) * 5);
    freshEl.textContent = `данные техники карьера обновляются по очереди, каждая машина — раз в ~${AKT.fmt(every)}${NB}мин модели`
      + `${lag != null && lag >= 5 ? ` (самые старые — на ${AKT.fmt(lag)}${NB}мин модели позади)` : ''} · обновлено ${AKT.fmt(Math.min(...ages))}${NB}с назад`
      + ' · между обновлениями — движение по циклу модели (схема)';
    freshEl.hidden = false;
  }

  function update() {
    layout.refresh();
    derive();
    updateFresh();
    Object.assign(state, { issues: derived.issues, issueNodes: derived.issueNodes, chain: derived.chain, chainEdges: derived.chainEdges, fresh: true, stale: !!AKT.err });
    state.simRate = simRate(); state.paused = state.simRate === 0;
    updateIssueLabels();
    ghostDirty = true;
    applyGlow();
    textsDirty = true;
  }

  /* --------------------------------------------------------------- loop */
  let raf = 0, last = 0, alive = true, lastPlace = 0, coreErr = 0, firstFrame = 0;
  const perf = { frames: 0, cost: 0, at: performance.now(), slow: 0, fast: 0, low: 0, hist: [], sample: false, full: 0, px: new Uint8Array(4) };
  const resize = () => {
    const w = Math.max(200, wrap.clientWidth), h = Math.max(200, wrap.clientHeight);
    if (w === size.w && h === size.h) return;
    size = { w, h };
    const bw = Math.floor(w * pixelRatio), bh = Math.floor(h * pixelRatio);
    if (canvas.width !== bw || canvas.height !== bh) renderer.setSize(bw, bh, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`); svg.setAttribute('width', w); svg.setAttribute('height', h);
    camMoved = true;
  };
  const ro = new ResizeObserver(resize); ro.observe(wrap);
  setLite = (on, auto) => {
    if (on === lite && !auto) return;
    lite = on;
    liteBtn.setAttribute('aria-pressed', String(on));
    liteNote.hidden = !on;
    /* a short note in the bar (it must not wrap at 1280 px); the reason and what the button does are in its tooltip */
    liteNote.textContent = on ? (auto === 'soft' ? 'без видеокарты' : auto ? `меньше ${LITE_FPS} кадров/с` : '') : '';
    liteNote.hidden = !on || !liteNote.textContent;
    liteNote.title = on ? `Лёгкий режим${auto === 'soft' ? ': нет видеокарты, сцену считает процессор' : auto ? `: включился сам, меньше ${LITE_FPS} кадров/с` : ''}. Ниже разрешение, ≈ 15 кадров в секунду, подписи реже, без пульсации беды. Кнопка «Лёгкий режим» возвращает прежний вид.` : '';
    pixelRatio = on ? Math.min(pixelRatio, 0.6) : pixelRatio0; size = { w: 0, h: 0 }; resize();
    perf.slow = 0; perf.fast = 0; perf.low = 0; perf.hist.length = 0; labelsDirty = true;
    if (on) for (const p of pulsing) { if (p.m.emissive) p.m.emissiveIntensity = 0.5; else if (p.base) p.m.color.copy(p.base).lerp(GLOW_ISSUE, 0.5); }
  };
  liteBtn.addEventListener('click', () => {
    const on = !lite;
    liteChoice = on ? '1' : '0';
    try { localStorage.setItem('dio-lite', liteChoice); } catch (e) { /* необязательно */ }
    setLite(on, false);
  });
  const frame = now => {
    if (!alive) return;
    raf = requestAnimationFrame(frame);
    if (document.hidden) { perf.frames = 0; perf.cost = 0; perf.at = now; perf.low = 0; return; }
    if (now - last < (lite ? FRAME_MS_LITE : FRAME_MS)) return;
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    const c0 = performance.now();
    try {
      const moved = stepCamera(dt);
      state.t = (now - tStart) / 1000; state.dt = dt; state.focus = focusId; state.camDist = cur.dist; state.lite = lite;
      const since = Math.min(2.5, Math.max(0, Date.now() / 1000 - AKT.polled));
      state.simNow = AKT.simTime == null ? null : AKT.simTime + since * state.simRate;
      if (ghostDirty) updateGhosts();
      if (textsDirty) { for (const L of labels) refreshLabel(L); textsDirty = false; labelsDirty = true; }
      for (const m of mods) {
        if (!m.impl || !m.impl.update) continue;
        try { m.impl.update(state, dt); } catch (e) {
          console.error(e); m.impl = null; note(`часть сцены «${m.ru}» остановлена: ${e && e.message ? e.message : e}`);
        }
      }
      state.fresh = false;
      if (pulsing.length && !lite) {
        const s = 0.5 + 0.5 * Math.sin(state.t * 4.2), k = 0.35 + 0.45 * s;
        for (const p of pulsing) {
          if (p.m.emissive) p.m.emissiveIntensity = k;
          else if (p.base) p.m.color.copy(p.base).lerp(GLOW_ISSUE, 0.3 + 0.4 * s);
        }
      }
      const r0 = performance.now();
      renderer.render(scene, camera);
      /* раз в секунду дожидаемся растеризации: полная цена кадра на программном WebGL */
      if (perf.sample) {
        perf.sample = false;
        try { const gl = renderer.getContext(); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, perf.px); } catch (e) { /* без замера */ }
        perf.full = performance.now() - c0;
      }
      if (!firstFrame) { firstFrame = performance.now(); marks.firstRender = Math.round(firstFrame - r0); marks.first = Math.round(firstFrame); }
      if (moved || labelsDirty || now - lastPlace > (lite ? 400 : 140)) { lastPlace = now; labelsDirty = false; placeLabels(); }
      camMoved = false;
      coreErr = 0;
    } catch (e) {
      console.error(e);
      if (++coreErr > 3) { stop(); if (onFail) onFail('ошибка отрисовки: ' + (e && e.message ? e.message : e)); return; }
    }
    /* счётчик кадров: fps — сколько кадров показано (не больше ≈ 30), fpsEq — сколько успели бы при полной цене
       кадра (с растеризацией); на программном WebGL при fpsEq < 18 снижаем разрешение холста */
    perf.frames++; perf.cost += performance.now() - c0;
    if (now - perf.at >= 1000) {
      const fps = perf.frames * 1000 / (now - perf.at), ms = perf.cost / Math.max(1, perf.frames);
      const full = Math.max(ms, perf.full || ms);
      const info = renderer.info.render;
      const stat = { fps: Math.round(fps * 10) / 10, ms: Math.round(ms * 10) / 10, fullMs: Math.round(full * 10) / 10, fpsEq: Math.round(10000 / Math.max(1, full)) / 10,
        calls: info.calls, tris: info.triangles, firstFrameMs: Math.round(firstFrame), marks, soft, gpu: gpuName, pixelRatio,
        labels: labels.filter(L => L.vis === 'shown').length };
      if (showPerf) window.__dio = stat;
      wrap.dataset.fps = stat.fps; wrap.dataset.fpsEq = stat.fpsEq; wrap.dataset.calls = stat.calls; wrap.dataset.first = stat.firstFrameMs;
      if (showPerf) perfEl.textContent = ` · ${AKT.fmt(stat.fps)} кадр/с (запас до ${AKT.fmt(stat.fpsEq)}) · кадр ${AKT.f1(stat.fullMs)} мс · вызовов отрисовки ${stat.calls} · треугольников ${AKT.fmt(stat.tris)}`;
      /* адаптивное разрешение: не в первые 5 с (компиляция шейдеров, загрузка), по медиане трёх замеров;
         при запасе разрешение возвращается обратно (оценка цены — по площади холста) */
      perf.hist.push(full); if (perf.hist.length > 3) perf.hist.shift();
      const med = perf.hist.slice().sort((a, b) => a - b)[Math.floor(perf.hist.length / 2)];
      const warm = firstFrame && performance.now() - firstFrame > 5000 && perf.hist.length === 3;
      const setPr = v => { pixelRatio = v; size = { w: 0, h: 0 }; resize(); perf.slow = 0; perf.fast = 0; perf.hist.length = 0; };
      if (warm && 1000 / med < 18 && pixelRatio > 0.6) { if (++perf.slow >= 3) setPr(Math.max(0.6, pixelRatio * 0.85)); } else perf.slow = 0;
      if (warm && !lite && pixelRatio < pixelRatio0 && med * Math.pow(Math.min(pixelRatio0, pixelRatio / 0.85) / pixelRatio, 2) < 1000 / 26) { if (++perf.fast >= 5) setPr(Math.min(pixelRatio0, pixelRatio / 0.85)); } else perf.fast = 0;
      if (liteChoice === null && !lite && warm && fps < LITE_FPS) { if (++perf.low >= 3) setLite(true, true); } else if (fps >= LITE_FPS) perf.low = 0;
      perf.frames = 0; perf.cost = 0; perf.at = now; perf.sample = true;
    }
  };
  const stop = () => { alive = false; cancelAnimationFrame(raf); };
  const onLost = ev => { ev.preventDefault(); stop(); if (onFail) onFail('потерян контекст WebGL'); };
  canvas.addEventListener('webglcontextlost', onLost);

  /* --------------------------------------------------------------- start */
  marks.labels = Math.round(performance.now());
  void wrap.clientWidth; marks.layout = Math.round(performance.now());
  resize();
  marks.resize = Math.round(performance.now());
  const focus0 = opts.focus ? AKT.name(opts.focus) : '';
  const fp = focus0 ? layout.pos(focus0) : null;
  setPreset(AKT.params.get('cam') || 'all', true);
  if (fp) { focusId = focus0; flyTo(fp, fitDist(140)); cur.t.copy(goal.t); cur.dist = goal.dist; }
  marks.camera = Math.round(performance.now());
  update();
  marks.ready = Math.round(performance.now());
  /* ?perf=1: точка проверки — что под пикселем и где на экране точка подиума */
  if (showPerf) window.__dioDebug = {
    pick: (x, y) => pickId({ clientX: x, clientY: y }),
    screen: (x, y, z) => { const v = new THREE.Vector3(x, y, z).project(camera), r = canvas.getBoundingClientRect(); return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; },
    route: (a, b) => { const c = route(a, b); return c ? Math.round(c.len) : null; },
    path: n => { const c = pathFor(n); return c ? Math.round(c.len) : null; },
  };
  if (liteChoice === '1') setLite(true, false);
  else if (liteChoice === null && soft) setLite(true, 'soft');     // без видеокарты сцена отнимала у стенда 4 ядра из 8 (23.10)
  raf = requestAnimationFrame(frame);

  return {
    update,
    highlight(node) {
      focusId = node ? AKT.name(node) : '';
      const p = focusId ? layout.pos(focusId) : null;
      if (p) flyTo(p, Math.min(goal.dist, fitDist(160)));
      applyGlow(); textsDirty = true;
    },
    destroy() {
      stop(); ro.disconnect();
      canvas.removeEventListener('pointerdown', onDown); canvas.removeEventListener('pointermove', onMove);
      canvas.removeEventListener('pointerup', onUp); canvas.removeEventListener('pointercancel', onUp);
      canvas.removeEventListener('wheel', onWheel); canvas.removeEventListener('dblclick', onDbl);
      canvas.removeEventListener('contextmenu', onCtx); canvas.removeEventListener('webglcontextlost', onLost);
      for (const m of mods) if (m.impl && m.impl.destroy) { try { m.impl.destroy(); } catch (e) { console.error(e); } }
      for (const d of disposables) { try { d.dispose(); } catch (e) { /* уже освобождён */ } }
      renderer.dispose();
      try { renderer.forceContextLoss(); } catch (e) { /* ignore */ }
      delete window.__dio; delete window.__dioDebug;
    },
  };
}
