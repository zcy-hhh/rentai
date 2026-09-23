# 作者：zcy
"""文档解析：PDF / PPT / Excel / 文本 → 分页(节)文本。

解析失败不阻塞整批（单页失败跳过），返回 [{page, text}]。
- PDF：PyMuPDF(fitz) 抽取文本层；扫描件(无文本)返回空，由上层走视觉理解（扩展点）。
- PPT：python-pptx 抽取文本框 + 表格，按页(slide)聚合。
- Excel：openpyxl 每 sheet 每行转"列|值"文本，page 记 sheet 序号，sheet 名入 meta。
"""
from __future__ import annotations


def _pdf(path: str) -> list[dict]:
    import fitz  # pymupdf

    out: list[dict] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc):
            t = page.get_text().strip()
            if t:
                out.append({"page": i + 1, "text": t})
    return out


def _pptx(path: str) -> list[dict]:
    from pptx import Presentation

    out: list[dict] = []
    prs = Presentation(path)
    for i, slide in enumerate(prs.slides):
        parts: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    txt = "".join(r.text for r in para.runs).strip()
                    if txt:
                        parts.append(txt)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    parts.append(" | ".join(c for c in cells if c))
        t = "\n".join(parts).strip()
        if t:
            out.append({"page": i + 1, "text": t})
    return out


def _xlsx(path: str) -> list[dict]:
    import openpyxl

    out: list[dict] = []
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    for idx, ws in enumerate(wb.worksheets, start=1):
        lines: list[str] = []
        for row in ws.iter_rows(values_only=True):
            vals = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if vals:
                lines.append(" | ".join(vals))
        t = "\n".join(lines).strip()
        if t:
            out.append({"page": idx, "text": t, "sheet": ws.title})
    return out


def _text(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read().strip()
    return [{"page": 1, "text": content}] if content else []


def extract_text(path: str, filename: str) -> list[dict]:
    """按扩展名解析文档 → [{page, text, sheet?}]。失败抛异常由调用方处理。"""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        return _pdf(path)
    if ext in ("pptx", "ppt"):
        return _pptx(path)
    if ext in ("xlsx", "xls"):
        return _xlsx(path)
    if ext in ("txt", "md", "csv"):
        return _text(path)
    raise ValueError(f"暂不支持的文档格式：.{ext}")
