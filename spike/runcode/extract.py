"""SPIKE: write every runnable python block (not `# no-run`) of the docs pages as OUT/<page>_<line>.py."""

import glob
import os
import sys

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
pages = sorted(glob.glob("docs/getting-started/*.md") + glob.glob("docs/user-guide/*.md") + glob.glob("docs/*.md"))
n = 0
for page in pages:
    lines = open(page, encoding="utf-8").read().split("\n")
    i = 0
    while i < len(lines):
        s = lines[i].lstrip()
        if s.startswith("```python"):
            indent = len(lines[i]) - len(s)
            j = i + 1
            while not lines[j].lstrip().startswith("```"):
                j += 1
            body = [ln[indent:] for ln in lines[i + 1:j]]
            first = next((b for b in body if b.strip()), "")
            if not first.strip().startswith(("# no-run", "# norun")):
                name = os.path.splitext(page[len("docs/"):])[0].replace("/", "-") + f"_{i + 1}.py"
                with open(os.path.join(out, name), "w", encoding="utf-8") as f:
                    f.write("\n".join(body) + "\n")
                n += 1
            i = j
        i += 1
print(n, "snippets")
