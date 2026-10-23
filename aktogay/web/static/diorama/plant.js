/* «Диорама», модуль «фабрика» (договор — API.md). Две линии обогащения в корпусах-разрезах:
   SAG (вращается, пока RUN; стоит при STOP / RELINE), дробление гали и HPGR (валки
   вращаются; пожар — pebble-N.fire), две шаровые мельницы на линию, батарея гидроциклонов
   (открытые — светлые, open_count), основная и перечистная флотация с пеной (высота и цвет
   пены — по извлечению из Ditto), сгуститель концентрата (гребки вращаются, пятно ила ∝
   inventory_t), фильтр-прессы (лампа на каждый работающий пресс, presses_on), ленты кека.
   Подача руды (ЦПД, конвейеры, склады, питатели) — plant_feed.js; склад концентрата, ж/д
   и вагоны — plant_ship.js; заготовки и общие пулы — plant_geo.js.
   Линия 2 — основное оборудование FLSmidth, безредукторные (кольцевые) приводы мельниц,
   HPGR thyssenkrupp POLYCOM (паспорта line-2, sag-2, ball-2*, pebble-2 в Ditto): синяя отделка
   и голубые корпуса мельниц, кольцевой статор вокруг барабана, крупный HPGR. Привод мельниц
   линии 1 в Ditto не указан — показан условным блоком двигателя. Всё — схема, не масштаб. */
import { kit, finishPools, STYLE, NB } from './plant_geo.js';
import { buildFeed } from './plant_feed.js';
import { buildShip } from './plant_ship.js';

export function build(ctx) {
  const { THREE, AKT, scene } = ctx;
  const K = kit(ctx);
  const group = new THREE.Group(); group.name = 'plant';
  scene.add(group);
  const froth = [], cyclones = [];
  const parts = [];
  const step = (name, f) => { try { const r = f(); if (r) parts.push(r); } catch (e) { console.error(e); ctx.note(`фабрика: часть «${name}» не построилась: ${e && e.message ? e.message : e}`); } };
  step('подача руды', () => buildFeed(ctx, K, group));
  for (const n of [1, 2]) step(`линия ${n}`, () => buildLine(ctx, K, group, n, froth, cyclones));
  step('склад концентрата', () => buildShip(ctx, K, group));
  const shared = buildShared(ctx, K, group, froth, cyclones);
  const pools = finishPools(ctx, K, group);
  /* ?perf=1: своя часть сцены для замеров (вызовы отрисовки, треугольники, скрыть/показать) */
  const dbg = AKT.params.get('perf') === '1';
  if (dbg) window.__dioPlant = {
    group, ctx,
    stat() {
      let calls = 0, tris = 0;
      group.traverseVisible(o => {
        if (!o.isMesh) return;
        const g = o.geometry, n = (g.index ? g.index.count : g.attributes.position.count) / 3;
        calls++; tris += n * (o.isInstancedMesh ? o.count : 1);
      });
      return { calls, tris: Math.round(tris) };
    },
  };
  return {
    update(state, dt) {
      for (const p of parts) p.update(state, dt);
      shared.update(state, dt);
      pools.update(state, dt);
    },
    destroy() { scene.remove(group); if (dbg) delete window.__dioPlant; },
  };
}

