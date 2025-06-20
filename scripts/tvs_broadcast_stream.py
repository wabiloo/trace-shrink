"""
This script processes HAR files to extract and analyze ads in a TV Segmentée stream.

It uses the HarReader class to detect the HLS playlist from a HAR file.
The PlaylistScanner class is used to identify and extractcomplete ads within these manifests.

The analysis outputs a table of ads, and compares the marker start and end with the actual start and end of the ad (from the segments PDT).

The script then extracts the segments to files, with a separate directory for each ad.

⚠️ This script requires some packages not part of the trace-shrink package. 
You must install them manually, eg. `uv pip install m3u8 threefive rich`
"""

import argparse
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import m3u8
from rich.console import Console
from rich.table import Table
from threefive import Cue, SegmentationDescriptor
from yarl import URL

from trace_shrink import HarEntry, HarReader, open_archive

console = Console()


@dataclass
class OriginalAd:
    id: str
    first_appearance: datetime
    daterange_id: str
    seg_num: int
    seg_total: int
    marker_start: datetime
    marker_end: Optional[datetime] = None
    segments: list[m3u8.Segment] = field(default_factory=list)
    break_id: Optional[str] = None

    def is_complete(self) -> bool:
        return self.marker_end is not None and self.marker_start is not None

    def add_segment(self, segment: m3u8.Segment):
        if not (any(s.media_sequence == segment.media_sequence for s in self.segments)):
            self.segments.append(segment)

    def set_break_id(self, break_id: str | None):
        if break_id is not None:
            self.break_id = break_id

    def first_ms(self) -> int:
        return self.segments[0].media_sequence

    def last_ms(self) -> int:
        return self.segments[-1].media_sequence

    def actual_start(self) -> datetime:
        if self.segments:
            return self.segments[0].current_program_date_time

    def actual_end(self) -> datetime:
        if self.segments:
            return self.segments[-1].current_program_date_time + timedelta(
                seconds=self.segments[-1].duration
            )

    def delta_start(self) -> timedelta:
        return self.marker_start - self.actual_start()

    def delta_end(self) -> timedelta:
        return self.marker_end - self.actual_end()


@dataclass
class AdCollection:
    ads: list[OriginalAd] = field(default_factory=list)

    def get(self, id: str) -> OriginalAd | None:
        for ad in self.ads:
            if ad.id == id:
                return ad
        return None

    def add_ad(self, ad: OriginalAd):
        if not (any(a.id == ad.id for a in self.ads)):
            self.ads.append(ad)

    def add_ads(self, new_ads: list[OriginalAd]):
        for ad in new_ads:
            self.add_ad(ad)

    def __iter__(self):
        return iter(self.ads)

    def __len__(self):
        return len(self.ads)


class PlaylistScanner:
    def __init__(self, playlist: m3u8.Playlist, first_appearance: datetime):
        self.playlist = playlist
        self.first_appearance = first_appearance

    def find_complete_ads(self) -> list[OriginalAd]:
        """
        Find all ads that have a complete set of segments.
        """
        ads = []
        pa_starts = self._retrieve_segments_by_segmentation_type(48)
        pa_ends = self._retrieve_segments_by_segmentation_type(49)

        # find pairs for the same event id
        for pa_start_segment, pa_start_daterange, pa_start_descriptor in pa_starts:
            for pa_end_segment, pa_end_daterange, pa_end_descriptor in pa_ends:
                if (
                    pa_start_descriptor.segmentation_event_id
                    == pa_end_descriptor.segmentation_event_id
                ):
                    ad = OriginalAd(
                        id=int(pa_start_descriptor.segmentation_event_id, 16),
                        daterange_id=pa_start_daterange.id,
                        first_appearance=self.first_appearance,
                        seg_num=pa_start_descriptor.segment_num,
                        seg_total=pa_start_descriptor.segments_expected,
                        marker_start=datetime.fromisoformat(
                            pa_start_daterange.start_date
                        ),
                        marker_end=datetime.fromisoformat(pa_end_daterange.start_date),
                    )
                    ad.segments = self.extract_segments_range_by_ms(
                        pa_start_segment.media_sequence,
                        pa_end_segment.media_sequence - 1,
                    )

                    # set the break id by extracting from the collocated CallAdServer
                    cue = Cue(pa_start_daterange.scte35_cmd)
                    cas_descriptor = next(
                        (d for d in cue.descriptors if d.segmentation_type_id == 2),
                        None,
                    )
                    if cas_descriptor:
                        ad.break_id = cas_descriptor.segmentation_upid["break_code"]

                    ads.append(ad)
        return ads

    def extract_segments_range_by_ms(
        self, ms_start: int, ms_end: int
    ) -> list[m3u8.Segment]:
        """
        Extract all segments that have a media sequence number between ms_start and ms_end.
        """
        segments: list[m3u8.Segment] = []
        for segment in self.playlist.segments:
            if segment.media_sequence >= ms_start and segment.media_sequence <= ms_end:
                segments.append(segment)
        return segments

    def _retrieve_segments_by_segmentation_type(
        self, segmentation_type_id: int
    ) -> list[Tuple[m3u8.Segment, m3u8.DateRange, SegmentationDescriptor]]:
        """
        Retrieve all segments that have attached to them a SCTE35 descriptor with the given segmentation type id.
        """
        segments: list[Tuple[m3u8.Segment, m3u8.DateRange, SegmentationDescriptor]] = []
        for segment in self.playlist.segments:
            if segment.dateranges:
                daterange: m3u8.DateRange
                for daterange in segment.dateranges:
                    cue = Cue(daterange.scte35_cmd)
                    if cue.descriptors:
                        for descriptor in cue.descriptors:
                            if descriptor.segmentation_type_id == segmentation_type_id:
                                segments.append((segment, daterange, descriptor))
        return segments

    def first_break_id(self) -> int:
        break_starts = self._retrieve_segments_by_segmentation_type(34)
        if break_starts:
            return int(break_starts[0][2].segmentation_event_id, 16)
        return None


