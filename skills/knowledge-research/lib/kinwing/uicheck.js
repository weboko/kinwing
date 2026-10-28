const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
  const errs = []; p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); }); p.on('pageerror', e => errs.push(String(e)));
  const base = process.argv[2];
  for (const h of ['#/', '#/t/spaced-repetition-scheduling', '#/t/spaced-repetition-scheduling?tab=concepts', '#/t/spaced-repetition-scheduling?tab=conclusions',
                   '#/t/spaced-repetition-scheduling?tab=unknowns', '#/t/spaced-repetition-scheduling?tab=sources', '#/t/spaced-repetition-scheduling?tab=activity',
                   '#/c/stability', '#/c/retrievability', '#/s/src-the-fsrs-algorithm-f67d', '#/highlights', '#/questions', '#/search?q=stab']) {
    await p.goto(base + '/' + h); await p.waitForTimeout(500);
    const t = await p.evaluate(() => document.querySelector('#view').innerText.slice(0, 160).replace(/\n+/g, ' | '));
    console.log(h, '=>', t);
  }
  await p.goto(base + '/#/c/stability'); await p.waitForTimeout(400);
  console.log('marks on concept:', await p.locator('mark.hl').count());
  await p.goto(base + '/#/s/src-the-fsrs-algorithm-f67d'); await p.waitForTimeout(400);
  console.log('marks on source:', await p.locator('mark.hl').count());
  await p.screenshot({ path: 'shot-source.png', fullPage: true });
  console.log('errors:', JSON.stringify(errs));
  await b.close();
})();
