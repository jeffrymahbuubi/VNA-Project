# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['e5063a_data_collector.py'],
    pathex=['.', '..', '../../ena_qt6_suite'],
    binaries=[],
    datas=[('mvp/assets', 'mvp/assets')],
    hiddenimports=['ena_dev_paths', 'core.visa_connection', 'core.scpi_commands', 'core.simulator'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='E5063A-Data-Collector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['mvp\\assets\\WTMH.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='E5063A-Data-Collector',
)
