import errno
import hashlib
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

from django.conf import settings


def should_allow_missing_manifest() -> bool:
    """
    Determines if unmanifested artifact loading is permitted.
    Requires BOTH an explicit development/test environment AND an explicit opt-in setting.
    Fails closed in production, staging, and unknown environments.
    """
    env = getattr(settings, "INFOTRUST_ENV", "production").strip().lower()
    is_dev_or_test = env in ("development", "test", "local")
    opt_in = getattr(settings, "MODEL_ALLOW_UNMANIFESTED_ARTIFACTS", False)
    return bool(is_dev_or_test and opt_in)


class ModelLoadingError(RuntimeError):
    """Base exception for all failures occurring during model artifact resolution or loading."""

    pass


class ModelArtifactNotFoundError(ModelLoadingError):
    """Raised when the artifact directory or one of its mandatory files is missing."""

    def __init__(
        self,
        message: str,
        path: str,
        missing_files: Optional[list[str]] = None,
    ):
        super().__init__(message)
        self.path = path
        self.missing_files = missing_files or []


class ModelArtifactCorruptedError(ModelLoadingError):
    """Raised when artifact files exist but are unreadable, invalid JSON, or have an unsupported architecture."""

    pass


class TokenizerIncompatibilityError(ModelLoadingError):
    """Raised strictly when AutoTokenizer fails to construct the fast tokenizer from tokenizer.json."""

    pass


def _validate_staged_dir(staged_dir: Path) -> bool:
    """
    Verifies that a staging directory is fully formed, readable, and valid.
    Checks for the completion sentinel, non-empty tokenizer.json, and a valid JSON object config.
    """
    sentinel = staged_dir / ".complete"
    config_path = staged_dir / "tokenizer_config.json"
    tok_path = staged_dir / "tokenizer.json"

    if not sentinel.is_file() or not config_path.is_file() or not tok_path.is_file():
        return False

    try:
        if tok_path.stat().st_size == 0:
            return False
        data = json.loads(config_path.read_bytes().decode("utf-8"))
        if not isinstance(data, dict):
            return False
        return True
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return False


def _is_destination_exists_collision(err: OSError) -> bool:
    """
    Identifies genuine destination-exists collisions using strict error classification.
    Excludes PermissionError, ENOSPC, and unrelated filesystem failures.
    """
    if isinstance(err, FileExistsError):
        return True
    if hasattr(err, "errno") and err.errno in (errno.EEXIST, errno.ENOTEMPTY):
        return True
    return False


def _wait_for_valid_staged_dir(
    staged_dir: Path, timeout: float = 1.0, interval: float = 0.05
) -> bool:
    """
    Polls staged_dir up to timeout seconds until _validate_staged_dir returns True.
    Allows concurrent publishers to complete directory movement and file flushing.
    """
    import time

    end_time = time.perf_counter() + timeout
    while time.perf_counter() < end_time:
        if _validate_staged_dir(staged_dir):
            return True
        time.sleep(interval)
    return _validate_staged_dir(staged_dir)


