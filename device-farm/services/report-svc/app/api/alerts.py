# Alert API Routes
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from datetime import datetime
import logging

from app.services.alert import alert_service
from app.models.alert import (
    AlertRule,
    Alert,
    AlertCreate,
    AlertUpdate,
    AlertHistory,
    AlertStatus,
    AlertType,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# === Alert Rules ===

@router.post("/rules", response_model=AlertRule)
async def create_alert_rule(rule: AlertCreate):
    """Create a new alert rule"""
    return alert_service.create_rule(rule)


@router.get("/rules", response_model=List[AlertRule])
async def list_alert_rules(
    enabled_only: bool = Query(False, description="Only return enabled rules"),
):
    """List all alert rules"""
    return alert_service.list_rules(enabled_only=enabled_only)


@router.get("/rules/{rule_id}", response_model=AlertRule)
async def get_alert_rule(rule_id: str):
    """Get a specific alert rule"""
    rule = alert_service.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return rule


@router.put("/rules/{rule_id}", response_model=AlertRule)
async def update_alert_rule(rule_id: str, update: AlertUpdate):
    """Update an alert rule"""
    rule = alert_service.update_rule(rule_id, update)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return rule


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    """Delete an alert rule"""
    if not alert_service.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return {"message": "Alert rule deleted", "rule_id": rule_id}


@router.post("/rules/{rule_id}/enable")
async def enable_alert_rule(rule_id: str):
    """Enable an alert rule"""
    rule = alert_service.update_rule(rule_id, AlertUpdate(enabled=True))
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return {"message": "Alert rule enabled", "rule_id": rule_id}


@router.post("/rules/{rule_id}/disable")
async def disable_alert_rule(rule_id: str):
    """Disable an alert rule"""
    rule = alert_service.update_rule(rule_id, AlertUpdate(enabled=False))
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return {"message": "Alert rule disabled", "rule_id": rule_id}


# === Alerts ===

@router.post("/trigger")
async def trigger_alert(
    rule_id: str,
    title: str,
    message: str,
    device_id: Optional[str] = None,
    task_id: Optional[str] = None,
):
    """Manually trigger an alert"""
    alert = alert_service.trigger_alert(
        rule_id=rule_id,
        title=title,
        message=message,
        device_id=device_id,
        task_id=task_id,
    )
    if not alert:
        raise HTTPException(
            status_code=400,
            detail="Failed to trigger alert (rule not found or in cooldown)"
        )
    return alert


@router.get("", response_model=List[Alert])
async def list_alerts(
    status: Optional[AlertStatus] = Query(None, description="Filter by status"),
    alert_type: Optional[AlertType] = Query(None, description="Filter by type"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
):
    """List alerts with optional filtering"""
    return alert_service.list_alerts(
        status=status,
        alert_type=alert_type,
        limit=limit,
    )


@router.get("/{alert_id}", response_model=Alert)
async def get_alert(alert_id: str):
    """Get a specific alert"""
    alert = alert_service.list_alerts()
    for a in alert:
        if a.id == alert_id:
            return a
    raise HTTPException(status_code=404, detail="Alert not found")


@router.post("/{alert_id}/acknowledge", response_model=Alert)
async def acknowledge_alert(alert_id: str, user_id: str):
    """Acknowledge an alert"""
    alert = alert_service.acknowledge_alert(alert_id, user_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/{alert_id}/resolve", response_model=Alert)
async def resolve_alert(alert_id: str, user_id: Optional[str] = None):
    """Resolve an alert"""
    alert = alert_service.resolve_alert(alert_id, user_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


# === Alert History ===

@router.get("/history/all", response_model=List[AlertHistory])
async def get_alert_history(
    alert_id: Optional[str] = Query(None, description="Filter by alert ID"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
):
    """Get alert history"""
    return alert_service.get_history(alert_id=alert_id, limit=limit)
