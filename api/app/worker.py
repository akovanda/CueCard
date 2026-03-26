from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from .db.repo import (
    claim_queue_batch,
    cleanup_expired_boosts,
    fail_queue_items,
    process_queue_items,
)
from .db.session import dispose_engines, session_scope, verify_database_compatibility
from .settings import Settings, load_settings


logger = logging.getLogger(__name__)


async def run_worker_cycle(settings: Optional[Settings] = None) -> int:
    settings = settings or load_settings()
    async with session_scope(settings) as session:
        items = await claim_queue_batch(
            session,
            batch_size=settings.worker_batch,
            lease_seconds=settings.worker_lease_sec,
        )
        if not items:
            return 0

        try:
            await process_queue_items(session, items, settings=settings)
        except Exception as exc:
            await session.rollback()
            await fail_queue_items(session, [item.id for item in items], str(exc))
            logger.exception("Worker failed processing queue batch")
            return 0

        return len(items)


async def run_cleanup_cycle(settings: Optional[Settings] = None) -> int:
    settings = settings or load_settings()
    async with session_scope(settings) as session:
        return await cleanup_expired_boosts(session)


async def run_worker(settings: Optional[Settings] = None) -> None:
    settings = settings or load_settings()
    await verify_database_compatibility(settings)

    next_cleanup_at = time.monotonic() + settings.cleanup_interval_sec
    while True:
        processed = await run_worker_cycle(settings)

        now = time.monotonic()
        if now >= next_cleanup_at:
            deleted = await run_cleanup_cycle(settings)
            if deleted:
                logger.info("Deleted %s expired usage boost rows", deleted)
            next_cleanup_at = now + settings.cleanup_interval_sec

        if processed:
            continue

        await asyncio.sleep(settings.worker_poll_sec)


def main() -> None:  # pragma: no cover
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        asyncio.run(run_worker())
    finally:
        asyncio.run(dispose_engines())


if __name__ == "__main__":  # pragma: no cover
    main()
