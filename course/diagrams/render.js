// Рендер HTML-схем в PNG (1200×675, масштаб 2).
const { chromium } = require(process.env.PW_PATH);
const fs = require('fs'), path = require('path');
(async () => {
  const dir = process.argv[2];
  const files = fs.readdirSync(dir).filter(f => f.endsWith('.html'));
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 675 }, deviceScaleFactor: 2 });
  for (const f of files) {
    await page.goto('file://' + path.join(dir, f));
    await page.evaluate(() => document.fonts.ready);
    await page.locator('#card').screenshot({ path: path.join(dir, f.replace('.html', '.png')) });
  }
  await browser.close();
  console.log('rendered', files.length);
})();
