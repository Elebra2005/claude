'use strict';
// «Миллор Групп: Секретная лаборатория» — сервер игры. Без внешних зависимостей: Node.js ≥ 22.13.
process.removeAllListeners('warning');
process.on('warning', (w) => { if (w.name !== 'ExperimentalWarning') console.warn(w); });

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { DatabaseSync } = require('node:sqlite');
const { TASKS, TASK_BY_ID, CHECKS, USES_ATTEMPTS, publicState, PREDICTIONS, LINES, norm } = require('./tasks');
const { ghostScene } = require('./scene');

const PORT = Number(process.env.PORT) || 3000;
const HOST = process.env.HOST || '0.0.0.0';
const DATA_DIR = path.resolve(process.env.DATA_DIR || path.join(__dirname, 'data'));
const UPLOAD_DIR = path.join(DATA_DIR, 'uploads');
const PUBLIC_DIR = path.join(__dirname, 'public');
const COOKIE_SECURE = process.env.COOKIE_SECURE === '1';
const TRUST_PROXY = process.env.TRUST_PROXY === '1';
const MAX_ATTEMPTS = 3;
const POINTS_TASK = 10;
const POINTS_LINE = 30;
const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
const PLAYER_SESSION_DAYS = 14;
const ADMIN_SESSION_HOURS = 12;
const PRIZES = {
  first: { title: '1-е место', amount: 2000 },
  second: { title: '2-е место', amount: 1500 },
  third: { title: '3-е место', amount: 1000 },
  creative: { title: 'Самый креативный участник', amount: 1000 },
  random_bingo: { title: 'Случайный участник с БИНГО', amount: 500 },
};

fs.mkdirSync(UPLOAD_DIR, { recursive: true });

let ADMIN_PASSWORD = process.env.ADMIN_PASSWORD;
if (!ADMIN_PASSWORD) {
  const f = path.join(DATA_DIR, 'admin-password.txt');
  if (fs.existsSync(f)) ADMIN_PASSWORD = fs.readFileSync(f, 'utf8').trim();
  else {
    ADMIN_PASSWORD = crypto.randomBytes(9).toString('base64url');
    fs.writeFileSync(f, ADMIN_PASSWORD + '\n', { mode: 0o600 });
  }
  console.log(`[admin] ADMIN_PASSWORD не задан. Пароль администратора сохранён в ${f}`);
}

// ---------- База данных ----------
const db = new DatabaseSync(path.join(DATA_DIR, 'game.db'));
db.exec(`
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS codes (
  code TEXT PRIMARY KEY, is_test INTEGER NOT NULL DEFAULT 0, revoked INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS players (
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE REFERENCES codes(code) ON DELETE CASCADE,
  name TEXT NOT NULL, work_format TEXT NOT NULL, is_test INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL, last_seen INTEGER NOT NULL, seen_reviews INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS admin_sessions (token_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS progress (
  player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, task_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'not_started', attempts INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT '{}',
  completed_at INTEGER, updated_at INTEGER NOT NULL, PRIMARY KEY (player_id, task_id));
CREATE TABLE IF NOT EXISTS uploads (
  id TEXT PRIMARY KEY, player_id INTEGER REFERENCES players(id) ON DELETE CASCADE,
  mime TEXT NOT NULL, size INTEGER NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  task_id INTEGER NOT NULL, text TEXT NOT NULL DEFAULT '', photo_id TEXT, consent INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending', comment TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL, reviewed_at INTEGER);
CREATE INDEX IF NOT EXISTS submissions_status ON submissions(status);
CREATE TABLE IF NOT EXISTS secrets (
  id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, answers TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS secret_answers (
  secret_id INTEGER NOT NULL REFERENCES secrets(id) ON DELETE CASCADE,
  player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  attempts INTEGER NOT NULL DEFAULT 0, solved_at INTEGER, PRIMARY KEY (secret_id, player_id));
CREATE TABLE IF NOT EXISTS awards (
  category TEXT PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, created_at INTEGER NOT NULL);
`);

const q = (sql) => db.prepare(sql);
const now = () => Date.now();
function tx(fn) {
  db.exec('BEGIN IMMEDIATE');
  try { const r = fn(); db.exec('COMMIT'); return r; } catch (e) { db.exec('ROLLBACK'); throw e; }
}

const DEFAULT_SETTINGS = {
  game_start: '2026-10-30T10:00:00+03:00',
  game_end: '2026-10-30T17:00:00+03:00',
  game_mode: 'schedule', // schedule | open | closed
  show_winners: false,
  task_overrides: {},
  logo: null,
  draw_log: [],
};
function getSetting(key) {
  const row = q('SELECT value FROM settings WHERE key = ?').get(key);
  return row ? JSON.parse(row.value) : structuredClone(DEFAULT_SETTINGS[key]);
}
function setSetting(key, value) {
  q('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value').run(key, JSON.stringify(value));
}

function gameStatus() {
  const mode = getSetting('game_mode');
  const start = Date.parse(getSetting('game_start'));
  const end = Date.parse(getSetting('game_end'));
  const t = now();
  let phase;
  if (mode === 'open') phase = 'running';
  else if (mode === 'closed') phase = 'stopped';
  else phase = t < start ? 'before' : t >= end ? 'after' : 'running';
  return { mode, phase, start: getSetting('game_start'), end: getSetting('game_end'), serverTime: t };
}
// Тестовые участники (демо-режим) играют вне расписания.
const isOpenFor = (player) => player.is_test === 1 || gameStatus().phase === 'running';

function taskTexts(task) {
  const o = getSetting('task_overrides')[task.id] || {};
  return { title: o.title || task.title, description: o.description || task.description };
}

// ---------- Подсчёт очков ----------
function scoreFromDone(done) {
  const lines = [];
  LINES.forEach((l, i) => { if (l.every((t) => done.has(t))) lines.push(i); });
  return { completed: done.size, lines, bingos: lines.length, score: done.size * POINTS_TASK + lines.length * POINTS_LINE };
}
function playerScore(playerId) {
  const done = new Set(q("SELECT task_id FROM progress WHERE player_id = ? AND status = 'done'").all(playerId).map((r) => r.task_id));
  return scoreFromDone(done);
}
function leaderboard(isTest) {
  const players = q('SELECT id, name, work_format, created_at FROM players WHERE is_test = ?').all(isTest ? 1 : 0);
  const doneRows = q("SELECT p.player_id, p.task_id, p.completed_at FROM progress p JOIN players pl ON pl.id = p.player_id WHERE p.status = 'done' AND pl.is_test = ?").all(isTest ? 1 : 0);
  const byPlayer = new Map(players.map((p) => [p.id, { done: new Set(), last: 0 }]));
  for (const r of doneRows) { const b = byPlayer.get(r.player_id); if (b) { b.done.add(r.task_id); b.last = Math.max(b.last, r.completed_at || 0); } }
  const rows = players.map((p) => ({ id: p.id, name: p.name, format: p.work_format, ...scoreFromDone(byPlayer.get(p.id).done) }));
  rows.sort((a, b) => b.score - a.score || b.completed - a.completed || a.name.localeCompare(b.name, 'ru'));
  let rank = 0, prev = null;
  rows.forEach((r, i) => { if (r.score !== prev) { rank = i + 1; prev = r.score; } r.rank = rank; });
  return rows;
}
function missionCount(isTest) {
  return q("SELECT COUNT(*) AS n FROM progress p JOIN players pl ON pl.id = p.player_id WHERE p.status = 'done' AND pl.is_test = ?").get(isTest ? 1 : 0).n;
}

