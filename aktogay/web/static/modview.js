/* Page «Модули» (menu Анализ): what each module reads, which decision it forms or what it changes in the work of the mine,
   its last decision with the model time, whether it keeps up with the simulator, and the effect of the twin in one click.
   Everything is read from Ditto (the module things, journal, baseline); the text of the cards is documentation. */
'use strict';
(function () {
  const esc = AKT.esc;
  const clean = s => String(s || '').replace(/\s*\[оценка на модели\]/g, ' (≈)').replace(/\s*\[допущение\]/g, ' (д)').replace(/\s*\[проект\]/g, ' (проект)');
  const setHtml = (id, html) => { const e = document.getElementById(id); if (e && e._raw !== html) { e._raw = html; e.innerHTML = html; if (AKT.glossify) AKT.glossify(e); } };
  const short = (s, n) => { s = clean(s).replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1).replace(/\s+\S*$/, '') + '…' : s; };

  /* the cards: static documentation of the module, live fields from its thing */
  const MODS = [
    { thing: 'mod-losses', title: 'Где теряется медь', view: 'inside', viewName: 'Изнутри',
      reads: 'Состояние узлов обеих линий из двойника: дробление, SAG, шаровые, циклоны, флотация, сгуститель, фильтры, склады, вода, энергия, партии руды; из InfluxDB — окна измерений за последние часы модели.',
      forms: 'Для каждого узла сравнивает измерение с ожиданием по руде и называет разрыв в т Cu/ч и $/ч со статусом «в пределах шума», «не уверен», «потеря», «стоит». Тихая потеря — та, которую уставка АСУ не видит — становится бедой в очереди.',
      changes: 'Через очередь бед: потеря получает номер, цену часа и бригаду, которую надо звать; после вызова узел возвращается к норме.',
      last: () => AKT.val('mod-losses', 'top_text') },
    { thing: 'mod-ore', title: 'Какая руда идёт', view: 'ore', viewName: 'Руда',
      reads: 'Партии руды, забои, экскаваторы, дробилки, ленты, склады, SAG и флотацию из двойника; из InfluxDB — историю подачи.',
      forms: 'Окна прихода твёрдой и мягкой руды к мельницам и прогноз подачи на 12 ч; после факта сверяет, сбылось ли.',
      changes: 'Даёт очереди бед время прихода твёрдой руды и совет по рычагу подачи или помола, который применяется кнопкой «Применить совет».',
      last: () => AKT.val('mod-ore', 'fc_text') },
    { thing: 'mod-priority', title: 'Очередь бед', view: 'queue', viewName: 'Все беды',
      reads: 'Всё, что читают два других модуля, плюс их результаты (mod-losses, mod-ore), журнал вызовов и состояние бригад из двойника.',
      forms: 'Собирает беды, считает ожидаемые потери за 12 ч на выборках прибытия и ремонта и выдаёт порядок вызова: кого звать сейчас, что можно отложить до какого часа, цена задержки на час.',
      changes: 'Вызов бригады по совету (кнопка «Позвать» или автовызов): человек смены идёт к узлу, узел возвращается в работу, потери прекращаются. Без вызова беда не закрывается.',
      last: () => { const j = AKT.shiftJournal ? AKT.shiftJournal()[0] : null; return j ? `${AKT.clock(j.sim_time)} — ${AKT.journalRu(j)}` : AKT.val('mod-priority', 'order_text'); } },
  ];

  function lagBadge(n) {
    const lag = AKT.moduleLag()[n];
    if (lag == null) return '<span class="mod-chip">ещё не считал этот прогон</span>';
    const warn = n === 'mod-ore' ? 45 : AKT.LAG_WARN;
    return lag <= warn ? `<span class="mod-chip ok">успевает: отставание ${esc(AKT.dur(lag))}</span>`
      : `<span class="mod-chip late">▲ отстаёт на ${esc(AKT.dur(lag))} модели</span>`;
  }

  function card(m) {
    const p = AKT.num(m.thing, 'processed_sim_time'), last = m.last();
    return `<section class="mod-card"><h3>${esc(m.title)} ${lagBadge(m.thing)}</h3><dl>
<dt>Что читает</dt><dd>${esc(m.reads)}</dd>
<dt>Какое решение формирует</dt><dd>${esc(m.forms)}</dd>
<dt>Что меняет в работе рудника</dt><dd>${esc(m.changes)}</dd>
<dt>Последнее решение</dt><dd>${last ? esc(short(last, 330)) : 'пока нет'}${p != null && p >= 0 ? `<br><span class="p-sub">посчитано на ${esc(AKT.clockDay(p))}; сейчас в модели ${esc(AKT.clockDay(AKT.simTime))}</span>` : ''}</dd>
</dl><p class="p-sub">Подробнее: <a href="${AKT.href('?view=' + m.view)}">${esc(m.viewName)}</a></p></section>`;
  }

  function leverCard() {
    const L = AKT.lever, issues = AKT.issues().filter(i => L && L.suggestion(AKT.val(i, 'lever')));
    const ap = L && L.applied;
    const last = ap ? `${AKT.clock(ap.t0)} — ${ap.s.label}` : (L && L.on() ? 'рычаги включены вручную на странице «Рычаги модели»' : 'рычаги не включены');
    return `<section class="mod-card"><h3>Рычаги и «Применить совет» <span class="mod-chip ${L && L.on() ? 'ok' : ''}">${L && L.on() ? 'рычаги включены' : 'рычаги выключены'}</span></h3><dl>
<dt>Что читает</dt><dd>Советы с рычагом из двойника (беды issue-N, прогноз по футеровке), текущую подачу, помол и дозу реагента.</dd>
<dt>Какое решение формирует</dt><dd>Подача на мельницу SAG каждой линии, целевой P80 помола, доза собирателя: что поменять, чтобы вернуть извлечение или разгрузить узел.</dd>
<dt>Что меняет в работе рудника</dt><dd>Кнопка «Применить совет в модели» пишет команду в двойник control; симулятор меняет режим линии, а карта, «Путь меди» и плитки показывают «было → стало» и разницу в меди. Это управление моделью, не фабрикой.</dd>
<dt>Последнее решение</dt><dd>${esc(last)}${issues.length ? `<br><span class="p-sub">готовых советов с рычагом сейчас: ${issues.length}</span>` : ''}</dd>
</dl><p class="p-sub">Подробнее: <a href="${AKT.href('?view=levers')}">Рычаги модели</a></p></section>`;
  }

  /* who called for the copy «с двойником» of «Два сразу»: shift_result.policy, written by akt-sim (CopySet.policy_report) */
  const SRC_RU = { module: 'вызов модуля', lab: 'проба лаборатории', alarm: 'тревога', plan: 'запасной порядок', fallback: 'запасной порядок', button: 'кнопка' };
  function policyHtml(r) {
    const p = r && r.policy;
    if (!p || (p.mode !== 'module' && p.mode !== 'fallback') || !(p.n_calls >= 0)) return '';
    const calls = (p.calls || []).map(c => `${esc(AKT.placeRu(c.node))} в ${esc(AKT.clock(c.t))} <span class="p-sub">(${esc(SRC_RU[c.src] || c.src)})</span>`).join(' → ');
    const share = p.share_module >= 0 ? `${AKT.fmt(100 * p.share_module, 0)} %` : '—';
    if (p.mode === 'fallback') {
      return `<p class="note"><b>Модуль не ответил, копия «с двойником» шла по запасному порядку.</b> С ${esc(AKT.clock(p.fallback_at))} модели «Очередь бед» молчала дольше 90 мин, и симулятор вернулся к порядку «по $», посчитанному заранее. Вызовов модуля: ${AKT.fmt(p.n_module)} из ${AKT.fmt(p.n_calls)} (${share}).${calls ? ` Вызовы: ${calls}.` : ''} Эффект ниже — запасного порядка, а не модуля.</p>`;
    }
    const same = p.same_order === 1 ? 'совпал с порядком «по $», посчитанным заранее' : p.same_order === 0 ? 'отличается от порядка «по $», посчитанного заранее' : 'сравнить с порядком «по $» пока не с чем';
    return `<p class="note"><b>Копия «с двойником» шла по вызовам модуля «Очередь бед».</b> Вызовов по бедам сценария: ${AKT.fmt(p.n_calls)}, из них модуля — ${AKT.fmt(p.n_module)} (${share}); тревога сама вызова не запускает.${calls ? ` Порядок: ${calls}.` : ''} Он ${same}. Эти вызовы модуль публикует в двойнике (<code>mod-priority.auto_call</code>), симулятор читает их оттуда — то же, что видит диспетчер в очереди.</p>`;
  }

  function effectHtml() {
    const e = AKT.effect(), r = AKT.shiftResult();
    const run = AKT.scenario();
    let big;
    if (e && e.kind === 'twin') big = `<p class="mod-eff">${esc(e.text)} <span class="p-sub">к ${esc(AKT.clockDay(e.t))}, оценка на модели</span></p>`;
    else if (e) big = `<p class="mod-eff">${esc(e.text)}</p><p class="p-sub">Копии «без двойника» в этом сценарии нет: она есть у «Двух бед сразу».</p>`;
    else big = '<p class="mod-eff dash">Сейчас идёт обычная смена без копий модели, сравнивать не с чем. Запустите «Две беды сразу»: счётчик пойдёт через минуту-две.</p>';
    return `${big}${r ? `<div class="mod-tab">${AKT.shiftTable ? AKT.shiftTable(r) : ''}</div>` : ''}${policyHtml(r)}
<p><button type="button" class="primary" id="mod-run"${run === 'fork' ? ' disabled' : ''}>${run === 'fork' ? 'Сценарий идёт' : 'Запустить «Две беды сразу»'}</button>
 <span class="p-sub">Откроются две копии одной смены с 08:00: с очередью двойника и без него (модуль выключен); разница копится на глазах.</span></p>
<p class="p-sub">Те же сравнения на 100 парных сменах: <a href="${AKT.href('?view=economics')}">Экономика</a>, <a href="${AKT.href('?view=replay')}">Повтор смены</a>.</p>`;
  }

  /* how «Где теряется медь» was checked: detect_eval.json (hidden causes x lines x sizes x seeds) and cusum_eval.json (false alarms), written
     offline by sim/detect_eval.py and sim/cusum_eval.py; every number is a model estimate */
  const KIND_RU = { dose: 'недодача собирателя (флотация)', cyclone: 'засор циклонов', liner: 'износ футеровки SAG', oxide: 'окисленная руда (флотация)' };
  const NODE_RU = { 'sag-1': 'SAG-1', 'cyclones-1': 'циклоны 1', 'flot-1': 'флотация 1', 'sag-2': 'SAG-2', 'cyclones-2': 'циклоны 2', 'flot-2': 'флотация 2' };
  const pc = v => v == null ? '—' : AKT.fmt(100 * v, 0) + ' %';
  const mm = v => v == null ? '—' : AKT.dur(v);
  function evalHtml() {
    const d = AKT.modEval && AKT.modEval.detect, c = AKT.modEval && AKT.modEval.cusum;
    if (!d) return '<p class="empty dash">Загружаю проверку модуля…</p>';
    const rows = Object.entries(d.by_cause).map(([k, b]) => `<tr><td>${esc(KIND_RU[k] || k)}</td><td class="n">${AKT.fmt(b.n)}</td><td class="n">${pc(b.detected_share)}<br><span class="p-sub">[${pc(b.detected_ci95[0])}; ${pc(b.detected_ci95[1])}]</span></td><td class="n">${pc(b.unsure_only_share)}</td><td class="n">${pc(b.missed_share)}</td><td class="n">${mm(b.latency_median_min)}</td><td class="n">${mm(b.latency_p90_min)}</td><td class="n">${pc(b.first_alarm_is_true_node_share)}</td></tr>`).join('');
    const f = d.fork_silent_dose;
    const mat = Object.entries(d.matrix_by_kind).map(([k, r]) => `<tr><td>${esc(KIND_RU[k] || k)}</td>${Object.values(r).map(v => `<td class="n">${pc(v)}</td>`).join('')}</tr>`).join('');
    const colRu = h => h.replace('cyclones', 'циклоны').replace('flot', 'флотация').replace('sag', 'SAG');
    const matHead = Object.keys(Object.values(d.matrix_by_kind)[0]).map(h => `<th>${esc(colRu(h))}</th>`).join('');
    const ctrl = d.control;
    let out = `<p class="lead">Модуль прогнан на библиотеке скрытых причин: ${AKT.fmt(d.runs)} прогонов (причина × линия × размер × seed ${d.seeds[0]}–${d.seeds[1]}), причина начинается в 09:00, модуль считает каждые 5 мин по тем же измерениям, что видит Ditto. «Нашёл» — статус «потеря» у узла причины; «не уверен» — узел вышел за 2σ, но тревоги нет. Оценка на модели.</p>
<table class="kv"><tr><th>Скрытая причина</th><th>Прогонов</th><th>Нашёл («потеря»)</th><th>Только «не уверен»</th><th>Не нашёл за смену</th><th>Задержка, медиана</th><th>Задержка, P90</th><th>Первой тревогой назван узел причины</th></tr>${rows}</table>
<p class="note">Всего ${pc(d.overall.detected_share)} найдено (медиана ${mm(d.overall.latency_median_min)}, P90 ${mm(d.overall.latency_p90_min)}); роль того, кто чинит, названа в ${pc(d.overall.role_named_share)} найденных. «Два сразу» (тихая недодача на 08:00, ${AKT.fmt(f.n)} прогонов): «потеря» у флотации 1 найдена в ${pc(f.detected_share)}, медиана ${mm(f.latency_median_min)} после 08:00 [P10–P90 ${mm(f.latency_p10_min)}–${mm(f.latency_p90_min)}], «не уверен» — медиана ${mm(f.latency_unsure_median_min)}.</p>
<h4>Какие узлы называет модуль</h4><table class="kv"><tr><th>Причина</th>${matHead}</tr>${mat}</table>
<p class="note">Доля прогонов, где узел показал «потеря» хоть раз за смену. Всё, кроме своего узла, — ложные указания на соседей: следствие того, что потеря меди на одном узле сдвигает ожидание на других.</p>
<p class="note"><b>Ложные тревоги.</b> Без причины (${AKT.fmt(ctrl.runs)} смен, ${AKT.fmt(ctrl.hours_total)} ч) модуль показал «потеря» ${AKT.fmt(ctrl.loss_episodes)} раз в ${AKT.fmt(ctrl.runs_with_loss)} прогонах из ${AKT.fmt(ctrl.runs)} (≈ ${AKT.fmt(ctrl.loss_per_week, 1)} в неделю на шесть узлов). Команда повтора: <code>${esc(d.command)}</code>; код ${esc(d.code_hash)}.</p>`;
    if (c) {
      const fr = c.free_run;
      const cur = c.curve.map(r => `<tr${r.work_point ? ' class="row-lv-1"' : ''}><td class="n">${AKT.fmt(r.h, 1)}</td><td class="n">${AKT.fmt(r.fast, 1)}</td><td class="n">${AKT.fmt(r.false_alarms_per_week_free_run, 1)}</td><td class="n">${mm(r.delay_median_min)}</td><td class="n">${mm(r.delay_p90_min)}</td><td class="n">${pc(r.detected_share)}</td><td>${r.work_point ? 'рабочая точка' : ''}</td></tr>`).join('');
      out += `<h4>Ложные тревоги детектора: заявлено и измерено</h4>
<p>Заявлено ≈ ${AKT.fmt(c.stated_false_alarms_per_week, 2)} в неделю. Для независимых N(0, 1) расчёт по Зигмунду даёт ≈ ${AKT.fmt(c.siegmund_alarms_per_week_6_monitors_cusum_only, 1)} в неделю при шаге 5 мин (Монте-Карло: ${AKT.fmt(c.monte_carlo_n01['6.5/99.0'].alarms_per_week_6_monitors, 1)} только по накоплению и ${AKT.fmt(c.monte_carlo_n01['6.5/3.5'].alarms_per_week_6_monitors, 1)} с быстрым порогом 3,5). На остатках двойника (${AKT.fmt(fr.weeks)} недели свободного прогона без скрытых причин и плановых остановок): <b>${AKT.fmt(fr.loss_episodes_per_week, 1)} «потерь» в неделю</b> и ${AKT.fmt(fr.unsure_episodes_per_week, 1)} «не уверен»: остатки не независимы (автокорреляция z на лагах 1–3: ${(Object.values(fr.z_autocorr_lag1_2_3).map(a => a[0]).reduce((s, v) => s + v, 0) / 6).toFixed(2).replace('.', ',')} в среднем по узлам на лаге 1).</p>
<table class="kv"><tr><th>h</th><th>быстрый порог z</th><th>ложных в неделю (свободный прогон)</th><th>задержка, медиана</th><th>задержка, P90</th><th>нашёл</th><th></th></tr>${cur}</table>
<p class="note">Код повтора: <code>${esc(c.command)}</code>. Оценка на модели.</p>`;
    }
    return out;
  }
  AKT.modEval = AKT.modEval || { detect: null, cusum: null, asked: false };
  function loadEval(cb) {
    if (AKT.modEval.asked) return;
    AKT.modEval.asked = true;
    AKT.get('/detect_eval.json').then(j => { AKT.modEval.detect = j; cb(); }).catch(() => { AKT.modEval.asked = false; });
    AKT.get('/cusum_eval.json').then(j => { AKT.modEval.cusum = j; cb(); }).catch(() => { /* optional */ });
  }

  AKT.views.modules = {
    build(stage) {
      stage.innerHTML = '';
      const d = document.createElement('div'); d.className = 'doc'; d.id = 'modules'; stage.appendChild(d);
      d.innerHTML = `<h2>Модули двойника</h2>
<p class="lead">Три модуля работают отдельными службами и читают только данные двойника (Ditto) и историю в InfluxDB; симулятор они не вызывают. Решение формируют модули, а изменения в работе рудника проходят через вызов бригады и рычаги.</p>
<h3>Эффект модуля в один клик</h3><div id="mod-eff"></div>
<h3>Что делает каждый модуль</h3><div id="mod-cards"></div>
<h3 id="mod-eval-h">«Где теряется медь»: как часто находит, как быстро, как часто ошибается</h3><div id="mod-eval"><p class="empty dash">Загружаю проверку модуля…</p></div>
<p class="note" id="mod-real"><b>Проверка на реальных рядах.</b> Детектор «Где теряется медь» (CUSUM, k 0,5, h 6,5) проверен на открытых 20-секундных данных флотации железной руды (OpenML 43311, CC0, одна фабрика, 2017 г.). Для расходомеров белый шум 1 % при публикации раз в минуту близок к реальному. Для реагентов, pH и плотности шум медленный, и цепочка с окном 45 мин даёт 24–40 ложных тревог в неделю на 6 узлов (двойник 29,8, теория для независимых отсчётов 2,8–5,4). Крупные ступени находятся за один–пять тактов. Это проверка датчиков и детектора на железной руде, а не доказательство для меди. Подробности и оговорки — <code>VALIDATION.md</code>, раздел 8.18.</p>
<p class="note">Отставание — разница между временем модели и последней точкой, которую посчитал модуль. Если он отстаёт, он берёт последнюю готовую точку и пропускает старые.</p>`;
      loadEval(() => this.update());
      this.update();
    },
    update() {
      setHtml('mod-eff', effectHtml());
      setHtml('mod-eval', evalHtml());
      setHtml('mod-cards', MODS.map(card).join('') + leverCard());
      const b = document.getElementById('mod-run');
      if (b && !b._on) {
        b._on = true;
        b.addEventListener('click', () => { b.disabled = true; AKT.panel.scenario('fork', { seed: 42, name: 'Две беды сразу' }); });
      }
    },
  };
})();
