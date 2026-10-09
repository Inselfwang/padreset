"""Load the vendored, unmodified epson_print_conf module.

In a source checkout it lives in third_party/epson_print_conf; in the
PyInstaller build it is bundled as a top-level module.
"""

import sys
import warnings
from pathlib import Path

# pysnmp emits SyntaxWarnings on import (upstream suppresses them too).
warnings.filterwarnings("ignore", category=SyntaxWarning)

_VENDORED = Path(__file__).resolve().parent.parent / "third_party" / "epson_print_conf"
if _VENDORED.is_dir() and str(_VENDORED) not in sys.path:
    sys.path.insert(0, str(_VENDORED))

import epson_print_conf as epc  # noqa: E402

__all__ = ["epc"]
