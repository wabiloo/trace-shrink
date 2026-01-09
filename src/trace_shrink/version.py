"""
Utility functions for retrieving package version information.
"""
import os
from importlib.metadata import version as get_package_version


def get_package_version() -> str:
    """
    Get the package version dynamically from package metadata.

    Returns:
        Package version string, or "unknown" if version cannot be determined.
    """
    try:
        return get_package_version("trace-shrink")
    except Exception:
        # Fallback: try to read from pyproject.toml manually
        try:
            pyproject_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "pyproject.toml",
            )
            with open(pyproject_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("version") and "=" in line:
                        # Extract version from line like: version = "0.3.0"
                        version = line.split("=", 1)[1].strip().strip('"').strip("'")
                        return version
        except Exception:
            pass
        return "unknown"

