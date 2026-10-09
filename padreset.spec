# -*- mode: python ; coding: utf-8 -*-
# Build: .\build.ps1   (one-file, windowed PadReset.exe in dist\)

import importlib.util
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

ROOT = Path(SPECPATH)
UI = ROOT / "padreset" / "ui"

# Load config.py on its own (importing the package would pull in pywebview).
_spec = importlib.util.spec_from_file_location("padreset_config", ROOT / "padreset" / "config.py")
config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config)

# File properties shown by Explorer (right-click > Properties > Details),
# Task Manager and antivirus tools. Simplified Chinese, Unicode.
_ver = tuple(int(x) for x in config.VERSION.split(".")) + (0,)
_name = f"{config.APP_NAME['zh']} {config.APP_NAME['en']}"
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_ver, prodvers=_ver),
    kids=[
        StringFileInfo([StringTable("080404B0", [
            StringStruct("CompanyName", config.AUTHOR),
            StringStruct("FileDescription", f"{_name} · 打印机废墨计数清零"),
            StringStruct("FileVersion", config.VERSION),
            StringStruct("InternalName", "PadReset"),
            StringStruct("LegalCopyright", f"© 2026 {config.AUTHOR} · EUPL-1.2 · 基于 Ircama 的 epson_print_conf"),
            StringStruct("OriginalFilename", "PadReset.exe"),
            StringStruct("ProductName", _name),
            StringStruct("ProductVersion", config.VERSION),
            StringStruct("Comments", f"{config.DESCRIPTION['zh']} {config.DESCRIPTION['en']} {config.REPO_URL}"),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0804, 1200])]),
    ],
)

datas = [(str(p), "padreset/ui") for p in UI.iterdir() if p.is_file() and p.name != "mock.js"]
datas += [
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "NOTICE.md"), "."),
    (str(ROOT / "third_party" / "epson_print_conf" / "LICENSE"), "third_party/epson_print_conf"),
]

a = Analysis(
    [str(ROOT / "padreset" / "__main__.py")],
    pathex=[str(ROOT), str(ROOT / "third_party" / "epson_print_conf")],
    datas=datas,
    hiddenimports=["epson_print_conf"],
    excludes=["tkinter", "pytest", "black"],  # PIL stays: epson_escp2 imports it at load time
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PadReset",
    icon=str(ROOT / "build" / "padreset.ico"),
    version=version_info,
    console=False,
    upx=False,  # UPX-packed executables trigger more antivirus false positives
    debug=False,
    strip=False,
)
