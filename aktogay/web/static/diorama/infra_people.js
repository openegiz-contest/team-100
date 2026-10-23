/* «Диорама», инфраструктура: люди смены и бригады.
   Каждый человек из Ditto (тип person) — фигурка в каске и жилете у своего
   узла (location; свободный — у дома из паспорта home; OFF — у АБК, пункт
   сбора), под ногами — кружок цвета состояния. TRAVEL — путь пунктиром по
   поверхности (ctx.route: из карьера и в карьер по съезду) от места до узла
   работы, фигурка идёт по нему: доля пути = (время модели − начало вызова) /
   (ETA − начало); ETA — AKT.travel (начало из журнала или точек InfluxDB,
   время в пути arrive_min — допущение стенда). Бригады (тип crew) — 1–2
   фигурки в синих комбинезонах: свободные у АБК, в работе — у узла задачи,
   в пути — за своим человеком. Кого звать к беде 1 (AKT.topCall) — синее
   кольцо и ореол, подпись «кого звать» / «позван», пунктир к беде, пока не
   позван. Подписи — та же короткая роль, что на плане и в панели. */

/* важность подписи человека: кого звать — как беда; в пути — как линии; занят — как главные узлы */
const PRIO = { call: 1, called: 1, travel: 3, busy: 4 };
const CREW_RU = { crusher_mech: 'Бригада ЦПД', plant_mech: 'Бригада фабрики', kip: 'Бригада КИПиА', tailings_engineer: 'Бригада хвостов' };

