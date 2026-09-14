"""Frozen bootstrap. Project implementations are loaded from recorded sources."""
from pathlib import Path
import runpy
import sys


def main():
    if not getattr(sys, 'frozen', False):
        print('Dieser Einstieg ist nur für das Anwendungspaket vorgesehen.', file=sys.stderr)
        return 2
    raw_root = getattr(sys, '_MEIPASS', None)
    try:
        if not isinstance(raw_root, str) or not Path(raw_root).is_absolute():
            raise ValueError('invalid resource root')
        root = Path(raw_root).resolve(strict=True)
        source = root / 'src'
        entry = source / 'runtime_entry.py'
        if (not source.is_dir() or source.is_symlink() or entry.is_symlink()
                or not entry.is_file() or entry.resolve(strict=True).parent != source):
            raise ValueError('missing or redirected source entry')
    except (OSError, RuntimeError, ValueError):
        print('Programmressourcen fehlen. Das vollständige Paket erneut entpacken.', file=sys.stderr)
        return 2
    # Project modules are excluded from PYZ by the spec. The real source files
    # are both executed and hashed by application provenance; do not duplicate
    # them as hidden imports or inside this bootstrap.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source))
    try:
        from package_identity import current_package_identity
        identity = current_package_identity()
        if sys.argv[1:] == ['--package-check']:
            # Read-only installation check: no UI, model or child process.
            import importlib
            import importlib.machinery
            import json
            modules = {}
            for name in ('package_identity', 'project_paths', 'process_commands',
                         'runtime_support', 'windows_process_job', 'setup_checks'):
                module = importlib.import_module(name)
                origin = Path(module.__file__).resolve(strict=True)
                if (origin != source / (name + '.py') or not isinstance(
                        module.__loader__, importlib.machinery.SourceFileLoader)):
                    raise ValueError('Programmcode wird nicht aus den erfassten Quellen geladen.')
                modules[name] = {'origin': origin.relative_to(root).as_posix(),
                                 'loader': type(module.__loader__).__name__}
            print(json.dumps({'ok': True, 'identity': identity, 'modules': modules},
                             ensure_ascii=True, sort_keys=True))
            return 0
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.argv[0] = str(entry)
    runpy.run_path(str(entry), run_name='__main__')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
