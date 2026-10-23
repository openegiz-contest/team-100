/* «Диорама», горные работы: формы машин и сооружений для mining.js.
   Низкополигональная схема по силуэтам реальных машин: самосвалы CAT 793 /
   785 / 777, экскаваторы Hitachi (прямая лопата класса EX3600, обратные
   лопаты ZX870 и EX1200), буровые станки, бульдозеры, ЦПД с приёмным
   бункером, конвейер со штабелеукладчиком, склад руды, ремонтный бокс.
   Размеры — схема (машины крупнее масштаба), чисел о них нет.
   Оси машины: x — вперёд, y — вверх, z — вправо (кабина самосвала слева, z < 0).
   Функции отдают части для ctx.merge: [{geometry, color, position, rotation} | {geometry, color, matrix}]. */
import * as THREE from '../vendor/three-0.160.0/three.module.min.js';

/* брус по границам */
export const box = (x0, x1, y0, y1, z0, z1, color) => ({
  geometry: new THREE.BoxGeometry(x1 - x0, y1 - y0, z1 - z0), color, position: [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2],
});
/* балка в плоскости xy от (ax, ay) до (bx, by): толщина t, по z от z0 до z1 */
export const beam = (ax, ay, bx, by, t, z0, z1, color) => {
  const L = Math.hypot(bx - ax, by - ay);
  return { geometry: new THREE.BoxGeometry(L, t, z1 - z0), color, position: [(ax + bx) / 2, (ay + by) / 2, (z0 + z1) / 2], rotation: [0, 0, Math.atan2(by - ay, bx - ax)] };
};
/* балка между точками a и b в пространстве, сечение t × t */
const X1 = new THREE.Vector3(1, 0, 0);
export const beam3 = (a, b, t, color) => {
  const A = new THREE.Vector3(...a), B = new THREE.Vector3(...b), d = B.clone().sub(A), L = d.length();
  const m = new THREE.Matrix4().compose(A.clone().add(B).multiplyScalar(0.5), new THREE.Quaternion().setFromUnitVectors(X1, d.normalize()), new THREE.Vector3(1, 1, 1));
  return { geometry: new THREE.BoxGeometry(L, t, t), color, matrix: m };
};
/* колесо (ось по z) */
const wheel = (x, y, z, r, w, color, seg) => ({ geometry: new THREE.CylinderGeometry(r, r, w, seg || 8), color, position: [x, y, z], rotation: [Math.PI / 2, 0, 0] });

const DK = 0x2c2e31, DM = 0x44484e, GL = 0x34414e;

