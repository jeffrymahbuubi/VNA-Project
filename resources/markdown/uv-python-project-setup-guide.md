# UV Python Project Setup Guide

**Date:** 2026-02-06
**Context:** Lessons learned from setting up cisco-ai-a2a-scanner in LibreVNA project

---

## Problem Summary

### Initial Setup (What Went Wrong)

The LibreVNA project was initially set up using a minimal approach:

```bash
# Original setup - manual venv creation
uv venv --python=3.10.11
uv pip install -r requirements.txt
```

**What happened:**
- Created a `.venv` with Python 3.10.11
- Dependencies managed via `requirements.txt` only
- No `pyproject.toml` existed

**Why `uv add cisco-ai-a2a-scanner` failed:**

```
error: No `pyproject.toml` found in current directory or any parent directory
```

Even after manually adding the package to `requirements.txt`, the installation failed:

```
× No solution found when resolving dependencies:
  ╰─▶ Because the current Python version (3.10.12) does not satisfy
      Python>=3.11 and cisco-ai-a2a-scanner==1.0.1 depends on Python>=3.11,
      we can conclude that cisco-ai-a2a-scanner cannot be used.
```

**Root causes:**
1. **Missing `pyproject.toml`** - Modern UV workflow requires it for `uv add`/`uv remove` commands
2. **Python version mismatch** - The `.venv` was created with Python 3.10, but a2a-scanner requires Python ≥3.11
3. **No version pinning** - `.python-version` file was set to `3.10`, conflicting with package requirements

---

## The Modern Approach (What Works)

### Step-by-Step: Proper UV Project Setup

```bash
# 1. Initialize project with pyproject.toml
cd your-project/
uv init --no-workspace

# 2. Pin Python version (if package has specific requirements)
uv python pin 3.11

# 3. Add dependencies using uv add (not manual requirements.txt editing)
uv add numpy pandas matplotlib
uv add cisco-ai-a2a-scanner

# 4. Sync environment
uv sync

# 5. Run your code
uv run python your_script.py
```

### What This Creates

After `uv init`:

**`pyproject.toml`** - Modern Python project metadata:
```toml
[project]
name = "your-project"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "cisco-ai-a2a-scanner>=1.0.1",
    "numpy>=2.2.6",
    "pandas>=2.3.3",
]
```

**`.python-version`** - Pinned Python version:
```
3.11
```

**`uv.lock`** - Deterministic dependency resolution (like package-lock.json)

---

## Why `pyproject.toml` is Better

### Old Approach: `requirements.txt` Only

```bash
# Manual workflow - error-prone
uv venv --python=3.10
source .venv/bin/activate
pip install -r requirements.txt

# To add package:
echo "new-package>=1.0.0" >> requirements.txt
pip install -r requirements.txt
```

**Problems:**
- ❌ No metadata about Python version requirements
- ❌ No project metadata (name, version, description)
- ❌ Manual dependency management (editing text files)
- ❌ No lock file for reproducible builds
- ❌ Python version conflicts discovered late (at install time)
- ❌ Can't use modern `uv add`/`uv remove` commands

### Modern Approach: `pyproject.toml` + UV

```bash
# Automated workflow - robust
uv init
uv python pin 3.11
uv add new-package  # Automatically updates pyproject.toml
uv sync             # Installs everything consistently
```

**Benefits:**
- ✅ **Python version enforcement** - `requires-python` prevents incompatible versions
- ✅ **Centralized metadata** - Project name, version, description in one place
- ✅ **Automated dependency management** - `uv add`/`uv remove` handle everything
- ✅ **Lock file** - `uv.lock` ensures reproducible builds across machines
- ✅ **Early conflict detection** - UV resolves dependencies before installation
- ✅ **Standard format** - PEP 621 compliant, works with all modern Python tools
- ✅ **Editable installs** - `uv sync` automatically installs your project in dev mode

---

## Migration Guide: requirements.txt → pyproject.toml

If you have an existing project with `requirements.txt`:

```bash
# 1. Initialize UV project (migrates requirements.txt automatically)
cd your-project/
uv init --no-workspace

# 2. Update Python version if needed
uv python pin 3.11

# 3. Sync to create new venv with correct Python version
uv sync

# 4. Verify everything works
uv run python your_script.py

# 5. (Optional) Keep requirements.txt for backwards compatibility
# UV will keep it in sync with pyproject.toml
```

**What `uv init` does:**
- Creates `pyproject.toml` from existing `requirements.txt`
- Detects current Python version from `.venv` or system
- Preserves all your dependencies with version constraints
- Does NOT delete `requirements.txt` (you can keep both)

---

## Common UV Commands Reference

### Project Setup
```bash
uv init                      # Create new project with pyproject.toml
uv init --no-workspace       # Single project (not part of workspace)
uv python pin 3.11           # Pin Python version in .python-version
```

### Dependency Management
```bash
uv add package-name          # Add dependency to pyproject.toml
uv add --dev pytest          # Add dev dependency
uv remove package-name       # Remove dependency
uv sync                      # Install all dependencies from lock file
uv sync --upgrade            # Upgrade all dependencies
uv lock                      # Update lock file without installing
```

### Running Code
```bash
uv run python script.py      # Run with project's Python + dependencies
uv run pytest                # Run tests with project environment
uv run --python 3.12 script  # Override Python version temporarily
```

### Environment Management
```bash
uv venv                      # Create .venv (usually automatic)
uv pip list                  # List installed packages
uv pip install -e .          # Install project in editable mode
```

