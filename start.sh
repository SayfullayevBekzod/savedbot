#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Create downloads directory
mkdir -p downloads

# Start the bot
python main.py
