import enum
import logging
import threading
import time
import uuid
from typing import Optional, Tuple

from django.conf import settings

from analysis.inference.adapter import ModelAdapterProtocol, ModelOutput
from analysis.model_loader.loader import (
    ModelArtifactCorruptedError,
    ModelArtifactNotFoundError,
    ModelLoadingError,
)

logger = logging.getLogger(__name__)


class InferenceServiceError(RuntimeError):
    """Base exception for operational errors within ModelInferenceService."""

    pass


class InvalidModelInputError(InferenceServiceError, ValueError):
    """Raised when input provided to ModelInferenceService fails contract validation."""

    pass


class InvalidModelOutputError(InferenceServiceError, ValueError):
    """Raised when the model adapter produces malformed or contract-violating output."""

    pass


class ModelCircuitBreakerOpenError(InferenceServiceError):
    """Raised when model inference is requested while the circuit breaker is OPEN."""

    pass


class BreakerState(enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class ModelCircuitBreaker:
    """
    Process-wide circuit breaker protecting the backend against model artifact corruption,
    missing files, and repeated model forward pass failures.

    State Machine:
    - CLOSED: Normal operation. Requests admitted without probe tokens.
    - OPEN: Fast reject. When open_until timestamp expires, transitions to HALF_OPEN.
    - HALF_OPEN: Admits exactly ONE probe request with a unique probe_id token.
      - Probe success (matching token): transitions to CLOSED.
      - Probe failure (matching token): transitions back to OPEN with updated cooldown.
      - Non-probe or mismatched token success/failure: does not clear or alter active probe state.
    """

    def __init__(
        self,
        ttl_seconds: float = 60.0,
        transient_ttl_seconds: float = 5.0,
    ):
        self._ttl_seconds = ttl_seconds
        self._transient_ttl_seconds = transient_ttl_seconds
        self._state = BreakerState.CLOSED
        self._open_until: float = 0.0
        self._probe_in_flight: bool = False
        self._current_probe_id: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> BreakerState:
        with self._lock:
            return self._state

    def reset(self) -> None:
        """Resets the circuit breaker to CLOSED (for testing/diagnostics)."""
        with self._lock:
            self._state = BreakerState.CLOSED
            self._open_until = 0.0
            self._probe_in_flight = False
            self._current_probe_id = None

    def admit_request(self) -> Tuple[bool, Optional[str]]:
        """
        Evaluates admission for an incoming inference request.

        Returns:
            Tuple of (admitted: bool, probe_id: Optional[str]).
            probe_id is non-None ONLY when admitting a single HALF_OPEN probe request.
        """
        with self._lock:
            if self._state == BreakerState.CLOSED:
                return True, None

            now = time.monotonic()
            if self._state == BreakerState.OPEN:
                if now < self._open_until:
                    return False, None
                # Cooldown expired: transition to HALF_OPEN
                self._state = BreakerState.HALF_OPEN
                self._probe_in_flight = True
                probe_id = str(uuid.uuid4())
                self._current_probe_id = probe_id
                logger.info(
                    "Model circuit breaker cooldown expired; entering HALF_OPEN with probe %s.",
                    probe_id,
                )
                return True, probe_id

            if self._state == BreakerState.HALF_OPEN:
                if not self._probe_in_flight:
                    self._probe_in_flight = True
                    probe_id = str(uuid.uuid4())
                    self._current_probe_id = probe_id
                    return True, probe_id
                return False, None

            return False, None

    def record_success(self, probe_id: Optional[str] = None) -> None:
        """
        Records a successful model forward pass.
        Decouples normal request success from HALF_OPEN probe resolution.
        """
        with self._lock:
            if self._state == BreakerState.HALF_OPEN:
                if probe_id is not None and probe_id == self._current_probe_id:
                    logger.info(
                        "Model circuit breaker probe %s succeeded; transitioning to CLOSED.",
                        probe_id,
                    )
                    self._state = BreakerState.CLOSED
                    self._open_until = 0.0
                    self._probe_in_flight = False
                    self._current_probe_id = None
                else:
                    logger.debug(
                        "Non-probe or non-matching success (probe_id=%s) in HALF_OPEN; "
                        "retaining active probe (%s).",
                        probe_id,
                        self._current_probe_id,
                    )
            elif self._state == BreakerState.CLOSED:
                pass

    def record_failure(self, exc: Exception, probe_id: Optional[str] = None) -> None:
        """
        Records an operational failure and adjusts circuit breaker state.
        Client validation errors never trip the breaker.
        Non-probe failures never invalidate an active HALF_OPEN probe.
        """
        if isinstance(exc, (InvalidModelInputError, TypeError)):
            return

        with self._lock:
            now = time.monotonic()
            is_artifact_error = isinstance(
                exc, (ModelArtifactNotFoundError, ModelArtifactCorruptedError)
            )
            ttl = (
                getattr(
                    settings,
                    "MODEL_CIRCUIT_BREAKER_TTL_SECONDS",
                    self._ttl_seconds,
                )
                if is_artifact_error
                else getattr(
                    settings,
                    "MODEL_CIRCUIT_BREAKER_TRANSIENT_TTL_SECONDS",
                    self._transient_ttl_seconds,
                )
            )

            if self._state == BreakerState.HALF_OPEN:
                if probe_id is not None and probe_id == self._current_probe_id:
                    logger.warning(
                        "Model circuit breaker probe %s failed (%s: %s); reopening breaker for %0.1fs.",
                        probe_id,
                        type(exc).__name__,
                        exc,
                        ttl,
                    )
                    self._state = BreakerState.OPEN
                    self._open_until = now + ttl
                    self._probe_in_flight = False
                    self._current_probe_id = None
                else:
                    logger.debug(
                        "Non-probe or stale failure (probe_id=%s) in HALF_OPEN; retaining active probe.",
                        probe_id,
                    )
            elif self._state == BreakerState.CLOSED:
                logger.warning(
                    "Model circuit breaker tripped to OPEN (%s: %s); cooldown=%0.1fs.",
                    type(exc).__name__,
                    exc,
                    ttl,
                )
                self._state = BreakerState.OPEN
                self._open_until = now + ttl
                self._probe_in_flight = False
                self._current_probe_id = None
            elif self._state == BreakerState.OPEN:
                self._open_until = max(self._open_until, now + ttl)


_shared_circuit_breaker: ModelCircuitBreaker = ModelCircuitBreaker()


class ModelInferenceService:
    """
    Domain-level service coordinating claim classification inference through
    configured model adapters conforming to ModelAdapterProtocol, protected by
    the process-wide ModelCircuitBreaker.
    """

    def __init__(
        self,
        adapter: Optional[ModelAdapterProtocol] = None,
        circuit_breaker: Optional[ModelCircuitBreaker] = None,
    ):
        """
        Initializes the service with optional adapter injection.

        Args:
            adapter: Instance conforming to ModelAdapterProtocol. If None,
                     lazily resolves to DebertaModelAdapter on first adapter access.
            circuit_breaker: Optional ModelCircuitBreaker instance. If None and adapter
                             is None, uses the process-wide shared circuit breaker.
        """
        self._adapter = adapter
        if circuit_breaker is not None:
            self._circuit_breaker = circuit_breaker
        elif adapter is not None:
            self._circuit_breaker = ModelCircuitBreaker()
        else:
            self._circuit_breaker = _shared_circuit_breaker

    @classmethod
    def get_circuit_breaker(cls) -> ModelCircuitBreaker:
        return _shared_circuit_breaker

    @classmethod
    def reset_circuit_breaker(cls) -> None:
        _shared_circuit_breaker.reset()

    @property
    def adapter(self) -> ModelAdapterProtocol:
        """
        Resolves the active adapter. Lazily instantiates DebertaModelAdapter
        if no adapter was injected.
        """
        if self._adapter is None:
            from analysis.inference.deberta import DebertaModelAdapter

            self._adapter = DebertaModelAdapter()
        return self._adapter

    @property
    def model_version(self) -> Optional[str]:
        """
        Returns the model version string reported by the configured adapter,
        or None if the adapter does not expose a version.
        """
        return getattr(self.adapter, "model_version", None)

    def predict(self, cleaned_text: str) -> ModelOutput:
        """
        Executes model inference on pre-cleaned, pre-validated claim text under circuit-breaker protection.

        Args:
            cleaned_text: Sanitized claim text (non-empty string).

        Returns:
            ModelOutput containing validated ModelPrediction and full-precision float confidence.

        Raises:
            TypeError: If cleaned_text is not a string.
            InvalidModelInputError: If cleaned_text is empty or whitespace-only.
            ModelCircuitBreakerOpenError: If breaker rejects admission.
            InvalidModelOutputError: If adapter returns a non-ModelOutput object.
            InferenceServiceError: If adapter forward pass or model loading fails.
        """
        if not isinstance(cleaned_text, str):
            raise TypeError(
                f"cleaned_text must be a string, got {type(cleaned_text).__name__}"
            )

        if not cleaned_text or not cleaned_text.strip():
            raise InvalidModelInputError(
                "cleaned_text cannot be empty or whitespace-only."
            )

        # 1. Circuit breaker admission check
        admitted, probe_id = self._circuit_breaker.admit_request()
        if not admitted:
            raise ModelCircuitBreakerOpenError(
                "Model circuit breaker is OPEN. Inference temporarily suspended."
            )

        from analysis.inference.deberta import ModelInferenceError

        try:
            raw_output = self.adapter.predict(cleaned_text)
            self._circuit_breaker.record_success(probe_id)
        except (
            ModelInferenceError,
            ModelLoadingError,
            ModelArtifactNotFoundError,
            ModelArtifactCorruptedError,
        ) as err:
            self._circuit_breaker.record_failure(err, probe_id)
            raise InferenceServiceError(f"Model inference failed: {err}") from err
        except Exception as err:
            self._circuit_breaker.record_failure(err, probe_id)
            raise

        if not isinstance(raw_output, ModelOutput):
            raise InvalidModelOutputError(
                f"Model adapter returned unexpected output type: expected ModelOutput, got {type(raw_output).__name__}"
            )

        if not isinstance(raw_output.confidence, float):
            return ModelOutput(
                prediction=raw_output.prediction,
                confidence=float(raw_output.confidence),
            )

        return raw_output
