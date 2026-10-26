import errno
import json
import shutil
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import torch
from django.conf import settings
from transformers import PretrainedConfig

from analysis.inference.adapter import ModelAdapterProtocol, ModelOutput
from analysis.inference.deberta import DebertaModelAdapter, ModelInferenceError
from analysis.model_loader.loader import (
    ModelArtifactCorruptedError,
    ModelArtifactNotFoundError,
    ModelLoader,
    ModelLoadingError,
    _atomic_publish_dir,
    resolve_artifact_path,
)
from analysis.models import ModelPrediction


class PathResolutionTests(TestCase):
    """
    Tests for resolve_artifact_path() ensuring consistent resolution across
    absolute paths, BASE_DIR-relative paths, repo-root paths, and child directories.
    """

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_path_res_"))

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_absolute_path_resolved_directly(self):
        artifact_dir = self.test_dir / "my_model"
        artifact_dir.mkdir()
        (artifact_dir / "model.safetensors").write_text("weights", encoding="utf-8")

        resolved = resolve_artifact_path(artifact_dir)
        self.assertEqual(resolved, artifact_dir.resolve())

    def test_relative_path_under_base_dir(self):
        rel_sub = Path("model_artifacts") / "custom_checkpoint"
        full_dir = settings.BASE_DIR / rel_sub
        full_dir.mkdir(parents=True, exist_ok=True)
        (full_dir / "model.safetensors").write_text("weights", encoding="utf-8")
        try:
            resolved = resolve_artifact_path(rel_sub)
            self.assertEqual(resolved, full_dir.resolve())
        finally:
            shutil.rmtree(settings.BASE_DIR / "model_artifacts", ignore_errors=True)

    def test_relative_path_under_repo_root(self):
        if (
            not hasattr(settings.BASE_DIR, "parent")
            or settings.BASE_DIR.parent == settings.BASE_DIR
        ):
            self.skipTest("No parent repository root available")

        rel_sub = Path("TestRepoModels") / "checkpoint_root"
        full_dir = settings.BASE_DIR.parent / rel_sub
        full_dir.mkdir(parents=True, exist_ok=True)
        (full_dir / "model.safetensors").write_text("weights", encoding="utf-8")
        try:
            resolved = resolve_artifact_path(rel_sub)
            self.assertEqual(resolved, full_dir.resolve())
        finally:
            shutil.rmtree(
                settings.BASE_DIR.parent / "TestRepoModels", ignore_errors=True
            )

    def test_parent_folder_unwrapped_to_child_checkpoint(self):
        parent_dir = self.test_dir / "parent_holder"
        child_dir = parent_dir / "final_model_corrected"
        child_dir.mkdir(parents=True)
        (child_dir / "model.safetensors").write_text("weights", encoding="utf-8")

        resolved = resolve_artifact_path(parent_dir)
        self.assertEqual(resolved, child_dir.resolve())

    def test_nonexistent_path_raises_artifact_not_found_error(self):
        fake_path = self.test_dir / "completely_missing_directory"
        with self.assertRaises(ModelArtifactNotFoundError) as ctx:
            resolve_artifact_path(fake_path)
        self.assertIn("completely_missing_directory", str(ctx.exception))


