"""Installation-relative defaults shared by the desktop app and CLI modules."""
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SOURCE_DIR.parent
DEFAULT_CONFIG = PROJECT_DIR / 'config' / 'config_v2.yaml'
DEFAULT_OUTPUT = PROJECT_DIR / 'workflow_output'
DEMO_DIR = PROJECT_DIR / 'demo'
