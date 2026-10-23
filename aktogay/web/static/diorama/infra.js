/* «Диорама», модуль «инфраструктура» (договор — API.md):
   infra_water.js  — хвостохранилище (дамба, пляж, пруд с уровнем из Ditto),
                     три пьезометра с уставкой S0, водоводы и насосные, стрелки потока;
   infra_power.js  — ПС 220/35 кВ, ВЛ 220 кВ и фидеры 35 кВ, «X из 300 МВт», огни по проводам;
   infra_people.js — люди смены и бригады у своих узлов, путь в дороге пунктиром и ETA,
                     кого звать к беде 1;
   infra_glow.js   — кольца и ореолы бед, путь беды до меди дугами по feeds;
   infra_legend.js — легенда (HTML) в углу холста.
   Здесь же — АБК (здание, стоянка; не вещь Ditto, схема). Всё живое — из AKT
   (опрос Ditto в app.js); модуль сам в сеть не ходит. */
import { makeKit } from './infra_kit.js';
import { buildWater } from './infra_water.js';
import { buildPower } from './infra_power.js';
import { buildPeople } from './infra_people.js';
import { buildGlow } from './infra_glow.js';
import { buildLegend } from './infra_legend.js';

function buildAbk(ctx, kit) {
  const { THREE } = ctx;
  const n = ctx.NODES.abk || { x: 200, z: -296 };
  const x = n.x, z = n.z - 4, y = ctx.heightAt(x, z);
  const L = kit.list();
  const WALL = 0xe6e3dc, GLASS = 0x5d7c96, TRIM = 0x8d969f;
  /* трёхэтажный корпус с ленточным остеклением, вход с козырьком */
  L.box(x, y, z, 56, 12.5, 18, WALL).box(x, y + 12.5, z, 57, 1.2, 19, TRIM);
  for (const yy of [2.2, 6.2, 10.0]) L.box(x, y + yy, z, 56.3, 1.7, 18.3, GLASS);
  L.box(x, y, z + 9.2, 9, 5.2, 1.2, 0x56636f).box(x, y + 5.2, z + 11, 12, 0.7, 5, TRIM)
    .box(x - 5.4, y, z + 13, 0.6, 5.2, 0.6, TRIM).box(x + 5.4, y, z + 13, 0.6, 5.2, 0.6, TRIM);
  /* вахтовый автобус и машины на стоянке (схема) */
  const car = (cx, cz, col) => L.box(cx, y + 0.6, cz, 3.6, 2.0, 6.4, col).box(cx, y + 2.6, cz - 0.6, 3.2, 1.5, 3.4, col).box(cx, y + 2.7, cz - 0.6, 3.3, 1.0, 3.5, GLASS);
  car(x - 22, z + 19, 0xf2f2ef); car(x - 16, z + 19, 0xb9c0c7); car(x - 10, z + 19, 0xf2f2ef);
  L.box(x + 20, y + 0.6, z + 19, 5, 4.8, 15, 0xf4f4f1).box(x + 20, y + 2.6, z + 19, 5.1, 1.5, 15.1, GLASS).box(x + 20, y + 0.6, z + 19, 5.1, 0.8, 15.1, 0x2f63a8);
  const m = L.mesh(); m.name = 'abk';
  const b = ctx.blob(70, 30, 0.2); b.position.set(x + 2, y + 0.12, z + 2);
  ctx.scene.add(m); ctx.scene.add(b);
  return m;
}

export function build(ctx) {
  const kit = makeKit(ctx);
  buildAbk(ctx, kit);
  /* кольца и ореолы считают землю с дамбой хвостохранилища */
  let ground = null;
  const glow = buildGlow(ctx, kit, (x, z) => ground ? ground(x, z) : ctx.heightAt(x, z));
  const water = buildWater(ctx, kit, glow);
  ground = water.surface;
  const power = buildPower(ctx, kit, glow);
  const people = buildPeople(ctx, kit, glow, water.ground);
  const legend = buildLegend(ctx);
  ctx.claim(['water', 'power', 'piezo-1', 'piezo-2', 'piezo-3']);
  ctx.claim(id => ctx.AKT.cat(id) === 'piezo');
  return {
    update(state, dt) {
      glow.begin();
      water.update(state, dt);
      power.update(state, dt);
      people.update(state, dt);
      glow.end(state);
      legend.update(state);
    },
    destroy() { legend.destroy(); },
  };
}