class TokenizerStagingTests(TestCase):
    """
    Tests for isolated, non-destructive tokenizer configuration normalization.
    """

    def setUp(self):
        self.source_dir = Path(tempfile.mkdtemp(prefix="source_tok_"))
        self.test_staging_base = Path(tempfile.mkdtemp(prefix="test_tok_cache_"))

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.test_staging_base, ignore_errors=True)

    def test_staging_successful_publication_without_extra_special_tokens(self):
        config_data = {
            "model_max_length": 128,
            "extra_special_tokens": {"some": "token"},
            "tokenizer_class": "DebertaV2Tokenizer",
        }
        (self.source_dir / "tokenizer_config.json").write_text(
            json.dumps(config_data), encoding="utf-8"
        )
        (self.source_dir / "tokenizer.json").write_text(
            '{"vocab": {}}', encoding="utf-8"
        )
        source_bytes_before = (self.source_dir / "tokenizer_config.json").read_bytes()

        loader = ModelLoader(
            artifact_path=self.source_dir,
            staging_base_dir=self.test_staging_base,
        )
        staged_dir = loader._prepare_tokenizer_dir(self.source_dir)

        self.assertNotEqual(staged_dir, self.source_dir)
        self.assertTrue((staged_dir / ".complete").is_file())
        self.assertTrue((staged_dir / "tokenizer.json").is_file())

        staged_config = json.loads(
            (staged_dir / "tokenizer_config.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("extra_special_tokens", staged_config)
        self.assertEqual(staged_config["model_max_length"], 128)

        # Source immutability check: original files unchanged
        source_bytes_after = (self.source_dir / "tokenizer_config.json").read_bytes()
        self.assertEqual(source_bytes_before, source_bytes_after)

    def test_staging_bypassed_if_extra_special_tokens_absent(self):
        config_data = {"model_max_length": 128, "tokenizer_class": "DebertaV2Tokenizer"}
        (self.source_dir / "tokenizer_config.json").write_text(
            json.dumps(config_data), encoding="utf-8"
        )
        (self.source_dir / "tokenizer.json").write_text(
            '{"vocab": {}}', encoding="utf-8"
        )

        loader = ModelLoader(
            artifact_path=self.source_dir,
            staging_base_dir=self.test_staging_base,
        )
        result_dir = loader._prepare_tokenizer_dir(self.source_dir)
        self.assertEqual(result_dir, self.source_dir)

    def test_staging_destination_collision_recovers_if_winner_valid(self):
        config_data = {"model_max_length": 128, "extra_special_tokens": {}}
        (self.source_dir / "tokenizer_config.json").write_text(
            json.dumps(config_data), encoding="utf-8"
        )
        (self.source_dir / "tokenizer.json").write_text(
            '{"vocab": {}}', encoding="utf-8"
        )

        loader = ModelLoader(
            artifact_path=self.source_dir,
            staging_base_dir=self.test_staging_base,
        )
        content_hash = loader._compute_tokenizer_identity(self.source_dir)
        staged_dir = self.test_staging_base / f"tok_{content_hash}"

        def fake_rename_winner_valid(src, dst):
            dst.mkdir(parents=True, exist_ok=True)
            (dst / ".complete").write_text("ready", encoding="utf-8")
            (dst / "tokenizer_config.json").write_text(
                '{"model_max_length": 128}', encoding="utf-8"
            )
            (dst / "tokenizer.json").write_text('{"vocab": {}}', encoding="utf-8")
            raise FileExistsError("Target directory exists")

        with patch(
            "analysis.model_loader.loader._atomic_publish_dir",
            side_effect=fake_rename_winner_valid,
        ):
            res_dir = loader._prepare_tokenizer_dir(self.source_dir)

        self.assertEqual(res_dir, staged_dir)

    def test_staging_destination_collision_raises_if_winner_corrupt(self):
        config_data = {"model_max_length": 128, "extra_special_tokens": {}}
        (self.source_dir / "tokenizer_config.json").write_text(
            json.dumps(config_data), encoding="utf-8"
        )
        (self.source_dir / "tokenizer.json").write_text(
            '{"vocab": {}}', encoding="utf-8"
        )

        loader = ModelLoader(
            artifact_path=self.source_dir,
            staging_base_dir=self.test_staging_base,
        )

        def fake_rename_winner_corrupt(src, dst):
            dst.mkdir(parents=True, exist_ok=True)
            (dst / "tokenizer_config.json").write_text(
                '{"model_max_length": 128}', encoding="utf-8"
            )
            # Missing .complete and tokenizer.json
            raise FileExistsError("Target directory exists")

        with patch(
            "analysis.model_loader.loader._atomic_publish_dir",
            side_effect=fake_rename_winner_corrupt,
        ):
            with self.assertRaises(ModelArtifactCorruptedError):
                loader._prepare_tokenizer_dir(self.source_dir)

    def test_staging_permission_error_raises_model_loading_error(self):
        config_data = {"extra_special_tokens": {}}
        (self.source_dir / "tokenizer_config.json").write_text(
            json.dumps(config_data), encoding="utf-8"
        )
        (self.source_dir / "tokenizer.json").write_text(
            '{"vocab": {}}', encoding="utf-8"
        )

        loader = ModelLoader(
            artifact_path=self.source_dir,
            staging_base_dir=self.test_staging_base,
        )
        with patch(
            "analysis.model_loader.loader._atomic_publish_dir",
            side_effect=PermissionError("Access is denied"),
        ):
            with self.assertRaises(ModelLoadingError) as ctx:
                loader._prepare_tokenizer_dir(self.source_dir)
            self.assertIn("Filesystem error", str(ctx.exception))

    def test_staging_enospc_error_raises_model_loading_error(self):
        config_data = {"extra_special_tokens": {}}
        (self.source_dir / "tokenizer_config.json").write_text(
            json.dumps(config_data), encoding="utf-8"
        )
        (self.source_dir / "tokenizer.json").write_text(
            '{"vocab": {}}', encoding="utf-8"
        )

        loader = ModelLoader(
            artifact_path=self.source_dir,
            staging_base_dir=self.test_staging_base,
        )
        enospc_err = OSError(errno.ENOSPC, "No space left on device")
        with patch(
            "analysis.model_loader.loader._atomic_publish_dir",
            side_effect=enospc_err,
        ):
            with self.assertRaises(ModelLoadingError) as ctx:
                loader._prepare_tokenizer_dir(self.source_dir)
            self.assertIn("No space left on device", str(ctx.exception))

    def test_staging_multi_threaded_concurrency(self):
        """
        Verifies that multiple concurrent threads attempting to stage the same tokenizer
        safely resolve to the same published staging directory without corruption.
        """
        config_data = {
            "model_max_length": 128,
            "extra_special_tokens": {"some": "token"},
            "tokenizer_class": "DebertaV2Tokenizer",
        }
        (self.source_dir / "tokenizer_config.json").write_text(
            json.dumps(config_data), encoding="utf-8"
        )
        (self.source_dir / "tokenizer.json").write_text(
            '{"vocab": {}}', encoding="utf-8"
        )

        from concurrent.futures import ThreadPoolExecutor

        def run_staging():
            loader = ModelLoader(
                artifact_path=self.source_dir,
                staging_base_dir=self.test_staging_base,
            )
            return loader._prepare_tokenizer_dir(self.source_dir)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_staging) for _ in range(5)]
            results = [f.result() for f in futures]

        first_res = results[0]
        for res in results:
            self.assertEqual(res, first_res)
        self.assertTrue((first_res / ".complete").is_file())
        self.assertTrue((first_res / "tokenizer_config.json").is_file())
        self.assertTrue((first_res / "tokenizer.json").is_file())

    def test_staging_pre_existing_incomplete_directory_raises_without_deletion(self):
        """
        Verifies that an existing incomplete or empty cache directory is not silently
        overwritten or deleted, and raises ModelArtifactCorruptedError.
        """
        config_data = {
            "model_max_length": 128,
            "extra_special_tokens": {"some": "token"},
            "tokenizer_class": "DebertaV2Tokenizer",
        }
        (self.source_dir / "tokenizer_config.json").write_text(
            json.dumps(config_data), encoding="utf-8"
        )
        (self.source_dir / "tokenizer.json").write_text(
            '{"vocab": {}}', encoding="utf-8"
        )

        loader = ModelLoader(
            artifact_path=self.source_dir,
            staging_base_dir=self.test_staging_base,
        )
        content_hash = loader._compute_tokenizer_identity(self.source_dir)
        staged_dir = self.test_staging_base / f"tok_{content_hash}"
        # Pre-create empty directory (missing .complete, config, and tokenizer files)
        staged_dir.mkdir(parents=True, exist_ok=True)

        with self.assertRaises(ModelArtifactCorruptedError) as ctx:
            loader._prepare_tokenizer_dir(self.source_dir)
        self.assertIn("incomplete or corrupted", str(ctx.exception))

        # Crucial check: verify staged_dir was NOT deleted
        self.assertTrue(staged_dir.exists())

    def test_staging_multi_process_concurrency(self):
        """
        Verifies cross-process publication safety on the local platform.
        Spawns multiple separate OS child processes and synchronizes them at the exact
        point of publication (os.rename), forcing a reproducible race collision.
        """
        config_data = {
            "model_max_length": 128,
            "extra_special_tokens": {"some": "token"},
            "tokenizer_class": "DebertaV2Tokenizer",
        }
        (self.source_dir / "tokenizer_config.json").write_text(
            json.dumps(config_data), encoding="utf-8"
        )
        (self.source_dir / "tokenizer.json").write_text(
            '{"vocab": {}}', encoding="utf-8"
        )

        import subprocess
        import sys
        import time

        sync_dir = Path(tempfile.mkdtemp(prefix="test_mp_barrier_"))

        worker_script = (
            "import os, sys, time\n"
            "from pathlib import Path\n"
            "import analysis.model_loader.loader as loader_mod\n"
            "from analysis.model_loader.loader import ModelLoader\n"
            "src = Path(sys.argv[1])\n"
            "base = Path(sys.argv[2])\n"
            "barrier = Path(sys.argv[3])\n"
            "\n"
            "real_publish = loader_mod._atomic_publish_dir\n"
            "def barrier_publish(s, d):\n"
            "    ready_marker = barrier / f'ready_{os.getpid()}'\n"
            "    ready_marker.write_text('ready', encoding='utf-8')\n"
            "    deadline = time.perf_counter() + 10.0\n"
            "    while not (barrier / 'release.gate').is_file() and time.perf_counter() < deadline:\n"
            "        time.sleep(0.005)\n"
            "    return real_publish(s, d)\n"
            "loader_mod._atomic_publish_dir = barrier_publish\n"
            "\n"
            "loader = ModelLoader(artifact_path=src, staging_base_dir=base)\n"
            "staged = loader._prepare_tokenizer_dir(src)\n"
            "print('RESULT:' + str(staged))\n"
        )

        num_processes = 4
        procs = []
        try:
            for _ in range(num_processes):
                p = subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        worker_script,
                        str(self.source_dir),
                        str(self.test_staging_base),
                        str(sync_dir),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                procs.append(p)

            # Wait for all child processes to construct their staging dirs and reach the rename barrier
            barrier_deadline = time.perf_counter() + 10.0
            while (
                len(list(sync_dir.glob("ready_*"))) < num_processes
                and time.perf_counter() < barrier_deadline
            ):
                time.sleep(0.02)

            ready_count = len(list(sync_dir.glob("ready_*")))
            self.assertEqual(
                ready_count,
                num_processes,
                f"Expected {num_processes} processes to reach publication barrier, got {ready_count}",
            )

            # Release all child processes simultaneously to force the publication race
            (sync_dir / "release.gate").write_text("go", encoding="utf-8")

            results = []
            for p in procs:
                stdout, stderr = p.communicate(timeout=15)
                self.assertEqual(
                    p.returncode,
                    0,
                    f"Subprocess {p.pid} failed with code {p.returncode}: {stderr}",
                )
                for line in stdout.splitlines():
                    if line.startswith("RESULT:"):
                        results.append(line[len("RESULT:") :])

            self.assertEqual(len(results), num_processes)
            first_path = results[0]
            for path_str in results:
                self.assertEqual(path_str, first_path)

            staged_dir = Path(first_path)
            self.assertTrue((staged_dir / ".complete").is_file())
            self.assertTrue((staged_dir / "tokenizer.json").is_file())
            self.assertTrue((staged_dir / "tokenizer_config.json").is_file())
        finally:
            shutil.rmtree(sync_dir, ignore_errors=True)


