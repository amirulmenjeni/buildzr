// Usage: node elk_run.mjs IN.json OUT.json [--repeat N]
// Prints the in-process layout time (ms; median when --repeat) to stderr.
import { readFileSync, writeFileSync } from "node:fs";
import ELK from "elkjs/lib/elk.bundled.js";

const args = process.argv.slice(2);
let repeat = 1;
const ri = args.indexOf("--repeat");
if (ri >= 0) { repeat = parseInt(args[ri + 1], 10); args.splice(ri, 2); }
const [inp, outp] = args;
const graph = JSON.parse(readFileSync(inp, "utf8"));
const elk = new ELK();
const times = [];
let result;
for (let i = 0; i < repeat; i++) {
  const g = structuredClone(graph);
  const t0 = performance.now();
  result = await elk.layout(g);
  times.push(performance.now() - t0);
}
writeFileSync(outp, JSON.stringify(result));
times.sort((a, b) => a - b);
const med = times[Math.floor(times.length / 2)];
process.stderr.write(`elk_ms=${med.toFixed(1)} runs=${repeat} first_ms=${times.length ? "" : ""}${(times[0]).toFixed(1)}\n`);
