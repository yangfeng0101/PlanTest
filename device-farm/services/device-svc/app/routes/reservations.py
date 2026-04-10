# Reservation Routes
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime
import logging

from app.models.reservation_schemas import (
    ReservationCreate,
    ReservationUpdate,
    ReservationResponse,
    ReservationListResponse,
    ReservationStatus,
    ReservationRenewRequest,
    QueuePositionResponse,
)
from app.services.reservation_service import reservation_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _reservation_to_response(reservation) -> ReservationResponse:
    """Convert reservation model to response schema"""
    return ReservationResponse(
        id=reservation.id,
        device_id=reservation.device_id,
        user_id=reservation.user_id,
        start_time=reservation.start_time,
        end_time=reservation.end_time,
        status=ReservationStatus(reservation.status.value),
        purpose=reservation.purpose,
        created_at=reservation.created_at,
        updated_at=reservation.updated_at
    )


@router.get("", response_model=ReservationListResponse)
async def list_reservations(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    status: Optional[ReservationStatus] = Query(None, description="Filter by status"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
):
    """
    Get list of reservations with optional filters.
    """
    reservations = await reservation_service.get_reservations(
        device_id=device_id,
        user_id=user_id,
        status=status,
        start_date=start_date,
        end_date=end_date
    )
    return ReservationListResponse(
        reservations=[_reservation_to_response(r) for r in reservations],
        total=len(reservations)
    )


@router.get("/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(reservation_id: str):
    """
    Get a specific reservation by ID.
    """
    reservation = await reservation_service.get_reservation(reservation_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return _reservation_to_response(reservation)


@router.patch("/{reservation_id}", response_model=ReservationResponse)
async def update_reservation(
    reservation_id: str,
    update: ReservationUpdate
):
    """
    Update a reservation.

    Only pending reservations can be updated.
    If the time is changed, it will be checked for conflicts.
    """
    try:
        reservation = await reservation_service.update_reservation(
            reservation_id,
            update
        )
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return _reservation_to_response(reservation)
    except ValueError as e:
        if "conflicts" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{reservation_id}")
async def cancel_reservation(reservation_id: str):
    """
    Cancel a reservation.

    Only pending or active reservations can be cancelled.
    """
    try:
        reservation = await reservation_service.cancel_reservation(reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return {"message": "Reservation cancelled", "reservation_id": reservation_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{reservation_id}/renew", response_model=ReservationResponse)
async def renew_reservation(
    reservation_id: str,
    renew_request: ReservationRenewRequest = ReservationRenewRequest()
):
    """
    Renew/extend an active reservation.

    Maximum extension is 1 hour. Only active reservations can be renewed.
    """
    try:
        reservation = await reservation_service.renew_reservation(
            reservation_id,
            extension_minutes=renew_request.extension_minutes
        )
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return _reservation_to_response(reservation)
    except ValueError as e:
        if "conflicts" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{reservation_id}/queue-position", response_model=QueuePositionResponse)
async def get_queue_position(reservation_id: str):
    """
    Get the queue position for a pending reservation.

    Returns position 0 if reservation is not in queue (not pending or not found).
    """
    reservation = await reservation_service.get_reservation(reservation_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    position = await reservation_service.get_queue_position(
        reservation.device_id,
        reservation_id
    )

    # Get total in queue
    all_pending = await reservation_service.get_reservations(
        device_id=reservation.device_id,
        status=ReservationStatus.PENDING
    )

    return QueuePositionResponse(
        reservation_id=reservation_id,
        device_id=reservation.device_id,
        position=position,
        total_in_queue=len(all_pending)
    )
