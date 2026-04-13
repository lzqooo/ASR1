"""Qwen chat summarization via DashScope OpenAI-compatible HTTP API."""

from __future__ import annotations

import httpx
from PySide6.QtCore import QThread, Signal

from app import config

MAX_INPUT_CHARS = 120_000

SYSTEM_PROMPT = (
    "你是专业的中文会议纪要助手。请根据用户给出的语音转写，输出一份**尽量详细**的结构化总结，"
    "必须使用 Markdown：\n"
    "1) 第一行起用一级标题：`# 会议/内容概要`（可自拟贴切标题）。\n"
    "2) 用若干二级标题 `## …` 组织章节，例如：背景与目的、讨论要点、决定与结论、待办与责任人、"
    "风险与疑问、时间线与数字、专有名词与术语等（按实际内容取舍，无则省略该章）。\n"
    "3) 在二级标题下可用三级标题 `### …` 细分小节。\n"
    "4) 正文用短段落与列表 `- ` 混排；关键结论加粗用 `**…**`；数字、日期、人名、产品名尽量保留原样。\n"
    "5) 内容要充实：不仅列提纲，还要写出可读的说明与推理脉络，必要时引用转写中的关键表述（简述即可，勿大段照抄）。\n"
    "6) 若无有效信息，只输出：`# 无有效内容` 及一句说明。\n"
    "不要输出代码块围栏以外的 HTML；不要编造转写中不存在的事实。"
)


def summarize_sync(transcript: str) -> str:
    key = config.api_key()
    if not key:
        raise ValueError("未配置 DASHSCOPE_API_KEY 或 QWEN_API_KEY")

    text = transcript.strip()
    if not text:
        raise ValueError("转写内容为空")

    url = f"{config.chat_base_url()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.summary_model(),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text[:MAX_INPUT_CHARS]},
        ],
        "max_tokens": 8192,
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"响应无 choices: {data}")
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if not content:
        raise RuntimeError(f"响应无正文: {data}")
    return content.strip()


class SummaryWorker(QThread):
    done = Signal(str)
    error = Signal(str)

    def __init__(self, transcript: str, parent=None) -> None:
        super().__init__(parent)
        self._transcript = transcript

    def run(self) -> None:
        try:
            out = summarize_sync(self._transcript)
            self.done.emit(out)
        except Exception as e:
            self.error.emit(str(e))
