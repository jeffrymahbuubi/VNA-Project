"""version.py — single source of truth for the E5063A Data Collector version.

Scheme + release workflow: docs/versioning-and-releases.md (SemVer:
MAJOR = data-contract break, MINOR = functional change to recorded data,
PATCH = cosmetic). Drop the "-dev" suffix only in the release commit
(`chore(release): vX.Y.Z`), never in feature work.

Consumers: main_window.py window title; release zip naming
(E5063A-Data-Collector-v<X.Y.Z>-win64.zip). The Dataflux CSV header must
NEVER carry this value (12-line byte-compatible layout is locked).
"""

__version__ = "1.1.0"
