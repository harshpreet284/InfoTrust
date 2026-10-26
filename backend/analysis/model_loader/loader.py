import errno
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from django.conf import settings


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
    Thread-safe, instance-bound loader for fine-tuned DeBERTa model artifacts and tokenizers.
    Implements lazy double-checked locking, path resolution, isolated tokenizer normalization,
    and device synchronization.
    """

    _compute_tokenizer_identity = staticmethod(_compute_tokenizer_identity)
    _atomic_publish_dir = staticmethod(_atomic_publish_dir)

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

    def get_model_and_tokenizer(self) -> tuple[Any, Any]:
        """
        Thread-safe lazy initialization of model weights and tokenizer.
        Guarantees that disk files and weights are loaded exactly once per ModelLoader instance.
        """
        if self._model is None or self._tokenizer is None:
            with self._lock:
                if self._model is None or self._tokenizer is None:
                    self._load()
                    self._load_count += 1
        return self._model, self._tokenizer

    def _load(self) -> None:
        import safetensors
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

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
