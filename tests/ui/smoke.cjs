// Screen test: clicks through Scan, untick, Save in light and dark mode, at desktop and phone width.
// Start tests/ui/fake_app.py first, then: node tests/ui/smoke.cjs
// Screenshots go to tests/ui/screens/ (not committed).
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');

const work = path.join(os.tmpdir(), 'scene-filter-ui');
const shots = path.join(__dirname, 'screens');
fs.mkdirSync(shots, { recursive: true });

async function waitFor(file) {
  for (let i = 0; i < 120; i++) {
    if (fs.existsSync(file) && fs.readFileSync(file, 'utf8').trim()) return fs.readFileSync(file, 'utf8').trim();
    await new Promise(r => setTimeout(r, 500));
  }
  throw new Error(`timed out waiting for ${file}`);
}

async function run(browser, url, video, scheme, width) {
  const page = await browser.newPage({ colorScheme: scheme, viewport: { width, height: 1000 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(url);
  await page.getByRole('button', { name: 'Scan movie' }).waitFor();
  await page.getByPlaceholder(/Users\/you/).fill(video);
  await page.getByRole('button', { name: 'Scan movie' }).click();
  await page.locator('.sf-count').filter({ hasText: '2' }).waitFor({ timeout: 60000 });
  if (!(await page.getByText('Double-checked with the accurate detector').isVisible())) throw new Error('badge missing');
  await page.getByText(/Exposed buttocks/).click();          // untick the second scene
  await page.getByText('Black screen', { exact: true }).click();
  await page.getByRole('button', { name: 'Save filtered movie' }).click();
  await page.getByText(/Done\. 1 scene\(s\) filtered/).waitFor({ timeout: 60000 });
  await page.screenshot({ path: path.join(shots, `${scheme}-${width}.png`), fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  await page.close();
  if (overflow) throw new Error(`page scrolls sideways at ${width}px`);
  if (errors.length) throw new Error(`page errors: ${errors.join('; ')}`);
}

(async () => {
  const url = await waitFor(path.join(work, 'url'));
  const video = await waitFor(path.join(work, 'video'));
  const browser = await chromium.launch();
  let failed = false;
  for (const scheme of ['light', 'dark']) {
    try {
      for (const width of [1280, 400]) await run(browser, url, video, scheme, width);
      console.log(`PASS ${scheme}`);
    } catch (e) {
      failed = true;
      console.log(`FAIL ${scheme}: ${e.message}`);
    }
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
