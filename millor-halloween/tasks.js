'use strict';
// Описание 16 заданий. Поля `secret` и функции `check` никогда не отправляются клиенту:
// клиент получает только результат publicView().

const norm = (s) => String(s || '').trim().toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, '');

const TASKS = [
  {
    id: 1, emoji: '🎬', title: 'Киношный шифр', type: 'auto', kind: 'quiz',
    description: 'Хакеры потустороннего мира зашифровали названия фильмов ужасов в эмодзи. Расшифруй все три — и лаборатория снова сможет включить кинопоказ.',
    content: {
      questions: [
        { q: '🎈🤡🕳️', options: [['a', '«Пила»'], ['b', '«Оно»'], ['c', '«Звонок»']] },
        { q: '👻🚫🚗', options: [['a', '«Каспер»'], ['b', '«Призрачный гонщик»'], ['c', '«Охотники за привидениями»']] },
        { q: '🧛‍♂️🏰🩸', options: [['a', '«Дракула»'], ['b', '«Сумерки»'], ['c', '«Семейка Аддамс»']] },
      ],
    },
    secret: ['b', 'c', 'a'],
  },
  {
    id: 2, emoji: '💊', title: 'Фармацевт Франкенштейна', type: 'creative', kind: 'text',
    description: 'Придумай название совершенно вымышленного препарата от понедельника и смешной слоган к нему.\n\nНапример: «Дедлайнофф — возвращает веру в пятницу!»\n\nТолько шуточные названия — без настоящих лекарств и медицинских обещаний.',
    content: { placeholder: 'Название — слоган', photo: false },
  },
  {
    id: 3, emoji: '🔐', title: 'Секрет Реглисама', type: 'auto', kind: 'anagram',
    description: 'Взрыв в лаборатории перемешал буквы на упаковке. Перетащи буквы так, чтобы снова получилось название препарата Миллор Групп.',
    content: { words: [{ letters: ['М', 'С', 'Л', 'И', 'Е', 'Р', 'А', 'Г'], hint: 'Препарат компании, 8 букв' }] },
    secret: ['реглисам'],
  },
  {
    id: 4, emoji: '👻', title: 'Охотник за привидениями', type: 'auto', kind: 'ghosts',
    description: 'В ночной лаборатории прячутся пять маленьких привидений. Найди их и нажми на каждое. Подсказка: они любят тёмные углы, колбы и аптечные полки.',
    content: { total: 5 },
    // Координаты в системе viewBox 800×500. Клиент рисует сцену, сервер засчитывает попадания.
    secret: [
      { x: 118, y: 150, r: 36 },
      { x: 676, y: 86, r: 36 },
      { x: 432, y: 452, r: 36 },
      { x: 588, y: 318, r: 36 },
      { x: 256, y: 32, r: 36 },
    ],
  },
  {
    id: 5, emoji: '🍊', title: 'Оранжевая тревога', type: 'creative', kind: 'photo',
    description: 'Найди вокруг себя три оранжевых предмета и сделай одну общую фотографию.\n\nНе хочешь загружать фото? Опиши три предмета словами — это тоже засчитывается.',
    content: { placeholder: 'Например: апельсин, маркер и чашка с тыквой', photo: true },
  },
  {
    id: 6, emoji: '🕵️', title: 'Пропавшие конфеты', type: 'auto', kind: 'detective',
    description: 'Праздничный запас конфет исчез с кухни лаборатории ровно в 15:10. Изучи дело, выбери виновного и улику, которая его выдаёт.',
    content: {
      case: 'Дело № 3010-Х. Место: кухня лаборатории, 2 этаж. Время: 15:10. Пропало: 3 кг праздничных конфет.',
      suspects: [
        { id: 'ghost', emoji: '👻', name: 'Призрак несогласованного бюджета', alibi: '«Я весь день был на общем видеосозвоне, у меня даже камера была включена!»' },
        { id: 'zombie', emoji: '🧟', name: 'Зомби бесконечных дедлайнов', alibi: '«Я… ыыы… просто шёл за кофе. Конфеты? Какие конфеты?»' },
        { id: 'witch', emoji: '🧙‍♀️', name: 'Ведьма срочных поручений', alibi: '«Я застряла в лифте между этажами и рассылала задачи с телефона!»' },
      ],
      clues: [
        { id: 'c1', icon: '🎥', text: 'Журнал видеосозвона: Призрак в эфире с 15:00 до 15:40 без перерывов.' },
        { id: 'c2', icon: '🛗', text: 'Диспетчер лифтов: кабина № 2 с Ведьмой стояла между этажами с 15:05 до 15:20.' },
        { id: 'c3', icon: '🪪', text: 'Электронный пропуск: дверь кухни открыта картой Зомби в 15:09.' },
        { id: 'c4', icon: '☕', text: 'Кофемашина приготовила двойной эспрессо в 15:30.' },
        { id: 'c5', icon: '🍬', text: 'На столе найден фантик и записка: «Дедлайн перенесён. Конфеты — тоже».' },
      ],
    },
    secret: { culprit: 'zombie', clue: 'c3' },
  },
  {
    id: 7, emoji: '🧪', title: 'Перепутанные этикетки', type: 'auto', kind: 'sort',
    description: 'Ночью кто-то переставил упаковки на складе. Расставь их в алфавитном порядке — сверху вниз (или слева направо).',
    content: { items: [['f', 'Фламин'], ['k', 'Кардиовален'], ['r', 'Реглисам']] },
    secret: ['k', 'r', 'f'],
  },
  {
    id: 8, emoji: '📨', title: 'Пятничное письмо с того света', type: 'creative', kind: 'text',
    description: 'Продолжи фразу максимально смешно:\n\n«В пятницу в 17:59 мне пришло письмо с темой…»',
    content: { placeholder: '…«СРОЧНО: согласовать отпуск призраков на 2027 год»', photo: false, prefix: 'В пятницу в 17:59 мне пришло письмо с темой…' },
  },
  {
    id: 9, emoji: '🧟', title: 'Выжить на корпоративном созвоне', type: 'auto', kind: 'story',
    description: 'Три абсурдные ситуации из жизни офиса. Неправильных ответов нет — выбирай то, что ближе твоей душе.',
    content: {
      steps: [
        { q: 'Ты подключился к совещанию, но все участники превратились в зомби. Твои действия?', options: [
          ['a', 'Включаю камеру и тоже начинаю медленно моргать'],
          ['b', 'Предлагаю перенести встречу на пятницу, 17:59'],
          ['c', 'Пишу в чат: «Коллеги, у вас микрофон… и лицо»'] ] },
        { q: 'Вампир корпоративных созвонов назначил встречу на 8:00 «буквально на пять минут». Что делаешь?', options: [
          ['a', 'Принимаю приглашение и ставлю рядом чеснок'],
          ['b', 'Отвечаю: «Предлагаю альтернативное время — никогда»'],
          ['c', 'Подключаюсь без камеры, но с тройным кофе'] ] },
        { q: 'Ведьма срочных поручений прислала задачу с пометкой «НУЖНО ВЧЕРА». Твой ход?', options: [
          ['a', 'Варю зелье продуктивности из трёх капучино'],
          ['b', 'Отправляю встречную задачу с пометкой «ПОЗАВЧЕРА»'],
          ['c', 'Ставлю статус «На шабаше, вернусь в понедельник»'] ] },
      ],
    },
    secret: {
      results: [
        { a: 'Тебя приняли за своего и назначили ответственным за протокол. Зомби аплодируют. Медленно.',
          b: 'Зомби в ужасе отключились. Даже нежить боится пятничных созвонов!',
          c: 'Сообщение прочитали 14 зомби. Ответ: «Ыыыы». Протокол утверждён единогласно.' },
        { a: 'Вампир продержался 4 минуты 59 секунд и улетел. Рекорд отдела!',
          b: 'Вампир впечатлён твоей смелостью и перенёс встречу на полнолуние.',
          c: 'Тройной кофе сделал тебя неуязвимым. Вампир попросил рецепт.' },
        { a: 'Зелье сработало: задача выполнена, а ты теперь слышишь, как думает принтер.',
          b: 'Ведьма растерялась и улетела на метле согласовывать сроки с самой собой.',
          c: 'Статус одобрен Советом ведьм. Тебе выдали бесплатный абонемент на шабаш.' },
      ],
      final: 'Ты выжил на корпоративном созвоне! Награда: медаль «Неубиваемый на созвонах».',
    },
  },
  {
    id: 10, emoji: '🎃', title: 'Хеллоуин-экзамен', type: 'auto', kind: 'quiz',
    description: 'Учёный совет лаборатории проверяет твои познания в хеллоуинской науке. Ответь на три вопроса.',
    content: {
      questions: [
        { q: 'Какого числа отмечают Хеллоуин?', options: [['a', '13 октября'], ['b', '31 октября'], ['c', '1 ноября']] },
        { q: 'Какой овощ традиционно используют для фонаря Джека?', options: [['a', 'Кабачок'], ['b', 'Баклажан'], ['c', 'Тыкву']] },
        { q: 'Как называется традиция выпрашивания сладостей в Хеллоуин?', options: [['a', 'Trick or Treat'], ['b', 'Black Friday'], ['c', 'Happy Hour']] },
      ],
    },
    secret: ['b', 'c', 'a'],
  },
  {
    id: 11, emoji: '🧛', title: 'Дресс-код потустороннего мира', type: 'creative', kind: 'photo',
    description: 'Покажи элемент своего хэллоуинского образа: необычный аксессуар, макияж, деталь одежды или тематический предмет.\n\nФото — без лица (руки, аксессуар, предмет на столе). Можно вместо фото описать свой образ словами.',
    content: { placeholder: 'Опиши свой образ: «Сегодня на мне паутинный галстук и…»', photo: true },
  },
  {
    id: 12, emoji: '🕸️', title: 'Перепутанные заклинания', type: 'auto', kind: 'anagram',
    description: 'Заклинания в книге рассыпались на буквы. Собери все три слова — перетаскивай буквы в правильном порядке.',
    content: {
      words: [
        { letters: ['А', 'В', 'Т', 'Ы', 'К'], hint: 'Главный овощ праздника' },
        { letters: ['К', 'З', 'А', 'Р', 'И', 'Р', 'П'], hint: 'Прозрачный обитатель старых замков' },
        { letters: ['Б', 'И', 'О', 'З', 'М'], hint: 'Ходит медленно, просит мозги' },
      ],
    },
    secret: ['тыква', 'призрак', 'зомби'],
  },
  {
    id: 13, emoji: '⚗️', title: 'Сейф Фламина', type: 'auto', kind: 'safe',
    description: 'В архиве стоит мистический сейф с трёхзначным кодом. Подсказки нацарапаны на дверце.',
    content: {
      hints: [
        'Первая цифра — количество букв в слове ФЛАМИН.',
        'Вторая цифра — количество букв «А» в этом слове.',
        'Третья цифра — количество гласных в этом слове.',
      ],
      digits: 3,
    },
    secret: '612',
  },
  {
    id: 14, emoji: '✍️', title: 'Проклятие корпоративного чата', type: 'creative', kind: 'text',
    description: 'Придумай максимально смешное название рабочего чата, в котором состоят зомби, ведьмы, вампиры и руководитель отдела.',
    content: { placeholder: 'Например: «Срочно, но не очень (и навсегда)»', photo: false },
  },
  {
    id: 15, emoji: '🔎', title: 'Кардиовален: секретный архив', type: 'auto', kind: 'archive',
    description: 'В секретном архиве лежат этикетки разных лет. Почти на всех полтергейст исказил название «Кардиовален». Найди единственную этикетку без ошибки.',
    content: {
      labels: [
        ['x1', 'КАРДИОВАЛЕМ', 'Серия 1987-Х'],
        ['x2', 'КОРДИОВАЛЕН', 'Серия 1993-Б'],
        ['x3', 'КАРДИОВАЛЕН', 'Серия 2001-Ф'],
        ['x4', 'КАРДИАВАЛЕН', 'Серия 1979-М'],
        ['x5', 'КАРДИОВАЛЛЕН', 'Серия 2013-Р'],
        ['x6', 'КАРДИОВЛЕН', 'Серия 1999-Ц'],
      ],
    },
    secret: 'x3',
  },
  {
    id: 16, emoji: '🔮', title: 'Эликсир идеальной пятницы', type: 'creative', kind: 'text',
    description: 'Придумай рецепт идеальной пятницы из трёх фантастических ингредиентов.\n\nНапример:\n• 100 мл отсутствия срочных поручений\n• две капли премии\n• щепотка отменённых совещаний',
    content: { placeholder: '1. …\n2. …\n3. …', photo: false },
  },
];

