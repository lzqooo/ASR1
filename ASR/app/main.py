"""应用入口（兼容 ``python -m app.main`` 与 ``from app.main import main``）。"""

from __future__ import annotations

from app.bootstrap import main as _run

__all__ = ["main"]


def main() -> None:
    _run()


if __name__ == "__main__":
    main()
