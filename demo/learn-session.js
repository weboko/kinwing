// Drives the reader like a user would: read, highlight, annotate, answer, challenge, resume, export.
const { chromium } = require('playwright');
const base = process.argv[2] || 'http://localhost:8765';
const shots = process.argv[3] || '.';
const log = (...a) => console.log('•', ...a);

async function select(page, scope, text) {
  const ok = await page.evaluate(([scope, text]) => {
    const root = document.querySelector(scope);
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const i = n.nodeValue.indexOf(text);
      if (i >= 0) {
        const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + text.length);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r);
        n.parentElement.scrollIntoView({ block: 'center' });
        document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
        return true;
      }
    }
    return false;
  }, [scope, text]);
  if (!ok) throw new Error('text not found: ' + text);
  await page.waitForSelector('#seltool:not([hidden])');
}
async function modalSave(page, text) {
  await page.waitForSelector('.modal textarea');
  await page.fill('.modal textarea', text);
  await page.click('.modal button.primary');
  await page.waitForSelector('#toast:not([hidden])');
  const t = await page.textContent('#toast'); log('toast:', t);
  return t;
}

(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(base + '/#/'); await page.waitForTimeout(700);
  await page.screenshot({ path: `${shots}/01-home.png` }); log('home');

  await page.goto(base + '/#/t/fsrs?tab=overview'); await page.waitForTimeout(700);
  await page.screenshot({ path: `${shots}/02-topic-overview.png` }); log('topic overview');
  await page.goto(base + '/#/t/fsrs?tab=concepts'); await page.waitForTimeout(500);
  await page.screenshot({ path: `${shots}/03-concept-map.png`, fullPage: true }); log('concept map');

  // Read a concept, highlight with a note, answer a prompt, say how well we know it.
  await page.goto(base + '/#/c/stability'); await page.waitForTimeout(700);
  await select(page, 'article', 'the number of days until retrievability drops to 90%'.slice(0, 0) || 'it is the time it takes for');
  await page.click('#seltool [data-act="note"]');
  await modalSave(page, 'So stability is a "90%-life", not a half-life: it is defined where recall odds hit 90%, not 50%.');
  await page.fill('.prompt textarea', 'At 90% desired retention the card would come back after about 10 days, because S is exactly the time until recall odds fall to 90%.');
  await page.click('.prompt button'); await page.waitForTimeout(600);
  await page.click('text=Familiar'); await page.waitForTimeout(500);
  await page.mouse.wheel(0, 2000); await page.waitForTimeout(5600);  // reading → progress is recorded
  await page.screenshot({ path: `${shots}/04-concept-highlight.png`, fullPage: true }); log('concept read + highlight + answer');

  // A doubt goes into the research queue.
  await page.goto(base + '/#/c/benchmark-metrics'); await page.waitForTimeout(600);
  await page.click('text=I\'m not convinced');
  await modalSave(page, 'Log loss gaps look small (0.35 vs 0.39). Is that a meaningful difference for a learner?');

  // Read a source, highlight an exact quote, leave mid-way.
  await page.goto(base + '/#/s/src-awesome-fsrs-wiki-the-4c03'); await page.waitForTimeout(700);
  await select(page, '.src-text', 'the subsequent stability converges to an upper limit');
  await page.click('#seltool [data-act="note"]');
  await modalSave(page, 'This is why a long break hurts less under FSRS than under SM-2.');
  await page.evaluate(() => document.getElementById('p86').scrollIntoView({ block: 'start' }));
  await page.waitForTimeout(5800);  // the tracker flushes every 5 s
  await page.goto(base + '/#/'); await page.waitForTimeout(800);
  await page.screenshot({ path: `${shots}/05-home-continue.png` }); log('home shows "continue where you left off"');
  await page.goto(base + '/#/s/src-awesome-fsrs-wiki-the-4c03'); await page.waitForTimeout(1000);
  const banner = await page.textContent('.banner').catch(() => '');
  log('resume banner:', banner.trim());
  await page.screenshot({ path: `${shots}/06-source-resumed.png` });

  // Evidence behind a conclusion.
  await page.goto(base + '/#/t/fsrs?tab=conclusions'); await page.waitForTimeout(600);
  await page.click('.claim details summary'); await page.waitForTimeout(300);
  await page.screenshot({ path: `${shots}/07-conclusions-evidence.png` }); log('conclusions with evidence');

  await page.goto(base + '/#/questions'); await page.waitForTimeout(600);
  await page.screenshot({ path: `${shots}/08-my-questions.png` }); log('my questions');

  // Export highlights + one concept note to Obsidian.
  await page.goto(base + '/#/highlights'); await page.waitForTimeout(600);
  for (const cb of await page.$$('.hl-item input[type=checkbox]')) await cb.check();
  await page.check('label.chip input[type=checkbox]');
  await page.click('text=Export selected'); await page.waitForTimeout(800);
  log('export result:\n' + (await page.textContent('.files')));
  await page.screenshot({ path: `${shots}/09-highlights-export.png`, fullPage: true });

  // A 15-minute session from the topic page.
  await page.goto(base + '/#/t/fsrs'); await page.waitForTimeout(500);
  await page.click('text=15 min'); await page.waitForTimeout(800);
  await page.screenshot({ path: `${shots}/10-session.png` }); log('session planned:', (await page.textContent('#view ol')).replace(/\s+/g, ' ').slice(0, 300));

  // Phone width.
  const phone = await b.newPage({ viewport: { width: 390, height: 844 } });
  await phone.goto(base + '/#/c/stability'); await phone.waitForTimeout(700);
  await phone.screenshot({ path: `${shots}/11-phone-concept.png` });
  const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  log('phone horizontal overflow px:', overflow);
  log('page errors:', JSON.stringify(errors));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
