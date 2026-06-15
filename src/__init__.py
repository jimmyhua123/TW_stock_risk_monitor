"""Core modules for TW Stock Risk Monitor."""

import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent)

# Keep legacy script-style imports working while modules are migrated to package imports.
if _SRC_DIR not in sys.path:
    sys.path.append(_SRC_DIR)
