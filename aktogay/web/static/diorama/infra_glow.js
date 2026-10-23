/* «Диорама», инфраструктура: свечение бед поверх всей сцены.
   Под узлом беды из очереди (state.issueNodes) — кольцо уровня беды на земле и
   ореол, пульсируют; узлы ниже по потоку (state.chain) — янтарные кольца; путь
   беды до меди — янтарные дуги над макетом по связям feeds из Ditto (только
   шаги «вниз по потоку», без обратных связей мельница ↔ циклоны), по дугам
   бегут огни от беды к складу концентрата; склад концентрата на пути —
   медное кольцо. Кольца и ореолы других частей модуля (кого звать, утечка,
   пьезометр выше S0, куда идёт человек) собираются здесь же за кадр:
   begin() → ring() / halo() → end(). */

const SEG = 12;

export function buildGlow(ctx, kit, groundFn) {
  const { THREE, AKT, layout, scene } = ctx;
  const group = new THREE.Group(); group.name = 'infra-glow'; scene.add(group);
  const G = ctx.glowColors;

  /* кольца на земле: один InstancedMesh */
  const RMAX = 64;
  const ringMesh = new THREE.InstancedMesh(ctx.keep(new THREE.RingGeometry(0.8, 1, 44).rotateX(-Math.PI / 2)),
    ctx.keep(new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.88, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 })), RMAX);
  ringMesh.count = 0; ringMesh.frustumCulled = false; ringMesh.renderOrder = 3; ringMesh.name = 'infra-rings';
  group.add(ringMesh);
  /* тонкие кольца: узлы на пути беды, куда идёт человек */
  const thinMesh = new THREE.InstancedMesh(ctx.keep(new THREE.RingGeometry(0.93, 1, 44).rotateX(-Math.PI / 2)), ringMesh.material, RMAX);
  thinMesh.count = 0; thinMesh.frustumCulled = false; thinMesh.renderOrder = 3; thinMesh.name = 'infra-rings-thin';
  group.add(thinMesh);
  /* ореолы: точки с мягкой текстурой, два размера */
  const haloSet = (cap, size) => {
    const pos = new Float32Array(cap * 3), col = new Float32Array(cap * 3);
    const g = ctx.keep(new THREE.BufferGeometry());
    const pa = new THREE.BufferAttribute(pos, 3), ca = new THREE.BufferAttribute(col, 3);
    pa.setUsage(THREE.DynamicDrawUsage); ca.setUsage(THREE.DynamicDrawUsage);
    g.setAttribute('position', pa); g.setAttribute('color', ca); g.setDrawRange(0, 0);
    const m = ctx.keep(new THREE.PointsMaterial({ size, sizeAttenuation: true, map: kit.radial, vertexColors: true, transparent: true, opacity: 0.9, depthWrite: false }));
    const pts = new THREE.Points(g, m); pts.frustumCulled = false; pts.renderOrder = 4;
    group.add(pts);
    return { pts, pos, col, pa, ca, cap, size, n: 0 };
  };
  const halos = [haloSet(24, 15), haloSet(24, 42)];
  /* дуги пути беды и пунктир «кого звать» */
  const arcBuf = kit.prisms(1100);
  arcBuf.mesh.name = 'infra-chain'; arcBuf.mesh.renderOrder = 2; group.add(arcBuf.mesh);
  /* огни по дугам */
  const PMAX = 64;
  const pulseMesh = new THREE.InstancedMesh(ctx.keep(new THREE.IcosahedronGeometry(2.1, 0)), ctx.keep(new THREE.MeshBasicMaterial({ color: 0xffffff })), PMAX);
  pulseMesh.count = 0; pulseMesh.frustumCulled = false; pulseMesh.name = 'infra-chain-pulses';
  group.add(pulseMesh);

  /* запас дуг: точки кривой без новых векторов в кадре */
  const AMAX = 60;
  const arcs = Array.from({ length: AMAX }, () => ({ pts: Array.from({ length: SEG + 1 }, () => new THREE.Vector3()), len: 0 }));
  let nArcs = 0;
  const staticRings = [];                  // {x, y, z, r, hex, pulse}
  const staticHalos = [];
  let call = null;                         // {a, b} — пунктир от человека к беде

  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(), pp = new THREE.Vector3(), cc = new THREE.Color(), white = new THREE.Color(0xffffff);
  const va = new THREE.Vector3(), vb = new THREE.Vector3(), vm = new THREE.Vector3();
  /* свои места колец для узлов, где центр площадки не там, где вещь видна
     (пруд хвостохранилища лежит в понижении пляжа, не в середине чаши) */
  const anchors = new Map();               // узел -> {x, z, r, y}
  const rOf = n => {
    const A = anchors.get(n); if (A) return A.r;
    const N = ctx.NODES[n];
    if (!N) return 12;
    if (N.r) return Math.min(70, N.r * 1.12);
    return Math.min(70, Math.max(10, Math.max(N.w || 20, N.d || 20) * 0.42));
  };
  const posOf = n => { const A = anchors.get(n); return A ? new THREE.Vector3(A.x, A.y, A.z) : layout.pos(n); };
  const groundAt = (x, z) => groundFn ? groundFn(x, z) : ctx.heightAt(x, z);
  /* точка над вещью для дуги: верх узла (или машины) + немного */
  const topOf = (n, out, lift) => {
    const A = anchors.get(n);
    if (A) return out.set(A.x, Math.max(A.y, groundAt(A.x, A.z)) + (lift == null ? 3 : lift), A.z);
    const p = layout.top(n, lift == null ? 3 : lift); if (!p) return null; out.copy(p); return out;
  };
  const arc = (a, b, slot, lift) => {
    const A = arcs[slot];
    const d = Math.hypot(b.x - a.x, b.z - a.z);
    vm.set((a.x + b.x) / 2, Math.max(a.y, b.y) + (lift == null ? 10 + 0.14 * d : lift), (a.z + b.z) / 2);
    for (let i = 0; i <= SEG; i++) {
      const t = i / SEG, u = 1 - t;
      A.pts[i].set(u * u * a.x + 2 * u * t * vm.x + t * t * b.x, u * u * a.y + 2 * u * t * vm.y + t * t * b.y, u * u * a.z + 2 * u * t * vm.z + t * t * b.z);
    }
    A.len = 0; for (let i = 1; i <= SEG; i++) A.len += A.pts[i].distanceTo(A.pts[i - 1]);
    return A;
  };

  /* после опроса: узлы бед, путь до меди, дуги */
  function rebuild(state) {
    staticRings.length = 0; staticHalos.length = 0; nArcs = 0;
    arcBuf.reset();
    const issues = state.issueNodes || new Set();
    for (const n of issues) {
      const p = posOf(n); if (!p) continue;
      const y = Math.max(p.y, groundAt(p.x, p.z)) + 0.5;
      staticRings.push({ x: p.x, y, z: p.z, r: rOf(n), hex: G.issue, pulse: true });
      const t = topOf(n, va, 8); if (t) staticHalos.push({ x: t.x, y: t.y, z: t.z, hex: G.issue, big: true });
    }
    for (const n of (state.chain || [])) {
      if (issues.has(n)) continue;
      const p = posOf(n); if (!p) continue;
      const y = Math.max(p.y, groundAt(p.x, p.z)) + 0.5;
      staticRings.push({ x: p.x, y, z: p.z, r: rOf(n) * 0.9, hex: n === 'conc-stock' ? 0xc8792f : G.chain, pulse: false, thin: true });
    }
    /* дуги: обход вниз по потоку от каждой беды, только шаги на один уровень глубже */
    const drawn = new Set();
    /* издалека дуги толще (как фигурки людей): ширина пересчитывается на каждом опросе */
    const W = Math.max(1, Math.min(1.9, (state.camDist || 0) / 1300));
    for (const src of issues) {
      const waterish = /^(water|piezo)/.test(src) || ['water-trouble', 'piezo'].includes(AKT.cat(src));
      const depth = new Map([[src, 0]]), qq = [src];
      while (qq.length) {
        const n = qq.shift();
        for (const f of AKT.feeds(n)) {
          if (f === 'water' && !waterish) continue;
          if (!depth.has(f)) { depth.set(f, depth.get(n) + 1); qq.push(f); }
          if (depth.get(f) !== depth.get(n) + 1) continue;
          const key = n + '>' + f;
          if (drawn.has(key) || nArcs >= AMAX) continue;
          drawn.add(key);
          if (!topOf(n, va) || !topOf(f, vb)) continue;
          const A = arc(va, vb, nArcs++);
          for (let i = 1; i <= SEG; i++) arcBuf.add(A.pts[i - 1], A.pts[i], 1.05 * W, G.chain);
        }
      }
    }
    /* «кого звать к беде 1»: точечный пунктир от человека к узлу беды */
    if (call && nArcs < AMAX) {
      const A = arc(call.a, call.b, AMAX - 1, 18 + 0.1 * call.a.distanceTo(call.b));
      for (let i = 1; i <= SEG; i++) if (i % 2) arcBuf.add(A.pts[i - 1], A.pts[i], 0.8 * W, 0xd99a1e);
    }
    arcBuf.commit();
  }

  /* кадр: сюда другие части модуля кладут свои кольца и ореолы */
  const frameRings = [], frameHalos = [];
  const api = {
    begin() { frameRings.length = 0; frameHalos.length = 0; },
    ring(x, y, z, r, hex, pulse, thin) { if (frameRings.length < RMAX) frameRings.push({ x, y, z, r, hex, pulse, thin }); },
    halo(x, y, z, hex, big) { frameHalos.push({ x, y, z, hex, big }); },
    setCall(a, b) { call = a && b ? { a: a.clone(), b: b.clone() } : null; },
    /* место кольца узла (модуль, который рисует вещь не в центре площадки) */
    anchor(n, x, y, z, r) { anchors.set(n, { x, y, z, r }); },
    /* точка над узлом для пунктира «кого звать»: своё место или layout.top */
    target(n, lift) { return topOf(n, new THREE.Vector3(), lift); },
    end(state) {
      if (state.fresh) rebuild(state);
      const s = 0.5 + 0.5 * Math.sin(state.t * 4.2);
      /* кольца */
      const cnt = [0, 0];
      const putRing = R => {
        const M = R.thin ? thinMesh : ringMesh, j = R.thin ? 1 : 0;
        if (cnt[j] >= RMAX) return;
        const r = R.r * (R.pulse ? 1 + 0.14 * s : 1);
        m4.compose(pp.set(R.x, R.y, R.z), q.identity(), sc.set(r, 1, r));
        M.setMatrixAt(cnt[j], m4);
        cc.setHex(R.hex); if (R.pulse) cc.lerp(white, 0.35 * (1 - s));
        M.setColorAt(cnt[j], cc);
        cnt[j]++;
      };
      for (const R of staticRings) putRing(R);
      for (const R of frameRings) putRing(R);
      ringMesh.count = cnt[0]; thinMesh.count = cnt[1];
      for (const M of [ringMesh, thinMesh]) { M.instanceMatrix.needsUpdate = true; if (M.instanceColor) M.instanceColor.needsUpdate = true; M.visible = M.count > 0; }
      /* ореолы */
      for (const H of halos) H.n = 0;
      const putHalo = h => {
        const H = halos[h.big ? 1 : 0]; if (H.n >= H.cap) return;
        H.pos[3 * H.n] = h.x; H.pos[3 * H.n + 1] = h.y; H.pos[3 * H.n + 2] = h.z;
        cc.setHex(h.hex); H.col[3 * H.n] = cc.r; H.col[3 * H.n + 1] = cc.g; H.col[3 * H.n + 2] = cc.b;
        H.n++;
      };
      for (const h of staticHalos) putHalo(h);
      for (const h of frameHalos) putHalo(h);
      for (const H of halos) {
        H.pts.geometry.setDrawRange(0, H.n); H.pa.needsUpdate = true; H.ca.needsUpdate = true;
        H.pts.material.size = H.size * (0.85 + 0.3 * s);
        H.pts.visible = H.n > 0;
      }
      /* огни по дугам пути беды: от беды к меди */
      let p = 0;
      for (let i = 0; i < nArcs && p < PMAX; i++) {
        const A = arcs[i];
        const u = ((state.t * 0.42 + i * 0.37) % 1);
        const f = u * SEG, j = Math.min(SEG - 1, Math.floor(f));
        pp.lerpVectors(A.pts[j], A.pts[j + 1], f - j);
        m4.compose(pp, q.identity(), sc.set(1, 1, 1));
        pulseMesh.setMatrixAt(p, m4);
        pulseMesh.setColorAt(p, cc.setHex(0xf3cf7a));
        p++;
      }
      pulseMesh.count = p;
      pulseMesh.instanceMatrix.needsUpdate = true;
      if (pulseMesh.instanceColor) pulseMesh.instanceColor.needsUpdate = true;
    },
  };
  /* цвета экземпляров создаются до первого кадра */
  ringMesh.setColorAt(0, white); thinMesh.setColorAt(0, white); pulseMesh.setColorAt(0, white);
  return api;
}
