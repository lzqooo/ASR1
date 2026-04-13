"""Microphone enumeration and PortAudio stream open with 16 kHz mono fallbacks."""

from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

from app import config
from app.audio.pcm_source import DTYPE, SAMPLE_RATE


@dataclass(frozen=True)
class InputDeviceInfo:
    index: int
    name: str
    max_input_channels: int


def _normalize_dedupe_key(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _short_hostapi_label(hostapi_name: str) -> str:
    h = (hostapi_name or "").lower()
    if "wasapi" in h:
        return "WASAPI"
    if "mme" in h:
        return "MME"
    if "directsound" in h or "dsound" in h:
        return "DirectSound"
    return (hostapi_name or "?")[:20]


def env_list_all_hostapis() -> bool:
    return os.environ.get("AUDIO_LIST_ALL_HOSTAPIS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _wasapi_hostapi_indices() -> set[int]:
    try:
        hostapis = sd.query_hostapis()
    except Exception:
        return set()
    return {i for i, h in enumerate(hostapis) if "wasapi" in h["name"].lower()}


def _device_pick_score(
    index: int, hostapi_name: str, default_in: int | None
) -> tuple[int, int]:
    """Lower tuple = higher priority. Prefer default input, then WASAPI."""
    if default_in is not None and index == default_in:
        tier = 0
    elif "wasapi" in hostapi_name.lower():
        tier = 1
    else:
        tier = 2
    return (tier, index)


def list_input_devices(*, all_hostapis: bool = False) -> list[InputDeviceInfo]:
    """列出输入设备。

    - ``all_hostapis=True``：列出全部主机 API（含 MME / DirectSound / WASAPI），
      名称后附接口类型。USB 摄像头等设备常在 WASAPI 下电平极低，换 **MME** 可正常。
    - 默认（Windows）：仅 WASAPI 并合并同名；若 **系统默认麦克风** 所用端点不在其中
      （多为 MME），则额外插入一条，避免与系统设置里「能测到声」的设备不一致。
    """
    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception:
        return []

    default_in = default_input_device_index()
    is_win = platform.system() == "Windows"
    wasapi_ha = _wasapi_hostapi_indices()

    rows: list[tuple[int, dict, str]] = []
    for i, d in enumerate(devices):
        mic = int(d.get("max_input_channels") or 0)
        if mic < 1:
            continue
        hidx = int(d["hostapi"])
        hname = hostapis[hidx]["name"] if 0 <= hidx < len(hostapis) else ""
        rows.append((i, d, hname))

    if all_hostapis:
        out: list[InputDeviceInfo] = []
        for idx, d, hname in rows:
            base = str(d.get("name") or f"device-{idx}")
            tag = _short_hostapi_label(hname)
            label = f"{base} ({tag})"
            mic = int(d.get("max_input_channels") or 0)
            out.append(InputDeviceInfo(index=idx, name=label, max_input_channels=mic))
        out.sort(key=lambda x: (x.name.lower(), x.index))
        return out

    if is_win and wasapi_ha:
        filtered = [r for r in rows if int(r[1]["hostapi"]) in wasapi_ha]
        if not filtered:
            filtered = rows
    else:
        filtered = rows

    best: dict[str, tuple[tuple[int, int], int, str, int]] = {}
    for idx, d, hname in filtered:
        name = str(d.get("name") or f"device-{idx}")
        key = _normalize_dedupe_key(name)
        mic = int(d.get("max_input_channels") or 0)
        sc = _device_pick_score(idx, hname, default_in)
        if key not in best or sc < best[key][0]:
            best[key] = (sc, idx, name, mic)

    out = [
        InputDeviceInfo(index=idx, name=name, max_input_channels=mic)
        for _sc, idx, name, mic in sorted(best.values(), key=lambda t: (t[2].lower(), t[1]))
    ]

    listed_idx = {x.index for x in out}
    if default_in is not None and default_in not in listed_idx:
        try:
            d = sd.query_devices(default_in, "input")
            hidx = int(d["hostapi"])
            hname = hostapis[hidx]["name"] if 0 <= hidx < len(hostapis) else ""
            tag = _short_hostapi_label(hname)
            base = str(d.get("name") or f"device-{default_in}")
            label = f"{base}（{tag}，与系统「默认麦克风」同一端点）"
            mic = int(d.get("max_input_channels") or 0)
            out.insert(
                0,
                InputDeviceInfo(index=default_in, name=label, max_input_channels=mic),
            )
        except Exception:
            pass

    return out


def default_input_device_index() -> int | None:
    try:
        inp, _ = sd.default.device
        if inp is None or int(inp) < 0:
            return None
        return int(inp)
    except Exception:
        return None


def _resolve_device_id(device: int | None) -> int | None:
    if device is not None:
        return device
    return default_input_device_index()


def wasapi_shared_extra_settings(device: int | None):
    """Use shared-mode WASAPI to reduce 'device in use' errors on Windows."""
    if platform.system() != "Windows" or not hasattr(sd, "WasapiSettings"):
        return None
    dev = _resolve_device_id(device)
    try:
        if dev is None:
            d = sd.query_devices(kind="input")
        else:
            d = sd.query_devices(dev, "input")
        hidx = int(d["hostapi"])
        hostapis = sd.query_hostapis()
        if not (0 <= hidx < len(hostapis)):
            return None
        if "wasapi" in hostapis[hidx]["name"].lower():
            return sd.WasapiSettings(exclusive=False, auto_convert=True)
    except Exception:
        pass
    return None


def _pick_mono_from_capture(arr: np.ndarray) -> np.ndarray:
    """多声道：选能量最大的声道（耳麦常见仅一路有麦克风）。"""
    a = np.asarray(arr)
    if a.ndim == 2 and a.shape[1] > 1:
        best_k = 0
        best_e = -1.0
        for k in range(a.shape[1]):
            ck = a[:, k].astype(np.float64, copy=False)
            e = float(np.dot(ck, ck))
            if e > best_e:
                best_e = e
                best_k = k
        a = a[:, best_k]
    elif a.ndim == 2:
        a = a[:, 0]
    return a.reshape(-1)


def _to_int16_mono(arr: np.ndarray) -> np.ndarray:
    mono = _pick_mono_from_capture(arr)
    if mono.dtype == np.float32 or mono.dtype == np.float64:
        x = mono.astype(np.float64)
        mx = float(np.max(np.abs(x))) if x.size else 0.0
        # 少数驱动把 16-bit 幅度放在 float 里（数值远大于 1）
        if mx > 1.5:
            y = np.clip(x / 32768.0, -1.0, 1.0) * 32767.0
        else:
            y = np.clip(x, -1.0, 1.0) * 32767.0
        return np.clip(np.round(y), -32768, 32767).astype(np.int16)
    return mono.astype(np.int16, copy=False)


def resample_int16_mono(samples: np.ndarray, src_sr: int, dst_sr: int, dst_len: int) -> np.ndarray:
    if src_sr <= 0 or dst_sr <= 0:
        return np.zeros(dst_len, dtype=np.int16)
    s = _to_int16_mono(samples)
    if len(s) == dst_len and src_sr == dst_sr:
        return s
    if len(s) <= 1:
        return np.zeros(dst_len, dtype=np.int16)
    x_new = np.linspace(0.0, float(len(s) - 1), num=dst_len)
    xp = np.arange(len(s), dtype=np.float64)
    y = np.interp(x_new, xp, s.astype(np.float64))
    return np.clip(np.round(y), -32768, 32767).astype(np.int16)


def peak_rms_int16(mono_i16: np.ndarray) -> tuple[float, float]:
    if mono_i16.size == 0:
        return 0.0, 0.0
    x = mono_i16.astype(np.float64)
    peak = float(np.max(np.abs(x))) / 32768.0
    rms = float(np.sqrt(np.mean(x * x))) / 32768.0
    return peak, rms


class PcmMicReader:
    """Opens an input stream and yields 16 kHz mono int16 PCM chunks for ASR."""

    def __init__(self, device: int | None, frames_16k: int) -> None:
        self.device = device
        self.frames_16k = max(1, int(frames_16k))
        self._stream: sd.RawInputStream | None = None
        self._read_frames = self.frames_16k
        self._src_sr = SAMPLE_RATE
        self._dtype: str = DTYPE

    def start(self) -> None:
        last: Exception | None = None

        def _sr_order(sr: int) -> list[tuple[int, str]]:
            # WASAPI 常见：原生采样率 + float 更可靠；立体声先打开再选大声道
            return [(2, "float32"), (1, "float32"), (2, DTYPE), (1, DTYPE)]

        candidates: list[tuple[int, int, str]] = []
        dev_idx: int | None = self.device
        if dev_idx is None:
            dev_idx = default_input_device_index()
        native_sr: int | None = None
        try:
            info = sd.query_devices(dev_idx, "input") if dev_idx is not None else sd.query_devices(kind="input")
            native_sr = int(float(info["default_samplerate"]))
        except Exception:
            pass
        # 先原生采样率再 16 kHz，避免部分驱动在强制 16 kHz 时“能打开但全静音”
        if native_sr and native_sr > 0:
            for ch, dt in _sr_order(native_sr):
                candidates.append((native_sr, ch, dt))
        for ch, dt in _sr_order(SAMPLE_RATE):
            candidates.append((SAMPLE_RATE, ch, dt))

        wasapi_extra = wasapi_shared_extra_settings(self.device)
        extra_passes: list[object | None] = []
        if wasapi_extra is not None:
            extra_passes.append(wasapi_extra)
            try:
                extra_passes.append(
                    sd.WasapiSettings(exclusive=False, auto_convert=False)
                )
            except Exception:
                pass
        extra_passes.append(None)

        for extra in extra_passes:
            for latency in ("high", "default"):
                for sr, ch, dtype in candidates:
                    read_sz = max(1, int(round(self.frames_16k * sr / SAMPLE_RATE)))
                    for blocksize in (read_sz, 0):
                        try:
                            kw: dict = dict(
                                device=self.device,
                                samplerate=sr,
                                channels=ch,
                                dtype=dtype,
                                blocksize=blocksize,
                                latency=latency,
                            )
                            if extra is not None:
                                kw["extra_settings"] = extra
                            stream = sd.RawInputStream(**kw)
                            stream.start()
                            self._stream = stream
                            self._read_frames = read_sz
                            self._src_sr = sr
                            self._dtype = dtype
                            return
                        except Exception as e:
                            last = e
                            continue
        raise RuntimeError(
            "无法打开麦克风（已尝试 WASAPI 共享模式、多种采样率/声道/延迟）。"
            "请关闭占用麦克风的其它应用，并在系统设置中允许桌面应用访问麦克风。"
            f" 详情: {last}"
        ) from last

    def read_pcm16_mono(self) -> tuple[bytes, float, float]:
        if not self._stream:
            raise RuntimeError("麦克风未启动")
        data, _overflowed = self._stream.read(self._read_frames)
        arr = np.asarray(data)
        mono = _to_int16_mono(arr)
        gain = config.audio_input_gain()
        if abs(gain - 1.0) > 1e-9:
            mono = np.clip(
                np.round(mono.astype(np.float64) * gain),
                -32768,
                32767,
            ).astype(np.int16)
        peak, rms = peak_rms_int16(mono)
        out = resample_int16_mono(mono, self._src_sr, SAMPLE_RATE, self.frames_16k)
        return out.tobytes(), peak, rms

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None


def env_audio_input_device() -> int | None:
    raw = os.environ.get("AUDIO_INPUT_DEVICE", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def describe_input_device(device_id: int) -> str | None:
    try:
        d = sd.query_devices(device_id, "input")
        return str(d.get("name") or "")
    except Exception:
        return None
