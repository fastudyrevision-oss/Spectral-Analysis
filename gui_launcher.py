# -*- coding: utf-8 -*-
"""
GUI Launcher - Start the Spectral Analysis Software GUI

Run this script to launch the PyQt6 desktop application.
"""

import sys
import os
import traceback
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Ensure Windows associates the process with our AppUserModelID for taskbar grouping & icon
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "jfdtech.libsspectralanalysis.1.1.1"
        )
    except Exception:
        pass


def _show_fatal_error(error_msg: str) -> None:
    """Display a fatal error message to the user before application exits."""
    # Write to crash log in %APPDATA%/LIBS_Analysis or local directory
    try:
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            crash_dir = Path(appdata) / "LIBS_Analysis"
            crash_dir.mkdir(parents=True, exist_ok=True)
            log_file = crash_dir / "crash.log"
        else:
            log_file = Path("crash.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n--- FATAL ERROR ---\n{error_msg}\n")
    except Exception:
        pass

    # Attempt native Windows MessageBox if GUI is not running
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"Spectral Analysis Software failed to start:\n\n{error_msg[:1000]}\n\nSee crash.log for details.",
                "Spectral Analysis Startup Error",
                0x10 | 0x0  # MB_ICONERROR | MB_OK
            )
            return
        except Exception:
            pass

    print(f"FATAL ERROR:\n{error_msg}", file=sys.stderr)


if __name__ == "__main__":
    try:
        from src.gui.main_window import main
        main()
    except Exception:
        _show_fatal_error(traceback.format_exc())
        sys.exit(1)

