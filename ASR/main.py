"""项目根目录入口。

pyside6-android-deploy 要求入口脚本文件名为 main.py 且位于项目根目录。
桌面运行：在项目根执行 ``python main.py`` 或继续使用 ``python -m app.main``。
"""

from __future__ import annotations

from app.bootstrap import main

if __name__ == "__main__":
    main()
