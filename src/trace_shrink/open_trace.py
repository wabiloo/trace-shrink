import os

from .readers.bodylogger_reader import BodyLoggerReader
from .readers.har_reader import HarReader
from .readers.multifile_reader import MultiFileFolderArchive
from .readers.proxyman_log_reader import ProxymanLogV2Reader
from .readers.trace_reader import TraceReader


def open_trace(path: str) -> TraceReader:
    """
    Factory function to open a trace file and return the correct TraceReader subclass.
    Supports .har, .proxymanlogv2, and .log (bodylogger) files.

    Raises ValueError for unknown/unsupported file formats.
    """
    if os.path.isdir(path):
        return MultiFileFolderArchive(path)

    ext = os.path.splitext(path)[1].lower()
    if ext == ".har":
        return HarReader(path)
    elif ext == ".proxymanlogv2":
        return ProxymanLogV2Reader(path)
    elif ext == ".log":
        return BodyLoggerReader(path)
    else:
        raise ValueError(f"Unsupported trace file extension: {ext}")
