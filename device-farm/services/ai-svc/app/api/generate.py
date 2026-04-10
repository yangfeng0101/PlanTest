# Test Generation API Routes
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import logging

from app.services.test_generator import (
    test_generator_service,
    TestType,
    TestCase,
    TestTemplate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class GenerateRequest(BaseModel):
    """Test generation request"""
    description: str
    test_type: str = "functional_test"
    test_name: Optional[str] = None


class GenerateFromTemplateRequest(BaseModel):
    """Generate from template request"""
    template_id: str
    parameters: Optional[Dict[str, str]] = None
    test_name: Optional[str] = None


class TestStepResponse(BaseModel):
    """Test step response"""
    step_type: str
    description: str
    action: str
    target: Optional[str] = None
    value: Optional[str] = None
    timeout: Optional[int] = None


class TestCaseResponse(BaseModel):
    """Test case response"""
    id: str
    name: str
    description: str
    test_type: str
    steps: List[TestStepResponse]
    preconditions: List[str] = []
    postconditions: List[str] = []
    tags: List[str] = []
    priority: int = 1


class TemplateResponse(BaseModel):
    """Template response"""
    id: str
    name: str
    description: str
    test_type: str
    template_steps: List[Dict[str, Any]]


class SuggestionResponse(BaseModel):
    """Improvement suggestion response"""
    type: str
    message: str
    severity: str
    step_index: Optional[int] = None


@router.post("/generate", response_model=TestCaseResponse)
async def generate_test_case(request: GenerateRequest):
    """
    Generate test case from natural language description

    The description should describe the test scenario in natural language,
    e.g., "打开应用，点击登录按钮，输入用户名和密码，点击提交"
    """
    try:
        test_type = TestType(request.test_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid test_type. Must be one of: {[t.value for t in TestType]}"
        )

    test_case = test_generator_service.generate_from_description(
        description=request.description,
        test_type=test_type,
        test_name=request.test_name,
    )

    return _test_case_to_response(test_case)


@router.post("/generate/from-template", response_model=TestCaseResponse)
async def generate_from_template(request: GenerateFromTemplateRequest):
    """
    Generate test case from a template

    Use predefined templates for common test patterns.
    """
    test_case = test_generator_service.generate_from_template(
        template_id=request.template_id,
        parameters=request.parameters,
        test_name=request.test_name,
    )

    if not test_case:
        raise HTTPException(
            status_code=404,
            detail=f"Template not found: {request.template_id}"
        )

    return _test_case_to_response(test_case)


@router.get("/templates", response_model=List[TemplateResponse])
async def list_templates():
    """
    List all available test templates

    Templates provide predefined test patterns for common scenarios.
    """
    templates = test_generator_service.get_templates()

    return [
        TemplateResponse(
            id=t.id,
            name=t.name,
            description=t.description,
            test_type=t.test_type.value,
            template_steps=t.template_steps,
        )
        for t in templates
    ]


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str):
    """Get a specific template by ID"""
    template = test_generator_service.get_template(template_id)

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        test_type=template.test_type.value,
        template_steps=template.template_steps,
    )


@router.post("/suggest", response_model=List[SuggestionResponse])
async def suggest_improvements(test_case: TestCaseResponse):
    """
    Suggest improvements for a test case

    Analyzes the test case and provides suggestions for improvement.
    """
    # Convert response back to TestCase
    from app.services.test_generator import TestStep, TestStepType

    tc = TestCase(
        id=test_case.id,
        name=test_case.name,
        description=test_case.description,
        test_type=TestType(test_case.test_type),
        steps=[
            TestStep(
                step_type=TestStepType(s.step_type),
                description=s.description,
                action=s.action,
                target=s.target,
                value=s.value,
                timeout=s.timeout,
            )
            for s in test_case.steps
        ],
        preconditions=test_case.preconditions,
        postconditions=test_case.postconditions,
        tags=test_case.tags,
        priority=test_case.priority,
    )

    suggestions = test_generator_service.suggest_improvements(tc)

    return [
        SuggestionResponse(
            type=s["type"],
            message=s["message"],
            severity=s["severity"],
            step_index=s.get("step_index"),
        )
        for s in suggestions
    ]


@router.post("/export")
async def export_test_case(
    test_case: TestCaseResponse,
    format: str = Query("python", description="Output format: python or json"),
):
    """
    Export test case to executable script

    Supported formats:
    - python: Python test script
    - json: JSON format
    """
    from app.services.test_generator import TestStep, TestStepType

    tc = TestCase(
        id=test_case.id,
        name=test_case.name,
        description=test_case.description,
        test_type=TestType(test_case.test_type),
        steps=[
            TestStep(
                step_type=TestStepType(s.step_type),
                description=s.description,
                action=s.action,
                target=s.target,
                value=s.value,
                timeout=s.timeout,
            )
            for s in test_case.steps
        ],
        preconditions=test_case.preconditions,
        postconditions=test_case.postconditions,
        tags=test_case.tags,
        priority=test_case.priority,
    )

    script = test_generator_service.to_script(tc, format=format)

    return {
        "test_id": tc.id,
        "format": format,
        "script": script,
    }


def _test_case_to_response(test_case: TestCase) -> TestCaseResponse:
    """Convert TestCase to response model"""
    from app.services.test_generator import TestStep

    return TestCaseResponse(
        id=test_case.id,
        name=test_case.name,
        description=test_case.description,
        test_type=test_case.test_type.value,
        steps=[
            TestStepResponse(
                step_type=s.step_type.value,
                description=s.description,
                action=s.action,
                target=s.target,
                value=s.value,
                timeout=s.timeout,
            )
            for s in test_case.steps
        ],
        preconditions=test_case.preconditions,
        postconditions=test_case.postconditions,
        tags=test_case.tags,
        priority=test_case.priority,
    )
