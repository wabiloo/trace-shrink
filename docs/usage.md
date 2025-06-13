# Usage Guide

This guide provides a quick overview of how to use `trace-shrink` to analyze your network capture files.

## Opening an Archive

The main entry point to the library is the `open_archive` function. It automatically detects the file type (HAR or Proxyman) and returns an appropriate `ArchiveReader` instance.

```python
from trace_shrink import open_archive

try:
    # Open a HAR file
    har_archive = open_archive("path/to/your/capture.har")

    # Or open a Proxyman log
    proxyman_archive = open_archive("path/to/your/capture.proxymanlogv2")

    print(f"Successfully opened archive with {len(har_archive)} entries.")

except FileNotFoundError:
    print("Error: The file was not found.")
except ValueError as e:
    print(f"Error: {e}")

```

## Iterating and Filtering Entries

Once you have an `ArchiveReader`, you can iterate over its `TraceEntry` objects or use the built-in methods to filter them.

### Basic Iteration

```python
from trace_shrink import open_archive

archive = open_archive("path/to/your/capture.har")

for entry in archive:
    print(f"[{entry.index}] {entry.request.method} {entry.request.url} -> {entry.response.status_code}")
```

### Filtering

The `filter` method allows you to find specific entries based on criteria like host, URL, or MIME type.

```python
from trace_shrink import open_archive

archive = open_archive("path/to/your/capture.har")

# Find all entries for a specific host
api_calls = archive.filter(host="api.example.com")
print(f"Found {len(api_calls)} entries for api.example.com")

# Find all HLS manifest files
hls_manifests = archive.filter(mime_type="application/vnd.apple.mpegurl")
for manifest in hls_manifests:
    print(f"Found HLS manifest: {manifest.request.url}")
```

## Working with ABR Streams

`trace-shrink` provides high-level APIs to simplify working with Adaptive Bitrate (ABR) streams like HLS and DASH.

### Finding Manifest URLs

You can automatically detect all ABR manifest URLs within a capture using the `get_abr_manifest_urls` method. This is more reliable than filtering by MIME type alone as it also inspects URLs.

```python
from trace_shrink import open_archive

archive = open_archive("path/to/your/capture.har")

# Get all ABR manifest URLs (HLS & DASH)
manifest_urls = archive.get_abr_manifest_urls()

print("Found ABR Manifests:")
for decorated_url in manifest_urls:
    print(f"- URL: {decorated_url.url}")
    print(f"  Format: {decorated_url.format}")

# You can also filter by a specific format
hls_urls = archive.get_abr_manifest_urls(format="hls")
print(f"\\nFound {len(hls_urls)} HLS manifest(s).")
```

### Extracting a Manifest Stream

Once you have a manifest URL, you can use `get_manifest_stream` to get a `ManifestStream` object. This object contains all the successive requests made to that single manifest URL, allowing you to analyze how an HLS playlist or DASH manifest changed over time.

```python
from trace_shrink import open_archive

archive = open_archive("path/to/your/capture.har")
manifest_urls = archive.get_abr_manifest_urls()

if not manifest_urls:
    print("No ABR manifests found in this capture.")
else:
    # Get the stream for the first manifest found
    main_manifest_url = manifest_urls[0].url
    print(f"Extracting stream for: {main_manifest_url}\\n")

    try:
        manifest_stream = archive.get_manifest_stream(main_manifest_url)

        print(f"Stream has {len(manifest_stream)} entries (refreshes).")
        print("Timeline of manifest refreshes:")
        for entry in manifest_stream:
            # The entries in the stream are the same TraceEntry objects
            print(f"- Refresh at {entry.timeline.request_start}")

    except ValueError as e:
        print(f"Error getting manifest stream: {e}")
```

This covers the most common use cases for getting started with `trace-shrink`. For a detailed list of all available classes and methods, please see the [API Reference](./api.md). 