// ---------- Утилиты HTTP ----------
const sha = (s) => crypto.createHash('sha256').update(s).digest('hex');
const newToken = () => crypto.randomBytes(32).toString('base64url');

class HttpError extends Error { constructor(status, message) { super(message); this.status = status; } }

function parseCookies(req) {
  const out = {};
  for (const part of (req.headers.cookie || '').split(';')) {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}
function setCookie(res, name, value, maxAgeSec) {
  const parts = [`${name}=${encodeURIComponent(value)}`, 'Path=/', 'HttpOnly', 'SameSite=Lax', `Max-Age=${maxAgeSec}`];
  if (COOKIE_SECURE) parts.push('Secure');
  const prev = res.getHeader('Set-Cookie') || [];
  res.setHeader('Set-Cookie', [...prev, parts.join('; ')]);
}
function clientIp(req) {
  if (TRUST_PROXY && req.headers['x-forwarded-for']) return String(req.headers['x-forwarded-for']).split(',')[0].trim();
  return req.socket.remoteAddress || '?';
}

// Ограничение частоты: rateLimit считает каждый запрос, failLimit — только неудачные попытки входа.
const buckets = new Map();
function bucket(key, windowMs) {
  const t = now();
  let b = buckets.get(key);
  if (!b || b.reset < t) { b = { n: 0, reset: t + windowMs }; buckets.set(key, b); }
  return b;
}
const TOO_MANY = 'Слишком много попыток. Подождите несколько минут.';
function rateLimit(key, limit, windowMs) {
  const b = bucket(key, windowMs);
  if (++b.n > limit) throw new HttpError(429, TOO_MANY);
}
function failGuard(key, limit, windowMs) {
  const b = bucket(key, windowMs);
  if (b.n >= limit) throw new HttpError(429, TOO_MANY);
  return () => { b.n++; };
}
setInterval(() => { const t = now(); for (const [k, b] of buckets) if (b.reset < t) buckets.delete(k); }, 60_000).unref();

function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    let size = 0; const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > limit) { reject(new HttpError(413, 'Слишком большой запрос')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => {
      if (!chunks.length) return resolve({});
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); } catch { reject(new HttpError(400, 'Некорректный JSON')); }
    });
    req.on('error', reject);
  });
}

const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'same-origin',
  'X-Frame-Options': 'DENY',
  'Content-Security-Policy': "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
};
function send(res, status, body, headers = {}) {
  res.writeHead(status, { ...SECURITY_HEADERS, ...headers });
  res.end(body);
}
const json = (res, status, obj) => send(res, status, JSON.stringify(obj), { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });

function csvCell(v) {
  let s = v == null ? '' : String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; // защита от формул в Excel
  return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
const toCsv = (rows) => '﻿' + rows.map((r) => r.map(csvCell).join(';')).join('\r\n') + '\r\n';
const sendCsv = (res, name, rows) => send(res, 200, toCsv(rows), {
  'Content-Type': 'text/csv; charset=utf-8', 'Cache-Control': 'no-store',
  'Content-Disposition': `attachment; filename="${name}"`,
});

const fmtMsk = (ms) => ms ? new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', dateStyle: 'short', timeStyle: 'medium' }).format(ms) : '';

// ---------- Аутентификация ----------
function currentPlayer(req) {
  const tok = parseCookies(req).mg_s;
  if (!tok) return null;
  const row = q('SELECT p.* FROM sessions s JOIN players p ON p.id = s.player_id JOIN codes c ON c.code = p.code WHERE s.token_hash = ? AND s.expires_at > ? AND c.revoked = 0').get(sha(tok), now());
  return row || null;
}
function requirePlayer(req) {
  const p = currentPlayer(req);
  if (!p) throw new HttpError(401, 'Нужно войти по игровому коду');
  return p;
}
function isAdmin(req) {
  const tok = parseCookies(req).mg_a;
  return !!tok && !!q('SELECT 1 FROM admin_sessions WHERE token_hash = ? AND expires_at > ?').get(sha(tok), now());
}
function requireAdmin(req) { if (!isAdmin(req)) throw new HttpError(401, 'Требуется вход администратора'); }

// Простая защита от CSRF: изменяющие запросы только из того же источника и только JSON.
function checkSameOrigin(req) {
  if (req.method === 'GET' || req.method === 'HEAD') return;
  const ct = req.headers['content-type'] || '';
  if (!ct.startsWith('application/json')) throw new HttpError(415, 'Ожидается JSON');
  const origin = req.headers.origin;
  if (origin) {
    const host = req.headers['x-forwarded-host'] || req.headers.host;
    try { if (new URL(origin).host !== host) throw 0; } catch { throw new HttpError(403, 'Запрос с чужого сайта'); }
  }
}

const CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
function generateCode(isTest) {
  const pick = (n) => Array.from({ length: n }, () => CODE_ALPHABET[crypto.randomInt(CODE_ALPHABET.length)]).join('');
  return `${isTest ? 'TEST' : 'MLR'}-${pick(4)}-${pick(4)}`;
}
const normCode = (s) => String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '').replace(/^(TEST|MLR)(.{4})(.{4})$/, '$1-$2-$3');

