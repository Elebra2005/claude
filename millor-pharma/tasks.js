'use strict';
// «Миллор Фарма: Секретная лаборатория — Halloween Bingo».
// Описание 16 заданий и серверная логика автоматических игр. Правильные ответы живут только здесь:
// клиент получает лишь то, что нужно для отрисовки (view), и результат проверки.
const crypto = require('node:crypto');

const GRACE = 1200; // запас на сетевую задержку, мс
const GRID = [16, 2, 12, 7, 5, 10, 8, 11, 3, 1, 6, 9, 15, 14, 4, 13]; // раскладка поля 4×4, одинакова у всех
const LINES = [];
for (let r = 0; r < 4; r++) LINES.push([0, 1, 2, 3].map((c) => GRID[r * 4 + c]));
for (let c = 0; c < 4; c++) LINES.push([0, 1, 2, 3].map((r) => GRID[r * 4 + c]));
LINES.push([0, 5, 10, 15].map((i) => GRID[i]), [3, 6, 9, 12].map((i) => GRID[i]));
const LINE_NAMES = ['Строка 1', 'Строка 2', 'Строка 3', 'Строка 4', 'Столбец 1', 'Столбец 2', 'Столбец 3', 'Столбец 4', 'Диагональ ↘', 'Диагональ ↙'];
const BINGO_MIN = 8; // клетка учитывается в БИНГО, если в ней не меньше стольких баллов
const BINGO_BONUS = 30;
const AUTO_IDS = [1, 3, 4, 6, 7, 9, 10, 12, 13, 15];
const CREATIVE_IDS = [2, 5, 8, 11, 14, 16];

const TIMER_DEFAULTS = { 1: 10, 3: 60, 4: 90, 6: 240, 7: 300, 9: 30, 10: 10, 12: 240, 13: 70 };
const TIMER_LABELS = {
  1: '№ 1. Секунд на каждый из 3 раундов', 3: '№ 3. Секунд на задание', 4: '№ 4. Секунд на попытку', 6: '№ 6. Секунд на расследование',
  7: '№ 7. Секунд на квест', 9: '№ 9. Секунд на смену', 10: '№ 10. Секунд на каждый из 5 вопросов', 12: '№ 12. Секунд на все три этапа', 13: '№ 13. Секунд на сборку (после 5 с запоминания)',
};
const MEMORIZE_MS = 5000;

const norm = (s) => String(s ?? '').toLowerCase().replace(/ё/g, 'е').replace(/[^a-zа-я0-9]/g, '');
const stripVS = (s) => String(s).replace(/️/g, '');
const bad = (m) => Object.assign(new Error(m), { status: 400 });
const shuffle = (a) => { const r = [...a]; for (let i = r.length - 1; i > 0; i--) { const j = crypto.randomInt(i + 1); [r[i], r[j]] = [r[j], r[i]]; } return r; };
const clampInt = (v, lo, hi) => Math.max(lo, Math.min(hi, Math.round(Number(v) || 0)));
const str = (v, max) => String(v ?? '').replace(/\s+/g, ' ').trim().slice(0, max);

// ---------- Общий движок раундов (задания 1 и 10) ----------
function makeRounds({ n, question, check, points, sanitize }) {
  return {
    init(ctx) { return { round: 0, roundStart: ctx.now, answers: [], ...(this.extra ? this.extra() : {}) }; },
    tick(s, ctx) {
      const ms = ctx.sec * 1000;
      while (s.round < n && ctx.now > s.roundStart + ms + GRACE) { s.answers.push(null); s.round++; s.roundStart += ms; }
    },
    done: (s) => s.round >= n,
    view(s, ctx) {
      return { round: s.round, total: n, sec: ctx.sec, roundEndsAt: s.roundStart + ctx.sec * 1000, question: s.round < n ? question(s, s.round) : null };
    },
    act(s, action, p, ctx) {
      const ms = ctx.sec * 1000;
      if (s.round >= n) return { done: true };
      if (action !== 'answer' && action !== 'timeout') throw bad('Неизвестное действие');
      if (Number(p.round) !== s.round) return { done: false, stale: true };
      const due = s.roundStart + ms;
      if (action === 'timeout') { if (ctx.now < due - 700) return { done: false, stale: true }; s.answers.push(null); }
      else s.answers.push(ctx.now <= due + GRACE ? sanitize(s, s.round, p.answer) : null);
      s.round++; s.roundStart = ctx.now;
      return { done: s.round >= n };
    },
    score(s) {
      const parts = []; let raw = 0;
      for (let i = 0; i < n; i++) {
        const ok = s.answers[i] != null && check(s, i, s.answers[i]);
        const got = ok ? points[i] : 0; raw += got;
        parts.push({ label: `Раунд ${i + 1}`, got, max: points[i] });
      }
      return { raw, parts };
    },
  };
}

