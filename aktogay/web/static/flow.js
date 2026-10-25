/* «Путь меди» (В1, second level) with the balances of copper and water (М3), and the hub «Участки».
   Everything comes from Ditto (features of the plant things, the open issues) — nothing is computed from the
   simulator. Widths of the grey bands are t/h of ore; the copper that goes to the tailings and the copper lost
   to the open troubles are red (shape and number as well as colour). */
'use strict';
(function () {
  const esc = AKT.esc, fmt = AKT.fmt, f1 = AKT.f1, f2 = AKT.f2;
  const NB = AKT.NB;
  const doc = (stage, id) => { stage.innerHTML = ''; const d = document.createElement('div'); d.className = 'doc'; d.id = id; stage.appendChild(d); return d; };
  const setHtml = (id, html) => { const e = document.getElementById(id); if (e && e._raw !== html) { e._raw = html; e.innerHTML = html; if (AKT.glossify) AKT.glossify(e); } };
  const n0 = (name, f) => AKT.num(name, f);
  const pos = v => (v != null && v > 0 ? v : 0);
  /* stage of the plant a node belongs to */
  const STAGE_OF = { pit: 0, fleet: 0, exc: 0, crusher: 1, conveyor: 1, stockpile: 2, sag: 3, pebble: 3, ball: 3, cyclones: 3, flot: 4, rougher: 4, cleaner: 4, thick: 5, filter: 5, 'conc-stock': 5 };
  const STAGE_RU = ['Карьер', 'Дробилка', 'Склад руды', 'Измельчение', 'Флотация', 'Концентрат'];
  const nodeStage = node => { const m = /^(.*?)(?:-(\d)[a-z]?)?$/.exec(node || ''); const t = m ? m[1] : node; return { stage: STAGE_OF[t], line: m && m[2] ? Number(m[2]) : 0 }; };

  /* ---------------------------------------------- numbers of one line, all from Ditto */
  const lineData = n => {
    const q = n0(`sag-${n}`, 'feed_tph') ?? n0(`line-${n}`, 'tph');
    const feedCuPct = n0(`flot-${n}`, 'feed_cu'), tailPct = n0(`flot-${n}`, 'tail_cu'), concPct = n0(`flot-${n}`, 'conc_cu');
    const concT = n0(`flot-${n}`, 'conc_tph');
    const cu = n0(`flot-${n}`, 'cu_tph') ?? n0(`line-${n}`, 'cu_tph');
    const tailsT = q != null && concT != null ? Math.max(0, q - concT) : null;
    const feedCu = q != null && feedCuPct != null ? q * feedCuPct / 100 : null;
    const tailsCu = tailsT != null && tailPct != null ? tailsT * tailPct / 100 : null;
    return {
      n, q, feedCuPct, tailPct, concPct, concT, cu, tailsT, feedCu, tailsCu,
      resid: feedCu != null && cu != null && tailsCu != null ? feedCu - cu - tailsCu : null,
      rec: n0(`line-${n}`, 'recovery'),
      crusher: n0(`crusher-${n}`, 'tph'), conv: n0(`conveyor-${n}`, 'tph'),
      in: n0(`stockpile-${n}`, 'in_tph'), out: n0(`stockpile-${n}`, 'out_tph'), level: n0(`stockpile-${n}`, 'level_t'), hours: n0(`stockpile-${n}`, 'hours_left'),
      sagMw: n0(`sag-${n}`, 'power_kw') != null ? n0(`sag-${n}`, 'power_kw') / 1000 : null,
      states: { crusher: AKT.st(`crusher-${n}`), conveyor: AKT.st(`conveyor-${n}`), stock: AKT.st(`stockpile-${n}`), sag: AKT.st(`sag-${n}`), flot: AKT.st(`flot-${n}`) },
    };
  };

  /* copper lost to the open troubles by line and stage, t Cu/h (from the money of the issue) */
  const troubleLoss = () => {
    const out = { by: {}, other: 0, list: [] };
    for (const i of AKT.issues()) {
      const usd = AKT.num(i, 'loss_usd_h');
      if (!(usd > 0) || !AKT.lossNow(i)) continue;
      const cu = AKT.cuOfUsd(usd), node = AKT.issueNode(i), s = nodeStage(node);
      if (s.stage != null && s.line) { const k = s.line + ':' + s.stage; out.by[k] = (out.by[k] || 0) + cu; } else out.other += cu;
      out.list.push({ issue: i, node, cu, usd });
    }
    return out;
  };

  AKT.troubleLoss = troubleLoss;

  /* --------------------------------------------------------------- the SVG */
  const W = 816, LANE = 214;
  const bandW = tph => (tph == null || tph <= 0 ? 1.5 : Math.max(2, Math.min(46, 46 * tph / 4400)));
  const band = (x0, x1, yc, tph, cls) => { const w = bandW(tph); return `<rect class="fl-band ${cls || ''}" x="${x0}" y="${(yc - w / 2).toFixed(1)}" width="${x1 - x0}" height="${w.toFixed(1)}"/>`; };
  const box = (x, y, w, h, title, lines, cls) => `<g class="fl-box ${cls || ''}"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="3"/><text class="fl-t" x="${x + w / 2}" y="${y + 15}" text-anchor="middle">${esc(title)}</text>${lines.map((l, i) => `<text class="fl-s" x="${x + w / 2}" y="${y + 31 + 14 * i}" text-anchor="middle">${esc(l)}</text>`).join('')}</g>`;
  const tag = (x, y, text, cls) => `<g class="fl-tag ${cls || 'loss'}"><rect x="${x - 4}" y="${y - 12}" width="${text.length * 6.2 + 12}" height="17" rx="3"/><text x="${x + 2}" y="${y}">▲ ${esc(text)}</text></g>`;

  /* HPGR (high pressure grinding rolls) of the pebble loop: only the line that has one (pebble hpgr_tph > 0; line 2,
     thyssenkrupp POLYCOM). Red when the metal detector tripped or the roll gap skew is at the alarm level. */
  const HPGR_SKEW_ALARM = 6;
  const hpgrNode = (n, sagX, sagW, yc) => {
    const pb = `pebble-${n}`;
    if (!AKT.things[pb] || !(n0(pb, 'hpgr_tph') > 0)) return '';
    const load = n0(pb, 'hpgr_load_pct'), kw = n0(pb, 'hpgr_kw'), skew = n0(pb, 'hpgr_skew_pct'), metal = n0(pb, 'metal_alarm') === 1;
    const stopped = AKT.st(pb) === 'STOP';
    const bad = metal || stopped || (skew != null && skew >= HPGR_SKEW_ALARM);
    const x = sagX - 22, w = 114, y = yc + 78, cx = sagX + sagW / 2;
    const lines = [stopped ? 'стоит' : kw != null ? `${fmt(kw)} кВт · ${load != null ? fmt(load) + ' %' : '—'}` : '—',
      metal ? '▲ металлодетектор' : `перекос ${skew != null ? f1(skew) : '—'} %`];
    return `<path class="fl-loop" d="M${cx - 8} ${yc + 38} L${cx - 8} ${y} M${cx + 8} ${y} L${cx + 8} ${yc + 38}"/>`
      + `<path class="fl-loop-h" d="M${cx - 12} ${yc + 46} L${cx - 8} ${yc + 38} L${cx - 4} ${yc + 46} M${cx + 4} ${y - 8} L${cx + 8} ${y} L${cx + 12} ${y - 8}"/>`
      + `<g class="fl-box ${bad ? 'bad' : ''}"><title>ВВД (валковый пресс высокого давления, thyssenkrupp POLYCOM, 1 061 т/ч, 2 × 1 750 кВт) в круге гали линии ${n}: перекос зазора валков и разница мощности приводов видны в карточке пресса</title>`
      + `<rect x="${x}" y="${y}" width="${w}" height="44" rx="3"/><text class="fl-t" x="${x + w / 2}" y="${y + 15}" text-anchor="middle">ВВД (POLYCOM)</text>`
      + lines.map((l, i) => `<text class="fl-s" x="${x + w / 2}" y="${y + 29 + 13 * i}" text-anchor="middle">${esc(l)}</text>`).join('') + '</g>';
  };

  const laneSvg = (L, loss, idx) => {
    const y0 = idx * LANE, yc = y0 + 112;
    const bx = [4, 156, 276, 410, 530], bw = [104, 70, 84, 70, 74];
    const hasStock = L.level != null;
    let g = `<text class="fl-lane" x="6" y="${y0 + 18}">Линия ${L.n}</text>`;
    const pitTph = n0('pit', 'mining_tph');
    // bands of ore between the boxes
    g += band(bx[0] + bw[0], bx[1], yc, L.crusher ?? pitTph, '');
    g += band(bx[1] + bw[1], bx[2], yc, L.conv ?? L.in, '');
    g += band(bx[2] + bw[2], bx[3], yc, L.out ?? L.q, '');
    g += band(bx[3] + bw[3], bx[4], yc, L.q, '');
    // flotation splits: concentrate (thin, up) and tails (wide, down)
    const sx = bx[4] + bw[4], tx = 634;
    g += `<path class="fl-band conc" d="M${sx} ${yc} C${sx + 30} ${yc} ${tx - 30} ${y0 + 56} ${tx} ${y0 + 56}" stroke-width="${bandW(L.concT).toFixed(1)}" fill="none"/>`;
    g += `<path class="fl-band tails" d="M${sx} ${yc} C${sx + 30} ${yc} ${tx - 30} ${y0 + 160} ${tx} ${y0 + 160}" stroke-width="${bandW(L.tailsT).toFixed(1)}" fill="none"/>`;
    const lab = (x, v, y) => `<text class="fl-n" x="${x}" y="${y}" text-anchor="middle">${v == null ? '—' : esc(fmt(v))}<tspan class="fl-u"> т/ч</tspan></text>`;
    g += lab((bx[0] + bw[0] + bx[1]) / 2, L.crusher ?? pitTph, yc - 30) + lab((bx[1] + bw[1] + bx[2]) / 2, L.conv ?? L.in, yc - 30)
      + lab((bx[2] + bw[2] + bx[3]) / 2, L.out ?? L.q, yc - 30) + lab((bx[3] + bw[3] + bx[4]) / 2, L.q, yc - 30);
    // boxes
    const st = s => (s && !/^(RUN|NORMAL|DIG)$/.test(s) ? AKT.stRu(s) : '');
    /* the pit: the excavators of ore (Ditto fleet / exc things); when every one stands the label is wrapped inside the box */
    const excTot = [1, 2, 3].filter(i => AKT.things['exc-' + i]), excDown = excTot.filter(i => AKT.st('exc-' + i) === 'DOWN').length;
    const allDown = excTot.length > 0 && excDown === excTot.length;
    const pitLines = allDown ? [pitTph != null ? `${fmt(pitTph)} т/ч` : '—', 'все экскаваторы', 'стоят']
      : [pitTph != null ? `${fmt(pitTph)} т/ч` : '—', 'выемка', excTot.length ? `${excTot.length - excDown} из ${excTot.length} экскав.` : ''];
    g += box(bx[0], yc - 38, bw[0], 76, 'Карьер', pitLines, allDown || excDown ? 'bad' : '');
    g += box(bx[1], yc - 38, bw[1], 76, 'Дробилка', [st(L.states.crusher) || 'идёт', L.crusher != null ? `${fmt(L.crusher)} т/ч` : '—', '+ лента'], L.states.crusher === 'STOP' ? 'bad' : '');
    if (hasStock) {
      const live = 40000, pct = Math.max(0, Math.min(1, L.level / live));
      g += `<g class="fl-box ${/^(LOW|EMPTY|FULL)$/.test(L.states.stock) ? 'warn' : ''}"><rect x="${bx[2]}" y="${yc - 48}" width="${bw[2]}" height="96" rx="3"/><text class="fl-t" x="${bx[2] + bw[2] / 2}" y="${yc - 33}" text-anchor="middle">Склад руды</text>`
        + `<rect class="fl-lvl" x="${bx[2] + 8}" y="${(yc + 36 - 56 * pct).toFixed(1)}" width="${bw[2] - 16}" height="${(56 * pct).toFixed(1)}"/><rect class="fl-vessel" x="${bx[2] + 8}" y="${yc - 20}" width="${bw[2] - 16}" height="56"/>`
        + `<text class="fl-s" x="${bx[2] + bw[2] / 2}" y="${yc + 52}" text-anchor="middle">${fmt(L.level)} т${L.hours != null && L.hours > 0 && L.hours <= 48 ? ' · ' + f1(L.hours) + ' ч' : ''}</text></g>`;
    }
    g += box(bx[3], yc - 38, bw[3], 76, 'SAG', [st(L.states.sag) || 'идёт', L.q != null ? `${fmt(L.q)} т/ч` : '—', L.sagMw != null ? `${f1(L.sagMw)} МВт` : ''], /^(STOP|RELINE)$/.test(L.states.sag) ? 'bad' : '');
    g += box(bx[4], yc - 38, bw[4], 76, 'Флотация', [st(L.states.flot) || 'идёт', L.feedCuPct != null ? `Cu ${f2(L.feedCuPct)} %` : '', L.rec != null ? `извл. ${f1(L.rec)} %` : ''], '');
    // concentrate and tails boxes
    g += `<g class="fl-box out"><rect x="${tx}" y="${y0 + 36}" width="176" height="42" rx="3"/><text class="fl-t" x="${tx + 88}" y="${y0 + 51}" text-anchor="middle">Концентрат</text><text class="fl-s" x="${tx + 88}" y="${y0 + 68}" text-anchor="middle">${L.cu != null ? esc(f1(L.cu)) : '—'} т Cu/ч · ${L.concT != null ? esc(fmt(L.concT)) : '—'} т/ч${L.concPct != null ? ' · ' + esc(f1(L.concPct)) + ' %' : ''}</text></g>`;
    g += `<g class="fl-box"><rect x="${tx}" y="${y0 + 134}" width="176" height="52" rx="3"/><text class="fl-t" x="${tx + 88}" y="${y0 + 150}" text-anchor="middle">Хвосты</text><text class="fl-s" x="${tx + 88}" y="${y0 + 167}" text-anchor="middle">${L.tailsT != null ? esc(fmt(L.tailsT)) : '—'} т/ч · Cu ${L.tailPct != null ? esc(f2(L.tailPct) + ' %') : '—'}</text>`
      + `<text class="fl-s" x="${tx + 88}" y="${y0 + 182}" text-anchor="middle">в хвосты ${L.tailsCu != null ? esc(f2(L.tailsCu)) : '—'} т Cu/ч</text></g>`;
    // red tags where the open troubles lose copper now
    [1, 2, 3, 4, 5].forEach(s => {
      const cu = loss.by[L.n + ':' + s];
      if (!(cu > 0)) return;
      const x = s === 1 ? bx[1] : s === 2 ? bx[2] : s === 3 ? bx[3] - 6 : s === 4 ? bx[4] - 4 : tx + 8;
      g += tag(x, s === 5 ? y0 + 104 : yc + 62, `−${f2(cu)} т Cu/ч`, 'loss');
    });
    g += hpgrNode(L.n, bx[3], bw[3], yc);
    return g;
  };

  /* ------------------------------------------------ oxide lane: ore -> heap -> PLS pond -> SX -> EW -> cathode store (all from Ditto) */
  const OX_BOXES = [
    ['oxfeed-1', 'Руда на кучу', t => [`${fmt(n0(t, 'ore_tph'))} т/ч`, `Cu ${f2(n0(t, 'grade_pct'))} %`, `${f2(n0(t, 'cu_tph'))} т Cu/ч`]],
    ['leach-1', 'Куча', t => [`орошение ${fmt(n0(t, 'irrigation_pct'))} %`, `куча ${fmt(n0(t, 'heap_temp_c'))} °C`, `растворяет ${f2(n0(t, 'leach_cu_tph'))} т/ч`]],
    ['pls-1', 'Пруд PLS', t => [`${fmt(n0(t, 'level_pct'))} % объёма`, `Cu ${f2(n0(t, 'pls_gl'))} г/л`, `рафинат ${f2(n0(t, 'raff_gl'))} г/л`]],
    ['sx-1', 'Экстракция SX', t => [`извлечение ${fmt(n0(t, 'extraction_pct'))} %`, `краб ${f1(n0(t, 'crud_cm'))} см`, `перенос ${f2(n0(t, 'transfer_cu_tph'))} т/ч`]],
    ['ew-1', 'Электролиз EW', t => [`ток ${f1(n0(t, 'current_ka'))} кА`, `${fmt(n0(t, 'current_density_am2'))} А/м²`, `катод ${f2(n0(t, 'cathode_tph'))} т/ч`]],
    ['catstore-1', 'Склад катода', t => [`${fmt(n0(t, 'stock_t'))} т`, `приход ${f2(n0(t, 'in_tph'))} т/ч`, `отгружено ${fmt(n0(t, 'shipped_t_total'))} т`]],
  ];
  const OX_BAD = { 'oxfeed-1': /^IDLE$/, 'leach-1': /^COLD$/, 'pls-1': /^(HIGH|FULL)$/, 'sx-1': /^(CRUD|DOWN)$/, 'ew-1': /^(TRIP)$/, 'catstore-1': /^(FULL)$/ };
  const oxLane = () => {
    const bw = 112, gap = 28, y = 20, h = 78, W2 = OX_BOXES.length * bw + (OX_BOXES.length - 1) * gap + 8;
    const loss = {};
    for (const i of AKT.issues()) { const usd = AKT.num(i, 'loss_usd_h'); if (usd > 0 && AKT.lossNow(i)) { const nd = AKT.issueNode(i); loss[nd] = (loss[nd] || 0) + usd; } }
    let g = '';
    OX_BOXES.forEach(([t, title, lines], k) => {
      const x = 4 + k * (bw + gap), st = AKT.st(t) || '';
      const bad = (OX_BAD[t] || /^$/).test(st);
      g += `<g class="fl-box ${bad ? 'bad' : ''}"><title>${esc(AKT.nameRu(t) || t)}: ${esc(AKT.stRu(st, t))}</title><rect x="${x}" y="${y}" width="${bw}" height="${h}" rx="3"/><text class="fl-t" x="${x + bw / 2}" y="${y + 15}" text-anchor="middle">${esc(title)}</text>`
        + lines(t).map((l, i) => `<text class="fl-s" x="${x + bw / 2}" y="${y + 31 + 14 * i}" text-anchor="middle">${esc(l)}</text>`).join('') + '</g>';
      if (loss[t] > 0) g += tag(x, y + h + 18, `−${AKT.approx(loss[t])}/ч`, 'loss');
      if (k < OX_BOXES.length - 1) g += `<path d="M${x + bw} ${y + h / 2} L${x + bw + gap - 2} ${y + h / 2}" stroke="currentColor" stroke-width="2.5" fill="none" marker-end="url(#ox-arr)"/>`;
    });
    const xs = 4 + 3 * (bw + gap) + bw / 2, xl = 4 + 1 * (bw + gap) + bw / 2, yb = y + h + 46;
    g += `<path class="fl-loop" d="M${xs} ${y + h} L${xs} ${yb} L${xl} ${yb} L${xl} ${y + h}" stroke-dasharray="5 4" fill="none"/><text class="fl-s" x="${(xs + xl) / 2}" y="${yb - 4}" text-anchor="middle">рафинат на кучу · ${f2(n0('pls-1', 'raff_gl'))} г/л Cu · ${fmt(n0('leach-1', 'irrigation_m3h'))} м³/ч</text>`;
    return `<svg class="fl-svg" viewBox="0 0 ${W2} ${yb + 14}" width="100%" role="img" aria-label="Окисленная цепочка: руда на кучу, куча, пруд PLS, экстракция, электролиз, склад катода; рафинат возвращается на кучу"><defs><marker id="ox-arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6 z" fill="currentColor"/></marker></defs>${g}</svg>`;
  };

  AKT.views.copper = {
    build(stage) {
      const d = doc(stage, 'copper');
      d.innerHTML = `<h2>Путь меди</h2>
<p class="lead">От карьера до концентрата и хвостов. Ширина серой полосы — т руды в час; красным — где медь теряется по открытым бедам; хвосты серые: это неизбежная часть извлечения, не отклонение. Числа — живые данные двойника, обновляются раз в 2 с.</p>
<div id="cp-flow"></div>
<div id="cp-legend"></div>
<h3>Окисленная цепочка: руда → куча → SX → электролиз → катод</h3><div id="cp-oxsvg"></div><div id="cp-ox"></div>
<h3>Баланс меди: питание = концентрат + хвосты</h3><div id="cp-cu"></div>
<h3>Баланс воды</h3><div id="cp-water"></div>`;
    },
    update() {
      const L = [lineData(1), lineData(2)];
      if (!AKT.polled || L.every(l => l.q == null)) { setHtml('cp-flow', '<p class="empty dash">Загружаю состояние фабрики…</p>'); return; }
      const loss = troubleLoss();
      const H = LANE * 2 + 56;
      const svg = `<svg class="fl-svg" viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Путь руды и меди по двум линиям: карьер, дробилка, склад, SAG (на линии 2 с валковым прессом ВВД), флотация, концентрат и хвосты">${L.map((l, i) => laneSvg(l, loss, i)).join('')}`
        + (loss.other > 0 ? tag(8, LANE * 2 + 48, `общие потери (карьер, вода, сеть): −${f2(loss.other)} т Cu/ч`, 'loss') : '') + '</svg>';
      setHtml('cp-flow', svg);
      const tot = loss.list.reduce((s, x) => s + x.cu, 0);
      setHtml('cp-legend', `<p class="fl-key"><span class="k band"></span> руда, ширина ∝ т/ч · <span class="k conc"></span> концентрат · <span class="k tails"></span> хвосты · <b class="redtxt">▲</b> красным — потери меди по открытым бедам (${loss.list.length ? '≈ ' + f2(tot) + ' т Cu/ч, ' + esc(AKT.approx(AKT.usdPerH(tot))) + '/ч' : 'нет'}). В хвосты уходит ${f2(pos(L[0].tailsCu) + pos(L[1].tailsCu))} т Cu/ч на двух линиях — неизбежная часть извлечения, серым. Потери по бедам — расчёт модуля очереди бед (≈), хвосты — измерение анализатора и расходомеров (с шумом).</p>`);
      /* oxide chain: twins linked by the flow; the quarterly figure of the reports only for the comparison */
      if (AKT.things['ew-1']) setHtml('cp-oxsvg', oxLane());
      const ox = k => AKT.num('sxew-1', k), cold = AKT.st('leach-1') === 'COLD';
      setHtml('cp-ox', ox('cathode_tph') == null ? '<p class="empty dash">Окисленная цепочка ещё не опубликована.</p>' : `<table class="kv"><tr><th>Квартал отчёта</th><th>Катод за квартал (отчёт)</th><th>Уровень квартала</th><th>Ожидает модель</th><th>Сейчас</th><th>Модель против отчёта</th></tr><tr><td class="n">${fmt(ox('quarter'))} кв. ${fmt(ox('year'), 0).replace(/\s/g, '')} г.</td><td class="n">${f2(n0('leach-1', 'quarter_cathode_kt'))} кт</td><td class="n">${f2(ox('cathode_level_tph'))} т/ч</td><td class="n">${f2(n0('ew-1', 'cathode_exp_tph'))} т/ч</td><td class="n">${f2(ox('cathode_tph'))} т/ч${cold ? ` (орошение ${fmt(n0('leach-1', 'irrigation_pct'))} %)` : ''}</td><td class="n">${ox('model_dev_pct') == null ? '—' : (ox('model_dev_pct') > 0 ? '+' : '−') + fmt(Math.abs(ox('model_dev_pct'))) + ' %'}</td></tr></table>
<p class="note">Катод сейчас — расчёт цепочки по закону Фарадея (ток × ванны × выход по току), а не замер; уровень квартала — число отчётов KAZ Minerals (катод ÷ часы квартала), не измерение. Кинетика кучи подогнана на катоде 32 кварталов 2018–2025 гг.: средняя ошибка по кварталу ≈ 10 %, график — на странице «Калибровка». Раствор, ёмкости прудов, число ванн и выход по току — допущения или аналоги (см. «Изнутри»). Дата — дата стенда; после 2025 г. берётся тот же день 2025 г. Беды цепочки — сценарии «Холодное выщелачивание на куче», «Отключение выпрямителя электролиза», «Краб в отстойнике SX».</p>`);
      /* copper balance table */
      const cell = (v, d = 2) => v == null ? '—' : fmt(Math.abs(v) < 0.5 * Math.pow(10, -d) ? 0 : v, d);
      const sum = f => (L[0][f] != null && L[1][f] != null) ? L[0][f] + L[1][f] : null;
      const rp = (a, b) => a != null && b ? 100 * a / b : null;
      const rows = [['Cu в питании (руда × содержание)', 'feedCu'], ['Cu в концентрате', 'cu'], ['Cu в хвостах', 'tailsCu'], ['невязка = питание − концентрат − хвосты', 'resid']];
      const ml = AKT.num('mod-losses', 'cu_residual_pct');
      const body = rows.map(([t, f]) => `<tr><td>${t}</td><td class="n">${cell(L[0][f])}</td><td class="n">${cell(L[1][f])}</td><td class="n"><b>${cell(sum(f))}</b></td></tr>`).join('');
      const rs = sum('resid'), fs = sum('feedCu');
      setHtml('cp-cu', `<table class="kv"><tr><th>т Cu/ч сейчас</th><th>Линия 1</th><th>Линия 2</th><th>Всего</th></tr>${body}
<tr><td>невязка, % от питания</td><td class="n">${cell(rp(L[0].resid, L[0].feedCu), 1)}</td><td class="n">${cell(rp(L[1].resid, L[1].feedCu), 1)}</td><td class="n"><b>${cell(rp(rs, fs), 1)}</b></td></tr>
<tr><td>извлечение (концентрат / питание)</td><td class="n">${cell(rp(L[0].cu, L[0].feedCu), 1)} %</td><td class="n">${cell(rp(L[1].cu, L[1].feedCu), 1)} %</td><td class="n"><b>${cell(rp(sum('cu'), fs), 1)} %</b></td></tr></table>
<p class="note">Мгновенные показания приборов с шумом (анализаторы ±, весы ±1 %): невязка в пределах нескольких процентов — это шум, а не потеря. Точный баланс — по счётчикам весов и расходомеров за 2 ч модуля «Где теряется медь»: ${ml == null ? 'мало точек' : `<b class="${Math.abs(ml) < 0.5 ? 'ok' : 'bad'}">${f2(ml)} %</b> (допуск 0,5 %)`}. Хвосты: питание × содержание хвостов — расчёт из измерений.</p>`);
      /* water balance */
      const w = k => n0('water', k), tph = n0('site', 'tph');
      const per = v => (v != null && tph > 0 ? v / tph : null);
      const wrows = [['Свежая вода (забор)', 'intake_m3h'], ['Оборотная вода (возврат с хвостохранилища)', 'recycle_m3h'], ['Уходит с хвостами (вода в порах)', 'tails_loss_m3h'], ['Испарение и фильтрация', 'evap_m3h']]
        .map(([t, k]) => `<tr><td>${t}</td><td class="n">${w(k) == null ? '—' : fmt(w(k))} м³/ч</td><td class="n">${per(w(k)) == null ? '—' : f2(per(w(k)))} м³/т</td></tr>`).join('');
      const wr = AKT.num('mod-losses', 'water_residual_pct');
      setHtml('cp-water', `<table class="kv"><tr><th>Поток воды сейчас</th><th>м³ в час</th><th>на тонну руды (${tph == null ? '—' : fmt(tph)} т/ч)</th></tr>${wrows}
<tr><td>Пруд хвостохранилища</td><td class="n">${w('pond_m3') == null ? '—' : f2(w('pond_m3') / 1e6)} млн м³</td><td class="n">—</td></tr></table>
<p class="note"><b>Против факта:</b> KAZ Minerals — забор воды 0,60 м³ на тонну переработанной руды в 2024 г. (среднее группы; для Актогая расчёт 34 852 Мл / 58,3 Мт ≈ 0,60) [факт, страница Water на kazminerals.com; расчёт]. Это интенсивность забора по группе, не сопоставимая «в точности» величина фабрики: определение забора и состав руды могут отличаться. Наш «Свежая вода» — ${per(w('intake_m3h')) == null ? '—' : f2(per(w('intake_m3h')))} м³/т сейчас. Невязка баланса воды (забор − потери − пруд) за 2 ч: ${wr == null ? 'мало точек' : `<b class="${Math.abs(wr) < 0.5 ? 'ok' : 'bad'}">${f2(wr)} %</b>`}.</p>`);
    },
  };

  /* ---------------------------------------------------------------- «Участки» */
  const AREAS = [
    { id: 'crush', name: 'Дробление и склад руды', nodes: ['crusher-1', 'crusher-2', 'conveyor-1', 'conveyor-2', 'stockpile-1', 'stockpile-2'], num: () => `дробилки ${fmt((n0('crusher-1', 'tph') || 0) + (n0('crusher-2', 'tph') || 0))} т/ч`, link: 'line1' },
    { id: 'grind', name: 'Измельчение', nodes: ['sag-1', 'sag-2', 'pebble-1', 'pebble-2', 'ball-1a', 'ball-1b', 'ball-2a', 'ball-2b', 'cyclones-1', 'cyclones-2'], num: () => `SAG ${fmt((n0('sag-1', 'feed_tph') || 0) + (n0('sag-2', 'feed_tph') || 0))} т/ч`, link: 'line1' },
    { id: 'flot', name: 'Флотация', nodes: ['flot-1', 'flot-2', 'rougher-1', 'rougher-2', 'cleaner-1', 'cleaner-2'], num: () => `медь ${f1(n0('site', 'cu_tph'))} т/ч`, link: 'line1' },
    { id: 'thick', name: 'Сгущение и фильтрация', nodes: ['thick-1', 'thick-2', 'filter-1', 'filter-2', 'conc-stock'], num: () => `склад концентрата ${fmt(n0('conc-stock', 'stock_t'))} т`, link: 'line2' },
    { id: 'tails', name: 'Хвосты', nodes: ['water', 'piezo-1', 'piezo-2', 'piezo-3'], num: () => `пруд ${n0('water', 'pond_m3') == null ? '—' : f2(n0('water', 'pond_m3') / 1e6)} млн м³`, link: 'copper' },
    { id: 'util', name: 'Вода и энергия', nodes: ['water', 'power'], num: () => `сеть ${fmt(n0('power', 'site_mw'))} из ${fmt(n0('power', 'grid_limit_mw'))} МВт`, link: 'copper' },
  ];
  const worst = nodes => { let lv = 0, who = ''; for (const n of nodes) { if (!AKT.things[n]) continue; const l = AKT.levelOf(n); if (l && (!lv || l < lv)) { lv = l; who = n; } } return { lv, who }; };

  AKT.views.areas = {
    build(stage) {
      const d = doc(stage, 'areas');
      d.innerHTML = `<h2>Участки</h2>
<p class="lead">Шесть участков фабрики. Серая рамка — всё в норме; цвет и значок появляются только у отклонения, внутри — что именно и сколько это стоит.</p>
<div class="ar-grid" id="ar-grid"></div>
<h3>Карты и модель</h3>
<ul class="ar-links"><li><a href="${AKT.href('?view=line&n=1')}">Схема линии 1</a> — склад → SAG → шаровые → циклоны → флотация → фильтр</li>
<li><a href="${AKT.href('?view=line&n=2')}">Схема линии 2</a> — то же, линия 2 (ВВД, безредукторные мельницы)</li>
<li><a href="${AKT.href('?view=copper')}">Путь меди</a> — поток руды и меди, балансы меди и воды</li>
<li><a href="${AKT.href('?view=diorama')}">Диорама</a> и <a href="${AKT.href('?view=site')}">Спутник 3D</a> — рудник как макет и по снимку</li>
<li><a href="${AKT.href('?view=ore')}">Руда</a> — партии, прогноз на 12 ч · <a href="${AKT.href('?view=tree')}">Состав двойника</a> · <a href="${AKT.href('?view=text')}">Всё текстом</a></li>
<li><a href="${AKT.href('?view=inside')}">Изнутри</a> — руда, дамба, люди, машины, фабрика, данные: узлы, сигналы (где виден каждый), типовые отказы и их источники</li></ul>`;
    },
    update() {
      const issues = AKT.issues();
      setHtml('ar-grid', AREAS.map(a => {
        const w = worst(a.nodes), cnt = issues.filter(i => a.nodes.includes(AKT.issueNode(i))).length;
        const what = w.lv ? `${AKT.glyph(w.lv)} <b>${esc(AKT.nameRu(w.who))}</b>: ${esc(AKT.stOf(w.who))}` : 'в норме';
        return `<a class="ar-card ${w.lv ? 'lv-' + w.lv : ''}" href="${AKT.href('?view=' + (a.link === 'line1' ? 'line&n=1' : a.link === 'line2' ? 'line&n=2' : a.link))}"><div class="ar-h">${esc(a.name)}</div><div class="ar-n">${esc(a.num())}</div><div class="ar-w">${what}${cnt ? ` · бед: ${cnt}` : ''}</div></a>`;
      }).join(''));
    },
  };
})();
