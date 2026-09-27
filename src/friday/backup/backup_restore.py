"""
src/friday/backup/backup_restore.py

WHAT THIS IS FOR:
Backup and restore (Runbook §47 — Phase Z3).

State that survives code upgrades:
  - Memory (episodic, semantic, procedural)
  - Preferences
  - Skills
  - Jobs
  - Trajectories
  - Configuration
  - Model registry
  - Provider configuration

Machine-specific state that needs revalidation:
  - Audio devices
  - GPU capability
  - VRAM
  - Hardware profile
  - Model compatibility
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BackupManager:
    """Manages backups of FRIDAY state."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.backup_dir = data_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, label: str = "") -> Path:
        """Create a full backup of critical state.

        Args:
            label: Human-readable backup label

        Returns:
            Path to the created backup
        """
        timestamp = datetime.now().isoformat()
        backup_name = f"backup-{timestamp}"
        if label:
            backup_name = f"{backup_name}-{label}"

        backup_path = self.backup_dir / backup_name
        backup_path.mkdir(parents=True, exist_ok=True)

        # Backup files to preserve
        preserve_items = [
            "friday.db",  # Memory database
            "config.yaml",  # Configuration
            "skills/",  # Learned skills
            "memory_checkpoint.json",  # Memory state
            "jobs_checkpoint.json",  # Scheduled jobs
            "preferences.json",  # User preferences
            "models/registry.json",  # Model registry
        ]

        metadata = {
            "backup_time": timestamp,
            "label": label,
            "items": [],
        }

        for item in preserve_items:
            item_path = self.data_dir / item
            if not item_path.exists():
                logger.warning(f"Item not found for backup: {item}")
                continue

            target_path = backup_path / item
            target_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                if item_path.is_dir():
                    shutil.copytree(item_path, target_path)
                else:
                    shutil.copy2(item_path, target_path)

                metadata["items"].append(item)
                logger.info(f"Backed up: {item}")
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
                logger.error(f"Error backing up {item}: {e}")

        # Save metadata
        metadata_path = backup_path / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Backup created: {backup_path}")
        return backup_path

    def list_backups(self) -> list[dict[str, Any]]:
        """List available backups."""
        backups = []

        for backup_path in sorted(self.backup_dir.iterdir(), reverse=True):
            if not backup_path.is_dir():
                continue

            metadata_path = backup_path / "metadata.json"
            if metadata_path.exists():
                try:
                    with open(metadata_path) as f:
                        metadata = json.load(f)
                    metadata["path"] = str(backup_path)
                    backups.append(metadata)
                except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
                    logger.error(f"Error reading backup metadata: {e}")

        return backups

    def restore_backup(self, backup_path: Path, force: bool = False) -> bool:
        """Restore from a backup.

        Args:
            backup_path: Path to the backup
            force: Overwrite existing files

        Returns:
            True if restore successful
        """
        if not backup_path.exists():
            logger.error(f"Backup not found: {backup_path}")
            return False

        metadata_path = backup_path / "metadata.json"
        if not metadata_path.exists():
            logger.error(f"No metadata in backup: {backup_path}")
            return False

        try:
            with open(metadata_path) as f:
                metadata = json.load(f)

            logger.info(f"Restoring backup from {metadata['backup_time']}")

            for item in metadata.get("items", []):
                source_path = backup_path / item
                target_path = self.data_dir / item

                if target_path.exists() and not force:
                    logger.warning(f"Item already exists, skipping: {item}")
                    continue

                if not source_path.exists():
                    logger.warning(f"Item not in backup: {item}")
                    continue

                try:
                    # Remove existing
                    if target_path.exists():
                        if target_path.is_dir():
                            shutil.rmtree(target_path)
                        else:
                            target_path.unlink()

                    # Restore
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    if source_path.is_dir():
                        shutil.copytree(source_path, target_path)
                    else:
                        shutil.copy2(source_path, target_path)

                    logger.info(f"Restored: {item}")
                except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
                    logger.error(f"Error restoring {item}: {e}")

            logger.info("Backup restore complete")
            return True

        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            logger.error(f"Error restoring backup: {e}")
            return False


class StateValidator:
    """Validates restored state against current hardware."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def validate_restored_state(self) -> dict[str, Any]:
        """Validate that restored state is compatible with current hardware.

        Returns:
            Dict with validation results and warnings
        """
        results = {
            "valid": True,
            "warnings": [],
            "errors": [],
        }

        # Check audio devices
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            has_input = any(d.get("max_input_channels", 0) > 0 for d in devices)
            has_output = any(d.get("max_output_channels", 0) > 0 for d in devices)

            if not has_input or not has_output:
                results["warnings"].append("Audio devices may have changed")
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            results["warnings"].append(f"Could not check audio devices: {e}")

        # Check GPU
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if not gpus:
                results["warnings"].append("GPU not detected (was previously available)")
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            results["warnings"].append("GPU library not available")

        # Validate model compatibility
        models_path = self.data_dir / "models" / "registry.json"
        if models_path.exists():
            try:
                with open(models_path) as f:
                    registry = json.load(f)

                for model_name, model_info in registry.items():
                    # Check if model file exists
                    model_file = self.data_dir / "models" / model_info.get("path", "")
                    if not model_file.exists():
                        results["warnings"].append(f"Model file missing: {model_name}")
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
                results["errors"].append(f"Error validating models: {e}")
                results["valid"] = False

        return results


__all__ = [
    "BackupManager",
    "StateValidator",
]