// ---------- Загрузка фото ----------
function saveImage(dataUrl, playerId) {
  const m = /^data:(image\/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$/.exec(String(dataUrl || ''));
  if (!m) throw new HttpError(400, 'Допустимы только фотографии JPEG, PNG или WebP');
  const buf = Buffer.from(m[2], 'base64');
  if (buf.length > MAX_PHOTO_BYTES) throw new HttpError(413, 'Фото больше 5 МБ');
  const isJpeg = buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff;
  const isPng = buf.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  const isWebp = buf.subarray(0, 4).toString('latin1') === 'RIFF' && buf.subarray(8, 12).toString('latin1') === 'WEBP';
  const mime = isJpeg ? 'image/jpeg' : isPng ? 'image/png' : isWebp ? 'image/webp' : null;
  if (!mime) throw new HttpError(400, 'Файл не похож на изображение');
  const id = crypto.randomBytes(16).toString('hex');
  fs.writeFileSync(path.join(UPLOAD_DIR, id), buf, { mode: 0o600 });
  q('INSERT INTO uploads (id, player_id, mime, size, created_at) VALUES (?, ?, ?, ?, ?)').run(id, playerId, mime, buf.length, now());
  return id;
}
function removeUploadFiles(ids) {
  for (const id of ids) { try { fs.unlinkSync(path.join(UPLOAD_DIR, id)); } catch {} }
}
function deletePlayers(whereSql, ...args) {
  const ids = q(`SELECT u.id FROM uploads u JOIN players p ON p.id = u.player_id WHERE ${whereSql}`).all(...args).map((r) => r.id);
  q(`DELETE FROM players WHERE ${whereSql.replace(/\bp\./g, '')}`).run(...args);
  removeUploadFiles(ids);
}

// ---------- Представление данных игрока ----------
function progressMap(playerId) {
  const m = new Map();
  for (const r of q('SELECT * FROM progress WHERE player_id = ?').all(playerId)) m.set(r.task_id, r);
  return m;
}
function attemptsLeft(task, row) {
  if (task.type !== 'auto' || !USES_ATTEMPTS.has(task.kind)) return null;
  return Math.max(0, MAX_ATTEMPTS - (row ? row.attempts : 0));
}
function activeSecret(player) {
  const s = q('SELECT * FROM secrets WHERE active = 1 ORDER BY id DESC LIMIT 1').get();
  if (!s) return null;
  const a = q('SELECT * FROM secret_answers WHERE secret_id = ? AND player_id = ?').get(s.id, player.id);
  return { id: s.id, question: s.question, solved: !!(a && a.solved_at), attemptsLeft: MAX_ATTEMPTS - (a ? a.attempts : 0) };
}
function meView(player) {
  const pm = progressMap(player.id);
  const board = TASKS.map((t) => {
    const row = pm.get(t.id);
    const { title } = taskTexts(t);
    return { id: t.id, emoji: t.emoji, title, type: t.type, status: row ? row.status : 'not_started', attemptsLeft: attemptsLeft(t, row) };
  });
  const sc = playerScore(player.id);
  const reviews = q("SELECT s.id, s.task_id, s.status, s.comment, s.reviewed_at FROM submissions s WHERE s.player_id = ? AND s.status != 'pending' AND s.reviewed_at > ? ORDER BY s.reviewed_at").all(player.id, player.seen_reviews);
  const lb = leaderboard(player.is_test === 1);
  const me = lb.find((r) => r.id === player.id);
  return {
    player: { name: player.name, format: player.work_format, isTest: player.is_test === 1, code: player.code },
    board, ...sc, rank: me ? me.rank : null, totalPlayers: lb.length,
    game: { ...gameStatus(), openForMe: isOpenFor(player) },
    mission: missionCount(player.is_test === 1),
    secret: activeSecret(player),
    reviews: reviews.map((r) => ({ id: r.id, taskId: r.task_id, status: r.status, comment: r.comment, at: r.reviewed_at })),
    logo: getSetting('logo') ? '/logo' : null,
  };
}
function taskView(player, task) {
  const row = progressMap(player.id).get(task.id);
  const state = row ? JSON.parse(row.state) : {};
  const out = {
    id: task.id, emoji: task.emoji, ...taskTexts(task), type: task.type, kind: task.kind,
    content: task.content, status: row ? row.status : 'not_started',
    attemptsLeft: attemptsLeft(task, row), maxAttempts: MAX_ATTEMPTS, state: publicState(task, state),
    lastResult: state.lastFeedback || null, prediction: state.prediction || null,
  };
  if (task.type === 'creative') {
    const s = q('SELECT * FROM submissions WHERE player_id = ? AND task_id = ? ORDER BY id DESC LIMIT 1').get(player.id, task.id);
    out.submission = s ? { text: s.text, photo: s.photo_id ? `/api/uploads/${s.photo_id}` : null, status: s.status, comment: s.comment, consent: !!s.consent } : null;
  }
  return out;
}

function upsertProgress(playerId, taskId, fields) {
  const cur = q('SELECT * FROM progress WHERE player_id = ? AND task_id = ?').get(playerId, taskId);
  const merged = { status: 'not_started', attempts: 0, state: '{}', completed_at: null, ...(cur || {}), ...fields, updated_at: now() };
  q(`INSERT INTO progress (player_id, task_id, status, attempts, state, completed_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(player_id, task_id) DO UPDATE SET status = excluded.status, attempts = excluded.attempts, state = excluded.state,
     completed_at = excluded.completed_at, updated_at = excluded.updated_at`)
    .run(playerId, taskId, merged.status, merged.attempts, merged.state, merged.completed_at, merged.updated_at);
  return merged;
}
const randomPrediction = () => PREDICTIONS[crypto.randomInt(PREDICTIONS.length)];

// ---------- Маршруты ----------
const routes = [];
const route = (method, pattern, handler) => routes.push({ method, re: new RegExp(`^${pattern}$`), handler });

route('GET', '/api/public', () => ({
  game: gameStatus(), logo: getSetting('logo') ? '/logo' : null, mission: missionCount(false),
}));

route('POST', '/api/login', async (req, res, body) => {
  const fail = failGuard('login:' + clientIp(req), 10, 10 * 60_000);
  rateLimit('login-all:' + clientIp(req), 300, 10 * 60_000);
  const code = normCode(body.code);
  const c = q('SELECT * FROM codes WHERE code = ? AND revoked = 0').get(code);
  if (!c) fail();
  if (!c) throw new HttpError(401, 'Код не найден или отключён. Проверьте код у организатора.');
  let player = q('SELECT * FROM players WHERE code = ?').get(code);
  if (!player) {
    const name = String(body.name || '').replace(/\s+/g, ' ').trim();
    const format = body.format === 'office' || body.format === 'remote' ? body.format : null;
    if (!name) return { needsProfile: true };
    if (name.length < 2 || name.length > 60) throw new HttpError(400, 'Имя: от 2 до 60 символов');
    if (!format) throw new HttpError(400, 'Выберите формат работы');
    try {
      const r = q('INSERT INTO players (code, name, work_format, is_test, created_at, last_seen) VALUES (?, ?, ?, ?, ?, ?)')
        .run(code, name, format, c.is_test, now(), now());
      player = q('SELECT * FROM players WHERE id = ?').get(r.lastInsertRowid);
    } catch { player = q('SELECT * FROM players WHERE code = ?').get(code); } // профиль уже создан параллельно
  }
  const tok = newToken();
  q('INSERT INTO sessions (token_hash, player_id, expires_at) VALUES (?, ?, ?)').run(sha(tok), player.id, now() + PLAYER_SESSION_DAYS * 864e5);
  setCookie(res, 'mg_s', tok, PLAYER_SESSION_DAYS * 86400);
  return { ok: true, name: player.name };
});

route('POST', '/api/logout', (req, res) => {
  const tok = parseCookies(req).mg_s;
  if (tok) q('DELETE FROM sessions WHERE token_hash = ?').run(sha(tok));
  setCookie(res, 'mg_s', '', 0);
  return { ok: true };
});

route('GET', '/api/me', (req) => {
  const p = requirePlayer(req);
  q('UPDATE players SET last_seen = ? WHERE id = ?').run(now(), p.id);
  return meView(p);
});

route('POST', '/api/me/seen-reviews', (req, res, body) => {
  const p = requirePlayer(req);
  const at = Math.min(Number(body.at) || 0, now());
  if (at > p.seen_reviews) q('UPDATE players SET seen_reviews = ? WHERE id = ?').run(at, p.id);
  return { ok: true };
});

function taskFromParams(m) {
  const t = TASK_BY_ID.get(Number(m[1]));
  if (!t) throw new HttpError(404, 'Задание не найдено');
  return t;
}
function ensureCanView(p) {
  const g = gameStatus();
  if (p.is_test !== 1 && g.phase === 'before') throw new HttpError(423, 'Лаборатория ещё закрыта. Задания откроются в начале игры.');
}
function ensureOpen(p) {
  if (!isOpenFor(p)) throw new HttpError(423, 'Сейчас игра не идёт — ответы не принимаются.');
}

route('GET', '/api/tasks/(\\d+)', (req, res, body, m) => {
  const p = requirePlayer(req); const t = taskFromParams(m);
  ensureCanView(p);
  return taskView(p, t);
});

route('GET', '/api/tasks/4/scene.svg', (req, res) => {
  const p = requirePlayer(req);
  ensureCanView(p);
  send(res, 200, ghostScene(TASK_BY_ID.get(4).secret), { 'Content-Type': 'image/svg+xml; charset=utf-8', 'Cache-Control': 'private, max-age=600' });
});

route('POST', '/api/tasks/(\\d+)/open', (req, res, body, m) => {
  const p = requirePlayer(req); const t = taskFromParams(m);
  if (!isOpenFor(p)) return { ok: true };
  const row = q('SELECT status FROM progress WHERE player_id = ? AND task_id = ?').get(p.id, t.id);
  if (!row || row.status === 'not_started') upsertProgress(p.id, t.id, { status: 'in_progress' });
  return { ok: true };
});

route('POST', '/api/tasks/(\\d+)/attempt', (req, res, body, m) => {
  const p = requirePlayer(req); const t = taskFromParams(m);
  if (t.type !== 'auto') throw new HttpError(400, 'Это творческое задание — отправьте ответ на проверку');
  ensureOpen(p);
  rateLimit('attempt:' + p.id, 120, 60_000);
  const outcome = tx(() => {
    const row = q('SELECT * FROM progress WHERE player_id = ? AND task_id = ?').get(p.id, t.id);
    if (row && row.status === 'done') throw new HttpError(409, 'Задание уже выполнено');
    if (row && row.status === 'failed') throw new HttpError(409, 'Попытки закончились');
    const state = row ? JSON.parse(row.state) : {};
    const r = CHECKS[t.kind](t, body.payload, state);
    if (r.result === 'invalid') throw new HttpError(400, 'Некорректный ответ');
    const newState = { ...state, ...(r.state || {}), lastFeedback: r.feedback };
    let status, attempts = row ? row.attempts : 0, prediction = null, completed_at = null;
    if (r.result === 'correct') {
      status = 'done'; completed_at = now(); prediction = randomPrediction(); newState.prediction = prediction;
    } else if (r.result === 'wrong') {
      attempts += 1; status = attempts >= MAX_ATTEMPTS ? 'failed' : 'retry';
    } else status = 'in_progress';
    upsertProgress(p.id, t.id, { status, attempts, state: JSON.stringify(newState), completed_at });
    return { result: r.result, status, feedback: r.feedback, hit: r.hit, outcome: r.outcome, prediction,
      attemptsLeft: attemptsLeft(t, { attempts }), state: publicState(t, newState) };
  });
  return { ...outcome, ...playerScore(p.id) };
});

route('POST', '/api/tasks/(\\d+)/submit', (req, res, body, m) => {
  const p = requirePlayer(req); const t = taskFromParams(m);
  if (t.type !== 'creative') throw new HttpError(400, 'Это задание проверяется автоматически');
  ensureOpen(p);
  rateLimit('submit:' + p.id, 20, 60_000);
  const text = String(body.text || '').trim().slice(0, 1500);
  const hasPhoto = t.content.photo && body.photo;
  if (!hasPhoto && text.length < 3) throw new HttpError(400, t.content.photo ? 'Загрузите фото или напишите хотя бы пару слов' : 'Напишите ответ (хотя бы пару слов)');
  return tx(() => {
    const row = q('SELECT * FROM progress WHERE player_id = ? AND task_id = ?').get(p.id, t.id);
    if (row && (row.status === 'done' || row.status === 'review')) throw new HttpError(409, row.status === 'done' ? 'Задание уже засчитано' : 'Ответ уже на проверке');
    const photoId = hasPhoto ? saveImage(body.photo, p.id) : null;
    q('INSERT INTO submissions (player_id, task_id, text, photo_id, consent, created_at) VALUES (?, ?, ?, ?, ?, ?)')
      .run(p.id, t.id, text, photoId, body.consent ? 1 : 0, now());
    const prediction = randomPrediction();
    const st = row ? JSON.parse(row.state) : {};
    upsertProgress(p.id, t.id, { status: 'review', state: JSON.stringify({ ...st, prediction }) });
    return { ok: true, status: 'review', prediction };
  });
});

route('GET', '/api/uploads/([0-9a-f]{32})', (req, res, body, m) => {
  const up = q('SELECT * FROM uploads WHERE id = ?').get(m[1]);
  if (!up) throw new HttpError(404, 'Нет файла');
  let allowed = isAdmin(req);
  if (!allowed) {
    const p = currentPlayer(req);
    if (p && up.player_id === p.id) allowed = true;
    else if (p && q("SELECT 1 FROM submissions s JOIN players pl ON pl.id = s.player_id WHERE s.photo_id = ? AND s.consent = 1 AND s.status = 'approved' AND pl.is_test = ?").get(up.id, p.is_test)) allowed = true;
  }
  if (!allowed) throw new HttpError(403, 'Нет доступа');
  send(res, 200, fs.readFileSync(path.join(UPLOAD_DIR, up.id)), { 'Content-Type': up.mime, 'Cache-Control': 'private, max-age=3600', 'Content-Disposition': 'inline' });
});

function awardsView(isTest) {
  if (isTest === undefined) isTest = false;
  return q('SELECT a.category, p.id AS player_id, p.name FROM awards a JOIN players p ON p.id = a.player_id WHERE p.is_test = ?').all(isTest ? 1 : 0)
    .map((a) => ({ ...a, ...PRIZES[a.category] }))
    .sort((a, b) => Object.keys(PRIZES).indexOf(a.category) - Object.keys(PRIZES).indexOf(b.category));
}

route('GET', '/api/leaderboard', (req) => {
  const p = requirePlayer(req);
  const rows = leaderboard(p.is_test === 1).map((r) => ({ rank: r.rank, name: r.name, format: r.format, completed: r.completed, bingos: r.bingos, score: r.score, me: r.id === p.id }));
  const secret = q('SELECT * FROM secrets WHERE active = 1 ORDER BY id DESC LIMIT 1').get();
  const secretSolvers = secret ? q('SELECT pl.name FROM secret_answers a JOIN players pl ON pl.id = a.player_id WHERE a.secret_id = ? AND a.solved_at IS NOT NULL AND pl.is_test = ? ORDER BY a.solved_at LIMIT 10').all(secret.id, p.is_test).map((r) => r.name) : [];
  return { rows, mission: missionCount(p.is_test === 1), winners: getSetting('show_winners') ? awardsView(p.is_test === 1) : null, secretSolvers };
});

route('GET', '/api/gallery', (req) => {
  const p = requirePlayer(req);
  return q("SELECT s.task_id, s.text, s.photo_id, pl.name FROM submissions s JOIN players pl ON pl.id = s.player_id WHERE s.status = 'approved' AND s.consent = 1 AND pl.is_test = ? ORDER BY s.reviewed_at DESC LIMIT 200")
    .all(p.is_test).map((s) => ({ taskId: s.task_id, title: taskTexts(TASK_BY_ID.get(s.task_id)).title, text: s.text, photo: s.photo_id ? `/api/uploads/${s.photo_id}` : null, name: s.name }));
});

route('POST', '/api/secret/answer', (req, res, body) => {
  const p = requirePlayer(req);
  ensureOpen(p);
  return tx(() => {
    const s = q('SELECT * FROM secrets WHERE active = 1 AND id = ?').get(Number(body.id));
    if (!s) throw new HttpError(404, 'Секретное задание уже закрыто');
    const a = q('SELECT * FROM secret_answers WHERE secret_id = ? AND player_id = ?').get(s.id, p.id) || { attempts: 0, solved_at: null };
    if (a.solved_at) return { correct: true, already: true };
    if (a.attempts >= MAX_ATTEMPTS) throw new HttpError(409, 'Попытки закончились');
    const correct = JSON.parse(s.answers).some((x) => norm(x) === norm(body.answer));
    q(`INSERT INTO secret_answers (secret_id, player_id, attempts, solved_at) VALUES (?, ?, ?, ?)
       ON CONFLICT(secret_id, player_id) DO UPDATE SET attempts = excluded.attempts, solved_at = excluded.solved_at`)
      .run(s.id, p.id, a.attempts + 1, correct ? now() : null);
    return { correct, attemptsLeft: MAX_ATTEMPTS - a.attempts - 1, prediction: correct ? randomPrediction() : null };
  });
});

route('GET', '/logo', (req, res) => {
  const logo = getSetting('logo');
  if (!logo) throw new HttpError(404, 'Логотип не загружен');
  send(res, 200, fs.readFileSync(path.join(DATA_DIR, 'logo')), { 'Content-Type': logo.mime, 'Cache-Control': 'public, max-age=300' });
});

// ---------- Администратор ----------
route('POST', '/api/admin/login', (req, res, body) => {
  const fail = failGuard('admin:' + clientIp(req), 8, 15 * 60_000);
  const a = Buffer.from(sha(String(body.password || ''))), b = Buffer.from(sha(ADMIN_PASSWORD));
  if (!crypto.timingSafeEqual(a, b)) fail();
  if (!crypto.timingSafeEqual(a, b)) throw new HttpError(401, 'Неверный пароль');
  const tok = newToken();
  q('INSERT INTO admin_sessions (token_hash, expires_at) VALUES (?, ?)').run(sha(tok), now() + ADMIN_SESSION_HOURS * 36e5);
  q('DELETE FROM admin_sessions WHERE expires_at < ?').run(now());
  setCookie(res, 'mg_a', tok, ADMIN_SESSION_HOURS * 3600);
  return { ok: true };
});
route('POST', '/api/admin/logout', (req, res) => {
  const tok = parseCookies(req).mg_a;
  if (tok) q('DELETE FROM admin_sessions WHERE token_hash = ?').run(sha(tok));
  setCookie(res, 'mg_a', '', 0);
  return { ok: true };
});
route('GET', '/api/admin/me', (req) => ({ admin: isAdmin(req) }));

function adminPlayers(isTest) {
  const lb = new Map(leaderboard(isTest).map((r) => [r.id, r]));
  const players = q('SELECT * FROM players WHERE is_test = ? ORDER BY created_at').all(isTest ? 1 : 0);
  const prog = q('SELECT p.* FROM progress p JOIN players pl ON pl.id = p.player_id WHERE pl.is_test = ?').all(isTest ? 1 : 0);
  const statuses = new Map();
  for (const r of prog) { if (!statuses.has(r.player_id)) statuses.set(r.player_id, {}); statuses.get(r.player_id)[r.task_id] = r.status; }
  return players.map((p) => {
    const s = lb.get(p.id);
    return { id: p.id, name: p.name, code: p.code, format: p.work_format, createdAt: p.created_at, lastSeen: p.last_seen,
      rank: s.rank, completed: s.completed, bingos: s.bingos, lines: s.lines, score: s.score, statuses: statuses.get(p.id) || {} };
  });
}
const wantTest = (url) => url.searchParams.get('test') === '1';

route('GET', '/api/admin/stats', (req, res, body, m, url) => {
  requireAdmin(req);
  const t = wantTest(url) ? 1 : 0;
  const rows = leaderboard(t === 1);
  const perTask = TASKS.map((task) => ({ id: task.id, emoji: task.emoji, title: taskTexts(task).title, type: task.type,
    done: q("SELECT COUNT(*) n FROM progress p JOIN players pl ON pl.id = p.player_id WHERE p.task_id = ? AND p.status = 'done' AND pl.is_test = ?").get(task.id, t).n }));
  return {
    game: gameStatus(),
    players: rows.length,
    office: q("SELECT COUNT(*) n FROM players WHERE work_format = 'office' AND is_test = ?").get(t).n,
    remote: q("SELECT COUNT(*) n FROM players WHERE work_format = 'remote' AND is_test = ?").get(t).n,
    completedTasks: missionCount(t === 1),
    pending: q("SELECT COUNT(*) n FROM submissions s JOIN players pl ON pl.id = s.player_id WHERE s.status = 'pending' AND pl.is_test = ?").get(t).n,
    bingos: rows.reduce((a, r) => a + r.bingos, 0),
    codes: q('SELECT COUNT(*) n FROM codes WHERE is_test = ?').get(t).n,
    leaderboard: rows.slice(0, 50), perTask,
  };
});

route('GET', '/api/admin/players', (req, res, body, m, url) => { requireAdmin(req); return adminPlayers(wantTest(url)); });
route('POST', '/api/admin/players/(\\d+)/delete', (req, res, body, m) => {
  requireAdmin(req);
  deletePlayers('p.id = ?', Number(m[1]));
  return { ok: true };
});

route('GET', '/api/admin/submissions', (req, res, body, m, url) => {
  requireAdmin(req);
  const status = url.searchParams.get('status') || 'pending';
  const t = wantTest(url) ? 1 : 0;
  const sql = `SELECT s.*, pl.name, pl.work_format FROM submissions s JOIN players pl ON pl.id = s.player_id WHERE pl.is_test = ? ${status === 'all' ? '' : 'AND s.status = ?'} ORDER BY s.created_at ${status === 'pending' ? 'ASC' : 'DESC'} LIMIT 500`;
  const rows = status === 'all' ? q(sql).all(t) : q(sql).all(t, status);
  return rows.map((s) => ({ id: s.id, taskId: s.task_id, taskTitle: taskTexts(TASK_BY_ID.get(s.task_id)).title, emoji: TASK_BY_ID.get(s.task_id).emoji,
    name: s.name, format: s.work_format, text: s.text, photo: s.photo_id ? `/api/uploads/${s.photo_id}` : null,
    consent: !!s.consent, status: s.status, comment: s.comment, createdAt: s.created_at, reviewedAt: s.reviewed_at }));
});

route('POST', '/api/admin/submissions/(\\d+)/review', (req, res, body, m) => {
  requireAdmin(req);
  const decision = body.decision;
  if (!['approve', 'reject', 'revoke'].includes(decision)) throw new HttpError(400, 'Неизвестное решение');
  const comment = String(body.comment || '').trim().slice(0, 500);
  return tx(() => {
    const s = q('SELECT * FROM submissions WHERE id = ?').get(Number(m[1]));
    if (!s) throw new HttpError(404, 'Ответ не найден');
    const latest = q('SELECT id FROM submissions WHERE player_id = ? AND task_id = ? ORDER BY id DESC LIMIT 1').get(s.player_id, s.task_id);
    if (latest.id !== s.id) throw new HttpError(409, 'Участник уже прислал более новый ответ на это задание');
    if (decision === 'revoke') {
      if (s.status !== 'approved') throw new HttpError(409, 'Отменить можно только подтверждённый ответ');
      q("UPDATE submissions SET status = 'rejected', comment = ?, reviewed_at = ? WHERE id = ?").run(comment || 'Подтверждение отменено организатором', now(), s.id);
      upsertProgress(s.player_id, s.task_id, { status: 'retry', completed_at: null });
      return { ok: true };
    }
    if (s.status !== 'pending') throw new HttpError(409, 'Этот ответ уже проверен');
    const approve = decision === 'approve';
    q('UPDATE submissions SET status = ?, comment = ?, reviewed_at = ? WHERE id = ?').run(approve ? 'approved' : 'rejected', comment, now(), s.id);
    upsertProgress(s.player_id, s.task_id, approve ? { status: 'done', completed_at: now() } : { status: 'retry' });
    return { ok: true, score: playerScore(s.player_id) };
  });
});

route('GET', '/api/admin/codes', (req, res, body, m, url) => {
  requireAdmin(req);
  return q('SELECT c.*, p.name, p.id AS player_id FROM codes c LEFT JOIN players p ON p.code = c.code WHERE c.is_test = ? ORDER BY c.created_at, c.code').all(wantTest(url) ? 1 : 0);
});
route('POST', '/api/admin/codes/generate', (req, res, body) => {
  requireAdmin(req);
  const count = Math.min(200, Math.max(1, Math.floor(Number(body.count) || 0)));
  const isTest = body.test ? 1 : 0;
  const created = [];
  tx(() => {
    while (created.length < count) {
      const c = generateCode(isTest);
      try { q('INSERT INTO codes (code, is_test, note, created_at) VALUES (?, ?, ?, ?)').run(c, isTest, String(body.note || '').slice(0, 100), now()); created.push(c); } catch {}
    }
  });
  return { created };
});
route('POST', '/api/admin/codes/([A-Z0-9-]+)/(revoke|restore|note)', (req, res, body, m) => {
  requireAdmin(req);
  if (m[2] === 'note') q('UPDATE codes SET note = ? WHERE code = ?').run(String(body.note || '').slice(0, 100), m[1]);
  else {
    q('UPDATE codes SET revoked = ? WHERE code = ?').run(m[2] === 'revoke' ? 1 : 0, m[1]);
    if (m[2] === 'revoke') q('DELETE FROM sessions WHERE player_id IN (SELECT id FROM players WHERE code = ?)').run(m[1]);
  }
  return { ok: true };
});
route('POST', '/api/admin/codes/([A-Z0-9-]+)/delete', (req, res, body, m) => {
  requireAdmin(req);
  deletePlayers('p.code = ?', m[1]);
  q('DELETE FROM codes WHERE code = ?').run(m[1]);
  return { ok: true };
});
route('GET', '/api/admin/codes.csv', (req, res, body, m, url) => {
  requireAdmin(req);
  const rows = q('SELECT c.*, p.name FROM codes c LEFT JOIN players p ON p.code = c.code WHERE c.is_test = ? ORDER BY c.created_at, c.code').all(wantTest(url) ? 1 : 0);
  sendCsv(res, 'millor-codes.csv', [['Код', 'Пометка', 'Участник', 'Статус'], ...rows.map((r) => [r.code, r.note, r.name || '', r.revoked ? 'отключён' : r.name ? 'используется' : 'свободен'])]);
});

route('GET', '/api/admin/settings', (req) => {
  requireAdmin(req);
  return { game: gameStatus(), showWinners: getSetting('show_winners'), logo: getSetting('logo') ? '/logo' : null };
});
route('POST', '/api/admin/settings', (req, res, body) => {
  requireAdmin(req);
  if (body.gameStart !== undefined || body.gameEnd !== undefined) {
    const s = Date.parse(body.gameStart), e = Date.parse(body.gameEnd);
    if (!Number.isFinite(s) || !Number.isFinite(e) || e <= s) throw new HttpError(400, 'Проверьте время начала и окончания');
    setSetting('game_start', body.gameStart); setSetting('game_end', body.gameEnd);
  }
  if (body.mode !== undefined) {
    if (!['schedule', 'open', 'closed'].includes(body.mode)) throw new HttpError(400, 'Неизвестный режим');
    setSetting('game_mode', body.mode);
  }
  if (body.showWinners !== undefined) setSetting('show_winners', !!body.showWinners);
  return { ok: true, game: gameStatus() };
});
route('POST', '/api/admin/logo', (req, res, body) => {
  requireAdmin(req);
  if (body.remove) { setSetting('logo', null); try { fs.unlinkSync(path.join(DATA_DIR, 'logo')); } catch {} return { ok: true }; }
  const m = /^data:(image\/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)$/.exec(String(body.image || ''));
  if (!m) throw new HttpError(400, 'Логотип: PNG, JPEG или WebP');
  const buf = Buffer.from(m[2], 'base64');
  if (buf.length > 1024 * 1024) throw new HttpError(413, 'Логотип больше 1 МБ');
  fs.writeFileSync(path.join(DATA_DIR, 'logo'), buf);
  setSetting('logo', { mime: m[1], updated: now() });
  return { ok: true };
});

route('GET', '/api/admin/tasks', (req) => {
  requireAdmin(req);
  const ov = getSetting('task_overrides');
  return TASKS.map((t) => ({ id: t.id, emoji: t.emoji, type: t.type, kind: t.kind, defaultTitle: t.title, defaultDescription: t.description,
    ...taskTexts(t), overridden: !!ov[t.id], answerKey: answerKey(t) }));
});
function answerKey(t) {
  switch (t.kind) {
    case 'quiz': return t.secret.map((id, i) => t.content.questions[i].options.find((o) => o[0] === id)[1]).join(' · ');
    case 'anagram': return t.secret.map((w) => w.toUpperCase()).join(' · ');
    case 'ghosts': return 'Пять привидений на картинке';
    case 'detective': return 'Зомби + улика «Электронный пропуск»';
    case 'sort': return t.secret.map((id) => t.content.items.find((i) => i[0] === id)[1]).join(' → ');
    case 'story': return 'Любые три ответа';
    case 'safe': return t.secret;
    case 'archive': return t.content.labels.find((l) => l[0] === t.secret)[1];
    default: return 'Ручная проверка';
  }
}
route('POST', '/api/admin/tasks/(\\d+)', (req, res, body, m) => {
  requireAdmin(req);
  const t = taskFromParams(m);
  const ov = getSetting('task_overrides');
  const title = String(body.title || '').trim().slice(0, 80), description = String(body.description || '').trim().slice(0, 3000);
  if (body.reset || (!title && !description)) delete ov[t.id];
  else ov[t.id] = { title: title && title !== t.title ? title : undefined, description: description && description !== t.description ? description : undefined };
  setSetting('task_overrides', ov);
  return { ok: true };
});

route('GET', '/api/admin/secrets', (req, res, body, m, url) => {
  requireAdmin(req);
  const t = wantTest(url) ? 1 : 0;
  return q('SELECT * FROM secrets ORDER BY id DESC').all().map((s) => ({
    id: s.id, question: s.question, answers: JSON.parse(s.answers), active: !!s.active, createdAt: s.created_at,
    solvers: q('SELECT pl.name, a.solved_at FROM secret_answers a JOIN players pl ON pl.id = a.player_id WHERE a.secret_id = ? AND a.solved_at IS NOT NULL AND pl.is_test = ? ORDER BY a.solved_at').all(s.id, t),
  }));
});
route('POST', '/api/admin/secrets', (req, res, body) => {
  requireAdmin(req);
  const question = String(body.question || '').trim().slice(0, 1000);
  const answers = String(body.answers || '').split(/[\n;]/).map((s) => s.trim()).filter(Boolean).slice(0, 10);
  if (!question || !answers.length) throw new HttpError(400, 'Нужны вопрос и хотя бы один правильный ответ');
  q('INSERT INTO secrets (question, answers, created_at) VALUES (?, ?, ?)').run(question, JSON.stringify(answers), now());
  return { ok: true };
});
route('POST', '/api/admin/secrets/(\\d+)/(activate|deactivate|delete)', (req, res, body, m) => {
  requireAdmin(req);
  const id = Number(m[1]);
  tx(() => {
    if (m[2] === 'activate') { q('UPDATE secrets SET active = 0').run(); q('UPDATE secrets SET active = 1 WHERE id = ?').run(id); }
    else if (m[2] === 'deactivate') q('UPDATE secrets SET active = 0 WHERE id = ?').run(id);
    else q('DELETE FROM secrets WHERE id = ?').run(id);
  });
  return { ok: true };
});

// ---------- Награды ----------
function logDraw(text) {
  const log = getSetting('draw_log');
  log.push({ at: now(), text });
  setSetting('draw_log', log.slice(-100));
}
function secureShuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) { const j = crypto.randomInt(i + 1); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}
route('GET', '/api/admin/awards', (req) => {
  requireAdmin(req);
  const rows = leaderboard(false);
  const awarded = new Set(q('SELECT player_id FROM awards').all().map((r) => r.player_id));
  return {
    awards: awardsView(false), prizes: PRIZES, log: getSetting('draw_log').map((l) => ({ ...l, atMsk: fmtMsk(l.at) })),
    pending: q("SELECT COUNT(*) n FROM submissions s JOIN players pl ON pl.id = s.player_id WHERE s.status = 'pending' AND pl.is_test = 0").get().n,
    candidates: rows.filter((r) => !awarded.has(r.id)).map((r) => ({ id: r.id, name: r.name, score: r.score, bingos: r.bingos })),
    showWinners: getSetting('show_winners'),
  };
});
route('POST', '/api/admin/awards/draw-top', (req, res, body) => {
  requireAdmin(req);
  const pending = q("SELECT COUNT(*) n FROM submissions s JOIN players pl ON pl.id = s.player_id WHERE s.status = 'pending' AND pl.is_test = 0").get().n;
  if (pending && !body.force) throw new HttpError(409, `Сначала проверьте все ответы: на проверке ещё ${pending}.`);
  const rows = leaderboard(false).filter((r) => r.score > 0);
  if (!rows.length) throw new HttpError(409, 'Пока нет участников с баллами');
  // Группы с равными баллами перемешиваются криптографически стойким генератором; ход жеребьёвки пишется в журнал.
  const groups = [];
  for (const r of rows) { const g = groups[groups.length - 1]; if (g && g.score === r.score) g.items.push(r); else groups.push({ score: r.score, items: [r] }); }
  const order = []; const notes = [];
  for (const g of groups) {
    if (order.length >= 3) break;
    if (g.items.length === 1) { order.push(g.items[0]); continue; }
    const sh = secureShuffle(g.items);
    notes.push(`Равенство (${g.score} б.): ${g.items.map((i) => i.name).join(', ')} → жребий: ${sh.map((i) => i.name).join(', ')}.`);
    order.push(...sh);
  }
  const cats = ['first', 'second', 'third'];
  tx(() => {
    q('DELETE FROM awards').run();
    order.slice(0, 3).forEach((r, i) => q('INSERT INTO awards (category, player_id, created_at) VALUES (?, ?, ?)').run(cats[i], r.id, now()));
  });
  logDraw(`Определены призёры: ${order.slice(0, 3).map((r, i) => `${i + 1}) ${r.name} — ${r.score} б.`).join('; ')}.` + (notes.length ? ' ' + notes.join(' ') : ' Жребий не понадобился.') + ' Специальные номинации сброшены.');
  return { ok: true };
});
route('POST', '/api/admin/awards/creative', (req, res, body) => {
  requireAdmin(req);
  if (!q("SELECT 1 FROM awards WHERE category = 'first'").get()) throw new HttpError(409, 'Сначала определите призёров 1–3 мест');
  const pid = Number(body.playerId);
  const pl = q('SELECT * FROM players WHERE id = ? AND is_test = 0').get(pid);
  if (!pl) throw new HttpError(404, 'Участник не найден');
  if (q("SELECT 1 FROM awards WHERE player_id = ? AND category != 'creative'").get(pid)) throw new HttpError(409, 'Этот участник уже получил приз');
  q("INSERT INTO awards (category, player_id, created_at) VALUES ('creative', ?, ?) ON CONFLICT(category) DO UPDATE SET player_id = excluded.player_id, created_at = excluded.created_at").run(pid, now());
  logDraw(`Номинация «Самый креативный участник»: ${pl.name} (выбор организатора).`);
  return { ok: true };
});
route('POST', '/api/admin/awards/random-bingo', (req) => {
  requireAdmin(req);
  if (!q("SELECT 1 FROM awards WHERE category = 'first'").get()) throw new HttpError(409, 'Сначала определите призёров 1–3 мест');
  const awarded = new Set(q("SELECT player_id FROM awards WHERE category != 'random_bingo'").all().map((r) => r.player_id));
  const pool = leaderboard(false).filter((r) => r.bingos > 0 && !awarded.has(r.id));
  if (!pool.length) throw new HttpError(409, 'Нет ненаграждённых участников с БИНГО');
  const win = pool[crypto.randomInt(pool.length)];
  q("INSERT INTO awards (category, player_id, created_at) VALUES ('random_bingo', ?, ?) ON CONFLICT(category) DO UPDATE SET player_id = excluded.player_id, created_at = excluded.created_at").run(win.id, now());
  logDraw(`Случайный участник с БИНГО: ${win.name}. Участвовали (${pool.length}): ${pool.map((r) => r.name).join(', ')}.`);
  return { ok: true, winner: win.name };
});
route('POST', '/api/admin/awards/reset', (req) => {
  requireAdmin(req);
  q('DELETE FROM awards').run();
  logDraw('Все награды сброшены организатором.');
  return { ok: true };
});

