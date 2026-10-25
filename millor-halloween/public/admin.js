'use strict';
/* Пульт организатора */
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const main = $('#main');
const STATUS = { not_started: 'не начато', in_progress: 'выполняется', review: 'на проверке', done: 'выполнено', retry: 'попробуй ещё раз', failed: 'попытки исчерпаны' };
const fmt = (ms) => ms ? new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).format(ms) : '—';
let tab = 'stats';
let testMode = false;
let reviewFilter = 'pending';

async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, { method, credentials: 'same-origin', headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
  let data = {};
  try { data = await res.json(); } catch {}
  if (res.status === 401 && path !== '/api/admin/login') { showLogin(); throw new Error('Сессия истекла'); }
  if (!res.ok) throw new Error(data.error || `Ошибка ${res.status}`);
  return data;
}
const T = (p) => p + (p.includes('?') ? '&' : '?') + (testMode ? 'test=1' : 'test=0');
const post = (p, body = {}) => api(p, { method: 'POST', body });
function toast(text, kind = '') {
  const el = document.createElement('div'); el.className = `toast ${kind}`; el.innerHTML = text;
  $('#toasts').append(el); setTimeout(() => el.remove(), 5000);
}
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(esc(e.message), 'bad'); } };

// ISO-время ↔ значение <input type="datetime-local"> в московском времени
function isoToMskInput(iso) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    .formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
const mskInputToIso = (v) => `${v}:00+03:00`;

function showLogin() { $('#login').hidden = false; $('#panel').hidden = true; }
async function init() {
  const me = await api('/api/admin/me');
  if (!me.admin) return showLogin();
  $('#login').hidden = true; $('#panel').hidden = false;
  render();
  setInterval(() => { if (!document.hidden && !$('#panel').hidden) updateBadge(); }, 20000);
}
$('#f-login').addEventListener('submit', async (e) => {
  e.preventDefault(); $('#err').textContent = '';
  try { await post('/api/admin/login', { password: $('#pw').value }); $('#pw').value = ''; init(); } catch (err) { $('#err').textContent = err.message; }
});
$('#logout').addEventListener('click', async () => { await post('/api/admin/logout').catch(() => {}); showLogin(); });
$('#tabs').addEventListener('click', (e) => { const b = e.target.closest('button[data-tab]'); if (b) { tab = b.dataset.tab; render(); } });
$('#test-mode').addEventListener('change', (e) => { testMode = e.target.checked; document.body.classList.toggle('test-on', testMode); render(); });