class AtomicPublishDirTests(TestCase):
    """
    Direct unit tests for _atomic_publish_dir covering Windows NTFS and Linux renameat2.
    """

    def setUp(self):
        self.test_base = Path(tempfile.mkdtemp(prefix="test_atomic_pub_"))
        self.src = self.test_base / "src"
        self.src.mkdir()
        (self.src / "sample.txt").write_text("content", encoding="utf-8")
        self.dst = self.test_base / "dst"

    def tearDown(self):
        shutil.rmtree(self.test_base, ignore_errors=True)

    def test_windows_refuses_existing_empty_destination(self):
        import sys

        if sys.platform != "win32":
            self.skipTest("Windows-specific native MoveFileEx test")

        # Create dst as an empty directory
        self.dst.mkdir()
        with self.assertRaises(FileExistsError):
            _atomic_publish_dir(self.src, self.dst)
        # Verify dst still exists and was not overwritten
        self.assertTrue(self.dst.is_dir())
        self.assertFalse((self.dst / "sample.txt").exists())

    @patch("sys.platform", "linux")
    @patch("ctypes.CDLL")
    def test_linux_renameat2_invoked_with_noreplace_flags(self, mock_cdll):
        mock_libc = MagicMock()
        mock_cdll.return_value = mock_libc
        mock_libc.renameat2.return_value = 0

        _atomic_publish_dir(self.src, self.dst)

        mock_libc.renameat2.assert_called_once()
        args = mock_libc.renameat2.call_args[0]
        self.assertEqual(args[0], -100)  # AT_FDCWD
        self.assertEqual(args[2], -100)  # AT_FDCWD
        self.assertEqual(args[4].value, 1)  # RENAME_NOREPLACE

    @patch("sys.platform", "linux")
    @patch("ctypes.CDLL")
    @patch("ctypes.get_errno", return_value=errno.EEXIST)
    def test_linux_renameat2_eexist_raises_file_exists_error(
        self, _mock_errno, mock_cdll
    ):
        mock_libc = MagicMock()
        mock_cdll.return_value = mock_libc
        mock_libc.renameat2.return_value = -1

        with self.assertRaises(FileExistsError):
            _atomic_publish_dir(self.src, self.dst)

    @patch("sys.platform", "linux")
    @patch("ctypes.CDLL")
    @patch("ctypes.get_errno", return_value=errno.ENOSYS)
    def test_linux_renameat2_enosys_raises_model_loading_error(
        self, _mock_errno, mock_cdll
    ):
        mock_libc = MagicMock()
        mock_cdll.return_value = mock_libc
        mock_libc.renameat2.return_value = -1

        with self.assertRaises(ModelLoadingError) as ctx:
            _atomic_publish_dir(self.src, self.dst)
        self.assertIn("does not support RENAME_NOREPLACE", str(ctx.exception))

    @patch("sys.platform", "linux")
    @patch("ctypes.CDLL")
    @patch(
        "ctypes.get_errno",
        return_value=getattr(errno, "EOPNOTSUPP", getattr(errno, "ENOTSUP", 95)),
    )
    def test_linux_renameat2_eopnotsupp_raises_model_loading_error(
        self, _mock_errno, mock_cdll
    ):
        mock_libc = MagicMock()
        mock_cdll.return_value = mock_libc
        mock_libc.renameat2.return_value = -1

        with self.assertRaises(ModelLoadingError) as ctx:
            _atomic_publish_dir(self.src, self.dst)
        self.assertIn("does not support RENAME_NOREPLACE", str(ctx.exception))

    @patch("sys.platform", "linux")
    @patch("ctypes.CDLL")
    @patch("platform.machine", return_value="x86_64")
    def test_linux_syscall_fallback_when_renameat2_wrapper_missing(
        self, _mock_machine, mock_cdll
    ):
        mock_libc = MagicMock(spec=["syscall"])
        mock_cdll.return_value = mock_libc
        mock_libc.syscall.return_value = 0

        _atomic_publish_dir(self.src, self.dst)

        mock_libc.syscall.assert_called_once()
        args = mock_libc.syscall.call_args[0]
        self.assertEqual(args[0].value, 316)  # SYS_renameat2 for x86_64
        self.assertEqual(args[1], -100)  # AT_FDCWD
        self.assertEqual(args[3], -100)  # AT_FDCWD
        self.assertEqual(args[5].value, 1)  # RENAME_NOREPLACE

    @patch("sys.platform", "linux")
    @patch("ctypes.CDLL")
    @patch("platform.machine", return_value="sparc64")
    def test_linux_unmapped_architecture_raises_model_loading_error(
        self, _mock_machine, mock_cdll
    ):
        mock_libc = MagicMock(spec=["syscall"])
        mock_cdll.return_value = mock_libc

        with self.assertRaises(ModelLoadingError) as ctx:
            _atomic_publish_dir(self.src, self.dst)
        self.assertIn("does not have a mapped SYS_renameat2", str(ctx.exception))

    @patch("sys.platform", "linux")
    @patch("ctypes.CDLL")
    def test_linux_no_renameat2_or_syscall_raises_model_loading_error(self, mock_cdll):
        mock_libc = MagicMock(spec=[])  # Neither renameat2 nor syscall
        mock_cdll.return_value = mock_libc

        with self.assertRaises(ModelLoadingError) as ctx:
            _atomic_publish_dir(self.src, self.dst)
        self.assertIn("does not provide renameat2 or syscall", str(ctx.exception))