route('GET', '/api/admin/export.csv', (req, res, body, m, url) => {
  requireAdmin(req);
  const players = adminPlayers(wantTest(url));
  const awards = new Map(q('SELECT * FROM awards').all().map((a) => [a.player_id, PRIZES[a.category]]));
  const ST = { not_started: 'не начато', in_progress: 'выполняется', review: 'на проверке', done: 'выполнено', retry: 'попробуй ещё раз', failed: 'попытки исчерпаны' };
  const head = ['Место', 'Участник', 'Код', 'Формат', 'Выполнено заданий', 'БИНГО', 'Баллы', 'Приз', 'Сумма, ₽', 'Регистрация (МСК)', ...TASKS.map((t) => `${t.id}. ${taskTexts(t).title}`)];
  const rows = players.sort((a, b) => a.rank - b.rank).map((p) => {
    const aw = awards.get(p.id);
    return [p.rank, p.name, p.code, p.format === 'office' ? 'Офис' : 'Удалённо', p.completed, p.bingos, p.score, aw ? aw.title : '', aw ? aw.amount : '', fmtMsk(p.createdAt),
      ...TASKS.map((t) => ST[p.statuses[t.id] || 'not_started'])];
  });
  sendCsv(res, `millor-halloween-results${wantTest(url) ? '-test' : ''}.csv`, [head, ...rows]);
});
route('GET', '/api/admin/answers.csv', (req, res, body, m, url) => {
  requireAdmin(req);
  const rows = q('SELECT s.*, pl.name FROM submissions s JOIN players pl ON pl.id = s.player_id WHERE pl.is_test = ? ORDER BY s.created_at').all(wantTest(url) ? 1 : 0);
  const ST = { pending: 'на проверке', approved: 'подтверждено', rejected: 'отклонено' };
  sendCsv(res, 'millor-creative-answers.csv', [['Участник', 'Задание', 'Ответ', 'Фото', 'Согласие на показ', 'Статус', 'Комментарий', 'Отправлено (МСК)'],
    ...rows.map((s) => [s.name, `${s.task_id}. ${taskTexts(TASK_BY_ID.get(s.task_id)).title}`, s.text, s.photo_id ? 'да' : 'нет', s.consent ? 'да' : 'нет', ST[s.status], s.comment, fmtMsk(s.created_at)])]);
});

