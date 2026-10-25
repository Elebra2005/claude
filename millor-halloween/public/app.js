'use strict';
/* Миллор Групп: Секретная лаборатория — клиент игрока */

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const app = $('#app');

const STATUS = {
  not_started: 'Не начато', in_progress: 'Выполняется', review: 'На проверке',
  done: 'Выполнено', retry: 'Попробуй ещё раз', failed: 'Попытки исчерпаны',
};
const plural = (n, one, few, many) => {
  const m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
};
const MSK = (iso, opts) => new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', ...opts }).format(new Date(iso));

const state = { me: null, prevLines: null, prevBoard: null, timeOffset: 0, publicInfo: null, pollTimer: null, tickTimer: null };

async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method, credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch {}
  if (!res.ok) { const e = new Error(data.error || `Ошибка ${res.status}`); e.status = res.status; throw e; }
  return data;
}

function toast(text, kind = '') {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.innerHTML = text;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), 6500);
}

/* ---------- Логотип и шапка ---------- */
function brandHtml(logo) {
  return logo ? `<img src="${logo}" alt="Миллор Групп">` : `<span class="wordmark">Миллор Групп · <b>Лаборатория</b></span>`;
}
function renderMission(n) {
  const el = $('#mission');
  const players = state.me ? state.me.totalPlayers : 0;
  const goal = Math.max(16, players * 16);
  el.innerHTML = `<span>🧟 Сотрудники Миллор Групп уже победили <strong>${n}</strong> ${plural(n, 'офисного монстра', 'офисных монстров', 'офисных монстров')}!</span>
    <span class="bar" title="Коллективная миссия"><i style="width:${Math.min(100, (n / goal) * 100).toFixed(1)}%"></i></span>`;
}
function showChrome(on) {
  $('#topbar').hidden = !on;
  document.body.classList.toggle('with-nav', on);
}
function setActiveNav(route) {
  $$('#nav a').forEach((a) => a.classList.toggle('active', a.dataset.route === route));
}

