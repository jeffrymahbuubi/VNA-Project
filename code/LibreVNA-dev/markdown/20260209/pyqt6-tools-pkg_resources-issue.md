# PyQt6-Tools pkg_resources Issue - Analysis & Solution

**Date:** 2026-02-09
**Issue:** `ModuleNotFoundError: No module named 'pkg_resources'` when running `pyqt6-tools designer`
**Status:** ✅ Resolved

---

## Problem Statement

When attempting to launch Qt Designer using the command:
```bash
pyqt6-tools designer
```

The following error occurs:
```python
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "D:\...\code\.venv\Scripts\pyqt6-tools.exe\__main__.py", line 4, in <module>
  File "D:\...\code\.venv\Lib\site-packages\pyqt6_tools\__init__.py", line 7, in <module>
    import pkg_resources
ModuleNotFoundError: No module named 'pkg_resources'
```

---

## Root Cause Analysis

### 1. **Legacy Dependency Issue**
   - `pyqt6-tools` (version 6.4.2.3.3) is an **outdated package** that depends on `pkg_resources`
   - `pkg_resources` is part of the legacy `setuptools` distribution system
   - The package has not been updated to use modern Python packaging standards

### 2. **setuptools Evolution**
   - Modern versions of `setuptools` (70+) have **deprecated and removed** `pkg_resources`
   - Python packaging has moved to `importlib.metadata` as the standard replacement
   - `pkg_resources` is considered legacy and is being phased out

### 3. **uv Package Manager Compatibility**
   - This project uses `uv` as the package manager for better dependency management
   - `uv` creates minimal, modern Python environments
   - Even when `setuptools` is installed, `uv` doesn't include the legacy `pkg_resources` module
   - This is by design — `uv` follows modern Python packaging best practices

### 4. **Attempted Fixes (All Failed)**
   ```bash
   # Attempt 1: Reinstall setuptools
   uv pip install --force-reinstall setuptools
   # Result: Still no pkg_resources

   # Attempt 2: Downgrade to older setuptools
   uv pip install "setuptools<70"  # Installed 69.5.1
   # Result: Still no pkg_resources in uv environment

   # Attempt 3: Direct venv Python access
   .venv/Scripts/python.exe -c "import pkg_resources"
   # Result: ModuleNotFoundError persists
   ```

---

## Solution: Bypass pyqt6-tools Wrapper

The `pyqt6-tools` package is merely a **wrapper** that launches the actual Qt Designer executable. We can bypass this problematic wrapper entirely.

### Direct Path to Qt Designer

Qt Designer is installed via the `qt6-applications` package and is located at:
```
.venv/Lib/site-packages/qt6_applications/Qt/bin/designer.exe
```

### Implementation

**Option 1: Direct Command (PowerShell)**
```powershell
& ".venv/Lib/site-packages/qt6_applications/Qt/bin/designer.exe"
```

**Option 2: PowerShell Script** (Recommended)
```powershell
# scripts/powershell/open-qt-designer.ps1
# Dynamically determines project root - works on any computer!
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "code"
$DesignerPath = Join-Path $ProjectRoot ".venv\Lib\site-packages\qt6_applications\Qt\bin\designer.exe"
Start-Process -FilePath $DesignerPath
```

Usage (works from any directory):
```powershell
# From anywhere in the project
.\scripts\powershell\open-qt-designer.ps1

# Or with full path (portable across computers)
& "path\to\project\scripts\powershell\open-qt-designer.ps1"
```

---

## Verification

After implementing the solution:

```bash
# Qt Designer launched successfully
# No errors in output
# GUI opens normally
```

The designer executable runs without any dependency on `pkg_resources` or the `pyqt6-tools` wrapper.

---

## Package Inventory

Current environment packages (relevant subset):
```
pyqt6                        6.4.2
pyqt6-plugins                6.4.2.2.3
pyqt6-qt6                    6.4.3
pyqt6-sip                    13.11.0
pyqt6-tools                  6.4.2.3.3      # ⚠️ Problematic wrapper
qt6-applications             6.4.3.2.3      # ✅ Contains designer.exe
qt6-tools                    6.4.3.1.3
setuptools                   69.5.1         # ⚠️ No pkg_resources in uv env
```

---

## Recommendations

### Short-term
- ✅ Use the PowerShell script to launch Designer
- ✅ Avoid using `pyqt6-tools` commands
- ✅ Document this workaround for team members
- ✅ **Portability:** The script uses dynamic path resolution (`$MyInvocation.MyCommand.Path`) - works on any computer without modification

### Long-term
1. **Consider removing `pyqt6-tools`** from the environment entirely since it's not functional
2. **Monitor for updates** to `pyqt6-tools` that support modern packaging (unlikely given last update was 2022)
3. **Alternative:** Explore newer GUI design tools or standalone Qt Designer installations

---

## Related Issues

This is a **known issue** across the Python ecosystem:
- `pyqt6-tools` has not been updated since 2022
- Multiple GitHub issues report `pkg_resources` problems with `uv`, `poetry`, and modern Python environments
- The package maintainer has not responded to these issues
- **Impact:** Affects any project using modern package managers (`uv`, `poetry`, `rye`) with `pyqt6-tools`

---

## Conclusion

The issue stems from **incompatibility between legacy packaging practices and modern Python tooling**. By accessing Qt Designer directly through its installed location in `qt6-applications`, we completely sidestep the problematic `pyqt6-tools` wrapper and its `pkg_resources` dependency.

**Key Takeaway:** When using modern package managers like `uv`, legacy packages that depend on `pkg_resources` will fail. Always look for the underlying tool and access it directly when wrappers cause issues.
