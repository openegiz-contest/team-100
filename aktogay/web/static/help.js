/* Help layer: the glossary (tooltips on terms, a window with all terms), the tour «Как пользоваться»
   (8 steps) and «Спросить двойник» — answers to the dispatcher's questions built from templates over the
   live data of the twin. No network beyond the stand's own /api, no language model: a question that no
   template knows gets an honest "не знаю" with the questions that work. */
'use strict';
(function () {
  const esc = AKT.esc, fmt = AKT.fmt, f1 = AKT.f1, f2 = AKT.f2, f3 = AKT.f3;

  /* ------------------------------------------------------------ glossary */
  /* [key, term, plain words, regex for automatic marking (null — only explicit)] */
  const TERMS = [
    ['twin', 'Цифровой двойник', 'Модель фабрики, которая ведёт себя как настоящая: по ней видно, что происходит и что будет, если ничего не делать.', /цифров\w* двойник\w*/i],
    ['simtime', 'Время модели, ×60', 'Часы двойника. При ×60 одна минута на экране — один час смены.', /время модели/i],
    ['shift', 'Смена', '12 часов, с 08:00 до 20:00.', null],
    ['issue', 'Беда', 'Всё, что угрожает людям или уменьшает выпуск меди: поломка, ограничение, скрытая потеря.', null],
    ['delay', 'Час промедления', 'Сколько денег добавится к потерям, если позвать человека на час позже. По нему решается, кого звать первым.', /час промедления/i],
    ['callby', 'Позвать до', 'Последний момент, когда звать ещё не поздно: запас (склад руды, сгуститель) держит до этого времени.', /позвать[^.]{0,40}? до \d/i],
    ['s0', 'Класс S0 / S1', 'S0 — опасность для людей или дамбы, S1 — риск поломки оборудования. Идут первыми, деньги не считаются.', /\bS[01]\b/],
    ['est', '≈ (оценка)', 'Число посчитано моделью, а не измерено прибором.', null],
    ['asm', 'д (допущение)', 'Числа нет в открытых источниках, принято разумное значение.', null],
    ['cpd', 'ЦПД', 'Дробильный комплекс у карьера: дробит руду перед конвейером на склад.', /ЦПД/],
    ['stockpile', 'Склад руды (штабель)', 'Запас дроблёной руды перед фабрикой; пока он есть, остановка дробилки не останавливает фабрику.', /склад\w* руды|штабел\w*/i],
    ['sag', 'SAG (мельница полусамоизмельчения)', 'Первая большая мельница линии: руда мелет сама себя с добавкой стальных шаров.', /\bSAG\b/],
    ['ball', 'Шаровая мельница', 'Вторая ступень помола, домалывает руду до тонкого песка.', /шаров\w+ мельниц\w*|шаров\w+/i],
    ['liner', 'Футеровка', 'Стальная броня внутри мельницы; изнашивается, её меняют (перефутеровка, ≈ 5 суток простоя).', /(пере)?футеровк\w*/i],
    ['pebble', 'Галя, дробление гали (HPGR)', 'Крупные куски, которые SAG не домолола; их дробят отдельно на прессе (HPGR) и возвращают в мельницу.', /гал[иья]\b|HPGR/i],
    ['cyclones', 'Гидроциклоны', 'Разделяют пульпу: тонкое — на флотацию, крупное — обратно на домол.', /гидроциклон\w*|циклон\w*/i],
    ['p80', 'Крупность помола (P80)', '80 % частиц мельче этого размера, мкм. Чем мельче, тем больше меди извлекается, но больше энергии.', /P80|крупность помола/],
    ['flot', 'Флотация', 'Медь цепляется к пузырькам воздуха и всплывает в пену — так получают концентрат.', /флотаци\w*/i],
    ['cleaner', 'Перечистка', 'Повторная флотация чернового концентрата: поднимает долю меди в нём.', /перечистк\w*/i],
    ['conc', 'Концентрат', 'Продукт фабрики: около 24 % меди; уходит поездом.', /концентрат\w*/i],
    ['tails', 'Хвосты', 'Пустая порода после флотации; уходит в хвостохранилище. Медь в хвостах — потеря.', /хвост(ы|ах|ов)\b/i],
    ['dam', 'Хвостохранилище', 'Пруд с дамбой, куда уходят хвосты; из него берут оборотную воду.', /хвостохранилищ\w*/i],
    ['recovery', 'Извлечение', 'Какая доля меди из руды попала в концентрат, %.', /извлечени\w*/i],
    ['pp', 'п.п. (процентный пункт)', 'Разница между процентами: 88 % → 87 % — это −1 п.п.', /п\.\s?п\./],
    ['cutph', 'т меди в час', 'Тонн меди в час в концентрате.', /т Cu\/ч/],
    ['grade', 'Медь в руде, %', 'Сколько меди в руде; на Актогае около 0,4 %.', /медь в руде|% Cu\b/i],
    ['axb', 'A×b', 'Мягкость руды. Меньше — твёрже, мельница мелет медленнее. М ≥ 38, С 30–38, Т < 30.', /A×b/],
    ['batch', 'Партия', '15 000 т руды из одного блока карьера.', /\bпарти[яиюей]\b/i],
    ['thick', 'Сгуститель', 'Чан, где из концентрата отстаивается вода; его ёмкость — запас перед фильтрами.', /сгустител\w*/i],
    ['filter', 'Фильтр (пресс)', 'Отжимает воду из концентрата; на линии два пресса.', /фильтр\w*/i],
    ['kip', 'КИПиА', 'Контрольно-измерительные приборы и автоматика; дежурный КИПиА чинит датчики.', /КИПиА/],
    ['piezo', 'Пьезометр', 'Датчик давления воды в теле дамбы хвостохранилища; рост давления — риск для дамбы.', /пьезометр\w*/i],
    ['recycle', 'Оборотная вода', 'Вода, которую возвращают из хвостохранилища на фабрику.', /оборотн\w+ вод\w*/i],
    ['setpoint', 'Уставка', 'Значение, которое автоматика держит или при котором подаёт сигнал.', /уставк\w*/i],
    ['grid', 'Из сети', 'Сколько мощности фабрика берёт из сети (с учётом потерь в приводе).', /из сети/i],
    ['lme', 'Цена меди, LME', 'Биржевая цена меди в Лондоне, $/т; стоимость меди считается по ней за вычетом платы переработчику.', /\bLME\b/],
    ['scenario', 'Учебный сценарий', 'Учебная поломка, которую запускают в модели, чтобы проверить, как двойник её найдёт.', /учебн\w+ сценари\w*/i],
    ['check', 'Режим проверки модели', 'Показывает то, чего диспетчер на смене не знает: скрытые причины и ход «без сценария».', /режим\w* проверки модели/i],
    ['roping', 'Канатирование', 'Нижний слив гидроциклона идёт жгутом: циклон перестаёт делить пульпу, перелив грубеет, циркулирующая нагрузка и нагрузка шаровой растут.', /канатирован\w*|роп(инг|ing)/i],
    ['skew', 'Перекос ВВД', 'Валки пресса давят неравномерно по ширине (чаще из-за неровного питания по крупности): зазор по краям разный, производительность падает.', /перекос\w* (валк\w*|ВВД)|перекос ВВД/i],
    ['dataage', 'Возраст данных', 'Сколько времени модели прошло с замера или с публикации числа. Старое число — повод проверить прибор: решение нельзя строить на нём вслепую.', /возраст\w* данных|данные \d+ мин назад/i],
    ['suspect', 'Под подозрением', 'Прибор может показывать неверно (старое показание, расхождение с контрольной пробой, дрейф). Показание не отбрасывается, но проверяется второй пробой.', /под подозрением/i],
    ['permit', 'Наряд-допуск', 'Письменное разрешение на опасную работу (например, внутри мельницы): человек по наряду до конца работ недоступен для другого вызова. Правила № 348, п. 12 и 63.', /наряд[- ]допуск\w*/i],
    ['loss_where', 'Где теряем медь', 'Модуль сравнивает, сколько меди узел должен давать по своей мощности и руде, с тем, что даёт. Разница больше точности приборов — это потеря.', null],
  ];
  const BY = {}; TERMS.forEach(t => { BY[t[0]] = t; });
  AKT.TERMS = TERMS;
  AKT.term = (key, text) => BY[key] ? `<abbr class="term" data-term="${key}" tabindex="0">${esc(text || BY[key][1])}</abbr>` : esc(text);
  const SKIP = /^(A|BUTTON|ABBR|SCRIPT|STYLE|INPUT|TEXTAREA|SELECT|OPTION|LABEL|SUMMARY|CODE|PRE|svg|SVG|TH)$/;
  /* marks the first use of each known term inside el (once per term) */
  AKT.glossify = el => {
    if (!el) return;
    const done = new Set(Array.from(el.querySelectorAll('[data-term]')).map(x => x.dataset.term));
    const walk = node => {
      for (let c = node.firstChild; c; c = c.nextSibling) {
        if (c.nodeType === 1) { if (!SKIP.test(c.tagName) && !c.classList.contains('term') && !c.closest('svg')) walk(c); continue; }
        if (c.nodeType !== 3 || !c.nodeValue || c.nodeValue.length < 2) continue;
        for (const [key, , , re] of TERMS) {
          if (!re || done.has(key)) continue;
          const m = re.exec(c.nodeValue);
          if (!m) continue;
          done.add(key);
          const after = c.splitText(m.index);
          after.splitText(m[0].length);
          const ab = document.createElement('abbr'); ab.className = 'term'; ab.dataset.term = key; ab.tabIndex = 0;
          ab.textContent = after.nodeValue;
          after.parentNode.replaceChild(ab, after);
          c = ab;
          break;
        }
      }
    };
    walk(el);
  };
  /* one tooltip for every term: hover and keyboard focus */
  let tip = null, tipFor = null;
  const showTip = el => {
    const t = BY[el.dataset.term]; if (!t) return;
    if (!tip) { tip = document.createElement('div'); tip.id = 'term-tip'; tip.setAttribute('role', 'tooltip'); document.body.appendChild(tip); }
    tip.innerHTML = `<b>${esc(t[1])}</b>${esc(t[2])}`;
    tip.hidden = false; tipFor = el;
    const r = el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    let x = Math.max(6, Math.min(window.innerWidth - w - 6, r.left));
    let y = r.bottom + 6; if (y + h > window.innerHeight - 6) y = r.top - h - 6;
    tip.style.left = x + 'px'; tip.style.top = Math.max(6, y) + 'px';
    el.setAttribute('aria-describedby', 'term-tip');
  };
  const hideTip = () => { if (tip) tip.hidden = true; if (tipFor) tipFor.removeAttribute('aria-describedby'); tipFor = null; };
  document.addEventListener('mouseover', ev => { const el = ev.target.closest && ev.target.closest('[data-term]'); if (el) showTip(el); else if (tipFor) hideTip(); });
  document.addEventListener('focusin', ev => { const el = ev.target.closest && ev.target.closest('[data-term]'); if (el) showTip(el); else hideTip(); });
  document.addEventListener('keydown', ev => { if (ev.key === 'Escape') hideTip(); });
  document.addEventListener('scroll', hideTip, true);

  AKT.glossaryHtml = () => `<dl class="gl-list">${TERMS.map(t => `<dt id="gl-${t[0]}">${esc(t[1])}</dt><dd>${esc(t[2])}</dd>`).join('')}</dl>`;
  /* the glossary window (menu «Словарь», key /) */
  AKT.glossary = {
    el: null,
    open() {
      if (!this.el) {
        const d = this.el = document.createElement('div'); d.id = 'gloss'; d.className = 'drawer'; d.setAttribute('role', 'dialog'); d.setAttribute('aria-labelledby', 'gl-h');
        d.innerHTML = `<header><h2 id="gl-h">Словарь</h2><button type="button" data-x aria-label="Закрыть словарь">×</button></header>
<form role="search"><input type="search" id="gl-q" placeholder="Найти термин" aria-label="Найти термин"></form><div class="a-log" id="gl-body">${AKT.glossaryHtml()}</div>`;
        document.body.appendChild(d);
        d.querySelector('[data-x]').addEventListener('click', () => this.close());
        d.querySelector('form').addEventListener('submit', ev => ev.preventDefault());
        d.querySelector('#gl-q').addEventListener('input', ev => {
          const q = ev.target.value.trim().toLowerCase();
          d.querySelectorAll('dt').forEach(dt => { const dd = dt.nextElementSibling; const hit = !q || (dt.textContent + ' ' + dd.textContent).toLowerCase().includes(q); dt.hidden = !hit; dd.hidden = !hit; });
        });
        d.addEventListener('keydown', ev => { if (ev.key === 'Escape') this.close(); });
      }
      if (AKT.ask && AKT.ask.el) AKT.ask.close();
      this.el.hidden = false; this.el.querySelector('#gl-q').focus();
    },
    close() { if (this.el) this.el.hidden = true; const b = document.getElementById('btn-gloss'); if (b) b.focus(); },
  };

  /* ------------------------------------------------------------ tour */
  const STEPS = [
    { sel: ['#topcard', '#tc-empty', '#now'], h: 'Беда №1 и кого звать', p: 'Время здесь модельное: при ×60 минута равна часу смены. Строка сверху и карточка справа называют главную беду, сколько меди она стоит и кого звать первым: сначала безопасность людей, потом то, где час промедления дороже. «Позвать …» записывает вызов в журнал смены, «Не сейчас…» откладывает с причиной.' },
    { sel: ['#plan-wrap', '#line-wrap', '#dio-wrap', '#s3-wrap', '#stage'], h: 'Как беда расходится по карте', p: 'Серое работает как надо, цвет только у отклонений. Номер в тёмном круге — место беды в очереди. Учебный сценарий (в «Пульте модели» внизу панели: дробилка, сеть, твёрдая руда, вода, износ узлов — привод SAG, ролики, пена, граблины, ткань, насос, тормоза, гусеницы) запускается там же: на карте видно, какие узлы и линии задело, а в «Пути меди» (меню «Сейчас») — где теряется медь.' },
    { sel: ['#dio-wrap', '#s3-wrap', '#stage'], h: '3D и «Разобрать»', p: 'Вид «3D» открывается по нажатию, пока вы его не откроете, он не рисуется и не нагружает компьютер. Нажмите на аппарат, затем «Разобрать»: деталь, о которой беда (кольцевой двигатель SAG, ролики, ткань фильтра, граблины, тормоза самосвала), подсвечена.' },
    { sel: ['#stage', '#plan-wrap'], h: 'Изнутри', p: 'Меню «Анализ» → «Изнутри» (?view=inside): у каждого узла сигналы, где их видно на настоящей фабрике, типовые отказы с источником и глубина данных A / B / C. Цифры без источника помечены «допущение», «пример» или «аналог».' },
    { sel: ['#sim', '#stage'], h: 'Рычаги модели и «Применить совет»', p: '«Пульт модели» → «Рычаги модели» (?view=levers): подача SAG по линиям ±20 %, целевой P80 160–200 мкм, доза собирателя. Это управление моделью, не фабрикой: рычаги выключены по умолчанию, ограничены и сбрасываются кнопкой «Отмена». На карточке беды со сменой режима (износ футеровки, грубый помол) кнопка «Применить совет в модели» одним нажатием ставит рычаг и показывает «было → стало».' },
    { sel: ['#tiles', '#stage'], h: 'Польза: опыт и цена часа промедления', p: 'Плитки показывают медь, руду, извлечение, сеть; знак ≈ — расчёт модели, а не прибор. «Анализ» → «Экономика» и «Повтор смены» — сколько меди двойник сберёг по сравнению с работой «как сейчас» и во что обходится час промедления по видам бед. Это оценка на калиброванной модели, нижняя граница.' },
    { sel: ['#stage', '#now'], h: 'Как проверить', p: 'Меню «Обучение и справка» → «Как проверить»: таблица «утверждение → где посмотреть», живой статус модулей, сценарии из каталога с пунктом «что должно произойти». «Калибровка» показывает сверку модели с отчётами и честную долю допущений.' },
    { sel: ['#now'], h: 'Что ещё под рукой', p: 'Кнопка «Спросить двойник» отвечает на вопросы по данным двойника («почему эта беда первая?», «сколько теряем?»), «Словарь» объясняет термины, «Сдать смену» собирает лист сдачи. Повторить этот тур можно в любой момент: «Как пользоваться».' },
  ];
  AKT.tour = {
    i: 0, card: null, hole: null, prev: null,
    target(st) { for (const s of st.sel) { const e = document.querySelector(s); if (e && !e.hidden && e.offsetParent !== null && e.getBoundingClientRect().height > 0) return e; } return document.getElementById('stage'); },
    start() {
      if (AKT.ask) AKT.ask.close(); if (AKT.glossary) AKT.glossary.close();
      this.prev = document.activeElement;
      if (!this.card) {
        this.hole = document.createElement('div'); this.hole.id = 'tour-hole'; document.body.appendChild(this.hole);
        const c = this.card = document.createElement('div'); c.id = 'tour-card'; c.setAttribute('role', 'dialog'); c.setAttribute('aria-labelledby', 'tour-h'); c.setAttribute('aria-describedby', 'tour-p'); c.tabIndex = -1;
        c.innerHTML = `<h2 id="tour-h"></h2><p id="tour-p"></p><div class="t-btns"><button type="button" data-b>Назад</button><button type="button" class="primary" data-n>Дальше</button><button type="button" data-e>Закончить</button><span class="t-step" id="tour-s"></span></div>`;
        document.body.appendChild(c);
        c.querySelector('[data-b]').addEventListener('click', () => this.go(this.i - 1));
        c.querySelector('[data-n]').addEventListener('click', () => this.go(this.i + 1));
        c.querySelector('[data-e]').addEventListener('click', () => this.end());
        c.addEventListener('keydown', ev => {
          if (ev.key === 'ArrowRight') { ev.preventDefault(); this.go(this.i + 1); }
          else if (ev.key === 'ArrowLeft') { ev.preventDefault(); this.go(this.i - 1); }
          else if (ev.key === 'Escape') { ev.preventDefault(); this.end(); }
        });
        window.addEventListener('resize', () => { if (!this.card.hidden) this.place(); });
      }
      this.card.hidden = false; this.hole.hidden = false;
      this.go(0);
    },
    go(i) {
      if (i >= STEPS.length) return this.end();
      this.i = Math.max(0, i);
      const st = STEPS[this.i];
      this.card.querySelector('#tour-h').textContent = `${this.i + 1}. ${st.h}`;
      this.card.querySelector('#tour-p').textContent = st.p;
      this.card.querySelector('#tour-s').textContent = `шаг ${this.i + 1} из ${STEPS.length}`;
      this.card.querySelector('[data-b]').disabled = this.i === 0;
      this.card.querySelector('[data-n]').textContent = this.i === STEPS.length - 1 ? 'Готово' : 'Дальше';
      const t = this.target(st);
      if (t && t.scrollIntoView) t.scrollIntoView({ block: 'nearest' });
      this.place();
      this.card.focus();
    },
    place() {
      const t = this.target(STEPS[this.i]);
      const r = t.getBoundingClientRect();
      const pad = 4, vw = window.innerWidth, vh = window.innerHeight;
      const x0 = Math.max(2, r.left - pad), y0 = Math.max(2, r.top - pad), x1 = Math.min(vw - 2, r.right + pad), y1 = Math.min(vh - 2, r.bottom + pad);
      Object.assign(this.hole.style, { left: x0 + 'px', top: y0 + 'px', width: (x1 - x0) + 'px', height: (y1 - y0) + 'px' });
      const c = this.card, w = c.offsetWidth, h = c.offsetHeight;
      let x, y;
      if (vw - x1 > w + 16) { x = x1 + 12; y = y0; }
      else if (x0 > w + 16) { x = x0 - w - 12; y = y0; }
      else if (vh - y1 > h + 16) { x = x0; y = y1 + 12; }
      else { x = x0 + 12; y = y0 + 12; }
      c.style.left = Math.max(8, Math.min(vw - w - 8, x)) + 'px';
      c.style.top = Math.max(8, Math.min(vh - h - 8, y)) + 'px';
    },
    end() {
      if (this.card) { this.card.hidden = true; this.hole.hidden = true; }
      AKT.store.set('akt-tour', 'done');
      const off = document.querySelector('#now .offer'); if (off) off.remove();
      if (this.prev && this.prev.focus) this.prev.focus();
    },
  };

  /* ------------------------------------------------------------ «Спросить двойник» */
  const T = () => AKT.simTime;
  const at = () => `по данным двойника на ${AKT.clockDay(T())} модели`;
  const issues = () => AKT.issues();
  const place = i => AKT.nameRu(AKT.issueNode(i));
  const sign = i => AKT.rankSign(i) || '•';
  const li = a => `<ul>${a.map(x => `<li>${x}</li>`).join('')}</ul>`;
  const P = s => `<p>${s}</p>`;
  const kpi = () => {
    const cu = AKT.num('site', 'cu_tph'), tph = AKT.num('site', 'tph');
    const t1 = AKT.num('line-1', 'tph') || 0, t2 = AKT.num('line-2', 'tph') || 0;
    const r1 = AKT.num('line-1', 'recovery'), r2 = AKT.num('line-2', 'recovery');
    const rec = (r1 != null || r2 != null) ? ((r1 || 0) * t1 + (r2 || 0) * t2) / ((t1 + t2) || 1) : null;
    return { cu, tph, rec };
  };
  const instruments = () => Object.keys(AKT.things).filter(n => ['analyzer', 'weigher', 'flowmeter', 'phmeter', 'piezometer'].includes(AKT.type(n))).sort(AKT.cmpNames);
  const A = {
    now() {
      const o = AKT.nowLine(), k = kpi();
      const n = issues().length;
      return P(esc(o.text)) + P(`Фабрика даёт ${f1(k.cu)} т меди в час: руда ${fmt(k.tph)} т/ч, извлечение ${f1(k.rec)} %. Сеть ${fmt(AKT.num('power', 'site_mw'))} из ${fmt(AKT.num('power', 'grid_limit_mw'))} МВт.`)
        + P(n ? `Открытых бед: ${fmt(n)}. Подробно — карточка ① справа и вид «Беды».` : 'Открытых бед нет.')
        + (AKT.scenario() ? P(`Идёт учебный сценарий «${esc(AKT.scenarioRu(AKT.scenario()))}». ${esc(AKT.scenWatch(AKT.scenario()).text)}.`) : '');
    },
    why_first() {
      const q = issues();
      if (!q.length) return P('Бед нет — порядок не нужен.');
      const top = q[0], two = q[1];
      const rule = 'Порядок — кого звать первым: сначала то, что опасно для людей (класс S0), потом то, где час промедления стоит дороже; если промедление пока ничего не стоит — то, что нужно звать раньше.';
      const why = i => {
        const s = String(AKT.val(i, 'safety_class') || '');
        if (s === 'S0') return 'опасно для людей (класс S0) — идёт первым всегда';
        const d = AKT.num(i, 'delay_cost_usd'), cb = AKT.num(i, 'call_by');
        if (d != null && d > 0) return `час промедления ${AKT.approx(d)}`;
        if (cb != null && cb > (T() ?? 0)) return `промедление пока ничего не стоит, звать нужно до ${AKT.clockDay(cb)}`;
        return AKT.lossNow(i) ? `теряем ${AKT.approx(AKT.num(i, 'loss_usd_h'))}/ч` : 'потерь пока нет';
      };
      const dot = s => /\.$/.test(s) ? s : s + '.';
      let out = P(rule) + P(`<b>${sign(top)} ${esc(place(top))}</b>: ${esc(dot(why(top)))}`);
      if (two) out += P(`<b>${sign(two)} ${esc(place(two))}</b>: ${esc(dot(why(two)))}`) + P(`Поэтому ${sign(top)} раньше: ${AKT.num(top, 'delay_cost_usd') > (AKT.num(two, 'delay_cost_usd') || 0) ? 'его час промедления дороже' : 'его срок «позвать до» наступает раньше или он опаснее'}.`);
      else out += P('Беда одна — сравнивать не с чем.');
      const qt = String(AKT.val('mod-priority', 'queue_text') || '').split('\n').filter(l => !/^\s*\d+\./.test(l)).join(' ').trim();
      if (qt) out += P(`Модуль очереди: ${esc(qt.replace(/\s*\[оценка на модели\]/g, ' (≈)'))}`);
      return out;
    },
    loss() {
      const q = issues();
      const now = q.filter(AKT.lossNow), later = q.filter(i => !AKT.lossNow(i) && (AKT.num(i, 'loss_usd_h') || 0) > 0);
      const sum = now.reduce((s, i) => s + (AKT.num(i, 'loss_usd_h') || 0), 0);
      let out = P(sum > 0 ? `<b>Сейчас теряем ${AKT.approx(sum)}/ч</b> (≈ ${f1(AKT.cuOfUsd(sum))} т меди в час).` : '<b>Сейчас потерь нет.</b>');
      if (now.length) out += li(now.map(i => `${sign(i)} ${esc(place(i))}: ${AKT.approx(AKT.num(i, 'loss_usd_h'))}/ч`));
      if (later.length) out += P('Начнутся, если не исправить:') + li(later.map(i => `${sign(i)} ${esc(place(i))}: с ${AKT.clockDay(AKT.num(i, 'loss_from'))} ${AKT.approx(AKT.num(i, 'loss_usd_h'))}/ч`));
      const shift = q.reduce((s, i) => s + (AKT.num(i, 'loss_shift_usd') || 0), 0);
      if (shift > 0) out += P(`Если никого не звать, за 12 ч ${AKT.approx(shift)}.`);
      const L = AKT.losses().filter(AKT.lossSure);
      if (L.length) out += P('Скрытые потери (модуль «Где теряем медь»): ' + L.map(l => `${esc(AKT.nameRu(l.node))} ≈ ${f1(l.gap)} т меди/ч`).join(', ') + '.');
      out += P(`Для сравнения: вся медь фабрики стоит ≈ ${AKT.money(AKT.usdPerH(AKT.num('site', 'cu_tph')))}/ч — это не потери, а выручка.`);
      return out;
    },
    who() {
      const q = issues().slice(0, 3);
      let out = '';
      if (!q.length) out += P('Бед нет — звать никого не нужно.');
      else out += li(q.map(i => {
        const per = AKT.issuePerson(i), cb = AKT.num(i, 'call_by');
        return `${sign(i)} ${esc(place(i))}: ${AKT.issueCalled(i) ? 'уже позвали' : 'позвать'} <b>${esc(AKT.roleAcc(AKT.issueRole(i)))}</b>${per ? ` — ${esc(AKT.personAvail(per))}` : ''}${!AKT.issueCalled(i) && cb != null && cb > (T() ?? 0) ? `; не позже ${AKT.clockDay(cb)}` : ''}.`;
      }));
      const free = AKT.persons().filter(n => AKT.st(n) === 'FREE').map(n => esc(AKT.nameRu(n)));
      const busy = AKT.persons().filter(n => AKT.st(n) !== 'FREE').map(n => `${esc(AKT.nameRu(n))} — ${esc(AKT.personAvail(n))}`);
      out += P(`Свободны: ${free.length ? free.join(', ') : 'никого'}.`);
      if (busy.length) out += P('Заняты или в пути:') + li(busy);
      out += P('Дорога к месту — 20–40 мин (допущение стенда).');
      return out;
    },
    wait() {
      const q = issues();
      if (!q.length) return P('Бед нет — ждать нечего.');
      const t = T() ?? 0;
      return li(q.slice(0, 3).map(i => {
        const s = String(AKT.val(i, 'safety_class') || '');
        if (s === 'S0') return `${sign(i)} ${esc(place(i))}: ждать нельзя — опасно для людей.`;
        const d = AKT.num(i, 'delay_cost_usd'), cb = AKT.num(i, 'call_by'), from = AKT.num(i, 'loss_from');
        if (d != null && d > 0) return `${sign(i)} ${esc(place(i))}: час ожидания добавит ${AKT.approx(d)} к потерям.`;
        if (cb != null && cb > t) return `${sign(i)} ${esc(place(i))}: ${cb > t + 60 ? `час подождать можно — звать нужно до ${AKT.clockDay(cb)}, тогда ремонт успеет до начала потерь${from != null ? ` (${AKT.clockDay(from)})` : ''}` : `через час будет поздно: звать нужно до ${AKT.clockDay(cb)}`}.`;
        if (AKT.lossNow(i)) return `${sign(i)} ${esc(place(i))}: потери уже идут, час ожидания ${AKT.approx(AKT.num(i, 'loss_usd_h'))}.`;
        return `${sign(i)} ${esc(place(i))}: потерь в ближайшие 12 ч не ждём.`;
      })) + P('Расчёт модуля очереди бед (≈), с запасом склада и сгустителя.');
    },
    ore() {
      const t = T() ?? 0, ok = String(AKT.val('mod-ore', 'idSimulationRun') || '') === AKT.run;
      if (!ok) return P('Модуль руды ещё не посчитал этот прогон — прогноз появится через минуту.');
      const fc3 = AKT.num('mod-ore', 'fc_tph_h3');
      let out = P(fc3 != null ? `Через 3 часа (к ${AKT.clockDay(t + 180)}) фабрика будет перерабатывать ≈ ${fmt(fc3)} т/ч руды (сейчас ${fmt(AKT.num('site', 'tph'))}).` : 'Прогноза на 3 часа нет.');
      for (const l of [1, 2]) {
        let arr = []; try { arr = JSON.parse(String(AKT.val('mod-ore', 'layers_l' + l) || '[]')); } catch (e) { arr = []; }
        const now = arr.filter(o => Number(o.in_sag || 0) > 0.3).map(o => `партия ${AKT.batchNo(String(o.batch))} (${AKT.oreWord(Number(o.axb))}, A×b ${f1(Number(o.axb))})`);
        const soon = arr.filter(o => typeof o.exp === 'number' && o.exp > t && o.exp <= t + 180 && Number(o.in_sag || 0) < 0.3).map(o => `партия ${AKT.batchNo(String(o.batch))} — ${AKT.oreWord(Number(o.axb))}, ожидаемо в ${AKT.clockDay(o.exp)}`);
        const hard = AKT.num('mod-ore', `next_hard_eta_h_l${l}`);
        out += P(`<b>Линия ${l}:</b> сейчас в мельнице ${now.length ? esc(now.join(' и ')) : 'нет данных'}.${soon.length ? ' В ближайшие 3 ч: ' + esc(soon.join('; ')) + '.' : ' Новых партий в ближайшие 3 ч не ждём.'} ${hard != null ? `Твёрдая руда — через ${AKT.durH(hard)}.` : 'Твёрдой руды в плане на 12 ч нет.'}`);
      }
      return out + P('Оценка модуля руды по блочной модели (≈, ошибка твёрдости около 12 %).');
    },
    copper() {
      const L = AKT.losses();
      const sure = L.filter(AKT.lossSure), weak = L.filter(l => AKT.lossShown(l) && !AKT.lossSure(l));
      let out = sure.length ? P('<b>Заметные потери меди:</b>') + li(sure.map(l => `${esc(AKT.nameRu(l.node))}: ≈ ${f1(l.gap)} т меди/ч (${AKT.approx(l.usd)}/ч)`))
        : P('<b>Заметных потерь нет:</b> расхождения в пределах точности приборов.');
      if (weak.length) out += P('Есть подозрение, но точность низкая — возможно, потерь нет: ' + weak.map(l => esc(AKT.nameRu(l.node))).join(', ') + '.');
      out += P(`Извлечение: линия 1 — ${f1(AKT.num('line-1', 'recovery'))} %, линия 2 — ${f1(AKT.num('line-2', 'recovery'))} %. Медь в хвостах: флотация 1 — ${f3(AKT.num('flot-1', 'tail_cu'))} %, флотация 2 — ${f3(AKT.num('flot-2', 'tail_cu'))} % (уставка 0,075 %).`);
      const sus = AKT.val('mod-losses', 'suspect_text');
      if (sus) out += P('Приборы: ' + esc(String(sus)) + '.');
      return out;
    },
    shift() {
      const t = T() ?? 0;
      const cu = (AKT.num('line-1', 'cum_cu_t') || 0) + (AKT.num('line-2', 'cum_cu_t') || 0);
      const usd = (AKT.num('line-1', 'cum_usd') || 0) + (AKT.num('line-2', 'cum_usd') || 0);
      let out = P(`С 08:00 до ${AKT.clock(t)} фабрика дала ${f1(cu)} т меди (≈ ${AKT.money(usd)}).`);
      const rows = AKT.journal.filter(r => !r.run || r.run === AKT.run);
      out += rows.length ? P(`Действия в журнале смены (${fmt(rows.length)}):`) + li(rows.slice(0, 6).map(r => `${AKT.clock(r.sim_time)} — ${esc(AKT.journalRu(r))}`)) : P('В журнале смены действий ещё не было.');
      const all = AKT.ofType('issue').filter(i => String(AKT.val(i, 'idSimulationRun') || '') === AKT.run);
      const fixed = all.filter(i => AKT.st(i) === 'RESOLVED');
      out += P(`Бед в этом прогоне: ${fmt(all.length)}, устранено ${fmt(fixed.length)}, открыто ${fmt(issues().length)}.`);
      if (AKT.scenario()) out += P(`Идёт учебный сценарий «${esc(AKT.scenarioRu(AKT.scenario()))}».`);
      return out;
    },
    water() {
      const ps = Object.keys(AKT.things).filter(x => AKT.cat(x) === 'piezo').sort(AKT.cmpNames);
      const piezo = ps.map(x => `${esc(AKT.nameRu(x).replace(/^Пьезометр дамбы /, ''))} ${fmt(AKT.num(x, 'kpa'))} кПа`).join(', ');
      const hi = ps.some(x => (AKT.num(x, 'kpa') || 0) >= (AKT.num(x, 'sp_kpa') || 150));
      const mw = AKT.num('power', 'site_mw'), lim = AKT.num('power', 'grid_limit_mw'), shed = AKT.num('power', 'shed_mw');
      return P(`<b>Вода:</b> ${esc(AKT.stOf('water'))}. Забор свежей воды ${fmt(AKT.num('water', 'intake_m3h'))} м³/ч (предел ${fmt(AKT.num('water', 'intake_cap_m3h'))}), оборотная вода ${fmt(AKT.num('water', 'recycle_m3h'))} м³/ч, пруд ${f2((AKT.num('water', 'pond_m3') || 0) / 1e6)} млн м³.${(AKT.num('water', 'leak_m3h') || 0) > 0 ? ` Утечка ${fmt(AKT.num('water', 'leak_m3h'))} м³/ч.` : ''}`)
        + P(`<b>Дамба:</b> пьезометры ${piezo || 'нет данных'}; тревога от 150 кПа — ${hi ? '<b>есть превышение</b>' : 'превышений нет'}.`)
        + P(`<b>Сеть:</b> ${esc(AKT.stOf('power'))}, нагрузка ${fmt(mw)} из ${fmt(lim)} МВт, запас ${fmt((lim || 0) - (mw || 0))} МВт${shed ? `, отключено ${fmt(shed)} МВт` : ''}.`);
    },
    handover() {
      const ho = AKT.val('mod-priority', 'handover') || {};
      const draft = String(AKT.val('mod-priority', 'handover_draft_text') || '');
      const L = s => String(s || '').split('\n').filter(Boolean);
      const at = typeof ho.at === 'number' && ho.at >= 0 ? ho.at : null;
      let out = '';
      if (draft) out += P(`<b>${esc(L(draft)[0] || 'Сдача смены')}</b> — ${esc(AKT.draftTitle(AKT.num('mod-priority', 'processed_sim_time'), AKT.simTime, AKT.clockDay).replace(/^Если сдавать сейчас/, 'если сдавать сейчас'))}:`) + li(L(draft).slice(1).map(x => esc(x.replace(/\s*\[оценка на модели\]/g, ' (≈)'))));
      else out += P('Модуль очереди бед ещё не посчитал этот прогон.');
      out += P(at != null ? `Последний лист сдачи записан в ${AKT.clockDay(at)} модели — вид «Сдача смены».` : 'Лист сдачи составляется в 07:30 и 19:30 времени модели — вид «Сдача смены».');
      return out;
    },
    permit() {
      const L = issues().map(i => String(AKT.val(i, 'chain_text') || '')).filter(Boolean);
      return L.length ? P('<b>Кто занят и кого звать вместо:</b>') + li(L.map(x => esc(x))) : P('Все, кого надо звать по открытым бедам, свободны: цепочка (основной → заместитель → начальник смены) не понадобилась.');
    },
    choice() {
      const L = [...new Set(issues().map(i => String(AKT.val(i, 'choice_text') || '').replace(/\s*\[оценка на модели\]/g, ' (≈)')).filter(Boolean))];
      return L.length ? li(L.map(x => esc(x))) : P('Сейчас нет двух бед, которым нужна одна и та же бригада: выбирать не из чего.');
    },
    review() {
      const L = String(AKT.val('mod-priority', 'review_text') || '').split('\n').filter(Boolean);
      return L.length ? li(L.map(x => esc(x.replace(/\s*\[оценка на модели\]/g, ' (≈)')))) : P('Модуль очереди бед ещё не посчитал этот прогон.');
    },
    tariff() {
      const tf = String(AKT.val('mod-priority', 'tariff_text') || '').replace(/\s*\[допущение\]/g, ' (д)');
      const s = String(AKT.val('mod-priority', 'season_text') || '');
      return P(esc(tf || 'Тариф ещё не посчитан.')) + (s ? P(esc(s)) : '');
    },
    deviations() {
      const L = String(AKT.val('mod-priority', 'deviations_text') || '').split('\n').filter(Boolean);
      return L.length ? li(L.map(x => esc(x.replace(/\s*\[оценка на модели\]/g, ' (≈)').replace(/\s*\[допущение\]/g, ' (д)')))) : P('Отклонений от нормы (шары, энергия) модуль сейчас не видит.');
    },
    stock() {
      const sp = n => { const h = AKT.num(`stockpile-${n}`, 'hours_left'), lvl = AKT.num(`stockpile-${n}`, 'level_t'); return `Склад ${n}: ${fmt(lvl)} т, ${h != null && h <= 48 ? `кончится через ${AKT.durH(h)}` : (AKT.num(`stockpile-${n}`, 'in_tph') || 0) >= (AKT.num(`stockpile-${n}`, 'out_tph') || 0) ? 'приход не меньше расхода' : 'хватит больше чем на 2 суток'}; дробилка ${n} — ${esc(AKT.stOf(`crusher-${n}`))}, ${fmt(AKT.num(`crusher-${n}`, 'tph'))} т/ч.`; };
      const hf = AKT.num('conc-stock', 'hours_to_full');
      return li([sp(1), sp(2), `Склад концентрата: ${fmt(AKT.num('conc-stock', 'stock_t'))} из ${fmt(AKT.pass('conc-stock', 'capacity_t'))} т${hf != null && hf < 48 ? `, заполнится через ${AKT.durH(hf)}` : ''}; отгрузка поездом в 06:00 и 18:00.`]);
    },
    pitstop() {
      const f = AKT.fc && AKT.fc.data();
      if (!f || !f.stock || !f.stock.lines) return P('Модуль очереди бед ещё не посчитал прогноз по складу.');
      const L = Object.keys(f.stock.lines).sort().map(n => ({ n, ...f.stock.lines[n] }));
      return P(f.stock.pit_stopped ? '<b>Карьер стоит.</b> Склад держит фабрику:' : '<b>Если карьер встанет сейчас, руды хватит:</b>')
        + li(L.map(r => `линия ${r.n}: ${r.hours >= 0 ? `≈ ${AKT.durH(r.hours)} (до ${AKT.clockDay(r.run_out_at)})` : 'SAG стоит'}; на складе ${fmt(r.level_t)} т, на пути ≈ ${fmt(r.transit_t)} т`))
        + P('Откатка (≈ 30 мин) и лента (≈ 9 мин) ещё довезут уже вынутую руду. По ПЭК рабочий объём склада 163 кт = 2 суток измельчения (проект); в модели живая часть 40 кт на линию (д). Подробнее — вид «Прогнозы».');
    },
    liner() {
      const f = AKT.fc && AKT.fc.data();
      if (!f || !f.liner || !f.liner.lines) return P('Счётчик наработки футеровки ещё не пришёл.');
      return li(Object.keys(f.liner.lines).sort().map(n => { const r = f.liner.lines[n]; return `SAG-${n}: наработка ${AKT.fmt(r.ground_mt, 1)} из ${AKT.fmt(r.life_mt, 0)} Мт; планировать перефутеровку через ≈ ${AKT.fmt(r.days_to_end, 0)} сут; к концу кампании т/ч ${AKT.fmt(r.drop_from_peak_pct, 1)} % от пика`; }))
        + P('Длина кампании 30 Мт — допущение (10–18 месяцев); факт: перефутеровки SAG в IV кв. 2023 (обе линии) и III кв. 2025 (линия 2).');
    },
    cuend() {
      const k = AKT.fc && AKT.fc.cu('shift'), d = AKT.fc && AKT.fc.cu('day');
      if (!k) return P('Счётчики меди ещё копятся: прогноз появится через несколько минут после старта смены.');
      return P(`<b>К ${AKT.clock(k.endAt)} (конец смены):</b> ≈ ${fmt(k.end)} т Cu, коридор ${fmt(k.lo)}–${fmt(k.hi)} т; уже сделано ${f1(k.now)} т, темп ${f1(k.rate)} т/ч.`)
        + (d ? P(`<b>К концу суток:</b> ≈ ${fmt(d.end)} т Cu (${fmt(d.lo)}–${fmt(d.hi)}); ориентир — средние сутки 2025 г.: ${fmt(d.plan)} т.`) : '')
        + P('Верх коридора — если закрыть сейчас беды, которые уже теряют медь; низ — разброс темпа за 3 ч. Это прогноз модели, не плановое задание.');
    },
    econ() {
      if (!AKT.exp23 || !AKT.exp23.data) { if (AKT.exp23) AKT.exp23.load(() => {}); return P('Итог опыта «вкл/выкл» ещё загружается, спросите ещё раз.'); }
      const tw = AKT.exp23.twin(), d = AKT.exp23.data.delay;
      return P(`${AKT.exp23.sentence()} Нижняя граница — +${AKT.fmt(tw.ci95_mean_bca[0], 2)} т. Час задержки вызова стоит ≈ ${AKT.fmt(d.slope_t_per_h.mean, 1)} т Cu. Страница «Экономика» — с оговорками.`);
    },
    suspect() {
      const inst = instruments().filter(n => ['SUSPECT', 'DRIFT'].includes(AKT.st(n)));
      const sus = String(AKT.val('mod-losses', 'suspect_text') || '');
      const ev = [];
      issues().forEach(i => AKT.evidenceItems(i).filter(x => x.suspect).forEach(x => ev.push(`${sign(i)} ${esc(place(i))}: ${esc(x.label)} — ${esc(x.text)}${x.unit ? ' ' + esc(x.unit) : ''}`)));
      const phIss = issues().filter(i => String(AKT.val(i, 'kind') || '') === 'sensor_ph');
      let out = inst.length ? P('<b>Приборы в состоянии «под подозрением» или «дрейф»:</b>') + li(inst.map(n => `${esc(AKT.nameRu(n))} — ${esc(AKT.stOf(n))}`))
        : P('<b>Состояние приборов в Ditto — исправны</b> (состояние «дрейф» ставится, когда дрейф подтверждён вызовом или пробой).');
      if (phIss.length) out += P('<b>Открыта беда «pH-метр под подозрением»:</b>') + li(phIss.map(i => `${sign(i)} ${esc(place(i))}: ручная проба расходится с онлайн-показанием — ${esc(AKT.roleAcc(AKT.issueRole(i)))}`));
      if (sus && !/не найдено/.test(sus)) out += P('Модуль «Где теряется медь»: ' + esc(sus.replace(/\s*\[оценка на модели\]/g, ' (≈)')) + '.');
      if (ev.length) out += P('В карточках бед помечены:') + li(ev);
      const phs = Object.keys(AKT.things).filter(n => AKT.type(n) === 'phmeter');
      out += phs.length ? P('pH-метры: ' + phs.map(n => `${esc(AKT.nameRu(n))} — онлайн ${f2(AKT.num(n, 'ph'))}, ручная проба ${f2(AKT.num(n, 'lab_ph'))}`).join('; ') + '. Онлайн-показание держится на уставке, расхождение с пробой — признак накипи на электроде.') : '';
      return out;
    },
    road() {
      const v = AKT.num('pit', 'visibility_m'), g = AKT.num('pit', 'road_grip'), hs = AKT.num('pit', 'haul_speed_pct'), r = AKT.num('pit', 'road_restrict') === 1;
      const w = AKT.num('water', 'wind_ms'), t = AKT.num('water', 'air_temp_c');
      const bad = (v != null && v <= 150) || (g != null && g <= 0.4);
      let out = P(`<b>Откатка:</b> видимость ${v == null ? '—' : fmt(v)} м, сцепление (индекс 0…1) ${g == null ? '—' : f2(g)}, скорость к сухой дороге ${hs == null ? '—' : fmt(hs)} %, ветер ${w == null ? '—' : fmt(w)} м/с, воздух ${t == null ? '—' : fmt(t)} °C.`);
      out += P(bad ? (r ? 'Дорога опасна, ограничение движения <b>введено</b>: беда S0 закрыта.' : '<b>Дорога опасна</b> (видимость до 150 м или сцепление до 0,4 — пороги принятые, допущение): ограничить движение; кого звать — в карточке беды S0.')
        : 'Порогов опасности не достигнуто' + (AKT.num('water', 'winter') === 1 ? ' (зима: сцепление ниже обычного, но в пределах)' : '') + '.');
      return out + P('KAZ Minerals называет метели и сильный ветер риском ДТП на Актогае, цифр не публикует: пороги — допущение стенда.');
    },
    stale() {
      const inst = instruments();
      const t = T() ?? 0;
      const rows = inst.map(n => {
        const st = AKT.num(n, 'sim_time'), pub = st != null ? Math.max(0, t - st) : null;
        const meas = AKT.num(n, 'age_min');
        return { n, pub, meas, bad: (pub != null && pub > 10) || (meas != null && meas > (AKT.type(n) === 'phmeter' ? 360 : 45)) };
      });
      const old = rows.filter(r => r.bad);
      let out = old.length ? P('<b>Данные давно не обновлялись:</b>') + li(old.map(r => `${esc(AKT.nameRu(r.n))}: опубликовано ${AKT.agoMin(r.pub)}${r.meas != null ? `, замер ${AKT.agoMin(r.meas)}` : ''}`)) : P('<b>Данные приборов свежие:</b> публикация не старше 10 минут модели, анализаторы — в пределах цикла, ручные пробы pH — не старше 6 ч.');
      out += P('Возраст замера: анализатор — цикл 12–16 мин (Metso, вендор); ручная проба pH — раз в несколько часов (периодичность — допущение). Остальные приборы публикуются непрерывно.');
      const e2 = []; issues().forEach(i => AKT.evidenceItems(i).filter(x => x.old).forEach(x => e2.push(`${sign(i)} ${esc(place(i))}: ${esc(x.label)} — данные ${esc(AKT.agoMin(x.age_pub_min))}`)));
      return out + (e2.length ? P('В карточках бед помечены «давно»:') + li(e2) : '');
    },
    balance() {
      const cu = AKT.num('mod-losses', 'cu_residual_pct'), w = AKT.num('mod-losses', 'water_residual_pct'), tph = AKT.num('site', 'tph'), fresh = AKT.num('water', 'intake_m3h');
      return li([`Медь (питание = концентрат + хвосты), невязка за 2 ч: ${cu == null ? 'мало точек' : AKT.fmt(cu, 2) + ' %'} (допуск 0,5 %)`,
        `Вода (забор = хвосты + испарение + пруд), невязка: ${w == null ? 'мало точек' : AKT.fmt(w, 2) + ' %'}`,
        `Свежая вода: ${tph > 0 && fresh != null ? AKT.fmt(fresh / tph, 2) : '—'} м³ на т руды; факт KAZ Minerals — 0,60 м³/т (забор по группе, 2024; не точный аналог)`])
        + P('Подробные таблицы — вид «Путь меди».');
    },
  };
  const QS = [
    ['now', 'Что сейчас происходит?', /происход|сейчас|обстанов|ситуац|главн|что (тут|здесь|делать)/],
    ['why_first', 'Почему эта беда первая?', /почему|порядок|очеред|приоритет|перв/],
    ['loss', 'Сколько мы теряем?', /теря|потер|убыт|денег|доллар|\$/],
    ['who', 'Кого звать и когда он свободен?', /кого|зват|позва|свобод|занят|механик|бригад|люд|человек|кто/],
    ['wait', 'Что будет, если подождать час?', /подожд|ждат|отлож|промедл|позже|потом|если.*час/],
    ['ore', 'Какая руда придёт через 3 часа?', /руд|парти|твёрд|тверд|мягк|a×b|axb|прогноз/],
    ['copper', 'Где теряется медь?', /где.*мед|мед.*(где|тер|хвост)|хвост|флотац|извлеч/],
    ['shift', 'Что изменилось за смену?', /смен|измени|журнал|итог|было|за день/],
    ['water', 'Как с водой и сетью?', /вод|дамб|пьезо|сет[ьи]|энерг|мощн|мвт|лэп|электр|пруд/],
    ['stock', 'Хватит ли руды на складах?', /склад|запас|хватит|дробилк|концентрат|поезд/],
    ['handover', 'Что передать смене?', /переда|сдач|сменщ|приём|прием|смене|смену/],
    ['permit', 'Кто занят по наряду-допуску?', /наряд|допуск|занят.*работ|заместит|цепочк/],
    ['choice', 'Куда отправить свободную бригаду?', /бригад.*(одн|свобод)|цена выбор|выбор/],
    ['review', 'А если бы позвали иначе?', /иначе|если бы|ошибк|порядок вызов/],
    ['tariff', 'Какой сейчас тариф и сезон?', /тариф|пик|ночь|зим|сезон|мороз/],
    ['deviations', 'Есть ли перерасход шаров?', /шар|перерасход|отклонени/],
    ['pitstop', 'Что будет, если карьер встанет?', /карьер.*(вста|стоп|останов)|останов.*карьер|склад.*час|на сколько.*хватит/],
    ['liner', 'Когда менять футеровку SAG?', /футеров|перефутер|износ|брон/],
    ['cuend', 'Сколько меди будет к концу смены?', /к концу|до конца|прогноз.*мед|мед.*(смен|сутк)|сутк/],
    ['econ', 'Сколько сберегает двойник?', /сберег|экономи|выгод|окупа|эффект|сколько.*двойник/],
    ['suspect', 'Что сейчас под подозрением из датчиков?', /подозр|датчик|прибор|врёт|врет|\bph\b|рн-метр|расходомер|анализатор/],
    ['road', 'Где дорога опасна?', /дорог|гололёд|гололед|метел|видимост|сцеплен|откатк/],
    ['stale', 'Какие данные устарели?', /устарел|старые данные|возраст данных|давно|свеж/],
    ['balance', 'Сходятся ли балансы меди и воды?', /баланс|невяз|сходит|м³\/т|на тонну/],
  ];
  const match = text => {
    const s = text.toLowerCase();
    let best = null, score = 0;
    for (const [id, , re] of QS) { const m = s.match(new RegExp(re.source, 'g')); const k = m ? m.length : 0; if (k > score) { score = k; best = id; } }
    return best;
  };
  AKT.ask = {
    el: null,
    open(id) {
      if (!this.el) {
        const d = this.el = document.createElement('div'); d.id = 'ask'; d.className = 'drawer'; d.setAttribute('role', 'dialog'); d.setAttribute('aria-labelledby', 'ask-h');
        d.innerHTML = `<header><h2 id="ask-h">Спросить двойник</h2><button type="button" data-x aria-label="Закрыть">×</button></header>
<div class="a-intro">Ответы собираются из живых данных двойника по готовым шаблонам. Числа со знаком ≈ — расчёт модели.</div>
<div class="a-qs">${QS.map(([qid, q]) => `<button type="button" data-q="${qid}">${esc(q)}</button>`).join('')}</div>
<form id="ask-f"><input type="text" id="ask-in" placeholder="Свой вопрос, например: хватит ли воды?" aria-label="Свой вопрос" maxlength="200" autocomplete="off"><button type="submit" class="primary">Спросить</button></form>
<div class="a-log" id="ask-log" aria-live="polite"></div>`;
        document.body.appendChild(d);
        d.querySelector('[data-x]').addEventListener('click', () => this.close());
        d.querySelectorAll('[data-q]').forEach(b => b.addEventListener('click', () => this.answer(b.dataset.q, b.textContent)));
        d.querySelector('#ask-f').addEventListener('submit', ev => {
          ev.preventDefault();
          const inp = d.querySelector('#ask-in'), q = inp.value.trim(); if (!q) return;
          inp.value = ''; this.answer(match(q), q);
        });
        d.addEventListener('keydown', ev => { if (ev.key === 'Escape') this.close(); });
      }
      if (AKT.glossary && AKT.glossary.el) AKT.glossary.el.hidden = true;
      this.el.hidden = false;
      if (id && A[id]) this.answer(id, (QS.find(x => x[0] === id) || [])[1] || id);
      else if (!this.el.querySelector('.a-a')) this.answer('now', 'Что сейчас происходит?');
      this.el.querySelector('#ask-in').focus();
    },
    close() { if (this.el) this.el.hidden = true; },
    answer(id, question) {
      const log = this.el.querySelector('#ask-log');
      let body;
      if (!AKT.polled) body = P('Связи с двойником ещё нет — данные не загружены. Спросите через несколько секунд.');
      else if (id && A[id]) { try { body = A[id](); } catch (e) { console.error(e); body = P('Не получилось собрать ответ из данных: части данных сейчас нет.'); } }
      else body = P('Не нашёл ответа на этот вопрос в данных двойника. Двойник отвечает только по тому, что есть в модели сейчас: беды и их порядок, потери, люди, руда, медь, вода и сеть, итоги смены.')
        + P('Попробуйте спросить так: «сколько теряем», «кого звать», «что будет, если подождать», «какая руда придёт», «как с водой».');
      const q = document.createElement('div'); q.className = 'a-q'; q.textContent = question;
      const a = document.createElement('div'); a.className = 'a-a'; a.innerHTML = body + `<div class="src">${esc(at())}</div>`;
      AKT.glossify(a);
      log.prepend(a); log.prepend(q);
      log.scrollTop = 0;
    },
  };
})();
