# NDI Wrapper + GitHub Actions Strategy

## 🎯 Your Options

### Current Setup (No Changes Required)
**File**: `build-ci.yml` and `build-release.yml`  
**Strategy**: Verify `.pyd` files exist in repo (no building in CI/CD)

```
Pros:
  ✅ Fast CI/CD (2 minutes)
  ✅ No NDI SDK needed in GitHub Actions
  ✅ No breaking changes to existing workflows
  ✅ Works today

Cons:
  ❌ Manual rebuild locally when C++ changes
  ❌ Developers must commit .pyd updates
  ❌ Bottleneck if multiple people edit main.cpp
```

**When to use**: 
- Small team
- Infrequent C++ changes
- Don't mind manual builds

**Command**:
```powershell
# Do locally
.\build_ndi_wrapper.ps1
git add videocue/ndi_wrapper/NDIlib*.pyd
git commit -m "Update NDI bindings"
git push
```

---

### Option 1: Auto-Rebuild on C++ Changes ⭐ Recommended
**File**: `.github/workflows/rebuild-ndi-wrapper.yml`  
**Strategy**: Automatically rebuild when `src/main.cpp` or build config changes

```
Pros:
  ✅ Automatic - no manual steps
  ✅ Always in sync with C++ changes
  ✅ Works for multiple Python versions
  ✅ Clear commit history of builds

Cons:
  ❌ CI/CD takes longer (~12-15 min)
  ❌ Requires NDI SDK setup in GitHub Actions
  ❌ May create "noisy" commits
  ❌ Needs self-hosted runner OR NDI SDK download solution
```

**When to use**:
- Active C++ development
- Multiple developers editing main.cpp
- Long-term maintenance mindset
- Have a self-hosted runner with NDI SDK

**Setup required**:
1. Option A: **Self-hosted runner** with NDI SDK pre-installed
   - Most reliable, no SDK licensing questions
   - Runner reuses NDI SDK download
   
2. Option B: **Download NDI SDK in workflow** (modify workflow)
   - Slower (adds 5+ min per build)
   - Need to handle NDI SDK licensing/distribution

**How it works**:
```
Developer → Push changes to src/main.cpp
           ↓
GitHub Actions triggered (rebuild-ndi-wrapper.yml)
           ↓
CMake + MSVC build .pyd
           ↓
Auto-commit .pyd or create PR
           ↓
Pre-built .pyd ready for build-release.yml
```

---

### Option 2: Manual Trigger Workflow ⭐ Good Middle Ground
**File**: `.github/workflows/rebuild-ndi-manual.yml`  
**Strategy**: Rebuild on-demand via GitHub UI

```
Pros:
  ✅ No impact on normal CI/CD
  ✅ Full control - rebuild anytime
  ✅ Good for testing C++ changes
  ✅ Requires NDI SDK only when needed
  ✅ Works with self-hosted OR local testing

Cons:
  ❌ Manual trigger (not automatic)
  ❌ Still requires NDI SDK somewhere
  ❌ Possible forgotten builds
```

**When to use**:
- Mixed approach - automate later
- Testing C++ changes before commit
- Slow CI/CD is problematic
- Want control over when builds run

**How to use**:
1. Go to: GitHub Repo → Actions → "Rebuild NDI Wrapper (Manual)"
2. Click "Run workflow"
3. Choose Python versions (3.10, 3.12, or both)
4. Choose if you want to auto-commit changes
5. Watch logs in real-time
6. Artifacts available for download

---

## 📋 Recommendation for Your Project

### Short Term (Now):
**Keep current approach** (verify mode)
- No changes needed
- CI/CD stays fast
- You build locally for now

### Medium Term (Next few weeks):
**Add Option 2** (Manual Workflow)
- Enables GitHub UI rebuild trigger
- No SDK/runner setup needed yet
- Low risk, high benefit
- Test it before going full auto

### Long Term (3+ months):
**Consider Option 1** (Auto Rebuild)
- After C++ changes stabilize
- After deciding on self-hosted runner
- If team grows and sharing code

---

## 🚀 Recommended Implementation Path

### Step 1: Keep Current CI/CD (No changes)
```
Current files work as-is:
  .github/workflows/build-ci.yml     ← Stays the same
  .github/workflows/build-release.yml ← Stays the same
```

