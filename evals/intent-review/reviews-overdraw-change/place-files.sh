#!/usr/bin/env bash
# Puts the case's repository in the current folder: main, and the branch
# refuse-overdraw with the change to review on top of it.
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
commit() { git add -A && git -c user.name=eval -c user.email=eval@example.com -c commit.gpgsign=false commit -q -m "$1"; }
cp -R "$here/files/base/." .
git init -q -b main
commit "Billing for reviews"
git checkout -q -b refuse-overdraw
cp -R "$here/files/change/." .
commit "Refuse a charge that would overdraw"
