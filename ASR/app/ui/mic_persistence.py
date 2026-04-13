"""麦克风下拉框填充与 QSettings 持久化（Qt / PortAudio 两套）。"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import QComboBox

from app import config
from app.audio.devices import (
    describe_input_device,
    env_audio_input_device,
    list_input_devices,
)


def populate_mic_combo(combo: QComboBox, *, all_hostapis: bool) -> None:
    combo.clear()
    if config.use_portaudio_audio():
        combo.addItem("系统默认", None)
        listed = list_input_devices(all_hostapis=all_hostapis)
        listed_idx = {d.index for d in listed}
        env_i = env_audio_input_device()
        if env_i is not None and env_i not in listed_idx:
            dn = describe_input_device(env_i) or "未知设备"
            combo.addItem(f"[{env_i}] {dn}（.env）", env_i)
        for d in listed:
            combo.addItem(f"[{d.index}] {d.name}", d.index)
        return
    combo.addItem("系统默认输入", None)
    for d in QMediaDevices.audioInputs():
        label = d.description()
        if d.isDefault():
            label += " [默认]"
        combo.addItem(label, QByteArray(bytes(d.id())))


def apply_saved_mic_selection(combo: QComboBox, settings: QSettings) -> None:
    if config.use_portaudio_audio():
        env_i = env_audio_input_device()
        if env_i is not None:
            for i in range(combo.count()):
                if combo.itemData(i) == env_i:
                    combo.setCurrentIndex(i)
                    return
        raw = settings.value("input_device")
        if raw in (None, ""):
            if env_i is None:
                for i in range(combo.count()):
                    if "与系统「默认麦克风」同一端点" in combo.itemText(i):
                        combo.setCurrentIndex(i)
                        return
            combo.setCurrentIndex(0)
            return
        try:
            want = int(raw)
        except (TypeError, ValueError):
            combo.setCurrentIndex(0)
            return
        for i in range(combo.count()):
            if combo.itemData(i) == want:
                combo.setCurrentIndex(i)
                return
        saved_name = settings.value("input_device_name", "")
        if isinstance(saved_name, str) and saved_name.strip():
            for i in range(combo.count()):
                data = combo.itemData(i)
                if data is None:
                    continue
                try:
                    if describe_input_device(int(data)) == saved_name.strip():
                        combo.setCurrentIndex(i)
                        return
                except (TypeError, ValueError):
                    continue
        combo.setCurrentIndex(0)
        return

    env_b = config.env_qt_input_device_id()
    if env_b is not None:
        for i in range(combo.count()):
            data = combo.itemData(i)
            if isinstance(data, QByteArray) and bytes(data) == env_b:
                combo.setCurrentIndex(i)
                return
    qb = settings.value("qt_input_device_id")
    if isinstance(qb, QByteArray) and not qb.isEmpty():
        bid = bytes(qb)
        for i in range(combo.count()):
            data = combo.itemData(i)
            if isinstance(data, QByteArray) and bytes(data) == bid:
                combo.setCurrentIndex(i)
                return
    desc = settings.value("qt_input_description", "")
    if isinstance(desc, str) and desc.strip():
        want = desc.strip()
        for i in range(combo.count()):
            if combo.itemText(i) == want:
                combo.setCurrentIndex(i)
                return
    combo.setCurrentIndex(0)


def save_mic_selection(combo: QComboBox, settings: QSettings) -> None:
    dev = combo.currentData()
    if config.use_portaudio_audio():
        if dev is None:
            settings.remove("input_device")
            settings.remove("input_device_name")
        else:
            di = int(dev)
            settings.setValue("input_device", di)
            name = describe_input_device(di)
            if name:
                settings.setValue("input_device_name", name)
        return
    if dev is None:
        settings.remove("qt_input_device_id")
        settings.remove("qt_input_description")
    else:
        settings.setValue("qt_input_device_id", dev)
        settings.setValue("qt_input_description", combo.currentText())


def selected_portaudio_index(combo: QComboBox) -> int | None:
    data = combo.currentData()
    return int(data) if data is not None else None


def selected_qt_device_id(combo: QComboBox) -> bytes | None:
    data = combo.currentData()
    if data is None:
        return None
    if isinstance(data, QByteArray):
        return bytes(data)
    return None
