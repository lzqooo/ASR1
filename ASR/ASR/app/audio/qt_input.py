"""
麦克风采集：Qt Multimedia（QAudioSource）。

与腾讯会议、企业微信、Teams 等桌面端类似：走 Qt 在 Windows 上的原生后端（WMF/WASAPI），
设备列表与「系统设置 → 声音」中的输入设备一致，而不是 PortAudio 的 MME/WASAPI 多份枚举。
"""

from __future__ import annotations

import time

import numpy as np
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSource, QMediaDevices

from app import config
from app.audio import devices as audio_dev
from app.audio.pcm_source import SAMPLE_RATE


def _bytes_per_sample(sf: QAudioFormat.SampleFormat) -> int:
    if sf == QAudioFormat.SampleFormat.Int16:
        return 2
    if sf == QAudioFormat.SampleFormat.Int32:
        return 4
    if sf == QAudioFormat.SampleFormat.Float:
        return 4
    return 2


def resolve_qt_input_device(device_id: bytes | None):
    """device_id 为 None 时使用系统默认输入（与会议软件默认麦克风一致）。"""
    if device_id is None:
        return QMediaDevices.defaultAudioInput()
    for d in QMediaDevices.audioInputs():
        if bytes(d.id()) == device_id:
            return d
    return QMediaDevices.defaultAudioInput()


class QtPcmMicReader:
    """16 kHz 单声道 int16 PCM，供 Fun-ASR；内部按设备实际格式读取并重采样。"""

    def __init__(self, device_id: bytes | None, frames_16k: int) -> None:
        self._device_id = device_id
        self.frames_16k = max(1, int(frames_16k))
        self._source: QAudioSource | None = None
        self._io = None
        self._fmt: QAudioFormat | None = None

    def start(self) -> None:
        dev = resolve_qt_input_device(self._device_id)
        fmt = QAudioFormat()
        fmt.setSampleRate(SAMPLE_RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not dev.isFormatSupported(fmt):
            fmt = dev.preferredFormat()
            fmt.setChannelCount(1)
        self._source = QAudioSource(dev, fmt)
        self._io = self._source.start()
        self._fmt = fmt
        if self._io is None:
            err = self._source.error()
            try:
                self._source.stop()
            except Exception:
                pass
            self._source = None
            raise RuntimeError(f"QAudioSource 未能打开麦克风 IO: {err}") from None
        # PySide6 下 error() 返回的枚举与 QAudio.Error.NoError 可能非同一实例，用 value 比较
        qerr = self._source.error()
        if qerr.value != QAudio.Error.NoError.value:
            self.close()
            raise RuntimeError(f"麦克风打开失败: {qerr}") from None

    def read_pcm16_mono(self) -> tuple[bytes, float, float]:
        if not self._io or not self._fmt:
            raise RuntimeError("麦克风未启动")
        fmt = self._fmt
        ch = fmt.channelCount()
        sr = fmt.sampleRate()
        sf = fmt.sampleFormat()
        bps = _bytes_per_sample(sf)
        frames_src = max(1, int(round(self.frames_16k * sr / SAMPLE_RATE)))
        nbytes = frames_src * ch * bps
        deadline = time.monotonic() + 1.0
        while self._io.bytesAvailable() < nbytes:
            time.sleep(0.002)
            if time.monotonic() > deadline:
                raise TimeoutError("读取麦克风超时（请检查是否被其它应用独占）")
        raw = bytes(self._io.read(nbytes))
        if len(raw) < nbytes:
            raw = raw + b"\x00" * (nbytes - len(raw))

        if sf == QAudioFormat.SampleFormat.Int16:
            arr = np.frombuffer(raw, dtype=np.int16).reshape(-1, ch)
            mono = audio_dev._to_int16_mono(arr)
        elif sf == QAudioFormat.SampleFormat.Float:
            arr = np.frombuffer(raw, dtype=np.float32).reshape(-1, ch)
            mono = audio_dev._to_int16_mono(arr)
        elif sf == QAudioFormat.SampleFormat.Int32:
            f = np.frombuffer(raw, dtype=np.int32).reshape(-1, ch).astype(np.float64)
            f = f / 2147483648.0
            mono = audio_dev._to_int16_mono(f)
        else:
            arr = np.frombuffer(raw, dtype=np.int16).reshape(-1, ch)
            mono = audio_dev._to_int16_mono(arr)
        gain = config.audio_input_gain()
        if abs(gain - 1.0) > 1e-9:
            mono = np.clip(
                np.round(mono.astype(np.float64) * gain),
                -32768,
                32767,
            ).astype(np.int16)
        peak, rms = audio_dev.peak_rms_int16(mono)
        out = audio_dev.resample_int16_mono(mono, sr, SAMPLE_RATE, self.frames_16k)
        return out.tobytes(), peak, rms

    def close(self) -> None:
        if self._source is not None:
            try:
                self._source.stop()
            except Exception:
                pass
            self._source = None
            self._io = None
            self._fmt = None
