#!/bin/bash
# Finder entry point; the shared helper resolves the project directory.
exec /bin/bash "$(cd -- "$(dirname -- "$0")" && pwd)/launcher.sh" setup "$@"
