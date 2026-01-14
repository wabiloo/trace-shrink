import os

from .readers.bodylogger_reader import BodyLoggerReader
from .readers.har_reader import HarReader
from .readers.multifile_reader import MultiFileFolderReader
from .readers.proxyman_log_reader import ProxymanLogV2Reader
from .trace import Trace


def open_trace(path: str) -> Trace:
    """
    Factory function to open a trace file and return a Trace object.
    Supports .har, .proxymanlogv2, and .log (bodylogger) files.

    The appropriate reader is used internally to load the file, but the returned
    Trace object is the primary interface for accessing entries, filtering them,
    extracting ManifestStream, etc.

    Raises ValueError for unknown/unsupported file formats.
    """
    if os.path.isdir(path):
        reader = MultiFileFolderReader(path)
    else:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".har":
            reader = HarReader(path)
        elif ext == ".proxymanlogv2":
            reader = ProxymanLogV2Reader(path)
        elif ext == ".log":
            reader = BodyLoggerReader(path)
        else:
            raise ValueError(f"Unsupported trace file extension: {ext}")

    return reader.trace