/* ------------------------------------------------------------ самосвал */
/* CAT 793 при масштабе 1; 785 и 777 — тот же силуэт меньше. Шарнир кузова сзади (hinge), центр днища (bed) */
export const TRUCK = { L: 12.6, W: 7.3, hinge: [-5.2, 3.6], bed: [-1.7, 4.0], top: 10 };
export function truckBody(C) {
  const Y = C.cat, T = C.tire;
  return [
    box(-5.6, 4.9, 1.6, 2.7, -1.1, 1.1, DK),            // рама
    box(-4.0, -1.8, 1.2, 2.5, -1.5, 1.5, DK),           // задний мост
    box(3.7, 6.1, 1.4, 4.4, -1.5, 1.5, DM),             // двигатель, радиатор
    box(5.8, 6.3, 1.1, 1.9, -3.2, 3.2, DK),             // бампер
    box(3.0, 6.1, 4.4, 4.75, -3.6, 3.6, Y),             // верхняя площадка
    box(2.3, 4.7, 3.6, 4.0, 2.3, 3.65, Y),              // крылья
    box(2.3, 4.7, 3.6, 4.0, -3.65, -2.3, Y),
    box(3.3, 5.3, 4.75, 6.5, -3.35, -1.2, Y),           // кабина слева
    box(3.25, 5.35, 5.6, 6.3, -3.4, -1.15, GL),         // окна
    box(3.4, 4.8, 4.75, 5.4, 0.5, 2.9, C.steelLight),   // воздухоочистители
    box(5.95, 6.3, 1.0, 4.4, -0.5, 0.5, Y),             // лестница
    box(-1.2, 1.6, 1.6, 3.0, -3.45, -2.1, Y),           // бак
    box(-5.6, -4.2, 2.6, 3.6, -1.6, 1.6, DK),           // опора шарнира кузова
    wheel(3.4, 1.75, 2.95, 1.75, 1.15, T),
    wheel(3.4, 1.75, -2.95, 1.75, 1.15, T),
    wheel(-2.9, 1.75, 2.55, 1.75, 2.3, T),              // задние сдвоенные
    wheel(-2.9, 1.75, -2.55, 1.75, 2.3, T),
    box(3.0, 3.8, 1.35, 2.15, 3.5, 3.6, C.steelLight),  // ступицы
    box(3.0, 3.8, 1.35, 2.15, -3.6, -3.5, C.steelLight),
  ];
}
export function truckBed(C) {
  const Y = C.cat, Yd = 0xd9a200;
  return [
    box(-6.4, 2.9, 3.6, 4.0, -3.55, 3.55, Yd),          // днище над колёсами
    box(-6.4, 2.9, 4.0, 6.3, 3.3, 3.6, Y),              // борта
    box(-6.4, 2.9, 4.0, 6.3, -3.6, -3.3, Y),
    box(2.6, 2.95, 4.0, 7.0, -3.6, 3.6, Y),             // передний борт
    box(2.95, 6.2, 6.75, 7.1, -3.6, 3.6, Y),            // козырёк над кабиной
    box(-6.4, 2.9, 6.2, 6.6, 3.2, 3.75, Yd),            // кромки
    box(-6.4, 2.9, 6.2, 6.6, -3.75, -3.2, Yd),
    box(-6.4, 2.9, 3.0, 3.6, -1.0, 1.0, Yd),            // продольная балка днища
  ];
}
/* груз в кузове: шестигранная горка, низ в 0, масштаб — по загрузке */
export const truckLoad = () => new THREE.CylinderGeometry(0.6, 1, 1, 6, 1).translate(0, 0.5, 0);

/* --------------------------------------------------------- экскаваторы */
/* Узел: нижняя рама (гусеницы), поворотная платформа со стрелой (поворот вокруг y на высоте ring),
   рукоять с ковшом (качание вокруг z в оголовке стрелы boom). bucket — центр ковша в осях рукояти.
   Углы рукояти (рад): dig0 → dig1 — копание, dump — над кузовом, rest — покой. */