class TokenizerConfigRootValidationTests(TestCase):
    """
    Tests verifying that tokenizer_config.json with non-dictionary roots are rejected.
    """

    def setUp(self):
        self.source_dir = Path(tempfile.mkdtemp(prefix="root_val_"))
        self.test_staging_base = Path(tempfile.mkdtemp(prefix="test_root_val_tok_"))
        (self.source_dir / "tokenizer.json").write_text(
            '{"vocab": {}}', encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.test_staging_base, ignore_errors=True)

    def _assert_root_rejected(self, raw_json: str, expected_type_name: str):
        (self.source_dir / "tokenizer_config.json").write_text(
            raw_json, encoding="utf-8"
        )
        loader = ModelLoader(
            artifact_path=self.source_dir,
            staging_base_dir=self.test_staging_base,
        )
        with self.assertRaises(ModelArtifactCorruptedError) as ctx:
            loader._prepare_tokenizer_dir(self.source_dir)
        self.assertIn(f"got {expected_type_name}", str(ctx.exception))

    def test_list_root_rejected(self):
        self._assert_root_rejected(json.dumps(["item1", "item2"]), "list")

    def test_string_root_rejected(self):
        self._assert_root_rejected(json.dumps("invalid string config"), "str")

    def test_int_root_rejected(self):
        self._assert_root_rejected(json.dumps(12345), "int")

    def test_null_root_rejected(self):
        self._assert_root_rejected(json.dumps(None), "NoneType")

    def test_bool_root_rejected(self):
        self._assert_root_rejected(json.dumps(True), "bool")


