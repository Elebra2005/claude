'use strict';
/* Кабинет организатора «Миллор Фарма». Права проверяет сервер; здесь только интерфейс. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const main = $('#main');
const fmt = (ms) => (ms ? new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(ms) : '—');
const ST = { new: 'не начато', active: 'в процессе', decide: 'можно улучшить', closed: 'закрыто', pending: 'на проверке', returned: 'на исправлении', approved: 'подтверждено', rejected: 'отклонено' };
let tab = 'dash', testMode = false, reviewFilter = 'pending';

async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, { method, credentials: 'same-origin', headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...(testMode ? { 'X-Scope': 'test' } : {}) }, body: body ? JSON.stringify(body) : undefined });
  let data = {}; try { data = await res.json(); } catch {}
  if (res.status === 401 && !path.startsWith('/api/admin/login') && !path.startsWith('/api/admin/setup')) { showLogin(); throw new Error('Сессия истекла'); }
  if (!res.ok) throw new Error(data.error || `Ошибка ${res.status}`);
  return data;
}
const post = (p, b = {}) => api(p, { method: 'POST', body: b });
const sc = (p) => p + (testMode ? (p.includes('?') ? '&' : '?') + 'scope=test' : '');
function toast(html, kind = '') { const el = document.createElement('div'); el.className = `toast ${kind}`; el.innerHTML = html; $('#toasts').append(el); setTimeout(() => el.remove(), 6000); }
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(esc(e.message), 'bad'); } };
const iso = (v) => `${v}:00+03:00`;
function toInput(isoStr) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(isoStr)).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
function openModal(html) { $('#modal-body').innerHTML = html; $('#modal').hidden = false; document.body.style.overflow = 'hidden'; $('#modal').scrollTop = 0; }
function closeModal() { $('#modal').hidden = true; document.body.style.overflow = ''; }
$('#modal-close').addEventListener('click', closeModal);
$('#modal').addEventListener('click', (e) => { if (e.target.id === 'modal') closeModal(); });

/* ---------- Вход ---------- */
function showLogin() { $('#login').hidden = false; $('#panel').hidden = true; drawLogin(); }
async function drawLogin() {
  const st = await fetch('/api/admin/status').then((r) => r.json());
  const body = $('#login-body');
  if (!st.configured) { body.innerHTML = '<div class="result bad">Администратор не настроен: на сервере не задан ADMIN_EMAIL. См. инструкцию в README.</div>'; return; }
  if (!st.hasPassword) {
    body.innerHTML = `<p>Первый вход. Введите адрес организатора, код настройки из журнала сервера (или файла <code>admin-setup.txt</code>) и придумайте пароль.</p>
      <form id="f"><label class="field"><span>Эл. почта администратора</span><input class="input" type="email" id="em" autocomplete="username" required></label>
      <label class="field"><span>Код первой настройки</span><input class="input" id="tk" autocomplete="off" required></label>
      <label class="field"><span>Новый пароль (не короче 12 символов)</span><input class="input" type="password" id="pw" autocomplete="new-password" minlength="12" required></label>
      <div class="form-error" id="err" role="alert"></div><button class="btn big" style="width:100%">Задать пароль</button></form>`;
    $('#f').addEventListener('submit', async (e) => { e.preventDefault(); $('#err').textContent = ''; try { await post('/api/admin/setup', { email: $('#em').value, token: $('#tk').value, password: $('#pw').value }); toast('Пароль задан. Теперь войдите.', 'ok'); drawLogin(); } catch (er) { $('#err').textContent = er.message; } });
    return;
  }
  body.innerHTML = `<form id="f"><label class="field"><span>Эл. почта</span><input class="input" type="email" id="em" autocomplete="username" required></label>
    <label class="field"><span>Пароль</span><input class="input" type="password" id="pw" autocomplete="current-password" required></label><div class="form-error" id="err" role="alert"></div><button class="btn big" style="width:100%">Войти</button></form>`;
  $('#f').addEventListener('submit', async (e) => { e.preventDefault(); $('#err').textContent = ''; try { await post('/api/admin/login', { email: $('#em').value, password: $('#pw').value }); $('#pw').value = ''; init(); } catch (er) { $('#err').textContent = er.message; } });
}
async function init() {
  const me = await fetch('/api/admin/me', { credentials: 'same-origin' }).then((r) => r.json());
  if (!me.admin) return showLogin();
  $('#login').hidden = true; $('#panel').hidden = false; render();
  if (!init.t) init.t = setInterval(() => { if (!document.hidden && !$('#panel').hidden) badge(); }, 15000);
}
$('#logout').addEventListener('click', async () => { await post('/api/admin/logout').catch(() => {}); showLogin(); });
$('#tabs').addEventListener('click', (e) => { const b = e.target.closest('[data-tab]'); if (b) { tab = b.dataset.tab; render(); } });
$('#test-mode').addEventListener('change', (e) => { testMode = e.target.checked; document.body.classList.toggle('test-on', testMode); render(); });
async function badge() { try { const d = await api('/api/admin/dashboard'); $('#pending-badge').textContent = d.pending || ''; } catch {} }
async function render() {
  $$('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
  $('#scope-note').innerHTML = testMode ? '<div class="banner test">🧪 <div class="grow"><b>Тестовая роль.</b> Показаны и изменяются только тестовые участники. Реальные результаты защищены сервером от изменений из этого режима.</div></div>' : '';
  main.innerHTML = '<p class="muted">Загрузка…</p>';
  try { await VIEWS[tab](); } catch (e) { main.innerHTML = `<div class="card">Ошибка: ${esc(e.message)}</div>`; }
  badge();
}
const phaseText = { before: 'ещё не началась', running: 'идёт', paused: 'на паузе (новые попытки не принимаются)', ended: 'завершена' };

const VIEWS = {
  async dash() {
    const d = await api('/api/admin/dashboard'), g = d.game;
    main.innerHTML = `<div class="banner ${g.phase === 'running' ? 'test' : 'warn'}"><div class="grow">Игра: <span class="state-pill ${g.phase}">${phaseText[g.phase]}</span> · ${esc(fmt(Date.parse(g.start)))} — ${esc(fmt(Date.parse(g.end)))} МСК${d.final ? ' · <b>итоги подведены</b>' : ''}</div>
      ${g.phase === 'before' || g.phase === 'ended' ? '<button class="btn sm green" data-g="start">▶ Запустить игру</button>' : ''}${g.phase === 'running' ? '<button class="btn sm ghost" data-g="pause">⏸ Пауза приёма попыток</button>' : ''}${g.phase === 'paused' ? '<button class="btn sm green" data-g="resume">▶ Продолжить</button>' : ''}${g.phase === 'running' || g.phase === 'paused' ? '<button class="btn sm red" data-g="end">⏹ Завершить игру</button>' : ''}</div>
      <div id="gm"></div>
      <div class="grid-stats"><div class="card stat"><div class="label">Всего участников</div><div class="value">${d.total}</div><div class="muted small">кодов выдано: ${d.codes}, использовано: ${d.codesUsed}</div></div>
        <div class="card stat"><div class="label">Активных (15 мин)</div><div class="value">${d.active}</div></div><div class="card stat"><div class="label">Завершённых заданий</div><div class="value">${d.closedTasks}</div></div>
        <div class="card stat"><div class="label">Работ на модерации</div><div class="value">${d.pending}</div></div><div class="card stat"><div class="label">Собрано БИНГО</div><div class="value">${d.bingos}</div></div><div class="card stat"><div class="label">Средний результат</div><div class="value">${d.average}</div></div></div>
      <div class="card"><h3>Текущие лидеры</h3><table class="tbl"><thead><tr><th>#</th><th>Участник</th><th class="n">БИНГО</th><th class="n">Баллы</th></tr></thead><tbody>${d.leaders.map((r) => `<tr><td>${r.rank}</td><td>${esc(r.name)}</td><td class="n">${r.bingos}</td><td class="n gold"><b>${r.total}</b></td></tr>`).join('') || '<tr><td colspan="4" class="muted">Пока никого</td></tr>'}</tbody></table></div>`;
    $$('[data-g]', main).forEach((b) => b.addEventListener('click', guard(async () => {
      const a = b.dataset.g;
      if (a === 'end') { $('#gm').innerHTML = '<div class="banner warn"><div class="grow">Завершить игру для всех? Новые попытки и ответы перестанут приниматься.</div><button class="btn sm red" id="y">Да, завершить</button><button class="btn sm ghost" id="n">Отмена</button></div>'; $('#n').onclick = () => ($('#gm').innerHTML = ''); $('#y').onclick = guard(async () => { await post('/api/admin/game', { action: 'end', confirm: true }); render(); }); return; }
      await post('/api/admin/game', { action: a }); toast('Готово', 'ok'); render();
    })));
  },

  async players() {
    const list = await api('/api/admin/players');
    main.innerHTML = `<div class="row" style="margin-bottom:12px"><h2 style="margin:0;margin-right:auto">Участники (${list.length})</h2><a class="btn sm" href="${sc('/api/admin/export.csv')}">⬇ Результаты в CSV (Excel)</a></div>
      <div class="card scroll-x"><table class="tbl"><thead><tr><th>Место</th><th>Имя</th><th>Место работы</th><th class="n">Пройдено</th><th class="n">Авто</th><th class="n">Творческие</th><th class="n">БИНГО-бонус</th><th class="n">Итого</th><th class="n">Попыток</th><th>Был в игре</th></tr></thead>
      <tbody>${list.map((p) => `<tr><td>${p.rank}${p.tied ? ' <span title="Полное равенство">⚖️</span>' : ''}</td><td><button class="name-link" data-id="${p.id}">${esc(p.name)}</button></td><td>${p.format === 'office' ? '🏢 Офис' : '🏠 Удалённо'}</td><td class="n">${p.closed}/16</td><td class="n">${p.auto}</td><td class="n">${p.creative}</td><td class="n">${p.bonus}</td><td class="n gold"><b>${p.total}</b></td><td class="n">${p.attempts}</td><td class="small muted">${esc(fmt(p.lastSeen))}</td></tr>`).join('') || '<tr><td colspan="10" class="muted">Участников пока нет</td></tr>'}</tbody></table></div>`;
    $$('.name-link', main).forEach((b) => b.addEventListener('click', guard(() => playerCard(b.dataset.id))));
  },

  async review() {
    const list = await api(`/api/admin/submissions?status=${reviewFilter}`);
    const F = { pending: 'На проверке', approved: 'Подтверждённые', returned: 'На исправлении', rejected: 'Отклонённые', all: 'Все' };
    main.innerHTML = `<div class="row" style="margin-bottom:14px"><div class="seg">${Object.entries(F).map(([k, v]) => `<button data-f="${k}" class="${k === reviewFilter ? 'on' : ''}">${v}</button>`).join('')}</div></div>
      ${list.length ? list.map((s) => `<div class="card sub" data-id="${s.id}" style="grid-template-columns:1fr">
        <div><div class="row"><b>${esc(s.name)}</b><span class="muted small">${s.format === 'office' ? '🏢 Офис' : '🏠 Удалённо'}</span><span class="pill ${s.status}">${ST[s.status] || s.status}</span>${s.revision ? '<span class="pill">исправленная версия</span>' : ''}</div>
        <div class="muted small">№ ${s.taskId} ${s.emoji} ${esc(s.title)} · отправлено ${esc(fmt(s.createdAt))}</div>
        <dl class="fields-view">${s.fields.map((f) => `<dt>${esc(f.label)}</dt><dd>${esc(f.value) || '<span class="muted">—</span>'}</dd>`).join('')}</dl>
        ${s.media.map((m) => `<div style="margin-top:8px">${m.kind === 'video' ? `<video src="${m.url}" controls playsinline preload="metadata"></video>` : `<a href="${m.url}" target="_blank" rel="noopener"><img src="${m.url}" alt="Фото участника" loading="lazy" style="max-width:100%;max-height:340px;border-radius:10px"></a>`}</div>`).join('')}
        <h4 style="margin:12px 0 4px">Критерии</h4>${s.criteria.map((k) => `<label class="crit"><input type="checkbox" data-c="${k.id}" data-p="${k.pts}" ${s.status === 'pending' ? '' : 'disabled'} ${s.ticked.includes(k.id) ? 'checked' : ''}><span>${esc(k.label)} — <b>${k.pts}</b></span></label>`).join('')}
        <div class="gold" style="font-weight:800;margin-top:4px">Баллы: <span class="sum">${s.status === 'pending' ? 0 : s.points ?? 0}</span> из 10</div>
        ${s.status === 'pending' ? `<div class="row" style="margin-top:8px"><input class="input cm" placeholder="Комментарий участнику (необязательно)" maxlength="500"><button class="btn green sm" data-act="approve">✓ Подтвердить результат</button>${s.revision ? '' : '<button class="btn ghost sm" data-act="return">↩ Вернуть на исправление</button>'}<button class="btn red sm" data-act="reject">✕ Отклонить</button></div>` : `${s.comment ? `<div class="muted small" style="margin-top:6px">Комментарий: ${esc(s.comment)}</div>` : ''}`}
      </div></div>`).join('') : '<div class="card empty">Здесь пока пусто 🎃</div>'}`;
    $$('.seg button', main).forEach((b) => b.addEventListener('click', () => { reviewFilter = b.dataset.f; render(); }));
    $$('.sub[data-id]', main).forEach((card) => {
      const upd = () => ($('.sum', card).textContent = $$('[data-c]:checked', card).reduce((a, i) => a + Number(i.dataset.p), 0));
      if ($('[data-act]', card)) $$('[data-c]', card).forEach((i) => i.addEventListener('change', upd));
      $$('[data-act]', card).forEach((b) => b.addEventListener('click', guard(async () => {
        const act = b.dataset.act;
        const r = await post(`/api/admin/submissions/${card.dataset.id}/review`, { decision: act, criteria: $$('[data-c]:checked', card).map((i) => i.dataset.c), comment: $('.cm', card).value });
        toast(act === 'approve' ? `Подтверждено: ${r.points} из 10, рейтинг обновлён` : act === 'return' ? 'Возвращено на исправление' : 'Отклонено', 'ok'); render();
      })));
    });
  },

  async rating() {
    const d = await api('/api/admin/rating');
    main.innerHTML = `<div class="row" style="margin-bottom:12px"><h2 style="margin:0;margin-right:auto">Рейтинг и победители</h2>${d.final ? '<span class="state-pill running">итоги подведены</span>' : '<span class="state-pill paused">рейтинг предварительный</span>'}</div>
      ${d.pending ? `<div class="banner warn">⏳ На проверке ещё <b>${d.pending}</b> работ. Перед подведением итогов лучше проверить их все.</div>` : ''}
      <div class="row" style="margin-bottom:12px"><a class="btn sm" href="${sc('/api/admin/export.csv')}">⬇ Выгрузить в CSV (Excel)</a><button class="btn sm ghost" id="tb">⚖️ Жеребьёвка среди полностью равных</button>
        ${d.final ? '<button class="btn sm ghost" id="uf">🔓 Снять фиксацию</button>' : '<button class="btn sm red" id="fin">🏁 Подвести итоги</button>'}</div><div id="fm"></div>
      ${d.final ? `<div class="card" style="margin-bottom:14px"><h3>🏆 Победители</h3>${d.final.top3.map((r) => `<div>${['🥇', '🥈', '🥉'][r.rank - 1] || r.rank} <b>${esc(r.name)}</b> — ${r.total} баллов, БИНГО: ${r.bingos}</div>`).join('')}</div>` : ''}
      <div class="card scroll-x"><table class="tbl"><thead><tr><th>#</th><th>Имя</th>${d.tasks.map((t) => `<th class="c" title="${esc(t.title)}">${t.id}</th>`).join('')}<th class="n">Бонус</th><th class="n">БИНГО</th><th class="n">«10»</th><th class="n">Попыт.</th><th class="n">Итого</th></tr></thead><tbody>
      ${d.rows.map((r) => `<tr><td>${r.rank}${r.tied ? ' ⚖️' : ''}</td><td>${esc(r.name)}</td>${d.tasks.map((t) => `<td class="c ${r.adjusted.includes(t.id) ? 'gold' : ''}">${r.pts[t.id] ?? '·'}</td>`).join('')}<td class="n">${r.bonus}</td><td class="n">${r.bingos}</td><td class="n">${r.tens}</td><td class="n">${r.attempts}</td><td class="n gold"><b>${r.total}</b></td></tr>`).join('') || `<tr><td colspan="${d.tasks.length + 7}" class="muted">Пока нет участников</td></tr>`}</tbody></table></div>
      <p class="muted small">Порядок при равенстве: баллы → БИНГО → заданий на 10 → меньше попыток → жеребьёвка. Золотым выделены оценки, скорректированные организатором. ⚖️ — полное равенство без жеребьёвки.</p>`;
    const tb = $('#tb'); if (tb) tb.addEventListener('click', guard(async () => { const r = await post('/api/admin/tiebreak'); toast('Жеребьёвка проведена: ' + esc(r.notes.join('; ')), 'ok'); render(); }));
    const uf = $('#uf'); if (uf) uf.addEventListener('click', guard(async () => { await post('/api/admin/unfreeze'); render(); }));
    const fin = $('#fin'); if (fin) fin.addEventListener('click', () => {
      $('#fm').innerHTML = `<div class="banner warn"><div class="grow">Подвести итоги и зафиксировать рейтинг? Участники увидят экран «ЛАБОРАТОРИЯ СПАСЕНА!». Оценки после фиксации не меняются, пока вы не снимете её.${d.pending ? ` <b>Работ на проверке: ${d.pending}</b> — они не будут учтены.` : ''}</div><button class="btn sm red" id="y">Подвести итоги</button><button class="btn sm ghost" id="n">Отмена</button></div>`;
      $('#n').onclick = () => ($('#fm').innerHTML = '');
      $('#y').onclick = guard(async () => { const r = await post('/api/admin/finalize', { force: true }); toast('Итоги подведены' + (r.draws.length ? '. Жеребьёвка: ' + esc(r.draws.join('; ')) : ''), 'ok'); render(); });
    });
  },

  async settings() {
    const s = await api('/api/admin/settings'), g = s.game;
    const codes = await api('/api/admin/codes');
    main.innerHTML = `<div class="cols2">
      <div class="card"><h2>🕰 Время игры (МСК)</h2><div class="muted small">Сейчас: <span class="state-pill ${g.phase}">${phaseText[g.phase]}</span></div>
        <form id="tf"><label class="field"><span>Начало</span><input class="input" type="datetime-local" id="ts" value="${toInput(g.start)}" required></label>
        <label class="field"><span>Окончание (можно изменить и во время игры)</span><input class="input" type="datetime-local" id="te" value="${toInput(g.end)}" required></label>
        <label class="check"><input type="checkbox" id="as" ${g.autoStart ? 'checked' : ''}><span>Начинать автоматически в указанное время</span></label><button class="btn">Сохранить время</button></form>
        <div class="row" style="margin-top:14px"><button class="btn sm green" data-g="start">▶ Запустить сейчас</button><button class="btn sm ghost" data-g="pause">⏸ Пауза</button><button class="btn sm ghost" data-g="resume">▶ Продолжить</button><button class="btn sm red" id="endg">⏹ Завершить игру</button></div><div id="gm"></div></div>
      <div class="card"><h2>⏱ Таймеры заданий</h2><p class="muted small">Менять можно до начала мероприятия. Во время игры изменение требует подтверждения и причины и записывается в журнал.</p>
        <form id="tm">${Object.entries(s.timerLabels).map(([id, l]) => `<div class="timer-row"><span>${esc(l)}</span><input class="input" type="number" min="3" max="900" data-t="${id}" value="${s.timers[id]}"></div>`).join('')}
        <div id="tm-extra"></div><button class="btn">Сохранить таймеры</button></form></div></div>
    <div class="card"><h2>🎟️ Игровые коды ${testMode ? '(тестовые)' : ''}</h2><p class="muted small">Один код — один игровой профиль. В базе хранится только защищённое представление; список для выдачи доступен здесь и в CSV.</p>
      <form class="row" id="gen"><input class="input" type="number" id="cnt" min="1" max="100" value="${testMode ? 3 : 50}" style="max-width:110px"><input class="input" id="note" placeholder="Пометка (необязательно)" maxlength="100"><button class="btn">Создать коды</button></form>
      <div class="row" style="margin-top:10px"><a class="btn ghost sm" href="${sc('/api/admin/codes.csv')}">⬇ Список кодов (CSV)</a><button class="btn ghost sm" id="print">🖨 Карточки для печати</button><span class="muted small">всего: ${codes.length}, свободно: ${codes.filter((c) => !c.name && !c.revoked).length}</span></div>
      <div class="scroll-x" style="margin-top:10px"><table class="tbl"><thead><tr><th>Код</th><th>Пометка</th><th>Участник</th><th>Статус</th><th></th></tr></thead><tbody>${codes.map((c) => `<tr><td class="code">${esc(c.code)}</td><td class="small">${esc(c.note)}</td><td>${c.name ? esc(c.name) : '<span class="muted">—</span>'}</td><td>${c.revoked ? '<span class="pill failed">отключён</span>' : c.name ? '<span class="pill done">используется</span>' : '<span class="pill">свободен</span>'}</td><td class="row">${c.revoked ? `<button class="btn ghost sm" data-c="${c.id}" data-a="restore">Включить</button>` : `<button class="btn ghost sm" data-c="${c.id}" data-a="revoke">Отключить</button>`}<button class="btn ghost sm" data-c="${c.id}" data-a="delete">Удалить</button></td></tr>`).join('') || '<tr><td colspan="5" class="muted">Кодов пока нет</td></tr>'}</tbody></table></div></div>
    <div class="cols2"><div class="card"><h2>🖼 Логотип</h2><p class="muted small">Официальный логотип Миллор Фарма (PNG/JPEG/WebP до 1 МБ). Без него показывается текстовое название.</p>${s.logo ? `<img src="${s.logo}?t=${Date.now()}" alt="Логотип" style="max-height:60px;background:#fff2;padding:8px;border-radius:8px">` : ''}
      <div class="row" style="margin-top:8px"><input type="file" id="logo" accept="image/png,image/jpeg,image/webp">${s.logo ? '<button class="btn ghost sm" id="rmlogo">Удалить</button>' : ''}</div></div>
      <div class="card"><h2>🧪 Тестовый режим</h2><p class="muted small">Тестовые участники играют вне расписания и не попадают в настоящий рейтинг. Включите «Тестовая роль» вверху, чтобы проверять модерацию, жеребьёвку и итоги на тестовых данных.</p>
        <div class="row"><button class="btn" id="mk">Создать 3 тестовых кода</button><button class="btn ghost" id="clr">Очистить тестовые данные</button></div><div id="newc"></div></div></div>
    <div class="card"><h2>📜 История</h2><div class="seg" id="logseg"><button data-k="points" class="on">Начисления и корректировки</button><button data-k="audit">Журнал действий организатора</button></div><div id="logbox" class="scroll-x" style="margin-top:10px"></div></div>
    <div class="card"><h2>💾 Резервная копия и удаление данных</h2><div class="row"><a class="btn sm" href="/api/admin/backup.json">⬇ Скачать резервную копию результатов (JSON)</a></div>
      <hr style="border-color:var(--line);margin:16px 0"><p>Удаление после мероприятия безвозвратно стирает участников, ответы и фото. Сначала выгрузите CSV и резервную копию.</p>
      <label class="check"><input type="checkbox" id="wc"><span>Удалить также игровые коды</span></label><div class="row"><input class="input" id="wconf" placeholder="Введите слово УДАЛИТЬ" style="max-width:260px"><button class="btn red" id="wipe">Удалить все игровые данные</button></div></div>`;
    $('#tf').addEventListener('submit', guard(async (e) => { e.preventDefault(); await post('/api/admin/game', { action: 'schedule', start: iso($('#ts').value), end: iso($('#te').value), autoStart: $('#as').checked }); toast('Время сохранено', 'ok'); render(); }));
    $$('[data-g]', main).forEach((b) => b.addEventListener('click', guard(async () => { await post('/api/admin/game', { action: b.dataset.g }); toast('Готово', 'ok'); render(); })));
    $('#endg').addEventListener('click', () => { $('#gm').innerHTML = '<div class="banner warn"><div class="grow">Завершить игру для всех?</div><button class="btn sm red" id="y">Да</button><button class="btn sm ghost" id="n">Нет</button></div>'; $('#n').onclick = () => ($('#gm').innerHTML = ''); $('#y').onclick = guard(async () => { await post('/api/admin/game', { action: 'end', confirm: true }); render(); }); });
    $('#tm').addEventListener('submit', guard(async (e) => {
      e.preventDefault();
      const timers = Object.fromEntries($$('[data-t]').map((i) => [i.dataset.t, Number(i.value)]));
      const changed = Object.keys(timers).filter((k) => timers[k] !== s.timers[k]);
      if (!changed.length) return toast('Изменений нет');
      if (g.phase !== 'before' && !$('#reason')) { $('#tm-extra').innerHTML = '<div class="result bad">Игра уже идёт или завершена. Укажите причину изменения правил — она будет записана в журнал.<label class="field"><span>Причина</span><input class="input" id="reason" maxlength="200"></label></div>'; return; }
      await post('/api/admin/timers', { timers, confirm: true, reason: $('#reason') ? $('#reason').value : '' }); toast('Таймеры сохранены', 'ok'); render();
    }));
    $('#gen').addEventListener('submit', guard(async (e) => { e.preventDefault(); const r = await post('/api/admin/codes/generate', { count: $('#cnt').value, note: $('#note').value }); toast(`Создано кодов: ${r.created.length}`, 'ok'); render(); }));
    $$('[data-a]', main).forEach((b) => b.addEventListener('click', guard(async () => {
      if (b.dataset.a === 'delete' && !confirm('Удалить код? Профиль и ответы участника тоже будут удалены.')) return;
      if (b.dataset.a === 'revoke' && !confirm('Отключить код? Участник будет разлогинен.')) return;
      await post(`/api/admin/codes/${b.dataset.c}/${b.dataset.a}`); render();
    })));
    $('#print').addEventListener('click', () => {
      const w = window.open('', '_blank'); if (!w) return toast('Разрешите всплывающие окна', 'bad');
      w.document.write(`<!doctype html><meta charset="utf-8"><title>Коды</title><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">${codes.filter((c) => !c.revoked).map((c) => `<div style="border:1px dashed #999;padding:14px;border-radius:8px;font-family:Arial"><div style="font-size:12px;color:#666">Миллор Фарма · Halloween Bingo 🎃</div><div style="font:700 18px 'Courier New';margin:8px 0;letter-spacing:1px">${esc(c.code)}</div><div style="font-size:12px">${esc(location.origin)}</div></div>`).join('')}</div>`); w.document.close();
    });
    $('#logo').addEventListener('change', guard(async (e) => {
      const f = e.target.files[0]; if (!f) return; if (f.size > 1024 * 1024) throw new Error('Файл больше 1 МБ');
      const data = await new Promise((ok, fail) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = fail; r.readAsDataURL(f); });
      await post('/api/admin/logo', { image: data }); toast('Логотип загружен', 'ok'); render();
    }));
    const rm = $('#rmlogo'); if (rm) rm.addEventListener('click', guard(async () => { await post('/api/admin/logo', { remove: true }); render(); }));
    $('#mk').addEventListener('click', guard(async () => { const r = await post('/api/admin/demo/create', { count: 3 }); $('#newc').innerHTML = `<p>Тестовые коды: ${r.created.map((c) => `<b class="code">${esc(c)}</b>`).join(' · ')}</p>`; }));
    $('#clr').addEventListener('click', guard(async () => { if (!confirm('Удалить всех тестовых участников, их ответы, фото и тестовые коды?')) return; await post('/api/admin/demo/clear'); toast('Тестовые данные удалены', 'ok'); render(); }));
    $('#wipe').addEventListener('click', guard(async () => { if (!confirm('Точно удалить ВСЕ игровые данные? Это необратимо.')) return; await post('/api/admin/wipe', { confirm: $('#wconf').value.trim(), codes: $('#wc').checked }); toast('Данные удалены', 'ok'); render(); }));
    const drawLog = async (k) => {
      const rows = await api(`/api/admin/log?kind=${k}`);
      $('#logbox').innerHTML = k === 'points' ? `<table class="tbl"><thead><tr><th>Время (МСК)</th><th>Участник</th><th>Задание</th><th class="n">Баллы</th><th>Что произошло</th><th>Кто</th></tr></thead><tbody>${rows.map((r) => `<tr><td class="small">${esc(r.atMsk)}</td><td>${esc(r.name)}</td><td class="small">${esc(r.task)}</td><td class="n">${r.points ?? ''}</td><td>${esc(r.note)}</td><td class="small muted">${esc(r.actor)}</td></tr>`).join('') || '<tr><td colspan="6" class="muted">Пока пусто</td></tr>'}</tbody></table>`
        : `<table class="tbl"><thead><tr><th>Время (МСК)</th><th>Кто</th><th>Действие</th><th>Детали</th></tr></thead><tbody>${rows.map((r) => `<tr><td class="small">${esc(r.atMsk)}</td><td class="small">${esc(r.actor)}</td><td>${esc(r.action)}</td><td class="small">${esc(r.detail)}</td></tr>`).join('') || '<tr><td colspan="4" class="muted">Пока пусто</td></tr>'}</tbody></table>`;
    };
    $$('#logseg button').forEach((b) => b.addEventListener('click', () => { $$('#logseg button').forEach((x) => x.classList.toggle('on', x === b)); drawLog(b.dataset.k).catch(() => {}); }));
    drawLog('points');
  },
};