/* ------------------------------------------------------------------ линия */
function buildLine(ctx, K, group, n, froth, cyclones) {
  const { THREE, AKT, NODES } = ctx;
  const { box, cyl, cylZ, beam, wallX, ring, ringX, body, pipe, lamp, band, stream, spin } = K;
  const S = STYLE[n];
  const L2 = n === 2;
  const z0 = NODES[`line-${n}`].z;
  const G = ctx.heightAt(NODES[`line-${n}`].x, z0);
  const id = { line: `line-${n}`, sag: `sag-${n}`, peb: `pebble-${n}`, a: `ball-${n}a`, b: `ball-${n}b`, cyc: `cyclones-${n}`,
    flot: `flot-${n}`, ro: `rougher-${n}`, cl: `cleaner-${n}`, an: `analyzer-${n}`, fm: `flowmeter-${n}`, th: `thick-${n}`, fi: `filter-${n}` };
  const N = k => NODES[id[k]];
  const has = x => !!AKT.things[x];
  const V = (x, y, z) => new THREE.Vector3(x, y, z);
  const run = x => has(x) && !AKT.stopped(AKT.st(x));
  const ups = [];
  const CONC = 0xbdb7ac, FRAME = 0x7c848c;
  const vc = () => ctx.materials.vc;

  /* корпус-разрез: задняя стена во всю высоту, боковые — со срезом к фронту, низкая передняя,
     кровля над задней частью, каркас над открытой */
  const hall = (P, o) => {
    const { x0, x1, za, zb, H } = o, t = 1.6, W = x1 - x0, cx = (x0 + x1) / 2, D = zb - za;
    const Hf = 0.28 * H;
    P.push(box(W, 0.35, D, cx, G, za + D / 2, S.floor));
    P.push(box(W, H, t, cx, G, za + t / 2, S.wall));
    P.push(box(W + 0.4, 2.4, t + 0.8, cx, G + H - 2.4, za + t / 2, S.trim));
    P.push(box(W - 8, 3, 0.4, cx, G + H - 9, za + t + 0.2, S.glass));
    P.push(box(W, 1.4, 0.5, cx, G + 0.35, za + t + 0.25, S.trim));
    for (const x of [x0, x1 - t]) {
      P.push(wallX([[za, G], [zb, G], [zb, G + Hf], [za, G + H]], x, t, S.wall));
      P.push(beam([x + t / 2, G + H, za], [x + t / 2, G + Hf, zb], 1.3, S.trim));
    }
    P.push(box(W, 4, 1.2, cx, G, zb - 0.6, S.wall));
    P.push(box(W + 1.2, 1.2, o.roof, cx, G + H, za + o.roof / 2, S.roof));
    for (const x of o.cols || [x0 + 0.6, x1 - 0.6]) {
      P.push(beam([x, G, zb - 0.6], [x, G + H + 0.6, zb - 0.6], 1.2, S.trim));
      P.push(beam([x, G + H + 0.6, za + o.roof], [x, G + H + 0.6, zb - 0.6], 0.9, S.trim));
    }
    P.push(beam([x0, G + H + 0.6, zb - 0.6], [x1, G + H + 0.6, zb - 0.6], 1.2, S.trim));
    if (o.crane != null) {
      const cy = G + H - 7;
      P.push(beam([x0 + 2, cy, za + 2.6], [x1 - 2, cy, za + 2.6], 1, S.trim), beam([x0 + 2, cy, zb - 2], [x1 - 2, cy, zb - 2], 1, S.trim));
      P.push(box(3.2, 2.6, D - 4, o.crane, cy + 0.5, za + D / 2, S.crane), box(5, 2.2, 5, o.crane, cy - 1.8, za + D * 0.42, 0x4b525a));
    }
    return P;
  };

  /* -------------------------------------------------- корпус измельчения */
  {
    const P = hall([], { x0: 238, x1: 416, za: z0 - 60, zb: z0 + 40, H: 48, roof: 26, cols: [238.6, 300, 360, 415.4], crane: 310 });
    const m = body(P, id.line);
    group.add(m);
    ctx.onClick(id.line, m);
  }

  /* ------------------------------------------------------------- SAG */
  const sx = N('sag').x, sAy = G + 21.5, SR = 16, SL = 20;
  {
    const P = [];
    /* опоры цапф, загрузочная воронка и течка, разгрузочный зумпф под бутарой */
    P.push(box(5.5, sAy - 4.6 - G, 14, sx - 17, G, z0, CONC), box(5.5, sAy - 4.6 - G, 14, sx + 17, G, z0, CONC));
    P.push(box(7, 6, 9, sx - 25, G + 26, z0, S.equip), beam([sx - 23, G + 27.5, z0], [sx - 18.5, sAy + 1, z0], 3, S.equip));
    P.push(box(11, 9, 13, sx + 23, G, z0, CONC));
    if (L2) {
      /* безредукторный привод: кольцевой статор вокруг барабана на фундаменте */
      P.push(ringX(SR + 0.7, SR + 3.3, 5, sx + 3, sAy, z0, S.accent, 30));
      P.push(box(7, sAy - SR - 3.3 - G + 1.2, 2 * SR + 10, sx + 3, G, z0, CONC));
    } else {
      P.push(box(9, 8, 7, sx + 6, G, z0 + 22, S.accent), box(4, 5, 3, sx + 6, G + 2, z0 + 17.5, S.trim));
    }
    /* площадка обслуживания вдоль мельницы */
    P.push(box(26, 0.8, 4, sx, G + 12, z0 - SR - 4, 0x8d949c));
    P.push(beam([sx - 12, G, z0 - SR - 5.5], [sx - 12, G + 12, z0 - SR - 5.5], 0.8, 0x8d949c), beam([sx + 12, G, z0 - SR - 5.5], [sx + 12, G + 12, z0 - SR - 5.5], 0.8, 0x8d949c));
    const m = body(P, id.sag);
    group.add(m);
    ctx.onClick(id.sag, m);
    band(id.sag, L2 ? [sx + 3, sAy, z0] : [sx + SL / 2 - 0.45, sAy, z0], L2 ? SR + 3.4 : SR + 0.8);
    lamp(id.sag, [sx - 25, G + 33.5, z0 + 3]);
    stream([sx + 23, sAy - 4.2, z0], () => G + 9, 3, 0x7d7a72, () => run(id.sag) && (AKT.num(id.sag, 'feed_tph') || 0) > 1);
  }
  const sagDrum = spin('sag-drum', () => ({ geometry: K.drum(SR, SL, { head: 5, trunnion: 5.6, tl: 4, trommel: 8, stripes: 12 }), material: vc() }),
    { id: id.sag, pos: [sx, sAy, z0], axis: 'x', color: S.shell });

  /* ---------------------------------------------------------- шаровые */
  const balls = [];
  for (const k of ['a', 'b']) {
    const bid = id[k], nb = NODES[bid], bx = nb.x, bz = nb.z, side = bz < z0 ? -1 : 1;
    const R = 11, Lb = 30, ay = G + 15;
    const P = [];
    P.push(box(4.5, ay - 3.3 - G, 11, bx - 19.5, G, bz, CONC), box(4.5, ay - 3.3 - G, 11, bx + 19.5, G, bz, CONC));
    P.push(box(4, 4, 4, bx - 23, ay - 1, bz, S.equip));
    if (L2) {
      P.push(ringX(R + 0.6, R + 2.6, 4, bx + 6, ay, bz, S.accent, 26));
      P.push(box(5, ay - R - 2.6 - G + 1, 2 * R + 7, bx + 6, G, bz, CONC));
    } else {
      P.push(box(8, 7, 7, bx + 4, G, bz + side * 17, S.accent), box(3.5, 4, 3, bx + 4, G + 2, bz + side * 12.5, S.trim));
    }
    const m = body(P, bid);
    group.add(m);
    ctx.onClick(bid, m);
    balls.push({ id: bid, sp: spin('ball-drum', () => ({ geometry: K.drum(R, Lb, { head: 3, trunnion: 4, tl: 3, stripes: 10 }), material: vc() }),
      { id: bid, pos: [bx, ay, bz], axis: 'x', color: S.shell }) });
    band(bid, L2 ? [bx + 6, ay, bz] : [bx + Lb / 2 - 0.45, ay, bz], L2 ? R + 2.7 : R + 0.8);
    lamp(bid, [bx - 23, ay + 4.6, bz]);
    /* разгрузка в зумпф циклонов; питание — пески циклонов */
    pipe([[bx + 21, ay - 1, bz], [372, G + 8, bz], [376, G + 8, z0 + side * 5]], 1.1, `${bid}>${id.cyc}`);
    pipe([[396, G + 19, z0 + side * 4], [394, G + 29, bz], [bx - 24, G + 29, bz], [bx - 24, ay + 2.6, bz]], 1, `${id.cyc}>${bid}`);
  }

  /* ------------------------------------------- дробление гали и HPGR */
  const pb = N('peb'), px = pb.x, pz = pb.z;
  const hpgrX = L2 ? 306 : 311;
  const rolls = [];
  const outA = [sx + 31, G + 6, z0 - 6], outB = [290, G + 13, pz + 5];
  const backA = [hpgrX + 5, G + 9, pz + 6], backB = [sx - 22, G + 31, z0 - 22];
  {
    const P = [box(44, 0.8, 22, px, G, pz, CONC)];
    const cone = x => P.push(cyl(3.4, 5, x, G + 0.8, pz, S.equip, 14), cyl(3.4, 2.6, x, G + 5.8, pz, S.accent, 14, 1.3), cyl(1.3, 2.6, x, G + 8.4, pz, S.equip, 12, 3));
    if (L2) {
      cone(283);
      P.push(box(15, 7.5, 12, hpgrX, G + 0.8, pz, S.accent), box(15.6, 1, 12.6, hpgrX, G + 8.3, pz, S.trim));
      P.push(box(4, 4, 5, hpgrX - 3.2, G + 8.3, pz + 8.5, S.equip), box(4, 4, 5, hpgrX + 3.2, G + 8.3, pz + 8.5, S.equip));
      P.push(cyl(2, 3.4, hpgrX, G + 15, pz, S.equip, 12, 5));
    } else {
      cone(283); cone(293);
      P.push(box(11, 6, 9, hpgrX, G + 0.8, pz, S.accent), box(11.6, 0.8, 9.6, hpgrX, G + 6.8, pz, S.trim));
      P.push(box(3, 3, 3.6, hpgrX - 2.2, G + 6.8, pz + 6.5, S.equip), box(3, 3, 3.6, hpgrX + 2.2, G + 6.8, pz + 6.5, S.equip));
      P.push(cyl(1.6, 2.6, hpgrX, G + 11.5, pz, S.equip, 12, 4));
    }
    /* эстакады лент гали и течка возврата в загрузку SAG */
    K.trestle(P, outA, outB, 3.6, 10, FRAME);
    K.trestle(P, backA, backB, 3.6, 14, FRAME);
    P.push(beam([sx - 22, G + 31, z0 - 22], [sx - 24, G + 29.5, z0 - 4], 2.2, S.equip));
    const m = body(P, id.peb);
    group.add(m);
    ctx.onClick(id.peb, m);
    /* валки HPGR: два встречно вращающихся, с полосами шипов (экземпляры, ось z) */
    const rr = L2 ? 3.3 : 2.3, rl = L2 ? 10 : 7, ry = L2 ? G + 11.6 : G + 9.1, dx = L2 ? 3.4 : 2.4;
    for (const s of [-1, 1]) {
      rolls.push(spin('hpgr-roll', () => ({ geometry: K.stripes(ctx.merge([cylZ(1, 1, 0, 0, 0, 0xffffff, 16)]), 'z', 10, 0.68, 0.5), material: vc() }),
        { id: id.peb, pos: [hpgrX + s * dx, ry, pz], axis: 'z', dir: s, s: [rr, rr, rl], color: 0x7a828b }));
    }
    lamp(id.peb, [hpgrX + (L2 ? 6.5 : 4.5), G + (L2 ? 10.5 : 8.6), pz - (L2 ? 5.5 : 4)]);
  }
  /* ленты: гали с бутары на дробление, продукт обратно в SAG */
  const pebOut = K.belt(outA, outB, 3.6, { id: id.peb, rep: 10 });
  const pebBack = K.belt(backA, backB, 3.6, { id: id.peb, rep: 10 });

  /* пожар на участке HPGR (pebble-N.fire = 1): пламя и дым, схема */
  const fire = new THREE.Group(); fire.visible = false; fire.name = id.peb + '-fire';
  const flames = [], smoke = [];
  {
    const fg = ctx.keep(new THREE.ConeGeometry(1, 1, 7, 1).translate(0, 0.5, 0));
    const fm1 = ctx.keep(new THREE.MeshBasicMaterial({ color: 0xff6a1a })), fm2 = ctx.keep(new THREE.MeshBasicMaterial({ color: 0xffc23a }));
    /* языки пламени крупнее масштаба (видны с пресета «Фабрика»), светятся сами */
    for (let i = 0; i < 7; i++) {
      const f = new THREE.Mesh(fg, i % 2 ? fm2 : fm1);
      f.position.set(hpgrX - 7 + i * 2.4, G + 9 + (i % 2), pz + (i % 3 - 1) * 3);
      fire.add(f); flames.push({ m: f, k: 0.7 + 0.12 * i, s: 3.2 + (i % 3) * 1.1 });
    }
    const sg = ctx.keep(new THREE.IcosahedronGeometry(1, 0));
    const sm = ctx.mat(0x3f4144);
    for (let i = 0; i < 5; i++) { const s = new THREE.Mesh(sg, sm); fire.add(s); smoke.push({ m: s, ph: i / 5 }); }
    group.add(fire);
  }

  /* ------------------------------------------------------- гидроциклоны */
  const cx0 = N('cyc').x, Gd = G + 27;
  {
    const P = [];
    for (const [dx, dz] of [[-9, -9], [9, -9], [9, 9], [-9, 9]]) P.push(beam([cx0 + dx, G, z0 + dz], [cx0 + dx, Gd - 1, z0 + dz], 1.1, S.trim));
    P.push(box(22, 1, 22, cx0, Gd - 1, z0, 0x8d949c));
    P.push(cyl(3.2, 7, cx0, Gd, z0, S.equip, 14), cyl(3.2, 1.4, cx0, Gd + 7, z0, S.accent, 14, 1.4));
    P.push(ring(8.7, 10.2, 1.8, cx0, Gd + 5.2, z0, S.launder, 24));
    P.push(ring(3.5, 8.5, 1.4, cx0, Gd - 9, z0, S.launder, 20));
    /* зумпф и насос питания циклонов */
    P.push(box(12, 9, 16, 380, G, z0, CONC), cyl(2.2, 3.4, 381, G, z0 + 11, S.accent, 12));
    const m = body(P, id.cyc);
    group.add(m);
    ctx.onClick(id.cyc, m);
    const units = Math.max(4, Math.min(24, Math.round(AKT.pass(id.cyc, 'units') || 14)));
    for (let i = 0; i < units; i++) {
      const a = 2 * Math.PI * i / units + 0.2;
      cyclones.push({ id: id.cyc, i, x: cx0 + 6.7 * Math.cos(a), y: Gd, z: z0 + 6.7 * Math.sin(a), a });
    }
    lamp(id.cyc, [cx0, Gd + 9.6, z0]);
    pipe([[300, G + 5, z0], [374, G + 5, z0]], 1.4, `${id.sag}>${id.cyc}`);
    pipe([[381, G + 2.5, z0 + 11], [388, G + 2.5, z0 + 11], [388, Gd + 4, z0 + 11], [cx0 - 2.5, Gd + 4, z0 + 2.5]], 1.1, `${id.sag}>${id.cyc}`);
    pipe([[cx0 + 10, Gd + 6, z0], [418, Gd + 6, z0 - 6], [431, G + 16, z0 - 22]], 1.2, `${id.cyc}>${id.ro}`);
  }

  /* -------------------------------------------------------------- флотация */
  {
    const P = hall([], { x0: 424, x1: 546, za: z0 - 38, zb: z0 + 38, H: 28, roof: 14, cols: [424.6, 485, 545.4] });
    /* поточный анализатор (шкаф) и расходомер собирателя (бак реагента, расходомер) — их карточки
       открывает лампа над ними */
    const a = N('an'), f = N('fm'), fz = z0 - 33;
    P.push(box(6, 9, 4, a.x, G, a.z - 1.5, 0xf2f2ef), box(4, 3, 0.3, a.x, G + 4.5, a.z + 0.6, 0x34383d), beam([a.x, G + 6, a.z - 3.5], [a.x - 8, G + 9, z0 + 28.6], 0.5, 0x59606a));
    P.push(cyl(2.2, 6, f.x - 5, G, fz, 0xf2f2ef, 12), box(2.4, 2, 2.4, f.x + 1, G + 3, fz, 0x59606a), box(6, 0.8, 4, f.x - 2, G, fz, 0x8d949c));
    const m = body(P, id.flot);
    group.add(m);
    ctx.onClick(id.flot, m);
    ctx.claim([id.an, id.fm]);
    lamp(id.an, [a.x + 2, G + 10, a.z - 1.5], null, 1.2);
    lamp(id.fm, [f.x + 1, G + 6, fz], null, 1.1);
    pipe([[f.x + 1, G + 4, fz], [f.x + 1, G + 4, z0 - 27.5], [432, G + 15, z0 - 26]], 0.5, '', id.fm);
  }
  const bank = (bid, n0, x0, dx, z, r, h, feedX) => {
    const P = [];
    for (let i = 0; i < n0; i++) {
      const x = x0 + i * dx;
      P.push(cyl(r, h, x, G, z, S.cell, K.soft ? 12 : 16));
      P.push(ring(r - 0.2, r + 1.1, 1.3, x, G + h - 1.1, z, S.launder, K.soft ? 12 : 16));
      P.push(box(1.2, 1, 2 * r + 1.8, x, G + h + 1.6, z, S.accent), box(2.2, 2.6, 2.2, x, G + h + 2.6, z, S.accent));
      froth.push({ id: bid, flot: id.flot, x, y: G + h - 0.3, z, r: r - 0.45, h: 0.6, hGoal: 0.6, col: new THREE.Color(0xa9a28c), colGoal: new THREE.Color(0xa9a28c) });
    }
    const side = z < z0 ? 1 : -1;               // жёлоб концентрата — к соседнему ряду
    const lx0 = x0 - r, lx1 = x0 + (n0 - 1) * dx + r;
    P.push(box(lx1 - lx0, 1.8, 2, (lx0 + lx1) / 2, G + h - 2.6, z + side * (r + 1.4), S.launder));
    P.push(box(6, h + 2, 9, feedX, G, z, S.equip), box(6, h - 4, 8, lx1 + 4, G, z, S.equip));
    const m = body(P, bid);
    group.add(m);
    ctx.onClick(bid, m);
    lamp(bid, [feedX, G + h + 3.2, z]);
  };
  bank(id.ro, 7, 440, 13.5, N('ro').z, 6, 13, 431);
  bank(id.cl, 5, 441, 12, N('cl').z, 5, 11, 434);
  pipe([[436, G + 11, z0 - 14.5], [436, G + 11, z0 + 14.5]], 1, `${id.ro}>${id.cl}`);
  pipe([[494, G + 9.5, z0 + 28.6], [540, G + 9.5, z0 + 28.6], [552, G + 11.5, z0 + 6], [N('th').x - 4, G + 11.5, z0 + 1.5]], 1.1, `${id.cl}>${id.th}`);

  /* -------------------------------------------------------- сгуститель */
  const t = N('th'), tx = t.x, tz = t.z;
  {
    const P = [];
    P.push(ring(24, 25.4, 9, tx, G, tz, 0xc9c4ba, 32));
    P.push(cyl(24, 0.4, tx, G + 7.6, tz, 0x93b7b4, 32));
    P.push(ring(22.4, 24, 1, tx, G + 7.4, tz, 0x9aa1a8, 32));
    P.push(cyl(4, 3, tx, G + 6.4, tz, S.equip, 14));
    P.push(box(27, 1.4, 3.2, tx - 13, G + 10, tz, S.accent));
    P.push(beam([tx - 26, G + 12.6, tz - 1.6], [tx, G + 12.6, tz - 1.6], 0.35, 0xf2b500), beam([tx - 26, G + 12.6, tz + 1.6], [tx, G + 12.6, tz + 1.6], 0.35, 0xf2b500));
    P.push(box(2.4, 10.4, 3.4, tx - 25, G, tz, CONC));
    P.push(cyl(3.6, 3, tx, G + 10, tz, S.accent, 14), box(2.4, 2, 2.4, tx, G + 13, tz, S.trim));
    P.push(box(5, 4, 5, tx + 29, G, tz + 6, S.equip));
    const m = body(P, id.th);
    group.add(m);
    ctx.onClick(id.th, m);
    lamp(id.th, [tx, G + 15.8, tz]);
    pipe([[tx + 29, G + 3, tz + 6], [614, G + 3, tz + 6], [622, G + 8, z0 + 1]], 1, `${id.th}>${id.fi}`);
  }
  /* пятно ила (∝ inventory_t) и гребки — экземпляры */
  const mud = spin('mud', () => ({ geometry: ctx.keep(ctx.bake(new THREE.CircleGeometry(1, 28).rotateX(-Math.PI / 2), { color: 0x4a463f })), material: ctx.materials.baked }),
    { id: id.th, pos: [tx, G + 8.15, tz], axis: 'y', s: [4, 1, 4], color: 0xffffff });
  const rake = spin('rake', () => ({
    geometry: ctx.merge([
      { geometry: new THREE.BoxGeometry(44, 0.5, 1.2), color: 0x3c4249, position: [0, 0, 0] },
      ...[-20, -15, -10, -5, 5, 10, 15, 20].map(x => ({ geometry: new THREE.BoxGeometry(0.6, 0.5, 3), color: 0x3c4249, position: [x, 0, 0], rotation: [0, 0.5, 0] })),
    ]),
    material: vc(),
  }), { id: id.th, pos: [tx, G + 8.4, tz], axis: 'y', color: 0xffffff });

  /* ------------------------------------------------------------- фильтр */
  const fi = N('fi'), fx = fi.x;
  const presses = [-8, 8];
  const toConc = n === 1 ? 1 : -1;                  // склад концентрата — к +z от линии 1, к −z от линии 2
  const cakeA = [633, G + 1.8, z0 - toConc * 14], cakeB = [650, G + 20, toConc > 0 ? -62 : 6];
  {
    const P = hall([], { x0: 614, x1: 654, za: z0 - 23, zb: z0 + 23, H: 28, roof: 14, cols: [614.6, 653.4] });
    presses.forEach(dz => {
      const z = z0 + dz;
      for (const [x, s] of [[621, -3], [645, -3], [621, 3], [645, 3]]) P.push(beam([x, G, z + s], [x, G + 9, z + s], 0.8, S.trim));
      P.push(box(2.4, 6, 7, 619, G + 9, z, S.accent), box(2, 5, 7, 647, G + 9, z, S.accent));
      P.push(beam([619, G + 13, z - 3.2], [647, G + 13, z - 3.2], 0.8, S.trim), beam([619, G + 13, z + 3.2], [647, G + 13, z + 3.2], 0.8, S.trim));
      P.push(box(24, 4.6, 5.2, 633, G + 9.4, z, 0x59606a));
      for (let k = 0; k < 10; k++) P.push(box(1.2, 5, 5.6, 622.2 + k * 2.4, G + 9.2, z, 0xe7e4dc));
      P.push(cyl(1.4, 5, 633, G + 3.2, z, S.equip, 12, 3.6));
    });
    K.trestle(P, cakeA, cakeB, 4, 14, FRAME);
    const m = body(P, id.fi);
    group.add(m);
    ctx.onClick(id.fi, m);
    presses.forEach((dz, i) => {
      const z = z0 + dz;
      lamp(id.fi, [619, G + 16, z], A => {
        if (!A.things[id.fi]) return 'off';
        if (A.stopped(A.st(id.fi))) return 'alarm';
        const on = A.num(id.fi, 'presses_on');
        return on != null && on > i ? 'run' : 'off';
      });
      stream([633, G + 9.2, z], () => G + 3, 2.4, 0x4a463f, () => run(id.fi) && (AKT.num(id.fi, 'presses_on') || 0) > i && (AKT.num(id.fi, 'cake_tph') || 0) > 0);
    });
  }
  /* лента кека на склад концентрата */
  const cake = K.belt(cakeA, cakeB, 4, { id: id.fi, rep: 10 });
  stream([cakeB[0], cakeB[1] - 0.5, cakeB[2] + toConc * 1.5], () => G + 10, 2, 0x4a463f, () => (AKT.num(id.fi, 'cake_tph') || 0) > 0 && run(id.fi));

  /* ------------------------------------------------------------- подписи */
  const tail = x => { const s = AKT.st(x); return !s || ['RUN', 'NORMAL', 'OK'].includes(s) ? '' : ` · ${AKT.stOf(x)}`; };
  const f0 = (x, f) => AKT.fmt(AKT.num(x, f));
  const f1 = (x, f) => AKT.f1(AKT.num(x, f));
  const mw = x => { const v = AKT.num(x, 'power_kw'); return v == null ? '—' : AKT.f1(v / 1000); };
  const lab = (x, text, o) => ctx.label(`plant:${x}`, () => has(x) ? text() : '', Object.assign({ thing: x }, o));
  const vendor = /FLSmidth/.test(String(AKT.pass(id.line, 'package') || ''));
  lab(id.line, () => `${AKT.nameRu(id.line)} · ${f0(id.line, 'tph')}${NB}т/ч · Cu ${f1(id.line, 'cu_tph')}${NB}т/ч${tail(id.line)}\nизвлечение ${f1(id.line, 'recovery')}${NB}%${L2 && vendor ? ' · оборудование FLSmidth' : ''}`, {
    prio: 1, at: V(262, G + 58, z0 - 52),
    title: () => `${AKT.nameRu(id.line)}: ${AKT.stOf(id.line)} · ${f0(id.line, 'tph')} т/ч руды, ${f1(id.line, 'cu_tph')} т/ч меди, извлечение ${f1(id.line, 'recovery')} % (Ditto)${L2 ? ' · ' + (AKT.pass(id.line, 'package') || '') : ''}`,
  });
  lab(id.sag, () => `SAG-${n} · ${mw(id.sag)}${NB}МВт${tail(id.sag)}`, {
    prio: 3, maxDist: 2400, at: V(sx, G + 42, z0),
    title: () => `${AKT.nameRu(id.sag)}: ${AKT.stOf(id.sag)} · ${mw(id.sag)} МВт, питание ${f0(id.sag, 'feed_tph')} т/ч, ${f0(id.sag, 'speed_pct')} % крит. скорости (Ditto)${L2 ? ' · безредукторный привод (паспорт)' : ''}`,
  });
  let fireOn = false, fireT = 0;
  /* при пожаре подпись поднята над столбом дыма, чтобы не закрывать пламя (схема) */
  const pebAt = V(px, G + 20, pz), pebAtFire = V(px, G + 95, pz);
  lab(id.peb, () => {
    const fireOn = (AKT.num(id.peb, 'fire') || 0) > 0;
    return `${AKT.nameRu(id.peb)} · ${f0(id.peb, 'feed_tph')}${NB}т/ч${fireOn ? ' · ПОЖАР' : tail(id.peb)}`;
  }, { prio: 3, maxDist: 1700, at: () => (fireOn ? pebAtFire : pebAt), title: () => `${AKT.nameRu(id.peb)}: ${AKT.stOf(id.peb)} · ${f0(id.peb, 'feed_tph')} т/ч, загрузка ${f0(id.peb, 'load_pct')} % (Ditto) · ${AKT.pass(id.peb, L2 ? 'hpgr' : 'kind') || ''}` });
  for (const k of ['a', 'b']) {
    const bid = id[k];
    /* мелкие узлы подписаны только при отклонении (в норме число — в подсказке и карточке): меньше шума в кадре */
    lab(bid, () => AKT.deviates(bid) ? `${AKT.nameRu(bid).replace(/^Шаровая мельница /, 'Шаровая ')} · ${mw(bid)}${NB}МВт${tail(bid)}` : '', {
      prio: 4, maxDist: 1500, at: V(NODES[bid].x, G + 30, NODES[bid].z), kind: 'small',
    });
  }
  lab(id.cyc, () => `${AKT.nameRu(id.cyc)} · P80 ${f0(id.cyc, 'p80_um')}${NB}мкм${tail(id.cyc)}`, {
    prio: 3, maxDist: 1800, at: V(cx0, Gd + 13, z0),
    title: () => `${AKT.nameRu(id.cyc)}: ${AKT.stOf(id.cyc)} · P80 ${f0(id.cyc, 'p80_um')} мкм, давление ${f0(id.cyc, 'pressure_kpa')} кПа, открыто ${f0(id.cyc, 'open_count')} из ${AKT.fmt(AKT.pass(id.cyc, 'units'))} (Ditto)`,
  });
  lab(id.flot, () => `${AKT.nameRu(id.flot)} · извлечение ${f1(id.flot, 'recovery')}${NB}%${tail(id.flot)}\nконцентрат ${f1(id.flot, 'conc_cu')}${NB}% Cu`, {
    prio: 3, maxDist: 2400, at: V(480, G + 34, z0 - 30),
    title: () => `${AKT.nameRu(id.flot)}: ${AKT.stOf(id.flot)} · извлечение ${f1(id.flot, 'recovery')} %, концентрат ${f1(id.flot, 'conc_cu')} % Cu, хвосты ${AKT.f3(AKT.num(id.flot, 'tail_cu'))} % Cu (Ditto) · высота и цвет пены ∝ извлечению (схема)`,
  });
  lab(id.ro, () => AKT.deviates(id.ro) ? `${AKT.nameRu(id.ro).replace(/^Основная и контрольная флотация/, 'Основная')} · ${f1(id.ro, 'stage_recovery')}${NB}%${tail(id.ro)}` : '', { prio: 6, maxDist: 1300, kind: 'small', at: V(482, G + 20, N('ro').z) });
  lab(id.cl, () => AKT.deviates(id.cl) ? `${AKT.nameRu(id.cl)} · ${f1(id.cl, 'stage_recovery')}${NB}%${tail(id.cl)}` : '', { prio: 6, maxDist: 1300, kind: 'small', at: V(465, G + 18, N('cl').z) });
  lab(id.an, () => AKT.deviates(id.an) ? `${AKT.nameRu(id.an)} · ${AKT.stOf(id.an)}` : '', { prio: 6, kind: 'small', at: V(N('an').x, G + 13, N('an').z) });
  lab(id.fm, () => AKT.deviates(id.fm) ? `${AKT.nameRu(id.fm)} · ${AKT.stOf(id.fm)}` : '', { prio: 6, kind: 'small', at: V(N('fm').x, G + 10, z0 - 33) });
  /* слив на фильтр — главное число; запас в сгустителе — когда он заметен (в норме слив ≈ питанию, запас ≈ 0) */
  lab(id.th, () => {
    const inv = AKT.num(id.th, 'inventory_t');
    return `${AKT.nameRu(id.th).replace(/ концентрата/, '')} · слив ${f1(id.th, 'underflow_tph')}${NB}т/ч${inv != null && inv >= 1 ? ` · запас ${f1(id.th, 'inventory_t')}${NB}т` : ''}${tail(id.th)}`;
  }, {
    prio: 3, maxDist: 2000, at: V(tx, G + 18, tz),
    title: () => `${AKT.nameRu(id.th)}: ${AKT.stOf(id.th)} · в сгустителе ${f1(id.th, 'inventory_t')} т, слив ${f1(id.th, 'underflow_tph')} т/ч (Ditto) · пятно ила ∝ запасу (схема)`,
  });
  lab(id.fi, () => `${AKT.nameRu(id.fi).replace(/ концентрата/, '')} · ${f1(id.fi, 'cake_tph')}${NB}т/ч · прессов ${f0(id.fi, 'presses_on')}${tail(id.fi)}`, {
    prio: 3, maxDist: 2000, at: V(fx, G + 34, z0),
    title: () => `${AKT.nameRu(id.fi)}: ${AKT.stOf(id.fi)} · кек ${f1(id.fi, 'cake_tph')} т/ч, влажность ${f1(id.fi, 'moisture_pct')} %, работает прессов ${f0(id.fi, 'presses_on')} из ${AKT.fmt(AKT.pass(id.fi, 'presses'))} (Ditto)`,
  });

  /* ------------------------------------------------------------- обновление */
  ups.push((state, dt) => {
    if (state.fresh) {
      const sp = AKT.num(id.sag, 'speed_pct');
      sagDrum.target = run(id.sag) && (AKT.num(id.sag, 'power_kw') || 1) > 0 ? 0.95 * (sp != null ? sp / 76 : 1) : 0;
      for (const b of balls) b.sp.target = run(b.id) ? 1.05 : 0;
      const pf = AKT.num(id.peb, 'feed_tph') || 0, pr = run(id.peb) && pf > 0;
      for (const r of rolls) r.target = pr ? 1.8 : 0;
      rake.target = run(id.th) ? 0.22 : 0;
      fireOn = (AKT.num(id.peb, 'fire') || 0) > 0 || AKT.st(id.peb) === 'FIRE';
      fire.visible = fireOn;
      const pv = pr ? 10 * Math.min(1.2, pf / 740) : 0;
      pebOut.set(pv, pr && pf > 1); pebBack.set(pv, pr && pf > 1);
      const ck = AKT.num(id.fi, 'cake_tph') || 0;
      cake.set(run(id.fi) ? 9 * Math.min(1.2, ck / 70) : 0, run(id.fi) && ck > 0.5);
      const issue = x => (ctx.glowOf(x) === 'issue' || ctx.glowOf(x) === 'alarm') ? 'issue' : '';
      pebOut.tint(state.chainEdges.has(`${id.sag}>${id.peb}`) ? 'chain' : issue(id.peb));
      pebBack.tint(state.chainEdges.has(`${id.peb}>${id.sag}`) ? 'chain' : issue(id.peb));
      cake.tint(state.chainEdges.has(`${id.fi}>conc-stock`) ? 'chain' : issue(id.fi));
      const inv = AKT.num(id.th, 'inventory_t'), cap = AKT.pass(id.th, 'capacity_t') || 340;
      mud.goal = 3 + 19 * Math.sqrt(Math.max(0, Math.min(1, (inv || 0) / cap)));
    }
    if (mud.goal != null && Math.abs(mud.goal - mud.s[0]) > 1e-3) {
      const r = mud.s[0] + (mud.goal - mud.s[0]) * (1 - Math.exp(-dt * 1.5));
      mud.s = [r, 1, r]; mud.dirty = true;
    }
    if (fireOn) {
      fireT += dt;
      for (const f of flames) { const s = f.s * (0.75 + 0.25 * Math.sin(fireT * 9 * f.k + f.s)); f.m.scale.set(f.s * 0.85, s * 5.5, f.s * 0.85); }
      for (const s of smoke) {
        const u = (fireT * 0.2 + s.ph) % 1;
        s.m.position.set(hpgrX + 3 * Math.sin(u * 5 + s.ph * 9), G + 22 + u * 70, pz + 10 * u);
        s.m.scale.setScalar(4 + 11 * u);
      }
    }
  });

  return { update(state, dt) { for (const f of ups) f(state, dt); } };
}

