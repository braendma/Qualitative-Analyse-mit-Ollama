"""Sensitivity entry point using the shared controlled-analysis lifecycle."""
import sys
from stability_analysis import configured_plan as _configured_plan, main as _main, planning_summary


def configured_plan(config_path):
    return _configured_plan(config_path, kind='sensitivity')


def main(argv=None):
    return _main(argv, kind='sensitivity')


if __name__ == '__main__':
    sys.exit(main())