---

## Best Practices for New Python Projects

### ✅ DO: Start with UV Init

```bash
# Good: Modern workflow from the start
mkdir my-project && cd my-project
uv init
uv python pin 3.11
uv add numpy pandas matplotlib
uv run python main.py
```

### ❌ DON'T: Manual venv + requirements.txt

```bash
# Bad: Old workflow, will cause problems later
mkdir my-project && cd my-project
uv venv --python=3.10
echo "numpy" > requirements.txt
uv pip install -r requirements.txt
```

### Project Structure Recommendation

```
my-project/
├── pyproject.toml          # ✅ Project metadata + dependencies
├── uv.lock                 # ✅ Lock file (committed to git)
├── .python-version         # ✅ Python version pin
├── requirements.txt        # ⚠️  Optional, for backwards compatibility
├── .venv/                  # ❌ Never commit (add to .gitignore)
├── src/
│   └── my_project/
│       └── __init__.py
└── tests/
    └── test_main.py
```

**`.gitignore` entries:**
```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

**Commit to git:**
```bash
git add pyproject.toml uv.lock .python-version
git commit -m "Initialize project with UV"
```

---

## Troubleshooting Common Issues

### Issue 1: Python Version Conflict

**Error:**
```
error: The Python request from `.python-version` resolved to Python 3.10.12,
which is incompatible with the project's Python requirement: `>=3.11`
```

**Solution:**
```bash
uv python pin 3.11   # Update .python-version
uv sync              # Recreate venv with correct Python
```

### Issue 2: Package Requires Newer Python

**Error:**
```
Because package-name depends on Python>=3.11 and current Python is 3.10
```

**Solution:**
```bash
# Update Python version in pyproject.toml
uv python pin 3.11
uv sync
```

Or edit `pyproject.toml`:
```toml
requires-python = ">=3.11"  # Update this line
```

### Issue 3: No pyproject.toml Found

**Error:**
```
error: No `pyproject.toml` found in current directory
```

**Solution:**
```bash
# Initialize project first
uv init --no-workspace
uv add your-package
```

### Issue 4: Conflicting Dependencies

**Error:**
```
× No solution found when resolving dependencies
```

**Solution:**
```bash
# Check what's conflicting
uv tree

# Try upgrading all dependencies
uv sync --upgrade

# Or pin specific versions in pyproject.toml
```

---

## When to Use requirements.txt vs pyproject.toml

### Use `pyproject.toml` (Preferred)

**For:**
- ✅ New projects (always)
- ✅ Applications you develop and deploy
- ✅ Libraries you publish to PyPI
- ✅ Projects with multiple contributors
- ✅ CI/CD pipelines (reproducible builds)

**Why:**
- Modern standard (PEP 621)
- Better dependency resolution
- Lock file support
- Python version enforcement

### Keep `requirements.txt` (Optional)

**For:**
- ⚠️  Legacy compatibility (Docker images, old CI)
- ⚠️  Simple scripts shared with non-UV users
- ⚠️  Documentation/examples

**How to maintain both:**
```bash
# UV can export to requirements.txt
uv pip compile pyproject.toml -o requirements.txt

# Or just keep both - UV updates requirements.txt automatically
```

---

## Real-World Example: LibreVNA Project Migration

### Before (Old Setup)
```bash
# Manual venv creation
uv venv --python=3.10.11

# requirements.txt
numpy>=1.24.0
pandas>=2.0.0
scikit-rf>=0.29.0
# ... 10+ packages
```

**Problems encountered:**
- Couldn't add a2a-scanner (required Python 3.11)
- No automatic version conflict detection
- Manual dependency tracking

### After (Modern Setup)
```bash
# Automated setup
uv init --no-workspace
uv python pin 3.11
uv add numpy pandas scikit-rf matplotlib seaborn plotly h5py scikit-learn pyyaml openpyxl cisco-ai-a2a-scanner
uv sync
```

**pyproject.toml:**
```toml
[project]
name = "code"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "cisco-ai-a2a-scanner>=1.0.1",
    "h5py>=3.15.1",
    "matplotlib>=3.10.8",
    "numpy>=2.2.6",
    # ... all packages
]
```

**Benefits achieved:**
- ✅ Python 3.11 enforced automatically
- ✅ All dependencies resolved consistently
- ✅ Lock file ensures reproducible builds
- ✅ Simple workflow: `uv run python script.py`

---

## Summary: Key Takeaways

1. **Always start with `uv init`** - Don't create manual venvs
2. **Pin Python version early** - Use `uv python pin X.Y` before adding packages
3. **Use `uv add` for dependencies** - Don't edit `pyproject.toml` manually
4. **Commit lock files** - `uv.lock` ensures team consistency
5. **Modern tooling = fewer problems** - Let UV handle dependency resolution

### Quick Start Template

```bash
# Start ANY new Python project with these commands:
mkdir my-project && cd my-project
uv init --no-workspace
uv python pin 3.11
uv add your-dependencies
echo ".venv/" >> .gitignore
git init && git add . && git commit -m "Initial commit"
uv run python main.py
```

---

## Additional Resources

- **UV Documentation:** https://docs.astral.sh/uv/
- **PEP 621 (pyproject.toml):** https://peps.python.org/pep-0621/
- **UV vs pip/poetry comparison:** https://docs.astral.sh/uv/pip/compatibility/

---

**Last Updated:** 2026-02-06
**Project:** LibreVNA Vector Network Analyzer
**Author:** Setup notes from a2a-scanner integration experience
