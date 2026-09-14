"""Synthetic child-series CLI used only in runner integration tests."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import diagnostic_series
from diagnostic_repetitions import prepare_repetitions
from runtime_support import atomic_json

parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
args=parser.parse_args()
diagnostic_series._runner_command=lambda:[sys.executable,str(ROOT/'tests/mock_pipeline.py')]
plan=prepare_repetitions(args.config,['blind_coding'],repetitions=2)
directory=Path.cwd()/'synthetic_repetitions'
result=diagnostic_series.execute_repetitions(plan,directory,resume=directory.exists())
if result['status']!='success':raise RuntimeError('Synthetic nested series incomplete')
atomic_json('child_series_result.json',result)
