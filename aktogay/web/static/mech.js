/* Screen of the mechanic (?view=mech, a view by role, not a menu item of the dispatcher): a narrow page for a tablet.
   «Мои вызовы» · «Работа» (что, где, наряд, точки отключения, как проверить) · «Статус» (принял / в пути / на месте /
   нужна помощь / готово). The status is the addressee's own: it goes to the thing `journal` (feature `mech`) through
   POST /api/mech, the priority module reads it and the dispatcher's trouble card shows the life cycle with the mark
   «(механик)». Touch targets are at least 48 px. Everything on the page is read from Ditto. */
'use strict';
(function () {
  const esc = AKT.esc;
  const KEY = 'akt-mech-person';
  const STATUS = [['accepted', 'Принял'], ['enroute', 'В пути'], ['onsite', 'На месте'], ['help', 'Нужна помощь'], ['done', 'Готово']];
  const doc = (stage, id) => { stage.innerHTML = ''; const d = document.createElement('div'); d.className = 'doc'; d.id = id; stage.appendChild(d); return d; };
  const setHtml = (id, html) => { const e = document.getElementById(id); if (e && e._raw !== html) { e._raw = html; e.innerHTML = html; } };
  const NOT_FOUND = 'уточнить по регламенту площадки';
  /* the person a call is addressed to: the chain's pick when the main person is busy on a permit, else the person of the issue */
  const onJob = (p, i) => ['TRAVEL', 'WORK'].includes(AKT.st(p)) && String(AKT.val(p, 'task') || '').split(',').map(x => AKT.name(x.trim())).includes(AKT.issueNode(i));
  const target = i => {
    const main = AKT.issuePerson(i);
    if (main && onJob(main, i)) return main;          /* the person is on the way to this node or works there: the call is his, whatever the chain says now */
    const ch = AKT.val(i, 'chain') || {};
    const pick = ch.via && ch.pick ? AKT.name(String(ch.pick)) : '';
    return pick && AKT.things[pick] ? pick : AKT.issuePerson(i);
  };
  const mine = p => AKT.issues().filter(i => AKT.issueCalled(i) && target(i) === p);
  const mechItems = () => { const m = AKT.val('journal', 'mech'); return m && typeof m === 'object' && m.items && typeof m.items === 'object' ? m.items : {}; };
  const entry = i => { const e = mechItems()[i]; return e && typeof e === 'object' && (!AKT.run || e.run === AKT.run) ? e : null; };
  const sentences = t => String(t || '').split(/(?<=[.;])\s+/).filter(Boolean);

  AKT.views.mech = {
    person: '', sel: '', local: {}, busy: false,
    build(stage) {
      document.body.classList.add('mech');
      const d = doc(stage, 'mech');
      d.innerHTML = `<div class="mh"><h2>Экран механика</h2><label>Кто вы <select id="mh-person" aria-label="Кто вы"></select></label>
<span class="note" id="mh-me"></span></div>
<h3>Мои вызовы</h3><div id="mh-calls"></div>
<h3>Работа</h3><div id="mh-work"></div>
<h3>Статус</h3><div id="mh-status"></div>
<p class="note" id="mh-msg" role="status" aria-live="polite"></p>
<p class="note">Статус пишется в журнал смены и виден диспетчеру на карточке беды. Данные экрана берутся из двойника; сам экран ничего не считает.</p>`;
      const sel = document.getElementById('mh-person');
      const people = AKT.ofType('person');
      sel.innerHTML = people.map(p => `<option value="${esc(p)}">${esc(AKT.nameRu(p))}</option>`).join('');
      let p = AKT.params.get('person') || AKT.store.get(KEY) || '';
      p = AKT.things[p] ? p : (AKT.things['person-' + p] ? 'person-' + p : '');
      this.person = p || people.find(x => mine(x).length) || people[0] || '';
      sel.value = this.person;
      sel.addEventListener('change', () => { this.person = sel.value; this.sel = ''; AKT.store.set(KEY, this.person); this.update(); });
      d.addEventListener('click', ev => {
        const c = ev.target.closest('[data-call]'); if (c) { this.sel = c.dataset.call; this.update(); return; }
        const s = ev.target.closest('[data-status]'); if (s && !s.disabled) this.send(s.dataset.status);
      });
    },
    destroy() { document.body.classList.remove('mech'); },
    async send(status) {
      const issue = this.sel;
      if (!issue || this.busy) return;
      this.busy = true;
      const label = STATUS.find(x => x[0] === status)[1];
      const msg = document.getElementById('mh-msg');
      try {
        const r = await AKT.post('/api/mech', { issue, status, person: this.person });
        this.local[issue] = { status, t: AKT.simTime };
        msg.textContent = r && r.training ? `${label}: учебная отметка, в журнал не записана.` : `${label}: отправлено в ${AKT.clock(AKT.simTime)} модели, диспетчер увидит на карточке беды.`;
      } catch (e) { msg.textContent = `${label}: не получилось отправить (${e.message}). Нажмите ещё раз.`; }
      this.busy = false;
      this.update();
    },
    update() {
      const p = this.person;
      if (!p) { setHtml('mh-calls', '<p class="empty dash">В двойнике нет людей смены.</p>'); return; }
      const info = AKT.personInfo(p);
      setHtml('mh-me', `${AKT.nameRu(p)}: ${AKT.personAvail(p)}`);
      const list = mine(p);
      if (!list.includes(this.sel)) this.sel = list[0] || '';
      setHtml('mh-calls', list.length ? list.map(i => {
        const at = AKT.life(i), step = at && at.steps.find(x => x.key === 'called');
        return `<button type="button" class="mh-call${i === this.sel ? ' on' : ''}" data-call="${esc(i)}" aria-pressed="${i === this.sel}">
<b>${esc(AKT.issueTitle(i))}</b><span>${esc(AKT.placeRu(AKT.issueNode(i)))}${step && step.t >= 0 ? ` · позвали в ${AKT.clock(step.t)}` : ''}</span></button>`;
      }).join('') : '<p class="empty dash">Вызовов нет. Вас пока никто не звал: диспетчер нажмёт «Позвать», и вызов появится здесь.</p>');
      const n = this.sel;
      if (!n) { setHtml('mh-work', '<p class="empty dash">Работы нет.</p>'); setHtml('mh-status', '<p class="note">Статус можно поставить, когда есть вызов.</p>'); return; }
      const m = AKT.issueMain(n);
      const checklist = String(AKT.val(n, 'checklist') || '').replace(/^Что делать:\s*/, '');
      const closure = String(AKT.val(n, 'closure') || '').replace(/^Закроется:\s*/, '');
      const off = sentences(checklist).filter(x => /отключ|плакат|напряжен|огражд|оград/i.test(x));
      const permit = String(AKT.val(n, 'permit_text') || '') || (AKT.val(p, 'permit') ? `по наряду-допуску: ${AKT.placeRu(AKT.name(String(AKT.val(p, 'permit'))))}` : '');
      const kv = (k, v) => `<dt>${k}</dt><dd>${v}</dd>`;
      setHtml('mh-work', `<dl class="mh-dl">
${kv('Что', `<b>${esc(AKT.issueTitle(n))}</b>. ${esc(AKT.issueWhy(n) || '')}`)}
${kv('Где', esc(AKT.placeRu(AKT.issueNode(n))) + (AKT.parent(AKT.issueNode(n)) ? ` · ${esc(AKT.nameRu(AKT.parent(AKT.issueNode(n))))}` : ''))}
${kv('Сколько стоит', `${esc(m.text)}${m.small ? ' <span class="note">' + esc(m.small) + '</span>' : ''}`)}
${kv('Наряд-допуск', permit ? esc(permit) : 'Работы повышенной опасности — только по наряду-допуску (Правила № 348, п. 12); по этой работе в двойнике наряда нет — оформляет начальник смены.')}
${kv('Точки отключения', off.length ? esc(off.join(' ')) : esc(NOT_FOUND))}
${kv('Что делать', esc(checklist || NOT_FOUND))}
${kv('Как проверить, что готово', esc(closure || 'Сигнал вернулся в норму: двойник сам закроет беду.'))}
</dl>`);
      const e = entry(n), loc = this.local[n], cur = (loc && (!e || (loc.t != null && (e.t == null || loc.t >= e.t))) ? loc : e) || {};
      const log = (e && Array.isArray(e.log) ? e.log : []).map(x => `${(STATUS.find(s => s[0] === x.s) || [0, x.s])[1]} ${AKT.clock(x.t)}`).join(' → ');
      setHtml('mh-status', `<div class="mh-btns">${STATUS.map(([k, t]) => `<button type="button" class="mh-st${cur.status === k ? ' on' : ''}${k === 'help' ? ' help' : ''}" data-status="${k}" aria-pressed="${cur.status === k}"${this.busy ? ' disabled' : ''}>${cur.status === k ? '✔ ' : ''}${t}</button>`).join('')}</div>
<p class="note">${log ? `Вы отметили: ${esc(log)}.` : 'Пока ничего не отмечено.'}${info && info.tr ? ` По двойнику вы в пути, будете ≈ ${AKT.clock(info.tr.eta)}.` : ''}</p>`);
    },
  };
})();
