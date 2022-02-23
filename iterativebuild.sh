#!/bin/bash

# This script is designed to called from github runner that builds and publish docs.
# If pydocbrowser fails with code 21 (timeout), sends signal to build docs again.

set +e
# For testing, it will create many jobs, a values more like 200 should be set for production
python -m pydocbrowser --build-timeout 0
# Exit code 21 means it stopped generating docs because of the build timeout
if [[ $? -eq 21 ]]; then
    set -e
    echo 'Sending signal to build docs again'
    curl -XPOST -u "$GH_USERNAME:$GH_TOKEN" \
        -H "Accept: application/vnd.github.everest-preview+json" \
        -H "Content-Type: application/json" \
        https://api.github.com/repos/pydocbrowser/pydocbrowser.github.io/actions/workflows/20465935/dispatches \
        --data '{"ref": "main"}'
    exit 0
elif [[ $? -eq 0 ]]; then
    exit 0
else
    exit 1
fi