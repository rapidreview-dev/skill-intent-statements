#!/usr/bin/env bash
# Puts the case's repository in the current folder, with one commit to start from.
set -eu
cp -R "$(dirname "$0")/files/." .
git init -q -b main
git add -A
git -c user.name=eval -c user.email=eval@example.com -c commit.gpgsign=false commit -q -m "Text helpers"
