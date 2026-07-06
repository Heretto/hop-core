#!/bin/bash
# Convenience script to run tests from project root

echo "Running hop-core Tests"
echo "======================"

# Check if Python is available
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "Error: Python is not installed"
    exit 1
fi

# Run the test suite
$PYTHON tests/run_tests.py "$@"
