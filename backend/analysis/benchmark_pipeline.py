"""
InfoTrust AI-021: Performance Review Benchmark Harness.

Standalone, modular benchmark harness measuring:
1. Model loading time (subprocess isolation, OS cache state tracked)
2. Average inference time (DeBERTa-v3 on CPU, cache miss vs. hit across claim lengths)
3. Rule Engine heuristics evaluation latency
4. Fact-Check API latency (cache hit vs. simulated network vs. guarded live)
5. Narrative Activity Engine (failure path vs. mock orchestration; real embedding marked UNAVAILABLE)
6. Database query count & persistence lifecycle (SQL statements vs. transaction boundaries)
7. Overall synchronous pipeline execution time (fresh claim isolation)
8. Memory & working set usage (current RSS checkpoints, stability delta, peak working set)

Provides descriptive distribution statistics (Mean, Median, P95 continuous linear
interpolation, Sample StdDev with Bessel's correction).
"""

import argparse
import ctypes
import json
import logging
import math
import os
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

# Setup logger
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger("benchmark_pipeline")


# =============================================================================
# 1. Data Contracts & Serialization
# =============================================================================

VALID_STATUSES = frozenset({"SUCCESS", "UNAVAILABLE", "SKIPPED", "FAILED"})


@dataclass
class BenchmarkMetricResult:
    """Standardized representation of a single benchmark metric result."""

    status: str
    sample_count: int
    unit: str
    mean: Optional[float] = None
    median: Optional[float] = None
    p95: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    std_dev: Optional[float] = None
    qualification: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None

    def __post_init__(self):
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid benchmark status: {self.status}")
        # Invariant: Never allow non-finite values in numerical fields
        for field in ("mean", "median", "p95", "min", "max", "std_dev"):
            val = getattr(self, field)
            if val is not None and not math.isfinite(val):
                setattr(self, field, None)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Ensure all numeric floats are rounded cleanly for export
        for k in ("mean", "median", "p95", "min", "max", "std_dev"):
            if d[k] is not None and isinstance(d[k], (int, float)):
                d[k] = round(float(d[k]), 4)
        return d


@dataclass
class BenchmarkReport:
    """Full benchmark execution report containing metadata and category results."""

    metadata: dict[str, Any]
    categories: dict[str, dict[str, BenchmarkMetricResult]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "categories": {
                cat_name: {
                    metric_name: metric_result.to_dict()
                    for metric_name, metric_result in cat_metrics.items()
                }
                for cat_name, cat_metrics in self.categories.items()
            },
        }

    def to_text_table(self) -> str:
        lines: list[str] = []
        lines.append("=" * 100)
        lines.append(
            "                        INFOTRUST AI-021 PERFORMANCE REVIEW BENCHMARK REPORT"
        )
        lines.append("=" * 100)
        env = self.metadata.get("environment", {})
        lines.append(
            f"Host: {env.get('os', 'Unknown')} | CPU: {env.get('cpu_cores', 'Unknown')} Cores | "
            f"Torch: {env.get('torch_version', 'Unknown')} | Device: {env.get('inference_device', 'Unknown')}"
        )
        lines.append(
            f"Python: {env.get('python_version', 'Unknown')} | Database: {env.get('database_backend', 'Unknown')} | "
            f"Timestamp: {self.metadata.get('timestamp', 'Unknown')}"
        )
        lines.append("=" * 100)

        for cat_name, cat_metrics in self.categories.items():
            lines.append("")
            lines.append(f"CATEGORY: {cat_name.upper()}")
            lines.append("-" * 100)
            lines.append(
                f"{'Metric':<40} {'Status':<9} {'N':<5} {'Mean':<10} {'Median':<10} {'P95':<10} {'Min':<9} {'Max':<9} {'StdDev':<8}"
            )
            lines.append("-" * 100)
            for m_name, m in cat_metrics.items():
                unit_str = f" {m.unit}" if m.unit else ""
                mean_str = f"{m.mean:.2f}{unit_str}" if m.mean is not None else "-"
                med_str = f"{m.median:.2f}{unit_str}" if m.median is not None else "-"
                p95_str = f"{m.p95:.2f}{unit_str}" if m.p95 is not None else "-"
                min_str = f"{m.min:.2f}{unit_str}" if m.min is not None else "-"
                max_str = f"{m.max:.2f}{unit_str}" if m.max is not None else "-"
                std_str = f"{m.std_dev:.2f}{unit_str}" if m.std_dev is not None else "-"

                lines.append(
                    f"{m_name:<40} {m.status:<9} {m.sample_count:<5} {mean_str:<10} {med_str:<10} "
                    f"{p95_str:<10} {min_str:<9} {max_str:<9} {std_str:<8}"
                )
                if m.qualification:
                    lines.append(f"  └─ Qualification: {m.qualification}")
                if m.reason:
                    lines.append(f"  └─ Reason: {m.reason}")
                if m.notes:
                    lines.append(f"  └─ Notes: {m.notes}")

        lines.append("=" * 100)
        return "\n".join(lines)


# =============================================================================
# 2. Helpers: Memory, Query Classifier, and Statistics
# =============================================================================


