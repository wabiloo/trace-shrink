"""
ABR Capture Inspector Library
"""

from .abr import ManifestStream
from .exporter import Exporter
from .open_trace import detect_format, open_trace
from .trace import DecoratedUrl, Trace
from .utils.formats import Format, MimeType

# Entries/readers/writers are intentionally not imported here. Use
# `from trace_shrink.entries import ...`, `trace_shrink.readers`, or
# `trace_shrink.writers` to access those symbols. This keeps the top-level
# namespace small and avoids eager imports.

__all__ = [
    "ManifestStream",
    "open_trace",
    "detect_format",
    "Exporter",
    "Trace",
    "Format",
    "MimeType",
    "DecoratedUrl",
]

# Keep lazy access to subpackages (so users can import trace_shrink.entries)
# but do not expose them as top-level names in __all__.
_subpackages = {
    "entries": "trace_shrink.entries",
    "readers": "trace_shrink.readers",
    "writers": "trace_shrink.writers",
}

def __getattr__(name: str):
    # Lazy import subpackages on attribute access (PEP 562)
    if name in _subpackages:
        import importlib

        mod = importlib.import_module(_subpackages[name])
        globals()[name] = mod
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    # Include lazy subpackages in dir() so completions and indexers see them
    return sorted(list(globals().keys()) + list(_subpackages.keys()))
