"""
在 CI（Linux）上修补已安装的 PySide6 内 deploy_lib/android/buildozer.py，
在 Qt 依赖 XML 解析出的权限之外，合并本应用所需的网络与麦克风等权限。

若本地为 Windows wheel（无 android 子包），则跳过。
"""
from __future__ import annotations

import pathlib
import re
import sys


MARKER = "# ASR_EXTRA_ANDROID_PERMISSIONS"

# 允许 PySide 小版本间空白差异
_PATCH_RE = re.compile(
    r"""
        (?P<head>[ \t]*permissions\s*=\s*self\.__find_permissions\(\s*pysidedeploy_config\.dependency_files\s*\)\s*\n)
        (?P<mid>[ \t]*permissions\s*=\s*["'],\s*["']\.join\(\s*permissions\s*\)\s*\n)
        (?P<tail>[ \t]*self\.set_value\(\s*["']app["']\s*,\s*["']android\.permissions["']\s*,\s*permissions\s*\))
    """,
    re.VERBOSE,
)


def _injection_block(indent: str) -> str:
    body = f"""{indent}{MARKER}: mic + network for ASR client app
{indent}permissions.update(
{indent}    {{
{indent}        "INTERNET",
{indent}        "RECORD_AUDIO",
{indent}        "MODIFY_AUDIO_SETTINGS",
{indent}        "WAKE_LOCK",
{indent}        "ACCESS_NETWORK_STATE",
{indent}    }}
{indent})
{indent}permissions = ", ".join(sorted(permissions))"""
    return body


def main() -> int:
    try:
        import PySide6
    except ImportError:
        print("PySide6 not installed, skip", file=sys.stderr)
        return 0

    root = pathlib.Path(PySide6.__file__).resolve().parent
    target = root / "scripts" / "deploy_lib" / "android" / "buildozer.py"
    if not target.is_file():
        print(f"No android buildozer module at {target}, skip (expected on Windows wheel)")
        return 0

    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"Already patched: {target}")
        return 0

    m = _PATCH_RE.search(text)
    if not m:
        print(
            f"patch_pyside_android_permissions: permission block not found in {target}; "
            "PySide6 version layout may have changed.",
            file=sys.stderr,
        )
        return 1

    indent = re.match(r"(\s*)", m.group("head")).group(1)
    replacement = m.group("head") + _injection_block(indent) + "\n" + m.group("tail")
    new_text = text[: m.start()] + replacement + text[m.end() :]
    target.write_text(new_text, encoding="utf-8")
    print(f"Patched: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
