/* Pages of the second level for the dispatcher and for the buyer: «Журнал» (search, CSV), «Отчёт смены» (one button,
   printable), «Экономика», «Как проверить», «Тренировка» with its frame. Data: Ditto, InfluxDB (journal, history) and
   the summary of the on/off trial that the calibration job writes into validation-calib. No numbers of their own:
   every figure here is read from those, or is named with its label. */
'use strict';
(function () {
  const esc = AKT.esc, fmt = AKT.fmt, f1 = AKT.f1, f2 = AKT.f2;
  const NB = AKT.NB;
  const doc = (stage, id) => { stage.innerHTML = ''; const d = document.createElement('div'); d.className = 'doc'; d.id = id; stage.appendChild(d); return d; };
  const setHtml = (id, html) => { const e = document.getElementById(id); if (e && e._raw !== html) { e._raw = html; e.innerHTML = html; if (AKT.glossify) AKT.glossify(e); } };
  const cleanTxt = s => String(s || '').replace(/\s*\[оценка на модели\]/g, ' (≈)').replace(/\s*\[допущение\]/g, ' (д)').replace(/\s*\[проект\]/g, ' (проект)');

  /* ================================================================== training mode (feature 19) */
  const TKEY = 'akt-train', TLOG = 'akt-train-log';
  const Train = AKT.train = {
    on() { return AKT.store.get(TKEY) === '1'; },
    set(v) { AKT.store.set(TKEY, v ? '1' : '0'); Train.apply(); if (AKT.current && AKT.current.update) AKT.current.update(); },
    /* the frame is on every screen; the chip sits in the header (no layout shift) */
    apply() {
      if (AKT.params.get('train') === '1') AKT.store.set(TKEY, '1'); else if (AKT.params.get('train') === '0') AKT.store.set(TKEY, '0');   /* ?train=1 / ?train=0 for a demo link */
      document.body.classList.toggle('training', Train.on());
      let chip = document.getElementById('train-chip');
      if (Train.on() && !chip) {
        chip = document.createElement('a'); chip.id = 'train-chip'; chip.className = 'train-chip'; chip.href = AKT.href('?view=train');
        chip.title = 'Тренировка включена: «Позвать» и «Не сейчас…» не пишутся в журнал и отчёты. Нажмите, чтобы открыть страницу тренировки.';
        chip.textContent = 'ТРЕНИРОВКА';
        const tools = document.getElementById('tools'); if (tools) tools.insertBefore(chip, tools.firstChild);
      } else if (!Train.on() && chip) chip.remove();
    },
    log() { try { return JSON.parse(AKT.store.get(TLOG) || '[]'); } catch (e) { return []; } },
    record(entry) { const l = Train.log(); l.push(Object.assign({ at: Date.now() }, entry)); AKT.store.set(TLOG, JSON.stringify(l.slice(-100))); },
    clear() { AKT.store.set(TLOG, '[]'); },
  };

  /* drills: the right call is the stand's own rule of who goes (modules/priority.WHO), the numbers are the live plant's */
  const ROLES = ['Механик ЦПД', 'Дежурный КИПиА', 'Механик фабрики', 'Металлург смены', 'Дежурный энергетик', 'Геолог смены', 'Горный диспетчер', 'Технолог хвостов и оборотной воды'];
  const DRILLS = [
    { id: 'crusher', title: 'Встала дробилка', line: 2, story: n => `Дробилка ЦПД-${n} остановилась, датчик масла в норме. Склад линии ${n} держит SAG ещё несколько часов.`, right: 'Механик ЦПД', why: 'Остановка самой дробилки — механическая: идёт механик ЦПД с бригадой (таблица «кого звать»: crusher_stop).' },
    { id: 'lube', title: 'Защита по давлению масла', line: 1, story: n => `Дробилка ЦПД-${n} стала по защите: давление масла ниже уставки, а насос исправен.`, right: 'Дежурный КИПиА', why: 'Это сигнал датчика и цепи защиты, а не поломка: идёт дежурный КИПиА (lube_trip). Механик потеряет время впустую.' },
    { id: 'sag', title: 'Мельница SAG стоит', line: 1, story: n => `Мельница SAG-${n} остановилась: привод не держит нагрузку.`, right: 'Механик фабрики', why: 'Останов мельницы — работа бригады мельниц: механик фабрики (sag_stop).' },
    { id: 'dose', title: 'Падает извлечение', line: 1, story: n => `На линии ${n} извлечение ниже ожидаемого по руде; расходомер реагента показывает норму, а баланс бака — перерасход.`, right: 'Дежурный КИПиА', why: 'Расходомер и дозатор — зона КИПиА; металлург подключается вторым (loss_flot / reagent_over).' },
    { id: 'grid', title: 'Сеть урезала мощность', line: 0, story: () => 'Сеть урезала лимит площадки. Нужно решить, что отключать первым.', right: 'Дежурный энергетик', why: 'Решение по нагрузке — у дежурного энергетика (grid_limited).' },
    { id: 'water', title: 'Не хватает оборотной воды', line: 0, story: () => 'Пруд просел, возврат воды с хвостохранилища упал, свежая вода упёрлась в предел.', right: 'Технолог хвостов и оборотной воды', why: 'Водовод и пруд — бригада хвостового хозяйства под технологом хвостов (water_short).' },
    { id: 'pit', title: 'Карьер не подаёт руду', line: 0, story: () => 'Все экскаваторы руды стоят. Откатка и лента довезут последнюю руду, дальше фабрика живёт со склада.', right: 'Горный диспетчер', why: 'Решение о выемке и забоях — у горного диспетчера (pit_stop); склад даёт время.' },
  ];
  const trainSvc = d => {
    const n = d.line || 0;
    const f = AKT.fc && AKT.fc.data(), r = n && f && f.stock && f.stock.lines && f.stock.lines[String(n)];
    const hours = n ? (r && r.hours >= 0 ? r.hours : AKT.hoursLeft(`stockpile-${n}`)) : null;
    const cu = n ? AKT.num(`line-${n}`, 'cu_tph') : AKT.num('site', 'cu_tph');
    return { n, hours, cu };
  };
  const trainResult = (d, pick) => {
    const s = trainSvc(d), ok = pick === d.right;
    const delay = 0.5;   /* h: переадресация при неверном вызове — допущение, диапазон 20–40 мин (время прибытия в таблице стенда) */
    let cost = '';
    if (!ok) {
      const lost = s.cu != null ? Math.max(0, delay - (s.hours != null ? s.hours : 99)) * s.cu : null;
      const hold = s.hours != null ? `Склад линии ${s.n} держит ещё ≈ ${AKT.durH(s.hours)} (по данным сейчас)` : '';
      const res = lost != null && lost > 0.005 ? `медь потеряна: ≈ ${f2(lost)} т Cu, ${esc(AKT.approx(AKT.usdPerH(lost)))}` : (hold ? 'поэтому медь не потеряна, но запас времени стал меньше' : 'на меди это не видно, но время потеряно');
      cost = `<p>Цена ошибки: пока вызывали не того, прошло ≈ ${AKT.fmt(delay * 60)} мин (допущение: 20–40 мин на переадресацию). ${hold ? hold + ', ' : ''}${res}. <span class="note">≈ — оценка на модели.</span></p>`;
    }
    return `<div class="tr-res ${ok ? 'ok' : 'bad'}"><b>${ok ? '✔ Верно' : '✖ Не то'}</b> — вы выбрали: ${esc(pick)}. Правильно: <b>${esc(d.right)}</b>.<p>${esc(d.why)}</p>${cost}</div>`;
  };
  AKT.views.train = {
    build(stage) {
      const d = doc(stage, 'train');
      d.innerHTML = `<h2>Тренировка</h2>
<p class="lead">Учебная беда, вы выбираете, кого звать, двойник оценивает выбор. Пока режим включён, вокруг экрана рамка «ТРЕНИРОВКА», а любые «Позвать» и «Не сейчас…» на всех экранах остаются учебными: они <b>не пишутся в журнал и не попадают в отчёты</b> смены и сравнения.</p>
<div class="tr-bar"><button type="button" id="tr-toggle"></button> <span class="note" id="tr-state"></span></div>
<h3>Учебная беда</h3><div id="tr-drill"></div>
<h3>Разобрать текущую беду №1</h3><div id="tr-live"></div>
<h3>Учебный журнал</h3><div id="tr-log"></div>
<p class="note">Учебный журнал хранится только в этом браузере. Правильный вызов — по правилу «кого звать» самого стенда (таблица в модуле очереди бед), числа — живые данные фабрики. Переадресация 20–40 мин — допущение.</p>`;
      this.state = { drill: 0, picked: '' };
      document.getElementById('tr-toggle').addEventListener('click', () => Train.set(!Train.on()));
    },
    update() {
      const on = Train.on();
      const tg = document.getElementById('tr-toggle'); if (tg) { tg.textContent = on ? 'Выключить тренировку' : 'Включить тренировку'; tg.className = on ? '' : 'primary'; }
      setHtml('tr-state', on ? 'Режим включён: рамка на всех экранах.' : 'Режим выключен: вызовы на других экранах настоящие.');
      const S = this.state, d = DRILLS[S.drill];
      const s = trainSvc(d);
      const opts = ROLES.map(r => `<button type="button" data-role="${esc(r)}" class="${S.picked === r ? 'on' : ''}">${esc(r)}</button>`).join(' ');
      const tabs = DRILLS.map((x, i) => `<button type="button" data-drill="${i}" class="${i === S.drill ? 'on' : ''}">${esc(x.title)}</button>`).join(' ');
      setHtml('tr-drill', `<div class="tr-tabs">${tabs}</div><div class="tr-case"><p><b>${esc(d.title)}</b> <span class="lbl-est">учебная беда</span></p><p>${esc(d.story(s.n || 1))}</p>
<p class="note">Сейчас на фабрике: ${s.n && s.hours != null ? `склад линии ${s.n} хватит на ≈ ${esc(AKT.durH(s.hours))}; ` : ''}${s.cu != null ? `линия даёт ${f1(s.cu)} т Cu/ч.` : ''}</p>
<p>Кого звать?</p><div class="tr-opts">${opts}</div>${S.picked ? trainResult(d, S.picked) : ''}</div>`);
      this.bind('tr-drill');
      const top = AKT.issues()[0];
      if (!top) setHtml('tr-live', '<p class="empty dash">Сейчас бед нет — разбирать нечего. Запустите учебный сценарий в «Пульте модели» или решите учебную беду выше.</p>');
      else {
        const right = AKT.roleFirst(AKT.issueRole(top)), L = this.state;
        setHtml('tr-live', `<p><b>${esc(AKT.issueTitle(top))}</b> — ${esc(AKT.nameRu(AKT.issueNode(top)))}. ${esc(AKT.issueMain(top).text || '')}</p>
<p>Кого звать?</p><div class="tr-opts">${ROLES.map(r => `<button type="button" data-live="${esc(r)}" class="${L.livePick === r ? 'on' : ''}">${esc(r)}</button>`).join(' ')}</div>
${L.livePick ? `<div class="tr-res ${L.livePick === right ? 'ok' : 'bad'}"><b>${L.livePick === right ? '✔ Совпало с советом двойника' : '✖ Двойник советует иначе'}</b> — вы выбрали: ${esc(L.livePick)}; двойник: <b>${esc(right || '—')}</b>.<p>${esc(cleanTxt(AKT.issueWhy(top) || ''))}</p></div>` : ''}`);
        this.bind('tr-live');
      }
      const lg = Train.log().slice().reverse();
      setHtml('tr-log', lg.length ? `<table class="kv"><tr><th>Когда</th><th>Беда</th><th>Выбрано</th><th>Правильно</th><th></th></tr>${lg.map(e => `<tr><td>${esc(new Date(e.at).toLocaleTimeString('ru-RU'))}</td><td>${esc(e.title)}</td><td>${esc(e.pick)}</td><td>${esc(e.right)}</td><td>${e.ok ? '✔' : '✖'}</td></tr>`).join('')}</table><button type="button" id="tr-clear">Очистить учебный журнал</button> <span class="note">верных: ${lg.filter(e => e.ok).length} из ${lg.length}</span>` : '<p class="empty dash">Пока ни одного учебного вызова.</p>');
      const cl = document.getElementById('tr-clear'); if (cl && !cl._b) { cl._b = 1; cl.addEventListener('click', () => { Train.clear(); this.update(); }); }
    },
    bind(id) {
      const root = document.getElementById(id);
      root.querySelectorAll('[data-drill]').forEach(b => { if (b._b) return; b._b = 1; b.addEventListener('click', () => { this.state.drill = Number(b.dataset.drill); this.state.picked = ''; this.update(); }); });
      root.querySelectorAll('[data-role]').forEach(b => { if (b._b) return; b._b = 1; b.addEventListener('click', () => { const d = DRILLS[this.state.drill]; this.state.picked = b.dataset.role; Train.record({ title: d.title, pick: b.dataset.role, right: d.right, ok: b.dataset.role === d.right }); this.update(); }); });
      root.querySelectorAll('[data-live]').forEach(b => { if (b._b) return; b._b = 1; b.addEventListener('click', () => { const top = AKT.issues()[0]; const right = top ? AKT.roleFirst(AKT.issueRole(top)) : ''; this.state.livePick = b.dataset.live; Train.record({ title: top ? AKT.issueTitle(top) : 'беда', pick: b.dataset.live, right, ok: b.dataset.live === right }); this.update(); }); });
    },
  };

  /* ================================================================== journal with search and CSV (feature 16) */
  const JR_RU = { call: 'позвали', snooze: 'отложили', auto_call: 'автовызов', remind: 'напомнили', next: 'позвали следующего', late: 'двойник: не прибыл', arrived: 'двойник: прибыли', resolved: 'беда устранена' };
  const escRows = () => ((AKT.val('mod-priority', 'escalations') || {}).log || []).filter(e => e && (e.action === 'late' || e.action === 'arrived' || e.action === 'resolved')).map(e => ({ sim_time: e.t, action: e.action, issue: e.issue, role: '', text: e.text, run: AKT.run }));
  const jrNode = r => { const i = r.issue || ''; if (!i) return ''; const t = AKT.things[i]; return t && (!r.run || r.run === AKT.run) ? AKT.nameRu(AKT.issueNode(i) || i) : (/^issue-(\d+)$/.test(i) ? 'беда ' + i.slice(6) : i); };
  AKT.views.journal = {
    build(stage) {
      const d = doc(stage, 'journal');
      d.innerHTML = `<h2>Журнал смены</h2>
<p class="lead">Все вызовы, отсрочки и напоминания диспетчера и двойника. Поиск по тексту, фильтр по действию, выгрузка таблицы в файл CSV (разделитель «;», кодировка UTF-8 — открывается в Excel). Учебные вызовы режима «Тренировка» сюда не попадают.</p>
<div class="jr-ctl"><label>Поиск <input type="search" id="jr-q" placeholder="узел, роль, комментарий"></label>
<label>Действие <select id="jr-a"><option value="">все</option>${Object.keys(JR_RU).map(k => `<option value="${k}">${JR_RU[k]}</option>`).join('')}</select></label>
<label>За <select id="jr-r"><option value="12h">12 ч</option><option value="24h" selected>24 ч</option><option value="72h">3 сут</option><option value="168h">7 сут</option></select></label>
<label><input type="checkbox" id="jr-run" checked> только этот прогон</label>
<button type="button" class="primary" id="jr-csv">Выгрузить CSV</button> <span class="note" id="jr-cnt"></span></div>
<div id="jr-tab"></div><p class="note">Время — модель (ЧЧ:ММ); журнал хранится в InfluxDB, строки пишет интерфейс («Позвать», «Не сейчас…», «Напомнить») и модуль очереди бед (двойник: не прибыл / прибыли).</p>`;
      this.rows = []; this.range = '24h';
      const upd = () => this.render();
      ['jr-q', 'jr-a', 'jr-run'].forEach(id => document.getElementById(id).addEventListener('input', upd));
      document.getElementById('jr-r').addEventListener('change', e => { this.range = e.target.value; this.load(); });
      document.getElementById('jr-csv').addEventListener('click', () => this.csv());
      this.load();
    },
    async load() {
      try { const d = await AKT.get('/api/journal?range=' + this.range); this.rows = d.rows || []; } catch (e) { this.rows = AKT.journal || []; }
      this.render();
    },
    all() {
      return this.rows.concat(escRows()).sort((a, b) => (b.sim_time || 0) - (a.sim_time || 0));
    },
    filtered() {
      const q = (document.getElementById('jr-q').value || '').trim().toLowerCase(), a = document.getElementById('jr-a').value, mine = document.getElementById('jr-run').checked;
      return this.all().filter(r => (!mine || !r.run || r.run === AKT.run) && (!a || r.action === a)
        && (!q || [jrNode(r), r.role, r.text, JR_RU[r.action], r.issue].join(' ').toLowerCase().includes(q)));
    },
    render() {
      if (!document.getElementById('jr-tab')) return;
      const rows = this.filtered();
      const head = '<tr><th>Время</th><th>Действие</th><th>Беда, узел</th><th>Кто</th><th>Комментарий</th></tr>';
      setHtml('jr-tab', rows.length ? `<table class="kv">${head}${rows.map(r => `<tr><td class="n">${AKT.clock(r.sim_time)}</td><td>${esc(JR_RU[r.action] || r.action)}</td><td>${esc(jrNode(r))}</td><td>${esc(r.role ? AKT.roleAcc(r.role) : '')}</td><td>${esc(cleanTxt(r.text))}</td></tr>`).join('')}</table>` : '<p class="empty dash">Записей по этим условиям нет.</p>');
      setHtml('jr-cnt', `${fmt(rows.length)} из ${fmt(this.all().length)} записей`);
    },
    update() { this.render(); },
    csv() {
      const rows = this.filtered();
      const q = v => { const s = String(v == null ? '' : v).replace(/\r?\n/g, ' '); return /[";\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
      const lines = [['время модели', 'минута модели', 'действие', 'беда', 'узел', 'кто', 'комментарий', 'прогон'].join(';')]
        .concat(rows.map(r => [AKT.clock(r.sim_time), r.sim_time == null ? '' : Math.round(r.sim_time), JR_RU[r.action] || r.action, r.issue || '', jrNode(r), r.role ? AKT.roleAcc(r.role) : '', cleanTxt(r.text), r.run || ''].map(q).join(';')));
      const blob = new Blob(['\ufeff' + lines.join('\r\n') + '\r\n'], { type: 'text/csv;charset=utf-8' });
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `zhurnal-smeny-${(AKT.run || 'run').replace(/[^A-Za-z0-9_-]/g, '')}.csv`;
      document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
      AKT.toast(`Выгружено ${rows.length} записей в файл ${a.download}`);
    },
  };

  /* ================================================================== shift report (feature 17) */
  const reportHtml = () => {
    const t = AKT.simTime, FC = AKT.fc;
    const s0 = t != null ? FC.shiftStart(t) : null;
    const cuNow = FC.shiftNow(), k = FC.cu('shift');
    const sum = f => { const a = AKT.num('line-1', f), b = AKT.num('line-2', f); return a == null || b == null ? null : a + b; };
    const usd = cuNow != null ? cuNow * AKT.payable() * AKT.cuPrice() : null;
    const issues = AKT.issues();
    const lossH = issues.filter(AKT.lossNow).reduce((s, i) => s + (AKT.num(i, 'loss_usd_h') || 0), 0);
    const jr = (AKT.journal || []).concat(escRows()).filter(r => (!r.run || r.run === AKT.run) && (s0 == null || (r.sim_time || 0) >= s0 - 1)).sort((a, b) => (a.sim_time || 0) - (b.sim_time || 0));
    const dec = AKT.val('mod-priority', 'decisions') || {};
    const suspLabels = n => AKT.evidenceItems(n).filter(i => i.suspect || i.old).map(i => i.label + (i.suspect ? ' (под подозрением)' : ' (данные давно)'));
    const rows = issues.map(n => `<tr><td>${AKT.rankNo(n) != null ? fmt(AKT.rankNo(n)) : '—'}</td><td>${esc(AKT.issueTitle(n))}<br><span class="p-sub">${esc(AKT.nameRu(AKT.issueNode(n)))}</span>${suspLabels(n).length ? `<br><span class="p-sub">Данные под вопросом: ${esc(suspLabels(n).join(', '))}</span>` : ''}</td><td>${esc(AKT.stRu(AKT.st(n), n))}</td><td class="n">${String(AKT.val(n, 'safety_class') || '') === 'S0' ? 'опасно' : AKT.num(n, 'loss_usd_h') > 0 ? '≈ ' + esc(AKT.usd(AKT.num(n, 'loss_usd_h'))) + '/ч' : '—'}</td><td>${esc(AKT.roleAcc(AKT.issueRole(n)))}</td></tr>`).join('');
    const dev = String(AKT.val('mod-priority', 'deviations_text') || '').split('\n').filter(Boolean).map(x => `<li>${esc(cleanTxt(x))}</li>`).join('');
    const sil = String(AKT.val('mod-losses', 'silent_text') || '').split('; ').filter(Boolean).map(x => `<li>${esc(cleanTxt(x))}</li>`).join('');
    const hd = String(AKT.val('mod-priority', 'handover_draft_text') || '').split('\n').filter(Boolean).slice(1).map(x => `<li>${esc(cleanTxt(x))}</li>`).join('');
    const calls = jr.filter(r => r.action === 'call' || r.action === 'auto_call' || r.action === 'next');
    const tbl = (h, body) => `<table class="kv">${h}${body}</table>`;
    let n = 0;
    const sec = (title, body) => (body ? `<h3>${++n}. ${title}</h3>${body}` : '');
    const review = String(AKT.val('mod-priority', 'review_text') || '');
    const floodLine = String(AKT.val('mod-priority', 'alarm_flood_text') || '');
    return `<article class="report">
<header><h2>Отчёт смены — Актогай, сульфидная часть</h2>
<p>Смена ${s0 != null ? AKT.clock(s0) + '–' + AKT.clock(s0 + 720) : '—'} времени модели · составлен в ${AKT.clockDay(t)} · прогон ${esc(AKT.run || '—')}${AKT.scenario() ? ' · учебный сценарий: ' + esc(AKT.scenarioRu(AKT.scenario())) : ''}${AKT.num('water', 'winter') === 1 ? ' · зима' : ''}</p></header>
${Train.on() ? '<p class="rp-warn">Отчёт построен в режиме тренировки: учебные вызовы в него не входят.</p>' : ''}
${sec('Медь и деньги', tbl('<tr><th>Показатель</th><th>Значение</th><th>Метка</th></tr>',
      `<tr><td>Медь в концентрате за смену (сейчас)</td><td class="n">${cuNow == null ? '—' : f1(cuNow)} т</td><td>измерение: счётчики линий</td></tr>
<tr><td>Прогноз к концу смены (${k ? AKT.clock(k.endAt) : '—'})</td><td class="n">${k ? '≈ ' + fmt(k.end) + ' т (' + fmt(k.lo) + '–' + fmt(k.hi) + ')' : '—'}</td><td>оценка на модели, коридор</td></tr>
<tr><td>Ориентир — 2025 г. в среднем (с остановками)</td><td class="n">${k ? fmt(k.plan) + ' т' : '—'}</td><td>факт KAZ Minerals, расчёт (не плановое задание)</td></tr>
<tr><td>Стоимость меди смены</td><td class="n">${usd == null ? '—' : '≈ ' + esc(AKT.money(usd))}</td><td>т × 95,5 % × LME ${fmt(AKT.cuPrice())} $/т</td></tr>
<tr><td>Электроэнергия / вода (забор)</td><td class="n">${sum('cum_mwh') == null ? '—' : fmt(sum('cum_mwh'))} МВт·ч / ${sum('cum_m3') == null ? '—' : fmt(sum('cum_m3'))} м³</td><td>измерение: счётчики линий</td></tr>
<tr><td>Теряем сейчас по открытым бедам</td><td class="n">${lossH > 0 ? '≈ ' + esc(AKT.usd(lossH)) + '/ч' : 'нет'}</td><td>оценка на модели</td></tr>`))}
${sec('Беды', issues.length ? tbl('<tr><th>№</th><th>Что и где</th><th>Статус</th><th>Цена</th><th>Кого звать</th></tr>', rows) : '<p>Открытых бед нет.</p>')}
${sec('Тревоги и беды', floodLine ? `<p>${esc(cleanTxt(floodLine))}</p>` : '')}
${sec('Кого звали и что решили', jr.length ? tbl('<tr><th>Время</th><th>Действие</th><th>Беда</th><th>Кто</th><th>Комментарий</th></tr>', jr.map(r => `<tr><td class="n">${AKT.clock(r.sim_time)}</td><td>${esc(JR_RU[r.action] || r.action)}</td><td>${esc(jrNode(r))}</td><td>${esc(r.role ? AKT.roleAcc(r.role) : '')}</td><td>${esc(cleanTxt(r.text))}</td></tr>`).join('')) + (review ? `<p>${esc(cleanTxt(review))}</p>` : '') + (dec.regret_cu != null && dec.regret_cu > 0 ? `<p>Разница между вашим порядком и лучшим по модели: ≈ ${f2(dec.regret_cu)} т Cu (${esc(AKT.approx(dec.regret_usd))}).</p>` : '') : '<p>В этой смене действий ещё не было.</p>' + (review ? `<p>${esc(cleanTxt(review))}</p>` : ''))}
${sec('Отклонения (хроника)', dev ? `<ul>${dev}</ul>` : '')}${sec('Тихие перерасходы', sil ? `<ul>${sil}</ul>` : '')}
${sec('Что передать следующей смене', hd ? `<ul>${hd}</ul>` : '')}
<footer><p class="note">≈ — расчёт модели, не измерение; (д) — допущение. Данные: Ditto и InfluxDB. Двойник советует, решение за диспетчером. Печать: Ctrl+P, «Сохранить как PDF».</p></footer></article>`;
  };
  AKT.views.report = {
    build(stage) {
      const d = doc(stage, 'report');
      d.innerHTML = `<h2>Отчёт смены</h2>
<p class="lead noprint">Одна кнопка: отчёт собирается из живых данных (медь, потери, беды, решения, кого звали) и печатается или сохраняется в PDF.</p>
<p class="noprint"><button type="button" class="primary" id="rp-print">Печать отчёта смены</button> <button type="button" id="rp-refresh">Обновить данные</button></p><div id="rp-doc"></div>`;
      document.getElementById('rp-print').addEventListener('click', () => { this.update(true); window.print(); });
      document.getElementById('rp-refresh').addEventListener('click', () => this.update(true));
      AKT.fc && AKT.fc.loadSeries();
    },
    /* the report is a snapshot: it is rebuilt on request (and once when the page opens), not under the cursor */
    update(force) { if (force || !this.built) { this.built = true; setHtml('rp-doc', reportHtml()); } },
  };

  /* ================================================================== economics (feature 21) */
  AKT.views.economics = {
    build(stage) {
      const d = doc(stage, 'economics');
      d.innerHTML = `<h2>Экономика: что даёт двойник</h2>
<p class="lead">Сколько меди и денег сберегает двойник против работы «как сейчас». Всё — <b>оценка на модели</b>, не замер на фабрике. Числа берутся из опыта «вкл/выкл» от 24.10.2026 на 100 парных сменах с симметричной базой — двойник добавлен к людям и не видит громкую беду раньше них (файл <code>exp23.json</code>, VALIDATION.md 8.6–8.8 и 8.17), а не из этой страницы.</p>
<div id="ec-big"><p class="empty dash">Загружаю итог опыта…</p></div><h3>Главное сравнение и повтор</h3><div id="ec-main"></div>
<h3>Из чего складывается</h3><div id="ec-parts"></div><h3>Сколько стоит задержка вызова</h3><div id="ec-delay"></div>
<h3>Новичок и двойник</h3><div id="ec-novice"></div>
<h3>От чего зависит (торнадо)</h3><div id="ec-tor"></div><h3>Этот прогон стенда</h3><div id="ec-run"></div>
<h3>Оговорки</h3><div id="ec-cav"></div>`;
      AKT.exp23.load(() => this.update());
    },
    update() {
      const X = AKT.exp23, j = X.data, tw = X.twin();
      const price = AKT.payable() * AKT.cuPrice();
      const grade = (() => { const a = AKT.num('flot-1', 'feed_cu'), b = AKT.num('flot-2', 'feed_cu'); return a != null && b != null ? (a + b) / 2 : (a ?? b); })();
      const rec = (() => { const a = AKT.num('line-1', 'recovery'), b = AKT.num('line-2', 'recovery'); return a != null && b != null ? (a + b) / 2 : (a ?? b); })();
      const ore = t => grade && rec ? t / ((grade / 100) * (rec / 100)) : null;
      if (tw) {
        const ci = tw.ci95_mean_bca, m = tw.mean, mm = j.main;
        const col = (title, mult, note) => `<div class="ec-card"><div class="ec-t">${title}</div><div class="ec-v">+${f2(m * mult)} т Cu</div><div class="ec-s">≈ ${esc(AKT.money(m * mult * price))}</div><div class="ec-n">${note}</div></div>`;
        setHtml('ec-big', `<div class="ec-row">${col('За смену (12 ч)', 1, `среднее по ${fmt(tw.n)} сменам; 95 % ДИ +${f2(ci[0])}…+${f2(ci[1])} т — нижняя граница +${f2(ci[0])} т ≈ ${esc(AKT.money(ci[0] * price))}${mm.without_top ? `; медиана +${f2(mm.median)}, без смены-выброса (seed ${mm.top_seed}) +${f2(mm.without_top.mean)}` : ''}`)}${col('За сутки (2 смены)', 2, 'расчёт: 2 × среднее за смену')}${col(`За опыт (${fmt(tw.n)} смен)`, tw.n, `сумма опыта; лучше в ${fmt(100 * (tw.p_plus || 0))} % смен, хуже — в ${fmt(100 * (tw.p_minus || 0))} %`)}
<div class="ec-card"><div class="ec-t">Простой</div><div class="ec-v">−${fmt(Math.abs(mm.down_min.mean))} мин</div><div class="ec-s">за смену, обе линии</div><div class="ec-n">95 % ДИ ${fmt(Math.abs(mm.down_min.ci95[1]))}…${fmt(Math.abs(mm.down_min.ci95[0]))} мин</div></div>
<div class="ec-card"><div class="ec-t">Энергия</div><div class="ec-v">−${fmt(Math.abs(mm.kwh_per_t_cu.mean))} кВт·ч</div><div class="ec-s">на т Cu</div><div class="ec-n">95 % ДИ ${fmt(Math.abs(mm.kwh_per_t_cu.ci95[1]))}…${fmt(Math.abs(mm.kwh_per_t_cu.ci95[0]))}</div></div></div>
<p class="note">$ = т Cu × 95,5 % оплаты × LME ${fmt(AKT.cuPrice())} $/т (цена на 15.10.2026; диапазон 10–15 тыс. $/т) — без затрат на ремонт и работу людей. В опыте $ посчитаны по ценам модели: ≈ $${fmt(mm.usd.mean / 1000, 1)} тыс. за смену. Текущий прогон стенда — ниже.</p>`);
        setHtml('ec-main', X.mainTable() + X.worse(), false);
        const orePerShift = ore(m);
        setHtml('ec-parts', `${X.detectOrder()}<p>Для масштаба: ${f2(m)} т меди — это ≈ ${orePerShift == null ? '—' : fmt(orePerShift)} т руды, переработанной впустую при содержании ${grade == null ? '—' : f2(grade)} % и извлечении ${rec == null ? '—' : f1(rec)} % [расчёт: т Cu ÷ (содержание × извлечение)]. Из-за меньшего простоя расход энергии на т Cu ниже; доля выпуска и эквивалент в п.п. извлечения — в VALIDATION.md, раздел 8.8.</p>${X.co2()}`, false);
        setHtml('ec-delay', X.delay(), false);
        setHtml('ec-novice', X.novice(), false);
        setHtml('ec-tor', X.tornado(), false);
      } else {
        ['ec-main', 'ec-parts', 'ec-delay', 'ec-novice', 'ec-tor'].forEach(id => setHtml(id, AKT.exp23.missing()));
      }
      const res = AKT.shiftResult();
      setHtml('ec-run', res ? `<p>Сравнение копий текущего прогона:</p>${AKT.shiftTable(res)}` : `<p class="note">${AKT.noCompareText()} Сейчас в этом прогоне двойник советует: открытых бед ${fmt(AKT.issues().length)}, потери по ним ${AKT.issues().some(AKT.lossNow) ? '≈ ' + esc(AKT.usd(AKT.issues().filter(AKT.lossNow).reduce((a, i) => a + (AKT.num(i, 'loss_usd_h') || 0), 0))) + '/ч' : 'нет'}.</p>`);
      const low = tw ? f2(tw.ci95_mean_bca[0]) : '—';
      setHtml('ec-cav', `<ul class="cav"><li><b>Оценка на модели, не замер.</b> Фабрика с двойником и без него в одно время не работала; выгода — разница двух прогонов модели с одними бедами и шумом.</li>
<li><b>Нижняя граница и выброс.</b> Для решений брать нижний край интервала (+${low} т за смену), не среднее. Среднее тянет одна смена (seed ${j && j.main.top_seed ? j.main.top_seed : '—'}: две защиты на одном КИПиА в одну минуту, двойник переставляет вызовы); медиана и среднее без неё — выше в этой строке. На повторе с новыми seed 2001–2100: ${j ? ci2(j.replication.cu.ci95) : '—'}.</li>
<li><b>Беды заданы опытом.</b> В каждой смене 2–3 беды из библиотеки (в среднем ${j ? fmt(j.main.troubles_per_shift, 2) : '—'}); реальная частота и размер бед на Актогае не опубликованы [допущение]. Годовое число из этой выгоды получить нельзя — это масштаб, не прогноз.</li>
<li><b>Допущения опыта (симметричная база, VALIDATION 8.17):</b> громкую беду двойник видит в ту же минуту, что смена (тревога через 5–15 мин; урезание сети и перефутеровка — через 10 мин) [допущение; Errington 2005, с. 3: у аварий, видимых по тревоге, разницы нет]; находку засора циклона и недодачи собирателя задаёт измерение модуля (медианы 95 и 110 мин) плюс чтение карточки 5–15 мин [допущение]; твёрдую руду «как сейчас» узнаёт при выемке (≈ 2 ч) или только на SAG (≈ 4 ч) — граница решает результат, оба края показаны выше; совет по тихой беде ждёт человека 30 мин, смена выполняет советы полностью. Торнадо и цена часа задержки посчитаны на прежней базе (<code>--twin-human none</code>).</li>
<li><b>Новичок задан числами других отраслей.</b> Время увидеть беду ×1,66 — лабораторный макет [аналог]; промахи диагноза и шага — симулятор атомной станции, 20 и 17 наблюдений диагноза [аналог]; множитель стресса — THERP; число шагов и цена промаха — [допущение]. Это оценка на модели, а не вывод о людях Актогая; при нижней границе параметров цена неопытности не отличима от нуля. Проверка — журналы реальных смен.</li>
<li><b>Не учтено:</b> затраты на ремонт, ложные вызовы, оплата труда, цена обучения; считается только медь и энергия/вода по ценам стенда.</li>
<li><b>Прежние результаты.</b> Опыт 22.10.2026 с прежней библиотекой бед давал +1,26 т Cu за смену [+1,06; +1,52], опыт 24.10.2026 на прежней несимметричной базе (двойник видит громкую беду в её начале) +1,07 [+0,89; +1,31]; оба сохранены как история и главными не считаются.</li>
<li>Метки: ≈ — расчёт модели; (д) — допущение; цена меди — факт LME; доля оплаты 95,5 % — расчёт по отчётам KAZ Minerals 2023–2025 (0,9549–0,9552).</li></ul>`);
    },
  };
  const ci2 = a => `+${f2(a[0])}…+${f2(a[1])} т`;

  /* ================================================================== how to check (feature 22) */
  const CLAIMS = [
    ['Модель повторяет итоги 2025 года: переработку, энергию SAG, извлечение', 'calib', 'Калибровка → таблица «подгонка 2025» (модель / отчёт / отклонение)', 'KAZ Minerals, Q4 2025, с. 3'],
    ['Модель проверена на 2024 и 2023 годах без подгонки, и промах 2024 года показан как есть', 'calib', 'Калибровка → «проверка 2024», «проверка 2023»: извлечение 2024 г. вне допуска', 'KAZ Minerals, Q4 2024, с. 3'],
    ['Модель проверена по кварталам 2018–2024, ошибки показаны', 'calib', 'Калибровка → «Проверка по кварталам»: график и таблица со ссылкой на отчёт каждого квартала', 'квартальные отчёты KAZ Minerals (ссылки в таблице)'],
    ['Двойник сберегает медь за смену против работы «как сейчас»: число, интервал и оговорки', 'economics', 'Экономика → большие числа, интервал и оговорки; Калибровка → «очередь по $ против очереди по громкости»', 'опыт на 100 парных сменах, оценка на модели'],
    ['Баланс меди сходится: питание = концентрат + хвосты', 'copper', 'Путь меди → «Баланс меди» (невязка по строкам и по счётчикам за 2 ч)', 'признаки вещей в Ditto'],
    ['Забор воды на тонну руды близок к факту KAZ Minerals (0,60 м³/т)', 'copper', 'Путь меди → «Баланс воды» (с оговоркой: интенсивность забора по группе)', 'страница Water на kazminerals.com'],
    ['Остановка карьера — беда «Карьер (останов)» по линиям: часы до остановки SAG, кого звать, чек-лист и закрытие', 'queue', 'Пульт модели → «Остановка карьера» → Все беды; карточка беды → «Подробнее» (что делать, закроется)', 'ПЭК, с. 10; сценарий pitstop'],
    ['Метель и гололёд: ограничить движение — беда S0 «Зимняя дорога» идёт первой; кого звать: горный диспетчер → начальник смены карьера → дорожная служба; рядом цена решения (откатка медленнее). Зима теперь влияет на карьер, а не на переработку', 'queue', 'Пульт модели → «Метель и гололёд на откатке» → Все беды; карточка беды → «Подробнее» (измерения и возраст данных); Изнутри → Среда и данные', 'KAZ Minerals ESG «Enhancing winter safety at Aktogay» (риск назван, цифр нет); пороги видимости и сцепления — допущение; сценарий icy'],
    ['Усталость водителя (сценарий, допущение) — беда S0 с номером машины HT141; источник датчика и случаев не подтверждён, поэтому это только сценарий с меткой «допущение»', 'queue', 'Пульт модели → «Усталость водителя (допущение)» → Все беды', 'НЕ ПОДТВЕРЖДЕНО (страницы CAT не открылись); перечень техники 29.02.2024; сценарий fatigue'],
    ['Канатирование циклонов и перегрузка шаровой — беда с ценой: циркулирующая нагрузка, нагрузка шаровой, P80; кого звать — оператор пульта измельчения, затем металлург; через 1,5 ч без решения флотация теряет ещё ≈ 3 п.п.', 'queue', 'Пульт модели → «Канатирование циклонов» → Все беды; Изнутри → Фабрика (гидроциклоны, шаровые)', 'CiDRA с Kennecott, Comminution 2014, с. 12; CiDRA, Centinela, с. 3 (≈ 6 ч); пороги — допущение; сценарий roping:1'],
    ['Датчик под подозрением и возраст данных — в карточке беды у каждого измерения возраст данных; pH-метр: ручная проба против онлайн-показания, онлайн держится на уставке', 'queue', 'Пульт модели → «pH-метр врёт» → карточка беды → «Подробнее» → «Измерения и возраст данных»; Изнутри → Среда и данные', 'ABB, pH/ORP во флотации меди, с. 3; Metso Metrics, с. 8 (маркетинг вендора); сценарий phdrift:1'],
    ['Неравномерное питание ВВД линии 2 — перекос валков, разница мощности двух приводов, металлодетектор; узел ВВД виден на «Пути меди» (красный при металле или перекосе от 6 %)', 'copper', 'Пульт модели → «Неравномерное питание ВВД линии 2»; Путь меди → линия 2, узел «ВВД (POLYCOM)»', 'Metso, блог о перекосе ВВД, 31.01.2022 (аналог); International Mining, 25.02.2021 (POLYCOM 1 061 т/ч); сценарий hpgr:2'],
    ['Руда сменилась — режим старый: твёрдая или окисленная партия — металлург смены в списке «кого звать», уведомление в карточке беды («Также сообщить»)', 'ore', 'Пульт модели → «Твёрдая руда» → Все беды; Изнутри → Руда (забои, что идёт на фабрику)', 'KAZ Minerals, H1 2025, с. 5: Бозшаколь 78,5 → 73,8 % — пример влияния минералогии, не потеря от задержки; сценарии hard:1, oxide:1'],
    ['Замена брони дробилки — плановая остановка ≈ 60 ч: часы склада до остановки SAG и цена после конца склада, недодроблено по паспорту дробилки и по аналогу', 'queue', 'Пульт модели → «Замена брони дробилки 1» → Все беды; Прогнозы → «Руда на складе»', 'Metso, La Caridad, 10.03.2023 (≈ 60 ч, 75–100 кт — другой рудник); ПЭК, с. 10; сценарий mantle:1'],
    ['Загрязнение масла экскаватора EX01 — тревога датчика на машине, в диспетчерскую она идёт, если подключена опция Global e-Service; отказ насоса через ≈ 8 ч после тревоги, если не вмешаться', 'queue', 'Пульт модели → «Загрязнение масла EX01» → Все беды; карточка вещи EX01 → показатели; Изнутри → Машины', 'Hitachi, проспект EX3600-6, с. 11; Abduazizov и др. 2026, с. 31 (≈ 70 % отказов гидросистем — загрязнение); сценарий oil'],
    ['Отказ экскаватора — недостача руды по линиям после выработки склада; кого звать — сменного механика карьера', 'queue', 'Пульт модели → «Загрязнение масла EX01» (без вмешательства через ≈ 11 ч) → Все беды', 'Вести Семей, 06.06.2024 (5 экскаваторов Hitachi, 2 700–3 700 т/ч); ремонт 57,45 ч — аналог PC3000'],
    ['Зазор безредукторного привода SAG сужается — тренд зазора, часы до отключения привода и цена остановки линии; пример предела ABB 12,5 мм, а не уставка; кого звать — дежурного КИПиА', 'queue', 'Сценарии → «Зазор привода SAG 1» → Все беды; 3D «Разобрать» → привод SAG', 'ABB, Remote diagnostic services for gearless mill drives, с. 18; сценарий gmd:1; tests/test_tier_t.py'],
    ['Перегрев ролика конвейера — температура подшипника, часы до остановки ленты по риску возгорания; доля отказов роликов 3 % в год — допущение изготовителя; кого звать — механика ЦПД', 'queue', 'Сценарии → «Перегрев ролика конвейера 1» → Все беды; 3D «Разобрать» → лента', 'Zimroz, Król 2009; PPI CRP 047-01, с. 1; сценарий idler:1; tests/test_tier_t.py'],
    ['Колебания уровня во флотации — размах уровня ячеек и потеря извлечения в п.п. (величина — допущение); кого звать — дежурного КИПиА', 'queue', 'Сценарии → «Колебания уровня флотации 1» → Все беды; Участки → Флотация', 'ANDRITZ MPC, с. 10 (до 2 ч); Valmet 29.09.2026 (качественно); сценарий froth:1; tests/test_tier_t.py'],
    ['Момент граблин сгустителя — тревога и останов привода (40/80 % — пример учебного блога), потеря производительности до ≈ 60 % как на Оюу-Толгое; кого звать — механика фабрики', 'queue', 'Сценарии → «Момент граблин сгустителя 1» → Все беды; 3D «Разобрать» → сгуститель', 'Outotec, Thickening technologies, с. 10; 911Metallurgist; BCM NewsWire 17.10.2014; сценарий rake:1; tests/test_tier_t.py'],
    ['Ткань фильтра слепнет — цикл фильтрации длиннее, производительность пресса ниже; замена «от 30 минут» — лучший случай изготовителя; кого звать — механика фабрики', 'queue', 'Сценарии → «Ткань фильтра слепнет 1» → Все беды; Участки → Сгущение и фильтрация', 'Metso, Larox PF, с. 4 и 8; сценарий cloth:1; tests/test_tier_t.py'],
    ['Кавитация насоса питания циклонов — напор падает, подача линии ниже; зоны вибрации ISO 10816 к пульповым насосам не применяются', 'queue', 'Сценарии → «Кавитация насоса циклонов 1» → Все беды; 3D «Разобрать» → насос', 'Weir, Warman AH, с. 7 и Technical Bulletin 36, с. 3 (случаи вендора); ISO 10816-7, §1; сценарий slurry:1; tests/test_tier_t.py'],
    ['Перегрев тормозов самосвала HT141 (CAT 793D, 236 т) — беда S0, порог с выдержкой времени; числа CAT не использованы, пороги — допущения; кого звать — сменного механика', 'queue', 'Сценарии → «Перегрев тормозов самосвала HT141» → Все беды', 'KAZ Minerals, AR 2020, с. 61; Peterson CAT 793F (аналог); сценарий brake; tests/test_tier_t.py'],
    ['Натяжение гусениц экскаватора EX3600 — давление растёт до автостопа хода; экскаватор не переходит к следующему забою; уровень автостопа не опубликован', 'queue', 'Сценарии → «Натяжение гусениц EX01» → Все беды; карточка вещи EX01', 'Hitachi, проспект EX3600-6, с. 7; сценарий track; tests/test_tier_t.py'],
    ['Новичок задан числами открытых работ (время увидеть ×1,66, промахи диагноза и шага): цена неопытности в т Cu и до какого уровня двойник поднимает новичка', 'economics', 'Экономика → «Новичок и двойник»; Калибровка → главное сравнение, строки про новичка', 'arXiv 2509.06657; NRC ML24151A634 (SHEEP); THERP, EPRI/NRC ML19212A732; VALIDATION.md 8.9–8.10, оценка на модели'],
    ['Смены, где двойник хуже «как сейчас»: какие seed, какие беды и почему', 'economics', 'Экономика → под таблицей главного сравнения', 'sim/data/experiment_24.json (worse_shifts); VALIDATION.md 8.11, 8.17'],
    ['У каждой беды в карточке есть цена часа задержки вызова по опыту на модели', 'queue', 'Все беды → карточка беды → «Подробнее» → «Цена часа задержки вызова по опыту»', 'sim/data/exp23/delaykind_*.json; VALIDATION.md 8.8'],
    ['Крупный помол оценён по наклону Бозшаколя (диапазон, не одно число); в модели стенда наклон другой, это сказано в карточке', 'queue', 'Пульт модели → «Канатирование циклонов» (после него P80 растёт) → карточка беды «помол крупнее нормы»', 'Satbayev University, регрессия по суточным данным Бозшаколя: −1,95 п.п. на +10 мкм, лаборатория 0,8–1,2; [аналог]'],
    ['Лавина тревог сводится к одной беде: события-тревоги смены → беды в очереди → одна на главном экране; ориентир ANSI/ISA-18.2', 'howto', 'Как проверить → «Лавина тревог и одна беда»; Отчёт смены → «Тревоги и беды»', 'modules/flood.py; tests/test_flood.py; нижняя оценка по состояниям узлов'],
    ['Энергия на т руды сверена с фактом KAZ Minerals; CO₂ двойника переведён из кВт·ч по коэффициенту из отчёта группы', 'calib', 'Калибровка → «Сверка с фактом KAZ Minerals»; Экономика → «Из чего складывается»', 'отчёт по устойчивому развитию 2024, с. 37 и 40; VALIDATION.md, раздел 4'],
    ['Если бед нет, в строке «Что сейчас» есть кнопка «Показать пример смены» (сценарий каталога «Две беды сразу»)', 'plan', 'Обзор → верхняя строка при «Бед нет»', 'tests/test_scenarios.py; aktogay/web/static/app.js'],
    ['Остановка ленты — беда «Конвейер стоит» (механик ЦПД); лента, стоящая без руды, бедой не считается', 'queue', 'Пульт модели → «Встал конвейер» → карточка беды → «Подробнее»', 'ПЭК, с. 18; Правила № 348, п. 12, 315, 316'],
    ['Окисленная линия: куча → SX-EW → катод — квартальный выпуск по отчётам (не замер); холодное выщелачивание — беда класса «деньги» с ценой по LME, кого звать — металлург смены', 'copper', 'Путь меди → «Окисленная руда»; Сценарии → «Холодное выщелачивание на куче» → Все беды; на плане у кучи (место — схема) подпись только при спаде', 'KAZ Minerals, 4 кв. 2024 и 4 кв. 2025, с. 3; sim/data/kaz_quarterly.csv; сценарий leachcold'],
    ['Остановка карьера доходит до фабрики через часы работы склада: в модели живая часть 40 кт на линию (≈ 3 ч полной загрузки, допущение); по ПЭК рабочий объём 163 кт ≈ 2 суток — две трактовки в VALIDATION 8.16', 'forecast', 'Прогнозы → «Руда на складе»; учебный сценарий «Остановка карьера» в Пульте модели', 'ПЭК ТОО «KAZ Minerals Aktogay» 2023–2024, с. 10'],
    ['Износ футеровки SAG прогнозируется, перефутеровка планируется за N суток', 'forecast', 'Прогнозы → «Футеровка мельниц SAG» (пунктир — прогноз)', 'отчёты KAZ Minerals: IV кв. 2023, III кв. 2025'],
    ['Прогноз меди до конца смены идёт пунктиром с коридором', 'plan', 'Обзор → плитка «Медь в концентрат»; Прогнозы → «Медь до конца смены и суток»', 'признаки Ditto + история InfluxDB'],
    ['У каждого числа есть метка: факт, вендор, аналог, допущение, расчёт, оценка на модели', 'legend', 'Обозначения (знаки и метки); карточка вещи → паспорт с источниками', 'aktogay/PARAMETERS.md'],
    ['Двойник знает, кого звать, и учитывает наряд-допуск', 'queue', 'Все беды → столбец «Кого звать»; карточка беды ① → цепочка ответственности', 'приказ МИР РК № 348, п. 12, 63'],
    ['Зима влияет на водный баланс, но не на переработку и извлечение', 'text', 'Пульт модели → сценарий «Зима»; метка «Зима» в шапке; Всё текстом → вещь water', 'KAZ Minerals, Q1 2019, с. 1'],
    ['Тариф на электроэнергию плоский 16 тг/кВт·ч; «пик/ночь» — только сценарий «что если»', 'queue', 'Все беды → строка «Тариф» под отклонениями', 'приказ МНЭ РК № 445 от 29.12.2017'],
    ['Все данные интерфейс берёт только из Ditto и InfluxDB', 'tree', 'Состав двойника → карточка любой вещи: «данные из Ditto, обновлено N с назад», сырой JSON', 'положение конкурса, п. 6.2'],
    ['Отчёты и журнал можно выгрузить', 'journal', 'Журнал с выгрузкой → «Выгрузить CSV»; Отчёт смены → «Печать»', '—'],
    ['Каждый сценарий запускается одной кнопкой по номеру прогона (seed); у каждого есть «что должно произойти» и «как проверить»', 'scenarios', 'Обучение и справка → Сценарии', 'aktogay/modules/scenarios.py; tests/test_scenarios.py'],
    ['Конструктор беды: узел, время и величина → команда в вещь control в Ditto, без кода', 'scenarios', 'Сценарии → «Конструктор беды»; команда видна в «Состав» → вещь control', 'sim/events.py (токен crusher:1@90=4.5)'],
    ['Смена с тремя бедами сразу: очередь выстраивается люди → экология → деньги', 'queue', 'Сценарии → «Смена с тремя бедами сразу» → Все беды', 'tests/test_scenarios.py::ThreeTroublesTest'],
    ['Повтор смены с двойником и без: две ленты времени (началась → заметили → позвали → прибыл → решено), разница в часах и т Cu', 'replay', 'Анализ → Повтор смены', 'sim/data/trial_n100.json, оценка на модели'],
    ['Экран механика: мои вызовы, работа (что, где, наряд, точки отключения, как проверить), статус; статус виден диспетчеру на карточке беды', 'mech', 'Экран механика (?view=mech); карточка беды ① → строка «Позвали … → принял … → на месте …»', 'tests/test_scenarios.py::MechanicTest'],
    ['Цена беды разложена на медь, энергию, реагенты и штрафы, и у каждой части видно, на чём она держится (факт, расчёт, допущение)', 'queue', 'Обзор → карточка беды → «Подробнее» → «Из чего складывается цена»', 'aktogay/PARAMETERS.md (метки строк)'],
    ['Кнопка «Сдать смену» появляется только за 60 мин до конца смены', 'handover', 'Шапка в 19:00–20:00 и 07:00–08:00 модели; Смена → Сдача смены', 'tests/test_scenarios.py::HandoverButtonTest'],
    ['Честная сводка меток параметров (факт, вендор, аналог, проект, расчёт, допущение) и список того, чего модель не умеет', 'calib', 'Калибровка → «На чём стоят числа модели», «Чего модель не умеет»', 'aktogay/PARAMETERS.md; VALIDATION.md, раздел 12.1'],
    ['Лёгкий режим диорамы включается сам без видеокарты, при fps ниже 20 или кнопкой; иначе вид прежний', 'diorama', 'Участки → Диорама → кнопка «Лёгкий режим» (?lite=1)', 'aktogay/web/static/diorama/core.js'],
  ];
  /* card of readiness: the nine points of every new trouble and forecast (aktogay/modules/readiness.py) */
  const READY_LABELS = [['problem', 'Проблема'], ['source', 'Источник'], ['signal_real', 'Сигнал на реальной фабрике'], ['signal_twin', 'Сигнал в двойнике'], ['rule', 'Правило'], ['params', 'Параметры'], ['price', 'Цена'], ['who', 'Кого звать'], ['backup', 'Запасной'], ['checklist', 'Что делать'], ['closure', 'Закрытие'], ['scenario', 'Сценарий'], ['test', 'Тест'], ['howto', 'Строка «Как проверить»'], ['limits', 'Границы'], ['connect', 'Что подключить']];
  const readyHtml = items => `<table class="kv"><tr><th>Беда или прогноз</th><th>Сигнал на реальной фабрике</th><th>Откуда данные в двойнике</th><th>Что подключить</th><th>Границы</th></tr>${items.map(r => `<tr><td><b>${esc(r.title)}</b><br><span class="p-sub">${esc(r.kind)}</span></td><td>${esc(r.signal_real)}</td><td>${esc(r.signal_twin)}</td><td>${esc(r.connect || '—')}</td><td>${esc(r.limits)}</td></tr>`).join('')}</table>`
    + items.map(r => `<details><summary>Девять пунктов: ${esc(r.title)}</summary><ul>${READY_LABELS.map(([k, t]) => `<li><b>${esc(t)}.</b> ${esc(r[k])}</li>`).join('')}</ul></details>`).join('')
    + '<p class="note">Метки: [факт], [проект], [вендор], [аналог], [расчёт], [допущение], [оценка на модели]. Где источника на порядок действий нет, написано «уточнить по регламенту площадки» — процедуры не выдуманы.</p>';
  AKT.views.howto = {
    build(stage) {
      const d = doc(stage, 'howto');
      d.innerHTML = `<h2>Как проверить</h2>
<p class="lead">Утверждение → где его посмотреть на стенде → на чём оно стоит. Каждая строка ведёт на экран, где число видно и откуда оно взято.</p>
<table class="kv" id="ht-tab"><tr><th>Утверждение</th><th>Где посмотреть</th><th>Источник</th></tr>${CLAIMS.map(c => `<tr><td>${esc(c[0])}</td><td><a href="${AKT.href('?view=' + c[1])}">${esc(c[2])}</a></td><td>${esc(c[3])}</td></tr>`).join('')}</table>
<h3 id="ht-flood-h">Лавина тревог и одна беда</h3><div id="ht-flood"></div>
<h3 id="ht-verify-h">Ожидаемый итог сценариев</h3><div id="ht-verify"><p class="empty dash">Загружаю заранее посчитанные итоги…</p></div>
<h3 id="ht-claims-h">Откуда числа в описании: опыт, проверка</h3><div id="ht-claims"><p class="empty dash">Загружаю реестр чисел…</p></div>
<h3>Модули: живой статус</h3><div id="ht-mods"><p class="empty dash">Загружаю список модулей…</p></div>
<h3>Повторить расчёт</h3>
<p>Таблица калибровки: <code>make akt-calib</code> или <code>python -I aktogay/run.py calib --quick</code> (≈ 2,5 мин); проверка по кварталам: <code>python -I aktogay/run.py backtest</code> (≈ 3 мин); опыт «вкл/выкл»: <code>python -I aktogay/run.py trial --n 100 --no-twin</code> (≈ 3 мин); тесты: <code>python -I -m unittest discover -s aktogay/tests -t aktogay</code>. Те же seed — те же числа.</p>
<h3>Путь внедрения: беда → сигнал на реальной фабрике → откуда данные</h3><div id="ht-ready"><p class="empty dash">Загружаю карточки готовности…</p></div>
<div id="ht-live"></div>`;
      AKT.exp23.load(() => this.update());
      AKT.verify.load(() => this.update());
      fetch('/claims.json', { cache: 'no-store' }).then(r => r.json()).then(d => { this.claims = d; this.update(); }).catch(() => { /* optional */ });
      fetch('/readiness.json', { cache: 'no-store' }).then(r => r.json()).then(d => { this.ready = d.items || []; this.update(); }).catch(() => { /* optional */ });
      fetch('/modules.json', { cache: 'no-store' }).then(r => r.json()).then(d => { this.mods = d.modules || []; this.update(); }).catch(() => { /* optional */ });
    },
    /* live status of a module from its own thing in Ditto: the last tact in model time, the age of the record, the run */
    modStatus(m) {
      const t = AKT.simTime, run = AKT.run;
      const paused = AKT.st('site') === 'PAUSED' || AKT.num('site', 'speed') === 0;
      const same = th => !run || String(AKT.val(th, 'idSimulationRun') || '') === run;
      const age = th => AKT.modifiedAge(th);
      if (m.id === 'akt-web') { const a = AKT.staleSec(); return a == null ? { lv: 2, word: 'нет ответа', last: '—', age: null } : { lv: a > 10 ? 2 : 0, word: a > 10 ? 'ответ запоздал' : 'отвечает', last: '—', age: a }; }
      if (!m.thing || !AKT.things[m.thing]) return { lv: 2, word: 'нет данных', last: '—', age: null };
      if (m.id === 'akt-sim') {
        const hb = AKT.num('site', 'heartbeat'), a = hb != null ? Math.max(0, Date.now() / 1000 - hb) : null;
        const ok = a != null && a < 30 || paused;
        return { lv: ok ? 0 : 2, word: AKT.num('site', 'degraded') ? 'есть потери сообщений' : (ok ? (paused ? 'на паузе' : 'работает') : 'не отвечает'), last: t != null ? AKT.clockDay(t) : '—', age: a };
      }
      if (m.id === 'akt-calib') {
        const st = AKT.st(m.thing);
        const w = { DONE: 'готово', RUNNING: 'считает', FAILED: 'ошибка', IDLE: 'не запускался' }[st] || st || 'нет данных';
        return { lv: st === 'FAILED' ? 2 : st === 'DONE' || st === 'RUNNING' ? 0 : 3, word: w, last: AKT.num(m.thing, 'shifts_done') != null ? `смен: ${fmt(AKT.num(m.thing, 'shifts_done'))} из ${fmt(AKT.num(m.thing, 'shifts_total'))}` : '—', age: age(m.thing) };
      }
      if (m.id === 'akt-setup') { const ok = (AKT.num(m.thing, 'things_ok') || 0) > 0; return { lv: ok ? 0 : 2, word: ok ? 'вещи созданы' : 'нет данных', last: ok ? `вещей: ${fmt(AKT.num(m.thing, 'things_ok'))}` : '—', age: age(m.thing) }; }
      const p = AKT.num(m.thing, m.live);
      if (p == null || !same(m.thing)) return { lv: 3, word: 'ждёт прогона', last: '—', age: age(m.thing) };
      const lag = t != null ? t - p : 0;
      return { lv: lag > 15 && !paused ? 3 : 0, word: lag > 15 && !paused ? `отстаёт на ${AKT.dur(lag)}` : 'работает', last: AKT.clockDay(p), age: age(m.thing) };
    },
    modsHtml() {
      const md = t => esc(t).replace(/`([^`]+)`/g, '<code>$1</code>');
      const rows = this.mods.map(m => {
        const s = this.modStatus(m);
        return `<tr><td><b>${esc(m.id)}</b><br><span class="p-sub">${esc(m.title)}</span></td><td>${md(m.rs)}</td><td>${md(m.ws)}</td>`
          + `<td class="n">${esc(s.last)}</td><td class="n">${s.age == null ? '—' : esc(AKT.ago(s.age))}</td><td>${AKT.glyph(s.lv)} ${esc(s.word)}</td><td>${m.tests.slice(0, 2).map(x => `<code>${esc(x.replace('tests/', ''))}</code>`).join('<br>')}</td></tr>`;
      }).join('');
      const full = this.mods.map(m => `<p><b>${esc(m.id)}</b> — ${esc(m.what)} Код: <code>${esc(m.code)}</code>.<br><b>Читает из Ditto:</b> ${m.reads.map(md).join('; ')}.<br><b>Читает из InfluxDB:</b> ${md(m.influx)}.<br><b>Пишет:</b> ${m.writes.map(md).join('; ')}.<br><b>Тесты:</b> ${m.tests.map(x => `<code>${esc(x)}</code>`).join(', ')}.</p>`).join('');
      return `<table class="kv" id="ht-mods-t"><tr><th>Модуль</th><th>Читает</th><th>Пишет</th><th>Последний такт</th><th>Запись в Ditto</th><th>Статус</th><th>Тест</th></tr>${rows}</table>
<details><summary>Вход, выход и тесты каждого модуля полностью</summary>${full}</details>
<p class="note">То же — в <code>aktogay/web/API.md</code> (его пишет <code>modules/apidoc.py</code>, тест сверяет). Статус читается из самих вещей Ditto: время такта в модельном времени и возраст записи.</p>`;
    },
    /* the registry of headline numbers (web/static/claims.json, scripts/check_numbers.py): every number of the description is tied to an experiment */
    claimsHtml() {
      const d = this.claims, how = { auto: 'пересчитано из файла результатов', history: 'прежний код, запись; сверено, где файл сохранён', manual: 'оговорено', literature: 'другая работа' };
      const ex = Object.entries(d.experiments).map(([id, e]) => {
        const cs = d.claims.filter(c => c.experiment === id);
        return `<tr><td><b>${esc(e.title)}</b><br><span class="p-sub">${esc(e.what)}</span></td><td>${esc(e.kind)}</td><td>${esc(e.ci)}</td><td class="n">${fmt(cs.length)}</td><td><code>${esc(e.command)}</code></td></tr>`;
      }).join('');
      const rows = d.claims.map(c => {
        const e = d.experiments[c.experiment];
        const live = (c.experiment === 'scen_seed42' && AKT.verify.data) ? 'посчитано заранее, seed ' + AKT.verify.data.seed : '';
        return `<tr><td class="n"><b>${esc(c.text)}</b>${c.ci_text ? `<br><span class="p-sub">[${esc(c.ci_text.join('; '))}]</span>` : ''}</td><td>${esc(c.meaning)}</td><td>${esc(e ? e.title : c.experiment)}</td><td>${esc(how[c.check] || c.check)}${live ? `<br><span class="p-sub">${esc(live)}</span>` : ''}${c.note ? `<br><span class="p-sub">${esc(c.note)}</span>` : ''}</td></tr>`;
      }).join('');
      return `<p class="lead">Одно и то же слово («вклад порядка», «раннее обнаружение») в разных местах описания — это числа разных опытов, а не противоречие: здесь каждое число названо с опытом, в котором оно получено. Проверка автоматическая: <code>python -I aktogay/scripts/check_numbers.py</code> падает, если в README, описании или презентации есть число «+N,NN т» без записи в реестре.</p>
<table class="kv"><tr><th>Опыт</th><th>Вид</th><th>Интервал</th><th>Чисел</th><th>Как повторить</th></tr>${ex}</table>
<details><summary>Все ${fmt(d.claims.length)} чисел реестра</summary><table class="kv" id="ht-claims-t"><tr><th>Число</th><th>Что это</th><th>Опыт</th><th>Как проверено</th></tr>${rows}</table></details>`;
    },
    /* events of the shift against the issues of the queue and the one on the main screen (modules/flood.py), live and from the experiment */
    floodHtml() {
      const f = AKT.val('mod-priority', 'alarm_flood'), st = AKT.exp23 && AKT.exp23.data && AKT.exp23.data.alarms;
      const live = f && typeof f === 'object' && f.events != null && f.elapsed_min >= 0
        ? `<p><b>В этой смене</b> (с ${AKT.clock(AKT.simTime - f.elapsed_min)}): <b>${fmt(f.events)}</b> событий-тревог по ${fmt(f.nodes)} узлам → <b>${fmt(f.issues)}</b> бед в очереди → <b>1</b> на главном экране${f.per_10min >= 0 ? `; ${fmt(f.per_10min, 2)} события за 10 мин против ≈ ${fmt(f.isa_per_10min, 1)} за 10 мин по ориентиру ANSI/ISA-18.2` : ''} [оценка на модели].</p>`
        : '<p class="note">В этой смене тревоги ещё не считались (модуль «Очередь бед» считает с начала смены).</p>';
      const stat = st && st.no_twin ? `<p><b>По опыту на модели</b> (${fmt(st.n)} смен, в среднем ${fmt(st.troubles_per_shift, 2)} беды за смену): ${fmt(st.no_twin.events_mean, 1)} событий-тревог за смену (медиана ${fmt(st.no_twin.events_median)}, 10–90 % ${fmt(st.no_twin.events_p10)}–${fmt(st.no_twin.events_p90)}), ≈ ${fmt(st.no_twin.events_per_trouble, 1)} на одну беду; на главном экране — одна. Это ${fmt(st.no_twin.per_10min_mean, 2)} события за 10 мин, то есть <b>ниже ориентира</b> ISA ≈ ${fmt(st.isa_per_shift)} за смену: лавину мы не воспроизводим и не утверждаем. Что показываем — свёртку: одна причина тянет за собой цепочку узлов (дробилка → лента → склад → SAG → линия → флотация), и диспетчеру показана одна беда с ценой.</p>` : '';
      return `${live}${stat}<p class="note">Событие — узел перешёл из нормального состояния в ненормальное (остановка, голодание, ограничение, «верх»/«низ» запаса, прибор под подозрением); узел, который остаётся в ненорме, — одно событие. Это нижняя граница: пороги по числовым сигналам (т/ч, кВт, кПа, уровень) не считаются, а запись между двумя точками двойника (5 мин модели) не видна. Ориентир: около 150 тревог на оператора в сутки — <a href="https://webstore.ansi.org/standards/isa/ansiisa182016" target="_blank" rel="noopener">ANSI/ISA-18.2</a>. Подробно — <code>VALIDATION.md</code>, раздел 8.12.</p>`;
    },
    update() {
      setHtml('ht-flood', this.floodHtml(), false);
      setHtml('ht-verify', AKT.verify.table());
      if (this.claims) setHtml('ht-claims', this.claimsHtml());
      if (this.mods) setHtml('ht-mods', this.modsHtml());
      if (this.ready) setHtml('ht-ready', readyHtml(this.ready));
      const raw = AKT.val('validation-calib', 'report_json');
      let rep = null; try { rep = typeof raw === 'string' && raw.trim() ? JSON.parse(raw) : null; } catch (e) { rep = null; }
      const rows = rep && Array.isArray(rep.rows) ? rep.rows : [];
      const okN = rows.filter(r => r.ok === true).length, badN = rows.filter(r => r.ok === false).length;
      const bt = rep && rep.backtest && rep.backtest.summary;
      setHtml('ht-live', `<p class="note">Сейчас в Ditto: проверка калибровки — ${rows.length ? `${fmt(rows.length)} строк, в допуске ${fmt(okN)}, вне допуска ${fmt(badN)}` : 'ещё не записана'}${bt ? '; проверка по кварталам записана' : ''}. Вещей в двойнике: ${fmt(Object.keys(AKT.things).length)}.</p>`);
    },
  };
})();
