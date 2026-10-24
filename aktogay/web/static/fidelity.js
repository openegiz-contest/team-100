/* «Калибровка»: правдоподобие по прогонам модели и «от чего зависят выводы».
   Данные — fidelity.json (sim/fidelity.py: доступность агрегатов, реальные остановки SAG по отчётам, прогноз вперёд на 2026 год,
   переподгонка извлечения, разброс руды) и influence.json (sim/influence.py: какие числа модели вообще способны изменить
   вывод опыта). Файлы лежат рядом со страницами, как params_summary.json; живые значения читает plausibility.js из Ditto.
   Всё, что дала модель, — [оценка на модели]; «отчёт» — [факт] KAZ Minerals (ссылка и страница в строке). */
'use strict';
(function () {
  const A = window.AKT || (window.AKT = {});
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v, d = 0) => (v == null || !isFinite(v)) ? '—'
    : new Intl.NumberFormat('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
  const sg = (v, d = 1) => v == null || !isFinite(v) ? '—' : `${v > 0.0005 ? '+' : v < -0.0005 ? '−' : ''}${fmt(Math.abs(v), d)}`;
  const mark = ok => ok ? '<b class="ok">✓ в допуске</b>' : '<b class="bad">✗ вне допуска</b>';
  /* the verdict cell of an availability row: only flotation is a check; grinding is a fit; the crusher row is a requirement of the reported ore */
  const verdict = u => u.class === 'requirement' ? '<b>требование к оборудованию</b><br><span class="p-sub">вердикта допуска нет: паспорта дробилки в источниках нет</span>'
    : u.class === 'fit' ? '<b>подгонка</b><br><span class="p-sub">следует из готовности линии, подогнанной на руду 2025 г.</span>' : mark(u.ok);
  const F = A.fidelity = { data: null, infl: null };

  F.load = function (cb) {
    if (F.data || F.loading) return;
    F.loading = true;
    Promise.all([
      fetch('/fidelity.json', { cache: 'no-store' }).then(r => r.json()).catch(() => null),
      fetch('/influence.json', { cache: 'no-store' }).then(r => r.json()).catch(() => null),
    ]).then(([d, i]) => { F.data = d; F.infl = i; F.loading = false; if (cb) cb(); });
  };

  const UNIT_RU = { crusher: 'Дробилка (ЦПД)', grinding: 'Измельчение (SAG и шаровые)', flotation: 'Флотация' };

  function availability(a) {
    if (!a) return '';
    const rows = Object.entries(a.units).map(([k, u]) => `<tr><td>${esc(UNIT_RU[k] || k)}</td><td class="n">${u.run_pct_range ? `${fmt(u.run_pct_range[0], 1)}–${fmt(u.run_pct_range[1], 1)}` : fmt(u.run_pct, 1)} %${u.run_pct_range ? '<br><span class="p-sub">часы работы при 5 044 и 4 386 т/ч</span>' : ''}</td>
<td class="n">${fmt(u.avail_pct, 1)} %</td><td class="n">${u.class === 'requirement' && u.design_hours_pct != null ? `проект ОВОС: ${fmt(u.design_hours_pct, 1)} % часов<br><span class="p-sub">литература Ausenco: ` : ''}${fmt(u.lit_lo, 0)}–${fmt(u.lit_hi, 0)} %${u.class === 'requirement' && u.design_hours_pct != null ? '</span>' : ''}</td><td class="n">${u.delta_pp == null ? '—' : sg(u.delta_pp)}</td><td>${verdict(u)}</td></tr>`).join('');
    return `<h4>Доступность агрегатов против литературы (годовой прогон ${a.year})</h4>
<table class="kv"><tr><th>Агрегат</th><th>Модель: в работе</th><th>Модель: не стоит</th><th>Проект и литература</th><th>Разница, п.п.</th><th>Итог</th></tr>${rows}</table>
<p class="note">${esc(a.source)}. ${esc(a.note)}</p>`;
  }

  function relines(r) {
    if (!r) return '';
    const rows = r.events.map(e => `<tr><td><a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.id)}</a> <span class="note">${esc(e.page)}</span></td>
<td>${esc(e.what)}</td><td class="n">${sg(e.obs_drop_pct)} %${e.obs_drop_per_day_pct != null ? `<br><span class="p-sub">на сутки ${sg(e.obs_drop_per_day_pct)} %</span>` : ''}</td><td class="n">${sg(e.pred_drop_pct)} %</td><td class="n">${sg(e.diff_pp)}${e.diff_per_day_pp != null ? `<br><span class="p-sub">к суткам ${sg(e.diff_per_day_pp)}</span>` : ''}</td>
<td class="n">${sg(e.err_with_pct)} % / ${sg(e.err_without_pct)} %</td></tr>`).join('');
    const s = r.sensitivity_reline_h || {};
    const sens = Object.keys(s).sort().map(h => `${h} ч: ${sg(s[h].mean_pred_pct)} %`).join(', ');
    return `<h4>Реальные перефутеровки SAG: падение руды линии в квартале события</h4>
<table class="kv"><tr><th>Событие</th><th>Что сказано в отчёте</th><th>Отчёт: квартал к опорному</th><th>Модель: с остановкой к без неё</th><th>Разница, п.п.</th><th>Ошибка руды квартала: с остановкой / без</th></tr>${rows}
<tr><td><b>Среднее (${fmt(r.n)})</b></td><td></td><td class="n"><b>${sg(r.mean_obs_pct)} %</b>${r.mean_obs_per_day_pct != null ? `<br><span class="p-sub">на сутки ${sg(r.mean_obs_per_day_pct, 2)} %</span>` : ''}</td><td class="n"><b>${sg(r.mean_pred_pct)} %</b></td><td class="n"><b>${fmt(r.mae_drop_pp, 1)}</b> (среднее |разница|)</td>
<td class="n"><b>${fmt(r.mae_with_pct, 1)} % / ${fmt(r.mae_without_pct, 1)} %</b></td></tr></table>
<p class="note">${esc(r.note)} Остановка ${fmt(r.reline_h)} ч — допущение; при другой длине среднее падение модели: ${esc(sens)}; в отчётном падении — ${sg(r.mean_obs_pct)} %${r.mean_obs_per_day_pct != null ? `, на сутки ${sg(r.mean_obs_per_day_pct, 2)} %: модель глубже в ${fmt(r.n_model_deeper_per_day)} из ${fmt(r.n)} событий на ${fmt(Math.abs(r.mean_diff_per_day_pp), 2)} п.п. (разброс отчётов — раздел 6.3 VALIDATION.md: оценка по регрессии −4,2 % при интервале 6–8 п.п., 84 ч не подгоняем)` : ''}.
Учёт остановки улучшает оценку руды квартала в ${fmt(r.n_better_with)} из ${fmt(r.n)} событий: опорная готовность предыдущего квартала уже несёт свои остановки, поэтому надёжнее читать столбец «падение», чем ошибку руды.</p>`;
  }

  function forward(f) {
    if (!f) return '';
    const rows = f.quarters.map(q => `<tr><td><a href="${esc(q.url)}" target="_blank" rel="noopener">${esc(q.q)}</a> <span class="note">${esc(q.page)}</span></td>
<td class="n">${fmt(q.ore_rep)} / ${fmt(q.blind_ore)} <span class="note">(${sg(q.blind_ore_err_pct)} %)</span></td>
<td class="n">${fmt(q.persist_same_q_pct, 1)} % / ${fmt(q.persist_mean_pct, 1)} %</td>
<td class="n">${fmt(q.cu_rep, 1)} / ${fmt(q.cu_model, 1)} <span class="note">(${sg(q.cu_err_model_pct)} %)</span></td>
<td class="n">${fmt(q.cu_const, 1)} <span class="note">(${sg(q.cu_err_const_pct)} %)</span></td>
<td class="n">${fmt(q.rec_implied, 1)} ± ${fmt(q.rec_implied_pm, 1)} / ${fmt(q.rec_model, 1)}</td></tr>`).join('');
    return `<h4>Прогноз вперёд: данные 2026 года, которых модель не видела</h4>
<table class="kv"><tr><th>Квартал</th><th>Руда, тыс. т: отчёт / модель вслепую (готовность 2025)</th><th>Ошибка «как в тот же квартал 2025» / «как среднее 2025»</th>
<th>Медь в конц., тыс. т: отчёт / модель (руда из отчёта)</th><th>Константа 87,2 %</th><th>Извлечение, %: из отчёта / модель</th></tr>${rows}</table>
<p class="note">${esc(f.note)}</p>`;
  }

  function recovery(r) {
    if (!r) return '';
    const rows = r.variants.map(v => `<tr><td>${esc(v.train === 'single' ? '2018 – III кв. 2021 (одна фабрика)' : '2018–2022 (с разгоном второй фабрики)')} <span class="note">(${fmt(v.n_train)} кв.)</span></td>
<td class="n">${fmt(v.slope_analog, 2)} → ${fmt(v.slope_refit, 2)}</td><td class="n">${sg(v.d_level_pp, 2)}</td><td class="n"><b>${fmt(v.mae_refit, 2)}</b></td><td class="n">${fmt(v.mae_const_train_mean, 2)}</td></tr>`).join('');
    return `<h4>Извлечение: переподгонка на ранних кварталах и проверка на 2023–2025 гг. (${fmt(r.n_test)} кв.)</h4>
<table class="kv"><tr><th>Данные подгонки</th><th>Наклон по ln содержания, п.п.: аналог → подгонка</th><th>Сдвиг уровня, п.п.</th><th>Ошибка после переподгонки, п.п.</th><th>Константа = среднее подгонки, п.п.</th></tr>${rows}
<tr><td><b>Модель, подогнанная на 2025 г.</b></td><td class="n">${fmt(r.variants[0].slope_analog, 2)}</td><td class="n">—</td><td class="n"><b>${fmt(r.mae_model_2025fit, 2)}</b></td><td class="n">константа 87,2 %: ${fmt(r.mae_const_2025, 2)}</td></tr></table>
<p class="note">Две честные цифры. 2023–2024 гг. (${fmt(r.n_test_2023_24)} кв., для подгонки на 2025 г. это настоящий прогноз): модель ${fmt(r.mae_model_2023_24, 2)} п.п., константа ${fmt(r.mae_const_2023_24, 2)} п.п., модель лучше в ${fmt(r.wins_model_2023_24)} из ${fmt(r.n_test_2023_24)} — преимущество в пределах шума.
Все 28 кварталов: модель ${fmt(r.mae_model_all28, 2)} п.п., константа ${fmt(r.mae_const_all28, 2)} п.п. — хуже, потому что до 2023 г. извлечение было другим. Переподгонка по ранним кварталам хуже вдвое: наклон по содержанию в отчётах не устойчив (до 2022 г. содержание и извлечение шли вместе, после — нет).
Оставлена модель, подогнанная на 2025 г.; формула извлечения служит для сценариев (помол, реагент, окисленная руда), а не для прогноза квартала лучше константы.</p>`;
  }

  function spread(s) {
    if (!s) return '';
    return `<h4>Разброс руды от квартала к кварталу (28 проверочных кварталов)</h4>
<table class="kv"><tr><th>Величина</th><th>Отчёты</th><th>Модель без плана горных работ</th><th>Модель с планом (${fmt(s.reported_n)} разностей)</th></tr>
<tr><td>СКО квартального изменения ln содержания Cu</td><td class="n">${fmt(100 * s.reported_sd_dln, 1)} %</td><td class="n">${fmt(100 * s.model_off_sd_dln, 1)} %</td><td class="n"><b>${fmt(100 * s.model_on_sd_dln, 1)} %</b></td></tr>
<tr><td>СКО извлечения между кварталами (уровень), п.п.</td><td class="n">${fmt(s.reported_rec_sd_pp, 2)}</td><td class="n">${fmt(s.model_off_rec_sd_pp, 2)}</td><td class="n"><b>${fmt(s.model_on_rec_sd_pp, 2)}</b></td></tr></table>
<p class="note">План горных работ: медленные изменения содержания, твёрдости и кислоторастворимой меди от участка к участку (<code>blk_plan_*</code>); включён в проверках разброса и выключен в парных сменах и в квартальной проверке, где он только прибавил бы шум. Сигма по меди подобрана под отчётный разброс содержания (расчёт), сигма кислоторастворимой меди — допущение, подобранное под разброс извлечения. ${esc(s.rec_note || '')}</p>`;
  }

  function influence(i) {
    if (!i) return '<p class="empty dash">Итог классификации (influence.json) не загружен.</p>';
    const s = i.summary;
    const NAME = { assumption: 'допущение', fact: 'факт', vendor: 'вендор', analog: 'аналог', project: 'проект', calc: 'расчёт' };
    const read = (s.matters || 0) + (s.read_small || 0) + (s.read || 0) + (s.read_fixed || 0);
    const top = (i.top || []).slice(0, 15).map(x => `<tr><td><code>${esc(x.key)}</code></td><td>${esc(NAME[x.label] || x.label)}</td><td class="n">${fmt(x.dev, 2)}</td>${x.dev_refit != null ? `<td class="n">${fmt(x.dev_refit, 2)}</td>` : '<td class="n">—</td>'}</tr>`).join('');
    const byLabel = ['assumption', 'fact', 'vendor', 'analog', 'project', 'calc'].map(k => `<tr><td>${esc(NAME[k])}</td><td class="n">${fmt(s[k].n)}</td><td class="n"><b>${fmt(s[k].matters)}</b></td><td class="n">${fmt(s[k].read_small)}</td><td class="n">${fmt(s[k].read_fixed || 0)}</td><td class="n">${fmt(s[k].read)}</td><td class="n">${fmt(s[k].not_read)}</td></tr>`).join('');
    const fam = i.recovery_family ? Object.entries(i.recovery_family).filter(([, r]) => r).map(([k, r]) => {
      const e = (r.edges || []).map(x => `${fmt(x.value, 2)}: ${sg(x.gain, 2)}`).join(' / ');
      const f = (r.refit_edges || []).map(x => `${fmt(x.value, 2)} (R∞ ${fmt(x.rinf0, 1)} %): ${sg(x.gain, 2)}`).join(' / ');
      return `<tr><td><code>${esc(k)}</code></td><td>${esc(e)}</td><td>${esc(f)}</td><td class="n">${fmt(r.dev, 2)}</td><td class="n"><b>${fmt(r.dev_refit, 2)}</b></td></tr>`;
    }).join('') : '';
    const m = i.mechanism;
    const mech = m ? `<details><summary>Почему края строк извлечения убивают выигрыш: хвосты базы против уставки тревоги АСУ</summary><table class="kv"><tr><th>Строка</th><th>Хвосты базы, % Cu</th><th>Выигрыш у края</th><th>Уставка сдвинута на запас базы</th><th>Выигрыш</th></tr>${m.rows.map(r => `<tr><td><code>${esc(r.name)}</code></td><td class="n">${fmt(r.tails_pct, 3)}</td><td class="n">${sg(r.gain, 2)}</td><td class="n">${r.shifted_sp != null ? fmt(r.shifted_sp, 3) + ' %' : `уставка ${fmt(m.set_point_pct, 3)} %`}</td><td class="n">${r.gain_shifted_sp != null ? sg(r.gain_shifted_sp, 2) : '—'}</td></tr>`).join('')}</table>
<p class="note">Дальние края строк извлечения поднимают хвосты базы к уставке тревоги АСУ (${fmt(m.set_point_pct, 3)} % Cu): тогда «как сейчас» ловит дрейфы по тревоге хвостов, и выигрыш двойника исчезает. Если пересчитать предельное извлечение так, чтобы база осталась 87,2 % (как в отчёте), или сдвинуть уставку на запас базы, выигрыш возвращается. С отчётом совместимы значения ASCu не выше ${fmt(m.compatible_with_the_report.blk_ascu_mean_pct, 1)} % и кинетика не ниже ${fmt(m.compatible_with_the_report.flot_ktau0, 2)}: дальше пересчитанное предельное извлечение выходит за свой диапазон.</p></details>` : '';
    return `<p>Чисел в таблицах: <b>${fmt(s.total)}</b>, допущений среди них <b>${fmt(s.assumptions_total)}</b>. Опыт «вкл/выкл» с полной библиотекой бед (симметричная база) читает ${fmt(read)} чисел; остальные <b>${fmt(s.not_read)}</b> (оформление, другие сценарии, калибровка, служебные) вывод опыта не могут изменить вовсе.
Из прочитанных чисел модели с диапазоном ${fmt(s.screened != null ? s.screened : s.matters + s.read_small)} (всех меток, а не только допущения) сдвинуто к каждому краю диапазона: <b>${fmt(s.matters)}</b> меняют выигрыш двойника на ${fmt(i.threshold_t_cu, 2)} т Cu за смену и больше хотя бы у одного края, ${fmt(s.read_small)} не меняют; ${fmt(s.read_fixed || 0)} прочитанных чисел модели без диапазона сдвинуть нельзя (паспортные значения); ${fmt(s.read)} читаются в модулях (одиночно проверить нельзя).</p>
<table class="kv"><tr><th>Метка</th><th>Всего</th><th>Влияют на вывод</th><th>Читаются, вывод не меняют</th><th>Читаются без диапазона</th><th>Читаются (модули)</th><th>Не читаются опытом</th></tr>${byLabel}</table>
${fam ? `<h5>Строки извлечения: край диапазона и тот же край с пересчётом предельного извлечения (база 87,2 %)</h5><table class="kv"><tr><th>Строка</th><th>Выигрыш у краёв, т Cu за смену</th><th>С пересчётом предельного извлечения</th><th>Сдвиг без пересчёта</th><th>Сдвиг с пересчётом</th></tr>${fam}</table>` : ''}
${mech}
${top ? `<details><summary>Числа, сильнее всего сдвигающие вывод (по диапазону, т Cu за смену)</summary><table class="kv"><tr><th>Число</th><th>Метка</th><th>Сдвиг выигрыша</th><th>С пересчётом</th></tr>${top}</table></details>` : ''}
<p class="note">Метод: счётчик чтений обеих таблиц в ${fmt(i.reach_n)} сменах опыта со всеми копиями; затем каждое прочитанное число модели с диапазоном, любой метки, сдвигается к каждому краю своего диапазона, отличному от значения (по одному, ${fmt((i.screen_seeds || []).length || i.screen_n)} смен, в которых есть все 11 видов бед, те же зёрна). База: выигрыш ${sg(i.base_gain, 2)} т Cu за смену на этих сменах (симметричная база). Это грубая проверка на малой выборке: порог ${fmt(i.threshold_t_cu, 2)} т оставлен прежним (в первом скрининге он был десятой частью главного результата). Первый скрининг двигал только допущения и только дальний край; «факты и вендор не влияют» тогда не измерялось. Допущения, которые опыт задаёт сам (приём советов, время находки, лаборатория), измерены в «торнадо» выше.</p>`;
  }

  F.renderFidelity = function () {
    const d = F.data;
    if (!d) return '<p class="empty dash">Итоги прогонов (fidelity.json) не загружены.</p>';
    return `<p class="note">Прогоны модели на код ${esc(d.generated)}, зерно ${esc(d.seed)}; подгонка 2025 г.: готовность ${fmt(d.fit.cal_avail, 4)}, коэффициент SAG ${fmt(d.fit.sag_k, 4)}, предельное извлечение ${fmt(d.fit.flot_rinf0_pct, 2)} %.</p>
${availability(d.availability)}${relines(d.relines)}${forward(d.forward_2026)}${recovery(d.recovery)}${spread(d.spread)}`;
  };
  F.renderInfluence = function () { return influence(F.infl); };
})();
