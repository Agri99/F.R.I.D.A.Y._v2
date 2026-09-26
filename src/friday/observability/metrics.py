"""
src/friday/observability/metrics.py

WHAT THIS IS FOR:
Metrics aggregation and instrumentation (Runbook §79).
Tracks Voice, Models, Computer use, and Learning metrics.
"""
from dataclasses import dataclass
from .events import EventBus, ObservabilityEvent


@dataclass
class MetricsStore:
    # Models
    model_time_to_first_token: float = 0.0
    model_tokens_per_sec: float = 0.0
    model_provider_failures: int = 0
    model_fallback_count: int = 0
    
    # Computer use
    cu_resolution_confidence: float = 0.0
    cu_execution_latency: float = 0.0
    cu_verification_failures: int = 0
    cu_replans: int = 0
    
    # Learning
    learning_candidate_count: int = 0
    learning_promotion_count: int = 0
    learning_rollback_count: int = 0


_STORE = MetricsStore()


def _handle_event(event: ObservabilityEvent):
    # Models
    if event.name == "model_inference_complete":
        _STORE.model_time_to_first_token = event.data.get("ttft", 0.0)
        _STORE.model_tokens_per_sec = event.data.get("tps", 0.0)
    elif event.name == "model_provider_failure":
        _STORE.model_provider_failures += 1
    elif event.name == "model_fallback":
        _STORE.model_fallback_count += 1
        
    # Computer use
    elif event.name == "cu_action_executed":
        _STORE.cu_execution_latency = event.data.get("latency_ms", 0.0)
        _STORE.cu_resolution_confidence = event.data.get("confidence", 0.0)
    elif event.name == "cu_verification_failed":
        _STORE.cu_verification_failures += 1
    elif event.name == "cu_replan":
        _STORE.cu_replans += 1
        
    # Learning
    elif event.name == "learning_candidate_generated":
        _STORE.learning_candidate_count += 1
    elif event.name == "learning_candidate_promoted":
        _STORE.learning_promotion_count += 1
    elif event.name == "learning_rollback":
        _STORE.learning_rollback_count += 1


EventBus().subscribe(_handle_event)


def get_current_metrics() -> dict:
    return {
        "models": {
            "time_to_first_token": _STORE.model_time_to_first_token,
            "tokens_per_sec": _STORE.model_tokens_per_sec,
            "provider_failures": _STORE.model_provider_failures,
            "fallback_count": _STORE.model_fallback_count
        },
        "computer_use": {
            "resolution_confidence": _STORE.cu_resolution_confidence,
            "execution_latency": _STORE.cu_execution_latency,
            "verification_failures": _STORE.cu_verification_failures,
            "replans": _STORE.cu_replans
        },
        "learning": {
            "candidate_count": _STORE.learning_candidate_count,
            "promotion_count": _STORE.learning_promotion_count,
            "rollback_count": _STORE.learning_rollback_count
        }
    }

