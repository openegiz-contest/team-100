/* «Проверка по кварталам» на странице «Калибровка»: модель против квартальных отчётов KAZ Minerals 2018–2025.
   AKT.backtest.render(data) -> строка HTML. data = validation-calib.report_json.backtest (sim/backtest.py):
   rows[] с полями q, kind, fit, ore_rep/ore_mod, grade_rep, rec_rep/rec_mod, cu_rep/cu_mod, rec_err, cu_err_pct,
   const_err, blind_cu_pct, tol_cu_pct, rec_ok, cu_ok, url, page; summary{all,single,ramp,two,fit}; tolerances; notes.
   Данные только из Ditto (report_json), без запросов к другим источникам. Цвет только у значений вне допуска и
   всегда с формой (ромб, подпись числа) и словами в таблице. Столбцы «модель» — [оценка на модели]; «отчёт» — [факт]. */
'use strict';
(function () {
  const A = window.AKT || (window.AKT = {});
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v, d = 0) => (v == null || !isFinite(v)) ? '—'
    : new Intl.NumberFormat('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
  const sg = (v, d = 1) => v == null || !isFinite(v) ? '—' : `${v > 0.0005 ? '+' : v < -0.0005 ? '−' : ''}${fmt(Math.abs(v), d)}`;
  const KIND_RU = { single: 'одна фабрика', ramp: 'разгон линии 2', two: 'две фабрики' };
  const CSS = `<style>
.bt-wrap{overflow-x:auto;max-width:100%}
.bt-svg{width:100%;min-width:640px;max-width:900px;height:auto;display:block}
.bt-svg text{font-size:11px;fill:var(--ink-2,#454b53)}
.bt-svg .bt-h{font-size:12px;font-weight:600;fill:var(--ink,#16191d)}
.bt-svg .bt-s{font-size:10px;fill:var(--ink-3,#5b626b)}
.bt-svg .bt-grid{stroke:var(--line,#c3c8cf);stroke-width:1}
.bt-svg .bt-zero{stroke:var(--ink,#16191d);stroke-width:1}
.bt-svg .bt-seg{fill:var(--ink,#16191d);fill-opacity:.045}
.bt-svg .bt-seg2{fill:var(--ink,#16191d);fill-opacity:.09}
.bt-svg .bt-none{fill:none}
.bt-svg .bt-fit{fill:url(#bt-hatch)}
.bt-svg .bt-band{fill:var(--ink,#16191d);fill-opacity:.12}
.bt-svg .bt-rep{fill:none;stroke:var(--ink,#16191d);stroke-width:1.4}
.bt-svg .bt-repd{fill:var(--ink,#16191d)}
.bt-svg .bt-mod{fill:none;stroke:var(--ink-2,#454b53);stroke-width:1.2}
.bt-svg .bt-modd{fill:var(--raised,#fff);stroke:var(--ink-2,#454b53);stroke-width:1.5}
.bt-svg .bt-badd{fill:var(--p1,#c62828);stroke:var(--p1-ink,#a61b1b);stroke-width:1}
.bt-svg .bt-const{stroke:var(--ink-3,#5b626b);stroke-width:1.2;stroke-dasharray:5 3;fill:none}
.bt-svg .bt-bar{fill:var(--ink-3,#5b626b)}
.bt-svg .bt-barbad{fill:var(--p1,#c62828)}
.bt-svg .bt-lbl{font-size:9px;font-weight:700;fill:var(--p1-ink,#a61b1b)}
.bt-svg .bt-ctick{stroke:var(--ink,#16191d);stroke-width:2}
.bt-leg{font-size:.86rem;color:var(--ink-2,#454b53);margin:2px 0 8px}
.bt-leg b{color:var(--ink,#16191d)}
table.bt-t{border-collapse:collapse;font-size:.86rem;min-width:720px;width:100%}
table.bt-t td,table.bt-t th{border-bottom:1px solid var(--line,#c3c8cf);padding:2px 4px;text-align:right;white-space:nowrap}
table.bt-t th{background:var(--sunk,#eceef1);font-weight:600;position:sticky;top:0}
table.bt-t td:first-child,table.bt-t th:first-child,table.bt-t td.l,table.bt-t th.l{text-align:left}
table.bt-t tr.bt-fitrow td{color:var(--ink-3,#5b626b);font-style:italic}
table.bt-t td.bt-bad{color:var(--p1-ink,#a61b1b);font-weight:700}
table.bt-t td.bt-sep,table.bt-t th.bt-sep{border-left:2px solid var(--line,#c3c8cf)}
</style>`;

  const shortPage = p => { const m = /p\.\s*(\d+)/.exec(p || ''); return m ? `с. ${m[1]}` : ''; };

  /* two stacked panels in one SVG: values (report vs model) above, error bars below */
  function chart(o) {
    const rows = o.rows, n = rows.length;
    const W = 760, PL = 52, PR = 12, top = 30, H1 = 170, gap = 34, H2 = 96, bot = 34;
    const H = top + H1 + gap + H2 + bot;
    const pw = W - PL - PR, step = pw / n;
    const X = i => PL + (i + 0.5) * step;
    const y1 = v => top + H1 * (1 - (v - o.lo) / (o.hi - o.lo));
    const yE = v => top + H1 + gap + H2 / 2 - (H2 / 2) * v / o.eMax;
    const ticks = []; for (let v = Math.ceil(o.lo / o.tick) * o.tick; v <= o.hi + 1e-9; v += o.tick) ticks.push(v);
    let s = `<svg class="bt-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.aria)}"><defs><pattern id="bt-hatch${o.id}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#8d939b" stroke-width="1.2" stroke-opacity=".35"/></pattern></defs>`;
    /* segments of the plant kind and the fit year */
    let i0 = 0;
    const seg = (a, b, label, cls) => {
      const xa = PL + a * step, xb = PL + (b + 1) * step;
      s += `<rect class="${cls}" x="${xa}" y="${top - 18}" width="${xb - xa}" height="${H1 + gap + H2 + 18}"${cls === 'bt-fit' ? ` style="fill:url(#bt-hatch${o.id})"` : ''}/><text class="bt-s" x="${(xa + xb) / 2}" y="${top - 6}" text-anchor="middle">${esc(label)}</text>`;
    };
    while (i0 < n) {
      let i1 = i0; const k = rows[i0].fit ? 'fit' : rows[i0].kind;
      while (i1 + 1 < n && (rows[i1 + 1].fit ? 'fit' : rows[i1 + 1].kind) === k) i1++;
      seg(i0, i1, k === 'fit' ? 'подгонка (не проверка)' : (KIND_RU[k] || k), k === 'fit' ? 'bt-fit' : k === 'two' ? 'bt-none' : k === 'ramp' ? 'bt-seg2' : 'bt-seg');
      i0 = i1 + 1;
    }
    /* grid and axis labels, upper panel */
    for (const v of ticks) s += `<line class="bt-grid" x1="${PL}" x2="${W - PR}" y1="${y1(v)}" y2="${y1(v)}"/><text x="${PL - 6}" y="${y1(v) + 4}" text-anchor="end">${esc(fmt(v, o.tickD))}</text>`;
    s += `<text class="bt-h" x="${PL - 46}" y="${top - 6}" text-anchor="start">${esc(o.unit)}</text>`;
    /* tolerance band around the report */
    const up = rows.map((r, i) => `${X(i)},${y1(Math.min(o.hi, o.rep(r) + o.tol(r)))}`);
    const dn = rows.map((r, i) => `${X(i)},${y1(Math.max(o.lo, o.rep(r) - o.tol(r)))}`).reverse();
    s += `<polygon class="bt-band" points="${up.concat(dn).join(' ')}"><title>${esc(o.bandTitle)}</title></polygon>`;
    if (o.constLine != null) s += `<line class="bt-const" x1="${PL}" x2="${W - PR}" y1="${y1(o.constLine)}" y2="${y1(o.constLine)}"><title>${esc(o.constTitle)}</title></line>`;
    s += `<polyline class="bt-rep" points="${rows.map((r, i) => `${X(i)},${y1(o.rep(r))}`).join(' ')}"/>`;
    s += `<polyline class="bt-mod" points="${rows.map((r, i) => `${X(i)},${y1(o.mod(r))}`).join(' ')}"/>`;
    rows.forEach((r, i) => {
      s += `<circle class="bt-repd" cx="${X(i)}" cy="${y1(o.rep(r))}" r="2.6"><title>${esc(r.q)} отчёт: ${esc(fmt(o.rep(r), o.valD))}</title></circle>`;
      const bad = !o.ok(r) && !r.fit, cx = X(i), cy = y1(o.mod(r));
      const tip = `<title>${esc(r.q)} модель: ${esc(fmt(o.mod(r), o.valD))}, отчёт ${esc(fmt(o.rep(r), o.valD))}, ошибка ${esc(sg(o.err(r), o.errD))}${bad ? ' — вне допуска' : ''}</title>`;
      s += bad ? `<polygon class="bt-badd" points="${cx},${cy - 5} ${cx + 5},${cy} ${cx},${cy + 5} ${cx - 5},${cy}">${tip}</polygon>`
        : `<rect class="bt-modd" x="${cx - 3.2}" y="${cy - 3.2}" width="6.4" height="6.4">${tip}</rect>`;
    });
    /* lower panel: model error bars, zero line, tolerance lines, constant-rule ticks */
    s += `<text class="bt-h" x="${PL - 46}" y="${top + H1 + gap - 8}">${esc(o.errUnit)}</text>`;
    for (const v of o.eTicks) s += `<line class="bt-grid" x1="${PL}" x2="${W - PR}" y1="${yE(v)}" y2="${yE(v)}"/><text x="${PL - 6}" y="${yE(v) + 4}" text-anchor="end">${esc(sg(v, o.errD))}</text>`;
    s += `<line class="bt-zero" x1="${PL}" x2="${W - PR}" y1="${yE(0)}" y2="${yE(0)}"/>`;
    s += `<g stroke="var(--ink-3,#5b626b)" stroke-dasharray="2 3"><line x1="${PL}" x2="${W - PR}" y1="${yE(o.errTol)}" y2="${yE(o.errTol)}"/><line x1="${PL}" x2="${W - PR}" y1="${yE(-o.errTol)}" y2="${yE(-o.errTol)}"/></g>`;
    rows.forEach((r, i) => {
      const e = Math.max(-o.eMax, Math.min(o.eMax, o.err(r))), bad = !o.ok(r) && !r.fit, x0 = X(i) - step * 0.3;
      const ya = yE(0), yb = yE(e);
      s += `<rect class="${bad ? 'bt-barbad' : 'bt-bar'}" x="${x0}" y="${Math.min(ya, yb)}" width="${step * 0.6}" height="${Math.max(0.8, Math.abs(yb - ya))}"><title>${esc(r.q)}: ошибка модели ${esc(sg(o.err(r), o.errD))} ${esc(o.errSfx)}${bad ? ' — вне допуска' : ''}</title></rect>`;
      if (bad) s += `<text class="bt-lbl" x="${X(i)}" y="${e >= 0 ? yb - 3 : yb + 11}" text-anchor="middle">${esc(sg(o.err(r), 1))}</text>`;
      if (o.errConst) s += `<line class="bt-ctick" x1="${X(i) - step * 0.34}" x2="${X(i) + step * 0.34}" y1="${yE(Math.max(-o.eMax, Math.min(o.eMax, o.errConst(r))))}" y2="${yE(Math.max(-o.eMax, Math.min(o.eMax, o.errConst(r))))}"><title>${esc(r.q)}: ошибка константы 87,2 % = ${esc(sg(o.errConst(r), o.errD))} п.п.</title></line>`;
    });
    /* quarter digits and years */
    rows.forEach((r, i) => { s += `<text class="bt-s" x="${X(i)}" y="${top + H1 + gap + H2 + 12}" text-anchor="middle">${esc(r.q.slice(5))}</text>`; });
    let ys = 0;
    while (ys < n) {
      const yr = rows[ys].q.slice(0, 4); let ye = ys; while (ye + 1 < n && rows[ye + 1].q.slice(0, 4) === yr) ye++;
      s += `<text x="${PL + (ys + ye + 1) * step / 2}" y="${top + H1 + gap + H2 + 26}" text-anchor="middle">${esc(yr)}</text>`;
      ys = ye + 1;
    }
    return s + '</svg>';
  }

  function summaryTable(d) {
    const S = d.summary || {}, rows = d.rows || [];
    const RM = { 1: 'I', 2: 'II', 3: 'III', 4: 'IV' }, qr = q => `${RM[q[5]]} кв. ${q.slice(0, 4)}`;
    const span = pred => { const q = rows.filter(pred).map(r => r.q); return q.length ? `${qr(q[0])} – ${qr(q[q.length - 1])}` : ''; };
    const defs = [['two', 'Две фабрики', r => !r.fit && r.kind === 'two'], ['single', 'Одна фабрика', r => !r.fit && r.kind === 'single'],
      ['ramp', 'Разгон линии 2', r => !r.fit && r.kind === 'ramp'], ['all', 'Все проверочные кварталы', r => !r.fit]]
      .filter(([k]) => S[k] && S[k].n);
    const line = ([k, name, pred]) => {
      const s = S[k];
      return `<tr><td class="l">${esc(name)}<br><span class="note">${esc(span(pred))}</span></td><td>${fmt(s.n)}</td>
<td>${esc(fmt(s.rec_mae_pp, 2))}</td><td>${esc(fmt(s.const_mae_pp, 2))}</td><td>${esc(fmt(s.rec_max_pp, 2))}</td><td>${esc(sg(s.rec_bias_pp, 2))}</td><td>${fmt(s.rec_ok)} из ${fmt(s.n)}</td>
<td class="bt-sep">${esc(fmt(s.cu_mae_pct, 2))} (${esc(fmt(s.cu_mae_kt, 2))} кт)</td><td>${esc(fmt(s.cu_const_mae_pct, 2))}</td><td>${esc(fmt(s.cu_max_pct, 1))}</td><td>${fmt(s.cu_ok)} из ${fmt(s.n)}</td>
<td class="bt-sep">${esc(fmt(s.blind_cu_mae_pct, 1))}</td></tr>`;
    };
    return `<div class="bt-wrap"><table class="bt-t"><tr><th class="l" rowspan="2">Кварталы</th><th rowspan="2">n</th>
<th colspan="5">Извлечение, п.п. [оценка на модели против факта]</th><th class="bt-sep" colspan="4">Медь в концентрате, % ошибки [то же]</th><th class="bt-sep">Вслепую</th></tr>
<tr><th>среднее по модулю</th><th>то же у константы 87,2 %</th><th>наибольшая</th><th>смещение</th><th>в допуске ±0,5</th>
<th class="bt-sep">среднее по модулю</th><th>то же у константы</th><th>наибольшая</th><th>в допуске</th><th class="bt-sep">Cu, среднее по модулю, %</th></tr>
${defs.map(line).join('')}</table></div>`;
  }

  function detailTable(d) {
    const rows = d.rows || [];
    const head = `<tr><th class="l">Квартал</th><th class="l">Фабрики</th><th>Руда, кт [факт]</th><th>Cu в питании, %</th>
<th class="bt-sep">Извлечение, %: отчёт</th><th>модель</th><th>ошибка, п.п.</th><th>константа 87,2 %, п.п.</th>
<th class="bt-sep">Cu, кт: отчёт</th><th>модель</th><th>ошибка, %</th><th>допуск, ±%</th><th class="bt-sep">Вслепую: Cu, %</th><th class="l bt-sep">Отчёт</th></tr>`;
    const body = rows.map(r => {
      const badR = !r.rec_ok && !r.fit, badC = !r.cu_ok && !r.fit;
      const mark = b => b ? '▲ ' : '';
      return `<tr${r.fit ? ' class="bt-fitrow"' : ''}><td>${esc(r.q.replace('Q', ' кв. '))}${r.fit ? ' (подгонка)' : ''}</td><td class="l">${esc(KIND_RU[r.kind] || r.kind)}</td><td>${fmt(r.ore_rep)}</td>
<td title="в модели ${esc(fmt(r.grade_mod, 3))} %">${esc(fmt(r.grade_rep, 2))}</td><td class="bt-sep">${esc(fmt(r.rec_rep, 1))}</td><td>${esc(fmt(r.rec_mod, 2))}</td>
<td class="${badR ? 'bt-bad' : ''}">${mark(badR)}${esc(sg(r.rec_err, 2))}</td><td>${esc(sg(r.const_err, 2))}</td>
<td class="bt-sep">${esc(fmt(r.cu_rep, 1))}</td><td>${esc(fmt(r.cu_mod, 2))}</td><td class="${badC ? 'bt-bad' : ''}">${mark(badC)}${esc(sg(r.cu_err_pct, 1))}</td><td>${esc(fmt(r.tol_cu_pct, 1))}</td>
<td class="bt-sep" title="тот же квартал при готовности, подогнанной на 2025 г., без руды из отчёта; руда: ${esc(sg(r.blind_ore_pct, 1))} %">${esc(sg(r.blind_cu_pct, 1))}</td>
<td class="l bt-sep">${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener" title="${esc(r.page || '')}">PDF ${esc(shortPage(r.page))}</a>` : '—'}</td></tr>`;
    }).join('');
    return `<div class="bt-wrap"><table class="bt-t">${head}${body}</table></div>`;
  }

  function lead(d) {
    const S = d.summary || {}, all = S.all || {}, two = S.two || {}, fit = d.fit_year || 2025;
    const parts = [`Модель подогнана только на ${fit} г. Остальные ${fmt(all.n)} кварталов — проверка без подгонки по квартальным отчётам KAZ Minerals [факт]: из отчёта берутся руда и содержание меди, извлечение и медь модель не видит.`];
    if (two.n) {
      const same = Math.abs(two.rec_mae_pp - two.const_mae_pp) < 0.15;
      parts.push(`Там, где работали обе фабрики (${fmt(two.n)} кв.), ошибка извлечения в среднем по модулю ${fmt(two.rec_mae_pp, 2)} п.п. против ${fmt(two.const_mae_pp, 2)} п.п. у константы 87,2 %${same ? ' — на уровне константы: пользы формулы извлечения по содержанию эти кварталы не показывают' : ''}; в допуске ±${fmt((d.tolerances || {}).rec_pp != null ? d.tolerances.rec_pp : 0.5, 1)} п.п. — ${fmt(two.rec_ok)} из ${fmt(two.n)}. Медь в концентрате — ${fmt(two.cu_mae_pct, 2)} % ошибки в среднем, ${fmt(two.cu_ok)} из ${fmt(two.n)} в допуске [оценка на модели].`);
    }
    const y24 = (d.rows || []).filter(r => r.q.startsWith('2024'));
    if (y24.length && y24.every(r => r.rec_err < 0)) parts.push(`Во всех ${fmt(y24.length)} кварталах 2024 г. извлечение модели ниже отчётного (${sg(Math.max(...y24.map(r => r.rec_err)), 2)}…${sg(Math.min(...y24.map(r => r.rec_err)), 2)} п.п.): это тот же промах, что в годовой проверке 2024 г., он не скрыт.`);
    const sg1 = S.single || {};
    if (sg1.n && sg1.rec_mae_pp > sg1.const_mae_pp) parts.push(`До октября 2021 г. (одна фабрика, ${fmt(sg1.n)} кв.) модель завышает извлечение на ${fmt(sg1.rec_bias_pp, 1)} п.п. и ошибается больше, чем константа (${fmt(sg1.rec_mae_pp, 2)} против ${fmt(sg1.const_mae_pp, 2)} п.п.).`);
    if (all.corr_grade_rec_rep != null && all.corr_grade_rec_mod != null) parts.push(`Связь извлечения с содержанием меди (корреляция по ${fmt(all.n)} кварталам): в отчётах ${sg(all.corr_grade_rec_rep, 2)}, у модели ${sg(all.corr_grade_rec_mod, 2)} — модель почти целиком следует за содержанием (наклон взят у аналога [аналог]), отчёты Актогая этого не показывают.`);
    return parts.map(p => `<p class="lead">${esc(p)}</p>`).join('');
  }

  A.backtest = {
    render(d) {
      if (!d || !Array.isArray(d.rows) || !d.rows.length) return '<p class="empty dash">Проверка по кварталам ещё не записана: расчёт калибровки не запускался или не закончил.</p>';
      const rows = d.rows, tol = d.tolerances || {};
      const recTol = tol.rec_pp != null ? tol.rec_pp : 0.5, constRec = tol.const_rec_pct != null ? tol.const_rec_pct : 87.2;
      const cuMax = Math.max(...rows.map(r => Math.max(r.cu_rep, r.cu_mod)));
      const cuHi = Math.ceil(cuMax / 10) * 10;
      const recVals = rows.flatMap(r => [r.rec_rep, r.rec_mod]);
      const recLo = Math.floor(Math.min(...recVals, constRec) - 0.5), recHi = Math.ceil(Math.max(...recVals, constRec) + 0.5);
      const cuChart = chart({
        id: 'cu', rows, aria: 'Медь в концентрате по кварталам: отчёт и модель, и ошибка модели в процентах', unit: 'Cu в концентрате, кт', errUnit: 'ошибка, %', errSfx: '%',
        lo: 0, hi: cuHi, tick: cuHi > 60 ? 20 : 10, tickD: 0, valD: 1, rep: r => r.cu_rep, mod: r => r.cu_mod, tol: r => r.cu_rep * r.tol_cu_pct / 100,
        err: r => r.cu_err_pct, errD: 1, ok: r => r.cu_ok, eMax: 8, eTicks: [-8, -4, 0, 4, 8], errTol: 3,
        bandTitle: 'Допуск по меди: 2 % [допущение] плюс полоса округления содержания в отчёте (±0,005 % Cu)', constLine: null,
      });
      /* the lower panel of copper shows the tolerance of the typical quarter (2 % + rounding about 1 %) as the dotted lines */
      const recChart = chart({
        id: 'rec', rows, aria: 'Извлечение по кварталам: отчёт, модель и константа 87,2 %, и ошибки в процентных пунктах', unit: 'извлечение, %', errUnit: 'ошибка, п.п.', errSfx: 'п.п.',
        lo: recLo, hi: recHi, tick: 2, tickD: 0, valD: 1, rep: r => r.rec_rep, mod: r => r.rec_mod, tol: () => recTol,
        err: r => r.rec_err, errD: 2, ok: r => r.rec_ok, eMax: 4, eTicks: [-4, -2, 0, 2, 4], errTol: recTol, errConst: r => r.const_err,
        bandTitle: `Допуск по извлечению: ±${fmt(recTol, 1)} п.п. [допущение]`, constLine: constRec, constTitle: `константа ${fmt(constRec, 1)} % (извлечение 2025 г.)`,
      });
      const notes = Array.isArray(d.notes) ? d.notes : [];
      return `${CSS}${lead(d)}
<h4 style="margin:10px 0 2px">Медь в концентрате по кварталам, кт</h4>
<div class="bt-wrap">${cuChart}</div>
<p class="bt-leg"><b>●</b> отчёт [факт] · <b>□</b> модель [оценка на модели] · серая полоса — допуск · <b style="color:var(--p1-ink,#a61b1b)">◆ красный ромб и красный столбик с числом</b> — вне допуска · штриховка — год подгонки (в счёт не входит). Нижняя панель: ошибка модели в %, пунктир — допуск 3 % (2 % + округление содержания ≈ 1 %).</p>
<h4 style="margin:10px 0 2px">Извлечение по кварталам, %</h4>
<div class="bt-wrap">${recChart}</div>
<p class="bt-leg"><b>●</b> отчёт [факт] · <b>□</b> модель [оценка на модели] · <b>- - -</b> константа ${esc(fmt(constRec, 1))} % · серая полоса и пунктир — допуск ±${esc(fmt(recTol, 1))} п.п. · <b style="color:var(--p1-ink,#a61b1b)">◆ красный</b> — вне допуска · <b>▬</b> чёрная черта в нижней панели — ошибка константы: модель полезна там, где её столбик короче черты.</p>
${summaryTable(d)}
<details open><summary>Таблица по кварталам: отчёт, модель, ошибки, ссылки на отчёты</summary>${detailTable(d)}</details>
<details><summary>Как считали и что это значит</summary><ul class="note">${notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>
<p class="note">Шаг ${esc(fmt(d.dt_min))} мин модели, seed ${esc(d.seed)}, подогнано: готовность ${esc(fmt((d.fit || {}).cal_avail, 4))}, K SAG ${esc(fmt((d.fit || {}).sag_k, 4))}, предельное извлечение ${esc(fmt((d.fit || {}).flot_rinf0_pct, 2))} %. Пересчёт: <code>${esc(d.command || 'python -I aktogay/run.py backtest')}</code>; данные: <code>aktogay/sim/data/kaz_quarterly.csv</code>.</p></details>`;
    },
  };
})();
