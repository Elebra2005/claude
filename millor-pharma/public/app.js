'use strict';
/* Миллор Фарма: Секретная лаборатория — клиент участника. Все баллы и проверки считает сервер. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const app = $('#app');
const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
const MSK = (iso, o) => new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', ...o }).format(new Date(iso));
const plural = (n, a, b, c) => { const m = n % 10, h = n % 100; return m === 1 && h !== 11 ? a : m >= 2 && m <= 4 && (h < 12 || h > 14) ? b : c; };

const S = { me: null, offset: 0, prevLines: null, prevStates: null, poll: null, anim: true, sound: false, task: null };
const now = () => Date.now() + S.offset;
const syncTime = (t) => { if (t) S.offset = t - Date.now(); };

/* ---------- Анимации, звуки и фоновая музыка ---------- */
S.anim = store.get('mp-anim') !== null ? store.get('mp-anim') === '1' : !matchMedia('(prefers-reduced-motion: reduce)').matches;
S.sound = store.get('mp-sound') === '1';
S.music = store.get('mp-music') !== '0';
function applyToggles() {
  document.body.classList.toggle('noanim', !S.anim);
  $('#tgl-anim').setAttribute('aria-pressed', String(S.anim));
  $('#tgl-sound').setAttribute('aria-pressed', String(S.sound)); $('#tgl-sound').textContent = S.sound ? '🔊' : '🔇';
  $('#tgl-music').setAttribute('aria-pressed', String(S.music)); $('#tgl-music').style.opacity = S.music ? 1 : .5;
}
$('#tgl-anim').addEventListener('click', () => { S.anim = !S.anim; store.set('mp-anim', S.anim ? '1' : '0'); applyToggles(); });
$('#tgl-sound').addEventListener('click', () => { S.sound = !S.sound; store.set('mp-sound', S.sound ? '1' : '0'); applyToggles(); beep([[660, .08]]); });
$('#tgl-music').addEventListener('click', () => { S.music = !S.music; store.set('mp-music', S.music ? '1' : '0'); applyToggles(); S.music ? Music.start() : Music.stop(); });
let actx;
const audioCtx = () => { try { actx = actx || new (window.AudioContext || window.webkitAudioContext)(); if (actx.state === 'suspended') actx.resume(); return actx; } catch { return null; } };
function beep(seq) {
  if (!S.sound) return;
  const ctx = audioCtx(); if (!ctx) return;
  let t = ctx.currentTime;
  for (const [f, d] of seq) { const o = ctx.createOscillator(), g = ctx.createGain(); o.frequency.value = f; o.type = 'triangle'; g.gain.setValueAtTime(.08, t); g.gain.exponentialRampToValueAtTime(.0001, t + d); o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + d); t += d * .9; }
}
/* Мелодия собирается в браузере из нот (без аудиофайлов): вальс в ля миноре, музыкальная шкатулка, низкий бас и эхо. */
const Music = (() => {
  const BEAT = 0.62; // секунд на долю, размер 3/4
  const hz = (m) => 440 * Math.pow(2, (m - 69) / 12);
  const MELODY = [
    [[76, 1], [72, 1], [69, 1], [71, 1], [72, 1], [74, 1], [77, 2], [76, 1], [74, 1], [71, 1], [68, 1]],
    [[69, 1], [72, 1], [76, 1], [81, 2], [80, 1], [77, 1], [76, 1], [74, 1], [76, 2], [null, 1]],
  ];
  const BASS = [[45, 52], [45, 52], [41, 48], [40, 47]]; // Am, Am, F, E: корень и квинта
  let ctx, master, echo, timer, nextT = 0, beat = 0, on = false;
  const pluck = (m, t, dur, vol) => {
    for (const [mul, v, type] of [[1, vol, 'sine'], [2, vol * .28, 'sine'], [3.01, vol * .08, 'sine']]) {
      const o = ctx.createOscillator(), g = ctx.createGain(); o.type = type; o.frequency.value = hz(m) * mul;
      g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(v, t + .012); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
      o.connect(g); g.connect(master); g.connect(echo); o.start(t); o.stop(t + dur + .05);
    }
  };
  const bass = (m, t, dur, vol) => {
    const o = ctx.createOscillator(), f = ctx.createBiquadFilter(), g = ctx.createGain(); o.type = 'triangle'; o.frequency.value = hz(m); f.type = 'lowpass'; f.frequency.value = 420;
    g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + .05); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    o.connect(f); f.connect(g); g.connect(master); o.start(t); o.stop(t + dur + .05);
  };
  const flat = MELODY.map((ph) => { const out = []; let b = 0; for (const [n, d] of ph) { out.push([b, n, d]); b += d; } return out; });
  const schedule = () => {
    while (nextT < ctx.currentTime + .7) {
      const bar = Math.floor(beat / 3), inBar = beat % 3, phrase = Math.floor(bar / 4) % 2, barInPhrase = bar % 4, t = nextT;
      const [root, fifth] = BASS[barInPhrase];
      if (inBar === 0) bass(root, t, BEAT * 2.6, .5); else bass(fifth, t, BEAT * .9, .22);
      for (const [b, n, d] of flat[phrase]) if (n && b === barInPhrase * 3 + inBar) pluck(n, t, BEAT * d * 1.9, .1);
      if (inBar === 0 && barInPhrase % 2 === 1 && Math.random() < .7) pluck([93, 88, 84][Math.floor(Math.random() * 3)], t + BEAT * .5, 2.4, .035); // далёкий колокольчик
      nextT += BEAT; beat++;
    }
  };
  return {
    start() {
      if (on || !S.music) return;
      ctx = audioCtx(); if (!ctx) return;
      if (!master) {
        master = ctx.createGain(); master.gain.value = 0; master.connect(ctx.destination);
        const d = ctx.createDelay(1.5); d.delayTime.value = BEAT * 1.5; const fb = ctx.createGain(); fb.gain.value = .38; const wet = ctx.createGain(); wet.gain.value = .5;
        const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 2600;
        echo = ctx.createGain(); echo.connect(d); d.connect(lp); lp.connect(fb); fb.connect(d); lp.connect(wet); wet.connect(master);
      }
      on = true; nextT = ctx.currentTime + .15; beat = 0;
      master.gain.cancelScheduledValues(ctx.currentTime); master.gain.linearRampToValueAtTime(.55, ctx.currentTime + 2);
      timer = setInterval(schedule, 150); schedule();
    },
    stop() {
      if (!on) return; on = false; clearInterval(timer);
      if (master && ctx) { master.gain.cancelScheduledValues(ctx.currentTime); master.gain.setTargetAtTime(0, ctx.currentTime, .15); }
    },
    get on() { return on; },
  };
})();
// Браузеры разрешают звук только после касания: запускаем музыку при первом действии на странице.
const unlockMusic = () => { if (S.music) Music.start(); };
document.addEventListener('pointerdown', unlockMusic, { once: true }); document.addEventListener('keydown', unlockMusic, { once: true });
document.addEventListener('visibilitychange', () => { if (!actx) return; if (document.hidden) actx.suspend(); else if (S.music || S.sound) actx.resume(); });
applyToggles();

/* ---------- Сеть ---------- */
async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, { method, credentials: 'same-origin', headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
  let data = {}; try { data = await res.json(); } catch {}
  if (!res.ok) { const e = new Error(data.error || `Ошибка ${res.status}`); e.status = res.status; throw e; }
  if (data && data.serverTime) syncTime(data.serverTime);
  if (data && data.task) syncTime(data.task.serverTime);
  return data;
}
function toast(html, kind = '') {
  const el = document.createElement('div'); el.className = `toast ${kind}`; el.innerHTML = html; $('#toasts').append(el); setTimeout(() => el.remove(), 6500);
}
const safe = (fn) => async (...a) => {
  try { return await fn(...a); } catch (e) {
    if (e.status === 401) { S.me = null; location.hash = '#/login'; return; }
    toast(esc(e.message), 'bad');
    if ((e.status === 409 || e.status === 423) && S.task && !$('#modal').hidden) reloadTask();
  }
};

/* ---------- Таймеры и очистка ---------- */
let cleanups = [];
const onCleanup = (fn) => cleanups.push(fn);
const runCleanups = () => { for (const f of cleanups.splice(0)) { try { f(); } catch {} } };
const timerHtml = () => '<div class="timer"><span class="t">…</span><span class="bar"><i style="width:100%"></i></span></div>';
function startTimer(root, endAt, startAt, onExpire) {
  const el = $('.timer', root); if (!el) return;
  const total = Math.max(1000, endAt - startAt); let fired = false;
  const tick = () => {
    const ms = endAt - now(), s = Math.max(0, ms);
    $('.t', el).textContent = `${Math.floor(s / 60000)}:${String(Math.floor(s / 1000) % 60).padStart(2, '0')}`;
    $('i', el).style.width = Math.min(100, (s / total) * 100) + '%';
    el.classList.toggle('low', s <= 5000);
    if (ms <= 0 && !fired) { fired = true; clearInterval(id); onExpire(); }
  };
  const id = setInterval(tick, 200); tick(); onCleanup(() => clearInterval(id));
}
const debounce = (fn, ms) => { let t; const d = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; d.flush = (...a) => { clearTimeout(t); return fn(...a); }; onCleanup(() => clearTimeout(t)); return d; };

