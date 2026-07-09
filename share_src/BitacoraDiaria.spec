# -*- mode: python ; coding: utf-8 -*-
import os
import re
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
    VarFileInfo, VarStruct,
)

# Fuente unica: la raiz del repo (un nivel arriba de este .spec), asi no hay
# copias de bitacora_app.py/bitacora.ico que se puedan desincronizar.
ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

# Metadata de version para el .exe: la saca de APP_VERSION en el codigo fuente,
# asi queda sincronizada sola en cada build. Un .exe sin esta info (nombre,
# descripcion, version) se ve mas "anonimo" y suma sospecha en antivirus.
with open(os.path.join(ROOT, 'bitacora_app.py'), encoding='utf-8') as _f:
    _match = re.search(r'APP_VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)"', _f.read())
_partes = tuple(int(p) for p in _match.groups()) if _match else (0, 0, 0)
_version_tuple = _partes + (0,)
_version_str = ".".join(str(p) for p in _partes)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=_version_tuple,
        prodvers=_version_tuple,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable(
                "040904B0",
                [
                    StringStruct("CompanyName", "Datadiscol"),
                    StringStruct("FileDescription", "Bitácora Diaria - registro de actividades"),
                    StringStruct("FileVersion", _version_str),
                    StringStruct("InternalName", "BitacoraDiaria"),
                    StringStruct("OriginalFilename", "BitacoraDiaria.exe"),
                    StringStruct("ProductName", "Bitácora Diaria"),
                    StringStruct("ProductVersion", _version_str),
                ],
            )
        ]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

datas = [(os.path.join(ROOT, 'bitacora.ico'), '.')]
binaries = []
hiddenimports = []
tmp_ret = collect_all('selenium')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('fpdf')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [os.path.join(ROOT, 'bitacora_app.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BitacoraDiaria',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(ROOT, 'bitacora.ico')],
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='BitacoraDiaria',
)
