"""
This script processes Proxyman log files to analyze and map Dynamic Ad Insertion (DAI) segments in video streams.

It uses the ProxymanLogV2Reader to read log files and extract entries related to specific hosts.
The script identifies and compares source and service markers, outputs summaries, and maps live segments to DAI segments.
"""

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from time import time
from typing import Optional

import m3u8
import threefive

# Import ProxymanEntry only needed if we add type hints later, not for runtime
# from dai_tracker.proxyman_entry import ProxymanEntry
from trace_shrink.proxyman_log_reader import ProxymanLogV2Reader

MAX_ENTRIES = 20000
SOURCE_HOST = "ndtv24x7elemarchana.akamaized.net"
SERVICE_HOST = "stream.broadpeak.io"


@dataclass
class SpanInfo:
    info: str
    after_segment: str
    from_segment: str
    from_pdt: str
    to_segment: Optional[str] = None
    to_pdt: Optional[str] = None
    payload: Optional[str] = None

    def actual_duration(self):
        if self.to_pdt is None:
            return None
        return (self.to_pdt - self.from_pdt).total_seconds()

    def __str__(self):
        return (
            f"{self.from_pdt} -> {self.to_pdt} ({self.actual_duration()}): {self.info}"
        )


class SpanDb:
    def __init__(self):
        self._db = dict()
        self._open_spans = []
        self._last_pdt = datetime.min.replace(tzinfo=timezone.utc)

    def add(self, span: SpanInfo):
        self._db[span.from_pdt] = span
        if span.to_pdt is None:
            self._open_spans.append(span)

    def close_last_span(self, span: SpanInfo):
        self._db[span.from_pdt] = span
        if span.to_pdt is not None:
            self._open_spans.remove(span)

    def __getitem__(self, key):
        return self._db[key]

    def __contains__(self, key):
        return key in self._db

    def get(self, key):
        return self._db.get(key)

    def set_last_pdt(self, pdt: datetime):
        self._last_pdt = pdt

    def get_last_pdt(self):
        return self._last_pdt

    def get_last_open_span(self) -> Optional[SpanInfo]:
        if self._open_spans:
            return self._open_spans[-1]
        return None

    def items(self):
        return self._db.items()

    def print_summary(self):
        summary = ""
        for span in self._db.values():
            summary += (
                f"- {span.from_pdt} -> {span.to_pdt} ({span.actual_duration()})\n"
                f"  {span.info}\n"
            )
        print(summary)


def main():
    parser = argparse.ArgumentParser(
        description="List entries from a Proxyman log file and show response body snippets."
    )
    parser.add_argument(
        "logfile", help="Path to the .proxymanlog or .proxymanlogv2 file"
    )

    args = parser.parse_args()

    log_file_path = args.logfile

    if not os.path.exists(log_file_path):
        print(f"Error: Log file not found: {log_file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        print(f"Processing log file: {log_file_path}\n")
        time_before = time()
        reader = ProxymanLogV2Reader(log_file_path)
        time_after = time()
        print(
            f"Time taken to initialize log reader: {time_after - time_before} seconds"
        )
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"Error initializing log reader: {e}", file=sys.stderr)
        sys.exit(1)

    source_marker_db = scan_source_entries(reader, SOURCE_HOST)
    service_marker_db = scan_service_entries(reader, SERVICE_HOST)

    print("\nSource markers:")
    source_marker_db.print_summary()

    print("\nService markers:")
    service_marker_db.print_summary()

    mappings = get_mappings(source_marker_db, service_marker_db)

    print("\nMappings:")
    for pdt, (source_span, service_span) in mappings.items():
        print()
        print(f"Live:    {str(source_span)}")
        print(f" >> DAI: {str(service_span)}")


