/**
 * Headless Three.js renderer using Puppeteer.
 *
 * Usage:
 *   node render.js <scene_data.json> <output.png>
 *
 * scene_data.json = { rooms, bounds, finishes, brand }
 */

const puppeteer = require('puppeteer');
const fs        = require('fs');
const path      = require('path');

async function render(sceneDataPath, outputPath) {
  const sceneData = JSON.parse(fs.readFileSync(sceneDataPath, 'utf8'));
  const htmlPath  = path.join(__dirname, 'scene.html');
  const fileUrl   = 'file://' + path.resolve(htmlPath);

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--use-gl=angle'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 1200, deviceScaleFactor: 1 });

  // Inject scene data before the page scripts run
  await page.evaluateOnNewDocument((data) => {
    window.__SCENE_DATA__ = data;
  }, sceneData);

  await page.goto(fileUrl, { waitUntil: 'networkidle0', timeout: 30000 });

  // Wait for Three.js render to complete
  await page.waitForFunction(() => window.__RENDER_DONE__ === true, { timeout: 15000 });

  await page.screenshot({ path: outputPath, type: 'png', fullPage: false });
  await browser.close();
  console.log(`Saved: ${outputPath}`);
}

const [,, sceneDataPath, outputPath] = process.argv;
if (!sceneDataPath || !outputPath) {
  console.error('Usage: node render.js <scene_data.json> <output.png>');
  process.exit(1);
}

render(sceneDataPath, outputPath).catch(e => { console.error(e); process.exit(1); });
