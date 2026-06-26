# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for LIBS Spectral Analysis Software
Produces a single-folder distribution under dist/LIBS_Analysis/
Run:  pyinstaller LIBS_Analysis.spec
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── Collect scipy, matplotlib, and PyQt6 data that PyInstaller may miss ──────
scipy_datas   = collect_data_files('scipy', includes=['**/*.pyd', '**/*.dll'])
mpl_datas     = collect_data_files('matplotlib')
pyqt6_datas   = collect_data_files('PyQt6')

a = Analysis(
    ['gui_launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Application source package
        ('src', 'src'),
        # NIST database CSVs bundled with the app
        ('data', 'data'),
        # Note: 'NIST database' folder — path with space handled explicitly
        (str(Path('NIST database').resolve()), 'NIST database'),
        # Matplotlib / scipy data
        *scipy_datas,
        *mpl_datas,
        *pyqt6_datas,
    ],
    hiddenimports=[
        # scipy sparse solvers used by ALS
        'scipy.sparse',
        'scipy.sparse.linalg',
        'scipy.sparse._csr',
        'scipy.sparse._csc',
        'scipy.sparse._coo',
        'scipy.linalg',
        'scipy.linalg.blas',
        'scipy.linalg.lapack',
        'scipy.signal',
        'scipy.signal._peak_finding',
        'scipy._lib.messagestream',
        # matplotlib backends
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_agg',
        'matplotlib.backends.backend_qt5agg',
        # PyQt6 modules
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        # pandas / numpy
        'pandas._libs.tslibs.np_datetime',
        'pandas._libs.tslibs.nattype',
        'pandas._libs.tslibs.timedeltas',
        'numpy.core._methods',
        'numpy.lib.format',
        # reportlab (PDF export — optional)
        'reportlab',
        'reportlab.platypus',
        'reportlab.lib',
        'reportlab.lib.styles',
        'reportlab.lib.units',
        'reportlab.lib.colors',
        'reportlab.lib.enums',
        # application submodules
        *collect_submodules('src'),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', '_tkinter',
        'IPython', 'jupyter', 'notebook',
        'test', 'tests',
        'google.colab',
    ],
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
    name='LIBS_Analysis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX can cause false-positive AV alerts
    console=False,              # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                  # Add .ico path here if you have an icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='LIBS_Analysis',
)