export function buildPeople(ctx, kit, glow, groundFn) {
  const { THREE, AKT, layout, scene } = ctx;
  const group = new THREE.Group(); group.name = 'infra-people'; scene.add(group);
  const ground = (x, z) => groundFn ? groundFn(x, z) : ctx.heightAt(x, z);

  /* фигурка (смотрит на +z): ноги, жилет со световозвращающей полосой, руки, голова, каска */
  const figure = (suit, vest, stripe, helmet) => {
    const L = kit.list();
    L.box(-0.62, 0, 0, 1.05, 4.1, 1.3, suit).box(0.62, 0, 0, 1.05, 4.1, 1.3, suit)
      .box(0, 4.0, 0, 3.0, 3.7, 1.8, vest).box(0, 4.9, 0, 3.06, 0.5, 1.86, stripe).box(0, 6.5, 0, 3.06, 0.4, 1.86, stripe)
      .box(-1.95, 4.3, 0, 0.8, 3.3, 1.0, vest).box(1.95, 4.3, 0, 0.8, 3.3, 1.0, vest)
      .sph(0, 8.7, 0, 1.12, 0xd6a27d)
      .raw(new THREE.SphereGeometry(1.32, 10, 4, 0, Math.PI * 2, 0, Math.PI / 2), helmet, new THREE.Matrix4().makeTranslation(0, 9.0, 0))
      .cyl(0, 8.85, 0, 1.55, 0.28, helmet);
    return L.geometry({ bake: false });
  };
  const PMAX = 16, CMAX = 28;
  const personMesh = new THREE.InstancedMesh(figure(0x2c3a52, 0xff7a1a, 0xe9edf0, 0xffffff), ctx.materials.vc, PMAX);
  const crewMesh = new THREE.InstancedMesh(figure(0x2b4f86, 0x2f63a8, 0xff8f1f, 0xf2a21a), ctx.materials.vc, CMAX);
  for (const m of [personMesh, crewMesh]) { m.count = 0; m.frustumCulled = false; group.add(m); }
  personMesh.name = 'people'; crewMesh.name = 'crews';
  const disks = new THREE.InstancedMesh(ctx.keep(new THREE.CircleGeometry(1, 18).rotateX(-Math.PI / 2)),
    ctx.keep(new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })), PMAX + CMAX);
  disks.count = 0; disks.frustumCulled = false; disks.renderOrder = 1; disks.name = 'people-disks';
  group.add(disks);
  const blobs = new THREE.InstancedMesh(ctx.blobGeometry, ctx.blobMaterial(0.25), PMAX + CMAX);
  blobs.count = 0; blobs.frustumCulled = false; blobs.renderOrder = 1; group.add(blobs);
  /* пунктир путей в дороге */
  const dash = kit.prisms(1400, { offset: true });
  dash.mesh.name = 'people-travel'; group.add(dash.mesh);

  const slots = [], crewSlots = [];
  ctx.onClick(hit => slots[hit.instanceId], personMesh, { halo: false });
  ctx.onClick(hit => crewSlots[hit.instanceId], crewMesh, { halo: false });
  ctx.claim(id => { const c = AKT.cat(id); return c === 'person' || c === 'crew'; });

  /* ------------------------------------------------------------- состояние */
  const ppl = new Map();          // id -> {id, crew, base: V3, cur: V3, head: V3, yaw, travel, label, ...}
  const STC = ctx.stColors;
  const name = v => AKT.name(String(v || ''));
  const routes = new Map();
  const routeOf = (from, to) => {
    const k = from + '>' + to;
    if (!routes.has(k)) {
      const c = ctx.route(from, to, { lift: 1.6 });
      /* по дамбе хвостохранилища и площадкам — не ниже поверхности */
      if (c) for (const p of c.points) { if (p.y > -1) p.y = Math.max(p.y, ground(p.x, p.z) + 1.6); }
      routes.set(k, c ? new ctx.PolyCurve(c.points) : null);
    }
    return routes.get(k);
  };
  const standOf = n => layout.stand(n) || layout.pos(n) || layout.stand('abk') || new THREE.Vector3();
  const crewShort = c => CREW_RU[AKT.attr(c, 'responsible.role')] || AKT.shortName(c);
  const crewSize = c => { const s = AKT.pass(c, 'size'); return typeof s === 'number' && s > 0 ? Math.min(2, Math.round(s)) : 2; };

  function entry(id, crew) {
    if (ppl.has(id)) return ppl.get(id);
    const e = { id, crew, base: new THREE.Vector3(), cur: new THREE.Vector3(), head: new THREE.Vector3(), yaw: 0, tr: null, curve: null,
      p0: 0, label: null, mode: '', hidden: false, st: '', walking: false };
    e.label = makeLabel(e, '');
    ppl.set(id, e);
    return e;
  }
  /* подпись: класс «кого звать» меняется — подпись пересоздаётся (ключ тот же) */
  function makeLabel(e, mode) {
    const id = e.id;
    if (e.crew) {
      return ctx.label('infra:' + id, () => {
        if (!AKT.things[id]) return '';
        const st = AKT.st(id);
        return `${crewShort(id)}${st && st !== 'FREE' ? ' · ' + AKT.stOf(id).toLowerCase() : ''}`;
      }, { thing: id, prio: 6, kind: 'small', at: () => e.head, title: () => `${AKT.nameRu(id)}: ${AKT.stOf(id)} · задача: ${AKT.placeRu(name(String(AKT.val(id, 'task') || '').split(',')[0])) } · нажмите — карточка` });
    }
    return ctx.label('infra:' + id, () => {
      if (!AKT.things[id]) return '';
      const i = AKT.personInfo(id), top = AKT.topCall();
      let s = AKT.personLabel(i);
      if (!i.tr && i.st && i.st !== 'FREE') s += ` · ${AKT.stRu(i.st, id).toLowerCase()}`;
      const sub = [];
      if (top && top.person === id) sub.push(top.called ? 'позван к беде 1' : 'кого звать к беде 1');
      if (i.tr) sub.push(`в пути ${AKT.fmt(i.tr.a0)}–${AKT.fmt(i.tr.a1)} мин ${AKT.ASSUME}`);
      return sub.length ? s + '\n' + sub.join(' · ') : s;
    }, { thing: id, prio: PRIO[mode] || 5, kind: 'small', at: () => e.head, cls: /call/.test(mode) ? 'dio-call' : '', title: () => AKT.personTitle(AKT.personInfo(id)) });
  }

  /* после опроса: где кто, кто в пути, кого звать */
  let topId = '', topNode = '', topCalled = false;
  function fresh(state) {
    const persons = Object.keys(AKT.things).filter(n => AKT.cat(n) === 'person').sort(AKT.cmpNames).slice(0, PMAX);
    const crews = Object.keys(AKT.things).filter(n => AKT.cat(n) === 'crew').sort(AKT.cmpNames);
    const seen = new Set(persons.concat(crews));
    for (const [id, e] of ppl) if (!seen.has(id)) { e.label.remove(); ppl.delete(id); }
    const top = AKT.topCall();
    topId = top ? top.person : ''; topNode = top ? top.node : ''; topCalled = !!(top && top.called);
    const groups = new Map();
    const place = (e, p) => {
      const k = Math.round(p.x / 6) + ':' + Math.round(p.z / 6);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(e); e.base.copy(p);
    };
    for (const id of persons) {
      const e = entry(id, false);
      const i = AKT.personInfo(id);
      e.st = i.st;
      e.tr = i.tr && i.tr.to ? i.tr : null;
      e.curve = null;
      if (e.tr) {
        const from = e.tr.from || i.home || 'abk';
        e.curve = routeOf(from, e.tr.to);
        if (e.curve) continue;
      }
      const node = i.st === 'OFF' ? 'abk' : (i.loc && i.loc !== 'site' ? i.loc : (i.task || i.home || 'abk'));
      place(e, standOf(node));
    }
    for (const id of crews) {
      const e = entry(id, true);
      e.st = AKT.st(id);
      const task = name(String(AKT.val(id, 'task') || '').split(',')[0]);
      const lead = name(AKT.attr(id, 'responsible.person'));
      e.lead = e.st === 'TRAVEL' && ppl.has(lead) && ppl.get(lead).curve ? ppl.get(lead) : null;
      e.n = crewSize(id);
      if (e.lead) continue;
      place(e, standOf((e.st === 'WORK' || e.st === 'TRAVEL') && task ? task : 'abk'));
    }
    /* несколько у одного места — в ряд поперёк взгляда (схема) */
    for (const g of groups.values()) {
      const w = g.reduce((s, e) => s + (e.crew ? 7 : 5.5), 0);
      let x = -w / 2;
      for (const e of g) { const ww = e.crew ? 7 : 5.5; e.base.x += x + ww / 2; x += ww; e.base.y = ground(e.base.x, e.base.z); }
    }
    for (const e of ppl.values()) {
      const mode = !e.crew && e.id === topId ? (topCalled ? 'called' : 'call') : e.st === 'TRAVEL' ? 'travel' : e.st && e.st !== 'FREE' ? 'busy' : '';
      if (mode !== e.mode) { e.mode = mode; e.label = makeLabel(e, mode); e.hidden = false; }
    }
    /* пунктир «кого звать» к узлу беды 1 — пока человек не позван */
    const te = topId && ppl.get(topId);
    if (te && !topCalled && topNode && !te.curve) {
      const b = glow.target(topNode, 6);
      glow.setCall(new THREE.Vector3(te.base.x, te.base.y + 12, te.base.z), b);
    } else glow.setCall(null, null);
    dashAt = -1;
  }

  /* ---------------------------------------------------------------- кадр */
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(1, 1, 1), pp = new THREE.Vector3(), tg = new THREE.Vector3(), cc = new THREE.Color();
  const UP = new THREE.Vector3(0, 1, 0), da = new THREE.Vector3(), db = new THREE.Vector3();
  let dashAt = -1;
  const progress = (e, simNow) => {
    if (!e.tr || simNow == null) return 0;
    const span = e.tr.eta - e.tr.start, u = (simNow - e.tr.start) / span;
    return span > 0 && isFinite(u) ? Math.max(0, Math.min(0.97, u)) : 0;
  };
  function frame(state) {
    if (state.fresh) fresh(state);
    let np = 0, nc = 0, nd = 0;
    const far = state.camDist > 1800;
    /* издалека фигурки крупнее (схема, как машины), вблизи — как есть */
    const K = Math.max(1, Math.min(1.9, (state.camDist || 0) / 1300));
    for (const e of ppl.values()) {
      /* где фигурка сейчас */
      e.walking = false;
      if (!e.crew && e.curve) {
        const u = progress(e, state.simNow);
        e.p0 = u;
        e.curve.getPointAt(u, e.cur); e.curve.getTangentAt(u, tg);
        e.cur.y -= 1.6;
        e.yaw = Math.atan2(tg.x, tg.z); e.walking = !state.paused;
      } else if (e.crew && e.lead) {
        const L = e.lead, u = Math.max(0, L.p0 - 10 / Math.max(1, L.curve.len));
        L.curve.getPointAt(u, e.cur); e.cur.y -= 1.6; L.curve.getTangentAt(u, tg);
        e.yaw = Math.atan2(tg.x, tg.z); e.walking = !state.paused;
      } else { e.cur.copy(e.base); e.yaw = 0; }
      const bob = e.walking ? 0.35 * K * Math.abs(Math.sin(state.t * 7 + e.cur.x)) : 0;
      e.head.set(e.cur.x, e.cur.y + 3 + 10 * K, e.cur.z);
      /* фигурки: человек — одна, бригада — 1–2 рядом */
      q.setFromAxisAngle(UP, e.yaw);
      const isTop = !e.crew && e.id === topId;
      if (!e.crew && np < PMAX) {
        m4.compose(pp.set(e.cur.x, e.cur.y + bob, e.cur.z), q, sc.set(K, K, K));
        personMesh.setMatrixAt(np, m4);
        personMesh.setColorAt(np, cc.setRGB(1, 1, 1));
        slots[np++] = e.id;
      } else if (e.crew) {
        for (let k = 0; k < e.n && nc < CMAX; k++) {
          const ox = (k - (e.n - 1) / 2) * 3.4 * K, oz = (k % 2 ? -2.2 : 0.6) * K;
          const c = Math.cos(e.yaw), s = Math.sin(e.yaw);
          m4.compose(pp.set(e.cur.x + ox * c + oz * s, e.cur.y + bob, e.cur.z - ox * s + oz * c), q, sc.set(0.92 * K, 0.92 * K, 0.92 * K));
          crewMesh.setMatrixAt(nc, m4);
          crewMesh.setColorAt(nc, cc.setRGB(1, 1, 1));
          crewSlots[nc++] = e.id;
        }
      }
      /* кружок состояния и пятно-тень */
      if (nd < PMAX + CMAX) {
        const r = (e.crew ? 4.6 : 3.4) * K;
        m4.compose(pp.set(e.cur.x, e.cur.y + 0.35, e.cur.z), q.identity(), sc.set(r, 1, r));
        disks.setMatrixAt(nd, m4);
        cc.setHex(STC[AKT.cls(e.st)] || STC['st-grey']); disks.setColorAt(nd, cc);
        m4.compose(pp.set(e.cur.x + 0.8, e.cur.y + 0.2, e.cur.z + 0.8), q, sc.set(r * 1.7, 1, r * 1.7));
        blobs.setMatrixAt(nd, m4);
        nd++;
      }
      /* кого звать к беде 1: синее кольцо и ореол */
      if (isTop) {
        glow.ring(e.cur.x, e.cur.y + 0.5, e.cur.z, 8.5 * K, 0x16191d, true);
        glow.halo(e.cur.x, e.cur.y + 6 * K, e.cur.z, 0x4f8ff7, false);
      }
      if (!e.crew && e.curve && e.tr) {
        const end = e.curve.points[e.curve.points.length - 1];
        glow.ring(end.x, end.y - 1.2, end.z, 6.5 * K, 0xff7a1a, false, true);
      }
      /* подписи: свободные — только вблизи; в пути, в работе и кого звать — всегда */
      const quiet = (e.st === 'FREE' || !e.st) && !isTop;
      const hide = quiet && far;
      if (hide !== e.hidden) { e.hidden = hide; e.label.hide(hide); }
    }
    personMesh.count = np; crewMesh.count = nc; disks.count = nd; blobs.count = nd;
    for (const m of [personMesh, crewMesh, disks, blobs]) { m.instanceMatrix.needsUpdate = true; if (m.instanceColor) m.instanceColor.needsUpdate = true; }
    /* пунктир оставшейся части пути: пересборка 4 раза в секунду; издалека толще и реже (как фигурки) */
    if (state.fresh || state.t - dashAt > 0.25) {
      dashAt = state.t;
      dash.reset();
      const step = 10 * K, seg = 6 * K, w = 1.15 * K;
      for (const e of ppl.values()) {
        if (e.crew || !e.curve) continue;
        const cv = e.curve, L = cv.len;
        const ofs = (state.t * 6) % step;
        for (let d = e.p0 * L + 3 + ofs; d < L - 1; d += step) {
          cv.at(d, da); cv.at(Math.min(L, d + seg), db);
          da.y -= 0.6; db.y -= 0.6;
          if (!dash.add(da, db, w, 0xff7a1a)) break;
        }
      }
      dash.commit();
    }
  }
  return { update: frame };
}
