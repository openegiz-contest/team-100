/* «Диорама», модуль «инфраструктура»: заготовки для склейки неподвижных частей
   (коробки, цилиндры, балки опор) в одну геометрию с запечённым светом, и
   буфер «трубок» — трёхгранных призм вдоль ломаной, который пересобирается без
   новых геометрий (пунктир пути человека, дуги пути беды до меди). */

export function makeKit(ctx) {
  const { THREE } = ctx;
  const K = g => ctx.keep(g);
  /* единичные заготовки: основание в y = 0 (коробка, цилиндр, конус), сфера и лежачий цилиндр — по центру */
  const U = {
    box: K(new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0)),
    cyl: K(new THREE.CylinderGeometry(1, 1, 1, 10).translate(0, 0.5, 0)),
    cyl6: K(new THREE.CylinderGeometry(1, 1, 1, 6).translate(0, 0.5, 0)),
    cylC: K(new THREE.CylinderGeometry(1, 1, 1, 10)),
    cone: K(new THREE.ConeGeometry(1, 1, 10).translate(0, 0.5, 0)),
    sph: K(new THREE.IcosahedronGeometry(1, 1)),
  };
  const Y = new THREE.Vector3(0, 1, 0);
  const tq = new THREE.Quaternion(), te = new THREE.Euler(), ts = new THREE.Vector3(), tp = new THREE.Vector3(), td = new THREE.Vector3();

  /* список частей: x, y (низ), z; размеры; цвет (hex); поворот вокруг вертикали ry */
  function list() {
    const parts = [], own = [];
    const put = (geometry, color, x, y, z, rx, ry, rz, sx, sy, sz) => {
      te.set(rx || 0, ry || 0, rz || 0); tq.setFromEuler(te);
      parts.push({ geometry, color, matrix: new THREE.Matrix4().compose(tp.set(x, y, z), tq, ts.set(sx, sy, sz)) });
    };
    const L = {
      parts,
      box(x, y, z, w, h, d, color, ry) { put(U.box, color, x, y, z, 0, ry, 0, w, h, d); return L; },
      cyl(x, y, z, r, h, color, lo) { put(lo ? U.cyl6 : U.cyl, color, x, y, z, 0, 0, 0, r, h, r); return L; },
      cone(x, y, z, r, h, color) { put(U.cone, color, x, y, z, 0, 0, 0, r, h, r); return L; },
      sph(x, y, z, r, color, sy) { put(U.sph, color, x, y, z, 0, 0, 0, r, r * (sy || 1), r); return L; },
      /* лежачий цилиндр по центру (x, y, z), ось — по направлению ry (0 — вдоль x) */
      hcyl(x, y, z, r, len, color, ry) { put(U.cylC, color, x, y, z, 0, ry || 0, Math.PI / 2, r, len, r); return L; },
      /* балка от a до b ([x, y, z]) толщиной t: стойки и раскосы опор, колонны порталов */
      beam(a, b, t, color, t2) {
        td.set(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
        const len = td.length();
        if (len < 1e-4) return L;
        tq.setFromUnitVectors(Y, td.multiplyScalar(1 / len));
        parts.push({ geometry: U.box, color, matrix: new THREE.Matrix4().compose(tp.set(a[0], a[1], a[2]), tq, ts.set(t, len, t2 || t)) });
        return L;
      },
      /* своя геометрия (освобождается после склейки) */
      raw(geometry, color, matrix) { own.push(geometry); parts.push({ geometry, color, matrix: matrix || new THREE.Matrix4() }); return L; },
      /* склеить; o.bake: false — без запекания (для Ламберта с цветами вершин) */
      geometry(o) {
        const g = ctx.merge(parts);
        for (const x of own) x.dispose();
        return o && o.bake === false ? g : ctx.bake(g, o);
      },
      mesh(material, o) { return new THREE.Mesh(L.geometry(o), material || ctx.materials.baked); },
    };
    return L;
  }

  /* Буфер призм с цветами вершин (MeshBasicMaterial): reset(), add(a, b, r, color) — отрезок,
     commit() — показать. Ёмкость задаётся числом отрезков; лишнее не рисуется. */
  function prisms(maxSeg, o) {
    const nV = maxSeg * 18;
    const pos = new Float32Array(nV * 3), col = new Float32Array(nV * 3);
    const g = K(new THREE.BufferGeometry());
    const pa = new THREE.BufferAttribute(pos, 3), ca = new THREE.BufferAttribute(col, 3);
    pa.setUsage(THREE.DynamicDrawUsage); ca.setUsage(THREE.DynamicDrawUsage);
    g.setAttribute('position', pa); g.setAttribute('color', ca);
    g.setDrawRange(0, 0);
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), 4000);
    const mat = K(new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide, polygonOffset: !!(o && o.offset), polygonOffsetFactor: -1, polygonOffsetUnits: -2 }));
    const mesh = new THREE.Mesh(g, mat);
    mesh.frustumCulled = false;
    let n = 0;
    const t = new THREE.Vector3(), u = new THREE.Vector3(), w = new THREE.Vector3(), c = new THREE.Color();
    const ring = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()], ring2 = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
    const A = [Math.PI / 2, Math.PI / 2 + 2.0944, Math.PI / 2 + 4.1888];
    const vtx = (p) => { const i = n * 3; pos[i] = p.x; pos[i + 1] = p.y; pos[i + 2] = p.z; col[i] = c.r; col[i + 1] = c.g; col[i + 2] = c.b; n++; };
    return {
      mesh,
      reset() { n = 0; },
      add(a, b, r, hex) {
        if (n + 18 > nV) return false;
        t.subVectors(b, a); const len = t.length(); if (len < 1e-3) return true;
        t.multiplyScalar(1 / len);
        u.set(-t.z, 0, t.x); if (u.lengthSq() < 1e-6) u.set(1, 0, 0); u.normalize();
        w.crossVectors(u, t).normalize();
        for (let k = 0; k < 3; k++) {
          const cs = Math.cos(A[k]) * r, sn = Math.sin(A[k]) * r;
          ring[k].copy(a).addScaledVector(u, cs).addScaledVector(w, sn);
          ring2[k].copy(b).addScaledVector(u, cs).addScaledVector(w, sn);
        }
        c.setHex(hex);
        for (let k = 0; k < 3; k++) {
          const k2 = (k + 1) % 3;
          vtx(ring[k]); vtx(ring2[k]); vtx(ring2[k2]);
          vtx(ring[k]); vtx(ring2[k2]); vtx(ring[k2]);
        }
        return true;
      },
      commit() {
        g.setDrawRange(0, n);
        pa.needsUpdate = true; ca.needsUpdate = true;
        if (pa.updateRanges) { pa.clearUpdateRanges(); ca.clearUpdateRanges(); pa.addUpdateRange(0, n * 3); ca.addUpdateRange(0, n * 3); }
        else { pa.updateRange.count = n * 3; ca.updateRange.count = n * 3; }
        mesh.visible = n > 0;
      },
      get count() { return n / 18; },
    };
  }

  /* мягкое пятно (ореол): текстура для точек-ореолов и колец */
  const radial = (() => {
    const cv = document.createElement('canvas'); cv.width = cv.height = 64;
    const x = cv.getContext('2d');
    const gr = x.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.35, 'rgba(255,255,255,0.55)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    x.fillStyle = gr; x.fillRect(0, 0, 64, 64);
    const t = K(new THREE.CanvasTexture(cv)); t.colorSpace = THREE.SRGBColorSpace;
    return t;
  })();

  return { U, list, prisms, radial };
}
