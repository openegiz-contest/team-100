/* «Диорама», инфраструктура: энергия.
   ПС 220/35 кВ с двумя трансформаторами и две ВЛ 220 кВ от ПС 500/220 кВ
   «Актогай» (ОВОС-2018, с. 12; в OSM ВЛ 220 кВ way/1027119995, ПС 500 кВ — в
   ≈ 25 км, вне макета), фидеры 35 кВ к линиям фабрики и к ЦПД по линиям схемы
   LINES. Потребление и лимит — из Ditto (power.site_mw, grid_limit_mw, shed_mw):
   подпись «X из 300 МВт», столбик загрузки у подстанции, огни бегут по проводам
   со скоростью ∝ МВт; при сбросе нагрузки — янтарные, при беде — красные провода.
   Опоры, порталы, размеры — схема. */

export function buildPower(ctx, kit, glow) {
  const { THREE, AKT, scene } = ctx;
  const group = new THREE.Group(); group.name = 'infra-power'; scene.add(group);
  const H = (x, z) => ctx.heightAt(x, z);
  const Z = ctx.ZONES.power || { x0: 405, x1: 535, z0: -440, z1: -370 };
  const py = H((Z.x0 + Z.x1) / 2, (Z.z0 + Z.z1) / 2);

  /* ------------------------------------------------------------ подстанция */
  const S = kit.list();
  const STEEL = 0x8d949c, DARK = 0x5b636b, INS = 0x7a4a2c, TR = 0x6c7468, FIN = 0x596057;
  /* ограждение */
  const fx0 = Z.x0 + 3, fx1 = Z.x1 - 3, fz0 = Z.z0 + 3, fz1 = Z.z1 - 3;
  S.box((fx0 + fx1) / 2, py, fz0, fx1 - fx0, 3, 0.4, 0xc4c9ce).box((fx0 + fx1) / 2, py, fz1, fx1 - fx0, 3, 0.4, 0xc4c9ce)
    .box(fx0, py, (fz0 + fz1) / 2, 0.4, 3, fz1 - fz0, 0xc4c9ce).box(fx1, py, (fz0 + fz1) / 2, 0.4, 3, fz1 - fz0, 0xc4c9ce);
  /* вводной портал 220 кВ (две цепи) и шинные порталы */
  const PZ = [-432, -408], PX = [526, 492, 458];
  PX.forEach((x, i) => {
    const h = i === 0 ? 24 : 17;
    for (const z of PZ) S.box(x, py, z, 1.5, h, 1.5, STEEL);
    S.box(x, py + h - 1.2, (PZ[0] + PZ[1]) / 2, 1.4, 1.4, PZ[1] - PZ[0] + 3, STEEL);
  });
  /* шины: три фазы между порталами */
  for (const dz of [-6, 0, 6]) S.box((PX[0] + PX[2]) / 2, py + 14.4, -420 + dz, PX[0] - PX[2], 0.5, 0.5, 0xb9bec3);
  /* выключатели и разъединители: колонки с изоляторами перед трансформаторами */
  const TX = [470, 432];                      // два трансформатора 220/35 кВ (ОВОС-2018, с. 12)
  for (const x of TX) for (const dx of [-4, 0, 4]) {
    S.box(x + dx, py, -404, 1.6, 1, 1.6, 0x9ea4aa).cyl(x + dx, py + 1, -404, 0.55, 6, DARK, true).cyl(x + dx, py + 7, -404, 0.75, 3.2, INS, true);
  }
  /* трансформаторы: бак, радиаторы, расширитель, вводы */
  for (const x of TX) {
    const z = -391;
    S.box(x, py, z, 13, 1.2, 10, 0xa8a49b)                            // фундамент
      .box(x, py + 1.2, z, 11, 9, 8, TR)
      .box(x, py + 10.2, z, 11.4, 0.6, 8.4, FIN);
    for (const s of [-1, 1]) for (const k of [-2.6, 0, 2.6]) S.box(x + s * 6.6, py + 2, z + k, 1.6, 7, 0.5, FIN);
    S.hcyl(x - 1, py + 13, z - 2.6, 1.5, 9, TR).box(x - 1, py + 10.8, z - 2.6, 0.7, 1.4, 0.7, FIN);
    for (const dx of [-3, 0, 3]) S.cyl(x + dx, py + 10.8, z + 1.6, 0.5, 4.6, INS, true);
  }
  /* ОПУ (здание управления) */
  S.box(416, py, -384, 15, 7.5, 12, 0xe2e5e8).box(416, py + 7.5, -384, 16, 1, 13, 0x8d969f)
    .box(416, py, -377.9, 3, 4.8, 0.3, 0x56636f).box(411, py + 3.4, -377.9, 4, 1.6, 0.3, 0x7fa6c2).box(421, py + 3.4, -377.9, 4, 1.6, 0.3, 0x7fa6c2);
  /* столбик загрузки (рамка; заливка — отдельный меш) */
  const MX = Z.x0 - 9, MZ = -377, my = H(MX, MZ), MH = 34;
  S.box(MX, my, MZ, 5.2, 1, 5.2, 0x7d8389).box(MX - 2.3, my + 1, MZ, 0.6, MH, 3.6, DARK).box(MX + 2.3, my + 1, MZ, 0.6, MH, 3.6, DARK)
    .box(MX, my + 1 + MH, MZ, 5.2, 0.8, 3.6, DARK).box(MX, my + 1, MZ - 1.6, 4.0, MH, 0.4, 0xf2f2ef)
    .box(MX, my + 1 + MH * (1 / 1.15) - 0.3, MZ + 2.0, 5.6, 0.6, 0.6, 0xd8342a);     // лимит сети (верх шкалы = 1,15 × лимит)
  const sub = S.mesh(); sub.name = 'substation';
  group.add(sub);
  ctx.onClick('power', sub);
  for (const [x, z, w, d] of [[TX[0] + 2, -389, 22, 18], [TX[1] + 2, -389, 22, 18], [417, -382, 22, 18]]) {
    const b = ctx.blob(w, d, 0.2); b.position.set(x, py + 0.12, z); group.add(b);
  }
  const meterFill = new THREE.Mesh(ctx.keep(new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0)), ctx.keep(new THREE.MeshBasicMaterial({ color: 0x4f86b8 })));
  meterFill.position.set(MX, my + 1, MZ - 1.0); meterFill.scale.set(3.4, 0.01, 0.6);
  meterFill.name = 'power-meter'; group.add(meterFill);
  ctx.onClick('power', meterFill, { halo: false });

  /* ------------------------------------------------------ опоры и провода */
  const T = kit.list(), wires = [];       // wires: {line, pts: [Vector3]}
  const sag = (a, b, s, out, n) => {
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      out.push(new THREE.Vector3(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t - s * 4 * t * (1 - t), a.z + (b.z - a.z) * t));
    }
  };
  /* опора двухцепной ВЛ 220 кВ: решётчатый ствол из балок, три траверсы, трос */
  const tower = (x, z, ang, hgt) => {
    const y0 = H(x, z), c = Math.cos(ang), s = Math.sin(ang);
    const P = (u, y, v) => [x + u * c - v * s, y0 + y, z + u * s + v * c];     // u — вдоль линии, v — поперёк
    const b0 = 4.2, b1 = 1.3, top = hgt;
    const legs = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
    for (const [a, b] of legs) T.beam(P(a * b0, 0, b * b0), P(a * b1, top, b * b1), 0.6, STEEL);
    const lv = [0, top * 0.3, top * 0.55, top * 0.78];
    for (let k = 0; k < lv.length - 1; k++) {
      const wA = b0 + (b1 - b0) * lv[k] / top, wB = b0 + (b1 - b0) * lv[k + 1] / top;
      for (let f = 0; f < 4; f++) {
        const [a1, c1] = legs[f], [a2, c2] = legs[(f + 1) % 4];
        T.beam(P(a1 * wA, lv[k], c1 * wA), P(a2 * wB, lv[k + 1], c2 * wB), 0.35, STEEL);
      }
    }
    const arms = [top * 0.62, top * 0.8, top * 0.97], spread = [9, 11, 8];
    const att = [];
    arms.forEach((ay, k) => {
      T.beam(P(0, ay, -spread[k]), P(0, ay, spread[k]), 0.7, STEEL);
      for (const sd of [-1, 1]) {
        T.beam(P(0, ay - 0.2, sd * (spread[k] - 0.4)), P(0, ay - 3.2, sd * (spread[k] - 0.4)), 0.45, INS);
        att.push({ v: sd * (spread[k] - 0.4), y: ay - 3.2 });
      }
    });
    T.beam(P(0, top * 0.97, 0), P(0, top + 4, 0), 0.6, STEEL);
    att.push({ v: 0, y: top + 4 });            // грозозащитный трос
    return att.map(a => { const p = P(0, a.y, a.v); return new THREE.Vector3(p[0], p[1], p[2]); });
  };
  /* ВЛ 220 кВ: от края подиума к вводному порталу */
  const PL = ctx.LINES['power-line'] || [[750, -455], [640, -440], [535, -420]];
  const towerAt = [[PL[0][0] - 8, PL[0][1] + 1], PL[1]];
  const angOf = (a, b) => Math.atan2(b[1] - a[1], b[0] - a[0]);
  const tAtt = towerAt.map((p, i) => tower(p[0], p[1], angOf(PL[Math.min(i, PL.length - 2)], PL[Math.min(i + 1, PL.length - 1)]), 40));
  /* вводной портал: 6 точек на ригеле (две цепи по три фазы) и трос */
  const gate = [];
  for (const z of PZ) for (const dz of [-4, 0, 4]) gate.push(new THREE.Vector3(PX[0], py + 22, z + dz * 0.8 + (z === PZ[0] ? 2 : -2)));
  gate.push(new THREE.Vector3(PX[0], py + 24, (PZ[0] + PZ[1]) / 2));
  /* обрыв на краю подиума: провода уходят за макет */
  const edge = tAtt[0].map(p => new THREE.Vector3(Math.min(749, p.x + 9), p.y - 1.5, p.z + 0.3));
  const spans220 = [[edge, tAtt[0]], [tAtt[0], tAtt[1]], [tAtt[1], gate]];
  const line220 = [];
  /* фазы двух концов пролёта: по порядку поперёк линии (z), трос — с тросом */
  const byZ = P => P.slice(0, 6).map((p, i) => [p.z, i]).sort((a, b) => a[0] - b[0]).map(x => P[x[1]]).concat(P.slice(6));
  for (const [A0, B0] of spans220) {
    const A = byZ(A0), B = byZ(B0);
    for (let i = 0; i < A.length; i++) {
      const a = A[i], b = B[Math.min(i, B.length - 1)];
      const pts = []; sag(a, b, a.distanceTo(b) * 0.035, pts, 10);
      wires.push({ line: 'power-line', pts });
      if (i === 2) line220.push(pts);
    }
  }
  /* фидеры 35 кВ: опоры каждые ≈ 55 у.е., три провода */
  const feeders = ['power-feed-1', 'power-feed-2', 'power-crush'];
  const feederPath = {};
  for (const k of feeders) {
    const ln = ctx.LINES[k]; if (!ln) continue;
    const cv = new ctx.PolyCurve(ln.map(([x, z]) => new THREE.Vector3(x, 0, z)));
    const n = Math.max(2, Math.round(cv.len / 55));
    const poles = [];
    for (let i = 0; i <= n; i++) {
      const p = cv.getPointAt(i / n), tg = cv.getTangentAt(Math.min(0.999, Math.max(0.001, i / n)));
      const ang = Math.atan2(tg.z, tg.x), y0 = H(p.x, p.z), hgt = 17;
      const c = Math.cos(ang), s = Math.sin(ang);
      const A = (v, y) => new THREE.Vector3(p.x - v * s, y0 + y, p.z + v * c);
      T.box(p.x, y0, p.z, 1.1, hgt, 1.1, 0xa3a7ab)
        .beam([p.x + 4.5 * s, y0 + hgt - 1.2, p.z - 4.5 * c], [p.x - 4.5 * s, y0 + hgt - 1.2, p.z + 4.5 * c], 0.6, DARK);
      poles.push([A(-4, hgt - 0.6), A(0, hgt + 0.6), A(4, hgt - 0.6)]);
      if (i === 0) T.box(p.x, y0 + hgt + 0.0, p.z, 0.5, 0.6, 0.5, INS);
    }
    const mid = [];
    for (let i = 1; i < poles.length; i++) for (let f = 0; f < 3; f++) {
      const a = poles[i - 1][f], b = poles[i][f], pts = []; sag(a, b, a.distanceTo(b) * 0.03, pts, 8);
      wires.push({ line: k, pts });
      if (f === 1) mid.push(...(mid.length ? pts.slice(1) : pts));
    }
    feederPath[k] = new ctx.PolyCurve(mid);
  }
  const lines = T.mesh(); lines.name = 'power-lines';
  group.add(lines);
  ctx.onClick('power', lines, { halo: false });
  /* провода: один LineSegments с цветами вершин (цвет — по линии) */
  let nSeg = 0; for (const w of wires) nSeg += w.pts.length - 1;
  const wpos = new Float32Array(nSeg * 6), wcol = new Float32Array(nSeg * 6), wline = [];
  { let k = 0; for (const w of wires) for (let i = 1; i < w.pts.length; i++) { const a = w.pts[i - 1], b = w.pts[i]; wpos.set([a.x, a.y, a.z, b.x, b.y, b.z], k * 6); wline.push(w.line); k++; } }
  const wg = ctx.keep(new THREE.BufferGeometry());
  wg.setAttribute('position', new THREE.BufferAttribute(wpos, 3));
  const wca = new THREE.BufferAttribute(wcol, 3); wg.setAttribute('color', wca);
  const wireMesh = new THREE.LineSegments(wg, ctx.keep(new THREE.LineBasicMaterial({ vertexColors: true })));
  wireMesh.name = 'power-wires'; group.add(wireMesh);
  const pathOf = { 'power-line': line220.length ? new ctx.PolyCurve([].concat(...line220.map((p, i) => i ? p.slice(1) : p))) : null };
  Object.assign(pathOf, feederPath);

  /* огни по проводам: от сети к подстанции и от подстанции к потребителям */
  const beads = [];
  for (const k of Object.keys(pathOf)) {
    const cv = pathOf[k]; if (!cv) continue;
    const n = Math.max(2, Math.round(cv.len / 40));
    for (let i = 0; i < n; i++) beads.push({ k, cv, u0: i / n });
  }
  const beadMesh = new THREE.InstancedMesh(ctx.keep(new THREE.OctahedronGeometry(1.5, 0)), ctx.keep(new THREE.MeshBasicMaterial({ color: 0xffffff })), Math.max(1, beads.length));
  beadMesh.name = 'power-beads'; beadMesh.frustumCulled = false; group.add(beadMesh);

  /* --------------------------------------------------------------- подписи */
  const NB = ' ';
  const has = () => !!AKT.things.power;
  const mw = f => AKT.num('power', f);
  ctx.label('infra:power', () => {
    if (!has()) return '';
    const shed = mw('shed_mw');
    const st = AKT.st('power');
    return `ПС 220/35 кВ · ${AKT.fmt(mw('site_mw'))} из ${AKT.fmt(mw('grid_limit_mw'))}${NB}МВт${shed > 0 ? ` · сброс ${AKT.fmt(shed)}${NB}МВт` : ''}${st && st !== 'NORMAL' && !(shed > 0) ? ' · ' + AKT.stOf('power').toLowerCase() : ''}\nлимит сети ${AKT.ASSUME}`;
  }, {
    thing: 'power', prio: 2, at: new THREE.Vector3(MX, my + MH + 4, MZ),
    title: () => `Энергоснабжение (Ditto): потребление ${AKT.fmt(mw('site_mw'))} МВт, из них помол ${AKT.fmt(mw('grinding_mw'))} МВт и прочее ${AKT.fmt(mw('other_mw'))} МВт; запас ${AKT.fmt(mw('headroom_mw'))} МВт; сброс ${AKT.fmt(mw('shed_mw'))} МВт. Лимит сети ${AKT.fmt(mw('grid_limit_mw'))} МВт — допущение стенда. ПС 220/35 кВ, 2 трансформатора 100/125 МВА — ОВОС-2018, с. 12`,
  });
  ctx.label('infra:ltl', 'ВЛ 220 кВ, 2 цепи · от ПС 500/220 кВ', {
    thing: 'power', prio: 8, kind: 'small', maxDist: 1700, at: new THREE.Vector3(towerAt[1][0], 46, towerAt[1][1]),
    title: 'Две ВЛ 220 кВ от ПС 500/220 кВ «Актогай» (≈ 25 км, вне макета): ОВОС-2018, с. 12; OSM way/1027119995. Опоры и пролёты — схема',
  });

  /* ---------------------------------------------------------------- update */
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(1, 1, 1), pp = new THREE.Vector3(), cc = new THREE.Color();
  const speed = { 'power-line': 0, 'power-feed-1': 0, 'power-feed-2': 0, 'power-crush': 0 }, phase = Object.assign({}, speed);
  const WIRE = 0x2f343a, WIRE_SHED = 0xd08a00, WIRE_BAD = 0xd8342a;
  let frac = 0, fracGoal = 0, beadHex = 0xffc83d, wireMode = null, meterHex = 0x4f86b8;
  function fresh(state) {
    const site = mw('site_mw') || 0, lim = mw('grid_limit_mw') || AKT.pass('power', 'limit_mw') || 300, shed = mw('shed_mw') || 0;
    fracGoal = Math.max(0, Math.min(1.15, site / lim)) / 1.15;
    const l1 = AKT.lineShaftMw ? AKT.lineShaftMw(1) : null, l2 = AKT.lineShaftMw ? AKT.lineShaftMw(2) : null;
    speed['power-line'] = site / lim;
    speed['power-feed-1'] = (l1 || 0) / (lim / 3);
    speed['power-feed-2'] = (l2 || 0) / (lim / 3);
    speed['power-crush'] = Math.max(0, (mw('other_mw') || 0)) / (lim / 2);
    const gl = state.glowOf ? state.glowOf('power') : '';
    const mode = gl === 'issue' || gl === 'alarm' ? 'bad' : shed > 0 || /LIMIT/.test(AKT.st('power') || '') ? 'shed' : '';
    beadHex = mode === 'bad' ? 0xff4a3a : mode === 'shed' ? 0xffa21a : 0xffc83d;
    meterHex = mode === 'bad' ? 0xd8342a : (mode === 'shed' || site / lim > 0.9) ? 0xe8a000 : 0x4f86b8;
    meterFill.material.color.setHex(meterHex);
    if (mode !== wireMode) {
      wireMode = mode;
      for (let k = 0; k < wline.length; k++) {
        const hot = mode && (wline[k] === 'power-line' || mode === 'bad');
        cc.setHex(hot ? (mode === 'bad' ? WIRE_BAD : WIRE_SHED) : WIRE);
        wcol.set([cc.r, cc.g, cc.b, cc.r, cc.g, cc.b], k * 6);
      }
      wca.needsUpdate = true;
    }
    beads.forEach((b, i) => beadMesh.setColorAt(i, cc.setHex(speed[b.k] > 0.005 ? beadHex : 0x8d949c)));
    if (beadMesh.instanceColor) beadMesh.instanceColor.needsUpdate = true;
  }
  function frame(state, dt) {
    if (state.fresh) fresh(state);
    frac += (fracGoal - frac) * Math.min(1, dt * 2);
    meterFill.scale.y = Math.max(0.01, frac * MH);
    for (const k in phase) if (!state.paused) phase[k] = (phase[k] + dt * (6 + 40 * Math.min(1.5, speed[k]))) % 1e6;
    beads.forEach((b, i) => {
      const u = ((b.u0 + phase[b.k] / b.cv.len) % 1 + 1) % 1;
      /* ВЛ: к подстанции; фидеры: от подстанции */
      b.cv.getPointAt(u, pp);
      m4.compose(pp, q, sc);
      beadMesh.setMatrixAt(i, m4);
    });
    beadMesh.instanceMatrix.needsUpdate = true;
    if (wireMode === 'bad') glow.halo(PX[0], py + 26, -420, 0xff3a2a, true);
  }
  wca.needsUpdate = true;
  fresh({});
  return { update: frame };
}