def _atomic_publish_dir(src: Path, dst: Path) -> None:
    """
    Publishes a private staging directory to the destination with atomic no-overwrite semantics.

    Platform Semantics:
    - Windows (NTFS): os.rename() maps to Win32 MoveFileExW without MOVEFILE_REPLACE_EXISTING,
      which atomically refuses any existing destination (file, empty directory, or non-empty directory)
      with FileExistsError (WinError 183).
    - Linux (Kernel >= 3.15): Uses renameat2(AT_FDCWD, src, AT_FDCWD, dst, RENAME_NOREPLACE).
      RENAME_NOREPLACE (flag=1) atomically prevents overwriting any existing destination (file, empty
      directory, or non-empty directory) and returns errno.EEXIST (17) without modifying the destination.
      If RENAME_NOREPLACE is unsupported by the kernel or filesystem (ENOSYS/EINVAL/EOPNOTSUPP/ENOTSUP),
      fails explicitly with ModelLoadingError rather than silently falling back to a replacement-prone operation.
    - Non-Linux POSIX Fallback (e.g. Darwin/BSD): Falls back to os.rename() if renameat2 is unavailable,
      with the documented limitation that empty directories can be replaced on platforms lacking RENAME_NOREPLACE.
    """
    import sys

    if sys.platform == "win32":
        os.rename(src, dst)
        return

    if sys.platform.startswith("linux"):
        import ctypes
        import platform

        AT_FDCWD = -100
        RENAME_NOREPLACE = 1  # Flag 1 << 0

        src_bytes = os.fsencode(src)
        dst_bytes = os.fsencode(dst)

        libc = ctypes.CDLL(None, use_errno=True)
        res = -1

        # 1. Try glibc 2.28+ wrapper with explicit argument and return types
        if hasattr(libc, "renameat2"):
            libc.renameat2.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            libc.renameat2.restype = ctypes.c_int
            res = libc.renameat2(
                AT_FDCWD,
                src_bytes,
                AT_FDCWD,
                dst_bytes,
                ctypes.c_uint(RENAME_NOREPLACE),
            )
        # 2. Try direct syscall for glibc < 2.28
        elif hasattr(libc, "syscall"):
            machine = platform.machine().lower()
            syscall_nr = None
            if machine in ("x86_64", "amd64"):
                syscall_nr = 316
            elif machine in ("aarch64", "arm64"):
                syscall_nr = 276
            elif machine in ("i386", "i686", "x86"):
                syscall_nr = 353

            if syscall_nr is not None:
                libc.syscall.argtypes = [
                    ctypes.c_long,
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_uint,
                ]
                libc.syscall.restype = ctypes.c_long
                res = libc.syscall(
                    ctypes.c_long(syscall_nr),
                    AT_FDCWD,
                    src_bytes,
                    AT_FDCWD,
                    dst_bytes,
                    ctypes.c_uint(RENAME_NOREPLACE),
                )
            else:
                raise ModelLoadingError(
                    f"Linux platform architecture '{machine}' does not have a mapped SYS_renameat2 syscall number."
                )
        else:
            raise ModelLoadingError(
                "Linux environment does not provide renameat2 or syscall in libc."
            )

        if res == 0:
            return

        err = ctypes.get_errno()
        if err in (errno.EEXIST, errno.ENOTEMPTY):
            raise FileExistsError(err, f"Target directory already exists: {dst}")

        unsupported_errs = {errno.ENOSYS, errno.EINVAL}
        if hasattr(errno, "EOPNOTSUPP"):
            unsupported_errs.add(errno.EOPNOTSUPP)
        if hasattr(errno, "ENOTSUP"):
            unsupported_errs.add(errno.ENOTSUP)

        if err in unsupported_errs:
            raise ModelLoadingError(
                f"Linux kernel or filesystem does not support RENAME_NOREPLACE (errno {err}: {os.strerror(err)}). "
                "Silent fallback to os.rename() is disabled to prevent directory replacement races."
            )
        raise OSError(err, os.strerror(err), str(dst))

    # Non-Linux POSIX fallback (e.g. Darwin/macOS)
    os.rename(src, dst)


def _compute_tokenizer_identity(source_dir: Path) -> str:
    """
    Computes a deterministic content hash across all tokenizer definition files.
    Ensures that modifications to any tokenizer file automatically produce a distinct cache key.
    Source files are opened in read-only binary mode; original files are never modified.
    """
    hasher = hashlib.sha256()
    for filename in sorted(
        ["tokenizer_config.json", "tokenizer.json", "special_tokens_map.json"]
    ):
        filepath = source_dir / filename
        if filepath.is_file():
            hasher.update(filename.encode("utf-8"))
            try:
                hasher.update(filepath.read_bytes())
            except OSError as err:
                raise ModelLoadingError(
                    f"Filesystem error reading tokenizer file {filepath}: {err}"
                ) from err
    return hasher.hexdigest()[:16]


