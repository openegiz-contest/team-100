/* 3D views: ?view=diorama (diorama/core.js, the main 3D view, menu «Диорама»; ?view=3d is the same) and
   ?view=site (site3d.js, menu «Спутник 3D»), ES modules
   with three.js r160 vendored in vendor/, loaded only when the view opens. Without
   WebGL, or when the scene fails to start, the 2D plan is shown with a note. */
'use strict';
(function () {
  const webgl = () => {
    try {
      const c = document.createElement('canvas');
      return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl') || c.getContext('experimental-webgl')));
    } catch (e) { return false; }
  };
  /* ru: {none, stopped, failed} — the notes over the 2D plan */
  const lazy3d = (url, ru) => ({
    impl: null,
    async build(stage, opts) {
      this.impl = null;
      if (!webgl()) return this.fallback(stage, ru.none);
      try {
        const m = await import(url);
        this.impl = await m.create(AKT, stage, Object.assign({ focus: AKT.params.get('focus') || '' }, opts || {}),
          reason => this.fallback(stage, `${ru.stopped} (${reason}): показан 2D-план.`));
      } catch (e) {
        console.error(e);
        return this.fallback(stage, `${ru.failed} (${e && e.message ? e.message : e}): показан 2D-план.`);
      }
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
    none: 'В этом браузере нет WebGL, вид «Спутник 3D» недоступен: показан 2D-план.',
    stopped: 'Вид «Спутник 3D» остановлен', failed: 'Вид «Спутник 3D» не запустился',
  });
  AKT.views.diorama = lazy3d('/diorama/core.js', {
    none: 'В этом браузере нет WebGL, диорама недоступна: показан 2D-план.',
    stopped: 'Диорама остановлена', failed: 'Диорама не запустилась',
  });
  /* the 3D code of the opened view loads while the first poll of Ditto runs */
  const pre = { site: '/site3d.js', diorama: '/diorama/core.js', '3d': '/diorama/core.js' }[AKT.params.get('view') || ''];
  if (pre && webgl()) import(pre).catch(() => { /* build() reports the error */ });
})();