def get_process_memory_info() -> dict[str, Any]:
    """
    Measures current and peak resident memory for the current running process.

    Returns:
        dict with:
        - current_rss_bytes: Optional[int] (None if platform cannot provide current RSS)
        - peak_rss_bytes: Optional[int] (cumulative high-water mark)
        - is_current_available: bool
        - platform_note: str
    """
    if sys.platform == "win32":
        try:
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t),
                ]

            GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
            GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
                wintypes.DWORD,
            ]
            GetProcessMemoryInfo.restype = wintypes.BOOL

            GetCurrentProcess = ctypes.windll.kernel32.GetCurrentProcess
            GetCurrentProcess.restype = wintypes.HANDLE

            pmc = PROCESS_MEMORY_COUNTERS_EX()
            pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
            if GetProcessMemoryInfo(GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return {
                    "current_rss_bytes": int(pmc.WorkingSetSize),
                    "peak_rss_bytes": int(pmc.PeakWorkingSetSize),
                    "is_current_available": True,
                    "platform_note": "Windows psapi.dll: WorkingSetSize (current) and PeakWorkingSetSize (peak)",
                }
        except Exception as err:
            logger.debug("Windows ctypes memory read failed: %s", err)

    # Linux check via /proc/self/status
    if sys.platform.startswith("linux"):
        try:
            status_path = Path("/proc/self/status")
            if status_path.is_file():
                vm_rss = None
                vm_hwm = None
                for line in status_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        vm_rss = int(parts[1]) * 1024  # kB to bytes
                    elif line.startswith("VmHWM:"):
                        parts = line.split()
                        vm_hwm = int(parts[1]) * 1024
                if vm_rss is not None:
                    return {
                        "current_rss_bytes": vm_rss,
                        "peak_rss_bytes": vm_hwm if vm_hwm is not None else vm_rss,
                        "is_current_available": True,
                        "platform_note": "Linux /proc/self/status: VmRSS and VmHWM",
                    }
        except Exception as err:
            logger.debug("Linux /proc memory read failed: %s", err)

    # POSIX fallback using getrusage
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        # On macOS ru_maxrss is bytes; on Linux/BSD it is kilobytes
        peak_bytes = (
            usage.ru_maxrss if sys.platform == "darwin" else int(usage.ru_maxrss * 1024)
        )
        return {
            "current_rss_bytes": None,
            "peak_rss_bytes": peak_bytes,
            "is_current_available": False,
            "platform_note": "POSIX getrusage: cumulative ru_maxrss (peak only; current RSS unavailable)",
        }
    except Exception:
        pass

    return {
        "current_rss_bytes": None,
        "peak_rss_bytes": None,
        "is_current_available": False,
        "platform_note": "Memory measurement unavailable on this platform",
    }


def _validate_outer_sql_statement(tokens: list[tuple[str, str]]) -> str:
    """
    Validates that the outer statement following CTE definitions (or at top level)
    is a complete, balanced, and supported DML/DQL statement or compound query.

    Returns:
        "SQL_STATEMENT" if valid and supported.
        "OTHER" if malformed, unmatched, empty, or unsupported.
    """
    # Strip any trailing semicolons from the outer expression
    while tokens and tokens[-1][0] == "SEMI":
        tokens.pop()

    if not tokens:
        return "OTHER"

    # 1. Validate parenthetical balance across the outer expression
    depth = 0
    for tok_type, _ in tokens:
        if tok_type == "LPAREN":
            depth += 1
        elif tok_type == "RPAREN":
            depth -= 1
            if depth < 0:
                return "OTHER"  # Premature closing parenthesis
    if depth != 0:
        return "OTHER"  # Missing closing parenthesis

    # 2. Check for empty parenthesized expressions anywhere in the statement: () or ( ; )
    for i in range(len(tokens) - 1):
        if tokens[i][0] == "LPAREN":
            k = i + 1
            while k < len(tokens) and tokens[k][0] == "SEMI":
                k += 1
            if k < len(tokens) and tokens[k][0] == "RPAREN":
                return "OTHER"

    # 3. Split top-level compound queries at depth == 0
    # Compound keywords: UNION, INTERSECT, EXCEPT (optionally followed by ALL or DISTINCT)
    branches: list[list[tuple[str, str]]] = []
    current_branch: list[tuple[str, str]] = []
    idx = 0
    n = len(tokens)
    depth = 0

    while idx < n:
        tok_type, tok_val = tokens[idx]
        if tok_type == "LPAREN":
            depth += 1
            current_branch.append((tok_type, tok_val))
            idx += 1
        elif tok_type == "RPAREN":
            depth -= 1
            current_branch.append((tok_type, tok_val))
            idx += 1
        elif (
            depth == 0
            and tok_type == "WORD"
            and tok_val.upper() in {"UNION", "INTERSECT", "EXCEPT"}
        ):
            # Top-level compound operator
            if not current_branch:
                return "OTHER"  # Leading compound operator without branch
            branches.append(current_branch)
            current_branch = []
            idx += 1
            # Optional ALL or DISTINCT
            if (
                idx < n
                and tokens[idx][0] == "WORD"
                and tokens[idx][1].upper() in {"ALL", "DISTINCT"}
            ):
                idx += 1
        else:
            current_branch.append((tok_type, tok_val))
            idx += 1

    if not current_branch:
        return "OTHER"  # Trailing compound operator without branch
    branches.append(current_branch)

    # 4. Validate every compound branch
    for branch in branches:
        # Strip trailing semicolons inside branch
        while branch and branch[-1][0] == "SEMI":
            branch.pop()

        # Strip enclosing outer parentheses: ((SELECT 1)) -> SELECT 1
        while (
            len(branch) >= 2 and branch[0][0] == "LPAREN" and branch[-1][0] == "RPAREN"
        ):
            # Verify that branch[0] matches branch[-1] and not an earlier closing paren
            d = 0
            all_enclosed = True
            for k in range(len(branch) - 1):
                if branch[k][0] == "LPAREN":
                    d += 1
                elif branch[k][0] == "RPAREN":
                    d -= 1
                if d == 0:
                    all_enclosed = False
                    break
            if all_enclosed:
                branch = branch[1:-1]
                # Strip trailing semicolons that might have been inside the parens
                while branch and branch[-1][0] == "SEMI":
                    branch.pop()
            else:
                break

        if not branch:
            return "OTHER"  # Empty parenthesized expression like ()

        # Must have at least 2 tokens (e.g. "SELECT 1" or "DELETE FROM ..."),
        # a single keyword like (SELECT) or (DELETE) is incomplete
        if len(branch) < 2:
            return "OTHER"

        if branch[0][0] != "WORD":
            return "OTHER"

        branch_verb = branch[0][1].rstrip(";,()").upper()
        if branch_verb not in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
            return "OTHER"

    return "SQL_STATEMENT"


def classify_database_query(raw_sql: str) -> str:
    """
    Classifies a raw SQL query string into:
    - 'SQL_STATEMENT' (DML/DQL: SELECT, INSERT, UPDATE, DELETE, or CTE resolving to DML/DQL)
    - 'TRANSACTION_BOUNDARY' (BEGIN, COMMIT, ROLLBACK, SAVEPOINT, RELEASE)
    - 'EMPTY' (whitespace or comment only)
    - 'OTHER' (unsupported or ambiguous statement)

    Leading whitespace and leading single/multi-line comments are safely stripped.
    String literals, quoted identifiers, and nested CTE bodies are preserved and
    not mistaken for the outer operative statement.
    """
    if not raw_sql or not raw_sql.strip():
        return "EMPTY"

    i = 0
    n = len(raw_sql)
    tokens: list[tuple[str, str]] = []

    while i < n:
        c = raw_sql[i]
        if c.isspace():
            i += 1
            continue

        # Single-line comment: -- ...
        if c == "-" and i + 1 < n and raw_sql[i + 1] == "-":
            newline = raw_sql.find("\n", i + 2)
            i = n if newline == -1 else newline + 1
            continue

        # Multi-line comment: /* ... */
        if c == "/" and i + 1 < n and raw_sql[i + 1] == "*":
            close_pos = raw_sql.find("*/", i + 2)
            if close_pos == -1:
                return "OTHER"  # Unclosed comment is ambiguous
            i = close_pos + 2
            continue

        # Single-quoted string literal: '...'
        if c == "'":
            start = i
            i += 1
            while i < n:
                if raw_sql[i] == "'":
                    if i + 1 < n and raw_sql[i + 1] == "'":
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    i += 1
            else:
                return "OTHER"  # Unclosed string literal
            tokens.append(("STRING", raw_sql[start:i]))
            continue

        # Quoted identifier: "..." or `...`
        if c in ('"', "`"):
            q = c
            start = i
            i += 1
            while i < n:
                if raw_sql[i] == q:
                    if i + 1 < n and raw_sql[i + 1] == q:
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    i += 1
            else:
                return "OTHER"  # Unclosed quoted identifier
            tokens.append(("QUOTED_ID", raw_sql[start:i]))
            continue

        # Parentheses
        if c == "(":
            tokens.append(("LPAREN", "("))
            i += 1
            continue
        if c == ")":
            tokens.append(("RPAREN", ")"))
            i += 1
            continue
        if c == ",":
            tokens.append(("COMMA", ","))
            i += 1
            continue
        if c == ";":
            tokens.append(("SEMI", ";"))
            i += 1
            continue

        # Standard word / identifier / operator
        start = i
        while (
            i < n
            and not raw_sql[i].isspace()
            and raw_sql[i] not in ("(", ")", ",", ";", '"', "`", "'")
            and raw_sql[i : i + 2] not in ("--", "/*")
        ):
            i += 1
        tokens.append(("WORD", raw_sql[start:i]))

    if not tokens:
        return "EMPTY"

    first_type, first_val = tokens[0]

    # Handle top-level parenthesized queries: (SELECT 1) or (SELECT 1) UNION (SELECT 2)
    if first_type == "LPAREN":
        return _validate_outer_sql_statement(list(tokens))

    if first_type != "WORD":
        return "OTHER"

    first_verb = first_val.rstrip(";,()").upper()

    # 1. Transaction boundaries
    if first_verb in {"BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE"}:
        return "TRANSACTION_BOUNDARY"

    # 2. Standard DML / DQL statements
    if first_verb in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
        return _validate_outer_sql_statement(list(tokens))

    # 3. CTE queries starting with WITH
    if first_verb == "WITH":
        idx = 1
        # Optional RECURSIVE
        if (
            idx < len(tokens)
            and tokens[idx][0] == "WORD"
            and tokens[idx][1].upper() == "RECURSIVE"
        ):
            idx += 1

        # Conservatively parse one or more CTE definitions:
        # <cte_name> [ (cols) ] AS [ [NOT] MATERIALIZED ] ( body )
        while idx < len(tokens):
            # CTE name (WORD or QUOTED_ID)
            if tokens[idx][0] not in ("WORD", "QUOTED_ID"):
                return "OTHER"
            idx += 1

            # Optional column list in parentheses: (col1, col2)
            if idx < len(tokens) and tokens[idx][0] == "LPAREN":
                col_start = idx
                depth = 1
                idx += 1
                col_tokens = 0
                while idx < len(tokens) and depth > 0:
                    if tokens[idx][0] == "LPAREN":
                        depth += 1
                    elif tokens[idx][0] == "RPAREN":
                        depth -= 1
                    else:
                        col_tokens += 1
                    idx += 1
                if depth != 0 or col_tokens == 0:
                    return "OTHER"

                # Check for empty parenthesized expressions inside the column list
                for c_i in range(col_start, idx - 1):
                    if tokens[c_i][0] == "LPAREN":
                        c_k = c_i + 1
                        while c_k < idx and tokens[c_k][0] == "SEMI":
                            c_k += 1
                        if c_k < idx and tokens[c_k][0] == "RPAREN":
                            return "OTHER"

            # Must have AS keyword
            if (
                idx >= len(tokens)
                or tokens[idx][0] != "WORD"
                or tokens[idx][1].upper() != "AS"
            ):
                return "OTHER"
            idx += 1

            # Optional NOT MATERIALIZED or MATERIALIZED
            if (
                idx < len(tokens)
                and tokens[idx][0] == "WORD"
                and tokens[idx][1].upper() == "NOT"
            ):
                idx += 1
                if (
                    idx < len(tokens)
                    and tokens[idx][0] == "WORD"
                    and tokens[idx][1].upper() == "MATERIALIZED"
                ):
                    idx += 1
                else:
                    return "OTHER"
            elif (
                idx < len(tokens)
                and tokens[idx][0] == "WORD"
                and tokens[idx][1].upper() == "MATERIALIZED"
            ):
                idx += 1

            # Must have parenthesized CTE body ( ... )
            if idx >= len(tokens) or tokens[idx][0] != "LPAREN":
                return "OTHER"

            body_start = idx
            depth = 1
            idx += 1
            body_tokens = 0
            while idx < len(tokens) and depth > 0:
                if tokens[idx][0] == "LPAREN":
                    depth += 1
                elif tokens[idx][0] == "RPAREN":
                    depth -= 1
                else:
                    body_tokens += 1
                idx += 1
            if depth != 0 or body_tokens == 0:
                return "OTHER"

            # Check for empty parenthesized expressions inside the CTE body
            for b_i in range(body_start, idx - 1):
                if tokens[b_i][0] == "LPAREN":
                    b_k = b_i + 1
                    while b_k < idx and tokens[b_k][0] == "SEMI":
                        b_k += 1
                    if b_k < idx and tokens[b_k][0] == "RPAREN":
                        return "OTHER"

            # Check if there is another comma-separated CTE definition
            if idx < len(tokens) and tokens[idx][0] == "COMMA":
                idx += 1
                continue
            else:
                break

        # After all CTE definitions, validate outer statement
        if idx >= len(tokens):
            return "OTHER"

        return _validate_outer_sql_statement(list(tokens[idx:]))

    return "OTHER"


def calculate_distribution_stats(
    samples: list[float],
) -> dict[str, Optional[float | int | str]]:
    """
    Calculates descriptive sample distribution metrics:
    - Arithmetic Mean
    - Median (P50)
    - 95th Percentile (Continuous linear interpolation matching standard numpy percentile)
    - Sample Standard Deviation (with Bessel's correction N - 1)
    - Minimum & Maximum

    Handles empty, single-sample, and non-finite samples with appropriate qualification.
    """
    # Filter non-finite values
    valid_samples = [
        float(x) for x in samples if isinstance(x, (int, float)) and math.isfinite(x)
    ]
    n = len(valid_samples)

    if n == 0:
        return {
            "sample_count": 0,
            "mean": None,
            "median": None,
            "p95": None,
            "min": None,
            "max": None,
            "std_dev": None,
            "qualification": "No samples collected",
        }

    valid_samples.sort()

    if n == 1:
        val = valid_samples[0]
        return {
            "sample_count": 1,
            "mean": val,
            "median": val,
            "p95": None,
            "min": val,
            "max": val,
            "std_dev": None,
            "qualification": "Statistically Insufficient (N=1); distribution metrics unavailable",
        }

    mean_val = sum(valid_samples) / n

    # Median
    if n % 2 == 1:
        median_val = valid_samples[(n - 1) // 2]
    else:
        median_val = (valid_samples[n // 2 - 1] + valid_samples[n // 2]) / 2.0

    # P95 using continuous linear interpolation: index = 0.95 * (n - 1)
    q = 0.95 * (n - 1)
    idx = int(math.floor(q))
    frac = q - idx
    if idx + 1 < n:
        p95_val = valid_samples[idx] + frac * (
            valid_samples[idx + 1] - valid_samples[idx]
        )
    else:
        p95_val = valid_samples[-1]

    # Sample standard deviation with Bessel's correction (N - 1)
    variance = sum((x - mean_val) ** 2 for x in valid_samples) / (n - 1)
    std_dev_val = math.sqrt(variance)

    # Qualification note based on sample size
    if n < 30:
        qualification_note = f"Exploratory estimate; sample size (N={n}) is statistically limited (prefer N >= 30)"
    else:
        qualification_note = f"Descriptive distribution estimate (N={n})"

    return {
        "sample_count": n,
        "mean": mean_val,
        "median": median_val,
        "p95": p95_val,
        "min": valid_samples[0],
        "max": valid_samples[-1],
        "std_dev": std_dev_val,
        "qualification": qualification_note,
    }


# =============================================================================
# 3. Category Runners
# =============================================================================


def run_model_load_benchmark(
    iterations: int = 5,
) -> dict[str, BenchmarkMetricResult]:
    """
    Category 1: Model Loading Time.
    Executes isolated subprocesses to measure:
    - First Process Model Load (OS cache state unknown)
    - Subsequent Fresh-Process Loads (OS cache may be warm)
    - First Forward Pass After Load (PyTorch thread pool initialization + tensor allocation)
    """
    results: dict[str, BenchmarkMetricResult] = {}
    python_exe = sys.executable
    backend_dir = str(Path(__file__).resolve().parent.parent)

    # Code to run inside isolated child process
    subprocess_script = f"""
import os, sys, time, json, tempfile, shutil
sys.path.insert(0, r"{backend_dir}")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
import django
django.setup()

from analysis.model_loader.loader import ModelLoader, resolve_artifact_path, ModelLoadingError
from analysis.inference.deberta import DebertaModelAdapter

temp_staging = tempfile.mkdtemp(prefix='bench_tok_stage_')
try:
    path = resolve_artifact_path()
    t0 = time.perf_counter()
    loader = ModelLoader(artifact_path=path, staging_base_dir=temp_staging)
    loader.get_model_and_tokenizer()
    t1 = time.perf_counter()
    load_time_ms = (t1 - t0) * 1000.0

    adapter = DebertaModelAdapter(loader=loader)
    t2 = time.perf_counter()
    adapter.predict("Clinical trial evaluation indicates high safety margin for newly formulated vaccine.")
    t3 = time.perf_counter()
    first_inf_ms = (t3 - t2) * 1000.0

    print(json.dumps({{"status": "SUCCESS", "load_time_ms": load_time_ms, "first_inf_ms": first_inf_ms}}))
except Exception as e:
    print(json.dumps({{"status": "FAILED", "error": f"{{type(e).__name__}}: {{str(e)}}"}}))
finally:
    shutil.rmtree(temp_staging, ignore_errors=True)
"""

    first_load_samples: list[float] = []
    subsequent_load_samples: list[float] = []
    first_inf_samples: list[float] = []

    total_runs = max(iterations, 2)
    for run_idx in range(total_runs):
        try:
            proc = subprocess.run(
                [python_exe, "-c", subprocess_script],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=backend_dir,
            )
            if proc.returncode != 0:
                logger.warning(
                    "Subprocess model load run %d failed: %s",
                    run_idx,
                    proc.stderr.strip(),
                )
                continue

            stdout_lines = [
                line.strip() for line in proc.stdout.splitlines() if line.strip()
            ]
            if not stdout_lines:
                continue

            data = json.loads(stdout_lines[-1])
            if data.get("status") == "SUCCESS":
                load_ms = data["load_time_ms"]
                inf_ms = data["first_inf_ms"]
                first_inf_samples.append(inf_ms)
                if run_idx == 0:
                    first_load_samples.append(load_ms)
                else:
                    subsequent_load_samples.append(load_ms)
            else:
                logger.warning(
                    "Subprocess run %d reported error: %s",
                    run_idx,
                    data.get("error"),
                )
        except Exception as exc:
            logger.warning("Subprocess run %d encountered exception: %s", run_idx, exc)

    # 1. First Process Load
    if first_load_samples:
        stats = calculate_distribution_stats(first_load_samples)
        results["First Process Model Load - OS Cache State Unknown"] = (
            BenchmarkMetricResult(
                status="SUCCESS",
                sample_count=stats["sample_count"],
                unit="ms",
                mean=stats["mean"],
                median=stats["median"],
                p95=stats["p95"],
                min=stats["min"],
                max=stats["max"],
                std_dev=stats["std_dev"],
                qualification=stats["qualification"],
                notes="Single subprocess observation. Windows OS file cache state is unknown.",
            )
        )
    else:
        results["First Process Model Load - OS Cache State Unknown"] = (
            BenchmarkMetricResult(
                status="FAILED",
                sample_count=0,
                unit="ms",
                reason="Subprocess failed to load model artifact",
            )
        )

    # 2. Subsequent Process Loads
    if subsequent_load_samples:
        stats = calculate_distribution_stats(subsequent_load_samples)
        results["Subsequent Fresh-Process Loads - OS Cache May Be Warm"] = (
            BenchmarkMetricResult(
                status="SUCCESS",
                sample_count=stats["sample_count"],
                unit="ms",
                mean=stats["mean"],
                median=stats["median"],
                p95=stats["p95"],
                min=stats["min"],
                max=stats["max"],
                std_dev=stats["std_dev"],
                qualification=stats["qualification"],
                notes="Subsequent fresh Python processes. Weights may be cached in Windows standby list.",
            )
        )
    else:
        results["Subsequent Fresh-Process Loads - OS Cache May Be Warm"] = (
            BenchmarkMetricResult(
                status="FAILED",
                sample_count=0,
                unit="ms",
                reason="Subsequent subprocesses failed to complete",
            )
        )

    # 3. First Forward Pass After Load
    if first_inf_samples:
        stats = calculate_distribution_stats(first_inf_samples)
        results["First Forward Pass After Load"] = BenchmarkMetricResult(
            status="SUCCESS",
            sample_count=stats["sample_count"],
            unit="ms",
            mean=stats["mean"],
            median=stats["median"],
            p95=stats["p95"],
            min=stats["min"],
            max=stats["max"],
            std_dev=stats["std_dev"],
            qualification=stats["qualification"],
            notes="Initial tokenization and forward pass immediately following model load.",
        )
    else:
        results["First Forward Pass After Load"] = BenchmarkMetricResult(
            status="FAILED",
            sample_count=0,
            unit="ms",
            reason="Inference failed in subprocess",
        )

    return results


def run_inference_benchmark(
    iterations: int = 100,
) -> dict[str, BenchmarkMetricResult]:
    """
    Category 2: DeBERTa Inference Latency.
    Measures warm inference (cache miss across Short, Nominal, Edge claim lengths)
    and in-memory LRU prediction cache hit latency.
    """
    results: dict[str, BenchmarkMetricResult] = {}

    from analysis.inference.deberta import DebertaModelAdapter
    from analysis.model_loader.loader import ModelLoader, resolve_artifact_path
    from analysis.services.inference import (
        InferencePredictionCache,
        ModelInferenceService,
    )

    try:
        artifact_path = resolve_artifact_path()
    except Exception as exc:
        results["Warm Inference - Nominal (Cache Miss)"] = BenchmarkMetricResult(
            status="UNAVAILABLE",
            sample_count=0,
            unit="ms",
            reason=f"Model artifact unavailable: {exc}",
        )
        return results

    # Isolate staging directory
    temp_staging = tempfile.mkdtemp(prefix="bench_inf_stage_")
    try:
        loader = ModelLoader(artifact_path=artifact_path, staging_base_dir=temp_staging)
        adapter = DebertaModelAdapter(loader=loader)
        cache = InferencePredictionCache(max_entries=1024)
        service = ModelInferenceService(adapter=adapter, prediction_cache=cache)

        claims = {
            "Warm Inference - Nominal (Cache Miss)": (
                "Health ministry officials confirmed that widespread clinical trial data demonstrated "
                "significant efficacy for the revised pediatric vaccine formula across multiple independent testing sites."
            ),
            "Warm Inference - Short (Cache Miss)": (
                "Scientists announce discovery of ancient freshwater reservoir beneath polar ice."
            ),
            "Warm Inference - Edge (Cache Miss)": (
                "According to extensive global health surveillance data published by international epidemiological institutes, "
                "the documented rate of seasonal respiratory infections decreased markedly following the introduction of updated "
                "public health guidelines and targeted community protection programs, notwithstanding initial skepticism regarding "
                "the speed and scale of deployment across both densely populated metropolitan areas and isolated rural health networks "
                "throughout the monitored consecutive reporting periods."
            ),
        }

        # Warmup: 3 unmeasured forward passes
        for _ in range(3):
            adapter.predict("Warmup claim text for CPU thread cache readiness.")

        # Measure each length
        for metric_name, text in claims.items():
            run_count = iterations if "Nominal" in metric_name else min(iterations, 30)
            samples: list[float] = []
            for i in range(run_count):
                # Vary slightly to prevent any hidden adapter cache
                query_text = f"{text} (run {i})"
                t0 = time.perf_counter()
                adapter.predict(query_text)
                t1 = time.perf_counter()
                samples.append((t1 - t0) * 1000.0)

            stats = calculate_distribution_stats(samples)
            results[metric_name] = BenchmarkMetricResult(
                status="SUCCESS",
                sample_count=stats["sample_count"],
                unit="ms",
                mean=stats["mean"],
                median=stats["median"],
                p95=stats["p95"],
                min=stats["min"],
                max=stats["max"],
                std_dev=stats["std_dev"],
                qualification=stats["qualification"],
                notes=f"CPU forward pass without model load overhead ({stats['sample_count']} samples)",
            )

        # Cache Hit Benchmark
        cache_hit_text = "Standard claim text to test in-memory prediction cache hit."
        service.predict(cache_hit_text)  # Prime cache

        # Warmup cache hits
        for _ in range(3):
            service.predict(cache_hit_text)

        hit_samples: list[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            service.predict(cache_hit_text)
            t1 = time.perf_counter()
            hit_samples.append((t1 - t0) * 1000.0)

        hit_stats = calculate_distribution_stats(hit_samples)
        results["Inference Cache Hit"] = BenchmarkMetricResult(
            status="SUCCESS",
            sample_count=hit_stats["sample_count"],
            unit="ms",
            mean=hit_stats["mean"],
            median=hit_stats["median"],
            p95=hit_stats["p95"],
            min=hit_stats["min"],
            max=hit_stats["max"],
            std_dev=hit_stats["std_dev"],
            qualification=hit_stats["qualification"],
            notes="In-memory LRU prediction cache retrieval (<1 ms)",
        )

    finally:
        import shutil

        shutil.rmtree(temp_staging, ignore_errors=True)

    return results


def run_rules_benchmark(
    iterations: int = 100,
) -> dict[str, BenchmarkMetricResult]:
    """Category 3: Rule Engine Evaluation Latency."""
    results: dict[str, BenchmarkMetricResult] = {}
    from analysis.services.rules import RuleEngineService

    service = RuleEngineService()

    nominal_text = "Officials reported that standard procedures were followed."
    flagged_text = (
        "BREAKING: SHOCKING DISCOVERY PROVES EVERYTHING WAS COMPLETELY FAKED!!!! "
        "Scientists verify miraculous cure hidden by government officials."
    )

    # Warmup
    for _ in range(3):
        service.evaluate(nominal_text)
        service.evaluate(flagged_text)

    # Nominal evaluation
    nominal_samples: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        service.evaluate(nominal_text)
        t1 = time.perf_counter()
        nominal_samples.append((t1 - t0) * 1000.0)

    n_stats = calculate_distribution_stats(nominal_samples)
    results["Rule Evaluation - Nominal Clean Text"] = BenchmarkMetricResult(
        status="SUCCESS",
        sample_count=n_stats["sample_count"],
        unit="ms",
        mean=n_stats["mean"],
        median=n_stats["median"],
        p95=n_stats["p95"],
        min=n_stats["min"],
        max=n_stats["max"],
        std_dev=n_stats["std_dev"],
        qualification=n_stats["qualification"],
    )

    # Flagged evaluation
    flagged_samples: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        service.evaluate(flagged_text)
        t1 = time.perf_counter()
        flagged_samples.append((t1 - t0) * 1000.0)

    f_stats = calculate_distribution_stats(flagged_samples)
    results["Rule Evaluation - Flagged Sensational Text"] = BenchmarkMetricResult(
        status="SUCCESS",
        sample_count=f_stats["sample_count"],
        unit="ms",
        mean=f_stats["mean"],
        median=f_stats["median"],
        p95=f_stats["p95"],
        min=f_stats["min"],
        max=f_stats["max"],
        std_dev=f_stats["std_dev"],
        qualification=f_stats["qualification"],
    )

    return results


def run_fact_check_benchmark(
    iterations: int = 100,
    include_live_api: bool = False,
) -> dict[str, BenchmarkMetricResult]:
    """Category 4: Fact-Check Service Latency."""
    results: dict[str, BenchmarkMetricResult] = {}
    from analysis.services.fact_check import (
        FactCheckResponseCache,
        FactCheckService,
    )

    # 1. In-Memory Cache Hit
    cache = FactCheckResponseCache(max_entries=500)

    claim_key = "Test claim for in-memory fact check response caching"
    # Seed cache
    from analysis.services.fact_check import (
        FactCheckEvidenceItem,
        FactCheckResult,
    )

    dummy_result = FactCheckResult(
        matches=1,
        sources=(
            FactCheckEvidenceItem(
                publisher="Test Publisher",
                rating="False",
                url="https://example.com/check",
            ),
        ),
        summary="External fact-check review by Test Publisher reported rating: 'False'.",
        evidence_urls=("https://example.com/check",),
    )
    cache.set(claim_key, dummy_result)

    # Warmup
    for _ in range(3):
        cache.get(claim_key)

    hit_samples: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        _ = cache.get(claim_key)
        t1 = time.perf_counter()
        hit_samples.append((t1 - t0) * 1000.0)

    hit_stats = calculate_distribution_stats(hit_samples)
    results["Fact-Check In-Memory Cache Hit"] = BenchmarkMetricResult(
        status="SUCCESS",
        sample_count=hit_stats["sample_count"],
        unit="ms",
        mean=hit_stats["mean"],
        median=hit_stats["median"],
        p95=hit_stats["p95"],
        min=hit_stats["min"],
        max=hit_stats["max"],
        std_dev=hit_stats["std_dev"],
        qualification=hit_stats["qualification"],
    )

    # 2. Simulated Network Latency
    class MockSimulatedHTTPClient:

        def __init__(self, delay_ms: float = 150.0):
            self.delay_sec = delay_ms / 1000.0

        def __call__(self, request: Any, timeout: float = 5.0) -> Any:
            time.sleep(self.delay_sec)

            class MockResponse:

                def read(self) -> bytes:
                    return b'{"claims": [{"claimReview": [{"publisher": {"name": "Simulated FactCheck"}, "textualRating": "False", "url": "https://simulated.org"}]}]}'

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            return MockResponse()

    sim_client = MockSimulatedHTTPClient(delay_ms=150.0)
    sim_service = FactCheckService(api_key="test_key_simulated", http_client=sim_client)

    sim_samples: list[float] = []
    sim_runs = min(iterations, 30)
    for i in range(sim_runs):
        t0 = time.perf_counter()
        sim_service.query(f"Simulated query {i} to bypass cache")
        t1 = time.perf_counter()
        sim_samples.append((t1 - t0) * 1000.0)

    sim_stats = calculate_distribution_stats(sim_samples)
    results["Fact-Check Simulated Network Latency (150ms Mock)"] = (
        BenchmarkMetricResult(
            status="SUCCESS",
            sample_count=sim_stats["sample_count"],
            unit="ms",
            mean=sim_stats["mean"],
            median=sim_stats["median"],
            p95=sim_stats["p95"],
            min=sim_stats["min"],
            max=sim_stats["max"],
            std_dev=sim_stats["std_dev"],
            qualification=sim_stats["qualification"],
            notes="Controlled 150ms mock delay to measure parsing, serialization, and caching overhead.",
        )
    )

    # 3. Live Google Fact Check API
    if not include_live_api:
        results["Live Google Fact-Check API Latency"] = BenchmarkMetricResult(
            status="SKIPPED",
            sample_count=0,
            unit="ms",
            reason="Guarded against quota exhaustion; pass --include-live-api to execute.",
        )
    else:
        from django.conf import settings

        api_key = getattr(settings, "FACT_CHECK_API_KEY", "")
        if not api_key:
            results["Live Google Fact-Check API Latency"] = BenchmarkMetricResult(
                status="UNAVAILABLE",
                sample_count=0,
                unit="ms",
                reason="FACT_CHECK_API_KEY is not configured.",
            )
        else:
            live_service = FactCheckService()
            live_samples: list[float] = []
            for q_idx in range(3):
                try:
                    t0 = time.perf_counter()
                    live_service.query(f"vaccine safety verification query {q_idx}")
                    t1 = time.perf_counter()
                    live_samples.append((t1 - t0) * 1000.0)
                    time.sleep(1.0)  # Rate pacing
                except Exception as exc:
                    logger.warning("Live API call %d failed: %s", q_idx, exc)

            if live_samples:
                live_stats = calculate_distribution_stats(live_samples)
                results["Live Google Fact-Check API Latency"] = BenchmarkMetricResult(
                    status="SUCCESS",
                    sample_count=live_stats["sample_count"],
                    unit="ms",
                    mean=live_stats["mean"],
                    median=live_stats["median"],
                    p95=live_stats["p95"],
                    min=live_stats["min"],
                    max=live_stats["max"],
                    std_dev=live_stats["std_dev"],
                    qualification=live_stats["qualification"],
                    notes="Guarded live API call (3 requests, 1s interval).",
                )
            else:
                results["Live Google Fact-Check API Latency"] = BenchmarkMetricResult(
                    status="FAILED",
                    sample_count=0,
                    unit="ms",
                    reason="Live API calls failed",
                )

    return results


def run_narrative_benchmark(
    iterations: int = 30,
) -> dict[str, BenchmarkMetricResult]:
    """Category 5: Narrative Activity Engine Benchmarks."""
    results: dict[str, BenchmarkMetricResult] = {}
    from analysis.services.narrative import NarrativeActivityService

    # 1. Real Sentence Transformer Embedding
    results["Real Sentence Transformer Embedding"] = BenchmarkMetricResult(
        status="UNAVAILABLE",
        sample_count=0,
        unit="ms",
        reason="Sentence Transformer artifact 'all-MiniLM-L6-v2' is absent on disk; external download prohibited.",
    )

    # 2. Production Operational Failure Path
    fail_service = NarrativeActivityService()
    fail_samples: list[float] = []
    # Warmup
    for _ in range(3):
        try:
            fail_service.evaluate("Warmup claim text")
        except Exception:
            pass

    for i in range(iterations):
        t0 = time.perf_counter()
        try:
            fail_service.evaluate(f"Missing artifact evaluation claim {i}")
        except Exception:
            pass
        t1 = time.perf_counter()
        fail_samples.append((t1 - t0) * 1000.0)

    f_stats = calculate_distribution_stats(fail_samples)
    results["Production Operational Failure Path"] = BenchmarkMetricResult(
        status="SUCCESS",
        sample_count=f_stats["sample_count"],
        unit="ms",
        mean=f_stats["mean"],
        median=f_stats["median"],
        p95=f_stats["p95"],
        min=f_stats["min"],
        max=f_stats["max"],
        std_dev=f_stats["std_dev"],
        qualification=f_stats["qualification"],
        notes="Measures graceful failure detection when model weights are absent.",
    )

    # 3. Mock-Based Orchestration
    import numpy as np

    class MockEmbeddingGenerator:

        def __init__(self, dimension: int = 384):
            self.dimension = dimension

        def embed(self, text: str) -> np.ndarray:
            vec = np.ones(self.dimension, dtype=np.float32)
            return vec / np.linalg.norm(vec)

        def embed_batch(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
            arr = np.ones((len(texts), self.dimension), dtype=np.float32)
            norm = np.linalg.norm(arr, axis=1, keepdims=True)
            return arr / np.where(norm == 0, 1.0, norm)

    mock_service = NarrativeActivityService(
        embedder=MockEmbeddingGenerator(dimension=384)
    )

    # Warmup
    for _ in range(3):
        mock_service.evaluate("Warmup claim for mock narrative orchestration")

    mock_samples: list[float] = []
    for i in range(iterations):
        t0 = time.perf_counter()
        mock_service.evaluate(
            f"Evaluation claim {i} for candidate search and vector math"
        )
        t1 = time.perf_counter()
        mock_samples.append((t1 - t0) * 1000.0)

    m_stats = calculate_distribution_stats(mock_samples)
    results["Mock-Based Narrative Orchestration"] = BenchmarkMetricResult(
        status="SUCCESS",
        sample_count=m_stats["sample_count"],
        unit="ms",
        mean=m_stats["mean"],
        median=m_stats["median"],
        p95=m_stats["p95"],
        min=m_stats["min"],
        max=m_stats["max"],
        std_dev=m_stats["std_dev"],
        qualification=m_stats["qualification"],
        notes="MOCK EMBEDDER ONLY — Measures database query and vector math orchestration, NOT neural embedding inference.",
    )

    return results


def run_database_benchmark(
    iterations: int = 30,
) -> dict[str, BenchmarkMetricResult]:
    """Category 6: Database Persistence & Query Lifecycle."""
    results: dict[str, BenchmarkMetricResult] = {}
    from django.contrib.auth import get_user_model
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from analysis.models import Verdict
    from analysis.services.explainability import ExplainabilityResult
    from analysis.services.hybrid import HybridAnalysisStatus
    from analysis.services.persistence import AnalysisPersistenceService
    from claims.models import Claim, ClaimStatus

    User = get_user_model()
    # Create benchmark user outside measurement
    user, _ = User.objects.get_or_create(
        email="benchmark_db_user@example.com",
        defaults={"role": "user", "is_active": True},
    )

    service = AnalysisPersistenceService()

    # Create dummy explainability result
    dummy_exp = ExplainabilityResult(
        verdict=Verdict.CREDIBLE,
        verdict_label="Likely Credible",
        credibility_score=78.5,
        confidence_level="HIGH",
        overall_status=HybridAnalysisStatus.COMPLETED,
        is_definitive=True,
        verdict_reason="Credibility score 78.5 meets or exceeds threshold.",
        reasoning=("Reasoning item 1",),
        score_breakdown={
            "model": {
                "component_score": 0.80,
                "effective_weight": 0.40,
                "weighted_contribution": 32.0,
                "status": "AVAILABLE",
            }
        },
        effective_weights={"model": 0.40},
        coverage_ratio=0.85,
        model_explanation={"detail_status": "FULL", "summary": "Model output full"},
        fact_check_explanation={
            "detail_status": "FULL",
            "summary": "Fact check full",
            "has_conflict": False,
        },
        narrative_explanation={
            "detail_status": "SUMMARY_ONLY",
            "summary": "Narrative summary",
        },
        rule_explanation={"detail_status": "FULL", "summary": "Rules clean"},
        similarity_explanation={
            "detail_status": "FULL",
            "summary": "Similarity summary",
        },
        diagnostics={"failed_components": ()},
    )

    durations: list[float] = []
    sql_counts: list[float] = []
    boundary_counts: list[float] = []
    total_ops: list[float] = []

    for i in range(iterations):
        # 1. Setup outside measurement boundary
        claim = Claim.objects.create(
            user=user,
            text=f"Benchmark persistence test claim {uuid.uuid4()}",
            status=ClaimStatus.PROCESSING,
        )

        try:
            # 2. Measurement inside CaptureQueriesContext
            with CaptureQueriesContext(connection) as ctx:
                t0 = time.perf_counter()
                service.persist_analysis(claim=claim, explainability_result=dummy_exp)
                t1 = time.perf_counter()

            durations.append((t1 - t0) * 1000.0)

            # Classify captured queries
            sql_cnt = 0
            bnd_cnt = 0
            for q in ctx.captured_queries:
                cls = classify_database_query(q["sql"])
                if cls == "SQL_STATEMENT":
                    sql_cnt += 1
                elif cls == "TRANSACTION_BOUNDARY":
                    bnd_cnt += 1

            sql_counts.append(float(sql_cnt))
            boundary_counts.append(float(bnd_cnt))
            total_ops.append(float(len(ctx.captured_queries)))

        finally:
            # 3. Teardown outside measurement boundary
            from analysis.models import Analysis

            Analysis.objects.filter(claim_id=claim.id).delete()
            claim.delete()

    # Record metrics
    d_stats = calculate_distribution_stats(durations)
    results["Persistence Execution Time"] = BenchmarkMetricResult(
        status="SUCCESS",
        sample_count=d_stats["sample_count"],
        unit="ms",
        mean=d_stats["mean"],
        median=d_stats["median"],
        p95=d_stats["p95"],
        min=d_stats["min"],
        max=d_stats["max"],
        std_dev=d_stats["std_dev"],
        qualification=d_stats["qualification"],
        notes="Row lock (select_for_update), duplicate check, and Analysis insert.",
    )

    s_stats = calculate_distribution_stats(sql_counts)
    results["Persistence SQL Statements"] = BenchmarkMetricResult(
        status="SUCCESS",
        sample_count=s_stats["sample_count"],
        unit="count",
        mean=s_stats["mean"],
        median=s_stats["median"],
        p95=s_stats["p95"],
        min=s_stats["min"],
        max=s_stats["max"],
        std_dev=s_stats["std_dev"],
        qualification=s_stats["qualification"],
        notes="DML/DQL statements executed during persist_analysis.",
    )

    b_stats = calculate_distribution_stats(boundary_counts)
    results["Persistence Transaction Boundaries"] = BenchmarkMetricResult(
        status="SUCCESS",
        sample_count=b_stats["sample_count"],
        unit="count",
        mean=b_stats["mean"],
        median=b_stats["median"],
        p95=b_stats["p95"],
        min=b_stats["min"],
        max=b_stats["max"],
        std_dev=b_stats["std_dev"],
        qualification=b_stats["qualification"],
        notes="BEGIN, COMMIT, ROLLBACK statements.",
    )

    o_stats = calculate_distribution_stats(total_ops)
    results["Persistence Total Database Operations"] = BenchmarkMetricResult(
        status="SUCCESS",
        sample_count=o_stats["sample_count"],
        unit="count",
        mean=o_stats["mean"],
        median=o_stats["median"],
        p95=o_stats["p95"],
        min=o_stats["min"],
        max=o_stats["max"],
        std_dev=o_stats["std_dev"],
        qualification=o_stats["qualification"],
        notes="Sum of SQL statements and transaction boundary statements.",
    )

    return results


def run_pipeline_benchmark(
    iterations: int = 30,
) -> dict[str, BenchmarkMetricResult]:
    """
    Category 7: Overall Synchronous Pipeline Execution Time.
    Executes AnalysisPipelineService.run_pipeline() end-to-end on fresh, isolated claims.
    """
    results: dict[str, BenchmarkMetricResult] = {}
    from unittest.mock import MagicMock

    from django.contrib.auth import get_user_model
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from analysis.inference.adapter import ModelOutput
    from analysis.models import Analysis, ModelPrediction
    from analysis.services.fact_check import FactCheckResult
    from analysis.services.pipeline import AnalysisPipelineService
    from claims.models import Claim, ClaimStatus

    User = get_user_model()
    user, _ = User.objects.get_or_create(
        email="benchmark_pipeline_user@example.com",
        defaults={"role": "user", "is_active": True},
    )

    pipeline_service = AnalysisPipelineService()

    # Use simulated network for fact-check to decouple external public network jitter
    def simulated_fact_check(query_text: str) -> FactCheckResult:
        time.sleep(0.05)  # 50ms simulated network
        return FactCheckResult(
            matches=0,
            sources=(),
            summary="No external fact-check reviews found for this claim.",
            evidence_urls=(),
        )

    pipeline_service.fact_check_service.query = MagicMock(
        side_effect=simulated_fact_check
    )

    # Fast mock model output to isolate pipeline orchestration overhead
    pipeline_service.model_service.predict = MagicMock(
        return_value=ModelOutput(prediction=ModelPrediction.CREDIBLE, confidence=0.88)
    )

    # Warmup
    warmup_claim = Claim.objects.create(
        user=user,
        text="Warmup claim for pipeline orchestration benchmark",
        status=ClaimStatus.PENDING,
    )
    pipeline_service.run_pipeline(warmup_claim.id)
    Analysis.objects.filter(claim_id=warmup_claim.id).delete()
    warmup_claim.delete()

    durations: list[float] = []
    sql_counts: list[float] = []
    boundary_counts: list[float] = []

    for i in range(iterations):
        # 1. Fresh claim setup outside measurement boundary
        claim = Claim.objects.create(
            user=user,
            text=f"Benchmark synchronous pipeline claim {i}: Public health authorities released updated epidemiological figures.",
            status=ClaimStatus.PENDING,
        )

        try:
            # 2. Timing boundary around synchronous pipeline execution
            with CaptureQueriesContext(connection) as ctx:
                t0 = time.perf_counter()
                pipeline_service.run_pipeline(claim.id)
                t1 = time.perf_counter()

            durations.append((t1 - t0) * 1000.0)

            sql_cnt = 0
            bnd_cnt = 0
            for q in ctx.captured_queries:
                cls = classify_database_query(q["sql"])
                if cls == "SQL_STATEMENT":
                    sql_cnt += 1
                elif cls == "TRANSACTION_BOUNDARY":
                    bnd_cnt += 1

            sql_counts.append(float(sql_cnt))
            boundary_counts.append(float(bnd_cnt))

        finally:
            # 3. Teardown outside measurement boundary
            Analysis.objects.filter(claim_id=claim.id).delete()
            claim.delete()

    d_stats = calculate_distribution_stats(durations)
    results["Synchronous Pipeline Execution Time"] = BenchmarkMetricResult(
        status="SUCCESS",
        sample_count=d_stats["sample_count"],
        unit="ms",
        mean=d_stats["mean"],
        median=d_stats["median"],
        p95=d_stats["p95"],
        min=d_stats["min"],
        max=d_stats["max"],
        std_dev=d_stats["std_dev"],
        qualification=d_stats["qualification"],
        notes="Full synchronous pipeline completion (50ms simulated network + mock model output).",
    )

    s_stats = calculate_distribution_stats(sql_counts)
    results["Pipeline SQL Statements"] = BenchmarkMetricResult(
        status="SUCCESS",
        sample_count=s_stats["sample_count"],
        unit="count",
        mean=s_stats["mean"],
        median=s_stats["median"],
        p95=s_stats["p95"],
        min=s_stats["min"],
        max=s_stats["max"],
        std_dev=s_stats["std_dev"],
        qualification=s_stats["qualification"],
        notes="Dynamically captured SQL statements (DML/DQL) during synchronous pipeline execution.",
    )

    b_stats = calculate_distribution_stats(boundary_counts)
    results["Pipeline Transaction Boundaries"] = BenchmarkMetricResult(
        status="SUCCESS",
        sample_count=b_stats["sample_count"],
        unit="count",
        mean=b_stats["mean"],
        median=b_stats["median"],
        p95=b_stats["p95"],
        min=b_stats["min"],
        max=b_stats["max"],
        std_dev=b_stats["std_dev"],
        qualification=b_stats["qualification"],
        notes="BEGIN, COMMIT, ROLLBACK boundaries.",
    )

    return results


def validate_memory_benchmark_payload(
    data: Any,
    expected_run_target: int,
    require_peak: bool = True,
) -> tuple[bool, Optional[str]]:
    """
    Validates the JSON payload emitted by the memory benchmark child process.

    Enforces:
    1. Payload is a valid dictionary with status == 'SUCCESS'.
    2. 'run_target' is a positive, non-boolean integer matching expected_run_target.
    3. Mandatory current RSS checkpoints ('baseline_bytes', 'post_load_bytes',
       'inf_1_bytes', 'inf_10_bytes', 'inf_n_bytes') are positive, non-boolean,
       finite numeric values (int or float).
    4. 'peak_bytes' is a positive, non-boolean, finite numeric value when require_peak=True
       or when present and not None.

    Returns:
        (True, None) if the payload is valid.
        (False, error_reason) if any requirement is violated.
    """
    if not isinstance(data, dict):
        return False, "Payload is not a valid JSON dictionary"

    status = data.get("status")
    if status != "SUCCESS":
        return False, f"Payload status is '{status}', expected 'SUCCESS'"

    # Validate run_target
    if "run_target" not in data:
        return False, "Missing 'run_target' in payload"

    run_target = data.get("run_target")
    if (
        isinstance(run_target, bool)
        or not isinstance(run_target, int)
        or run_target <= 0
    ):
        return (
            False,
            f"Invalid non-boolean positive integer 'run_target': {run_target!r}",
        )

    if run_target != expected_run_target:
        return (
            False,
            f"Payload run_target ({run_target}) does not match expected run_target ({expected_run_target})",
        )

    # Mandatory current RSS checkpoints
    mandatory_checkpoints = (
        "baseline_bytes",
        "post_load_bytes",
        "inf_1_bytes",
        "inf_10_bytes",
        "inf_n_bytes",
    )
    for cp in mandatory_checkpoints:
        if cp not in data:
            return False, f"Missing required memory checkpoint: '{cp}'"
        val = data[cp]
        if (
            isinstance(val, bool)
            or not isinstance(val, (int, float))
            or not math.isfinite(val)
            or val <= 0
        ):
            return (
                False,
                f"Invalid value for required checkpoint '{cp}': {val!r} (must be a positive finite number)",
            )

    # Peak RSS validation
    if require_peak:
        if "peak_bytes" not in data or data["peak_bytes"] is None:
            return False, "Missing required memory metric: 'peak_bytes'"
        peak_val = data["peak_bytes"]
        if (
            isinstance(peak_val, bool)
            or not isinstance(peak_val, (int, float))
            or not math.isfinite(peak_val)
            or peak_val <= 0
        ):
            return (
                False,
                f"Invalid value for 'peak_bytes': {peak_val!r} (must be a positive finite number)",
            )
    else:
        if "peak_bytes" in data and data["peak_bytes"] is not None:
            peak_val = data["peak_bytes"]
            if (
                isinstance(peak_val, bool)
                or not isinstance(peak_val, (int, float))
                or not math.isfinite(peak_val)
                or peak_val <= 0
            ):
                return (
                    False,
                    f"Invalid value for 'peak_bytes': {peak_val!r} (must be a positive finite number)",
                )

    return True, None


def run_memory_benchmark(
    iterations: int = 100,
) -> dict[str, BenchmarkMetricResult]:
    """
    Category 8: Memory & Working Set Usage.
    Measures current RSS and peak working set within an isolated child process
    to guarantee a clean baseline even when preceded by inference or model loading.
    """
    results: dict[str, BenchmarkMetricResult] = {}
    python_exe = sys.executable
    backend_dir = str(Path(__file__).resolve().parent.parent)

    run_target = max(iterations, 15)

    subprocess_script = f"""
import os, sys, time, json, tempfile, shutil
sys.path.insert(0, r"{backend_dir}")

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
import django
django.setup()

from analysis.benchmark_pipeline import get_process_memory_info
from analysis.inference.deberta import DebertaModelAdapter
from analysis.model_loader.loader import ModelLoader, resolve_artifact_path

# Checkpoint 1: Clean Django Baseline Setup (before model load)
mem_init = get_process_memory_info()
if not mem_init["is_current_available"]:
    print(json.dumps({{
        "status": "UNAVAILABLE",
        "reason": mem_init["platform_note"],
    }}))
    sys.exit(0)

baseline_bytes = mem_init["current_rss_bytes"]

try:
    artifact_path = resolve_artifact_path()
except Exception as exc:
    print(json.dumps({{
        "status": "UNAVAILABLE",
        "reason": f"Model artifact unavailable: {{exc}}",
    }}))
    sys.exit(0)

temp_staging = tempfile.mkdtemp(prefix="bench_mem_stage_")
try:
    loader = ModelLoader(artifact_path=artifact_path, staging_base_dir=temp_staging)
    adapter = DebertaModelAdapter(loader=loader)

    # Checkpoint 2: Post Model Loading
    loader.get_model_and_tokenizer()
    mem_post_load = get_process_memory_info()
    post_load_bytes = mem_post_load["current_rss_bytes"]

    # Checkpoint 3: Post First Inference
    adapter.predict("Claim for first inference working set evaluation.")
    mem_inf_1 = get_process_memory_info()
    inf_1_bytes = mem_inf_1["current_rss_bytes"]

    # Checkpoint 4: Post Inference #10
    for i in range(2, 11):
        adapter.predict(f"Claim for inference run {{i}}")
    mem_inf_10 = get_process_memory_info()
    inf_10_bytes = mem_inf_10["current_rss_bytes"]

    # Checkpoint 5: Post Inference #{run_target}
    for i in range(11, {run_target} + 1):
        adapter.predict(f"Claim for inference run {{i}}")
    mem_inf_n = get_process_memory_info()
    inf_n_bytes = mem_inf_n["current_rss_bytes"]
    peak_bytes = mem_inf_n["peak_rss_bytes"]

    print(json.dumps({{
        "status": "SUCCESS",
        "run_target": {run_target},
        "platform_note": mem_init["platform_note"],
        "baseline_bytes": baseline_bytes,
        "post_load_bytes": post_load_bytes,
        "inf_1_bytes": inf_1_bytes,
        "inf_10_bytes": inf_10_bytes,
        "inf_n_bytes": inf_n_bytes,
        "peak_bytes": peak_bytes,
    }}))
except Exception as e:
    print(json.dumps({{
        "status": "FAILED",
        "error": f"{{type(e).__name__}}: {{str(e)}}",
    }}))
finally:
    shutil.rmtree(temp_staging, ignore_errors=True)
"""

    try:
        proc = subprocess.run(
            [python_exe, "-c", subprocess_script],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=backend_dir,
        )
        if proc.returncode != 0:
            err_msg = (
                proc.stderr.strip() or f"Process exited with code {proc.returncode}"
            )
            logger.warning("Memory benchmark subprocess failed: %s", err_msg)
            results["Django Baseline Setup Current RSS"] = BenchmarkMetricResult(
                status="FAILED",
                sample_count=0,
                unit="MB",
                reason=f"Subprocess failed: {err_msg[:200]}",
            )
            return results

        stdout_lines = [
            line.strip() for line in proc.stdout.splitlines() if line.strip()
        ]
        if not stdout_lines:
            results["Django Baseline Setup Current RSS"] = BenchmarkMetricResult(
                status="FAILED",
                sample_count=0,
                unit="MB",
                reason="Subprocess produced no output",
            )
            return results

        data = json.loads(stdout_lines[-1])
        status = data.get("status")

        if status == "UNAVAILABLE":
            reason = data.get("reason", "Measurement unavailable")
            results["Django Baseline Setup Current RSS"] = BenchmarkMetricResult(
                status="UNAVAILABLE", sample_count=0, unit="MB", reason=reason
            )
            return results

        if status == "FAILED":
            reason = data.get("error", "Memory benchmark failed in child process")
            results["Django Baseline Setup Current RSS"] = BenchmarkMetricResult(
                status="FAILED", sample_count=0, unit="MB", reason=reason
            )
            return results

        if status == "SUCCESS":
            # Validate child JSON payload strictly before constructing any SUCCESS metric
            is_valid, validation_err = validate_memory_benchmark_payload(
                data, expected_run_target=run_target, require_peak=True
            )
            if not is_valid:
                logger.warning(
                    "Memory benchmark payload validation failed: %s", validation_err
                )
                results["Django Baseline Setup Current RSS"] = BenchmarkMetricResult(
                    status="FAILED",
                    sample_count=0,
                    unit="MB",
                    reason=f"Invalid payload from child process: {validation_err}",
                )
                return results

            baseline_mb = data["baseline_bytes"] / (1024 * 1024)
            post_load_mb = data["post_load_bytes"] / (1024 * 1024)
            inf_1_mb = data["inf_1_bytes"] / (1024 * 1024)
            inf_10_mb = data["inf_10_bytes"] / (1024 * 1024)
            inf_n_mb = data["inf_n_bytes"] / (1024 * 1024)
            peak_mb = (
                data["peak_bytes"] / (1024 * 1024)
                if data.get("peak_bytes") is not None
                else None
            )
            actual_run_target = data["run_target"]
            platform_note = data.get("platform_note", "")

            # Checkpoint 1: Clean Django Baseline Setup
            results["Django Baseline Setup Current RSS"] = BenchmarkMetricResult(
                status="SUCCESS",
                sample_count=1,
                unit="MB",
                mean=baseline_mb,
                median=baseline_mb,
                p95=None,
                min=baseline_mb,
                max=baseline_mb,
                std_dev=None,
                qualification="Single-point baseline checkpoint in clean child process",
                notes=f"Measured in isolated child process before model load. {platform_note}",
            )

            # Checkpoint 2: Post Model Loading
            results["Post-Model Loading Current RSS"] = BenchmarkMetricResult(
                status="SUCCESS",
                sample_count=1,
                unit="MB",
                mean=post_load_mb,
                median=post_load_mb,
                p95=None,
                min=post_load_mb,
                max=post_load_mb,
                std_dev=None,
                qualification="Single-point post-load checkpoint in child process",
                notes="Working set after DeBERTa weights and fast tokenizer are placed into process memory.",
            )

            # Checkpoint 3: Post First Inference
            results["Post-Inference Current RSS (Run 1)"] = BenchmarkMetricResult(
                status="SUCCESS",
                sample_count=1,
                unit="MB",
                mean=inf_1_mb,
                median=inf_1_mb,
                p95=None,
                min=inf_1_mb,
                max=inf_1_mb,
                std_dev=None,
                qualification="Single-point post-inference checkpoint in child process",
                notes="Working set after initial PyTorch thread pool initialization and activation buffers.",
            )

            # Checkpoint 4: Post Inference #10
            results["Post-Inference Current RSS (Run 10)"] = BenchmarkMetricResult(
                status="SUCCESS",
                sample_count=1,
                unit="MB",
                mean=inf_10_mb,
                median=inf_10_mb,
                p95=None,
                min=inf_10_mb,
                max=inf_10_mb,
                std_dev=None,
                qualification="Single-point checkpoint after 10 inferences in child process",
                notes="Working set after 10 sequential inference executions.",
            )

            # Checkpoint 5: Post Inference #run_target
            results[f"Post-Inference Current RSS (Run {actual_run_target})"] = (
                BenchmarkMetricResult(
                    status="SUCCESS",
                    sample_count=1,
                    unit="MB",
                    mean=inf_n_mb,
                    median=inf_n_mb,
                    p95=None,
                    min=inf_n_mb,
                    max=inf_n_mb,
                    std_dev=None,
                    qualification=f"Single-point checkpoint after {actual_run_target} inferences in child process",
                    notes=f"Working set after {actual_run_target} sequential inference executions.",
                )
            )

            # Stability Delta (Run run_target - Run 10)
            delta_mb = inf_n_mb - inf_10_mb
            results[f"Memory Stability Delta (Run {actual_run_target} - Run 10)"] = (
                BenchmarkMetricResult(
                    status="SUCCESS",
                    sample_count=1,
                    unit="MB",
                    mean=delta_mb,
                    median=delta_mb,
                    p95=None,
                    min=delta_mb,
                    max=delta_mb,
                    std_dev=None,
                    qualification="Exploratory memory stability evidence (No arbitrary threshold)",
                    notes=(
                        f"Difference between Run {actual_run_target} and Run 10 in isolated process. "
                        "Fluctuations arise naturally from Python, PyTorch, GC, and OS virtual memory paging."
                    ),
                )
            )

            # Cumulative Peak RSS
            if peak_mb is not None:
                results["Peak Process RSS (High-Water Mark)"] = BenchmarkMetricResult(
                    status="SUCCESS",
                    sample_count=1,
                    unit="MB",
                    mean=peak_mb,
                    median=peak_mb,
                    p95=None,
                    min=peak_mb,
                    max=peak_mb,
                    std_dev=None,
                    qualification="Cumulative child process peak working set",
                    notes="Maximum physical memory mapped during child process lifetime.",
                )
            else:
                results["Peak Process RSS (High-Water Mark)"] = BenchmarkMetricResult(
                    status="UNAVAILABLE",
                    sample_count=0,
                    unit="MB",
                    reason="Peak RSS measurement unavailable on platform",
                )

    except Exception as exc:
        logger.exception("Memory benchmark runner failed: %s", exc)
        results["Django Baseline Setup Current RSS"] = BenchmarkMetricResult(
            status="FAILED",
            sample_count=0,
            unit="MB",
            reason=f"{type(exc).__name__}: {str(exc)}",
        )

    return results


# =============================================================================
# 4. CLI Router & Orchestrator
# =============================================================================

CATEGORY_RUNNERS = {
    "model-load": run_model_load_benchmark,
    "inference": run_inference_benchmark,
    "rules": run_rules_benchmark,
    "fact-check": run_fact_check_benchmark,
    "narrative": run_narrative_benchmark,
    "database": run_database_benchmark,
    "pipeline": run_pipeline_benchmark,
    "memory": run_memory_benchmark,
}


def build_environment_metadata() -> dict[str, Any]:
    """Captures runtime hardware and software metadata."""
    import platform

    torch_ver = "Unknown"
    torch_threads = "Unknown"
    cuda_avail = False
    try:
        import torch

        torch_ver = str(torch.__version__)
        torch_threads = torch.get_num_threads()
        cuda_avail = bool(torch.cuda.is_available())
    except Exception:
        pass

    db_engine = "Unknown"
    try:
        from django.conf import settings

        db_engine = str(settings.DATABASES["default"]["ENGINE"])
    except Exception:
        pass

    return {
        "os": platform.platform(),
        "cpu_cores": os.cpu_count(),
        "torch_version": torch_ver,
        "torch_threads": torch_threads,
        "inference_device": "cuda" if cuda_avail else "cpu",
        "python_version": sys.version.split()[0],
        "database_backend": db_engine,
    }


def main():
    parser = argparse.ArgumentParser(
        description="InfoTrust AI-021 Performance Review Benchmark Harness"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all benchmark categories (mutually exclusive with --category)",
    )
    parser.add_argument(
        "-c",
        "--category",
        action="append",
        choices=list(CATEGORY_RUNNERS.keys()),
        help="Specify one or more categories to run (e.g. -c inference -c memory)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Override sample count for configurable warm-path benchmarks",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--include-live-api",
        action="store_true",
        default=False,
        help="Opt-in flag to run guarded live Google Fact Check API calls",
    )

    args = parser.parse_args()

    # Precedence & Mutually Exclusive Handling
    if args.all and args.category:
        parser.error("Cannot specify both --all and --category.")

    categories_to_run: list[str] = []
    if args.category:
        categories_to_run = list(dict.fromkeys(args.category))  # deduplicate
    else:
        # Default is all categories
        categories_to_run = list(CATEGORY_RUNNERS.keys())

    # Initialize Django if not already active
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
    import django

    django.setup()

    metadata = {
        "benchmark_version": "1.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": build_environment_metadata(),
    }

    report_categories: dict[str, dict[str, BenchmarkMetricResult]] = {}

    for cat in categories_to_run:
        runner_fn = CATEGORY_RUNNERS[cat]
        try:
            # Pass category-specific kwargs
            if cat == "fact-check":
                iter_count = args.iterations or 100
                report_categories[cat] = runner_fn(
                    iterations=iter_count,
                    include_live_api=args.include_live_api,
                )
            elif cat in {"inference", "rules"}:
                iter_count = args.iterations or 100
                report_categories[cat] = runner_fn(iterations=iter_count)
            elif cat in {"database", "pipeline", "narrative"}:
                iter_count = args.iterations or 30
                report_categories[cat] = runner_fn(iterations=iter_count)
            elif cat == "model-load":
                iter_count = args.iterations or 5
                report_categories[cat] = runner_fn(iterations=iter_count)
            elif cat == "memory":
                iter_count = args.iterations or 100
                report_categories[cat] = runner_fn(iterations=iter_count)
            else:
                report_categories[cat] = runner_fn()
        except Exception as exc:
            logger.exception("Category '%s' failed unexpectedly: %s", cat, exc)
            report_categories[cat] = {
                f"{cat}_execution": BenchmarkMetricResult(
                    status="FAILED",
                    sample_count=0,
                    unit="ms",
                    reason=f"{type(exc).__name__}: {str(exc)}",
                )
            }

    report = BenchmarkReport(metadata=metadata, categories=report_categories)

    if args.format == "json":
        output_str = json.dumps(report.to_dict(), indent=2)
    else:
        output_str = report.to_text_table()

    if args.output:
        Path(args.output).write_text(output_str, encoding="utf-8")
        print(f"Benchmark report written to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
