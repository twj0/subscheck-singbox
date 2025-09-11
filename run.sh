#!/bin/bash
# This script ensures that the main.py is executed from the project's root directory
# and logs its output for cron jobs.

# Get the absolute path of the directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE}" )" &> /dev/null && pwd )"

# Change to the script's directory to ensure all relative paths in the python script work correctly
cd "$DIR"

# Create results directory if it doesn't exist
mkdir -p results

# Find the python executable.
# Prefer 'python3' if available, otherwise use 'python'.
if command -v python3 &> /dev/null
then
    PYTHON_EXEC="python3"
else
    PYTHON_EXEC="python"
fi

# Run the main python script.
# The '>>' appends the output to the log file.
# '2>&1' redirects stderr to stdout, so both are captured in the log file.
echo "--- Running SubCheck cron job at $(date) ---" >> results/cron.log
$PYTHON_EXEC main.py --file subscription.txt --config config.yaml >> results/cron.log 2>&1
echo "--- SubCheck cron job finished at $(date) ---" >> results/cron.log