"""Modal dialog to verify microphone input levels (no API calls)."""

from __future__ import annotations

import math
import threading

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from app import config
from app.audio.devices import PcmMicReader
from app.audio.qt_input import QtPcmMicReader


class _MicLevelWorker(QThread):
    level = Signal(float, float)
    failed = Signal(str)

    def __init__(
        self,
        qt_device_id: bytes | None,
        portaudio_index: int | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._qt_device_id = qt_device_id
        self._portaudio_index = portaudio_index
        self._stop = threading.Event()
        self._reader: PcmMicReader | QtPcmMicReader | None = None

    def stop_safe(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            if config.use_portaudio_audio():
                self._reader = PcmMicReader(self._portaudio_index, frames_16k=1600)
            else:
                self._reader = QtPcmMicReader(self._qt_device_id, frames_16k=1600)
            self._reader.start()
            while not self._stop.is_set():
                _pcm, peak, rms = self._reader.read_pcm16_mono()
                self.level.emit(peak, rms)
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            if self._reader is not None:
                self._reader.close()
                self._reader = None


class MicTestDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        qt_device_id: bytes | None = None,
        portaudio_index: int | None = None,
    ) -> None:
        super().__init__(parent)
        g = config.audio_input_gain()
        title = "麦克风测试"
        if abs(g - 1.0) > 1e-9:
            title += f"（增益×{g:g}）"
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(420, 220)
        self._qt_device_id = qt_device_id
        self._portaudio_index = portaudio_index
        self._worker: _MicLevelWorker | None = None

        layout = QVBoxLayout(self)
        if config.use_portaudio_audio():
            hint = (
                "当前为 PortAudio 模式（AUDIO_BACKEND=portaudio）。"
                "点击「开始」后观察电平；若与系统设置差异大，可去掉该环境变量改用 Qt 采集。\n"
                "仍弱时可调 AUDIO_INPUT_GAIN。"
            )
        else:
            hint = (
                "使用 Qt Multimedia 采集，与 Windows「设置→声音」及常见会议软件默认麦克风路由一致。\n"
                "点击「开始」后观察电平；仍很弱时可调高系统输入音量，或在 .env 设 AUDIO_INPUT_GAIN。"
            )
        layout.addWidget(QLabel(hint))

        self._bar = QProgressBar()
        self._bar.setRange(0, 10_000)
        self._bar.setFormat("0.00%")
        self._bar.setValue(0)
        layout.addWidget(self._bar)
        self._label = QLabel("峰值: —    RMS: —")
        layout.addWidget(self._label)

        row = QHBoxLayout()
        self._btn_start = QPushButton("开始")
        self._btn_stop = QPushButton("停止")
        self._btn_stop.setEnabled(False)
        row.addWidget(self._btn_start)
        row.addWidget(self._btn_stop)
        row.addStretch()
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop.clicked.connect(self._on_stop)

    def _on_start(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._worker = _MicLevelWorker(
            self._qt_device_id,
            self._portaudio_index,
            self,
        )
        self._worker.level.connect(self._on_level)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_stop(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop_safe()
            self._worker.wait(5000)

    def _on_level(self, peak: float, rms: float) -> None:
        bar = math.sqrt(min(1.0, peak))
        self._bar.setValue(min(10_000, int(round(bar * 10_000))))
        self._bar.setFormat(f"{bar * 100:.2f}%")
        self._label.setText(f"峰值: {peak * 100:.2f}%    RMS: {rms * 100:.2f}%")

    def _on_failed(self, msg: str) -> None:
        QMessageBox.warning(self, "麦克风测试失败", msg)
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)

    def _on_worker_finished(self) -> None:
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._worker = None

    def reject(self) -> None:
        self._on_stop()
        super().reject()

    def closeEvent(self, event) -> None:
        self._on_stop()
        super().closeEvent(event)
