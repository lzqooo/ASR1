"""DashScope Fun-ASR realtime streaming in a QThread."""

from __future__ import annotations

import threading

import dashscope
from PySide6.QtCore import QThread, Signal
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

from app import config
from app.audio.devices import PcmMicReader
from app.audio.pcm_source import SAMPLE_RATE, frames_per_chunk
from app.audio.qt_input import QtPcmMicReader


class FunAsrWorker(QThread):
    """Runs Recognition.start → send_audio_frame loop → stop in background."""

    connected = Signal()
    partial_text = Signal(str)
    sentence_final = Signal(str)
    failed = Signal(str)
    finished_clean = Signal()
    level = Signal(float, float)

    def __init__(
        self,
        parent=None,
        *,
        qt_device_id: bytes | None = None,
        portaudio_index: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._qt_device_id = qt_device_id
        self._portaudio_index = portaudio_index
        self._run_flag = threading.Event()
        self._run_flag.set()
        self._pause = threading.Event()
        self._connected = threading.Event()
        self._server_failed = threading.Event()
        self._recognition: Recognition | None = None

    def request_stop(self) -> None:
        self._run_flag.clear()

    def request_pause(self) -> None:
        self._pause.set()

    def request_resume(self) -> None:
        self._pause.clear()

    def is_paused(self) -> bool:
        return self._pause.is_set()

    def run(self) -> None:
        key = config.api_key()
        if not key:
            self.failed.emit("未配置 DASHSCOPE_API_KEY 或 QWEN_API_KEY")
            self.finished_clean.emit()
            return

        dashscope.api_key = key
        dashscope.base_websocket_api_url = config.websocket_url()

        self._connected.clear()
        self._server_failed.clear()
        worker = self

        class _Cb(RecognitionCallback):
            def on_open(self) -> None:
                worker._connected.set()
                worker.connected.emit()

            def on_close(self) -> None:
                pass

            def on_complete(self) -> None:
                pass

            def on_error(self, result) -> None:
                worker._server_failed.set()
                worker.request_stop()
                msg = (getattr(result, "message", None) or "").strip() or "语音识别错误"
                code = getattr(result, "code", None)
                req = getattr(result, "request_id", None)
                sc = getattr(result, "status_code", None)
                bits = [msg]
                if code is not None:
                    bits.append(f"code={code}")
                if req:
                    bits.append(f"request_id={req}")
                if sc is not None:
                    bits.append(f"status={sc}")
                detail = " | ".join(bits)
                if "internal server error" in msg.lower():
                    detail += "\n\n提示：核对 ASR_MODEL、DASHSCOPE_REGION 与 Key 是否开通语音识别。"
                worker.failed.emit(detail)

            def on_event(self, result: RecognitionResult) -> None:
                sentence = result.get_sentence()
                if not isinstance(sentence, dict) or "text" not in sentence:
                    return
                text = sentence["text"]
                if not text:
                    return
                if RecognitionResult.is_sentence_end(sentence):
                    worker.sentence_final.emit(text)
                else:
                    worker.partial_text.emit(text)

        frame_ms = config.frame_ms()
        chunk_frames = frames_per_chunk(frame_ms)

        kwargs: dict = {
            "model": config.asr_model(),
            "format": "pcm",
            "sample_rate": SAMPLE_RATE,
            "semantic_punctuation_enabled": config.semantic_punctuation(),
            "callback": _Cb(),
        }
        if config.heartbeat():
            kwargs["heartbeat"] = True

        try:
            recognition = Recognition(**kwargs)
        except TypeError:
            kwargs.pop("heartbeat", None)
            recognition = Recognition(**kwargs)
        self._recognition = recognition

        try:
            recognition.start()
        except Exception as e:
            self.failed.emit(f"启动识别失败: {e}")
            self.finished_clean.emit()
            return

        if not self._connected.wait(timeout=20.0):
            self.failed.emit("连接识别服务超时")
            try:
                recognition.stop()
            except Exception:
                pass
            self.finished_clean.emit()
            return

        record_error: str | None = None
        mic: PcmMicReader | QtPcmMicReader | None = None
        try:
            if config.use_portaudio_audio():
                mic = PcmMicReader(self._portaudio_index, frames_16k=chunk_frames)
            else:
                mic = QtPcmMicReader(self._qt_device_id, frames_16k=chunk_frames)
            mic.start()
            try:
                while self._run_flag.is_set():
                    if self._server_failed.is_set():
                        break
                    pcm, peak, rms = mic.read_pcm16_mono()
                    self.level.emit(peak, rms)
                    if self._pause.is_set():
                        continue
                    if pcm and not self._server_failed.is_set():
                        try:
                            recognition.send_audio_frame(pcm)
                        except Exception as send_exc:
                            if self._server_failed.is_set():
                                break
                            if "Speech recognition has stopped" in str(send_exc):
                                break
                            raise
            finally:
                if mic is not None:
                    mic.close()
                    mic = None
        except Exception as e:
            if not self._server_failed.is_set():
                record_error = f"录音失败: {e}"
                self.failed.emit(record_error)
        finally:
            try:
                recognition.stop()
            except Exception:
                pass
            self._recognition = None
            self.finished_clean.emit()
