# Reports API Router
import asyncio
import json
import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse

from app.models.models import (
    Report,
    ReportCreate,
    ReportListResponse,
    ReportStatus,
    ReportFormat,
    ReportDownloadResponse,
)
from app.services.generator import report_generator
from app.services.storage import storage_service
from app.services.aggregator import aggregator_service
from app.middleware.auth import get_current_user
from app.config import settings

router = APIRouter()

# In-memory storage (replace with database in production)
_reports_db: dict = {}


def _save_report(report: Report):
    """Save report to storage"""
    _reports_db[report.id] = report

    # Save metadata to file
    os.makedirs(settings.REPORT_STORAGE_PATH, exist_ok=True)
    meta_path = os.path.join(settings.REPORT_STORAGE_PATH, f"{report.id}.json")
    with open(meta_path, "w") as f:
        json.dump(report.model_dump(), f, default=str)


def _get_report(report_id: str) -> Optional[Report]:
    """Get report from storage"""
    if report_id in _reports_db:
        return _reports_db[report_id]

    # Try to load from file
    meta_path = os.path.join(settings.REPORT_STORAGE_PATH, f"{report_id}.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r") as f:
            data = json.load(f)

        # Parse datetime strings
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        report = Report(**data)
        _reports_db[report_id] = report
        return report

    return None


def _get_content_type(format: ReportFormat) -> str:
    """Get content type for report format"""
    content_types = {
        ReportFormat.HTML: "text/html",
        ReportFormat.JSON: "application/json",
        ReportFormat.PDF: "application/pdf",
        ReportFormat.MARKDOWN: "text/markdown",
    }
    return content_types.get(format, "application/octet-stream")


async def fetch_task_result(task_id: str) -> Optional[dict]:
    """Fetch task result from test service"""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.TEST_SERVICE_URL}/api/v1/tasks/{task_id}",
                timeout=10.0
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"Error fetching task result: {e}")

    return None


@router.get("", response_model=ReportListResponse)
async def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[ReportStatus] = None,
    task_id: Optional[str] = None,
    search: Optional[str] = None,
):
    """List all reports with pagination"""
    reports = list(_reports_db.values())

    # Apply filters
    if status:
        reports = [r for r in reports if r.status == status]

    if task_id:
        reports = [r for r in reports if r.task_id == task_id]

    if search:
        search_lower = search.lower()
        reports = [
            r for r in reports
            if search_lower in r.task_id.lower()
            or (r.title and search_lower in r.title.lower())
        ]

    # Sort by created_at descending
    reports.sort(key=lambda x: x.created_at, reverse=True)

    # Paginate
    total = len(reports)
    start = (page - 1) * page_size
    end = start + page_size
    items = reports[start:end]

    return ReportListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 1
    )


@router.post("", response_model=Report, status_code=status.HTTP_201_CREATED)
async def create_report(report: ReportCreate):
    """Create a new report from task result"""
    new_report = Report(**report.model_dump())

    # Fetch task result
    task_result = await fetch_task_result(report.task_id)

    if task_result:
        # Get execution result from task
        execution_result = task_result.get("result", {})

        # Generate report
        report_generator.generate_report(
            new_report,
            execution_result,
            new_report.format
        )
    else:
        # Generate report with placeholder data
        report_generator.generate_report(
            new_report,
            {
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 0,
                "skipped_tests": 0,
                "duration": 0.0,
                "errors": ["Task result not found"],
                "logs": [],
            },
            new_report.format
        )

    _save_report(new_report)
    return new_report


@router.get("/{report_id}", response_model=Report)
async def get_report(report_id: str):
    """Get report by ID"""
    report = _get_report(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found"
        )

    return report


