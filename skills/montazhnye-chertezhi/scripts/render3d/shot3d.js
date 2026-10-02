// Рендеры 3D-модели через viewer.html (three.js) в headless Chromium.
// Запуск: node shot3d.js <папка с viewer.html и .gltf.json> <папка для png> [iso,top,front:sec] [доп. параметры вида, напр. "t=0,0,900&d=2400"]
// Внутри поднимается локальный сервер с UTF-8 (без charset кириллица в панели viewer превращается в «Ã…»).
// three.js берётся из node_modules рядом (npm i three@0.160.0), т.к. CDN в песочнице может быть недоступен.
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const [src, out, viewsArg, extra] = process.argv.slice(2);
if (!src || !out) { console.error('usage: node shot3d.js <src dir> <out dir> [views] [params]'); process.exit(2); }
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8', '.glb': 'model/gltf-binary' };
const nm = path.join(__dirname, 'node_modules');
const srv = http.createServer((q, r) => {
  let u = decodeURIComponent(q.url.split('?')[0]);
  let f = u.startsWith('/node_modules/') ? path.join(nm, u.slice(14)) : path.join(src, u === '/' ? 'index.html' : u);
  if (u === '/index.html' || u === '/') {           // viewer.html с three.js из локальных node_modules
    const h = fs.readFileSync(path.join(src, 'viewer.html'), 'utf8').replace(/https:\/\/unpkg\.com\/three@[\d.]+\//g, '/node_modules/three/');
    r.writeHead(200, { 'Content-Type': TYPES['.html'] }); return r.end(h);
  }
  fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); return r.end(); } r.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream' }); r.end(d); });
}).listen(0, '127.0.0.1', async () => {
  const port = srv.address().port;
  fs.mkdirSync(out, { recursive: true });
  const b = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/opt/pw-browsers/chromium',
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const p = await b.newPage({ viewport: { width: 1600, height: 1100 } });
  p.on('console', m => { if (m.type() === 'error') console.log('ERR', m.text()); });
  for (const v of (viewsArg || 'iso,top,front:sec').split(',')) {
    const [name, sec] = v.split(':');
    await p.goto(`http://127.0.0.1:${port}/index.html?view=${name}&${extra || ''}${sec ? '&sec=1' : ''}`);
    await p.waitForFunction(() => window.__ready, null, { timeout: 120000 }); await p.waitForTimeout(800);
    const f = path.join(out, `m_${name}${sec ? '_sec' : ''}.png`); await p.screenshot({ path: f }); console.log(f);
  }
  await b.close(); srv.close();
});