def resolve_artifact_path(raw_path: Optional[str | Path] = None) -> Path:
    """
    Resolves the model artifact directory across local development, Docker, and CI.

    Search Order:
    1. If raw_path is given and absolute -> use directly.
    2. If raw_path is given and relative:
       a. Check relative to settings.BASE_DIR (handles Docker /app and backend/ subfolder execution).
       b. Check relative to settings.BASE_DIR.parent (handles local dev with repo-root folders like InfoTrustModels/).
    3. If raw_path is None or empty:
       Check configured default locations in order:
       - BASE_DIR / "model_artifacts" / "final_model_corrected"
       - BASE_DIR.parent / "InfoTrustModels" / "final_model_corrected"
       - BASE_DIR.parent / "model_artifacts" / "final_model_corrected"
       - BASE_DIR / "model_artifacts"
       - BASE_DIR.parent / "InfoTrustModels"
    4. Flexible checkpoint unwrapping:
       - If resolved directory contains model.safetensors, return it.
       - If resolved directory contains a subfolder 'final_model_corrected' with model.safetensors, return the subfolder.
    5. If all candidates fail -> raise ModelArtifactNotFoundError listing all attempted paths.
    """
    base_dir = getattr(settings, "BASE_DIR", Path.cwd())
    attempted_paths: list[str] = []

    candidates: list[Path] = []
    if raw_path:
        p = Path(raw_path)
        if p.is_absolute():
            candidates.append(p)
        else:
            candidates.append(base_dir / p)
            if hasattr(base_dir, "parent") and base_dir.parent != base_dir:
                candidates.append(base_dir.parent / p)
    else:
        # Check standard defaults
        candidates.append(base_dir / "model_artifacts" / "final_model_corrected")
        if hasattr(base_dir, "parent") and base_dir.parent != base_dir:
            candidates.append(
                base_dir.parent / "InfoTrustModels" / "final_model_corrected"
            )
            candidates.append(
                base_dir.parent / "model_artifacts" / "final_model_corrected"
            )
        candidates.append(base_dir / "model_artifacts")
        if hasattr(base_dir, "parent") and base_dir.parent != base_dir:
            candidates.append(base_dir.parent / "InfoTrustModels")

    for cand in candidates:
        attempted_paths.append(str(cand))
        if cand.is_dir():
            if (cand / "model.safetensors").is_file():
                return cand.resolve()
            # Check child final_model_corrected
            sub = cand / "final_model_corrected"
            attempted_paths.append(str(sub))
            if sub.is_dir() and (sub / "model.safetensors").is_file():
                return sub.resolve()

    raise ModelArtifactNotFoundError(
        f"Model artifact directory not found. Attempted paths: {attempted_paths}",
        path=str(raw_path or "default locations"),
        missing_files=["model.safetensors"],
    )


