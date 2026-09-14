"""Coverage CLI using the existing pipeline's config, manifest and report contracts."""
from coverage_core import analyze_coverage, render_coverage
from diagnostic_cli import run_diagnostic
from progress_events import track_module


@track_module
def main(argv=None):
    run_diagnostic('coverage', 'coverage', 'Coverage aus vorhandenen verifizierten Analyseergebnissen',
                   analyze_coverage, render_coverage, argv)


if __name__ == '__main__':
    main()
