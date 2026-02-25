"""Unit tests for core event bus module."""
import pytest
from autotrader.core.event_bus import EventBus


@pytest.fixture
def bus():
    """Fixture providing a fresh EventBus instance."""
    return EventBus()


class TestEventBusBasics:
    """Test basic EventBus functionality."""

    async def test_subscribe_and_emit(self, bus):
        """Test subscribing to an event and emitting data."""
        received = []

        async def handler(data):
            received.append(data)

        bus.subscribe("test_event", handler)
        await bus.emit("test_event", {"value": 42})
        assert received == [{"value": 42}]

    async def test_emit_without_data(self, bus):
        """Test emitting without data parameter."""
        received = []

        async def handler(data):
            received.append(data)

        bus.subscribe("event", handler)
        await bus.emit("event")
        assert received == [None]

    async def test_emit_with_string_data(self, bus):
        """Test emitting string data."""
        received = []

        async def handler(data):
            received.append(data)

        bus.subscribe("string_event", handler)
        await bus.emit("string_event", "test_string")
        assert received == ["test_string"]

    async def test_emit_with_number_data(self, bus):
        """Test emitting numeric data."""
        received = []

        async def handler(data):
            received.append(data)

        bus.subscribe("number_event", handler)
        await bus.emit("number_event", 42)
        assert received == [42]

    async def test_emit_with_complex_object(self, bus):
        """Test emitting complex objects."""
        received = []

        async def handler(data):
            received.append(data)

        complex_obj = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "tuple": (4, 5, 6)
        }
        bus.subscribe("complex", handler)
        await bus.emit("complex", complex_obj)
        assert received[0] == complex_obj


class TestMultipleSubscribers:
    """Test multiple subscribers to same event."""

    async def test_multiple_subscribers(self, bus):
        """Test multiple handlers receiving the same event."""
        results_a, results_b = [], []

        async def handler_a(data):
            results_a.append(data)

        async def handler_b(data):
            results_b.append(data)

        bus.subscribe("tick", handler_a)
        bus.subscribe("tick", handler_b)
        await bus.emit("tick", "AAPL")
        assert results_a == ["AAPL"]
        assert results_b == ["AAPL"]

    async def test_three_subscribers(self, bus):
        """Test three handlers receiving the same event."""
        results = [[], [], []]

        async def make_handler(idx):
            async def handler(data):
                results[idx].append(data)
            return handler

        for i in range(3):
            handler = await make_handler(i)
            bus.subscribe("event", handler)

        await bus.emit("event", "data")
        assert all(r == ["data"] for r in results)

    async def test_same_handler_subscribed_twice(self, bus):
        """Test same handler subscribed twice receives event twice."""
        received = []

        async def handler(data):
            received.append(data)

        bus.subscribe("event", handler)
        bus.subscribe("event", handler)
        await bus.emit("event", "data")
        assert received == ["data", "data"]


class TestUnsubscribe:
    """Test unsubscribe functionality."""

    async def test_unsubscribe(self, bus):
        """Test unsubscribing from an event."""
        received = []

        async def handler(data):
            received.append(data)

        bus.subscribe("event", handler)
        bus.unsubscribe("event", handler)
        await bus.emit("event", "ignored")
        assert received == []

    async def test_unsubscribe_one_of_many(self, bus):
        """Test unsubscribing one handler when multiple are registered."""
        results_a, results_b = [], []

        async def handler_a(data):
            results_a.append(data)

        async def handler_b(data):
            results_b.append(data)

        bus.subscribe("event", handler_a)
        bus.subscribe("event", handler_b)
        bus.unsubscribe("event", handler_a)
        await bus.emit("event", "data")
        assert results_a == []
        assert results_b == ["data"]

    async def test_unsubscribe_nonexistent_handler(self, bus):
        """Test unsubscribing a handler that was never subscribed."""
        async def handler(data):
            pass

        # Should not raise
        bus.unsubscribe("event", handler)

    async def test_unsubscribe_nonexistent_event(self, bus):
        """Test unsubscribing from an event that has no subscribers."""
        async def handler(data):
            pass

        # Should not raise
        bus.unsubscribe("nonexistent", handler)

    async def test_unsubscribe_then_resubscribe(self, bus):
        """Test re-subscribing after unsubscribing."""
        received = []

        async def handler(data):
            received.append(data)

        bus.subscribe("event", handler)
        bus.unsubscribe("event", handler)
        bus.subscribe("event", handler)
        await bus.emit("event", "data")
        assert received == ["data"]


class TestNoSubscribers:
    """Test event emission with no subscribers."""

    async def test_emit_no_subscribers(self, bus):
        """Test emitting when nobody is listening."""
        # Should not raise
        await bus.emit("nobody_listens", "data")

    async def test_emit_no_subscribers_complex_data(self, bus):
        """Test emitting complex data when nobody is listening."""
        # Should not raise
        await bus.emit("event", {"nested": {"data": [1, 2, 3]}})


