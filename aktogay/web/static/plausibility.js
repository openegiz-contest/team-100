/* «Проверка правдоподобия» на странице «Калибровка»: инварианты двойника по живым значениям из Ditto.
   Список проверок — plausibility.json (sim/plausibility.py: балансы меди, воды, массы и энергии, пределы оборудования,
   диапазоны величин с источником). Правило то же, что в Python: значение = масштаб × сумма членов / сумма знаменателя,
   член = коэффициент × произведение показаний; проверка выполнена, если каждое значение с данными лежит в [lo, hi].
   Нет данных — «нет данных», не «✓». Раз в минуту (по часам браузера) значения попадают в счёт: сколько минут
   наблюдения проверка выполнялась. Источник данных — только состояние Ditto (AKT.num), ничего больше. */
'use strict';
(function () {
  const A = window.AKT || (window.AKT = {});
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v, d = 0) => (v == null || !isFinite(v)) ? '—'
    : new Intl.NumberFormat('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
  const GROUP = { balance: 'баланс', limit: 'предел', range: 'диапазон' };
  const LABEL = { fact: 'факт', vendor: 'вендор', project: 'проект', analog: 'аналог', calc: 'расчёт', assumption: 'допущение' };
  const SAMPLE_S = 60;

  const P = A.plaus = { spec: null, hist: {}, since: null, lastSample: 0, minutes: 0, rows: [] };

  /* показание "thing.feature" из состояния; -1 — «нет значения» модели */
  function get(ref) {
    const i = ref.indexOf('.');
    const v = A.num(ref.slice(0, i), ref.slice(i + 1));
    return (v == null || !isFinite(v) || v === -1) ? null : v;
  }
  function prod(refs) {
    let x = 1;
    for (const r of refs) { const g = get(r); if (g == null) return null; x *= g; }
    return x;
  }
  function sum(terms) {
    let s = 0;
    for (const t of terms) { const p = prod(t.slice(1)); if (p == null) return null; s += t[0] * p; }
    return s;
  }
  P.itemValue = function (it) {
    let num = sum(it.terms);
    if (num == null) return null;
    if (it.den) { const d = sum(it.den); if (d == null || Math.abs(d) < 1e-6) return null; num /= d; }
    return (it.scale == null ? 1 : it.scale) * num;
  };
  P.evaluate = function (spec) {
    return spec.checks.map(c => {
      let worst = null, n = 0, bad = 0;
      c.items.forEach((it, i) => {
        const v = P.itemValue(it);
        if (v == null) return;
        n++;
        const h = c.item_hi ? c.item_hi[i] : c.hi, lo = c.lo;
        const span = (lo != null && h != null) ? (h - lo) : (Math.abs(h != null ? h : lo) || 1);
        const over = Math.max(lo != null ? (lo - v) / span : -1e9, h != null ? (v - h) / span : -1e9);
        if (over > 1e-9) bad++;
        if (!worst || over > worst.over) worst = { over, v, name: it.name || '', lim: h };
      });
      return { id: c.id, status: !worst ? 'na' : (bad ? 'bad' : 'ok'), value: worst && worst.v, name: worst ? worst.name : '', n, bad, lim: worst ? worst.lim : null };
    });
  };
  P.load = function (cb) {
    if (P.spec || P.loading) return;
    P.loading = true;
    fetch('/plausibility.json', { cache: 'no-store' }).then(r => r.json()).then(j => { P.spec = j; P.loading = false; if (cb) cb(); })
      .catch(() => { P.loading = false; });
  };
  const rangeText = c => {
    const f = v => fmt(v, Math.abs(v) < 1 && v !== 0 ? 3 : (Math.abs(v) < 20 ? 1 : 0));
    if (c.lo != null && c.hi != null) return `${f(c.lo)} … ${f(c.hi)}`;
    if (c.hi != null) return `не выше ${f(c.hi)}`;
    return `не ниже ${f(c.lo)}`;
  };
  /* вызывается при каждом обновлении страницы; в счёт попадает не чаще раза в минуту */
  P.tick = function () {
    if (!P.spec) return null;
    P.rows = P.evaluate(P.spec);
    const now = Date.now() / 1000;
    if (P.since == null) P.since = now;
    if (now - P.lastSample >= SAMPLE_S && P.rows.some(r => r.status !== 'na')) {
      P.lastSample = now; P.minutes++;
      P.rows.forEach(r => { const h = P.hist[r.id] || (P.hist[r.id] = { ok: 0, bad: 0, na: 0 }); h[r.status]++; });
    }
    return P.rows;
  };
  P.render = function () {
    if (!P.spec) return '<p class="empty dash">Загружаю список проверок…</p>';
    const rows = P.rows.length ? P.rows : P.evaluate(P.spec);
    const by = Object.fromEntries(rows.map(r => [r.id, r]));
    const nOk = rows.filter(r => r.status === 'ok').length, nBad = rows.filter(r => r.status === 'bad').length;
    const nNa = rows.length - nOk - nBad;
    const lead = `<p class="lead">Сейчас выполнено <b>${nOk}</b> из ${rows.length} проверок${nBad ? `, не выполнено <b>${nBad}</b>` : ''}${nNa ? `, без данных ${nNa} (нужен модуль или линия в работе)` : ''}.
 Считается по живому состоянию двойника; в журнал наблюдения попадает одна точка в минуту: ${P.minutes ? `за ${P.minutes} мин наблюдения на этой странице` : 'ждём первую минуту'}.</p>`;
    const body = P.spec.checks.map(c => {
      const r = by[c.id] || { status: 'na' };
      const h = P.hist[c.id];
      const mark = r.status === 'ok' ? '✓ выполнено' : r.status === 'bad' ? '✗ не выполнено' : '— нет данных';
      const val = r.value == null ? '—' : `${fmt(r.value, Math.abs(r.value) < 1 ? 3 : (Math.abs(r.value) < 100 ? 2 : 0))}${r.name && c.items.length > 1 ? ` <span class="note">(${esc(r.name)}${c.item_hi && r.lim != null ? `, предел ${fmt(r.lim, 0)}` : ''})</span>` : ''}`;
      const share = h && (h.ok + h.bad) ? `${fmt(100 * h.ok / (h.ok + h.bad))} % из ${h.ok + h.bad}` : '—';
      return `<tr class="${r.status === 'bad' ? 'row-lv-1' : ''}"><td><b class="${r.status === 'bad' ? 'bad' : 'ok'}">${mark}</b></td><td>${esc(GROUP[c.group] || c.group)}</td><td>${esc(c.ru)}</td>
<td class="n">${val} ${esc(c.unit)}</td><td class="n">${esc(rangeText(c))}</td><td>${esc(c.src)} <span class="note">[${esc(LABEL[c.label] || c.label)}]</span></td><td class="n">${share}</td></tr>`;
    }).join('');
    /* доступность агрегатов: не живое значение, а итог годового прогона модели (fidelity.json) против проектных значений Ausenco */
    const fd = A.fidelity && A.fidelity.data && A.fidelity.data.availability;
    const NAME = { crusher: 'Дробилка: часы работы за год (руда / номинальная производительность)', grinding: 'Измельчение: доля времени в работе за год', flotation: 'Флотация: доля времени в работе за год' };
    /* verdict of a row: only flotation is a check (✓/✗); grinding is a fit, the crusher row is a requirement of the reported ore on the equipment: no verdict */
    const aver = u => u.class === 'requirement' ? ['', 'требование к оборудованию'] : u.class === 'fit' ? ['', 'подгонка, не проверка'] : u.ok ? ['ok', '✓ выполнено'] : ['bad', '✗ не выполнено'];
    const asrc = (u, y) => u.class === 'requirement'
      ? `часы работы по счётчику при темпе участка 5 044–4 386 т/ч (с коэффициентом 1,15; паспорта дробилки нет); руде ${y} г. нужны ${fmt(u.required_hours_pct[2], 1)}–${fmt(u.required_hours_pct[0], 1)} % часов, проект ОВОС даёт ${fmt(u.design_hours_pct, 1)} %, Ausenco ${fmt(u.lit_lo, 0)}–${fmt(u.lit_hi, 0)} % <span class="note">[проект][вендор]</span>`
      : u.class === 'fit' ? `следует из готовности линии, подогнанной на руду ${y} г.; проектная доступность Ausenco ${fmt(u.lit_lo, 0)}–${fmt(u.lit_hi, 0)} % <span class="note">[вендор]</span>`
        : `прогон модели ${y} г. против проектной доступности Ausenco (${fmt(u.lit_lo, 0)}–${fmt(u.lit_hi, 0)} %, допуск ±2 п.п.) <span class="note">[вендор]</span>`;
    const avail = fd ? Object.entries(fd.units).map(([k, u]) => { const [cl, txt] = aver(u); return `<tr class="${cl === 'bad' ? 'row-lv-1' : ''}"><td><b${cl ? ` class="${cl}"` : ''}>${txt}</b></td><td>доступность</td><td>${esc(NAME[k] || k)}</td>
<td class="n">${u.run_pct_range ? `${fmt(u.run_pct_range[0], 1)}–${fmt(u.run_pct_range[1], 1)}` : fmt(u.run_pct, 1)} %</td><td class="n">${u.class === 'requirement' ? '—' : `${fmt(u.lit_lo - 2, 0)} … ${fmt(u.lit_hi + 2, 0)}`}</td><td>${asrc(u, fd.year)}</td><td class="n">за год</td></tr>`; }).join('') : '';
    return `${lead}<div style="overflow-x:auto"><table class="kv"><tr><th>Итог</th><th>Вид</th><th>Что проверяем</th><th>Значение</th><th>Допустимо</th><th>Источник</th><th>Минут ✓</th></tr>${body}${avail}</table></div>
<p class="note">Значение — худшее среди линий, мельниц или самосвалов. ✗ значит, что число выходит за границу; это не отказ оборудования, а вопрос к модели или к границе. Границы без источника в таблице помечены «допущение». Список и правила: <code>sim/plausibility.py</code> → <code>plausibility.json</code>.</p>`;
  };
})();
