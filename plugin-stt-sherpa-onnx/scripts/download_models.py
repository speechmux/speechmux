#!/usr/bin/env python3
"""Download sherpa-onnx Zipformer models for Korean, English, and Japanese.

Models are fetched from HuggingFace Hub using the huggingface_hub library.
Downloaded files are placed in the directory specified by --model-dir (default:
./models). After downloading, update config/inference.yaml to point to the
downloaded file paths.

Usage:
    python scripts/download_models.py --lang ko
    python scripts/download_models.py --lang en --lang ja
    python scripts/download_models.py --all

Required:
    pip install huggingface_hub
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# HuggingFace repo IDs for confirmed Zipformer streaming (transducer) models.
# NOTE: these must be *streaming* (online) variants — non-streaming (offline) models
# lack encoder_dims metadata and fail at OnlineRecognizer.from_transducer() time.
_MODEL_REPOS: dict[str, str] = {
    "ko": "k2-fsa/sherpa-onnx-streaming-zipformer-korean-2024-06-16",
    "en": "csukuangfj/sherpa-onnx-streaming-zipformer-en-2023-06-26",
    "ja": "reazon-research/reazonspeech-k2-v2",
}

# File names within each repo (int8-quantized variants).
# These names match the Korean repo exactly. The English streaming repo uses
# chunk/left-context suffixes (e.g. "encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx");
# download English models manually and update config/inference.yaml accordingly.
_MODEL_FILES: list[str] = [
    "encoder-epoch-99-avg-1.int8.onnx",
    "decoder-epoch-99-avg-1.int8.onnx",
    "joiner-epoch-99-avg-1.int8.onnx",
    "tokens.txt",
]


def _download_language(language: str, model_dir: Path) -> None:
    """Download the four model files for *language* into *model_dir/language*.

    Args:
        language: BCP-47 language code (e.g. "ko", "en", "ja").
        model_dir: Root directory to place downloaded models.

    Raises:
        KeyError: When *language* is not in _MODEL_REPOS.
        ImportError: When huggingface_hub is not installed.
        Exception: On download failure.
    """
    try:
        from huggingface_hub import hf_hub_download  # type: ignore[import-untyped]
    except ImportError:
        print(
            "ERROR: huggingface_hub is not installed. "
            "Run: pip install huggingface_hub",
            file=sys.stderr,
        )
        sys.exit(1)

    if language not in _MODEL_REPOS:
        supported = ", ".join(sorted(_MODEL_REPOS))
        print(f"ERROR: unsupported language {language!r}. Supported: {supported}", file=sys.stderr)
        sys.exit(1)

    repo_id = _MODEL_REPOS[language]
    language_dir = model_dir / language
    language_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{language}] Downloading from {repo_id} → {language_dir}")
    for filename in _MODEL_FILES:
        destination = language_dir / filename
        if destination.exists():
            print(f"  {filename} — already present, skipping")
            continue
        print(f"  Downloading {filename}…")
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=str(language_dir),
        )
        print(f"  → {local_path}")

    print(f"[{language}] Done. Update config/inference.yaml:")
    for filename in _MODEL_FILES:
        key = filename.split("-")[0] if "-" in filename else "tokens"
        if filename == "tokens.txt":
            key = "tokens"
        print(f"    {key}: {language_dir / filename}")


def main() -> None:
    """Parse arguments and download the requested models."""
    parser = argparse.ArgumentParser(description="Download sherpa-onnx Zipformer models")
    parser.add_argument(
        "--lang",
        action="append",
        metavar="CODE",
        dest="languages",
        help="BCP-47 language code to download (may be repeated)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download models for all supported languages (ko, en, ja)",
    )
    parser.add_argument(
        "--model-dir",
        default="models",
        metavar="DIR",
        help="Root directory to store downloaded models (default: models/)",
    )
    args = parser.parse_args()

    if args.all:
        languages = list(_MODEL_REPOS)
    elif args.languages:
        languages = args.languages
    else:
        parser.print_help()
        sys.exit(0)

    model_dir = Path(args.model_dir)
    for language in languages:
        _download_language(language, model_dir)

    print("\nAll downloads complete.")
    print("Update config/inference.yaml with the paths shown above before starting the plugin.")


if __name__ == "__main__":
    main()
