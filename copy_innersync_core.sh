#!/bin/bash
# Clone Innersync_Core (replace with your auth method)
# For private repo, use SSH or PAT
git clone https://github.com/bryntje/Innersync_Core.git temp-core

# Create shared directory if it doesn't exist
mkdir -p shared

# Copy all contents (excluding .git)
cp -r temp-core/* shared/
cp temp-core/.* shared/ 2>/dev/null || true

# Remove temp directory
rm -rf temp-core

echo 'Code copied successfully. Run: git add shared/ && git commit -m "Add Innersync_Core code as regular directory"'