export const EXC_RIG = {
  shovel: { ring: 3.0, boom: [7.5, 7.0], bucket: [1.3, -7.2], dig0: -0.05, dig1: 0.95, dump: 1.22, rest: 0.4 },
  backhoe: { ring: 2.8, boom: [9.0, 6.2], bucket: [-0.55, -6.5], dig0: 0.72, dig1: -0.3, dump: 1.3, rest: 0.25 },
};
export function excLower(C, kind) {
  const r = EXC_RIG[kind].ring, l = kind === 'shovel' ? 4.9 : 4.4, w = kind === 'shovel' ? 3.9 : 3.4, tw = kind === 'shovel' ? 2.0 : 1.7;
  return [
    box(-l, l, 0, tw - 0.1, w - tw, w, DK),
    box(-l, l, 0, tw - 0.1, -w, -(w - tw), DK),
    box(-l + 0.4, l - 0.4, tw - 0.1, tw + 0.15, w - tw + 0.2, w - 0.2, 0x55595f),
    box(-l + 0.4, l - 0.4, tw - 0.1, tw + 0.15, -(w - 0.2), -(w - tw + 0.2), 0x55595f),
    box(-2.6, 2.6, 1.0, r - 0.35, -(w - tw), w - tw, DM),
    { geometry: new THREE.CylinderGeometry(2.3, 2.5, 0.35, 12), color: DK, position: [0, r - 0.17, 0] },
  ];
}
export function excUpper(C, kind) {
  const H = C.hitachi, Hd = 0xc9620f, W = C.white, S = C.steel;
  if (kind === 'shovel') return [
    box(-4.6, 2.9, 0, 3.4, -3.6, 3.6, H),               // платформа
    box(-5.7, -4.4, 0.1, 3.2, -3.5, 3.5, Hd),           // противовес
    box(-4.3, 1.6, 3.4, 4.0, -3.1, 3.1, H),             // капот
    box(-3.6, -2.4, 4.0, 5.0, 1.3, 2.3, DM),            // выхлоп
    box(1.4, 3.4, 3.4, 6.2, -3.6, -1.3, W),             // кабина
    box(1.35, 3.45, 4.9, 5.9, -3.65, -1.25, GL),
    box(-4.6, 2.9, 3.3, 3.45, 3.6, 4.4, S),             // мостки
    box(-4.6, 2.9, 3.3, 3.45, -4.4, -3.6, S),
    beam(2.2, 1.6, 7.5, 7.0, 1.8, -1.3, 1.3, H),        // стрела
    beam(0.6, 1.0, 5.2, 5.4, 0.6, 1.4, 1.9, S),         // гидроцилиндры стрелы
    beam(0.6, 1.0, 5.2, 5.4, 0.6, -1.9, -1.4, S),
  ];
  return [
    box(-4.4, 2.4, 0, 2.9, -3.2, 3.2, H),
    box(-5.3, -4.2, 0.1, 2.7, -3.1, 3.1, Hd),
    box(-4.1, 0.4, 2.9, 3.5, -2.8, 2.8, H),
    box(0.7, 2.7, 0.2, 4.0, -3.2, -1.3, W),             // кабина слева
    box(0.65, 2.75, 2.7, 3.6, -3.25, -1.25, GL),
    beam(2.0, 1.4, 6.2, 7.0, 1.5, -0.8, 0.8, H),        // стрела с изломом
    beam(6.2, 7.0, 9.0, 6.2, 1.3, -0.8, 0.8, H),
    beam(1.2, 0.8, 4.6, 5.4, 0.5, 0.9, 1.3, S),
  ];
}
export function excArm(C, kind) {
  const H = C.hitachi, Hd = 0xb85a10;
  if (kind === 'shovel') return [
    box(-0.7, 0.7, -6.4, 0.4, -1.0, 1.0, H),            // рукоять
    box(-0.6, 3.1, -8.6, -5.9, -2.3, 2.3, Hd),          // ковш
    box(3.0, 3.5, -8.75, -7.9, -2.3, 2.3, DK),          // зубья
    box(-0.8, -0.5, -8.4, -6.0, -2.35, 2.35, C.steel),
  ];
  return [
    box(-0.5, 0.5, -6.0, 0.4, -0.7, 0.7, H),
    box(-1.7, 0.6, -7.4, -5.6, -1.3, 1.3, Hd),
    box(-2.05, -1.6, -7.5, -6.6, -1.3, 1.3, DK),
  ];
}
/* комок породы (в ковше) и пыль */
export const lump = () => new THREE.IcosahedronGeometry(1, 0);

/* --------------------------------------------------------- буровой станок */
/* мачта качается вокруг шарнира mast (x, y, z): 0 — стоит, ≈ 1,45 — опущена назад */
export const DRILL = { mast: [4.6, 2.6, 1.0], top: 18 };
export function drillBody(C) {
  const Y = 0xffffff, W = 0xf4f1e6;   // окраска — цветом экземпляра (Sandvik, Epiroc — жёлтые)
  return [
    box(-5.0, 5.0, 0, 1.5, 1.5, 2.8, DK),
    box(-5.0, 5.0, 0, 1.5, -2.8, -1.5, DK),
    box(-5.6, 5.4, 1.5, 2.6, -2.7, 2.7, Y),             // рама
    box(-5.3, 0.6, 2.6, 5.2, -2.3, 2.3, Y),             // силовой блок
    box(-5.0, 0.3, 5.2, 5.5, -2.0, 2.0, C.steelLight),
    box(1.0, 3.2, 2.6, 5.6, -2.7, -0.7, W),             // кабина
    box(0.95, 3.25, 4.4, 5.3, -2.75, -0.65, GL),
    box(3.8, 5.4, 2.6, 3.3, 0.2, 2.2, DM),              // стол мачты
  ];
}
export function drillMast() {
  const Y = 0xffffff;
  return [
    box(-0.75, 0.75, 0, 16, -0.8, 0.8, Y),              // мачта (решётка — схема)
    box(-0.9, 0.9, 15.6, 16.7, -0.9, 0.9, DK),          // вращатель, голова
    box(-0.22, 0.22, -2.4, 0.2, -0.22, 0.22, DK),       // штанга
    box(-0.95, 0.95, 6.0, 6.6, -0.95, 0.95, DM),
  ];
}

