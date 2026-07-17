from typing import (
    Any,
    Callable,
    Optional,
    List,
)

from .exceptions import InvalidStateError

_PENDING = "PENDING"
_FINISHED = "FINISHED"


class SyncFuture:

    _state = _PENDING
    _result: Optional[Any] = None
    _exception: Optional[Exception] = None
    _callbacks: List[Callable]
    _cancel_message = None

    deferred_callback: Optional[Callable] = None

    def __init__(self):
        self._callbacks = []

    @classmethod
    def resolve(cls, value: Any) -> "SyncFuture":
        """Wrap a value in an already-resolved future (``Promise.resolve``)."""
        future = cls()
        future.set_result(value)
        return future

    @classmethod
    def all(cls, futures: List) -> "SyncFuture":
        """Resolve once every input future completes (``Promise.all``).

        Non-future items pass through unchanged; order is preserved.
        """
        results: List = [None] * len(futures)
        result_future = cls()
        unresolved = 0

        for i, f in enumerate(futures):
            if not isinstance(f, SyncFuture):
                results[i] = f
                continue
            if f.done():
                results[i] = f.result()
                continue
            unresolved += 1

            def on_done(value, idx=i):
                nonlocal unresolved
                results[idx] = value
                unresolved -= 1
                if unresolved == 0:
                    result_future.set_result(results)

            f.add_done_callback(on_done)

        if unresolved == 0:
            result_future.set_result(results)
        return result_future

    def done(self) -> bool:
        return self._state != _PENDING

    def result(self):
        self._assert_state(_FINISHED)
        if self._exception is not None:
            raise self._exception
        return self._result

    def exception(self):
        self._assert_state(_FINISHED)
        return self._exception

    def add_done_callback(self, fn: Callable) -> None:
        self._assert_state(_PENDING)
        self._callbacks.append(fn)

    def set_result(self, result: Any) -> None:
        if self is result:
            raise TypeError("Cannot resolve future with itself.")

        if isinstance(result, SyncFuture):
            if result.done():
                # add_done_callback asserts PENDING, so flatten an already-resolved
                # future inline (propagating any exception).
                if result._exception is not None:
                    self.set_exception(result._exception)
                else:
                    self.set_result(result._result)
            else:
                result.add_done_callback(self.set_result)
        else:
            self._assert_state(_PENDING)
            self._result = result
            self._finish()

    def set_exception(self, exception: Exception) -> None:
        self._assert_state(_PENDING)
        if isinstance(exception, type):
            exception = exception()
        self._exception = exception
        self._finish()

    def _assert_state(self, state: str) -> None:
        if self._state != state:
            raise InvalidStateError(f"Future is not {state}")

    def _finish(self):
        self._state = _FINISHED
        callbacks = self._callbacks
        if not callbacks:
            return
        self._callbacks = []
        for callback in callbacks:
            callback(self._result)

    def then(
            self,
            on_complete: Callable,
            handle_exception: Callable = None,
    ) -> "SyncFuture":
        ret = SyncFuture()

        def call_and_resolve(v: Any) -> None:
            try:
                ret.set_result(on_complete(v))
            except Exception as e:
                if handle_exception is None:
                    ret.set_exception(e)
                else:
                    handle_exception(e, ret)

        if self.done():
            call_and_resolve(self.result())
        else:
            self.add_done_callback(call_and_resolve)

        return ret

    def sync_resolve(self) -> Any:
        """Resolve this future by draining pending dataloader batches.

        For use outside a GraphQL execution context, which otherwise drives the
        batch queue itself.
        """
        if self.done():
            return self.result()
        # Local import: sync_dataloader imports this module.
        from .sync_dataloader import dataloader_batch_callbacks

        dataloader_batch_callbacks.run_all_callbacks()
        if not self.done():
            raise InvalidStateError(
                "SyncFuture is still pending after draining dataloader batches"
            )
        return self.result()


def maybe_then(value, on_complete, on_exception=None):
    try:
        if not isinstance(value, SyncFuture):
            return on_complete(value)

        if value.done():
            return on_complete(value.result())
    except Exception as e:
        if on_exception:
            return on_exception(e)
        else:
            raise

    return value.then(on_complete, on_exception)
