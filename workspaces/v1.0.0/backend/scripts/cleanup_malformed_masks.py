#!/usr/bin/env python3
"""Clean up malformed mask files with stacked page-number prefixes."""

import os
import sys
from pathlib import Path

def cleanup_malformed_masks(project_dir: str, dry_run: bool = True):
    """Remove mask files with excessive underscores (stacked prefixes)."""
    masks_dir = Path(project_dir) / "masks"
    if not masks_dir.exists():
        print(f"Masks directory not found: {masks_dir}")
        return

    removed_count = 0
    total_size = 0

    for mask_file in masks_dir.glob("*.png"):
        name = mask_file.name
        # Malformed files have > 3 underscores (e.g. 09_07_03_02_01_15_mask_uuid.png)
        # Valid files: 01_manual_mask.png, 01_mask_<uuid>.png (2-3 underscores)
        if name.count('_') > 3:
            size = mask_file.stat().st_size
            total_size += size
            if dry_run:
                print(f"Would delete: {name} ({size:,} bytes)")
            else:
                mask_file.unlink()
                print(f"Deleted: {name}")
            removed_count += 1

    print(f"\n{'Would delete' if dry_run else 'Deleted'} {removed_count:,} malformed mask files")
    print(f"Total size: {total_size / 1024 / 1024:.2f} MB")

    if dry_run:
        print("\nRun with --delete to actually remove these files")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cleanup_malformed_masks.py <project_dir> [--delete]")
        sys.exit(1)

    project_dir = sys.argv[1]
    delete_mode = "--delete" in sys.argv

    cleanup_malformed_masks(project_dir, dry_run=not delete_mode)
