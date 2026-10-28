'use strict';
// «Миллор Фарма: Секретная лаборатория — Halloween Bingo». Сервер без внешних зависимостей (Node.js ≥ 22.13, встроенный SQLite).
process.removeAllListeners('warning');
process.on('warning', (w) => { if (w.name !== 'ExperimentalWarning') console.warn(w); });

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { DatabaseSync } = require('node:sqlite');
const G = require('./tasks');
const { ghostScene } = require('./scene');
const { posterSvg } = require('./poster');
const { TASKS, TASK_BY_ID, ENGINES, CREATIVE, LINES, LINE_NAMES, BINGO_MIN, BINGO_BONUS, AUTO_IDS, CREATIVE_IDS } = G;

const PORT = Number(process.env.PORT) || 3000;
const HOST = process.env.HOST || '0.0.0.0';
const DATA_DIR = path.resolve(process.env.DATA_DIR || path.join(__dirname, 'data'));
const UPLOAD_DIR = path.join(DATA_DIR, 'uploads');
const PUBLIC_DIR = path.join(__dirname, 'public');
const COOKIE_SECURE = process.env.COOKIE_SECURE === '1';
const TRUST_PROXY = process.env.TRUST_PROXY === '1';
const ADMIN_EMAIL = String(process.env.ADMIN_EMAIL || '').trim().toLowerCase();
const MAX_ATTEMPTS = 2;
const SECOND_ATTEMPT_PENALTY = 2;
const PLAYER_SESSION_DAYS = 14;
const ADMIN_SESSION_HOURS = 10;
const IMAGE_LIMIT = 6 * 1024 * 1024;
const VIDEO_LIMIT = 40 * 1024 * 1024;
const MAX_UPLOADS_PER_PLAYER = 8;

fs.mkdirSync(UPLOAD_DIR, { recursive: true });

// Секрет сервера: перец для хэшей кодов и ключ шифрования копии кода (чтобы организатор мог повторно выгрузить список).
const KEY_FILE = path.join(DATA_DIR, 'secret.key');
if (!fs.existsSync(KEY_FILE)) fs.writeFileSync(KEY_FILE, crypto.randomBytes(32).toString('hex'), { mode: 0o600 });
const KEY = Buffer.from(fs.readFileSync(KEY_FILE, 'utf8').trim(), 'hex');
const codeHash = (code) => crypto.createHmac('sha256', KEY).update(code).digest('hex');
function encCode(code) {
  const iv = crypto.randomBytes(12); const c = crypto.createCipheriv('aes-256-gcm', KEY, iv);
  const enc = Buffer.concat([c.update(code, 'utf8'), c.final()]);
  return [iv, c.getAuthTag(), enc].map((b) => b.toString('base64')).join('.');
}
function decCode(s) {
  try {
    const [iv, tag, enc] = s.split('.').map((x) => Buffer.from(x, 'base64'));
    const d = crypto.createDecipheriv('aes-256-gcm', KEY, iv); d.setAuthTag(tag);
    return Buffer.concat([d.update(enc), d.final()]).toString('utf8');
  } catch { return ''; }
}

// ---------- База данных ----------
const db = new DatabaseSync(path.join(DATA_DIR, 'game.db'));
db.exec(`
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, code_hash TEXT NOT NULL UNIQUE, code_enc TEXT NOT NULL, is_test INTEGER NOT NULL DEFAULT 0,
  revoked INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS players (
  id INTEGER PRIMARY KEY AUTOINCREMENT, code_id INTEGER NOT NULL UNIQUE REFERENCES codes(id) ON DELETE CASCADE,
  name TEXT NOT NULL, work_format TEXT NOT NULL, is_test INTEGER NOT NULL DEFAULT 0, rules_seen INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL, last_seen INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS admin_sessions (token_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS progress (
  player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, task_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'new', attempts_used INTEGER NOT NULL DEFAULT 0, best INTEGER, closed INTEGER NOT NULL DEFAULT 0,
  hint_used INTEGER NOT NULL DEFAULT 0, completed_at INTEGER, updated_at INTEGER NOT NULL, PRIMARY KEY (player_id, task_id));
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, task_id INTEGER NOT NULL,
  n INTEGER NOT NULL, started_at INTEGER NOT NULL, deadline_at INTEGER, finished_at INTEGER, state TEXT NOT NULL,
  raw INTEGER, final INTEGER, detail TEXT);
CREATE INDEX IF NOT EXISTS attempts_open ON attempts(finished_at, deadline_at);
CREATE INDEX IF NOT EXISTS attempts_pt ON attempts(player_id, task_id);
CREATE TABLE IF NOT EXISTS drafts (player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, task_id INTEGER NOT NULL, data TEXT NOT NULL, media TEXT NOT NULL DEFAULT '[]', updated_at INTEGER NOT NULL, PRIMARY KEY (player_id, task_id));
CREATE TABLE IF NOT EXISTS uploads (id TEXT PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, kind TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, task_id INTEGER NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL, media TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'pending',
  criteria TEXT NOT NULL DEFAULT '[]', points INTEGER, comment TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL, reviewed_at INTEGER);
CREATE INDEX IF NOT EXISTS submissions_status ON submissions(status);
CREATE TABLE IF NOT EXISTS adjustments (player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, task_id INTEGER NOT NULL, points INTEGER NOT NULL, reason TEXT NOT NULL, actor TEXT NOT NULL, at INTEGER NOT NULL, PRIMARY KEY (player_id, task_id));
CREATE TABLE IF NOT EXISTS point_log (id INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER NOT NULL, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE, task_id INTEGER, kind TEXT NOT NULL, points INTEGER, note TEXT NOT NULL, actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);
`);

const q = (sql) => db.prepare(sql);
const now = () => Date.now();
function tx(fn) {
  db.exec('BEGIN IMMEDIATE');
  try { const r = fn(); db.exec('COMMIT'); return r; } catch (e) { db.exec('ROLLBACK'); throw e; }
}

const DEFAULT_SETTINGS = {
  game_start: '2026-10-30T10:00:00+03:00', game_end: '2026-10-30T17:00:00+03:00',
  game_state: 'idle', auto_start: true, timers: {}, tie_draw: {}, final_0: null, final_1: null, logo: null, admin_pw: null, admin_setup: null,
};
function getSetting(key) { const r = q('SELECT value FROM settings WHERE key = ?').get(key); return r ? JSON.parse(r.value) : structuredClone(DEFAULT_SETTINGS[key] ?? null); }
function setSetting(key, v) { q('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value').run(key, JSON.stringify(v)); }
function audit(actor, action, detail) { q('INSERT INTO audit_log (at, actor, action, detail) VALUES (?, ?, ?, ?)').run(now(), actor, action, typeof detail === 'string' ? detail : JSON.stringify(detail)); }
const timers = () => ({ ...G.TIMER_DEFAULTS, ...getSetting('timers') });

// ---------- Состояние игры (серверное московское время — источник истины) ----------
function gameStatus() {
  const state = getSetting('game_state'), start = Date.parse(getSetting('game_start')), end = Date.parse(getSetting('game_end')), t = now();
  let phase;
  if (state === 'ended') phase = 'ended';
  else if (state === 'paused') phase = t >= end ? 'ended' : 'paused';
  else if (state === 'running') phase = t >= end ? 'ended' : 'running';
  else phase = t >= end ? 'ended' : getSetting('auto_start') && t >= start ? 'running' : 'before';
  return { state, phase, start: getSetting('game_start'), end: getSetting('game_end'), autoStart: getSetting('auto_start'), serverTime: t };
}
const canStart = (p) => p.is_test === 1 || gameStatus().phase === 'running';
const canSubmit = (p) => p.is_test === 1 || ['running', 'paused'].includes(gameStatus().phase);
const getFinal = (isTest) => getSetting(isTest ? 'final_1' : 'final_0');
function assertNotFrozen(p) { if (getFinal(p.is_test === 1)) throw new HttpError(423, 'Итоги уже подведены'); }

// ---------- Утилиты HTTP ----------
class HttpError extends Error { constructor(status, message) { super(message); this.status = status; } }
const sha = (s) => crypto.createHash('sha256').update(s).digest('hex');
const newToken = () => crypto.randomBytes(32).toString('base64url');
const safeEq = (a, b) => { const x = Buffer.from(a), y = Buffer.from(b); return x.length === y.length && crypto.timingSafeEqual(x, y); };

function parseCookies(req) {
  const out = {};
  for (const part of (req.headers.cookie || '').split(';')) { const i = part.indexOf('='); if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim()); }
  return out;
}
function setCookie(res, name, value, maxAgeSec, sameSite = 'Lax') {
  const parts = [`${name}=${encodeURIComponent(value)}`, 'Path=/', 'HttpOnly', `SameSite=${sameSite}`, `Max-Age=${maxAgeSec}`];
  if (COOKIE_SECURE) parts.push('Secure');
  res.setHeader('Set-Cookie', [...(res.getHeader('Set-Cookie') || []), parts.join('; ')]);
}
const clientIp = (req) => (TRUST_PROXY && req.headers['x-forwarded-for'] ? String(req.headers['x-forwarded-for']).split(',')[0].trim() : req.socket.remoteAddress || '?');

