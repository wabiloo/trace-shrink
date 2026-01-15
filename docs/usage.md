# Usage Guide

This guide provides a quick overview of how to use `trace-shrink` to analyze your network capture files.

## Opening an Archive

The main entry point to the library is the `open_trace` function. It automatically detects the file type (HAR, Proxyman, Bodylogger, or multifile directory) and returns a `Trace` object. The appropriate reader is used internally to load the file, but you work directly with the `Trace` object.

```python
from trace_shrink import open_trace

try:
    # Open a HAR file
    har_trace = open_trace("path/to/your/capture.har")

    # Or open a Proxyman log
    proxyman_trace = open_trace("path/to/your/capture.proxymanlogv2")

    # Or open a Bodylogger file
    bodylogger_trace = open_trace("path/to/your/capture.log")

    # Or open a multifile directory archive
    multifile_trace = open_trace("path/to/your/capture_folder")

    print(f"Successfully opened trace with {len(har_trace)} entries.")

except FileNotFoundError:
    print("Error: The file was not found.")
except ValueError as e:
    print(f"Error: {e}")

```

**Note**: Bodylogger files (.log) are read-only. You cannot modify or save changes to them.

## Iterating and Filtering Entries

Once you have a `Trace` object, you can iterate over its `TraceEntry` objects or use the built-in methods to filter them.

### Basic Iteration

```python
from trace_shrink import open_trace

trace = open_trace("path/to/your/capture.har")

for entry in trace:
    print(f"[{entry.index}] {entry.request.method} {entry.request.url} -> {entry.response.status_code}")
```

### Filtering

The `Trace` class provides multiple filtering methods:

```python
from trace_shrink import open_trace

trace = open_trace("path/to/your/capture.har")

# General filter method - combine multiple criteria
api_calls = trace.filter(host="api.example.com", mime_type="application/json")
print(f"Found {len(api_calls)} JSON API calls")

# Filter by host
host_entries = trace.get_entries_by_host("example.com")

# Filter by exact URL
url_entries = trace.get_entries_for_url("https://example.com/manifest.mpd")

# Filter by URL path
path_entries = trace.get_entries_by_path("/api/v1/data")

# Filter by partial URL (substring or regex pattern)
partial_entries = trace.get_entries_for_partial_url("manifest")

# Get specific entry by ID
entry = trace.get_entry_by_id("entry-123")

# Get multiple entries by IDs
entries = trace.get_entries_by_ids(["entry-1", "entry-2", "entry-3"])

# Navigate to next/previous entry in a manifest stream
next_entry = trace.get_next_entry_by_id("entry-123", direction=1, n=1)  # Next
prev_entry = trace.get_next_entry_by_id("entry-123", direction=-1, n=1)  # Previous
```

## Working with ABR Streams

`trace-shrink` provides high-level APIs to simplify working with Adaptive Bitrate (ABR) streams like HLS and DASH.

### Finding Manifest URLs

You can automatically detect all ABR manifest URLs within a capture using the `get_abr_manifest_urls` method. This is more reliable than filtering by MIME type alone as it also inspects URLs.

```python
from trace_shrink import open_trace, Format

trace = open_trace("path/to/your/capture.har")

# Get all ABR manifest URLs (HLS & DASH)
manifest_urls = trace.get_abr_manifest_urls()

print("Found ABR Manifests:")
for decorated_url in manifest_urls:
    print(f"- URL: {decorated_url.url}")
    print(f"  Format: {decorated_url.format}")

# You can also filter by a specific format (using string or Format enum)
hls_urls = trace.get_abr_manifest_urls(format="hls")
# Or using Format enum:
# hls_urls = trace.get_abr_manifest_urls(format=Format.HLS)
print(f"\\nFound {len(hls_urls)} HLS manifest(s).")
```

### ManifestStream

A `ManifestStream` represents the sequence of requests made to a single manifest URL in chronological order (for example, repeated GETs of the same HLS playlist). It is useful to analyze manifest refreshes, compare versions over time, and navigate entries by time or position.

