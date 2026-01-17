#!/bin/bash

# Stop script on first error
set -e
 
echo "1. Installing required build tools..."
sudo apt-get update
sudo apt-get install -y fakeroot build-essential python3-all debhelper dh-python python3-stdeb

echo "2. Cleaning up old builds..."
rm -rf deb_dist dist build *.egg-info package_build logs
rm -f settings.json rebuild.sh selected_docker_compose_path.txt
rm -rf AppDir *.spec build_tmp *.AppImage
find . -type d -name "__pycache__" -exec rm -rf {} +

echo "3. Generating Debian Source..."
# We use sdist_dsc to generate the debian/ folder structure without trying to compile yet
python3 setup.py --command-packages=stdeb.command sdist_dsc

echo "4. Building .deb package..."
# We enter the generated directory and build manually.
# Find the generated package directory dynamically based on the new name
PACKAGE_DIR=$(find deb_dist -maxdepth 1 -type d -name "tray-chat-ai-*" -print -quit)

if [ -z "$PACKAGE_DIR" ]; then
    echo "Error: Could not find the generated package directory (tray-chat-ai-*) in deb_dist."
    exit 1
fi

cd "$PACKAGE_DIR"
# dpkg-buildpackage options: -rfakeroot (simulates root), -uc -us (skips GPG signing), -b (build binary only)
dpkg-buildpackage -rfakeroot -uc -us -b


echo "--------------------------------------------------"
echo "Success! Package is located in the deb_dist/ folder."