#!/usr/bin/env python3
"""
Script to dump all SDK Python files to a single file with filename headers.
"""

import os


def dump_sdk_files():
    """Dump all SDK Python files to a single output file."""

    # Define the SDK directory and output file
    sdk_dir = "barndoor/sdk"
    output_file = "sdk_dump.txt"

    # Get all Python files in the SDK directory (excluding __pycache__)
    py_files = []
    for root, dirs, files in os.walk(sdk_dir):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != "__pycache__"]

        for file in files:
            if file.endswith(".py"):
                py_files.append(os.path.join(root, file))

    # Sort files for consistent output
    py_files.sort()

    print(f"Found {len(py_files)} Python files in {sdk_dir}")

    # Write all files to the output file
    with open(output_file, "w", encoding="utf-8") as outf:
        outf.write("=" * 80 + "\n")
        outf.write("BARNDOOR SDK PYTHON FILES DUMP\n")
        outf.write("=" * 80 + "\n\n")

        for py_file in py_files:
            print(f"Processing: {py_file}")

            # Write filename header
            outf.write("\n" + "=" * 80 + "\n")
            outf.write(f"FILE: {py_file}\n")
            outf.write("=" * 80 + "\n\n")

            try:
                # Read and write file content
                with open(py_file, encoding="utf-8") as inf:
                    content = inf.read()
                    outf.write(content)

                    # Ensure there's a newline at the end
                    if not content.endswith("\n"):
                        outf.write("\n")

            except Exception as e:
                outf.write(f"ERROR reading file: {e}\n")

            outf.write("\n")

    print(f"\nDump completed! Output written to: {output_file}")
    print(f"Total files processed: {len(py_files)}")


if __name__ == "__main__":
    dump_sdk_files()