/* -------------------------------------------------------------- бульдозер */
export function dozerBody(C) {
  const Y = 0xffffff;     // окраска — цветом экземпляра (CAT, Komatsu)
  return [
    box(-3.3, 3.3, 0, 1.5, 1.25, 2.5, DK),
    box(-3.3, 3.3, 0, 1.5, -2.5, -1.25, DK),
    box(-0.6, 3.2, 1.0, 3.0, -1.25, 1.25, Y),           // капот
    box(-2.7, -0.4, 1.0, 4.3, -1.3, 1.3, Y),            // кабина
    box(-2.75, -0.35, 3.0, 4.0, -1.35, 1.35, GL),
    box(-2.9, -0.2, 4.3, 4.55, -1.45, 1.45, Y),         // крыша ROPS
    box(-3.0, 3.0, 1.5, 1.8, -2.5, 2.5, Y),             // крылья над гусеницами
    box(3.6, 4.2, 0.1, 2.5, -2.75, 2.75, Y),            // отвал
    box(1.4, 3.7, 0.6, 1.1, 2.3, 2.6, Y),               // толкающие брусья
    box(1.4, 3.7, 0.6, 1.1, -2.6, -2.3, Y),
    box(-4.6, -3.3, 0.2, 2.4, -0.3, 0.3, DK),           // рыхлитель
    box(0.6, 0.9, 3.0, 3.9, 0.3, 0.6, DK),              // выхлоп
  ];
}

/* ---------------------------------------------------------- забой: развал */
/* горка взорванной породы: икосаэдр с неровностями, низ срезан (y ≥ 0), длина по x */
export function pileGeometry() {
  const g = new THREE.IcosahedronGeometry(1, 1);
  const p = g.attributes.position, v = new THREE.Vector3();
  const h = (x, y, z) => { const s = Math.sin(x * 12.9898 + y * 78.233 + z * 37.719) * 43758.5453; return s - Math.floor(s); };
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    const k = 0.82 + 0.3 * h(Math.round(v.x * 100), Math.round(v.y * 100), Math.round(v.z * 100));
    v.multiplyScalar(k);
    v.y = Math.max(0, v.y + 0.25);
    p.setXYZ(i, v.x, v.y, v.z);
  }
  g.computeVertexNormals();
  return g;
}

/* ------------------------------------------------------------------- ЦПД */
/* корпус ЦПД у узла (nx, nz): площадка разгрузки с отбойным брусом и приёмный бункер на западе
   (самосвал заезжает задом), корпус дробилки, операторская, перегрузочный узел к конвейеру на востоке.
   y0 — верх площадки зоны. Центр бункера: nx + HOPPER. */
