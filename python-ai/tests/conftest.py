from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_AI_ROOT = PROJECT_ROOT / "python-ai"

if str(PYTHON_AI_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_AI_ROOT))
