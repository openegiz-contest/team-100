/* «Диорама», разбор машин: щелчок по самосвалу, экскаватору, мельнице SAG, дробилке ЦПД, конвейеру, шаровой мельнице, ВВД, флотомашине, гидроциклонам, сгустителю или фильтр-прессу показывает рядом
   подробную модель на подставке (строится при выборе и освобождается при закрытии: пока ничего не выбрано, её нет ни в сцене, ни в памяти видеокарты) и боковую карточку:
   кнопка «Разрез» / «Разобрать», список частей, состояние и сигналы выбранной части (inside.json + живые числа Ditto),
   метка доказательности и ссылка на полную карточку «Изнутри». Часть с открытой бедой (или близким сроком перефутеровки)
   подсвечена на самой модели. Остальные машины и аппараты — по щелчку на карточку «Изнутри». Логика выбора — parts.js. */
import * as P from './parts.js';
import { BUILDERS } from './models.js';

const PLANT = new Set(['crusher', 'conveyor', 'stockpile', 'pebble', 'ball', 'cyclones', 'flot', 'rougher', 'cleaner', 'thick', 'filter', 'conc-stock', 'sag']);

export async function build(ctx) {
  const { THREE, AKT, scene } = ctx;
  const esc = AKT.esc;
  const root = new THREE.Group(); root.visible = false; root.name = 'inspect'; scene.add(root);
  const cache = new Map();                    // вид -> {model, entries}
  let D = null, loading = false;
  const st = { id: '', kind: '', part: '', on: false, k: 0, cur: null, labels: [], panel: null };

  /* ------------------------------------------------------------ описание узлов */
  const loadInside = () => {
    if (D || loading) return; loading = true;
    fetch('/inside.json', { cache: 'no-store' }).then(r => r.json()).then(d => { D = d; render(); }).catch(() => { loading = false; });
  };

  /* ------------------------------------------------------------ модель */
  const mats = {
    base: ctx.materials.vcDouble,
    issue: ctx.mat(0xffffff, { vc: true, side: THREE.DoubleSide, emissive: 0xc62828, ei: 0.7 }),
    warn: ctx.mat(0xffffff, { vc: true, side: THREE.DoubleSide, emissive: 0xffb020, ei: 0.55 }),
    sel: ctx.mat(0xffffff, { vc: true, side: THREE.DoubleSide, emissive: 0xffffff, ei: 0.28 }),
  };
  const podiumMat = ctx.keep(new THREE.MeshLambertMaterial({ color: 0xaab3bc, transparent: true, opacity: 0.55 }));
  const ringMat = ctx.keep(new THREE.MeshBasicMaterial({ color: 0xc62828, transparent: true, opacity: 0.85 }));
  const poleMat = ctx.keep(new THREE.MeshBasicMaterial({ color: 0x5b626b }));

  function make(kind) {
    if (cache.has(kind)) return cache.get(kind);
    const model = BUILDERS[kind](ctx.colors);
    const own = [];                           // геометрии подставки и столба: освобождаются при закрытии (не через ctx.keep)
    const group = new THREE.Group(); group.visible = false; root.add(group);
    const entries = [], body = new THREE.Group(); group.add(body);   // body: детали (его можно наклонить к камере), подставка остаётся ровной
    for (const g of model.groups) {
      const mesh = new THREE.Mesh(ctx.merge(g.parts), mats.base);
      mesh.geometry.computeBoundingBox();
      const c = mesh.geometry.boundingBox.getCenter(new THREE.Vector3());
      mesh.userData.inspect = true;
      body.add(mesh);
      entries.push({ part: g.part, mesh, flip: g.flip, when: g.when, hl: g.hl || g.part, center: c, off: new THREE.Vector3() });
    }
    const R = model.size * 0.62;
    const podG = new THREE.CylinderGeometry(R, R * 1.04, 0.8, 28), ringG = new THREE.TorusGeometry(R * 1.05, 0.5, 5, 40).rotateX(Math.PI / 2);
    own.push(podG, ringG);
    const podium = new THREE.Mesh(podG, podiumMat);
    let minY = 0, minDy = 0;
    for (const e of entries) minY = Math.min(minY, e.mesh.geometry.boundingBox.min.y);
    if (P.modeOf(kind) === 'explode') for (const p of P.partsOf(kind)) minDy = Math.min(minDy, p.explode[1] * model.esize);
    podium.position.y = minY + minDy - 0.5; group.add(podium);
    const ring = new THREE.Mesh(ringG, ringMat);
    ring.position.y = podium.position.y + 0.6; ring.visible = false; group.add(ring);
    const o = { model, group, body, entries, ring, podium, own };
    cache.set(kind, o);
    return o;
  }

  /* освободить модель вида: геометрии на видеокарте и массивы в памяти (материалы общие, остаются) */
  const freeGeo = g => { g.dispose(); for (const n of Object.keys(g.attributes)) g.deleteAttribute(n); g.index = null; };
  function disposeKind(kind) {
    const o = cache.get(kind); if (!o) return;
    root.remove(o.group);
    for (const e of o.entries) freeGeo(e.mesh.geometry);
    for (const g of o.own) freeGeo(g);
    cache.delete(kind);
  }

  /* ------------------------------------------------------------ данные: беды, прогноз, подсветка */
  function openKinds() {
    const out = new Set(), id = st.id;
    for (const i of AKT.issues()) {
      const kind = String(AKT.val(i, 'kind') || ''), node = AKT.issueNode(i);
      if (st.kind === 'pump') { if (kind === 'pump_cavit' && node === 'cyclones-' + lineOf(id)) out.add(kind); continue; }
      if (st.kind === 'truck') {
        if (kind === 'driver_fatigue') { if (AKT.name(String(AKT.val('fleet', 'fatigue_truck') || '')) === id) out.add(kind); }
        else if (kind === 'brake_hot') { if (AKT.name(String(AKT.val('fleet', 'brake_truck') || '')) === id) out.add(kind); }
        else if (kind === 'road_winter' || kind === 'fleet_short') out.add(kind);
      } else if (node === id) out.add(kind);
    }
    return out;
  }
  const linerForecast = () => {
    const m = /^sag-(\d+)$/.exec(st.id); if (!m) return null;
    const f = AKT.fc && AKT.fc.data ? AKT.fc.data() : null;
    return f && f.liner && f.liner.lines ? f.liner.lines[m[1]] || null : null;
  };
  /* шламовый насос — вещи в Ditto нет (pump-N: насос питания циклонов линии N), имя и состояние берутся от линии */
  const lineOf = id => (/(\d+)/.exec(String(id)) || [0, 1])[1];
  const nameOf = id => (st.kind === 'pump' ? `Шламовый насос питания циклонов, линия ${lineOf(id)}` : AKT.nameRu(id));
  const stateOf = id => (AKT.things[id] ? AKT.stOf(id) : 'отдельной вещи в двойнике нет');
  const hlOf = (pid, ok, fc) => P.highlightOf(st.kind, pid, ok, fc);
  const hlText = h => (h === 'issue' ? '■ беда' : h === 'warn' ? '▲ срок близко' : '');

  function applyMaterials() {
    const o = cache.get(st.kind); if (!o) return;
    const ok = openKinds(), fc = linerForecast();
    for (const e of o.entries) {
      const h = hlOf(e.hl, ok, fc), sel = e.part === st.part;
      e.mesh.material = h === 'issue' ? mats.issue : h === 'warn' ? mats.warn : sel ? mats.sel : mats.base;
    }
    o.ring.visible = P.wholeAlarm(st.kind, ok);
  }

  /* ------------------------------------------------------------ положение частей */
  function layoutParts() {
    const o = cache.get(st.kind); if (!o) return;
    const mode = P.modeOf(st.kind), k = mode === 'explode' ? st.k : 0, es = o.model.esize;
    for (const e of o.entries) {
      const part = P.partById(st.kind, e.part);
      const off = part ? P.explodeOffset(part, k, es) : [0, 0, 0];
      e.mesh.position.set(off[0] * e.flip[0], off[1] * e.flip[1], off[2] * e.flip[2]);
      e.mesh.visible = e.when === 'both' || (st.on && mode === 'cut' ? e.when === 'cut' : e.when === 'whole');
    }
  }

  /* ------------------------------------------------------------ подписи частей */
  function dropLabels() { for (const L of st.labels) L.remove(); st.labels = []; }
  function addLabels() {
    dropLabels();
    const o = cache.get(st.kind); if (!o) return;
    const seen = new Set();
    for (const e of o.entries) {
      if (seen.has(e.part)) continue; seen.add(e.part);
      const part = P.partById(st.kind, e.part); if (!part) continue;
      const mine = o.entries.filter(x => x.part === e.part);
      st.labels.push(ctx.label('insp:' + e.part, () => {
        if (!st.on || !root.visible) return '';
        const h = hlText(hlOf(mine[0].hl, openKinds(), linerForecast()));
        return `${part.ru}${h ? ' · ' + h : ''}`;
      }, {
        thing: null, href: null, prio: 1, kind: 'small',
        at: () => {
          const m = mine.find(x => x.mesh.visible) || mine[0];
          const v = m.center.clone().add(m.mesh.position);
          return o.body.localToWorld(v);
        },
      }));
    }
  }

  /* ------------------------------------------------------------ карточка */
  function liveText(s) {
    if (!s.feature) return 'нет в Ditto';
    const cands = [], n = lineOf(st.id);
    if (AKT.things[st.id] && AKT.raw(st.id, s.feature) != null) cands.push(st.id);
    const spec = [].concat(s.thing || []);
    for (const t of spec) { const q = st.kind === 'ball' && /^ball-/.test(String(t)) ? st.id : String(t).replace('{n}', n); if (AKT.things[q]) cands.push(q); }
    const id = cands[0];
    if (!id) return '—';
    const v = AKT.raw(id, s.feature);
    if (typeof v !== 'number' || v === -1) return typeof v === 'string' && v ? AKT.valText(id, s.feature) : '—';
    return AKT.fmt(v, s.digits != null ? s.digits : (Number.isInteger(v) ? 0 : 2)) + (s.unit ? ' ' + s.unit : '');
  }
  function partCard() {
    const part = P.partById(st.kind, st.part);
    if (!part) return '<p class="p-sub">Выберите часть в списке или щелчком по модели.</p>';
    const ok = openKinds(), h = hlOf(part.id, ok, linerForecast());
    const sigs = P.partSignals(D, st.kind, st.id, part.id);
    const node = P.nodeOf(st.id), link = AKT.href(`?view=inside&n=${encodeURIComponent(node)}`);
    const open = AKT.issues().filter(i => part.troubles.includes(String(AKT.val(i, 'kind') || '')) && (st.kind === 'truck' || AKT.issueNode(i) === st.id));
    const state = h === 'issue' ? `<b class="bad">■ открыта беда: ${esc(open.length ? AKT.kindRu(String(AKT.val(open[0], 'kind') || '')) : '')}</b> · ${esc(open.length ? AKT.stRu(AKT.st(open[0]), open[0]) : '')}`
      : h === 'warn' ? '<b>▲ срок перефутеровки близко</b> по прогнозу наработки' : 'отклонений по этой части нет';
    const rows = sigs.map(s => `<tr><td>${esc(s.name)}</td><td class="n">${esc(liveText(s))}</td><td>${esc(P.evidenceRu(s.where))}${s.label ? ` <span class="lbl-est">[${esc(s.label)}]</span>` : ''}</td></tr>`).join('');
    return `<h4>${esc(part.ru)}</h4><p>${state}</p>
${rows ? `<table class="kv"><tr><th>сигнал</th><th>сейчас</th><th>где виден</th></tr>${rows}</table>`
      : '<p class="p-sub">Отдельного сигнала для этой части в источниках нет: смотрите общий узел.</p>'}
<p><a href="${esc(link)}">Полная карточка «Изнутри»</a></p>`;
  }
  function render() {
    if (!st.panel || !st.id) return;
    const K = P.KINDS[st.kind], ok = openKinds(), fc = linerForecast();
    const list = P.partsOf(st.kind).map(p => {
      const h = hlText(hlOf(p.id, ok, fc));
      return `<button type="button" data-part="${p.id}" aria-pressed="${p.id === st.part}">${esc(p.ru)}${h ? ' <span class="in-hl">' + h + '</span>' : ''}</button>`;
    }).join('');
    const whole = P.wholeAlarm(st.kind, ok) ? `<p class="bad"><b>■ ${esc(K.whole.filter(t => ok.has(t)).map(t => AKT.kindRu(t)).join(', '))}</b></p>` : '';
    const html = `<div class="ip-head"><b>${esc(nameOf(st.id))}</b> <button type="button" class="ip-x" data-act="close" aria-label="Закрыть">✕</button></div>
<p class="p-sub">${esc(stateOf(st.id))} · схема: ${esc(K.ru)}${st.kind === 'truck' && !/793/.test(AKT.nameRu(st.id)) ? '; сигналы узла — по CAT 793 (аналог)' : ''}</p>${whole}
<button type="button" class="primary" data-act="toggle" aria-pressed="${st.on}">${esc(P.toggleText(st.kind, st.on))}</button>
<div class="ip-parts">${list}</div>
${st.kind === 'cyclones' || st.kind === 'ball' ? '<button type="button" data-act="pump">Шламовый насос питания →</button>' : ''}
<div class="ip-card">${D ? partCard() : '<p class="p-sub">Загружаю описание узлов…</p>'}</div>
<p class="p-sub"><a href="${esc(AKT.href('?view=inside&n=' + encodeURIComponent(P.nodeOf(st.id))))}">Все сигналы и отказы узла: «Изнутри»</a></p>`;
    if (st.panel._html !== html) { st.panel._html = html; st.panel.innerHTML = html; }
    applyMaterials();
  }
  function ensurePanel() {
    if (st.panel) return;
    const el = document.createElement('aside'); el.className = 'ip-panel'; el.setAttribute('aria-label', 'Разбор машины');
    el.addEventListener('click', ev => {
      const b = ev.target.closest('button'); if (!b) return;
      if (b.dataset.act === 'close') close();
      else if (b.dataset.act === 'pump') open('pump-' + lineOf(st.id));
      else if (b.dataset.act === 'toggle') { st.on = !st.on; layoutParts(); render(); fly(); }
      else if (b.dataset.part) { st.part = b.dataset.part; render(); }
    });
    ctx.wrap.appendChild(el); st.panel = el;
  }

  /* ------------------------------------------------------------ открыть / закрыть */
  /* камера: на подставку; при разборе дальше, карточка закрывает правую часть кадра — цель сдвинута вправо от модели */
  function fly() {
    const o = cache.get(st.kind); if (!o) return;
    const k = P.modeOf(st.kind) === 'explode' ? (st.on ? 1.5 : 0.95) : 0.85;
    const dist = ctx.fitDist(o.model.size * o.model.scale * k * (o.model.fit || 1));
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(ctx.camera.quaternion); right.y = 0; right.normalize();
    ctx.flyTo(root.position.clone().add(new THREE.Vector3(0, 6, 0)).addScaledVector(right, dist * 0.2), dist);
  }
  function open(id) {
    const kind = P.kindOf(id); if (!kind) return false;
    ensurePanel(); loadInside();
    const o = make(kind);
    if (st.kind && st.kind !== kind) { dropLabels(); disposeKind(st.kind); }
    Object.assign(st, { id, kind, part: '', on: false, k: 0 });
    o.group.visible = true; root.visible = true;
    const p = ctx.layout.pos(kind === 'pump' ? 'cyclones-' + lineOf(id) : id) || new THREE.Vector3();
    const gy = Math.max(ctx.heightAt(p.x, p.z), p.y || 0);
    /* подставка на столбе над машиной; сама машина остаётся на месте */
    root.position.set(p.x, gy + o.model.lift, p.z);
    o.group.scale.setScalar(o.model.scale);
    /* стоящие аппараты (tilt в модели): верх наклонён к камере, иначе сверху виден только бункер или крышка */
    if (o.model.tilt) {
      const f = new THREE.Vector3(0, 0, -1).applyQuaternion(ctx.camera.quaternion), rt = new THREE.Vector3(1, 0, 0).applyQuaternion(ctx.camera.quaternion);
      rt.y = 0; rt.normalize();
      const pitch = Math.asin(Math.max(-1, Math.min(1, -f.y)));
      o.body.quaternion.setFromAxisAngle(rt, Math.max(0, Math.PI / 2 - pitch) * o.model.tilt);
    } else o.body.quaternion.identity();
    if (!o.pole) { const pg = new THREE.CylinderGeometry(0.5, 0.5, 1, 6).translate(0, -0.5, 0); o.own.push(pg); o.pole = new THREE.Mesh(pg, poleMat); root.add(o.pole); }
    o.pole.scale.set(1, o.model.lift, 1); o.pole.position.set(0, -0.8 * o.model.scale, 0);
    o.pole.visible = true;
    layoutParts(); addLabels(); render();
    fly();
    return true;
  }
  function close() {
    st.id = ''; st.on = false; root.visible = false;
    dropLabels();
    for (const k of [...cache.keys()]) disposeKind(k);
    st.kind = '';
    if (st.panel) { st.panel.remove(); st.panel = null; }
  }

  /* ------------------------------------------------------------ щелчок */
  const meshes = () => { const o = cache.get(st.kind); return o ? o.entries.filter(e => e.mesh.visible).map(e => e.mesh) : []; };
  ctx.setClickHook(ev => {
    if (st.id && root.visible) {
      const ray = ctx.rayAt(ev), hit = ray.intersectObjects(meshes(), false)[0];
      if (hit) {
        const o = cache.get(st.kind), e = o.entries.find(x => x.mesh === hit.object);
        if (e) { st.part = e.part; render(); return true; }
      }
    }
    const id = ctx.pickId(ev);
    if (!id) return false;
    if (P.kindOf(id)) return open(id);
    const cat = AKT.cat(id);
    if (!(AKT.MACHINE_CATS && AKT.MACHINE_CATS.has(cat)) && !PLANT.has(AKT.type(id))) return false;
    const href = AKT.insideHref ? AKT.insideHref(id) : null;
    if (href) { location.href = href; return true; }
    return false;
  });
  if (AKT.params.get('perf') === '1') window.__inspect = { open: id => open(id), close, st, cache, root, toggle: () => { st.on = !st.on; layoutParts(); render(); fly(); }, pick: p => { st.part = p; render(); } };
  /* ?perf=1&insp=sag-1[&cut=1]: открыть разбор сразу (для замера нагрузки с открытой моделью) */
  if (AKT.params.get('perf') === '1' && AKT.params.get('insp')) setTimeout(() => { if (open(AKT.params.get('insp')) && AKT.params.get('cut') === '1') { st.on = true; layoutParts(); render(); } }, 2500);
  const onKey = ev => { if (ev.key === 'Escape' && st.id) close(); };
  document.addEventListener('keydown', onKey);

  /* ------------------------------------------------------------ кадр */
  return {
    update(state, dt) {
      if (!st.id) return;
      const want = P.modeOf(st.kind) === 'explode' && st.on ? 1 : 0;
      if (Math.abs(st.k - want) > 0.002) { st.k += (want - st.k) * Math.min(1, dt * (state.lite ? 8 : 5)); layoutParts(); }
      else if (st.k !== want) { st.k = want; layoutParts(); }
      if (state.fresh) render();
    },
    destroy() { delete window.__inspect; document.removeEventListener('keydown', onKey); close(); ctx.setClickHook(null); scene.remove(root); },
    /* для проверки */
    _open: open, _close: close, _state: st,
  };
}
