#!/bin/bash
set -euo pipefail

finish() {
    local result=$?
    if (( result != 0 )); then
        printf '\nAbgebrochen. Bitte die Fehlermeldung oben beachten.\n' >&2
    fi
    if [[ -t 0 && -z "${CI:-}" ]]; then
        read -r -p 'Zum Schliessen des Fensters Enter druecken ... ' _ || true
    fi
    exit "$result"
}
trap finish EXIT

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$root"
mode="${1:-start}"
if (( $# > 0 )); then shift; fi
if [[ "$mode" != setup && "$mode" != start ]]; then
    printf 'Unbekannte Aktion: %s\n' "$mode" >&2
    exit 2
fi
if [[ "$(uname -s)" != Darwin ]]; then
    printf 'Diese Startdateien sind fuer macOS. Siehe README fuer andere Systeme.\n' >&2
    exit 1
fi

# Separate from the Windows virtual environment when sharing a project folder.
python="$root/.venv-macos/bin/python3"
if [[ "$mode" == setup ]]; then
    if [[ ! -x "$python" ]]; then
        candidate=""
        for item in "${QUALITATIVE_PYTHON:-}" python3 python3.14 python3.13 python3.12 python3.11 python3.10 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
            [[ -n "$item" ]] || continue
            if command -v "$item" >/dev/null 2>&1 && "$item" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
                candidate="$item"
                break
            fi
        done
        if [[ -z "$candidate" ]]; then
            printf 'Python 3.10 oder neuer fehlt. Installation: https://www.python.org/downloads/macos/\n' >&2
            exit 1
        fi
        "$candidate" -m venv "$root/.venv-macos"
    fi
    "$python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
    printf 'Installiere Python-Pakete in .venv-macos. Internet wird benoetigt.\n'
    "$python" -m pip install -r "$root/requirements.txt"
    printf '\nEinrichtung abgeschlossen. Jetzt start/macos/Start_Oberflaeche.command oeffnen.\n'
else
    if [[ ! -x "$python" ]]; then
        printf 'Zuerst start/macos/Einrichtung.command ausfuehren.\n' >&2
        exit 1
    fi
    if ! "$python" -c 'import pandas,numpy,matplotlib,yaml,ollama,openpyxl'; then
        printf 'Python-Pakete fehlen. start/macos/Einrichtung.command erneut ausfuehren.\n' >&2
        exit 1
    fi
    printf 'Die Oberflaeche oeffnet sich im Browser. Dieses Terminal offen lassen.\n'
    printf 'Beenden: Ctrl+C.\n'
    "$python" -X utf8 "$root/src/local_app.py" "$@"
fi
