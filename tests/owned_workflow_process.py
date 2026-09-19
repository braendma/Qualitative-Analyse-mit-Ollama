"""Bound CI fixtures and reap their complete process tree before temp cleanup."""
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run_owned(command, *, env, directory, timeout=180):
    ticket = uuid.uuid4().hex
    base = Path(directory)
    receipt = base / (ticket + '.supervision.json')
    stdout = base / (ticket + '.stdout.log')
    stderr = base / (ticket + '.stderr.log')
    controller = [sys.executable, str(ROOT / 'src/managed_ollama.py'), '--command',
                  str(receipt), ticket, *command]
    with stdout.open('wb') as out, stderr.open('wb') as err:
        process = subprocess.Popen(controller, env=env, stdin=subprocess.PIPE, stdout=out, stderr=err)
        try:
            process.wait(timeout=timeout)
        finally:
            # EOF releases only this fixture's supervisor lease. Its existing
            # Windows job / POSIX group cleanup includes child repetitions.
            process.stdin.close()
            process.wait(timeout=30)
            saved = json.loads(receipt.read_text(encoding='utf-8'))
            if saved.get('ticket') != ticket or not saved.get('cleanup_confirmed'):
                raise RuntimeError('Testprozessbaum nicht sicher beendet; temporäre Dateien bleiben gesperrt.')
    return subprocess.CompletedProcess(command, process.returncode,
        stdout.read_text(encoding='utf-8'), stderr.read_text(encoding='utf-8'))
