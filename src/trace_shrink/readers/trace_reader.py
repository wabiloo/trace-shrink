from abc import ABC
from typing import Dict, List, Optional, Pattern

import yarl

from ..abr import ManifestStream
from ..entries.trace_entry import TraceEntry
from ..trace import DecoratedUrl, Trace
from ..utils.formats import Format


class TraceReader(ABC):
    """
    Internal abstract base class for all trace readers (HAR, Proxyman, etc).

    This is an internal implementation detail. Users should use `open_trace(path)`
    which returns a `Trace` object directly.
    """

    def __init__(self, trace: Optional[Trace] = None):
        self._trace = trace or Trace()

    @property
    def trace(self) -> Trace:
        return self._trace



