"""Load environment and DashScope-related settings."""

from __future__ import annotations

import base64
import os
from pathlib import Path

from dotenv import load_dotenv

_APP_DIR = Path(__file__).resolve().parent
_ROOT = _APP_DIR.parent
# 与 .env.example 一致：优先仓库根目录；兼容密钥放在 app/.env 的情况（PyCharm 工作目录常为 app）
load_dotenv(_ROOT / ".env", override=False)
load_dotenv(_APP_DIR / ".env", override=True)

WSS_CN = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
WSS_INTL = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"
CHAT_BASE_DEFAULT = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def api_key() -> str:
    return (
        os.environ.get("DASHSCOPE_API_KEY", "").strip()
        or os.environ.get("QWEN_API_KEY", "").strip()
    )


def websocket_url() -> str:
    region = os.environ.get("DASHSCOPE_REGION", "cn").strip().lower()
    return WSS_INTL if region == "intl" else WSS_CN


def asr_model() -> str:
    return os.environ.get("ASR_MODEL", "fun-asr-realtime").strip()


def summary_model() -> str:
    return os.environ.get("SUMMARY_MODEL", "qwen-turbo").strip()


def chat_base_url() -> str:
    return os.environ.get("DASHSCOPE_CHAT_BASE", CHAT_BASE_DEFAULT).rstrip("/")


def frame_ms() -> int:
    return max(40, min(500, int(os.environ.get("FRAME_MS", "100"))))


def semantic_punctuation() -> bool:
    return os.environ.get("SEMANTIC_PUNCTUATION", "false").lower() in (
        "1",
        "true",
        "yes",
    )


def heartbeat() -> bool:
    return os.environ.get("HEARTBEAT", "false").lower() in ("1", "true", "yes")


def use_portaudio_audio() -> bool:
    """为 True 时使用 PortAudio(sounddevice) 枚举与采集；默认 False 使用 Qt Multimedia（与会议软件路由一致）。"""
    return os.environ.get("AUDIO_BACKEND", "").strip().lower() == "portaudio"


def env_qt_input_device_id() -> bytes | None:
    raw = os.environ.get("AUDIO_QT_DEVICE_ID", "").strip()
    if not raw:
        return None
    try:
        return base64.standard_b64decode(raw)
    except Exception:
        return None


def audio_input_gain() -> float:
    """Linear gain applied to captured int16 PCM before resampling / ASR (default 1)."""
    raw = os.environ.get("AUDIO_INPUT_GAIN", "").strip()
    if not raw:
        return 1.0
    try:
        g = float(raw)
    except ValueError:
        return 1.0
    return max(0.25, min(64.0, g))
