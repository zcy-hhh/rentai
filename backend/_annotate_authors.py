# -*- coding: utf-8 -*-
# 作者：zcy
"""为 RentAI 项目所有代码文件标注作者（zcy）。只插入头部注释，不改任何逻辑。"""
import os

ROOT = r"E:\Code\rentai"

# 排除目录
SKIP_DIRS = {".venv", "node_modules", "dist", "__pycache__", ".git", ".pytest_cache", ".next", "coverage"}

# 扩展名 -> 注释前缀（保持行注释语法）
MARKERS = {
    ".py": "# 作者：zcy",
    ".ts": "// 作者：zcy",
    ".tsx": "// 作者：zcy",
    ".js": "// 作者：zcy",
    ".jsx": "// 作者：zcy",
    ".css": "/* 作者：zcy */",
    ".html": "<!-- 作者：zcy -->",
    ".yml": "# 作者：zcy",
    ".yaml": "# 作者：zcy",
}


def prepend(path: str, marker: str) -> bool:
    with open(path, "r", encoding="utf-8", newline="") as f:
        content = f.read()
    if not content.strip():
        return False
    # 已有标注则跳过（幂等）
    if marker in content[:60] or "作者：zcy" in content[:80]:
        return False
    lines = content.split("\n")
    # Python 文件保留首行 shebang / coding 声明，标注插在其后
    insert_at = 0
    if marker.startswith("#") and lines and (
        lines[0].startswith("#!") or lines[0].startswith("# -*-") or lines[0].startswith("# coding")
    ):
        insert_at = 1
    lines.insert(insert_at, marker)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines))
    return True


annotated, skipped = [], 0
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    for fn in filenames:
        ext = os.path.splitext(fn)[1].lower()
        if ext not in MARKERS:
            continue
        p = os.path.join(dirpath, fn)
        try:
            if prepend(p, MARKERS[ext]):
                annotated.append(p)
            else:
                skipped += 1
        except Exception as e:
            print("SKIP 异常:", p, e)

print(f"已标注 {len(annotated)} 个文件，跳过 {skipped}（无内容或已标注）")