export const HOPPER = -27.5;
export function crusherParts(C, nx, nz, y0) {
  const P = [
    box(nx - 54, nx - 33, 0, 1.6, nz - 13, nz + 13, C.concrete),            // площадка разгрузки
    box(nx - 35.5, nx - 33, 0, 2.7, nz - 13, nz + 13, 0x9d978c),            // отбойный брус
    box(nx - 33, nx - 22, y0, y0 + 0.1, nz - 10, nz + 10, 0x2a2724),         // проём бункера
    box(nx - 34, nx - 21, y0, y0 + 5, nz - 12.6, nz - 10, C.concrete),       // стенки бункера
    box(nx - 34, nx - 21, y0, y0 + 5, nz + 10, nz + 12.6, C.concrete),
    box(nx - 28.2, nx - 26.8, y0 + 0.1, y0 + 1.3, nz - 10, nz + 10, C.steelDark),   // траверса дробилки
    box(nx - 22, nx + 18, y0, y0 + 24, nz - 16, nz + 16, C.cladding),       // корпус
    box(nx - 23, nx + 19, y0 + 24, y0 + 25.4, nz - 17, nz + 17, C.roof),
    box(nx - 14, nx + 8, y0 + 25.4, y0 + 31, nz - 11, nz + 5, C.wall),      // операторская
    box(nx - 14.25, nx + 8.25, y0 + 28.2, y0 + 30.2, nz - 11.25, nz + 5.25, C.glass),
    box(nx - 15, nx + 9, y0 + 31, y0 + 31.8, nz - 12, nz + 6, C.roof),
    box(nx - 22.3, nx + 18.3, y0 + 9, y0 + 9.8, nz - 16.3, nz + 16.3, 0x5e7690), // пояс обшивки
    box(nx + 18, nx + 30, y0, y0 + 11, nz - 5, nz + 5, C.wall),             // перегрузочный узел
    box(nx - 2, nx + 10, y0, y0 + 9, nz + 16, nz + 24, C.wall),             // щитовая
    box(nx - 2.3, nx + 10.3, y0 + 9, y0 + 9.6, nz + 15.7, nz + 24.3, C.roof),
    box(nx - 24, nx - 21, y0, y0 + 6.5, nz + 9.6, nz + 12.6, C.cat),        // бутобой: тумба и стрела
    beam3([nx - 22.5, y0 + 6.3, nz + 11], [nx - 27, y0 + 8.5, nz + 5], 0.9, C.cat),
    beam3([nx - 27, y0 + 8.5, nz + 5], [nx - 29, y0 + 3.5, nz + 2], 0.7, C.cat),
  ];
  return P;
}
/* мантия дробилки (качается, когда идёт руда) */
export const mantle = () => new THREE.ConeGeometry(3.4, 2.4, 10, 1).translate(0, 1.2, 0);

/* -------------------------------------------- конвейер со штабелеукладчиком */
/* наклонный став от (xa, ya) до (xb, yb) на z; опоры до земли ground(x, z); головная башня над конусом */
export function conveyorParts(C, xa, ya, xb, yb, z, ground) {
  const P = [], k = (yb - ya) / (xb - xa);
  const yAt = x => ya + (x - xa) * k;
  P.push(beam(xa, ya - 0.7, xb, yb - 0.7, 1.1, z - 2.7, z - 2.15, C.steel));        // ставы
  P.push(beam(xa, ya - 0.7, xb, yb - 0.7, 1.1, z + 2.15, z + 2.7, C.steel));
  P.push(beam(xa, ya - 1.25, xb, yb - 1.25, 0.25, z + 2.7, z + 3.9, C.steelLight)); // проход
  P.push(beam(xa, ya + 1.6, xb, yb + 1.6, 0.25, z + 3.75, z + 3.9, 0xe2b13a));      // перила
  for (let x = xa + 10; x < xb - 8; x += 21) {
    const y = yAt(x) - 1.25, g = ground(x, z);
    P.push(box(x - 0.5, x + 0.5, g, y, z - 2.9, z - 2.1, C.steelDark), box(x - 0.5, x + 0.5, g, y, z + 2.1, z + 2.9, C.steelDark));
    P.push(box(x - 0.6, x + 0.6, y - 0.8, y, z - 2.9, z + 3.9, C.steelDark));
    if (y - g > 14) P.push(beam3([x, g + 0.5, z - 2.5], [x, y - 1, z + 2.5], 0.45, C.steelDark));
  }
  /* башня у вершины конуса: четыре стойки, площадка, барабан */
  const gb = ground(xb, z), top = yb - 1.6;
  for (const [dx, dz] of [[-4, -3], [-4, 3], [1.5, -3], [1.5, 3]]) P.push(box(xb + dx - 0.45, xb + dx + 0.45, gb, top, z + dz - 0.45, z + dz + 0.45, C.steelDark));
  P.push(box(xb - 4.8, xb + 2.3, top, top + 0.6, z - 3.8, z + 3.8, C.steel));
  P.push(box(xb - 1.5, xb + 2.2, top + 0.6, yb + 1.6, z - 2.8, z + 2.8, C.steelLight));     // головной барабан, кожух
  P.push(beam3([xb - 4, gb + 3, z - 3], [xb + 1.5, top - 3, z - 3], 0.4, C.steelDark));
  P.push(beam3([xb - 4, gb + 3, z + 3], [xb + 1.5, top - 3, z + 3], 0.4, C.steelDark));
  /* хвостовая часть у ЦПД: приёмная воронка */
  P.push(box(xa - 2, xa + 4, ya - 2.4, ya + 2.2, z - 3.3, z + 3.3, C.steelLight));
  return P;
}
/* конвейерные весы: рамка поверх ленты и шкаф */
export function weigherParts(C, x, y, z) {
  return [
    box(x - 1.6, x + 1.6, y + 1.0, y + 3.2, z - 3.1, z + 3.1, C.white),
    box(x - 1.4, x + 1.4, y - 1.8, y + 1.0, z - 3.3, z - 2.7, C.steelDark),
    box(x - 1.4, x + 1.4, y - 1.8, y + 1.0, z + 2.7, z + 3.3, C.steelDark),
    box(x - 1.65, x + 1.65, y + 1.0, y + 1.5, z - 3.15, z + 3.15, 0x5a6068),
  ];
}
/* конус склада: радиус 62, высота 52 (как узел в layout.js) при масштабе 1; неровная поверхность */
export function coneGeometry() {
  const g = new THREE.ConeGeometry(62, 52, 22, 3, true).translate(0, 26, 0);
  const p = g.attributes.position, v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    const a = Math.atan2(v.z, v.x), r = Math.hypot(v.x, v.z);
    if (v.y > 1 && v.y < 51) { const k = 1 + 0.045 * Math.sin(a * 5 + v.y * 0.13) + 0.03 * Math.cos(a * 9); v.x *= k; v.z *= k; }
    else if (v.y <= 1 && r > 0) { const k = 1 + 0.03 * Math.sin(a * 7); v.x *= k; v.z *= k; }
    p.setXYZ(i, v.x, v.y, v.z);
  }
  g.computeVertexNormals();
  return g;
}

