/* What-if levers of the MODEL («Рычаги модели»): feed rate of each SAG line, grind P80 target, collector dose. They are a
   control of the model, not of the plant: the command goes to the thing `control` (feature lever) in Ditto, the simulator
   obeys, and everything else (map, «Путь меди», tiles, 3D, «база / с рычагами / разница») reads the changed features from
   Ditto as usual. Off by default; a reset or «Остановить» returns the stand to the plain free run.
   Also: the button «Применить совет в модели» of an advice that changes the regime (issue.lever, forecast.liner.lever). */
'use strict';
(function () {
  const esc = AKT.esc, fmt = AKT.fmt;
  const doc = (stage, id) => { stage.innerHTML = ''; const d = document.createElement('div'); d.className = 'doc'; d.id = id; stage.appendChild(d); return d; };
  /* ranges of the levers = lev_* rows of sim/params_lev.py (a test keeps them equal) */
  const R = { feed: { min: 80, max: 120, step: 1, nominal: 3853 }, p80: { min: 160, max: 200, step: 5 }, dose: { min: 15, max: 40, step: 1, opt: 25 } };
  const P80_SLOPE = { lab: 1.2, plant: 1.95 };       /* pp of Cu recovery per 10 um (Bozshakol study: laboratory, plant model) */
  const NOTE = 'управление моделью, не фабрикой';

  const L = AKT.lever = {
    ranges: R, applied: null,
    on() { return AKT.num('site', 'lever_on') === 1; },
    values() { return { feed_1: AKT.num('site', 'lever_feed_1'), feed_2: AKT.num('site', 'lever_feed_2'), p80_um: AKT.num('site', 'lever_p80_um'), dose_gt: AKT.num('site', 'lever_dose_gt') }; },
    /* the base copy of the comparison (levers off) is valid for this run */
    baseOk() { return L.on() && !!AKT.run && String(AKT.val('baseline', 'idSimulationRun') || '') === AKT.run; },
    base(thing, f) { if (!L.baseOk()) return null; return AKT.num('baseline', `${thing}_${f}_base`); },
    /* the numbers compared: [key, label, unit, digits, getter(thing, f -> number|null)] */
    metrics(get) {
      const w = (f, g) => { const a = get('line-1', 'tph'), b = get('line-2', 'tph'), x = g('line-1', f), y = g('line-2', f); if (x == null || y == null || !((a || 0) + (b || 0))) return null; return (x * (a || 0) + y * (b || 0)) / ((a || 0) + (b || 0)); };
      return {
        tph: get('site', 'tph'), cu: get('site', 'cu_tph'),
        rec: w('recovery', get), kwht: w('e_kwh_t', (t, f) => get(t === 'line-1' ? 'sag-1' : 'sag-2', f)),
        p80: w('p80_um', (t, f) => get(t === 'line-1' ? 'cyclones-1' : 'cyclones-2', f)),
        mw: get('site', 'power_mw'),
        usd: (get('line-1', 'cum_usd') != null && get('line-2', 'cum_usd') != null) ? get('line-1', 'cum_usd') + get('line-2', 'cum_usd') : null,
        hrs: Math.min(...[1, 2].map(n => get('stockpile-' + n, 'hours_left')).filter(v => v != null && v >= 0).concat([99])),
        conc: (() => { const c = get('flot-1', 'cu_tph'), d = get('flot-1', 'conc_tph'), c2 = get('flot-2', 'cu_tph'), d2 = get('flot-2', 'conc_tph'); const cu = (c || 0) + (c2 || 0), cc = (d || 0) + (d2 || 0); return cc > 0 ? 100 * cu / cc : null; })(),
      };
    },
    now() { return L.metrics((t, f) => AKT.num(t, f)); },
    baseNow() { return L.baseOk() ? L.metrics((t, f) => L.base(t, f)) : null; },
    /* a suggestion of an advice (issue.lever / forecast.liner.lever): {name, line, value, unit, label, reason} or null */
    suggestion(o) { return o && typeof o === 'object' && o.name ? o : null; },
    payload(s) { return s.name === 'p80_um' ? { p80_um: s.value } : s.name === 'feed' ? { ['feed_' + s.line]: s.value } : { dose_gt: s.value }; },
    async send(body, what) {
      try {
        await AKT.post('/api/lever', body);
        setTimeout(AKT.poll, 300); setTimeout(AKT.poll, 3000);
        return true;
      } catch (e) { AKT.toast(`${what}: не получилось — ${e.message}. Нажмите ещё раз.`); return false; }
    },
    /* one click: set the lever of the advice, remember the numbers before */
    async apply(s, ref) {
      const before = L.now(), t0 = AKT.simTime;
      const body = L.payload(s), cur = L.values();
      if (s.name === 'p80_um') for (const n of [1, 2]) if (cur['feed_' + n] > 100) body['feed_' + n] = 100;   /* the grind advice also takes back a feed above the nominal */
      const ok = await L.send(body, 'Рычаг');
      if (!ok) return false;
      L.applied = { s, ref: ref || '', t0, before, base: null };
      AKT.toast(`Рычаг включён в ${AKT.clock(t0)}: ${s.label} — ${NOTE}. Результат — под советом и на странице «Рычаги модели».`);
      return true;
    },
    reset() { L.applied = null; return L.send({ reset: 1 }, 'Сброс рычагов'); },
    /* the button of an advice */
    btnHtml(s, ref) {
      return `<div class="lv-adv"><button type="button" class="primary" data-lever-apply="${esc(JSON.stringify(s))}" data-ref="${esc(ref || '')}">Применить совет в модели</button> <span class="p-sub">${esc(s.label)} · ${NOTE}. ${esc(s.reason)}</span></div>`;
    },
    /* before / after under the advice: numbers at the click, numbers now, the run without levers */
    resultHtml() {
      const a = L.applied;
      if (!a || !L.on()) return '';
      const now = L.now(), base = L.baseNow(), b = a.before;
      const row = (name, k, unit, d, sign) => {
        const v = now[k], x = b ? b[k] : null, y = base ? base[k] : null;
        if (v == null) return '';
        const df = (v1, v0) => v0 == null ? '' : ` (${v1 - v0 >= 0 ? '+' : '−'}${fmt(Math.abs(v1 - v0), d)})`;
        return `<tr><td>${name}</td><td class="n">${x == null ? '—' : fmt(x, d)}</td><td class="n">${fmt(v, d)}${sign ? df(v, x) : ''}</td><td class="n">${y == null ? '—' : fmt(y, d)}</td></tr>`;
      };
      return `<table class="kv lv-res"><tr><th>${NOTE}</th><th>в момент нажатия (${AKT.clock(a.t0)})</th><th>сейчас</th><th>ход без рычагов</th></tr>
${row('Руда на фабрику, т/ч', 'tph', '', 0, true)}${row('Медь в концентрат, т/ч', 'cu', '', 1, true)}${row('Извлечение, %', 'rec', '', 1, true)}${row('SAG, кВт·ч/т', 'kwht', '', 2, true)}${row('P80, мкм', 'p80', '', 0, true)}</table>
<p class="p-sub">Числа «сейчас» устанавливаются за 20–40 минут модели (склад, флотация); «ход без рычагов» — копия модели от той же минуты без рычага. Всё это оценка на модели.</p>`;
    },
    /* the part of the card of the first trouble */
    renderCard(issue) {
      const el = document.getElementById('tc-lever');
      if (!el) return;
      const s = issue ? L.suggestion(AKT.val(issue, 'lever')) : null;
      const html = s ? L.btnHtml(s, issue) + (L.applied && L.applied.ref === issue ? L.resultHtml() : '') : '';
      if (el._raw !== html) { el._raw = html; el.innerHTML = html; }
      el.hidden = !html;
    },
  };

  /* one click on any «Применить совет в модели» */
  document.addEventListener('click', ev => {
    const b = ev.target && ev.target.closest && ev.target.closest('[data-lever-apply]');
    if (!b) return;
    ev.preventDefault();
    let s = null; try { s = JSON.parse(b.dataset.leverApply); } catch (e) { /* ignore */ }
    if (s && s.name) { b.disabled = true; L.apply(s, b.dataset.ref).finally(() => { b.disabled = false; }); }
  });

  AKT.views.levers = {
    build(stage) {
      const d = doc(stage, 'levers');
      d.innerHTML = `<h2>Рычаги модели</h2>
<p class="lead"><b>${NOTE[0].toUpperCase() + NOTE.slice(1)}.</b> Три «что если» для металлурга: подача каждой линии SAG, цель по помолу P80, доза собирателя. Рычаг передаётся модели через двойник, модель подчиняется, а карта, «Путь меди», плитки и 3D сами показывают последствия — рядом с ходом без рычагов. На фабрике ничего не меняется. По умолчанию рычаги выключены; «Сбросить» возвращает обычный ход.</p>
<div class="lv-grid">
<article class="sc-card"><h3>Подача линии SAG</h3>
<p class="note">% номинала линии (≈ ${fmt(R.feed.nominal)} т/ч, модель). Выше 100 % мельница выходит на предел мощности (28 МВт), износ футеровки и круг гали по-прежнему ограничивают; ниже — склад копится.</p>
<label>Линия 1: <b id="lv-f1v"></b> % <input type="range" id="lv-f1" min="${R.feed.min}" max="${R.feed.max}" step="${R.feed.step}" value="100"></label>
<label>Линия 2: <b id="lv-f2v"></b> % <input type="range" id="lv-f2" min="${R.feed.min}" max="${R.feed.max}" step="${R.feed.step}" value="100"></label></article>
<article class="sc-card"><h3>Цель по помолу P80</h3>
<p class="note">Шаровые держат выбранный P80, подача подстраивается по Бонду (кВт·ч/т растёт при более тонком помоле, пропускная способность падает). Извлечение: <b>−${fmt(P80_SLOPE.lab, 1)} п.п. на +10 мкм</b> — лабораторный наклон (в модели) … <b>−${fmt(P80_SLOPE.plant, 2)}</b> — модель по суточным данным завода (Бозшаколь, Satbayev). Диапазон, не одно число.</p>
<label><input type="checkbox" id="lv-p80on"> включить: <b id="lv-p80v"></b> мкм <input type="range" id="lv-p80" min="${R.p80.min}" max="${R.p80.max}" step="${R.p80.step}" value="180"></label></article>
<article class="sc-card"><h3>Доза собирателя</h3>
<p class="note">Оптимум проекта ${fmt(R.dose.opt)} г/т (ОВОС линии 2). Ниже оптимума — потеря извлечения (в модели −3,5 п.п. при −40 % <i>[допущение]</i>, лабораторный аналог). Выше оптимума прироста извлечения нет (промышленный опыт, Индонезия: SIBX 5–15 г/т), а расход реагента и цена растут, качество концентрата падает (качественно).</p>
<label><input type="checkbox" id="lv-doseon"> включить: <b id="lv-dosev"></b> г/т <input type="range" id="lv-dose" min="${R.dose.min}" max="${R.dose.max}" step="${R.dose.step}" value="${R.dose.opt}"></label></article>
</div>
<div class="lv-btns"><button type="button" class="primary" id="lv-apply">Применить рычаги</button> <button type="button" id="lv-reset">Сбросить все рычаги</button> <span class="note" id="lv-state"></span></div>
<h3>База и с рычагами</h3><div id="lv-table"><p class="empty dash">Рычаги выключены: сравнивать не с чем. Передвиньте рычаг и нажмите «Применить рычаги».</p></div>
<p class="note">Откуда числа: подача и помол — модель Моррелла/Бонда стенда (PARAMETERS.md); наклон P80 — Бозшаколь (лаборатория −1,2, завод −1,95 п.п. на 10 мкм); доза и цена реагента — допущения стенда, показан порядок величины. Это оценка на модели, а не прогноз для фабрики.</p>`;
      const $ = id => document.getElementById(id);
      const sync = () => {
        $('lv-f1v').textContent = $('lv-f1').value; $('lv-f2v').textContent = $('lv-f2').value;
        $('lv-p80v').textContent = $('lv-p80on').checked ? $('lv-p80').value : 'выкл.'; $('lv-dosev').textContent = $('lv-doseon').checked ? $('lv-dose').value : 'выкл.';
        $('lv-p80').disabled = !$('lv-p80on').checked; $('lv-dose').disabled = !$('lv-doseon').checked;
      };
      d.querySelectorAll('input').forEach(i => i.addEventListener('input', () => { d.dataset.touched = '1'; sync(); }));
      $('lv-apply').addEventListener('click', async () => {
        const body = { feed_1: Number($('lv-f1').value), feed_2: Number($('lv-f2').value), p80_um: $('lv-p80on').checked ? Number($('lv-p80').value) : 0, dose_gt: $('lv-doseon').checked ? Number($('lv-dose').value) : 0 };
        if (await L.send(body, 'Рычаги')) { d.dataset.touched = ''; L.applied = { s: { label: 'рычаги со страницы «Рычаги модели»' }, ref: '', t0: AKT.simTime, before: L.now(), base: null }; AKT.toast(`Рычаги включены в ${AKT.clock(AKT.simTime)} — ${NOTE}.`); }
      });
      $('lv-reset').addEventListener('click', async () => { if (await L.reset()) { d.dataset.touched = ''; AKT.toast('Рычаги сброшены: обычный ход фабрики.'); } });
      sync();
    },
    update() {
      const d = document.getElementById('levers');
      if (!d) return;
      const $ = id => document.getElementById(id);
      const v = L.values(), on = L.on();
      if (!d.dataset.touched) {      /* the sliders follow the state of the model until the user moves one */
        if (v.feed_1 != null) $('lv-f1').value = v.feed_1; if (v.feed_2 != null) $('lv-f2').value = v.feed_2;
        $('lv-p80on').checked = v.p80_um != null && v.p80_um > 0; if (v.p80_um > 0) $('lv-p80').value = v.p80_um;
        $('lv-doseon').checked = v.dose_gt != null && v.dose_gt > 0; if (v.dose_gt > 0) $('lv-dose').value = v.dose_gt;
        $('lv-f1v').textContent = $('lv-f1').value; $('lv-f2v').textContent = $('lv-f2').value;
        $('lv-p80v').textContent = $('lv-p80on').checked ? $('lv-p80').value : 'выкл.'; $('lv-dosev').textContent = $('lv-doseon').checked ? $('lv-dose').value : 'выкл.';
        $('lv-p80').disabled = !$('lv-p80on').checked; $('lv-dose').disabled = !$('lv-doseon').checked;
      }
      $('lv-state').textContent = on ? `Включено в модели: ${L.describe()}` : 'Рычаги выключены.';
      const warm = AKT.st('site') === 'WARMUP';
      $('lv-apply').disabled = warm;
      const now = L.now(), base = L.baseNow();
      let html = '<p class="empty dash">Рычаги выключены: сравнивать не с чем. Передвиньте рычаг и нажмите «Применить рычаги».</p>';
      if (on && base) {
        const row = (name, k, dd, note) => {
          const a = base[k], b = now[k];
          if (a == null || b == null) return '';
          const df = b - a;
          return `<tr><td>${name}</td><td class="n">${fmt(a, dd)}</td><td class="n">${fmt(b, dd)}</td><td class="n lv-d">${df >= 0 ? '+' : '−'}${fmt(Math.abs(df), dd)}</td><td class="p-sub">${note || ''}</td></tr>`;
        };
        html = `<table class="kv"><tr><th>Показатель</th><th>База (без рычагов)</th><th>С рычагами</th><th>Разница</th><th></th></tr>
${row('Руда на фабрику, т/ч', 'tph', 0)}${row('Медь в концентрат, т Cu/ч', 'cu', 2)}${row('Извлечение, %', 'rec', 2)}${row('SAG, кВт·ч/т', 'kwht', 2, 'энергия на тонну')}${row('P80 флотации, мкм', 'p80', 0)}${row('Мощность площадки, МВт', 'mw', 1)}${row('Cu в концентрате, %', 'conc', 2, 'разбавление при передозировке — качественно')}${row('Стоимость за смену (Cu − энергия − вода), $', 'usd', 0, 'реагент учтён рычагом дозы [допущение]')}${row('Запас склада, ч', 'hrs', 1, 'меньше — склад вырабатывается')}</table>
<p class="p-sub">База — копия модели от минуты первого рычага, ведётся рядом без рычагов; решения (вызовы бригад) в обеих копиях одни и те же. Числа устанавливаются за 20–40 минут модели.</p>`;
      } else if (on) html = '<p class="empty dash">Рычаг включён, копия «без рычагов» ещё публикуется (до минуты).</p>';
      const res = on ? L.resultHtml() : '';
      const out = html + (res ? '<h3>С момента нажатия</h3>' + res : '');
      const t = $('lv-table'); if (t._raw !== out) { t._raw = out; t.innerHTML = out; }
    },
  };
  L.describe = () => {
    const v = L.values(), parts = [];
    if (v.feed_1 != null && v.feed_1 !== 100) parts.push(`линия 1 — ${fmt(v.feed_1)} % подачи`);
    if (v.feed_2 != null && v.feed_2 !== 100) parts.push(`линия 2 — ${fmt(v.feed_2)} % подачи`);
    if (v.p80_um != null && v.p80_um > 0) parts.push(`цель P80 ${fmt(v.p80_um)} мкм`);
    if (v.dose_gt != null && v.dose_gt > 0) parts.push(`доза ${fmt(v.dose_gt)} г/т`);
    return parts.join('; ') || '—';
  };
})();