def collect_ads(manifest_entries: list[HarEntry]) -> AdCollection:
    ads = AdCollection()

    for entry in manifest_entries:
        # print(f"Scanning entry {entry.id} @ {entry.timeline.request_start}")
        manifest_body = entry.content

        manifest_obj = m3u8.loads(manifest_body)
        playlist_scanner = PlaylistScanner(manifest_obj, entry.timeline.request_start)
        detected_ads = playlist_scanner.find_complete_ads()

        ads.add_ads(detected_ads)
    return ads


def print_ads(ads: AdCollection):
    table = Table(title="Ads")
    table.add_column("Break")
    table.add_column("ID")
    table.add_column("First Appearance")
    table.add_column("Num")
    table.add_column("Marker Start")
    table.add_column("Marker End")
    table.add_column("Segments")
    table.add_column("MSeqs")
    table.add_column("Actual Start")
    table.add_column("𝚫 Start")
    table.add_column("Actual End")
    table.add_column("𝚫 End")

    for ad in ads:
        delta_start_color = (
            "green" if math.fabs(ad.delta_start().total_seconds()) < 0.1 else "red"
        )
        delta_end_color = (
            "green" if math.fabs(ad.delta_end().total_seconds()) < 0.1 else "red"
        )

        table.add_row(
            str(ad.break_id) if ad.break_id else "",
            f"{ad.id} ({ad.daterange_id})",
            (
                ad.first_appearance.isoformat().split("T")[1][:12]
                if ad.first_appearance
                else ""
            ),
            f"{ad.seg_num}/{ad.seg_total}",
            ad.marker_start.isoformat().split("T")[1][:12] if ad.marker_start else "",
            ad.marker_end.isoformat().split("T")[1][:12] if ad.marker_end else "",
            str(len(ad.segments)),
            f"{ad.first_ms()}-{ad.last_ms()}",
            (
                ad.actual_start().isoformat().split("T")[1][:12]
                if ad.actual_start()
                else ""
            ),
            f"[{delta_start_color}]{str(round(ad.delta_start().total_seconds(), 2))}[/]",
            ad.actual_end().isoformat().split("T")[1][:12] if ad.actual_end() else "",
            f"[{delta_end_color}]{str(round(ad.delta_end().total_seconds(), 2))}[/]",
        )

    console.print(table)


def extract_ad_segments(ads: AdCollection, manifest_url: str, archive_reader):
    for ad in ads:
        print(f"Extracting segments for ad {ad.id}")
        for segment in ad.segments:
            # resolve the segment uri based on the manifest url
            segment_url = manifest_url.join(URL(segment.uri))

            # Fast lookup using the archive reader's indexed method
            segment_entries = archive_reader.get_entries_for_url(segment_url)

            if segment_entries:
                # save the segment to a file
                target_dir = Path("segments") / f"{ad.break_id}_{ad.id}_{ad.seg_num}"
                target_dir.mkdir(parents=True, exist_ok=True)
                with open(target_dir / f"{segment.uri}", "wb") as f:
                    f.write(segment_entries[0].content)
            else:
                print(f"Segment {segment.uri} not found")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze ads in TV Segmentée stream from HAR/Proxyman files"
    )
    parser.add_argument("har_file", help="Path to the HAR or Proxyman log file")
    args = parser.parse_args()

    archive_reader = open_archive(args.har_file)
    print(f"Archive loaded with {len(archive_reader)} total entries")

    manifest_urls = archive_reader.get_abr_manifest_urls()
    print(f"Found {len(manifest_urls)} manifest URLs:")
    for i, manifest_url in enumerate(manifest_urls):
        print(f"  {i}: {manifest_url.url} ({manifest_url.format})")

    if not manifest_urls:
        print("No manifest URLs found! Exiting.")
        return

    # Find the manifest with the most entries (most active)
    print("\nAnalyzing manifests to find the most active one...")
    best_manifest_url = None
    max_entries = 0

    for i, manifest_url in enumerate(manifest_urls):
        entries = archive_reader.get_entries_for_url(manifest_url.url)
        entry_count = len(entries)
        print(f"  Manifest {i}: {entry_count} entries")

        if entry_count > max_entries:
            max_entries = entry_count
            best_manifest_url = manifest_url.url

    selected_manifest_url = best_manifest_url
    print(
        f"\nSelected manifest URL (most active with {max_entries} entries): {selected_manifest_url}"
    )

    manifest_entries = archive_reader.get_entries_for_url(selected_manifest_url)

    detected_ads = collect_ads(manifest_entries)
    print(f"Detected {len(detected_ads)} ads total")
    print_ads(detected_ads)

    if detected_ads:
        extract_ad_segments(detected_ads, selected_manifest_url, archive_reader)
    else:
        print("No ads detected, skipping segment extraction.")


if __name__ == "__main__":
    main()
