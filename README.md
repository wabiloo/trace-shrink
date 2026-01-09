# trace-shrink

A Python package for analyzing HTTP traffic captures from HAR files or Proxyman logs, with a focus on ABR streams (HLS and MPEG-DASH). trace-shrink provides a unified API to detect ABR manifest URLs, extract requests, and analyze streaming sessions, in particular recorded from live streams in which the same manifest URL is requested multiple times for refreshes.

## Features

- Unified API for different trace file formats (.har and .proxymanlogv2)
- Detect ABR manifest URLs from captured HTTP traffic
- Extract and analyze streams of requests to ABR manifests
- Focus on live streaming scenarios with repeated manifest requests

## Documentation

See the full documentation for more details: https://wabiloo.github.io/trace-shrink/

## Installation

```bash
pip install trace-shrink
```

**Requirements:** Python 3.10 or higher

