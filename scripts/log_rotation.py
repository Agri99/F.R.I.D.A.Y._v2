#!/usr/bin/env python3
"""
scripts/log_rotation.py

WHAT THIS IS FOR:
Log rotation and management for F.R.I.D.A.Y. v3 (§28).
Handles audit logs, trajectory logs, application logs, and error logs.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_LOG_DIRS = {
    "audit": _ROOT / "data" / "audit",
    "trajectories": _ROOT / "data" / "trajectories",
    "jobs": _ROOT / "data" / "jobs",
    "voice_enrollment": _ROOT / "data" / "voice_enrollment",
}


class LogRotator:
    """Manages log rotation and cleanup for F.R.I.D.A.Y. logs."""

    def __init__(self, log_dirs: dict[str, Path] | None = None):
        self.log_dirs = log_dirs or _LOG_DIRS
        for dir_path in self.log_dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)

    def rotate_logs(self, max_size_mb: int = 10, max_age_days: int = 30, compress: bool = True) -> dict[str, int]:
        """Rotate logs exceeding size or age limits."""
        results = {"rotated": 0, "compressed": 0, "deleted": 0, "errors": 0}

        for name, log_dir in self.log_dirs.items():
            if not log_dir.exists():
                continue

            for log_file in log_dir.glob("*.log"):
                self._rotate_single_log(log_file, max_size_mb, max_age_days, compress, results)

            # Also check for uncompressed rotated logs
            for rotated in log_dir.glob("*.log.*"):
                if rotated.suffix == ".gz":
                    continue
                self._compress_rotated_log(rotated, results)

        return results

    def _rotate_single_log(self, log_file: Path, max_size_mb: int, max_age_days: int, compress: bool, results: dict) -> None:
        """Rotate a single log file if it exceeds limits."""
        try:
            stat = log_file.stat()
            size_mb = stat.st_size / (1024 * 1024)
            age_days = (time.time() - stat.st_mtime) / 86400

            if size_mb >= max_size_mb or age_days >= max_age_days:
                timestamp = datetime.fromtimestamp(stat.st_mtime).strftime("%Y%m%d_%H%M%S")
                rotated_name = f"{log_file.stem}_{timestamp}{log_file.suffix}"
                rotated_path = log_file.parent / rotated_name

                shutil.move(str(log_file), str(rotated_path))
                print(f"  [+] Rotated: {log_file.name} -> {rotated_name}")
                results["rotated"] += 1

                if compress:
                    self._compress_rotated_log(rotated_path, results)

        except Exception as e:
            print(f"  [!] Error rotating {log_file}: {e}")
            results["errors"] += 1

    def _compress_rotated_log(self, log_file: Path, results: dict) -> None:
        """Compress a rotated log file with gzip."""
        try:
            compressed_path = Path(str(log_file) + ".gz")
            with open(log_file, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            log_file.unlink()
            print(f"  [+] Compressed: {log_file.name}.gz")
            results["compressed"] += 1
        except Exception as e:
            print(f"  [!] Error compressing {log_file}: {e}")
            results["errors"] += 1

    def cleanup_old_logs(self, max_age_days: int = 30, keep_recent: int = 50) -> dict[str, int]:
        """Delete old log files beyond retention policy."""
        results = {"deleted": 0, "kept": 0, "errors": 0}

        for name, log_dir in self.log_dirs.items():
            if not log_dir.exists():
                continue

            # Get all log files (including compressed)
            all_logs = []
            for pattern in ["*.log", "*.log.gz", "*.log.*.gz"]:
                all_logs.extend(log_dir.glob(pattern))

            # Sort by modification time (newest first)
            all_logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            # Keep the most recent N
            to_keep = set(all_logs[:keep_recent])

            for log_file in all_logs[keep_recent:]:
                age_days = (time.time() - log_file.stat().st_mtime) / 86400
                if age_days > max_age_days:
                    try:
                        log_file.unlink()
                        print(f"  [-] Deleted old log: {log_file.name} (age: {age_days:.1f} days)")
                        results["deleted"] += 1
                    except Exception as e:
                        print(f"  [!] Error deleting {log_file}: {e}")
                        results["errors"] += 1
                else:
                    results["kept"] += 1

        return results

    def archive_trajectories(self, days_old: int = 7) -> int:
        """Move old trajectory files to archive."""
        traj_dir = self.log_dirs.get("trajectories")
        if not traj_dir or not traj_dir.exists():
            return 0

        archive_dir = traj_dir / "archive"
        archive_dir.mkdir(exist_ok=True)

        archived = 0
        for traj_file in traj_dir.glob("*.jsonl"):
            try:
                age_days = (time.time() - traj_file.stat().st_mtime) / 86400
                if age_days > days_old:
                    dest = archive_dir / traj_file.name
                    shutil.move(str(traj_file), str(dest))
                    archived += 1
                    print(f"  [+] Archived: {traj_file.name}")
            except Exception as e:
                print(f"  [!] Error archiving {traj_file}: {e}")

        print(f"[+] Archived {archived} trajectory files")
        return archived

    def get_log_stats(self) -> dict:
        """Get statistics about current logs."""
        stats = {}
        total_size = 0
        total_files = 0

        for name, log_dir in self.log_dirs.items():
            if not log_dir.exists():
                stats[name] = {"files": 0, "size_mb": 0, "oldest": None, "newest": None}
                continue

            files = list(log_dir.glob("*"))
            if not files:
                stats[name] = {"files": 0, "size_mb": 0, "oldest": None, "newest": None}
                continue

            sizes = [f.stat().st_size for f in files]
            total = sum(sizes)
            oldest = min(f.stat().st_mtime for f in files)
            newest = max(f.stat().st_mtime for f in files)

            stats[name] = {
                "files": len(files),
                "size_mb": total / (1024 * 1024),
                "oldest": datetime.fromtimestamp(oldest).isoformat(),
                "newest": datetime.fromtimestamp(newest).isoformat(),
            }
            total_size += total
            total_files += len(files)

        stats["total"] = {"files": total_files, "size_mb": total_size / (1024 * 1024)}
        return stats


def main():
    parser = argparse.ArgumentParser(description="F.R.I.D.A.Y. v3 Log Rotation Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Rotate command
    rotate_parser = subparsers.add_parser("rotate", help="Rotate logs exceeding size/age limits")
    rotate_parser.add_argument("--max-size", type=int, default=10, help="Max size in MB before rotation")
    rotate_parser.add_argument("--max-age", type=int, default=30, help="Max age in days before rotation")
    rotate_parser.add_argument("--no-compress", action="store_true", help="Don't compress rotated logs")

    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old logs")
    cleanup_parser.add_argument("--max-age", type=int, default=30, help="Max age in days")
    cleanup_parser.add_argument("--keep", type=int, default=50, help="Number of recent logs to keep per category")

    # Archive command
    archive_parser = subparsers.add_parser("archive", help="Archive old trajectory files")
    archive_parser.add_argument("--days", type=int, default=7, help="Archive trajectories older than N days")

    # Stats command
    subparsers.add_parser("stats", help="Show log statistics")

    args = parser.parse_args()

    rotator = LogRotator()

    if args.command == "rotate":
        results = rotator.rotate_logs(
            max_size_mb=args.max_size,
            max_age_days=args.max_age,
            compress=not args.no_compress
        )
        print(f"\nRotation complete: {results}")

    elif args.command == "cleanup":
        results = rotator.cleanup_old_logs(max_age_days=args.max_age, keep_recent=args.keep)
        print(f"\nCleanup complete: {results}")

    elif args.command == "archive":
        archived = rotator.archive_trajectories(days_old=args.days)
        print(f"\nArchived {archived} trajectory files")

    elif args.command == "stats":
        stats = rotator.get_log_stats()
        print("\nLog Statistics:")
        for name, stat in stats.items():
            if name == "total":
                print(f"  Total: {stat['files']} files, {stat['size_mb']:.1f} MB")
            else:
                print(f"  {name}: {stat['files']} files, {stat['size_mb']:.1f} MB")
                if stat['oldest']:
                    print(f"    Oldest: {stat['oldest']}")
                    print(f"    Newest: {stat['newest']}")


if __name__ == "__main__":
    main()