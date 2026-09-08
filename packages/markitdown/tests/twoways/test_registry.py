from markitdown.twoways._registry import PriorityRegistry


def test_registry_matches_upstream_priority_and_equal_priority_order():
    registry = PriorityRegistry[str]()
    registry.register("first-zero", priority=0)
    registry.register("ten", priority=10)
    registry.register("minus-one", priority=-1)
    registry.register("second-zero", priority=0)
    assert [r.implementation for r in registry.iter_candidates()] == [
        "minus-one",
        "second-zero",
        "first-zero",
        "ten",
    ]


def test_candidate_iteration_does_not_mutate_registry():
    registry = PriorityRegistry[str]()
    registry.register("a")
    registry.register("b", priority=-1)
    first = tuple(registry.iter_candidates())
    second = tuple(registry.iter_candidates())
    assert first == second
    assert [entry.implementation for entry in registry.registrations] == ["a", "b"]


def test_registration_keeps_optional_name():
    registry = PriorityRegistry[object]()
    implementation = object()
    registration = registry.register(implementation, priority=2.5, name="pptx-patch")
    assert registration.implementation is implementation
    assert registration.priority == 2.5
    assert registration.name == "pptx-patch"
