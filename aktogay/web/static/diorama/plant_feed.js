/* «Диорама», модуль «фабрика»: подача руды — ЦПД-1/2 (приёмный бункер, гирационная дробилка,
   корпус), магистральные конвейеры с бегущей рудой (скорость ∝ т/ч из Ditto), конвейерные
   весы, конусные склады руды (высота ∝ level_t / паспорт live_t) и питающие ленты со складов
   в SAG (feed-1/2). Дробилки, конвейеры, весы и склады по API.md рисует mining.js: если он их
   уже занял (ctx.claimed), здесь они не строятся — остаются только питающие ленты.
   Линия 2 — оборудование FLSmidth (паспорт crusher-2 в Ditto): синяя отделка. Схема, не масштаб. */
import { STYLE, NB } from './plant_geo.js';

export function buildFeed(ctx, K, group) {
  const { THREE, AKT, NODES } = ctx;
  const { box, cyl, beam, ring, body } = K;
  const ups = [];
  const has = id => !!AKT.things[id];
  const free = id => !ctx.claimed(id);
  const tph = (id, f) => AKT.num(id, f || 'tph');
  const t0 = v => v == null ? '—' : AKT.fmt(v);
  const tail = id => { const s = AKT.st(id); return !s || ['RUN', 'NORMAL', 'OK'].includes(s) ? '' : ` · ${AKT.stOf(id)}`; };
  const V = (x, y, z) => new THREE.Vector3(x, y, z);

  for (const n of [1, 2]) {
    const S = STYLE[n];
    const crusher = `crusher-${n}`, conv = `conveyor-${n}`, stock = `stockpile-${n}`, wgh = `weigher-${n}`;
    const z0 = NODES[crusher].z;
    const Gc = ctx.heightAt(NODES[crusher].x, z0);           // площадка ЦПД
    const Gs = ctx.heightAt(NODES[stock].x, z0);              // площадка складов
    const sx = NODES[stock].x;
    /* лента магистрального конвейера: от узла пересыпки под дробилкой до головы над центром склада */
    const HEAD_Y = Gs + 55;
    const A = [-40, Gc + 6, z0], B = [sx - 5, HEAD_Y - 1.5, z0];
    const beltY = x => A[1] + (x - A[0]) / (B[0] - A[0]) * (B[1] - A[1]);

    /* ------------------------------------------------------------- ЦПД */
    if (free(crusher)) {
      const P = [];
      /* площадка разгрузки самосвалов, упор для колёс, стены приёмного бункера */
      P.push(box(22, 0.6, 36, -101, Gc, z0, 0xb9b2a6));
      P.push(box(1.8, 2.4, 30, -99.6, Gc, z0, 0xc9c4ba));
      P.push(box(18, 8, 1.8, -89, Gc, z0 - 15.1, 0xc9c4ba), box(18, 8, 1.8, -89, Gc, z0 + 15.1, 0xc9c4ba));
      P.push(box(1.8, 10, 32, -79.1, Gc, z0, 0xc9c4ba));
      P.push(box(16, 0.6, 28.4, -89, Gc, z0, 0x4d4842));
      /* верх гирационной дробилки в бункере: фланец чаши, траверса (крестовина) */
      P.push(ring(5.4, 7.6, 2.2, -89, Gc + 0.6, z0, S.equip, 20));
      P.push(box(16, 1.4, 1.8, -89, Gc + 3.6, z0, S.accent), box(1.8, 1.4, 16, -89, Gc + 3.6, z0, S.accent));
      P.push(cyl(1.9, 1.8, -89, Gc + 4.6, z0, S.accent, 12));
      /* руда по углам бункера (схема) */
      for (const [dx, dz, r] of [[-5, -10, 3.6], [4.5, 10, 3.2], [5, -10.5, 2.8]]) P.push(cyl(r, 2.6, -89 + dx, Gc + 0.6, z0 + dz, 0x7f6e5c, 9, 0.6));
      /* гидромолот на тумбе (жёлтый) */
      P.push(box(3, 10, 3, -82.5, Gc, z0 - 12.5, 0x9a958c));
      P.push(beam([-82.5, Gc + 10, z0 - 12.5], [-87, Gc + 14, z0 - 7], 1.2, 0xe8b21a), beam([-87, Gc + 14, z0 - 7], [-89.5, Gc + 7, z0 - 3.5], 1, 0xe8b21a));
      /* корпус ЦПД: машинный зал и пролёт крана */
      P.push(box(32, 26, 36, -62.5, Gc, z0, S.wall));
      P.push(box(32.4, 1.8, 36.4, -62.5, Gc + 25, z0, S.trim));
      P.push(box(26, 18, 26, -63.5, Gc + 26.8, z0, S.wall));
      P.push(box(27.4, 1.4, 27.4, -63.5, Gc + 44.4, z0, S.roof));
      P.push(box(24, 3, 0.4, -63, Gc + 17, z0 + 18.1, S.glass), box(20, 2.6, 0.4, -63.5, Gc + 36, z0 + 13.1, S.glass));
      P.push(box(10, 13, 0.5, -54, Gc, z0 + 18.2, 0x5b636c));
      P.push(box(5, 31, 5, -45, Gc, z0 - 15, S.trim));
      /* пересыпка на конвейер */
      P.push(box(9, 10, 11, -42, Gc, z0, 0xc9c4ba));
      const m = body(P, crusher);
      group.add(m);
      ctx.onClick(crusher, m);
      /* конус дробилки в бункере: качается (гирация), пока дробилка работает */
      const mantle = new THREE.Mesh(ctx.keep(new THREE.ConeGeometry(4.6, 4.4, 14, 1).translate(0, 2.2, 0)), ctx.mat(0x6b737c));
      mantle.position.set(-89, Gc + 0.8, z0);
      group.add(mantle);
      ctx.onClick(crusher, mantle);
      K.lamp(crusher, [-63.5, Gc + 47, z0 + 10]);
      let ph = 0, w = 0;
      ups.push((state, dt) => {
        const run = has(crusher) && !AKT.stopped(AKT.st(crusher)) && (tph(crusher) || 0) > 0 && !state.paused;
        w += ((run ? 5 : 0) - w) * (1 - Math.exp(-dt * 2));
        ph += w * dt;
        mantle.rotation.x = 0.07 * Math.cos(ph) * Math.min(1, w / 5);
        mantle.rotation.z = 0.07 * Math.sin(ph) * Math.min(1, w / 5);
      });
      ctx.label('plant:' + crusher, () => has(crusher) ? `${AKT.nameRu(crusher)} · ${t0(tph(crusher))}${NB}т/ч${tail(crusher)}` : '', {
        thing: crusher, prio: 2, at: V(-66, Gc + 48, z0),
        title: () => `${AKT.nameRu(crusher)}: ${AKT.stOf(crusher)} · ${t0(tph(crusher))} т/ч (Ditto) · ${AKT.pass(crusher, 'kind') || ''}`,
      });
    }

    /* -------------------------------------------------- магистральный конвейер */
    if (free(conv)) {
      const P = K.trestle([], A, B, 6, 18, 0x7c848c);
      const m = body(P, conv);
      group.add(m);
      ctx.onClick(conv, m);
      const bl = K.belt(A, B, 6, { id: conv });
      K.lamp(conv, [-42, Gc + 11.5, z0 + 4]);
      const cap = () => AKT.pass(conv, 'capacity_tph') || 4880;
      ups.push(state => {
        if (!state.fresh) return;
        const v = tph(conv) || 0;
        bl.set(22 * Math.min(1.2, v / cap()), v > 1);
        bl.tint(ctx.glowOf(conv));
      });
      ctx.label('plant:' + conv, () => has(conv) ? `${AKT.nameRu(conv)} · ${t0(tph(conv))}${NB}т/ч${tail(conv)}` : '', {
        thing: conv, prio: 3, maxDist: 2200, at: V(10, beltY(10) + 4, z0),
        title: () => `${AKT.nameRu(conv)}: ${AKT.stOf(conv)} · ${t0(tph(conv))} т/ч (Ditto) · лента ${AKT.pass(conv, 'length_km') || '—'} км по паспорту, на макете — схема`,
      });
    }
    /* конвейерные весы на ленте */
    if (free(wgh) && has(wgh)) {
      const wx = NODES[wgh] ? NODES[wgh].x : 40, wy = beltY(wx);
      const g = ctx.heightAt(wx, z0);
      const P = [
        beam([wx - 2, g, z0 - 5], [wx - 2, wy + 4, z0 - 5], 1, 0x59606a), beam([wx - 2, g, z0 + 5], [wx - 2, wy + 4, z0 + 5], 1, 0x59606a),
        beam([wx - 2, wy + 4, z0 - 5.5], [wx - 2, wy + 4, z0 + 5.5], 1.2, 0xe8b21a), box(3, 2, 3, wx - 2, wy + 4.5, z0 + 5, 0xf2f2ef),
      ];
      const m = body(P, wgh);
      group.add(m);
      ctx.onClick(wgh, m);
      K.lamp(wgh, [wx - 2, wy + 7.2, z0 + 5], null, 1.1);
      ctx.label('plant:' + wgh, () => has(wgh) && AKT.deviates(wgh) ? `${AKT.nameRu(wgh)} · ${AKT.stOf(wgh)}` : '', { thing: wgh, prio: 6, kind: 'small', at: V(wx, wy + 9, z0) });
    }

    /* ------------------------------------------------------------- склад */
    const coneTop = { y: Gs + 30 };
    if (free(stock)) {
      const P = [];
      /* башня под головой конвейера: 4 стойки, связи, будка привода */
      const legs = [[-5, -5], [5, -5], [5, 5], [-5, 5]];
      for (const [dx, dz] of legs) P.push(beam([sx + dx, Gs, z0 + dz], [sx + dx * 0.6, HEAD_Y - 3, z0 + dz * 0.6], 1.2, 0x7c848c));
      for (let y = Gs + 12; y < HEAD_Y - 6; y += 13) {
        const f = (y - Gs) / (HEAD_Y - 3 - Gs), k = 5 - 2 * f, k2 = 5 - 2 * Math.min(1, f + 13 / (HEAD_Y - 3 - Gs));
        for (let i = 0; i < 4; i++) {
          const [ax, az] = legs[i], [bx, bz] = legs[(i + 1) % 4];
          P.push(beam([sx + ax / 5 * k, y, z0 + az / 5 * k], [sx + bx / 5 * k2, y + 13, z0 + bz / 5 * k2], 0.5, 0x7c848c));
        }
      }
      P.push(box(12, 7, 10, sx - 1, HEAD_Y - 4, z0, S.wall), box(12.6, 1, 10.6, sx - 1, HEAD_Y + 3, z0, S.roof));
      const m = body(P, stock);
      group.add(m);
      ctx.onClick(stock, m);
      /* конус руды: высота ∝ запасу; масштаб по кубическому корню (объём конуса) */
      const cg = new THREE.ConeGeometry(1, 0.78, K.soft ? 22 : 30, 4, true).translate(0, 0.39, 0);
      const parts = [{ geometry: cg, color: 0x8a7865 }];
      const g = ctx.merge(parts);
      const C = g.attributes.color, Pp = g.attributes.position;
      for (let i = 0; i < C.count; i++) {
        const k = 0.88 + 0.2 * (0.5 + 0.5 * Math.sin(Pp.getX(i) * 31.7 + Pp.getZ(i) * 17.3 + Pp.getY(i) * 11.1));
        C.setXYZ(i, C.getX(i) * k, C.getY(i) * k, C.getZ(i) * k);
      }
      const cone = new THREE.Mesh(ctx.bake(g), ctx.materials.baked);
      cone.name = stock + '-cone';
      cone.position.set(sx, Gs - 0.2, z0);
      const R0 = 56;
      let s = 0.6, goal = 0.6;
      cone.scale.setScalar(R0 * s);
      group.add(cone);
      ctx.onClick(stock, cone);
      coneTop.y = Gs + 0.78 * R0 * s;
      K.stream([sx - 1, HEAD_Y - 4, z0], () => coneTop.y, 2.4, 0x8a7865, () => (tph(conv) || 0) > 1);
      ups.push((state, dt) => {
        if (state.fresh && has(stock)) {
          const lv = AKT.num(stock, 'level_t'), cap = AKT.pass(stock, 'live_t') || 40000;
          if (lv != null) goal = Math.max(0.14, Math.min(1.05, Math.cbrt(Math.max(0, lv) / cap)));
        }
        if (Math.abs(goal - s) > 1e-4) {
          s += (goal - s) * (1 - Math.exp(-dt * 1.5));
          cone.scale.setScalar(R0 * s);
          coneTop.y = Gs + 0.78 * R0 * s;
        }
      });
      ctx.label('plant:' + stock, () => {
        if (!has(stock)) return '';
        const lv = AKT.num(stock, 'level_t');
        return `${AKT.nameRu(stock)} · ${t0(lv)}${NB}т${tail(stock)}`;
      }, {
        thing: stock, prio: 2, at: V(sx, HEAD_Y + 6, z0),
        title: () => `${AKT.nameRu(stock)}: ${AKT.stOf(stock)} · запас ${t0(AKT.num(stock, 'level_t'))} т, приход ${t0(AKT.num(stock, 'in_tph'))} т/ч, выпуск ${t0(AKT.num(stock, 'out_tph'))} т/ч (Ditto); паспорт: ${t0(AKT.pass(stock, 'live_t'))} т активного запаса · высота конуса ∝ запасу (схема)`,
      });
    }

    /* --------------------------------------------- питающая лента склад → SAG */
    {
      const sag = `sag-${n}`;
      const G = ctx.heightAt(NODES[sag].x, z0);
      const a = [sx + 60, Gs + 3, z0], b = [NODES[sag].x - 25, G + 31, z0];
      /* портал туннеля выпуска (питатели под складом) и эстакада ленты */
      const P = [box(10, 6.5, 13, sx + 56, Gs, z0, 0xc9c4ba), box(0.4, 4.4, 7, sx + 61.1, Gs, z0, 0x34383d)];
      K.misc(K.trestle(P, a, b, 5, 12, 0x7c848c));
      const bl = K.belt(a, b, 5, { id: sag });
      ups.push(state => {
        if (!state.fresh) return;
        const v = AKT.num(sag, 'feed_tph') ?? AKT.num(stock, 'out_tph') ?? 0;
        bl.set(18 * Math.min(1.2, v / 4880), v > 1);
        bl.tint(state.chainEdges.has(`${stock}>${sag}`) ? 'chain' : (ctx.glowOf(stock) === 'issue' ? 'issue' : ''));
      });
    }
  }

  return {
    update(state, dt) { for (const u of ups) u(state, dt); },
  };
}
