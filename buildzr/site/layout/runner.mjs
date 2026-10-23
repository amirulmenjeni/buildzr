// Long-lived ELK runner. Protocol: one JSON object per line.
//   argv: node runner.mjs /abs/path/to/elk.bundled.js
//   stdout, first line:   {"ready": true, "elk": "<version>"}
//   stdin request line:   {"id": <n>, "graphs": {"<name>": <ELK graph>, ...}}
//   stdout response line: {"id": <n>, "results": {"<name>": {"graph": <laid out>, "ms": <number>} | {"error": "<msg>"}}}
// "ms" is the in-process time of one elk.layout() call, after a warm-up.
import { createRequire } from "node:module";
import { createInterface } from "node:readline";

const require = createRequire(import.meta.url);
const ELK = require(process.argv[2]);
const elk = new ELK();

await elk.layout({
  id: "root",
  layoutOptions: { "elk.algorithm": "layered" },
  children: [
    { id: "a", width: 10, height: 10 },
    { id: "b", width: 10, height: 10 },
  ],
  edges: [{ id: "e", sources: ["a"], targets: ["b"] }],
});

process.stdout.write(JSON.stringify({ ready: true, elk: elk.version ?? "" }) + "\n");

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
  if (!line.trim()) continue;
  const req = JSON.parse(line);
  const results = {};
  for (const [name, graph] of Object.entries(req.graphs)) {
    try {
      const t0 = performance.now();
      const out = await elk.layout(graph);
      results[name] = { graph: out, ms: performance.now() - t0 };
    } catch (e) {
      results[name] = { error: String(e && e.message ? e.message : e) };
    }
  }
  process.stdout.write(JSON.stringify({ id: req.id, results }) + "\n");
}