You can get a `ManifestStream` from a `Trace` by passing a manifest URL (as `yarl.URL` or string) to `get_manifest_stream()`.

```python
from trace_shrink import open_trace

trace = open_trace("path/to/your/capture.har")
manifest_urls = trace.get_abr_manifest_urls()

if manifest_urls:
    # Use the first detected manifest URL
    manifest_stream = trace.get_manifest_stream(manifest_urls[0].url)
    print(f"Manifest stream contains {len(manifest_stream)} entries")
    # Iterate chronological entries
    for entry in manifest_stream:
        print(entry.timeline.request_start, entry.response.status_code)

    # Find entry near a given time
    from datetime import datetime, timezone
    target = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    found = manifest_stream.find_entry_by_time(target, position="nearest", tolerance=2.0)
    if found:
        print("Closest entry at", found.timeline.request_start)
```

#### Advanced ManifestStream Operations

The `ManifestStream` class provides additional methods for time-based navigation:

```python
from datetime import datetime, timezone, timedelta

# Find entry by time with tolerance
target_time = datetime(2026, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
entry = manifest_stream.find_entry_by_time(
    target_time,
    position="nearest",  # or "before", "after"
    tolerance=5.0  # seconds
)

# Navigate relative to a specific entry
current_entry = manifest_stream.entries[5]
next_entry = manifest_stream.get_relative_entry(current_entry, direction=1, n=1)  # Next entry
previous_entry = manifest_stream.get_relative_entry(current_entry, direction=-1, n=1)  # Previous
third_next = manifest_stream.get_relative_entry(current_entry, direction=1, n=3)  # Skip ahead 3

# Get the original path of the manifest
manifest_path = manifest_stream.get_original_path()
```

### Configuring ABR Detection

You can define what entries are considered to be containing manifests and/or part of a manifest stream, by configuring the ABR detector.

#### Ignore query parameters

If there is a query parameter that appears on some URLs that look like manifest URLs but are not (eg. sidecar files), you can customize which query parameters to ignore:

```python
from trace_shrink import open_trace

# Open the trace and configure the ABR detector to ignore specific query params
trace = open_trace("path/to/your/capture.har")

# Treat URLs that do not contain specific query params
trace.abr_detector.ignore_query_params(["bk-ml", "token"])  # method chains and accepts a string or list

# Now retrieve deduplicated manifest URLs
manifest_urls = trace.get_abr_manifest_urls()
for d in manifest_urls:
    print(d.url, d.format)

# You can then extract a ManifestStream for a chosen manifest URL as usual:
manifest_stream = trace.get_manifest_stream(manifest_urls[0].url)
```

## Converting / Exporting

You can export entries from a `Trace` to supported archive formats. The `Exporter`
class provides convenient instance and class methods for exporting to different formats, in particular HAR or Proxyman Logs v2. 

Use the instance API when you have a `Trace`, or the class methods when you already have a list of `TraceEntry` objects.

```python
from trace_shrink import open_trace, Exporter

# Open any trace file
trace = open_trace("path/to/capture.log")

# Create an exporter and convert to HAR
exporter = Exporter(trace)
exporter.to_har("output.har")

# Or convert to Proxyman format
exporter.to_proxyman("output.proxymanlogv2")

print(f"Converted {len(trace)} entries.")
```

You can also use the `Exporter` as a class method with specific entries:

```python
from trace_shrink import open_trace, Exporter

trace = open_trace("path/to/capture.har")

# Export only specific entries
filtered_entries = trace.filter(host="api.example.com")
Exporter.to_har("filtered.har", filtered_entries)
```


You can also export to the directory-based multifile format:

```python
from trace_shrink import open_trace, Exporter

trace = open_trace("path/to/capture.har")
Exporter(trace).to_multifile("output_folder")

# Or as a class method when you already have a list of entries:
Exporter.to_multifile("output_folder", trace.entries)
```

This covers the most common use cases for getting started with `trace-shrink`. For a detailed list of all available classes and methods, please see the [API Reference](./api.md). 