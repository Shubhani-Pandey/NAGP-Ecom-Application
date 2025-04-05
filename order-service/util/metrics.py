# metrics collection for circuit breaker events
from dataclasses import dataclass
from datetime import datetime, timedelta
import threading

@dataclass
class CircuitBreakerEvent:
    circuit_name: str
    state: str
    timestamp: datetime
    failure_count: int

class MetricsCollector:
    _instance = None
    _lock = threading.Lock()
    _events = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MetricsCollector, cls).__new__(cls)
        return cls._instance

    def record_event(self, circuit_name, state, failure_count):
        with self._lock:
            event = CircuitBreakerEvent(
                circuit_name=circuit_name,
                state=state,
                timestamp=datetime.utcnow(),
                failure_count=failure_count
            )
            self._events.append(event)

    def get_recent_events(self, minutes=5):
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        with self._lock:
            return [e for e in self._events if e.timestamp >= cutoff]
