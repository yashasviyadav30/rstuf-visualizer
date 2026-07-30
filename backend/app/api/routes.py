"""HTTP endpoints exposed to the browser.

Every route here is a GET. The visualizer reads a TUF repository and
changes nothing in it.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz", tags=["ops"])
def healthz() -> dict[str, str]:
    """Report that the process is alive.

    Polled by the container orchestrator, not by the browser. It says
    nothing about the state of the TUF repository.
    """
    return {"status": "ok"}
