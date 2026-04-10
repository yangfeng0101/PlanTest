# Reservation Background Tasks
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List
import logging

from app.models.reservation import DeviceReservation, ReservationStatus
from app.services.reservation_service import reservation_service
from app.database import AsyncSessionLocal
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)


class ReservationTasks:
    """Background tasks for reservation management"""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._check_interval = 60  # Check every 60 seconds
        self._reminder_minutes = 5  # Remind 5 minutes before start
        self._max_extension_hours = 1  # Max 1 hour extension

    async def start(self):
        """Start the background tasks"""
        if self._running:
            logger.warning("Reservation tasks already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("Reservation background tasks started")

    async def stop(self):
        """Stop the background tasks"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Reservation background tasks stopped")

    async def _run_scheduler(self):
        """Main scheduler loop"""
        while self._running:
            try:
                await self._process_reservations()
            except Exception as e:
                logger.error(f"Error processing reservations: {e}")

            await asyncio.sleep(self._check_interval)

    async def _process_reservations(self):
        """Process all reservation-related tasks"""
        async with AsyncSessionLocal() as session:
            # 1. Activate pending reservations that have started
            await self._activate_pending_reservations(session)

            # 2. Complete expired reservations (auto-release)
            await self._complete_expired_reservations(session)

            # 3. Send reminders for upcoming reservations
            await self._send_reminders(session)

    async def _activate_pending_reservations(self, session):
        """Activate reservations that have reached their start time"""
        now = datetime.utcnow()

        # Find pending reservations that should be active
        result = await session.execute(
            select(DeviceReservation).where(
                and_(
                    DeviceReservation.status == ReservationStatus.PENDING,
                    DeviceReservation.start_time <= now,
                    DeviceReservation.end_time > now
                )
            )
        )
        reservations = list(result.scalars().all())

        for reservation in reservations:
            reservation.status = ReservationStatus.ACTIVE
            logger.info(f"Activated reservation {reservation.id} for device {reservation.device_id}")

        if reservations:
            await session.commit()
            logger.info(f"Activated {len(reservations)} pending reservations")

    async def _complete_expired_reservations(self, session):
        """Complete reservations that have passed their end time (auto-release)"""
        now = datetime.utcnow()

        # Find active or pending reservations that have expired
        result = await session.execute(
            select(DeviceReservation).where(
                and_(
                    DeviceReservation.status.in_([
                        ReservationStatus.ACTIVE,
                        ReservationStatus.PENDING
                    ]),
                    DeviceReservation.end_time <= now
                )
            )
        )
        reservations = list(result.scalars().all())

        for reservation in reservations:
            reservation.status = ReservationStatus.COMPLETED
            logger.info(
                f"Auto-released reservation {reservation.id} for device {reservation.device_id}"
            )

        if reservations:
            await session.commit()
            logger.info(f"Auto-released {len(reservations)} expired reservations")

    async def _send_reminders(self, session):
        """Send reminders for reservations starting soon"""
        now = datetime.utcnow()
        reminder_time = now + timedelta(minutes=self._reminder_minutes)

        # Find active/pending reservations starting within reminder window
        # that haven't been reminded yet (we'll track this with a simple flag)
        result = await session.execute(
            select(DeviceReservation).where(
                and_(
                    DeviceReservation.status.in_([
                        ReservationStatus.PENDING,
                        ReservationStatus.ACTIVE
                    ]),
                    DeviceReservation.start_time > now,
                    DeviceReservation.start_time <= reminder_time
                )
            )
        )
        reservations = list(result.scalars().all())

        for reservation in reservations:
            # In production, this would send a notification (WebSocket, email, etc.)
            logger.info(
                f"Reminder: Reservation {reservation.id} for device {reservation.device_id} "
                f"starts at {reservation.start_time.isoformat()}"
            )
            # TODO: Integrate with notification service (WebSocket, Feishu, Email)

        if reservations:
            logger.info(f"Sent {len(reservations)} reservation reminders")

    @property
    def max_extension_hours(self) -> int:
        """Maximum extension duration in hours"""
        return self._max_extension_hours


# Singleton instance
reservation_tasks = ReservationTasks()
