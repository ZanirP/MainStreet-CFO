# MainStreet-CFO

`backend/services/nessie_service.py` owns Nessie API calls. Load `.env` with
`python-dotenv` at the application/script entry point, then instantiate
`NessieService()`. It reads `NESSIE_API_KEY` from the environment and uses
`https://api.nessieisreal.com` with the `key` query parameter, matching the
previous successful smoke test. Keep `.env` ignored by Git.

Methods return parsed JSON (including POST response envelopes). HTTP failures,
network failures, and invalid JSON raise `NessieServiceError`; HTTP errors have
`status_code`. Error messages omit response bodies and authenticated URLs.
Requests have a 15-second timeout and do not follow redirects.

Routes and bodies were verified on October 3, 2026 against the
[official OpenAPI specification](https://nessieisreal.com/nessie-openapi-spec.yaml).
The specification omits account purchase routes; those and the purchase body
were verified against the [official purchase SDK](https://github.com/nessieisreal/nessie-javascript-sdk/blob/master/lib/purchase.js).
POST methods accept a dictionary and send it unchanged as JSON; the API performs
payload validation.

| Method | Route | POST body fields |
| --- | --- | --- |
| `get_customers`, `create_customer` | `/customers` | `first_name`, `last_name`, `address` |
| `get_customer` | `/customers/{customer_id}` | — |
| `get_customer_accounts`, `create_account` | `/customers/{customer_id}/accounts` | `type`, `nickname`, `rewards`, `balance` |
| `get_account` | `/accounts/{account_id}` | — |
| `get_purchases`, `create_purchase` | `/accounts/{account_id}/purchases` | `merchant_id`, `medium`, `purchase_date`, `amount`, `status`, `description` |
| `get_deposits`, `create_deposit` | `/accounts/{account_id}/deposits` | `medium`, `transaction_date`, `status`, `amount`, `description` |
| `get_bills`, `create_bill` | `/accounts/{account_id}/bills` | `status`, `payee`, `payment_amount`; optional `nickname`, `payment_date`, `recurring_date` |

`address` contains string fields `street_number`, `street_name`, `city`, `state`,
and `zip`. Account `type` is `Credit Card`, `Savings`, or `Checking`; `rewards`
and `balance` are nonnegative integers. Deposit `amount` is an integer. The
purchase SDK illustrates `medium: "balance"` and `status: "pending"`.
Purchases require an existing merchant ID. Bill status is `pending`, `cancelled`,
`completed`, or `recurring`; `recurring_date` is an integer from 1 to 31.

Run offline checks:

```sh
.venv/bin/python -m unittest test_nessie_service
```

Run the real API smoke test (loads the root `.env`; prints only result counts):

```sh
.venv/bin/python test_nessie.py
.venv/bin/python test_nessie.py --customer-id CUSTOMER_ID --account-id ACCOUNT_ID
```

The first command checks all customers. The second exercises all seven GET
methods using existing IDs. POST checks are explicit and create real sandbox
records. Put the documented body in a JSON file and run one operation:

```sh
.venv/bin/python test_nessie.py --create customer --payload customer.json
.venv/bin/python test_nessie.py --create account --customer-id CUSTOMER_ID --payload account.json
.venv/bin/python test_nessie.py --create purchase --account-id ACCOUNT_ID --payload purchase.json
.venv/bin/python test_nessie.py --create deposit --account-id ACCOUNT_ID --payload deposit.json
.venv/bin/python test_nessie.py --create bill --account-id ACCOUNT_ID --payload bill.json
```

No API key argument is needed. Neither the smoke script nor the service prints
the key, authenticated URLs, or raw API responses.

## Financial analysis

`FinancialAnalyzer` is independent of Nessie and accepts flat lists of account,
deposit, purchase, and bill dictionaries. Combine GET results for all relevant
accounts before calling it. It performs no API calls or environment reads.

```python
from datetime import date
from backend.services.financial_analyzer import FinancialAnalyzer

analysis = FinancialAnalyzer().analyze_business(
    accounts=accounts,
    deposits=deposits,
    purchases=purchases,
    bills=bills,
    as_of=date(2026, 10, 3),
    largest_expenses_limit=5,
)
```

All inputs default to empty lists. The result contains `summary`,
`expense_breakdown`, `largest_expenses`, `monthly_revenue`, `monthly_expenses`,
`trends`, `recurring_bills`, and `health`. Money and percentages are numeric,
rounded to two decimal places; internal sums use decimal arithmetic.

Calculation conventions:

- Deposits are a revenue proxy. This is cash-flow analysis; loans or owner
  contributions in deposits are not distinguished from earned revenue.
- Totals include completed transactions and records without a status. Pending,
  recurring, cancelled, and other non-completed statuses are excluded. Expenses
  sum purchase `amount` and bill `payment_amount`; signed amounts are retained
  so credits reduce totals. Caller-supplied records are assumed distinct; there
  is no reconciliation between bill payments and purchases.
- Cash sums Checking and Savings balances, excluding Credit Card balances.
  Missing account types fall back to inclusion. Margin is net cash flow divided
  by revenue times 100, or zero when revenue is zero.
- Categories are `Purchases` and `Bills`; Nessie's supplied contracts have no
  expense category field. Largest expenses contain positive amounts, sorted
  descending, with stable input-order ties and normalized `id`, `description`,
  `category`, `amount`, and ISO `date` fields.
- Monthly series use `{ "month": "YYYY-MM", "amount": 0 }` entries and share
  a calendar spanning the earliest to latest dated realized transaction.
  Calendar gaps are zero-filled. Trends compare its last two calendar months;
  these may include a partial month. Fewer than two months yield zero change.
  Growth from zero to a nonzero amount yields `null`, because the percentage
  is undefined; zero to zero yields zero.
- Missing or invalid amounts contribute zero. Missing or invalid dates are
  excluded from monthly series while amounts remain in overall totals.
- `recurring_bills` lists pending and recurring bills, prioritizing
  `upcoming_payment_date` over `payment_date`, sorted by date with undated bills
  last. With `as_of`, earlier one-time pending bills are excluded. Recurring
  bills stay visible even with stale dates; no payment occurrences are invented.
  Without `as_of`, all active obligations are listed, including overdue ones.
- Health contains descriptive cash-flow and reserve flags, the listed bill
  total, whether cash covers that total, and a coverage ratio (`null` when
  obligations are zero). It uses no external benchmarks or generated advice.

Run the offline checks for both services:

```sh
.venv/bin/python -m unittest test_financial_analyzer test_nessie_service
```

## Run the backend

From the repository root:

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn backend.app:app --reload
```

The API runs at `http://127.0.0.1:8000`; interactive API documentation is at
`http://127.0.0.1:8000/docs`. The root `.env` is loaded on startup.

- `GET /health` returns `{ "status": "ok" }` without requiring a Nessie key.
- `GET /businesses` returns Nessie's customer list.
- `GET /businesses/{customer_id}/analysis` retrieves accounts and aggregates
  deposits, purchases, and bills from each account before calling the analyzer.
  All accounts contribute transactions; the analyzer controls which balances
  count as cash. Empty account lists produce an empty analysis.

CORS permits `http://localhost:5173` and `http://127.0.0.1:5173` for local Vite
development, using FastAPI's
[CORSMiddleware](https://fastapi.tiangolo.com/tutorial/cors/).
Missing service configuration returns HTTP 503. Upstream missing resources
return 404, rate limits return 503, and other upstream/network failures return
502. Malformed upstream lists also return 502 rather than partial totals.
Errors contain fixed messages without credentials or upstream response bodies.

Run all offline tests (HTTP requests to Nessie are mocked):

```sh
python -m unittest test_app test_financial_analyzer test_nessie_service
```
