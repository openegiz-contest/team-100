/* Page «Сценарии»: the catalog of scenarios (every one starts in one click, by its seed, with «что должно произойти» and
   «как проверить») and the constructor of a trouble (node, time, magnitude -> one token -> control.scenario in Ditto, the
   same path as the buttons of «Пульт модели»). The texts and ranges come from scenarios.json, which aktogay/modules/
   scenarios.py writes (a test keeps it equal); the numbers on this page are read from there or from Ditto. */
'use strict';
(function () {
  const esc = AKT.esc, fmt = AKT.fmt;
  const START_MIN = 480;                        /* the scenario shift starts at 08:00 of the model clock */
  const MAX_ROWS = 3;
  const doc = (stage, id) => { stage.innerHTML = ''; const d = document.createElement('div'); d.className = 'doc'; d.id = id; stage.appendChild(d); return d; };
  const numRu = (v, step) => fmt(v, step && step < 1 ? (step < 0.1 ? 2 : 1) : (Number.isInteger(v) ? 0 : 1));
  /* the token of one constructor row: kind[:N][@start_min][=magnitude] (sim/events.py) */
  const tokenOf = r => `${r.kind}${r.line ? ':' + r.line : ''}${r.delay ? '@' + r.delay : ''}${r.mag != null ? '=' + String(r.mag) : ''}`;
  AKT.scen = { tokenOf };

  AKT.views.scenarios = {
    data: null,
    rows: [],
    build(stage) {
      const d = doc(stage, 'scenarios');
      d.innerHTML = `<h2>Сценарии</h2>
<p class="lead">Каждый сценарий запускается одной кнопкой и описан двумя строками: что должно произойти и как это проверить. Сценарий начинает смену заново с 08:00 по номеру прогона: тот же сценарий и тот же номер дают те же числа. Идущий сценарий виден по синей штриховке рамки и плашке «Учебный сценарий» вверху панели; остановить его можно там же.</p>
<div class="sc-bar"><label>Номер прогона (seed) <input type="number" id="scn-seed" min="1" max="99999" step="1" value="42"></label>
<a href="${AKT.href('?view=plan')}" id="scn-go">к обзору →</a><span class="note" id="scn-state"></span></div>
<div id="scn-cat"><p class="empty dash">Загружаю каталог…</p></div>
<h2 id="constructor">Конструктор беды</h2>
<p class="lead">Выберите узел, время и величину — беда запустится без кода тем же путём, что кнопки каталога: команда записывается в вещь <code>control</code> в Ditto. Диапазон величины — диапазон правдоподобия параметра модели, метка рядом с ним (допущение, аналог…) говорит, на чём он стоит. До трёх бед в одной смене.</p>
<div id="scn-ctor"></div>`;
      fetch('/scenarios.json', { cache: 'no-store' }).then(r => r.json()).then(j => { this.data = j; this.render(); this.update(); })
        .catch(() => { const c = document.getElementById('scn-cat'); if (c) c.innerHTML = '<p class="empty dash">Каталог не загрузился.</p>'; });
    },
    seed() { return Math.max(1, Math.round(Number((document.getElementById('scn-seed') || {}).value) || 42)); },
    render() {
      const j = this.data;
      const cat = document.getElementById('scn-cat');
      cat.innerHTML = j.groups.map(g => {
        const items = j.scenarios.filter(s => s.group === g.id);
        if (!items.length) return '';
        return `<h3>${esc(g.name)}</h3>` + items.map(s => `<article class="sc-card" id="sc-${esc(s.id.replace(/[^a-z0-9]/g, '_'))}">
<div class="sc-head"><b title="Код сценария: ${esc(s.id)}">${esc(s.name)}</b> <span class="sc-live" data-live="${esc(s.id)}" hidden>идёт сейчас</span>
<button type="button" class="sc-run" data-id="${esc(s.id)}" data-name="${esc(s.name)}">Запустить</button></div>
<div class="sc-ok" hidden><span>Смена начнётся заново с 08:00, прогон № <b class="sc-seedv"></b>. Текущий прогон закончится.</span>
<button type="button" class="primary" data-go="${esc(s.id)}">Да, запустить</button><button type="button" data-no>Отмена</button></div>
<dl class="sc-dl"><dt>Что должно произойти</dt><dd>${esc(s.what)}</dd>
<dt>Какая беда первая</dt><dd>${esc(s.first)}</dd>
<dt>Как проверить</dt><dd><ol>${s.steps.map(x => `<li>${esc(x)}</li>`).join('')}</ol></dd>
<dt>Кого звать</dt><dd>${esc(s.who)}${s.backup ? `; запасной: ${esc(s.backup)}` : ''}</dd>
<dt>Закроется</dt><dd>${esc(s.closure)}</dd></dl>
<p class="note" title="Автотест: ${esc(s.test)}">${s.howto ? `Строка «Как проверить»: ${esc(s.howto)} · ` : ''}прогон № ${fmt(s.seed)}</p>
</article>`).join('');
      }).join('');
      cat.querySelectorAll('.sc-run').forEach(b => b.addEventListener('click', () => {
        const card = b.closest('.sc-card'), box = card.querySelector('.sc-ok');
        cat.querySelectorAll('.sc-ok').forEach(o => { if (o !== box) o.hidden = true; });
        box.querySelector('.sc-seedv').textContent = String(this.seed());
        box.hidden = !box.hidden;
        if (!box.hidden) box.querySelector('[data-go]').focus();
      }));
      cat.querySelectorAll('[data-no]').forEach(b => b.addEventListener('click', () => { b.closest('.sc-ok').hidden = true; }));
      cat.querySelectorAll('[data-go]').forEach(b => b.addEventListener('click', async () => {
        b.closest('.sc-ok').hidden = true;
        const card = b.closest('.sc-card'), name = card.querySelector('.sc-run').dataset.name;
        const ok = await AKT.panel.scenario(b.dataset.go, { seed: this.seed(), name });
        this.say(ok ? `Сценарий «${name}» запущен (прогон № ${this.seed()}). Обратный отсчёт — вверху панели.` : 'Не получилось запустить, нажмите ещё раз.');
      }));
      this.renderCtor();
    },
    say(t) { const e = document.getElementById('scn-state'); if (e) e.textContent = t; },
    /* ------------------------------------------------------------ constructor */
    renderCtor() {
      const c = this.data.constructor, el = document.getElementById('scn-ctor');
      const nodes = [...new Set(c.troubles.map(t => t.node))];
      el.innerHTML = `<div class="ct-grid">
<label>Узел <select id="ct-node">${nodes.map(n => `<option>${esc(n)}</option>`).join('')}</select></label>
<label>Что случится <select id="ct-kind"></select></label>
<label id="ct-line-w">Линия <select id="ct-line"></select></label>
<label class="ct-wide">Когда: <b id="ct-delay-v"></b><input type="range" id="ct-delay" min="0" max="${c.delay_max_min}" step="${c.delay_step_min}" value="60"></label>
<label class="ct-wide" id="ct-mag-w"><span><span id="ct-mag-l"></span>: <b id="ct-mag-v"></b></span><input type="range" id="ct-mag"></label>
</div>
<p class="note" id="ct-note"></p>
<div class="ct-btns"><button type="button" id="ct-add">Добавить в сценарий</button><span class="note" id="ct-msg"></span></div>
<div id="ct-list"></div>`;
      const $ = id => document.getElementById(id);
      const cur = () => c.troubles.find(t => t.node === $('ct-node').value && t.title === $('ct-kind').value) || c.troubles[0];
      const fillKinds = () => {
        const list = c.troubles.filter(t => t.node === $('ct-node').value);
        $('ct-kind').innerHTML = list.map(t => `<option>${esc(t.title)}</option>`).join('');
        fillLine();
      };
      const fillLine = () => {
        const t = cur();
        $('ct-line-w').hidden = !t.lines.length;
        $('ct-line').innerHTML = t.lines.map(n => `<option value="${n}">${n}</option>`).join('');
        const m = t.mag;
        $('ct-mag-w').hidden = !m;
        if (m) {
          const r = $('ct-mag'); r.min = m.min; r.max = m.max; r.step = m.step || (m.max - m.min) / 20; r.value = m.default;
          $('ct-mag-l').textContent = `${m.label}, ${m.unit} (диапазон ${numRu(m.min, m.step)}–${numRu(m.max, m.step)}, ${m.label_src})`;
        }
        $('ct-note').textContent = `${t.note}.${m ? '' : ' Величины у этой беды нет.'}`;
        preview();
      };
      const row = () => {
        const t = cur(), m = t.mag;
        const r = { kind: t.kind, line: t.lines.length ? Number($('ct-line').value) : 0, delay: Number($('ct-delay').value), mag: null, t };
        if (m) { const v = Number($('ct-mag').value); r.mag = Math.abs(v - m.default) < 1e-9 ? null : Math.round(v * 1000) / 1000; r.magShown = v; }
        return r;
      };
      const words = r => {
        const t = r.t, m = t.mag;
        return `${t.node}${r.line ? ' ' + r.line : ''}: ${t.title.toLowerCase()}, в ${AKT.clock(START_MIN + r.delay)}` +
          (m ? `, ${m.label.toLowerCase()} ${numRu(r.magShown, m.step)} ${m.unit}` : '');
      };
      const preview = () => {
        const r = row();
        $('ct-delay-v').textContent = `через ${AKT.dur(r.delay)} после начала смены (в ${AKT.clock(START_MIN + r.delay)})`;
        if (r.t.mag) $('ct-mag-v').textContent = `${numRu(r.magShown, r.t.mag.step)} ${r.t.mag.unit}`;
      };
      $('ct-node').addEventListener('change', fillKinds);
      $('ct-kind').addEventListener('change', fillLine);
      ['ct-line', 'ct-delay', 'ct-mag'].forEach(id => $(id).addEventListener('input', preview));
      $('ct-add').addEventListener('click', () => {
        const r = row();
        if (this.rows.length >= MAX_ROWS) { $('ct-msg').textContent = `Не больше ${MAX_ROWS} бед в смене.`; return; }
        if (this.rows.some(x => x.kind === r.kind && x.line === r.line)) { $('ct-msg').textContent = 'Такая беда на этом узле уже есть в списке.'; return; }
        $('ct-msg').textContent = '';
        r.text = words(r);
        this.rows.push(r);
        this.renderList();
      });
      this.ctor = { words };
      fillKinds();
      this.renderList();
    },
    renderList() {
      const el = document.getElementById('ct-list');
      if (!el) return;
      if (!this.rows.length) { el.innerHTML = '<p class="empty dash">Сценарий пуст: выберите беду и нажмите «Добавить в сценарий».</p>'; return; }
      const id = this.rows.map(tokenOf).join('+');
      el.innerHTML = `<ol class="ct-rows">${this.rows.map((r, i) => `<li>${esc(r.text)} <button type="button" class="quiet" data-del="${i}">убрать</button></li>`).join('')}</ol>
<p class="note" title="Команда двойнику: ${esc(id)}">Прогон № ${this.seed()}</p>
<div class="ct-btns"><button type="button" class="primary" id="ct-run">Запустить сценарий</button> <button type="button" id="ct-clear">Очистить</button>
<span class="sc-ok" id="ct-ok" hidden><span>Смена начнётся заново с 08:00. Текущий прогон закончится.</span> <button type="button" class="primary" id="ct-yes">Да, запустить</button> <button type="button" id="ct-no">Отмена</button></span></div>`;
      el.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', () => { this.rows.splice(Number(b.dataset.del), 1); this.renderList(); }));
      document.getElementById('ct-clear').addEventListener('click', () => { this.rows = []; this.renderList(); });
      document.getElementById('ct-run').addEventListener('click', () => { document.getElementById('ct-ok').hidden = false; document.getElementById('ct-yes').focus(); });
      document.getElementById('ct-no').addEventListener('click', () => { document.getElementById('ct-ok').hidden = true; });
      document.getElementById('ct-yes').addEventListener('click', async () => {
        document.getElementById('ct-ok').hidden = true;
        const ok = await AKT.panel.scenario(id, { seed: this.seed(), name: 'Своя беда' });
        this.say(ok ? `Запущено: своя беда (прогон № ${this.seed()}).` : 'Не получилось запустить, нажмите ещё раз.');
      });
    },
    update() {
      if (!this.data) return;
      const scen = AKT.scenario();
      document.querySelectorAll('#scn-cat [data-live]').forEach(e => { e.hidden = !(scen && scen.split('+').join('+') === e.dataset.live.split('+').join('+')); });
      const seedEl = document.getElementById('scn-seed');
      if (seedEl && document.activeElement !== seedEl && !seedEl.dataset.touched && AKT.num('site', 'seed') != null) seedEl.value = String(AKT.num('site', 'seed'));
      const warm = AKT.st('site') === 'WARMUP';
      document.querySelectorAll('#scn-cat .sc-run, #ct-run').forEach(b => { b.disabled = warm; });
      const note = document.getElementById('ct-list'); if (note && this.rows.length) { const p = note.querySelector('code'); if (p) p.textContent = this.rows.map(tokenOf).join('+'); }
    },
  };
  document.addEventListener('input', ev => { if (ev.target && ev.target.id === 'scn-seed') ev.target.dataset.touched = '1'; });
})();
