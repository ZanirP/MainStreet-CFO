"""MainStreet CFO's initial HTTP API."""

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.services.financial_analyzer import FinancialAnalyzer
from backend.services.nessie_service import NessieService, NessieServiceError

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="MainStreet CFO")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


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


@app.get("/businesses")
def businesses(service: NessieService = Depends(get_nessie_service)) -> list[dict[str, Any]]:
    return _records(service.get_customers())


@app.get("/businesses/{customer_id}/analysis")
def business_analysis(
    customer_id: str, service: NessieService = Depends(get_nessie_service)
) -> dict[str, Any]:
    accounts = _records(service.get_customer_accounts(customer_id))
    deposits, purchases, bills = [], [], []
    # Include credit accounts for their expenses; the analyzer owns cash-balance rules.
    for account in accounts:
        account_id = account.get("_id")
        if not isinstance(account_id, str) or not account_id.strip():
            raise HTTPException(status_code=502, detail="Financial data service returned an invalid account")
        deposits.extend(_records(service.get_deposits(account_id)))
        purchases.extend(_records(service.get_purchases(account_id)))
        bills.extend(_records(service.get_bills(account_id)))
    return FinancialAnalyzer().analyze_business(
        accounts=accounts, deposits=deposits, purchases=purchases, bills=bills
    )
