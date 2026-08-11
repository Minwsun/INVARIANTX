import asyncio

from app.runtime.events import EventJournal, EventType
from app.storage.memory import InMemoryStore


def test_event_journal_sequences_and_replays_after_event_id() -> None:
    async def run():
        journal = EventJournal(InMemoryStore())
        first = await journal.append("run-1", EventType.RUN_CREATED, "api")
        second = await journal.append("run-1", EventType.RUN_STARTED, "runtime")
        third = await journal.append("run-1", EventType.RUN_COMPLETED, "runtime")

        replay = await journal.list("run-1", second.event_id)
        streamed = [
            event
            async for event in journal.stream("run-1", first.event_id)
        ]
        return first, second, third, replay, streamed

    first, second, third, replay, streamed = asyncio.run(run())

    assert [first.sequence, second.sequence, third.sequence] == [1, 2, 3]
    assert replay == [third]
    assert streamed == [second, third]


def test_event_journal_rejects_events_after_terminal() -> None:
    async def run():
        journal = EventJournal(InMemoryStore())
        await journal.append("run-1", EventType.RUN_COMPLETED, "runtime")
        try:
            await journal.append("run-1", EventType.TASK_PROPOSED, "planner")
        except RuntimeError:
            return
        raise AssertionError("journal accepted an event after terminal state")

    asyncio.run(run())
