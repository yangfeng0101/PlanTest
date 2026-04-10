# Aggregator Service for Parallel Execution Reports
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import json

from pydantic import BaseModel, Field

from app.config import settings
from app.models.models import (
    Report,
    ReportStatus,
    ReportFormat,
    TestSummary,
    TestCaseResult,
    ReportDetail,
)


class ParallelExecutionReport(BaseModel):
    """Report model for parallel execution"""
    parallel_task_id: str
    script_id: str
    execution_time: datetime = Field(default_factory=datetime.utcnow)

    # Device summary
    total_devices: int = 0
    successful_devices: int = 0
    failed_devices: int = 0

    # Test summary
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0

    # Duration
    total_duration: float = 0.0
    avg_duration: float = 0.0

    # Device details
    device_results: List[Dict[str, Any]] = Field(default_factory=list)
    failed_devices: List[Dict[str, Any]] = Field(default_factory=list)


class AggregatorService:
    """Service for aggregating and generating reports from parallel execution"""

    def __init__(self):
        self.reports_dir = settings.REPORT_STORAGE_PATH
        os.makedirs(self.reports_dir, exist_ok=True)

    async def aggregate_parallel_results(
        self,
        parallel_task_id: str,
        test_svc_url: str = None
    ) -> ParallelExecutionReport:
        """Aggregate results from test-svc for a parallel task

        Args:
            parallel_task_id: ID of the parallel task
            test_svc_url: URL of test-svc (optional, uses config default)

        Returns:
            Aggregated parallel execution report
        """
        import httpx

        base_url = test_svc_url or settings.TEST_SERVICE_URL or "http://localhost:8001"

        async with httpx.AsyncClient() as client:
            # Get parallel task summary
            summary_resp = await client.get(
                f"{base_url}/api/v1/tasks/parallel/{parallel_task_id}/summary",
                timeout=30.0
            )

            if summary_resp.status_code != 200:
                raise ValueError(f"Failed to get parallel task: {summary_resp.text}")

            summary = summary_resp.json()

            # Get aggregated results
            aggregate_resp = await client.post(
                f"{base_url}/api/v1/tasks/parallel/{parallel_task_id}/aggregate",
                timeout=60.0
            )

            aggregated = None
            if aggregate_resp.status_code == 200:
                aggregated = aggregate_resp.json()

        # Build parallel execution report
        report = ParallelExecutionReport(
            parallel_task_id=parallel_task_id,
            script_id=summary.get("script_id", ""),
            total_devices=summary.get("total_devices", 0),
            successful_devices=summary.get("completed_devices", 0),
            failed_devices=summary.get("failed_devices", 0),
            total_tests=summary.get("total_tests", 0),
            passed_tests=summary.get("passed_tests", 0),
            failed_tests=summary.get("failed_tests", 0),
            skipped_tests=summary.get("skipped_tests", 0),
            total_duration=summary.get("total_duration", 0.0),
            avg_duration=summary.get("avg_device_duration", 0.0),
        )

        # Add device details if available
        if aggregated and "device_results" in aggregated:
            report.device_results = aggregated["device_results"]

            # Extract failed devices
            report.failed_devices = [
                dr for dr in aggregated["device_results"]
                if dr.get("status") != "success"
            ]

        return report

    def generate_html_report(
        self,
        parallel_report: ParallelExecutionReport
    ) -> str:
        """Generate HTML report for parallel execution

        Args:
            parallel_report: Parallel execution report data

        Returns:
            HTML content
        """
        device_success_rate = 0.0
        if parallel_report.total_devices > 0:
            device_success_rate = (
                parallel_report.successful_devices / parallel_report.total_devices
            ) * 100

        test_success_rate = 0.0
        if parallel_report.total_tests > 0:
            test_success_rate = (
                parallel_report.passed_tests / parallel_report.total_tests
            ) * 100

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>并行执行报告 - {parallel_report.parallel_task_id}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #1890ff; padding-bottom: 15px; margin-top: 0; }}
        h2 {{ color: #333; margin-top: 30px; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .summary-card {{ background: #fafafa; padding: 20px; border-radius: 8px; text-align: center; }}
        .summary-card h3 {{ margin: 0 0 10px; color: #666; font-size: 14px; font-weight: normal; }}
        .summary-card .value {{ font-size: 28px; font-weight: bold; color: #333; }}
        .summary-card .value.success {{ color: #52c41a; }}
        .summary-card .value.failed {{ color: #ff4d4f; }}
        .summary-card .value.info {{ color: #1890ff; }}
        .section {{ margin: 30px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e8e8e8; }}
        th {{ background: #fafafa; font-weight: 500; }}
        .status-success {{ color: #52c41a; font-weight: 500; }}
        .status-failed {{ color: #ff4d4f; font-weight: 500; }}
        .meta {{ color: #666; font-size: 14px; margin-bottom: 20px; }}
        .progress-bar {{ height: 8px; background: #e8e8e8; border-radius: 4px; overflow: hidden; margin: 10px 0; }}
        .progress-bar .fill {{ height: 100%; background: #52c41a; }}
        .progress-bar .fill.partial {{ background: linear-gradient(90deg, #52c41a 70%, #ff4d4f 70%); }}
    </style>
</head>
<body>
    <div class="container">
        <h1>并行执行报告</h1>
        <div class="meta">
            <p><strong>任务ID:</strong> {parallel_report.parallel_task_id}</p>
            <p><strong>脚本ID:</strong> {parallel_report.script_id}</p>
            <p><strong>执行时间:</strong> {parallel_report.execution_time.strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>

        <div class="section">
            <h2>设备执行概览</h2>
            <div class="summary-grid">
                <div class="summary-card">
                    <h3>总设备数</h3>
                    <div class="value info">{parallel_report.total_devices}</div>
                </div>
                <div class="summary-card">
                    <h3>成功设备</h3>
                    <div class="value success">{parallel_report.successful_devices}</div>
                </div>
                <div class="summary-card">
                    <h3>失败设备</h3>
                    <div class="value failed">{parallel_report.failed_devices}</div>
                </div>
                <div class="summary-card">
                    <h3>设备成功率</h3>
                    <div class="value {('success' if device_success_rate == 100 else 'failed' if device_success_rate < 50 else '')}">{device_success_rate:.1f}%</div>
                </div>
            </div>
            <div class="progress-bar">
                <div class="fill {'partial' if parallel_report.failed_devices > 0 else ''}" style="width: {device_success_rate}%"></div>
            </div>
        </div>

        <div class="section">
            <h2>测试用例统计</h2>
            <div class="summary-grid">
                <div class="summary-card">
                    <h3>总用例数</h3>
                    <div class="value info">{parallel_report.total_tests}</div>
                </div>
                <div class="summary-card">
                    <h3>通过用例</h3>
                    <div class="value success">{parallel_report.passed_tests}</div>
                </div>
                <div class="summary-card">
                    <h3>失败用例</h3>
                    <div class="value failed">{parallel_report.failed_tests}</div>
                </div>
                <div class="summary-card">
                    <h3>跳过用例</h3>
                    <div class="value">{parallel_report.skipped_tests}</div>
                </div>
                <div class="summary-card">
                    <h3>用例通过率</h3>
                    <div class="value {('success' if test_success_rate == 100 else 'failed' if test_success_rate < 50 else '')}">{test_success_rate:.1f}%</div>
                </div>
                <div class="summary-card">
                    <h3>平均执行时长</h3>
                    <div class="value">{parallel_report.avg_duration:.2f}s</div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>设备执行详情</h2>
            <table>
                <thead>
                    <tr>
                        <th>设备ID</th>
                        <th>状态</th>
                        <th>总用例</th>
                        <th>通过</th>
                        <th>失败</th>
                        <th>执行时长</th>
                    </tr>
                </thead>
                <tbody>
"""

        for device in parallel_report.device_results:
            status_class = "status-success" if device.get("status") == "success" else "status-failed"
            status_text = "成功" if device.get("status") == "success" else "失败"
            html += f"""
                    <tr>
                        <td>{device.get('device_id', 'N/A')}</td>
                        <td class="{status_class}">{status_text}</td>
                        <td>{device.get('total_tests', 0)}</td>
                        <td>{device.get('passed_tests', 0)}</td>
                        <td>{device.get('failed_tests', 0)}</td>
                        <td>{device.get('duration', 0):.2f}s</td>
                    </tr>
"""

        html += """
                </tbody>
            </table>
        </div>
"""

        # Add failed devices section if any
        if parallel_report.failed_devices:
            html += """
        <div class="section">
            <h2>失败设备详情</h2>
            <table>
                <thead>
                    <tr>
                        <th>设备ID</th>
                        <th>错误信息</th>
                        <th>执行时长</th>
                    </tr>
                </thead>
                <tbody>
"""
            for device in parallel_report.failed_devices:
                html += f"""
                    <tr>
                        <td>{device.get('device_id', 'N/A')}</td>
                        <td>{device.get('error', '未知错误')}</td>
                        <td>{device.get('duration', 0):.2f}s</td>
                    </tr>
"""
            html += """
                </tbody>
            </table>
        </div>
"""

        html += """
    </div>
</body>
</html>
"""
        return html

    def generate_json_report(
        self,
        parallel_report: ParallelExecutionReport
    ) -> str:
        """Generate JSON report for parallel execution

        Args:
            parallel_report: Parallel execution report data

        Returns:
            JSON content
        """
        return json.dumps(parallel_report.model_dump(), default=str, indent=2)

    def save_report(
        self,
        parallel_task_id: str,
        content: str,
        format: ReportFormat = ReportFormat.HTML
    ) -> str:
        """Save report to file

        Args:
            parallel_task_id: Parallel task ID
            content: Report content
            format: Report format

        Returns:
            File path
        """
        file_name = f"parallel_{parallel_task_id}.{format.value}"
        file_path = os.path.join(self.reports_dir, file_name)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return file_path

    async def create_parallel_report(
        self,
        parallel_task_id: str,
        format: ReportFormat = ReportFormat.HTML
    ) -> Dict[str, Any]:
        """Create a complete parallel execution report

        Args:
            parallel_task_id: Parallel task ID
            format: Report format

        Returns:
            Report metadata with file path
        """
        # Aggregate results
        parallel_report = await self.aggregate_parallel_results(parallel_task_id)

        # Generate content
        if format == ReportFormat.HTML:
            content = self.generate_html_report(parallel_report)
        elif format == ReportFormat.JSON:
            content = self.generate_json_report(parallel_report)
        else:
            raise ValueError(f"Unsupported format: {format}")

        # Save to file
        file_path = self.save_report(parallel_task_id, content, format)

        return {
            "parallel_task_id": parallel_task_id,
            "file_path": file_path,
            "format": format.value,
            "file_size": len(content),
            "created_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_devices": parallel_report.total_devices,
                "successful_devices": parallel_report.successful_devices,
                "failed_devices": parallel_report.failed_devices,
                "total_tests": parallel_report.total_tests,
                "passed_tests": parallel_report.passed_tests,
                "failed_tests": parallel_report.failed_tests,
            }
        }

    def get_report_file(
        self,
        parallel_task_id: str,
        format: ReportFormat = ReportFormat.HTML
    ) -> Optional[str]:
        """Get report file path if exists

        Args:
            parallel_task_id: Parallel task ID
            format: Report format

        Returns:
            File path or None
        """
        file_name = f"parallel_{parallel_task_id}.{format.value}"
        file_path = os.path.join(self.reports_dir, file_name)

        if os.path.exists(file_path):
            return file_path

        return None


# Global instance
aggregator_service = AggregatorService()