/* ------------------------------------------------------------ ремонтный бокс */
export const SHOP = { x0: -28, x1: 32, z0: -359, z1: -335, h: 19, bays: [-18, 2, 22], bayZ: -347 };
export function shopParts(C, y0) {
  const { x0, x1, z0, z1, h } = SHOP, Cl = C.cladding, xo = x0 - 13;
  return [
    box(x0, x1, y0, y0 + h, z0, z0 + 1.2, Cl),                       // задняя стена
    box(x0, x0 + 1.2, y0, y0 + h, z0, z1, Cl),                       // торцы
    box(x1 - 1.2, x1, y0, y0 + h, z0, z1, Cl),
    box(-8.6, -7.4, y0, y0 + h, z0, z1, Cl),                         // простенки между боксами
    box(11.4, 12.6, y0, y0 + h, z0, z1, Cl),
    box(x0, x1, y0 + 15, y0 + h, z1 - 1.2, z1, Cl),                  // перемычка над воротами
    box(x0 - 1, x1 + 1, y0 + h, y0 + h + 1.2, z0 - 1, z1 + 1, C.roof),
    box(x0 + 2, x1 - 2, y0 + h + 1.2, y0 + h + 2.4, z0 + 4, z1 - 4, 0xb4bcc4),   // фонарь кровли
    box(x0 - 0.2, x1 + 0.2, y0 + 15.8, y0 + 16.4, z1 - 0.2, z1 + 0.2, 0xe2b13a), // полоса над воротами
    box(xo, x0, y0, y0 + 8, z0, z0 + 16, C.wall),                    // бытовой блок
    box(xo - 0.1, x0 + 0.1, y0 + 4.6, y0 + 6.4, z0 - 0.1, z0 + 16.1, C.glass),
    box(xo - 0.5, x0 + 0.5, y0 + 8, y0 + 8.6, z0 - 0.5, z0 + 16.5, C.roof),
    box(x0 + 1.2, x1 - 1.2, y0, y0 + 0.2, z0 + 1.2, z1, 0xa9a49a),   // пол боксов
  ];
}
