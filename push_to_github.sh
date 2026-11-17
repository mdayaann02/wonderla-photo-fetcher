#!/data/data/com.termux/files/usr/bin/bash
set -e

REPO_DIR="/data/data/com.termux/files/home/wonderla-photo-fetcher"
cd "$REPO_DIR"

echo "=========================================================="
echo "    Push Wonderla Photo Fetcher to GitHub                "
echo "=========================================================="

# Check if gh is authenticated
if gh auth status >/dev/null 2>&1; then
    echo "✅ GitHub CLI is authenticated!"
    read -p "Enter repository name (default: wonderla-photo-fetcher): " REPO_NAME
    REPO_NAME=${REPO_NAME:-wonderla-photo-fetcher}
    
    echo "Creating GitHub repository '$REPO_NAME' and pushing..."
    gh repo create "$REPO_NAME" --public --source=. --remote=origin --push || git push -u origin main
    echo "🎉 Successfully pushed to GitHub!"
else
    echo "GitHub is not yet authenticated on this device."
    echo ""
    echo "Option 1: Quick login via GitHub CLI (recommended):"
    echo "  Run: gh auth login"
    echo "  Select: GitHub.com -> HTTPS -> Yes -> Login with a web browser"
    echo ""
    echo "Option 2: Push using your repository URL:"
    echo "  1. Create a new empty repository at https://github.com/new"
    echo "  2. Run:"
    echo "     git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO>.git"
    echo "     git push -u origin main"
fi
