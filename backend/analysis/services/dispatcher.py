"""
Asynchronous pipeline dispatcher for InfoTrust (AI-014).
Provides semaphore-bounded admission control for in-process background worker execution,
leak-proof capacity permit accounting, clean database connection lifecycle handling,
and pluggable synchronous execution for deterministic testing.
"""

import logging
import os
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional

from django.db import close_old_connections

logger = logging.getLogger(__name__)


class AnalysisPipelineDispatcher:
    """
    Manages bounded in-process execution of claim analysis pipelines.
    Enforces a strict upper bound on total outstanding tasks (running + queued)
    using a BoundedSemaphore to prevent CPU and memory exhaustion.
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        max_outstanding_tasks: Optional[int] = None,
        sync_mode: bool = False,
    ) -> None:
        if max_workers is not None:
            self.max_workers = max_workers
        else:
            self.max_workers = int(os.environ.get("ANALYSIS_MAX_WORKERS", "2"))

        if max_outstanding_tasks is not None:
            self.max_outstanding_tasks = max_outstanding_tasks
        else:
            self.max_outstanding_tasks = int(
                os.environ.get("ANALYSIS_MAX_OUTSTANDING_TASKS", "50")
            )

        self.sync_mode = sync_mode
        self._semaphore = threading.BoundedSemaphore(value=self.max_outstanding_tasks)
        self._shutting_down = False
        self._lock = threading.Lock()
        self._executor: Optional[ThreadPoolExecutor] = None

    def _get_executor_unlocked(self) -> ThreadPoolExecutor:
        """
        Retrieves or initializes the ThreadPoolExecutor.
        Must be called only while holding self._lock.
        """
        if self._shutting_down:
            raise RuntimeError("Cannot initialize executor after dispatcher shutdown.")
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self.max_workers,
                thread_name_prefix="analysis-worker-",
            )
        return self._executor

    def _get_executor(self) -> ThreadPoolExecutor:
        """
        Thread-safe accessor for the ThreadPoolExecutor.
        Acquires self._lock to ensure lazy initialization safety when called externally.
        """
        with self._lock:
            return self._get_executor_unlocked()

    def dispatch(self, claim_id: uuid.UUID) -> bool:
        """
        Submits a claim analysis task for execution.

        Returns:
            True if the task was successfully admitted and scheduled.
            False if the dispatcher is shutting down or capacity is saturated.
        """
        if self.sync_mode:
            self._execute_task(claim_id)
            return True

        with self._lock:
            if self._shutting_down:
                logger.warning(
                    "Dispatch rejected for claim %s: dispatcher is shutting down.",
                    claim_id,
                )
                return False

            acquired = self._semaphore.acquire(blocking=False)
            if not acquired:
                logger.warning(
                    "Dispatch rejected for claim %s: capacity saturated (%d outstanding tasks).",
                    claim_id,
                    self.max_outstanding_tasks,
                )
                return False

            try:
                executor = self._get_executor_unlocked()
                future = executor.submit(self._worker_wrapper, claim_id)
                # Future callback guarantees permit release on completion, exception, or queue cancellation
                future.add_done_callback(self._on_future_done)
                return True
            except Exception:
                self._semaphore.release()
                raise

    def _on_future_done(self, future: Future) -> None:
        """
        Releases the semaphore permit when the task reaches any terminal state
        (success, failure, or queue cancellation).
        """
        try:
            self._semaphore.release()
        except ValueError:
            logger.error("Semaphore permit release exceeded initial bound.")

    def _worker_wrapper(self, claim_id: uuid.UUID) -> None:
        """
        Entry point for worker threads. Manages thread-local database connection hygiene.
        """
        close_old_connections()
        try:
            self._execute_task(claim_id)
        finally:
            close_old_connections()

    def _execute_task(self, claim_id: uuid.UUID) -> None:
        """
        Instantiates the pipeline orchestrator and executes the pipeline for claim_id.
        """
        from analysis.services.pipeline import AnalysisPipelineService

        service = AnalysisPipelineService()
        service.run_pipeline(claim_id)

    def shutdown(self, wait: bool = False, cancel_futures: bool = True) -> None:
        """
        Initiates dispatcher shutdown. Rejects subsequent dispatches and optionally
        cancels queued unstarted futures.
        """
        with self._lock:
            self._shutting_down = True
            if self._executor is not None:
                self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
                self._executor = None


_dispatcher_instance: Optional[AnalysisPipelineDispatcher] = None
_dispatcher_lock = threading.Lock()


def get_pipeline_dispatcher() -> AnalysisPipelineDispatcher:
    """
    Returns the process-wide singleton pipeline dispatcher.
    """
    global _dispatcher_instance
    with _dispatcher_lock:
        if _dispatcher_instance is None:
            sync_env = os.environ.get("ANALYSIS_PIPELINE_SYNC", "False").lower() in (
                "true",
                "1",
            )
            _dispatcher_instance = AnalysisPipelineDispatcher(sync_mode=sync_env)
        return _dispatcher_instance


def set_pipeline_dispatcher(
    dispatcher: Optional[AnalysisPipelineDispatcher],
) -> None:
    """
    Overrides the process-wide singleton dispatcher (used for test isolation).
    """
    global _dispatcher_instance
    with _dispatcher_lock:
        _dispatcher_instance = dispatcher