async function playerCard(id) {
  const d = await api(`/api/admin/players/${id}`);
  openModal(`<h2>${esc(d.player.name)} <span class="muted small">${d.player.format === 'office' ? '🏢 Офис' : '🏠 Удалённо'}</span></h2>
    <p>Итого: <b class="gold">${d.score.total}</b> (задания ${d.score.auto + d.score.creative}, БИНГО-бонус ${d.score.bonus}, линий ${d.score.bingos}). Был в игре: ${esc(fmt(d.player.lastSeen))}</p>
    <div class="scroll-x"><table class="tbl"><thead><tr><th>№</th><th>Задание</th><th>Статус</th><th class="n">Баллы</th><th>Попытки / работы</th></tr></thead><tbody>${d.tasks.map((t) => `<tr><td>${t.id}</td><td>${t.emoji} ${esc(t.title)}</td><td>${ST[t.status] || t.status}${t.hint ? ' 💡' : ''}</td><td class="n ${t.adjusted ? 'gold' : ''}"><b>${t.points ?? '—'}</b>${t.adjusted ? '*' : ''}</td>
      <td class="small">${t.attempts.map((a) => `п.${a.n}: ${a.final == null ? 'идёт' : `${a.raw}→${a.final}`}`).join('; ')}${t.submissions.map((x) => `работа ${x.revision ? 'v2' : 'v1'}: ${ST[x.status === 'pending' ? 'pending' : x.status === 'returned' ? 'returned' : x.status]}${x.points != null ? ' ' + x.points : ''}`).join('; ')}</td></tr>`).join('')}</tbody></table></div>
    <p class="muted small">* оценка скорректирована организатором. 💡 — использована подсказка.</p>
    <h3>Скорректировать оценку</h3><form id="adj" class="row"><select class="input" id="at" style="max-width:260px">${d.tasks.map((t) => `<option value="${t.id}">№ ${t.id} ${esc(t.title)}</option>`).join('')}</select><input class="input" id="ap" type="number" min="0" max="10" placeholder="0–10" style="max-width:100px"><input class="input" id="ar" placeholder="Причина (обязательно)" maxlength="300"><button class="btn sm">Применить</button><button class="btn ghost sm" type="button" id="aclr">Снять корректировку</button></form>
    <h3>Последние начисления</h3><table class="tbl"><tbody>${d.log.slice(0, 15).map((l) => `<tr><td class="small muted">${esc(fmt(l.at))}</td><td class="small">${l.task_id ? '№' + l.task_id : ''}</td><td class="small">${esc(l.note)}</td><td class="small muted">${esc(l.actor)}</td></tr>`).join('')}</tbody></table>
    <div class="actions"><button class="btn ghost sm" id="delp">Удалить профиль</button></div>`);
  $('#adj').addEventListener('submit', guard(async (e) => { e.preventDefault(); await post('/api/admin/adjust', { playerId: Number(id), taskId: Number($('#at').value), points: Number($('#ap').value), reason: $('#ar').value }); toast('Оценка изменена, баллы и БИНГО пересчитаны', 'ok'); closeModal(); render(); }));
  $('#aclr').addEventListener('click', guard(async () => { await post('/api/admin/adjust', { playerId: Number(id), taskId: Number($('#at').value), points: null, reason: $('#ar').value || 'снятие корректировки' }); closeModal(); render(); }));
  $('#delp').addEventListener('click', guard(async () => { if (!confirm('Удалить профиль со всеми ответами и фото?')) return; await post(`/api/admin/players/${id}/delete`); closeModal(); render(); }));
}

init().catch(() => showLogin());
