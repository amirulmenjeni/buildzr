// Screenshots: landscape, one expanded system, one expanded container; desktop 1600x1000 and phone 390x844.
import fs from 'node:fs';
import path from 'node:path';
import { newPage, open, ROOT, serve, launch } from './lib.mjs';

export default async function shots(browser, srv, F, name) {
  const out = path.join(ROOT, '.shots');
  fs.mkdirSync(out, { recursive: true });
  const sys = F.expandable.find((id) => !F.parentOf(id));
  const cont = F.expandable.find((id) => F.parentOf(id));
  const states = [['landscape', '#/m'], ['system', `#/m/${sys}`], ...(cont ? [['container', `#/m/${cont}`]] : [])];
  for (const [dev, vp] of [['desktop', { width: 1600, height: 1000 }], ['phone', { width: 390, height: 844 }]]) {
    for (const [st, hash] of states) {
      const errors = [];
      const p = await newPage(browser, errors, { viewport: vp, deviceScaleFactor: dev === 'phone' ? 2 : 1 });
      await open(p, srv.url, hash);
      await p.screenshot({ path: path.join(out, `${name}-${dev}-${st}.png`) });
      await p.context().close();
    }
  }
  console.log(`  screenshots in ${out}`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const dir = path.resolve(process.argv[2] || path.join(ROOT, '../tests/site/fixtures/small'));
  const index = JSON.parse(fs.readFileSync(path.join(dir, 'index.json'), 'utf8'));
  const model = JSON.parse(fs.readFileSync(path.join(dir, index.model.file), 'utf8'));
  const els = model.elements;
  const expandable = els.filter((e) => ('e/' + e.id) in index.scenes && e.children.length).map((e) => e.id);
  const srv = await serve(dir);
  const b = await launch();
  await shots(b, srv, { expandable, parentOf: (id) => els.find((e) => e.id === id).parent ?? '' }, path.basename(dir));
  await b.close(); srv.close();
}
