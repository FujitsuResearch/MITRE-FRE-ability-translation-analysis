"""Test bootstrap: allow `pytest` from the repo root without installing the
package, by putting the src/ layout on sys.path."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
