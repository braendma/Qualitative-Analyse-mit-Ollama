"""Application entry with internal child dispatch before any UI is loaded.

This entry does not establish frozen source/PYZ provenance. A real bundle must
separately ensure imports use the same supplied project sources as its hashes.
"""
from pathlib import Path
import runpy
import sys


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    # Do not import the UI while deciding whether this is an internal child.
    from process_commands import APPROVED_SCRIPTS, INTERNAL_SCRIPT_FLAG, validate_script
    from project_paths import SOURCE_DIR

    if args and args[0] == INTERNAL_SCRIPT_FLAG:
        if len(args) < 2 or args[1] not in APPROVED_SCRIPTS:
            print('Ungültiger interner Programmeinstieg. Installation und Startbefehl prüfen.', file=sys.stderr)
            return 2
        target, args = args[1], args[2:]
    elif INTERNAL_SCRIPT_FLAG in args:
        print('Der interne Programmeinstieg muss am Anfang des Startbefehls stehen.', file=sys.stderr)
        return 2
    else:
        target = 'local_app.py'
    try:
        script = validate_script(SOURCE_DIR / target)
        if not script.is_file():
            raise ValueError('Die Programmdatei fehlt. Installation erneut entpacken.')
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    original_argv, original_path = sys.argv, sys.path[:]
    try:
        sys.argv = [str(script), *args]
        # The packaging step must prevent a second project implementation in
        # PYZ; sys.path precedence alone cannot provide that guarantee.
        sys.path.insert(0, str(Path(SOURCE_DIR)))
        if script.parent != Path(SOURCE_DIR):sys.path.insert(0,str(script.parent))
        runpy.run_path(str(script), run_name='__main__')
    finally:
        sys.argv = original_argv
        sys.path[:] = original_path
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
