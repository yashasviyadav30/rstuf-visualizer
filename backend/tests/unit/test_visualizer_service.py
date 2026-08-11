# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""The ordering rules, with both upstreams replaced.

Neither the RSTUF API nor the storage server is reached here. What is under
test is what the service decides, not whether a signature checks out; that
belongs to the integration tests, where real keys sign real metadata.
"""

from __future__ import annotations

from app.client.tuf_client import RepositoryView
from app.config import Settings
from app.dto.schemas import RepositoryState
from app.services import visualizer_service as service_module
from app.services.visualizer_service import VisualizerService
from tests.base import UnitTestCase


class _StubApi:
    """Answers whatever the test told it to, and counts the asking."""

    def __init__(self, answer) -> None:
        self.answer = answer
        self.calls = 0

    async def bootstrap_state(self):
        self.calls += 1
        return self.answer


def _service(
    api_url: str | None = "http://rstuf.example",
) -> VisualizerService:
    return VisualizerService(
        Settings(metadata_url="http://metadata.example/", api_url=api_url)
    )


class TestRepositoryState(UnitTestCase):
    """How RSTUF's answer becomes a state the interface can draw.

    The repository has to be describable before its metadata is worth
    reading, because a repository that was never set up has no signed files
    to show and saying so plainly is better than an empty screen.
    """

    async def test_a_repository_still_being_created_is_initialising(
        self,
    ) -> None:
        service = _service()
        service._rstuf = _StubApi((False, "pre"))

        assert await service._repository_state() is (
            RepositoryState.INITIALISING
        )

    async def test_a_repository_waiting_on_signers_says_so(self) -> None:
        service = _service()
        service._rstuf = _StubApi((False, "signing"))

        assert await service._repository_state() is (
            RepositoryState.AWAITING_SIGNATURES
        )

    async def test_a_finished_bootstrap_is_ready(self) -> None:
        service = _service()
        service._rstuf = _StubApi((True, "finished"))

        assert await service._repository_state() is RepositoryState.READY

    async def test_anything_else_has_not_been_set_up(self) -> None:
        service = _service()
        service._rstuf = _StubApi((False, ""))

        assert await service._repository_state() is (
            RepositoryState.NOT_INITIALISED
        )

    async def test_silence_from_the_api_is_not_an_answer(self) -> None:
        """An API that cannot be reached says nothing about the repository.

        The signed metadata is the evidence, and it lives somewhere else.
        Reading silence as "not set up" would hide a repository that is
        right there and checkable.
        """
        service = _service()
        service._rstuf = _StubApi(None)

        assert await service._repository_state() is RepositoryState.READY

    async def test_no_api_configured_means_nothing_to_ask(self) -> None:
        service = _service(api_url=None)

        assert service._rstuf is None
        assert await service._repository_state() is RepositoryState.READY


class TestRefreshLimit(UnitTestCase):
    """A visible button is pressed by everyone who arrives, every time.

    Honouring every press would mean one full verification pass per visitor
    while the repository itself has not moved, so the cache only survives if
    the server declines the presses that cannot tell it anything new.
    """

    @staticmethod
    def _counting_service(monkeypatch) -> tuple[VisualizerService, list[int]]:
        service = _service(api_url=None)
        passes: list[int] = []

        async def load() -> RepositoryView:
            passes.append(1)
            return RepositoryView()

        monkeypatch.setattr(service, "_load", load)
        return service, passes

    async def test_a_second_press_is_declined(self, monkeypatch) -> None:
        service, passes = self._counting_service(monkeypatch)

        await service.view()
        await service.view(refresh=True)
        await service.view(refresh=True)

        assert len(passes) == 1

    async def test_the_press_is_honoured_once_the_answer_has_aged(
        self, monkeypatch
    ) -> None:
        """Turning a refresh away is a rate limit, not a refusal."""
        service, passes = self._counting_service(monkeypatch)
        monkeypatch.setattr(service_module, "MIN_REFRESH_SECONDS", 0.0)

        await service.view()
        await service.view(refresh=True)

        assert len(passes) == 2

    async def test_the_first_reading_is_never_declined(
        self, monkeypatch
    ) -> None:
        """With nothing in hand there is nothing to compare against."""
        service, passes = self._counting_service(monkeypatch)

        await service.view(refresh=True)

        assert len(passes) == 1
