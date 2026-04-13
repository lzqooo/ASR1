"""全局样式与总结区轻量 Markdown→HTML（供 QTextBrowser 显示）。"""

from __future__ import annotations

import html
import re

# 大地色系：砂岩、羊皮纸、赭石、橄榄褐、陶土；字号再放大一档
MAIN_STYLESHEET = """
QMainWindow {
    background-color: #c9b8a0;
}
QWidget#centralRoot {
    background-color: #c9b8a0;
}
QWidget {
    color: #3a3228;
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 17px;
}
QFrame#toolCard, QFrame#editorCard {
    background-color: #f3ebe0;
    border: 1px solid #b5a286;
    border-radius: 12px;
}
QFrame#editorCard {
    background-color: #f7f1e6;
}
QLabel.sectionTitle {
    font-size: 16px;
    font-weight: 600;
    color: #5c4d3d;
    letter-spacing: 0.08em;
    padding-bottom: 4px;
}
QLabel.hint {
    color: #6e5f4c;
    font-size: 15px;
}
QComboBox {
    background-color: #fffdf8;
    border: 1px solid #c4b09a;
    border-radius: 8px;
    padding: 9px 14px;
    min-height: 30px;
    font-size: 17px;
}
QComboBox:hover {
    border-color: #9a8268;
}
QComboBox::drop-down {
    border: none;
    width: 34px;
}
QCheckBox {
    spacing: 10px;
    color: #4a3f32;
    font-size: 17px;
}
QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border-radius: 4px;
    border: 1px solid #a89278;
    background: #fffdf8;
}
QCheckBox::indicator:checked {
    background: #8b7355;
    border-color: #6b5644;
}
QPushButton#btnMicTest {
    background-color: #e8ddce;
    color: #3d3428;
    border: 1px solid #c4b09a;
    border-radius: 8px;
    padding: 11px 18px;
    font-weight: 600;
    font-size: 17px;
}
QPushButton#btnMicTest:hover {
    background-color: #ddd1c0;
}
QPushButton#btnMicTest:pressed {
    background-color: #d0c2b0;
}
QPushButton#btnRecord {
    background-color: #6d6348;
    color: #fffdf8;
    border: none;
    border-radius: 12px;
    padding: 14px;
    font-weight: 700;
}
QPushButton#btnRecord:hover {
    background-color: #5d5540;
}
QPushButton#btnRecord:pressed {
    background-color: #4e4736;
}
QPushButton#btnRecord[recording="true"] {
    background-color: #b5654a;
}
QPushButton#btnRecord[recording="true"]:hover {
    background-color: #a0553e;
}
QPushButton#btnSecondary {
    background-color: #e5d9c8;
    color: #2e281f;
    border: 1px solid #bda892;
    border-radius: 12px;
    padding: 14px;
    font-weight: 600;
}
QPushButton#btnSecondary:hover {
    background-color: #d9cbb6;
}
QPushButton#btnSecondary:pressed {
    background-color: #ccbaa4;
}
QPushButton#btnSecondary:disabled {
    background-color: #ebe3d8;
    color: #9a8b7a;
    border-color: #cfc2b2;
}
QPushButton#btnAccent {
    background-color: #6b5344;
    color: #fffdf8;
    border: none;
    border-radius: 12px;
    padding: 14px;
    font-weight: 700;
}
QPushButton#btnAccent:hover {
    background-color: #5a4538;
}
QPushButton#btnAccent:pressed {
    background-color: #4a392e;
}
QPushButton#btnAccent:disabled {
    background-color: #b5a99a;
    color: #f0ebe4;
}
QProgressBar {
    border: 1px solid #c4b09a;
    border-radius: 6px;
    background-color: #ebe3d6;
    text-align: center;
    color: #3a3228;
    min-height: 28px;
    font-size: 16px;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #a68968, stop:1 #c4a574);
    border-radius: 5px;
}
QProgressBar#summaryBusy {
    border-radius: 6px;
    max-height: 7px;
    min-height: 7px;
}
QProgressBar#summaryBusy::chunk {
    background-color: #8b7355;
}
QPlainTextEdit {
    background-color: #fffdf8;
    color: #322a22;
    border: 1px solid #d4c4b0;
    border-radius: 8px;
    padding: 14px;
    font-family: "Cascadia Mono", "Consolas", "Microsoft YaHei UI", monospace;
    font-size: 16px;
    selection-background-color: #d4c4a8;
}
QTextBrowser {
    background-color: #fffdf8;
    color: #322a22;
    border: 1px solid #d4c4b0;
    border-radius: 8px;
    padding: 12px;
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 17px;
}
QSplitter::handle {
    background-color: #c9b8a5;
    height: 3px;
    margin: 4px 12px;
    border-radius: 2px;
}
QSplitter::handle:hover {
    background-color: #9a8268;
}
QStatusBar {
    background-color: #b8a892;
    color: #2a241c;
    border-top: 1px solid #9a8b78;
    font-size: 15px;
    padding: 5px 10px;
}
"""


