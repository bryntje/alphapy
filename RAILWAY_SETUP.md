# Railway No-Submodule Setup

## ✅ Completed
- ✅ Removed Innersync_Core submodule
- ✅ Cleaned up .git/modules
- ✅ Removed GitHub Actions flatten workflow

## 🚀 Next Steps

### 1. Copy Innersync_Core Code
Run the provided script to copy code:
```bash
./copy_innersync_core.sh
```

Or manually:
```bash
# Clone Innersync_Core (use your auth method for private repo)
git clone https://YOUR_PAT@github.com/bryntje/Innersync_Core.git temp-core
# or: git clone git@github.com:bryntje/Innersync_Core.git temp-core

# Copy to shared/
cp -r temp-core/* shared/
cp temp-core/.* shared/ 2>/dev/null || true
rm -rf temp-core

# Commit
git add shared/
git commit -m "Add Innersync_Core code as regular directory"
git push
```

### 2. Railway Dashboard Configuration
**Service:** Dashboard (Next.js)
- **GitHub Repo:** `bryntje/alphapy`
- **Branch:** `master` (or your main branch)
- **Root Directory:** `/`
- **Config File Path:** `/shared/innersync-core/railway.toml`
- **Builder:** Dockerfile → `Dockerfile.dashboard`
- **Watch Paths:** `shared/innersync-core/**`

### 3. Verify Files After Copy
After running the copy script, verify:
- `shared/innersync-core/package.json` exists
- `shared/innersync-core/railway.toml` exists
- `shared/innersync-core/Dockerfile` exists

## 🔧 Dockerfile Check
Your `Dockerfile.dashboard` should have correct paths:
```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./  # ✅ Correct (relative to context)
```

## 🎯 Result
- No submodule auth issues
- Direct deployment from master
- Railway finds config at `/shared/innersync-core/railway.toml`
- Builds from root context but uses dashboard Dockerfile