async function updateBadge() {
  try { const s = await api(T('/api/admin/stats')); $('#pending-badge').textContent = s.pending || ''; } catch {}
}
async function render() {
  $$('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
  main.innerHTML = '<p class="muted">Загрузка…</p>';
  try { await VIEWS[tab](); } catch (e) { main.innerHTML = `<div class="card">Ошибка: ${esc(e.message)}</div>`; }
  updateBadge();
}
const testNote = () => testMode ? '<div class="banner test">🧪 Показаны <b>тестовые</b> участники. Снимите галочку «Тестовые данные», чтобы вернуться к настоящим.</div>' : '';

const VIEWS = {
  async stats() {
    const s = await api(T('/api/admin/stats'));
    const g = s.game;
    const phase = { before: 'ещё не началась', running: 'идёт', after: 'завершена', stopped: 'остановлена вручную' }[g.phase];
    main.innerHTML = `${testNote()}
      <div class="banner ${g.phase === 'running' ? 'test' : 'warn'}">🕰 Игра <b>${phase}</b>. Расписание: ${esc(fmt(Date.parse(g.start)))} — ${esc(fmt(Date.parse(g.end)))} (МСК). Режим: ${{ schedule: 'по расписанию', open: 'открыта вручную', closed: 'закрыта вручную' }[g.mode]}.</div>
      <div class="grid-stats">
        <div class="card stat"><div class="label">Участников</div><div class="value">${s.players}</div><div class="muted small">🏢 ${s.office} · 🏠 ${s.remote} · кодов: ${s.codes}</div></div>
        <div class="card stat"><div class="label">Выполнено заданий</div><div class="value">${s.completedTasks}</div></div>
        <div class="card stat"><div class="label">На проверке</div><div class="value">${s.pending}</div></div>
        <div class="card stat"><div class="label">Собрано БИНГО</div><div class="value">${s.bingos}</div></div>
      </div>
      <div class="cols2">
        <div class="card"><h3>Текущий рейтинг</h3><div class="tbl-wrap"><table class="tbl"><thead><tr><th>#</th><th>Участник</th><th class="n">Задания</th><th class="n">БИНГО</th><th class="n">Баллы</th></tr></thead>
          <tbody>${s.leaderboard.map((r) => `<tr><td>${r.rank}</td><td>${esc(r.name)}</td><td class="n">${r.completed}</td><td class="n">${r.bingos}</td><td class="n amber"><b>${r.score}</b></td></tr>`).join('') || '<tr><td colspan="5" class="muted">Пока никого</td></tr>'}</tbody></table></div></div>
        <div class="card"><h3>Задания</h3><table class="tbl"><thead><tr><th>Задание</th><th>Тип</th><th class="n">Выполнили</th></tr></thead>
          <tbody>${s.perTask.map((t) => `<tr><td>${t.emoji} ${t.id}. ${esc(t.title)}</td><td class="muted small">${t.type === 'auto' ? 'авто' : 'творческое'}</td><td class="n">${t.done}</td></tr>`).join('')}</tbody></table></div>
      </div>`;
  },

  async review() {
    const list = await api(T(`/api/admin/submissions?status=${reviewFilter}`));
    const F = { pending: 'На проверке', approved: 'Подтверждённые', rejected: 'Отклонённые', all: 'Все' };
    main.innerHTML = `${testNote()}<div class="row" style="margin-bottom:14px"><div class="seg">${Object.entries(F).map(([k, v]) => `<button data-f="${k}" class="${k === reviewFilter ? 'on' : ''}">${v}</button>`).join('')}</div>
      <a class="btn ghost sm" href="${T('/api/admin/answers.csv')}">⬇ Все творческие ответы (CSV)</a></div>
      ${list.length ? list.map((s) => `<div class="card sub" data-id="${s.id}">
        <div><div class="row"><b>${esc(s.name)}</b><span class="muted small">${s.format === 'office' ? '🏢 Офис' : '🏠 Удалённо'}</span>
          <span class="pill ${s.status === 'pending' ? 'review' : s.status === 'approved' ? 'done' : 'failed'}">${{ pending: 'на проверке', approved: 'подтверждено', rejected: 'отклонено' }[s.status]}</span></div>
          <div class="muted small">Задание ${s.taskId}. ${s.emoji} ${esc(s.taskTitle)} · отправлено ${esc(fmt(s.createdAt))} · ${s.consent ? '✅ согласен на показ в галерее' : '🔒 без согласия на показ'}</div>
          <div class="txt">${s.text ? esc(s.text) : '<span class="muted">(без текста)</span>'}</div>
          ${s.status === 'pending' ? `<div class="row"><input class="input cm" placeholder="Комментарий участнику (необязательно)" maxlength="500">
            <button class="btn green sm" data-act="approve">✓ Подтвердить</button><button class="btn red sm" data-act="reject">✕ Отклонить</button></div>`
            : `${s.comment ? `<div class="muted small">Комментарий: ${esc(s.comment)}</div>` : ''}${s.status === 'approved' ? '<button class="btn ghost sm" data-act="revoke" style="margin-top:8px">Отменить подтверждение</button>' : ''}`}
        </div>
        <div>${s.photo ? `<a href="${s.photo}" target="_blank" rel="noopener"><img src="${s.photo}" alt="Фото участника" loading="lazy"></a>` : '<div class="muted small">Без фото</div>'}</div>
      </div>`).join('') : '<div class="card empty">Здесь пока пусто 🎃</div>'}`;
    $$('.seg button', main).forEach((b) => b.addEventListener('click', () => { reviewFilter = b.dataset.f; render(); }));
    $$('[data-act]', main).forEach((b) => b.addEventListener('click', guard(async () => {
      const card = b.closest('.sub');
      const act = b.dataset.act;
      if (act === 'revoke' && !confirm('Отменить подтверждение? Баллы участника будут пересчитаны.')) return;
      const comment = act === 'revoke' ? prompt('Комментарий участнику (необязательно)', '') ?? '' : $('.cm', card).value;
      await post(`/api/admin/submissions/${card.dataset.id}/review`, { decision: act, comment });
      toast(act === 'approve' ? 'Подтверждено, баллы начислены' : act === 'reject' ? 'Отклонено — участник может отправить заново' : 'Подтверждение отменено', 'ok');
      render();
    })));
  },

  async players() {
    const list = await api(T('/api/admin/players'));
    main.innerHTML = `${testNote()}<div class="row" style="margin-bottom:12px"><h2 style="margin:0;margin-right:auto">Участники (${list.length})</h2>
      <a class="btn sm" href="${T('/api/admin/export.csv')}">⬇ Результаты в Excel (CSV)</a></div>
      <div class="card tbl-wrap"><table class="tbl"><thead><tr><th>#</th><th>Участник</th><th>Код</th><th>Формат</th><th>Поле</th><th class="n">Задания</th><th class="n">БИНГО</th><th class="n">Баллы</th><th>Был в игре</th><th></th></tr></thead>
      <tbody>${list.sort((a, b) => a.rank - b.rank).map((p) => `<tr><td>${p.rank}</td><td><b>${esc(p.name)}</b></td><td class="code small">${esc(p.code)}</td>
        <td>${p.format === 'office' ? '🏢' : '🏠'}</td>
        <td><div class="mini-board" title="Статусы клеток">${Array.from({ length: 16 }, (_, i) => `<i class="${p.statuses[i + 1] || ''}" title="${i + 1}: ${STATUS[p.statuses[i + 1] || 'not_started']}"></i>`).join('')}</div></td>
        <td class="n">${p.completed}</td><td class="n">${p.bingos}</td><td class="n amber"><b>${p.score}</b></td><td class="small muted">${esc(fmt(p.lastSeen))}</td>
        <td><button class="btn ghost sm" data-del="${p.id}" data-name="${esc(p.name)}">Удалить</button></td></tr>`).join('') || '<tr><td colspan="10" class="muted">Никто ещё не зарегистрировался</td></tr>'}</tbody></table></div>
      <p class="muted small">Удаление стирает профиль, ответы и фото участника. Код при этом остаётся — по нему можно зарегистрироваться заново.</p>`;
    $$('[data-del]', main).forEach((b) => b.addEventListener('click', guard(async () => {
      if (!confirm(`Удалить профиль «${b.dataset.name}» со всеми ответами?`)) return;
      await post(`/api/admin/players/${b.dataset.del}/delete`); render();
    })));
  },

  async codes() {
    const list = await api(T('/api/admin/codes'));
    const free = list.filter((c) => !c.name && !c.revoked).length;
    main.innerHTML = `${testNote()}<div class="card"><h2>🎟️ Игровые коды ${testMode ? '(тестовые)' : ''}</h2>
      <p class="muted">Каждый код — один игровой профиль. Выдайте по одному коду каждому участнику (личным сообщением). По коду можно войти с любого устройства.</p>
      <form class="row" id="gen"><input class="input" type="number" id="cnt" min="1" max="200" value="${testMode ? 3 : 50}" style="max-width:120px">
        <input class="input" id="note" placeholder="Пометка (например, отдел)" maxlength="100"><button class="btn">Создать коды</button></form>
      <div class="row" style="margin-top:12px"><a class="btn ghost sm" href="${T('/api/admin/codes.csv')}">⬇ Скачать список (CSV)</a>
        <button class="btn ghost sm" id="print">🖨 Карточки для печати</button><span class="muted small">Всего: ${list.length} · свободно: ${free}</span></div></div>
      <div class="card tbl-wrap"><table class="tbl"><thead><tr><th>Код</th><th>Пометка</th><th>Участник</th><th>Статус</th><th></th></tr></thead>
      <tbody>${list.map((c) => `<tr><td class="code">${esc(c.code)}</td><td class="small">${esc(c.note)}</td><td>${c.name ? esc(c.name) : '<span class="muted">—</span>'}</td>
        <td>${c.revoked ? '<span class="pill failed">отключён</span>' : c.name ? '<span class="pill done">используется</span>' : '<span class="pill">свободен</span>'}</td>
        <td class="row">${c.revoked ? `<button class="btn ghost sm" data-c="${esc(c.code)}" data-a="restore">Включить</button>` : `<button class="btn ghost sm" data-c="${esc(c.code)}" data-a="revoke">Отключить</button>`}
          <button class="btn ghost sm" data-c="${esc(c.code)}" data-a="delete">Удалить</button></td></tr>`).join('') || '<tr><td colspan="5" class="muted">Кодов пока нет</td></tr>'}</tbody></table></div>`;
    $('#gen').addEventListener('submit', guard(async (e) => {
      e.preventDefault();
      const r = await post('/api/admin/codes/generate', { count: $('#cnt').value, note: $('#note').value, test: testMode });
      toast(`Создано кодов: ${r.created.length}`, 'ok'); render();
    }));
    $$('[data-a]', main).forEach((b) => b.addEventListener('click', guard(async () => {
      const a = b.dataset.a;
      if (a === 'delete' && !confirm(`Удалить код ${b.dataset.c}? Профиль и ответы участника тоже будут удалены.`)) return;
      if (a === 'revoke' && !confirm(`Отключить код ${b.dataset.c}? Участник будет разлогинен и не сможет войти.`)) return;
      await post(`/api/admin/codes/${encodeURIComponent(b.dataset.c)}/${a}`); render();
    })));
    $('#print').addEventListener('click', () => {
      const w = window.open('', '_blank');
      if (!w) return toast('Разрешите всплывающие окна', 'bad');
      const items = list.filter((c) => !c.revoked).map((c) => `<div style="border:1px dashed #999;padding:14px;border-radius:8px;font-family:Arial">
        <div style="font-size:12px;color:#666">Миллор Групп · Секретная лаборатория 🎃</div>
        <div style="font:700 20px 'Courier New';margin:8px 0;letter-spacing:2px">${esc(c.code)}</div>
        <div style="font-size:12px">Вход: ${esc(location.origin)}</div>${c.note ? `<div style="font-size:11px;color:#666">${esc(c.note)}</div>` : ''}</div>`).join('');
      w.document.write(`<!doctype html><meta charset="utf-8"><title>Коды</title><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">${items}</div>`);
      w.document.close();
    });
  },

  async tasks() {
    const list = await api('/api/admin/tasks');
    main.innerHTML = `<div class="banner">✏️ Здесь можно изменить формулировки заданий. Правильные ответы и механика не меняются — они проверяются на сервере. Пустые поля — вернуть текст по умолчанию.</div>
      ${list.map((t) => `<div class="card task-edit" data-id="${t.id}"><div class="row"><b>${t.emoji} ${t.id}.</b>
        <span class="pill">${t.type === 'auto' ? 'авто · ' + t.kind : 'творческое · ' + (t.kind === 'photo' ? 'фото/текст' : 'текст')}</span>
        ${t.overridden ? '<span class="pill review">изменено</span>' : ''}<span class="key">Ответ: ${esc(t.answerKey)}</span></div>
        <label class="field"><span>Название</span><input class="input ti" value="${esc(t.title)}" maxlength="80"></label>
        <label class="field"><span>Описание</span><textarea class="input de" maxlength="3000">${esc(t.description)}</textarea></label>
        <div class="row"><button class="btn sm" data-save>Сохранить</button>${t.overridden ? '<button class="btn ghost sm" data-reset>Вернуть исходный текст</button>' : ''}</div></div>`).join('')}`;
    $$('.task-edit', main).forEach((card) => {
      $('[data-save]', card).addEventListener('click', guard(async () => {
        await post(`/api/admin/tasks/${card.dataset.id}`, { title: $('.ti', card).value, description: $('.de', card).value }); toast('Сохранено', 'ok'); render();
      }));
      const r = $('[data-reset]', card);
      if (r) r.addEventListener('click', guard(async () => { await post(`/api/admin/tasks/${card.dataset.id}`, { reset: true }); render(); }));
    });
  },

  async extra() {
    const list = await api(T('/api/admin/secrets'));
    const s = await api(T('/api/admin/stats'));
    main.innerHTML = `${testNote()}<div class="cols2"><div class="card"><h2>🗝️ Секретное задание дня</h2>
      <p class="muted">Короткая загадка для всех сразу. Появляется на поле у всех участников, пока активна. Не даёт баллов в основном рейтинге — победители отмечаются отдельно в Зале славы.</p>
      <form id="sf"><label class="field"><span>Загадка</span><textarea class="input" id="sq" maxlength="1000" placeholder="Что можно сломать, даже не прикоснувшись? (ответ — одно слово)"></textarea></label>
        <label class="field"><span>Правильные ответы (каждый с новой строки; регистр и «ё» не важны)</span><textarea class="input" id="sa" style="min-height:70px" placeholder="обещание"></textarea></label>
        <button class="btn">Добавить</button></form></div>
      <div class="card"><h2>🧟 Коллективная миссия</h2><p>Сейчас на сайте: «Сотрудники Миллор Групп уже победили <b class="amber">${s.completedTasks}</b> офисных монстров!»</p>
        <p class="muted">Считается автоматически по реально выполненным и подтверждённым заданиям всех участников.</p>
        <h2>🔮 Предсказания</h2><p class="muted">Участник получает случайное шуточное предсказание после каждого выполненного задания и после отправки творческого ответа. На баллы не влияют.</p></div></div>
      <div class="card"><h3>Загадки</h3>${list.length ? list.map((x) => `<div class="card" style="box-shadow:none" data-id="${x.id}">
        <div class="row"><b style="margin-right:auto">${esc(x.question)}</b>${x.active ? '<span class="pill done">активна</span>' : ''}</div>
        <div class="key">Ответы: ${x.answers.map(esc).join(' / ')}</div>
        <div class="muted small">Разгадали (${x.solvers.length}): ${x.solvers.map((p) => `${esc(p.name)} (${esc(fmt(p.solved_at))})`).join(', ') || '—'}</div>
        <div class="row" style="margin-top:8px">${x.active ? '<button class="btn sm red" data-a="deactivate">Остановить</button>' : '<button class="btn sm" data-a="activate">Запустить для всех</button>'}
          <button class="btn ghost sm" data-a="delete">Удалить</button></div></div>`).join('') : '<p class="muted">Загадок пока нет.</p>'}</div>`;
    $('#sf').addEventListener('submit', guard(async (e) => {
      e.preventDefault(); await post('/api/admin/secrets', { question: $('#sq').value, answers: $('#sa').value }); render();
    }));
    $$('[data-a]', main).forEach((b) => b.addEventListener('click', guard(async () => {
      if (b.dataset.a === 'delete' && !confirm('Удалить загадку?')) return;
      await post(`/api/admin/secrets/${b.closest('[data-id]').dataset.id}/${b.dataset.a}`); render();
    })));
  },

  async awards() {
    const a = await api('/api/admin/awards');
    const has = (c) => a.awards.find((x) => x.category === c);
    main.innerHTML = `<div class="banner">🏆 Награды определяются только среди <b>настоящих</b> участников. Один сотрудник — не более одного приза. Сначала 1–3 места, затем специальные номинации среди ещё не награждённых.</div>
      ${a.pending ? `<div class="banner warn">⏳ На проверке ещё <b>${a.pending}</b> ответ(ов). Жеребьёвку проводят после завершения проверки.</div>` : ''}
      <div class="cols2"><div class="card"><h2>Призёры</h2>
        <table class="tbl"><tbody>${Object.entries(a.prizes).map(([k, p]) => { const w = has(k); return `<tr><td>${esc(p.title)}</td><td class="n">${p.amount.toLocaleString('ru-RU')} ₽</td><td><b>${w ? esc(w.name) : '<span class="muted">—</span>'}</b></td></tr>`; }).join('')}</tbody></table>
        <div class="actions"><button class="btn" id="draw">🎲 Определить 1–3 места</button><button class="btn ghost" id="rnd">🎲 Случайный участник с БИНГО</button></div>
        <div class="row" style="margin-top:12px"><select class="input" id="cr"><option value="">— самый креативный участник —</option>${a.candidates.map((c) => `<option value="${c.id}">${esc(c.name)} (${c.score} б.)</option>`).join('')}</select><button class="btn sm" id="crb">Назначить</button></div>
        <label class="check" style="margin-top:14px"><input type="checkbox" id="sw" ${a.showWinners ? 'checked' : ''}><span>Показать победителей участникам в Зале славы</span></label>
        <button class="btn ghost sm" id="reset">Сбросить все награды</button></div>
      <div class="card"><h2>Журнал жеребьёвки</h2><p class="muted small">Каждое решение записывается с московским временем — его можно показать участникам для прозрачности.</p>
        <div class="log">${a.log.length ? a.log.slice().reverse().map((l) => `<div><span class="muted small">${esc(l.atMsk)}</span><br>${esc(l.text)}</div>`).join('') : '<span class="muted">Пока пусто</span>'}</div></div></div>`;
    $('#draw').addEventListener('click', guard(async () => {
      if (!confirm('Определить призёров 1–3 мест? Равные баллы разрешатся случайной жеребьёвкой. Специальные номинации будут сброшены.')) return;
      try { await post('/api/admin/awards/draw-top'); } catch (e) {
        if (/проверьте/.test(e.message) && confirm(e.message + '\n\nВсё равно провести?')) await post('/api/admin/awards/draw-top', { force: true }); else throw e;
      }
      render();
    }));
    $('#rnd').addEventListener('click', guard(async () => { const r = await post('/api/admin/awards/random-bingo'); toast(`Победитель: ${esc(r.winner)}`, 'ok'); render(); }));
    $('#crb').addEventListener('click', guard(async () => { if (!$('#cr').value) return; await post('/api/admin/awards/creative', { playerId: $('#cr').value }); render(); }));
    $('#sw').addEventListener('change', guard(async (e) => { await post('/api/admin/settings', { showWinners: e.target.checked }); toast('Сохранено', 'ok'); }));
    $('#reset').addEventListener('click', guard(async () => { if (confirm('Сбросить все награды?')) { await post('/api/admin/awards/reset'); render(); } }));
  },

  async settings() {
    const s = await api('/api/admin/settings');
    const g = s.game;
    main.innerHTML = `<div class="cols2">
      <div class="card"><h2>🕰 Время игры (МСК)</h2>
        <form id="tf"><label class="field"><span>Начало</span><input class="input" type="datetime-local" id="ts" value="${isoToMskInput(g.start)}" required></label>
        <label class="field"><span>Окончание</span><input class="input" type="datetime-local" id="te" value="${isoToMskInput(g.end)}" required></label>
        <button class="btn">Сохранить время</button></form>
        <h3 style="margin-top:20px">Запуск и остановка</h3>
        <div class="seg" id="mode">${[['schedule', '⏱ По расписанию'], ['open', '▶ Открыть сейчас'], ['closed', '⏸ Остановить']].map(([k, v]) => `<button data-m="${k}" class="${g.mode === k ? 'on' : ''}">${v}</button>`).join('')}</div>
        <p class="muted small">«По расписанию» — игра сама откроется и закроется по времени выше. Тестовые участники играют всегда.</p></div>
      <div class="card"><h2>🖼 Логотип компании</h2>
        <p class="muted">Загрузите официальный логотип Миллор Групп (PNG / JPEG / WebP, до 1 МБ, лучше на прозрачном фоне). Пока логотипа нет, показывается текстовое название.</p>
        ${s.logo ? `<img src="${s.logo}?t=${Date.now()}" alt="Логотип" style="max-height:70px;background:#fff1;padding:8px;border-radius:8px">` : ''}
        <div class="row" style="margin-top:10px"><input type="file" id="logo" accept="image/png,image/jpeg,image/webp">${s.logo ? '<button class="btn ghost sm" id="rmlogo">Удалить</button>' : ''}</div></div>
    </div>
    <div class="card"><h2>🧪 Демонстрационный режим</h2>
      <p>Тестовые участники играют вне расписания, не попадают в настоящий рейтинг, статистику и награды. Их данные видны в пульте при включённой галочке «Тестовые данные».</p>
      <ol class="muted"><li>Создайте тестовые коды кнопкой ниже.</li><li>Откройте игру на нескольких устройствах (телефон, ноутбук) и войдите разными кодами.</li>
        <li>Пройдите задания, отправьте фото и тексты, одобрите их во вкладке «Проверка» (с галочкой «Тестовые данные»).</li><li>Перед запуском нажмите «Очистить тестовые данные».</li></ol>
      <div class="row"><button class="btn" id="mk">Создать 3 тестовых кода</button><button class="btn ghost" id="clr">Очистить тестовые данные</button></div>
      <div id="new-codes"></div></div>
    <div class="card danger"><h2>🗑 Удаление данных после мероприятия</h2>
      <p>Безвозвратно удаляет всех участников, ответы, фотографии, загадки и награды. Перед удалением выгрузите результаты в CSV (вкладка «Участники»).</p>
      <label class="check"><input type="checkbox" id="wc"><span>Удалить также игровые коды</span></label>
      <div class="row"><input class="input" id="wconf" placeholder="Введите слово УДАЛИТЬ" style="max-width:260px"><button class="btn red" id="wipe">Удалить все игровые данные</button></div></div>`;
    $('#tf').addEventListener('submit', guard(async (e) => {
      e.preventDefault();
      await post('/api/admin/settings', { gameStart: mskInputToIso($('#ts').value), gameEnd: mskInputToIso($('#te').value) }); toast('Время сохранено', 'ok'); render();
    }));
    $$('#mode button').forEach((b) => b.addEventListener('click', guard(async () => {
      if (b.dataset.m === 'closed' && !confirm('Остановить игру для всех участников? Ответы перестанут приниматься.')) return;
      await post('/api/admin/settings', { mode: b.dataset.m }); toast('Режим изменён', 'ok'); render();
    })));
    $('#logo').addEventListener('change', guard(async (e) => {
      const f = e.target.files[0]; if (!f) return;
      if (f.size > 1024 * 1024) throw new Error('Файл больше 1 МБ');
      const data = await new Promise((ok, fail) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = fail; r.readAsDataURL(f); });
      await post('/api/admin/logo', { image: data }); toast('Логотип загружен', 'ok'); render();
    }));
    const rm = $('#rmlogo'); if (rm) rm.addEventListener('click', guard(async () => { await post('/api/admin/logo', { remove: true }); render(); }));
    $('#mk').addEventListener('click', guard(async () => {
      const r = await post('/api/admin/demo/create', { count: 3 });
      $('#new-codes').innerHTML = `<p>Тестовые коды: ${r.created.map((c) => `<b class="code">${esc(c)}</b>`).join(' · ')}</p>`;
    }));
    $('#clr').addEventListener('click', guard(async () => {
      if (!confirm('Удалить всех тестовых участников, их ответы, фото и тестовые коды?')) return;
      await post('/api/admin/demo/clear'); toast('Тестовые данные удалены', 'ok');
    }));
    $('#wipe').addEventListener('click', guard(async () => {
      if (!confirm('Точно удалить ВСЕ игровые данные? Это необратимо.')) return;
      await post('/api/admin/wipe', { confirm: $('#wconf').value.trim(), codes: $('#wc').checked }); toast('Данные удалены', 'ok'); render();
    }));
  },
};

init().catch((e) => { main.textContent = e.message; });
