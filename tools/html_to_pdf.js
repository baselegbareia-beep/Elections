// A self-contained HTML page -> a one-page PDF as tall as the page (headless Chrome through Playwright).
//   node tools/html_to_pdf.js IN.html OUT.pdf
// Used for the Arab-localities turnout report (pipeline/arab_report.py). Set PW_CHROME to a Chrome binary when
// Playwright's own browser is not installed.
const { chromium } = require('playwright');

(async () => {
  const [src, dst] = process.argv.slice(2);
  if (!src || !dst) { console.error('usage: node tools/html_to_pdf.js IN.html OUT.pdf'); process.exit(2); }
  const browser = await chromium.launch(process.env.PW_CHROME ? { executablePath: process.env.PW_CHROME } : {});
  try {
    const page = await browser.newPage({ viewport: { width: 794, height: 1123 } });
    await page.goto('file://' + require('path').resolve(src), { waitUntil: 'load' });
    const h = await page.evaluate(() => Math.ceil(document.documentElement.scrollHeight));
    await page.pdf({ path: dst, width: '794px', height: `${h + 2}px`, printBackground: true, pageRanges: '1',
                     margin: { top: '0', right: '0', bottom: '0', left: '0' } });
    console.log(JSON.stringify({ pdf: dst, height: h }));
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(String(e)); process.exit(1); });
