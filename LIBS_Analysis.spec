# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for LIBS Spectral Analysis Software
Produces:  dist/LIBS_Analysis/LIBS_Analysis.exe

Build:  pyinstaller LIBS_Analysis.spec --clean

Requires:  PyInstaller >= 6.x, NumPy >= 2.x

Delivery layout
---------------
dist/LIBS_Analysis/
  LIBS_Analysis.exe
  NIST database/            <- sits BESIDE the exe, user-editable
    Neutral lines/          <- user can drop new CSV/XLSX files here
    Ionic lines/
  Processed Data/           <- pure-element reference CSVs for Step 5
                               moved to ProgramData by the ISS installer
                               so users can add/remove files freely
  src/                      <- frozen Python bytecode
  _internal/                <- DLLs: scipy, matplotlib, PyQt6
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import os

# NOTE: block_cipher / cipher removed in PyInstaller 6.x

# ── Collect data files from packages that need assets ───────────────────────
mpl_datas = collect_data_files('matplotlib', include_py_files=False)

a = Analysis(
    ['gui_launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        *mpl_datas,
    ],
    hiddenimports=[
        # scipy
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
        'scipy.optimize',
        'scipy.interpolate',
        'scipy._lib.messagestream',
        # matplotlib Qt6 backend
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_agg',
        # PyQt6
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        # pandas
        'pandas._libs.tslibs.np_datetime',
        'pandas._libs.tslibs.nattype',
        'pandas._libs.tslibs.timedeltas',
        # numpy
        'numpy.lib.format',
        # reportlab (PDF export, optional)
        'reportlab',
        'reportlab.platypus',
        'reportlab.lib',
        'reportlab.lib.styles',
        'reportlab.lib.units',
        'reportlab.lib.colors',
        'reportlab.lib.enums',
        # Windows registry (nist_loader uses this to find ProgramData path)
        'winreg',
        # All src submodules
        *collect_submodules('src'),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Fix AttributeError: module 'pyarrow' has no attribute '__version__'
        'pyarrow',
        # Exclude massive machine learning / deep learning packages
        'torch', 'torchvision', 'torchaudio',
        'transformers', 'tokenizers', 'safetensors', 'sentence_transformers',
        'tensorflow', 'tensorboard', 'keras',
        'onnx', 'onnxruntime',
        'cv2', 'opencv',
        'sklearn', 'scikit_learn',
        'numba', 'llvmlite',
        # Exclude web frameworks & servers
        'django', 'flask', 'starlette', 'fastapi', 'uvicorn', 'streamlit',
        'tornado', 'twisted', 'aiohttp', 'httpx', 'requests_toolbelt',
        # Exclude unused database drivers & ORMs (keep sqlite3 / _sqlite3)
        'sqlalchemy', 'psycopg2', 'psycopg2_binary', 'MySQLdb', 'pymysql',
        'peewee', 'redis', 'pymongo',
        # Exclude automation & browser drivers
        'selenium', 'playwright', 'webdriver_manager', 'pywinauto', 'uiautomation',
        # Exclude development, test, and interactive tools
        'IPython', 'jupyter', 'notebook', 'ipywidgets',
        'google.colab',
        'tkinter', '_tkinter',
        'PyQt5', 'PySide2', 'PySide6',
        '_pytest', 'pytest', 'pytest_cov', 'hypothesis', 'unittest',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LIBS_Analysis',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    # NIST database copied beside the exe so users can freely add/edit files.
    # Uses Tree() so all CSV/XLSX files and subdirectories are included.
    Tree('NIST database', prefix='NIST database'),
    # Processed Data (pure-element reference CSVs for Step 5 validation).
    # Guard: only include if the folder exists (may be absent on a bare CI clone
    # that has not yet populated reference data).
    *([Tree('Processed Data', prefix='Processed Data')]
      if os.path.isdir('Processed Data') else []),
    strip=False,
    upx=False,
    name='LIBS_Analysis',
)
