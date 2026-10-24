/* «Изнутри» (second level, B of the task of 23.10.2026): inside the ore, the dam, the people, the machines, the plant and the
   environment-and-data group. The knowledge (nodes, signals with the place where each is seen, failures with their sources, the depth of
   evidence A/B/C) comes from /inside.json (written by aktogay/modules/inside.py, a test keeps it equal to the code); the live numbers come
   from Ditto only. Nothing is hard-coded here but the layout: wording of the labels, sources and limits is read from the file. */
'use strict';
(function () {
  const esc = AKT.esc, fmt = AKT.fmt, f1 = AKT.f1, f2 = AKT.f2, f3 = AKT.f3;
  const NB = AKT.NB;
  const doc = (stage, id) => { stage.innerHTML = ''; const d = document.createElement('div'); d.className = 'doc'; d.id = id; stage.appendChild(d); return d; };
  const setHtml = (id, html) => { const e = document.getElementById(id); if (e && e._raw !== html) { e._raw = html; e.innerHTML = html; if (AKT.glossify) AKT.glossify(e); } };
  const n0 = (name, f) => AKT.num(name, f);

  /* a sign for every place a signal is seen: the word is always next to it (not colour alone) */
  const MARK = { machine: '■', sent: '◐', analog: '◇', dcs: '●', lab: '▲', model: '○', assumption: '△' };
  const DEPTH_SHAPE = { A: '●●●', B: '●●○', C: '●○○' };
  /* group of the page by the key `live` of inside.json */
  const LIVE_KEYS = ['faces', 'dam', 'people', 'machines', 'plant', 'env'];
  const PLANT_TYPES = new Set(['crusher', 'conveyor', 'stockpile', 'line', 'sag', 'pebble', 'ball', 'cyclones', 'flot', 'rougher', 'cleaner', 'thick', 'filter', 'conc-stock']);

  /* ------------------------------------------------------------- pure helpers (checked in node by the test) */
  /* "ph-{n}" -> existing ph-1, ph-2 ...; "a, b" or ["a", "b"] -> list; a name without a pattern stays as it is */
  const expand = spec => {
    if (spec == null || spec === '') return [];
    const arr = Array.isArray(spec) ? spec : String(spec).split(/[\s,;]+/).filter(Boolean);
    const out = [];
    for (const s of arr) {
      if (String(s).includes('{n}')) { for (const n of [1, 2, 3]) { const id = String(s).replace('{n}', n); if (AKT.things[id]) out.push(id); } }
      else out.push(String(s));
    }
    return out;
  };
  const shortName = id => String(AKT.nameRu(id)).replace(/^Пьезометр дамбы /, 'П-').replace(/^Экскаватор /, '');
  /* value of one feature of one or several things in words; "—" without a value */
  const oneText = (id, f, d, u) => {
    const v = AKT.raw(id, f);
    if (typeof v === 'number') {
      if (v === -1) return '—';
      if (AKT.TIME_FEATS && AKT.TIME_FEATS.has(f)) return AKT.valText(id, f);
      return fmt(v, d != null ? d : (Number.isInteger(v) ? 0 : 2)) + (u ? NB + u : '');
    }
    if (typeof v === 'string' && v) return AKT.valText(id, f);
    return '—';
  };
  const liveText = (spec, f, d, u) => {
    const ids = expand(spec).filter(id => AKT.things[id]);
    if (!ids.length) return '—';
    return ids.map(id => (ids.length > 1 ? shortName(id) + ': ' : '') + oneText(id, f, d, u)).join('; ');
  };
  const groupOfThing = n => {
    const type = AKT.type(n), cat = AKT.cat ? AKT.cat(n) : '';
    if (type === 'water' || cat === 'piezo') return 'dam';
    if (cat === 'person') return 'people';
    if (cat === 'face') return 'faces';
    if (cat === 'exc' || cat === 'truck' || cat === 'dozer' || cat === 'drill' || type === 'pit' || type === 'fleet') return 'machines';
    if (PLANT_TYPES.has(type)) return 'plant';
    if (['analyzer', 'weigher', 'flowmeter', 'phmeter', 'piezometer'].includes(type)) return 'env';
    return null;
  };
  /* link of a thing card to its place in the page «Изнутри» */
  AKT.insideHref = n => { const g = groupOfThing(n); return g ? AKT.href(`?view=inside&g=${g}&t=${encodeURIComponent(n)}`) : null; };

  /* ------------------------------------------------------------- live blocks, one per group */
  const tw = html => `<div class="in-tw">${html}</div>`;
  const kvText = (id, items) => items.map(([f, label, unit, d]) => {
    if (f === 'state') return AKT.stOf(id);
    const v = AKT.raw(id, f);
    if (typeof v !== 'number' || v === -1) return '';
    return `${label ? label + ' ' : ''}${fmt(v, d != null ? d : (Number.isInteger(v) ? 0 : 1))}${unit ? NB + unit : ''}`;
  }).filter(Boolean).join(' · ');

  const FACE_NODES = () => AKT.ofType('face').filter(n => AKT.val(n, 'hardness') !== 'вскрыша' && String(AKT.pass(n, 'kind') || '') !== 'вскрыша');
  const liveFaces = () => {
    const rows = FACE_NODES().map(n => {
      const b = String(AKT.val(n, 'block') || ''), axb = n0(n, 'est_axb'), st = AKT.st(n);
      const ascu = b && AKT.things[b] ? Number(AKT.pass(b, 'est_ascu')) : NaN;
      return `<tr><td><b>${esc(AKT.nameRu(n))}</b></td><td>${b ? 'партия ' + esc(AKT.batchNo(b)) : '—'}</td><td class="n">${isFinite(ascu) && ascu >= 0 ? f1(ascu) + NB + '%' : '—'}</td><td class="n">${n0(n, 'est_cu') == null ? '—' : f2(n0(n, 'est_cu')) + NB + '%'}</td><td class="n">${axb == null ? '—' : f1(axb)}</td><td>${esc(String(AKT.val(n, 'hardness') || '—'))}</td><td class="n">${n0(n, 'tph') == null ? '—' : fmt(n0(n, 'tph')) + NB + 'т/ч'}</td><td class="n">${n0(n, 'blasted_t') == null ? '—' : fmt(n0(n, 'blasted_t') / 1000, 1) + NB + 'тыс. т'}</td><td>${esc(AKT.stRu(st, n))}</td></tr>`;
    }).join('');
    const lines = [1, 2].map(l => {
      let arr = []; try { arr = JSON.parse(String(AKT.val('mod-ore', 'layers_l' + l) || '[]')); } catch (e) { arr = []; }
      const now = arr.filter(o => Number(o.in_sag || 0) > 0.3).map(o => `партия ${AKT.batchNo(String(o.batch))} (${AKT.oreWord(Number(o.axb))}, A×b ${f1(Number(o.axb))})`);
      return `<tr><td><b>Линия ${l}</b></td><td>${now.length ? esc(now.join(' и ')) : 'нет данных'}</td><td class="n">${n0(`sag-${l}`, 'axb_soft') == null ? '—' : f1(n0(`sag-${l}`, 'axb_soft'))}</td><td class="n">${n0(`flot-${l}`, 'feed_cu') == null ? '—' : f3(n0(`flot-${l}`, 'feed_cu')) + NB + '% Cu'}</td></tr>`;
    }).join('');
    const kinds = new Set(['hard_ore', 'loss_flot_oxide']);
    const iss = AKT.issues().filter(i => kinds.has(String(AKT.val(i, 'kind') || '')));
    const notify = iss.length ? `<ul>${iss.map(i => `<li><b>${esc(AKT.issueTitle(i))}</b> — ${esc(AKT.stRu(AKT.st(i), i))}; кого звать: ${esc(AKT.roleAcc(AKT.issueRole(i)))}.${AKT.val(i, 'notify_text') ? '<br><span class="p-sub">Также сообщить: ' + esc(String(AKT.val(i, 'notify_text'))) + '</span>' : ''}</li>`).join('')}</ul>`
      : '<p class="empty dash">Смена забоя с другой рудой (твёрдой, окисленной) сейчас не ожидается: открытых бед «твёрдая руда» и «окисленная руда» нет.</p>';
    const fc = String(AKT.val('mod-ore', 'fc_text') || '');
    return `<h3>Забои руды сейчас</h3>${tw(`<table class="kv"><tr><th>забой</th><th>партия</th><th>окисленная (ASCu) ≈</th><th>Cu по блочной модели ≈</th><th>A×b ≈</th><th>твёрдость</th><th>копает</th><th>взорвано</th><th>состояние</th></tr>${rows || '<tr><td colspan="9">забоев в двойнике нет</td></tr>'}</table>`)}
<h3>Что идёт на фабрику сейчас</h3>${tw(`<table class="kv"><tr><th>линия</th><th>партия в питании SAG (по модулю руды)</th><th>A×b по SAG (датчик, ≈)</th><th>Cu в питании (анализатор)</th></tr>${lines}</table>`)}
${fc ? `<p class="p-sub">Модуль руды: ${esc(fc.replace(/\s*\[оценка на модели\]/g, ' (≈)'))}</p>` : ''}
<h3>Смена забоя и металлург</h3>${notify}`;
  };

  const liveDam = () => {
    const ps = Object.keys(AKT.things).filter(n => AKT.type(n) === 'piezometer').sort(AKT.cmpNames);
    const rows = ps.map(n => `<tr><td><b>${esc(AKT.nameRu(n))}</b></td><td class="n">${n0(n, 'kpa') == null ? '—' : fmt(n0(n, 'kpa')) + NB + 'кПа'}</td><td class="n">${n0(n, 'level_m') == null ? '—' : f1(n0(n, 'level_m')) + NB + 'м'}</td><td class="n">${fmt(n0(n, 'sp_kpa') || 150)}${NB}кПа</td><td>${esc(AKT.stOf(n))}${n0(n, 'alarm') === 1 ? ' · <b>▲ тревога</b>' : ''}</td></tr>`).join('');
    const w = k => n0('water', k);
    const iss = AKT.issues().filter(i => ['dam_alarm', 'tailings_dust', 'water_short'].includes(String(AKT.val(i, 'kind') || '')));
    return `<h3>Дамба и пруд сейчас</h3>${tw(`<table class="kv"><tr><th>пьезометр</th><th>давление</th><th>уровень воды</th><th>уставка тревоги (S0)</th><th>состояние</th></tr>${rows || '<tr><td colspan="5">пьезометров в двойнике нет</td></tr>'}</table>`)}
<table class="kv"><tr><td>Хвосты и вода</td><td>${esc(AKT.stOf('water'))}</td></tr>
<tr><td>Пруд</td><td class="n">${w('pond_m3') == null ? '—' : f2(w('pond_m3') / 1e6) + NB + 'млн м³'} (д)</td></tr>
<tr><td>Показание дамбы в модели</td><td class="n">${w('piezo_kpa') == null ? '—' : fmt(w('piezo_kpa')) + NB + 'кПа'}</td></tr>
<tr><td>Ветер / сухой пляж</td><td class="n">${w('wind_ms') == null ? '—' : fmt(w('wind_ms')) + NB + 'м/с'} / ${w('beach_dry_pct') == null ? '—' : fmt(w('beach_dry_pct')) + NB + '%'}</td></tr>
<tr><td>Воздух · сезон</td><td class="n">${w('air_temp_c') == null ? '—' : fmt(w('air_temp_c')) + NB + '°C'} · ${w('winter') === 1 ? 'зима: возврат воды снижен (лёд)' : 'не зима'}</td></tr></table>
${iss.length ? `<p><b>Открытые беды по дамбе и воде:</b> ${iss.map(i => esc(AKT.issueTitle(i))).join('; ')}</p>` : '<p class="empty dash">Открытых бед по дамбе, пылению и воде нет.</p>'}`;
  };

  const livePeople = () => {
    const rows = AKT.persons().map(n => {
      const dep = AKT.name(String(AKT.attr(n, 'responsible.deputy') || ''));
      const permit = String(AKT.val(n, 'permit') || '');
      const free = n0(n, 'free_at');
      return `<tr><td><b>${esc(AKT.nameRu(n))}</b></td><td>${esc(AKT.stOf(n))}</td><td>${esc(AKT.placeRu(AKT.name(String(AKT.val(n, 'location') || ''))))}</td><td>${permit ? '<b>■ наряд-допуск:</b> ' + esc(AKT.placeRu(AKT.name(permit))) : '—'}</td><td>${free != null && free >= 0 ? esc(AKT.clockDay(free)) : '—'}</td><td>${dep && AKT.things[dep] ? esc(AKT.nameRu(dep)) : '—'}</td></tr>`;
    }).join('');
    const chains = AKT.issues().map(i => ({ i, c: AKT.val(i, 'chain') || {} })).filter(x => x.c.line);
    return `<h3>Люди смены сейчас</h3>${tw(`<table class="kv"><tr><th>кто</th><th>статус</th><th>где</th><th>наряд-допуск</th><th>свободен с</th><th>кто вместо (заместитель)</th></tr>${rows || '<tr><td colspan="6">людей в двойнике нет</td></tr>'}</table>`)}
${chains.length ? `<h3>Цепочки вызова по открытым бедам</h3><ul>${chains.map(x => `<li><b>${esc(AKT.issueTitle(x.i))}</b>: ${esc(x.c.line)}</li>`).join('')}</ul>` : '<p class="empty dash">Открытых бед с цепочкой вызова нет.</p>'}
<p class="p-sub">В карьере за смену больше 500 человек и больше 100 единиц техники (Вести Семей, 06.06.2024); здесь — люди, на которых строится вызов. Роли и состав смены — допущение стенда.</p>`;
  };

  const liveMachines = () => {
    const exc = Object.keys(AKT.things).filter(n => AKT.type(n) === 'exc').sort(AKT.cmpNames);
    const erows = exc.map(n => {
      const oil = n0(n, 'oil_pct');
      return `<tr><td><b>${esc(AKT.nameRu(n))}</b></td><td>${esc(String(AKT.pass(n, 'model') || '—'))}</td><td>${esc(AKT.stOf(n))}</td><td class="n">${n0(n, 'tph') == null ? '—' : fmt(n0(n, 'tph')) + NB + 'т/ч'}</td><td class="n">${oil == null ? 'нет датчика в источниках' : fmt(oil) + NB + '% от уровня тревоги' + (n0(n, 'oil_alert') === 1 ? ' · <b>▲ тревога</b>' : '')}</td></tr>`;
    }).join('');
    const tr = Object.keys(AKT.things).filter(n => AKT.type(n) === 'truck').sort(AKT.cmpNames);
    const ht = tr.find(n => /HT141/.test(AKT.nameRu(n))) || tr[0];
    const fl = n => n0('fleet', n);
    const dz = Object.keys(AKT.things).filter(n => AKT.type(n) === 'dozer').sort(AKT.cmpNames);
    const dr = Object.keys(AKT.things).filter(n => AKT.type(n) === 'drill').sort(AKT.cmpNames);
    const simple = list => list.map(n => `<tr><td>${esc(AKT.nameRu(n))}</td><td>${esc(AKT.stOf(n))}</td><td>${esc(AKT.placeRu(AKT.name(String(AKT.val(n, 'location') || ''))))}</td></tr>`).join('');
    return `<h3>Экскаваторы сейчас</h3>${tw(`<table class="kv"><tr><th>машина</th><th>модель</th><th>состояние</th><th>копает</th><th>загрязнение гидромасла</th></tr>${erows || '<tr><td colspan="5">нет</td></tr>'}</table>`)}
<h3>Самосвалы</h3><p>Парк: на ходу ${fl('trucks_ready') == null ? '—' : fmt(fl('trucks_ready'))} из ${fl('trucks_total') == null ? '—' : fmt(fl('trucks_total'))}, вывозка ${fl('haul_tph') == null ? '—' : fmt(fl('haul_tph')) + NB + 'т/ч'}, скорость откатки ${n0('pit', 'haul_speed_pct') == null ? '—' : fmt(n0('pit', 'haul_speed_pct')) + NB + '% к сухой дороге'}${n0('fleet', 'fatigue') === 1 ? ` · <b>▲ оповещение об усталости: ${esc(String(AKT.val('fleet', 'fatigue_truck') || ''))} (допущение)</b>` : ''}.</p>
${ht ? `<p>${esc(AKT.nameRu(ht))}: ${esc(AKT.stOf(ht))}, ${esc(AKT.placeRu(AKT.name(String(AKT.val(ht, 'location') || ''))))}, рейс ${n0(ht, 'cycle_min') == null ? '—' : fmt(n0(ht, 'cycle_min')) + NB + 'мин'}.</p>` : ''}
${dz.length ? `<h3>Бульдозеры</h3>${tw(`<table class="kv"><tr><th>машина</th><th>состояние</th><th>где</th></tr>${simple(dz)}</table>`)}` : ''}
${dr.length ? `<h3>Буровые станки</h3>${tw(`<table class="kv"><tr><th>станок</th><th>состояние</th><th>забой</th></tr>${simple(dr)}</table>`)}` : ''}`;
  };

  const PLANT_ROWS = [
    ['Дробилка ЦПД', n => kvText(`crusher-${n}`, [['state'], ['tph', '', 'т/ч', 0]]) + (n0(`crusher-${n}`, 'service') === 1 ? ` · плановая замена брони, ещё ${AKT.durH(n0(`crusher-${n}`, 'service_left_h'))}` : '')],
    ['Конвейер', n => kvText(`conveyor-${n}`, [['state'], ['tph', '', 'т/ч', 0]]) + (n0(`conveyor-${n}`, 'fault') === 1 ? ' · сигнал защиты' : '')],
    ['Склад руды', n => kvText(`stockpile-${n}`, [['state'], ['level_t', '', 'т', 0], ['hours_left', 'хватит на', 'ч', 1]])],
    ['Дробление гали, ВВД', n => kvText(`pebble-${n}`, [['state'], ['load_pct', 'загрузка', '%', 0]]) + (n0(`pebble-${n}`, 'hpgr_tph') > 0 ? ' · ВВД: ' + kvText(`pebble-${n}`, [['hpgr_kw', '', 'кВт', 0], ['hpgr_skew_pct', 'перекос', '%', 1], ['hpgr_kw_diff_pct', 'разница приводов', '%', 1]]) + (n0(`pebble-${n}`, 'metal_alarm') === 1 ? ' · ▲ металлодетектор' : '') : ' · ВВД в модели нет')],
    ['SAG', n => kvText(`sag-${n}`, [['state'], ['feed_tph', '', 'т/ч', 0], ['power_kw', '', 'кВт', 0], ['e_kwh_t', '', 'кВт·ч/т', 2], ['liner_ground_t', 'наработка футеровки', 'т', 0]])],
    ['Шаровые мельницы', n => ['a', 'b'].map(s => `${s.toUpperCase()}: ` + kvText(`ball-${n}${s}`, [['state'], ['power_pct', 'нагрузка', '%', 0]])).join(' · ')],
    ['Гидроциклоны', n => kvText(`cyclones-${n}`, [['state'], ['p80_um', 'P80', 'мкм', 0], ['circ_load_pct', 'циркулирующая нагрузка', '%', 0], ['pressure_kpa', 'давление', 'кПа', 0]])],
    ['Флотация', n => kvText(`flot-${n}`, [['state'], ['recovery', 'извлечение', '%', 1], ['tail_cu', 'хвосты', '% Cu', 3]]) + (AKT.things[`ph-${n}`] ? ` · pH: онлайн ${n0(`ph-${n}`, 'ph') == null ? '—' : f2(n0(`ph-${n}`, 'ph'))}, проба ${n0(`ph-${n}`, 'lab_ph') == null ? '—' : f2(n0(`ph-${n}`, 'lab_ph'))}` : '')],
    ['Сгуститель', n => kvText(`thick-${n}`, [['state'], ['inventory_t', 'запас', 'т', 0], ['hours_to_full', 'заполнится через', 'ч', 1]])],
    ['Фильтр', n => kvText(`filter-${n}`, [['state'], ['presses_on', 'прессов', '', 0], ['cake_tph', 'кек', 'т/ч', 1]])],
  ];
  const livePlant = () => `<h3>Узлы фабрики сейчас</h3>${tw(`<table class="kv"><tr><th>узел</th><th>Линия 1</th><th>Линия 2</th></tr>${PLANT_ROWS.map(([t, f]) => `<tr><td><b>${esc(t)}</b></td><td>${esc(f(1))}</td><td>${esc(f(2))}</td></tr>`).join('')}</table>`)}
<p class="p-sub">Насосы пульпы и оборотной воды отдельными вещами в двойнике не представлены: ниже — карточка узла с тем, что известно из источников.</p>`;

  const INSTR = ['analyzer', 'weigher', 'flowmeter', 'phmeter', 'piezometer'];
  const instrReading = n => {
    const t = AKT.type(n);
    if (t === 'analyzer') return `Cu: питание ${n0(n, 'feed_cu') == null ? '—' : f3(n0(n, 'feed_cu'))}, хвосты ${n0(n, 'tail_cu') == null ? '—' : f3(n0(n, 'tail_cu'))}, концентрат ${n0(n, 'conc_cu') == null ? '—' : f1(n0(n, 'conc_cu'))} %`;
    if (t === 'weigher') return n0(n, 'tph') == null ? '—' : fmt(n0(n, 'tph')) + NB + 'т/ч';
    if (t === 'flowmeter') return `${n0(n, 'dose_gt') == null ? '—' : f1(n0(n, 'dose_gt'))} г/т при уставке ${n0(n, 'sp_gt') == null ? '—' : f1(n0(n, 'sp_gt'))}`;
    if (t === 'phmeter') {
      const a = n0(n, 'ph'), b = n0(n, 'lab_ph');
      return `онлайн ${a == null ? '—' : f2(a)}, проба ${b == null ? '—' : f2(b)}${a != null && b != null ? ', расхождение ' + f2(Math.abs(a - b)) : ''}, уставка ${n0(n, 'sp_ph') == null ? '—' : f1(n0(n, 'sp_ph'))}`;
    }
    return n0(n, 'kpa') == null ? '—' : fmt(n0(n, 'kpa')) + NB + 'кПа';
  };
  const liveEnv = () => {
    const t = AKT.simTime;
    const rows = Object.keys(AKT.things).filter(n => INSTR.includes(AKT.type(n))).sort((a, b) => INSTR.indexOf(AKT.type(a)) - INSTR.indexOf(AKT.type(b)) || AKT.cmpNames(a, b)).map(n => {
      const st = AKT.st(n), meas = n0(n, 'age_min'), s = n0(n, 'sim_time'), pub = s != null && t != null ? Math.max(0, t - s) : null;
      const doubt = ['SUSPECT', 'DRIFT'].includes(st), old = (pub != null && pub > 10) || (meas != null && meas > (AKT.type(n) === 'phmeter' ? 360 : 45));
      return `<tr class="${doubt ? 'ev-susp' : old ? 'ev-old' : ''}"><td><b>${esc(AKT.nameRu(n))}</b><br><span class="p-sub">${esc(AKT.typeRu(AKT.type(n)))}</span></td><td>${esc(instrReading(n))}</td><td>${esc(AKT.stOf(n))}${doubt ? ' · <b>▲ под подозрением</b>' : ''}${old && !doubt ? ' · <b>⏱ давно</b>' : ''}</td><td>${esc(AKT.agoMin(pub))}</td><td>${meas != null ? esc(AKT.agoMin(meas)) : 'непрерывно'}</td></tr>`;
    }).join('');
    const sus = String(AKT.val('mod-losses', 'suspect_text') || '');
    const w = k => n0('water', k), p = k => n0('pit', k);
    return `<h3>Среда сейчас</h3><table class="kv"><tr><th>воздух</th><th>ветер</th><th>видимость на откатке</th><th>сцепление (индекс 0…1)</th><th>скорость откатки</th><th>ограничение движения</th></tr>
<tr><td class="n">${w('air_temp_c') == null ? '—' : fmt(w('air_temp_c')) + NB + '°C'}</td><td class="n">${w('wind_ms') == null ? '—' : fmt(w('wind_ms')) + NB + 'м/с'}</td><td class="n">${p('visibility_m') == null ? '—' : fmt(p('visibility_m')) + NB + 'м'}</td><td class="n">${p('road_grip') == null ? '—' : f2(p('road_grip'))}</td><td class="n">${p('haul_speed_pct') == null ? '—' : fmt(p('haul_speed_pct')) + NB + '%'}</td><td>${p('road_restrict') === 1 ? 'введено' : 'нет'}</td></tr></table>
<h3>Данные: приборы, возраст, подозрения</h3>${tw(`<table class="kv"><tr><th>прибор</th><th>показание</th><th>состояние</th><th>опубликовано</th><th>возраст замера</th></tr>${rows || '<tr><td colspan="5">приборов в двойнике нет</td></tr>'}</table>`)}
<p class="p-sub">«Опубликовано» — сколько времени модели прошло с последней публикации прибора в Ditto; «возраст замера» — для анализатора и ручной пробы pH (у остальных замер непрерывный). ▲ — прибор под подозрением; ⏱ — данные давно.</p>
${sus && !/не найдено/.test(sus) ? `<p><b>Модуль «Где теряется медь»:</b> ${esc(sus.replace(/\s*\[оценка на модели\]/g, ' (≈)'))}</p>` : '<p class="empty dash">Модуль «Где теряется медь» сомнительных показаний не нашёл.</p>'}`;
  };
  const LIVE = { faces: liveFaces, dam: liveDam, people: livePeople, machines: liveMachines, plant: livePlant, env: liveEnv };

  /* ------------------------------------------------------------- knowledge cards from inside.json */
  const sigHtml = (s, where) => {
    const things = Array.isArray(s.thing) ? s.thing.join(',') : (s.thing || '');
    const live = things && s.feature ? `<td class="n in-live" data-t="${esc(things)}" data-f="${esc(s.feature)}" data-d="${s.digits == null ? '' : esc(s.digits)}" data-u="${esc(s.unit || '')}">—</td>` : '<td class="n">нет в Ditto</td>';
    const src = `${esc(s.source || '')}${s.url ? ` <a href="${esc(s.url)}" target="_blank" rel="noopener">ссылка</a>` : ''}${s.label ? ` <span class="lbl-est">[${esc(s.label)}]</span>` : ''}${s.note ? `<br><span class="p-sub">${esc(s.note)}</span>` : ''}`;
    return `<tr><td>${esc(s.name)}</td>${live}<td><span class="in-mark" aria-hidden="true">${MARK[s.where] || '·'}</span> ${esc(where[s.where] || s.where || '')}</td><td>${src}</td></tr>`;
  };
  const failHtml = f => {
    const link = f.trouble ? `<a href="${AKT.href('?view=queue')}">${esc(AKT.kindRu(f.trouble))}</a>` : '—';
    const open = f.trouble ? AKT.issues().filter(i => String(AKT.val(i, 'kind') || '') === f.trouble) : [];
    return `<tr><td>${esc(f.name)}</td><td>${esc(f.stat || '')}</td><td>${esc(f.source || '')}${f.url ? ` <a href="${esc(f.url)}" target="_blank" rel="noopener">ссылка</a>` : ''}${f.label ? ` <span class="lbl-est">[${esc(f.label)}]</span>` : ''}</td><td>${link}${open.length ? ` · <b>открыта сейчас: ${esc(AKT.stRu(AKT.st(open[0]), open[0]))}</b>` : ''}</td></tr>`;
  };
  const nodeHtml = (nd, D, hit) => {
    const where = D.where_ru || {}, dep = nd.depth || 'C';
    const sigs = (nd.signals || []).map(s => sigHtml(s, where)).join('');
    const fails = (nd.failures || []).map(failHtml).join('');
    const links = (nd.troubles || []).map(k => {
      const open = AKT.issues().filter(i => String(AKT.val(i, 'kind') || '') === k);
      return `<a href="${AKT.href('?view=queue')}">${esc(AKT.kindRu(k))}</a>${open.length ? ` (<b>сейчас: ${esc(AKT.stRu(AKT.st(open[0]), open[0]))}</b>)` : ''}`;
    }).join(' · ');
    const things = expand(nd.thing).filter(id => AKT.things[id]);
    return `<section class="in-node${hit ? ' in-hit' : ''}" id="in-n-${esc(nd.id)}" aria-labelledby="in-h-${esc(nd.id)}">
<h3 id="in-h-${esc(nd.id)}">${esc(nd.title)} <span class="in-depth in-depth-${esc(dep)}" title="${esc((D.depth_ru || {})[dep] || '')}"><span aria-hidden="true">${DEPTH_SHAPE[dep] || ''}</span> уровень ${esc(dep)}</span></h3>
<p class="p-sub">${esc((D.depth_ru || {})[dep] || '')}${nd.depth_note ? ' — ' + esc(nd.depth_note) : ''}</p>
${nd.what ? `<p>${esc(nd.what)}</p>` : ''}
${sigs ? `<h4>Сигналы</h4>${tw(`<table class="kv in-sig"><tr><th>сигнал</th><th>сейчас</th><th>где виден</th><th>источник · метка</th></tr>${sigs}</table>`)}` : ''}
${fails ? `<h4>Типовые отказы</h4>${tw(`<table class="kv"><tr><th>отказ</th><th>доля или случай</th><th>источник · метка</th><th>беда в двойнике</th></tr>${fails}</table>`)}` : ''}
${links ? `<p><b>Беды по этому узлу:</b> ${links}</p>` : ''}
${nd.limits ? `<p class="in-lim"><b>Границы.</b> ${esc(nd.limits)}</p>` : ''}
${things.length ? `<p class="p-sub">${things.slice(0, 6).map(id => `<a href="${AKT.href('?view=unit&id=' + AKT.id(id))}">карточка: ${esc(AKT.nameRu(id))}</a>`).join(' · ')}</p>` : ''}
</section>`;
  };

  /* ------------------------------------------------------------- the view */
  const view = AKT.views.inside = {
    D: null, failed: '', group: '', hit: '', timer: null,
    load() {
      return fetch('/inside.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(d => { this.D = d; this.failed = ''; }).catch(e => { this.failed = String(e.message || e); });
    },
    /* the group and the node to show: ?g=<group id or live key>, ?n=<node id>, ?t=<thing> (the link of a thing card) */
    pick() {
      const D = this.D; if (!D || !Array.isArray(D.groups) || !D.groups.length) return null;
      const g0 = AKT.params.get('g') || this.group;
      let g = D.groups.find(x => x.id === g0 || x.live === g0) || null;
      const t = AKT.params.get('t'), nid = AKT.params.get('n');
      if (nid) {
        const hg = D.groups.find(x => (x.nodes || []).some(nd => nd.id === nid));
        if (hg) { g = hg; this.hit = nid; }
      } else if (t) {
        const byThing = D.groups.map(x => [x, (x.nodes || []).find(nd => expand(nd.thing).includes(t))]).find(q => q[1])
          || D.groups.map(x => [x, (x.nodes || []).find(nd => (nd.signals || []).some(s => expand(s.thing).includes(t)))]).find(q => q[1]);
        if (byThing) { g = byThing[0]; this.hit = byThing[1].id; }
        else if (!g) g = D.groups.find(x => x.live === groupOfThing(t)) || null;
      }
      return g || D.groups[0];
    },
    build(stage) {
      const d = doc(stage, 'inside');
      d.innerHTML = `<h2>Изнутри: руда, дамба, люди, машины, фабрика, данные</h2>
<p class="lead">Второй уровень: что стоит внутри узла, по каким сигналам это видно и где сигнал виден (на машине, в диспетчерской, только при подключённой опции), какие отказы известны и откуда это известно. Живые числа — из двойника; знания и источники — из описания узлов. Глубина: A — узлы, сигналы и отказы с источником; B — узлы, отказы по аналогу или допущению; C — только общее состояние.</p>
<div id="in-tabs" class="in-tabs" role="tablist" aria-label="Группы"></div>
<div id="in-body"><p class="empty dash">Загружаю описание узлов…</p></div>`;
      this.hit = '';
      this.load().then(() => { this.renderAll(); if (AKT.current === this && this.hit) { const e = document.getElementById('in-n-' + this.hit); if (e && e.scrollIntoView) e.scrollIntoView({ block: 'start' }); } });
      this.timer = setInterval(() => { if (!this.D) this.load().then(() => this.renderAll()); }, 10000);
    },
    destroy() { clearInterval(this.timer); },
    renderAll() {
      const body = document.getElementById('in-body'), tabs = document.getElementById('in-tabs');
      if (!body || !tabs) return;
      if (!this.D) { body.innerHTML = `<p class="bad">Описание узлов (inside.json) не получено${this.failed ? ': ' + esc(this.failed) : ''}. Живые числа этой страницы — на карточках вещей.</p>`; return; }
      const D = this.D, g = this.pick();
      this.group = g.id;
      tabs.innerHTML = D.groups.map(x => `<a role="tab" class="in-tab" href="${AKT.href('?view=inside&g=' + encodeURIComponent(x.id))}" data-g="${esc(x.id)}" aria-selected="${x.id === g.id}">${esc(x.title)}</a>`).join('');
      tabs.querySelectorAll('a[data-g]').forEach(a => a.addEventListener('click', ev => {
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button) return;
        ev.preventDefault();
        this.group = a.dataset.g; this.hit = '';
        const u = new URL(location.href); u.searchParams.set('g', this.group); u.searchParams.delete('t'); u.searchParams.delete('n');
        history.replaceState(null, '', u.pathname + u.search);
        AKT.params = new URLSearchParams(u.search);
        this.renderAll(); this.update();
      }));
      const legend = Object.entries(D.where_ru || {}).map(([k, v]) => `<li><span class="in-mark" aria-hidden="true">${MARK[k] || '·'}</span> ${esc(v)}</li>`).join('');
      body.innerHTML = `<h3 class="in-gh">${esc(g.title)} <span class="in-depth in-depth-${esc(g.depth || 'B')}" title="${esc((D.depth_ru || {})[g.depth || 'B'] || '')}"><span aria-hidden="true">${DEPTH_SHAPE[g.depth || 'B'] || ''}</span> глубина ${esc(g.depth || 'B')}</span></h3>
${g.intro ? `<p>${esc(g.intro)}</p>` : ''}${g.note ? `<p class="p-sub">${esc(g.note)}</p>` : ''}
<div id="in-live">${''}</div>
${(g.nodes || []).map(nd => nodeHtml(nd, D, nd.id === this.hit)).join('')}
<details class="in-leg"><summary>Где виден сигнал: знаки</summary><ul class="in-legend">${legend}</ul><p class="p-sub">Метки: ${esc((D.labels || []).join(', '))}. «Допущение» — числа или сигнала нет в открытых источниках; «аналог» — данные другой модели или другого рудника.</p></details>`;
      this._live = LIVE[g.live] || null;
      if (AKT.glossify) AKT.glossify(body);
    },
    update() {
      if (!this.D) return;
      if (this._live) setHtml('in-live', this._live());
      document.querySelectorAll('#inside .in-live').forEach(c => {
        const d = c.dataset.d === '' ? null : Number(c.dataset.d);
        const s = liveText(c.dataset.t, c.dataset.f, d, c.dataset.u);
        if (c.textContent !== s) c.textContent = s;
      });
    },
  };
  /* for the test in node */
  AKT.inside = { h: { expand, liveText, groupOfThing, shortName } };
})();
