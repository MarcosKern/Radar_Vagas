import os
from pathlib import Path

DATA_HOME = Path(os.environ.get("RADAR_DATA_HOME", Path(__file__).resolve().parents[1]))