// ---------- № 1. Кино наоборот ----------
const FILMS = [
  { title: '«Оно»', palette: ['🎈', '🤡', '🕳️', '👻', '🎃', '🦇', '🧙', '🔮'], need: ['🎈', '🤡'], any: null },
  { title: '«Охотники за привидениями»', palette: ['👻', '🚫', '🚗', '🕵️', '🪤', '🧟', '🦇', '🎃'], need: ['👻', '🚫'], any: ['🚗', '🪤', '🕵️'] },
  { title: '«Дракула»', palette: ['🧛', '🏰', '🩸', '🦇', '🌙', '🎃', '👻', '🔮'], need: ['🧛', '🏰'], any: ['🩸', '🦇'] },
];
const MAX_EMOJI = 4;
const films = makeRounds({
  n: 3, points: [3, 3, 4],
  question: (s, i) => ({ title: FILMS[i].title, palette: FILMS[i].palette, maxPick: MAX_EMOJI }),
  sanitize: (s, i, a) => (Array.isArray(a) ? a.slice(0, 8).map((e) => String(e).slice(0, 12)) : []),
  check: (s, i, ans) => {
    const f = FILMS[i];
    if (!Array.isArray(ans) || ans.length > MAX_EMOJI) return false;
    const set = new Set(ans.map(stripVS));
    if (set.size !== ans.length) return false;
    const pal = new Set(f.palette.map(stripVS));
    if (![...set].every((e) => pal.has(e))) return false;
    if (!f.need.every((e) => set.has(stripVS(e)))) return false;
    return !f.any || f.any.some((e) => set.has(stripVS(e)));
  },
});

// ---------- № 10. Экзамен на звание ведьмы ----------
const QUIZ = [
  { q: 'Из чего первоначально делали фонари Джека в Ирландии?', o: ['Репа', 'Тыква', 'Картофель'], c: 0 },
  { q: 'Что означает Halloween?', o: ['Канун Дня всех святых', 'День ведьм', 'Ночь урожая'], c: 0 },
  { q: 'Сколько сестёр Сандерсон в фильме «Фокус-покус»?', o: ['Две', 'Три', 'Четыре'], c: 1 },
  { q: 'Как зовут главного героя фильма «Кошмар перед Рождеством»?', o: ['Джек Скеллингтон', 'Эдвард Руки-ножницы', 'Бугимен'], c: 0 },
  { q: 'С каким древним кельтским праздником связывают Хеллоуин?', o: ['Самайн', 'Йоль', 'Белтайн'], c: 0 },
];
const quiz = makeRounds({
  n: 5, points: [2, 2, 2, 2, 2],
  question: (s, i) => ({ text: QUIZ[i].q, options: s.perm[i].map((k) => QUIZ[i].o[k]) }),
  sanitize: (s, i, a) => { const d = Number(a); return Number.isInteger(d) && d >= 0 && d <= 2 ? s.perm[i][d] : -1; },
  check: (s, i, orig) => orig === QUIZ[i].c,
});
quiz.extra = () => ({ perm: QUIZ.map(() => shuffle([0, 1, 2])) });