class ArchitectureAndLabelValidationTests(TestCase):
    """
    Tests for _verify_and_load_config() ensuring model_type, num_labels, and label mapping.
    """

    def setUp(self):
        self.artifact_dir = Path(tempfile.mkdtemp(prefix="arch_val_"))
        (self.artifact_dir / "config.json").write_text("{}", encoding="utf-8")
        self.loader = ModelLoader(artifact_path=self.artifact_dir)

    def tearDown(self):
        shutil.rmtree(self.artifact_dir, ignore_errors=True)

    @patch("transformers.AutoConfig.from_pretrained")
    def test_unsupported_model_type_rejected(self, mock_auto_config):
        cfg = MagicMock(spec=PretrainedConfig)
        cfg.model_type = "roberta"
        cfg.num_labels = 2
        cfg.id2label = {0: "CREDIBLE", 1: "MISINFORMATION"}
        mock_auto_config.return_value = cfg

        with self.assertRaises(ModelArtifactCorruptedError) as ctx:
            self.loader._verify_and_load_config(self.artifact_dir)
        self.assertIn("expected 'deberta-v2', got 'roberta'", str(ctx.exception))

    @patch("transformers.AutoConfig.from_pretrained")
    def test_unsupported_num_labels_rejected(self, mock_auto_config):
        cfg = MagicMock(spec=PretrainedConfig)
        cfg.model_type = "deberta-v2"
        cfg.num_labels = 3
        cfg.id2label = {0: "CREDIBLE", 1: "MISINFORMATION", 2: "UNVERIFIED"}
        mock_auto_config.return_value = cfg

        with self.assertRaises(ModelArtifactCorruptedError) as ctx:
            self.loader._verify_and_load_config(self.artifact_dir)
        self.assertIn("expected 2, got 3", str(ctx.exception))

    @patch("transformers.AutoConfig.from_pretrained")
    def test_invalid_label_mapping_rejected(self, mock_auto_config):
        cfg = MagicMock(spec=PretrainedConfig)
        cfg.model_type = "deberta-v2"
        cfg.num_labels = 2
        cfg.id2label = {0: "MISINFORMATION", 1: "CREDIBLE"}  # Inverted mapping
        mock_auto_config.return_value = cfg

        with self.assertRaises(ModelArtifactCorruptedError) as ctx:
            self.loader._verify_and_load_config(self.artifact_dir)
        self.assertIn("Invalid label mapping", str(ctx.exception))


