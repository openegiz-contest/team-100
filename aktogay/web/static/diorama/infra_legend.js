/* «Диорама», инфраструктура: легенда поверх сцены (HTML) и стили подписей
   модуля. Легенда — в правом нижнем углу холста, на узком холсте свёрнута; открыта или
   свёрнута — помнит браузер (localStorage, необязательно). Число людей и
   бригад — из Ditto. */

const CSS = `
.dio-legend { position: absolute; right: 6px; bottom: 4px; z-index: 4; max-width: 232px; font-size: 12px; line-height: 14px;
  color: var(--ink, #16191d); background: rgba(255, 255, 255, 0.93); border: 1px solid rgba(60, 70, 85, 0.25); border-radius: 7px;
  box-shadow: 0 1px 4px rgba(20, 30, 50, 0.12); pointer-events: auto; }
.dio-legend button { all: unset; cursor: pointer; display: block; padding: 2px 7px; font-weight: 700; font-size: 12px; }
.dio-legend button:focus-visible { outline: 2px solid #111111; outline-offset: 1px; border-radius: 6px; }
.dio-legend button::after { content: ' ▾'; font-weight: 400; color: var(--muted, #5b626b); }
.dio-legend.closed button::after { content: ' ▸'; }
.dio-legend ul { list-style: none; margin: 0; padding: 0 7px 4px; }
.dio-legend.closed ul { display: none; }
.dio-legend li { margin: 1px 0; white-space: normal; }
.dio-legend .lg { display: inline-block; vertical-align: -2px; margin-right: 4px; width: 14px; height: 10px; position: relative; }
.lg.l-issue { width: 10px; height: 10px; border-radius: 50%; border: 2px solid #ff3324; box-sizing: border-box; box-shadow: 0 0 4px 1px rgba(255, 51, 36, 0.6); }
.lg.l-chain { height: 3px; vertical-align: 2px; background: #e8a000; border-radius: 2px; box-shadow: 0 0 3px rgba(232, 160, 0, 0.8); }
.lg.l-chain::after { content: ''; position: absolute; left: 5px; top: -2px; width: 6px; height: 6px; border-radius: 50%; background: #9cc3ff; }
.lg.l-copper { width: 10px; height: 10px; border-radius: 50%; border: 2px solid #c8792f; box-sizing: border-box; }
.lg.l-person { width: 8px; }
.lg.l-person::before { content: ''; position: absolute; left: 2px; top: -1px; width: 5px; height: 4px; border-radius: 3px 3px 0 0; background: #fff; border: 1px solid #8a9096; }
.lg.l-person::after { content: ''; position: absolute; left: 1px; top: 4px; width: 7px; height: 7px; border-radius: 2px; background: #ff7a1a; }
.lg.l-crew::after { background: #2f63a8; }
.lg.l-call { width: 10px; height: 10px; border-radius: 50%; border: 2px solid #16191d; box-sizing: border-box; }
.lg.l-travel { height: 3px; vertical-align: 2px; background: repeating-linear-gradient(90deg, #ff7a1a 0 4px, transparent 4px 7px); }
.lg.l-fresh, .lg.l-recycle, .lg.l-tails { width: 10px; height: 4px; vertical-align: 2px; border-radius: 2px; }
.lg.l-fresh { background: #1f78d1; } .lg.l-recycle { background: #0f9aa3; } .lg.l-tails { background: #b06a28; }
.lg.l-piezo { width: 8px; height: 8px; border-radius: 50%; background: #ff3a2a; box-shadow: 0 0 4px 2px rgba(255, 58, 42, 0.55); }
.lg.l-power { width: 8px; height: 8px; transform: rotate(45deg) scale(0.8); background: #ffc83d; border: 1px solid #b08400; }
.dio-legend .lg-note { color: var(--muted, #5b626b); }
.dl.dio-call { box-shadow: 0 0 0 2px #16191d, 0 1px 3px rgba(20, 30, 50, 0.16); }
`;

export function buildLegend(ctx) {
  const AKT = ctx.AKT;
  const wrap = document.getElementById('dio-wrap');
  if (!document.getElementById('dio-infra-css')) {
    const st = document.createElement('style'); st.id = 'dio-infra-css'; st.textContent = CSS;
    document.head.appendChild(st);
  }
  if (!wrap) return { update() {}, destroy() {} };
  const el = document.createElement('div');
  el.className = 'dio-legend'; el.setAttribute('role', 'note'); el.setAttribute('aria-label', 'Обозначения диорамы');
  el.title = 'Кольца и дуги — по очереди бед и связям feeds в Ditto; к беде 1 — тот, кого звать (как в панели); пунктир — путь человека в дороге, время прибытия — допущение стенда (arrive_min); стрелки на трубах бегут со скоростью ∝ расходу, огни на проводах — ∝ потреблению; роли смены и места пьезометров — допущения стенда';
  el.innerHTML = `<button type="button" aria-expanded="true">Обозначения</button>
<ul>
<li><i class="lg l-issue"></i>беда в очереди (пульсирует)</li>
<li><i class="lg l-chain"></i>путь беды до меди <i class="lg l-copper"></i></li>
<li><i class="lg l-person"></i><span class="lg-n">люди</span> · <i class="lg l-person l-crew"></i><span class="lg-c">бригады</span> · <i class="lg l-call"></i>кого звать</li>
<li><i class="lg l-travel"></i>в пути, ETA ${AKT.ASSUME}</li>
<li><i class="lg l-fresh"></i>свежая <i class="lg l-recycle"></i>оборотная <i class="lg l-tails"></i>хвосты</li>
<li><i class="lg l-piezo"></i>пьезометр выше S0 · <i class="lg l-power"></i>МВт по проводам</li>
</ul>`;
  wrap.appendChild(el);
  const btn = el.querySelector('button');
  const KEY = 'dio-legend-open';
  let open = wrap.clientWidth >= 1000;               // узкий холст (рядом панель) — свёрнута
  try { const v = localStorage.getItem(KEY); if (v === '0' || v === '1') open = v === '1'; } catch (e) { /* хранилище необязательно */ }
  const apply = () => { el.classList.toggle('closed', !open); btn.setAttribute('aria-expanded', String(open)); };
  apply();
  btn.addEventListener('click', ev => {
    ev.stopPropagation();
    open = !open; apply();
    try { localStorage.setItem(KEY, open ? '1' : '0'); } catch (e) { /* хранилище необязательно */ }
  });
  const nEl = el.querySelector('.lg-n'), cEl = el.querySelector('.lg-c');
  let last = '';
  return {
    update(state) {
      if (!state.fresh) return;
      const np = Object.keys(AKT.things).filter(n => AKT.cat(n) === 'person').length;
      const nc = Object.keys(AKT.things).filter(n => AKT.cat(n) === 'crew').length;
      const k = np + '|' + nc;
      if (k === last) return;
      last = k;
      nEl.textContent = `люди ${AKT.fmt(np)}`;
      cEl.textContent = `бригады ${AKT.fmt(nc)}`;
    },
    destroy() { el.remove(); const st = document.getElementById('dio-infra-css'); if (st) st.remove(); },
  };
}
