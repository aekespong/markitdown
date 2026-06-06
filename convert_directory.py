#!/usr/bin/env python3
"""Convert every file in a directory to Markdown using the markitdown CLI."""

from __future__ import annotations

import argparse
import subprocess
import sys
from enum import Enum
from pathlib import Path


class ConversionStatus(Enum):
    CONVERTED = "converted"
    FAILED = "failed"
    SKIPPED = "skipped"


def iter_input_files(directory: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(
        path
        for path in directory.glob(pattern)
        if path.is_file() and path.suffix.lower() != ".md"
    )


def output_path_for(input_path: Path) -> Path:
    return input_path.with_suffix(".md")


def convert_file(
    input_path: Path, output_path: Path, overwrite: bool
) -> ConversionStatus:
    if output_path.exists() and not overwrite:
        print(f"skip existing: {output_path}", file=sys.stderr)
        return ConversionStatus.SKIPPED

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            ["markitdown", str(input_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        print("error: markitdown command was not found in PATH", file=sys.stderr)
        raise SystemExit(127)
    except subprocess.CalledProcessError as error:
        print(f"failed: {input_path}", file=sys.stderr)
        if error.stderr:
            print(error.stderr.rstrip(), file=sys.stderr)
        return ConversionStatus.FAILED

    output_path.write_text(result.stdout, encoding="utf-8")
    print(f"created: {output_path}")
    return ConversionStatus.CONVERTED


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert files in a directory to Markdown using markitdown."
    )
    parser.add_argument("directory", type=Path, help="Directory containing files to convert")
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only convert files directly inside the directory",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing .md files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    directory = args.directory.expanduser().resolve()

    if not directory.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 2

    input_files = iter_input_files(directory, recursive=not args.no_recursive)
    if not input_files:
        print(f"no files to convert in: {directory}")
        return 0

    converted = 0
    failed = 0
    skipped = 0

    for input_path in input_files:
        status = convert_file(
            input_path=input_path,
            output_path=output_path_for(input_path),
            overwrite=args.overwrite,
        )
        if status is ConversionStatus.CONVERTED:
            converted += 1
        elif status is ConversionStatus.FAILED:
            failed += 1
        elif status is ConversionStatus.SKIPPED:
            skipped += 1

    print(
        f"done: converted {converted}, skipped {skipped}, "
        f"failed {failed}, total {len(input_files)}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
