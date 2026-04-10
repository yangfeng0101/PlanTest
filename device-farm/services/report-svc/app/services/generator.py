# Report Generator Service
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings
from app.models.models import (
    Report,
    ReportDetail,
    TestSummary,
    TestCaseResult,
    ReportStatus,
    ReportFormat,
)
from app.services.storage import storage_service


class ReportGenerator:
    """Generate test reports in various formats"""

    def __init__(self):
        self.template_dir = os.path.join(
            os.path.dirname(__file__),
            "templates"
        )
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(["html", "xml"])
        ) if os.path.exists(self.template_dir) else None

    def generate_report(
        self,
        report: Report,
        execution_result: Dict[str, Any],
        format: ReportFormat = ReportFormat.HTML
    ) -> bool:
        """Generate report from execution result"""
        try:
            # Parse execution result into report detail
            detail = self._parse_execution_result(execution_result)
            report.detail = detail

            # Generate content based on format
            if format == ReportFormat.HTML:
                content = self._generate_html(report)
                content_type = "text/html"
            elif format == ReportFormat.JSON:
                content = self._generate_json(report)
                content_type = "application/json"
            elif format == ReportFormat.MARKDOWN:
                content = self._generate_markdown(report)
                content_type = "text/markdown"
            else:
                raise ValueError(f"Unsupported format: {format}")

            # Save to storage
            object_name = f"reports/{report.id}/report.{format.value}"
            if storage_service.upload_data(
                object_name,
                content.encode("utf-8"),
                content_type
            ):
                report.file_path = object_name
                report.file_size = len(content)
                report.status = ReportStatus.COMPLETED
                return True
            else:
                # Fallback to local file system
                return self._save_to_local(report, content, format)

        except Exception as e:
            print(f"Error generating report: {e}")
            report.status = ReportStatus.FAILED
            return False

    def _parse_execution_result(self, result: Dict[str, Any]) -> ReportDetail:
        """Parse execution result into report detail"""
        summary = TestSummary(
            total=result.get("total_tests", 0),
            passed=result.get("passed_tests", 0),
            failed=result.get("failed_tests", 0),
            skipped=result.get("skipped_tests", 0),
            duration=result.get("duration", 0.0),
        )

        # Calculate success rate
        if summary.total > 0:
            summary.success_rate = (summary.passed / summary.total) * 100

        # Parse test cases
        test_cases = []
        logs = result.get("logs", [])
        errors = result.get("errors", [])

        # Create test case results from logs
        for i, log in enumerate(logs):
            if isinstance(log, dict):
                test_cases.append(TestCaseResult(
                    name=log.get("test_name", f"Test {i + 1}"),
                    status=log.get("status", "passed"),
                    duration=log.get("duration", 0.0),
                    message=log.get("message"),
                    error=log.get("error"),
                    screenshots=log.get("screenshots", [])
                ))

        # If no test cases from logs, create summary test case
        if not test_cases:
            test_cases.append(TestCaseResult(
                name="Overall Test",
                status="passed" if summary.failed == 0 else "failed",
                duration=summary.duration,
                message=f"Total: {summary.total}, Passed: {summary.passed}, Failed: {summary.failed}",
                error=errors[0] if errors else None
            ))

        return ReportDetail(
            summary=summary,
            test_cases=test_cases,
            environment=result.get("environment", {}),
            execution_log=[str(log) for log in logs],
            artifacts=result.get("screenshots", []) + result.get("videos", [])
        )

    def _generate_html(self, report: Report) -> str:
        """Generate HTML report"""
        if self.env:
            template = self.env.get_template("report.html")
            return template.render(
                report=report,
                generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            )
        else:
            return self._generate_simple_html(report)

    def _generate_simple_html(self, report: Report) -> str:
        """Generate simple HTML without templates"""
        detail = report.detail
        summary = detail.summary if detail else TestSummary()

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Report - {report.title or report.task_id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
        .summary {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 15px; margin: 20px 0; }}
        .summary-card {{ background: #f9f9f9; padding: 20px; border-radius: 8px; text-align: center; }}
        .summary-card h3 {{ margin: 0; color: #666; font-size: 14px; }}
        .summary-card p {{ margin: 10px 0 0; font-size: 24px; font-weight: bold; }}
        .passed {{ color: #4CAF50; }}
        .failed {{ color: #f44336; }}
        .skipped {{ color: #FF9800; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f5f5f5; }}
        .status-passed {{ color: #4CAF50; font-weight: bold; }}
        .status-failed {{ color: #f44336; font-weight: bold; }}
        .status-skipped {{ color: #FF9800; font-weight: bold; }}
        .meta {{ color: #666; font-size: 14px; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Test Report</h1>
        <div class="meta">
            <p><strong>Task ID:</strong> {report.task_id}</p>
            <p><strong>Generated:</strong> {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}</p>
            <p><strong>Duration:</strong> {summary.duration:.2f}s</p>
        </div>
        <div class="summary">
            <div class="summary-card">
                <h3>Total</h3>
                <p>{summary.total}</p>
            </div>
            <div class="summary-card">
                <h3>Passed</h3>
                <p class="passed">{summary.passed}</p>
            </div>
            <div class="summary-card">
                <h3>Failed</h3>
                <p class="failed">{summary.failed}</p>
            </div>
            <div class="summary-card">
                <h3>Skipped</h3>
                <p class="skipped">{summary.skipped}</p>
            </div>
            <div class="summary-card">
                <h3>Success Rate</h3>
                <p>{summary.success_rate:.1f}%</p>
            </div>
        </div>
        <h2>Test Results</h2>
        <table>
            <thead>
                <tr>
                    <th>Test Name</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th>Message</th>
                </tr>
            </thead>
            <tbody>
"""
        if detail and detail.test_cases:
            for tc in detail.test_cases:
                status_class = f"status-{tc.status}"
                html += f"""
                <tr>
                    <td>{tc.name}</td>
                    <td class="{status_class}">{tc.status.upper()}</td>
                    <td>{tc.duration:.2f}s</td>
                    <td>{tc.message or tc.error or "-"}</td>
                </tr>
"""
        html += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""
        return html

    def _generate_json(self, report: Report) -> str:
        """Generate JSON report"""
        return json.dumps(report.model_dump(), default=str, indent=2)

    def _generate_markdown(self, report: Report) -> str:
        """Generate Markdown report"""
        detail = report.detail
        summary = detail.summary if detail else TestSummary()

        md = f"""# Test Report

**Task ID:** {report.task_id}
**Generated:** {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | {summary.total} |
| Passed | {summary.passed} |
| Failed | {summary.failed} |
| Skipped | {summary.skipped} |
| Success Rate | {summary.success_rate:.1f}% |
| Duration | {summary.duration:.2f}s |

## Test Results

| Test Name | Status | Duration | Message |
|-----------|--------|----------|---------|
"""
        if detail and detail.test_cases:
            for tc in detail.test_cases:
                md += f"| {tc.name} | {tc.status.upper()} | {tc.duration:.2f}s | {tc.message or tc.error or '-'} |\n"

        return md

    def _save_to_local(self, report: Report, content: str, format: ReportFormat) -> bool:
        """Save report to local file system"""
        try:
            os.makedirs(settings.REPORT_STORAGE_PATH, exist_ok=True)

            file_name = f"{report.id}.{format.value}"
            file_path = os.path.join(settings.REPORT_STORAGE_PATH, file_name)

            with open(file_path, "w") as f:
                f.write(content)

            report.file_path = file_path
            report.file_size = len(content)
            report.status = ReportStatus.COMPLETED
            return True

        except Exception as e:
            print(f"Error saving to local: {e}")
            report.status = ReportStatus.FAILED
            return False


# Global report generator instance
report_generator = ReportGenerator()