/* ------------------------------------------- пена флотации и гидроциклоны */
function buildShared(ctx, K, group, froth, cyclones) {
  const { THREE, AKT } = ctx;
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), p = new THREE.Vector3(), s = new THREE.Vector3();
  const LOW = new THREE.Color(0x9b9a92), HIGH = new THREE.Color(0xcda640), RED = new THREE.Color(ctx.glowColors.issue), BLUE = new THREE.Color(ctx.glowColors.chain);
  /* пена: текстура пузырей, цвет экземпляра — по извлечению стадии (stage_recovery), иначе по флотации */
  const tex = (() => {
    const c = document.createElement('canvas'); c.width = 64; c.height = 64;
    const x = c.getContext('2d');
    x.fillStyle = '#e9e5d8'; x.fillRect(0, 0, 64, 64);
    let sd = 7;
    const rnd = () => { sd = (sd * 16807) % 2147483647; return sd / 2147483647; };
    for (let i = 0; i < 70; i++) {
      const r = 1.5 + rnd() * 4, cx = rnd() * 64, cy = rnd() * 64;
      x.fillStyle = 'rgba(255,255,250,0.9)'; x.beginPath(); x.arc(cx, cy, r, 0, 2 * Math.PI); x.fill();
      x.strokeStyle = 'rgba(90,80,60,0.45)'; x.lineWidth = 0.8; x.stroke();
    }
    const t = ctx.keep(new THREE.CanvasTexture(c));
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.repeat.set(1.5, 1.5);
    return t;
  })();
  let fm = null;
  if (froth.length) {
    const g = ctx.keep(new THREE.CylinderGeometry(1, 1, 1, K.soft ? 12 : 16, 1).translate(0, 0.5, 0));
    fm = new THREE.InstancedMesh(g, ctx.keep(new THREE.MeshLambertMaterial({ map: tex })), froth.length);
    fm.name = 'froth'; fm.frustumCulled = false;
    froth.forEach((o, i) => { m4.compose(p.set(o.x, o.y, o.z), q, s.set(o.r, o.h, o.r)); fm.setMatrixAt(i, m4); fm.setColorAt(i, o.col); });
    group.add(fm);
    ctx.onClick(hit => (froth[hit.instanceId] || {}).id || '', fm, { halo: false });
  }
  /* гидроциклоны: открытые — светлые, резерв — тёмные */
  let cm = null;
  if (cyclones.length) {
    const g = ctx.merge([
      { geometry: new THREE.CylinderGeometry(1.25, 1.25, 2, 10), color: 0xffffff, position: [0, 2.5, 0] },
      { geometry: new THREE.CylinderGeometry(1.25, 0.35, 7.5, 10), color: 0xffffff, position: [0, -2.25, 0] },
      { geometry: new THREE.BoxGeometry(2.4, 0.6, 0.6), color: 0xffffff, position: [1.2, 3.8, 0] },
    ]);
    cm = new THREE.InstancedMesh(g, ctx.materials.vc, cyclones.length);
    cm.name = 'cyclones'; cm.frustumCulled = false;
    cyclones.forEach((o, i) => {
      q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), -o.a);
      m4.compose(p.set(o.x, o.y, o.z), q, s.set(1, 1, 1));
      cm.setMatrixAt(i, m4);
      cm.setColorAt(i, new THREE.Color(0xbfc5cb));
    });
    q.identity();
    group.add(cm);
    ctx.onClick(hit => (cyclones[hit.instanceId] || {}).id || '', cm, { halo: false });
  }
  const c = new THREE.Color();
  const tint = (col, id) => {
    const g = ctx.glowOf(id);
    if (g === 'issue' || g === 'alarm') col.lerp(RED, 0.45);
    else if (g === 'chain') col.lerp(BLUE, 0.35);
    return col;
  };
  function fresh() {
    for (const o of froth) {
      const st = AKT.st(o.id), on = !!AKT.things[o.id] && !AKT.stopped(st);
      const rec = AKT.num(o.id, 'stage_recovery') ?? AKT.num(o.flot, 'recovery');
      const t = on && rec != null ? Math.max(0, Math.min(1, (rec - 70) / 25)) : 0;
      o.hGoal = on ? 0.5 + 1.6 * t : 0.15;
      tint(o.colGoal.copy(LOW).lerp(HIGH, t), o.id);
    }
    if (cm) {
      cyclones.forEach((o, i) => {
        const on = !!AKT.things[o.id] && !AKT.stopped(AKT.st(o.id));
        const open = AKT.num(o.id, 'open_count') ?? AKT.pass(o.id, 'units_on');
        c.setHex(on && (open == null || o.i < open) ? 0xc9ced3 : 0x5b636c);
        cm.setColorAt(i, tint(c, o.id));
      });
      cm.instanceColor.needsUpdate = true;
    }
  }
  return {
    update(state, dt) {
      if (state.fresh) fresh();
      if (!fm) return;
      if (!state.paused) tex.offset.y = (tex.offset.y + dt * 0.04) % 1;
      let ch = false;
      const k = 1 - Math.exp(-dt * 1.2);
      froth.forEach((o, i) => {
        const dh = o.hGoal - o.h;
        const dc = Math.abs(o.colGoal.r - o.col.r) + Math.abs(o.colGoal.g - o.col.g) + Math.abs(o.colGoal.b - o.col.b);
        if (Math.abs(dh) < 1e-3 && dc < 2e-3) return;
        o.h += dh * k; o.col.lerp(o.colGoal, k);
        m4.compose(p.set(o.x, o.y, o.z), q, s.set(o.r, o.h, o.r));
        fm.setMatrixAt(i, m4); fm.setColorAt(i, o.col);
        ch = true;
      });
      if (ch) { fm.instanceMatrix.needsUpdate = true; fm.instanceColor.needsUpdate = true; }
    },
  };
}
