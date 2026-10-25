#!/usr/bin/env sh
set -eu
python -m compileall -q app tests
python -m pytest -q
