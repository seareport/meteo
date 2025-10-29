#!/usr/bin/env bash
#

set -Eeo pipefail

venv_path='/dev/shm/meteo_venv'
if [ ! -d "${venv_path}" ]; then
    echo "Creating virtualenv at ${venv_path}..."
    python3 -m venv "${venv_path}"
    source "${venv_path}"/bin/activate
    poetry install
else
    source "${venv_path}"/bin/activate
fi
