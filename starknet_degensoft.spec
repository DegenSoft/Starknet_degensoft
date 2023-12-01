# -*- mode: python ; coding: utf-8 -*-
import platform

if platform.system() == 'Darwin':
    binaries = [('venv/lib/python3.11/site-packages/libcrypto_c_exports.dylib', '.')]
    datas=[('starknet_degensoft/abi', 'starknet_degensoft/abi')]
else:
    binaries = [('venv\Lib\site-packages\libcrypto_c_exports.dll', '.')]
    datas=[('starknet_degensoft\abi', 'starknet_degensoft\abi')]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='starknet_degensoft',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if platform.system() == 'Darwin':
    app = BUNDLE(
        exe,
        name='starknet_degensoft.app',
        icon='degensoft_icon.icns',
        bundle_identifier=None,
    )
