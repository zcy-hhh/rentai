# -*- coding: utf-8 -*-
import os
from collections import Counter

ROOT = r"E:\Code\rentai"
counts = Counter()
total = 0
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in {"node_modules", "dist", ".venv", "__pycache__", ".git", "reference"}]
    for fn in filenames:
        p = os.path.join(dirpath, fn)
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(120)
            if "作者：zcy" in head:
                rel = os.path.relpath(p, ROOT)
                top = rel.split(os.sep)[0] if os.sep in rel else "(根)"
                counts[top] += 1
                total += 1
        except Exception:
            pass

for top, n in sorted(counts.items()):
    print(f"{top}: {n}")
print("总计:", total)