/* ---------- Каркас и маршруты ---------- */
const brandHtml = (logo) => (logo ? `<img src="${logo}" alt="Миллор Фарма">` : '<span class="wordmark">Миллор Фарма<small> · <b>Лаборатория</b></small></span>');
const showChrome = (on) => { $('#topbar').hidden = !on; document.body.classList.toggle('with-nav', on); };
async function router() {
  closeModal(true);
  const [, route = '', arg] = location.hash.replace(/^#\/?/, '#/').split('/');
  if (route === '' || route === 'welcome') return viewWelcome();
  if (route === 'login') return viewLogin();
  try { if (!S.me) await refreshMe(); } catch (e) { if (e.status === 401) { location.hash = '#/login'; return; } throw e; }
  showChrome(true);
  $$('#nav a').forEach((a) => a.classList.toggle('active', a.dataset.route === route || (route === 'task' && a.dataset.route === 'board')));
  if (route === 'board') return viewBoard();
  if (route === 'task') { viewBoard(); return openTask(Number(arg)); }
  if (route === 'bingo') return viewBingo();
  if (route === 'hall') return viewHall();
  location.hash = '#/board';
}
window.addEventListener('hashchange', router);

/* ---------- Приветствие и вход ---------- */
const FLASKS = `<svg viewBox="0 0 60 96"><rect x="24" y="6" width="12" height="30" rx="2" fill="#9fb3b8" opacity=".35"/><path d="M24 34 8 84q0 8 8 8h28q8 0 8-8L36 34z" fill="#9fb3b8" opacity=".25"/><path d="M15 62 8 84q0 8 8 8h28q8 0 8-8l-7-22z" fill="#8a1830"/><circle class="bubble" cx="26" cy="80" r="3" fill="#ffb3bd"/><circle class="bubble" cx="34" cy="84" r="2" fill="#ffb3bd"/><circle class="bubble" cx="30" cy="76" r="2.5" fill="#ffb3bd"/></svg>
<svg viewBox="0 0 70 96"><path d="M28 4h14v28c14 6 24 20 24 34 0 16-14 28-31 28S4 82 4 66c0-14 10-28 24-34z" fill="#9fb3b8" opacity=".25"/><path d="M6 64c0 16 13 28 29 28s29-12 29-28z" fill="#d97a2b"/><circle class="bubble" cx="30" cy="80" r="3" fill="#ffe0b8"/><circle class="bubble" cx="42" cy="84" r="2" fill="#ffe0b8"/><circle class="bubble" cx="36" cy="74" r="2.5" fill="#ffe0b8"/></svg>
<svg viewBox="0 0 80 96"><g transform="translate(6 34)"><rect width="68" height="56" rx="3" fill="#f4ede6"/><rect width="68" height="12" fill="#6e1222"/><rect y="22" width="68" height="14" fill="#d97a2b" opacity=".9"/><text x="34" y="32" text-anchor="middle" font-size="8" font-weight="700" font-family="Arial" fill="#241003">ПЯТНИЦИН</text><rect x="6" y="42" width="10" height="10" fill="#6e1222"/></g></svg>
<svg viewBox="0 0 70 96"><g transform="translate(35 64)"><ellipse rx="30" ry="24" fill="#c9631b"/><ellipse rx="10" ry="23" fill="#d97a2b" transform="translate(-11 0)"/><ellipse rx="10" ry="23" fill="#d97a2b" transform="translate(11 0)"/><rect x="-3" y="-32" width="6" height="10" rx="2" fill="#4c6b2f"/><path d="M-16-6l6-7 6 7zM4-6l6-7 6 7zM-14 8q14 12 28 0l-5 5-5-3-4 3-5-3z" fill="#3a1606"/></g></svg>`;
async function viewWelcome() {
  showChrome(false);
  let info = null, loggedIn = false;
  try { info = await api('/api/public'); } catch {}
  try { await refreshMe(); loggedIn = true; } catch {}
  app.innerHTML = `<section class="hero"><div class="hero-inner">
    <div class="hero-logo">${info && info.logo ? `<img src="${info.logo}" alt="Миллор Фарма">` : ''}</div>
    <div class="lab-shelf" aria-hidden="true">${FLASKS}</div>
    <h1>МИЛЛОР ФАРМА</h1><div class="h2">HALLOWEEN BINGO</div>
    <div class="subtitle">Секретная лаборатория: спаси пятницу!</div>
    <div class="alert-box"><span class="siren">ВНИМАНИЕ! В ЛАБОРАТОРИИ ЧРЕЗВЫЧАЙНАЯ СИТУАЦИЯ!</span>
      <p class="hl">В секретной лаборатории Миллор Фарма произошёл мистический инцидент!</p>
      <p>Призраки похитили конфеты, ведьмы перепутали архивы, а офисные дедлайны превратились в настоящих монстров.</p>
      <p class="hl">Пятница под угрозой!</p>
      <p>Только сотрудники Миллор Фарма могут восстановить порядок.</p>
      <p>Проходи испытания, зарабатывай баллы, собирай БИНГО и стань легендой секретной лаборатории!</p></div>
    <a class="btn big" href="${loggedIn ? '#/board' : '#/login'}">${loggedIn ? 'Вернуться в лабораторию' : 'Начать спасение пятницы'}</a>
    <div class="foot">16 испытаний. 50 участников. Одна общая миссия.</div></div></section>`;
}
function viewLogin() {
  showChrome(false);
  app.innerHTML = `<section class="login"><div class="card"><h2>🔐 Вход в лабораторию</h2>
    <div class="seg" id="mode" role="tablist"><button type="button" data-m="new" class="on">Я здесь впервые</button><button type="button" data-m="old">Войти</button></div>
    <form id="f"><label class="field"><span>Имя и фамилия</span><input class="input" id="name" maxlength="60" autocomplete="username" required></label>
      <div class="field" id="fmt"><span class="muted small">Место работы</span><div class="chips" style="margin-top:6px"><button type="button" class="chip" data-format="office" aria-pressed="false">🏢 Офис</button><button type="button" class="chip" data-format="remote" aria-pressed="false">🏠 Удалённо</button></div></div>
      <label class="field"><span id="pin-l">Придумай PIN: 4 цифры</span><input class="input pin-input" id="pin" type="password" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" autocomplete="new-password" placeholder="••••" required></label>
      <label class="field" id="pin2f"><span>Повтори PIN</span><input class="input pin-input" id="pin2" type="password" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" autocomplete="off" placeholder="••••"></label>
      <p class="muted small" id="pin-note">Запомни PIN: по имени и PIN можно продолжить игру с любого устройства, а результаты сохранятся. Забудешь — обратись к организатору.</p>
      <div class="form-error" id="err" role="alert"></div><button class="btn big" style="width:100%" id="go">Войти в лабораторию</button></form></div>
    <p class="center"><a href="#/">← На главный экран</a></p></section>`;
  let format = null, mode = 'new';
  const setMode = (m) => {
    mode = m; $$('#mode button').forEach((b) => b.classList.toggle('on', b.dataset.m === m));
    $('#fmt').hidden = $('#pin2f').hidden = m === 'old'; $('#pin2').required = m === 'new';
    $('#pin-l').textContent = m === 'new' ? 'Придумай PIN: 4 цифры' : 'Твой PIN'; $('#pin').autocomplete = m === 'new' ? 'new-password' : 'current-password';
    $('#pin-note').hidden = m === 'old'; $('#err').textContent = '';
  };
  $$('#mode button').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.m)));
  $$('.chip').forEach((b) => b.addEventListener('click', () => { format = b.dataset.format; $$('.chip').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); }));
  $$('.pin-input').forEach((i) => i.addEventListener('input', () => (i.value = i.value.replace(/\D/g, '').slice(0, 4))));
  setMode('new'); $('#name').focus();
  $('#f').addEventListener('submit', async (e) => {
    e.preventDefault(); $('#err').textContent = '';
    const body = { name: $('#name').value, pin: $('#pin').value };
    if (!/^\d{4}$/.test(body.pin)) { $('#err').textContent = 'PIN — ровно 4 цифры'; return; }
    if (mode === 'new') {
      if (!format) { $('#err').textContent = 'Выберите: офис или удалённо'; return; }
      if ($('#pin2').value !== body.pin) { $('#err').textContent = 'PIN-коды не совпадают'; return; }
      body.format = format;
    }
    $('#go').disabled = true;
    try {
      await api(mode === 'new' ? '/api/register' : '/api/login', { method: 'POST', body });
      S.me = null; S.prevLines = null; S.prevStates = null; location.hash = '#/board';
    } catch (err) { $('#err').textContent = err.message; $('#go').disabled = false; }
  });
}

/* ---------- Данные игрока ---------- */
async function refreshMe() {
  const me = await api('/api/me');
  S.me = me;
  $('#brand').innerHTML = brandHtml(me.logo);
  if (S.prevLines) { const fresh = me.lines.filter((l) => l.complete && !S.prevLines.includes(l.idx)); if (fresh.length) celebrateBingo(fresh); }
  S.prevLines = me.lines.filter((l) => l.complete).map((l) => l.idx);
  if (!S.poll) S.poll = setInterval(async () => {
    if (document.hidden || !S.me) return;
    try { await refreshMe(); if (location.hash.startsWith('#/board') && $('#modal').hidden) renderBoard(); if (location.hash.startsWith('#/hall')) viewHall(true); if (location.hash.startsWith('#/bingo')) viewBingo(); } catch (e) { if (e.status === 401) { clearInterval(S.poll); S.poll = null; S.me = null; location.hash = '#/login'; } }
  }, 15000);
  maybeFinale();
  return me;
}

