/* «Окисленная цепочка: расчёт против отчётов» на странице «Калибровка»: кинетика кучи подогнана на катоде кварталов 2018–2025 гг.,
   1 пол. 2026 г. — проверка вперёд; жёсткая проверка — подгонка до 2024 г. и прогноз 2025 – 1 пол. 2026 гг.
   Данные: /backtest_ox.json (sim/oxide.py, `python -I aktogay/run.py oxide --write aktogay/web/static/backtest_ox.json`), только файл, без запросов к Ditto.
   Модель — [расчёт кучи]; отчёт — [факт]. Цвет только у значений вне ±20 %, всегда с подписью числа. */
'use strict';
(function () {
  const A = window.AKT || (window.AKT = {});
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v, d = 1) => (v == null || !isFinite(v)) ? '—' : new Intl.NumberFormat('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
  const sg = v => v == null || !isFinite(v) ? '—' : `${v > 0.05 ? '+' : v < -0.05 ? '−' : ''}${fmt(Math.abs(v), 1)}`;
  const O = A.oxbt = { data: null };

  O.load = function (cb) {
    if (O.data || O.loading) return;
    O.loading = true;
    fetch('/backtest_ox.json', { cache: 'no-store' }).then(r => r.json()).catch(() => null).then(d => { O.data = d; O.loading = false; O.done = true; if (cb) cb(); });
  };

  const stat = (t, s) => s && s.n ? `<tr><td>${esc(t)}</td><td class="n">${s.n}</td><td class="n">${fmt(s.mape_pct)} %</td><td class="n">${sg(s.bias_pct)} %</td><td class="n">${fmt(s.rmse_pct)} %</td><td class="n">${sg(s.worst_pct)} %</td></tr>` : '';

  function chart(rows) {
    const W = 860, H = 230, L = 38, R = 8, T = 14, B = 34, n = rows.length;
    const ymax = Math.ceil(Math.max(...rows.map(r => Math.max(r.report_kt, r.model_kt))) + 0.5);
    const x = i => L + (W - L - R) * (i + 0.5) / n, y = v => T + (H - T - B) * (1 - v / ymax);
    let g = '';
    for (let v = 0; v <= ymax; v += 2) g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="currentColor" opacity=".15"/><text x="${L - 4}" y="${y(v) + 4}" text-anchor="end" font-size="10" fill="currentColor">${v}</text>`;
    const fwd = rows.findIndex(r => r.period === 'forward');
    if (fwd >= 0) g += `<rect x="${x(fwd) - (W - L - R) / n / 2}" y="${T}" width="${W - R - (x(fwd) - (W - L - R) / n / 2)}" height="${H - T - B}" fill="currentColor" opacity=".08"/><text x="${W - R - 4}" y="${T + 10}" text-anchor="end" font-size="10" fill="currentColor">проверка вперёд</text>`;
    rows.forEach((r, i) => {
      if (r.quarter.endsWith('Q1')) g += `<text x="${x(i)}" y="${H - 18}" text-anchor="middle" font-size="10" fill="currentColor">${r.quarter.slice(0, 4)}</text>`;
    });
    g += `<polyline fill="none" stroke="currentColor" stroke-width="1.6" points="${rows.map((r, i) => x(i) + ',' + y(r.report_kt)).join(' ')}"/>`;
    g += `<polyline fill="none" stroke="currentColor" stroke-width="1.4" stroke-dasharray="5 3" opacity=".75" points="${rows.map((r, i) => x(i) + ',' + y(r.model_kt)).join(' ')}"/>`;
    rows.forEach((r, i) => {
      g += `<circle cx="${x(i)}" cy="${y(r.report_kt)}" r="3" fill="currentColor"><title>${esc(r.quarter)}: отчёт ${fmt(r.report_kt)} кт, расчёт ${fmt(r.model_kt)} кт (${sg(r.err_pct)} %); руда на кучи ${fmt(r.ore_kt, 0)} кт, ${fmt(r.grade_pct, 2)} % Cu</title></circle>`;
      if (Math.abs(r.err_pct) > 20) g += `<path d="M${x(i)} ${y(r.model_kt) - 7} l5 5 l-5 5 l-5 -5 z" fill="var(--p1,#c62828)"><title>${esc(r.quarter)}: ошибка ${sg(r.err_pct)} %</title></path>`;
    });
    return `<svg class="bt-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Катод по кварталам 2018–2026: отчёты KAZ Minerals (сплошная линия) и расчёт кучи (пунктир), кт"><text x="${L}" y="9" font-size="11" fill="currentColor">кт катода за квартал</text>${g}</svg>`;
  }

  O.render = function () {
    const d = O.data;
    if (!d) return `<p class="empty dash">${O.loading || !O.done ? 'Загружаю итог проверки…' : 'Итог проверки окисленной цепочки недоступен: файл backtest_ox.json не открылся.'}</p>`;
    const s = d.strict || {};
    const ann = Object.entries(d.annual || {}).map(([y, a]) => `<tr><td>${esc(y)}</td><td class="n">${fmt(a.report_kt)}</td><td class="n">${fmt(a.model_kt)}</td><td class="n">${sg(a.err_pct)} %</td></tr>`).join('');
    return `<p class="bt-leg">Кинетика кучи (доля выщелачиваемой меди, постоянная времени, кажущаяся энергия активации, медь в куче до 2018 г.) подогнана на катоде <b>32 кварталов 2018–2025 гг.</b> по руде и содержанию из тех же отчётов и температуре воздуха ERA5; <b>1 и 2 кв. 2026 г. — проверка вперёд</b>. Сплошная линия — отчёты [факт], пунктир — расчёт кучи [расчёт].</p>
<div class="bt-wrap">${chart(d.rows)}</div>
<table class="kv"><tr><th>Проверка</th><th>Кварталов</th><th>Средняя ошибка</th><th>Смещение</th><th>СКО</th><th>Худший квартал</th></tr>
${stat('подгонка 2018–2025', d.fit)}${stat('вперёд: 1 пол. 2026 г.', d.forward)}${stat('вперёд, эталон «среднее по подгонке»', d.baseline_constant_forward)}${stat('вперёд, эталон «прошлый квартал»', d.baseline_previous_quarter_forward)}
${stat('жёстко: подгонка до 2024 г., 2018–2024', s.fit)}${stat('жёстко: вперёд 2025 – 1 пол. 2026 г.', s.forward)}${stat('жёстко: эталон «прошлый квартал»', s.baseline_previous_quarter_forward)}</table>
<h4>Годовые итоги: отчёт и расчёт, кт</h4><table class="kv"><tr><th>Год</th><th>Отчёт</th><th>Расчёт</th><th>Ошибка</th></tr>${ann}</table>
<p class="note">Корреляция расчёта с отчётами по 34 кварталам ${fmt(d.r_all, 2)}. Подгонка по кварталу — от температуры воздуха (сезон) и от руды на кучи; в жёсткой проверке (подгонка до 2024 г.) хвост выщелачивания 2025–2026 гг. ниже отчёта — расчёт хуже эталона «прошлый квартал», но лучше эталона «среднее». Модель — не прогноз для фабрики: потоки раствора, ёмкости прудов и ванны электролиза — допущения или аналоги (ОВОС: рафинат 1 500 м³/ч, катод до 25 тыс. т в год).</p>`;
  };
})();
