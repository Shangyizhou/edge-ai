"""Local metadata locations; no credentials or model artifacts are read here."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOME = Path(os.environ.get('EDGE_AI_STATE_DIR', str(Path.home()/'.local/share/edge-ai/mlflow')))
CATALOG_ROOT = Path(os.environ.get('EDGE_AI_CATALOG_DIR', str(ROOT/'studies/voice-interaction/catalog')))
RELEASE_ROOT = Path(os.environ.get('EDGE_AI_RELEASES_DIR', str(ROOT/'studies/voice-interaction/releases')))
