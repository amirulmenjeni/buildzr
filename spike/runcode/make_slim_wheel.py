"""SPIKE: the docs wheel. The full wheel is 21.8 MB (PlantUML jars); the browser needs only the Python of the DSL and
of the build stages. Drops the jars, the viewer bundle (the docs ship it separately) and the ELK bundle (loaded as JS).

    python spike/runcode/make_slim_wheel.py dist/buildzr-X-py3-none-any.whl docs/runcode/
"""

import os
import sys
import zipfile

DROP = ("buildzr/jars/", "buildzr/site/static/", "buildzr/site/layout/vendor/elk.bundled.js")

src, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
dst = os.path.join(out_dir, os.path.basename(src))
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
    for info in zin.infolist():
        if info.filename.startswith(DROP):
            continue
        data = zin.read(info.filename)
        if info.filename.endswith(".dist-info/RECORD"):  # keep RECORD consistent with what is left
            data = b"".join(ln + b"\n" for ln in data.splitlines() if not ln.decode().startswith(DROP))
        zout.writestr(info, data, zipfile.ZIP_DEFLATED, 9)
print(dst, os.path.getsize(dst))
