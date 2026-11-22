"""Windows entry point; also supports an optional command-line mode."""

import argparse
import multiprocessing
from pathlib import Path
import sys

from audioextract.engine import MODELS, Options, Segment, friendly_error, save_export, transcribe


def main() -> int:
    parser = argparse.ArgumentParser(description="AudioExtract — local video transcription")
    parser.add_argument("--input", type=Path, help="Video/audio to transcribe (omit for desktop UI)")
    parser.add_argument("--output", type=Path, help="Output path; default: next to input")
    parser.add_argument("--format", choices=("txt", "srt", "vtt", "json"), default="txt")
    parser.add_argument("--model", choices=MODELS, default="small")
    parser.add_argument("--language", default="auto", help="auto, vi, en, ja, ...")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing export")
    args = parser.parse_args()
    if not args.input:
        from audioextract.gui import launch
        launch()
        return 0
    output = args.output or args.input.with_suffix("." + args.format)
    if output.exists() and not args.overwrite:
        parser.error(f"Output already exists: {output}. Use --overwrite to replace it.")
    segments = []
    metadata = {}
    on_progress_line = False

    def receive(event):
        nonlocal on_progress_line
        if event["type"] == "segment":
            segments.append(Segment(**event["data"]))
            print(f"\r{event['progress']:.0f}% — {len(segments)} segments", end="", flush=True)
            on_progress_line = True
        elif event["type"] == "metadata":
            metadata.update(event["data"])
        elif event["type"] == "status":
            # Without the newline the status is glued onto "NN% — ..." and the queue
            # parses the whole line as progress, dropping the status.
            print(("\n" if on_progress_line else "") + event["text"], flush=True)
            on_progress_line = False
        elif event["type"] == "done":
            metadata["complete"] = True

    try:
        transcribe(Options(str(args.input), args.model,
                           None if args.language == "auto" else args.language,
                           args.device, args.offline), receive)
        save_export(output, segments, args.format, metadata, args.input)
    except KeyboardInterrupt:
        print("\nCancelled. No output was written.", file=sys.stderr)
        return 130
    except Exception as error:
        print("\n" + friendly_error(error, args.offline), file=sys.stderr)
        return 1
    print(f"\nSaved {len(segments)} segments: {output.resolve()}")
    if not segments:
        print("No speech detected. Try selecting the spoken language or a larger model.")
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
