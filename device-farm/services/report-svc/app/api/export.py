# Export API Routes
from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import Response
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import logging
import json

from app.services.export import export_service, ExportFormat
from app.services.statistics import statistics_service
from app.middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/csv")
async def export_to_csv(
    data: List[Dict[str, Any]],
    filename: str = Query("export.csv", description="Output filename"),
    current_user: dict = Depends(get_current_user),
):
    """Export data to CSV format"""
    if not data:
        raise HTTPException(status_code=400, detail="No data provided")

    csv_bytes = export_service.export_to_csv(data, filename)

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.post("/excel")
async def export_to_excel(
    data: List[Dict[str, Any]],
    sheet_name: str = Query("Data", description="Sheet name"),
    filename: str = Query("export.xlsx", description="Output filename"),
    current_user: dict = Depends(get_current_user),
):
    """Export data to Excel format"""
    if not data:
        raise HTTPException(status_code=400, detail="No data provided")

    excel_bytes = export_service.export_to_excel(data, sheet_name, filename)

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.post("/pdf")
async def export_to_pdf(
    title: str = Query("Report", description="Report title"),
    content: Dict[str, Any] = None,
    filename: str = Query("report.pdf", description="Output filename"),
    current_user: dict = Depends(get_current_user),
):
    """Export data to PDF format"""
    if not content:
        raise HTTPException(status_code=400, detail="No content provided")

    pdf_bytes = export_service.export_to_pdf(title, content, filename)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/statistics/csv")
async def export_statistics_csv(
    report_type: str = Query("daily", description="Report type: daily, weekly, monthly"),
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    current_user: dict = Depends(get_current_user),
):
    """Export statistics to CSV"""
    if report_type not in ["daily", "weekly", "monthly"]:
        raise HTTPException(
            status_code=400,
            detail="report_type must be 'daily', 'weekly', or 'monthly'"
        )

    report = statistics_service.generate_report(
        report_type=report_type,
        device_id=device_id,
    )

    # Convert to dict format for CSV
    device_usage = [
        {
            "device_id": d.device_id,
            "device_name": d.device_name,
            "total_usage_minutes": d.total_usage_minutes,
            "session_count": d.session_count,
            "average_session_minutes": d.average_session_minutes,
        }
        for d in report.device_usage
    ]

    task_stats = report.task_stats.model_dump() if report.task_stats else None

    usage_trend = [
        {
            "timestamp": p.timestamp.isoformat(),
            "value": p.value,
        }
        for p in report.usage_trend.data
    ] if report.usage_trend else []

    csv_bytes = export_service.export_statistics_to_csv(
        device_usage=device_usage,
        task_stats=task_stats,
        usage_trend=usage_trend,
    )

    filename = f"statistics_{report_type}_{datetime.utcnow().strftime('%Y%m%d')}.csv"

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/statistics/excel")
async def export_statistics_excel(
    report_type: str = Query("daily", description="Report type: daily, weekly, monthly"),
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    current_user: dict = Depends(get_current_user),
):
    """Export statistics to Excel"""
    if report_type not in ["daily", "weekly", "monthly"]:
        raise HTTPException(
            status_code=400,
            detail="report_type must be 'daily', 'weekly', or 'monthly'"
        )

    report = statistics_service.generate_report(
        report_type=report_type,
        device_id=device_id,
    )

    # Prepare data for Excel
    device_usage = [
        {
            "Device ID": d.device_id,
            "Device Name": d.device_name,
            "Total Usage (min)": d.total_usage_minutes,
            "Session Count": d.session_count,
            "Avg Session (min)": d.average_session_minutes,
        }
        for d in report.device_usage
    ]

    excel_bytes = export_service.export_to_excel(
        data=device_usage,
        sheet_name="Device Usage",
    )

    filename = f"statistics_{report_type}_{datetime.utcnow().strftime('%Y%m%d')}.xlsx"

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.post("/execution-logs/excel")
async def export_execution_logs_excel(
    logs: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
    filename: str = Query("execution_logs.xlsx", description="Output filename"),
    current_user: dict = Depends(get_current_user),
):
    """Export execution logs to Excel with summary"""
    if not logs:
        raise HTTPException(status_code=400, detail="No logs provided")

    excel_bytes = export_service.export_execution_logs_to_excel(
        logs=logs,
        summary=summary,
    )

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.post("/test-report/pdf")
async def export_test_report_pdf(
    report: Dict[str, Any],
    filename: str = Query("test_report.pdf", description="Output filename"),
    current_user: dict = Depends(get_current_user),
):
    """Export test report to PDF"""
    if not report:
        raise HTTPException(status_code=400, detail="No report provided")

    pdf_bytes = export_service.export_test_report_to_pdf(report)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.post("/batch")
async def batch_export(
    exports: List[Dict[str, Any]],
    current_user: dict = Depends(get_current_user),
):
    """
    Batch export multiple data sets

    Each export item should have:
    - type: export type (statistics, execution_logs, etc.)
    - data: the data to export
    - filename: output filename
    - format: csv, excel, or pdf
    """
    if not exports:
        raise HTTPException(status_code=400, detail="No exports provided")

    results = export_service.batch_export(exports)

    # Return as JSON with base64 encoded content
    import base64
    response = {}
    for filename, content in results.items():
        response[filename] = {
            "size": len(content),
            "content_base64": base64.b64encode(content).decode('utf-8') if content else None,
        }

    return response