def _inline_format(text: str) -> str:
    s = html.escape(text)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)

    def _code(m: re.Match[str]) -> str:
        inner = m.group(1)
        return (
            '<code style="background:#ebe3d6;padding:2px 6px;border-radius:4px;'
            f'font-size:0.92em;">{inner}</code>'
        )

    s = re.sub(r"`([^`]+)`", _code, s)
    return s


def summary_markdown_to_html(md: str) -> str:
    """将模型返回的 Markdown 转为 QTextBrowser 可用的 HTML（分级标题与正文字号）。"""
    md = (md or "").strip()
    if not md:
        return ""

    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    buf: list[str] = []
    in_ul = False

    def flush_para() -> None:
        if not buf:
            return
        text = " ".join(buf)
        out.append(f'<p style="margin:8px 0;line-height:1.7;">{_inline_format(text)}</p>')
        buf.clear()

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("### "):
            flush_para()
            close_ul()
            out.append(f'<h3 style="margin:14px 0 6px;font-size:19px;color:#5c4d3d;font-weight:600;">{_inline_format(stripped[4:].strip())}</h3>')
        elif stripped.startswith("## "):
            flush_para()
            close_ul()
            out.append(f'<h2 style="margin:18px 0 8px;font-size:24px;color:#4a3f32;font-weight:600;letter-spacing:0.02em;">{_inline_format(stripped[3:].strip())}</h2>')
        elif stripped.startswith("# "):
            flush_para()
            close_ul()
            out.append(f'<h1 style="margin:6px 0 12px;font-size:30px;color:#3d3428;font-weight:700;letter-spacing:0.03em;">{_inline_format(stripped[2:].strip())}</h1>')
        elif re.match(r"^[-*]\s+", stripped):
            flush_para()
            if not in_ul:
                out.append('<ul style="margin:6px 0;padding-left:22px;">')
                in_ul = True
            item = re.sub(r"^[-*]\s+", "", stripped)
            out.append(f'<li style="margin:5px 0;line-height:1.65;">{_inline_format(item)}</li>')
        elif re.match(r"^\d+\.\s+", stripped):
            flush_para()
            close_ul()
            item = re.sub(r"^\d+\.\s+", "", stripped)
            out.append(f'<p style="margin:4px 0 4px 12px;line-height:1.65;">• {_inline_format(item)}</p>')
        elif not stripped:
            flush_para()
            close_ul()
        else:
            close_ul()
            buf.append(stripped)

    flush_para()
    close_ul()
    body = "\n".join(out)

    base = """
    body {
      font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
      font-size: 18px;
      color: #322a22;
      line-height: 1.65;
      margin: 4px 6px 12px;
    }
    """
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><style>{base}</style></head><body>{body}</body></html>"""


def plain_text_to_summary_html(text: str) -> str:
    """无 Markdown 结构时的兜底：按段落成 HTML。"""
    text = (text or "").strip()
    if not text:
        return ""
    parts = re.split(r"\n\s*\n+", text)
    paras = "".join(
        f'<p style="margin:8px 0;line-height:1.7;">{_inline_format(p.strip())}</p>'
        for p in parts
        if p.strip()
    )
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/></head><body style="font-family:Microsoft YaHei UI,Segoe UI,sans-serif;font-size:18px;color:#322a22;">{paras}</body></html>"""
