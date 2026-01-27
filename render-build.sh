#!/usr/bin/env bash
set -o errexit

STORAGE_DIR=/opt/render/project/src/chrome

echo "1. Installing Python Dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "2. Installing Chrome..."
mkdir -p $STORAGE_DIR
wget -P ./chrome https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
dpkg -x ./chrome/google-chrome-stable_current_amd64.deb $STORAGE_DIR
rm ./chrome/google-chrome-stable_current_amd64.deb

echo "Build Complete!"