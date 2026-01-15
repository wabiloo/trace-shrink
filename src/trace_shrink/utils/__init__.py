"""Utility helpers for trace_shrink.

Expose submodules so documentation tooling and griffe can discover
`trace_shrink.utils.formats` reliably.
"""
from . import formats, http_utils, highlight

__all__ = ["formats", "http_utils", "highlight"]
