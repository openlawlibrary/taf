# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

# Include the path to the Python installation directory
python_install_path = os.path.dirname(sys.executable)

a = Analysis(
    ['taf/tools/cli/taf.py'],
    pathex=[python_install_path],
    binaries=[(os.path.join(python_install_path, 'python310.dll'), '.')],
    datas=[('taf/libs', 'taf/libs')],
    hiddenimports=[],
    hookspath=['.'],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='taf',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    onefile=True,  # Ensuring single executable file
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='taf',
)
