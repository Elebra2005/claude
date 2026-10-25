'use strict';
// Сквозные тесты через HTTP: регистрация, все 16 заданий, баллы, БИНГО, права доступа, админка.
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const DATA = fs.mkdtempSync(path.join(os.tmpdir(), 'mg-test-'));
process.env.DATA_DIR = DATA;
process.env.ADMIN_PASSWORD = 'test-admin-pass';
const { server } = require('../server');
let base;

before(() => new Promise((ok) => server.listen(0, '127.0.0.1', () => { base = `http://127.0.0.1:${server.address().port}`; ok(); })));
after(() => { server.close(); fs.rmSync(DATA, { recursive: true, force: true }); });

// Мини-клиент с собственными cookie — имитирует отдельное устройство.
function client() {
  const jar = {};
  const call = async (method, p, body) => {
    const res = await fetch(base + p, {
      method, headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), Cookie: Object.entries(jar).map(([k, v]) => `${k}=${v}`).join('; ') },
      body: body ? JSON.stringify(body) : undefined,
    });
    for (const c of res.headers.getSetCookie()) { const [kv] = c.split(';'); const [k, v] = kv.split('='); if (v) jar[k] = v; else delete jar[k]; }
    const type = res.headers.get('content-type') || '';
    const data = type.includes('json') ? await res.json() : await res.text();
    return { status: res.status, data, headers: res.headers };
  };
  return { get: (p) => call('GET', p), post: (p, b = {}) => call('POST', p, b), jar };
}

const PNG_1PX = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
const SOLUTIONS = {
  1: [{ answers: ['b', 'c', 'a'] }],
  3: [{ words: ['РеГлИсАм'] }],
  4: [{ x: 118, y: 150 }, { x: 676, y: 86 }, { x: 432, y: 452 }, { x: 588, y: 318 }, { x: 256, y: 32 }],
  6: [{ culprit: 'zombie', clue: 'c3' }],
  7: [{ order: ['k', 'r', 'f'] }],
  9: [{ choice: 'a' }, { choice: 'b' }, { choice: 'c' }],
  10: [{ answers: ['b', 'c', 'a'] }],
  12: [{ words: ['тыква', 'призрак', 'зомби'] }],
  13: [{ code: '612' }],
  15: [{ label: 'x3' }],
};
const CREATIVE = [2, 5, 8, 11, 14, 16];

let admin, codes, testCodes;

test('вход администратора и выдача кодов', async () => {
  admin = client();
  assert.equal((await admin.post('/api/admin/login', { password: 'wrong' })).status, 401);
  assert.equal((await admin.post('/api/admin/login', { password: 'test-admin-pass' })).status, 200);
  const r = await admin.post('/api/admin/codes/generate', { count: 50 });
  assert.equal(r.data.created.length, 50);
  assert.equal(new Set(r.data.created).size, 50);
  codes = r.data.created;
  testCodes = (await admin.post('/api/admin/demo/create', { count: 3 })).data.created;
  assert.equal(testCodes.length, 3);
});

test('без авторизации админ-API и данные игрока закрыты', async () => {
  const anon = client();
  assert.equal((await anon.get('/api/admin/players')).status, 401);
  assert.equal((await anon.get('/api/me')).status, 401);
  assert.equal((await anon.get('/api/admin/export.csv')).status, 401);
});

test('регистрация: один профиль на код, повторный вход с другого устройства', async () => {
  const a = client();
  assert.equal((await a.post('/api/login', { code: 'MLR-0000-0000' })).status, 401);
  const r1 = await a.post('/api/login', { code: codes[0].toLowerCase() });
  assert.equal(r1.data.needsProfile, true);
  assert.equal((await a.post('/api/login', { code: codes[0], name: 'Анна Смирнова' })).status, 400); // нет формата
  const r2 = await a.post('/api/login', { code: codes[0], name: 'Анна Смирнова', format: 'office' });
  assert.equal(r2.status, 200);
  // второе устройство с тем же кодом попадает в тот же профиль, имя не перезаписывается
  const b = client();
  const r3 = await b.post('/api/login', { code: codes[0], name: 'Кто-то другой', format: 'remote' });
  assert.equal(r3.data.name, 'Анна Смирнова');
  assert.equal((await b.get('/api/me')).data.player.name, 'Анна Смирнова');
  const players = (await admin.get('/api/admin/players?test=0')).data;
  assert.equal(players.length, 1);
});

test('до начала игры задания закрыты, тестовый участник играет вне расписания', async () => {
  const a = client();
  await a.post('/api/login', { code: codes[0] });
  assert.equal((await a.get('/api/tasks/1')).status, 423);
  assert.equal((await a.post('/api/tasks/1/attempt', { payload: { answers: ['b', 'c', 'a'] } })).status, 423);
  const t = client();
  await t.post('/api/login', { code: testCodes[0], name: 'Тестер', format: 'remote' });
  assert.equal((await t.get('/api/tasks/1')).status, 200);
});

