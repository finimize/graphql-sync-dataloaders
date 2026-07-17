import pytest

from graphql_sync_dataloaders import SyncFuture, InvalidStateError


def test_sync_future():

    f = SyncFuture()
    assert not f.done()
    with pytest.raises(InvalidStateError):
        f.result()
    f.set_result(42)
    assert f.result() == 42
    assert f.done()


def test_chaining():
    f = SyncFuture()
    f2 = f.then(lambda x: x * 2)
    f3 = f2.then(lambda x: f"{x}")

    f.set_result(1)

    assert f.done()
    assert f2.done()
    assert f3.done()

    assert f.result() == 1
    assert f2.result() == 2
    assert f3.result() == "2"


def test_nested_chaining():
    f = SyncFuture()
    f2 = SyncFuture()
    f3 = f.then(lambda _: f2).then(lambda x: f"{x}")

    f.set_result(1)

    assert f.done()
    assert not f2.done()
    assert not f3.done()

    f2.set_result(2)

    assert f.done()
    assert f2.done()
    assert f3.done()

    assert f.result() == 1
    assert f2.result() == 2
    assert f3.result() == "2"


def test_set_result_flattens_already_resolved_future():
    # A callback that returns an already-resolved future must flatten inline;
    # add_done_callback asserts PENDING so this would otherwise raise.
    done = SyncFuture()
    done.set_result(1)

    outer = SyncFuture()
    outer.set_result(done)

    assert outer.done()
    assert outer.result() == 1


def test_then_callback_returning_resolved_future():
    f = SyncFuture()
    r = f.then(lambda x: _resolved(x + 10))
    f.set_result(5)

    assert r.done()
    assert r.result() == 15


def test_set_result_flattens_already_rejected_future():
    rejected = SyncFuture()
    rejected.set_exception(ValueError("boom"))

    outer = SyncFuture()
    outer.set_result(rejected)

    assert outer.done()
    assert isinstance(outer.exception(), ValueError)


def test_resolve_wraps_a_value():
    f = SyncFuture.resolve(42)
    assert f.done()
    assert f.result() == 42


def test_all_resolves_when_every_input_completes():
    a = SyncFuture()
    b = SyncFuture()
    r = SyncFuture.all([a, b])
    assert not r.done()

    a.set_result(1)
    assert not r.done()
    b.set_result(2)

    assert r.done()
    assert r.result() == [1, 2]


def test_all_preserves_order_and_passes_plain_values_through():
    pending = SyncFuture()
    r = SyncFuture.all([SyncFuture.resolve("a"), pending, "c"])
    assert not r.done()

    pending.set_result("b")

    assert r.result() == ["a", "b", "c"]


def test_all_of_only_resolved_or_plain_is_done_immediately():
    r = SyncFuture.all([1, SyncFuture.resolve(2), 3])
    assert r.done()
    assert r.result() == [1, 2, 3]


def test_all_empty():
    assert SyncFuture.all([]).result() == []


def _resolved(value):
    f = SyncFuture()
    f.set_result(value)
    return f
