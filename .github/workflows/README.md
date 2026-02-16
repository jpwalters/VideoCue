# GitHub Actions Workflows

This project uses GitHub Actions for automated building and testing.

## Build Release (`build-release.yml`)

**Triggers:** On pushing a version tag (e.g., `git tag v0.4.2`)

**What it does:**
1. Checks out the code
2. Sets up Python environment
3. Installs dependencies
4. Extracts version from git tag
5. Runs `build.ps1` with the version
6. Uploads installer and portable ZIP to GitHub Release
7. Saves build artifacts for debugging (30-day retention)

**Usage:**
```bash
# Create and push a version tag
git tag v0.4.2
git push origin v0.4.2

# GitHub Actions will automatically:
# - Build the executable
# - Create an installer
# - Upload both files to the release page
```

**Output files:**
- `VideoCue-0.4.2-Setup.exe` - Windows installer
- `VideoCue-0.4.2-portable.zip` - Portable ZIP

**Notes:**
- Uses `softprops/action-gh-release` to automatically create release with assets
- GitHub token is automatically available as `secrets.GITHUB_TOKEN`
- Build artifacts retained for 30 days for debugging failed builds

---

## Continuous Integration (`build-ci.yml`)

**Triggers:** On push to `main`/`develop` or on pull requests to `main`

**What it does:**
1. Checks out the code
2. Sets up Python environment
3. Installs dependencies
4. Runs linting with Ruff
5. Runs tests (if configured)
6. Builds executable with PyInstaller
7. Uploads build artifacts (for QA/testing)

**Purpose:**
- Verify code quality on every commit
- Catch build issues early
- Provide test builds for pull requests

**Artifact retention:** 7 days

---

## Setup Instructions

### Prerequisites
- Repository is on GitHub
- `.github/workflows/` directory exists (create if needed)

### 1. Enable GitHub Actions
- Go to repository Settings → Actions → General
- Ensure "Allow all actions and reusable workflows" is selected

### 2. Create Version Tags for Releases
```bash
# After committing changes
git tag v0.4.2 -m "Release v0.4.2"
git push origin v0.4.2
```

### 3. Monitor Builds
- Go to **Actions** tab on GitHub
- Click on workflow to see build logs
- On success, release files appear under **Releases** tab

---

## Troubleshooting

### Build fails with "NDI not found"
- The workflow doesn't install NDI SDK (GitHub runners have limited storage)
- NDI is bundled in the executable via `VideoCue.spec`
- Ensure NDI DLL path is correct in `VideoCue.spec` line 13

### Build fails with "Module not found"
- Check `requirements.txt` includes all dependencies
- Run locally: `pip install -r requirements.txt`
- Update `requirements.txt` and push change before tagging

### Release doesn't appear
- Check Actions tab for workflow logs
- Verify tag format matches `v*` pattern
- GitHub token is automatically provided (no manual setup needed)

### Modify Build Process
Edit `build.ps1` parameters in workflows:
```yaml
- name: Run build script
  run: |
    .\build.ps1 -Version "0.4.2" -SkipInstaller  # Skip installer if needed
```

---

## Next Steps

### Add automated testing
```yaml
- name: Run tests
  run: pytest videocue/test/ -v
```

### Add code coverage
```yaml
- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
```

### Add macOS/Linux builds
Create additional workflows with `ubuntu-latest` or `macos-latest` runners

### Email notifications on failure
Configure repository Settings → Actions → Notifications

---

## GitHub Actions Features Used

- **Workflow triggers**: Tags, push, pull requests
- **Matrix builds**: Sequential job (could be extended to parallel)
- **Artifacts**: Build outputs, debugging
- **Releases**: Auto-create GitHub release with assets
- **Caching**: Python pip cache for speed
- **Environment variables**: Version extraction, token passing

Refer to [GitHub Actions Documentation](https://docs.github.com/en/actions) for advanced features.
