// Сборка SVG-листов в один PDF (формат страницы — по viewBox каждого листа) и PNG-превью для самопроверки.
// Запуск: node export_pdf.js <out.pdf> <лист1.svg> [лист2.svg …] [--png <папка>]
// Нужен playwright (npm i playwright или глобальный NODE_PATH). Путь к Chromium можно задать в CHROME_PATH.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');

(async () => {
  const args = process.argv.slice(2);
  const pngAt = args.indexOf('--png');
  const pngDir = pngAt >= 0 ? args.splice(pngAt, 2)[1] : null;
  const [out, ...files] = args;
  if (!out || !files.length) { console.error('usage: node export_pdf.js out.pdf a.svg [b.svg …] [--png dir]'); process.exit(2); }
  const opts = process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {};
  const b = await chromium.launch(opts);
  const p = await b.newPage();
  const sizes = new Map();
  let body = '';
  files.forEach((f, i) => {
    const s = fs.readFileSync(f, 'utf8');
    const [, w, h] = s.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/);
    const key = `p${w}x${h}`.replace(/\./g, '_');
    sizes.set(key, `@page ${key}{size:${w}mm ${h}mm;margin:0}`);
    body += `<div style="page:${key}">${s}</div>`;
  });
  await p.setContent(`<html><head><style>${[...sizes.values()].join('')}body{margin:0}svg{display:block}</style></head><body>${body}</body></html>`);
  await p.pdf({ path: out, preferCSSPageSize: true, printBackground: true });
  if (pngDir) {
    fs.mkdirSync(pngDir, { recursive: true });
    for (const f of files) {
      let s = fs.readFileSync(f, 'utf8');
      const [, w, h] = s.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/);
      const W = Math.round(w * 4), H = Math.round(h * 4);              // ~100 dpi
      s = s.replace(/width="[\d.]+mm" height="[\d.]+mm"/, `width="${W}" height="${H}"`);
      await p.setViewportSize({ width: W, height: H });
      await p.setContent(`<html><body style="margin:0">${s}</body></html>`);
      await p.screenshot({ path: path.join(pngDir, path.basename(f, '.svg') + '.png') });
    }
  }
  await b.close();
  console.log('PDF:', out, files.length, 'стр.');
})();
