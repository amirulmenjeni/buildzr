// Generates ../../tools/font_metrics.json from Inter (OFL-1.1) via @fontsource/inter .woff files.
import fs from 'node:fs';
import opentype from 'opentype.js';

const pkg = JSON.parse(fs.readFileSync('node_modules/@fontsource/inter/package.json', 'utf8'));
function load(w) {
  const b = fs.readFileSync(`node_modules/@fontsource/inter/files/inter-latin-${w}-normal.woff`);
  return opentype.parse(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
}
const fonts = { regular: load(400), bold: load(700) };
const out = {
  font: 'Inter', source: `@fontsource/inter@${pkg.version}`, license: 'OFL-1.1',
  unitsPerEm: fonts.regular.unitsPerEm, kerning: false, advances: {}, average: {},
};
for (const [k, f] of Object.entries(fonts)) {
  if (f.unitsPerEm !== out.unitsPerEm) throw new Error('unitsPerEm mismatch');
  const adv = [];
  for (let c = 32; c <= 126; c++) {
    const g = f.charToGlyph(String.fromCharCode(c));
    if (!g || g.index === 0) throw new Error('missing glyph ' + c);
    adv.push(g.advanceWidth);
  }
  out.advances[k] = adv; // index = codepoint - 32
  out.average[k] = Math.round(adv.reduce((a, b) => a + b, 0) / adv.length);
}
fs.writeFileSync('../../tools/font_metrics.json', JSON.stringify(out) + '\n');
console.log('wrote', out.font, out.source, out.unitsPerEm, out.average);
