# utils/circuit_breaker.py
import time
from functools import wraps
from enum import Enum
import threading
import logging
from util.metrics import MetricsCollector

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"      # Service calls are blocked
    HALF_OPEN = "HALF_OPEN"  # Testing if service is back

class CircuitBreaker:
    def __init__(self, name, failure_threshold=5, reset_timeout=60, half_open_timeout=30):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout  # Time to wait before attempting reset
        self.half_open_timeout = half_open_timeout  # Time to wait in half-open state
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time = None
        self.half_open_time = None
        self._lock = threading.Lock()
        self.metrics = MetricsCollector()

    def can_execute(self):
        """Check if the circuit breaker allows execution"""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.reset_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_time = time.time()
                    logger.info(f"Circuit {self.name} moved to HALF_OPEN state")
                    return True
                return False
            
            if self.state == CircuitState.HALF_OPEN:
                if time.time() - self.half_open_time >= self.half_open_timeout:
                    self.state = CircuitState.CLOSED
                    self.failures = 0
                    logger.info(f"Circuit {self.name} moved to CLOSED state")
                    return True
                return True
            
            return False

    def record_failure(self):
        """Record a failure and potentially open the circuit"""
        with self._lock:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.last_failure_time = time.time()
                self.metrics.record_event(
                    self.name, 
                    self.state.value, 
                    self.failures
                )
                logger.warning(f"Circuit {self.name} OPENED due to {self.failures} failures")

    def record_success(self):
        """Record a success and potentially close the circuit"""
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failures = 0
                logger.info(f"Circuit {self.name} CLOSED after successful execution")

    def get_state(self):
        """Get the current state of the circuit breaker"""
        return self.state

# Circuit breaker registry to manage multiple circuit breakers
class CircuitBreakerRegistry:
    _instance = None
    _circuit_breakers = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CircuitBreakerRegistry, cls).__new__(cls)
        return cls._instance

    def get_circuit_breaker(self, name, **kwargs):
        """Get or create a circuit breaker"""
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker(name, **kwargs)
        return self._circuit_breakers[name]

    def get_all_states(self):
        """Get states of all circuit breakers"""
        return {name: cb.get_state().value 
                for name, cb in self._circuit_breakers.items()}

# Decorator for circuit breaker pattern
def circuit_breaker(name, fallback_function=None, **cb_kwargs):
    def decorator(func):
        cb = CircuitBreakerRegistry().get_circuit_breaker(name, **cb_kwargs)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not cb.can_execute():
                if fallback_function:
                    return fallback_function(*args, **kwargs)
                raise Exception(f"Circuit {name} is OPEN")
            
            try:
                result = func(*args, **kwargs)
                cb.record_success()
                return result
            except Exception as e:
                cb.record_failure()
                raise
                
        return wrapper
    return decorator
