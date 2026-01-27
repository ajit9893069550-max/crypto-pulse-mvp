#!/usr/bin/env bash
set -o errexit

STORAGE_DIR=/opt/render/project/src/chrome

echo "1. Installing Basic Dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "2. Manually Installing Pandas-TA..."
# Clone directly to avoid pip git auth issues
if [ -d "pandas-ta" ]; then rm -rf pandas-ta; fi
git clone https://github.com/twopirllc/pandas-ta.git
cd pandas-ta
pip install .
cd ..

echo "3. Installing Chrome..."
mkdir -p $STORAGE_DIR
wget -P ./chrome https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
dpkg -x ./chrome/google-chrome-stable_current_amd64.deb $STORAGE_DIR
rm ./chrome/google-chrome-stable_current_amd64.deb

echo "Build Complete!"