class TestErrorHandling:
    """Test error handling in event handlers."""

    async def test_handler_error_does_not_block_others(self, bus):
        """Test that handler error doesn't prevent other handlers from running."""
        results = []

        async def bad_handler(data):
            raise ValueError("boom")

        async def good_handler(data):
            results.append(data)

        bus.subscribe("event", bad_handler)
        bus.subscribe("event", good_handler)
        await bus.emit("event", "ok")
        assert results == ["ok"]

    async def test_multiple_handler_errors(self, bus):
        """Test multiple handlers throwing errors."""
        results = []

        async def bad_handler_1(data):
            raise ValueError("error1")

        async def good_handler(data):
            results.append(data)

        async def bad_handler_2(data):
            raise RuntimeError("error2")

        bus.subscribe("event", bad_handler_1)
        bus.subscribe("event", good_handler)
        bus.subscribe("event", bad_handler_2)
        await bus.emit("event", "ok")
        assert results == ["ok"]

    async def test_first_handler_error_doesnt_block_second(self, bus):
        """Test that first handler error doesn't block second handler."""
        first_executed = False
        second_executed = False

        async def first_handler(data):
            nonlocal first_executed
            first_executed = True
            raise Exception("first error")

        async def second_handler(data):
            nonlocal second_executed
            second_executed = True

        bus.subscribe("event", first_handler)
        bus.subscribe("event", second_handler)
        await bus.emit("event", None)

        assert first_executed is True
        assert second_executed is True

    async def test_handler_exception_types(self, bus):
        """Test various exception types in handlers."""
        executed = []

        async def value_error_handler(data):
            executed.append("value_error")
            raise ValueError("value error")

        async def runtime_error_handler(data):
            executed.append("runtime_error")
            raise RuntimeError("runtime error")

        async def good_handler(data):
            executed.append("success")

        bus.subscribe("event", value_error_handler)
        bus.subscribe("event", runtime_error_handler)
        bus.subscribe("event", good_handler)
        await bus.emit("event", None)

        assert "value_error" in executed
        assert "runtime_error" in executed
        assert "success" in executed


class TestMultipleEvents:
    """Test handling multiple different events."""

    async def test_different_events(self, bus):
        """Test that different events have separate handlers."""
        event_a_results = []
        event_b_results = []

        async def handler_a(data):
            event_a_results.append(data)

        async def handler_b(data):
            event_b_results.append(data)

        bus.subscribe("event_a", handler_a)
        bus.subscribe("event_b", handler_b)
        await bus.emit("event_a", "a_data")
        await bus.emit("event_b", "b_data")

        assert event_a_results == ["a_data"]
        assert event_b_results == ["b_data"]

    async def test_many_different_events(self, bus):
        """Test many different events."""
        results = {}

        for i in range(10):
            event_name = f"event_{i}"
            results[event_name] = []

            async def make_handler(event_key):
                async def handler(data):
                    results[event_key].append(data)
                return handler

            handler = await make_handler(event_name)
            bus.subscribe(event_name, handler)
            await bus.emit(event_name, f"data_{i}")

        for i in range(10):
            event_name = f"event_{i}"
            assert results[event_name] == [f"data_{i}"]

    async def test_overlapping_handlers_different_events(self, bus):
        """Test same handler for different events."""
        received = []

        async def universal_handler(data):
            received.append(data)

        bus.subscribe("event_1", universal_handler)
        bus.subscribe("event_2", universal_handler)
        await bus.emit("event_1", "data1")
        await bus.emit("event_2", "data2")

        assert received == ["data1", "data2"]


class TestSequentialEmits:
    """Test sequential event emissions."""

    async def test_sequential_emissions(self, bus):
        """Test emitting same event multiple times."""
        received = []

        async def handler(data):
            received.append(data)

        bus.subscribe("event", handler)
        await bus.emit("event", "data1")
        await bus.emit("event", "data2")
        await bus.emit("event", "data3")

        assert received == ["data1", "data2", "data3"]

    async def test_emit_then_subscribe(self, bus):
        """Test that subscribing after emit doesn't receive past events."""
        received = []

        async def handler(data):
            received.append(data)

        await bus.emit("event", "data1")
        bus.subscribe("event", handler)
        await bus.emit("event", "data2")

        assert received == ["data2"]


class TestEventBusState:
    """Test EventBus internal state."""

    def test_new_bus_has_no_handlers(self):
        """Test that new EventBus has no handlers."""
        bus = EventBus()
        assert len(bus._handlers) == 0

    async def test_subscribe_creates_event_entry(self):
        """Test that subscribing creates event entry."""
        bus = EventBus()

        async def handler(data):
            pass

        bus.subscribe("event", handler)
        assert "event" in bus._handlers
        assert len(bus._handlers["event"]) == 1

    async def test_multiple_subscribers_creates_one_entry(self):
        """Test that multiple subscribers share one event entry."""
        bus = EventBus()

        async def handler_a(data):
            pass

        async def handler_b(data):
            pass

        bus.subscribe("event", handler_a)
        bus.subscribe("event", handler_b)
        assert len(bus._handlers) == 1
        assert len(bus._handlers["event"]) == 2

    async def test_unsubscribe_all_cleans_up(self):
        """Test that unsubscribing all handlers doesn't clean up the entry."""
        bus = EventBus()

        async def handler(data):
            pass

        bus.subscribe("event", handler)
        bus.unsubscribe("event", handler)
        # Entry still exists, but list is empty
        assert "event" in bus._handlers
        assert len(bus._handlers["event"]) == 0
