#!/usr/bin/env python3
"""Convert one file or every file in a directory using the markitdown CLI."""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
import zipfile
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
    output_name = f"{input_path.stem.replace(' ', '_')}.md"
    return input_path.with_name(output_name)


def looks_like_markdown(text: str) -> bool:
    return "# " in text and "## " in text


def detect_stdin_extension(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return ".pdf"

    if data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return None

        if "word/document.xml" in names:
            return ".docx"
        if "xl/workbook.xml" in names:
            return ".xlsx"

    # Legacy Office files use the same compound-file signature. These stream
    # names are enough to tell Excel from Word for stdin extension hints.
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        if (
            b"W\x00o\x00r\x00k\x00b\x00o\x00o\x00k\x00" in data
            or b"B\x00o\x00o\x00k\x00" in data
        ):
            return ".xls"
        if (
            b"W\x00o\x00r\x00d\x00D\x00o\x00c\x00u\x00m\x00e\x00n\x00t\x00"
            in data
        ):
            return ".doc"

    return None


def read_text_file(input_path: Path) -> str | None:
    try:
        return input_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"failed: {input_path}", file=sys.stderr)
        print("error: text file is not valid UTF-8", file=sys.stderr)
        return None


def convert_file(
    input_path: Path, output_path: Path, overwrite: bool
) -> ConversionStatus:
    if output_path.exists() and not overwrite:
        print(f"skip existing: {output_path}", file=sys.stderr)
        return ConversionStatus.SKIPPED

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if input_path.suffix.lower() == ".txt":
        text = read_text_file(input_path)
        if text is None:
            return ConversionStatus.FAILED
        if not looks_like_markdown(text):
            print(f"failed: {input_path}", file=sys.stderr)
            print(
                'error: text file does not look like Markdown; missing "# " or "## "',
                file=sys.stderr,
            )
            return ConversionStatus.FAILED

        output_path.write_text(text, encoding="utf-8")
        print(f"created: {output_path}")
        return ConversionStatus.CONVERTED

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


def convert_stdin_with_markitdown(data: bytes, extension: str) -> int:
    if extension == ".doc":
        print(
            "error: legacy .doc input was detected, but this markitdown setup "
            "only supports .docx Word files",
            file=sys.stderr,
        )
        return 1

    try:
        result = subprocess.run(
            ["markitdown", "-x", extension],
            input=data,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        print("error: markitdown command was not found in PATH", file=sys.stderr)
        return 127
    except subprocess.CalledProcessError as error:
        print(f"error: failed to convert stdin as {extension}", file=sys.stderr)
        if error.stderr:
            print(
                error.stderr.decode("utf-8", errors="replace").rstrip(),
                file=sys.stderr,
            )
        return 1

    sys.stdout.buffer.write(result.stdout)
    return 0


def convert_stdin() -> int:
    data = sys.stdin.buffer.read()
    if not data:
        print("error: no input received on stdin", file=sys.stderr)
        return 2

    extension = detect_stdin_extension(data)
    if extension is not None:
        return convert_stdin_with_markitdown(data, extension)

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        print(
            "error: stdin is neither UTF-8 Markdown nor a supported PDF, DOCX, XLSX, or XLS file",
            file=sys.stderr,
        )
        return 1

    if not looks_like_markdown(text):
        print(
            'error: stdin does not look like Markdown; missing "# " or "## "',
            file=sys.stderr,
        )
        return 1

    print(text, end="" if text.endswith("\n") else "\n")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert files to Markdown using markitdown."
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        help="File to convert when -d/--directory is not used",
    )
    parser.add_argument(
        "-d",
        "--directory",
        type=Path,
        help="Directory containing files to convert",
    )
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

    if args.directory and args.file:
        print("error: provide either a file or -d/--directory, not both", file=sys.stderr)
        return 2

    if args.directory:
        directory = args.directory.expanduser().resolve()

        if not directory.is_dir():
            print(f"error: not a directory: {directory}", file=sys.stderr)
            return 2

        input_files = iter_input_files(directory, recursive=not args.no_recursive)
        if not input_files:
            print(f"no files to convert in: {directory}")
            return 0
    else:
        if not args.file:
            return convert_stdin()

        input_file = args.file.expanduser().resolve()
        if not input_file.is_file():
            print(f"error: not a file: {input_file}", file=sys.stderr)
            return 2
        if input_file.suffix.lower() == ".md":
            print(f"error: input is already Markdown: {input_file}", file=sys.stderr)
            return 2

        input_files = [input_file]

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
