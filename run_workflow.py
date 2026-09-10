"""Command-line entry point; use Start_Oberflaeche.cmd for the desktop interface."""
from pathlib import Path
import runpy
import sys

if __name__ == '__main__':
    source = Path(__file__).resolve().parent / 'src'
    sys.path.insert(0, str(source))
    runpy.run_path(str(source / '00_WORKFLOW_RUNNER.py'), run_name='__main__')