@router.get("/{report_id}/download")
async def download_report(report_id: str):
    """Download report file"""
    report = _get_report(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found"
        )

    if report.status != ReportStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report is not ready for download. Status: {report.status}"
        )

    # Try to get from MinIO
    if report.file_path and report.file_path.startswith("reports/"):
        content = storage_service.download_data(report.file_path)
        if content:
            content_type = _get_content_type(report.format)
            file_name = f"report_{report_id}.{report.format.value}"
            return Response(
                content=content,
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{file_name}"'
                }
            )

    # Try local file system
    if report.file_path and os.path.exists(report.file_path):
        with open(report.file_path, "r") as f:
            content = f.read()

        content_type = _get_content_type(report.format)
        file_name = f"report_{report_id}.{report.format.value}"
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}"'
            }
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Report file not found"
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(report_id: str):
    """Delete a report"""
    report = _get_report(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found"
        )

    # Delete from storage
    if report.file_path:
        if report.file_path.startswith("reports/"):
            storage_service.delete_file(report.file_path)
        elif os.path.exists(report.file_path):
            os.remove(report.file_path)

    # Delete metadata
    meta_path = os.path.join(settings.REPORT_STORAGE_PATH, f"{report_id}.json")
    if os.path.exists(meta_path):
        os.remove(meta_path)

    # Remove from memory
    if report_id in _reports_db:
        del _reports_db[report_id]

    return None


@router.get("/{report_id}/preview", response_class=Response)
async def preview_report(report_id: str):
    """Preview HTML report in browser"""
    report = _get_report(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found"
        )

    if report.format != ReportFormat.HTML:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Preview only available for HTML reports"
        )

    if report.status != ReportStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report is not ready. Status: {report.status}"
        )

    # Try to get content
    content = None

    if report.file_path and report.file_path.startswith("reports/"):
        content = storage_service.download_data(report.file_path)
        if content:
            content = content.decode("utf-8")
    elif report.file_path and os.path.exists(report.file_path):
        with open(report.file_path, "r") as f:
            content = f.read()

    if content:
        return Response(content=content, media_type="text/html")

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Report file not found"
    )


# ============ Parallel Execution Report Endpoints ============

@router.post("/parallel/{parallel_task_id}", status_code=status.HTTP_201_CREATED)
async def create_parallel_report(
    parallel_task_id: str,
    format: ReportFormat = Query(ReportFormat.HTML),
):
    """Create a report for parallel execution

    This endpoint aggregates results from a parallel task execution
    and generates a comprehensive report.

    Args:
        parallel_task_id: ID of the parallel task
        format: Report format (html or json)

    Returns:
        Report metadata with file path
    """
    try:
        result = await aggregator_service.create_parallel_report(
            parallel_task_id,
            format=format
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create report: {str(e)}"
        )


@router.get("/parallel/{parallel_task_id}/download")
async def get_parallel_report(
    parallel_task_id: str,
    format: ReportFormat = Query(ReportFormat.HTML),
):
    """Get or download parallel execution report

    If the report exists, returns the file content.
    If not, generates it on-the-fly.

    Args:
        parallel_task_id: ID of the parallel task
        format: Report format (html or json)

    Returns:
        Report file content
    """
    # Check if report already exists
    file_path = aggregator_service.get_report_file(parallel_task_id, format)

    if not file_path:
        # Generate report on-the-fly
        try:
            result = await aggregator_service.create_parallel_report(
                parallel_task_id,
                format=format
            )
            file_path = result.get("file_path")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate report: {str(e)}"
            )

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report for parallel task {parallel_task_id} not found"
        )

    # Read and return content
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    content_type = _get_content_type(format)
    file_name = f"parallel_{parallel_task_id}.{format.value}"

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"'
        }
    )


@router.get("/parallel/{parallel_task_id}/preview", response_class=Response)
async def preview_parallel_report(parallel_task_id: str):
    """Preview parallel execution report in browser

    Args:
        parallel_task_id: ID of the parallel task

    Returns:
        HTML content for browser preview
    """
    # Check if report exists
    file_path = aggregator_service.get_report_file(parallel_task_id, ReportFormat.HTML)

    if not file_path:
        # Generate report on-the-fly
        try:
            result = await aggregator_service.create_parallel_report(
                parallel_task_id,
                format=ReportFormat.HTML
            )
            file_path = result.get("file_path")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate report: {str(e)}"
            )

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report for parallel task {parallel_task_id} not found"
        )

    # Read and return HTML content
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    return Response(content=content, media_type="text/html")