route('POST', '/api/admin/demo/create', (req, res, body) => {
  requireAdmin(req);
  const n = Math.min(10, Math.max(1, Math.floor(Number(body.count) || 3)));
  const created = [];
  while (created.length < n) {
    const c = generateCode(true);
    try { q('INSERT INTO codes (code, is_test, note, created_at) VALUES (?, 1, ?, ?)').run(c, 'Тест', now()); created.push(c); } catch {}
  }
  return { created };
});
route('POST', '/api/admin/demo/clear', (req) => {
  requireAdmin(req);
  tx(() => {
    deletePlayers('p.is_test = 1');
    q('DELETE FROM codes WHERE is_test = 1').run();
  });
  return { ok: true };
});
route('POST', '/api/admin/wipe', (req, res, body) => {
  requireAdmin(req);
  if (body.confirm !== 'УДАЛИТЬ') throw new HttpError(400, 'Введите слово УДАЛИТЬ для подтверждения');
  tx(() => {
    q('DELETE FROM players').run();
    q('DELETE FROM uploads').run();
    q('DELETE FROM secrets').run();
    q('DELETE FROM awards').run();
    if (body.codes) q('DELETE FROM codes').run();
    setSetting('draw_log', []);
  });
  for (const f of fs.readdirSync(UPLOAD_DIR)) { try { fs.unlinkSync(path.join(UPLOAD_DIR, f)); } catch {} }
  db.exec('VACUUM');
  return { ok: true };
});

