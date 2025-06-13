from enum import Enum

import yarl


class Format(Enum):
    HLS = "HLS"
    DASH = "DASH"


MIME_TYPES = {
    Format.HLS: [
        "application/vnd.apple.mpegurl",
        "application/x-mpegurl",
        "application/x-mpegURL",
    ],
    Format.DASH: ["application/dash+xml", "application/dash-xml"],
}


def is_mime_type(mime_type: str, mime_type_key: str) -> bool:
    return mime_type in MIME_TYPES[mime_type_key]


def is_dash_mime_type(mime_type: str) -> bool:
    return is_mime_type(mime_type, "DASH")


def is_abr_mime_type(mime_type: str) -> bool:
    return is_mime_type(mime_type, "HLS") or is_mime_type(mime_type, "DASH")


def is_string_content(mime_type: str) -> bool:
    # check if the mime type is a content-type for HLS or DASH formats, based on the MIME_TYPES dictionary
    return any(mime_type in mime_types for mime_types in MIME_TYPES.values())


def get_abr_format_from_mime_type(mime_type: str) -> str:
    if is_mime_type(mime_type, Format.HLS):
        return Format.HLS
    elif is_mime_type(mime_type, Format.DASH):
        return Format.DASH


def get_abr_format_from_extension(extension: str) -> str:
    if extension == "m3u8":
        return Format.HLS
    elif extension == "mpd":
        return Format.DASH
    return None


def get_abr_format_from_url(url: yarl.URL) -> str:
    # extract the extension from the last part of the path
    last_part = url.path.split("/")[-1]
    extension = last_part.split(".")[-1]
    return get_abr_format_from_extension(extension)


def get_abr_format(mime_type: str, url: yarl.URL) -> str:
    abr_format = get_abr_format_from_mime_type(mime_type)
    if abr_format is None:
        abr_format = get_abr_format_from_url(url)
    return abr_format