test('ключи ответов не уходят клиенту', async () => {
  const t = client();
  await t.post('/api/login', { code: testCodes[0] });
  for (let id = 1; id <= 16; id++) {
    const r = await t.get(`/api/tasks/${id}`);
    assert.equal(r.status, 200);
    assert.equal(r.data.secret, undefined);
    const raw = JSON.stringify(r.data);
    if (id === 12) assert.ok(!/тыква|призрак|зомби/i.test(raw));
    if (id === 13) assert.ok(!raw.includes('612'));
    if (id === 9) assert.ok(!raw.includes('Медленно'));
  }
});

test('лимит в 3 попытки и статус «Попробуй ещё раз»', async () => {
  const t = client();
  await t.post('/api/login', { code: testCodes[1], name: 'Тестер Два', format: 'office' });
  let r = await t.post('/api/tasks/13/attempt', { payload: { code: '111' } });
  assert.equal(r.data.status, 'retry'); assert.equal(r.data.attemptsLeft, 2);
  r = await t.post('/api/tasks/13/attempt', { payload: { code: '222' } });
  assert.equal(r.data.attemptsLeft, 1);
  r = await t.post('/api/tasks/13/attempt', { payload: { code: '333' } });
  assert.equal(r.data.status, 'failed');
  r = await t.post('/api/tasks/13/attempt', { payload: { code: '612' } });
  assert.equal(r.status, 409);
  assert.equal((await t.get('/api/me')).data.score, 0);
  // некорректный ввод не тратит попытку
  assert.equal((await t.post('/api/tasks/1/attempt', { payload: { answers: ['a'] } })).status, 400);
  assert.equal((await t.get('/api/tasks/1')).data.attemptsLeft, 3);
});

test('анаграммы: регистр не важен, собранные слова сохраняются', async () => {
  const t = client();
  await t.post('/api/login', { code: testCodes[1] });
  let r = await t.post('/api/tasks/12/attempt', { payload: { words: ['ТЫКВА', 'ПРИЗКРА', 'зомби'] } });
  assert.equal(r.data.result, 'wrong');
  assert.deepEqual(r.data.state.solved, [true, false, true]);
  r = await t.post('/api/tasks/12/attempt', { payload: { words: ['xxx', 'Призрак', 'xxx'] } });
  assert.equal(r.data.result, 'correct');
  r = await t.post('/api/tasks/3/attempt', { payload: { words: ['рЕГЛИСАМ'] } });
  assert.equal(r.data.result, 'correct');
});

test('привидения: промахи бесплатны, повторный клик по найденному не считается', async () => {
  const t = client();
  await t.post('/api/login', { code: testCodes[1] });
  let r = await t.post('/api/tasks/4/attempt', { payload: { x: 5, y: 5 } });
  assert.equal(r.data.hit, false);
  r = await t.post('/api/tasks/4/attempt', { payload: { x: 120, y: 152 } });
  assert.equal(r.data.hit, true);
  r = await t.post('/api/tasks/4/attempt', { payload: { x: 120, y: 152 } });
  assert.equal(r.data.hit, false);
  assert.equal(r.data.state.found.length, 1);
  const svg = await t.get('/api/tasks/4/scene.svg');
  assert.equal(svg.status, 200);
  assert.match(svg.headers.get('content-type'), /svg/);
  assert.equal((await client().get('/api/tasks/4/scene.svg')).status, 401);
});