// ---------- Статика ----------
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.webmanifest': 'application/manifest+json' };
function serveStatic(req, res, pathname) {
  if (pathname === '/' || pathname === '') pathname = '/index.html';
  if (pathname === '/admin' || pathname === '/admin/') pathname = '/admin.html';
  const file = path.normalize(path.join(PUBLIC_DIR, pathname));
  if (!file.startsWith(PUBLIC_DIR + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    return send(res, 404, 'Не найдено', { 'Content-Type': 'text/plain; charset=utf-8' });
  }
  const ext = path.extname(file);
  send(res, 200, fs.readFileSync(file), { 'Content-Type': MIME[ext] || 'application/octet-stream', 'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=300' });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  try {
    if (!url.pathname.startsWith('/api/') && url.pathname !== '/logo') return serveStatic(req, res, url.pathname);
    const r = routes.find((x) => x.method === req.method && x.re.test(url.pathname));
    if (!r) throw new HttpError(404, 'Неизвестный адрес');
    checkSameOrigin(req);
    const limit = /\/(submit|logo)$/.test(url.pathname) ? 8 * 1024 * 1024 : 64 * 1024;
    const body = req.method === 'POST' ? await readBody(req, limit) : {};
    const result = await r.handler(req, res, body, url.pathname.match(r.re), url);
    if (!res.headersSent) json(res, 200, result === undefined ? { ok: true } : result);
  } catch (e) {
    if (!(e instanceof HttpError)) console.error(e);
    if (!res.headersSent) json(res, e.status || 500, { error: e instanceof HttpError ? e.message : 'Внутренняя ошибка сервера' });
  }
});
server.requestTimeout = 60_000;

setInterval(() => {
  q('DELETE FROM sessions WHERE expires_at < ?').run(now());
  q('DELETE FROM admin_sessions WHERE expires_at < ?').run(now());
}, 3600_000).unref();

if (require.main === module) {
  server.listen(PORT, HOST, () => console.log(`Миллор Групп: Секретная лаборатория — http://${HOST}:${PORT}  (админка: /admin)`));
}
module.exports = { server, db };
