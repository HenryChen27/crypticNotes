"""Cooperative latest-request cancellation, scoped to the matching worker."""
from contextlib import contextmanager
from threading import local
_state = local()
class Superseded(Exception):
    pass

def checkpoint():
    current = getattr(_state, 'current', None)
    if current is not None and int(current[0].get()) != current[1]:
        raise Superseded()

@contextmanager
def request_scope(counter=None, request=0):
    previous = getattr(_state, 'current', None)
    _state.current = (counter, int(request)) if counter is not None else None
    try:
        checkpoint()
        yield
        checkpoint()
    finally:
        _state.current = previous
