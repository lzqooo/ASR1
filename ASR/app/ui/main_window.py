"""主窗口：护眼配色、大按钮、录音呼吸动效、总结区 Markdown 分级显示。"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPropertyAnimation,
    QSettings,
    Qt,
)
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.audio.devices import env_list_all_hostapis
from app.services.asr import FunAsrWorker
from app.services.summary import SummaryWorker
from app.ui import mic_persistence as mic_p
from app.ui.appearance import MAIN_STYLESHEET, plain_text_to_summary_html, summary_markdown_to_html
from app.ui.mic_test_dialog import MicTestDialog


class MainWindow(QMainWindow):
    _BTN_PT = 22
    _BTN_H = 72

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("实时转写与总结")
        self.resize(1080, 820)
        self.setStyleSheet(MAIN_STYLESHEET)

        self._settings = QSettings("LocalASR", "FunASR")
        self._asr_thread: FunAsrWorker | None = None
        self._summary_thread: SummaryWorker | None = None
        self._final_lines: list[str] = []
        self._partial: str = ""
        self._summary_markdown: str = ""

        central = QWidget(self)
        central.setObjectName("centralRoot")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(12)

        tool_card = QFrame()
        tool_card.setObjectName("toolCard")
        tc = QVBoxLayout(tool_card)
        tc.setContentsMargins(16, 14, 16, 14)
        tc.setSpacing(10)

        mic_row = QHBoxLayout()
        lbl_mic = QLabel("麦克风")
        lbl_mic.setObjectName("sectionTitle")
        mic_row.addWidget(lbl_mic)
        self._mic_combo = QComboBox()
        self._mic_combo.setMinimumWidth(260)
        self._mic_combo.setToolTip("与系统「设置→声音」默认输入一致（Qt）；可选 PortAudio：.env 设 AUDIO_BACKEND=portaudio")
        self._chk_all_apis = QCheckBox("PortAudio 列出全部接口")
        if not config.use_portaudio_audio():
            self._chk_all_apis.hide()
        elif env_list_all_hostapis():
            self._chk_all_apis.setChecked(True)
            self._chk_all_apis.setEnabled(False)
        else:
            self._chk_all_apis.setChecked(self._settings.value("list_all_hostapis", False, type=bool))
        self._chk_all_apis.toggled.connect(self._on_all_hostapis_toggled)
        mic_p.populate_mic_combo(self._mic_combo, all_hostapis=self._all_hostapis_mode())
        self._mic_combo.blockSignals(True)
        mic_p.apply_saved_mic_selection(self._mic_combo, self._settings)
        self._mic_combo.blockSignals(False)
        self._mic_combo.currentIndexChanged.connect(lambda: mic_p.save_mic_selection(self._mic_combo, self._settings))
        mic_row.addWidget(self._mic_combo, stretch=1)
        self._btn_mic_test = QPushButton("麦克风测试")
        self._btn_mic_test.setObjectName("btnMicTest")
        self._btn_mic_test.clicked.connect(self._on_mic_test)
        mic_row.addWidget(self._btn_mic_test)
        tc.addLayout(mic_row)
        tc.addWidget(self._chk_all_apis)

        lvl_row = QHBoxLayout()
        lbl_lvl = QLabel("输入电平")
        lbl_lvl.setObjectName("sectionTitle")
        lvl_row.addWidget(lbl_lvl)
        self._level_bar = QProgressBar()
        self._level_bar.setRange(0, 10_000)
        self._level_bar.setFormat("—")
        self._level_bar.setTextVisible(True)
        self._level_bar.setFixedHeight(22)
        lvl_row.addWidget(self._level_bar, stretch=1)
        self._level_lbl = QLabel("未录音")
        self._level_lbl.setObjectName("hint")
        self._level_lbl.setMinimumWidth(120)
        lvl_row.addWidget(self._level_lbl)
        tc.addLayout(lvl_row)

        self._btn_record = QPushButton("开始录音")
        self._btn_record.setObjectName("btnRecord")
        self._btn_pause = QPushButton("暂停")
        self._btn_pause.setObjectName("btnSecondary")
        self._btn_resume = QPushButton("继续")
        self._btn_resume.setObjectName("btnSecondary")
        self._btn_summary = QPushButton("生成总结")
        self._btn_summary.setObjectName("btnAccent")
        self._btn_exp_tr = QPushButton("导出转录")
        self._btn_exp_tr.setObjectName("btnSecondary")
        self._btn_exp_sum = QPushButton("导出总结")
        self._btn_exp_sum.setObjectName("btnSecondary")
        for b in (
            self._btn_record,
            self._btn_pause,
            self._btn_resume,
            self._btn_summary,
            self._btn_exp_tr,
            self._btn_exp_sum,
        ):
            self._make_big(b)
        self._btn_pause.setEnabled(False)
        self._btn_resume.setEnabled(False)

        tc.addWidget(self._btn_record)
        row_pr = QHBoxLayout()
        row_pr.setSpacing(10)
        row_pr.addWidget(self._btn_pause)
        row_pr.addWidget(self._btn_resume)
        tc.addLayout(row_pr)
        tc.addWidget(self._btn_summary)
        row_ex = QHBoxLayout()
        row_ex.setSpacing(10)
        row_ex.addWidget(self._btn_exp_tr)
        row_ex.addWidget(self._btn_exp_sum)
        tc.addLayout(row_ex)

        self._btn_record.clicked.connect(self._on_record_toggle)
        self._btn_pause.clicked.connect(self._on_pause)
        self._btn_resume.clicked.connect(self._on_resume)
        self._btn_summary.clicked.connect(self._on_summarize)
        self._btn_exp_tr.clicked.connect(self._on_export_transcript)
        self._btn_exp_sum.clicked.connect(self._on_export_summary)

        root.addWidget(tool_card)

        editor_card = QFrame()
        editor_card.setObjectName("editorCard")
        ec = QVBoxLayout(editor_card)
        ec.setContentsMargins(12, 12, 12, 12)
        ec.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        tw = QWidget()
        tl = QVBoxLayout(tw)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)
        lt = QLabel("转写")
        lt.setObjectName("sectionTitle")
        tl.addWidget(lt)
        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText("开始录音后显示…")
        tl.addWidget(self.transcript)
        splitter.addWidget(tw)
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(6)
        ls = QLabel("总结")
        ls.setObjectName("sectionTitle")
        sl.addWidget(ls)
        self._summary_busy = QProgressBar()
        self._summary_busy.setObjectName("summaryBusy")
        self._summary_busy.setRange(0, 100)
        self._summary_busy.setValue(0)
        self._summary_busy.setMaximumHeight(8)
        self._summary_busy.setTextVisible(False)
        self._summary_busy.hide()
        sl.addWidget(self._summary_busy)
        self.summary = QTextBrowser()
        self.summary.setReadOnly(True)
        self.summary.setOpenExternalLinks(True)
        self.summary.setPlaceholderText("生成总结后显示…")
        sl.addWidget(self.summary)
        splitter.addWidget(sw)
        splitter.setSizes([380, 320])
        ec.addWidget(splitter)
        root.addWidget(editor_card, stretch=1)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("就绪")

        self._record_opacity = QGraphicsOpacityEffect(self._btn_record)
        self._record_opacity.setOpacity(1.0)
        self._btn_record.setGraphicsEffect(self._record_opacity)
        self._record_breathe = QPropertyAnimation(self._record_opacity, b"opacity", self)
        self._record_breathe.setDuration(2400)
        self._record_breathe.setStartValue(1.0)
        self._record_breathe.setEndValue(0.88)
        self._record_breathe.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._record_breathe.setLoopCount(-1)

        self._sync_record_style()

    def _make_big(self, btn: QPushButton) -> None:
        f = QFont(self.font())
        f.setPointSize(self._BTN_PT)
        f.setBold(True)
        btn.setFont(f)
        btn.setMinimumHeight(self._BTN_H)

    def _sync_record_style(self) -> None:
        self._btn_record.setProperty("recording", self._recording())
        self._btn_record.style().unpolish(self._btn_record)
        self._btn_record.style().polish(self._btn_record)

    def _start_record_breathe(self) -> None:
        if self._record_breathe.state() == QAbstractAnimation.State.Running:
            return
        self._record_opacity.setOpacity(1.0)
        self._record_breathe.start()

    def _stop_record_breathe(self) -> None:
        self._record_breathe.stop()
        self._record_opacity.setOpacity(1.0)

    def _on_asr_connected(self) -> None:
        self._status_bar.showMessage("录音中")
        self._start_record_breathe()

    def _all_hostapis_mode(self) -> bool:
        return env_list_all_hostapis() or self._chk_all_apis.isChecked()

    def _on_all_hostapis_toggled(self, _c: bool) -> None:
        if not env_list_all_hostapis():
            self._settings.setValue("list_all_hostapis", self._chk_all_apis.isChecked())
        self._mic_combo.blockSignals(True)
        mic_p.populate_mic_combo(self._mic_combo, all_hostapis=self._all_hostapis_mode())
        mic_p.apply_saved_mic_selection(self._mic_combo, self._settings)
        self._mic_combo.blockSignals(False)

    def _recording(self) -> bool:
        return self._asr_thread is not None and self._asr_thread.isRunning()

    def _refresh_transport_ui(self) -> None:
        run = self._recording()
        self._btn_record.setText("结束录音" if run else "开始录音")
        if run and self._asr_thread is not None:
            p = self._asr_thread.is_paused()
            self._btn_pause.setEnabled(not p)
            self._btn_resume.setEnabled(p)
        else:
            self._btn_pause.setEnabled(False)
            self._btn_resume.setEnabled(False)
        self._sync_record_style()

    def _reset_level_ui(self) -> None:
        self._level_bar.setValue(0)
        self._level_bar.setFormat("—")
        self._level_lbl.setText("未录音")

    def _on_input_level(self, peak: float, _rms: float) -> None:
        b = math.sqrt(min(1.0, peak))
        self._level_bar.setValue(min(10_000, int(round(b * 10_000))))
        self._level_bar.setFormat(f"{b * 100:.1f}%")
        self._level_lbl.setText(f"峰值 {peak * 100:.1f}%")

    def _on_mic_test(self) -> None:
        if self._recording():
            QMessageBox.information(self, "提示", "请先结束录音再测试麦克风。")
            return
        if config.use_portaudio_audio():
            MicTestDialog(self, portaudio_index=mic_p.selected_portaudio_index(self._mic_combo)).exec()
        else:
            MicTestDialog(self, qt_device_id=mic_p.selected_qt_device_id(self._mic_combo)).exec()

    def _render_transcript(self) -> None:
        parts: list[str] = []
        if self._final_lines:
            parts.append("\n".join(self._final_lines))
        if self._partial:
            parts.append(self._partial)
        self.transcript.setPlainText("\n".join(parts))
        self.transcript.moveCursor(QTextCursor.MoveOperation.End)

    def _on_record_toggle(self) -> None:
        if self._recording():
            self._status_bar.showMessage("正在停止…")
            self._asr_thread.request_stop()
            return
        self._final_lines.clear()
        self._partial = ""
        self._render_transcript()
        self._mic_combo.setEnabled(False)
        self._btn_mic_test.setEnabled(False)
        if config.use_portaudio_audio() and not env_list_all_hostapis():
            self._chk_all_apis.setEnabled(False)
        self._status_bar.showMessage("连接识别服务…")

        if config.use_portaudio_audio():
            self._asr_thread = FunAsrWorker(self, portaudio_index=mic_p.selected_portaudio_index(self._mic_combo))
        else:
            self._asr_thread = FunAsrWorker(self, qt_device_id=mic_p.selected_qt_device_id(self._mic_combo))
        w = self._asr_thread
        w.connected.connect(self._on_asr_connected)
        w.partial_text.connect(self._on_partial)
        w.sentence_final.connect(self._on_sentence)
        w.failed.connect(self._on_asr_failed)
        w.finished_clean.connect(self._on_asr_finished)
        w.level.connect(self._on_input_level)
        w.started.connect(self._refresh_transport_ui)
        w.start()
        self._refresh_transport_ui()

    def _on_pause(self) -> None:
        if self._asr_thread and self._asr_thread.isRunning():
            self._asr_thread.request_pause()
            self._status_bar.showMessage("已暂停")
            self._refresh_transport_ui()

    def _on_resume(self) -> None:
        if self._asr_thread and self._asr_thread.isRunning():
            self._asr_thread.request_resume()
            self._status_bar.showMessage("录音中")
            self._refresh_transport_ui()

    def _on_partial(self, text: str) -> None:
        self._partial = text
        self._render_transcript()

    def _on_sentence(self, text: str) -> None:
        line = text.strip()
        if line:
            self._final_lines.append(line)
        self._partial = ""
        self._render_transcript()

    def _on_asr_failed(self, msg: str) -> None:
        self._status_bar.showMessage("错误")
        self._stop_record_breathe()
        QMessageBox.warning(self, "语音识别", msg)

    def _on_asr_finished(self) -> None:
        self._mic_combo.setEnabled(True)
        self._btn_mic_test.setEnabled(True)
        if config.use_portaudio_audio() and not env_list_all_hostapis():
            self._chk_all_apis.setEnabled(True)
        self._reset_level_ui()
        self._stop_record_breathe()
        self._refresh_transport_ui()
        if not self._status_bar.currentMessage().startswith("错误"):
            self._status_bar.showMessage("就绪")

    def _on_summarize(self) -> None:
        body = self.transcript.toPlainText().strip()
        if not body:
            QMessageBox.information(self, "总结", "没有转写内容。")
            return
        if self._summary_thread and self._summary_thread.isRunning():
            return
        self._btn_summary.setEnabled(False)
        self._status_bar.showMessage("生成总结…")
        self._summary_busy.setRange(0, 0)
        self._summary_busy.show()
        self._summary_thread = SummaryWorker(body, self)
        self._summary_thread.done.connect(self._on_summary_done)
        self._summary_thread.error.connect(self._on_summary_error)
        self._summary_thread.finished.connect(self._on_summary_thread_finished)
        self._summary_thread.start()

    def _on_summary_thread_finished(self) -> None:
        self._btn_summary.setEnabled(True)
        self._summary_busy.setRange(0, 100)
        self._summary_busy.setValue(0)
        self._summary_busy.hide()

    def _on_summary_done(self, text: str) -> None:
        self._summary_markdown = text.strip()
        html_out = summary_markdown_to_html(self._summary_markdown)
        if not html_out.strip():
            html_out = plain_text_to_summary_html(self._summary_markdown)
        self.summary.setHtml(html_out)
        self._status_bar.showMessage("就绪")

    def _on_summary_error(self, msg: str) -> None:
        QMessageBox.warning(self, "总结失败", msg)
        self._status_bar.showMessage("就绪")

    def _on_export_transcript(self) -> None:
        text = self.transcript.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "导出", "转写为空。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出转录", str(Path.home() / "转录.txt"), "文本 (*.txt);;所有文件 (*.*)"
        )
        if path:
            try:
                Path(path).write_text(text + "\n", encoding="utf-8")
                self._status_bar.showMessage(f"已导出转录：{path}")
            except OSError as e:
                QMessageBox.warning(self, "导出失败", str(e))

    def _on_export_summary(self) -> None:
        text = (self._summary_markdown or "").strip()
        if not text:
            text = self.summary.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "导出", "总结为空。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出总结", str(Path.home() / "总结.md"), "Markdown (*.md);;文本 (*.txt);;所有文件 (*.*)"
        )
        if path:
            try:
                Path(path).write_text(text + "\n", encoding="utf-8")
                self._status_bar.showMessage(f"已导出总结：{path}")
            except OSError as e:
                QMessageBox.warning(self, "导出失败", str(e))

    def closeEvent(self, event) -> None:
        if self._asr_thread and self._asr_thread.isRunning():
            self._asr_thread.request_stop()
            self._asr_thread.wait(8000)
        super().closeEvent(event)
