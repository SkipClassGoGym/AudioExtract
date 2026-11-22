from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np

from audioextract.audio import SAMPLE_RATE, AudioChunk, audio_duration, stream_audio_chunks
from audioextract.engine import Options, transcribe


class AudioStreamingTests(unittest.TestCase):
    def test_chunking_preserves_every_sample_and_absolute_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "speech.wav"
            count = int(10.37 * SAMPLE_RATE)
            original = (np.sin(np.arange(count) * 0.17) * 10000).astype(np.int16)
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(SAMPLE_RATE)
                audio.writeframes(original.tobytes())
            chunks = list(stream_audio_chunks(source, chunk_seconds=4))
            self.assertEqual(len(chunks), 3)
            self.assertEqual([chunk.start for chunk in chunks], [0, 4, 8])
            self.assertAlmostEqual(chunks[-1].end, count / SAMPLE_RATE)
            self.assertAlmostEqual(audio_duration(source), count / SAMPLE_RATE)
            for chunk in chunks:
                self.assertEqual(chunk.samples.dtype, np.float32)
                self.assertLessEqual(len(chunk.samples), 4 * SAMPLE_RATE)
            np.testing.assert_allclose(np.concatenate([c.samples for c in chunks]), original / 32768,
                                       atol=0.000001, rtol=0)

    def test_quiet_cut_does_not_drop_the_carried_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "silence.wav"
            count = 31 * SAMPLE_RATE + 7
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(SAMPLE_RATE)
                audio.writeframes(np.zeros(count, dtype=np.int16).tobytes())
            chunks = list(stream_audio_chunks(source, chunk_seconds=12))
            self.assertEqual(sum(len(c.samples) for c in chunks), count)
            for previous, current in zip(chunks, chunks[1:]):
                self.assertAlmostEqual(previous.end, current.start)
            self.assertLessEqual(max(len(c.samples) for c in chunks), 12 * SAMPLE_RATE)

    def test_engine_offsets_subtitles_and_progress_across_silent_chunks(self):
        from types import SimpleNamespace

        class Model:
            calls = 0

            def __init__(self, *args, **kwargs):
                pass

            def transcribe(self, audio, **kwargs):
                # The backend must only ever receive the current bounded array.
                self.assert_array(audio)
                self.calls += 1
                segments = [] if self.calls == 1 else [SimpleNamespace(start=1, end=2, text="Xin chào")]
                return iter(segments), SimpleNamespace(language="vi", language_probability=0.99)

            @staticmethod
            def assert_array(audio):
                assert isinstance(audio, np.ndarray) and len(audio) <= 120 * SAMPLE_RATE

        chunks = [AudioChunk(start, np.zeros(120 * SAMPLE_RATE, dtype=np.float32)) for start in (0, 120, 240)]
        events = []
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "video.mp4"
            source.write_bytes(b"fixture")
            with patch("audioextract.engine.audio_duration", return_value=360), \
                 patch("audioextract.engine.stream_audio_chunks", return_value=iter(chunks)), \
                 patch("faster_whisper.WhisperModel", Model):
                transcribe(Options(str(source), device="cpu"), events.append)
        segments = [e["data"] for e in events if e["type"] == "segment"]
        self.assertEqual([s["start"] for s in segments], [121, 241])
        self.assertEqual([s["end"] for s in segments], [122, 242])
        progress = [e["progress"] for e in events if e["type"] == "progress"]
        self.assertEqual(progress, sorted(progress))
        self.assertEqual(progress[-1], 99)
        self.assertTrue([e for e in events if e["type"] == "metadata"][-1]["data"]["complete"])
        self.assertEqual(events[-1]["type"], "done")


if __name__ == "__main__":
    unittest.main()
