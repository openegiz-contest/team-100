/* 3D views: ?view=diorama (diorama/core.js, the main 3D view, menu «Диорама»; ?view=3d is the same) and
   ?view=site (site3d.js, menu «Спутник 3D»), ES modules
   with three.js r160 vendored in vendor/, loaded only when the view opens. Without
   WebGL, or when the scene fails to start, the 2D plan is shown with a note. */
'use strict';
(function () {
  /* One place that makes WebGL contexts. A browser under load (software WebGL in a headless Chrome next to the whole
     stand) now and then refuses a context for a moment: the probe and the renderer retry with a pause instead of giving up,
     and a context is never required to be "hardware" (failIfMajorPerformanceCaveat false). */
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const GL = AKT.gl = {
    attrs(antialias) { return { antialias: !!antialias, alpha: false, depth: true, stencil: false, powerPreference: 'default', failIfMajorPerformanceCaveat: false, preserveDrawingBuffer: false }; },
    make(canvas, antialias) {
      for (const k of ['webgl2', 'webgl', 'experimental-webgl']) {
        try { const g = canvas.getContext(k, GL.attrs(antialias)); if (g) return g; } catch (e) { /* the next kind */ }
      }
      return null;
    },
    /* a context for the renderer: up to `tries` attempts, 250 ms · n apart; null when the browser never gave one */
    async acquire(canvas, antialias, tries) {
      for (let i = 0; i < (tries || 5); i++) {
        const g = GL.make(canvas, antialias);
        if (g && !(g.isContextLost && g.isContextLost())) return g;
        await sleep(250 * (i + 1));
      }
      return null;
    },
    info: null,
    /* does the browser give WebGL at all, and is it software (SwiftShader, llvmpipe)? cached; the probe context is released */
    probe() {
      if (GL.info && GL.info.ok) return GL.info;
      let info = { ok: false, name: '', soft: false };
      try {
        const g = GL.make(document.createElement('canvas'), false);
        if (g) {
          const ext = g.getExtension('WEBGL_debug_renderer_info');
          const name = String(ext ? g.getParameter(ext.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER));
          info = { ok: true, name, soft: /swiftshader|llvmpipe|software|basic render/i.test(name) };
          const lose = g.getExtension('WEBGL_lose_context'); if (lose) lose.loseContext();
        }
      } catch (e) { /* no WebGL */ }
      if (info.ok || !GL.info) GL.info = info;
      return GL.info;
    },
    async available() {
      for (let i = 0; i < 4; i++) { if (GL.probe().ok) return true; await sleep(300 * (i + 1)); }
      return false;
    },
  };
  const webgl = () => !!window.WebGLRenderingContext && GL.probe().ok;
  const WEBGL_NOTE = '3D не запустился: браузер не дал создать контекст WebGL. Чтобы увидеть 3D: включите аппаратное ускорение в настройках браузера (Chrome: Настройки → Система) и обновите страницу; на компьютере без видеокарты запустите Chrome с флагом --enable-unsafe-swiftshader. Все данные и последствия сценариев показаны на 2D-плане.';
  const HOW = 'Чтобы получить 3D, обновите страницу; если не помогло — включите аппаратное ускорение браузера или запустите Chrome с флагом --enable-unsafe-swiftshader.';
  /* ru: {none, stopped, failed} — the notes over the 2D plan */
  const lazy3d = (url, ru) => ({
    impl: null,
    async build(stage, opts) {
      this.impl = null;
      if (!window.WebGLRenderingContext || !(await GL.available())) return this.fallback(stage, ru.none);
      let lastErr = null;
      for (let attempt = 0; attempt < 3; attempt++) {         /* a scene that fails to start is started again twice before the 2D plan */
        try {
          const m = await import(url);
          this.impl = await m.create(AKT, stage, Object.assign({ focus: AKT.params.get('focus') || '' }, opts || {}),
            reason => this.fallback(stage, `${ru.stopped} (${reason}): показан 2D-план. ${HOW}`));
          return;
        } catch (e) {
          lastErr = e; console.error(e);
          if (AKT.current !== this && AKT.views[AKT.viewName()] !== this) return;   /* the user has left the view */
          await sleep(400 * (attempt + 1));
        }
      }
      return this.fallback(stage, `${ru.failed} (${lastErr && lastErr.message ? lastErr.message : lastErr}): показан 2D-план. ${HOW}`);
    },
    async fallback(stage, note) {
      if (this.impl && this.impl !== AKT.views.plan && this.impl.destroy) { try { this.impl.destroy(); } catch (e) { console.error(e); } }
      this.impl = AKT.views.plan;
      await AKT.views.plan.build(stage, { note });
      AKT.views.plan.update();
    },
    update() { if (this.impl && this.impl.update) this.impl.update(); },
    destroy() { if (this.impl && this.impl.destroy) this.impl.destroy(); this.impl = null; },
    highlight(node) { if (this.impl && this.impl.highlight) this.impl.highlight(node); },
  });
  AKT.views.site = lazy3d('/site3d.js', {
    none: WEBGL_NOTE,
    stopped: 'Вид «Спутник 3D» остановлен', failed: 'Вид «Спутник 3D» не запустился',
  });
  AKT.views.diorama = lazy3d('/diorama/core.js', {
    none: WEBGL_NOTE,
    stopped: 'Диорама остановлена', failed: 'Диорама не запустилась',
  });
  /* the 3D code of the opened view loads while the first poll of Ditto runs */
  const pre = { site: '/site3d.js', diorama: '/diorama/core.js', '3d': '/diorama/core.js' }[AKT.params.get('view') || ''];
  if (pre && webgl()) import(pre).catch(() => { /* build() reports the error */ });
})();
