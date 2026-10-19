// The synchronous ELK of the browser (buildzr/site/layout/browser_elk.js) behind the line protocol of runner.mjs,
// so tests can build with it from CPython. argv: node browser_elk_runner.mjs /abs/path/to/elk.bundled.js
import { createRequire } from "node:module";
import { createInterface } from "node:readline";

const require = createRequire(import.meta.url);
const ELK = require(process.argv[2]);
const { makeElkSync } = require("../../buildzr/site/layout/browser_elk.js");
const elkLayoutSync = await makeElkSync(ELK);
process.stdout.write(JSON.stringify({ ready: true }) + "\n");
for await (const line of createInterface({ input: process.stdin, crlfDelay: Infinity })) {
  if (!line.trim()) continue;
  const req = JSON.parse(line);
  process.stdout.write(JSON.stringify({ id: req.id, results: JSON.parse(elkLayoutSync(JSON.stringify(req.graphs))) }) + "\n");
}
