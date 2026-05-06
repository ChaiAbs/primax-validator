#!/usr/bin/env bash
set -e

# Install ffmpeg
apt-get update -y && apt-get install -y ffmpeg

# Install Python dependencies
pip install -r requirements.txt
