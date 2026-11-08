"""
Unit tests for AI-021 performance review instrumentation.

Verifies:
1. time.perf_counter() monotonicity and non-negative finite duration.
2. Database query classification (DML/DQL vs. transaction boundaries).
3. Common Table Expression (CTE), comment-stripping, and quoted-string handling.
4. Database query capture isolation (excluding setup and teardown operations).
5. Cross-platform process memory reading contracts (current vs. peak RSS).
6. Statistical distribution calculation (mean, median, P95 linear interpolation, Bessel's sample std dev).
7. Small sample size qualification, non-finite filtering, and edge cases.
8. Benchmark result contract serialization across SUCCESS, UNAVAILABLE, SKIPPED, and FAILED states.
9. Strict memory benchmark child payload validation contracts.

Strict invariant: Contains zero machine-dependent wall-clock latency assertions.
"""

import json
import math
import time
import uuid

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from analysis.benchmark_pipeline import (
    BenchmarkMetricResult,
    BenchmarkReport,
    calculate_distribution_stats,
    classify_database_query,
    get_process_memory_info,
    validate_memory_benchmark_payload,
)
from claims.models import Claim, ClaimStatus

User = get_user_model()


class PerformanceInstrumentationUnitTests(SimpleTestCase):
    """Deterministic unit tests for performance profiling and calculation logic."""

    def test_perf_counter_measurement_is_finite_and_positive(self):
        """1. Verifies that time.perf_counter() measures strictly positive, finite, monotonic durations without latency thresholds."""
        t0 = time.perf_counter()
        # Perform deterministic, lightweight in-memory work
        accum = 0
        for i in range(1000):
            accum += i
        t1 = time.perf_counter()

        elapsed = t1 - t0
        self.assertIsInstance(elapsed, float)
        self.assertGreater(elapsed, 0.0)
        self.assertTrue(math.isfinite(elapsed))
        self.assertEqual(accum, 499500)
        # Strict Invariant: No upper bound wall-clock threshold assertion

    def test_query_classification_sql_and_boundaries(self):
        """2. Verifies that standard DML/DQL statements and transaction boundaries are accurately separated."""
        sql_samples = [
            "SELECT id, text FROM claims_claim WHERE id = 'xyz'",
            "INSERT INTO analysis_analysis (id, score) VALUES (1, 80.0)",
            "UPDATE claims_claim SET status = 'PROCESSING' WHERE id = 1",
            "DELETE FROM claims_claim WHERE id = 1",
            "  select count(*) from claims_claim",
            "\n\tUPDATE claims_claim SET is_deleted = false",
        ]
        for query in sql_samples:
            self.assertEqual(
                classify_database_query(query),
                "SQL_STATEMENT",
                f"Failed for SQL statement: {query}",
            )

        boundary_samples = [
            "BEGIN",
            "COMMIT",
            "ROLLBACK",
            "SAVEPOINT s1",
            "RELEASE SAVEPOINT s1",
            "  begin;",
            "\n\tcommit",
        ]
        for query in boundary_samples:
            self.assertEqual(
                classify_database_query(query),
                "TRANSACTION_BOUNDARY",
                f"Failed for boundary: {query}",
            )

    def test_query_classification_handles_cte_and_quotes(self):
        """3. Verifies CTE recognition, comment stripping, and preservation of quoted strings."""
        # Common Table Expressions (CTEs) resolving to DML/DQL
        cte_select = (
            "WITH recent_claims AS (SELECT id, text FROM claims_claim LIMIT 10) "
            "SELECT * FROM recent_claims"
        )
        self.assertEqual(classify_database_query(cte_select), "SQL_STATEMENT")

        cte_insert = (
            "WITH new_claim AS (SELECT 'sample' as text) "
            "INSERT INTO claims_claim (text) SELECT text FROM new_claim"
        )
        self.assertEqual(classify_database_query(cte_insert), "SQL_STATEMENT")

        # Additional valid CTE variants (explicit columns, materialized, parenthesized outer)
        self.assertEqual(
            classify_database_query(
                "WITH cte(a, b) AS (SELECT 1, 2) SELECT a, b FROM cte"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS MATERIALIZED (SELECT 1) SELECT * FROM cte"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) (SELECT * FROM cte)"),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) ((SELECT * FROM cte))"),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT 1) (SELECT 1) UNION (SELECT 2)"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT 1) (SELECT 1) UNION ALL (SELECT 2)"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT 1) (SELECT 1) INTERSECT (SELECT 2)"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT 1) (SELECT 1) EXCEPT (SELECT 2)"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query("(SELECT id, text FROM claims_claim)"),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query("(SELECT 1) UNION (SELECT 2)"),
            "SQL_STATEMENT",
        )

        # Missing closing parenthesis in outer statement
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) (SELECT"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) (SELECT * FROM cte"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("(SELECT 1"),
            "OTHER",
        )

        # Empty parentheses in outer statement and nested queries
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) ()"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) (())"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) (   )"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) () UNION (SELECT 1)"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) (SELECT 1) UNION ()"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("()"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("(())"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("(SELECT * FROM t WHERE id IN ())"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("SELECT * FROM t WHERE id IN ()"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("(SELECT * FROM t WHERE id IN (()))"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("SELECT * FROM t WHERE id IN (())"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT 1) (SELECT * FROM cte WHERE id IN ())"
            ),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT 1) SELECT * FROM cte WHERE id IN ()"
            ),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT * FROM t WHERE id IN ()) SELECT * FROM cte"
            ),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte () AS (SELECT 1) SELECT * FROM cte"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte (()) AS (SELECT 1) SELECT * FROM cte"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte (col, ()) AS (SELECT 1) SELECT * FROM cte"
            ),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte (col, (())) AS (SELECT 1) SELECT * FROM cte"
            ),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS () SELECT * FROM cte"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query(
                "(SELECT 1) UNION (SELECT * FROM t WHERE id IN ())"
            ),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query(
                "(SELECT * FROM t WHERE id IN ()) UNION (SELECT 1)"
            ),
            "OTHER",
        )

        # Valid nested subqueries
        self.assertEqual(
            classify_database_query(
                "SELECT * FROM claims_claim WHERE id IN (SELECT claim_id FROM analysis_analysis)"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query(
                "(SELECT * FROM claims_claim WHERE id IN (SELECT claim_id FROM analysis_analysis))"
            ),
            "SQL_STATEMENT",
        )

        # Valid CTE column lists and valid nested expressions in CTE bodies
        self.assertEqual(
            classify_database_query(
                "WITH cte (col1, col2) AS (SELECT 1, 2) SELECT * FROM cte"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT 1, (SELECT 2)) SELECT * FROM cte"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT * FROM claims_claim WHERE id IN (SELECT claim_id FROM analysis_analysis)) SELECT * FROM cte"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT count(*), max(id) FROM claims_claim) SELECT * FROM cte"
            ),
            "SQL_STATEMENT",
        )

        # Valid function calls with arguments
        self.assertEqual(
            classify_database_query("SELECT count(*), max(id) FROM claims_claim"),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query("(SELECT count(id), max(id) FROM claims_claim)"),
            "SQL_STATEMENT",
        )

        # String literals and quoted identifiers containing the characters '()'
        self.assertEqual(
            classify_database_query(
                "SELECT * FROM claims_claim WHERE text = 'Claim with empty parens () in text'"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query(
                "(SELECT * FROM claims_claim WHERE text = 'Claim with empty parens () in text')"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query('SELECT "col()name" FROM claims_claim'),
            "SQL_STATEMENT",
        )

        # Incomplete outer parenthesized expressions (single token)
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) (SELECT)"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) (SELECT;)"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) SELECT"),
            "OTHER",
        )

        # Nested unmatched parentheses in outer statement
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) ((SELECT * FROM cte)"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) (SELECT * FROM cte))"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) (SELECT (1 FROM cte)"),
            "OTHER",
        )

        # Unsupported compound outer statements
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT 1) (SELECT 1) UNION (EXECUTE sp_proc)"
            ),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT 1) (EXECUTE sp_proc) UNION (SELECT 1)"
            ),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT 1) SELECT 1 UNION EXECUTE sp_proc"
            ),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) (SELECT 1) UNION"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) UNION (SELECT 1)"),
            "OTHER",
        )

        # Comment stripping (leading comments should not obstruct keyword identification)
        commented_sql = (
            "-- This is a comment before the query\n" "SELECT id FROM claims_claim"
        )
        self.assertEqual(classify_database_query(commented_sql), "SQL_STATEMENT")

        block_commented_sql = "/* Block comment before query */ UPDATE claims_claim SET status = 'COMPLETED'"
        self.assertEqual(classify_database_query(block_commented_sql), "SQL_STATEMENT")

        # Quoted strings containing comment-like dashes or asterisks must NOT be corrupted
        quoted_sql = (
            "INSERT INTO claims_claim (text) "
            "VALUES ('Claim with -- dashes and /* block comment characters */ in text')"
        )
        self.assertEqual(classify_database_query(quoted_sql), "SQL_STATEMENT")

        # DML/DQL keywords inside multi-word string literals must NOT fool the classifier
        self.assertEqual(
            classify_database_query(
                "INSERT INTO claims_claim (text) VALUES ('Claim with SELECT and DELETE inside text')"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (VALUES ('this string contains SELECT'))\nEXECUTE sp_proc;"
            ),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (SELECT 'INSERT' as action, 'UPDATE' as action2) EXECUTE sp_proc"
            ),
            "OTHER",
        )

        # Quoted identifiers containing DML/DQL keywords
        self.assertEqual(
            classify_database_query(
                'WITH "SELECT" AS (SELECT 1) SELECT * FROM "SELECT"'
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query('WITH "SELECT" AS (SELECT 1) EXECUTE sp_proc;'),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH `DELETE` AS (SELECT 1) DELETE FROM t"),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query("WITH `DELETE` AS (SELECT 1) EXECUTE sp_proc"),
            "OTHER",
        )

        # Nested CTEs
        self.assertEqual(
            classify_database_query(
                "WITH outer_cte AS (WITH inner_cte AS (SELECT 1) SELECT * FROM inner_cte) SELECT * FROM outer_cte"
            ),
            "SQL_STATEMENT",
        )
        self.assertEqual(
            classify_database_query(
                "WITH outer_cte AS (WITH inner_cte AS (SELECT 1) SELECT * FROM inner_cte) EXECUTE sp_proc"
            ),
            "OTHER",
        )

        # SELECT inside a CTE body followed by unsupported EXECUTE
        self.assertEqual(
            classify_database_query("WITH cte AS (SELECT 1) EXECUTE sp_proc;"),
            "OTHER",
        )

        # Empty or comment-only strings
        self.assertEqual(classify_database_query(""), "EMPTY")
        self.assertEqual(classify_database_query("   \n\t   "), "EMPTY")
        self.assertEqual(
            classify_database_query("-- Just a comment without SQL"), "EMPTY"
        )
        self.assertEqual(classify_database_query("/* Block comment only */"), "EMPTY")

        # Unsupported outer statements returning OTHER
        self.assertEqual(
            classify_database_query("WITH cte AS (VALUES (1)) TABLE cte;"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query(
                "WITH cte AS (VALUES (1)) MERGE INTO target USING cte ON (1=1) WHEN MATCHED THEN NOTHING"
            ),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("WITH cte AS (VALUES (1)) VACUUM"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("EXPLAIN SELECT * FROM claims_claim"),
            "OTHER",
        )
        self.assertEqual(
            classify_database_query("PRAGMA table_info(claims_claim)"), "OTHER"
        )
        self.assertEqual(classify_database_query("VACUUM"), "OTHER")

    def test_memory_profiler_reports_valid_rss(self):
        """5. Verifies cross-platform memory profiler contract without hardcoded size limits."""
        mem_info = get_process_memory_info()
        self.assertIsInstance(mem_info, dict)
        self.assertIn("current_rss_bytes", mem_info)
        self.assertIn("peak_rss_bytes", mem_info)
        self.assertIn("is_current_available", mem_info)
        self.assertIn("platform_note", mem_info)

        # Peak RSS must always be a non-negative integer on supported platforms
        peak = mem_info["peak_rss_bytes"]
        if peak is not None:
            self.assertIsInstance(peak, int)
            self.assertGreater(peak, 0)

        # If current RSS is available on this platform, assert valid non-negative integer
        if mem_info["is_current_available"]:
            current = mem_info["current_rss_bytes"]
            self.assertIsInstance(current, int)
            self.assertGreater(current, 0)
            if peak is not None:
                self.assertGreaterEqual(peak, current)

    def test_statistics_aggregator_computes_exact_metrics(self):
        """6. Verifies descriptive statistics: Mean, Median, continuous P95 linear interpolation, and Bessel's sample std dev."""
        # Synthetic dataset with 30 uniform values from 1.0 to 30.0
        samples = [float(i) for i in range(1, 31)]
        stats = calculate_distribution_stats(samples)

        self.assertEqual(stats["sample_count"], 30)
        # Mean of 1..30 is 15.5
        self.assertAlmostEqual(stats["mean"], 15.5)
        # Median of 1..30 is (15.0 + 16.0) / 2 = 15.5
        self.assertAlmostEqual(stats["median"], 15.5)
        self.assertEqual(stats["min"], 1.0)
        self.assertEqual(stats["max"], 30.0)

        # P95 with continuous linear interpolation:
        # q = 0.95 * (30 - 1) = 27.55
        # idx = 27 (value = 28.0), frac = 0.55
        # p95 = 28.0 + 0.55 * (29.0 - 28.0) = 28.55
        self.assertAlmostEqual(stats["p95"], 28.55)

        # Sample standard deviation with Bessel's correction (N - 1 = 29)
        # Population variance of 1..30 is (30^2 - 1) / 12 = 899 / 12 = 74.91666...
        # Sample variance = 74.91666... * (30 / 29) = 77.5
        # Sample std dev = sqrt(77.5) = 8.803408...
        expected_std = math.sqrt(77.5)
        self.assertAlmostEqual(stats["std_dev"], expected_std, places=4)
        self.assertIn("Descriptive distribution estimate", stats["qualification"])

    def test_statistics_aggregator_handles_edge_cases_and_small_n(self):
        """7. Verifies statistics aggregator behavior on empty, single-sample, small sample sizes, and non-finite values."""
        # Empty dataset
        empty_stats = calculate_distribution_stats([])
        self.assertEqual(empty_stats["sample_count"], 0)
        self.assertIsNone(empty_stats["mean"])
        self.assertIsNone(empty_stats["median"])
        self.assertIsNone(empty_stats["p95"])
        self.assertIsNone(empty_stats["std_dev"])
        self.assertEqual(empty_stats["qualification"], "No samples collected")

        # Single observation (N=1)
        single_stats = calculate_distribution_stats([42.5])
        self.assertEqual(single_stats["sample_count"], 1)
        self.assertEqual(single_stats["mean"], 42.5)
        self.assertEqual(single_stats["median"], 42.5)
        self.assertEqual(single_stats["min"], 42.5)
        self.assertEqual(single_stats["max"], 42.5)
        # Single observation cannot have a meaningful P95 or sample standard deviation
        self.assertIsNone(single_stats["p95"])
        self.assertIsNone(single_stats["std_dev"])
        self.assertIn("Statistically Insufficient (N=1)", single_stats["qualification"])

        # Small sample size (N=4, e.g. subsequent subprocess loads)
        small_stats = calculate_distribution_stats([10.0, 20.0, 30.0, 40.0])
        self.assertEqual(small_stats["sample_count"], 4)
        self.assertEqual(small_stats["mean"], 25.0)
        self.assertEqual(small_stats["median"], 25.0)
        self.assertIsNotNone(small_stats["p95"])
        self.assertIsNotNone(small_stats["std_dev"])
        self.assertIn(
            "Exploratory estimate; sample size (N=4) is statistically limited",
            small_stats["qualification"],
        )

        # Non-finite values (NaN, +inf, -inf) must be filtered cleanly
        dirty_samples = [10.0, float("nan"), 20.0, float("inf"), float("-inf"), 30.0]
        cleaned_stats = calculate_distribution_stats(dirty_samples)
        self.assertEqual(cleaned_stats["sample_count"], 3)
        self.assertEqual(cleaned_stats["mean"], 20.0)
        self.assertEqual(cleaned_stats["median"], 20.0)
        self.assertEqual(cleaned_stats["min"], 10.0)
        self.assertEqual(cleaned_stats["max"], 30.0)

    def test_benchmark_result_serialization_contract(self):
        """8. Verifies JSON serialization contract across SUCCESS, UNAVAILABLE, SKIPPED, and FAILED states."""
        # SUCCESS metric
        success_m = BenchmarkMetricResult(
            status="SUCCESS",
            sample_count=100,
            unit="ms",
            mean=167.5,
            median=166.0,
            p95=175.0,
            min=160.0,
            max=185.0,
            std_dev=4.2,
            qualification="Descriptive distribution estimate (N=100)",
            notes="Nominal claim cache miss",
        )
        d_success = success_m.to_dict()
        self.assertEqual(d_success["status"], "SUCCESS")
        self.assertEqual(d_success["sample_count"], 100)
        self.assertEqual(d_success["mean"], 167.5)

        # UNAVAILABLE metric (no fake 0.0 ms values)
        unavail_m = BenchmarkMetricResult(
            status="UNAVAILABLE",
            sample_count=0,
            unit="ms",
            reason="Sentence Transformer weights absent on disk",
        )
        d_unavail = unavail_m.to_dict()
        self.assertEqual(d_unavail["status"], "UNAVAILABLE")
        self.assertEqual(d_unavail["sample_count"], 0)
        self.assertIsNone(d_unavail["mean"])
        self.assertIsNone(d_unavail["p95"])
        self.assertEqual(
            d_unavail["reason"],
            "Sentence Transformer weights absent on disk",
        )

        # SKIPPED metric
        skipped_m = BenchmarkMetricResult(
            status="SKIPPED",
            sample_count=0,
            unit="ms",
            reason="Guarded against quota exhaustion",
        )
        d_skipped = skipped_m.to_dict()
        self.assertEqual(d_skipped["status"], "SKIPPED")
        self.assertIsNone(d_skipped["mean"])

        # FAILED metric
        failed_m = BenchmarkMetricResult(
            status="FAILED",
            sample_count=0,
            unit="ms",
            reason="RuntimeError: Connection timed out",
        )
        d_failed = failed_m.to_dict()
        self.assertEqual(d_failed["status"], "FAILED")
        self.assertIn("RuntimeError", d_failed["reason"])

        # Verify full report serializes cleanly to JSON without NaN/Infinity
        report = BenchmarkReport(
            metadata={"timestamp": "2026-11-07T22:00:00Z"},
            categories={
                "inference": {"warm_miss": success_m},
                "narrative": {"neural": unavail_m},
            },
        )
        json_output = json.dumps(report.to_dict())
        parsed = json.loads(json_output)
        self.assertEqual(
            parsed["categories"]["inference"]["warm_miss"]["status"], "SUCCESS"
        )
        self.assertEqual(
            parsed["categories"]["narrative"]["neural"]["status"],
            "UNAVAILABLE",
        )
        self.assertIsNone(parsed["categories"]["narrative"]["neural"]["mean"])

    def test_memory_benchmark_payload_validation(self):
        """9. Verifies strict memory benchmark child payload validation (types, values, thresholds, missing keys)."""
        valid_payload = {
            "status": "SUCCESS",
            "run_target": 15,
            "baseline_bytes": 67108864,
            "post_load_bytes": 734003200,
            "inf_1_bytes": 754974720,
            "inf_10_bytes": 765460480,
            "inf_n_bytes": 775946240,
            "peak_bytes": 838860800,
            "platform_note": "Windows psapi.dll",
        }

        # 1. Valid payload passes
        is_valid, err = validate_memory_benchmark_payload(
            valid_payload, expected_run_target=15, require_peak=True
        )
        self.assertTrue(is_valid)
        self.assertIsNone(err)

        # 2. Rejects non-dict payload
        is_valid, err = validate_memory_benchmark_payload(
            "not a dict", expected_run_target=15
        )
        self.assertFalse(is_valid)
        self.assertIn("not a valid JSON dictionary", err)

        is_valid, err = validate_memory_benchmark_payload(None, expected_run_target=15)
        self.assertFalse(is_valid)

        # 3. Rejects non-SUCCESS status
        is_valid, err = validate_memory_benchmark_payload(
            {"status": "FAILED"}, expected_run_target=15
        )
        self.assertFalse(is_valid)
        self.assertIn("expected 'SUCCESS'", err)

        # 4. Rejects missing or invalid run_target
        p = dict(valid_payload)
        del p["run_target"]
        is_valid, err = validate_memory_benchmark_payload(p, expected_run_target=15)
        self.assertFalse(is_valid)
        self.assertIn("Missing 'run_target'", err)

        for invalid_target in (True, False, "15", -5, 0, 15.0):
            p = dict(valid_payload, run_target=invalid_target)
            is_valid, err = validate_memory_benchmark_payload(p, expected_run_target=15)
            self.assertFalse(is_valid)

        # Mismatched run_target
        p = dict(valid_payload, run_target=100)
        is_valid, err = validate_memory_benchmark_payload(p, expected_run_target=15)
        self.assertFalse(is_valid)
        self.assertIn("does not match expected run_target", err)

        # 5. Rejects missing required current RSS checkpoints
        checkpoints = (
            "baseline_bytes",
            "post_load_bytes",
            "inf_1_bytes",
            "inf_10_bytes",
            "inf_n_bytes",
        )
        for cp in checkpoints:
            p = dict(valid_payload)
            del p[cp]
            is_valid, err = validate_memory_benchmark_payload(p, expected_run_target=15)
            self.assertFalse(is_valid)
            self.assertIn(f"Missing required memory checkpoint: '{cp}'", err)

        # 6. Rejects null, boolean, string, zero, negative, and non-finite checkpoint values
        for invalid_val in (
            None,
            True,
            False,
            "1048576",
            0,
            -100,
            float("nan"),
            float("inf"),
        ):
            for cp in checkpoints:
                p = dict(valid_payload, **{cp: invalid_val})
                is_valid, err = validate_memory_benchmark_payload(
                    p, expected_run_target=15
                )
                self.assertFalse(is_valid)
                self.assertIn(f"Invalid value for required checkpoint '{cp}'", err)

        # 7. Peak RSS validation
        # Missing peak_bytes when require_peak=True
        p = dict(valid_payload)
        del p["peak_bytes"]
        is_valid, err = validate_memory_benchmark_payload(
            p, expected_run_target=15, require_peak=True
        )
        self.assertFalse(is_valid)
        self.assertIn("Missing required memory metric: 'peak_bytes'", err)

        # Null peak_bytes when require_peak=True
        p = dict(valid_payload, peak_bytes=None)
        is_valid, err = validate_memory_benchmark_payload(
            p, expected_run_target=15, require_peak=True
        )
        self.assertFalse(is_valid)
        self.assertIn("Missing required memory metric: 'peak_bytes'", err)

        for invalid_peak in (True, False, 0, -500, float("nan")):
            p = dict(valid_payload, peak_bytes=invalid_peak)
            is_valid, err = validate_memory_benchmark_payload(
                p, expected_run_target=15, require_peak=True
            )
            self.assertFalse(is_valid)
            self.assertIn("Invalid value for 'peak_bytes'", err)

        # When require_peak=False, missing or None peak_bytes is permitted
        p = dict(valid_payload, peak_bytes=None)
        is_valid, err = validate_memory_benchmark_payload(
            p, expected_run_target=15, require_peak=False
        )
        self.assertTrue(is_valid)
        self.assertIsNone(err)


class PerformanceInstrumentationIntegrationTests(TestCase):
    """Integration test verifying query capture boundary isolation with Django database connection."""

    def test_query_capture_excludes_setup_and_teardown(self):
        """4. Verifies that fixtures created outside CaptureQueriesContext are excluded from captured query counts."""
        # Setup outside measurement boundary
        user = User.objects.create(
            email=f"test_instrumentation_{uuid.uuid4()}@example.com",
            role="user",
        )
        claim = Claim.objects.create(
            user=user,
            text="Initial setup claim to verify query exclusion.",
            status=ClaimStatus.PENDING,
        )

        try:
            # Measurement inside CaptureQueriesContext
            with CaptureQueriesContext(connection) as ctx:
                # Perform exactly one isolated query inside
                found = Claim.objects.filter(id=claim.id).exists()
                self.assertTrue(found)

            # Assert that setup queries (INSERT User, INSERT Claim) were NOT captured inside ctx
            self.assertEqual(len(ctx.captured_queries), 1)
            classified = classify_database_query(ctx.captured_queries[0]["sql"])
            self.assertEqual(classified, "SQL_STATEMENT")

        finally:
            # Teardown outside measurement boundary
            claim.delete()
            user.delete()