// ---------- № 3. Досье № 13 ----------
const DOSSIER_CODE = '1864131019114';
const DOSSIER_SPLIT = [18, 6, 4, 13, 10, 19, 1, 14];
const HINT_TEXT = 'Числа обозначают порядковые номера букв русского алфавита, включая Ё. А = 1, Б = 2.';
const cipher = {
  init: (ctx) => ({ name: '', split: '', hint: ctx.hint ? 1 : 0 }),
  view: (s) => ({ code: DOSSIER_CODE, fields: { name: s.name, split: s.split }, hint: s.hint ? HINT_TEXT : null }),
  save(s, p) { if (p.name !== undefined) s.name = str(p.name, 40); if (p.split !== undefined) s.split = String(p.split).slice(0, 80); },
  act(s, action) { if (action !== 'hint') throw bad('Неизвестное действие'); s.hint = 1; return { done: false, hintUsed: true }; },
  score(s) {
    const nameOk = norm(s.name) === 'реглисам';
    const nums = (String(s.split).match(/\d+/g) || []).map(Number);
    const splitOk = nums.length === DOSSIER_SPLIT.length && nums.every((v, i) => v === DOSSIER_SPLIT[i]);
    // Пояснение засчитывается, если верно записаны числа, либо словами названо правило: номера букв в алфавите.
    const t = norm(s.split);
    const wordsOk = t.includes('алфавит') && /(номер|порядк|позици|цифр|числ)/.test(t);
    const explainOk = splitOk || wordsOk;
    const base = nameOk ? (explainOk ? 10 : 5) : 0;
    const parts = [{ label: 'Название препарата', got: nameOk ? 5 : 0, max: 5 }, { label: 'Принцип расшифровки', got: nameOk && explainOk ? 5 : 0, max: 5 }];
    let raw = base;
    if (s.hint) { parts.push({ label: 'Штраф за подсказку', got: -Math.min(5, base), max: 0, penalty: true }); raw = Math.max(0, base - 5); }
    return { raw, parts };
  },
};

// ---------- № 4. Охотник за привидениями ----------
const GHOSTS = [{ x: 150, y: 140, r: 24 }, { x: 712, y: 80, r: 24 }, { x: 664, y: 458, r: 24 }, { x: 575, y: 312, r: 24 }, { x: 58, y: 52, r: 24 }];
const MAX_WRONG = 8;
const ghosts = {
  init: () => ({ found: [], wrong: 0 }),
  view: (s) => ({ found: s.found.map((i) => ({ x: GHOSTS[i].x, y: GHOSTS[i].y })), wrong: s.wrong, maxWrong: MAX_WRONG, total: GHOSTS.length }),
  act(s, action, p) {
    if (action !== 'click') throw bad('Неизвестное действие');
    const x = Number(p.x), y = Number(p.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) throw bad('Некорректные координаты');
    let hit = -1, again = false;
    GHOSTS.forEach((g, i) => {
      if (hit >= 0 || Math.hypot(g.x - x, g.y - y) > g.r) return;
      if (s.found.includes(i)) again = true; else hit = i;
    });
    if (hit >= 0) s.found.push(hit); else if (!again) s.wrong++;
    return { done: s.found.length === GHOSTS.length || s.wrong >= MAX_WRONG, feedback: { hit: hit >= 0, ignored: again } };
  },
  score: (s) => ({ raw: s.found.length * 2, parts: [{ label: `Найдено привидений: ${s.found.length} из 5 (по 2 балла)`, got: s.found.length * 2, max: 10 }, { label: `Ошибочных нажатий: ${s.wrong} из ${MAX_WRONG}`, got: 0, max: 0 }] }),
};

// ---------- № 6. Дело о пропавших конфетах ----------
const SUSPECTS = [{ id: 'ghost', emoji: '👻', name: 'Призрак' }, { id: 'witch', emoji: '🧙‍♀️', name: 'Ведьма' }, { id: 'zombie', emoji: '🧟', name: 'Зомби' }, { id: 'vampire', emoji: '🧛', name: 'Вампир' }];
const SLOTS = ['15:00', '15:05', '15:10', '15:15'];
const TRUE_ORDER = ['ghost', 'witch', 'zombie', 'vampire'];
const detective = {
  init: () => ({ order: [null, null, null, null], culprit: null }),
  view: (s) => ({
    suspects: SUSPECTS, slots: SLOTS, order: s.order, culprit: s.culprit,
    clues: ['Призрак появился раньше Ведьмы.', 'Ведьма пришла ровно за пять минут до Зомби.', 'Вампир зашёл позже Зомби.', 'Шкаф с конфетами открывали в 15:10.'],
  }),
  save(s, p) {
    const ids = SUSPECTS.map((x) => x.id);
    if (p.order !== undefined) {
      if (!Array.isArray(p.order) || p.order.length !== 4) throw bad('Некорректная хронология');
      const o = p.order.map((v) => (ids.includes(v) ? v : null));
      if (new Set(o.filter(Boolean)).size !== o.filter(Boolean).length) throw bad('Персонаж не может быть дважды');
      s.order = o;
    }
    if (p.culprit !== undefined) s.culprit = ids.includes(p.culprit) ? p.culprit : null;
  },
  score(s) {
    const right = s.order.filter((v, i) => v === TRUE_ORDER[i]).length;
    const chrono = right === 4 ? 4 : right >= 2 ? 2 : 0;
    const thief = s.culprit === 'zombie' ? 6 : 0;
    return { raw: chrono + thief, parts: [{ label: 'Хронология', got: chrono, max: 4 }, { label: 'Похититель', got: thief, max: 6 }] };
  },
};

