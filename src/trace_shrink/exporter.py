"""
Export functionality for converting between trace archive formats.
"""

from typing import List, Optional

from .entries.trace_entry import TraceEntry
from .trace import Trace
from .writers.har_writer import HarWriter
from .writers.multifile_writer import MultiFileWriter
from .writers.proxyman_writer import ProxymanWriter


class _ExportMethod:
    """Descriptor that allows a method to work as both class and instance method."""

    def __init__(self, export_func):
        self.export_func = export_func

    def __get__(self, obj, objtype=None):
        if obj is None:
            # Called on class: return a function that requires entries
            def class_method(output_path: str, entries: List[TraceEntry]) -> None:
                return self.export_func(entries, output_path)

            return class_method
        else:
            # Called on instance: return a function that can use reader entries
            def instance_method(
                output_path: str, entries: Optional[List[TraceEntry]] = None
            ) -> None:
                if entries is None:
                    entries = obj._trace.entries
                return self.export_func(entries, output_path)

            return instance_method


class Exporter:
    """
    Exports entries to different formats (HAR, Proxyman, etc.).

    The exporter works with any list of TraceEntry objects and converts them
    using the unified TraceEntry interface.

    Can be used as class methods for direct export, or instantiated with a
    Trace for convenience when exporting all entries.

    Examples:
        # As class method (entries required)
        Exporter.to_har("output.har", entries)

        # As instance method (entries optional, defaults to all trace entries)
        exporter = Exporter(trace)
        exporter.to_har("output.har")  # Exports all entries
        exporter.to_har("output.har", filtered_entries)  # Exports specific entries
    """

    def __init__(self, source: Trace):
        """
        Initialize the exporter with a Trace container.

        Args:
            source: The Trace instance to export from.
        """
        if not isinstance(source, Trace):
            raise TypeError("Exporter source must be a Trace instance.")
        self._trace = source

    to_har = _ExportMethod(HarWriter.write)
    to_proxyman = _ExportMethod(ProxymanWriter.write)
    to_multifile = _ExportMethod(MultiFileWriter.write)
