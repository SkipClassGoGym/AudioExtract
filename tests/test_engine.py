import json
import math
from pathlib import Path
import tempfile
import unittest

from audioextract.engine import Segment, render_export, save_export, timestamp, validate_source


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.segments = [Segment(0, 1.25, "Xin chào Việt Nam!"),
                         Segment(3661.9996, 3663.5, "Hẹn gặp lại.")]

    def test_timestamp_carries_milliseconds_into_minutes_and_hours(self):
        self.assertEqual(timestamp(59.9996), "00:01:00.000")
        self.assertEqual(timestamp(3599.9996, ","), "01:00:00,000")
        self.assertEqual(timestamp(360_000), "100:00:00.000")

    def test_srt_has_numbered_cues_original_timing_and_vietnamese(self):
        self.assertEqual(render_export(self.segments, "srt"),
                         "1\n00:00:00,000 --> 00:00:01,250\nXin chào Việt Nam!\n\n"
                         "2\n01:01:02,000 --> 01:01:03,500\nHẹn gặp lại.\n")

    def test_sub_millisecond_segment_still_has_positive_subtitle_duration(self):
        result = render_export([Segment(0, 0.0001, "Hi")], "srt")
        self.assertIn("00:00:00,000 --> 00:00:00,001", result)

    def test_vtt_escapes_subtitle_markup(self):
        result = render_export([Segment(2, 3, "A < B & C > D")], "vtt")
        self.assertTrue(result.startswith("WEBVTT\n\n"))
        self.assertIn("00:00:02.000 --> 00:00:03.000", result)
        self.assertIn("A &lt; B &amp; C &gt; D", result)

    def test_embedded_blank_line_does_not_break_subtitle_cue(self):
        result = render_export([Segment(0, 1, "First\n\nsecond")], "srt")
        self.assertIn("First second\n", result)

    def test_txt_contains_only_recognized_words(self):
        self.assertEqual(render_export(self.segments, "txt"), "Xin chào Việt Nam!\nHẹn gặp lại.\n")

    def test_json_keeps_partial_metadata_and_numeric_timestamps(self):
        result = json.loads(render_export(self.segments, "json", {"complete": False}))
        self.assertFalse(result["metadata"]["complete"])
        self.assertEqual(result["segments"][0], {"start": 0, "end": 1.25, "text": "Xin chào Việt Nam!"})

    def test_rejects_unknown_format(self):
        with self.assertRaises(ValueError):
            render_export(self.segments, "exe")

    def test_rejects_invalid_segment_timestamps(self):
        for start, end in [(1, 0), (-1, 0), (math.nan, 1), (0, math.inf)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                Segment(start, end, "Hi")

    def test_export_to_unicode_path_and_replace_existing_export(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "Phụ đề tiếng Việt.srt"
            target.write_text("old", encoding="utf-8")
            save_export(target, self.segments, "srt")
            self.assertIn("Xin chào Việt Nam!", target.read_text(encoding="utf-8"))
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_refuses_to_overwrite_source_even_with_relative_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "video.mp4"
            source.write_bytes(b"original-video")
            with self.assertRaises(ValueError):
                save_export(source.parent / "." / source.name, self.segments, "txt", source=source)
            self.assertEqual(source.read_bytes(), b"original-video")

    def test_failed_export_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "keep.txt"
            target.write_text("keep", encoding="utf-8")
            with self.assertRaises(ValueError):
                save_export(target, self.segments, "invalid")
            self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_missing_and_empty_input_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "empty.mp4"
            with self.assertRaises(ValueError):
                validate_source(str(target))
            target.touch()
            with self.assertRaises(ValueError):
                validate_source(str(target))


if __name__ == "__main__":
    unittest.main()