// ---------- № 7. Складской переполох ----------
const BOXES = [{ id: 'reglisam', name: 'Реглисам' }, { id: 'flamin', name: 'Фламин' }, { id: 'kardio', name: 'Кардиовален' }, { id: 'reaktaktiv', name: 'Реактактив' }];
const BOX_ORDER = ['kardio', 'reaktaktiv', 'flamin', 'reglisam'];
const WAREHOUSE_CODE = '1023';
const warehouse = {
  init: () => ({ order: [null, null, null, null], code: '' }),
  view: (s) => ({
    boxes: BOXES, order: s.order, code: s.code,
    clues: ['Реглисам находится справа с краю.', 'Фламин расположен сразу справа от Реактактива.', 'Кардиовален находится в первой половине.', 'Кардиовален не соседствует с Фламином.'],
    codeRule: 'Код из трёх чисел, записанных подряд: количество букв во втором названии, количество гласных в третьем, количество гласных в четвёртом (слева направо).',
  }),
  save(s, p) {
    const ids = BOXES.map((b) => b.id);
    if (p.order !== undefined) {
      if (!Array.isArray(p.order) || p.order.length !== 4) throw bad('Некорректная расстановка');
      const o = p.order.map((v) => (ids.includes(v) ? v : null));
      if (new Set(o.filter(Boolean)).size !== o.filter(Boolean).length) throw bad('Упаковка не может стоять дважды');
      s.order = o;
    }
    if (p.code !== undefined) s.code = String(p.code).replace(/\D/g, '').slice(0, 6);
  },
  score(s) {
    const a = s.order.every((v, i) => v === BOX_ORDER[i]) ? 4 : 0;
    const c = s.code === WAREHOUSE_CODE ? 6 : 0;
    return { raw: a + c, parts: [{ label: 'Расстановка упаковок', got: a, max: 4 }, { label: 'Код склада', got: c, max: 6 }] };
  },
};

// ---------- № 9. Призрачный конвейер ----------
const CONV = { count: 20, enchanted: 10, step: 1300, travel: 4200, labels: ['Реглисам', 'Фламин', 'Кардиовален', 'Реактактив'] };
const conveyor = {
  init() {
    const flags = shuffle([...Array(CONV.enchanted).fill(1), ...Array(CONV.count - CONV.enchanted).fill(0)]);
    return { items: flags.map((f, i) => ({ enter: i * CONV.step, e: f, l: crypto.randomInt(4) })), clicked: [], correct: 0, wrong: 0 };
  },
  view: (s) => ({ items: s.items, travel: CONV.travel, clicked: s.clicked, correct: s.correct, wrong: s.wrong, labels: CONV.labels }),
  act(s, action, p, ctx) {
    if (action !== 'click') throw bad('Неизвестное действие');
    const id = Number(p.id);
    const it = s.items[id];
    if (!Number.isInteger(id) || !it || s.clicked.includes(id)) return { done: false, feedback: { ignored: true } };
    const el = ctx.now - ctx.startedAt;
    if (el < it.enter - 400 || el > it.enter + CONV.travel + 800) return { done: false, feedback: { ignored: true } };
    s.clicked.push(id);
    if (it.e) s.correct++; else s.wrong++;
    return { done: false, feedback: { good: !!it.e, correct: s.correct, wrong: s.wrong } };
  },
  score: (s) => ({ raw: clampInt(s.correct - s.wrong, 0, 10), parts: [{ label: `Заколдованных упаковок поймано: ${s.correct}`, got: s.correct, max: 10 }, { label: `Ошибочных нажатий: ${s.wrong}`, got: -s.wrong, max: 0, penalty: true }] }),
};