You already have:
- ✅ Pre-compiled .pyd in repo
- ✅ C++ source in videocue/ndi_wrapper/src/
- ✅ Local build script (build_ndi_wrapper.ps1)
- ✅ CMake configuration

### Step 2: Test Manual Rebuild Workflow
```
NEW file: .github/workflows/rebuild-ndi-manual.yml
  - Adds manual trigger option
  - No impact on existing workflows
  - Zero breaking changes
```

### Step 3: If You Need Auto Rebuild Later
```
NEW file: .github/workflows/rebuild-ndi-wrapper.yml
  - Replaces manual workflow
  - Requires NDI SDK setup decision
  - Can be added later without breaking anything
```

---

## 🔧 Setup Decision Tree

> Do you want to build .pyd in GitHub Actions right now?

**No:**
- Keep current workflows
- Use local `build_ndi_wrapper.ps1` when needed
- Commit .pyd files manually
- ✅ Zero setup, works today

**Maybe/Later:**
- Add manual workflow (rebuild-ndi-manual.yml)
- Use GitHub UI to trigger rebuilds on demand
- ✅ Low overhead, gained flexibility

**Yes, Full Auto:**
- Set up self-hosted Windows runner with NDI SDK pre-installed
- Add auto-rebuild workflow (rebuild-ndi-wrapper.yml)
- Builds triggered on C++ source changes
- ✅ Most automated, but requires runner setup

---

## 🎓 How Each Workflow Works

### Current: `build-ci.yml`

```yaml
Triggers: push to main/develop, pull requests

Steps:
  1. Setup Python 3.10
  2. Install dependencies (pip, pyinstaller)
  3. ✓ Verify .pyd files exist (no building)
  4. Lint with ruff
  5. Run tests
  6. Build executable with PyInstaller
  7. Upload artifacts
```

**Time**: ~5-8 min (no build time)

---

### Manual: `rebuild-ndi-manual.yml`

```yaml
Triggers: Manual via GitHub UI (workflow_dispatch)

Steps:
  1. Setup Python 3.10 and 3.12
  2. Install CMake, pybind11
  3. Find NDI SDK (must exist on runner)
  4. Build .pyd for selected Python version(s)
  5. [Optional] Commit and push changes
  6. Upload artifacts for download
```

**Time**: ~10-15 min (includes build)

**Access from GitHub UI:**
- Actions tab
- "Rebuild NDI Wrapper (Manual)"
- Configure options
- "Run workflow"

---

### Auto: `rebuild-ndi-wrapper.yml`

```yaml
Triggers: Push changes to src/main.cpp, CMakeLists.txt, or workflow itself

Steps:
  1. Setup Python 3.10 and 3.12
  2. Install CMake, pybind11
  3. Find NDI SDK (must exist on runner)
  4. Build both Python 3.10 and 3.12 .pyd
  5. Check if anything changed
  6. [If changes] Auto-commit and push
     OR [If on develop] Create PR to main
  7. Done - CI/CD can use updated .pyd
```

**Time**: ~10-15 min (includes build)

**Considerations**:
- Runs automatically on every C++ change
- Could create "noisy" commits
- Requires runner with NDI SDK
- Better for active development

---

## 💾 What Gets Committed

### Option: Auto-Commit Direct to Branch
```
Developer pushes: src/main.cpp changes
    ↓
Workflow rebuilds .pyd
    ↓
Auto-commits: NDIlib.cp310-win_amd64.pyd + ndlib.cp312-win_amd64.pyd
    ↓
Same commit available in build-release.yml
```

**Pro**: Direct integration  
**Con**: Hard to review what changed in C++

### Option: Create Pull Request
```
Developer pushes: src/main.cpp changes to develop
    ↓
Workflow rebuilds .pyd
    ↓
Creates PR: "Automated: Update NDI wrapper bindings"
    ↓
Developers review before merging
    ↓
Merge to main with clean history
```

**Pro**: Reviewable, clean history  
**Con**: Extra PR step

---

## 🛠️ Implementation Examples

### Example 1: Just Keep Current Setup

**Do nothing.** Your workflows already work:
- Pre-compiled .pyd in repo ✅
- build-ci.yml verifies them ✅
- build-release.yml uses them ✅

