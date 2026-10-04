"""MainStreet CFO's initial HTTP API."""

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.services.financial_analyzer import FinancialAnalyzer
from backend.services.nessie_service import NessieService, NessieServiceError
from backend.services.scenario_engine import ScenarioEngine
from backend.services.cfo_assistant import CFOAssistant, CFOAssistantError

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="MainStreet CFO")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class HireScenarioRequest(BaseModel):
    hourly_wage: float = Field(ge=0, allow_inf_nan=False, strict=True)
    hours_per_week: float = Field(ge=0, allow_inf_nan=False, strict=True)
    months: int = Field(default=6, gt=0, strict=True)
    stress_test: bool = Field(default=False, strict=True)


def get_nessie_service() -> NessieService:
    # Lazy initialization lets health checks work even without API configuration.
    try:
        return NessieService()
    except ValueError:
        raise HTTPException(status_code=503, detail="Financial data service is not configured") from None


@app.exception_handler(NessieServiceError)
async def nessie_error_handler(request: Request, exc: NessieServiceError) -> JSONResponse:
    # Never return exception text, upstream bodies, or authenticated URLs.
    if exc.status_code == 404:
        status, detail = 404, "Requested financial resource was not found"
    elif exc.status_code == 429:
        status, detail = 503, "Financial data service is temporarily rate limited"
    else:
        status, detail = 502, "Unable to retrieve financial data"
    return JSONResponse(status_code=status, content={"detail": detail})


def _records(value: Any) -> list[dict[str, Any]]:
    """Reject malformed upstream lists instead of returning partial financial totals."""
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise HTTPException(status_code=502, detail="Financial data service returned unexpected data")
    return value


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class LocationScenarioRequest(BaseModel):
    upfront_cost: float = Field(ge=0, le=1e12, allow_inf_nan=False, strict=True)
    monthly_revenue: float = Field(ge=0, le=1e12, allow_inf_nan=False, strict=True)
    rent: float = Field(ge=0, le=1e12, allow_inf_nan=False, strict=True)
    payroll: float = Field(ge=0, le=1e12, allow_inf_nan=False, strict=True)
    utilities: float = Field(ge=0, le=1e12, allow_inf_nan=False, strict=True)
    inventory: float = Field(ge=0, le=1e12, allow_inf_nan=False, strict=True)
    other: float = Field(ge=0, le=1e12, allow_inf_nan=False, strict=True)
    ramp_months: int = Field(default=3, ge=1, le=120, strict=True)
    months: int = Field(default=6, ge=1, le=120, strict=True)
    financing_amount: float = Field(default=0, ge=0, le=1e12, allow_inf_nan=False, strict=True)
    annual_interest_percent: float = Field(default=0, ge=0, le=100, allow_inf_nan=False, strict=True)
    financing_term_months: int = Field(default=60, ge=1, le=360, strict=True)
    stress_test: bool = Field(default=False, strict=True)


class CFOQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000, strict=True)
    location_inputs: LocationScenarioRequest | None = None


def get_cfo_assistant() -> CFOAssistant:
    return CFOAssistant()


@app.exception_handler(CFOAssistantError)
async def cfo_error_handler(request: Request, exc: CFOAssistantError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.post("/businesses/{customer_id}/cfo/ask")
def ask_cfo(customer_id: str, inputs: CFOQuestionRequest,
            service: NessieService = Depends(get_nessie_service),
            assistant: CFOAssistant = Depends(get_cfo_assistant)) -> dict[str, Any]:
    if not inputs.question.strip():
        raise HTTPException(status_code=422, detail="Enter a financial question.")
    analysis = _business_analysis(customer_id, service)
    try:
        if inputs.location_inputs is not None:
            scenario = ScenarioEngine().simulate_location(analysis, **inputs.location_inputs.model_dump())
            return assistant.ask(analysis, inputs.question, location_scenario=scenario)
        return assistant.ask(analysis, inputs.question)
    except ValueError:
        raise HTTPException(status_code=422, detail="Enter a valid financial question.") from None


@app.get("/businesses")
def businesses(service: NessieService = Depends(get_nessie_service)) -> list[dict[str, Any]]:
    return _records(service.get_customers())


@app.get("/businesses/{customer_id}/analysis")
def business_analysis(
    customer_id: str, service: NessieService = Depends(get_nessie_service)
) -> dict[str, Any]:
    return _business_analysis(customer_id, service)


def _business_analysis(customer_id: str, service: NessieService) -> dict[str, Any]:
    """Shared loading and analysis for the dashboard and scenario endpoints."""
    accounts = _records(service.get_customer_accounts(customer_id))
    deposits, purchases, bills, loans = [], [], [], []
    # Include credit accounts for their expenses; the analyzer owns cash-balance rules.
    for account in accounts:
        account_id = account.get("_id")
        if not isinstance(account_id, str) or not account_id.strip():
            raise HTTPException(status_code=502, detail="Financial data service returned an invalid account")
        deposits.extend(_records(service.get_deposits(account_id)))
        purchases.extend(_records(service.get_purchases(account_id)))
        # Local provenance scopes explicit payment links; these are not API fields.
        bills.extend({**bill, "_source_account_id": account_id} for bill in _records(service.get_bills(account_id)))
        loans.extend({**loan, "_source_account_id": account_id} for loan in _records(service.get_loans(account_id)))
    return FinancialAnalyzer().analyze_business(
        accounts=accounts, deposits=deposits, purchases=purchases, bills=bills, loans=loans
    )


@app.post("/businesses/{customer_id}/scenarios/hire")
def hire_scenario(
    customer_id: str, inputs: HireScenarioRequest,
    service: NessieService = Depends(get_nessie_service),
) -> dict[str, Any]:
    analysis = _business_analysis(customer_id, service)
    try:
        return ScenarioEngine().simulate_hire(analysis, **inputs.model_dump())
    except ValueError as exc:
        # ScenarioEngine messages name fields only, never supplied values or secrets.
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.post("/businesses/{customer_id}/scenarios/location")
def location_scenario(customer_id: str, inputs: LocationScenarioRequest,
                      service: NessieService = Depends(get_nessie_service)) -> dict[str, Any]:
    analysis = _business_analysis(customer_id, service)
    try:
        return ScenarioEngine().simulate_location(analysis, **inputs.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


class OneTimeScenarioRequest(BaseModel):
    amount: float = Field(ge=0, allow_inf_nan=False, strict=True)
    months: int = Field(default=6, gt=0, strict=True)
    stress_test: bool = Field(default=False, strict=True)


def _one_time_scenario(customer_id: str, inputs: OneTimeScenarioRequest,
                       service: NessieService, scenario: str) -> dict[str, Any]:
    analysis = _business_analysis(customer_id, service)
    engine = ScenarioEngine()
    simulate = engine.simulate_equipment if scenario == "equipment" else engine.simulate_withdrawal
    try:
        return simulate(analysis, **inputs.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.post("/businesses/{customer_id}/scenarios/equipment")
def equipment_scenario(customer_id: str, inputs: OneTimeScenarioRequest,
                       service: NessieService = Depends(get_nessie_service)) -> dict[str, Any]:
    return _one_time_scenario(customer_id, inputs, service, "equipment")


@app.post("/businesses/{customer_id}/scenarios/withdrawal")
def withdrawal_scenario(customer_id: str, inputs: OneTimeScenarioRequest,
                        service: NessieService = Depends(get_nessie_service)) -> dict[str, Any]:
    return _one_time_scenario(customer_id, inputs, service, "withdrawal")
