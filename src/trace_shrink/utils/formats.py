from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Optional

import yarl

if TYPE_CHECKING:
    from ..entries.trace_entry import TraceEntry


class Format(Enum):
    HLS = "HLS"
    DASH = "DASH"

    def to_extension(self) -> str:
        """Get file extension for this format.

        Returns:
            Extension string with leading dot (e.g., ".m3u8", ".mpd")
        """
        if self == Format.HLS:
            return ".m3u8"
        elif self == Format.DASH:
            return ".mpd"
        return ""

    @staticmethod
    def from_extension(extension: str) -> Optional[Format]:
        if extension == "m3u8":
            return Format.HLS
        elif extension == "mpd":
            return Format.DASH
        return None

    @staticmethod
    def from_mime_type(mime_type: str) -> Optional[Format]:
        return MimeType(mime_type).to_format()

    @staticmethod
    def from_url(url: yarl.URL) -> Optional[Format]:
        return Format.from_extension(url.path.split(".")[-1])

    @staticmethod
    def from_path(url_path: str) -> Optional[Format]:
        return Format.from_extension(url_path.split(".")[-1])

    @staticmethod
    def from_url_or_mime_type(mime_type: str, url: yarl.URL) -> Optional[Format]:
        try:
            format = Format.from_mime_type(mime_type)
            if format:
                return format
        except ValueError:
            pass

        return Format.from_url(url)


class MimeType:
    MIME_TYPES = {
        Format.HLS: [
            "application/vnd.apple.mpegurl",
            "application/x-mpegurl",
            "application/x-mpegURL",
        ],
        Format.DASH: ["application/dash+xml", "application/dash-xml"],
    }

    def __init__(self, mime_type: str):
        if mime_type is None:
            raise ValueError("Mime type cannot be None")
        self.mime_type = mime_type.split(";")[0].strip()

    def __str__(self) -> str:
        return self.mime_type

    def is_format(self, format: Format) -> bool:
        return self.mime_type in self.MIME_TYPES[format]

    def is_dash(self) -> bool:
        return self.is_format(Format.DASH)

    def is_hls(self) -> bool:
        return self.is_format(Format.HLS)

    def is_abr_manifest(self) -> bool:
        return self.is_hls() or self.is_dash()

    def has_text_content(self) -> bool:
        # check if the mime type is a content-type for HLS or DASH formats, based on the MIME_TYPES dictionary
        return self.is_abr_manifest()

    def to_format(self) -> Optional[Format]:
        if self.is_hls():
            return Format.HLS
        elif self.is_dash():
            return Format.DASH
        return None


def get_extension_for_entry(entry: "TraceEntry") -> str:
    """Get file extension for a TraceEntry.

    Tries content-type/mime-type first, then falls back to URL extension.

    Args:
        entry: The TraceEntry to get extension for

    Returns:
        Extension string with leading dot (e.g., ".m3u8", ".mpd") or empty string if unknown
    """
    # Try content-type/mime-type first
    if entry.response.mime_type:
        try:
            mime_type = MimeType(entry.response.mime_type)

            # Try ABR format (HLS/DASH)
            format = mime_type.to_format()
            if format:
                return format.to_extension()

            # Handle other common mime types
            mime_to_ext = {
                "application/vnd.vast+xml": ".xml",
                "application/vnd.vmap+xml": ".xml",
                "application/xml": ".xml",
                "text/xml": ".xml",
                "application/json": ".json",
                "text/json": ".json",
            }
            extension = mime_to_ext.get(mime_type.mime_type.lower(), "")
            if extension:
                return extension
        except ValueError:
            pass

    # Fall back to URL extension
    url = entry.request.url
    if url.path:
        path_parts = url.path.split(".")
        if len(path_parts) > 1:
            ext = path_parts[-1].lower()
            if ext:
                return f".{ext}"

    return ""