class ModelLoader:
    """
    Thread-safe, process-cached loader for fine-tuned DeBERTa model artifacts and tokenizers.
    Implements lazy double-checked locking, manifest schema validation, cold SHA-256 integrity verification,
    canonical directory cache isolation, and device synchronization.
    """

    _compute_tokenizer_identity = staticmethod(_compute_tokenizer_identity)
    _atomic_publish_dir = staticmethod(_atomic_publish_dir)

    _model_load_lock = threading.Lock()
    _cached_model: Optional[Any] = None
    _cached_tokenizer: Optional[Any] = None
    _cached_fingerprint: Optional[str] = None
    _cached_artifact_dir: Optional[str] = None

    @classmethod
    def reset_cache(cls) -> None:
        """Resets the process-wide model and tokenizer cache (for testing/reloads)."""
        with cls._model_load_lock:
            cls._cached_model = None
            cls._cached_tokenizer = None
            cls._cached_fingerprint = None
            cls._cached_artifact_dir = None

    def __init__(
        self,
        artifact_path: Optional[str | Path] = None,
        model_version: Optional[str] = None,
        device: Optional[Any] = None,
        staging_base_dir: Optional[str | Path] = None,
    ):
        self._raw_artifact_path = artifact_path
        self._model_version = str(
            model_version
            or getattr(settings, "MODEL_VERSION", os.environ.get("MODEL_VERSION", "v1"))
        )
        self._device_override = device
        self._staging_base_dir = (
            Path(staging_base_dir) if staging_base_dir is not None else None
        )

        self._resolved_path: Optional[Path] = None
        self._device: Optional[Any] = None
        self._model: Optional[Any] = None
        self._tokenizer: Optional[Any] = None
        self._fingerprint: Optional[str] = None
        self._load_count: int = 0
        import threading

        self._lock = threading.Lock()

    @property
    def staging_base_dir(self) -> Path:
        if self._staging_base_dir is not None:
            return self._staging_base_dir
        return Path(tempfile.gettempdir()) / "infotrust_tokenizer_cache"

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def artifact_path(self) -> Optional[Path]:
        return self._resolved_path

    @property
    def artifact_fingerprint(self) -> str:
        """
        Returns the verified cryptographic artifact fingerprint bound to this validated model instance.
        Triggers model resolution and manifest validation if not already executed.
        """
        if self._fingerprint is None:
            self.get_model_and_tokenizer()
        return self._fingerprint

    @property
    def device(self) -> Any:
        if self._device is None:
            self._device = self._resolve_device(self._device_override)
        return self._device

    @property
    def load_count(self) -> int:
        return self._load_count

    @property
    def model(self) -> Any:
        if self._model is None:
            self.get_model_and_tokenizer()
        return self._model

    @property
    def tokenizer(self) -> Any:
        if self._tokenizer is None:
            self.get_model_and_tokenizer()
        return self._tokenizer

    def _resolve_device(self, override: Optional[Any] = None) -> Any:
        import torch

        if override is not None:
            if isinstance(override, torch.device):
                return override
            device_env = str(override).strip().lower()
        else:
            device_env = (
                os.environ.get("INFOTRUST_INFERENCE_DEVICE", "").strip().lower()
            )

        if not device_env or device_env == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")

        if device_env == "cpu":
            return torch.device("cpu")

        if device_env.startswith("cuda"):
            if not torch.cuda.is_available():
                raise ModelLoadingError(
                    f"CUDA device '{device_env}' was explicitly requested via INFOTRUST_INFERENCE_DEVICE, "
                    "but CUDA is not available in this environment. Silent CPU fallback is prohibited."
                )
            try:
                dev = torch.device(device_env)
                if dev.index is not None and dev.index >= torch.cuda.device_count():
                    raise ModelLoadingError(
                        f"CUDA device index {dev.index} is out of range. "
                        f"Available device count: {torch.cuda.device_count()}."
                    )
                return dev
            except RuntimeError as err:
                raise ModelLoadingError(
                    f"Invalid CUDA device specification '{device_env}': {err}"
                ) from err

        raise ModelLoadingError(
            f"Invalid INFOTRUST_INFERENCE_DEVICE='{device_env}'. "
            "Supported values are 'auto', 'cpu', or valid CUDA identifiers (e.g. 'cuda', 'cuda:0')."
        )

    def _prepare_tokenizer_dir(self, source_dir: Path) -> Path:
        """
        Prepares a fast-tokenizer compatible configuration without mutating the original artifact.
        Normalizes tokenizer_config.json in a private temporary directory before publishing
        to a deterministic cache directory via os.rename.

        Platform Semantics & Concurrency Boundaries:
        - Windows (NTFS): os.rename provides strict no-overwrite semantics (raises FileExistsError
          if staged_dir exists, whether empty or non-empty).
        - POSIX (Linux): os.rename provides no-overwrite semantics against existing non-empty
          directories (raises OSError with ENOTEMPTY or EEXIST). POSIX rename over an existing empty
          directory would succeed; to prevent silent replacement of pre-existing empty or corrupt
          directories, this method checks staged_dir.exists() prior to publication and raises
          ModelArtifactCorruptedError if an existing directory remains invalid.
        - Concurrent Publication: When competing processes concurrently publish, the winner populates
          staged_dir with non-empty files and a completion marker; the loser's os.rename fails with a
          destination-exists collision, discards its private temporary directory, and validates the
          winner's published files.
        - Shared Cache Safety: Shared cache directories are never deleted (shutil.rmtree is never
          called on staged_dir), avoiding race conditions against concurrent readers or publishers.
        - Filesystem Limitations: Rename atomicity and collision semantics are verified on the local
          NTFS filesystem. Behavior on distributed networked filesystems (NFS, SMB) remains unverified.
        """
        config_file = source_dir / "tokenizer_config.json"
        if not config_file.is_file():
            raise ModelArtifactNotFoundError(
                f"tokenizer_config.json not found in {source_dir}",
                path=str(source_dir),
                missing_files=["tokenizer_config.json"],
            )

        try:
            raw_bytes = config_file.read_bytes()
            config_data = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise ModelArtifactCorruptedError(
                f"Failed to parse {config_file} as valid UTF-8 JSON: {err}"
            ) from err
        except OSError as err:
            raise ModelLoadingError(
                f"Filesystem error reading {config_file}: {err}"
            ) from err

        if not isinstance(config_data, dict):
            raise ModelArtifactCorruptedError(
                f"Invalid tokenizer_config.json root in {source_dir}: expected JSON object (dict), got {type(config_data).__name__}"
            )

        if "extra_special_tokens" not in config_data:
            return source_dir

        content_hash = _compute_tokenizer_identity(source_dir)
        staging_base = self.staging_base_dir
        staging_base.mkdir(parents=True, exist_ok=True)
        staged_dir = staging_base / f"tok_{content_hash}"

        if _validate_staged_dir(staged_dir):
            return staged_dir

        # If staged_dir exists but is not yet valid, another thread/process may be in the middle
        # of publishing. Poll briefly to see if it finishes publishing.
        if staged_dir.exists():
            if _wait_for_valid_staged_dir(staged_dir, timeout=0.5):
                return staged_dir
            raise ModelArtifactCorruptedError(
                f"Existing staged tokenizer directory at {staged_dir} is incomplete or corrupted. "
                "Shared cache directory will not be overwritten or deleted."
            )

        temp_staging = Path(tempfile.mkdtemp(prefix="tok_stage_tmp_", dir=staging_base))
        try:
            clean_config = {
                k: v for k, v in config_data.items() if k != "extra_special_tokens"
            }
            with open(
                temp_staging / "tokenizer_config.json", "w", encoding="utf-8"
            ) as f:
                json.dump(clean_config, f, indent=2, ensure_ascii=False)

            for companion in ["tokenizer.json", "special_tokens_map.json"]:
                src = source_dir / companion
                if src.is_file():
                    shutil.copy2(src, temp_staging / companion)

            (temp_staging / ".complete").write_text("ready", encoding="utf-8")

            if not _validate_staged_dir(temp_staging):
                raise ModelArtifactCorruptedError(
                    f"Private staging directory {temp_staging} failed validation prior to publication."
                )

            try:
                _atomic_publish_dir(temp_staging, staged_dir)
            except OSError as err:
                if _is_destination_exists_collision(err):
                    shutil.rmtree(temp_staging, ignore_errors=True)
                    # Poll briefly for the winning publisher to complete file flush
                    if _wait_for_valid_staged_dir(staged_dir, timeout=1.0):
                        return staged_dir
                    raise ModelArtifactCorruptedError(
                        f"Destination collision at {staged_dir}, but existing staged directory is incomplete or corrupted."
                    )

                raise ModelLoadingError(
                    f"Filesystem error during tokenizer publication: {err}"
                ) from err

            return staged_dir

        except Exception:
            shutil.rmtree(temp_staging, ignore_errors=True)
            raise

    def _verify_and_load_config(self, artifact_path: Path) -> Any:
        from transformers import AutoConfig

        config_file = artifact_path / "config.json"
        if not config_file.is_file():
            raise ModelArtifactNotFoundError(
                f"config.json not found in {artifact_path}",
                path=str(artifact_path),
                missing_files=["config.json"],
            )

        try:
            config = AutoConfig.from_pretrained(artifact_path, local_files_only=True)
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise ModelArtifactCorruptedError(
                f"Corrupt config.json at {config_file}: {err}"
            ) from err
        except Exception as err:
            raise ModelArtifactCorruptedError(
                f"Failed to load config from {artifact_path}: {err}"
            ) from err

        if getattr(config, "model_type", None) != "deberta-v2":
            raise ModelArtifactCorruptedError(
                f"Invalid model_type in config.json: expected 'deberta-v2', got '{getattr(config, 'model_type', None)}'"
            )

        if getattr(config, "num_labels", None) != 2:
            raise ModelArtifactCorruptedError(
                f"Invalid num_labels in config.json: expected 2, got {getattr(config, 'num_labels', None)}"
            )

        id2label = getattr(config, "id2label", {})
        mapped = {int(k): str(v).upper() for k, v in id2label.items()}
        if mapped.get(0) != "CREDIBLE" or mapped.get(1) != "MISINFORMATION":
            raise ModelArtifactCorruptedError(
                f"Invalid label mapping in config.json: expected {{0: 'CREDIBLE', 1: 'MISINFORMATION'}}, got {id2label}"
            )

        return config

    def validate_and_read_manifest(
        self,
        artifact_path: Path,
        verify_weights_digest: bool = False,
    ) -> tuple[dict[str, Any], str]:
        """
        Validates artifact integrity and manifest schema.
        - In production/staging: model_manifest.json is strictly required.
        - In dev/test: missing manifest falls back to structural signature check only if opted in.
        - On cold load (verify_weights_digest=True): streams model.safetensors and validates SHA-256 digest.
        - On warm hit (verify_weights_digest=False): checks schema, release_id, and file sizes/mtimes (<0.1ms).

        Returns:
            Tuple of (manifest_data, cache_fingerprint).
        """
        manifest_file = artifact_path / "model_manifest.json"
        if not manifest_file.is_file():
            if not should_allow_missing_manifest():
                env = getattr(settings, "INFOTRUST_ENV", "production").strip().lower()
                raise ModelArtifactNotFoundError(
                    f"model_manifest.json not found in {artifact_path} and unmanifested artifacts are disallowed in environment '{env}'.",
                    path=str(artifact_path),
                    missing_files=["model_manifest.json"],
                )

            # Fallback: structural signature check for development/test
            mandatory = ["config.json", "tokenizer.json", "model.safetensors"]
            missing = [f for f in mandatory if not (artifact_path / f).is_file()]
            if missing:
                raise ModelArtifactNotFoundError(
                    f"Mandatory artifact files missing in {artifact_path}: {missing}",
                    path=str(artifact_path),
                    missing_files=missing,
                )

            try:
                stat_cfg = (artifact_path / "config.json").stat()
                stat_tok = (artifact_path / "tokenizer.json").stat()
                stat_weights = (artifact_path / "model.safetensors").stat()
            except OSError as err:
                raise ModelArtifactCorruptedError(
                    f"Filesystem error inspecting artifacts in {artifact_path}: {err}"
                ) from err

            synthetic_fingerprint = (
                f"unmanifested:{self._model_version}:"
                f"{stat_cfg.st_size}_{stat_cfg.st_mtime_ns}:"
                f"{stat_tok.st_size}_{stat_tok.st_mtime_ns}:"
                f"{stat_weights.st_size}_{stat_weights.st_mtime_ns}:"
                f"{artifact_path.resolve()}"
            )
            return {"unmanifested": True}, synthetic_fingerprint

        # Manifest exists: strictly parse and validate schema
        try:
            raw_bytes = manifest_file.read_bytes()
            manifest = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise ModelArtifactCorruptedError(
                f"Corrupted model_manifest.json at {manifest_file}: {err}"
            ) from err
        except OSError as err:
            raise ModelLoadingError(
                f"Filesystem error reading {manifest_file}: {err}"
            ) from err

        if not isinstance(manifest, dict):
            raise ModelArtifactCorruptedError(
                f"Invalid model_manifest.json at {manifest_file}: expected JSON object (dict), got {type(manifest).__name__}"
            )

        release_id = manifest.get("release_id")
        if (
            isinstance(release_id, bool)
            or not isinstance(release_id, str)
            or not release_id.strip()
        ):
            raise ModelArtifactCorruptedError(
                f"Invalid or missing 'release_id' in {manifest_file}"
            )

        model_version = manifest.get("model_version")
        if isinstance(model_version, bool) or not isinstance(model_version, str):
            raise ModelArtifactCorruptedError(
                f"Invalid 'model_version' in {manifest_file}: expected string"
            )
        if self._model_version and model_version != self._model_version:
            raise ModelArtifactCorruptedError(
                f"Manifest model_version mismatch: expected '{self._model_version}', got '{model_version}'"
            )

        files = manifest.get("files")
        if not isinstance(files, dict):
            raise ModelArtifactCorruptedError(
                f"Invalid or missing 'files' dictionary in {manifest_file}"
            )

        required_files = ("config.json", "tokenizer.json", "model.safetensors")
        for req_f in required_files:
            if req_f not in files:
                raise ModelArtifactCorruptedError(
                    f"Manifest {manifest_file} missing required file entry for '{req_f}'"
                )
            entry = files[req_f]
            if not isinstance(entry, dict):
                raise ModelArtifactCorruptedError(
                    f"Manifest entry for '{req_f}' must be a dict, got {type(entry).__name__}"
                )

            # Strict SHA-256 string validation without type coercion
            raw_sha = entry.get("sha256")
            if isinstance(raw_sha, bool) or not isinstance(raw_sha, str):
                raise ModelArtifactCorruptedError(
                    f"Invalid sha256 type for {req_f} in manifest: expected hex string, got {type(raw_sha).__name__}"
                )
            sha_normalized = raw_sha.strip().lower()
            if len(sha_normalized) != 64 or any(
                c not in "0123456789abcdef" for c in sha_normalized
            ):
                raise ModelArtifactCorruptedError(
                    f"Invalid sha256 format for {req_f} in manifest: must be 64-char hex string, got '{raw_sha}'"
                )

            raw_size = entry.get("size")
            if (
                isinstance(raw_size, bool)
                or not isinstance(raw_size, int)
                or raw_size <= 0
            ):
                raise ModelArtifactCorruptedError(
                    f"Invalid size for {req_f} in manifest: expected positive int, got {raw_size!r}"
                )

            target_path = artifact_path / req_f
            if not target_path.is_file():
                raise ModelArtifactNotFoundError(
                    f"Manifest file '{req_f}' not found on disk at {target_path}",
                    path=str(artifact_path),
                    missing_files=[req_f],
                )

            try:
                st = target_path.stat()
            except OSError as err:
                raise ModelLoadingError(
                    f"Filesystem error reading {target_path}: {err}"
                ) from err

            if st.st_size != raw_size:
                raise ModelArtifactCorruptedError(
                    f"File size mismatch for {req_f}: manifest expects {raw_size} bytes, disk has {st.st_size} bytes"
                )

            # In-memory checksum validation for config and tokenizer on every check
            if req_f in ("config.json", "tokenizer.json"):
                computed = hashlib.sha256(target_path.read_bytes()).hexdigest()
                if computed.lower() != sha_normalized:
                    raise ModelArtifactCorruptedError(
                        f"SHA-256 digest mismatch for {req_f}: manifest expects {sha_normalized}, calculated {computed}"
                    )

            # Full weights SHA-256 validation only on cold load
            if req_f == "model.safetensors" and verify_weights_digest:
                hasher = hashlib.sha256()
                try:
                    with open(target_path, "rb") as f:
                        while chunk := f.read(65536):
                            hasher.update(chunk)
                except OSError as err:
                    raise ModelLoadingError(
                        f"Filesystem error hashing {target_path}: {err}"
                    ) from err
                computed_weights = hasher.hexdigest()
                if computed_weights.lower() != sha_normalized:
                    raise ModelArtifactCorruptedError(
                        f"SHA-256 digest mismatch for {req_f}: manifest expects {sha_normalized}, calculated {computed_weights}"
                    )

        fingerprint = (
            f"manifest:{release_id}:{model_version}:"
            f"{files['model.safetensors']['size']}:{files['model.safetensors']['sha256']}:"
            f"{artifact_path.resolve()}"
        )
        return manifest, fingerprint

    def get_model_and_tokenizer(self) -> tuple[Any, Any]:
        """
        Thread-safe cached initialization of model weights and tokenizer.
        Verifies manifest schema and directory isolation.
        Performs full cryptographic validation on cold load under _model_load_lock.
        """
        if self._model is not None and self._tokenizer is not None:
            return self._model, self._tokenizer

        resolved_path = resolve_artifact_path(self._raw_artifact_path)
        canonical_dir_str = str(resolved_path.resolve())

        # 1. Manifest / metadata validation (verify_weights_digest=False for fast cache hit)
        _, fingerprint = self.validate_and_read_manifest(
            resolved_path, verify_weights_digest=False
        )

        # 2. Fast cache hit check
        if (
            ModelLoader._cached_model is not None
            and ModelLoader._cached_tokenizer is not None
            and ModelLoader._cached_artifact_dir == canonical_dir_str
            and ModelLoader._cached_fingerprint == fingerprint
        ):
            self._model = ModelLoader._cached_model
            self._tokenizer = ModelLoader._cached_tokenizer
            self._resolved_path = resolved_path
            self._fingerprint = fingerprint
            return self._model, self._tokenizer

        # 3. Cache miss: serialize model loading under process-wide lock
        with ModelLoader._model_load_lock:
            if (
                ModelLoader._cached_model is not None
                and ModelLoader._cached_tokenizer is not None
                and ModelLoader._cached_artifact_dir == canonical_dir_str
                and ModelLoader._cached_fingerprint == fingerprint
            ):
                self._model = ModelLoader._cached_model
                self._tokenizer = ModelLoader._cached_tokenizer
                self._resolved_path = resolved_path
                self._fingerprint = fingerprint
                return self._model, self._tokenizer

            # Cold load: full SHA-256 verification of weights
            self.validate_and_read_manifest(resolved_path, verify_weights_digest=True)

            self._load(resolved_path)
            self._load_count += 1

            ModelLoader._cached_model = self._model
            ModelLoader._cached_tokenizer = self._tokenizer
            ModelLoader._cached_fingerprint = fingerprint
            ModelLoader._cached_artifact_dir = canonical_dir_str
            self._fingerprint = fingerprint

        return self._model, self._tokenizer

    def _load(self, resolved_path: Optional[Path] = None) -> None:
        import safetensors
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        if resolved_path is None:
            resolved_path = resolve_artifact_path(self._raw_artifact_path)
        self._resolved_path = resolved_path
        self._device = self._resolve_device(self._device_override)

        self._verify_and_load_config(resolved_path)

        tok_dir = self._prepare_tokenizer_dir(resolved_path)
        try:
            tokenizer = AutoTokenizer.from_pretrained(
                tok_dir, use_fast=True, local_files_only=True
            )
        except (OSError, ValueError, KeyError) as err:
            raise TokenizerIncompatibilityError(
                f"Failed to load fast tokenizer from {tok_dir}: {err}"
            ) from err

        weights_file = resolved_path / "model.safetensors"
        if not weights_file.is_file():
            raise ModelArtifactNotFoundError(
                f"model.safetensors not found in {resolved_path}",
                path=str(resolved_path),
                missing_files=["model.safetensors"],
            )

        try:
            model = AutoModelForSequenceClassification.from_pretrained(
                resolved_path, local_files_only=True, use_safetensors=True
            )
        except (safetensors.SafetensorError, OSError, ValueError) as err:
            raise ModelArtifactCorruptedError(
                f"Failed to load safetensors model weights from {resolved_path}: {err}"
            ) from err

        model.to(self._device)
        model.eval()

        self._model = model
        self._tokenizer = tokenizer
