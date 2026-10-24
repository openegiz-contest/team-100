/* Page «Повтор смены»: one shift of the on/off trial with the twin and without it, two timelines side by side
   (началась → заметили → позвали → прибыл → решено), the difference in hours and in t Cu. The data is replay.json,
   which `python -I aktogay/run.py replay` builds from the stored rows of the trial N = 100 (sim/data/trial_n100.json);
   a test keeps the file equal. Every number is an estimate on the model, not a measurement. */
'use strict';
(function () {
  const esc = AKT.esc, fmt = AKT.fmt, f2 = AKT.f2;
  const doc = (stage, id) => { stage.innerHTML = ''; const d = document.createElement('div'); d.className = 'doc'; d.id = id; stage.appendChild(d); return d; };
  const STAGES = [['start', 'Началась', '◆'], ['noticed', 'Заметили', '●'], ['called', 'Позвали', '▲'], ['arrived', 'Прибыл', '■'], ['done', 'Решено', '✔']];
  const hm = m => m == null ? '—' : AKT.clock(m) + (m >= 1440 ? ' (+1 сут.)' : '');
  const dh = h => { if (h == null) return '—'; const a = Math.abs(h), t = a < 1 ? `${Math.round(a * 60)} мин` : `${AKT.f1(a)} ч`; return h > 0.001 ? `${t} раньше` : h < -0.001 ? `${t} позже` : 'одновременно'; };
  const sign = v => (v > 0 ? '+' : v < 0 ? '−' : '') + f2(Math.abs(v));

  /* two timelines on one time axis, grouped by stage: for each stage a dark mark (с двойником) above a grey one (без двойника)
     and the gap between them in words; the axis is fitted to the events of this trouble */
  const lanes = (t, x0, x1, step) => {
    const W = 760, L = 112, R = 150, ROW = 36, TOP = 8, H = TOP + STAGES.length * ROW + 30, X = m => L + (W - L - R) * (m - x0) / (x1 - x0);
    const ticks = [];
    for (let m = Math.ceil(x0 / step) * step; m <= x1; m += step) ticks.push(m);
    const shape = (k, x, y, on) => {
      const c = on ? 'rp-on' : 'rp-off';
      if (k === 'start') return `<path class="${c}" d="M${x},${y - 6} l6,6 l-6,6 l-6,-6 z"/>`;
      if (k === 'noticed') return `<circle class="${c}" cx="${x}" cy="${y}" r="5.5"/>`;
      if (k === 'called') return `<path class="${c}" d="M${x},${y - 6.5} l6.5,12 l-13,0 z"/>`;
      if (k === 'arrived') return `<rect class="${c}" x="${x - 5}" y="${y - 5}" width="10" height="10"/>`;
      return `<path class="rp-chk ${c}" d="M${x - 6},${y} l4,5 l8,-10"/>`;
    };
    const val = (k, w) => k === 'start' ? t.start : t[w][k];
    const rows = STAGES.map(([k, name, g], i) => {
      const yc = TOP + i * ROW + ROW / 2, yw = yc - 7, yo = yc + 7;
      const a = val(k, 'with'), b = val(k, 'without');
      const mk = (v, y, on, who) => v == null ? `<text class="rp-t" x="${L - 6}" y="${y + 4}" text-anchor="end">${who === 'with' ? '' : ''}—</text>` : `<g><title>${esc(name)} ${who === 'with' ? 'с двойником' : 'без двойника'} ${esc(hm(v))}</title>${shape(k, X(v), y, on)}</g>`;
      const link = a != null && b != null && Math.abs(X(a) - X(b)) > 1 ? `<line class="rp-gap" x1="${X(a)}" x2="${X(b)}" y1="${yc}" y2="${yc}"/>` : '';
      const txt = k !== 'start' && a != null && b != null ? `<text class="rp-d" x="${W - R + 10}" y="${yc + 4}">${esc(dh((b - a) / 60))}</text>` : '';
      return `<line class="rp-grid" x1="${L}" x2="${W - R}" y1="${yc + ROW / 2}" y2="${yc + ROW / 2}"/><text class="rp-l" x="4" y="${yc + 4}">${g} ${esc(name)}</text>${link}${mk(a, yw, true, 'with')}${mk(b, yo, false, 'without')}${txt}`;
    }).join('');
    const end = x0 <= 1200 && x1 > 1200 ? `<line class="rp-end" x1="${X(1200)}" x2="${X(1200)}" y1="${TOP}" y2="${H - 26}"/><text class="rp-t" x="${X(1200) + 3}" y="${TOP + 10}">20:00 конец смены</text>` : '';
    const lg = `<g class="rp-leg"><circle class="rp-on" cx="${L + 4}" cy="${H - 6}" r="4"/><text class="rp-t" x="${L + 12}" y="${H - 2}">с двойником</text><circle class="rp-off" cx="${L + 100}" cy="${H - 6}" r="4"/><text class="rp-t" x="${L + 108}" y="${H - 2}">без двойника</text></g>`;
    return `<svg class="rp-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Две ленты времени: с двойником и без, по этапам">
${ticks.map(m => `<line class="rp-tick" x1="${X(m)}" x2="${X(m)}" y1="${H - 30}" y2="${H - 25}"/><text class="rp-t" x="${X(m)}" y="${H - 14}" text-anchor="middle">${AKT.clock(m)}</text>`).join('')}
<line class="rp-axis" x1="${L}" x2="${W - R}" y1="${H - 30}" y2="${H - 30}"/>${end}${rows}${lg}</svg>`;
  };

  const troubleHtml = t => {
    const pts = [t.start, t.with.noticed, t.with.called, t.with.arrived, t.with.done, t.without.noticed, t.without.called, t.without.arrived, t.without.done].filter(v => v != null);
    const lo = Math.min(...pts), hi = Math.max(...pts), pad = Math.max(20, (hi - lo) * 0.06);
    const x0 = Math.floor((lo - pad) / 30) * 30, x1 = Math.ceil((hi + pad) / 30) * 30;
    const step = [15, 30, 60, 120, 240].find(v => (x1 - x0) / v <= 7) || 240;
    const row = (name, key) => {
      const w = key === 'start' ? t.start : t.with[key], o = key === 'start' ? t.start : t.without[key];
      const d = key === 'start' || w == null || o == null ? '—' : dh((o - w) / 60);
      return `<tr><td>${name}</td><td class="n">${hm(w)}</td><td class="n">${hm(o)}</td><td>${d}</td></tr>`;
    };
    const note = [t.hidden ? 'скрытая: двойник находит её через время обнаружения опыта, без двойника её находит проба или сигнал АСУ' : '',
      t.decision ? 'решение, а не ремонт: бригада не нужна, «решено» — момент вызова' : '',
      t.without.called == null ? 'без двойника беду не заметили за сутки' : ''].filter(Boolean).join('; ');
    return `<section class="rp-tr"><h3 title="Код беды: ${esc(t.issue)}">${esc(t.title)}</h3>${lanes(t, x0, x1, step)}
<table class="kv rp-tab"><tr><th>Этап</th><th>С двойником</th><th>Без двойника</th><th>Разница</th></tr>${STAGES.map(([k, n, g]) => row(`<span aria-hidden="true">${g}</span> ${n}`, k)).join('')}</table>
${note ? `<p class="note">${esc(note)}.</p>` : ''}</section>`;
  };

  AKT.views.replay = {
    data: null, cur: null,
    build(stage) {
      const d = doc(stage, 'replay');
      d.innerHTML = `<h2>Повтор смены: с двойником и без</h2>
<p class="lead">Одна и та же смена прожита дважды на модели: с двойником и «как сейчас», без него. Беды, времена ремонта и шум совпадают, различается только то, когда беду заметили и позвали. Это смена из опыта на 100 парных сменах, <b>оценка на модели</b>, а не запись с фабрики.</p>
<div class="rp-bar-row"><label>Смена <select id="rp-sel"></select></label>
<button type="button" data-pick="median">Типичная</button><button type="button" data-pick="best">Лучшая</button><button type="button" data-pick="worst">Самая слабая</button></div>
<div id="rp-sum"></div><div id="rp-body"><p class="empty dash">Загружаю смены…</p></div>
<ul class="cav" id="rp-cav"></ul>`;
      fetch('/replay.json', { cache: 'no-store' }).then(r => r.json()).then(j => { this.data = j; this.init(); })
        .catch(() => { document.getElementById('rp-body').innerHTML = '<p class="empty dash">Файл повтора не загрузился.</p>'; });
    },
    init() {
      const j = this.data, byGain = j.shifts.slice().sort((a, b) => a.gain_cu_t - b.gain_cu_t);
      this.order = { best: byGain[byGain.length - 1].seed, worst: byGain[0].seed, median: byGain[Math.floor(byGain.length / 2)].seed };
      const sel = document.getElementById('rp-sel');
      sel.innerHTML = j.shifts.map(s => `<option value="${s.seed}">прогон № ${s.seed} · бед: ${s.troubles.length} · ${sign(s.gain_cu_t)} т Cu</option>`).join('');
      sel.addEventListener('change', () => this.show(Number(sel.value)));
      document.querySelectorAll('#replay [data-pick]').forEach(b => b.addEventListener('click', () => { sel.value = String(this.order[b.dataset.pick]); this.show(this.order[b.dataset.pick]); }));
      const q = Number(AKT.params.get('seed')) || this.order.median;
      sel.value = String(q);
      this.show(q);
      const s = j.summary, p = j.source;
      document.getElementById('rp-cav').innerHTML = `<li><b>Откуда числа.</b> Повтор берёт смены прежнего опыта от 22.10.2026 (${fmt(s.n)} парных смен, seed ${p.seed0}–${p.seed1}, прежняя библиотека бед): тогда в среднем +${f2(s.mean_cu_t)} т Cu за смену, 95 % ДИ +${f2(s.ci95[0])}…+${f2(s.ci95[1])}; лучше в ${fmt(100 * s.p_plus)} % смен, хуже в ${fmt(100 * s.p_minus)} %. Это историческая запись; текущий главный результат (опыт 24.10.2026, полная библиотека бед) — на странице «Экономика». Оценка на модели.</li>
<li><b>Допущения опыта.</b> Двойник находит скрытую беду через ${fmt(p.detect_min)} мин после начала; без двойника вызов идёт через ${fmt(p.asis_notice_min)} мин после того, как беду увидели (оба числа — допущения). Времени «заметили» без двойника в опыте нет отдельно: люди звонят, когда увидели, поэтому там «заметили» = «позвали».</li>
<li><b>Повторяемость.</b> Опыт посчитан на коде 22.10.2026. Тот же seed на текущем коде даёт те же времена событий, а медь отличается меньше чем на 0,1 % (проверено на seed ${p.seed0}); итог опыта не пересчитывался.</li>
<li><b>Что не показано.</b> Затраты на ремонт, ложные вызовы и работа людей не считаются; на настоящей фабрике нужны метки времени начала, обнаружения, вызова, прибытия и устранения из журналов смен.</li>`;
    },
    show(seed) {
      const s = this.data.shifts.find(x => x.seed === seed);
      if (!s) return;
      const price = s.gain_usd;
      document.getElementById('rp-sum').innerHTML = `<div class="rp-sum"><div><span class="note">с двойником</span><b>${f2(s.cu_t.with)} т Cu</b></div>
<div><span class="note">без двойника</span><b>${f2(s.cu_t.without)} т Cu</b></div>
<div><span class="note">разница к 20:00</span><b>${sign(s.gain_cu_t)} т Cu</b><span class="note">≈ ${esc(AKT.money(price))}</span></div>
<div><span class="note">без бед было бы</span><b>${f2(s.cu_t.base)} т Cu</b></div></div>
<p class="note" title="Код сценария: ${esc(s.text)}; повторить: python -I aktogay/run.py trial --n 1 --seed0 ${s.seed} --no-twin --jobs 1">Прогон № ${s.seed}${s.shared_crew ? ' · двум бедам нужна одна бригада' : ''}.</p>`;
      document.getElementById('rp-body').innerHTML = s.troubles.map(troubleHtml).join('');
    },
  };
})();