test('полное прохождение: 16 заданий, 10 БИНГО, 460 баллов, без двойного начисления', async () => {
  const p = client();
  await p.post('/api/login', { code: testCodes[2], name: 'Чемпион', format: 'remote' });
  for (const [id, steps] of Object.entries(SOLUTIONS)) {
    let last;
    for (const payload of steps) last = await p.post(`/api/tasks/${id}/attempt`, { payload });
    assert.equal(last.data.result, 'correct', `задание ${id}`);
    assert.ok(last.data.prediction, 'есть предсказание');
    assert.equal((await p.post(`/api/tasks/${id}/attempt`, { payload: steps[0] })).status, 409, `повтор ${id}`);
  }
  let me = (await p.get('/api/me')).data;
  assert.equal(me.completed, 10);

  // Творческие: текст, фото, а ещё фото без текста
  for (const id of CREATIVE) {
    const body = id === 5 ? { text: '', photo: PNG_1PX, consent: true } : id === 11 ? { text: 'Паутинный галстук', photo: PNG_1PX } : { text: `Ответ на задание ${id}`, consent: id === 2 };
    const r = await p.post(`/api/tasks/${id}/submit`, body);
    assert.equal(r.status, 200, `творческое ${id}: ${JSON.stringify(r.data)}`);
    assert.equal((await p.post(`/api/tasks/${id}/submit`, body)).status, 409, 'нельзя отправить дважды, пока на проверке');
  }
  me = (await p.get('/api/me')).data;
  assert.equal(me.board.filter((b) => b.status === 'review').length, 6);
  // творческие ещё не подтверждены: собрана только диагональ 4-7-10-13, где все задания автоматические
  assert.deepEqual(me.lines, [9]);
  assert.equal(me.score, 10 * 10 + 30);

  const queue = (await admin.get('/api/admin/submissions?status=pending&test=1')).data;
  assert.equal(queue.length, 6);
  // Отклоняем одно с комментарием — участник видит «Попробуй ещё раз» и может переотправить
  const s8 = queue.find((s) => s.taskId === 8);
  await admin.post(`/api/admin/submissions/${s8.id}/review`, { decision: 'reject', comment: 'Добавь драмы!' });
  me = (await p.get('/api/me')).data;
  assert.equal(me.board.find((b) => b.id === 8).status, 'retry');
  assert.equal(me.reviews[0].comment, 'Добавь драмы!');
  assert.equal((await admin.post(`/api/admin/submissions/${s8.id}/review`, { decision: 'approve' })).status, 409, 'повторная проверка запрещена');
  assert.equal((await p.post('/api/tasks/8/submit', { text: 'СРОЧНО: отчёт о квартальной нежити' })).status, 200);

  for (const s of (await admin.get('/api/admin/submissions?status=pending&test=1')).data) {
    assert.equal((await admin.post(`/api/admin/submissions/${s.id}/review`, { decision: 'approve' })).status, 200);
  }
  me = (await p.get('/api/me')).data;
  assert.equal(me.completed, 16);
  assert.equal(me.bingos, 10);
  assert.equal(me.score, 460);

  // Отмена одного подтверждения пересчитывает линии: клетка 2 входит в 1-ю строку и 2-й столбец
  const ap = (await admin.get('/api/admin/submissions?status=approved&test=1')).data.find((s) => s.taskId === 2);
  await admin.post(`/api/admin/submissions/${ap.id}/review`, { decision: 'revoke' });
  me = (await p.get('/api/me')).data;
  assert.equal(me.bingos, 8);
  assert.equal(me.score, 15 * 10 + 8 * 30);
});

test('фото доступны только автору и организатору', async () => {
  const sub = (await admin.get('/api/admin/submissions?status=all&test=1')).data.find((s) => s.photo && !s.consent);
  assert.ok(sub);
  assert.equal((await admin.get(sub.photo)).status, 200);
  assert.equal((await client().get(sub.photo)).status, 403);
  const other = client();
  await other.post('/api/login', { code: testCodes[0] });
  assert.equal((await other.get(sub.photo)).status, 403);
  // в галерее только одобренные ответы с согласием
  const gallery = (await other.get('/api/gallery')).data;
  assert.ok(gallery.every((g) => g.taskId !== 11));
  assert.ok(gallery.some((g) => g.taskId === 5));
});

test('загрузка: только изображения и не больше 5 МБ', async () => {
  const p = client();
  await p.post('/api/login', { code: testCodes[0] });
  const fake = 'data:image/png;base64,' + Buffer.from('<script>alert(1)</script>').toString('base64');
  assert.equal((await p.post('/api/tasks/11/submit', { photo: fake })).status, 400);
  const svg = 'data:image/svg+xml;base64,' + Buffer.from('<svg/>').toString('base64');
  assert.equal((await p.post('/api/tasks/11/submit', { photo: svg })).status, 400);
  const big = 'data:image/jpeg;base64,' + Buffer.concat([Buffer.from([0xff, 0xd8, 0xff]), Buffer.alloc(5.5 * 1024 * 1024)]).toString('base64');
  assert.equal((await p.post('/api/tasks/11/submit', { photo: big })).status, 413);
});

test('тестовые участники не попадают в настоящий рейтинг; рейтинг и CSV', async () => {
  const real = client();
  await real.post('/api/login', { code: codes[0] });
  const lb = (await real.get('/api/leaderboard')).data;
  assert.equal(lb.rows.length, 1);
  assert.equal(lb.rows[0].name, 'Анна Смирнова');
  const tlb = await (async () => { const t = client(); await t.post('/api/login', { code: testCodes[2] }); return (await t.get('/api/leaderboard')).data; })();
  assert.equal(tlb.rows[0].name, 'Чемпион');
  assert.ok(tlb.rows[0].me);
  const csv = await admin.get('/api/admin/export.csv?test=1');
  assert.equal(csv.status, 200);
  assert.match(csv.headers.get('content-type'), /text\/csv/);
  const raw = Buffer.from(await (await fetch(base + '/api/admin/export.csv?test=1', { headers: { Cookie: Object.entries(admin.jar).map(([k, v]) => `${k}=${v}`).join('; ') } })).arrayBuffer());
  assert.deepEqual([...raw.subarray(0, 3)], [0xef, 0xbb, 0xbf], 'BOM для Excel');
  assert.ok(csv.data.includes('Чемпион'));
});

