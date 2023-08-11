#!/bin/bash

CUR_DIR="$(cd "$(dirname "$0")" && pwd)"

cd /test_repo_0

git config --global --add safe.directory /test_repo_0

git config user.email "you@example.com"
git config user.name "Your Name"

vmn init
vmn init-app app1
vmn stamp -orm patch app1

# Create branch 1
git checkout -b "branch_1"
# Stamp RC
echo a >> a.txt ; git add a.txt ; git commit -m "txt" ; git push origin
vmn stamp --orm patch --pr rc1 app1

# Checkout master
git checkout "master"

# Create branch 2
git checkout -b "branch_2"
# Stamp RC
echo a >> a.txt ; git add a.txt ; git commit -m "txt" ; git push origin
vmn stamp --orm patch --pr rc2 app1

# Release branch 1 version
vmn release -v "0.0.2-rc1.1"

# Stamp RC With branch 2
echo a >> a.txt ; git add a.txt ; git commit -m "txt" ; git push origin
vmn stamp --orm patch --pr rc2 app1
