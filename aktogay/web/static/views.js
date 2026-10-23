/* Secondary views (L4): «Беды» (queue), «Руда», «Калибровка», «Состав двойника», «Всё текстом»,
   «Легенда и словарь». Each builds a document once and refreshes in place. */
'use strict';
(function () {
  const esc = AKT.esc, fmt = AKT.fmt, f1 = AKT.f1, f2 = AKT.f2, f3 = AKT.f3;
  const doc = (stage, id) => { stage.innerHTML = ''; const d = document.createElement('div'); d.className = 'doc'; d.id = id; stage.appendChild(d); return d; };
  const setHtml = (id, html, gloss) => { const e = document.getElementById(id); if (e && e._raw !== html) { e._raw = html; e.innerHTML = html; if (gloss !== false && AKT.glossify) AKT.glossify(e); } };
  const link = n => `<a href="${AKT.href('?view=unit&id=' + AKT.id(n))}">${esc(AKT.nameRu(n))}</a>`;
  const badge = n => { const lv = AKT.levelOf(n); return `<span class="badge ${AKT.lvCls(lv)}">${lv ? AKT.LV_GLYPH[lv] + ' ' : ''}${esc(AKT.stRu(AKT.st(n), n))}</span>`; };

  /* ---------------------------------------------------------------- «Беды» */
  AKT.views.queue = {
    build(stage) {
      const d = doc(stage, 'queue');
      d.innerHTML = `<h2>Беды — по порядку, кого звать</h2>
<p class="lead">Порядок — кого звать первым. Сначала то, что опасно для людей; дальше то, где час промедления стоит дороже. Суммы со знаком ≈ — расчёт модели.</p>
<div id="q-list"></div>
<h3>Тихие перерасходы</h3><div id="q-silent"></div>
<div id="q-dev"></div>
<h3 id="q-ho">Сдача смены</h3><div id="q-handover"></div>
<h3>Как считали порядок</h3><div id="q-mod"></div>
<h3 id="q-journal">Журнал смены</h3><div id="q-jr"></div>`;
    },
    update() {
      const issues = AKT.issues();
      const rows = issues.map(n => {
        const lv = AKT.issueLevel(n), m = AKT.issueMain(n);
        const d = AKT.num(n, 'delay_cost_usd'), cb = AKT.num(n, 'call_by');
        const per = AKT.issuePerson(n);
        const called = AKT.issueCalled(n);
        const shift = AKT.num(n, 'loss_shift_usd');
        const why = [AKT.issueWhy(n), AKT.issueAdvice(n) ? 'Совет модуля: ' + AKT.issueAdvice(n) : '', String(AKT.val(n, 'choice_text') || '').replace(/\s*\[оценка на модели\]/g, ' (≈)'), String(AKT.val(n, 'chain_text') || ''), shift > 0 ? `Если никого не звать, за 12 ч ${AKT.approx(shift)}.` : ''].filter(Boolean).join(' ');
        return `<tr class="row-lv-${lv}"><td class="n">${AKT.rankNo(n) != null ? `<span class="rk">${fmt(AKT.rankNo(n))}</span>` : '—'}</td>
<td>${AKT.glyph(lv)} <b>${esc(AKT.issueTitle(n))}</b><br>${AKT.issueNode(n) ? link(AKT.issueNode(n)) : ''}${why ? `<details><summary>Почему так решено</summary>${esc(why)}</details>` : ''}</td>
<td>${esc(m.text)}${m.small ? ' <span class="p-sub">' + esc(m.small) + '</span>' : ''}</td>
<td class="n">${String(AKT.val(n, 'safety_class') || '') === 'S0' ? 'опасно' : d != null && d > 0 ? '≈ ' + esc(AKT.usd(d)) : 'пока ничего'}</td>
<td>${cb != null ? esc(AKT.clockDay(cb)) : 'сейчас'}</td>
<td>${esc(AKT.roleAcc(AKT.issueRole(n)))}${per ? `<br><span class="p-sub">${esc(AKT.personAvail(per))}</span>` : ''}</td>
<td>${esc(AKT.stRu(AKT.st(n), n))}${AKT.num(n, 'eta') != null && AKT.st(n) === 'CALLED' ? `<br><span class="p-sub">ждём к ${esc(AKT.clockDay(AKT.num(n, 'eta')))}</span>` : ''}${AKT.val(n, 'escalation') ? `<br><b class="esc">${esc(String(AKT.val(n, 'escalation')))}</b>` : ''}</td>
<td>${AKT.val(n, 'escalation') ? `<button type="button" class="primary" data-i="${esc(n)}" data-a="remind">Напомнить</button> <button type="button" data-i="${esc(n)}" data-a="next">Позвать следующего</button>` : called ? '—' : `<button type="button" class="primary" data-i="${esc(n)}" data-a="call">Позвать ${esc(AKT.roleAcc(AKT.roleFirst(AKT.issueRole(n))))}</button> <button type="button" data-i="${esc(n)}" data-a="snooze">Не сейчас…</button>`}</td></tr>`;
      }).join('');
      const html = issues.length ? `<table class="kv"><tr><th>№</th><th>Где и что</th><th>Сейчас</th><th>Час промедления</th><th>Позвать до</th><th>Кого звать</th><th>Статус</th><th>Действие</th></tr>${rows}</table>`
        : `<p class="empty">${AKT.warming() ? 'Модель прогревается: беда, если есть, появится через ~1 мин.' : 'Бед нет. Все участки в норме.'}</p>`;
      const q = document.getElementById('q-list');
      if (q._raw !== html) {
        q._raw = html; q.innerHTML = html; AKT.glossify(q);
        q.querySelectorAll('button[data-a]').forEach(b => b.addEventListener('click', () => {
          if (b.dataset.a === 'call') return AKT.panel.call(b.dataset.i);
          if (b.dataset.a === 'remind' || b.dataset.a === 'next') return AKT.panel.remind(b.dataset.i, b.dataset.a === 'next');
          /* «Не сейчас…»: the form of the panel card, opened for this issue */
          AKT.panel.open = b.dataset.i; AKT.panel.update();
          const f = document.getElementById('tc-form'); f.hidden = false; document.getElementById('topcard').scrollIntoView({ block: 'nearest' });
          f.querySelector('input[type=radio]:checked').focus();
        }));
      }
      const alarm = String(AKT.val('mod-priority', 'alarm_order_text') || '');
      const m = /разница ([−\-\d,\s]+) т Cu \(([^)]+)\)/.exec(alarm);
      const one = issues.length < 2;
      const sum = m ? `Порядок по деньгам против «кто громче» в этой смене: разница ≈ ${m[1].trim()} т меди (${m[2]})${one ? ' — беда одна, порядок не нужен' : ''}.` : (one ? 'Беда одна или ни одной — порядок не нужен.' : 'Модуль ещё не сравнил порядки.');
      const ac = AKT.val('mod-priority', 'auto_call');
      const clean = s => esc(String(s || '—').replace(/\s*\[оценка на модели\]/g, ' (≈)').replace(/\bпо громкости\b/g, '«кто громче»'));
      setHtml('q-mod', `<p>${esc(sum)}</p><details><summary>Разбор модуля очереди бед</summary><table class="kv"><tr><td>очередь</td><td>${clean(AKT.val('mod-priority', 'queue_text'))}</td></tr><tr><td>порядок по деньгам</td><td>${clean(AKT.val('mod-priority', 'order_text'))}</td></tr><tr><td>порядок «кто громче»</td><td>${clean(AKT.val('mod-priority', 'alarm_order_text'))}</td></tr><tr><td>последний автовызов</td><td>${ac && typeof ac === 'object' && Object.keys(ac).length ? esc(AKT.objText(ac)) : 'не было'}</td></tr><tr><td>модуль посчитал на</td><td>${AKT.clockDay(AKT.num('mod-priority', 'processed_sim_time'))} модели</td></tr></table></details>`);
      setHtml('q-silent', silentHtml());
      const devT = String(AKT.val('mod-priority', 'deviations_text') || '').split('\n').filter(Boolean);
      setHtml('q-dev', devT.length ? `<h3>Отклонения (хроника, в очередь не идут)</h3><ul>${devT.map(x => `<li>${esc(x.replace(/\s*\[оценка на модели\]/g, ' (≈)').replace(/\s*\[допущение\]/g, ' (д)'))}</li>`).join('')}</ul><p class="p-sub">${esc(String(AKT.val('mod-priority', 'tariff_text') || '').replace(/\s*\[допущение\]/g, ' (д)'))}</p>` : '');
      setHtml('q-handover', AKT.views.handover.html());
      const JR_RU = { call: 'позвали', snooze: 'отложили', auto_call: 'автовызов', remind: 'напомнили', next: 'позвали следующего', late: 'двойник: не прибыл', arrived: 'двойник: прибыли' };
      const esc_rows = ((AKT.val('mod-priority', 'escalations') || {}).log || []).filter(e => e && (e.action === 'late' || e.action === 'arrived'))
        .map(e => ({ sim_time: e.t, action: e.action, issue: e.issue, role: '', text: e.text, run: AKT.run }));
      const jr = r => `<tr><td>${AKT.clock(r.sim_time)}</td><td>${esc(JR_RU[r.action] || r.action)}</td><td>${esc(AKT.things[r.issue] && (!r.run || r.run === AKT.run) ? AKT.nameRu(AKT.issueNode(r.issue) || r.issue) : (/^issue-(\d+)$/.test(r.issue || '') ? 'беда ' + r.issue.slice(6) : (r.issue || '')))}</td><td>${esc(r.role ? AKT.roleAcc(r.role) : '')}</td><td>${esc(r.text || '')}</td></tr>`;
      const head = '<tr><th>время модели</th><th>действие</th><th>беда</th><th>кто</th><th>комментарий</th></tr>';
      const mine = AKT.journal.filter(r => !r.run || r.run === AKT.run).concat(esc_rows).sort((a, b) => (b.sim_time || 0) - (a.sim_time || 0)), old = AKT.journal.filter(r => r.run && r.run !== AKT.run);
      setHtml('q-jr', (mine.length ? `<table class="kv">${head}${mine.map(jr).join('')}</table>` : '<p class="empty dash">В этой смене действий ещё не было.</p>')
        + (old.length ? `<details><summary>Прошлые прогоны (${fmt(old.length)})</summary><table class="kv">${head}${old.map(jr).join('')}</table></details>` : ''), false);
    },
  };

  /* ------------------------------------------------- тихие перерасходы (mod-losses) */
  function silentHtml() {
    const t = String(AKT.val('mod-losses', 'silent_text') || '');
    if (!t) return '<p class="empty dash">Модуль «Где теряется медь» ещё не посчитал этот прогон.</p>';
    const parts = t.split('; ').map(x => esc(x.replace(/\s*\[оценка на модели\]/g, ' (≈)')));
    return `<ul>${parts.map(x => `<li>${x}</li>`).join('')}</ul><p class="p-sub">Энергия SAG — измеренные кВт·ч/т против Моррелла на оценке партии; реагенты — баланс бака на весах против расходомера; вода — невязка баланса забора, потерь и пруда. Цены: электроэнергия 16 тг/кВт·ч (факт, 2026), вода и ксантогенат — допущения.</p>`;
  }

  /* ------------------------------------------------------- «Сдача смены» (mod-priority) */
  AKT.views.handover = {
    build(stage) {
      const d = doc(stage, 'handover');
      d.innerHTML = `<h2>Сдача смены</h2>
<p class="lead">Лист собирает модуль очереди бед в 07:30 и 19:30 времени модели: открытые беды (кого позвали, когда ждём), отложенные со сроком, приборы под подозрением, руда на 12 ч, бригады. Ниже — что передать, если бы смену сдавали сейчас.</p>
<div id="ho-body"></div>`;
    },
    update() { setHtml('ho-body', this.html()); },
    html() {
      const ho = AKT.val('mod-priority', 'handover') || {};
      const draft = String(AKT.val('mod-priority', 'handover_draft_text') || '');
      const lines = s => String(s || '').split('\n').filter(Boolean);
      const block = (title, s) => { const L = lines(s); return L.length ? `<div class="ho"><b>${esc(title)}</b><ul>${L.slice(1).map(x => `<li>${esc(x.replace(/\s*\[оценка на модели\]/g, ' (≈)'))}</li>`).join('')}</ul></div>` : ''; };
      const at = typeof ho.at === 'number' && ho.at >= 0 ? ho.at : null;
      return (at != null ? block(/записан/.test(ho.title || '') ? ho.title : `${ho.title || 'Сдача смены'} (лист записан в ${AKT.clockDay(at)} модели)`, ho.text) : '<p class="empty dash">Лист ещё не составлен: он появится в 07:30 или 19:30 времени модели.</p>')
        + (draft ? block(`Если сдавать сейчас (${AKT.clockDay(AKT.num('mod-priority', 'processed_sim_time'))} модели)`, draft) : '')
        + '<p class="p-sub">Зачем лист по разделам: на тренажёре НПЗ (Honeywell, ENGEN, 10 пар операторов) с таким листом в журнал попадало 76 % нужных сведений против 57 % (Plocher и др., 2011; литература, другая отрасль).</p>';
    },
  };

  /* ------------------------------------------------------------------ «Руда» */
  AKT.views.ore = {
    build(stage) {
      const d = doc(stage, 'ore');
      d.innerHTML = `<h2>Руда: партии и прогноз</h2>
<p class="lead">Партия — 15 000 т руды из одного блока карьера. Здесь видно, где каждая партия сейчас и когда твёрдая руда дойдёт до мельниц.</p>
<h3>Когда придёт твёрдая руда</h3><div id="o-hard"></div>
<h3>Партии</h3><div id="o-batches"></div><h3>Прогноз на 12 часов</h3><div id="o-fc"></div><h3>Слои складов</h3><div id="o-layers"></div><h3>Сбылось ли</h3><div id="o-check"></div>
<details><summary>Как считается</summary><p class="note">Состояние партии — где её последняя тонна: «копается», пока часть ещё в карьере; «в пути к складу», пока хвост на дороге и ленте; «на складе», когда вся легла в штабель. «Осталось по весам» — учёт конвейерных весов (первой пришла — первой ушла); «≈ в штабеле» — оценка модуля руды по своей модели смешения (штабель не FIFO), поэтому числа разные. Окна прихода и слои — оценка по блочной модели (ошибка твёрдости около 12 %).</p></details>`;
    },
    update() {
      const bs = AKT.batches();
      const oreOk = String(AKT.val('mod-ore', 'idSimulationRun') || '') === AKT.run;
      const layer = {};
      for (const l of [1, 2]) {
        const raw = AKT.val('mod-ore', 'layers_l' + l);
        if (oreOk && typeof raw === 'string' && raw.trim().startsWith('[')) { try { for (const o of JSON.parse(raw)) layer[o.batch] = o; } catch (e) { /* skip */ } }
      }
      const t0 = AKT.num('mod-ore', 'processed_sim_time') ?? AKT.simTime ?? 0;
      const eta = l => { const e = AKT.num('mod-ore', `next_hard_eta_early_h_l${l}`), x = AKT.num('mod-ore', `next_hard_eta_h_l${l}`);
        return e == null && x == null ? 'в плане на 12 ч твёрдой руды нет' : `ожидаемо в ${AKT.clockDay(t0 + 60 * (x ?? e))} (через ${AKT.durH(x ?? e)})${e != null ? `; раньше всего — в ${AKT.clockDay(t0 + 60 * e)}` : ''}`; };
      setHtml('o-hard', oreOk ? `<table class="kv"><tr><td>Линия 1</td><td>${eta(1)}</td></tr><tr><td>Линия 2</td><td>${eta(2)}</td></tr>${AKT.num('mod-ore', 'next_hard_axb') != null ? `<tr><td>твёрдость ближайшей</td><td>A×b ≈ ${f1(AKT.num('mod-ore', 'next_hard_axb'))}</td></tr>` : ''}</table>` : '<p class="empty dash">Модуль руды ещё не посчитал этот прогон.</p>');
      const tn = v => v == null ? '—' : fmt(v);
      const where = n => { const loc = AKT.name(AKT.val(n, 'location') || AKT.parent(n) || ''); return AKT.things[loc] ? AKT.nameRu(loc) : (loc === 'pit' ? 'карьер' : loc); };
      setHtml('o-batches', bs.length ? `<table class="kv"><tr><th>партия</th><th>где сейчас</th><th></th><th>масса, т</th><th>ещё в карьере, т</th><th>осталось по весам, т</th><th>≈ в штабеле, т</th><th>руда</th><th>медь по блоку, %</th><th>медь по лаборатории, %</th></tr>${bs.map(n => {
        const o = layer[n];
        return `<tr><td>${link(n)}</td><td>${esc(AKT.stRu(AKT.st(n), n))}</td><td>${esc(where(n))}</td><td class="n">${tn(AKT.pass(n, 'tonnes'))}</td><td class="n">${tn(AKT.num(n, 'pit_t'))}</td><td class="n">${tn(AKT.num(n, 'tonnes_left'))}</td><td class="n">${o ? '≈ ' + fmt(o.t) : '—'}</td><td>${AKT.oreLetter(AKT.batchAxb(n))} — ${esc(AKT.oreWord(AKT.batchAxb(n)))} (A×b ≈ ${f1(AKT.batchAxb(n))})</td><td class="n">≈ ${f3(AKT.pass(n, 'est_cu'))}</td><td class="n">${AKT.num(n, 'cu_meas') == null ? '<span class="note">ещё нет</span>' : f3(AKT.num(n, 'cu_meas'))}</td></tr>`;
      }).join('')}</table>` : '<p class="empty dash">Партий в плане ещё нет — они появятся, когда карьер начнёт новый блок.</p>');
      const fc = Array.from({ length: 12 }, (_, i) => AKT.num('mod-ore', `fc_tph_h${i + 1}`));
      const max = Math.max(1, ...fc.map(v => v || 0));
      setHtml('o-fc', `<p>${esc(String(AKT.val('mod-ore', 'fc_text') || '—').replace(/\s*\[оценка на модели\]/g, ' (≈)'))}</p><p class="note">Доля сбывшихся прогнозов: ${AKT.num('mod-ore', 'hit_rate') == null ? 'проверок ещё не было' : f1(AKT.num('mod-ore', 'hit_rate')) + ' %'}.</p>
<table class="kv"><tr><th>час</th><th>≈ руда, т/ч</th><th></th></tr>${fc.map((v, i) => `<tr><td>${AKT.clockDay(t0 + 60 * i)}–${AKT.clock(t0 + 60 * (i + 1))}</td><td class="n">${fmt(v)}</td><td><span class="fc-bar" style="width:${Math.round(200 * (v || 0) / max)}px"></span></td></tr>`).join('')}</table>`);
      setHtml('o-layers', [1, 2].map(l => {
        const raw = AKT.val('mod-ore', 'layers_l' + l);
        let arr = null;
        if (oreOk && typeof raw === 'string' && raw.trim().startsWith('[')) { try { arr = JSON.parse(raw); } catch (e) { arr = null; } }
        const tm = v => (typeof v === 'number' && v >= 0) ? AKT.clockDay(v) : '—';
        const body = arr && arr.length ? `<table class="kv"><tr><th>партия</th><th>блок</th><th>руда</th><th>медь, %</th><th>≈ в штабеле, т</th><th>где</th><th>доля в мельнице</th><th>раньше всего</th><th>ожидаемо</th><th>не позже</th></tr>${arr.map(o => `<tr><td>${esc(AKT.things[o.batch] ? AKT.nameRu(o.batch) : 'партия ' + AKT.batchNo(String(o.batch)))}</td><td>${esc(o.block || '—')}</td><td>${esc(o.cls || '')} (A×b ${f1(o.axb)})</td><td class="n">${f3(o.cu)}</td><td class="n">${fmt(o.t)}</td><td>${esc(AKT.batchStRu(o.state))}</td><td class="n">${fmt(100 * (o.in_sag || 0))} %</td><td>${tm(o.early)}</td><td>${tm(o.exp)}</td><td>${tm(o.late)}</td></tr>`).join('')}</table>`
          : `<p class="empty dash">${oreOk ? 'слоёв нет' : 'модуль руды ещё не посчитал этот прогон'}</p>`;
        return `<h4 style="margin:4px 0">Склад ${l}</h4>${body}`;
      }).join(''));
      setHtml('o-check', esc(String((oreOk && AKT.val('mod-ore', 'check_text')) || 'пока нет: партия ещё не дошла до мельницы').replace(/\s*\[оценка на модели\]/g, ' (≈)')));
    },
  };

  /* ---------------------------------------------------------------- «Калибровка» */
  AKT.views.calib = {
    build(stage) {
      const d = doc(stage, 'calib');
      d.innerHTML = `<h2>Калибровка и проверка модели</h2>
<p class="lead" id="cb-lead">Загружаю итог проверки…</p>
<div id="cb-chart"></div>
<h3>Проверка: очередь «по деньгам» против очереди «кто громче»</h3><div id="cb-trial"></div>
<h3>Калибровка по годовым отчётам</h3><div id="cb-report"></div>
<h3>Балансы сейчас</h3><div id="cb-bal"></div>
<h3>Сравнение с ходом без сценария</h3><div id="cb-base"></div>
<p class="note" id="cb-state"></p>`;
    },
    update() {
      const st = AKT.st('validation-calib');
      const raw = AKT.val('validation-calib', 'report_json');
      let rep = null, bad = '';
      if (typeof raw === 'string' && raw.trim()) { try { rep = JSON.parse(raw); } catch (e) { bad = raw; } }
      const when = AKT.thing('validation-calib') && AKT.thing('validation-calib')._modified;
      setHtml('cb-state', `Расчёт: ${esc(AKT.stRu(st, 'validation-calib'))}${st === 'DONE' ? `, записан ${esc(when ? new Date(when).toLocaleString('ru-RU') : '—')}${rep && rep.seconds ? `, счёт ${fmt(rep.seconds)} с` : ''}` : st === 'RUNNING' ? ' (≈ 2 мин), таблицы появятся сами' : ''}.`, false);
      const tr = rep && rep.trial, s = tr && tr.summary || {};
      const d = s.d_cu_t_2000, tw = s.twin_cu_t_2000;
      let lead = 'Итог проверки ещё не записан: расчёт калибровки не закончил или не запускался.';
      if (d) {
        const pm = d.p_minus || 0;
        lead = `Проверено на ${fmt(d.n || tr.n)} сменах модели. Очередь «по деньгам» в среднем сохраняет ≈ ${AKT.fmt(d.mean, 2)} т меди за смену против очереди «кто громче» и ${pm === 0 ? 'ни в одной смене не хуже' : `хуже в ${fmt(100 * pm)} % смен`}.`
          + (tw ? ` Двойник целиком даёт ≈ +${AKT.fmt(tw.mean, 2)} т меди за смену против работы без двойника.` : '');
      }
      setHtml('cb-lead', esc(lead));
      setHtml('cb-chart', d ? ciChart(s) : '', false);
      setHtml('cb-trial', tr ? renderTrial(tr) : `<p class="empty dash">${st === 'RUNNING' ? 'Считается.' : 'Итог проверки ещё не записан.'}</p>`);
      let body = '<p class="empty dash">Отчёт ещё не записан.</p>';
      if (rep && Array.isArray(rep.rows)) body = renderCalib(rep);
      else if (rep) body = renderReport(rep);
      else if (bad) body = `<pre>${esc(bad)}</pre>`;
      setHtml('cb-report', body, false);
      const ml = k => AKT.num('mod-losses', k);
      const resid = v => v == null ? '<span class="note">мало точек</span>' : `<span class="${Math.abs(v) < 0.5 ? 'ok' : 'bad'}">${f2(v)} %</span>`;
      setHtml('cb-bal', `<p class="note">Невязка — насколько не сходятся счётчики весов и расходомеров за последние 2 ч модели. Первый час после запуска — «мало точек». Медь сводится по формуле двух продуктов, её невязка близка к нулю по построению.</p><table class="kv"><tr><th>баланс</th><th>невязка</th><th>допуск</th></tr>
<tr><td>медь: питание = концентрат + хвосты</td><td class="n">${resid(ml('cu_residual_pct'))}</td><td>&lt; 0,5 %</td></tr>
<tr><td>вода: забор = вода с хвостами + испарение + влага кека + изменение пруда</td><td class="n">${resid(ml('water_residual_pct'))}</td><td>&lt; 0,5 %</td></tr>
<tr><td>концентрат: питание сгустителя = разгрузка на фильтр + изменение запаса</td><td class="n">${resid(ml('conc_residual_pct'))}</td><td>&lt; 0,5 %</td></tr>
<tr><td>мощность по частям</td><td colspan="2">${esc(AKT.val('mod-losses', 'power_parts_text') || `мельницы ${f1(AKT.num('power', 'grinding_mw'))} · прочее ${f1(AKT.num('power', 'other_mw'))} · итого ${f1(AKT.num('power', 'site_mw'))} из ${fmt(AKT.num('power', 'grid_limit_mw'))} МВт`)} · запас ${f1(ml('power_headroom_mw') ?? AKT.num('power', 'headroom_mw'))} МВт</td></tr></table>`);
      const res = AKT.shiftResult();
      setHtml('cb-base', res ? AKT.shiftTable(res) : `<p class="note">${AKT.check ? 'Сравнения нет: ход без сценария считается только во время сценария; в свободном ходе итог появляется в конце смены.' : 'Сравнение с ходом без сценария видно только в «Режиме проверки модели» (в «Пульте модели»): диспетчеру на смене оно недоступно.'}</p>`);
    },
  };
  /* interval chart: mean (dot) and 95 % interval (line) per comparison, one axis — t of copper per shift */
  const CI_ROWS = [['d_cu_t_2000', 'по деньгам − «кто громче», к 20:00'], ['d_cu_t_0800', 'то же, к 08:00 следующего дня'],
    ['detection_cu_t_2000', 'вклад обнаружения бед'], ['twin_cu_t_2000', 'двойник целиком − без двойника']];
  function ciChart(s) {
    const rows = CI_ROWS.filter(([k]) => s[k] && Array.isArray(s[k].ci95_mean_bca));
    if (!rows.length) return '';
    const W = 760, PL = 10, PW = 420, LH = 30, top = 10, H = top + rows.length * LH + 34;
    let lo = 0, hi = 0;
    for (const [k] of rows) { lo = Math.min(lo, s[k].ci95_mean_bca[0]); hi = Math.max(hi, s[k].ci95_mean_bca[1]); }
    hi = Math.ceil(hi * 2) / 2 || 0.5; lo = Math.floor(lo * 2) / 2;
    const X = v => PL + PW * (v - lo) / (hi - lo);
    const ticks = []; for (let v = lo; v <= hi + 1e-9; v += 0.5) ticks.push(v);
    return `<svg class="ci-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Разница меди за смену, т: среднее и 95-процентный интервал">
${ticks.map(v => `<line class="${Math.abs(v) < 1e-9 ? 'zero' : 'grid'}" x1="${X(v)}" x2="${X(v)}" y1="${top - 4}" y2="${top + rows.length * LH}"/><text x="${X(v)}" y="${top + rows.length * LH + 16}" text-anchor="middle">${AKT.fmt(v, 1)}</text>`).join('')}
<text x="${PL + PW / 2}" y="${H - 2}" text-anchor="middle">т меди за смену</text>
${rows.map(([k, l], i) => { const r = s[k], y = top + i * LH + LH / 2; return `<line class="ci" x1="${X(r.ci95_mean_bca[0])}" x2="${X(r.ci95_mean_bca[1])}" y1="${y}" y2="${y}"/><circle class="mean" cx="${X(r.mean)}" cy="${y}" r="4"/><text x="${PL + PW + 14}" y="${y + 4}">${esc(l)}: ≈ ${AKT.fmt(r.mean, 2)}</text>`; }).join('')}
</svg><p class="note">Точка — среднее по сменам, линия — 95 % интервал. Табличный вид — ниже.</p>`;
  }
  const TRIAL_ROWS = [
    ['d_cu_t_2000', 'по деньгам − «кто громче», т меди к 20:00', 't'],
    ['d_cu_t_0800', 'то же к 08:00 следующего дня, т меди', 't'],
    ['d_usd_2000', 'то же в $ к 20:00 (оплачиваемая медь − энергия − вода)', 'usd'],
    ['detection_cu_t_2000', 'вклад обнаружения: «кто громче» − без двойника, т меди к 20:00', 't'],
    ['twin_cu_t_2000', 'двойник целиком: по деньгам − без двойника, т меди к 20:00', 't'],
  ];
  const CUT_RU = { 'troubles=2': '2 беды за смену', 'troubles=3': '3 беды за смену', 'shared_crew=False': 'у бед разные бригады',
    'shared_crew=True': 'две беды ждут одну бригаду', has_crusher: 'есть поломка дробилки', has_trip: 'есть срабатывание защиты дробилки',
    has_cyclone: 'есть засор циклона', has_dose: 'есть дрейф расходомера реагента', has_grid: 'есть урезание сети',
    has_hard: 'есть твёрдая руда', has_reline: 'есть перефутеровка SAG' };
  const pct = v => v == null ? '—' : `${fmt(100 * v)} %`;
  const ci = (a, f) => Array.isArray(a) && a.length === 2 ? ` <span class="note">(${f(a[0])}…${f(a[1])})</span>` : '';
  const pval = p => p == null ? '—' : (p < 1e-4 ? '<span title="вероятность случайного результата меньше 0,01 %">p < 0,0001</span>' : `p = ${fmt(p, 4)}`);
  function renderTrial(t) {
    const c = t.config || {}, s = t.summary || {}, seeds = t.seeds || [];
    const n = t.n ?? c.n;
    const val = (v, kind) => kind === 'usd' ? '≈ ' + AKT.money(v) : (v == null ? '—' : `${v < 0 ? '−' : v > 0 ? '+' : ''}${fmt(Math.abs(v), 2)}`);
    const rows = TRIAL_ROWS.filter(([k]) => s[k]).map(([k, label, kind]) => {
      const r = s[k], f = v => val(v, kind), w = r.wilcoxon || {};
      return `<tr><td>${esc(label)}</td><td class="n">${fmt(r.n)}</td><td class="n">${f(r.mean)}${ci(r.ci95_mean_bca, f)}</td><td class="n">${f(r.median)}</td>
<td class="n">${pct(r.p0)}</td><td class="n">${pct(r.p_minus)}</td><td class="n">${pct(r.p_plus)}</td><td class="n">${pval(w.p)}</td></tr>`;
    }).join('');
    const cuts = Object.entries(t.cuts || {}).map(([k, r]) => `<tr><td>${esc(CUT_RU[k] || k)}</td><td class="n">${fmt(r.n)}</td><td class="n">${val(r.mean, 't')}${ci(r.ci95_mean_bca, v => val(v, 't'))}</td><td class="n">${val(r.median, 't')}</td><td class="n">${pct(r.p0)}</td><td class="n">${pct(r.p_minus)}</td></tr>`).join('');
    return `<table class="kv"><tr><th>что сравниваем</th><th>смен</th><th>в среднем (95 % интервал)</th><th>медиана</th><th>смен без разницы</th><th>смен, где хуже</th><th>смен, где лучше</th><th>надёжность (тест Уилкоксона)</th></tr>${rows}</table>
${cuts ? `<details><summary>Срезы: разница к 20:00 по типам смен, т меди</summary><table class="kv"><tr><th>смены</th><th>смен</th><th>в среднем</th><th>медиана</th><th>без разницы</th><th>хуже</th></tr>${cuts}</table></details>` : ''}
<details><summary>Как считали и как повторить</summary><p class="note">${fmt(n)} парных смен 08:00–20:00 на модели (seed ${esc(seeds[0] ?? '—')}–${esc(seeds[1] ?? '—')}), в смене 2–3 беды; у копий одни и те же беды, шум и времена ремонта, различается только порядок вызова бригад. Интервал среднего — бутстреп BCa (${fmt(c.boot)} повторов), доли — интервал Уилсона 95 %; «без разницы» — |разница| < 0,05 т меди. Входы проверки (допущения): двойник находит скрытую беду через ${fmt(c.detect_min)} мин, пропусков ${pct(c.miss)}, совет по тихой беде ждёт человека ${fmt(c.loud_react_min)} мин, разброс ремонта σ ln ${fmt(c.sigma_ln, 1)}, КИПиА — ${fmt(c.kip)} бригада. Пересчёт: <code>python -I aktogay/run.py trial --n 100 --no-twin</code> (≈ 3 мин; те же seed — те же числа).</p></details>`;
  }

  const GROUP_RU = [[/^fit params$/, 'параметры подгонки'], [/^fit (\d{4})$/, 'подгонка $1'], [/^check (\d{4})$/, 'проверка $1'],
    [/^balance (\d{4})$/, 'балансы $1'], [/^reline$/, 'перефутеровка'], [/^quarters$/, 'кварталы'], [/^week$/, '7 суток модели']];
  const NAME_RU = [
    [/^ore processed \(input\)$/, 'руда переработана (вход)'], [/^ore processed$/, 'руда переработана'],
    [/^SAG mean P\/Q while running$/, 'SAG: удельная мощность в работе'], [/^recovery$/, 'извлечение Cu'],
    [/^Cu in concentrate$/, 'Cu в концентрате'], [/^electricity \(input\)$/, 'электроэнергия (вход)'], [/^electricity, site$/, 'электроэнергия площадки'],
    [/^electricity per t ore$/, 'электроэнергия на 1 т руды'], [/^electricity$/, 'электроэнергия'],
    [/^water intake per t ore$/, 'забор воды на 1 т руды'], [/^water recycle per t ore$/, 'оборотная вода на 1 т руды'], [/^water intake$/, 'забор воды'],
    [/^availability (\d{4}) \(matched to ore\)$/, 'готовность $1 (под тонны руды)'],
    [/^availability (\d{4}) \(matched to ore from electricity\)$/, 'готовность $1 (под руду из электроэнергии)'],
    [/^feed grade \(input\)$/, 'Cu в питании (вход)'],
    [/^line (\d) tonnes Q(\d) vs Q(\d) (\d{4})$/, 'линия $1: тонны Q$2 к Q$3 $4'], [/^line (\d) ore Q(\d) (\d{4})$/, 'линия $1: руда Q$2 $3'],
    [/^Q(\d) (\d{4}) recovery, model at quarter grade$/, 'Q$1 $2: извлечение, модель при содержании квартала'],
    [/^Q(\d) (\d{4}) recovery, constant$/, 'Q$1 $2: извлечение, константа 87,2 %'],
    [/^Q(\d) (\d{4}) recovery, model at annual grade$/, 'Q$1 $2: извлечение, модель при годовом содержании'],
    [/^Q(\d) (\d{4}) ore processed$/, 'Q$1 $2: руда переработана'],
    [/^Cu: feed - concentrate - tails$/, 'Cu: питание − концентрат − хвосты'], [/^Cu: largest \|residual\|, plant counters$/, 'Cu: наибольшая невязка счётчиков'],
    [/^concentrate: cleaner = thickener \+ filter = stock \+ shipped$/, 'концентрат: перечистка = сгуститель + фильтр = склад + отгрузка'],
    [/^ore: stockpile in - out - level change$/, 'руда: приход склада − расход − изменение'], [/^ore: SAG feed - stockpile out$/, 'руда: питание SAG − расход склада'],
    [/^water: intake - losses - pond change$/, 'вода: забор − потери − изменение пруда'], [/^water: largest \|residual\| of water_step$/, 'вода: наибольшая невязка шага'],
    [/^site power highest$/, 'мощность площадки, максимум'], [/^SAG power highest$/, 'мощность SAG, максимум'], [/^ball mill power highest$/, 'мощность шаровой, максимум'],
    [/^SAG feed-end wear counter highest$/, 'износ футеровки SAG у загрузки, максимум'], [/^SAG running hours per line (\d{4})$/, 'часы работы SAG на линию, $1'],
    [/^cal_avail$/, 'cal_avail — готовность линии'], [/^sag_k$/, 'sag_k — коэффициент мощности SAG'], [/^flot_rinf0_pct$/, 'flot_rinf0_pct — предельное извлечение'],
    [/^water_evap_m3h$/, 'water_evap_m3h — испарение и фильтрация'], [/^pow_other_mw$/, 'pow_other_mw — прочая нагрузка площадки'],
    [/^stockpile-(\d) lowest level$/, 'склад $1: наименьший уровень'], [/^stockpile-(\d) highest level$/, 'склад $1: наибольший уровень'],
    [/^pond lowest$/, 'пруд: наименьший объём'], [/^pond highest$/, 'пруд: наибольший объём'],
    [/^max \|cu_residual_pct\|$/, 'наибольшая невязка меди'], [/^max \|water_residual_pct\|$/, 'наибольшая невязка воды'],
    [/^max \|conc_residual_pct\|$/, 'наибольшая невязка концентрата'], [/^shift counter resets$/, 'сбросы счётчиков смены'],
    [/^longest shift counter$/, 'самый длинный счётчик смены'], [/^ACS false alarms$/, 'ложные тревоги АСУ'],
    [/^line (\d) mean t\/h$/, 'линия $1: средняя производительность'],
  ];
  /* notes of sim/calib.py rows in Russian (numbers keep their values; decimal point -> comma) */
  const NOTE_RU = [
    [/^cal_avail ([\d.]+) \(table ([\d.]+)\); run (\d+) of (\d+)$/, 'cal_avail $1 (в таблице $2); прогон $3 из $4'],
    [/^sag_k ([\d.]+) \(table ([\d.]+)\); ([\d.]+) MW at (\d+) t\/h$/, 'sag_k $1 (в таблице $2); $3 МВт при $4 т/ч'],
    [/^flot_rinf0_pct ([\d.]+) \(table ([\d.]+)\); model feed ([\d.]+) % Cu$/, 'flot_rinf0_pct $1 (в таблице $2); питание модели $3 % Cu'],
    [/^not fitted: ore x model feed x recovery; feed target ([\d.]+) % = ([\d.]+) \/ \(([\d.]+) x ([\d.]+)\), report grade ([\d.]+) % is rounded$/,
      'не подгоняется: руда × питание модели × извлечение; целевое питание $1 % = $2 / ($3 × $4), содержание в отчёте $5 % округлено'],
    [/^pow_other_mw ([\d.]+) \(table ([\d.]+)\); site part (\d+) GWh over (\d+) d, line part (\d+) GWh; run (\d+) of (\d+)$/,
      'pow_other_mw $1 (в таблице $2); общая часть площадки $3 ГВт·ч за $4 сут, часть линий $5 ГВт·ч; прогон $6 из $7'],
    [/^water_evap_m3h ([\d.]+) \(table ([\d.]+)\); evaporation and seepage ([\d.]+) Mm3, tails pores ([\d.]+) Mm3$/,
      'water_evap_m3h $1 (в таблице $2); испарение и фильтрация $3 млн м³, вода в порах хвостов $4 млн м³'],
    [/^availability matched to the report tonnes$/, 'готовность подобрана под тонны отчёта'],
    [/^report column: fitted 2025 availability; no reline of 2023 in the calendar$/, 'в столбце «отчёт» — подогнанная готовность 2025; перефутеровок 2023 в календаре нет'],
    [/^report column: fitted 2025 availability$/, 'в столбце «отчёт» — подогнанная готовность 2025'],
    [/^availability ([\d.]+) from the 2024 fit \(same run\)$/, 'готовность $1 из подгонки 2024 (тот же прогон)'],
    [/^blk_cu_mean_pct = report grade; report balance ([\d.]+) \/ \(([\d.]+) x ([\d.]+)\) gives ([\d.]+) %$/,
      'blk_cu_mean_pct = содержание отчёта; баланс отчёта $1 / ($2 × $3) даёт $4 %'],
    [/^model feed ([\d.]+) %; constant ([\d.]+) % would be off by ([-\d.]+) pp$/, 'питание модели $1 %; константа $2 % ошиблась бы на $3 п. п.'],
    [/^ore x model feed x recovery$/, 'руда × питание модели × извлечение'],
    [/^report column: ore implied by (\d+) GWh with the 2024 fit \(([\d.]+) kWh\/t for mills, crushers, conveyors and line loads that stop with the line; site part (\d+) GWh\); 2023 ore not in sources yet$/,
      'в столбце «отчёт» — руда из $1 ГВт·ч по подгонке 2024 ($2 кВт·ч/т на мельницы, дробилки, конвейеры и нагрузки, которые стоят вместе с линией; общая часть площадки $3 ГВт·ч); руды 2023 в источниках пока нет'],
    [/^gives the ore above, not a check$/, 'даёт руду выше, это не проверка'],
    [/^blk_cu_mean_pct = report grade$/, 'blk_cu_mean_pct = содержание отчёта'],
    [/^evaporation and seepage ([\d.]+) Mm3 \(2024 fit\), tails pores ([\d.]+) Mm3$/, 'испарение и фильтрация $1 млн м³ (подгонка 2024), вода в порах хвостов $2 млн м³'],
    [/^blk_cu_mean_pct = tgt_2025_feed_pct ([\d.]+) % \(report Cu \/ \(ore x recovery\)\); block model and stockpile give the model feed$/,
      'blk_cu_mean_pct = tgt_2025_feed_pct $1 % (Cu отчёта / (руда × извлечение)); питание модели дают блочная модель и склад'],
    [/^2025 not published, report column: 2024 at ([\d.]+) Mt, model ([\d.]+) Mt; other (\d+) GWh \(2024 fit\)$/,
      '2025 не опубликован; в столбце «отчёт» — 2024 при $1 млн т, модель $2 млн т; прочее $3 ГВт·ч (подгонка 2024)'],
    [/^2024 report per t; the constant other load spreads over more ore in 2025$/, 'отчёт 2024 на 1 т; постоянная прочая нагрузка в 2025 делится на больше руды'],
    [/^2025 not published, report column: 2024 at ([\d.]+) Mt; evaporation and seepage ([\d.]+) Mm3 \(2024 fit\)$/,
      '2025 не опубликован; в столбце «отчёт» — 2024 при $1 млн т; испарение и фильтрация $2 млн м³ (подгонка 2024)'],
    [/^2024 report per t; OVOS fresh water ([\d.]+)-([\d.]+) m3\/t$/, 'отчёт 2024 на 1 т; свежая вода по ОВОС $1–$2 м³/т'],
    [/^OVOS$/, 'ОВОС'],
    [/^SAG reline of line 2 in August 2025 named in the Q3 2025 report \(p\. 3\); its length (\d+) h is an assumption, not taken from this quarter; hours alone give ([-\d.]+) %; model adds stockpile, stops and the liner campaign \(peak before, new-liner ramp after\); run hours Q2 (\d+) h, Q3 (\d+) h$/,
      'перефутеровка SAG линии 2 в августе 2025 названа в отчёте за 3 кв. 2025 (с. 3); её длительность $1 ч — допущение, не из этого квартала; одни часы дают $2 %; модель добавляет склад, остановки и кампанию футеровки (пик до, разгон новой после); часы работы: 2 кв. $3 ч, 3 кв. $4 ч'],
    [/^annual 2025 run$/, 'годовой прогон 2025'],
    [/^tolerance = error of the constant ([\d.]+) %; grade ([\d.]+) % \(model feed ([\d.]+) %\); run from day (\d+)$/,
      'допуск = ошибка константы $1 %; содержание $2 % (питание модели $3 %); прогон с дня $4'],
    [/^flot_rec_ref_pct, reference error$/, 'flot_rec_ref_pct: ошибка константы для сравнения'],
    [/^annual run, grade ([\d.]+) %$/, 'годовой прогон, содержание $1 %'],
    [/^Q2 grade not in sources yet$/, 'содержания 2 кв. в источниках пока нет'],
    [/^annual run; quarterly tonnes are not fitted$/, 'годовой прогон; квартальные тонны не подгоняются'],
    [/^feed ([\d.]+) = concentrate ([\d.]+) \+ tails ([\d.]+) kt; flotation holds no Cu$/, 'питание $1 = концентрат $2 + хвосты $3 тыс. т; флотация медь не копит'],
    [/^Plant\.balances, daily and at the end$/, 'счётчики модели: раз в сутки и в конце'],
    [/^largest \|residual\|, Plant\.balances$/, 'наибольшая невязка, счётчики модели'],
    [/^level change ([+-]?[\d.]+) kt over the run$/, 'изменение запаса $1 тыс. т за прогон'],
    [/^SAG feed is drawn from the stockpile only$/, 'SAG питается только со склада'],
    [/^intake ([\d.]+) = tails ([\d.]+) \+ concentrate ([\d.]+) \+ evaporation ([\d.]+) \+ pond ([+-]?[\d.]+) Mm3$/,
      'забор $1 = хвосты $2 + концентрат $3 + испарение $4 + пруд $5 млн м³'],
    [/^band ([\d.]+)-([\d.]+) MW \(grid limit; mean ([\d.]+) MW\)$/, 'предел $2 МВт (лимит сети); среднее $3 МВт'],
    [/^band ([\d.]+)-([\d.]+) MW \(grid limit\)$/, 'предел $2 МВт (лимит сети)'],
    [/^band ([\d.]+)-([\d.]+) MW \(rated drive, shaft\)$/, 'предел $2 МВт (номинал привода, на валу)'],
    [/^band ([\d.]+)-([\d.]+) mm: feed end changed at intermediate relines \(liner_feed_end_mm\)$/,
      'предел $2 мм: загрузочный торец меняют на промежуточных перефутеровках (liner_feed_end_mm)'],
    [/^band ([\d.]+)-([\d.]+) %; start (\d+) %$/, 'полоса $1–$2 %; на старте $3 %'], [/^band ([\d.]+)-([\d.]+) %$/, 'полоса $1–$2 %'],
    [/^band ([\d.]+)-([\d.]+) Mm3$/, 'полоса $1–$2 млн м³'],
    [/^report column: table value$/, 'в столбце «отчёт» — значение таблицы'],
    [/^report column: OVOS design hours$/, 'в столбце «отчёт» — проектные часы ОВОС'],
    [/^(\d+) hourly samples$/, '$1 часовых отсчётов'], [/^on_shift_end calls (\d+)$/, 'концов смены: $1'],
    [/^shift counters must restart every shift$/, 'счётчики смены должны обнуляться каждую смену'],
    [/^tails setpoint ([\d.]+) % Cu; (\d+) alarms, (\d+) hidden causes$/, 'уставка по хвостам $1 % Cu; тревог $2, скрытых причин $3'],
    [/^free run: no planned stops; pebble stops and hidden causes on$/, 'свободный ход: без плановых остановок; остановки дробления гали и скрытые причины включены'],
  ];
  const noteRu = s => {
    const parts = String(s || '').split('; ');
    const whole = ru(String(s || ''), NOTE_RU);
    const text = whole !== String(s || '') ? whole : parts.map(p => p === 'not available' ? 'нет данных' : p === 'model value not finite' ? 'значение модели не число' : ru(p, NOTE_RU)).join('; ');
    return text.replace(/(\d)\.(\d)/g, '$1,$2');
  };
  /* rows whose report column is a band (calib.py: report = centre, tol = half width, note "band lo-hi ...") */
  /* the note only marks the row (its numbers are rounded); the band itself is report ± tol */
  const bandOf = x => /^band /.test(x.note || '') && typeof x.report === 'number' && typeof x.tol === 'number' && x.tol >= 0
    ? [Math.max(0, x.report - x.tol), x.report + x.tol].map(v => Math.abs(v) < 1e-9 ? 0 : v) : null;
  const UNIT_RU = { Mt: 'млн т', kt: 'тыс. т', 'kWh/t': 'кВт·ч/т', GWh: 'ГВт·ч', Mm3: 'млн м³', 'm3/t': 'м³/т', 'm3/h': 'м³/ч', MW: 'МВт', mm: 'мм', h: 'ч', '-': '' };
  const ru = (s, table) => { for (const [re, to] of table) if (re.test(s)) return s.replace(re, to); return s; };
  const num4 = v => v == null ? '—' : fmt(v, Math.abs(v) >= 1000 ? 1 : Math.abs(v) >= 100 ? 2 : Math.abs(v) >= 1 ? 3 : 4);
  function renderCalib(r) {
    let nOk = 0, nNo = 0, nInfo = 0;
    const rows = r.rows.map(x => {
      const okh = x.ok === true ? (nOk++, '<span class="ok">да</span>') : x.ok === false ? (nNo++, '<span class="bad">нет</span>') : (nInfo++, '—');
      const band = bandOf(x);
      let repCell, devCell, tolCell;
      if (band) {
        /* a limit or a band, not a value to hit: "≤ предел 28", the margin left, the band itself */
        const [lo, hi] = band;
        repCell = lo === 0 ? `≤ предел ${num4(hi)}` : `${num4(lo)}…${num4(hi)}`;
        devCell = x.model == null ? '—' : x.model > hi ? `выше на ${num4(x.model - hi)}` : x.model < lo ? `ниже на ${num4(lo - x.model)}`
          : (lo === 0 ? `запас ${num4(hi - x.model)}` : 'в полосе');
        tolCell = lo === 0 ? `0…${num4(hi)}` : `${num4(lo)}…${num4(hi)}`;
      } else {
        const dev = (x.model != null && x.report != null) ? x.model - x.report : null;
        const rel = dev != null && x.report && !['%', 'pp'].includes(x.unit) ? ` (${dev >= 0 ? '+' : '−'}${fmt(Math.abs(100 * dev / x.report), 1)} %)` : '';
        repCell = num4(x.report);
        devCell = dev == null ? '—' : (dev >= 0 ? '+' : '−') + num4(Math.abs(dev)) + rel;
        tolCell = x.tol != null && x.tol >= 0 ? '±' + num4(x.tol) : '—';
      }
      return `<tr><td>${esc(ru(x.group || '', GROUP_RU))}</td><td>${esc(ru(x.name || '', NAME_RU))}</td><td class="n">${num4(x.model)}</td><td class="n">${repCell}</td><td>${esc(UNIT_RU[x.unit] ?? x.unit ?? '')}</td>
<td class="n">${devCell}</td><td class="n">${tolCell}</td><td>${okh}</td></tr>`;
    }).join('');
    const notes = r.rows.filter(x => x.note).map(x => `<li>${esc(ru(x.group || '', GROUP_RU))} · ${esc(ru(x.name || '', NAME_RU))}: ${esc(noteRu(x.note))}</li>`).join('');
    const errs = (r.errors || []).length ? `<p class="bad">Ошибки счёта: ${esc(r.errors.join('; '))}</p>` : '';
    return `<p class="note">Модель подогнана к отчётам 2025 года (3 числа) и проверена на 2023–2024 без подгонки. Строк ${fmt(r.rows.length)}: в допуске ${fmt(nOk)}, вне допуска ${fmt(nNo)}, без допуска ${fmt(nInfo)}${r.quick ? ' (быстрый режим, без 7 суток)' : ''}. Числа модели — расчёт (≈).</p>${errs}
<table class="kv"><tr><th>группа</th><th>величина</th><th>модель</th><th>отчёт</th><th>ед.</th><th>отклонение</th><th>допуск</th><th>в допуске</th></tr>${rows}</table>
${notes ? `<details><summary>Пояснения к строкам</summary><ul class="note">${notes}</ul></details>` : ''}`;
  }

  function renderReport(r) {
    if (Array.isArray(r)) return AKT.kvTable(r);
    if (typeof r !== 'object' || r === null) return esc(String(r));
    return Object.entries(r).map(([k, v]) => `<h3>${esc(k)}</h3>${typeof v === 'object' ? AKT.kvTable(v) : `<p>${esc(v)}</p>`}`).join('');
  }

  /* ----------------------------------------------------------------- «Состав двойника» */
  const SERVICE = /^(control|journal|baseline|mod-.*|validation-.*)$/;
  AKT.views.tree = {
    build(stage) { const d = doc(stage, 'tree'); d.innerHTML = '<h2>Состав двойника</h2><p class="lead">Все объекты двойника по вложенности: площадка → участки → аппараты. Служебные — внизу, свёрнуты.</p><div class="tree" id="tree-body"></div>'; },
    update() {
      const kids = {};
      const all = Object.keys(AKT.things);
      for (const n of all) { const p = AKT.parent(n) || ''; (kids[p] = kids[p] || []).push(n); }
      for (const k in kids) kids[k].sort(AKT.cmpNames);
      const node = n => `<li>${link(n)} <span class="note">${esc(AKT.typeRu(AKT.type(n)))}</span> ${AKT.st(n) && AKT.levelOf(n) ? badge(n) : ''}${kids[n] ? `<ul>${kids[n].filter(x => !SERVICE.test(AKT.type(x))).map(node).join('')}</ul>` : ''}</li>`;
      const roots = (kids[''] || []).filter(n => !SERVICE.test(AKT.type(n)));
      const svc = all.filter(n => SERVICE.test(AKT.type(n))).sort(AKT.cmpNames);
      setHtml('tree-body', `<ul>${roots.map(node).join('')}</ul><details><summary>Служебное (${fmt(svc.length)}): модули, пульт модели, журнал, проверка</summary><ul>${svc.map(n => `<li>${link(n)} <span class="note">${esc(AKT.typeRu(AKT.type(n)))}</span></li>`).join('')}</ul></details><p class="note">объектов: ${fmt(all.length)}</p>`, false);
    },
  };

  /* ----------------------------------------------------------------- «Всё текстом» */
  const AREAS = [
    ['Карьер', n => ['pit', 'fleet', 'exc', 'truck', 'dozer', 'drill', 'face', 'road', 'batch'].includes(AKT.type(n)) || ['truck', 'dozer', 'drill', 'face', 'road', 'exc'].includes(AKT.cat(n))],
    ['Дробление и склады руды', n => ['crusher', 'conveyor', 'stockpile', 'weigher'].includes(AKT.type(n))],
    ['Линия 1', n => /-1[ab]?$/.test(n) && !['crusher', 'conveyor', 'stockpile', 'weigher', 'piezometer'].includes(AKT.type(n)) && AKT.cat(n) !== 'person'],
    ['Линия 2', n => /-2[ab]?$/.test(n) && !['crusher', 'conveyor', 'stockpile', 'weigher', 'piezometer'].includes(AKT.type(n)) && AKT.cat(n) !== 'person'],
    ['Концентрат', n => AKT.type(n) === 'conc-stock'],
    ['Вода и дамба', n => AKT.type(n) === 'water' || AKT.cat(n) === 'piezo' || AKT.cat(n) === 'water-trouble'],
    ['Энергия', n => AKT.type(n) === 'power'],
    ['Люди', n => ['person', 'crew'].includes(AKT.cat(n))],
    ['Беды', n => AKT.type(n) === 'issue'],
  ];
  AKT.views.text = {
    build(stage) { const d = doc(stage, 'text'); d.innerHTML = '<h2>Всё текстом</h2><p class="note">Для печати и экранных чтецов: то же, что на экранах, без графики, по участкам. Числа со знаком ≈ — расчёт модели, с пометкой (д) — допущение; остальное измерено.</p><div id="text-body"></div>'; },
    update() {
      const o = AKT.nowLine();
      const cu = AKT.num('site', 'cu_tph');
      const q = AKT.issues();
      const head = `<p><b>${esc(o.text)}</b></p><p>Время модели ${AKT.clockDay(AKT.simTime)}, модель идёт ×${fmt(AKT.num('site', 'speed'))}. Руда ${fmt(AKT.num('site', 'tph'))} т/ч · медь ${f1(cu)} т/ч · стоимость меди ≈ ${AKT.money(AKT.usdPerH(cu))}/ч · сеть ${fmt(AKT.num('power', 'site_mw'))} из ${fmt(AKT.num('power', 'grid_limit_mw'))} МВт · вода ${fmt(AKT.num('site', 'water_m3h'))} м³/ч${AKT.scenario() ? ' · учебный сценарий: ' + esc(AKT.scenarioRu(AKT.scenario())) : ''}.</p>`
        + (q.length ? `<p>Беды по порядку: ${q.map(i => `${AKT.rankSign(i) || '•'} ${esc(AKT.issueTitle(i))} — ${esc(AKT.issueMain(i).text)}, ${esc(AKT.issuePrice(i))}, звать ${esc(AKT.roleAcc(AKT.issueRole(i)))}`).join('; ')}.</p>` : '<p>Бед нет.</p>');
      const used = new Set();
      const para = n => {
        used.add(n);
        const t = AKT.thing(n);
        const feats = AKT.simOnly(n) ? esc(AKT.SIM_ONLY_NOTE) : Object.keys(t.features || {}).filter(f => !['idSimulationRun', 'sim_time', 'state', 'status', 'state_ru', 'status_ru'].includes(f))
          .map(f => `${esc(AKT.featRu(n, f))}: ${esc(AKT.valText(n, f))}`).join('; ');
        return `<p><b>${link(n)}</b> (${esc(AKT.typeRu(AKT.type(n)))})${AKT.st(n) ? ' — ' + esc(AKT.stOf(n)) : ''}<br><span class="note">${feats}</span></p>`;
      };
      const names = Object.keys(AKT.things).sort(AKT.cmpNames);
      let body = '';
      for (const [title, test] of AREAS) {
        const ns = names.filter(n => !used.has(n) && test(n));
        if (ns.length) body += `<h3>${esc(title)}</h3>` + ns.map(para).join('');
      }
      const rest = names.filter(n => !used.has(n));
      if (rest.length) body += `<details><summary>Служебное (${fmt(rest.length)})</summary>${rest.map(para).join('')}</details>`;
      setHtml('text-body', head + body, false);
    },
  };

  /* --------------------------------------------------------------- «Легенда и словарь» */
  const ico = (inner, w) => `<svg width="${w || 26}" height="20" viewBox="0 0 ${w || 26} 20" aria-hidden="true">${inner}</svg>`;
  AKT.views.legend = {
    build(stage) {
      const d = doc(stage, 'legend');
      d.innerHTML = `<h2>Легенда и словарь</h2>
<div class="lg-grid">
<div class="lg-card"><h4>Почему почти всё серое</h4><p>${ico('<rect x="4" y="4" width="18" height="12" rx="2" fill="#c9cdd3" stroke="#5b626b"/>')} Серое — работает как надо. Цвет появляется только там, где нужно внимание. Рядом с цветом всегда есть значок и слово.</p></div>
<div class="lg-card"><h4>Уровни</h4>
<p>${ico('<rect x="4" y="4" width="18" height="12" rx="2" fill="#c62828" stroke="#a61b1b"/>')} <span class="lv lv-1">◆</span> стоит или опасно — звать сейчас</p>
<p>${ico('<rect x="4" y="4" width="18" height="12" rx="2" fill="#e8a000" stroke="#5c4300" stroke-width="1.5"/>')} <span class="lv lv-2">▲</span> отклонение или теряем сейчас</p>
<p>${ico('<rect x="4" y="4" width="18" height="12" rx="2" fill="#fff" stroke="#5c4300" stroke-dasharray="3 2" stroke-width="1.5"/>')} <span class="lv lv-3">△</span> скоро: запас ещё держит</p></div>
<div class="lg-card"><h4>Номер беды</h4><p>${ico('<circle cx="13" cy="10" r="8" fill="#16191d"/><text x="13" y="14" text-anchor="middle" font-size="12" font-weight="700" fill="#fff">1</text>')} Тёмный круг с цифрой — место беды в очереди: кого звать первым. Номер не окрашен: цвет несёт кольцо вокруг узла.</p>
<p>${ico('<circle cx="13" cy="10" r="7" fill="none" stroke="#5c4300" stroke-width="3"/>')} Кольцо уровня у узла беды; у беды ① оно пульсирует, а рядом — подпись с ценой: «час промедления ≈ $…» или «позвать до ЧЧ:ММ».</p></div>
<div class="lg-card"><h4>≈ и (д)</h4><p><b>≈</b> — расчёт модели, не измерение (деньги, потери, прогнозы, слои склада).</p><p><b>(д)</b> или надстрочная «д» — допущение: числа нет в открытых источниках, принято разумное значение.</p><p>Числа без знака измерены и пришли из двойника, обновление раз в 2 с.</p></div>
<div class="lg-card"><h4>Учебный сценарий</h4><p>${ico('<rect x="3" y="3" width="20" height="14" rx="2" fill="#e3ecfa" stroke="#1f5fbf" stroke-width="2" stroke-dasharray="3 2"/>')} Синяя пунктирная рамка и слово «сценарий» — это сделала учебная поломка из «Пульта модели», а не жизнь. Синий цвет больше нигде не используется.</p></div>
<div class="lg-card"><h4>Руда</h4><p><span class="badge" style="background:var(--ore-soft);color:var(--ink)">М — мягкая, A×b ≥ 38</span> <span class="badge" style="background:var(--ore-mid);color:#fff">С — средняя</span> <span class="badge" style="background:var(--ore-hard);color:#fff">Т — твёрдая, A×b &lt; 30</span></p><p>Один тон, темнее — твёрже, и всегда буква. Слой «Руда» на карте показывает партии у экскаваторов, на лентах и слои складов.</p></div>
<div class="lg-card"><h4>Потоки и движение</h4><p>${ico('<line x1="2" y1="10" x2="24" y2="10" stroke="#3a3f47" stroke-width="6"/><line x1="2" y1="10" x2="24" y2="10" stroke="#b9a27a" stroke-width="3" stroke-dasharray="3 6"/>')} Ширина ленты ∝ т/ч, бегущая руда — скорость ∝ т/ч. Стоящая лента — красный пунктир.</p><p>${ico('<circle cx="8" cy="10" r="3" fill="#3a3f47" stroke="#fff"/><circle cx="18" cy="10" r="3" fill="#6b5a3a" stroke="#fff"/>')} Точки на дорогах карьера — самосвалы (тёмные — гружёные), место на дороге — схема движения между обновлениями.</p></div>
<div class="lg-card"><h4>Люди</h4><p>${ico('<circle cx="13" cy="6" r="3" fill="#fff" stroke="#454b53"/><path d="M7.5 17 C7.5 9.5 18.5 9.5 18.5 17 Z" fill="#454b53"/>')} Фигурка с короткой ролью. В пути — пунктир от места к месту и «будет ≈ ЧЧ:ММ». Слой «Люди» включается сам, когда кого-то позвали.</p></div>
<div class="lg-card"><h4>Карта</h4><p>Стрелка «С» — север, линейка — 1 км. «Схема» — объекта нет на карте OpenStreetMap, нарисован условно. Подложка «Спутник» — снимок Sentinel-2.</p><p>Высоты в 3D: глубина карьера 230 м — факт; уступы, здания и машины — схема, машины крупнее масштаба.</p></div>
</div>
<h3>Откуда данные</h3><p>Экран показывает состояние цифрового двойника фабрики: числа приходят раз в 2 секунды, история за 2 часа — из архива. Кнопки «Позвать» и «Не сейчас…» пишут в журнал смены; «Пульт модели» управляет учебной моделью. Геометрия плана — © участники OpenStreetMap, <a href="https://opendatacommons.org/licenses/odbl/1-0/" target="_blank" rel="license noopener">ODbL</a>.</p>
<details><summary>Для инженера</summary><p class="note">Интерфейс читает только Ditto (состояние вещей) и InfluxDB (тренды, журнал) через сервер стенда akt-web; симулятор ему недоступен. Кнопки пишут только в вещи control и journal. Список допущений — файл aktogay/PARAMETERS.md. «Режим проверки модели» (в «Пульте модели») показывает журнал скрытых причин симулятора и копии модели без сценария.</p></details>
<h3 id="glossary">Словарь</h3>${AKT.glossaryHtml()}`;
    },
    update() {},
  };
})();