test('секретное задание дня: без влияния на баллы', async () => {
  await admin.post('/api/admin/secrets', { question: 'Что можно сломать, не прикасаясь?', answers: 'Обещание' });
  const s = (await admin.get('/api/admin/secrets')).data[0];
  await admin.post(`/api/admin/secrets/${s.id}/activate`);
  const p = client();
  await p.post('/api/login', { code: testCodes[2] });
  const before = (await p.get('/api/me')).data;
  assert.equal(before.secret.question, 'Что можно сломать, не прикасаясь?');
  assert.equal((await p.post('/api/secret/answer', { id: s.id, answer: 'не знаю' })).data.correct, false);
  assert.equal((await p.post('/api/secret/answer', { id: s.id, answer: '  ОБЕЩАНИЕ ' })).data.correct, true);
  assert.equal((await p.get('/api/me')).data.score, before.score);
});

test('награды: жеребьёвка, один приз на человека, случайный с БИНГО', async () => {
  // Делаем трёх настоящих участников с равными баллами
  await admin.post('/api/admin/settings', { mode: 'open' });
  const names = ['Борис', 'Вера', 'Глеб'];
  for (let i = 0; i < 3; i++) {
    const c = client();
    await c.post('/api/login', { code: codes[i + 1], name: names[i], format: 'remote' });
    for (const id of [1, 3, 4, 6]) for (const payload of SOLUTIONS[id]) await c.post(`/api/tasks/${id}/attempt`, { payload });
  }
  const r = await admin.post('/api/admin/awards/draw-top');
  assert.equal(r.status, 200, JSON.stringify(r.data));
  const aw = (await admin.get('/api/admin/awards')).data;
  const winners = aw.awards.map((a) => a.name);
  assert.equal(winners.length, 3);
  assert.equal(new Set(winners).size, 3);
  assert.ok(aw.log.at(-1).text.includes('жребий'));
  // Креативный — только среди ненаграждённых
  const awardedId = aw.awards[0].player_id;
  assert.equal((await admin.post('/api/admin/awards/creative', { playerId: awardedId })).status, 409);
  assert.equal((await admin.post('/api/admin/awards/creative', { playerId: aw.candidates[0].id })).status, 200);
  // Линия 1-я строка: 1,2,3,4 — у Бориса/Веры/Глеба только 1,3,4 → БИНГО ни у кого из оставшихся
  assert.equal((await admin.post('/api/admin/awards/random-bingo')).status, 409);
  await admin.post('/api/admin/settings', { mode: 'schedule' });
});

test('отключённый код разлогинивает игрока; очистка тестовых данных и полное удаление', async () => {
  const p = client();
  await p.post('/api/login', { code: codes[5], name: 'Временный', format: 'office' });
  await admin.post(`/api/admin/codes/${codes[5]}/revoke`);
  assert.equal((await p.get('/api/me')).status, 401);
  assert.equal((await client().post('/api/login', { code: codes[5] })).status, 401);

  await admin.post('/api/admin/demo/clear');
  assert.equal((await admin.get('/api/admin/players?test=1')).data.length, 0);
  assert.equal((await admin.get('/api/admin/codes?test=1')).data.length, 0);
  assert.ok((await admin.get('/api/admin/players?test=0')).data.length > 0);

  assert.equal((await admin.post('/api/admin/wipe', { confirm: 'нет' })).status, 400);
  assert.equal((await admin.post('/api/admin/wipe', { confirm: 'УДАЛИТЬ' })).status, 200);
  assert.equal((await admin.get('/api/admin/players?test=0')).data.length, 0);
  assert.equal(fs.readdirSync(path.join(DATA, 'uploads')).length, 0);
  assert.equal((await admin.get('/api/admin/codes?test=0')).data.length, 50, 'коды остались');
});

test('CSRF: запрос с чужого Origin и не-JSON отклоняются', async () => {
  const r = await fetch(base + '/api/admin/logout', { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: 'https://evil.example' }, body: '{}' });
  assert.equal(r.status, 403);
  const r2 = await fetch(base + '/api/login', { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: '{}' });
  assert.equal(r2.status, 415);
});
