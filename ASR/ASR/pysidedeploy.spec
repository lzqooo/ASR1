[app]

# 应用标题（会显示在 Android 应用信息中）
title = ASR转写总结

# 项目根目录；留空则使用 input_file 所在目录
project_dir =

# 入口文件（须为项目根下的 main.py）
input_file = main.py

exec_directory =

project_file =

icon =

[python]

python_path =

# 桌面 pyside6-deploy 用；Android 流程会另外安装 buildozer 等
packages = Nuitka==2.7.11

android_packages = buildozer==1.5.0,cython==0.29.33

[qt]

qml_files =

excluded_qml_plugins =

modules =

plugins =

[android]

# 从 Qt 官方页或 qtpip 下载后填写绝对路径，例如：
# wheel_pyside = /path/to/PySide6-6.x.x-cp311-cp311-linux_aarch64.whl
wheel_pyside =

wheel_shiboken =

plugins =

[nuitka]

macos.permissions =

mode = onefile

extra_args = --quiet --noinclude-qt-translations

[buildozer]

# 麦克风与网络等权限由 CI 在部署前修补 PySide 的 buildozer 生成逻辑合并进 buildozer.spec
# （见 scripts/patch_pyside_android_permissions.py）

# debug 生成 .apk；release 生成 .aab
mode = debug

recipe_dir =

jars_dir =

ndk_path =

sdk_path =

local_libs =

# 真机一般为 aarch64；模拟器可能是 x86_64
arch = aarch64
