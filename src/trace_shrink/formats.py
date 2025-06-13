from __future__ import annotations

from enum import Enum
from typing import Optional

import yarl


class Format(Enum):
    HLS = "HLS"
    DASH = "DASH"

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
        format = Format.from_mime_type(mime_type)
        if format:
            return format
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