// Проверки. Возвращают { result: 'correct'|'wrong'|'progress'|'invalid', state, feedback }.
const CHECKS = {
  quiz(task, payload) {
    const ans = Array.isArray(payload && payload.answers) ? payload.answers : null;
    if (!ans || ans.length !== task.secret.length) return { result: 'invalid' };
    const right = ans.filter((a, i) => a === task.secret[i]).length;
    if (right === task.secret.length) return { result: 'correct', feedback: 'Все ответы верны!' };
    return { result: 'wrong', feedback: `Верно ${right} из ${task.secret.length}. Попробуй ещё раз!` };
  },
  anagram(task, payload, state) {
    const words = Array.isArray(payload && payload.words) ? payload.words : null;
    if (!words || words.length !== task.secret.length) return { result: 'invalid' };
    const solved = task.secret.map((w, i) => (state.solved && state.solved[i]) || norm(words[i]) === w);
    const next = { solved };
    if (solved.every(Boolean)) return { result: 'correct', state: next, feedback: 'Заклинание сработало!' };
    const n = solved.filter(Boolean).length;
    return { result: 'wrong', state: next, feedback: task.secret.length > 1 ? `Собрано слов: ${n} из ${task.secret.length}.` : 'Буквы встали не на свои места.' };
  },
  ghosts(task, payload, state) {
    const x = Number(payload && payload.x), y = Number(payload && payload.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return { result: 'invalid' };
    const found = new Set(state.found || []);
    let hit = -1;
    task.secret.forEach((g, i) => { if (hit < 0 && !found.has(i) && Math.hypot(g.x - x, g.y - y) <= g.r) hit = i; });
    if (hit >= 0) found.add(hit);
    const next = { found: [...found].sort() };
    if (found.size === task.secret.length) return { result: 'correct', state: next, feedback: 'Все привидения пойманы!' };
    return { result: 'progress', state: next, hit: hit >= 0, feedback: hit >= 0 ? 'Попался!' : 'Здесь пусто…' };
  },
  detective(task, payload) {
    if (!payload || typeof payload.culprit !== 'string' || typeof payload.clue !== 'string') return { result: 'invalid' };
    const okC = payload.culprit === task.secret.culprit, okE = payload.clue === task.secret.clue;
    if (okC && okE) return { result: 'correct', feedback: 'Дело раскрыто! Зомби пришёл на кухню в 15:09, у остальных железное алиби.' };
    if (okC) return { result: 'wrong', feedback: 'Подозреваемый верный, но эта улика его не доказывает.' };
    return { result: 'wrong', feedback: 'У этого подозреваемого есть алиби. Перечитай улики!' };
  },
  sort(task, payload) {
    const order = Array.isArray(payload && payload.order) ? payload.order : null;
    if (!order || order.length !== task.secret.length) return { result: 'invalid' };
    if (order.every((v, i) => v === task.secret[i])) return { result: 'correct', feedback: 'Склад в идеальном порядке!' };
    return { result: 'wrong', feedback: 'Порядок пока не алфавитный.' };
  },
  story(task, payload, state) {
    const steps = state.steps || [];
    const step = steps.length;
    const choice = payload && payload.choice;
    const total = task.content.steps.length;
    if (step >= total) return { result: 'invalid' };
    const outcome = task.secret.results[step][choice];
    if (!outcome) return { result: 'invalid' };
    const next = { steps: [...steps, { choice, outcome }] };
    if (next.steps.length === total) return { result: 'correct', state: next, feedback: task.secret.final, outcome };
    return { result: 'progress', state: next, outcome, feedback: outcome };
  },
  safe(task, payload) {
    const code = String((payload && payload.code) || '').replace(/\D/g, '');
    if (code.length !== task.secret.length) return { result: 'invalid' };
    if (code === task.secret) return { result: 'correct', feedback: 'Щёлк! Сейф открыт.' };
    return { result: 'wrong', feedback: 'Сейф недовольно скрипит. Код неверный.' };
  },
  archive(task, payload) {
    const id = payload && payload.label;
    if (!task.content.labels.some((l) => l[0] === id)) return { result: 'invalid' };
    if (id === task.secret) return { result: 'correct', feedback: 'Подлинник найден! Архив спасён.' };
    return { result: 'wrong', feedback: 'На этой этикетке полтергейст поменял буквы. Присмотрись!' };
  },
};

// Доп. попытки бессмысленны там, где ответа «неверно» не бывает.
const USES_ATTEMPTS = new Set(['quiz', 'anagram', 'detective', 'sort', 'safe', 'archive']);

// Публичные данные состояния (то, что уже открыл сам игрок).
function publicState(task, state) {
  state = state || {};
  if (task.kind === 'ghosts') return { found: state.found || [], spots: (state.found || []).map((i) => ({ x: task.secret[i].x, y: task.secret[i].y })) };
  if (task.kind === 'anagram') return { solved: state.solved || [], words: (state.solved || []).map((s, i) => (s ? task.secret[i].toUpperCase() : null)) };
  if (task.kind === 'story') return { steps: state.steps || [] };
  return {};
}

const PREDICTIONS = [
  'Звёзды предсказывают: сегодня ни один принтер не зажуёт бумагу.',
  'В ближайшую пятницу все совещания закончатся на 10 минут раньше.',
  'Тебя ждёт письмо без пометки «срочно». Береги его.',
  'Кофемашина на твоём этаже сегодня на твоей стороне.',
  'Скоро кто-то скажет тебе: «Это можно и в понедельник».',
  'Дедлайн, которого ты боишься, окажется добрым привидением.',
  'Твой ноутбук обновится ровно тогда, когда тебе будет удобно. Невероятно, но факт.',
  'Сегодня твоя камера включится только с хорошим светом.',
  'Хрустальный шар видит: в твоей почте наступит «входящие: 0».',
  'Звёзды советуют: возьми лишнюю конфету. Зомби всё равно не заметит.',
  'Ближайший созвон пройдёт без фразы «вы меня слышите?».',
  'Призрак несогласованного бюджета обходит тебя стороной.',
  'Тебе достанется последний кусочек торта на ближайшем дне рождения.',
  'Ведьма срочных поручений сегодня улетела в отпуск.',
  'Твоя идея на следующем совещании окажется гениальной — и её не присвоят.',
  'Вселенная готовит тебе пятницу без вечерних писем.',
  'Скоро ты найдёшь ту самую ручку, которая пропала в прошлом квартале.',
  'Вампир созвонов сегодня проспит до обеда.',
  'Луна в знаке отчётности: все таблицы сойдутся с первого раза.',
  'Сегодня Wi-Fi будет ловить даже в переговорке у лифта.',
];

// Линии бинго на поле 4×4 (задания расположены построчно: 1–4, 5–8, 9–12, 13–16).
const LINES = [];
for (let r = 0; r < 4; r++) LINES.push([1, 2, 3, 4].map((c) => r * 4 + c));
for (let c = 1; c <= 4; c++) LINES.push([0, 1, 2, 3].map((r) => r * 4 + c));
LINES.push([1, 6, 11, 16], [4, 7, 10, 13]);

const TASK_BY_ID = new Map(TASKS.map((t) => [t.id, t]));

module.exports = { TASKS, TASK_BY_ID, CHECKS, USES_ATTEMPTS, publicState, PREDICTIONS, LINES, norm };
