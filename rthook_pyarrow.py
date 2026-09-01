# -*- coding: utf-8 -*-
"""
PyInstaller Runtime Hook - PyArrow compatibility guard.

Ensures that if pyarrow is excluded from the build, sys.modules does not
contain a partial/poisoned entry that could trigger AttributeError in
libraries checking 'if "pyarrow" in sys.modules'.
"""

import sys

# Ensure any partially-initialized pyarrow reference is removed
if "pyarrow" in sys.modules and sys.modules["pyarrow"] is None:
    del sys.modules["pyarrow"]

