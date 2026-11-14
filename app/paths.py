"""Where the bundled data lives, in a source checkout and in an installed package.

A source checkout keeps it in <repo>/data. The wheel ships the same files inside the
package as app/data (see [tool.hatch.build] in pyproject.toml), so `uvx` installs work too.
"""

from __future__ import annotations

from pathlib import Path

_PACKAGE_DATA = Path(__file__).resolve().parent / "data"
_REPOSITORY_DATA = Path(__file__).resolve().parents[1] / "data"

DATA_DIR = _PACKAGE_DATA if _PACKAGE_DATA.is_dir() else _REPOSITORY_DATA
REFERENCE_DIR = DATA_DIR / "reference"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
SCHEMA_DIR = DATA_DIR / "schemas"
