'use strict';
// Сквозные тесты через HTTP. Номера «Сценарий N» соответствуют критериям готовности из ТЗ.
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const DATA = fs.mkdtempSync(path.join(os.tmpdir(), 'mp-test-'));
process.env.DATA_DIR = DATA;
process.env.ADMIN_EMAIL = 'Organizer@Example.ru';
process.env.TRUST_PROXY = '1';
const { server } = require('../server');
const T = require('../tasks');
let base;
before(() => new Promise((ok) => server.listen(0, '127.0.0.1', () => { base = `http://127.0.0.1:${server.address().port}`; ok(); })));
after(() => { server.close(); fs.rmSync(DATA, { recursive: true, force: true }); });

function client(scope) {
  const jar = {};
  const call = async (method, p, body, extra = {}) => {
    const res = await fetch(base + p, {
      method, headers: { ...(body && !extra.raw ? { 'Content-Type': 'application/json' } : {}), ...(scope ? { 'X-Scope': scope } : {}), ...(extra.headers || {}), Cookie: Object.entries(jar).map(([k, v]) => `${k}=${v}`).join('; ') },
      body: extra.raw ? body : body ? JSON.stringify(body) : undefined,
    });
    for (const c of res.headers.getSetCookie()) { const [kv] = c.split(';'); const i = kv.indexOf('='); const k = kv.slice(0, i), v = kv.slice(i + 1); if (v) jar[k] = v; else delete jar[k]; }
    const type = res.headers.get('content-type') || '';
    const data = type.includes('json') ? await res.json() : Buffer.from(await res.arrayBuffer());
    return { status: res.status, data, headers: res.headers };
  };
  return { get: (p, h) => call('GET', p, null, { headers: h }), post: (p, b = {}, h) => call('POST', p, b, { headers: h }), raw: (p, buf, headers) => call('POST', p, buf, { raw: true, headers }), jar };
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
const PNG_PAD = Buffer.concat([PNG, Buffer.alloc(200)]);

let admin, adminT, testNames;
const PIN = '4821';
async function newPlayer(name, format = 'office') {
  const c = client();
  const r = await c.post('/api/register', { name, format, pin: PIN });
  assert.equal(r.status, 200, JSON.stringify(r.data));
  return c;
}
async function loginAs(name, pin = PIN) { const c = client(); const r = await c.post('/api/login', { name, pin }); assert.equal(r.status, 200, JSON.stringify(r.data)); return c; }
const setPts = (c, playerId, taskId, points) => c.post('/api/admin/adjust', { playerId, taskId, points, reason: 'тест' });
const me = async (c) => (await c.get('/api/me')).data;
async function idOf(name, a = admin) { return (await a.get('/api/admin/players')).data.find((p) => p.name === name).id; }

test('Сценарий 10: настройка администратора, вход, отказ обычным пользователям', async () => {
  const anon = client();
  assert.equal((await anon.get('/api/admin/dashboard')).status, 401);
  assert.equal((await anon.get('/api/admin/export.csv')).status, 401);
  const st = (await anon.get('/api/admin/status')).data;
  assert.deepEqual(st, { configured: true, hasPassword: false });
  const token = fs.readFileSync(path.join(DATA, 'admin-setup.txt'), 'utf8').trim().split(': ')[1];
  assert.equal((await anon.post('/api/admin/login', { email: 'organizer@example.ru', password: 'whatever-whatever' })).status, 401, 'до настройки пароля войти нельзя');
  assert.equal((await anon.post('/api/admin/setup', { email: 'organizer@example.ru', token: 'bad', password: 'a-long-password-1' })).status, 401);
  assert.equal((await anon.post('/api/admin/setup', { email: 'other@example.ru', token, password: 'a-long-password-1' })).status, 401, 'чужая почта');
  assert.equal((await anon.post('/api/admin/setup', { email: 'organizer@example.ru', token, password: 'short' })).status, 400);
  assert.equal((await anon.post('/api/admin/setup', { email: 'ORGANIZER@example.ru', token, password: 'a-long-password-1' })).status, 200);
  assert.equal((await anon.post('/api/admin/setup', { email: 'organizer@example.ru', token, password: 'another-password-2' })).status, 409, 'повторная настройка закрыта');
  assert.ok(!fs.existsSync(path.join(DATA, 'admin-setup.txt')));
  admin = client();
  assert.equal((await admin.post('/api/admin/login', { email: 'organizer@example.ru', password: 'wrong-password-123' })).status, 401);
  assert.equal((await admin.post('/api/admin/login', { email: 'organizer@example.ru', password: 'a-long-password-1' })).status, 200);
  adminT = client('test');
  await adminT.post('/api/admin/login', { email: 'organizer@example.ru', password: 'a-long-password-1' });
  assert.equal((await admin.get('/api/admin/dashboard')).status, 200);
});

test('Регистрация: имя + свой PIN из 4 цифр; вход с другого устройства; имя занято', async () => {
  const a = client();
  assert.equal((await a.post('/api/register', { name: 'Анна Смирнова', format: 'office', pin: '12' })).status, 400, 'PIN — ровно 4 цифры');
  assert.equal((await a.post('/api/register', { name: 'Анна Смирнова', format: 'office', pin: 'abcd' })).status, 400);
  assert.equal((await a.post('/api/register', { name: 'А', format: 'office', pin: PIN })).status, 400);
  assert.equal((await a.post('/api/register', { name: 'Анна Смирнова', pin: PIN })).status, 400, 'нужно место работы');
  assert.equal((await a.post('/api/register', { name: 'Анна Смирнова', format: 'office', pin: PIN })).status, 200);
  assert.equal((await me(a)).player.name, 'Анна Смирнова', 'после регистрации сессия открыта');
  // имя занято (регистр, лишние пробелы и «ё» не важны)
  assert.equal((await client().post('/api/register', { name: '  анна   СМИРНОВА ', format: 'remote', pin: '0000' })).status, 409);
  // другое устройство: имя + PIN → тот же профиль
  const b = await loginAs('анна смирнова');
  assert.equal((await me(b)).player.name, 'Анна Смирнова');
  assert.equal((await client().post('/api/login', { name: 'Анна Смирнова', pin: '0000' })).status, 401, 'чужой PIN не подходит');
  assert.equal((await client().post('/api/login', { name: 'Никто Никакой', pin: PIN })).status, 401);
  assert.equal((await client().get('/api/me')).status, 401);
  assert.equal((await admin.get('/api/admin/players')).data.length, 1, 'один человек — один профиль');
  const { db } = require('../server');
  assert.ok(!JSON.stringify(db.prepare('SELECT * FROM players').all()).includes(PIN), 'PIN хранится только в виде хэша');
});

test('Подбор PIN ограничен: 5 ошибок блокируют вход на 10 минут; организатор сбрасывает PIN', async () => {
  await newPlayer('Борис Блокировка');
  const c = client();
  for (let i = 1; i <= 4; i++) { const r = await c.post('/api/login', { name: 'Борис Блокировка', pin: '0000' }); assert.equal(r.status, 401); assert.match(r.data.error, new RegExp(`Осталось попыток: ${5 - i}`)); }
  assert.equal((await c.post('/api/login', { name: 'Борис Блокировка', pin: '0000' })).status, 401);
  const locked = await c.post('/api/login', { name: 'Борис Блокировка', pin: PIN });
  assert.equal(locked.status, 429, 'даже верный PIN в период блокировки не принимается');
  // организатор сбрасывает PIN: игрок задаёт новый при следующем входе, прогресс остаётся
  const id = await idOf('Борис Блокировка');
  assert.equal((await adminT.post(`/api/admin/players/${id}/reset-pin`)).status, 409, 'тестовая роль не трогает реальных игроков');
  assert.equal((await admin.post(`/api/admin/players/${id}/reset-pin`)).status, 200);
  const fresh = client();
  assert.equal((await fresh.post('/api/login', { name: 'Борис Блокировка', pin: '7777' })).status, 200, 'новый PIN задан при входе');
  assert.equal((await client().post('/api/login', { name: 'Борис Блокировка', pin: PIN })).status, 401, 'старый PIN больше не работает');
  assert.equal((await loginAs('Борис Блокировка', '7777') && 1), 1);
  // защита от перебора имён с одного адреса
  const h = { 'X-Forwarded-For': '203.0.113.9' }; let last;
  for (let i = 0; i < 61; i++) last = await client().post('/api/login', { name: 'Нет Такого ' + i, pin: PIN }, h);
  assert.equal(last.status, 429);
  assert.equal((await client().post('/api/login', { name: 'Анна Смирнова', pin: PIN }, h)).status, 429, 'адрес временно закрыт');
  assert.equal((await client().post('/api/login', { name: 'Анна Смирнова', pin: PIN }, { 'X-Forwarded-For': '203.0.113.10' })).status, 200);
});

test('Тестовые участники создаются организатором и входят по имени и PIN 1234', async () => {
  const r = await adminT.post('/api/admin/demo/create', { count: 3 });
  testNames = r.data.created.map((x) => x.name);
  assert.deepEqual(testNames, ['Тест Участник 1', 'Тест Участник 2', 'Тест Участник 3']);
  assert.equal((await client().post('/api/login', { name: testNames[0], pin: '1234' })).status, 200);
  assert.equal((await adminT.get('/api/admin/players')).data.length, 3);
  assert.equal((await admin.get('/api/admin/players')).data.some((p) => /Тест Участник/.test(p.name)), false);
});

test('Игра не началась: настоящие участники закрыты, тестовые играют', async () => {
  const a = await loginAs('Анна Смирнова');
  assert.equal((await a.get('/api/tasks/15')).status, 423);
  const t = await loginAs(testNames[0], '1234');
  assert.equal((await t.get('/api/tasks/15')).status, 200);
  assert.equal((await t.post('/api/tasks/15/start')).status, 200);
  const m = await me(t);
  assert.deepEqual(m.cells.map((c) => c.id), [16, 2, 12, 7, 5, 10, 8, 11, 3, 1, 6, 9, 15, 14, 4, 13]);
});

test('Ключи ответов не уходят клиенту', async () => {
  const t = await loginAs(testNames[1], '1234');
  const hidden = { 3: ['реглисам'], 7: ['1023'], 12: ['ТЫКВА', 'ПРИЗРАК', 'ЗОМБИ'] };
  for (const id of [1, 3, 4, 6, 7, 9, 10, 12, 13, 15]) {
    const before = JSON.stringify((await t.get(`/api/tasks/${id}`)).data);
    await t.post(`/api/tasks/${id}/start`);
    const during = JSON.stringify((await t.get(`/api/tasks/${id}`)).data);
    for (const w of hidden[id] || []) { assert.ok(!before.toLowerCase().includes(w.toLowerCase()) && !during.toLowerCase().includes(w.toLowerCase()), `задание ${id} раскрывает «${w}»`); }
    assert.ok(!/"secret"|"answerKey"/.test(before + during), `задание ${id}`);
  }
  const v10 = JSON.stringify((await t.get('/api/tasks/10')).data);
  assert.ok(!v10.includes('"c":'));
  const v3 = (await t.get('/api/tasks/3')).data;
  assert.equal(v3.active.view.code, '1864131019114'); assert.equal(v3.active.view.hint, null);
  assert.ok(!JSON.stringify(v3).includes('18-6-4'));
  const v6 = JSON.stringify((await t.get('/api/tasks/6')).data);
  assert.ok(!/culprit|"thief"/.test(v6.replace('"culprit":null', '')));
});

test('Запуск игры организатором, пауза, возобновление', async () => {
  const a = await loginAs('Анна Смирнова');
  assert.equal((await admin.post('/api/admin/game', { action: 'start' })).data.game.phase, 'running');
  assert.equal((await a.get('/api/tasks/15')).status, 200);
  await admin.post('/api/admin/game', { action: 'pause' });
  assert.equal((await a.post('/api/tasks/15/start')).status, 423, 'новые попытки на паузе закрыты');
  await admin.post('/api/admin/game', { action: 'resume' });
  assert.equal((await a.post('/api/tasks/15/start')).status, 200);
});

test('Сценарий 1+2+3: прогресс сохраняется; 6 → 10−2 = 8; третья попытка невозможна', async () => {
  const p = await newPlayer('Борис Попытки', 'remote');
  const start = await p.post('/api/tasks/15/start');
  assert.equal(start.data.task.attempts.used, 1);
  // 6 из 8 пустых клеток верно, без бонуса за полную таблицу
  const sol = [1, 2, 3, 4, 3, 4, 1, 2, 2, 1, 4, 3, 4, 3, 2, 1];
  const given = [1, 2, 0, 0, 3, 4, 0, 0, 0, 0, 4, 3, 0, 0, 2, 1];
  const cells = sol.map((v, i) => (given[i] ? given[i] : v));
  let wrong = 0; cells.forEach((v, i) => { if (!given[i] && wrong < 2) { cells[i] = 0; wrong++; } });
  assert.equal((await p.post('/api/tasks/15/act', { action: 'save', cells })).status, 200);
  // «обновили страницу»: попытка и введённые значения на месте
  const again = (await p.get('/api/tasks/15')).data;
  assert.equal(again.active.n, 1); assert.deepEqual(again.active.view.cells, cells);
  const fin = await p.post('/api/tasks/15/act', { action: 'finish' });
  assert.equal(fin.data.result.final, 6);
  assert.equal(fin.data.task.attempts.decide, true);
  assert.equal(fin.data.task.attempts.left, 1);
  // вторая попытка: полностью верно → raw 10, итог 8, лучший = max(6, 8) = 8
  assert.equal((await p.post('/api/tasks/15/start')).data.task.active.n, 2);
  const f2 = await p.post('/api/tasks/15/act', { action: 'finish', data: { cells: sol } });
  assert.equal(f2.data.result.raw, 10); assert.equal(f2.data.result.final, 8); assert.equal(f2.data.result.best, 8);
  assert.equal(f2.data.task.points, 8); assert.equal(f2.data.task.attempts.closed, true);
  assert.equal((await p.post('/api/tasks/15/start')).status, 409, 'третья попытка отклонена');
  assert.equal((await p.post('/api/tasks/15/act', { action: 'finish' })).data.result, null, 'повторная отправка ничего не меняет');
  assert.equal((await me(p)).total, 8);
  // вторая попытка хуже первой не уменьшает результат
  const q = await newPlayer('Вера Лучшая');
  await q.post('/api/tasks/15/start'); await q.post('/api/tasks/15/act', { action: 'finish', data: { cells: sol } });
  assert.equal((await me(q)).total, 10, 'первая попытка на 10 закрывает задание');
  assert.equal((await q.post('/api/tasks/15/start')).status, 409);
  const w = await newPlayer('Глеб Оставил');
  await w.post('/api/tasks/15/start'); const f = await w.post('/api/tasks/15/act', { action: 'finish', data: { cells: cells } });
  assert.equal(f.data.result.final, 6);
  assert.equal((await w.post('/api/tasks/15/keep')).data.task.attempts.closed, true, '«Оставить результат» закрывает задание');
  assert.equal((await w.post('/api/tasks/15/start')).status, 409);
});

test('Сценарий 4: подсказка в № 3 и штрафы, включая вторую попытку', async () => {
  const p = await newPlayer('Дарья Шифр');
  await p.post('/api/tasks/3/start');
  const hint = await p.post('/api/tasks/3/act', { action: 'hint' });
  assert.match(hint.data.task.active.view.hint, /порядковые номера букв русского алфавита/);
  const f1 = await p.post('/api/tasks/3/act', { action: 'finish', data: { name: 'реглисам', split: '18–6–4–13–10–19–1–14' } });
  assert.equal(f1.data.result.raw, 5, '10 − 5 за подсказку'); assert.equal(f1.data.result.final, 5);
  // подсказка запомнена: на второй попытке штраф действует снова, плюс −2
  const s2 = await p.post('/api/tasks/3/start');
  assert.ok(s2.data.task.active.view.hint, 'подсказка остаётся открытой');
  const f2 = await p.post('/api/tasks/3/act', { action: 'finish', data: { name: 'Реглисам', split: '18 6 4 13 10 19 1 14' } });
  assert.equal(f2.data.result.raw, 5); assert.equal(f2.data.result.final, 3); assert.equal(f2.data.result.best, 5, 'сохраняется лучший');
  // без подсказки: имя без разбивки = 5; верно всё = 10; неверное имя = 0
  const q = await newPlayer('Егор Без Подсказки');
  await q.post('/api/tasks/3/start');
  assert.equal((await q.post('/api/tasks/3/act', { action: 'finish', data: { name: 'РЕГЛИСАМ', split: '1,2,3' } })).data.result.final, 5);
  await q.post('/api/tasks/3/start');
  assert.equal((await q.post('/api/tasks/3/act', { action: 'finish', data: { name: 'Фламин', split: '' } })).data.result.final, 0);
  // подсказка только во второй попытке
  const r = await newPlayer('Жанна Поздняя');
  await r.post('/api/tasks/3/start');
  assert.equal((await r.post('/api/tasks/3/act', { action: 'finish', data: { name: 'Реглисам', split: '1' } })).data.result.final, 5);
  await r.post('/api/tasks/3/start'); await r.post('/api/tasks/3/act', { action: 'hint' });
  const f = await r.post('/api/tasks/3/act', { action: 'finish', data: { name: 'Реглисам', split: '18-6-4-13-10-19-1-14' } });
  assert.equal(f.data.result.raw, 5); assert.equal(f.data.result.final, 3);
  // результат не может уйти ниже нуля
  const z = await newPlayer('Зоя Ноль');
  await z.post('/api/tasks/3/start'); await z.post('/api/tasks/3/act', { action: 'hint' });
  assert.equal((await z.post('/api/tasks/3/act', { action: 'finish', data: { name: 'xx', split: '' } })).data.result.final, 0);
});

test('Сценарии 5 и 6: БИНГО только при ≥ 8 в каждой из четырёх клеток; ровно +30', async () => {
  const p = await newPlayer('Игорь Линии');
  const id = await idOf('Игорь Линии');
  // строка 1 поля: задания 16, 2, 12, 7
  for (const [t, v] of [[16, 8], [2, 9], [12, 10]]) assert.equal((await setPts(admin, id, t, v)).status, 200);
  assert.equal((await me(p)).bingos, 0, 'три клетки — не БИНГО');
  assert.equal((await me(p)).nextBingo, 1);
  await setPts(admin, id, 7, 8);
  let m = await me(p);
  assert.equal(m.bingos, 1); assert.equal(m.total, 8 + 9 + 10 + 8 + 30, 'ровно +30');
  assert.deepEqual(m.lines.filter((l) => l.complete).map((l) => l.idx), [0]);
  // 10, 7, 10, 10 — не засчитывается
  await setPts(admin, id, 9, 0); // служебное
  const q = await newPlayer('Кира Семёрка');
  const qid = await idOf('Кира Семёрка');
  for (const [t, v] of [[5, 10], [10, 7], [8, 10], [11, 10]]) await setPts(admin, qid, t, v);
  m = await me(q);
  assert.equal(m.bingos, 0); assert.equal(m.total, 37);
  assert.equal(m.nextBingo, 1);
  // повышаем 7 → 8: линия появляется; снижаем → пропадает; повторный пересчёт не дублирует бонус
  await setPts(admin, qid, 10, 8); assert.equal((await me(q)).total, 38 + 30);
  await setPts(admin, qid, 10, 8); assert.equal((await me(q)).total, 38 + 30);
  await setPts(admin, qid, 10, 7); assert.equal((await me(q)).total, 37);
});

test('Все 10 линий: 4 строки, 4 столбца, 2 диагонали, максимум 460', async () => {
  const p = await newPlayer('Максим Максимум');
  const id = await idOf('Максим Максимум');
  for (let t = 1; t <= 16; t++) await setPts(admin, id, t, 10);
  const m = await me(p);
  assert.equal(m.bingos, 10); assert.equal(m.total, 460);
  for (const line of T.LINES) assert.equal(line.length, 4);
  const set = new Set(T.LINES.map((l) => l.join(',')));
  assert.equal(set.size, 10);
  // диагонали по позициям поля
  assert.deepEqual(T.LINES[8], [16, 10, 6, 13]); assert.deepEqual(T.LINES[9], [7, 8, 1, 15]);
});

test('Сценарии 7 и 8: творческое задание — проверка по критериям, баллы, рейтинг, пересчёт', async () => {
  const p = await newPlayer('Лена Творец');
  const lid = await idOf('Лена Творец');
  const v0 = (await p.get('/api/tasks/16')).data;
  assert.equal(v0.creative.criteria.reduce((a, c) => a + c.pts, 0), 10);
  assert.equal((await p.post('/api/tasks/16/submit', { data: { name: 'Пятницин' } })).status, 400, 'нужны все поля');
  assert.equal((await p.post('/api/tasks/16/draft', { data: { name: 'Пятницин', i1: 'Две капли премии' } })).status, 200);
  assert.equal((await p.get('/api/tasks/16')).data.creative.draft.data.name, 'Пятницин');
  const full = { name: 'Пятницин', i1: 'Две капли премии', i2: 'Щепотка отменённых созвонов', i3: '100 мл тишины в почте', effect: 'Встречи после 16:00 исчезают' };
  const sub = await p.post('/api/tasks/16/submit', { data: full });
  assert.equal(sub.data.task.creative.submission.status, 'pending');
  assert.equal((await p.post('/api/tasks/16/submit', { data: full })).status, 409, 'повторная отправка заблокирована');
  assert.equal((await p.post('/api/tasks/16/draft', { data: full })).status, 409);
  assert.equal((await me(p)).total, 0, 'до подтверждения баллов нет');
  const queue = (await admin.get('/api/admin/submissions?status=pending')).data;
  const s = queue.find((x) => x.name === 'Лена Творец');
  assert.equal(s.criteria.length, 5);
  // организатор: возвращает на доработку → одно исправление
  assert.equal((await admin.post(`/api/admin/submissions/${s.id}/review`, { decision: 'return', comment: 'Добавь юмора' })).status, 200);
  const back = (await p.get('/api/tasks/16')).data;
  assert.equal(back.creative.submission.status, 'returned'); assert.equal(back.creative.submission.comment, 'Добавь юмора'); assert.equal(back.creative.canEdit, true);
  const re = await p.post('/api/tasks/16/submit', { data: { ...full, effect: 'Все созвоны отменены навсегда' } });
  assert.equal(re.data.task.creative.submission.revision, 1);
  const s2 = (await admin.get('/api/admin/submissions?status=pending')).data.find((x) => x.name === 'Лена Творец');
  assert.equal((await admin.post(`/api/admin/submissions/${s2.id}/review`, { decision: 'return' })).status, 409, 'второй возврат запрещён');
  // подтверждает 4 критерия из 5 → 8 баллов
  const ok = await admin.post(`/api/admin/submissions/${s2.id}/review`, { decision: 'approve', criteria: ['name', 'i1', 'i2', 'effect'], comment: 'Хорошо' });
  assert.equal(ok.data.points, 8);
  assert.equal((await admin.post(`/api/admin/submissions/${s2.id}/review`, { decision: 'approve', criteria: ['name'] })).status, 409, 'нельзя начислить дважды');
  let m = await me(p);
  assert.equal(m.total, 8); assert.equal(m.cells.find((c) => c.id === 16).state, 'good');
  assert.equal((await p.get('/api/leaderboard')).data.rows.find((r) => r.name === 'Лена Творец').total, 8);
  assert.equal((await p.post('/api/tasks/16/submit', { data: full })).status, 409, 'после подтверждения задание закрыто');
  // корректировка оценки и её история
  assert.equal((await admin.post('/api/admin/adjust', { playerId: lid, taskId: 16, points: 10 })).status, 400, 'нужна причина');
  await setPts(admin, lid, 16, 10);
  assert.equal((await me(p)).total, 10);
  await admin.post('/api/admin/adjust', { playerId: lid, taskId: 16, points: null, reason: 'снимаю корректировку' });
  assert.equal((await me(p)).total, 8);
  const log = (await admin.get('/api/admin/log')).data;
  assert.ok(log.some((l) => /Подтверждено: 8/.test(l.note)) && log.some((l) => /Корректировка/.test(l.note)));
  // отклонение закрывает задание с нулём
  const r = await newPlayer('Макар Отклонён');
  await r.post('/api/tasks/14/submit', { data: { title: 'Чат', m1: 'раз', m2: 'два', m3: 'три' } });
  const rs = (await admin.get('/api/admin/submissions?status=pending')).data.find((x) => x.name === 'Макар Отклонён');
  await admin.post(`/api/admin/submissions/${rs.id}/review`, { decision: 'reject', comment: 'Не по теме' });
  assert.equal((await me(r)).cells.find((c) => c.id === 14).state, 'rejected');
  assert.equal((await r.post('/api/tasks/14/submit', { data: { title: 'Чат', m1: 'раз', m2: 'два', m3: 'три' } })).status, 409);
});

test('Приватные загрузки: фото и видео; чужие и посторонние не видят', async () => {
  const p = await newPlayer('Фёдор Фото');
  const h = { 'x-requested-with': 'mgp', 'content-type': 'application/octet-stream' };
  assert.equal((await p.raw('/api/uploads?kind=image', PNG_PAD, {})).status, 403, 'нужен служебный заголовок');
  const up = await p.raw('/api/uploads?kind=image', PNG_PAD, h);
  assert.equal(up.status, 200);
  assert.equal((await p.raw('/api/uploads?kind=image', Buffer.from('<svg onload=alert(1)>'.repeat(20)), h)).status, 400);
  assert.equal((await p.raw('/api/uploads?kind=image', Buffer.concat([Buffer.from([0xff, 0xd8, 0xff]), Buffer.alloc(6.5 * 1024 * 1024)]), h)).status, 413);
  const mp4 = Buffer.concat([Buffer.from([0, 0, 0, 0x18]), Buffer.from('ftypmp42'), Buffer.alloc(5000, 7)]);
  const vid = await p.raw('/api/uploads?kind=video', mp4, h);
  assert.equal(vid.status, 200); assert.equal(vid.data.mime, 'video/mp4');
  assert.equal((await p.raw('/api/uploads?kind=image', mp4, h)).status, 400, 'видео как фото не принимается');
  // задание 5 принимает только фото, 11 — фото или видео
  assert.equal((await p.post('/api/tasks/5/submit', { data: { note: '' }, media: [vid.data.id] })).status, 400);
  assert.equal((await p.post('/api/tasks/5/submit', { data: { note: '' }, media: [] })).status, 400, 'нужно фото или описание');
  assert.equal((await p.post('/api/tasks/5/submit', { data: { note: 'Апельсин, мандарин, тыква' }, media: [up.data.id] })).status, 200);
  assert.equal((await p.post('/api/tasks/11/submit', { data: { character: 'Вампир отчётов', note: '' }, media: [vid.data.id] })).status, 200);
  // доступ
  assert.equal((await p.get(up.data.url)).status, 200);
  assert.equal((await client().get(up.data.url)).status, 403);
  const other = await newPlayer('Чужой Игрок');
  assert.equal((await other.get(up.data.url)).status, 403);
  assert.equal((await other.post('/api/tasks/5/submit', { data: { note: 'x'.repeat(12) }, media: [up.data.id] })).status, 400, 'чужой файл прикрепить нельзя');
  assert.equal((await admin.get(up.data.url)).status, 200);
  const rng = await admin.get(vid.data.url, { Range: 'bytes=0-99' });
  assert.equal(rng.status, 206); assert.equal(rng.data.length, 100);
  assert.match(rng.headers.get('content-range'), /^bytes 0-99\/\d+$/);
});

test('Автоигры: № 4 привидения, № 6, № 7, № 12, № 13 — частичные баллы и проверка на сервере', async () => {
  // № 4
  const a = await newPlayer('Анатолий Охотник');
  await a.post('/api/tasks/4/start');
  let r;
  for (const g of T.GHOSTS.slice(0, 3)) r = await a.post('/api/tasks/4/act', { action: 'click', x: g.x + 5, y: g.y - 5 });
  assert.equal(r.data.task.active.view.found.length, 3);
  assert.equal((await a.post('/api/tasks/4/act', { action: 'click', x: T.GHOSTS[0].x, y: T.GHOSTS[0].y })).data.task.active.view.wrong, 0, 'повторное нажатие на найденное — не ошибка');
  for (let i = 0; i < 10; i++) r = await a.post('/api/tasks/4/act', { action: 'click', x: 5, y: 495 });
  assert.equal(r.data.result.raw, 6, '3 привидения × 2, раунд закончен десятой ошибкой');
  assert.equal((await me(a)).cells.find((c) => c.id === 4).points, 6);
  const b = await newPlayer('Борис Полный');
  await b.post('/api/tasks/4/start');
  for (const g of T.GHOSTS) r = await b.post('/api/tasks/4/act', { action: 'click', x: g.x, y: g.y });
  assert.equal(r.data.result.final, 10); assert.equal(r.data.task.attempts.closed, true);
  // № 6
  const d = await newPlayer('Денис Детектив');
  await d.post('/api/tasks/6/start');
  await d.post('/api/tasks/6/act', { action: 'save', order: ['ghost', 'witch', 'vampire', 'zombie'], culprit: 'zombie' });
  let f = await d.post('/api/tasks/6/act', { action: 'finish' });
  assert.equal(f.data.result.raw, 2 + 6, 'два на местах → 2, вор верный → 6');
  await d.post('/api/tasks/6/start');
  f = await d.post('/api/tasks/6/act', { action: 'finish', data: { order: ['ghost', 'witch', 'zombie', 'vampire'], culprit: 'zombie' } });
  assert.equal(f.data.result.raw, 10); assert.equal(f.data.result.final, 8);
  // № 7
  const w = await newPlayer('Ольга Склад');
  await w.post('/api/tasks/7/start');
  f = await w.post('/api/tasks/7/act', { action: 'finish', data: { order: ['kardio', 'reaktaktiv', 'flamin', 'reglisam'], code: '15' } });
  assert.equal(f.data.result.raw, 4);
  await w.post('/api/tasks/7/start');
  f = await w.post('/api/tasks/7/act', { action: 'finish', data: { order: ['kardio', 'reaktaktiv', 'flamin', 'reglisam'], code: '1023' } });
  assert.equal(f.data.result.raw, 10);
  // № 12
  const s = await newPlayer('Сергей Шифры');
  await s.post('/api/tasks/12/start');
  f = await s.post('/api/tasks/12/act', { action: 'finish', data: { a: ['ТЫКВА', 'призрак', 'зомбо'] } });
  assert.equal(f.data.result.raw, 6);
  await s.post('/api/tasks/12/start');
  f = await s.post('/api/tasks/12/act', { action: 'finish', data: { a: ['тыква', 'ПРИЗРАК', 'Зомби'] } });
  assert.equal(f.data.result.raw, 10);
  // № 13
  const p = await newPlayer('Павел Пазл');
  const v = (await p.post('/api/tasks/13/start')).data.task.active.view;
  assert.ok(v.arr.every((x, i) => x !== i), 'плитки перемешаны');
  assert.equal((await p.post('/api/tasks/13/act', { action: 'save', arr: [0, 0, 1, 2, 3, 4, 5, 6, 7] })).status, 400);
  const arr = [0, 1, 2, 3, 4, 5, 6, 8, 7];
  f = await p.post('/api/tasks/13/act', { action: 'finish', data: { arr } });
  assert.equal(f.data.result.raw, 7, '7 плиток на местах, без бонуса');
  await p.post('/api/tasks/13/start');
  f = await p.post('/api/tasks/13/act', { action: 'finish', data: { arr: [0, 1, 2, 3, 4, 5, 6, 7, 8] } });
  assert.equal(f.data.result.raw, 10); assert.equal(f.data.result.final, 8);
});

test('№ 1 и № 10: раунды, ответы, таймаут и серверный таймер', async () => {
  const p = await newPlayer('Роман Кино');
  let v = (await p.post('/api/tasks/1/start')).data.task.active.view;
  assert.equal(v.round, 0); assert.equal(v.question.title, '«Оно»'); assert.equal(v.question.palette.length, 8);
  let r = await p.post('/api/tasks/1/act', { action: 'answer', round: 0, answer: ['🎈', '🤡'] });
  assert.equal(r.data.task.active.view.round, 1);
  assert.equal((await p.post('/api/tasks/1/act', { action: 'answer', round: 0, answer: ['🎈'] })).data.task.active.view.round, 1, 'устаревший ответ игнорируется');
  r = await p.post('/api/tasks/1/act', { action: 'answer', round: 1, answer: ['👻', '🚫', '🪤'] });
  r = await p.post('/api/tasks/1/act', { action: 'answer', round: 2, answer: ['🧛', '🏰', '🦇'] });
  assert.equal(r.data.result.raw, 10);
  // порядок не важен; лишний эмодзи сверх лимита и пустая комбинация не засчитываются
  const q = await newPlayer('Тимур Кино');
  await q.post('/api/tasks/1/start');
  await q.post('/api/tasks/1/act', { action: 'answer', round: 0, answer: ['🤡', '🎈', '🎃', '🦇', '🔮'] });
  await q.post('/api/tasks/1/act', { action: 'answer', round: 1, answer: ['👻', '🚫'] });
  r = await q.post('/api/tasks/1/act', { action: 'answer', round: 2, answer: ['🧛', '🏰', '🩸'] });
  assert.equal(r.data.result.raw, 4, 'раунд 1 не засчитан (5 эмодзи), раунд 2 без одного из трёх вариантов — тоже, раунд 3 верен (4)');
  // № 10
  const e = await newPlayer('Эльвира Ведьма');
  v = (await e.post('/api/tasks/10/start')).data.task.active.view;
  assert.equal(v.sec, 10, 'по умолчанию 10 секунд');
  const right = ['Репа', 'Канун Дня всех святых', 'Три', 'Джек Скеллингтон', 'Самайн'];
  for (let i = 0; i < 5; i++) {
    const cur = (await e.get('/api/tasks/10')).data.active.view;
    assert.equal(cur.round, i);
    const idx = cur.question.options.indexOf(right[i]);
    assert.ok(idx >= 0);
    r = await e.post('/api/tasks/10/act', { action: 'answer', round: i, answer: i === 4 ? (idx + 1) % 3 : idx });
  }
  assert.equal(r.data.result.raw, 8, 'четыре верных по 2, последний неверный');
  assert.equal((await e.post('/api/tasks/10/act', { action: 'finish' })).data.result, null);
});

test('Таймеры на сервере: обновление страницы не сбрасывает, по истечении результат фиксируется сам', async () => {
  assert.equal((await admin.post('/api/admin/timers', { timers: { 3: 3, 10: 3, 1: 3 } })).status, 409, 'во время игры — только с подтверждением');
  assert.equal((await admin.post('/api/admin/timers', { timers: { 3: 3, 10: 3, 1: 3 }, confirm: true, reason: 'ускоряем тест' })).status, 200);
  const p = await newPlayer('Тарас Таймер');
  const t0 = (await p.post('/api/tasks/3/start')).data.task.active;
  await p.post('/api/tasks/3/act', { action: 'save', name: 'Реглисам', split: '18 6 4 13 10 19 1 14' });
  await sleep(1200);
  const t1 = (await p.get('/api/tasks/3')).data.active;
  assert.equal(t1.startedAt, t0.startedAt, 'таймер не сбросился обновлением');
  assert.equal(t1.deadlineAt, t0.deadlineAt);
  await sleep(3600);
  const done = (await p.get('/api/tasks/3')).data;
  assert.equal(done.active, undefined);
  assert.equal(done.last.final, 10, 'сохранённые ответы засчитаны по таймеру');
  assert.equal((await p.post('/api/tasks/3/act', { action: 'finish', data: { name: 'x' } })).data.result, null, 'отправка после таймера ничего не меняет');
  // раунды без активности игрока: все три раунда истекают сами
  const q = await newPlayer('Ника Раунды');
  await q.post('/api/tasks/1/start');
  await sleep(6500);
  const after = (await q.get('/api/tasks/1')).data;
  assert.ok(after.last || after.active, 'состояние есть');
  await sleep(4000);
  const fin = (await q.get('/api/tasks/1')).data;
  assert.equal(fin.last.final, 0); assert.equal(fin.active, undefined);
  // таймаут викторины: вопросы закрываются по 3 секунды
  const w = await newPlayer('Влад Викторина');
  await w.post('/api/tasks/10/start');
  await sleep(4600);
  assert.equal((await w.get('/api/tasks/10')).data.active.view.round, 1, 'первый вопрос закрылся по таймеру');
  // правило меняется только с подтверждением, когда игра идёт
  assert.equal((await admin.post('/api/admin/timers', { timers: { 10: 8 } })).status, 409);
  assert.equal((await admin.post('/api/admin/timers', { timers: { 10: 8, 3: 60, 1: 10 }, confirm: true, reason: 'Тест показал: нужно больше времени' })).status, 200);
  const audit = (await admin.get('/api/admin/log?kind=audit')).data;
  assert.ok(audit.some((a) => a.action === 'timers' && /Тест показал/.test(a.detail)));
});

test('№ 9: конвейер — +1/−1, окно клика, дубли игнорируются', async () => {
  const p = await newPlayer('Кирилл Конвейер');
  const v = (await p.post('/api/tasks/9/start')).data.task.active.view;
  assert.equal(v.items.length, 20); assert.equal(v.items.filter((i) => i.e).length, 10);
  await sleep(3000); // к этому моменту появились упаковки 0..2
  let r;
  const enchanted = [0, 1, 2].filter((i) => v.items[i].e), plain = [0, 1, 2].filter((i) => !v.items[i].e);
  for (const i of enchanted) r = await p.post('/api/tasks/9/act', { action: 'click', id: i });
  assert.equal((await p.post('/api/tasks/9/act', { action: 'click', id: enchanted[0] })).data.feedback.ignored, true);
  assert.equal((await p.post('/api/tasks/9/act', { action: 'click', id: 19 })).data.feedback.ignored, true, 'упаковка ещё не выехала');
  for (const i of plain) r = await p.post('/api/tasks/9/act', { action: 'click', id: i });
  const fin = await p.post('/api/tasks/9/act', { action: 'finish' });
  assert.equal(fin.data.result.raw, Math.max(0, enchanted.length - plain.length));
  // вторая попытка перемешивает
  const v2 = (await p.post('/api/tasks/9/start')).data.task.active.view;
  assert.notDeepEqual(v2.items.map((i) => i.e), v.items.map((i) => i.e));
});

test('Сценарий 9: одинаковые баллы — критерии ничьих и жеребьёвка', async () => {
  const mk = async (_, name) => { const c = await newPlayer(name); return { c, id: await idOf(name) }; };
  const A = await mk(0, 'Ничья А'), B = await mk(0, 'Ничья Б'), C = await mk(0, 'Ничья В'), D = await mk(0, 'Ничья Г');
  // А: 8+8 = 16, Б: 10+6 = 16 (больше «десяток»), В и Г: по 9+7 = 16 с одинаковыми попытками
  for (const [pl, vals] of [[A, [8, 8]], [B, [10, 6]], [C, [9, 7]], [D, [9, 7]]]) { await setPts(admin, pl.id, 14, vals[0]); await setPts(admin, pl.id, 16, vals[1]); }
  const rows = (await admin.get('/api/admin/rating')).data.rows;
  const by = (n) => rows.find((r) => r.name === n);
  assert.equal(by('Ничья А').total, 16); assert.equal(by('Ничья Б').total, 16);
  assert.ok(by('Ничья Б').rank < by('Ничья А').rank, 'больше заданий на 10 — выше');
  assert.equal(by('Ничья В').rank, by('Ничья Г').rank, 'полное равенство — одно место');
  assert.ok(by('Ничья В').tied);
  // меньше использованных попыток — выше: В играет № 15 с двумя попытками, Г — только с одной
  const sol = [1, 2, 3, 4, 3, 4, 1, 2, 2, 1, 4, 3, 4, 3, 2, 1];
  const bad = sol.map((v, i) => ([2, 3, 6, 7, 8, 9, 12, 13].includes(i) ? 0 : v));
  await C.c.post('/api/tasks/15/start'); await C.c.post('/api/tasks/15/act', { action: 'finish', data: { cells: bad } }); await C.c.post('/api/tasks/15/start');
  await C.c.post('/api/tasks/15/act', { action: 'finish', data: { cells: bad } });
  await setPts(admin, C.id, 15, 0); await setPts(admin, D.id, 15, 0);
  await D.c.post('/api/tasks/15/start'); await D.c.post('/api/tasks/15/act', { action: 'finish', data: { cells: bad } }); await D.c.post('/api/tasks/15/keep');
  const rows2 = (await admin.get('/api/admin/rating')).data.rows;
  assert.ok(rows2.find((r) => r.name === 'Ничья Г').rank < rows2.find((r) => r.name === 'Ничья В').rank, 'меньше попыток — выше');
  // полное равенство: жеребьёвка
  const E = await mk(0, 'Ничья Д'), F = await mk(0, 'Ничья Е');
  for (const x of [E, F]) await setPts(admin, x.id, 14, 5);
  let rr = (await admin.get('/api/admin/rating')).data.rows;
  assert.equal(rr.find((r) => r.name === 'Ничья Д').rank, rr.find((r) => r.name === 'Ничья Е').rank);
  const tb = await admin.post('/api/admin/tiebreak');
  assert.equal(tb.status, 200);
  rr = (await admin.get('/api/admin/rating')).data.rows;
  assert.notEqual(rr.find((r) => r.name === 'Ничья Д').rank, rr.find((r) => r.name === 'Ничья Е').rank);
  assert.ok((await admin.get('/api/admin/log?kind=audit')).data.some((a) => a.action === 'tiebreak'));
});

test('Тестовый режим панели не трогает настоящие данные', async () => {
  const t = await loginAs(testNames[2], '1234');
  const real = (await admin.get('/api/admin/players')).data[0];
  assert.equal((await adminT.post('/api/admin/adjust', { playerId: real.id, taskId: 1, points: 5, reason: 'проба' })).status, 409);
  const tid = (await adminT.get('/api/admin/players')).data.find((p) => p.name === testNames[2]).id;
  assert.equal((await admin.post('/api/admin/adjust', { playerId: tid, taskId: 1, points: 5, reason: 'проба' })).status, 409);
  assert.equal((await adminT.post('/api/admin/adjust', { playerId: tid, taskId: 1, points: 5, reason: 'проба' })).status, 200);
  assert.ok(!(await admin.get('/api/admin/players')).data.some((p) => p.name === testNames[2]));
  assert.ok((await t.get('/api/leaderboard')).data.rows.every((r) => !/Ничья/.test(r.name)), 'тестовый рейтинг отдельный');
});

test('Итоги: «Подвести итоги», фиксация рейтинга, снятие фиксации', async () => {
  assert.equal((await admin.post('/api/admin/finalize', {})).status, 409, 'игра ещё идёт / есть работы на проверке');
  // проверим оставшиеся работы
  for (const s of (await admin.get('/api/admin/submissions?status=pending')).data) await admin.post(`/api/admin/submissions/${s.id}/review`, { decision: 'approve', criteria: s.criteria.map((c) => c.id) });
  assert.equal((await admin.post('/api/admin/game', { action: 'end' })).status, 409, 'нужно подтверждение');
  await admin.post('/api/admin/game', { action: 'end', confirm: true });
  const a = await loginAs('Анна Смирнова');
  assert.equal((await a.post('/api/tasks/15/start')).status, 423, 'после окончания новые попытки закрыты');
  const f = await admin.post('/api/admin/finalize', {});
  assert.equal(f.status, 200, JSON.stringify(f.data));
  assert.equal(f.data.top3.length, 3);
  const lb = (await a.get('/api/leaderboard')).data;
  assert.equal(lb.final, true); assert.equal(lb.top3.length, 3);
  assert.equal((await a.get('/api/me')).data.final.top3.length, 3);
  const id = await idOf('Ничья А');
  assert.equal((await setPts(admin, id, 1, 3)).status, 423, 'после фиксации оценки менять нельзя');
  await admin.post('/api/admin/unfreeze');
  assert.equal((await setPts(admin, id, 1, 3)).status, 200);
});

test('Экспорт CSV, резервная копия, список кодов, очистка тестовых данных и удаление', async () => {
  const csv = await admin.get('/api/admin/export.csv');
  assert.equal(csv.status, 200); assert.match(csv.headers.get('content-type'), /text\/csv/);
  assert.deepEqual([...csv.data.subarray(0, 3)], [0xef, 0xbb, 0xbf]);
  const text = csv.data.toString('utf8');
  assert.ok(text.includes('№1 Кино наоборот') && text.includes('№16 Эликсир идеальной пятницы') && text.includes('Бонус БИНГО') && text.includes('Максим Максимум'));
  const bk = (await admin.get('/api/admin/backup.json')).data; const backup = JSON.stringify(bk);
  assert.ok(bk.players.length > 20);
  assert.ok(!/pin_hash|pin_salt/.test(backup), 'в резервной копии нет PIN-данных');
  assert.equal((await admin.post('/api/admin/demo/clear')).status, 200);
  assert.equal((await adminT.get('/api/admin/players')).data.length, 0);
  assert.ok((await admin.get('/api/admin/players')).data.length > 20);
  assert.equal((await admin.post('/api/admin/wipe', { confirm: 'нет' })).status, 400);
  assert.equal((await admin.post('/api/admin/wipe', { confirm: 'УДАЛИТЬ' })).status, 200);
  assert.equal((await admin.get('/api/admin/players')).data.length, 0);
  assert.equal(fs.readdirSync(path.join(DATA, 'uploads')).length, 0);
});

test('Сценарий 11: 50 участников играют одновременно', async () => {
  await admin.post('/api/admin/game', { action: 'reopen' });
  const fresh = Array.from({ length: 50 }, (_, i) => `Участник ${String(i + 1).padStart(2, '0')}`);
  const t0 = Date.now();
  const sol = [1, 2, 3, 4, 3, 4, 1, 2, 2, 1, 4, 3, 4, 3, 2, 1];
  const results = await Promise.all(fresh.map(async (name, i) => {
    const c = await newPlayer(name, i % 2 ? 'remote' : 'office');
    const out = [];
    out.push((await c.post('/api/tasks/15/start')).status);
    out.push((await c.post('/api/tasks/15/act', { action: 'finish', data: { cells: i % 3 ? sol : sol.map((v, k) => (k === 2 ? 0 : v)) } })).status);
    out.push((await c.post('/api/tasks/4/start')).status);
    for (const g of T.GHOSTS) out.push((await c.post('/api/tasks/4/act', { action: 'click', x: g.x, y: g.y })).status);
    out.push((await c.post('/api/tasks/2/submit', { data: { name: `Препарат ${i}`, slogan: 'Слоган' } })).status);
    out.push((await c.get('/api/leaderboard')).status);
    out.push((await c.get('/api/me')).status);
    return out;
  }));
  assert.ok(results.every((r) => r.every((s) => s === 200)), 'все запросы успешны');
  const rows = (await admin.get('/api/admin/players')).data;
  assert.equal(rows.length, 50);
  assert.equal(new Set(rows.map((r) => r.name)).size, 50);
  assert.ok(rows.every((r) => r.total === 20 || r.total === 17), `итоги: ${[...new Set(rows.map((r) => r.total))]}`);
  assert.equal((await admin.get('/api/admin/dashboard')).data.pending, 50);
  assert.ok(Date.now() - t0 < 15000, 'уложились в разумное время');
});
