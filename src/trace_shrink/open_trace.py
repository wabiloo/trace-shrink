from pathlib import Path
from typing import Union

from .readers.bodylogger_reader import BodyLoggerReader
from .readers.har_reader import HarReader
from .readers.multifile_reader import MultiFileFolderReader
from .readers.proxyman_log_reader import ProxymanLogV2Reader
from .trace import Trace


def detect_format(path: Union[str, Path]) -> str:
    """
    Detect the format of a trace file from its path.

    Args:
        path: Path to the trace file or directory (as string or Path object)

    Returns:
        Format string: "har", "proxymanlogv2", "bodylogger" (for .log files), or "multifile"

    Raises:
        ValueError: If the format cannot be determined from the path
    """
    path_obj = Path(path)

    # Check if it's a directory (multifile archive)
    if path_obj.is_dir():
        return "multifile"

    # Otherwise, detect from file extension
    ext = path_obj.suffix.lower()

    if ext == ".har":
        return "har"
    elif ext == ".proxymanlogv2":
        return "proxymanlogv2"
    elif ext == ".log":
        return "bodylogger"
    else:
        raise ValueError(
            f"Unsupported trace file extension: {ext}. "
            f"Supported formats: .har, .proxymanlogv2, .log, or directory (multifile)"
        )


def open_trace(path: str) -> Trace:
    """
    Factory function to open a trace file and return a Trace object.
    Supports .har, .proxymanlogv2, and .log (bodylogger) files.

    The appropriate reader is used internally to load the file, but the returned
    Trace object is the primary interface for accessing entries, filtering them,
    extracting ManifestStream, etc.

    The returned Trace object will have 'path' and 'format' properties set.

    Raises ValueError for unknown/unsupported file formats.
    """
    format = detect_format(path)

    if format == "multifile":
        reader = MultiFileFolderReader(path)
    elif format == "har":
        reader = HarReader(path)
    elif format == "proxymanlogv2":
        reader = ProxymanLogV2Reader(path)
    elif format == "bodylogger":
        reader = BodyLoggerReader(path)
    else:
        # This should never happen if detect_format is correct, but handle it anyway
        raise ValueError(f"Unsupported trace format: {format}")

    trace = reader.trace
    # Set path and format metadata
    trace.metadata["path"] = path
    trace.metadata["format"] = format
    return trace