// ---------- № 12. Перепутанные заклинания ----------
const spells = {
  init: () => ({ a: ['', '', ''] }),
  view: (s) => ({
    answers: s.a,
    stages: [
      { type: 'reverse', text: 'АВКЫТ', pts: 3, title: 'Этап 1. Прочитай наоборот' },
      { type: 'numbers', codes: [17, 18, 10, 9, 18, 1, 12], pts: 3, title: 'Этап 2. Числа вместо букв' },
      { type: 'shift', text: 'ИПНВЙ', pts: 4, title: 'Этап 3. Сдвиг на одну букву назад' },
    ],
  }),
  save(s, p) { if (Array.isArray(p.a)) s.a = [0, 1, 2].map((i) => str(p.a[i], 12)); },
  score(s) {
    const ok = [norm(s.a[0]) === 'тыква', norm(s.a[1]) === 'призрак', norm(s.a[2]) === 'зомби'];
    const pts = [3, 3, 4];
    return { raw: ok.reduce((a, v, i) => a + (v ? pts[i] : 0), 0), parts: ok.map((v, i) => ({ label: `Этап ${i + 1}`, got: v ? pts[i] : 0, max: pts[i] })) };
  },
};

// ---------- № 13. Разбитый постер ----------
const puzzle = {
  init() {
    let perm; do { perm = shuffle([0, 1, 2, 3, 4, 5, 6, 7, 8]); } while (perm.some((v, i) => v === i));
    return { arr: perm };
  },
  view: (s, ctx) => ({ arr: s.arr, memorizeUntil: ctx.startedAt + MEMORIZE_MS, memorizeMs: MEMORIZE_MS }),
  save(s, p) {
    if (!Array.isArray(p.arr) || p.arr.length !== 9 || new Set(p.arr.map(Number)).size !== 9 || !p.arr.every((v) => Number.isInteger(v) && v >= 0 && v < 9)) throw bad('Некорректная раскладка');
    s.arr = p.arr.map(Number);
  },
  score(s) {
    const right = s.arr.filter((v, i) => v === i).length;
    const all = right === 9 ? 1 : 0;
    return { raw: right + all, parts: [{ label: `Плиток на своих местах: ${right} из 9`, got: right, max: 9 }, { label: 'Постер собран целиком', got: all, max: 1 }] };
  },
};

// ---------- № 15. Ведьмино судоку ----------
const SUDOKU_GIVEN = [1, 2, 0, 0, 3, 4, 0, 0, 0, 0, 4, 3, 0, 0, 2, 1]; // 1=👻 2=🎃 3=🦇 4=⚗️
const SUDOKU_SOL = [1, 2, 3, 4, 3, 4, 1, 2, 2, 1, 4, 3, 4, 3, 2, 1];
const sudoku = {
  init: () => ({ cells: [...SUDOKU_GIVEN] }),
  view: (s) => ({ given: SUDOKU_GIVEN, cells: s.cells, symbols: ['👻', '🎃', '🦇', '⚗️'] }),
  save(s, p) {
    if (!Array.isArray(p.cells) || p.cells.length !== 16) throw bad('Некорректное поле');
    s.cells = p.cells.map((v, i) => (SUDOKU_GIVEN[i] ? SUDOKU_GIVEN[i] : clampInt(v, 0, 4)));
  },
  score(s) {
    let right = 0, empties = 0;
    SUDOKU_GIVEN.forEach((g, i) => { if (!g) { empties++; if (s.cells[i] === SUDOKU_SOL[i]) right++; } });
    const all = right === empties ? 2 : 0;
    return { raw: right + all, parts: [{ label: `Правильно заполнено клеток: ${right} из ${empties}`, got: right, max: empties }, { label: 'Кабинет открыт целиком', got: all, max: 2 }] };
  },
};

const ENGINES = { films, cipher, ghosts, detective, warehouse, conveyor, quiz, spells, puzzle, sudoku };

// Момент автоматического завершения попытки (null — без таймера).
function deadlineFor(task, startedAt, sec) {
  switch (task.kind) {
    case 'films': return startedAt + 3 * (sec * 1000 + GRACE) + 3000;
    case 'quiz': return startedAt + 5 * (sec * 1000 + GRACE) + 3000;
    case 'puzzle': return startedAt + MEMORIZE_MS + sec * 1000 + GRACE;
    case 'sudoku': return null;
    default: return startedAt + sec * 1000 + GRACE;
  }
}
// Время, которое видит участник.
const displayDeadline = (task, startedAt, sec) => (task.kind === 'puzzle' ? startedAt + MEMORIZE_MS + sec * 1000 : task.kind === 'sudoku' ? null : startedAt + sec * 1000);

