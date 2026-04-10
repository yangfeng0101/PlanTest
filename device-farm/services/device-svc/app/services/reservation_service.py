# Reservation Service
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import logging

from app.models.reservation import DeviceReservation, ReservationStatus as ModelReservationStatus
from app.models.reservation_schemas import (
    ReservationCreate,
    ReservationUpdate,
    ReservationStatus,
)
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Maximum extension duration in hours
MAX_EXTENSION_HOURS = 1


class ReservationService:
    """Service for managing device reservations"""

    async def create_reservation(
        self,
        reservation_data: ReservationCreate,
        db: Optional[AsyncSession] = None
    ) -> DeviceReservation:
        """
        Create a new device reservation.

        Args:
            reservation_data: Reservation creation data
            db: Optional database session

        Returns:
            Created reservation

        Raises:
            ValueError: If there's a conflict with existing reservations
        """
        async def _create(session: AsyncSession):
            # Check for conflicts
            conflicts = await self._check_conflicts(
                session,
                reservation_data.device_id,
                reservation_data.start_time,
                reservation_data.end_time
            )

            if conflicts:
                conflict_details = [
                    {
                        "reservation_id": c.id,
                        "start_time": c.start_time.isoformat(),
                        "end_time": c.end_time.isoformat(),
                        "user_id": c.user_id
                    }
                    for c in conflicts
                ]
                raise ValueError(
                    f"Reservation conflicts with existing reservations: {conflict_details}"
                )

            # Create reservation
            reservation = DeviceReservation(
                device_id=reservation_data.device_id,
                user_id=reservation_data.user_id,
                start_time=reservation_data.start_time,
                end_time=reservation_data.end_time,
                purpose=reservation_data.purpose,
                status=ModelReservationStatus.PENDING
            )
            session.add(reservation)
            await session.flush()
            await session.refresh(reservation)
            return reservation

        if db:
            return await _create(db)
        else:
            async with AsyncSessionLocal() as session:
                return await _create(session)

    async def cancel_reservation(
        self,
        reservation_id: str,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> Optional[DeviceReservation]:
        """
        Cancel a reservation.

        Args:
            reservation_id: ID of reservation to cancel
            user_id: Optional user ID for authorization check
            db: Optional database session

        Returns:
            Cancelled reservation or None if not found
        """
        async def _cancel(session: AsyncSession):
            result = await session.execute(
                select(DeviceReservation).where(
                    DeviceReservation.id == reservation_id
                )
            )
            reservation = result.scalar_one_or_none()

            if not reservation:
                return None

            # Check authorization if user_id provided
            if user_id and reservation.user_id != user_id:
                raise ValueError("Not authorized to cancel this reservation")

            # Can only cancel pending or active reservations
            if reservation.status not in [
                ModelReservationStatus.PENDING,
                ModelReservationStatus.ACTIVE
            ]:
                raise ValueError(
                    f"Cannot cancel reservation with status {reservation.status}"
                )

            reservation.status = ModelReservationStatus.CANCELLED
            await session.flush()
            await session.refresh(reservation)
            return reservation

        if db:
            return await _cancel(db)
        else:
            async with AsyncSessionLocal() as session:
                return await _cancel(session)

    async def get_reservations(
        self,
        device_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: Optional[ReservationStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        db: Optional[AsyncSession] = None
    ) -> List[DeviceReservation]:
        """
        Get reservations with optional filters.

        Args:
            device_id: Filter by device ID
            user_id: Filter by user ID
            status: Filter by status
            start_date: Filter reservations starting after this date
            end_date: Filter reservations ending before this date
            db: Optional database session

        Returns:
            List of matching reservations
        """
        async def _get(session: AsyncSession):
            query = select(DeviceReservation)

            conditions = []
            if device_id:
                conditions.append(DeviceReservation.device_id == device_id)
            if user_id:
                conditions.append(DeviceReservation.user_id == user_id)
            if status:
                conditions.append(DeviceReservation.status == ModelReservationStatus(status.value))
            if start_date:
                conditions.append(DeviceReservation.start_time >= start_date)
            if end_date:
                conditions.append(DeviceReservation.end_time <= end_date)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.order_by(DeviceReservation.start_time.asc())
            result = await session.execute(query)
            return list(result.scalars().all())

        if db:
            return await _get(db)
        else:
            async with AsyncSessionLocal() as session:
                return await _get(session)

    async def get_reservation(
        self,
        reservation_id: str,
        db: Optional[AsyncSession] = None
    ) -> Optional[DeviceReservation]:
        """
        Get a specific reservation by ID.

        Args:
            reservation_id: Reservation ID
            db: Optional database session

        Returns:
            Reservation or None if not found
        """
        async def _get(session: AsyncSession):
            result = await session.execute(
                select(DeviceReservation).where(
                    DeviceReservation.id == reservation_id
                )
            )
            return result.scalar_one_or_none()

        if db:
            return await _get(db)
        else:
            async with AsyncSessionLocal() as session:
                return await _get(session)

    async def _check_conflicts(
        self,
        session: AsyncSession,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
        exclude_reservation_id: Optional[str] = None
    ) -> List[DeviceReservation]:
        """
        Check for reservation conflicts.

        A conflict occurs when:
        - Same device
        - Overlapping time range
        - Neither reservation is cancelled

        Args:
            session: Database session
            device_id: Device ID to check
            start_time: Proposed start time
            end_time: Proposed end time
            exclude_reservation_id: Optional reservation ID to exclude from check

        Returns:
            List of conflicting reservations
        """
        # Query for overlapping reservations
        # Two time ranges overlap if: start1 < end2 AND start2 < end1
        conditions = [
            DeviceReservation.device_id == device_id,
            DeviceReservation.status != ModelReservationStatus.CANCELLED,
            DeviceReservation.start_time < end_time,
            DeviceReservation.end_time > start_time
        ]

        if exclude_reservation_id:
            conditions.append(
                DeviceReservation.id != exclude_reservation_id
            )

        query = select(DeviceReservation).where(and_(*conditions))
        result = await session.execute(query)
        return list(result.scalars().all())

    async def update_reservation(
        self,
        reservation_id: str,
        update_data: ReservationUpdate,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> Optional[DeviceReservation]:
        """
        Update a reservation.

        Args:
            reservation_id: ID of reservation to update
            update_data: Update data
            user_id: Optional user ID for authorization check
            db: Optional database session

        Returns:
            Updated reservation or None if not found
        """
        async def _update(session: AsyncSession):
            result = await session.execute(
                select(DeviceReservation).where(
                    DeviceReservation.id == reservation_id
                )
            )
            reservation = result.scalar_one_or_none()

            if not reservation:
                return None

            # Check authorization if user_id provided
            if user_id and reservation.user_id != user_id:
                raise ValueError("Not authorized to update this reservation")

            # Can only update pending reservations
            if reservation.status != ModelReservationStatus.PENDING:
                raise ValueError(
                    f"Cannot update reservation with status {reservation.status}"
                )

            # Update fields
            new_start = update_data.start_time or reservation.start_time
            new_end = update_data.end_time or reservation.end_time

            # Check for conflicts if time changed
            if update_data.start_time or update_data.end_time:
                conflicts = await self._check_conflicts(
                    session,
                    reservation.device_id,
                    new_start,
                    new_end,
                    exclude_reservation_id=reservation_id
                )
                if conflicts:
                    raise ValueError(
                        f"Updated time conflicts with existing reservations"
                    )

            if update_data.start_time:
                reservation.start_time = update_data.start_time
            if update_data.end_time:
                reservation.end_time = update_data.end_time
            if update_data.purpose is not None:
                reservation.purpose = update_data.purpose

            await session.flush()
            await session.refresh(reservation)
            return reservation

        if db:
            return await _update(db)
        else:
            async with AsyncSessionLocal() as session:
                return await _update(session)

    async def renew_reservation(
        self,
        reservation_id: str,
        extension_minutes: int = 60,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> Optional[DeviceReservation]:
        """
        Renew/extend a reservation.

        Args:
            reservation_id: ID of reservation to renew
            extension_minutes: Extension duration in minutes (default 60, max 60)
            user_id: Optional user ID for authorization check
            db: Optional database session

        Returns:
            Updated reservation or None if not found

        Raises:
            ValueError: If renewal is not allowed or conflicts exist
        """
        # Cap extension at max allowed
        extension_minutes = min(extension_minutes, MAX_EXTENSION_HOURS * 60)

        async def _renew(session: AsyncSession):
            result = await session.execute(
                select(DeviceReservation).where(
                    DeviceReservation.id == reservation_id
                )
            )
            reservation = result.scalar_one_or_none()

            if not reservation:
                return None

            # Check authorization if user_id provided
            if user_id and reservation.user_id != user_id:
                raise ValueError("Not authorized to renew this reservation")

            # Can only renew active reservations
            if reservation.status != ModelReservationStatus.ACTIVE:
                raise ValueError(
                    f"Cannot renew reservation with status {reservation.status}"
                )

            # Calculate new end time
            new_end_time = reservation.end_time + timedelta(minutes=extension_minutes)

            # Check for conflicts with the extended time
            conflicts = await self._check_conflicts(
                session,
                reservation.device_id,
                reservation.end_time,  # Start checking from current end time
                new_end_time,
                exclude_reservation_id=reservation_id
            )

            if conflicts:
                raise ValueError(
                    "Cannot extend reservation: conflicts with existing reservations"
                )

            # Extend the reservation
            reservation.end_time = new_end_time
            logger.info(
                f"Extended reservation {reservation_id} by {extension_minutes} minutes"
            )

            await session.flush()
            await session.refresh(reservation)
            return reservation

        if db:
            return await _renew(db)
        else:
            async with AsyncSessionLocal() as session:
                return await _renew(session)

    async def get_queue_position(
        self,
        device_id: str,
        reservation_id: str,
        db: Optional[AsyncSession] = None
    ) -> int:
        """
        Get the queue position for a pending reservation.

        Args:
            device_id: Device ID
            reservation_id: Reservation ID
            db: Optional database session

        Returns:
            Queue position (1-based), 0 if not in queue
        """
        async def _get_position(session: AsyncSession):
            # Get all pending reservations for this device, ordered by start time
            result = await session.execute(
                select(DeviceReservation)
                .where(
                    and_(
                        DeviceReservation.device_id == device_id,
                        DeviceReservation.status == ModelReservationStatus.PENDING
                    )
                )
                .order_by(DeviceReservation.start_time.asc())
            )
            reservations = list(result.scalars().all())

            # Find position
            for i, res in enumerate(reservations, 1):
                if res.id == reservation_id:
                    return i
            return 0

        if db:
            return await _get_position(db)
        else:
            async with AsyncSessionLocal() as session:
                return await _get_position(session)


# Singleton instance
reservation_service = ReservationService()
