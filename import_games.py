#!/usr/bin/env python3
"""
Import games into GameShelf from a JSON file.
"""

import os
import sys
import argparse
from pathlib import Path

from data_handler import DataHandler
from importers.json_importer import JsonImporter


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Import games into GameShelf from a JSON file.")
    parser.add_argument("json_file", help="Path to the JSON file containing game data")
    parser.add_argument("--cover-dir", "-c",
                       help="Base directory for cover images (defaults to JSON file's directory)")
    parser.add_argument("--data-dir", "-d", default="data",
                       help="Path to GameShelf data directory (defaults to 'data')")
    parser.add_argument("--limit", "-l", type=int,
                       help="Limit the number of games to import (for testing)")

    args = parser.parse_args()

    # Validate JSON file path
    json_path = os.path.abspath(args.json_file)
    if not os.path.exists(json_path):
        print(f"Error: JSON file not found: {json_path}")
        return 1

    # Determine cover images base directory
    if args.cover_dir:
        cover_base_dir = os.path.abspath(args.cover_dir)
    else:
        # Default to JSON file's directory
        cover_base_dir = os.path.dirname(json_path)

    if not os.path.exists(cover_base_dir):
        print(f"Error: Cover images directory not found: {cover_base_dir}")
        return 1

    # Initialize data handler and importer
    data_handler = DataHandler(args.data_dir)
    importer = JsonImporter(data_handler)

    # Perform import
    print(f"Importing games from: {json_path}")
    print(f"Using cover images from: {cover_base_dir}")

    try:
        # Pass limit argument if specified
        imported_count, errors = importer.import_from_file(json_path, cover_base_dir, limit=args.limit)

        # Report results
        print(f"\nImport complete: {imported_count} games imported.")

        if errors:
            print(f"\n{len(errors)} errors occurred:")
            for error in errors:
                print(f"- {error}")

        return 0 if not errors else 2

    except Exception as e:
        print(f"Import failed with error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())