// Actual Streamlit browser captures; no generated/reconstructed UI images.
import { createRequire } from 'node:module';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_DIR
  ? path.join(process.env.PLAYWRIGHT_MODULE_DIR, 'playwright') : 'playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const phase = process.argv[2];
if (!['before', 'after'].includes(phase)) throw new Error('Usage: node capture.mjs before|after [base-url] [case-id]');
const base = process.argv[3] || `http://127.0.0.1:${phase === 'before' ? 8502 : 8503}`;
if (!['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) throw new Error('Capture target must be loopback');
const manifest = JSON.parse(await readFile(path.join(root, 'tests/visual/manifest.json'), 'utf8'));
const selection = process.argv[4]?.split(',');
const cases = manifest.cases.filter(item => !selection || selection.includes(item.id));
if (!cases.length) throw new Error('No capture cases selected');
const output = path.join(root, 'docs/changes/foodguide', phase);
await mkdir(path.join(output, 'full'), { recursive: true });
const browser = await chromium.launch({ headless: true });
const records = [];
try {
  for (const item of cases) {
    const context = await browser.newContext({ viewport: { width: 430, height: 932 },
      deviceScaleFactor: 1, locale: 'ko-KR', timezoneId: 'Asia/Seoul', reducedMotion: 'reduce' });
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      return ['localhost', '127.0.0.1', '[::1]', 'fonts.googleapis.com', 'fonts.gstatic.com'].includes(url.hostname)
        || ['data:', 'blob:'].includes(url.protocol) ? route.continue() : route.abort('blockedbyclient');
    });
    const page = await context.newPage();
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.goto(`${base}/?case=${encodeURIComponent(item.id)}`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.body.innerText.includes('모시고') || document.body.innerText.includes('Traceback'));
    await page.locator(`[data-capture-ready="${item.id}"]`).waitFor({ state: 'attached' });
    if (phase === 'after' && item.details) {
      await page.getByText('맛과 재료 자세히 보기', { exact: true }).click();
    }
    if (item.action) {
      await page.locator('input[type="file"]').setInputFiles(path.join(root, 'core/data/paris_menu.jpg'));
      await page.getByRole('button', { name: '이 사진으로 읽기', exact: true }).click();
      if (item.action === 'processing') {
        const status = page.getByText(phase === 'before' ? '메뉴판을 읽고 있어요' : '메뉴를 분석하고 있어요', { exact: true });
        await status.waitFor();
        if (phase === 'after') await page.getByText('가족 입맛을 비교하고 있어요', { exact: true }).waitFor();
        await status.scrollIntoViewIfNeeded();
      } else {
        await page.getByText(phase === 'before' ? '사진을 읽지 못했어요. 글씨가 잘 보이게 다시 찍어 주세요.' : '음식 분석을 완료하지 못했어요.', { exact: true }).first().waitFor();
        await page.locator('[data-testid="stMain"]').evaluate(el => { el.scrollTop = 0; });
      }
    }
    await page.waitForTimeout(500);
    const text = await page.locator('body').innerText();
    if (await page.locator('[data-testid="stException"]').count()
        || text.includes('이 화면을 여는 중에 문제가 생겼어요') || pageErrors.length) {
      throw new Error(`${item.id}: rendered error: ${JSON.stringify(pageErrors)} ${text.slice(0, 1200)}`);
    }
    await page.screenshot({ path: path.join(output, `${item.id}.png`), animations: 'disabled' });
    // Streamlit scrolls inside stMain. Extend only the viewport height to capture
    // that entire rendered page while preserving the same 430px mobile layout.
    const contentHeight = await page.locator('[data-testid="stMain"]').evaluate(el => el.scrollHeight);
    const fullHeight = Math.min(30000, Math.max(932, contentHeight));
    await page.setViewportSize({ width: 430, height: fullHeight });
    await page.waitForTimeout(150);
    await page.screenshot({ path: path.join(output, 'full', `${item.id}.png`), fullPage: true, animations: 'disabled' });
    records.push({ id: item.id, viewport: [430, 932], full_height: fullHeight, page_errors: pageErrors,
      controlled_provider_state: item.action || null });
    console.log(`${phase}: ${item.id} (${fullHeight}px)`);
    await context.close();
  }
} finally { await browser.close(); }
const metadata = { phase, source_commit: execFileSync('git', ['rev-parse', 'HEAD'],
  { cwd: process.env.MOSHIGO_CAPTURE_ROOT || root, encoding: 'utf8' }).trim(),
  source_dirty: Boolean(execFileSync('git', ['status', '--porcelain', '--', 'core', 'ui', 'streamlit_app.py', 'requirements.txt', 'scripts/visual_snapshot_app.py', 'tests/visual'],
    { cwd: process.env.MOSHIGO_CAPTURE_ROOT || root, encoding: 'utf8' }).trim()),
  playwright_version: require(process.env.PLAYWRIGHT_MODULE_DIR
    ? path.join(process.env.PLAYWRIGHT_MODULE_DIR, 'playwright/package.json') : 'playwright/package.json').version,
  fixture: phase === 'after' ? manifest.api_fixture : manifest.source_fixture, live_provider_evidence: false, records };
await writeFile(path.join(output, selection ? selection.length > 1 ? 'capture-extra.json' : `${selection[0]}.capture.json` : 'capture.json'), JSON.stringify(metadata, null, 2) + '\n');
