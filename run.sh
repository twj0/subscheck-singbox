#!/bin/bash
# This script ensures that the main.py is executed using the Python interpreter
# from the project's virtual environment (.venv).

# Get the absolute directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE}" )" &> /dev/null && pwd )"

# Define the path to the virtual environment's Python executable
VENV_PYTHON="$DIR/.venv/bin/python3"

# Check if the venv python exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Python interpreter not found at $VENV_PYTHON"
    echo "Please run the install.sh script first to set up the virtual environment."
    exit 1
fi

# Change to the script's directory and execute main.py using the venv python
# Append output to a log file in the results directory.
cd "$DIR"
"$VENV_PYTHON" main.py >> "$DIR/results/cron.log" 2>&1