"""Entry types exposed by trace_shrink.entries

This module re-exports the main TraceEntry implementations so users can
`from trace_shrink.entries import TraceEntry, HarEntry, MultiFileTraceEntry`.
"""
from .bodylogger_entry import BodyLoggerEntry
from .har_entry import HarEntry
from .multifile_entry import MultiFileTraceEntry
from .proxyman_entry import ProxymanLogV2Entry
from .requests_entry import RequestsResponseTraceEntry
from .trace_entry import (
                          RequestDetails,
                          ResponseBodyDetails,
                          ResponseDetails,
                          TimelineDetails,
                          TraceEntry,
)

__all__ = [
    "TraceEntry",
    "RequestDetails",
    "ResponseDetails",
    "ResponseBodyDetails",
    "TimelineDetails",
    "HarEntry",
    "MultiFileTraceEntry",
    "ProxymanLogV2Entry",
    "BodyLoggerEntry",
    "RequestsResponseTraceEntry",
]
