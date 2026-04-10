# Test Generator Service for Device Farm
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import json

from app.config import settings

logger = logging.getLogger(__name__)


class TestType(str, Enum):
    """Test types"""
    UI_TEST = "ui_test"
    FUNCTIONAL_TEST = "functional_test"
    SMOKE_TEST = "smoke_test"
    REGRESSION_TEST = "regression_test"


class TestStepType(str, Enum):
    """Test step types"""
    CLICK = "click"
    INPUT = "input"
    SWIPE = "swipe"
    WAIT = "wait"
    ASSERT = "assert"
    SCREENSHOT = "screenshot"


@dataclass
class TestStep:
    """Single test step"""
    step_type: TestStepType
    description: str
    action: str
    target: Optional[str] = None  # Element description
    value: Optional[str] = None  # Input value, wait time, etc.
    timeout: Optional[int] = None  # Timeout in seconds
    assertions: Optional[List[str]] = None


@dataclass
class TestCase:
    """Generated test case"""
    id: str
    name: str
    description: str
    test_type: TestType
    steps: List[TestStep]
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    priority: int = 1  # 1=high, 2=medium, 3=low


@dataclass
class TestTemplate:
    """Test case template"""
    id: str
    name: str
    description: str
    test_type: TestType
    template_steps: List[Dict[str, Any]]  # Template with placeholders