class DeviceResolutionTests(TestCase):
    """
    Tests for device resolution semantics, CPU fallback, and explicit CUDA error handling.
    """

    def test_explicit_cpu_resolution(self):
        loader = ModelLoader()
        dev = loader._resolve_device("cpu")
        self.assertEqual(dev, torch.device("cpu"))

    @patch("torch.cuda.is_available", return_value=False)
    def test_explicit_cuda_requested_without_gpu_raises(self, _mock_cuda):
        loader = ModelLoader()
        with self.assertRaises(ModelLoadingError) as ctx:
            loader._resolve_device("cuda")
        self.assertIn("CUDA is not available", str(ctx.exception))

    def test_invalid_device_string_raises(self):
        loader = ModelLoader()
        with self.assertRaises(ModelLoadingError) as ctx:
            loader._resolve_device("tpu")
        self.assertIn("Invalid INFOTRUST_INFERENCE_DEVICE", str(ctx.exception))


class DebertaAdapterProtocolAndExecutionTests(TestCase):
    """
    Tests for DebertaModelAdapter conformance, input validation, deterministic label mapping,
    and output validation using controlled test doubles.
    """

    def setUp(self):
        self.mock_model = MagicMock()
        self.mock_tokenizer = MagicMock()
        self.mock_loader = MagicMock(spec=ModelLoader)
        self.mock_loader.device = torch.device("cpu")
        self.mock_loader.model_version = "v1"
        self.mock_loader.artifact_path = Path("/mock/model")
        self.mock_loader.get_model_and_tokenizer.return_value = (
            self.mock_model,
            self.mock_tokenizer,
        )

        self.adapter = DebertaModelAdapter(loader=self.mock_loader)

    def test_adapter_conforms_to_protocol(self):
        self.assertIsInstance(self.adapter, ModelAdapterProtocol)

    def test_non_string_input_rejected(self):
        for invalid in [None, 123, 45.6, [], {}]:
            with self.assertRaises(TypeError):
                self.adapter.predict(invalid)  # type: ignore

    def test_empty_or_whitespace_input_rejected(self):
        for invalid in ["", "   ", "\t\n  "]:
            with self.assertRaises(ValueError):
                self.adapter.predict(invalid)

    def test_tokenizer_called_with_expected_arguments(self):
        self.mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[1, 2, 3]]),
            "attention_mask": torch.tensor([[1, 1, 1]]),
        }
        outputs = MagicMock()
        outputs.logits = torch.tensor([[2.0, -1.0]])
        self.mock_model.return_value = outputs

        self.adapter.predict("Test claim text statement.")

        self.mock_tokenizer.assert_called_once_with(
            "Test claim text statement.",
            max_length=128,
            truncation=True,
            padding=True,
            return_tensors="pt",
        )

    def test_label_mapping_credible_when_class_0_wins(self):
        self.mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[1, 2]]),
            "attention_mask": torch.tensor([[1, 1]]),
        }
        outputs = MagicMock()
        outputs.logits = torch.tensor([[2.5, -1.0]])
        self.mock_model.return_value = outputs

        result = self.adapter.predict("Claim predicting credible.")
        self.assertIsInstance(result, ModelOutput)
        self.assertEqual(result.prediction, ModelPrediction.CREDIBLE)
        self.assertGreater(result.confidence, 0.5)
        self.assertLessEqual(result.confidence, 1.0)

    def test_label_mapping_misinformation_when_class_1_wins(self):
        self.mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[1, 2]]),
            "attention_mask": torch.tensor([[1, 1]]),
        }
        outputs = MagicMock()
        outputs.logits = torch.tensor([[-1.2, 3.4]])
        self.mock_model.return_value = outputs

        result = self.adapter.predict("Claim predicting misinformation.")
        self.assertIsInstance(result, ModelOutput)
        self.assertEqual(result.prediction, ModelPrediction.MISINFORMATION)
        self.assertGreater(result.confidence, 0.5)
        self.assertLessEqual(result.confidence, 1.0)

    def test_tied_logits_yields_exact_half_confidence(self):
        self.mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[1, 2]]),
            "attention_mask": torch.tensor([[1, 1]]),
        }
        outputs = MagicMock()
        outputs.logits = torch.tensor([[0.0, 0.0]])
        self.mock_model.return_value = outputs

        result = self.adapter.predict("Tied claim.")
        self.assertEqual(result.confidence, 0.5)

    def test_model_forward_pass_runtime_error_wrapped(self):
        self.mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[1, 2]]),
            "attention_mask": torch.tensor([[1, 1]]),
        }
        self.mock_model.side_effect = RuntimeError("CUDA out of memory")

        with self.assertRaises(ModelInferenceError) as ctx:
            self.adapter.predict("Claim triggering failure.")
        self.assertIn("Model forward pass failed", str(ctx.exception))

    def test_model_forward_pass_index_error_wrapped(self):
        self.mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[1, 2]]),
            "attention_mask": torch.tensor([[1, 1]]),
        }
        outputs = MagicMock()
        outputs.logits = torch.empty(0)  # triggers IndexError on indexing [0]
        self.mock_model.return_value = outputs

        with self.assertRaises(ModelInferenceError) as ctx:
            self.adapter.predict("Claim triggering indexing failure.")
        self.assertIn("Model forward pass failed", str(ctx.exception))

    def test_model_forward_pass_value_error_wrapped(self):
        self.mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[1, 2]]),
            "attention_mask": torch.tensor([[1, 1]]),
        }
        self.mock_model.side_effect = ValueError("Invalid tensor value")

        with self.assertRaises(ModelInferenceError) as ctx:
            self.adapter.predict("Claim triggering value error.")
        self.assertIn("Model forward pass failed", str(ctx.exception))

    def test_tokenization_runtime_error_wrapped(self):
        self.mock_tokenizer.side_effect = RuntimeError("Tokenizer backend failure")

        with self.assertRaises(ModelInferenceError) as ctx:
            self.adapter.predict("Claim triggering tokenization error.")
        self.assertIn("Tokenization failed", str(ctx.exception))

    def test_tokenization_value_error_wrapped(self):
        self.mock_tokenizer.side_effect = ValueError("Invalid sequence")

        with self.assertRaises(ModelInferenceError) as ctx:
            self.adapter.predict("Claim triggering tokenization value error.")
        self.assertIn("Tokenization failed", str(ctx.exception))

    def test_programming_error_attribute_error_not_masked(self):
        self.mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[1, 2]]),
            "attention_mask": torch.tensor([[1, 1]]),
        }
        # Simulate unexpected code bug (e.g. model output object missing logits attribute)
        self.mock_model.side_effect = AttributeError("Unexpected NoneType attribute")

        with self.assertRaises(AttributeError):
            self.adapter.predict("Claim encountering unexpected bug.")

    def test_programming_error_type_error_not_masked(self):
        self.mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[1, 2]]),
            "attention_mask": torch.tensor([[1, 1]]),
        }
        # Simulate unexpected TypeError inside forward pass
        self.mock_model.side_effect = TypeError("Invalid argument types")

        with self.assertRaises(TypeError):
            self.adapter.predict("Claim encountering type error.")


