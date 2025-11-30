#!/bin/bash
# Production Version with English Logs

echo " "
echo "🚀 STARTING JOAN 6 DASHBOARD GENERATOR..."
echo "---------------------------------------------------"

# Fix line endings (just in case)
echo "🔧 Fixing file formatting (dos2unix)..."
dos2unix /app/run.py

# Start App
echo "🐍 Starting Python..."
echo "---------------------------------------------------"
python3 -u /app/run.py