const buckets = new Map();
function bucket(key, windowMs) { const t = now(); let b = buckets.get(key); if (!b || b.reset < t) { b = { n: 0, reset: t + windowMs }; buckets.set(key, b); } return b; }
const TOO_MANY = 'Слишком много попыток. Подождите несколько минут.';
function rateLimit(key, limit, windowMs) { const b = bucket(key, windowMs); if (++b.n > limit) throw new HttpError(429, TOO_MANY); }
function failGuard(key, limit, windowMs) { const b = bucket(key, windowMs); if (b.n >= limit) throw new HttpError(429, TOO_MANY); return () => { b.n++; }; }
setInterval(() => { const t = now(); for (const [k, b] of buckets) if (b.reset < t) buckets.delete(k); }, 60_000).unref();

function readRaw(req, limit) {
  return new Promise((resolve, reject) => {
    if (Number(req.headers['content-length']) > limit) { reject(new HttpError(413, 'Файл слишком большой')); req.resume(); return; }
    let size = 0; const chunks = [];
    req.on('data', (c) => { size += c.length; if (size > limit) { reject(new HttpError(413, 'Файл слишком большой')); req.destroy(); return; } chunks.push(c); });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}
async function readJson(req, limit = 256 * 1024) {
  const buf = await readRaw(req, limit);
  if (!buf.length) return {};
  try { return JSON.parse(buf.toString('utf8')); } catch { throw new HttpError(400, 'Некорректный JSON'); }
}

const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin', 'X-Frame-Options': 'DENY',
  'Content-Security-Policy': "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
};
function send(res, status, body, headers = {}) { res.writeHead(status, { ...SECURITY_HEADERS, ...headers }); res.end(body); }
const json = (res, status, obj) => send(res, status, JSON.stringify(obj), { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
const csvCell = (v) => { let s = v == null ? '' : String(v); if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
const toCsv = (rows) => '﻿' + rows.map((r) => r.map(csvCell).join(';')).join('\r\n') + '\r\n';
const sendCsv = (res, name, rows) => send(res, 200, toCsv(rows), { 'Content-Type': 'text/csv; charset=utf-8', 'Cache-Control': 'no-store', 'Content-Disposition': `attachment; filename="${name}"` });
const fmtMsk = (ms) => (ms ? new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', dateStyle: 'short', timeStyle: 'medium' }).format(ms) : '');

// ---------- Аутентификация ----------
function currentPlayer(req) {
  const tok = parseCookies(req).mgp_s;
  if (!tok) return null;
  return q(`SELECT p.* FROM sessions s JOIN players p ON p.id = s.player_id JOIN codes c ON c.id = p.code_id
            WHERE s.token_hash = ? AND s.expires_at > ? AND c.revoked = 0`).get(sha(tok), now()) || null;
}
function requirePlayer(req) { const p = currentPlayer(req); if (!p) throw new HttpError(401, 'Нужно войти по игровому коду'); return p; }
const isAdmin = (req) => { const tok = parseCookies(req).mgp_a; return !!tok && !!q('SELECT 1 FROM admin_sessions WHERE token_hash = ? AND expires_at > ?').get(sha(tok), now()); };
function requireAdmin(req) { if (!isAdmin(req)) throw new HttpError(401, 'Требуется вход администратора'); }
const adminActor = () => ADMIN_EMAIL || 'admin';
const scopeOf = (req) => (req.headers['x-scope'] === 'test' || new URL(req.url, 'http://x').searchParams.get('scope') === 'test' ? 1 : 0);

function checkSameOrigin(req, raw) {
  if (req.method === 'GET' || req.method === 'HEAD') return;
  if (raw) { if (req.headers['x-requested-with'] !== 'mgp') throw new HttpError(403, 'Недопустимый запрос'); }
  else if (!(req.headers['content-type'] || '').startsWith('application/json')) throw new HttpError(415, 'Ожидается JSON');
  const origin = req.headers.origin;
  if (origin) { try { if (new URL(origin).host !== (req.headers['x-forwarded-host'] || req.headers.host)) throw 0; } catch { throw new HttpError(403, 'Запрос с чужого сайта'); } }
}

const CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
function generateCode(isTest) {
  const pick = (n) => Array.from({ length: n }, () => CODE_ALPHABET[crypto.randomInt(CODE_ALPHABET.length)]).join('');
  return `${isTest ? 'TST' : 'MLF'}-${pick(4)}-${pick(4)}-${pick(4)}`;
}
function normCode(s) {
  const t = String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  const m = /^(MLF|TST)([A-Z0-9]{4})([A-Z0-9]{4})([A-Z0-9]{4})$/.exec(t);
  return m ? `${m[1]}-${m[2]}-${m[3]}-${m[4]}` : t;
}

// ---------- Пароль администратора ----------
function hashPassword(pw) { const salt = crypto.randomBytes(16); return `scrypt$${salt.toString('hex')}$${crypto.scryptSync(pw, salt, 64).toString('hex')}`; }
function verifyPassword(pw, stored) {
  const [alg, salt, hash] = String(stored || '').split('$');
  const calc = crypto.scryptSync(pw, Buffer.from(salt || '00', 'hex'), 64);
  return alg === 'scrypt' && !!hash && safeEq(calc.toString('hex'), hash);
}
function createSetupToken() {
  const tok = crypto.randomBytes(12).toString('hex');
  setSetting('admin_setup', { hash: sha(tok) });
  const f = path.join(DATA_DIR, 'admin-setup.txt');
  fs.writeFileSync(f, `Код первой настройки администратора: ${tok}\n`, { mode: 0o600 });
  console.log(`[admin] Код первой настройки: ${tok}  (также в файле ${f}). Откройте /admin и задайте пароль для ${ADMIN_EMAIL}.`);
}
function ensureAdminSetup() {
  if (!ADMIN_EMAIL) { console.warn('[admin] ADMIN_EMAIL не задан — вход в панель организатора отключён.'); return; }
  if (!getSetting('admin_pw') && !getSetting('admin_setup')) createSetupToken();
}
if (process.argv.includes('--reset-admin')) {
  if (!ADMIN_EMAIL) { console.error('Задайте ADMIN_EMAIL'); process.exit(1); }
  setSetting('admin_pw', null); q('DELETE FROM admin_sessions').run(); createSetupToken(); audit('cli', 'reset-admin', ADMIN_EMAIL); process.exit(0);
}
ensureAdminSetup();

// ---------- Загрузки ----------
function detectMedia(buf) {
  if (buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff) return { kind: 'image', mime: 'image/jpeg' };
  if (buf.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return { kind: 'image', mime: 'image/png' };
  if (buf.subarray(0, 4).toString('latin1') === 'RIFF' && buf.subarray(8, 12).toString('latin1') === 'WEBP') return { kind: 'image', mime: 'image/webp' };
  if (buf.subarray(4, 8).toString('latin1') === 'ftyp') return { kind: 'video', mime: buf.subarray(8, 12).toString('latin1') === 'qt  ' ? 'video/quicktime' : 'video/mp4' };
  if (buf[0] === 0x1a && buf[1] === 0x45 && buf[2] === 0xdf && buf[3] === 0xa3) return { kind: 'video', mime: 'video/webm' };
  return null;
}
function serveFile(req, res, file, mime) {
  const size = fs.statSync(file).size;
  const h = { ...SECURITY_HEADERS, 'Content-Type': mime, 'Accept-Ranges': 'bytes', 'Cache-Control': 'private, max-age=600', 'Content-Disposition': 'inline' };
  const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || '');
  if (m && (m[1] || m[2])) {
    let start = m[1] ? Number(m[1]) : Math.max(0, size - Number(m[2])), end = m[1] && m[2] ? Number(m[2]) : size - 1;
    end = Math.min(end, size - 1);
    if (start > end || start >= size) { res.writeHead(416, { ...h, 'Content-Range': `bytes */${size}` }); return res.end(); }
    res.writeHead(206, { ...h, 'Content-Range': `bytes ${start}-${end}/${size}`, 'Content-Length': end - start + 1 });
    return fs.createReadStream(file, { start, end }).pipe(res);
  }
  res.writeHead(200, { ...h, 'Content-Length': size });
  fs.createReadStream(file).pipe(res);
}
const removeUploadFiles = (ids) => { for (const id of ids) { try { fs.unlinkSync(path.join(UPLOAD_DIR, id)); } catch {} } };
function deletePlayers(where, ...args) {
  const ids = q(`SELECT u.id FROM uploads u JOIN players p ON p.id = u.player_id WHERE ${where}`).all(...args).map((r) => r.id);
  q(`DELETE FROM players WHERE ${where.replace(/\bp\./g, '')}`).run(...args);
  removeUploadFiles(ids);
}

// ---------- Очки, БИНГО, рейтинг ----------
const progressOf = (pid, tid) => q('SELECT * FROM progress WHERE player_id = ? AND task_id = ?').get(pid, tid);
function upsertProgress(pid, tid, f) {
  const cur = progressOf(pid, tid) || { status: 'new', attempts_used: 0, best: null, closed: 0, hint_used: 0, completed_at: null };
  const m = { ...cur, ...f, updated_at: now() };
  q(`INSERT INTO progress (player_id, task_id, status, attempts_used, best, closed, hint_used, completed_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(player_id, task_id) DO UPDATE SET status = excluded.status, attempts_used = excluded.attempts_used, best = excluded.best, closed = excluded.closed,
     hint_used = excluded.hint_used, completed_at = excluded.completed_at, updated_at = excluded.updated_at`)
    .run(pid, tid, m.status, m.attempts_used, m.best, m.closed, m.hint_used, m.completed_at, m.updated_at);
}
function logPoints(pid, tid, kind, points, note, actor = 'система') { q('INSERT INTO point_log (at, player_id, task_id, kind, points, note, actor) VALUES (?, ?, ?, ?, ?, ?, ?)').run(now(), pid, tid, kind, points, note, actor); }

function scoreFromPoints(pts) { // pts: Map taskId -> points | null
  const lines = [];
  LINES.forEach((l, i) => { if (l.every((t) => (pts.get(t) ?? -1) >= BINGO_MIN)) lines.push(i); });
  let auto = 0, creative = 0, tens = 0;
  for (const [t, v] of pts) { if (v == null) continue; if (AUTO_IDS.includes(t)) auto += v; else creative += v; if (v === 10) tens++; }
  const bonus = lines.length * BINGO_BONUS;
  return { lines, bingos: lines.length, bonus, auto, creative, tens, total: auto + creative + bonus };
}
function loadPoints(pid) {
  const pts = new Map(TASKS.map((t) => [t.id, null]));
  for (const r of q('SELECT task_id, best FROM progress WHERE player_id = ?').all(pid)) if (r.best != null) pts.set(r.task_id, r.best);
  const adj = new Map();
  for (const a of q('SELECT * FROM adjustments WHERE player_id = ?').all(pid)) { pts.set(a.task_id, a.points); adj.set(a.task_id, a); }
  return { pts, adj };
}

const KEYS = (r) => [r.total, r.bingos, r.tens, -r.attempts];
function computeRows(isTest) {
  const t = isTest ? 1 : 0;
  const players = q('SELECT id, name, work_format, last_seen, created_at FROM players WHERE is_test = ?').all(t);
  const byP = new Map(players.map((p) => [p.id, { pts: new Map(TASKS.map((x) => [x.id, null])), attempts: 0, closed: 0, adj: new Set() }]));
  for (const r of q('SELECT p.* FROM progress p JOIN players pl ON pl.id = p.player_id WHERE pl.is_test = ?').all(t)) {
    const b = byP.get(r.player_id); if (!b) continue;
    if (r.best != null) b.pts.set(r.task_id, r.best);
    if (AUTO_IDS.includes(r.task_id)) b.attempts += r.attempts_used;
    if (r.closed) b.closed++;
  }
  for (const a of q('SELECT a.* FROM adjustments a JOIN players pl ON pl.id = a.player_id WHERE pl.is_test = ?').all(t)) { const b = byP.get(a.player_id); if (b) { b.pts.set(a.task_id, a.points); b.adj.add(a.task_id); } }
  const draw = getSetting('tie_draw');
  const rows = players.map((p) => {
    const b = byP.get(p.id);
    return { id: p.id, name: p.name, format: p.work_format, lastSeen: p.last_seen, ...scoreFromPoints(b.pts), attempts: b.attempts, closed: b.closed, pts: Object.fromEntries(b.pts), adjusted: [...b.adj], draw: draw[p.id] ?? null };
  });
  rows.sort((a, b) => {
    const ka = KEYS(a), kb = KEYS(b);
    for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return kb[i] - ka[i];
    return (a.draw ?? 0) - (b.draw ?? 0) || a.name.localeCompare(b.name, 'ru');
  });
  rows.forEach((r, i) => {
    const prev = rows[i - 1];
    const same = prev && KEYS(prev).every((v, k) => v === KEYS(r)[k]) && (prev.draw ?? 0) === (r.draw ?? 0);
    r.rank = same ? prev.rank : i + 1;
  });
  rows.forEach((r, i) => { r.tied = rows.some((o, j) => j !== i && o.rank === r.rank); });
  return rows;
}
const pendingCount = (isTest) => q("SELECT COUNT(*) n FROM submissions s JOIN players pl ON pl.id = s.player_id WHERE s.status = 'pending' AND pl.is_test = ?").get(isTest ? 1 : 0).n;
const publicRow = (r, meId) => ({ rank: r.rank, name: r.name, format: r.format, total: r.total, bingos: r.bingos, tens: r.tens, closed: r.closed, me: r.id === meId });
function ratingFor(player) {
  const isTest = player.is_test === 1;
  const fin = getFinal(isTest);
  const rows = fin ? fin.rows : computeRows(isTest);
  const pending = pendingCount(isTest);
  return { rows: rows.map((r) => publicRow(r, r.id)).map((r, i) => ({ ...r, me: rows[i].id === player.id })), final: !!fin, prelim: !fin, pending, phase: gameStatus().phase, top3: fin ? fin.top3 : null, finalAt: fin ? fin.at : null };
}

// ---------- Клетки поля ----------
const latestSub = (pid, tid) => q('SELECT * FROM submissions WHERE player_id = ? AND task_id = ? ORDER BY id DESC LIMIT 1').get(pid, tid);
function cellsFor(player) {
  const { pts, adj } = loadPoints(player.id);
  const prog = new Map(q('SELECT * FROM progress WHERE player_id = ?').all(player.id).map((r) => [r.task_id, r]));
  const drafts = new Set(q('SELECT task_id FROM drafts WHERE player_id = ?').all(player.id).map((r) => r.task_id));
  const cells = GRID_CELLS.map((tid, pos) => {
    const t = TASK_BY_ID.get(tid), pr = prog.get(tid), p = pts.get(tid);
    let state = 'new', label = 'Не начато';
    const scored = () => { state = p >= BINGO_MIN ? 'good' : 'partial'; };
    if (t.type === 'auto') {
      if (pr && pr.status === 'active') { state = 'active'; label = 'В процессе'; }
      else if (pr && pr.status === 'decide') { scored(); label = `Можно улучшить · ${p}/10`; }
      else if (pr && pr.closed) { scored(); label = `${p}/10`; }
    } else if (pr && pr.status === 'pending') { state = 'review'; label = 'На проверке'; }
    else if (pr && pr.status === 'returned') { state = 'returned'; label = 'Нужна доработка'; }
    else if (pr && pr.status === 'approved') { scored(); label = `${p}/10`; }
    else if (pr && pr.status === 'rejected') { state = 'rejected'; label = 'Отклонено · 0/10'; }
    else if (drafts.has(tid)) { state = 'active'; label = 'Черновик'; }
    if (adj.has(tid)) { scored(); label = `${p}/10 (скорр.)`; }
    return { id: tid, pos, emoji: t.emoji, title: t.title, type: t.type, state, label, closed: !!(pr && pr.closed), points: p, attemptsLeft: t.type === 'auto' ? Math.max(0, MAX_ATTEMPTS - (pr ? pr.attempts_used : 0)) : null };
  });
  return { cells, pts };
}
const GRID_CELLS = G.GRID;

function meView(player) {
  const { cells, pts } = cellsFor(player);
  const sc = scoreFromPoints(pts);
  const lines = LINES.map((l, i) => {
    const have = l.filter((t) => (pts.get(t) ?? -1) >= BINGO_MIN).length;
    return { idx: i, name: LINE_NAMES[i], tasks: l, have, complete: have === 4, need: 4 - have, cells: l.map((t) => ({ id: t, points: pts.get(t) ?? null })) };
  });
  const open = lines.filter((l) => !l.complete);
  const next = open.length ? Math.min(...open.map((l) => l.need)) : null;
  const rows = ratingFor(player);
  const mine = rows.rows.find((r) => r.me);
  const fin = getFinal(player.is_test === 1);
  return {
    player: { name: player.name, format: player.work_format, isTest: player.is_test === 1, rulesSeen: !!player.rules_seen },
    cells, lines, bingos: sc.bingos, bonus: sc.bonus, total: sc.total, tasksDone: cells.filter((c) => c.closed).length,
    nextBingo: next, rank: mine ? mine.rank : null, totalPlayers: rows.rows.length, prelim: rows.prelim, pending: rows.pending,
    game: { ...gameStatus(), openForMe: canStart(player) },
    final: fin ? { top3: fin.top3, at: fin.at, myRank: mine ? mine.rank : null, myTotal: sc.total } : null,
    logo: getSetting('logo') ? '/logo' : null,
  };
}

// ---------- Попытки ----------
const activeAttempt = (pid, tid) => q('SELECT * FROM attempts WHERE player_id = ? AND task_id = ? AND finished_at IS NULL').get(pid, tid);
const attemptCtx = (att, sec) => ({ now: now(), sec, startedAt: att.started_at, n: att.n });

function finalizeAttempt(att, task, eng, state, ctx) {
  const sc = eng.score(state, ctx);
  const raw = Math.max(0, Math.min(10, Math.round(sc.raw)));
  const final = att.n === 1 ? raw : Math.max(0, raw - SECOND_ATTEMPT_PENALTY);
  const parts = sc.parts.slice();
  if (att.n > 1) parts.push({ label: 'Штраф за вторую попытку', got: -Math.min(SECOND_ATTEMPT_PENALTY, raw), max: 0, penalty: true });
  q('UPDATE attempts SET finished_at = ?, state = ?, raw = ?, final = ?, detail = ? WHERE id = ? AND finished_at IS NULL')
    .run(now(), JSON.stringify(state), raw, final, JSON.stringify({ parts, hint: !!state.hint }), att.id);
  const pr = progressOf(att.player_id, att.task_id);
  const prev = pr && pr.best != null ? pr.best : null;
  const best = Math.max(prev ?? 0, final);
  const closed = att.n >= MAX_ATTEMPTS || final === 10 ? 1 : 0;
  upsertProgress(att.player_id, att.task_id, { status: closed ? 'closed' : 'decide', best, closed, completed_at: closed ? now() : null });
  if (prev == null || best > prev) logPoints(att.player_id, att.task_id, 'auto', best, `Попытка ${att.n}: ${raw} из 10${att.n > 1 ? ' − 2 (штраф)' : ''} → итог ${final}`);
  else logPoints(att.player_id, att.task_id, 'auto', best, `Попытка ${att.n}: итог ${final}, сохранён лучший результат ${best}`);
  return { n: att.n, raw, final, parts, best, closed: !!closed };
}
// Завершает попытку, если её время вышло или игра закончилась сама. Возвращает результат или null.
function settleAttempt(att) {
  const task = TASK_BY_ID.get(att.task_id), eng = ENGINES[task.kind];
  const state = JSON.parse(att.state), ctx = attemptCtx(att, timers()[task.id]);
  const before = JSON.stringify(state);
  if (eng.tick) eng.tick(state, ctx);
  const expired = att.deadline_at != null && ctx.now > att.deadline_at;
  if (expired || (eng.done && eng.done(state))) return finalizeAttempt(att, task, eng, state, ctx);
  if (JSON.stringify(state) !== before) q('UPDATE attempts SET state = ? WHERE id = ?').run(JSON.stringify(state), att.id);
  return null;
}
setInterval(() => {
  try {
    for (const att of q('SELECT * FROM attempts WHERE finished_at IS NULL').all()) {
      if ((att.deadline_at != null && now() > att.deadline_at - 5000) || ENGINES[TASK_BY_ID.get(att.task_id).kind].tick) tx(() => { const a = q('SELECT * FROM attempts WHERE id = ? AND finished_at IS NULL').get(att.id); if (a) settleAttempt(a); });
    }
  } catch (e) { console.error('sweeper', e); }
}, 2000).unref();

function lastFinished(pid, tid) {
  const a = q('SELECT * FROM attempts WHERE player_id = ? AND task_id = ? AND finished_at IS NOT NULL ORDER BY n DESC LIMIT 1').get(pid, tid);
  if (!a) return null;
  const d = JSON.parse(a.detail || '{}');
  return { n: a.n, raw: a.raw, final: a.final, parts: d.parts || [], finishedAt: a.finished_at };
}

function mediaList(ids) {
  return JSON.parse(ids || '[]').map((id) => { const u = q('SELECT id, kind, mime FROM uploads WHERE id = ?').get(id); return u ? { id, kind: u.kind, mime: u.mime, url: `/api/uploads/${id}` } : null; }).filter(Boolean);
}

function taskView(player, task) {
  let att = activeAttempt(player.id, task.id);
  if (att) { tx(() => { const a = activeAttempt(player.id, task.id); if (a) settleAttempt(a); }); att = activeAttempt(player.id, task.id); }
  const pr = progressOf(player.id, task.id);
  const { pts, adj } = loadPoints(player.id);
  const sec = timers()[task.id];
  const g = gameStatus();
  const out = {
    meta: { id: task.id, emoji: task.emoji, title: task.title, type: task.type, kind: task.kind, story: task.story, rules: task.rules.map((r) => r.replace('{sec}', sec)), sec: sec ?? null },
    points: pts.get(task.id), adjusted: adj.has(task.id), serverTime: now(), phase: g.phase, frozen: !!getFinal(player.is_test === 1),
    status: pr ? pr.status : 'new',
  };
  if (task.type === 'auto') {
    const used = pr ? pr.attempts_used : 0;
    out.attempts = { used, left: Math.max(0, MAX_ATTEMPTS - used), closed: !!(pr && pr.closed), decide: !!(pr && pr.status === 'decide'), hintUsed: !!(pr && pr.hint_used) };
    out.last = lastFinished(player.id, task.id);
    out.canStart = canStart(player) && !out.frozen && !att && !out.attempts.closed && out.attempts.left > 0;
    if (att) {
      const eng = ENGINES[task.kind], ctx = attemptCtx(att, sec), st = JSON.parse(att.state);
      out.active = { id: att.id, n: att.n, startedAt: att.started_at, deadlineAt: G.displayDeadline(task, att.started_at, sec), hardDeadline: att.deadline_at, view: eng.view(st, ctx) };
    }
  } else {
    const def = CREATIVE[task.id];
    const sub = latestSub(player.id, task.id);
    const draft = q('SELECT * FROM drafts WHERE player_id = ? AND task_id = ?').get(player.id, task.id);
    const closed = !!(pr && pr.closed);
    out.creative = {
      fields: def.fields, media: def.media || null, criteria: def.criteria, mediaOrNote: def.mediaOrNote || null,
      submission: sub ? { id: sub.id, status: sub.status, revision: sub.revision, data: JSON.parse(sub.data), media: mediaList(sub.media), comment: sub.comment, points: sub.points, criteria: JSON.parse(sub.criteria) } : null,
      draft: draft ? { data: JSON.parse(draft.data), media: mediaList(draft.media) } : null,
      canEdit: !closed && (!sub || sub.status === 'returned') && canSubmit(player) && !out.frozen,
    };
  }
  return out;
}

// ---------- Маршруты ----------
const routes = [];
const route = (method, pattern, handler, opts = {}) => routes.push({ method, re: new RegExp(`^${pattern}$`), handler, raw: !!opts.raw });
const taskParam = (m) => { const t = TASK_BY_ID.get(Number(m[1])); if (!t) throw new HttpError(404, 'Задание не найдено'); return t; };
function assertTaskOpen(player) {
  const g = gameStatus();
  if (player.is_test !== 1 && g.phase === 'before') throw new HttpError(423, 'Лаборатория ещё закрыта. Задания откроются в начале игры.');
}

route('GET', '/api/public', () => ({ game: gameStatus(), logo: getSetting('logo') ? '/logo' : null }));

route('POST', '/api/login', async (req, res, body) => {
  const fail = failGuard('login:' + clientIp(req), 30, 10 * 60_000);
  const failAll = failGuard('login-all', 300, 10 * 60_000);
  rateLimit('login-req:' + clientIp(req), 120, 10 * 60_000);
  const code = normCode(body.code);
  const c = q('SELECT * FROM codes WHERE code_hash = ? AND revoked = 0').get(codeHash(code));
  if (!c) { fail(); failAll(); throw new HttpError(401, 'Код не найден или отключён. Проверьте код у организатора.'); }
  let player = q('SELECT * FROM players WHERE code_id = ?').get(c.id);
  if (!player) {
    const name = String(body.name || '').replace(/\s+/g, ' ').trim();
    const format = body.format === 'office' || body.format === 'remote' ? body.format : null;
    if (!name) return { needsProfile: true };
    if (name.length < 2 || name.length > 60) throw new HttpError(400, 'Имя и фамилия: от 2 до 60 символов');
    if (!format) throw new HttpError(400, 'Выберите «Офис» или «Удалённо»');
    try { q('INSERT INTO players (code_id, name, work_format, is_test, created_at, last_seen) VALUES (?, ?, ?, ?, ?, ?)').run(c.id, name, format, c.is_test, now(), now()); } catch {}
    player = q('SELECT * FROM players WHERE code_id = ?').get(c.id);
  }
  const tok = newToken();
  q('INSERT INTO sessions (token_hash, player_id, expires_at) VALUES (?, ?, ?)').run(sha(tok), player.id, now() + PLAYER_SESSION_DAYS * 864e5);
  setCookie(res, 'mgp_s', tok, PLAYER_SESSION_DAYS * 86400);
  return { ok: true, name: player.name };
});
route('POST', '/api/logout', (req, res) => { const tok = parseCookies(req).mgp_s; if (tok) q('DELETE FROM sessions WHERE token_hash = ?').run(sha(tok)); setCookie(res, 'mgp_s', '', 0); return { ok: true }; });
route('GET', '/api/me', (req) => { const p = requirePlayer(req); q('UPDATE players SET last_seen = ? WHERE id = ?').run(now(), p.id); return meView(p); });
route('POST', '/api/me/rules-seen', (req) => { const p = requirePlayer(req); q('UPDATE players SET rules_seen = 1 WHERE id = ?').run(p.id); return { ok: true }; });
route('GET', '/api/leaderboard', (req) => ratingFor(requirePlayer(req)));

route('GET', '/api/tasks/(\\d+)', (req, res, body, m) => { const p = requirePlayer(req); const t = taskParam(m); assertTaskOpen(p); return taskView(p, t); });
route('GET', '/api/scene.svg', (req, res) => {
  const p = requirePlayer(req); assertTaskOpen(p);
  send(res, 200, ghostScene(G.GHOSTS), { 'Content-Type': 'image/svg+xml; charset=utf-8', 'Cache-Control': 'private, max-age=600' });
});
route('GET', '/api/poster.svg', (req, res) => send(res, 200, posterSvg(), { 'Content-Type': 'image/svg+xml; charset=utf-8', 'Cache-Control': 'public, max-age=3600' }));

route('POST', '/api/tasks/(\\d+)/start', (req, res, body, m) => {
  const p = requirePlayer(req); const t = taskParam(m);
  if (t.type !== 'auto') throw new HttpError(400, 'Это творческое задание');
  assertTaskOpen(p); assertNotFrozen(p);
  if (!canStart(p)) throw new HttpError(423, gameStatus().phase === 'paused' ? 'Организатор поставил приём новых попыток на паузу.' : 'Игра не идёт — новые попытки не принимаются.');
  rateLimit('start:' + p.id, 60, 60_000);
  tx(() => {
    const open = activeAttempt(p.id, t.id);
    if (open && !settleAttempt(open)) return;
    const pr = progressOf(p.id, t.id);
    if (pr && pr.closed) throw new HttpError(409, 'Задание уже закрыто');
    const used = pr ? pr.attempts_used : 0;
    if (used >= MAX_ATTEMPTS) throw new HttpError(409, 'Попытки закончились. Третьей попытки не бывает.');
    const n = used + 1, startedAt = now(), sec = timers()[t.id];
    const eng = ENGINES[t.kind];
    const state = eng.init({ now: startedAt, sec, hint: !!(pr && pr.hint_used), n });
    q('INSERT INTO attempts (player_id, task_id, n, started_at, deadline_at, state) VALUES (?, ?, ?, ?, ?, ?)').run(p.id, t.id, n, startedAt, G.deadlineFor(t, startedAt, sec), JSON.stringify(state));
    upsertProgress(p.id, t.id, { status: 'active', attempts_used: n });
  });
  return { task: taskView(p, t) };
});

route('POST', '/api/tasks/(\\d+)/act', (req, res, body, m) => {
  const p = requirePlayer(req); const t = taskParam(m);
  if (t.type !== 'auto') throw new HttpError(400, 'Это творческое задание');
  rateLimit('act:' + p.id, 900, 60_000);
  let result = null, feedback = null;
  tx(() => {
    const att = activeAttempt(p.id, t.id);
    if (!att) return;
    const settled = settleAttempt(att);
    if (settled) { result = settled; return; }
    const fresh = activeAttempt(p.id, t.id);
    const eng = ENGINES[t.kind], sec = timers()[t.id], ctx = attemptCtx(fresh, sec), state = JSON.parse(fresh.state);
    const action = String(body.action || '');
    let done = false;
    if (action === 'sync') { /* только обновить */ }
    else if (action === 'save') { if (!eng.save) throw new HttpError(400, 'Сохранение недоступно'); eng.save(state, body); }
    else if (action === 'finish') { if (eng.save && body.data) eng.save(state, body.data); done = true; }
    else {
      const r = eng.act(state, action, body, ctx);
      done = !!r.done; feedback = r.feedback || null;
      if (r.hintUsed) upsertProgress(p.id, t.id, { hint_used: 1 });
    }
    if (done) result = finalizeAttempt(fresh, t, eng, state, ctx);
    else q('UPDATE attempts SET state = ? WHERE id = ?').run(JSON.stringify(state), fresh.id);
  });
  return { task: taskView(p, t), result, feedback };
});

route('POST', '/api/tasks/(\\d+)/keep', (req, res, body, m) => {
  const p = requirePlayer(req); const t = taskParam(m);
  assertNotFrozen(p);
  const pr = progressOf(p.id, t.id);
  if (!pr || pr.status !== 'decide') throw new HttpError(409, 'Сейчас нечего закрывать');
  upsertProgress(p.id, t.id, { status: 'closed', closed: 1, completed_at: now() });
  return { task: taskView(p, t) };
});

function sanitizeCreative(task, data, mediaIds, player) {
  const def = CREATIVE[task.id];
  const clean = {};
  for (const f of def.fields) {
    const v = String(data?.[f.id] ?? '').replace(/\r/g, '').trim().slice(0, f.max);
    clean[f.id] = f.multiline ? v : v.replace(/\s+/g, ' ');
  }
  const ids = Array.isArray(mediaIds) ? mediaIds.map(String).slice(0, def.media ? def.media.max : 0) : [];
  for (const id of ids) {
    const u = q('SELECT * FROM uploads WHERE id = ? AND player_id = ?').get(id, player.id);
    if (!u || !def.media || !def.media.kinds.includes(u.kind)) throw new HttpError(400, 'Недопустимый файл');
  }
  return { clean, ids };
}
route('POST', '/api/tasks/(\\d+)/draft', (req, res, body, m) => {
  const p = requirePlayer(req); const t = taskParam(m);
  if (t.type !== 'creative') throw new HttpError(400, 'Черновики только у творческих заданий');
  const view = taskView(p, t);
  if (!view.creative.canEdit) throw new HttpError(409, 'Ответ сейчас нельзя редактировать');
  rateLimit('draft:' + p.id, 120, 60_000);
  const { clean, ids } = sanitizeCreative(t, body.data, body.media, p);
  q(`INSERT INTO drafts (player_id, task_id, data, media, updated_at) VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(player_id, task_id) DO UPDATE SET data = excluded.data, media = excluded.media, updated_at = excluded.updated_at`).run(p.id, t.id, JSON.stringify(clean), JSON.stringify(ids), now());
  return { ok: true };
});
route('POST', '/api/tasks/(\\d+)/submit', (req, res, body, m) => {
  const p = requirePlayer(req); const t = taskParam(m);
  if (t.type !== 'creative') throw new HttpError(400, 'Это задание проверяется автоматически');
  assertTaskOpen(p); assertNotFrozen(p);
  if (!canSubmit(p)) throw new HttpError(423, 'Приём ответов закрыт');
  rateLimit('submit:' + p.id, 30, 60_000);
  const def = CREATIVE[t.id];
  const { clean, ids } = sanitizeCreative(t, body.data, body.media, p);
  for (const f of def.fields) if (!f.optional && !clean[f.id]) throw new HttpError(400, `Заполните поле «${f.label}»`);
  if (def.mediaOrNote && !ids.length && (clean[def.mediaOrNote] || '').length < 10) throw new HttpError(400, 'Загрузите файл или опишите словами (не меньше 10 символов)');
  tx(() => {
    const pr = progressOf(p.id, t.id), sub = latestSub(p.id, t.id);
    if (pr && pr.closed) throw new HttpError(409, 'Задание уже закрыто');
    if (sub && sub.status === 'pending') throw new HttpError(409, 'Ответ уже на проверке');
    if (sub && sub.status === 'returned' && sub.revision >= 1) throw new HttpError(409, 'Исправление уже использовано');
    const revision = sub ? sub.revision + 1 : 0;
    q('INSERT INTO submissions (player_id, task_id, revision, data, media, created_at) VALUES (?, ?, ?, ?, ?, ?)').run(p.id, t.id, revision, JSON.stringify(clean), JSON.stringify(ids), now());
    q('DELETE FROM drafts WHERE player_id = ? AND task_id = ?').run(p.id, t.id);
    upsertProgress(p.id, t.id, { status: 'pending' });
  });
  return { task: taskView(p, t) };
});

route('POST', '/api/uploads', async (req, res, body, m, url) => {
  const p = requirePlayer(req);
  rateLimit('upload:' + p.id, 20, 10 * 60_000);
  if (q('SELECT COUNT(*) n FROM uploads WHERE player_id = ?').get(p.id).n >= MAX_UPLOADS_PER_PLAYER) throw new HttpError(429, 'Слишком много загруженных файлов');
  if (!canSubmit(p)) throw new HttpError(423, 'Приём ответов закрыт');
  const want = url.searchParams.get('kind') === 'video' ? 'video' : 'image';
  const buf = await readRaw(req, want === 'video' ? VIDEO_LIMIT : IMAGE_LIMIT);
  const media = detectMedia(buf);
  if (!media || (want === 'image' && media.kind !== 'image') || buf.length < 100) throw new HttpError(400, want === 'image' ? 'Допустимы фото JPEG, PNG или WebP' : 'Допустимо видео MP4, MOV или WebM');
  const id = crypto.randomBytes(16).toString('hex');
  fs.writeFileSync(path.join(UPLOAD_DIR, id), buf, { mode: 0o600 });
  q('INSERT INTO uploads (id, player_id, kind, mime, size, created_at) VALUES (?, ?, ?, ?, ?, ?)').run(id, p.id, media.kind, media.mime, buf.length, now());
  return { id, kind: media.kind, mime: media.mime, url: `/api/uploads/${id}` };
}, { raw: true });
route('GET', '/api/uploads/([0-9a-f]{32})', (req, res, body, m) => {
  const u = q('SELECT * FROM uploads WHERE id = ?').get(m[1]);
  if (!u) throw new HttpError(404, 'Нет файла');
  const pl = currentPlayer(req);
  if (!isAdmin(req) && !(pl && pl.id === u.player_id)) throw new HttpError(403, 'Нет доступа');
  serveFile(req, res, path.join(UPLOAD_DIR, u.id), u.mime);
});
route('GET', '/logo', (req, res) => {
  const logo = getSetting('logo');
  if (!logo) throw new HttpError(404, 'Логотип не загружен');
  send(res, 200, fs.readFileSync(path.join(DATA_DIR, 'logo')), { 'Content-Type': logo.mime, 'Cache-Control': 'public, max-age=300' });
});

// ---------- Администратор ----------
route('GET', '/api/admin/status', () => ({ configured: !!ADMIN_EMAIL, hasPassword: !!getSetting('admin_pw') }));
route('POST', '/api/admin/setup', (req, res, body) => {
  const fail = failGuard('adm-setup:' + clientIp(req), 6, 15 * 60_000);
  const setup = getSetting('admin_setup');
  if (!ADMIN_EMAIL || !setup || getSetting('admin_pw')) throw new HttpError(409, 'Первичная настройка уже выполнена');
  const okEmail = safeEq(String(body.email || '').trim().toLowerCase(), ADMIN_EMAIL);
  const okTok = safeEq(sha(String(body.token || '').trim()), setup.hash);
  const pw = String(body.password || '');
  if (!okEmail || !okTok) { fail(); throw new HttpError(401, 'Неверный адрес или код настройки'); }
  if (pw.length < 12) throw new HttpError(400, 'Пароль: не короче 12 символов');
  setSetting('admin_pw', hashPassword(pw)); setSetting('admin_setup', null);
  try { fs.unlinkSync(path.join(DATA_DIR, 'admin-setup.txt')); } catch {}
  audit(ADMIN_EMAIL, 'setup', 'Задан пароль администратора');
  return { ok: true };
});
route('POST', '/api/admin/login', (req, res, body) => {
  const fail = failGuard('adm:' + clientIp(req), 8, 15 * 60_000);
  const failAll = failGuard('adm-all', 60, 15 * 60_000);
  const stored = getSetting('admin_pw');
  const okPw = verifyPassword(String(body.password || ''), stored || 'x$00$00');
  const okEmail = !!ADMIN_EMAIL && safeEq(String(body.email || '').trim().toLowerCase(), ADMIN_EMAIL);
  if (!stored || !okPw || !okEmail) { fail(); failAll(); throw new HttpError(401, 'Неверный адрес или пароль'); }
  const tok = newToken();
  q('INSERT INTO admin_sessions (token_hash, expires_at) VALUES (?, ?)').run(sha(tok), now() + ADMIN_SESSION_HOURS * 36e5);
  q('DELETE FROM admin_sessions WHERE expires_at < ?').run(now());
  setCookie(res, 'mgp_a', tok, ADMIN_SESSION_HOURS * 3600, 'Strict');
  audit(ADMIN_EMAIL, 'login', clientIp(req));
  return { ok: true };
});
route('POST', '/api/admin/logout', (req, res) => { const tok = parseCookies(req).mgp_a; if (tok) q('DELETE FROM admin_sessions WHERE token_hash = ?').run(sha(tok)); setCookie(res, 'mgp_a', '', 0, 'Strict'); return { ok: true }; });
route('GET', '/api/admin/me', (req) => ({ admin: isAdmin(req), email: isAdmin(req) ? ADMIN_EMAIL : null }));

function scopedPlayer(req, id) {
  const p = q('SELECT * FROM players WHERE id = ?').get(Number(id));
  if (!p) throw new HttpError(404, 'Участник не найден');
  if (p.is_test !== scopeOf(req)) throw new HttpError(409, p.is_test ? 'Это тестовый участник: переключитесь в тестовый режим панели' : 'Это настоящий участник: тестовый режим панели не может менять реальные данные');
  return p;
}
const gameRunningReal = () => gameStatus().phase === 'running';

route('GET', '/api/admin/dashboard', (req) => {
  requireAdmin(req);
  const t = scopeOf(req);
  const rows = computeRows(t === 1);
  const g = gameStatus();
  const closedTasks = q('SELECT COUNT(*) n FROM progress p JOIN players pl ON pl.id = p.player_id WHERE p.closed = 1 AND pl.is_test = ?').get(t).n;
  return {
    game: g, scope: t, total: rows.length, active: rows.filter((r) => now() - r.lastSeen < 15 * 60_000).length, closedTasks, pending: pendingCount(t === 1),
    bingos: rows.reduce((a, r) => a + r.bingos, 0), average: rows.length ? Math.round((rows.reduce((a, r) => a + r.total, 0) / rows.length) * 10) / 10 : 0,
    leaders: rows.slice(0, 5).map((r) => ({ rank: r.rank, name: r.name, total: r.total, bingos: r.bingos })), final: !!getFinal(t === 1),
    codes: q('SELECT COUNT(*) n FROM codes WHERE is_test = ?').get(t).n, codesUsed: q('SELECT COUNT(*) n FROM players WHERE is_test = ?').get(t).n,
  };
});
route('GET', '/api/admin/players', (req) => {
  requireAdmin(req);
  return computeRows(scopeOf(req) === 1).map((r) => ({ id: r.id, rank: r.rank, name: r.name, format: r.format, closed: r.closed, auto: r.auto, creative: r.creative, bonus: r.bonus, bingos: r.bingos, total: r.total, attempts: r.attempts, tied: r.tied, lastSeen: r.lastSeen }));
});
route('GET', '/api/admin/players/(\\d+)', (req, res, body, m) => {
  requireAdmin(req);
  const p = scopedPlayer(req, m[1]);
  const { pts, adj } = loadPoints(p.id);
  const sc = scoreFromPoints(pts);
  const tasks = TASKS.map((t) => {
    const pr = progressOf(p.id, t.id);
    return {
      id: t.id, emoji: t.emoji, title: t.title, type: t.type, status: pr ? pr.status : 'new', points: pts.get(t.id), adjusted: adj.has(t.id) ? adj.get(t.id) : null,
      attemptsUsed: pr ? pr.attempts_used : 0, hint: !!(pr && pr.hint_used),
      attempts: q('SELECT n, started_at, finished_at, raw, final FROM attempts WHERE player_id = ? AND task_id = ? ORDER BY n').all(p.id, t.id),
      submissions: q('SELECT id, revision, status, points, comment, created_at FROM submissions WHERE player_id = ? AND task_id = ? ORDER BY id').all(p.id, t.id),
    };
  });
  const log = q('SELECT * FROM point_log WHERE player_id = ? ORDER BY id DESC LIMIT 100').all(p.id);
  return { player: { id: p.id, name: p.name, format: p.work_format, createdAt: p.created_at, lastSeen: p.last_seen, isTest: p.is_test === 1 }, score: sc, tasks, log };
});
route('POST', '/api/admin/players/(\\d+)/delete', (req, res, body, m) => {
  requireAdmin(req); const p = scopedPlayer(req, m[1]);
  deletePlayers('p.id = ?', p.id); audit(adminActor(), 'delete-player', `${p.name} (#${p.id})`);
  return { ok: true };
});

route('GET', '/api/admin/submissions', (req, res, body, m, url) => {
  requireAdmin(req);
  const status = url.searchParams.get('status') || 'pending';
  const base = 'SELECT s.*, pl.name, pl.work_format FROM submissions s JOIN players pl ON pl.id = s.player_id WHERE pl.is_test = ?';
  const rows = status === 'all' ? q(`${base} ORDER BY s.created_at DESC LIMIT 400`).all(scopeOf(req)) : q(`${base} AND s.status = ? ORDER BY s.created_at ${status === 'pending' ? 'ASC' : 'DESC'} LIMIT 400`).all(scopeOf(req), status);
  return rows.map((s) => {
    const t = TASK_BY_ID.get(s.task_id), def = CREATIVE[s.task_id];
    return { id: s.id, playerId: s.player_id, name: s.name, format: s.work_format, taskId: s.task_id, emoji: t.emoji, title: t.title, revision: s.revision, status: s.status,
      fields: def.fields.map((f) => ({ label: f.label, value: JSON.parse(s.data)[f.id] || '' })), media: mediaList(s.media), criteria: def.criteria, ticked: JSON.parse(s.criteria),
      points: s.points, comment: s.comment, createdAt: s.created_at, reviewedAt: s.reviewed_at };
  });
});
route('POST', '/api/admin/submissions/(\\d+)/review', (req, res, body, m) => {
  requireAdmin(req);
  const decision = String(body.decision);
  if (!['approve', 'return', 'reject'].includes(decision)) throw new HttpError(400, 'Неизвестное решение');
  const comment = String(body.comment || '').trim().slice(0, 500);
  return tx(() => {
    const s = q('SELECT * FROM submissions WHERE id = ?').get(Number(m[1]));
    if (!s) throw new HttpError(404, 'Работа не найдена');
    const p = scopedPlayer(req, s.player_id);
    if (getFinal(p.is_test === 1)) throw new HttpError(423, 'Итоги подведены. Снимите фиксацию, чтобы менять оценки.');
    if (s.status !== 'pending') throw new HttpError(409, 'Эта работа уже проверена');
    if (decision === 'return' && s.revision >= 1) throw new HttpError(409, 'Исправление уже использовано: подтвердите или отклоните работу');
    const def = CREATIVE[s.task_id];
    const ticked = (Array.isArray(body.criteria) ? body.criteria : []).filter((id) => def.criteria.some((c) => c.id === id));
    const points = decision === 'approve' ? def.criteria.filter((c) => ticked.includes(c.id)).reduce((a, c) => a + c.pts, 0) : null;
    q('UPDATE submissions SET status = ?, criteria = ?, points = ?, comment = ?, reviewed_at = ? WHERE id = ?')
      .run({ approve: 'approved', return: 'returned', reject: 'rejected' }[decision], JSON.stringify(ticked), points, comment, now(), s.id);
    if (decision === 'approve') { upsertProgress(s.player_id, s.task_id, { status: 'approved', best: points, closed: 1, completed_at: now() }); logPoints(s.player_id, s.task_id, 'creative', points, `Подтверждено: ${points} из 10${comment ? ` («${comment}»)` : ''}`, adminActor()); }
    else if (decision === 'reject') { upsertProgress(s.player_id, s.task_id, { status: 'rejected', best: 0, closed: 1, completed_at: now() }); logPoints(s.player_id, s.task_id, 'creative', 0, `Отклонено${comment ? ` («${comment}»)` : ''}`, adminActor()); }
    else upsertProgress(s.player_id, s.task_id, { status: 'returned' });
    audit(adminActor(), 'review', { submission: s.id, decision, points });
    return { ok: true, points };
  });
});
route('POST', '/api/admin/adjust', (req, res, body) => {
  requireAdmin(req);
  const p = scopedPlayer(req, body.playerId); const t = TASK_BY_ID.get(Number(body.taskId));
  if (!t) throw new HttpError(404, 'Задание не найдено');
  if (getFinal(p.is_test === 1)) throw new HttpError(423, 'Итоги подведены. Снимите фиксацию, чтобы менять оценки.');
  const reason = String(body.reason || '').trim().slice(0, 300);
  if (reason.length < 3) throw new HttpError(400, 'Укажите причину корректировки');
  if (body.points === null) {
    q('DELETE FROM adjustments WHERE player_id = ? AND task_id = ?').run(p.id, t.id);
    logPoints(p.id, t.id, 'adjust', progressOf(p.id, t.id)?.best ?? null, `Корректировка снята: ${reason}`, adminActor());
  } else {
    const pts = Number(body.points);
    if (!Number.isInteger(pts) || pts < 0 || pts > 10) throw new HttpError(400, 'Баллы: целое число от 0 до 10');
    q(`INSERT INTO adjustments (player_id, task_id, points, reason, actor, at) VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT(player_id, task_id) DO UPDATE SET points = excluded.points, reason = excluded.reason, actor = excluded.actor, at = excluded.at`).run(p.id, t.id, pts, reason, adminActor(), now());
    logPoints(p.id, t.id, 'adjust', pts, `Корректировка оценки: ${reason}`, adminActor());
  }
  audit(adminActor(), 'adjust', { player: p.id, task: t.id, points: body.points, reason });
  return { ok: true };
});

route('GET', '/api/admin/rating', (req) => {
  requireAdmin(req);
  const t = scopeOf(req) === 1, fin = getFinal(t), rows = computeRows(t);
  return { rows: rows.map((r) => ({ id: r.id, rank: r.rank, name: r.name, format: r.format, pts: r.pts, adjusted: r.adjusted, auto: r.auto, creative: r.creative, bonus: r.bonus, bingos: r.bingos, tens: r.tens, attempts: r.attempts, total: r.total, tied: r.tied, draw: r.draw })),
    final: fin ? { at: fin.at, top3: fin.top3 } : null, pending: pendingCount(t), tasks: TASKS.map((x) => ({ id: x.id, emoji: x.emoji, title: x.title })) };
});
function exportCsv(req, res) {
  requireAdmin(req);
  const isTest = scopeOf(req) === 1;
  const rows = computeRows(isTest);
  const head = ['Место', 'Имя', 'Офис/удалённо', ...TASKS.map((t) => `№${t.id} ${t.title}`), 'Баллы за автозадания', 'Баллы за творческие', 'Бонус БИНГО', 'Линий БИНГО', 'Итого', 'Заданий на 10', 'Использовано попыток'];
  sendCsv(res, `millor-pharma-results${isTest ? '-test' : ''}.csv`, [head, ...rows.map((r) => [r.rank, r.name, r.format === 'office' ? 'Офис' : 'Удалённо', ...TASKS.map((t) => r.pts[t.id] ?? ''), r.auto, r.creative, r.bonus, r.bingos, r.total, r.tens, r.attempts])]);
}
route('GET', '/api/admin/export.csv', (req, res) => exportCsv(req, res));

route('POST', '/api/admin/tiebreak', (req) => {
  requireAdmin(req);
  const rows = computeRows(scopeOf(req) === 1);
  const draw = getSetting('tie_draw'), groups = new Map();
  for (const r of rows) if (r.tied && r.draw == null) { (groups.get(r.rank) || groups.set(r.rank, []).get(r.rank)).push(r); }
  if (!groups.size) throw new HttpError(409, 'Нет участников с полным равенством');
  const notes = [];
  for (const [rank, g] of groups) { const sh = shuffleIds(g.map((r) => r.id)); sh.forEach((id, i) => { draw[id] = i + 1; }); notes.push(`место ${rank}: ${sh.map((id) => g.find((r) => r.id === id).name).join(' → ')}`); }
  setSetting('tie_draw', draw); audit(adminActor(), 'tiebreak', notes.join('; '));
  return { ok: true, notes };
});
function shuffleIds(a) { const r = [...a]; for (let i = r.length - 1; i > 0; i--) { const j = crypto.randomInt(i + 1); [r[i], r[j]] = [r[j], r[i]]; } return r; }

route('POST', '/api/admin/finalize', (req, res, body) => {
  requireAdmin(req);
  const t = scopeOf(req) === 1;
  const pending = pendingCount(t);
  if (pending && !body.force) throw new HttpError(409, `На проверке ещё ${pending} работ. Проверьте их или подтвердите подведение итогов без них.`);
  if (gameStatus().phase !== 'ended' && !t && !body.force) throw new HttpError(409, 'Игра ещё не завершена. Завершите игру или подтвердите досрочное подведение итогов.');
  if (getFinal(t)) throw new HttpError(409, 'Итоги уже подведены');
  let rows = computeRows(t);
  const draw = getSetting('tie_draw'), notes = [];
  const top = rows.filter((r) => r.rank <= 3);
  const groups = new Map();
  for (const r of top) if (r.tied && r.draw == null) (groups.get(r.rank) || groups.set(r.rank, []).get(r.rank)).push(r);
  for (const [rank, g] of groups) { const sh = shuffleIds(g.map((r) => r.id)); sh.forEach((id, i) => { draw[id] = i + 1; }); notes.push(`место ${rank}: ${sh.map((id) => g.find((r) => r.id === id).name).join(' → ')}`); }
  if (groups.size) { setSetting('tie_draw', draw); rows = computeRows(t); }
  const snap = { at: now(), rows, top3: rows.slice(0, 3).map((r) => ({ rank: r.rank, name: r.name, total: r.total, bingos: r.bingos })), draws: notes };
  setSetting(t ? 'final_1' : 'final_0', snap);
  audit(adminActor(), 'finalize', { scope: t ? 'test' : 'real', top3: snap.top3, draws: notes, pending });
  return { ok: true, top3: snap.top3, draws: notes };
});
route('POST', '/api/admin/unfreeze', (req) => { requireAdmin(req); const t = scopeOf(req) === 1; setSetting(t ? 'final_1' : 'final_0', null); audit(adminActor(), 'unfreeze', t ? 'test' : 'real'); return { ok: true }; });

route('GET', '/api/admin/settings', (req) => {
  requireAdmin(req);
  return { game: gameStatus(), timers: timers(), timerLabels: G.TIMER_LABELS, timerDefaults: G.TIMER_DEFAULTS, logo: getSetting('logo') ? '/logo' : null, email: ADMIN_EMAIL };
});
route('POST', '/api/admin/game', (req, res, body) => {
  requireAdmin(req);
  const act = String(body.action);
  const g = gameStatus();
  if (act === 'start') setSetting('game_state', 'running');
  else if (act === 'pause') { if (g.phase !== 'running') throw new HttpError(409, 'Игра сейчас не идёт'); setSetting('game_state', 'paused'); }
  else if (act === 'resume') { if (g.phase !== 'paused') throw new HttpError(409, 'Игра не на паузе'); setSetting('game_state', 'running'); }
  else if (act === 'end') { if (!body.confirm) throw new HttpError(409, 'Нужно подтверждение'); setSetting('game_state', 'ended'); }
  else if (act === 'reopen') { setSetting('game_state', 'running'); }
  else if (act === 'schedule') {
    const s = Date.parse(body.start), e = Date.parse(body.end);
    if (!Number.isFinite(s) || !Number.isFinite(e) || e <= s) throw new HttpError(400, 'Проверьте время начала и окончания');
    if (g.phase === 'running' && e < now()) throw new HttpError(400, 'Время окончания не может быть в прошлом');
    setSetting('game_start', body.start); setSetting('game_end', body.end); setSetting('auto_start', body.autoStart !== false);
  } else throw new HttpError(400, 'Неизвестное действие');
  audit(adminActor(), 'game', { act, start: body.start, end: body.end });
  return { ok: true, game: gameStatus() };
});
route('POST', '/api/admin/timers', (req, res, body) => {
  requireAdmin(req);
  const next = { ...getSetting('timers') }, changes = [];
  for (const [id, v] of Object.entries(body.timers || {})) {
    if (!(id in G.TIMER_DEFAULTS)) continue;
    const sec = Math.round(Number(v));
    if (!Number.isFinite(sec) || sec < 3 || sec > 900) throw new HttpError(400, `№ ${id}: допустимо от 3 до 900 секунд`);
    if (timers()[id] !== sec) { changes.push(`№${id}: ${timers()[id]} → ${sec} с`); next[id] = sec; }
  }
  if (!changes.length) return { ok: true, changed: 0 };
  const reason = String(body.reason || '').trim();
  if (gameStatus().phase !== 'before' && (!body.confirm || reason.length < 3)) throw new HttpError(409, 'Игра уже идёт или завершена: правила меняются только с подтверждением и причиной');
  setSetting('timers', next); audit(adminActor(), 'timers', { changes, reason });
  return { ok: true, changed: changes.length };
});
route('GET', '/api/admin/log', (req, res, body, m, url) => {
  requireAdmin(req);
  const kind = url.searchParams.get('kind') || 'points';
  if (kind === 'audit') return q('SELECT * FROM audit_log ORDER BY id DESC LIMIT 200').all().map((r) => ({ ...r, atMsk: fmtMsk(r.at) }));
  return q('SELECT l.*, p.name FROM point_log l JOIN players p ON p.id = l.player_id WHERE p.is_test = ? ORDER BY l.id DESC LIMIT 300').all(scopeOf(req))
    .map((r) => ({ ...r, task: r.task_id ? `№${r.task_id} ${TASK_BY_ID.get(r.task_id).title}` : '', atMsk: fmtMsk(r.at) }));
});

route('GET', '/api/admin/codes', (req) => {
  requireAdmin(req);
  return q('SELECT c.id, c.code_enc, c.revoked, c.note, c.created_at, p.name, p.id AS player_id FROM codes c LEFT JOIN players p ON p.code_id = c.id WHERE c.is_test = ? ORDER BY c.id').all(scopeOf(req))
    .map((c) => ({ id: c.id, code: decCode(c.code_enc), revoked: !!c.revoked, note: c.note, name: c.name, playerId: c.player_id }));
});
route('POST', '/api/admin/codes/generate', (req, res, body) => {
  requireAdmin(req);
  const count = Math.min(100, Math.max(1, Math.floor(Number(body.count) || 0)));
  const isTest = scopeOf(req);
  const created = [];
  tx(() => { while (created.length < count) { const c = generateCode(isTest); try { q('INSERT INTO codes (code_hash, code_enc, is_test, note, created_at) VALUES (?, ?, ?, ?, ?)').run(codeHash(c), encCode(c), isTest, String(body.note || '').slice(0, 100), now()); created.push(c); } catch {} } });
  audit(adminActor(), 'codes', `создано ${count}${isTest ? ' (тест)' : ''}`);
  return { created };
});
route('POST', '/api/admin/codes/(\\d+)/(revoke|restore|delete)', (req, res, body, m) => {
  requireAdmin(req);
  const c = q('SELECT * FROM codes WHERE id = ?').get(Number(m[1]));
  if (!c) throw new HttpError(404, 'Код не найден');
  if (c.is_test !== scopeOf(req)) throw new HttpError(409, 'Код относится к другому режиму панели');
  if (m[2] === 'delete') { deletePlayers('p.code_id = ?', c.id); q('DELETE FROM codes WHERE id = ?').run(c.id); }
  else { q('UPDATE codes SET revoked = ? WHERE id = ?').run(m[2] === 'revoke' ? 1 : 0, c.id); if (m[2] === 'revoke') q('DELETE FROM sessions WHERE player_id IN (SELECT id FROM players WHERE code_id = ?)').run(c.id); }
  audit(adminActor(), `code-${m[2]}`, `#${c.id}`);
  return { ok: true };
});
route('GET', '/api/admin/codes.csv', (req, res) => {
  requireAdmin(req);
  const rows = q('SELECT c.*, p.name FROM codes c LEFT JOIN players p ON p.code_id = c.id WHERE c.is_test = ? ORDER BY c.id').all(scopeOf(req));
  sendCsv(res, 'millor-pharma-codes.csv', [['Код', 'Пометка', 'Участник', 'Статус'], ...rows.map((r) => [decCode(r.code_enc), r.note, r.name || '', r.revoked ? 'отключён' : r.name ? 'используется' : 'свободен'])]);
});
route('POST', '/api/admin/logo', (req, res, body) => {
  requireAdmin(req);
  if (body.remove) { setSetting('logo', null); try { fs.unlinkSync(path.join(DATA_DIR, 'logo')); } catch {} return { ok: true }; }
  const m = /^data:(image\/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)$/.exec(String(body.image || ''));
  if (!m) throw new HttpError(400, 'Логотип: PNG, JPEG или WebP');
  const buf = Buffer.from(m[2], 'base64');
  if (buf.length > 1024 * 1024) throw new HttpError(413, 'Логотип больше 1 МБ');
  fs.writeFileSync(path.join(DATA_DIR, 'logo'), buf); setSetting('logo', { mime: m[1], updated: now() });
  return { ok: true };
}, {});
route('GET', '/api/admin/backup.json', (req, res) => {
  requireAdmin(req);
  const dump = {
    exportedAt: new Date().toISOString(), game: gameStatus(), timers: timers(),
    players: q('SELECT id, name, work_format, is_test, created_at FROM players').all(),
    progress: q('SELECT * FROM progress').all(), attempts: q('SELECT id, player_id, task_id, n, started_at, finished_at, raw, final, detail FROM attempts').all(),
    submissions: q('SELECT * FROM submissions').all(), adjustments: q('SELECT * FROM adjustments').all(), pointLog: q('SELECT * FROM point_log').all(), audit: q('SELECT * FROM audit_log').all(),
    finalStandings: { real: getSetting('final_0'), test: getSetting('final_1') },
  };
  send(res, 200, JSON.stringify(dump, null, 1), { 'Content-Type': 'application/json; charset=utf-8', 'Content-Disposition': `attachment; filename="millor-pharma-backup-${new Date().toISOString().slice(0, 10)}.json"`, 'Cache-Control': 'no-store' });
});
route('POST', '/api/admin/demo/create', (req, res, body) => {
  requireAdmin(req);
  const n = Math.min(20, Math.max(1, Math.floor(Number(body.count) || 3))), created = [];
  while (created.length < n) { const c = generateCode(1); try { q('INSERT INTO codes (code_hash, code_enc, is_test, note, created_at) VALUES (?, ?, 1, ?, ?)').run(codeHash(c), encCode(c), 'Тест', now()); created.push(c); } catch {} }
  return { created };
});
route('POST', '/api/admin/demo/clear', (req) => {
  requireAdmin(req);
  tx(() => { deletePlayers('p.is_test = 1'); q('DELETE FROM codes WHERE is_test = 1').run(); setSetting('final_1', null); });
  audit(adminActor(), 'clear-test', ''); return { ok: true };
});
route('POST', '/api/admin/wipe', (req, res, body) => {
  requireAdmin(req);
  if (body.confirm !== 'УДАЛИТЬ') throw new HttpError(400, 'Введите слово УДАЛИТЬ');
  tx(() => { q('DELETE FROM players').run(); q('DELETE FROM uploads').run(); if (body.codes) q('DELETE FROM codes').run(); setSetting('final_0', null); setSetting('final_1', null); setSetting('tie_draw', {}); });
  for (const f of fs.readdirSync(UPLOAD_DIR)) { try { fs.unlinkSync(path.join(UPLOAD_DIR, f)); } catch {} }
  audit(adminActor(), 'wipe', body.codes ? 'вместе с кодами' : 'коды сохранены');
  return { ok: true };
});

// ---------- Статика и сервер ----------
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon' };
function serveStatic(req, res, pathname) {
  if (pathname === '/' || pathname === '') pathname = '/index.html';
  if (pathname === '/admin' || pathname === '/admin/') pathname = '/admin.html';
  const file = path.normalize(path.join(PUBLIC_DIR, pathname));
  if (!file.startsWith(PUBLIC_DIR + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return send(res, 404, 'Не найдено', { 'Content-Type': 'text/plain; charset=utf-8' });
  const ext = path.extname(file);
  send(res, 200, fs.readFileSync(file), { 'Content-Type': MIME[ext] || 'application/octet-stream', 'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=120' });
}
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  try {
    if (!url.pathname.startsWith('/api/') && url.pathname !== '/logo') return serveStatic(req, res, url.pathname);
    const r = routes.find((x) => x.method === req.method && x.re.test(url.pathname));
    if (!r) throw new HttpError(404, 'Неизвестный адрес');
    checkSameOrigin(req, r.raw);
    const body = req.method === 'POST' && !r.raw ? await readJson(req, url.pathname === '/api/admin/logo' ? 2 * 1024 * 1024 : 256 * 1024) : {};
    const result = await r.handler(req, res, body, url.pathname.match(r.re), url);
    if (!res.headersSent && !res.writableEnded) json(res, 200, result === undefined ? { ok: true } : result);
  } catch (e) {
    if (!(e instanceof HttpError)) console.error(e);
    if (!res.headersSent) json(res, e.status || 500, { error: e instanceof HttpError ? e.message : 'Внутренняя ошибка сервера' });
  }
});
server.requestTimeout = 120_000;
setInterval(() => { q('DELETE FROM sessions WHERE expires_at < ?').run(now()); q('DELETE FROM admin_sessions WHERE expires_at < ?').run(now()); }, 3600_000).unref();

if (require.main === module) server.listen(PORT, HOST, () => console.log(`Миллор Фарма: Секретная лаборатория — http://${HOST}:${PORT}  (админка: /admin)`));
module.exports = { server, db, computeRows, scoreFromPoints, GRID_CELLS };