def scan_source_entries(reader: ProxymanLogV2Reader, host: str):
    source_entries = reader.list_entries_by_host(host)
    total_entries = len(source_entries)

    source_entries = reader.get_entries_by_host(host)

    span_db = SpanDb()

    counter = 0
    for entry in source_entries:
        print(f"Scanning entry: {entry.id} ({counter}/{total_entries})")
        body = entry.content
        if body:
            try:
                playlist = m3u8.loads(body)
                new_marker_found = scan_source_segments(playlist, span_db)
                if new_marker_found:
                    print(span_db)
            except Exception as e:
                print(f"Error parsing M3U8: {e}")

        counter += 1
        if counter > MAX_ENTRIES:
            break

    return span_db


def scan_service_entries(reader: ProxymanLogV2Reader, host: str):
    service_entries = reader.list_entries_by_host(host)
    total_entries = len(service_entries)

    service_entries = reader.get_entries_by_host(host)

    span_db = SpanDb()

    counter = 0
    for entry in service_entries:
        print(f"Scanning entry: {entry.id} ({counter}/{total_entries})")
        body = entry.content
        if body:
            try:
                playlist = m3u8.loads(body)
                new_marker_found = scan_service_segments(playlist, span_db)
                if new_marker_found:
                    print(span_db)
            except Exception as e:
                print(f"Error parsing M3U8: {e}")

        counter += 1
        if counter > MAX_ENTRIES:
            break

    return span_db


def scan_source_segments(playlist: m3u8.M3U8, span_db: SpanDb):
    new_marker_found = False
    for i, segment in enumerate(playlist.segments):
        # skip any previously seen segments
        if segment.current_program_date_time < span_db.get_last_pdt():
            continue
        else:
            span_db.set_last_pdt(segment.current_program_date_time)

        if segment.cue_out_start:
            pdt = segment.current_program_date_time
            if pdt not in span_db:
                cue = threefive.Cue(segment.scte35)

                new_span = SpanInfo(
                    after_segment=playlist.segments[i - 1].uri,
                    from_segment=segment.uri,
                    from_pdt=pdt,
                    payload=segment.scte35,
                    info=f"{segment.scte35} ({cue.command.splice_event_id}/{segment.scte35_duration})",
                )
                span_db.add(new_span)
                new_marker_found = True

        if segment.cue_in:
            last_open_span = span_db.get_last_open_span()
            if last_open_span:
                last_open_span.to_segment = segment.uri
                last_open_span.to_pdt = segment.current_program_date_time
                span_db.close_last_span(last_open_span)

    return new_marker_found


def scan_service_segments(playlist: m3u8.M3U8, span_db: SpanDb):
    new_adreplacement_found = False
    for i, segment in enumerate(playlist.segments):
        # skip any previously seen segments
        if segment.current_program_date_time < span_db.get_last_pdt():
            continue
        else:
            span_db.set_last_pdt(segment.current_program_date_time)

        if segment.discontinuity:
            open_span = span_db.get_last_open_span()

            if "bpkio-jitt" in segment.uri:
                segment_filename = segment.uri.split("?")[0].split("/")[-1]

                # first one?  then it's a new ad break
                if not open_span:
                    print(f"JITT discontinuity at {segment_filename}")
                    new_span = SpanInfo(
                        after_segment=playlist.segments[i - 1].uri,
                        from_segment=segment.uri,
                        from_pdt=segment.current_program_date_time,
                        info="ad replacement: ",
                    )
                    span_db.add(new_span)
                    new_adreplacement_found = True

                # otherwise it's a new ad
                else:
                    open_span.info += replacement_type(segment.uri)

            else:
                if open_span:
                    open_span.to_segment = segment.uri
                    open_span.to_pdt = segment.current_program_date_time
                    span_db.close_last_span(open_span)

    return new_adreplacement_found


def get_mappings(source_marker_db: SpanDb, service_marker_db: SpanDb):
    mappings = {}
    for pdt, source_span in source_marker_db.items():
        if service_span := service_marker_db.get(pdt):
            mappings[pdt] = (source_span, service_span)
        else:
            mappings[pdt] = (source_span, None)

    return mappings


def replacement_type(segment_uri: str):
    if "slate" in segment_uri:
        return "S"
    else:
        return "A"


if __name__ == "__main__":
    main()
