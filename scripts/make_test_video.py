"""Create a local speech video fixture from a WAV synthesized by Windows SAPI."""

from fractions import Fraction
from pathlib import Path
import wave

import av
import numpy as np


def main():
    directory = Path(__file__).resolve().parents[1] / ".test-artifacts"
    with wave.open(str(directory / "speech.wav")) as speech:
        rate = speech.getframerate()
        samples = np.frombuffer(speech.readframes(speech.getnframes()), dtype=np.int16)
    duration = len(samples) / rate
    for name, with_audio in [("video-local.mp4", True), ("video-no-audio.mp4", False)]:
        with av.open(str(directory / name), "w") as output:
            video = output.add_stream("libx264", rate=1)
            video.width = 480
            video.height = 270
            video.pix_fmt = "yuv420p"
            audio = output.add_stream("aac", rate=rate) if with_audio else None
            if audio:
                audio.layout = "mono"
            for second in range(int(duration) + 1):
                pixels = np.zeros((270, 480, 3), dtype=np.uint8)
                pixels[:] = (8, 90 + second * 5, 85)
                frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                frame.pts = second
                frame.time_base = Fraction(1, 1)
                for packet in video.encode(frame):
                    output.mux(packet)
                if audio:
                    start = second * rate
                    block = samples[start:start + rate]
                    if block.size:
                        frame = av.AudioFrame.from_ndarray(block.reshape(1, -1), format="s16", layout="mono")
                        frame.sample_rate = rate
                        frame.pts = start
                        frame.time_base = Fraction(1, rate)
                        for packet in audio.encode(frame):
                            output.mux(packet)
            for packet in video.encode():
                output.mux(packet)
            if audio:
                for packet in audio.encode():
                    output.mux(packet)
    print(f"Created MP4 fixtures: {duration:.1f} seconds")


if __name__ == "__main__":
    main()