/* ---------- Правила ---------- */
function openRules(first) {
  showModal(`<div class="rules-grid"><div class="rules-text"><h2>КАК ИГРАТЬ В HALLOWEEN BINGO?</h2>
    <p>Перед тобой поле из 16 заданий. Выбирай любую клетку, проходи испытания и зарабатывай баллы.</p>
    <h3>1. Выполняй задания</h3><p>За каждое можно заработать до 10 баллов. Некоторые задания состоят из нескольких этапов, поэтому даже частичное выполнение может принести баллы.</p>
    <h3>2. Следи за попытками</h3><p>Для автоматических игр предусмотрены две попытки. Первая попытка — максимум 10 баллов. Вторая попытка — штраф 2 балла от заработанного результата. Сохраняется лучший результат.</p>
    <p>Для творческих заданий предусмотрена одна отправка на проверку организатору.</p>
    <h3>3. Собирай БИНГО</h3><p>Самое интересное — дополнительные баллы за линии! Если четыре клетки подряд по горизонтали, вертикали или диагонали получили минимум по 8 баллов каждая, ты собираешь БИНГО. За каждую такую линию получаешь <b class="gold">+30 баллов</b>! Можно собрать несколько линий одновременно.</p>
    <h3>4. Следи за рейтингом</h3><p>Все подтверждённые баллы автоматически попадают в общий рейтинг.</p>
    <h3>5. Успей до 17:00 МСК</h3><p>После этого новые задания и попытки будут закрыты.</p>
    <p><b>Желаем удачи! Да пребудет с тобой сила пятницы!</b></p></div>
    <div><div class="demo-grid" id="demo">${Array.from({ length: 16 }, () => '<div class="dc"></div>').join('')}</div><div class="demo-msg" id="demo-msg"></div>
    <p class="muted small center">Линия считается, только если в каждой из четырёх клеток не меньше 8 баллов.</p></div></div>
    <div class="actions"><button class="btn big" id="rules-ok">Понятно, начать игру</button></div>`, { onClose: () => { stopDemo && stopDemo(); } });
  stopDemo = bingoDemo($('#demo'), $('#demo-msg'));
  $('#rules-ok').addEventListener('click', async () => { closeModal(); if (first) api('/api/me/rules-seen', { method: 'POST', body: {} }).catch(() => {}); });
}
let stopDemo = null;
function bingoDemo(grid, msg) {
  const cells = $$('.dc', grid); let timers = [], dead = false;
  const at = (ms, fn) => timers.push(setTimeout(() => !dead && fn(), ms));
  const reset = () => { cells.forEach((c) => { c.className = 'dc'; c.textContent = ''; }); msg.textContent = ''; msg.className = 'demo-msg'; };
  const row = (r, vals, cls) => vals.forEach((v, i) => { const c = cells[r * 4 + i]; c.textContent = v; c.className = 'dc ' + (v >= 8 ? 'g' : 'bad') + (cls || ''); });
  if (!S.anim) { // без анимации — оба примера сразу
    row(0, [10, 8, 9, 10], ' line'); row(2, [10, 7, 10, 10]); msg.innerHTML = 'БИНГО! +30 баллов — верхняя линия.<br>Нижняя линия не считается: 7 меньше 8.'; msg.className = 'demo-msg win';
    return () => { dead = true; };
  }
  const play = () => {
    reset();
    [10, 8, 9, 10].forEach((v, i) => at(500 + i * 600, () => { cells[i].textContent = v; cells[i].className = 'dc g'; }));
    at(3300, () => { for (let i = 0; i < 4; i++) cells[i].classList.add('line'); msg.textContent = 'БИНГО! +30 баллов'; msg.className = 'demo-msg win'; beep([[523, .12], [659, .12], [784, .2]]); });
    at(6300, () => { reset(); });
    [10, 7, 10, 10].forEach((v, i) => at(6800 + i * 600, () => { cells[i].textContent = v; cells[i].className = 'dc ' + (v >= 8 ? 'g' : 'bad'); }));
    at(9600, () => { msg.textContent = 'Не засчитывается: в одной клетке меньше 8 баллов'; msg.className = 'demo-msg no'; });
    at(12800, play);
  };
  play();
  return () => { dead = true; timers.forEach(clearTimeout); };
}
$('#btn-how').addEventListener('click', () => openRules(false));

/* ---------- Игровое поле ---------- */
const PHASE_TEXT = { before: 'Лаборатория откроется', paused: 'Организатор поставил приём новых попыток на паузу. Прогресс сохранён.', ended: 'Игра завершена. Новые попытки не принимаются; присланные работы проверяются.' };
function viewBoard() { app.innerHTML = '<div class="wrap page"><div id="board-root"></div></div>'; renderBoard(); if (S.me && !S.me.player.rulesSeen) { S.me.player.rulesSeen = true; openRules(true); } }
function renderBoard() {
  const root = $('#board-root'); if (!root || !S.me) return;
  const me = S.me, g = me.game;
  const inLine = new Set(me.lines.filter((l) => l.complete).flatMap((l) => l.tasks));
  const locked = g.phase === 'before' && !me.player.isTest;
  const banners = [];
  if (me.player.isTest) banners.push('<div class="banner test">🧪 <div class="grow"><b>Тестовый профиль.</b> Не попадает в настоящий рейтинг и играет вне расписания.</div></div>');
  if (g.phase === 'before') banners.push(`<div class="banner warn">⏳ <div class="grow">Лаборатория откроется <b>${esc(MSK(g.start, { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' }))}</b> (МСК). До начала: <span class="countdown" data-to="${esc(g.start)}"></span></div></div>`);
  else if (g.phase === 'running') banners.push(`<div class="banner">🕰 <div class="grow">Лаборатория открыта до <b>${esc(MSK(g.end, { hour: '2-digit', minute: '2-digit' }))}</b> по Москве. Осталось: <span class="countdown" data-to="${esc(g.end)}"></span></div></div>`);
  else banners.push(`<div class="banner warn">⏸ <div class="grow">${esc(PHASE_TEXT[g.phase])}</div></div>`);
  if (me.final) banners.push('<div class="banner test">🏁 <div class="grow"><b>Итоги подведены.</b> <a href="#/hall">Смотреть Зал славы</a></div></div>');
  const next = me.nextBingo;
  root.innerHTML = `<p class="welcome-line">Добро пожаловать в лабораторию, ${esc(me.player.name)}!</p>
    <div class="hud"><div class="card"><div class="label">Мои баллы</div><div class="value gold">${me.total}</div></div><div class="card"><div class="label">Собрано БИНГО</div><div class="value">${me.bingos}<span class="muted small">/10</span></div></div><div class="card"><div class="label">Выполнено заданий</div><div class="value">${me.tasksDone}<span class="muted small">/16</span></div></div></div>
    ${banners.join('')}
    <div class="board" role="grid" aria-label="Игровое поле 4 на 4">${me.cells.map((c) => `
      <button class="cell s-${c.state} ${inLine.has(c.id) ? 'in-line' : ''} ${locked ? 'locked' : ''}" data-id="${c.id}" role="gridcell" aria-label="Задание ${c.id}: ${esc(c.title)}. ${esc(c.label)}">
        <span class="num">№ ${c.id}</span><span class="emoji">${c.emoji}</span><span class="title">${esc(c.title)}</span>
        <span class="meta"><span class="pill">${esc(c.label)}</span><span class="pts">до 10 баллов</span></span></button>`).join('')}</div>
    <div class="next-bingo">${next === null ? '🎉 Все линии БИНГО собраны!' : next === 0 ? '' : `🎯 До следующего БИНГО осталось закрыть ${next} ${plural(next, 'клетку', 'клетки', 'клеток')}`}</div>
    <div class="line-chips">${me.lines.map((l) => `<span class="line-chip ${l.complete ? 'done' : ''}" title="${l.tasks.join(', ')}">${l.name}: ${l.have}/4</span>`).join('')}</div>
    <p class="muted small">Место в рейтинге: <b>${me.rank ?? '—'}</b> из ${me.totalPlayers}. БИНГО-бонус сейчас: ${me.bonus} баллов.</p>`;
  $$('.cell', root).forEach((b) => b.addEventListener('click', () => { if (locked) return toast('Лаборатория ещё закрыта — задания откроются в начале игры.'); location.hash = `#/task/${b.dataset.id}`; }));
  // мягкая зелёная вспышка при переходе клетки в «зелёную»
  const states = Object.fromEntries(me.cells.map((c) => [c.id, c.state]));
  if (S.prevStates && S.anim) for (const c of me.cells) if (c.state === 'good' && S.prevStates[c.id] !== 'good') { const el = $(`.cell[data-id="${c.id}"]`, root); el.classList.add('glow'); beep([[600, .1], [800, .15]]); }
  S.prevStates = states;
  tickCountdowns();
}
let cdTimer;
function tickCountdowns() {
  clearInterval(cdTimer);
  const upd = () => {
    const els = $$('.countdown'); if (!els.length) return clearInterval(cdTimer);
    for (const el of els) {
      let ms = Date.parse(el.dataset.to) - now();
      if (ms <= 0) { el.textContent = '00:00:00'; if (!el.dataset.f) { el.dataset.f = 1; setTimeout(() => refreshMe().then(renderBoard).catch(() => {}), 1500); } continue; }
      const d = Math.floor(ms / 864e5); ms -= d * 864e5;
      el.textContent = `${d ? d + ' д ' : ''}${String(Math.floor(ms / 36e5)).padStart(2, '0')}:${String(Math.floor((ms % 36e5) / 6e4)).padStart(2, '0')}:${String(Math.floor((ms % 6e4) / 1e3)).padStart(2, '0')}`;
    }
  };
  upd(); cdTimer = setInterval(upd, 1000);
}

/* ---------- БИНГО: золотые искры ---------- */
function celebrateBingo(lines) {
  const el = $('#bingo'), n = lines.length;
  el.innerHTML = `<div class="bingo-card"><h2>БИНГО!</h2><p>+30 баллов${n > 1 ? ` × ${n}` : ''}</p><p class="muted small">${lines.map((l) => l.name).join(' · ')}</p><p class="muted small">Нажми, чтобы продолжить</p></div>` +
    (S.anim ? Array.from({ length: 46 }, () => `<span class="spark" style="left:${Math.random() * 100}%;font-size:${14 + Math.random() * 22}px;animation-duration:${2.2 + Math.random() * 2.6}s;animation-delay:${Math.random() * 1.2}s">${['✦', '✧', '★', '✨'][Math.floor(Math.random() * 4)]}</span>`).join('') : '');
  el.hidden = false; beep([[523, .12], [659, .12], [784, .12], [1047, .3]]);
  const close = () => { el.hidden = true; const ids = new Set(lines.flatMap((l) => l.tasks)); $$('.cell').forEach((c) => { if (ids.has(Number(c.dataset.id)) && S.anim) c.classList.add('glow'); }); };
  el.onclick = close; setTimeout(() => { if (!el.hidden) close(); }, 6000);
}