/* ---------- Маршрутизация ---------- */
async function router() {
  closeModal(true);
  const [, route = '', arg] = location.hash.replace(/^#\/?/, '#/').split('/');
  if (route === '' || route === 'welcome') return viewWelcome();
  if (route === 'login') return viewLogin();
  try {
    if (!state.me) await refreshMe();
  } catch (e) {
    if (e.status === 401) { location.hash = '#/login'; return; }
    throw e;
  }
  showChrome(true);
  setActiveNav(route);
  if (route === 'board') return viewBoard();
  if (route === 'task') { viewBoard(); return openTask(Number(arg)); }
  if (route === 'hall') return viewHall();
  if (route === 'gallery') return viewGallery();
  if (route === 'rules') return viewRules();
  location.hash = '#/board';
}
window.addEventListener('hashchange', router);

/* ---------- Приветствие ---------- */
const FLASKS_SVG = `
<svg viewBox="0 0 60 96"><rect x="24" y="6" width="12" height="30" rx="2" fill="#9fb3b8" opacity=".35"/>
  <path d="M24 34 8 84q0 8 8 8h28q8 0 8-8L36 34z" fill="#9fb3b8" opacity=".25"/>
  <path d="M15 62 8 84q0 8 8 8h28q8 0 8-8l-7-22z" fill="#a3192b"/>
  <circle class="bubble" cx="26" cy="80" r="3" fill="#ffb3bd"/><circle class="bubble" cx="34" cy="84" r="2" fill="#ffb3bd"/><circle class="bubble" cx="30" cy="76" r="2.5" fill="#ffb3bd"/></svg>
<svg viewBox="0 0 70 96"><path d="M28 4h14v28c14 6 24 20 24 34 0 16-14 28-31 28S4 82 4 66c0-14 10-28 24-34z" fill="#9fb3b8" opacity=".25"/>
  <path d="M6 64c0 16 13 28 29 28s29-12 29-28z" fill="#f28c28"/>
  <circle class="bubble" cx="30" cy="80" r="3" fill="#ffe0b8"/><circle class="bubble" cx="42" cy="84" r="2" fill="#ffe0b8"/><circle class="bubble" cx="36" cy="74" r="2.5" fill="#ffe0b8"/></svg>
<svg viewBox="0 0 80 96"><g transform="translate(6 34)"><rect width="68" height="56" rx="3" fill="#f4ede6"/><rect width="68" height="12" fill="#6e1222"/>
  <rect y="22" width="68" height="14" fill="#f28c28" opacity=".9"/><text x="34" y="32" text-anchor="middle" font-size="8" font-weight="700" font-family="Arial" fill="#2a1406">АНТИДЕДЛАЙН</text>
  <rect x="6" y="42" width="10" height="10" fill="#6e1222"/><rect x="8" y="46" width="6" height="2" fill="#fff"/><rect x="10" y="44" width="2" height="6" fill="#fff"/></g></svg>
<svg viewBox="0 0 70 96"><g transform="translate(35 64)"><ellipse rx="30" ry="24" fill="#e0731d"/><ellipse rx="10" ry="23" fill="#f28c28" transform="translate(-11 0)"/><ellipse rx="10" ry="23" fill="#f28c28" transform="translate(11 0)"/>
  <rect x="-3" y="-32" width="6" height="10" rx="2" fill="#4c6b2f"/><path d="M-16-6l6-7 6 7zM4-6l6-7 6 7zM-14 8q14 12 28 0l-5 5-5-3-4 3-5-3z" fill="#3a1606"/></g></svg>`;

async function viewWelcome() {
  showChrome(false);
  let info = state.publicInfo;
  try { info = state.publicInfo = await api('/api/public'); } catch {}
  let loggedIn = false;
  try { await refreshMe(); loggedIn = true; } catch {}
  const g = info && info.game;
  const when = g ? `${MSK(g.start, { day: 'numeric', month: 'long', year: 'numeric' })}, ${MSK(g.start, { hour: '2-digit', minute: '2-digit' })}–${MSK(g.end, { hour: '2-digit', minute: '2-digit' })} по московскому времени` : '30 октября 2026, 10:00–17:00 по московскому времени';
  app.innerHTML = `
  <section class="hero"><div class="hero-inner">
    <div class="hero-logo">${info && info.logo ? `<img src="${info.logo}" alt="Миллор Групп">` : '<span class="wordmark">Миллор Групп</span>'}</div>
    <div class="lab-shelf" aria-hidden="true">${FLASKS_SVG}</div>
    <div style="font-size:2.6rem;line-height:1">🎃</div>
    <h1>Миллор Групп: Секретная лаборатория</h1>
    <div class="subtitle">Halloween Bingo — Выживи до пятницы!</div>
    <div class="alert-box">
      <span class="siren">ТРЕВОГА</span>
      <p>Внимание, сотрудники Миллор Групп!</p>
      <p>В лаборатории зафиксирована аномальная активность. Дедлайны ожили, письма приходят из потустороннего мира, а пятница находится под угрозой.</p>
      <p>Только вы сможете спасти компанию!</p>
      <p>Выполняйте задания, собирайте БИНГО и зарабатывайте баллы.</p>
      <p><b>Да пребудет с вами сила пятницы!</b></p>
    </div>
    <div class="villains" aria-label="Сбежавшие из лаборатории">
      <span>👻 Призрак несогласованного бюджета</span><span>🧟 Зомби бесконечных дедлайнов</span>
      <span>🧛 Вампир корпоративных созвонов</span><span>🧙‍♀️ Ведьма срочных поручений</span><span>📨 Монстр пятничных писем</span>
    </div>
    <a class="btn big" href="${loggedIn ? '#/board' : '#/login'}">${loggedIn ? 'Вернуться в лабораторию' : 'Войти в секретную лабораторию'}</a>
    <div class="when">🗓 ${esc(when)}</div>
  </div></section>`;
}

/* ---------- Вход ---------- */
function viewLogin() {
  showChrome(false);
  app.innerHTML = `
  <section class="login">
    <div class="card">
      <h2>🔐 Пропуск в лабораторию</h2>
      <p class="muted">Введите индивидуальный игровой код от организатора. По этому же коду можно продолжить игру с другого устройства.</p>
      <form id="f-code">
        <label class="field"><span>Игровой код</span>
          <input class="input code-input" id="code" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="MLR-XXXX-XXXX" required maxlength="20"></label>
        <div class="form-error" id="err"></div>
        <button class="btn big" style="width:100%">Далее</button>
      </form>
      <form id="f-profile" hidden>
        <p>Код принят! Осталось представиться — так вас увидят в Зале славы.</p>
        <label class="field"><span>Имя и фамилия или согласованный игровой псевдоним</span>
          <input class="input" id="name" maxlength="60" autocomplete="name" required></label>
        <div class="field"><span class="muted small">Формат работы</span>
          <div class="chips" style="margin-top:6px">
            <button type="button" class="chip" data-format="office" aria-pressed="false">🏢 Офис</button>
            <button type="button" class="chip" data-format="remote" aria-pressed="false">🏠 Удалённо</button>
          </div></div>
        <div class="form-error" id="err2"></div>
        <button class="btn big" style="width:100%">Войти в лабораторию</button>
        <p class="muted small">Один код — один игровой профиль. Имя потом изменить нельзя, только через организатора.</p>
      </form>
    </div>
    <p class="center"><a href="#/">← На главный экран</a></p>
  </section>`;
  let format = null;
  const code = $('#code');
  code.focus();
  $$('.chip').forEach((b) => b.addEventListener('click', () => {
    format = b.dataset.format;
    $$('.chip').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  }));
  $('#f-code').addEventListener('submit', async (e) => {
    e.preventDefault();
    $('#err').textContent = '';
    try {
      const r = await api('/api/login', { method: 'POST', body: { code: code.value } });
      if (r.needsProfile) { $('#f-code').hidden = true; $('#f-profile').hidden = false; $('#name').focus(); return; }
      await enterGame(r.name);
    } catch (err) { $('#err').textContent = err.message; }
  });
  $('#f-profile').addEventListener('submit', async (e) => {
    e.preventDefault();
    $('#err2').textContent = '';
    if (!format) { $('#err2').textContent = 'Выберите: офис или удалённо'; return; }
    try {
      const r = await api('/api/login', { method: 'POST', body: { code: code.value, name: $('#name').value, format } });
      await enterGame(r.name);
    } catch (err) { $('#err2').textContent = err.message; }
  });
}
async function enterGame(name) {
  state.me = null; state.prevLines = null; state.prevBoard = null;
  toast(`Добро пожаловать в лабораторию, ${esc(name)}! 🧪`, 'ok');
  location.hash = '#/board';
}

/* ---------- Данные игрока и опрос ---------- */
async function refreshMe() {
  const me = await api('/api/me');
  state.timeOffset = me.game.serverTime - Date.now();
  state.me = me;
  $('#brand').innerHTML = brandHtml(me.logo);
  renderMission(me.mission);
  // Уведомления о проверке творческих заданий
  if (me.reviews.length) {
    for (const r of me.reviews) {
      const t = me.board.find((b) => b.id === r.taskId);
      if (r.status === 'approved') toast(`✅ Организатор подтвердил «${esc(t.title)}»: +10 баллов!${r.comment ? `<br><span class="muted">${esc(r.comment)}</span>` : ''}`, 'ok');
      else toast(`↩️ «${esc(t.title)}»: попробуй ещё раз.${r.comment ? `<br><span class="muted">Комментарий: ${esc(r.comment)}</span>` : ''}`, 'bad');
    }
    api('/api/me/seen-reviews', { method: 'POST', body: { at: Math.max(...me.reviews.map((r) => r.at)) } }).catch(() => {});
  }
  // Новые линии БИНГО (при первой загрузке не празднуем уже собранные)
  if (state.prevLines) {
    const fresh = me.lines.filter((l) => !state.prevLines.includes(l));
    if (fresh.length) celebrateBingo(fresh);
  }
  state.prevLines = me.lines;
  startPolling();
  return me;
}
function startPolling() {
  if (state.pollTimer) return;
  state.pollTimer = setInterval(async () => {
    if (document.hidden || !state.me) return;
    try {
      await refreshMe();
      if (location.hash.startsWith('#/board') && $('#modal').hidden) renderBoard();
      if (location.hash.startsWith('#/hall')) viewHall(true);
    } catch (e) { if (e.status === 401) { clearInterval(state.pollTimer); state.pollTimer = null; state.me = null; location.hash = '#/login'; } }
  }, 20000);
}

/* ---------- Игровое поле ---------- */
const LINES = (() => {
  const L = [];
  for (let r = 0; r < 4; r++) L.push([1, 2, 3, 4].map((c) => r * 4 + c));
  for (let c = 1; c <= 4; c++) L.push([0, 1, 2, 3].map((r) => r * 4 + c));
  L.push([1, 6, 11, 16], [4, 7, 10, 13]);
  return L;
})();

function gameBanner(me) {
  const g = me.game;
  const parts = [];
  if (me.player.isTest) parts.push(`<div class="banner test">🧪 <div class="grow"><b>Тестовый режим.</b> Этот профиль создан для проверки игры: он не попадает в основной рейтинг и может играть вне расписания.</div></div>`);
  if (!me.game.openForMe) {
    if (g.phase === 'before') parts.push(`<div class="banner warn">⏳ <div class="grow">Лаборатория откроется <b>${esc(MSK(g.start, { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' }))}</b> (МСК). До начала: <span class="countdown" data-to="${esc(g.start)}"></span></div></div>`);
    else if (g.phase === 'after') parts.push(`<div class="banner warn">🏁 <div class="grow">Игра завершена. Спасибо, что спасали лабораторию! Итоги — в <a href="#/hall">Зале славы</a>.</div></div>`);
    else parts.push(`<div class="banner warn">⏸ <div class="grow">Организатор временно приостановил игру. Прогресс сохранён — скоро продолжим!</div></div>`);
  } else if (g.phase === 'running' && g.mode === 'schedule') {
    parts.push(`<div class="banner">🕰 <div class="grow">Лаборатория открыта до <b>${esc(MSK(g.end, { hour: '2-digit', minute: '2-digit' }))}</b> (МСК). Осталось: <span class="countdown" data-to="${esc(g.end)}"></span></div></div>`);
  }
  if (me.secret && me.game.openForMe) {
    const s = me.secret;
    parts.push(`<div class="banner secret">🗝️ <div class="grow"><b>Секретное задание дня!</b> ${esc(s.question)}
      <div class="muted small">Не влияет на основной рейтинг — только на славу.</div></div>
      ${s.solved ? '<b class="amber">Разгадано ✓</b>' : s.attemptsLeft > 0 ? `<form id="secret-f" style="display:flex;gap:8px;flex-wrap:wrap;flex:1 1 260px">
        <input class="input" id="secret-a" placeholder="Ваш ответ" maxlength="100" style="flex:1;min-width:140px">
        <button class="btn sm">Ответить</button></form><span class="muted small">Попыток: ${s.attemptsLeft}</span>` : '<span class="muted">Попытки закончились</span>'}</div>`);
  }
  return parts.join('');
}

function viewBoard() {
  app.innerHTML = `<div class="wrap page"><div id="board-root"></div></div>`;
  renderBoard();
}
function renderBoard() {
  const root = $('#board-root');
  if (!root || !state.me) return;
  const me = state.me;
  const lineCells = new Set(me.lines.flatMap((i) => LINES[i]));
  const locked = !me.game.openForMe && me.game.phase === 'before';
  root.innerHTML = `
    <div class="hud">
      <div class="card hello"><div class="label">${me.player.format === 'office' ? '🏢 Офис' : '🏠 Удалённо'}</div><div class="value">${esc(me.player.name)}</div></div>
      <div class="card"><div class="label">Баллы</div><div class="value amber">${me.score}</div></div>
      <div class="card"><div class="label">Задания</div><div class="value">${me.completed}<span class="muted small">/16</span></div></div>
      <div class="card"><div class="label">БИНГО</div><div class="value">${me.bingos}<span class="muted small">/10</span></div></div>
    </div>
    ${gameBanner(me)}
    <div class="board" role="grid" aria-label="Карточка бинго 4 на 4">
      ${me.board.map((c) => `
        <button class="cell ${c.status} ${lineCells.has(c.id) ? 'in-line' : ''} ${locked ? 'locked' : ''}" data-id="${c.id}" role="gridcell" aria-label="${esc(c.title)}: ${STATUS[c.status]}">
          <span class="num">${c.id}</span>
          <span class="emoji">${c.emoji}</span>
          <span class="title">${esc(c.title)}</span>
          <span class="meta"><span class="pill ${c.status}">${STATUS[c.status]}</span><span class="pts">10 б.</span></span>
        </button>`).join('')}
    </div>
    <div class="legend">
      <span>🏅 Место в рейтинге: <b>${me.rank ?? '—'}</b> из ${me.totalPlayers}</span>
      <span>⭐ 10 баллов за задание</span><span>✨ +30 за каждую линию из 4 клеток</span><span>🎯 Максимум: 460</span>
    </div>`;
  $$('.cell', root).forEach((b) => b.addEventListener('click', () => {
    if (locked) { toast('Лаборатория ещё закрыта — задания откроются в начале игры.'); return; }
    location.hash = `#/task/${b.dataset.id}`;
  }));
  const sf = $('#secret-f', root);
  if (sf) sf.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const r = await api('/api/secret/answer', { method: 'POST', body: { id: me.secret.id, answer: $('#secret-a').value } });
      if (r.correct) toast(`🗝️ Секрет разгадан!${r.prediction ? `<br>🔮 ${esc(r.prediction)}` : ''}`, 'ok');
      else toast(`Не то заклинание. Осталось попыток: ${r.attemptsLeft}`, 'bad');
      await refreshMe(); renderBoard();
    } catch (err) { toast(esc(err.message), 'bad'); }
  });
  tickCountdowns();
}
function tickCountdowns() {
  clearInterval(state.tickTimer);
  const upd = () => {
    const els = $$('.countdown');
    if (!els.length) { clearInterval(state.tickTimer); return; }
    for (const el of els) {
      let ms = Date.parse(el.dataset.to) - (Date.now() + state.timeOffset);
      if (ms <= 0) { el.textContent = '00:00:00'; if (!el.dataset.fired) { el.dataset.fired = 1; setTimeout(() => refreshMe().then(renderBoard).catch(() => {}), 1500); } continue; }
      const d = Math.floor(ms / 864e5); ms -= d * 864e5;
      const h = Math.floor(ms / 36e5), m = Math.floor((ms % 36e5) / 6e4), s = Math.floor((ms % 6e4) / 1e3);
      el.textContent = `${d ? d + ' д ' : ''}${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
  };
  upd();
  state.tickTimer = setInterval(upd, 1000);
}

/* ---------- БИНГО ---------- */
function celebrateBingo(lines) {
  const el = $('#bingo');
  const bits = ['🎃', '👻', '🦇', '🧪', '🍬', '⭐', '✨', '💊'];
  el.innerHTML = `<div class="bingo-card"><h2>БИНГО!</h2><p>Ты только что спас часть лаборатории!</p>
    <div class="plus">+${30 * lines.length} баллов${lines.length > 1 ? ` · ${lines.length} линии сразу!` : ''}</div>
    <p class="muted small">Нажми, чтобы продолжить</p></div>` +
    Array.from({ length: 40 }, () => `<span class="confetti" style="left:${Math.random() * 100}%;animation-duration:${2.5 + Math.random() * 2.5}s;animation-delay:${Math.random() * 1.2}s">${bits[Math.floor(Math.random() * bits.length)]}</span>`).join('');
  el.hidden = false;
  const close = () => {
    el.hidden = true;
    const cells = new Set(lines.flatMap((i) => LINES[i]));
    $$('.cell').forEach((c) => { if (cells.has(Number(c.dataset.id))) { c.classList.add('flash'); setTimeout(() => c.classList.remove('flash'), 3800); } });
  };
  el.onclick = close;
  setTimeout(() => { if (!el.hidden) close(); }, 5000);
}

/* ---------- Модальное окно задания ---------- */
let modalTaskId = null;
function closeModal(silent) {
  if ($('#modal').hidden) return;
  $('#modal').hidden = true;
  $('#modal-body').innerHTML = '';
  document.body.style.overflow = '';
  modalTaskId = null;
  if (!silent && location.hash.startsWith('#/task/')) history.replaceState(null, '', '#/board');
  if (!silent) renderBoard();
}
$('#modal-close').addEventListener('click', () => closeModal());
$('#modal').addEventListener('click', (e) => { if (e.target.id === 'modal') closeModal(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#modal').hidden) closeModal(); });

async function openTask(id) {
  let task;
  try { task = await api(`/api/tasks/${id}`); } catch (e) { toast(esc(e.message), 'bad'); history.replaceState(null, '', '#/board'); return; }
  modalTaskId = id;
  $('#modal').hidden = false;
  document.body.style.overflow = 'hidden';
  if (state.me.game.openForMe && task.status === 'not_started') {
    task.status = 'in_progress';
    api(`/api/tasks/${id}/open`, { method: 'POST', body: {} }).catch(() => {});
  }
  renderTask(task);
}
async function reloadTask() {
  if (!modalTaskId) return;
  const task = await api(`/api/tasks/${modalTaskId}`);
  renderTask(task);
}

function renderTask(t) {
  const body = $('#modal-body');
  const open = state.me.game.openForMe;
  const finished = t.status === 'done' || t.status === 'failed';
  const attempts = t.attemptsLeft != null ? `<span class="pill">Попыток: ${t.attemptsLeft} из ${t.maxAttempts}</span>` : '';
  body.innerHTML = `
    <div class="task-head"><div class="emoji">${t.emoji}</div><div>
      <h2>${esc(t.title)}</h2>
      <div class="task-tags"><span class="pill ${t.status}">${STATUS[t.status]}</span><span class="pill amber">10 баллов</span>
        <span class="pill">${t.type === 'auto' ? '⚡ Проверяется автоматически' : '🎨 Творческое · проверяет организатор'}</span>${t.type === 'auto' && !finished ? attempts : ''}</div>
    </div></div>
    <div class="task-desc">${esc(t.description)}</div>
    <div id="task-ui"></div>
    <div id="task-result"></div>`;
  const ui = $('#task-ui', body);
  const ro = !open || finished || t.status === 'review';
  const R = RENDERERS[t.kind];
  R(ui, t, ro);
  if (t.status === 'done') showDone(t);
  else if (t.status === 'failed') setResult('bad', 'Попытки исчерпаны. Это задание уже не принесёт баллов, но впереди ещё много монстров — вперёд к другим клеткам!');
  else if (!open) setResult('info', state.me.game.phase === 'after' ? 'Игра завершена — ответы больше не принимаются.' : 'Сейчас игра не идёт — ответы не принимаются.');
  else if (t.status === 'retry' && t.lastResult && t.type === 'auto') setResult('bad', esc(t.lastResult));
}
function setResult(kind, html) {
  $('#task-result').innerHTML = `<div class="result ${kind}">${html}</div>`;
}
function showDone(t, prediction) {
  const p = prediction || t.prediction;
  $('#task-result').innerHTML = `<div class="result ok">✅ Задание выполнено! +10 баллов в копилку лаборатории.</div>
    ${p ? `<div class="prediction">🔮 <b>Случайное предсказание:</b> ${esc(p)}</div>` : ''}
    <div class="actions"><button class="btn" id="to-board">К полю бинго</button></div>`;
  $('#to-board').addEventListener('click', () => closeModal());
}

async function attempt(t, payload) {
  const r = await api(`/api/tasks/${t.id}/attempt`, { method: 'POST', body: { payload } });
  return r;
}
async function afterAttempt(t, r, { onWrong } = {}) {
  if (r.result === 'correct') {
    await reloadTask();
    showDone({ ...t, status: 'done' }, r.prediction);
    await refreshMe();
  } else if (r.result === 'wrong') {
    if (r.status === 'failed') { await reloadTask(); await refreshMe(); return; }
    await reloadTask();
    setResult('bad', `${esc(r.feedback)} Осталось попыток: ${r.attemptsLeft}.`);
    $('#task-ui').classList.add('shake'); setTimeout(() => $('#task-ui') && $('#task-ui').classList.remove('shake'), 500);
    if (onWrong) onWrong(r);
  }
}
function wrapErr(fn) {
  return async (...a) => { try { await fn(...a); } catch (e) { setResult('bad', esc(e.message)); } };
}

/* ---------- Перетаскивание (мышь и сенсор) ---------- */
function sortable(container, { vertical = false } = {}) {
  let drag = null, selected = null;
  container.addEventListener('pointerdown', (e) => {
    if (container.classList.contains('locked')) return;
    const item = e.target.closest('[data-id]');
    if (!item || item.parentElement !== container) return;
    e.preventDefault();
    drag = { item, pid: e.pointerId, sx: e.clientX, sy: e.clientY, moved: false };
    item.setPointerCapture(e.pointerId);
  });
  container.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.pid) return;
    const { item } = drag;
    if (!drag.moved) {
      if (Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy) < 6) return;
      drag.moved = true;
      const r = item.getBoundingClientRect();
      drag.ox = drag.sx - r.left; drag.oy = drag.sy - r.top;
      drag.ph = item.cloneNode(true); drag.ph.classList.add('ph'); drag.ph.removeAttribute('data-id');
      drag.ph.style.width = r.width + 'px'; drag.ph.style.height = r.height + 'px';
      item.after(drag.ph);
      item.style.width = r.width + 'px'; item.style.height = r.height + 'px';
      item.classList.add('dragging');
      if (selected) { selected.classList.remove('selected'); selected = null; }
    }
    item.style.left = (e.clientX - drag.ox) + 'px';
    item.style.top = (e.clientY - drag.oy) + 'px';
    const others = [...container.children].filter((x) => x !== item && x !== drag.ph);
    let before = null;
    for (const o of others) {
      const r = o.getBoundingClientRect();
      if (vertical ? e.clientY < r.top + r.height / 2 : (e.clientY < r.top || (e.clientY <= r.bottom && e.clientX < r.left + r.width / 2))) { before = o; break; }
    }
    if (before) { if (drag.ph.nextSibling !== before) container.insertBefore(drag.ph, before); } else if (container.lastElementChild !== drag.ph) container.append(drag.ph);
  });
  const end = (e) => {
    if (!drag || e.pointerId !== drag.pid) return;
    const { item } = drag;
    if (drag.moved) {
      drag.ph.replaceWith(item);
      item.classList.remove('dragging');
      item.style.left = item.style.top = item.style.width = item.style.height = '';
    } else {
      // Нажатие без перетаскивания: выбрать элемент, затем второй — поменять местами.
      if (selected && selected !== item) {
        const a = selected, b = item, ph = document.createElement('span');
        a.replaceWith(ph); b.replaceWith(a); ph.replaceWith(b);
        a.classList.remove('selected'); selected = null;
      } else if (selected === item) { item.classList.remove('selected'); selected = null; }
      else { selected = item; item.classList.add('selected'); }
    }
    drag = null;
  };
  container.addEventListener('pointerup', end);
  container.addEventListener('pointercancel', end);
  return () => [...container.children].map((x) => x.dataset.id);
}

/* ---------- Отрисовка заданий ---------- */
const RENDERERS = {
  quiz(ui, t, ro) {
    const picks = [];
    ui.innerHTML = t.content.questions.map((q, i) => `
      <div class="q"><div class="qtext ${/^\p{Extended_Pictographic}/u.test(q.q) ? 'emoji-q' : ''}">${i + 1}. ${esc(q.q)}</div>
        <div class="opts">${q.options.map(([id, txt]) => `<button class="opt" data-q="${i}" data-id="${id}" aria-pressed="false" ${ro ? 'disabled' : ''}>${esc(txt)}</button>`).join('')}</div></div>`).join('') +
      (ro ? '' : `<div class="actions"><button class="btn" id="go">Проверить ответы</button></div>`);
    $$('.opt', ui).forEach((b) => b.addEventListener('click', () => {
      picks[b.dataset.q] = b.dataset.id;
      $$(`.opt[data-q="${b.dataset.q}"]`, ui).forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    }));
    if (!ro) $('#go', ui).addEventListener('click', wrapErr(async () => {
      if (picks.filter(Boolean).length < t.content.questions.length) { setResult('info', 'Ответь на все вопросы.'); return; }
      afterAttempt(t, await attempt(t, { answers: picks }));
    }));
  },

  anagram(ui, t, ro) {
    const getters = [];
    ui.innerHTML = t.content.words.map((w, i) => {
      const solved = t.state.words && t.state.words[i];
      const letters = solved ? [...solved] : w.letters;
      return `<div class="word-row"><div class="hint">${t.content.words.length > 1 ? `Слово ${i + 1}: ` : ''}${esc(w.hint)}${solved ? ' — <b style="color:var(--green)">собрано ✓</b>' : ''}</div>
        <div class="sortable ${solved || ro ? 'locked' : ''}" data-w="${i}">${letters.map((l, j) => `<div class="tile" data-id="${j}:${esc(l)}">${esc(l)}</div>`).join('')}</div></div>`;
    }).join('') + (ro ? '' : `<p class="sort-help">Перетащи буквы пальцем или мышкой. Можно и так: нажми на одну букву, затем на другую — они поменяются местами.</p>
      <div class="actions"><button class="btn" id="go">Произнести заклинание</button></div>`);
    $$('.sortable', ui).forEach((c) => getters.push(sortable(c)));
    if (!ro) $('#go', ui).addEventListener('click', wrapErr(async () => {
      const words = getters.map((g) => g().map((id) => id.split(':')[1]).join(''));
      afterAttempt(t, await attempt(t, { words }));
    }));
  },

  ghosts(ui, t, ro) {
    ui.innerHTML = `<div class="actions" style="margin:0 0 10px;align-items:center"><span class="counter" id="gc">Найдено: ${t.state.found.length}/${t.content.total}</span>
      <span class="muted small">Нажимай на привидений прямо на картинке</span></div>
      <div class="scene" id="scene"><img src="/api/tasks/4/scene.svg" alt="Ночная лаборатория Миллор Групп" draggable="false"></div>`;
    const scene = $('#scene', ui);
    const mark = (x, y, cls) => {
      const m = document.createElement('span'); m.className = cls;
      m.style.left = (x / 8) + '%'; m.style.top = (y / 5) + '%';
      scene.append(m);
      if (cls === 'miss') setTimeout(() => m.remove(), 700);
    };
    t.state.spots.forEach((s) => mark(s.x, s.y, 'mark'));
    if (ro) return;
    let busy = false;
    scene.addEventListener('click', wrapErr(async (e) => {
      if (busy) return; busy = true;
      try {
        const r = scene.getBoundingClientRect();
        const x = ((e.clientX - r.left) / r.width) * 800, y = ((e.clientY - r.top) / r.height) * 500;
        const res = await attempt(t, { x, y });
        if (res.hit || res.result === 'correct') {
          $$('.mark', scene).forEach((m) => m.remove());
          res.state.spots.forEach((s) => mark(s.x, s.y, 'mark'));
        } else mark(x, y, 'miss');
        $('#gc').textContent = `Найдено: ${res.state.found.length}/${t.content.total}`;
        if (res.result === 'correct') { await refreshMe(); showDone({ ...t, status: 'done' }, res.prediction); }
        else setResult(res.hit ? 'ok' : 'info', esc(res.feedback));
      } finally { busy = false; }
    }));
  },

  detective(ui, t, ro) {
    const c = t.content;
    let culprit = null, clue = null;
    ui.innerHTML = `<div class="case-file">${esc(c.case)}</div>
      <h3>Подозреваемые</h3>
      <div class="suspects">${c.suspects.map((s) => `<button class="suspect" data-id="${s.id}" aria-pressed="false" ${ro ? 'disabled' : ''}>
        <div class="face">${s.emoji}</div><div class="nm">${esc(s.name)}</div><div class="al">${esc(s.alibi)}</div></button>`).join('')}</div>
      <h3>Улики</h3>
      <div class="clues">${c.clues.map((k) => `<button class="clue" data-id="${k.id}" aria-pressed="false" ${ro ? 'disabled' : ''}><span>${k.icon}</span><span>${esc(k.text)}</span></button>`).join('')}</div>
      ${ro ? '' : `<p class="muted small" style="margin-top:12px">Выбери виновного и улику, которая его выдаёт.</p><div class="actions"><button class="btn red" id="go">🔨 Предъявить обвинение</button></div>`}`;
    $$('.suspect', ui).forEach((b) => b.addEventListener('click', () => { culprit = b.dataset.id; $$('.suspect', ui).forEach((x) => x.setAttribute('aria-pressed', String(x === b))); }));
    $$('.clue', ui).forEach((b) => b.addEventListener('click', () => { clue = b.dataset.id; $$('.clue', ui).forEach((x) => x.setAttribute('aria-pressed', String(x === b))); }));
    if (!ro) $('#go', ui).addEventListener('click', wrapErr(async () => {
      if (!culprit || !clue) { setResult('info', 'Нужно выбрать и подозреваемого, и улику.'); return; }
      afterAttempt(t, await attempt(t, { culprit, clue }));
    }));
  },

  sort(ui, t, ro) {
    const colors = { f: '#9b1d2a', k: '#5a2a7a', r: '#f28c28' };
    ui.innerHTML = `<p class="sort-help">Перетащи упаковки: сверху — первая по алфавиту. Или нажми на одну упаковку, а затем на другую, чтобы поменять их местами.</p>
      <div class="sortable vertical ${ro ? 'locked' : ''}" id="packs">${t.content.items.map(([id, name]) => `
        <div class="pack" data-id="${id}" style="--pc:${colors[id]}"><span class="grip">⋮⋮</span><span class="pack-name">${esc(name.toUpperCase())}</span><span class="pack-sub">Миллор Групп · склад 13</span></div>`).join('')}</div>
      ${ro ? '' : '<div class="actions"><button class="btn" id="go">Проверить порядок</button></div>'}`;
    const get = sortable($('#packs', ui), { vertical: true });
    if (t.status === 'done') {
      const order = ['k', 'r', 'f'];
      order.forEach((id) => $('#packs', ui).append($(`[data-id="${id}"]`, ui)));
    }
    if (!ro) $('#go', ui).addEventListener('click', wrapErr(async () => afterAttempt(t, await attempt(t, { order: get() }))));
  },

  story(ui, t, ro) {
    const steps = t.state.steps;
    const c = t.content.steps;
    const cur = steps.length;
    ui.innerHTML = steps.map((s, i) => `<div class="story-step"><div><b>Ситуация ${i + 1}.</b> ${esc(c[i].q)}</div>
        <div class="ans">➜ ${esc(c[i].options.find((o) => o[0] === s.choice)[1])}</div><div class="out">${esc(s.outcome)}</div></div>`).join('') +
      (cur < c.length && !ro ? `<div class="q" style="margin-top:14px"><div class="qtext">Ситуация ${cur + 1} из ${c.length}. ${esc(c[cur].q)}</div>
        <div class="opts">${c[cur].options.map(([id, txt]) => `<button class="opt" data-id="${id}">${esc(txt)}</button>`).join('')}</div></div>` : '');
    $$('.opt', ui).forEach((b) => b.addEventListener('click', wrapErr(async () => {
      $$('.opt', ui).forEach((x) => (x.disabled = true));
      const r = await attempt(t, { choice: b.dataset.id });
      if (r.result === 'correct') { await reloadTask(); showDone({ ...t, status: 'done' }, r.prediction); $('#task-result').insertAdjacentHTML('afterbegin', `<div class="result info">🏅 ${esc(r.feedback)}</div>`); await refreshMe(); }
      else { await reloadTask(); }
    })));
  },

  safe(ui, t, ro) {
    let code = '';
    const done = t.status === 'done';
    ui.innerHTML = `<div class="safe-wrap">
      <div><ol class="hints">${t.content.hints.map((h) => `<li>${esc(h)}</li>`).join('')}</ol>
        ${ro ? '' : `<div class="keypad">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => `<button data-k="${n}">${n}</button>`).join('')}<button data-k="del" aria-label="Стереть">⌫</button><button data-k="0">0</button><button data-k="ok" style="background:var(--pumpkin);color:#2a1406">✓</button></div>`}</div>
      <div class="safe ${done ? 'open' : ''}" id="safe">
        <div class="safe-inside">🧪✨</div>
        <div class="safe-door"><div class="safe-screen" id="scr"><span></span><span></span><span></span></div><div class="dial" id="dial"></div></div>
      </div></div>`;
    const show = () => $$('#scr span', ui).forEach((s, i) => (s.textContent = code[i] || (done ? '612'[i] : '')));
    show();
    if (ro) return;
    $$('.keypad button', ui).forEach((b) => b.addEventListener('click', wrapErr(async () => {
      const k = b.dataset.k;
      if (k === 'del') code = code.slice(0, -1);
      else if (k === 'ok') {
        if (code.length < 3) { setResult('info', 'Нужно три цифры.'); return; }
        const r = await attempt(t, { code });
        $('#dial', ui).style.transform = `rotate(${720 + Math.random() * 180}deg)`;
        if (r.result === 'correct') {
          setTimeout(() => $('#safe', ui).classList.add('open'), 500);
          setTimeout(async () => { await refreshMe(); showDone({ ...t, status: 'done' }, r.prediction); $$('.keypad button', ui).forEach((x) => (x.disabled = true)); }, 1300);
          return;
        }
        code = '';
        await afterAttempt(t, r);
        return;
      } else if (code.length < 3) code += k;
      show();
    })));
  },

  archive(ui, t, ro) {
    let pick = null;
    ui.innerHTML = `<div class="archive">${t.content.labels.map(([id, name, ser]) => `
      <button class="label-card" data-id="${id}" aria-pressed="false" ${ro ? 'disabled' : ''}><span class="stamp">АРХИВ</span>
        <div class="lname">${esc(name)}</div><div class="lser">${esc(ser)}</div></button>`).join('')}</div>
      ${ro ? '' : '<div class="actions"><button class="btn" id="go">Это подлинник!</button></div>'}`;
    $$('.label-card', ui).forEach((b) => b.addEventListener('click', () => { pick = b.dataset.id; $$('.label-card', ui).forEach((x) => x.setAttribute('aria-pressed', String(x === b))); }));
    if (!ro) $('#go', ui).addEventListener('click', wrapErr(async () => {
      if (!pick) { setResult('info', 'Сначала выбери этикетку.'); return; }
      const chosen = pick;
      await afterAttempt(t, await attempt(t, { label: chosen }), { onWrong: () => { const el = $(`.label-card[data-id="${chosen}"]`); if (el) el.classList.add('wrong'); } });
    }));
  },

  text(ui, t, ro) { creative(ui, t, ro); },
  photo(ui, t, ro) { creative(ui, t, ro); },
};

function creative(ui, t, ro) {
  const s = t.submission;
  const reviewInfo = s && s.status === 'pending' ? '<div class="result info">⏳ Ответ на проверке у организатора. Баллы придут после подтверждения — мы сообщим!</div>' :
    s && s.status === 'rejected' ? `<div class="result bad">↩️ Организатор вернул ответ: попробуй ещё раз.${s.comment ? `<br>Комментарий: ${esc(s.comment)}` : ''}</div>` : '';
  const shown = s ? `<div class="submitted">${s.text ? esc(s.text) : '<span class="muted">(без текста)</span>'}${s.photo ? `<img src="${s.photo}" alt="Ваше фото">` : ''}</div>` : '';
  if (ro || (s && s.status === 'pending')) {
    ui.innerHTML = (shown ? `<h3>Твой ответ</h3>${shown}` : '') + reviewInfo;
    return;
  }
  ui.innerHTML = `${reviewInfo}
    ${t.content.prefix ? `<div class="prefix">${esc(t.content.prefix)}</div>` : ''}
    <label class="field"><span>${t.content.photo ? 'Описание (или вместо фото — расскажи словами)' : 'Твой ответ'}</span>
      <textarea class="input" id="ans" maxlength="1500" placeholder="${esc(t.content.placeholder)}">${s && s.status === 'rejected' ? esc(s.text) : ''}</textarea></label>
    ${t.content.photo ? `<label class="photo-drop" id="drop"><input type="file" id="file" accept="image/jpeg,image/png,image/webp,image/heic,image/*" hidden>
      <span id="drop-inner">📷 Нажми, чтобы прикрепить фото (необязательно)<br><span class="small">JPEG / PNG / WebP, до 5 МБ. Лицо показывать не нужно.</span></span></label>` : ''}
    <label class="check"><input type="checkbox" id="consent"><span>Разрешаю показать мой ответ коллегам в «Галерее лаборатории» после одобрения. Без галочки ответ увидит только организатор.</span></label>
    <div class="actions"><button class="btn" id="go">Отправить на проверку</button></div>`;
  let photo = null;
  const file = $('#file', ui);
  if (file) file.addEventListener('change', wrapErr(async () => {
    const f = file.files[0];
    if (!f) return;
    if (!f.type.startsWith('image/')) throw new Error('Это не изображение');
    if (f.size > 25 * 1024 * 1024) throw new Error('Файл слишком большой');
    $('#drop-inner').textContent = 'Обрабатываю фото…';
    photo = await resizeImage(f);
    $('#drop-inner').innerHTML = `<img src="${photo}" alt="Предпросмотр"><br><span class="small">Нажми, чтобы заменить фото</span>`;
    setResult('info', 'Фото готово к отправке. Геометки и данные камеры удалены.');
  }));
  $('#go', ui).addEventListener('click', wrapErr(async () => {
    const text = $('#ans', ui).value.trim();
    if (!photo && text.length < 3) throw new Error(t.content.photo ? 'Прикрепи фото или опиши словами.' : 'Напиши ответ — хотя бы пару слов.');
    $('#go', ui).disabled = true;
    try {
      const r = await api(`/api/tasks/${t.id}/submit`, { method: 'POST', body: { text, photo, consent: $('#consent', ui).checked } });
      await reloadTask();
      $('#task-result').innerHTML = `<div class="result ok">📨 Ответ отправлен организатору!</div>${r.prediction ? `<div class="prediction">🔮 <b>Случайное предсказание:</b> ${esc(r.prediction)}</div>` : ''}`;
      await refreshMe();
    } finally { const g = $('#go', ui); if (g) g.disabled = false; }
  }));
}

// Уменьшаем фото в браузере: меньше трафика и без EXIF (в том числе без геометок).
async function resizeImage(file, max = 1600) {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    await new Promise((ok, fail) => { img.onload = ok; img.onerror = () => fail(new Error('Не удалось открыть фото. Попробуйте JPEG или PNG.')); img.src = url; });
    const k = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement('canvas');
    c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
    let q = 0.85, out = c.toDataURL('image/jpeg', q);
    while (out.length > 6.5e6 && q > 0.4) { q -= 0.15; out = c.toDataURL('image/jpeg', q); }
    return out;
  } finally { URL.revokeObjectURL(url); }
}

/* ---------- Зал славы ---------- */
async function viewHall(silent) {
  let d;
  try { d = await api('/api/leaderboard'); } catch (e) { if (!silent) app.innerHTML = `<div class="wrap page empty">${esc(e.message)}</div>`; return; }
  if (silent && !location.hash.startsWith('#/hall')) return;
  renderMission(d.mission);
  const top = d.rows.slice(0, 3);
  const medal = ['🥇', '🥈', '🥉'];
  const podium = top.length ? `<div class="podium">${[1, 0, 2].filter((i) => top[i]).map((i) => `
      <div class="pl p${i + 1}"><div class="medal">${medal[i]}</div><div class="nm">${esc(top[i].name)}</div>
      <div class="sc">${top[i].score}</div><div class="muted small">${top[i].completed} заданий · ${top[i].bingos} БИНГО</div></div>`).join('')}</div>` : '';
  app.innerHTML = `<div class="wrap page">
    <h1>🏆 Зал славы Миллор Групп</h1>
    <p class="muted">Общий рейтинг офисных и удалённых сотрудников. Обновляется после каждого подтверждённого задания.</p>
    ${d.winners && d.winners.length ? `<div class="card section"><h2>🎉 Победители</h2><div class="prizes">${d.winners.map((w) => `<div class="prize">${esc(w.title)}<br><b>${esc(w.name)}</b> · ${w.amount.toLocaleString('ru-RU')} ₽</div>`).join('')}</div></div>` : ''}
    ${podium}
    ${d.rows.length ? `<div class="card" style="padding:8px 12px;overflow-x:auto"><table class="rating">
      <thead><tr><th>Место</th><th>Участник</th><th class="n hide-sm">Заданий</th><th class="n">БИНГО</th><th class="n">Баллы</th></tr></thead>
      <tbody>${d.rows.map((r) => `<tr class="${r.rank <= 3 ? 'top' : ''} ${r.me ? 'me' : ''}"><td>${r.rank <= 3 ? medal[r.rank - 1] : r.rank}</td>
        <td>${esc(r.name)} ${r.me ? '<span class="pill">это вы</span>' : ''} <span class="muted small" title="${r.format === 'office' ? 'Офис' : 'Удалённо'}">${r.format === 'office' ? '🏢' : '🏠'}</span></td>
        <td class="n hide-sm">${r.completed}</td><td class="n">${r.bingos}</td><td class="n score">${r.score}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Пока никто не вошёл в лабораторию. Будь первым!</div>'}
    ${d.secretSolvers.length ? `<div class="section card"><h3>🗝️ Первыми разгадали секретное задание</h3><p>${d.secretSolvers.map(esc).join(' · ')}</p><p class="muted small">Секретные задания не влияют на основной рейтинг.</p></div>` : ''}
    <div class="section"><h2>🎁 Призовой фонд — 6 000 ₽</h2><div class="prizes">
      <div class="prize">🥇 1-е место<br><b>2 000 ₽</b></div><div class="prize">🥈 2-е место<br><b>1 500 ₽</b></div><div class="prize">🥉 3-е место<br><b>1 000 ₽</b></div>
      <div class="prize">🎨 Самый креативный участник<br><b>1 000 ₽</b></div><div class="prize">🎲 Случайный участник с БИНГО<br><b>500 ₽</b></div></div>
      <p class="muted small">Один сотрудник получает не более одного приза. При равенстве баллов места определяет прозрачная жеребьёвка после проверки всех ответов.</p></div>
  </div>`;
}

/* ---------- Галерея ---------- */
async function viewGallery() {
  let items = [];
  try { items = await api('/api/gallery'); } catch (e) { app.innerHTML = `<div class="wrap page empty">${esc(e.message)}</div>`; return; }
  app.innerHTML = `<div class="wrap page"><h1>🖼️ Галерея лаборатории</h1>
    <p class="muted">Здесь только одобренные организатором ответы, авторы которых разрешили их показать.</p>
    ${items.length ? `<div class="gallery">${items.map((i) => `<div class="item card">${i.photo ? `<img src="${i.photo}" alt="" loading="lazy">` : ''}
      <div class="muted small">${esc(i.title)}</div>${i.text ? `<div style="white-space:pre-line">${esc(i.text)}</div>` : ''}<div class="small amber" style="margin-top:6px">— ${esc(i.name)}</div></div>`).join('')}</div>`
      : '<div class="empty">Пока пусто. Отправляй творческие ответы с галочкой «Разрешаю показать» — и они появятся здесь!</div>'}</div>`;
}

/* ---------- Правила ---------- */
function viewRules() {
  const g = state.me.game;
  app.innerHTML = `<div class="wrap page"><h1>📜 Правила лаборатории</h1><div class="card"><ul class="rules">
    <li>Игра идёт <b>${esc(MSK(g.start, { day: 'numeric', month: 'long' }))} с ${esc(MSK(g.start, { hour: '2-digit', minute: '2-digit' }))} до ${esc(MSK(g.end, { hour: '2-digit', minute: '2-digit' }))}</b> по московскому времени.</li>
    <li>На поле 4×4 — 16 испытаний. Выполняй их в любом порядке. Все задания доступны и в офисе, и дома.</li>
    <li>За каждое задание — <b class="amber">10 баллов</b>. За каждую линию из 4 выполненных клеток (по горизонтали, вертикали или диагонали) — ещё <b class="amber">30 баллов</b>. Всего 10 линий, максимум — 460 баллов.</li>
    <li>10 заданий проверяются автоматически. В викторинах и головоломках — до 3 попыток, одинаково для всех.</li>
    <li>6 творческих заданий проверяет организатор. Баллы начисляются после подтверждения. Если ответ вернули — можно отправить новый.</li>
    <li>Баллы за одно задание начисляются только один раз.</li>
    <li>Фото — по желанию и без лица. Везде, где есть фото, можно ответить текстом.</li>
    <li>Твои ответы и фото видит только организатор. В Галерее показываются лишь одобренные ответы, если ты поставил галочку согласия.</li>
    <li>Секретное задание дня и предсказания — для удовольствия, на рейтинг они не влияют.</li>
    <li>Призы: 1-е место — 2 000 ₽, 2-е — 1 500 ₽, 3-е — 1 000 ₽, самый креативный — 1 000 ₽, случайный участник с БИНГО — 500 ₽. Не более одного приза на человека.</li>
  </ul>
  <p class="muted small">Ваш игровой код: <b>${esc(state.me.player.code)}</b> — по нему можно войти с другого устройства. Никому его не передавайте.</p>
  <div class="actions"><button class="btn ghost" id="logout">Выйти на этом устройстве</button></div></div></div>`;
  $('#logout').addEventListener('click', async () => {
    await api('/api/logout', { method: 'POST', body: {} }).catch(() => {});
    state.me = null; clearInterval(state.pollTimer); state.pollTimer = null;
    location.hash = '#/';
  });
}

router().catch((e) => { app.innerHTML = `<div class="wrap page empty">Не удалось загрузить игру: ${esc(e.message)}</div>`; });