class TestGeneratorService:
    """Service for generating test cases from natural language"""

    # Common action patterns
    ACTION_PATTERNS = {
        "click": ["点击", "点击一下", "按下", "click", "tap", "press"],
        "input": ["输入", "填写", "设置", "input", "enter", "fill", "type"],
        "swipe": ["滑动", "滑动到", "左滑", "右滑", "swipe", "scroll"],
        "wait": ["等待", "等待秒", "wait", "sleep"],
        "assert": ["验证", "检查", "确认", "assert", "verify", "check"],
    }

    # Built-in templates
    TEMPLATES = [
        TestTemplate(
            id="login_flow",
            name="登录流程",
            description="标准登录测试流程",
            test_type=TestType.FUNCTIONAL_TEST,
            template_steps=[
                {"step_type": "input", "target": "用户名输入框", "description": "输入用户名"},
                {"step_type": "input", "target": "密码输入框", "description": "输入密码"},
                {"step_type": "click", "target": "登录按钮", "description": "点击登录"},
                {"step_type": "assert", "value": "登录成功", "description": "验证登录成功"},
            ]
        ),
        TestTemplate(
            id="search_flow",
            name="搜索流程",
            description="标准搜索测试流程",
            test_type=TestType.FUNCTIONAL_TEST,
            template_steps=[
                {"step_type": "click", "target": "搜索框", "description": "点击搜索框"},
                {"step_type": "input", "target": "搜索输入框", "description": "输入搜索关键词"},
                {"step_type": "click", "target": "搜索按钮", "description": "执行搜索"},
                {"step_type": "assert", "value": "搜索结果", "description": "验证搜索结果"},
            ]
        ),
        TestTemplate(
            id="form_submit",
            name="表单提交",
            description="标准表单提交流程",
            test_type=TestType.FUNCTIONAL_TEST,
            template_steps=[
                {"step_type": "input", "target": "{field1}", "description": "填写第一个字段"},
                {"step_type": "input", "target": "{field2}", "description": "填写第二个字段"},
                {"step_type": "click", "target": "提交按钮", "description": "提交表单"},
                {"step_type": "assert", "value": "提交成功", "description": "验证提交成功"},
            ]
        ),
        TestTemplate(
            id="smoke_basic",
            name="基础冒烟测试",
            description="基础功能冒烟测试",
            test_type=TestType.SMOKE_TEST,
            template_steps=[
                {"step_type": "screenshot", "description": "初始截图"},
                {"step_type": "assert", "value": "页面加载", "description": "验证页面加载"},
            ]
        ),
    ]

    def __init__(self):
        self._templates = {t.id: t for t in self.TEMPLATES}

    def _parse_action(self, text: str) -> tuple:
        """Parse action from text"""
        text_lower = text.lower()

        for action_type, patterns in self.ACTION_PATTERNS.items():
            for pattern in patterns:
                if pattern in text_lower:
                    # Extract target and value
                    remaining = text_lower.replace(pattern, "").strip()
                    return action_type, remaining

        return None, text

    def _generate_step_from_description(self, description: str) -> Optional[TestStep]:
        """Generate a test step from natural language description"""
        action_type, remaining = self._parse_action(description)

        if action_type == "click":
            return TestStep(
                step_type=TestStepType.CLICK,
                description=description,
                action="click",
                target=remaining,
            )

        elif action_type == "input":
            # Try to extract value (e.g., "输入用户名 test@example.com")
            parts = remaining.split()
            target = parts[0] if parts else remaining
            value = parts[1] if len(parts) > 1 else None

            return TestStep(
                step_type=TestStepType.INPUT,
                description=description,
                action="input",
                target=target,
                value=value,
            )

        elif action_type == "swipe":
            direction = "left" if "左" in remaining else "right" if "右" in remaining else "up"
            return TestStep(
                step_type=TestStepType.SWIPE,
                description=description,
                action="swipe",
                value=direction,
            )

        elif action_type == "wait":
            # Extract seconds
            import re
            match = re.search(r'\d+', remaining)
            seconds = int(match.group()) if match else 2

            return TestStep(
                step_type=TestStepType.WAIT,
                description=description,
                action="wait",
                value=str(seconds),
                timeout=seconds,
            )

        elif action_type == "assert":
            return TestStep(
                step_type=TestStepType.ASSERT,
                description=description,
                action="assert",
                value=remaining,
                assertions=[remaining],
            )

        return None

    def generate_from_description(
        self,
        description: str,
        test_type: TestType = TestType.FUNCTIONAL_TEST,
        test_name: Optional[str] = None,
    ) -> TestCase:
        """
        Generate test case from natural language description

        Args:
            description: Natural language description of test scenario
            test_type: Type of test to generate
            test_name: Optional test name

        Returns:
            Generated TestCase
        """
        import uuid

        # Split description into sentences/steps
        import re
        sentences = re.split(r'[。\n;,；，]', description)
        sentences = [s.strip() for s in sentences if s.strip()]

        # Generate steps
        steps = []
        for sentence in sentences:
            step = self._generate_step_from_description(sentence)
            if step:
                steps.append(step)

        # Add screenshot at end
        steps.append(TestStep(
            step_type=TestStepType.SCREENSHOT,
            description="结果截图",
            action="screenshot",
        ))

        # Generate test case
        test_id = f"test_{uuid.uuid4().hex[:8]}"
        name = test_name or f"Generated Test - {test_id}"

        return TestCase(
            id=test_id,
            name=name,
            description=description,
            test_type=test_type,
            steps=steps,
            tags=["generated", "ai"],
        )

    def generate_from_template(
        self,
        template_id: str,
        parameters: Dict[str, str] = None,
        test_name: Optional[str] = None,
    ) -> Optional[TestCase]:
        """
        Generate test case from template

        Args:
            template_id: Template ID
            parameters: Parameters to fill in template
            test_name: Optional test name

        Returns:
            Generated TestCase or None if template not found
        """
        template = self._templates.get(template_id)
        if not template:
            return None

        import uuid
        params = parameters or {}

        # Generate steps from template
        steps = []
        for template_step in template.template_steps:
            step_type = TestStepType(template_step["step_type"])

            # Replace placeholders in target and value
            target = template_step.get("target", "")
            value = template_step.get("value", "")

            for key, val in params.items():
                target = target.replace(f"{{{key}}}", val)
                value = value.replace(f"{{{key}}}", val)

            step = TestStep(
                step_type=step_type,
                description=template_step.get("description", ""),
                action=step_type.value,
                target=target if target else None,
                value=value if value else None,
            )
            steps.append(step)

        # Generate test case
        test_id = f"test_{uuid.uuid4().hex[:8]}"
        name = test_name or f"{template.name} - {test_id}"

        return TestCase(
            id=test_id,
            name=name,
            description=template.description,
            test_type=template.test_type,
            steps=steps,
            tags=["template", template_id],
        )

    def get_templates(self) -> List[TestTemplate]:
        """Get all available templates"""
        return list(self._templates.values())

    def get_template(self, template_id: str) -> Optional[TestTemplate]:
        """Get a specific template"""
        return self._templates.get(template_id)

    def add_template(self, template: TestTemplate) -> None:
        """Add a custom template"""
        self._templates[template.id] = template

    def suggest_improvements(self, test_case: TestCase) -> List[Dict[str, Any]]:
        """
        Suggest improvements for a test case

        Args:
            test_case: Test case to analyze

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        # Check for missing assertions
        has_assert = any(s.step_type == TestStepType.ASSERT for s in test_case.steps)
        if not has_assert:
            suggestions.append({
                "type": "missing_assertion",
                "message": "测试用例缺少验证步骤，建议添加断言",
                "severity": "warning",
            })

        # Check for missing screenshot
        has_screenshot = any(s.step_type == TestStepType.SCREENSHOT for s in test_case.steps)
        if not has_screenshot:
            suggestions.append({
                "type": "missing_screenshot",
                "message": "建议添加截图步骤以便调试",
                "severity": "info",
            })

        # Check for missing wait after click
        for i, step in enumerate(test_case.steps[:-1]):
            if step.step_type == TestStepType.CLICK:
                next_step = test_case.steps[i + 1]
                if next_step.step_type not in [TestStepType.WAIT, TestStepType.SCREENSHOT]:
                    suggestions.append({
                        "type": "missing_wait",
                        "message": f"步骤 {i+1} 点击后建议添加等待步骤",
                        "severity": "info",
                        "step_index": i,
                    })

        # Check step count
        if len(test_case.steps) < 3:
            suggestions.append({
                "type": "too_short",
                "message": "测试用例步骤较少，建议完善测试流程",
                "severity": "info",
            })

        return suggestions

    def to_script(self, test_case: TestCase, format: str = "python") -> str:
        """
        Convert test case to executable script

        Args:
            test_case: Test case to convert
            format: Output format (python, json)

        Returns:
            Script string
        """
        if format == "json":
            return json.dumps({
                "id": test_case.id,
                "name": test_case.name,
                "description": test_case.description,
                "test_type": test_case.test_type.value,
                "steps": [
                    {
                        "step_type": s.step_type.value,
                        "description": s.description,
                        "action": s.action,
                        "target": s.target,
                        "value": s.value,
                        "timeout": s.timeout,
                    }
                    for s in test_case.steps
                ],
                "tags": test_case.tags,
            }, ensure_ascii=False, indent=2)

        # Python format
        lines = [
            f"# Test: {test_case.name}",
            f"# Description: {test_case.description}",
            f"# Type: {test_case.test_type.value}",
            "",
            "def test_case(driver):",
        ]

        for i, step in enumerate(test_case.steps, 1):
            lines.append(f"    # Step {i}: {step.description}")

            if step.step_type == TestStepType.CLICK:
                lines.append(f"    element = driver.find_element_by_description('{step.target}')")
                lines.append("    element.click()")

            elif step.step_type == TestStepType.INPUT:
                lines.append(f"    element = driver.find_element_by_description('{step.target}')")
                if step.value:
                    lines.append(f"    element.send_keys('{step.value}')")

            elif step.step_type == TestStepType.WAIT:
                seconds = step.value or "2"
                lines.append(f"    time.sleep({seconds})")

            elif step.step_type == TestStepType.SWIPE:
                direction = step.value or "up"
                lines.append(f"    driver.swipe_{direction}()")

            elif step.step_type == TestStepType.ASSERT:
                lines.append(f"    assert '{step.value}' in driver.page_source")

            elif step.step_type == TestStepType.SCREENSHOT:
                lines.append(f"    driver.save_screenshot('screenshot_{i}.png')")

            lines.append("")

        return "\n".join(lines)


# Global instance
test_generator_service = TestGeneratorService()