/* ---------- Мои БИНГО ---------- */
function viewBingo() {
  const me = S.me, byId = Object.fromEntries(me.cells.map((c) => [c.id, c]));
  app.innerHTML = `<div class="wrap page"><h1>🎯 Мои БИНГО</h1><p class="muted">Собрано линий: <b class="gold">${me.bingos}</b> из 10. Линия засчитывается, когда в каждой из четырёх клеток не меньше 8 баллов: бонус +30.</p>
    ${me.lines.map((l) => `<div class="card line-card ${l.complete ? 'done' : ''}"><div><b>${l.name}</b> ${l.complete ? '<span class="pill s-good" style="background:rgba(240,184,74,.2);color:#f0b84a">БИНГО +30</span>' : `<span class="muted small">осталось клеток: ${l.need}</span>`}</div>
      <div class="line-cells">${l.cells.map((c) => `<div class="lc ${c.points != null && c.points >= 8 ? 'ok' : ''}"><span class="e">${byId[c.id].emoji}</span><span class="small">№ ${c.id}</span><b>${c.points == null ? '—' : c.points + '/10'}</b></div>`).join('')}</div></div>`).join('')}</div>`;
}

/* ---------- Зал славы ---------- */
async function viewHall(silent) {
  let d; try { d = await api('/api/leaderboard'); } catch (e) { if (!silent) app.innerHTML = `<div class="wrap page empty">${esc(e.message)}</div>`; return; }
  if (silent && !location.hash.startsWith('#/hall')) return;
  const medal = ['🥇', '🥈', '🥉'], top = d.rows.slice(0, 3);
  const status = d.final ? '<div class="banner test">🏁 Итоговый рейтинг. Игра окончена.</div>' : `<div class="banner warn">⏳ <div class="grow">${d.pending ? 'Рейтинг предварительный — некоторые работы ожидают проверки' : d.phase === 'ended' ? 'Рейтинг предварительный — организатор подводит итоги' : 'Рейтинг предварительный — игра продолжается'}</div></div>`;
  app.innerHTML = `<div class="wrap page"><h1>🏆 Зал славы Миллор Фарма</h1>${status}
    ${d.final ? '<p><button class="btn sm" id="show-fin">Показать праздничный экран</button></p>' : ''}
    ${top.length && top[0].total > 0 ? `<div class="podium">${[1, 0, 2].filter((i) => top[i]).map((i) => `<div class="pl p${i + 1}"><div class="medal">${medal[i]}</div><div class="nm">${esc(top[i].name)}</div><div class="sc">${top[i].total}</div><div class="muted small">${top[i].bingos} БИНГО · ${top[i].closed} заданий</div></div>`).join('')}</div>` : ''}
    ${d.rows.length ? `<div class="card" style="padding:8px 12px;overflow-x:auto"><table class="rating"><thead><tr><th>Место</th><th>Участник</th><th class="n hide-sm">Выполнено</th><th class="n">БИНГО</th><th class="n">Баллы</th></tr></thead><tbody>
      ${d.rows.map((r) => `<tr class="${r.rank <= 3 && r.total > 0 ? 'top' : ''} ${r.me ? 'me' : ''}"><td>${r.rank <= 3 && r.total > 0 ? medal[r.rank - 1] : r.rank}</td><td>${esc(r.name)} ${r.me ? '<span class="pill">это вы</span>' : ''} <span title="${r.format === 'office' ? 'Офис' : 'Удалённо'}">${r.format === 'office' ? '🏢' : '🏠'}</span></td><td class="n hide-sm">${r.closed}</td><td class="n">${r.bingos}</td><td class="n score">${r.total}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Пока никто не вошёл в лабораторию.</div>'}
    <p class="muted small">Одинаковые баллы: выше тот, у кого больше БИНГО, затем больше заданий на 10 баллов, затем меньше использованных попыток. Скорость прохождения на место не влияет.</p></div>`;
  const b = $('#show-fin'); if (b) b.addEventListener('click', () => showFinale(true));
}
function maybeFinale() { const f = S.me && S.me.final; if (f && store.get('mp-fin-' + f.at) !== '1') showFinale(false); }
function showFinale(force) {
  const f = S.me.final; if (!f) return;
  store.set('mp-fin-' + f.at, '1');
  const el = $('#bingo'); const medal = ['🥇', '🥈', '🥉'];
  el.innerHTML = `<div class="bingo-card finale"><h2>ЛАБОРАТОРИЯ СПАСЕНА!</h2><p>Благодаря сотрудникам Миллор Фарма нечисть побеждена, конфеты найдены, созвоны закончены, а пятница спасена!</p>
    <div class="podium" style="margin-top:20px">${[1, 0, 2].filter((i) => f.top3[i]).map((i) => `<div class="pl p${i + 1}"><div class="medal">${medal[i]}</div><div class="nm">${esc(f.top3[i].name)}</div><div class="sc">${f.top3[i].total} баллов</div></div>`).join('')}</div>
    <p class="muted small">Твой результат: место ${f.myRank ?? '—'}, ${f.myTotal} баллов. Нажми, чтобы закрыть.</p></div>` + (S.anim ? Array.from({ length: 40 }, () => `<span class="spark" style="left:${Math.random() * 100}%;font-size:${14 + Math.random() * 22}px;animation-duration:${2.5 + Math.random() * 2.5}s;animation-delay:${Math.random() * 1.5}s">${['✦', '✧', '🎃', '👻'][Math.floor(Math.random() * 4)]}</span>`).join('') : '');
  el.hidden = false; el.onclick = () => { el.hidden = true; };
}

/* ---------- Модальное окно ---------- */
let modalOnClose = null;
function showModal(html, { onClose } = {}) { $('#modal-body').innerHTML = html; $('#modal').hidden = false; document.body.style.overflow = 'hidden'; modalOnClose = onClose || null; $('#modal').scrollTop = 0; }
function closeModal(silent) {
  if ($('#modal').hidden) return;
  runCleanups(); if (modalOnClose) { modalOnClose(); modalOnClose = null; }
  $('#modal').hidden = true; $('#modal-body').innerHTML = ''; document.body.style.overflow = ''; S.task = null;
  if (!silent) { if (location.hash.startsWith('#/task/')) history.replaceState(null, '', '#/board'); if (S.me) refreshMe().then(() => { if ($('#board-root')) renderBoard(); }).catch(() => {}); }
}
$('#modal-close').addEventListener('click', () => closeModal());
$('#modal').addEventListener('click', (e) => { if (e.target.id === 'modal' && !S.task) closeModal(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#modal').hidden) closeModal(); });

/* ---------- Задание: каркас ---------- */
const STATUS_LABEL = { new: 'Не начато', active: 'В процессе', decide: 'Можно улучшить', closed: 'Закрыто', pending: 'На проверке', returned: 'Нужна доработка', approved: 'Подтверждено', rejected: 'Отклонено' };
async function openTask(id) {
  let t; try { t = await api(`/api/tasks/${id}`); } catch (e) { toast(esc(e.message), 'bad'); history.replaceState(null, '', '#/board'); return; }
  showModal('', { onClose: () => { S.task = null; } }); renderTask(t);
}
async function reloadTask() { if (!S.task) return; renderTask(await api(`/api/tasks/${S.task.meta.id}`)); }
function renderTask(t, result) {
  runCleanups(); S.task = t; syncTime(t.serverTime);
  const m = t.meta;
  const info = `<p class="story">${esc(m.story)}</p><ul class="rules">${m.rules.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>`;
  $('#modal-body').innerHTML = `<div class="task-head"><div class="emoji">${m.emoji}</div><h2>${esc(m.title)}</h2></div>
    <div class="task-tags"><span class="pill">№ ${m.id}</span><span class="pill">${m.type === 'auto' ? '⚡ Автоматическая проверка' : '🎨 Проверяет организатор'}</span>
    <span class="pill" style="color:var(--gold)">${t.points != null ? `${t.points} из 10 баллов` : 'до 10 баллов'}${t.adjusted ? ' (скорр.)' : ''}</span>
    ${t.attempts && !t.attempts.closed ? `<span class="pill">Попыток осталось: ${t.attempts.left} из 2</span>` : ''}</div>
    ${t.active ? `<details class="fold"><summary>Сюжет и правила задания</summary>${info}</details>` : info}<div id="task-ui"></div>`;
  const ui = $('#task-ui');
  if (m.type === 'creative') return creativeView(ui, t);
  if (t.active) return runGame(ui, t);
  if (t.attempts.closed) return finishedView(ui, t, result);
  if (t.attempts.decide) return decideView(ui, t, result);
  introView(ui, t);
}
function unavailableReason(t) {
  if (t.frozen) return 'Итоги подведены.';
  if (t.phase === 'paused') return 'Организатор поставил приём новых попыток на паузу.';
  if (t.phase === 'ended') return 'Игра завершена: новые попытки не принимаются.';
  if (t.phase === 'before') return 'Игра ещё не началась.';
  return '';
}
function resultCard(last) {
  if (!last) return '';
  return `<div class="card" style="box-shadow:none;margin-top:12px"><div class="muted small">Результат попытки ${last.n}</div><div class="score-big">${last.final}<span class="muted" style="font-size:1rem"> из 10</span></div>
    <table class="parts"><tbody>${last.parts.map((p) => `<tr class="${p.penalty ? 'pen' : ''}"><td>${esc(p.label)}</td><td>${p.max ? `${p.got} / ${p.max}` : p.got < 0 ? p.got : ''}</td></tr>`).join('')}</tbody></table>
    ${last.n === 1 ? '' : '<p class="muted small">Итог вычисляется так: лучший из первой попытки и второй попытки минус 2. Результаты не суммируются.</p>'}</div>`;
}
const doorHtml = (icon) => `<div class="door-wrap"><div class="door"><div class="inside">${icon}</div><div class="leaf">🚪</div></div></div>`;
function introView(ui, t) {
  const why = t.canStart ? '' : unavailableReason(t);
  ui.innerHTML = `<p class="muted small">Открытие окна попытку не тратит. Попытка начинается после нажатия кнопки${t.meta.sec ? ': тогда же запустится серверный таймер, который нельзя сбросить обновлением страницы' : ''}.</p>
    ${why ? `<div class="result info">${esc(why)}</div>` : ''}
    <div class="actions"><button class="btn big" id="go" ${t.canStart ? '' : 'disabled'}>Начать попытку</button>${t.meta.kind === 'conveyor' ? '<button class="btn ghost" id="train">Потренироваться (без баллов)</button>' : ''}</div><div id="train-zone"></div>`;
  $('#go', ui).addEventListener('click', safe(async () => { $('#go', ui).disabled = true; const r = await api(`/api/tasks/${t.meta.id}/start`, { method: 'POST', body: {} }); renderTask(r.task); refreshMe(); }));
  const tr = $('#train', ui); if (tr) tr.addEventListener('click', () => conveyorTraining($('#train-zone', ui)));
}
function decideView(ui, t, result) {
  const why = t.canStart ? '' : unavailableReason(t);
  ui.innerHTML = `<div class="result info">Сейчас у тебя ${t.points} из 10. Можно оставить результат или использовать вторую (последнюю) попытку: из неё будет вычтено 2 балла, а сохранится лучший результат.</div>${resultCard(t.last)}
    ${why ? `<div class="result bad">${esc(why)}</div>` : ''}
    <div class="actions"><button class="btn green" id="keep">Оставить результат</button><button class="btn ghost" id="retry" ${t.canStart ? '' : 'disabled'}>Попробовать ещё раз — штраф 2 балла</button></div>`;
  $('#keep', ui).addEventListener('click', safe(async () => { const r = await api(`/api/tasks/${t.meta.id}/keep`, { method: 'POST', body: {} }); renderTask(r.task); refreshMe(); }));
  $('#retry', ui).addEventListener('click', safe(async () => { $('#retry', ui).disabled = true; const r = await api(`/api/tasks/${t.meta.id}/start`, { method: 'POST', body: {} }); renderTask(r.task); refreshMe(); }));
}
function finishedView(ui, t) {
  const last = t.last, k = t.meta.kind;
  ui.innerHTML = `<div class="result ok">✅ Задание закрыто. Твой результат: <b>${t.points} из 10</b>${t.points >= 8 ? ' — клетка учитывается в БИНГО' : ' — для БИНГО нужно минимум 8'}.</div>
    ${last && last.raw === 10 && k === 'warehouse' ? doorHtml('📦') : ''}${last && last.raw === 10 && k === 'sudoku' ? doorHtml('👨‍⚕️') : ''}
    ${resultCard(last)}<p class="muted small">Правильные решения не показываются.</p><div class="actions"><button class="btn" id="back">К полю</button></div>`;
  $('#back', ui).addEventListener('click', () => closeModal());
  if (last && last.final >= 8) beep([[600, .1], [800, .18]]);
}

/* ---------- Запуск активной попытки ---------- */
async function actCall(t, payload) { return api(`/api/tasks/${t.meta.id}/act`, { method: 'POST', body: payload }); }
function applyAct(r) { renderTask(r.task, r.result); if (r.result) refreshMe(); }
function runGame(ui, t) {
  const A = t.active;
  const sec = t.meta.kind === 'sudoku' ? '' : timerHtml();
  ui.innerHTML = `<div class="round-head">Попытка ${A.n} из 2${A.n === 2 ? ' · штраф −2' : ''}</div>${['films', 'quiz'].includes(t.meta.kind) ? '' : sec}<div id="game"></div><div id="game-msg"></div>`;
  if (!['films', 'quiz', 'sudoku'].includes(t.meta.kind) && A.deadlineAt) startTimer(ui, A.deadlineAt, A.startedAt, safe(async () => { applyAct(await actCall(t, { action: 'sync' })); }));
  GAMES[t.meta.kind]($('#game', ui), t, A);
}
const gmsg = (kind, html) => { const el = $('#game-msg'); if (el) el.innerHTML = html ? `<div class="result ${kind}">${html}</div>` : ''; };
const sendSave = (t, payload) => actCall(t, { action: 'save', ...payload }).catch(() => {});

const GAMES = {};
function roundGame(root, t, A, build) {
  const v = A.view; let busy = false;
  const timer = timerHtml();
  root.innerHTML = `<div class="round-head">Раунд ${v.round + 1} из ${v.total}</div>${timer}<div id="rb"></div>`;
  startTimer(root, v.roundEndsAt, v.roundEndsAt - v.sec * 1000, safe(async () => { if (busy) return; busy = true; applyAct(await actCall(t, { action: 'timeout', round: v.round })); }));
  const send = safe(async (answer) => { if (busy) return; busy = true; applyAct(await actCall(t, { action: 'answer', round: v.round, answer })); });
  build($('#rb', root), v.question, send);
}
GAMES.films = (root, t, A) => roundGame(root, t, A, (box, q, send) => {
  let sel = [];
  box.innerHTML = `<div class="film-title">${esc(q.title)}</div><div class="muted small">Составь афишу из эмодзи: выбери до ${q.maxPick}.</div><div class="picked" id="picked"></div>
    <div class="emoji-grid">${q.palette.map((e) => `<button class="emo" data-e="${e}" aria-pressed="false">${e}</button>`).join('')}</div><div class="actions"><button class="btn" id="ok">Готово</button></div>`;
  const show = () => { $('#picked', box).innerHTML = sel.length ? sel.join(' ') : '<span class="muted small">Ничего не выбрано</span>'; $$('.emo', box).forEach((b) => b.setAttribute('aria-pressed', String(sel.includes(b.dataset.e)))); };
  $$('.emo', box).forEach((b) => b.addEventListener('click', () => { const e = b.dataset.e; if (sel.includes(e)) sel = sel.filter((x) => x !== e); else if (sel.length < q.maxPick) sel.push(e); else toast(`Можно выбрать не больше ${q.maxPick}`); show(); }));
  $('#ok', box).addEventListener('click', () => send(sel)); show();
});
GAMES.quiz = (root, t, A) => roundGame(root, t, A, (box, q, send) => {
  box.innerHTML = `<h3 style="font-size:1.25rem">${esc(q.text)}</h3><div class="opts">${q.options.map((o, i) => `<button class="opt" data-i="${i}">${esc(o)}</button>`).join('')}</div>`;
  $$('.opt', box).forEach((b) => b.addEventListener('click', () => { $$('.opt', box).forEach((x) => (x.disabled = true)); send(Number(b.dataset.i)); }));
});
GAMES.cipher = (root, t, A) => {
  const v = A.view; let hint = v.hint;
  root.innerHTML = `<div class="code-display">${esc(v.code)}</div><p class="muted small whisper">🕯 ${esc(v.whisper)}</p>
    <label class="field"><span>Название препарата</span><input class="input" id="nm" maxlength="40" autocomplete="off" value="${esc(v.fields.name)}"></label>
    <div id="hint">${hint ? `<div class="hint-box">💡 ${esc(hint)}</div>` : ''}</div>
    <div class="actions"><button class="btn ghost" id="hb" ${hint ? 'hidden' : ''}>Получить подсказку (−5 баллов)</button><button class="btn" id="ok">Отправить</button></div><div id="hc"></div>`;
  const save = debounce(() => sendSave(t, { name: $('#nm', root).value }), 400);
  $('#nm', root).addEventListener('input', save);
  $('#hb', root).addEventListener('click', () => { $('#hc', root).innerHTML = '<div class="result info">Подсказка снизит результат на 5 баллов, штраф сохранится и на второй попытке. Взять подсказку? <div class="actions"><button class="btn sm red" id="hy">Да, взять</button><button class="btn sm ghost" id="hn">Нет</button></div></div>';
    $('#hn', root).addEventListener('click', () => ($('#hc', root).innerHTML = ''));
    $('#hy', root).addEventListener('click', safe(async () => { const r = await actCall(t, { action: 'hint' }); $('#hc', root).innerHTML = ''; $('#hint', root).innerHTML = `<div class="hint-box">💡 ${esc(r.task.active.view.hint)}</div>`; $('#hb', root).hidden = true; }));
  });
  $('#ok', root).addEventListener('click', safe(async () => { $('#ok', root).disabled = true; applyAct(await actCall(t, { action: 'finish', data: { name: $('#nm', root).value } })); }));
};
GAMES.ghosts = (root, t, A) => {
  const v = A.view; let zoom = 1, busy = false, wrong = v.wrong, found = v.found.length;
  root.innerHTML = `<div class="scene-tools"><span class="stat gold" id="fc">Найдено: ${found}/${v.total}</span><span class="stat" id="wc">Ошибки: ${wrong}/${v.maxWrong}</span><span style="flex:1"></span><button class="btn sm ghost" id="zo" aria-label="Уменьшить">−</button><button class="btn sm ghost" id="zi" aria-label="Увеличить">+</button></div>
    <div class="scene-scroll"><div class="scene" id="scene" style="width:100%"><img src="/api/scene.svg" alt="Ночная лаборатория Миллор Фарма" draggable="false"></div></div><p class="muted small">Нажимай на привидений прямо на картинке. Увеличивай кнопкой «+», изображение можно прокручивать.</p>`;
  const scene = $('#scene', root);
  const mark = (x, y, cls) => { const m = document.createElement('span'); m.className = cls; m.style.left = x / 8 + '%'; m.style.top = y / 5 + '%'; scene.append(m); if (cls === 'miss') setTimeout(() => m.remove(), 700); };
  v.found.forEach((p) => mark(p.x, p.y, 'mark'));
  const setZoom = (z) => { zoom = Math.max(1, Math.min(3, z)); scene.style.width = zoom * 100 + '%'; };
  $('#zi', root).addEventListener('click', () => setZoom(zoom + .5)); $('#zo', root).addEventListener('click', () => setZoom(zoom - .5));
  scene.addEventListener('click', safe(async (e) => {
    if (busy) return; busy = true;
    try {
      const r = scene.getBoundingClientRect(), x = ((e.clientX - r.left) / r.width) * 800, y = ((e.clientY - r.top) / r.height) * 500;
      const res = await actCall(t, { action: 'click', x, y });
      if (res.result) { applyAct(res); return; }
      const nv = res.task.active.view;
      if (nv.found.length > found) { $$('.mark', scene).forEach((m) => m.remove()); nv.found.forEach((p) => mark(p.x, p.y, 'mark')); beep([[700, .1]]); } else if (nv.wrong > wrong) mark(x, y, 'miss');
      found = nv.found.length; wrong = nv.wrong; $('#fc', root).textContent = `Найдено: ${found}/${nv.total}`; $('#wc', root).textContent = `Ошибки: ${wrong}/${nv.maxWrong}`;
    } finally { busy = false; }
  }));
};

/* Расстановка по слотам: нажми карточку, затем слот; или перетащи мышью. Занятый слот меняется местами. */
function slotArranger(root, { getOrder, setOrder, onChange, redraw }) {
  let sel = null;
  const place = (id, i) => {
    const order = [...getOrder()], from = order.indexOf(id), occupant = order[i];
    if (from === i) return;
    if (from >= 0) order[from] = occupant || null; // место-источник получает прежнего жильца (обмен) или освобождается
    order[i] = id; setOrder(order); sel = null; onChange(); redraw();
  };
  const unplace = (id) => { setOrder(getOrder().map((x) => (x === id ? null : x))); sel = null; onChange(); redraw(); };
  return {
    get sel() { return sel; },
    bind() {
      $$('[data-card]', root).forEach((c) => {
        const id = c.dataset.card;
        c.setAttribute('draggable', 'true');
        c.addEventListener('dragstart', (e) => { e.dataTransfer.setData('text/plain', id); e.dataTransfer.effectAllowed = 'move'; });
        c.addEventListener('click', (e) => { if (e.target.closest('[data-stop]')) return; e.stopPropagation(); const slot = c.closest('[data-slot]');
          if (sel && slot && sel !== id) return place(sel, Number(slot.dataset.slot)); // нажали на занятый слот при выбранной карточке — ставим/меняем
          sel = sel === id ? null : id; redraw(); });
      });
      $$('[data-slot]', root).forEach((s) => {
        const i = Number(s.dataset.slot);
        s.addEventListener('click', () => { if (sel) place(sel, i); });
        s.addEventListener('dragover', (e) => { e.preventDefault(); s.classList.add('target'); }); s.addEventListener('dragleave', () => s.classList.remove('target'));
        s.addEventListener('drop', (e) => { e.preventDefault(); const id = e.dataTransfer.getData('text/plain'); if (id) place(id, i); });
      });
      const pool = $('[data-pool]', root);
      if (pool) { pool.addEventListener('dragover', (e) => e.preventDefault()); pool.addEventListener('drop', (e) => { e.preventDefault(); const id = e.dataTransfer.getData('text/plain'); if (id) unplace(id); }); pool.addEventListener('click', () => { if (sel && getOrder().includes(sel)) unplace(sel); }); }
    },
  };
}
GAMES.detective = (root, t, A) => {
  const v = A.view; let order = [...v.order], culprit = v.culprit;
  const byId = Object.fromEntries(v.suspects.map((s) => [s.id, s]));
  const save = debounce(() => sendSave(t, { order, culprit }), 300);
  let warn = null;
  const arr = slotArranger(root, { getOrder: () => order, setOrder: (o) => (order = o), onChange: () => { warn = null; save(); }, redraw: () => draw() });
  const card = (s) => `<div class="char ${arr.sel === s.id ? 'selected' : ''}" data-card="${s.id}"><span class="f">${s.emoji}</span>${esc(s.name)}</div>`;
  const draw = () => {
    const pool = v.suspects.filter((s) => !order.includes(s.id));
    const placed = order.filter(Boolean).length;
    root.innerHTML = `<div class="step"><span class="step-n">Шаг 1</span> Расставь персонажей по времени визита</div>
      <p class="muted small">Нажми персонажа, затем время. Можно перетаскивать; нажми на занятое время, чтобы поменять местами. Расставлено: ${placed} из 4.</p>
      <div class="timeline">${v.slots.map((tm, i) => `<div class="slot ${arr.sel ? 'target' : ''}" data-slot="${i}"><span class="time">${tm}</span>${order[i] ? card(byId[order[i]]) : '<span class="muted small">пусто</span>'}</div>`).join('')}</div>
      <div data-pool style="margin-top:10px"><div class="chars">${pool.map(card).join('') || '<span class="muted small">Все на местах. Чтобы убрать персонажа, выбери его и нажми сюда.</span>'}</div></div>
      <h3 style="margin-top:14px">Улики</h3>${v.clues.map((c, i) => `<div class="clue-card"><b>${i + 1}.</b> ${esc(c)}</div>`).join('')}
      <div class="step thief ${culprit ? 'set' : ''}"><span class="step-n">Шаг 2</span> 🔪 Кто украл конфеты? Выбери вора</div>
      <div class="thief-grid">${v.suspects.map((s) => `<button type="button" class="thief-btn ${culprit === s.id ? 'on' : ''}" data-t="${s.id}" aria-pressed="${culprit === s.id}"><span class="f">${s.emoji}</span><span>${esc(s.name)}</span></button>`).join('')}</div>
      <div class="thief-status ${culprit ? 'ok' : 'no'}">${culprit ? `Вор: ${byId[culprit].emoji} ${esc(byId[culprit].name)}` : '⚠ Вор не выбран: это 6 баллов из 10'}</div>
      ${warn ? `<div class="result bad">${warn}<div class="actions"><button class="btn sm red" id="force">Всё равно отправить</button><button class="btn sm ghost" id="back">Вернуться</button></div></div>` : ''}
      <div class="actions"><button class="btn red" id="ok">🔨 Предъявить обвинение</button></div>`;
    arr.bind();
    $$('.thief-btn', root).forEach((b) => b.addEventListener('click', () => { culprit = b.dataset.t; warn = null; save(); draw(); }));
    const send = safe(async () => { $('#ok', root).disabled = true; applyAct(await actCall(t, { action: 'finish', data: { order, culprit } })); });
    $('#ok', root).addEventListener('click', () => {
      const miss = [!culprit && 'не выбран вор (шаг 2)', placed < 4 && 'не все персонажи поставлены на время (шаг 1)'].filter(Boolean);
      if (miss.length) { warn = `Не закончено: ${miss.join('; ')}. Баллы за это не начислятся.`; draw(); const w = $('.result.bad', root); if (w) w.scrollIntoView({ block: 'center' }); return; }
      send();
    });
    const f = $('#force', root); if (f) f.addEventListener('click', send); const bk = $('#back', root); if (bk) bk.addEventListener('click', () => { warn = null; draw(); });
  };
  draw();
};
GAMES.warehouse = (root, t, A) => {
  const v = A.view; let order = [...v.order]; const colors = { reglisam: '#c9631b', flamin: '#8a1830', kardio: '#5a2a7a', reaktaktiv: '#2f6b5a' };
  const name = Object.fromEntries(v.boxes.map((b) => [b.id, b.name]));
  let code = v.code;
  const save = debounce(() => sendSave(t, { order, code }), 300);
  const arr = slotArranger(root, { getOrder: () => order, setOrder: (o) => (order = o), onChange: save, redraw: () => draw() });
  const pack = (id) => `<div class="pack ${arr.sel === id ? 'selected' : ''}" data-card="${id}" style="--pc:${colors[id]}">${esc(name[id].toUpperCase())}</div>`;
  const draw = () => {
    root.innerHTML = `<h3>Улики</h3>${v.clues.map((c, i) => `<div class="clue-card"><b>${i + 1}.</b> ${esc(c)}</div>`).join('')}
      <h3 style="margin-top:14px">Полка слева направо</h3><p class="muted small">Нажми упаковку, затем место на полке. Можно перетаскивать; упаковки на полке можно менять местами между собой.</p>
      <div class="shelf">${order.map((id, i) => `<div class="slot ${arr.sel ? 'target' : ''}" data-slot="${i}"><span class="time">${i + 1}</span>${id ? pack(id) : '<span class="muted small">пусто</span>'}</div>`).join('')}</div>
      <h3 style="margin-top:14px">Упаковки</h3><div class="chars" data-pool>${v.boxes.filter((b) => !order.includes(b.id)).map((b) => pack(b.id)).join('') || '<span class="muted small">Все на полке. Чтобы снять, выбери упаковку и нажми сюда.</span>'}</div>
      <label class="field"><span>Код склада</span><input class="input" id="code" inputmode="numeric" maxlength="6" value="${esc(code)}" autocomplete="off"></label><p class="muted small">${esc(v.codeRule)}</p>
      <div class="actions"><button class="btn" id="ok">Открыть склад</button></div>`;
    arr.bind();
    $('#code', root).addEventListener('input', (e) => { code = e.target.value; save(); });
    $('#ok', root).addEventListener('click', safe(async () => { $('#ok', root).disabled = true; applyAct(await actCall(t, { action: 'finish', data: { order, code: $('#code', root).value } })); }));
  };
  draw();
};

/* Конвейер: общий движок для боя и тренировки */
const boxSvg = (label, e, color) => `<svg viewBox="0 0 100 86"><rect x="4" y="14" width="92" height="68" rx="6" fill="#f4ede6"/><rect x="4" y="14" width="20" height="68" rx="6" fill="${color}"/><rect x="24" y="14" width="72" height="6" fill="#d9cdbd"/><text x="60" y="56" font-size="10" font-weight="900" text-anchor="middle" fill="#2a1d20" font-family="Arial">${esc(label.toUpperCase())}</text>${e ? '<g><circle cx="78" cy="24" r="15" fill="#7a3fd1" stroke="#d6b8ff" stroke-width="2.5"/><text x="78" y="31" font-size="18" text-anchor="middle">👻</text></g>' : '<rect x="62" y="68" width="26" height="6" rx="2" fill="#bfb3a3"/>'}</svg>`;
const BOX_COLORS = ['#c9631b', '#8a1830', '#5a2a7a', '#2f6b5a'];
function runBelt(belt, items, travel, labels, elapsed, onClick, clickedInit = []) {
  const els = items.map((it, i) => { const b = document.createElement('button'); b.className = 'box'; b.type = 'button'; b.setAttribute('aria-label', 'Упаковка'); b.innerHTML = boxSvg(labels[it.l], it.e, BOX_COLORS[it.l]); b.style.display = 'none'; b.addEventListener('pointerdown', (ev) => { ev.preventDefault(); if (b.dataset.done) return; b.dataset.done = 1; onClick(i, b); }); belt.append(b); if (clickedInit.includes(i)) b.dataset.done = 1; return b; });
  let raf; const frame = () => {
    const el = elapsed();
    els.forEach((b, i) => { const p = (el - items[i].enter) / travel; if (b.dataset.done || p < 0 || p > 1.05) { if (!b.classList.contains('pop-g') && !b.classList.contains('pop-b')) b.style.display = 'none'; return; } b.style.display = 'block'; b.style.left = p * 110 - 5 + '%'; });
    raf = requestAnimationFrame(frame);
  };
  raf = requestAnimationFrame(frame); onCleanup(() => cancelAnimationFrame(raf));
}
function popBox(b, good) { b.classList.add(good ? 'pop-g' : 'pop-b'); setTimeout(() => (b.style.display = 'none'), 520); beep(good ? [[700, .08]] : [[200, .15]]); }
GAMES.conveyor = (root, t, A) => {
  const v = A.view; let c = v.correct, w = v.wrong;
  root.innerHTML = `<div class="conv-score" id="cs"></div><div class="belt" id="belt"></div><p class="muted small">Нажимай только на упаковки с фиолетовой печатью 👻. Ошибка — минус 1.</p>`;
  const upd = () => ($('#cs', root).innerHTML = `✅ ${c} &nbsp; ❌ ${w}`); upd();
  runBelt($('#belt', root), v.items, v.travel, v.labels, () => now() - A.startedAt, async (i, b) => {
    popBox(b, !!v.items[i].e); if (v.items[i].e) c++; else w++; upd();
    try { const r = await actCall(t, { action: 'click', id: i }); const f = r.feedback; if (f && f.correct != null) { c = f.correct; w = f.wrong; upd(); } } catch {}
  }, v.clicked);
};
function conveyorTraining(zone) {
  zone.innerHTML = '<div class="card" style="box-shadow:none;margin-top:12px"><b>Тренировка без баллов.</b> Нажимай только на упаковки с печатью 👻.<div class="conv-score" id="ts"></div><div class="belt" id="tbelt"></div></div>';
  const items = Array.from({ length: 6 }, (_, i) => ({ enter: i * 1300, e: i % 2, l: i % 4 })); let c = 0, w = 0; const st = Date.now();
  const upd = () => ($('#ts', zone).innerHTML = `✅ ${c} &nbsp; ❌ ${w}`); upd();
  runBelt($('#tbelt', zone), items, 4200, ['Реглисам', 'Фламин', 'Кардиовален', 'Реактактив'], () => Date.now() - st, (i, b) => { popBox(b, !!items[i].e); if (items[i].e) c++; else w++; upd(); });
}
const ALPHA = 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ';
GAMES.spells = (root, t, A) => {
  const v = A.view; const ans = [...v.answers];
  const save = debounce(() => sendSave(t, { a: ans }), 400);
  const [s1, s2, s3] = v.stages;
  root.innerHTML = `<div class="word-stage"><h3>${esc(s1.title)} · ${s1.pts} б.</h3><div class="letters">${[...s1.text].map((l, i) => `<button class="lt" data-i="${i}">${l}</button>`).join('')}</div>
      <div class="muted small">Нажимай буквы так, чтобы слово читалось в обратном порядке:</div><div class="letters" id="o1"></div><button class="btn sm ghost" id="b1">Стереть</button></div>
    <div class="word-stage"><h3>${esc(s2.title)} · ${s2.pts} б.</h3><div class="num-boxes">${s2.codes.map((n, i) => `<div class="num-box">${n}<input maxlength="1" data-i="${i}" autocomplete="off" aria-label="Буква ${i + 1}"></div>`).join('')}</div><button class="btn sm ghost" id="al" style="margin-top:8px">Показать алфавит с номерами</button><div class="alpha" id="alpha" hidden>${[...ALPHA].map((l, i) => `<span><b>${i + 1}</b> ${l}</span>`).join('')}</div></div>
    <div class="word-stage"><h3>${esc(s3.title)} · ${s3.pts} б.</h3><div class="wheel">${esc(s3.text)}</div>
      <label class="field"><span>Расшифрованное слово</span><input class="input" id="a3" maxlength="12" autocomplete="off"></label></div>
    <div class="actions"><button class="btn" id="ok">Завершить заклинания</button></div>`;
  const out1 = []; // выбранные индексы букв этапа 1
  const draw1 = () => { $('#o1', root).innerHTML = out1.map((i) => `<span class="lt out">${s1.text[i]}</span>`).join(''); ans[0] = out1.map((i) => s1.text[i]).join(''); save(); };
  $$('.lt', root).forEach((b) => b.addEventListener('click', () => { const i = Number(b.dataset.i); if (!out1.includes(i)) { out1.push(i); draw1(); b.style.opacity = .35; } }));
  $('#b1', root).addEventListener('click', () => { out1.length = 0; $$('.lt[data-i]', root).forEach((b) => (b.style.opacity = 1)); draw1(); });
  if (ans[0]) { $('#o1', root).innerHTML = [...ans[0]].map((l) => `<span class="lt out">${l}</span>`).join(''); }
  const inputs = $$('.num-box input', root);
  inputs.forEach((inp, i) => { if (ans[1][i]) inp.value = ans[1][i]; inp.addEventListener('input', () => { inp.value = inp.value.toUpperCase(); ans[1] = inputs.map((x) => x.value).join(''); save(); if (inp.value && inputs[i + 1]) inputs[i + 1].focus(); }); });
  $('#al', root).addEventListener('click', () => { const a = $('#alpha', root); a.hidden = !a.hidden; });
  const a3 = $('#a3', root); a3.value = ans[2] || ''; a3.addEventListener('input', () => { ans[2] = a3.value; save(); });
  $('#ok', root).addEventListener('click', safe(async () => { $('#ok', root).disabled = true; ans[1] = inputs.map((x) => x.value).join(''); applyAct(await actCall(t, { action: 'finish', data: { a: ans } })); }));
};
GAMES.puzzle = (root, t, A) => {
  const v = A.view; let arr = [...v.arr], sel = null;
  const save = debounce(() => sendSave(t, { arr }), 250);
  const draw = () => {
    root.innerHTML = `<div class="puzzle" id="pz">${arr.map((piece, i) => `<div class="ptile ${sel === i ? 'selected' : ''}" draggable="true" data-i="${i}" style="background-image:url(/api/poster.svg);background-position:${(piece % 3) * 50}% ${Math.floor(piece / 3) * 50}%"></div>`).join('')}</div>
      <p class="muted small center">Компьютер: перетаскивай плитки. Телефон: коснись одной плитки, затем другой. Верные места не подсвечиваются.</p><div class="actions" style="justify-content:center"><button class="btn" id="ok">Готово</button></div>`;
    const swap = (a, b) => { if (a === b) return; [arr[a], arr[b]] = [arr[b], arr[a]]; sel = null; save(); draw(); };
    $$('.ptile', root).forEach((el) => {
      const i = Number(el.dataset.i);
      el.addEventListener('click', () => { if (sel === null) { sel = i; draw(); } else if (sel === i) { sel = null; draw(); } else swap(sel, i); });
      el.addEventListener('dragstart', (e) => { e.dataTransfer.setData('text/plain', String(i)); e.dataTransfer.effectAllowed = 'move'; });
      el.addEventListener('dragover', (e) => { e.preventDefault(); el.classList.add('over'); }); el.addEventListener('dragleave', () => el.classList.remove('over'));
      el.addEventListener('drop', (e) => { e.preventDefault(); const from = Number(e.dataTransfer.getData('text/plain')); swap(from, i); });
    });
    $('#ok', root).addEventListener('click', safe(async () => { $('#ok', root).disabled = true; applyAct(await actCall(t, { action: 'finish', data: { arr } })); }));
  };
  const left = v.memorizeUntil - now();
  if (left > 0) {
    root.innerHTML = `<p class="center"><b>Запоминай постер!</b> <span id="mm" class="gold"></span></p><img class="poster-full" src="/api/poster.svg" alt="Праздничный постер Миллор Фарма">`;
    const tm = setInterval(() => { const l = v.memorizeUntil - now(); if (l <= 0) { clearInterval(tm); draw(); } else $('#mm', root).textContent = Math.ceil(l / 1000) + ' с'; }, 100); onCleanup(() => clearInterval(tm));
  } else draw();
};
GAMES.sudoku = (root, t, A) => {
  const v = A.view; const cells = [...v.cells]; let sel = null;
  const save = debounce(() => sendSave(t, { cells }), 300);
  const draw = () => {
    root.innerHTML = `<div class="sudoku">${cells.map((c, i) => `<button class="sc ${v.given[i] ? 'given' : ''} ${sel === i ? 'sel' : ''} ${Math.floor(i / 4) === 1 ? 'r2' : ''} ${i % 4 === 1 ? 'c2' : ''}" data-i="${i}" ${v.given[i] ? 'tabindex="-1"' : ''}>${c ? v.symbols[c - 1] : ''}</button>`).join('')}</div>
      <div class="palette">${v.symbols.map((s, k) => `<button data-k="${k + 1}" aria-label="Символ ${s}">${s}</button>`).join('')}<button data-k="0" aria-label="Очистить">⌫</button></div>
      <p class="muted small center">Каждый символ — по одному разу в каждой строке, столбце и блоке 2×2. Ошибки не подсвечиваются.</p><div class="actions" style="justify-content:center"><button class="btn big" id="ok">Открыть кабинет</button></div>`;
    $$('.sc', root).forEach((b) => b.addEventListener('click', () => { const i = Number(b.dataset.i); if (v.given[i]) return; sel = i; draw(); }));
    $$('.palette button', root).forEach((b) => b.addEventListener('click', () => { if (sel === null) return toast('Сначала выбери пустую клетку'); cells[sel] = Number(b.dataset.k); save(); draw(); }));
    $('#ok', root).addEventListener('click', safe(async () => { $('#ok', root).disabled = true; applyAct(await actCall(t, { action: 'finish', data: { cells } })); }));
  };
  draw();
};

/* ---------- Творческие задания ---------- */
function resizeImage(file, max = 1600) {
  return new Promise((ok, fail) => {
    const url = URL.createObjectURL(file), img = new Image();
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight)), c = document.createElement('canvas');
      c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k); c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url); c.toBlob((b) => (b ? ok(b) : fail(new Error('Не удалось обработать фото'))), 'image/jpeg', .85);
    };
    img.onerror = () => { URL.revokeObjectURL(url); fail(new Error('Не удалось открыть фото. Попробуйте JPEG или PNG.')); };
    img.src = url;
  });
}
function videoDuration(file) {
  return new Promise((ok) => { const v = document.createElement('video'), url = URL.createObjectURL(file); v.preload = 'metadata'; v.onloadedmetadata = () => { URL.revokeObjectURL(url); ok(v.duration); }; v.onerror = () => { URL.revokeObjectURL(url); ok(null); }; v.src = url; });
}
async function uploadBlob(blob, kind) {
  const res = await fetch(`/api/uploads?kind=${kind}`, { method: 'POST', credentials: 'same-origin', headers: { 'x-requested-with': 'mgp', 'content-type': 'application/octet-stream' }, body: blob });
  const d = await res.json().catch(() => ({})); if (!res.ok) throw new Error(d.error || 'Не удалось загрузить файл'); return d;
}
const mediaTag = (m) => (m.kind === 'video' ? `<video src="${m.url}" controls playsinline preload="metadata"></video>` : `<img src="${m.url}" alt="Загруженное фото">`);
function creativeView(ui, t) {
  const c = t.creative, sub = c.submission;
  const crit = `<h3 style="font-size:1rem;margin-top:14px">За что начисляются баллы</h3><ul class="criteria">${c.criteria.map((k) => `<li>${esc(k.label)} — ${k.pts} б.${sub && sub.status === 'approved' ? (sub.criteria.includes(k.id) ? ' ✅' : ' —') : ''}</li>`).join('')}</ul>`;
  const status = !sub ? '' : sub.status === 'pending' ? '<div class="result info">⏳ Работа у организатора. Баллы появятся после проверки.</div>'
    : sub.status === 'returned' ? `<div class="result bad">↩️ Организатор вернул работу на исправление.${sub.comment ? `<br>Комментарий: ${esc(sub.comment)}` : ''}<br>У тебя одно исправление — отправь работу ещё раз.</div>`
    : sub.status === 'approved' ? `<div class="result ok">✅ Подтверждено: <b>${sub.points} из 10 баллов</b>.${sub.comment ? `<br>Комментарий: ${esc(sub.comment)}` : ''}</div>`
    : `<div class="result bad">Работа отклонена, задание закрыто.${sub.comment ? `<br>Комментарий: ${esc(sub.comment)}` : ''}</div>`;
  const shown = (d, media) => `<dl class="submitted">${c.fields.map((f) => (d[f.id] ? `<dt>${esc(f.label)}</dt><dd>${esc(d[f.id])}</dd>` : '')).join('')}${media.map((m) => `<div class="media-prev">${mediaTag(m)}</div>`).join('')}</dl>`;
  if (!c.canEdit) {
    ui.innerHTML = `${status}${sub ? `<h3 style="font-size:1rem;margin-top:14px">Твоя работа</h3>${shown(sub.data, sub.media)}` : `<div class="result info">${esc(t.frozen ? 'Итоги подведены.' : t.phase === 'before' ? 'Игра ещё не началась.' : 'Приём работ закрыт.')}</div>`}${crit}<div class="actions"><button class="btn" id="back">К полю</button></div>`;
    $('#back', ui).addEventListener('click', () => closeModal()); return;
  }
  const base = sub && sub.status === 'returned' ? { data: sub.data, media: sub.media } : c.draft || { data: {}, media: [] };
  const data = { ...base.data }; let media = [...base.media]; let busy = false;
  ui.innerHTML = `${status}<h3 style="font-size:1rem">Твой ответ</h3>
    ${c.fields.map((f) => `<label class="form-f field"><span>${esc(f.label)}${f.optional ? ' (необязательно)' : ''}<span class="cnt" data-cnt="${f.id}"></span></span>${f.multiline ? `<textarea class="input" data-f="${f.id}" maxlength="${f.max}" placeholder="${esc(f.placeholder || '')}"></textarea>` : `<input class="input" data-f="${f.id}" maxlength="${f.max}" placeholder="${esc(f.placeholder || '')}" autocomplete="off">`}</label>`).join('')}
    ${c.media ? `<div class="form-f"><label class="drop" id="drop"><input type="file" id="file" accept="${c.media.kinds.includes('video') ? 'image/*,video/*' : 'image/*'}" hidden><span id="drop-t">${c.media.kinds.includes('video') ? '📷 Нажми, чтобы выбрать фото или видео до 15 секунд' : '📷 Нажми, чтобы выбрать фото'}<br><span class="small">Фото уменьшится автоматически. Лицо показывать не нужно. Файл видит только организатор.</span></span></label><div id="media-list"></div></div>` : ''}
    <div id="confirm"></div><div class="actions"><button class="btn" id="send">Отправить на проверку</button></div><p class="muted small" id="saved"></p>${crit}`;
  for (const f of c.fields) { const el = $(`[data-f="${f.id}"]`, ui); el.value = data[f.id] || ''; const cnt = $(`[data-cnt="${f.id}"]`, ui); const u = () => (cnt.textContent = `${el.value.length}/${f.max}`); u(); el.addEventListener('input', () => { data[f.id] = el.value; u(); persist(); }); }
  const persist = debounce(async () => { try { await api(`/api/tasks/${t.meta.id}/draft`, { method: 'POST', body: { data, media: media.map((m) => m.id) } }); $('#saved', ui).textContent = 'Черновик сохранён'; } catch {} }, 900);
  const drawMedia = () => { const l = $('#media-list', ui); if (!l) return; l.innerHTML = media.map((m, i) => `<div class="media-prev">${mediaTag(m)}<button class="btn sm ghost" data-rm="${i}" style="margin-top:6px">Убрать</button></div>`).join(''); $$('[data-rm]', l).forEach((b) => b.addEventListener('click', () => { media.splice(Number(b.dataset.rm), 1); drawMedia(); persist(); })); };
  drawMedia();
  const file = $('#file', ui);
  if (file) file.addEventListener('change', safe(async () => {
    const f = file.files[0]; file.value = ''; if (!f) return;
    $('#drop-t', ui).textContent = 'Обрабатываю и загружаю…';
    try {
      let rec;
      if (f.type.startsWith('video/')) {
        if (!c.media.kinds.includes('video')) throw new Error('В этом задании нужно фото');
        if (f.size > 40 * 1024 * 1024) throw new Error('Видео больше 40 МБ');
        const d = await videoDuration(f); if (d && d > 15.5) throw new Error('Видео длиннее 15 секунд');
        rec = await uploadBlob(f, 'video');
      } else if (f.type.startsWith('image/')) rec = await uploadBlob(await resizeImage(f), 'image');
      else throw new Error('Допустимы фото и видео');
      media = [rec]; drawMedia(); persist();
    } finally { $('#drop-t', ui).innerHTML = c.media.kinds.includes('video') ? '📷 Нажми, чтобы заменить фото или видео' : '📷 Нажми, чтобы заменить фото'; }
  }));
  $('#send', ui).addEventListener('click', () => {
    for (const f of c.fields) if (!f.optional && !(data[f.id] || '').trim()) return toast(`Заполни поле «${esc(f.label)}»`, 'bad');
    if (c.mediaOrNote && !media.length && (data[c.mediaOrNote] || '').trim().length < 10) return toast('Загрузи файл или опиши словами (не меньше 10 символов)', 'bad');
    $('#confirm', ui).innerHTML = `<div class="result info">Отправить работу организатору? ${sub && sub.status === 'returned' ? 'Это твоё единственное исправление.' : 'Изменить ответ после отправки будет нельзя, если организатор не вернёт его на доработку.'}<div class="actions"><button class="btn sm green" id="yes">Да, отправить</button><button class="btn sm ghost" id="no">Вернуться</button></div></div>`;
    $('#no', ui).addEventListener('click', () => ($('#confirm', ui).innerHTML = ''));
    $('#yes', ui).addEventListener('click', safe(async () => { if (busy) return; busy = true; $('#yes', ui).disabled = true; const r = await api(`/api/tasks/${t.meta.id}/submit`, { method: 'POST', body: { data, media: media.map((m) => m.id) } }); renderTask(r.task); refreshMe(); toast('📨 Работа отправлена организатору', 'ok'); }));
  });
}

/* ---------- Запуск ---------- */
router().catch((e) => { app.innerHTML = `<div class="wrap page empty">Не удалось загрузить игру: ${esc(e.message)}</div>`; });