To rebuild locally:
```powershell
.\build_ndi_wrapper.ps1
git add videocue/ndi_wrapper/*.pyd
git commit -m "Update NDI bindings"
git push
```

---

### Example 2: Add Manual Workflow (No Breaking Changes)

The file `.github/workflows/rebuild-ndi-manual.yml` is already created!

**To enable it**:
1. Commit it to repo
2. On GitHub UI, go to Actions
3. You'll see new task: "Rebuild NDI Wrapper (Manual)"
4. Click → Run workflow → Select options

**Zero impact on existing CI/CD.**

---

### Example 3: Full Auto Rebuild Setup

**Prerequisites**:
1. Self-hosted Windows runner with:
   - CMake installed
   - Python 3.10 + 3.12
   - NDI SDK (path: `C:\NDI SDK 6`)

2. Runner registered to repo:
   ```bash
   # On self-hosted machine
   # Docs: https://docs.github.com/actions/hosting-your-own-runners
   ```

**Then**:
```
1. Commit: .github/workflows/rebuild-ndi-wrapper.yml
2. Update workflow to use: runs-on: [ self-hosted, windows ]
3. Modify NDI SDK path if needed
4. Every push to src/main.cpp triggers rebuild
```

---

## 📊 Quick Comparison

| Feature | Current | Manual | Auto |
|---------|---------|--------|------|
| **Fast CI/CD** | ✅ Yes | ✅ Yes | ❌ +10-15min |
| **Manual trigger** | ❌ No | ✅ Yes | N/A |
| **Auto on C++ change** | ❌ No | ❌ No | ✅ Yes |
| **NDI SDK needed** | ❌ No | ⚠️ Yes | ⚠️ Yes |
| **Setup complexity** | 🟢 None | 🟡 Low | 🔴 Medium |
| **Best for** | Small team | Testing | Active dev |

---

## 🎯 My Recommendation

**For now:**
1. Keep current approach (no changes)
2. Build locally when you change C++
3. Commit .pyd manually

**When C++ changes get frequent:**
1. Add manual workflow
2. Use GitHub UI for rebuilds
3. Zero setup, full control

**Later (if team grows):**
1. Consider self-hosted runner
2. Enable full auto-rebuild
3. Maximum automation

---

## Questions to Consider

1. **How often will C++ change?**
   - Rarely → Keep current
   - Sometimes → Add manual workflow
   - Often → Set up auto-rebuild

2. **How many developers work on main.cpp?**
   - Just you → Current approach fine
   - Multiple → Manual workflow helpful
   - Team → Auto-rebuild recommended

3. **Can you spare 10-15 min per CI/CD run?**
   - No → Keep current (2 min fast)
   - Yes → Auto-rebuild is OK

4. **Do you have a Windows machine for self-hosted runner?**
   - No → Manual workflow is best
   - Yes → Can do full auto-rebuild

---

## Files Reference

**Current Workflows** (no changes needed):
- `.github/workflows/build-ci.yml` - Fast CI, verify .pyd exist
- `.github/workflows/build-release.yml` - Release build

**New Workflows** (optional additions):
- `.github/workflows/rebuild-ndi-manual.yml` - Manual trigger
- `.github/workflows/rebuild-ndi-wrapper.yml` - Auto rebuild

**Supporting Files** (already created):
- `build_ndi_wrapper.ps1` - Local build script
- `videocue/ndi_wrapper/src/main.cpp` - C++ source (1,495 lines)
- `videocue/ndi_wrapper/CMakeLists.txt` - Build config
- `videocue/ndi_wrapper/LICENSE.md` - Attribution
- `videocue/ndi_wrapper/README_BUILD.md` - Build instructions

---

## Next Steps

### Option A: Do Nothing (Recommended for now)
```bash
# Everything works as-is
# Use: .\build_ndi_wrapper.ps1 locally
# Commit .pyd manually
```

### Option B: Add Manual Workflow (Low Risk)
```bash
git add .github/workflows/rebuild-ndi-manual.yml
git commit -m "feat: add manual NDI wrapper rebuild workflow"
git push

# Now available in GitHub Actions UI
```

### Option C: Full Auto (Requires Setup)
```bash
# 1. Set up self-hosted runner with NDI SDK
# 2. Add workflow files
# 3. Test thoroughly first
```

**I recommend starting with Option A or B, then evolving to C later if needed.**