// ---------- Описание заданий ----------
const T = (o) => o;
const TASKS = [
  T({ id: 1, emoji: '🎬', title: 'Кино наоборот: эмодзи-режиссёр', type: 'auto', kind: 'films',
    story: 'Лабораторный проектор показывает названия фильмов ужасов, но афиши потерялись. Стань режиссёром и придумай для каждого фильма афишу из эмодзи.',
    rules: ['Три раунда по {sec} секунд. Раунд закрывается по таймеру.', 'В каждом раунде выбери до 4 эмодзи, которые лучше всего описывают фильм.', 'Баллы: 3 + 3 + 4. Порядок эмодзи не важен.'] }),
  T({ id: 2, emoji: '💊', title: 'Фармацевт Франкенштейна', type: 'creative', kind: 'creative',
    story: 'Миллор Фарма получила необычный заказ — разработать совершенно фантастическое средство против понедельника!',
    rules: ['Ориентир 2–3 минуты, без жёсткого таймера.', 'Название — 5 баллов, слоган — 5 баллов.', 'Это шутка: вымышленный препарат без реальных лечебных свойств.', 'Пример: «Дедлайнофф — возвращает веру в пятницу!»'] }),
  T({ id: 3, emoji: '🔐', title: 'Досье № 13: стёртая этикетка', type: 'auto', kind: 'cipher',
    story: 'В секретном архиве на досье № 13 стёрлось название препарата. Остался только числовой код.',
    rules: ['Время: {sec} секунд.', 'Восстанови название и объясни, как расшифровал(а) код.', 'Правильное название без пояснения — 5 баллов, с верным пояснением — 10.', 'Подсказка стоит −5 баллов и действует на обеих попытках.'] }),
  T({ id: 4, emoji: '👻', title: 'Охотник за привидениями', type: 'auto', kind: 'ghosts',
    story: 'В ночной лаборатории Миллор Фарма прячутся пять маленьких привидений. Найди их всех!',
    rules: ['Время: {sec} секунд на попытку.', 'По 2 балла за каждое привидение, максимум 10.', 'Не больше 8 ошибочных нажатий — потом охота заканчивается.', 'Привидения маленькие и прячутся за предметами и на похожем фоне; белых предметов-обманок хватает. На телефоне изображение можно увеличить.'] }),
  T({ id: 5, emoji: '🍊', title: 'Оранжевая тревога', type: 'creative', kind: 'creative',
    story: 'Объявлен оранжевый уровень хэллоуинской угрозы!',
    rules: ['Найди вокруг себя три разных оранжевых предмета и составь из них небольшую тематическую композицию.', 'Загрузи одну фотографию. Лицо показывать не нужно, ничего покупать не нужно.', 'Три предмета — по 2 балла, композиция — 4 балла.', 'Не хочешь загружать фото — опиши композицию словами.'] }),
  T({ id: 6, emoji: '🕵️', title: 'Дело о пропавших конфетах', type: 'auto', kind: 'detective',
    story: 'В Миллор Фарма исчезла коробка праздничных конфет. В 15:08 она ещё находилась на месте, а к 15:12 уже пропала. Четыре персонажа заходили в помещение в разное время.',
    rules: ['Время: {sec} секунд.', 'Расставь персонажей по времени визита и назови похитителя.', 'Хронология — 4 балла, похититель — 6.', 'Ответы проверяются после отправки или по окончании времени.'] }),
  T({ id: 7, emoji: '🧪', title: 'Складской переполох', type: 'auto', kind: 'warehouse',
    story: 'Призрак перепутал упаковки препаратов Миллор Фарма и заблокировал склад. Расставь упаковки и вычисли код двери.',
    rules: ['Время: {sec} секунд.', 'Расстановка — 4 балла, код — 6.', 'Названия препаратов — корпоративная игра, без медицинских свойств.'] }),
  T({ id: 8, emoji: '📨', title: 'Пятничное письмо с того света', type: 'creative', kind: 'creative',
    story: 'Пятница, 17:59. Ты уже мысленно дома. Вдруг приходит письмо с пометкой «СРОЧНО».',
    rules: ['Продолжи фразу «В пятницу в 17:59 мне пришло письмо с темой…» и напиши короткий текст письма.', 'Тема — 5 баллов, содержание — 5.', 'Пример. Тема: «Небольшой вопрос на 47 страниц». Текст: «Коллеги, просьба согласовать до вчера».'] }),
  T({ id: 9, emoji: '📦', title: 'Призрачный конвейер', type: 'auto', kind: 'conveyor',
    story: 'По конвейеру едут упаковки. Часть из них заколдована: на них фиолетовая печать с привидением.',
    rules: ['Время: {sec} секунд на попытку.', 'Нажимай только на упаковки с печатью. Всего 20 упаковок, 10 заколдованы.', '+1 за верное нажатие, −1 за ошибочное. Итог от 0 до 10.', 'Перед стартом можно потренироваться — без баллов.'] }),
  T({ id: 10, emoji: '🧙‍♀️', title: 'Экзамен на звание ведьмы', type: 'auto', kind: 'quiz',
    story: 'Совет ведьм проверяет твои знания о Хеллоуине. Отвечай быстро!',
    rules: ['Пять вопросов по {sec} секунд, у каждого три варианта.', 'За каждый правильный ответ — 2 балла.', 'Если время вышло, вопрос закрывается с нулём.'] }),
  T({ id: 11, emoji: '🧛', title: 'Дресс-код потустороннего мира', type: 'creative', kind: 'creative',
    story: 'Кем бы ты работал(а) в мистической версии Миллор Фарма? Например: Ведьма согласований, Вампир отчётов, Призрак дедлайнов.',
    rules: ['Придумай название персонажа и загрузи фото или короткое видео (до 15 секунд).', 'Лицо и фигуру показывать не нужно: подойдёт аксессуар, деталь образа или предмет.', 'Идея — 5 баллов, фото или видео — 5.', 'Материалы видит только организатор. Не хочешь загружать файл — опиши образ словами.'] }),
  T({ id: 12, emoji: '🕸️', title: 'Перепутанные заклинания', type: 'auto', kind: 'spells',
    story: 'Три заклинания в книге ведьмы зашифрованы по-разному. Расшифруй их.',
    rules: ['Время: {sec} секунд на все три этапа. Таймер между этапами не сбрасывается.', 'Баллы: 3 + 3 + 4.', 'Используется русский алфавит с буквой Ё (33 буквы).'] }),
  T({ id: 13, emoji: '🧩', title: 'Разбитый постер', type: 'auto', kind: 'puzzle',
    story: 'Полтергейст разбил праздничный плакат Миллор Фарма на девять частей.',
    rules: ['Сначала постер показывают 5 секунд, затем плитки перемешиваются. На сборку — {sec} секунд.', 'Компьютер: перетаскивай плитки. Телефон: коснись одной плитки, затем другой — они поменяются местами.', 'Каждая плитка на своём месте — 1 балл, весь постер — ещё +1. Максимум 10.', 'Верные места не подсвечиваются. Проверка — после «Готово» или по таймеру.'] }),
  T({ id: 14, emoji: '✍️', title: 'Проклятие корпоративного чата', type: 'creative', kind: 'creative',
    story: 'В один корпоративный чат попали Зомби, Ведьма, Вампир и руководитель отдела.',
    rules: ['Придумай смешное название чата и три коротких сообщения от участников.', 'Название — 4 балла, каждое сообщение — 2. Максимум 10.', 'Не используй реальные личные переписки и имена коллег.'] }),
  T({ id: 15, emoji: '🚪', title: 'Ведьмино судоку', type: 'auto', kind: 'sudoku',
    story: 'Чтобы попасть в кабинет загадочного врача № 13, нужно разгадать магическое судоку: дверь заколдована.',
    rules: ['Без таймера. Символы 👻 🎃 🦇 ⚗️ должны встретиться по одному разу в каждой строке, каждом столбце и каждом блоке 2×2.', 'Каждая верно заполненная клетка — 1 балл, полностью верная таблица — ещё +2.', 'Неверные клетки не подсвечиваются. Проверка — по кнопке «Открыть кабинет».'] }),
  T({ id: 16, emoji: '🔮', title: 'Эликсир идеальной пятницы', type: 'creative', kind: 'creative',
    story: 'Секретная лаборатория ищет рецепт идеальной пятницы для сотрудников Миллор Фарма.',
    rules: ['Придумай название эликсира, три фантастических ингредиента и шуточный эффект.', 'Название — 2 балла, каждый ингредиент — 2, эффект — 2.', 'Пример: «Пятницин». Две капли премии, щепотка отменённых созвонов, 100 мл отсутствия срочных поручений. Эффект: все встречи после 16:00 исчезают из календаря.'] }),
];
const TASK_BY_ID = new Map(TASKS.map((t) => [t.id, t]));

