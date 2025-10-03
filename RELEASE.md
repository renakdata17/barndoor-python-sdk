# Release Process

This document is for maintainers and describes how to create and publish releases of the Barndoor Python SDK.

## Overview

This project uses:
- **[uv-dynamic-versioning](https://github.com/ninoseki/uv-dynamic-versioning)** for automatic version management based on git tags
- **Release branches** (`release/X.Y.x`) to allow patch releases without bringing in unreleased changes from `main`
- **GitHub Releases** to trigger automated builds and PyPI publishing
- **Trusted Publishing** to securely publish to PyPI without API tokens

## Version Strategy

We follow [Semantic Versioning](https://semver.org/):
- **Major** (X.0.0): Breaking changes
- **Minor** (0.X.0): New features, backward compatible
- **Patch** (0.0.X): Bug fixes, backward compatible

Version numbers are **automatically derived from git tags** by `uv-dynamic-versioning`. You don't manually edit version numbers in code.

## Release Branches

Release branches allow us to maintain multiple versions and create patch releases without bringing in new features from `main`:

- **`main`**: Active development branch
- **`release/X.Y.x`**: Long-lived branches for each minor version (e.g., `release/1.0.x`, `release/1.1.x`)

Once a minor version is released, its release branch remains available for future patch releases.

---

## Creating a New Release

### 1. Major or Minor Release (from `main`)

Use this process when releasing a new major or minor version (e.g., `1.0.0` or `1.1.0`).

#### Step 1: Prepare the release branch

```bash
# Ensure you're up to date
git checkout main
git pull origin main

# Create a new release branch for this minor version
# For version 1.2.0, create release/1.2.x
git checkout -b release/1.2.x
git push origin release/1.2.x
```

#### Step 2: Verify the version

The version is automatically calculated from git tags. Preview it:

```bash
uvx uv-dynamic-versioning
# Output example: 1.1.0.post5.dev0+abc1234 (before tagging)
```

#### Step 3: Create and push the version tag

```bash
# Create an annotated tag for the release
git tag -a v1.2.0 -m "Release v1.2.0"

# Push the tag
git push origin v1.2.0
```

#### Step 4: Verify the version resolves correctly

```bash
uvx uv-dynamic-versioning
# Output: 1.2.0 (exact version after tagging)
```

#### Step 5: Create a GitHub Release

Go to [GitHub Releases](../../releases) and create a new release:

1. Click **"Draft a new release"**
2. **Tag**: Select `v1.2.0` (the tag you just pushed)
3. **Target**: Select the `release/1.2.x` branch
4. **Title**: `v1.2.0`
5. **Description**: Add release notes (features, fixes, breaking changes)
6. **Set as latest release**: ✅ (for major/minor releases)
7. Click **"Publish release"**

**This triggers the automated release workflow** which will:
- Build the package using `uv build`
- Publish to PyPI via trusted publishing

#### Step 6: Verify the release

Check that:
- The [Release workflow](../../actions/workflows/release.yml) completed successfully
- The package appears on [PyPI](https://pypi.org/project/barndoor/)
- You can install it: `pip install barndoor==1.2.0`

> **Note:** The release branch (`release/1.2.x`) remains available for future patch releases (e.g., `v1.2.1`, `v1.2.2`). You do not need to merge it back to `main` unless you make changes on the release branch that should be backported.

---

### 2. Patch Release (from existing release branch)

Use this process when creating a patch release (e.g., `1.2.1`) to fix bugs in an already-released minor version.

#### Step 1: Create a feature branch from the release branch

```bash
# Check out the appropriate release branch
git checkout release/1.2.x
git pull origin release/1.2.x

# Create a feature branch for your fix
git checkout -b fix/critical-bug-in-1.2
```

#### Step 2: Make your changes and commit

```bash
# Make your bug fix changes
# ...

# Commit the changes
git add .
git commit -m "fix: resolve critical bug in authentication"
```

#### Step 3: Create a PR targeting the release branch

```bash
# Push your feature branch
git push origin fix/critical-bug-in-1.2
```

Open a pull request on GitHub:
- **Base branch**: `release/1.2.x` (the release branch, not `main`)
- **Compare branch**: `fix/critical-bug-in-1.2`
- **Title**: "Fix critical bug in authentication"
- **Description**: "Fixes authentication issue discovered in v1.2.0"

Review and merge the PR through GitHub.

#### Step 4: Tag the patch release

After merging the fix PR:

```bash
# Pull the updated release branch
git checkout release/1.2.x
git pull origin release/1.2.x

# Preview the version (should show development version)
uvx uv-dynamic-versioning

# Create and push the patch tag
git tag -a v1.2.1 -m "Release v1.2.1"
git push origin v1.2.1

# Verify the version
uvx uv-dynamic-versioning
# Output: 1.2.1
```

#### Step 5: Create a GitHub Release

Follow the same GitHub Release process as Step 6 in the major/minor release:

1. Create a new release for tag `v1.2.1`
2. Target branch: `release/1.2.x`
3. Mark as latest if this is the newest stable version
4. Publish

#### Step 6: Backport to main (if needed)

**Important:** Decide whether this fix should also be in `main`. If `main` has diverged significantly or already has a different fix, you may not need to backport.

**Option A: Merge the entire release branch**

Push the release branch and open a pull request on GitHub:
- **Base branch**: `main`
- **Compare branch**: `release/1.2.x`
- **Title**: "Backport v1.2.1 fixes to main"
- **Description**: "Backporting critical bug fixes from v1.2.1"

**Option B: Cherry-pick specific commits**

```bash
git checkout main
git pull origin main
git checkout -b backport/critical-bug-fix
git cherry-pick <commit-hash-from-release-branch>
git push origin backport/critical-bug-fix
```

Open a pull request on GitHub:
- **Base branch**: `main`
- **Compare branch**: `backport/critical-bug-fix`
- **Title**: "Backport: Fix critical bug in authentication"
- **Description**: "Cherry-picked from release/1.2.x"

**Option C: No backport needed**

If the issue only affects the released version or has already been fixed differently in `main`, you can skip this step.

---

## Understanding Version Calculation

`uv-dynamic-versioning` automatically calculates versions using the [dunamai](https://github.com/mtkennerly/dunamai) library:

### On a tagged commit:
```bash
git tag v1.2.0
uvx uv-dynamic-versioning
# Output: 1.2.0
```

### On a commit after a tag:
```bash
# 5 commits after v1.2.0
uvx uv-dynamic-versioning
# Output: 1.2.0.post5.dev0+abc1234
```

### On a branch with no tags:
```bash
uvx uv-dynamic-versioning
# Output: 0.0.0.post52.dev0+abc1234
```

The version is derived at **build time**, so you never need to edit version numbers in the code.

---

## Development Releases

Every push to `main` automatically creates a development pre-release on GitHub (see [main.yml](../.github/workflows/main.yml)). These are not published to PyPI but are available for testing:

```bash
# Install a dev release from GitHub
pip install https://github.com/barndoor-ai/barndoor-python-sdk/releases/download/barndoor-dev-0.1.0.dev20250103120000+abc1234/barndoor-0.1.0.dev20250103120000+abc1234-py3-none-any.whl
```

---

## Pre-release Checklist

Before creating a release, ensure:

- [ ] All CI checks pass on the release branch
- [ ] Tests pass locally: `uv run pytest`
- [ ] Pre-commit hooks pass: `uv run pre-commit run --all-files`
- [ ] `uv.lock` is up to date: `uv lock` (should show no changes)
- [ ] CHANGELOG or release notes are prepared
- [ ] Breaking changes are clearly documented (for major releases)
