"""A failure inside a future chain must reach the response as a located error --
never be lost, and never leave execution pending ("deferred execution failed")."""

from unittest.mock import Mock

from graphql import (
    GraphQLField,
    GraphQLList,
    GraphQLNonNull,
    GraphQLObjectType,
    GraphQLSchema,
    GraphQLString,
    graphql_sync,
)

from graphql_sync_dataloaders import DeferredExecutionContext, SyncDataLoader, SyncFuture


def run(schema, query):
    return graphql_sync(schema, query, execution_context_class=DeferredExecutionContext)


def make_schema(resolve_items, is_viewer_nullable=True):
    viewer = GraphQLObjectType(
        name="Viewer",
        fields={
            "items": GraphQLField(
                GraphQLNonNull(GraphQLList(GraphQLNonNull(GraphQLString))),
                resolve=resolve_items,
            )
        },
    )
    viewer_type = viewer if is_viewer_nullable else GraphQLNonNull(viewer)
    return GraphQLSchema(
        query=GraphQLObjectType(
            name="Query",
            fields={"viewer": GraphQLField(viewer_type, resolve=lambda *_: {})},
        )
    )


def errors_of(result):
    return [(error.message, error.path) for error in result.errors or []]


def test_non_null_field_resolving_null_from_a_loader_nulls_the_nullable_parent():
    loader = SyncDataLoader(lambda keys: [[] for _ in keys])
    schema = make_schema(lambda *_: loader.load("k").then(lambda _: None))

    result = run(schema, "{ viewer { items } }")

    assert result.data == {"viewer": None}
    assert errors_of(result) == [
        ("Cannot return null for non-nullable field Viewer.items.", ["viewer", "items"])
    ]


def test_error_raised_in_a_then_callback_surfaces_with_its_own_message():
    loader = SyncDataLoader(lambda keys: [None for _ in keys])
    schema = make_schema(lambda *_: loader.load("k").then(lambda value: list(value)))

    result = run(schema, "{ viewer { items } }")

    assert result.data == {"viewer": None}
    assert errors_of(result) == [
        ("'NoneType' object is not iterable", ["viewer", "items"])
    ]


def test_error_reaching_the_root_is_reported_not_left_pending():
    loader = SyncDataLoader(lambda keys: [None for _ in keys])
    schema = make_schema(
        lambda *_: loader.load("k").then(lambda value: list(value)),
        is_viewer_nullable=False,
    )

    result = run(schema, "{ viewer { items } }")

    assert result.data is None
    assert errors_of(result) == [
        ("'NoneType' object is not iterable", ["viewer", "items"])
    ]


def test_then_passes_a_failure_on_without_calling_on_complete():
    source = SyncFuture()
    on_complete = Mock()
    chained = source.then(on_complete)
    seen_by_done_callback = []
    source.add_done_callback(
        lambda _value: seen_by_done_callback.append(source.exception())
    )
    error = ValueError("boom")

    source.set_exception(error)

    on_complete.assert_not_called()
    assert chained.exception() is error
    assert seen_by_done_callback == [error]


def test_adopting_a_pending_future_adopts_its_failure():
    inner, outer = SyncFuture(), SyncFuture()
    outer.set_result(inner)

    inner.set_exception(ValueError("boom"))

    assert isinstance(outer.exception(), ValueError)


def test_all_fails_when_any_input_fails():
    first, second = SyncFuture(), SyncFuture()
    combined = SyncFuture.all([first, second])

    first.set_result(1)
    second.set_exception(ValueError("boom"))

    assert isinstance(combined.exception(), ValueError)