// ---------- Творческие задания: поля и критерии проверки ----------
const text = (id, label, max = 200, extra = {}) => ({ id, label, max, ...extra });
const CREATIVE = {
  2: { fields: [text('name', 'Название препарата', 60, { placeholder: 'Дедлайнофф' }), text('slogan', 'Рекламный слоган', 160, { placeholder: 'Возвращает веру в пятницу!', multiline: true })],
    criteria: [{ id: 'name', label: 'Придумано название', pts: 5 }, { id: 'slogan', label: 'Придуман смешной слоган', pts: 5 }] },
  5: { fields: [text('note', 'Какие три предмета на фото? (по желанию)', 300, { multiline: true, optional: true, placeholder: 'Апельсин, маркер и тыква-свечка' })], media: { kinds: ['image'], max: 1 }, mediaOrNote: 'note',
    criteria: [{ id: 'i1', label: 'Первый оранжевый предмет', pts: 2 }, { id: 'i2', label: 'Второй оранжевый предмет', pts: 2 }, { id: 'i3', label: 'Третий оранжевый предмет', pts: 2 }, { id: 'comp', label: 'Тематическая композиция', pts: 4 }] },
  8: { fields: [text('subject', 'Тема письма', 120, { placeholder: 'Небольшой вопрос на 47 страниц' }), text('body', 'Текст письма', 400, { multiline: true, placeholder: 'Коллеги, просьба согласовать до вчера' })],
    criteria: [{ id: 'subject', label: 'Тема письма', pts: 5 }, { id: 'body', label: 'Содержание письма', pts: 5 }] },
  11: { fields: [text('character', 'Название персонажа', 80, { placeholder: 'Ведьма согласований' }), text('note', 'Описание образа (если не хочешь загружать файл)', 300, { multiline: true, optional: true })], media: { kinds: ['image', 'video'], max: 1 }, mediaOrNote: 'note',
    criteria: [{ id: 'idea', label: 'Идея персонажа', pts: 5 }, { id: 'media', label: 'Фото или видео', pts: 5 }] },
  14: { fields: [text('title', 'Название чата', 80, { placeholder: 'Срочно, но не очень' }), text('m1', 'Сообщение 1', 160, { multiline: true }), text('m2', 'Сообщение 2', 160, { multiline: true }), text('m3', 'Сообщение 3', 160, { multiline: true })],
    criteria: [{ id: 'title', label: 'Название чата', pts: 4 }, { id: 'm1', label: 'Первое сообщение', pts: 2 }, { id: 'm2', label: 'Второе сообщение', pts: 2 }, { id: 'm3', label: 'Третье сообщение', pts: 2 }] },
  16: { fields: [text('name', 'Название эликсира', 60, { placeholder: 'Пятницин' }), text('i1', 'Ингредиент 1', 100, { placeholder: 'Две капли премии' }), text('i2', 'Ингредиент 2', 100, { placeholder: 'Щепотка отменённых созвонов' }), text('i3', 'Ингредиент 3', 100, { placeholder: '100 мл отсутствия срочных поручений' }), text('effect', 'Шуточный эффект', 200, { multiline: true })],
    criteria: [{ id: 'name', label: 'Есть название', pts: 2 }, { id: 'i1', label: 'Первый ингредиент', pts: 2 }, { id: 'i2', label: 'Второй ингредиент', pts: 2 }, { id: 'i3', label: 'Третий ингредиент', pts: 2 }, { id: 'effect', label: 'Описан результат', pts: 2 }] },
};


module.exports = {
  GRID, LINES, LINE_NAMES, BINGO_MIN, BINGO_BONUS, AUTO_IDS, CREATIVE_IDS, TASKS, TASK_BY_ID, ENGINES, CREATIVE,
  TIMER_DEFAULTS, TIMER_LABELS, MEMORIZE_MS, GRACE, deadlineFor, displayDeadline, GHOSTS, norm,
};
