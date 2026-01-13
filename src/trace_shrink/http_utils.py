"""
HTTP utility functions.
"""


def get_status_text(status_code: int) -> str:
    """
    Get HTTP status text for a status code.

    Args:
        status_code: The HTTP status code.

    Returns:
        The status text (e.g., "OK" for 200), or "Unknown" if not found.
    """
    status_texts = {
        200: "OK",
        201: "Created",
        204: "No Content",
        301: "Moved Permanently",
        302: "Found",
        304: "Not Modified",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
    }
    return status_texts.get(status_code, "Unknown")

