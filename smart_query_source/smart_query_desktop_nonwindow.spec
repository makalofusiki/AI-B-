# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python314\\Lib\\site-packages\\PySide6\\plugins', 'PySide6/plugins')],
    hiddenimports=['PySide6', 'PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui'],
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
    a.binaries,
    a.datas,
    [],
    name='smart_query_desktop_nonwindow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
