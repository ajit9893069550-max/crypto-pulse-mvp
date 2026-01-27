#!/usr/bin/env bash
set -o errexit

STORAGE_DIR=/opt/render/project/src/chrome

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install --force-reinstall -r requirements.txt

echo "Installing Chrome..."
mkdir -p $STORAGE_DIR
wget -P ./chrome https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
dpkg -x ./chrome/google-chrome-stable_current_amd64.deb $STORAGE_DIR
rm ./chrome/google-chrome-stable_current_amd64.deb

echo "Chrome installed to $STORAGE_DIR"