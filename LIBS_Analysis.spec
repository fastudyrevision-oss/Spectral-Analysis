# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for LIBS Spectral Analysis Software
Produces:  dist/LIBS_Analysis/LIBS_Analysis.exe  (plus all required DLLs)

Build:  pyinstaller LIBS_Analysis.spec --clean
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── Collect data files from heavy packages ────────────────────────────────────
scipy_datas   = collect_data_files('scipy')
mpl_datas     = collect_data_files('matplotlib')
pyqt6_datas   = collect_data_files('PyQt6')

a = Analysis(
    ['gui_launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Application source tree
        ('src', 'src'),
        # NIST database CSVs (lives under data/)
        ('data', 'data'),
        # Heavy library data
        *scipy_datas,
        *mpl_datas,
        *pyqt6_datas,
    ],
    hiddenimports=[
        # scipy sparse / signal
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
        # matplotlib Qt6 backend
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_agg',
        # PyQt6
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        # pandas internals
        'pandas._libs.tslibs.np_datetime',
        'pandas._libs.tslibs.nattype',
        'pandas._libs.tslibs.timedeltas',
        # numpy
        'numpy.core._methods',
        'numpy.lib.format',
        # reportlab (PDF export — optional, gracefully absent at runtime)
        'reportlab',
        'reportlab.platypus',
        'reportlab.lib',
        'reportlab.lib.styles',
        'reportlab.lib.units',
        'reportlab.lib.colors',
        'reportlab.lib.enums',
        # all src submodules
        *collect_submodules('src'),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', '_tkinter',
        'IPython', 'jupyter', 'notebook',
        'google.colab',
        '_pytest', 'pytest',
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # folder-mode build (smaller, faster startup)
    name='LIBS_Analysis',
    debug=False,
    strip=False,
    upx=False,                  # skip UPX to avoid AV false-positives
    console=False,              # no console window
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='LIBS_Analysis',
)
