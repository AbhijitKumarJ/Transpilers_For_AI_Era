#!/usr/bin/env python3
"""
Test runner for Ported 18_micro_shutil (Python-shutil filesystem tree operations in PythonSharp).
Builds the project with `psc` and validates paths, recursive copying, tree scanning, and cleanup.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroShutil via `psc build` ===")
    psc_bin = shutil.which("psc")
    if psc_bin:
        cmd = [psc_bin, "build", str(proj_dir)]
    else:
        cmd = [sys.executable, "-m", "psc.cli", "build", str(proj_dir)]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Build failed:\n{res.stderr}\n{res.stdout}", file=sys.stderr)
        return 1
    print(res.stdout.strip())

    print("\n=== Step 2: Testing Ported MicroShutil Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_shutil import PathMetadata, ShutilEngine, TreeStats
    except ImportError as e:
        print(f"Failed to import micro_shutil: {e}", file=sys.stderr)
        return 1

    # 1. Path joining and existence
    joined = ShutilEngine.combine_paths("folder", "subfolder")
    assert joined == os.path.join("folder", "subfolder")
    print(f"[PASS] CombinePaths: {joined}")

    three = ShutilEngine.combine_three_paths("a", "b", "c.txt")
    assert three == os.path.join("a", "b", "c.txt")
    print(f"[PASS] CombineThreePaths: {three}")

    # Use a temporary directory for active filesystem mutations
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_root = Path(tmp_dir)

        # 2. Directory Creation
        sub_dir = test_root / "test_nested" / "deep_folder"
        ShutilEngine.ensure_directory(str(sub_dir))
        assert ShutilEngine.exists(str(sub_dir))
        assert ShutilEngine.is_directory(str(sub_dir))
        assert not ShutilEngine.is_file(str(sub_dir))
        print(f"[PASS] EnsureDirectory & Type Guards verified on {sub_dir.name}")

        # 3. File Creation and Metadata
        file1 = sub_dir / "document.txt"
        file1.write_text("Hello PythonSharp MicroShutil!", encoding="utf-8")
        file2 = sub_dir / "data.csv"
        file2.write_text("id,val\n1,100\n2,200\n", encoding="utf-8")

        meta = ShutilEngine.get_metadata(str(file1))
        assert isinstance(meta, PathMetadata)
        assert meta.file_name == "document.txt"
        assert meta.extension == ".txt"
        assert meta.size_bytes == len("Hello PythonSharp MicroShutil!")
        assert not meta.is_directory
        print(f"[PASS] GetMetadata: {meta.file_name} size={meta.size_bytes}B ext={meta.extension}")

        # 4. Copying and Moving Files
        copied_file = test_root / "document_copy.txt"
        ShutilEngine.copy_file(str(file1), str(copied_file))
        assert ShutilEngine.exists(str(copied_file))
        assert ShutilEngine.get_metadata(str(copied_file)).size_bytes == meta.size_bytes
        print("[PASS] CopyFile verified")

        moved_file = test_root / "document_moved.txt"
        ShutilEngine.move_file(str(copied_file), str(moved_file))
        assert not ShutilEngine.exists(str(copied_file))
        assert ShutilEngine.exists(str(moved_file))
        print("[PASS] MoveFile verified")

        # 5. Tree Scanning & Recursion
        # Create additional files in tree
        another_dir = test_root / "another_branch"
        ShutilEngine.ensure_directory(str(another_dir))
        (another_dir / "notes.txt").write_text("More notes here.", encoding="utf-8")

        stats = ShutilEngine.scan_tree(str(test_root))
        assert isinstance(stats, TreeStats)
        assert stats.file_count == 4  # document.txt, data.csv, document_moved.txt, notes.txt
        assert stats.directory_count == 3  # test_nested, deep_folder, another_branch
        print(f"[PASS] ScanTree: files={stats.file_count}, dirs={stats.directory_count}, total_bytes={stats.total_size_bytes}")

        # 6. Find Files by Extension
        txt_files = ShutilEngine.find_files_with_extension(str(test_root), ".txt")
        assert len(txt_files) == 3
        print(f"[PASS] FindFilesWithExtension (.txt): found {len(txt_files)} files")

        csv_files = ShutilEngine.find_files_with_extension(str(test_root), ".csv")
        assert len(csv_files) == 1
        print(f"[PASS] FindFilesWithExtension (.csv): found {len(csv_files)} files")

        # 7. Copy Directory Tree
        backup_tree = test_root / "backup_root"
        ShutilEngine.copy_tree(str(test_root / "test_nested"), str(backup_tree))
        assert ShutilEngine.exists(str(backup_tree / "deep_folder" / "document.txt"))
        print("[PASS] CopyTree verified across nested folder hierarchies")

        # 8. Remove Directory Tree
        ShutilEngine.remove_tree(str(backup_tree))
        assert not ShutilEngine.exists(str(backup_tree))
        print("[PASS] RemoveTree verified with complete recursive cleanup")

    print("\nAll 18_micro_shutil verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

