"""Synthetic subprocess trees for lifecycle tests; never launches a model."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from runtime_support import atomic_json

mode, directory = sys.argv[1], Path(sys.argv[2])
if mode == 'leaf':
    atomic_json(directory/'leaf.json', {'pid':os.getpid()})
    time.sleep(120)
elif mode in ('tree', 'orphan'):
    child=subprocess.Popen([sys.executable,__file__,'leaf',str(directory)])
    atomic_json(directory/'tree.json', {'pid':os.getpid()})
    deadline=time.monotonic()+10
    while not (directory/'leaf.json').is_file() and time.monotonic()<deadline:
        time.sleep(.02)
    if mode == 'tree':
        child.wait()
elif mode == 'controller':
    from diagnostic_series import _execute
    atomic_json(directory/'controller.json', {'pid':os.getpid()})
    _execute([sys.executable,__file__,'tree',str(directory)],directory,directory/'probe.log',dict(os.environ))
elif mode == 'series':
    import diagnostic_series
    from diagnostic_repetitions import prepare_repetitions
    diagnostic_series._runner_command=lambda:[sys.executable,str(ROOT/'tests/mock_pipeline.py')]
    atomic_json(directory/'controller.json', {'pid':os.getpid()})
    diagnostic_series.execute_repetitions(prepare_repetitions(directory/'base.yaml',['blind_coding'],repetitions=2),directory/'series')
else:
    raise SystemExit(2)
