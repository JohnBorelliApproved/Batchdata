#!/bin/bash

# Update package lists
sudo apt-get update

# Install Python, Pip, venv, and Nginx
sudo apt-get install -y python3 python3-pip python3-venv nginx

# Navigate to the project directory
PROJECT_DIR="/var/www/html"
cd $PROJECT_DIR

# Create a Python virtual environment
python3 -m venv venv

# Activate the virtual environment and install dependencies
source venv/bin/activate
pip install -r requirements.txt

# Deactivate for now
deactivate

echo "Deployment setup complete. Please configure and enable the systemd and Nginx services."
