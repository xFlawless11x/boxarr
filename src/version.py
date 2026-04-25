"""Dynamic version management for Boxarr using git tags."""

import subprocess
from pathlib import Path


def get_version() -> str:
    """
    Get the current version from git tags or fallback to a default.

    Returns:
        Version string in format 'x.y.z' or 'x.y.z-dev' if not on a tag
    """
    try:
        # Try to get version from git describe
        result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).parent.parent,
        )

        if result.returncode == 0:
            version = result.stdout.strip()

            # Clean up version string
            if version.startswith("v"):
                version = version[1:]

            # Check if we're on a tagged commit
            tag_result = subprocess.run(
                ["git", "describe", "--exact-match", "--tags"],
                capture_output=True,
                text=True,
                check=False,
                cwd=Path(__file__).parent.parent,
            )

            if tag_result.returncode != 0:
                # Not on a tag, add -dev suffix if not already present
                if "-" in version:
                    # Format: v0.4.1-2-g1234567 -> 0.4.1-dev
                    parts = version.split("-")
                    base_version = parts[0]
                    if "dirty" in version:
                        version = f"{base_version}-dev-dirty"
                    else:
                        version = f"{base_version}-dev"
                else:
                    # Just a commit hash, use fallback
                    version = "1.7.0-dev"

            return version

    except (subprocess.SubprocessError, FileNotFoundError):
        # Git not available or not in a git repo
        pass

    # Fallback: read version baked in at Docker build time via APP_VERSION build arg.
    # Falls back to "dev" if not set (e.g. local runs without git).
    import os

    baked = os.environ.get("APP_VERSION", "dev")
    # Strip leading 'v' in case the tag format (e.g. v1.8.0) was passed directly
    return baked.lstrip("v") if baked else "dev"


# Cache the version at import time
__version__ = get_version()