class InstanceCachingTests(TestCase):
    """
    Tests ensuring that caching is strictly per-ModelLoader instance and thread-safe.
    """

    def test_repeated_predictions_reuse_model_instance(self):
        mock_model = MagicMock()
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[1]]),
            "attention_mask": torch.tensor([[1]]),
        }
        out = MagicMock()
        out.logits = torch.tensor([[1.0, 0.0]])
        mock_model.return_value = out

        loader = ModelLoader()
        loader._model = mock_model
        loader._tokenizer = mock_tokenizer
        loader._device = torch.device("cpu")
        loader._resolved_path = Path("/mock")
        loader._load_count = 1

        adapter = DebertaModelAdapter(loader=loader)

        # First call
        res1 = adapter.predict("Claim 1")
        # Second call
        res2 = adapter.predict("Claim 2")

        self.assertEqual(loader.load_count, 1)
        self.assertIs(loader.model, mock_model)
        self.assertIs(loader.tokenizer, mock_tokenizer)
        self.assertEqual(res1.prediction, ModelPrediction.CREDIBLE)
        self.assertEqual(res2.prediction, ModelPrediction.CREDIBLE)

    def test_distinct_loaders_have_independent_caches(self):
        loader_a = ModelLoader(model_version="v1")
        loader_b = ModelLoader(model_version="v2")

        loader_a._load_count = 1
        loader_a._model = MagicMock()

        self.assertEqual(loader_a.load_count, 1)
        self.assertEqual(loader_b.load_count, 0)
        self.assertIsNone(loader_b._model)
