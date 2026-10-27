from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

log = logging.getLogger("groundzero.layer4")


class Layer4Supervisor:
    """Small in-process supervisor for active trips.

    Layer 3 remains the durable session authority. Layer 4 only owns the
    live loop: active sessions get a periodic worker; paused/terminal sessions
    are removed immediately. This keeps the implementation safe in VS Code,
    Docker and a single-process FastAPI deployment.
    """

    def __init__(self, orchestrator=None, interval_s: int = 60):
        self.orchestrator = orchestrator
        self.interval_s = interval_s
        self._tasks: Dict[str, asyncio.Task] = {}

    def start(self, session_id: str) -> None:
        if session_id in self._tasks and not self._tasks[session_id].done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._tasks[session_id] = loop.create_task(self._run(session_id), name=f"layer4:{session_id}")

    def stop(self, session_id: str) -> None:
        task = self._tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    async def shutdown(self) -> None:
        for sid in list(self._tasks):
            self.stop(sid)
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def _run(self, session_id: str) -> None:
        try:
            while True:
                session = self.orchestrator.repo.get_session(session_id) if self.orchestrator else None
                status = (session or {}).get("status")
                if status != "active":
                    return
                # Worker 4's durable state is already written by Layer 3.
                # This hook is intentionally lightweight; navigation is demand-driven
                # from the map and never polls OSRM in the background.
                await asyncio.sleep(self.interval_s)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Layer 4 supervisor failed for session %s", session_id)
