/* Result of the on/off experiment of 24.10.2026 (VALIDATION.md 8.6-8.8) for the pages «Экономика» and «Калибровка».
   The data is exp23.json, which `python -I aktogay/run.py exp23 --write` builds from sim/data/experiment_23.json;
   the older files (trial_n100.json, the report of the calibration job) are not used here. Every number is a model estimate. */
'use strict';
(function () {
  const esc = AKT.esc, fmt = AKT.fmt;
  const sg = (v, d = 2) => (v > 0 ? '+' : v < 0 ? '−' : '') + fmt(Math.abs(v), d);
  const ci = (a, d = 2) => `[${sg(a[0], d)}; ${sg(a[1], d)}]`;
  const X = AKT.exp23 = {
    data: null, pending: null,
    /* loads exp23.json once; cb runs when the data is there (or never, if the file is missing) */
    load(cb) {
      if (X.data) { cb(X.data); return; }
      if (!X.pending) X.pending = fetch('/exp23.json', { cache: 'no-store' }).then(r => r.json()).then(j => { X.data = j; return j; }).catch(() => null);
      X.pending.then(j => { if (j) cb(j); });
    },
    /* the main comparison in the form the pages used for the old trial summary */
    twin() {
      const m = X.data && X.data.main; if (!m) return null;
      return { mean: m.cu.mean, ci95_mean_bca: m.cu.ci95, n: m.n, p_plus: m.share_better, p_minus: m.share_worse };
    },
    headline() {
      const m = X.data.main;
      return `+${fmt(m.cu.mean, 2)} т Cu за смену ${ci(m.cu.ci95)}`;
    },
    /* one line for answers and the lead: twin minus expert */
    sentence() {
      const j = X.data, m = j.main;
      return `Двойник даёт в среднем +${fmt(m.cu.mean, 2)} т Cu за смену против опытной смены без двойника (95 % ДИ ${ci(m.cu.ci95)}), ≈ $${fmt(m.usd.mean / 1000, 1)} тыс. за смену, простой короче на ${fmt(Math.abs(m.down_min.mean))} мин за смену, ${fmt(Math.abs(m.kwh_per_t_cu.mean))} кВт·ч на т Cu меньше; хуже в ${fmt(100 * m.share_worse)} % смен. Оценка на модели, ${fmt(m.n)} парных смен (опыт ${j.source.date}).`;
    },
    /* horizontal chart: mean and 95 % interval of the benefit for the base and every changed assumption */
    tornado() {
      const rows = X.data.tornado;
      const W = 760, PL = 10, PW = 330, LH = 30, top = 10, H = top + rows.length * LH + 34;
      let hi = 0; rows.forEach(r => { hi = Math.max(hi, r.ci95[1]); });
      hi = Math.min(Math.ceil(hi * 2) / 2, 3.5);
      const x = v => PL + PW * Math.max(0, Math.min(v, hi)) / hi;
      const ticks = []; for (let v = 0; v <= hi + 1e-9; v += 0.5) ticks.push(v);
      return `<svg class="ci-chart tornado" viewBox="0 0 ${W} ${H}" role="img" aria-label="Польза двойника при разных допущениях, т Cu за смену: среднее и 95-процентный интервал">
${ticks.map(v => `<line class="${v === 0 ? 'zero' : 'grid'}" x1="${x(v)}" x2="${x(v)}" y1="${top - 4}" y2="${top + rows.length * LH}"/><text x="${x(v)}" y="${top + rows.length * LH + 16}" text-anchor="middle">${fmt(v, 1)}</text>`).join('')}
<text x="${PL + PW / 2}" y="${H - 2}" text-anchor="middle">польза двойника, т Cu за смену</text>
${rows.map((r, i) => { const y = top + i * LH + LH / 2; return `<line class="ci" x1="${x(r.ci95[0])}" x2="${x(r.ci95[1])}" y1="${y}" y2="${y}"/><circle class="mean" cx="${x(r.mean)}" cy="${y}" r="4"/><text x="${PL + PW + 14}" y="${y + 4}">${esc(r.label)}: ${sg(r.mean)}${i ? ` (${sg(r.delta)})` : ''}</text>`; }).join('')}
</svg><p class="note">Точка — среднее по 100 парным сменам, линия — 95 % интервал (правая часть оси обрезана на ${fmt(hi, 1)} т). В скобках сдвиг от базы. Торнадо посчитан при цикле вызовов 5 мин, поэтому его база выше главного результата (цикл 1 мин). Польза не падает до нуля ни в одной строке; ошибка оценки модуля ×2 ничего не меняет, доля выполненных советов 50 % и время находки 150 мин — больше всего.</p>`;
    },
    /* table: the main contrasts and the replication */
    mainTable() {
      const j = X.data, m = j.main, r = j.replication;
      return `<table class="kv"><tr><th>Сравнение (100 смен, ${fmt(m.troubles_per_shift, 2)} беды за смену)</th><th>т Cu за смену [95 % ДИ]</th><th>Что ещё</th></tr>
<tr><td><b>двойник − опытный (главное)</b>, seed ${m.seeds[0]}–${m.seeds[1]}</td><td class="n"><b>${sg(m.cu.mean)} ${ci(m.cu.ci95)}</b></td><td>≈ ${esc(AKT.money(m.usd.mean))}; простой ${sg(m.down_min.mean, 1)} мин за смену ${ci(m.down_min.ci95, 1)}; ${sg(m.kwh_per_t_cu.mean, 0)} кВт·ч на т Cu; хуже в ${fmt(100 * m.share_worse)} % смен, лучше в ${fmt(100 * m.share_better)} %</td></tr>
<tr><td>повтор на новых seed ${r.seeds[0]}–${r.seeds[1]}</td><td class="n">${sg(r.cu.mean)} ${ci(r.cu.ci95)}</td><td>хуже в ${fmt(100 * r.share_worse)} % смен</td></tr>
${X.noviceRows()}</table>`;
    },
    /* the rows of the main table for the novice from data (VALIDATION 8.9, 8.10); the «one at a time» novice of 8.8 stays as a history row */
    noviceRows() {
      const j = X.data, n = j.novice, d = n && n.data;
      const old = `<tr><td>опытный − «новичок по одной» (8.8, история)</td><td class="n">${sg(n.v1_expert_minus_novice_cu.mean)} ${ci(n.v1_expert_minus_novice_cu.ci95)}</td><td>правило «по одной беде за раз» придумано нами, цена неопытности в нём ноль; заменено новичком по данным</td></tr>`;
      if (!d) return old;
      const P = d.pairs, rg = d.ranges || {};
      const row = (t, p, note) => `<tr><td>${t}</td><td class="n">${sg(p.cu.mean)} ${ci(p.cu.ci95)}</td><td>${note}</td></tr>`;
      const rep = rg.rep && rg.rep.pairs['expert-nov_r'], lo = rg.lo && rg.lo.pairs['expert-nov_r'], hi = rg.hi && rg.hi.pairs['expert-nov_r'];
      return `${row('<b>опытный − новичок по данным</b>', P['expert-nov_r'], `цена неопытности в модели; хуже опытного новичок в ${fmt(100 * P['expert-nov_r'].share_better)} % смен${rep ? `; повтор seed ${rg.rep.seeds[0]}–${rg.rep.seeds[1]}: ${sg(rep.cu.mean)} ${ci(rep.cu.ci95)}` : ''}${lo && hi ? `; границы параметров: ${sg(lo.cu.mean)} … ${sg(hi.cu.mean)}` : ''}`)}
${row('двойник − новичок по данным', P['twin-nov_r'], 'сколько двойник добавляет новичку')}
${row('новичок с двойником − опытный без двойника', P['nov_twin-expert'], 'до какого уровня двойник поднимает новичка')}
${old}`;
    },
    /* the section «Новичок и двойник» of the page «Экономика» */
    novice() {
      const j = X.data, d = j.novice && j.novice.data;
      if (!d) return '<p class="note">Новичок по данным не считался.</p>';
      const P = d.pairs, M = d.means_cu, pa = P['expert-nov_r'], lift = P['nov_twin-expert'];
      const lead = lift.cu.ci95[0] > 0.05 ? 'выше опытного без двойника' : lift.cu.ci95[0] >= -0.05 ? 'не хуже опытного без двойника' : 'ниже опытного без двойника';
      const rg = d.ranges || {};
      return `<table class="kv"><tr><th>Кто на смене</th><th class="n">т Cu за смену</th><th>Разность против опытного без двойника, т Cu [95 % ДИ]</th></tr>
<tr><td>новичок по данным, без двойника</td><td class="n">${fmt(M.nov_r, 2)}</td><td class="n">${sg(-pa.cu.mean)} ${ci([-pa.cu.ci95[1], -pa.cu.ci95[0]])}</td></tr>
<tr><td>опытный, без двойника</td><td class="n">${fmt(M.expert, 2)}</td><td class="n">—</td></tr>
<tr><td>двойник (его вызовы по очереди $)</td><td class="n">${fmt(M.twin, 2)}</td><td class="n">${sg(P['twin-expert'].cu.mean)} ${ci(P['twin-expert'].cu.ci95)}</td></tr>
<tr><td>новичок с двойником</td><td class="n">${fmt(M.nov_twin, 2)}</td><td class="n">${sg(lift.cu.mean)} ${ci(lift.cu.ci95)}</td></tr></table>
<p>Новичок, заданный числами открытых работ, теряет против опытного <b>${fmt(pa.cu.mean, 2)} т Cu за смену</b> ${ci(pa.cu.ci95)}; с двойником он ${lead}: ${sg(lift.cu.mean)} т ${ci(lift.cu.ci95)}. Из потери новичка около ${fmt(d.parts.seeing.mean, 2)} т даёт медленное обнаружение (время ×1,66), около ${fmt(d.parts.slips.mean, 2)} т — промахи диагноза и шагов; доверительные интервалы частей пересекаются.</p>
<p class="note">Повтор на seed ${rg.rep ? rg.rep.seeds[0] + '–' + rg.rep.seeds[1] : '—'}: ${rg.rep ? sg(rg.rep.pairs['expert-nov_r'].cu.mean) + ' ' + ci(rg.rep.pairs['expert-nov_r'].cu.ci95) : '—'}. Если взять все параметры новичка на нижней границе диапазона (без замедления и почти без промахов), цена неопытности ${rg.lo ? sg(rg.lo.pairs['expert-nov_r'].cu.mean) + ' ' + ci(rg.lo.pairs['expert-nov_r'].cu.ci95) + (rg.lo.pairs['expert-nov_r'].effect ? '' : ' — эффект не найден') : '—'}; на верхней границе — ${rg.hi ? sg(rg.hi.pairs['expert-nov_r'].cu.mean) + ' ' + ci(rg.hi.pairs['expert-nov_r'].cu.ci95) : '—'}. Числа новичка — [аналог]: время увидеть беду из лабораторного макета (arXiv 2509.06657), ошибки из симулятора АЭС (NRC SHEEP, 20 и 17 наблюдений диагноза) и множитель стресса THERP; число шагов и цена промаха — [допущение]. Это оценка на модели, не вывод о людях Актогая. Сравнение — <code>VALIDATION.md</code>, 8.9–8.10.</p>`;
    },
    /* the shifts where the twin is worse than the expert (VALIDATION 8.11) */
    worse() {
      const w = X.data.worse; if (!w || !w.main_full) return '';
      const m = w.main_full, r = w.rep_full;
      const seeds = a => a.rows.map(x => `${x.seed} (${sg(x.d_cu)} т)`).join(', ');
      return `<p><b>Смены, где двойник хуже опытного.</b> На seed ${X.data.main.seeds[0]}–${X.data.main.seeds[1]} таких ${fmt(m.n_worse)} из ${fmt(m.n)} (потеря не больше ${fmt(Math.abs(m.worst), 2)} т): ${seeds(m)}; во всех есть канатирование циклонов — оператор в модели видит его за 55 мин, двойник находит за 75 [допущение входа], то есть вызывает на 20 мин позже.${r ? ` На повторе seed ${X.data.replication.seeds[0]}–${X.data.replication.seeds[1]}: ${fmt(r.n_worse)} смен, худшая ${sg(r.worst)} т (seed ${r.rows[0].seed}, две беды одной бригады: бригада, уже отправленная к тихой потере, не переназначается на новую остановку дробилки).` : ''}</p>`;
    },
    /* energy, CO2 and the group fact (VALIDATION 4, 8.8) */
    co2() {
      const e = X.data.energy; if (!e) return '';
      return `<p><b>CO₂.</b> Коэффициент ${fmt(e.co2_t_per_mwh, 2)} т CO₂ на МВт·ч [расчёт: Scope 2 группы KAZ Minerals 2 308 тыс. т ÷ электроэнергия группы 13,06 ПДж, 2024]. Двойник снижает энергию на т Cu на ${fmt(Math.abs(e.d_kwh_per_t_cu.mean))} кВт·ч ${ci(e.d_kwh_per_t_cu.ci95, 0)}, то есть на ${fmt(Math.abs(e.d_co2_kg_per_t_cu.mean))} кг CO₂ на т Cu (${ci(e.d_co2_kg_per_t_cu.ci95, 0)}). Это интенсивность: смена с двойником выпускает больше меди на ту же энергию (энергия смены ${sg(e.d_mwh.mean, 1)} МВт·ч, выбросы ${sg(e.d_co2_t_shift_absolute.mean, 1)} т CO₂ за смену), при выпуске смены это эквивалент ≈ ${fmt(Math.abs(e.d_co2_t_shift_same_output.mean), 1)} т CO₂ за смену. Для масштаба: у группы 7,8 т CO₂-экв. на т Cu в 2024 г. [факт, отчёт KAZ Minerals по устойчивому развитию, с. 40]; модель даёт ${fmt(e.co2_t_per_t_cu.by_value, 1)} т CO₂ на т Cu только по электроэнергии (Scope 2 группы: 2 308 тыс. т ÷ 379,9 тыс. т Cu = 6,1 т) [оценка на модели].</p>`;
    },
    /* price of an hour of delay inside the card of an issue (kind of the module -> kind of the experiment) */
    delayFor(kind) {
      const j = X.data && X.data.delay; if (!j) return '';
      const k = j.issue_kinds[kind], r = k && j.by_kind[k];
      if (!r) return `<p class="note">Цена часа задержки вызова для этой беды в опыте не считалась; ориентир — «Час промедления» выше (расчёт модуля).</p>`;
      const body = r.below_threshold ? `час задержки вызова почти ничего не стоит: ${fmt(r.t_per_h, 2)} т Cu ${ci(r.ci95)} — ниже порога 0,05 т, эффекта нет`
        : `${fmt(r.t_per_h, 2)} т Cu за час задержки вызова ${ci(r.ci95)}, ≈ $${fmt(r.usd_per_h / 1000, 1)} тыс. (${esc(r.label)}, ${fmt(r.n)} смен)`;
      return `<p class="delay-h"><b>Цена часа задержки вызова по опыту:</b> ${body} [оценка на модели, среднее по сменам, где такая беда была; не прогноз на фабрике].</p>`;
    },
    detectOrder() {
      const d = X.data.detect_vs_order;
      const row = (c, t) => `<tr><td>${t}</td><td class="n">${sg(d[c].detection.mean)} ${ci(d[c].detection.ci95)}</td><td class="n">${sg(d[c].order.mean)} ${ci(d[c].order.ci95)}</td></tr>`;
      return `<table class="kv"><tr><th>Бригад на смене</th><th>раннее обнаружение, т Cu</th><th>порядок вызова «по $», т Cu</th></tr>${row('1', '1 бригада')}${row('2', '2 бригады')}</table>
<p class="note">Обнаружение даёт около +1,0 т; порядок — +0,23 при одной бригаде и +0,06 при двух: свободные бригады порядок почти обесценивают.</p>`;
    },
    delay() {
      const j = X.data.delay;
      return `<p>Час задержки вызова бригады стоит в среднем <b>${fmt(j.slope_t_per_h.mean, 2)} т Cu</b> ${ci(j.slope_t_per_h.ci95)} ≈ <b>$${fmt(j.slope_usd_per_h.mean / 1000)} тыс.</b> на смену с 2–3 бедами. Руда беднеет — опоздание стоит дороже.</p>
<table class="kv"><tr><th>Вид беды (час задержки)</th>${j.by_kind_t_per_h.map(k => `<th class="n">${esc(k.label)}</th>`).join('')}</tr><tr><td>т Cu за час</td>${j.by_kind_t_per_h.map(k => `<td class="n">${fmt(k.mean, 2)}</td>`).join('')}</tr></table>
<p class="note">Дорого дело там, где стоит дробилка или срабатывает защита; для твёрдой руды, циклона и перефутеровки час задержки почти ничего не стоит. Лаборатория: задержка результата пробы влияет мало и перестаёт влиять после 12 ч.</p>`;
    },
  };
})();
