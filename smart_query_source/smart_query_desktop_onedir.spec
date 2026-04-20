# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[('src\\data', 'data'), ('C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python314\\Lib\\site-packages\\PySide6\\plugins', 'PySide6\\plugins')],
    hiddenimports=[],
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
    name='smart_query_desktop_onedir',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='smart_query_desktop_onedir',
)
