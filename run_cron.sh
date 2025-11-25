#!/bin/bash

# check that we have passed a command name
if [[ $# < 1 ]]
then
	echo "specify what command to launch (e.g., download_videos, render_segments, download_clips)"
	exit 1
fi

# Get the repository root directory (where this script is located)
REPO_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Source the virtual environment
if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
	source "$REPO_ROOT/.venv/bin/activate"
else
	echo "Error: .venv not found at $REPO_ROOT/.venv"
	exit 1
fi

# check if the process is running or not
if pgrep -f "tvc.py $1" >/dev/null 2>&1 ; 
then
	echo "script already running, skipping"
	exit 1
fi 

# else lets run the script!
DATE=$(date +\%Y-\%m-\%d)
TIME=$(date +\%H-\%M-\%S)
mkdir -p "$REPO_ROOT/logs/$DATE/"
cd "$REPO_ROOT"
python3 "$REPO_ROOT/tvc.py" "$1" "${@:2}" 2>&1 | tee "$REPO_ROOT/logs/$DATE/$TIME-$1.log"

