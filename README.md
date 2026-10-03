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
python -m unittest test_app test_financial_analyzer test_nessie_service test_scenario_engine
```

## Hire employee simulation

`ScenarioEngine.simulate_hire(analysis, hourly_wage, hours_per_week, months=6)`
uses the existing analyzer output and performs no API calls. The monthly added
wage cost is `hourly_wage * hours_per_week * 52 / 12`. Taxes, benefits, hiring
costs, revenue growth, and seasonality are not modeled.

The baseline is average monthly net cash flow across the entire supplied
calendar history: total monthly revenue minus total monthly expenses, divided
by the number of calendar months from the earliest through the latest entry.
Missing months count as zero. History may contain partial months; the engine
cannot identify those from the analyzer output.

Both projections start from `summary.cash_balance`. Each entry shows an
end-of-month balance after adding baseline cash flow (or baseline minus wage
cost) for that many months. The first projection month follows the latest
historical month, making repeated simulations deterministic even if the
system date changes. Stale history therefore produces projections anchored to
that history, rather than to today's date. Decimal calculations retain precision
until results are rounded to two decimal places.

Negative/nonfinite wages or hours, noninteger/nonpositive months, missing cash
balance, malformed monthly records, and completely empty monthly history raise
`ValueError`. Zero wages or hours and explicit zero-valued monthly history are
valid. The API returns HTTP 422 for invalid inputs or insufficient scenario
history, and keeps the existing sanitized Nessie error handling.

```sh
curl -X POST http://127.0.0.1:8000/businesses/CUSTOMER_ID/scenarios/hire \
  -H 'Content-Type: application/json' \
  -d '{"hourly_wage":18,"hours_per_week":30,"months":6}'
```

The request model uses [Pydantic field constraints](https://docs.pydantic.dev/latest/concepts/fields/)
for nonnegative finite numbers and positive integer months (default six).
Local Vite CORS permits GET and POST. The endpoint retrieves the financial
records through the shared analysis-loading helper, calls `FinancialAnalyzer`,
and returns the `ScenarioEngine` result without modifying Nessie data.

```sh
python -m unittest test_scenario_engine test_app test_financial_analyzer test_nessie_service
```

## Frontend dashboard

The complete React/TypeScript dashboard lives in `frontend/`. See
[frontend setup and usage](frontend/README.md) for configuration, build, and tests.

Run FastAPI from the repository root:

```sh
source .venv/bin/activate
uvicorn backend.app:app --reload
```

In a second terminal:

```sh
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://127.0.0.1:5173`. The browser uses only the FastAPI backend.
Businesses and all financial results come from the backend. Empty customer
lists show an empty state; hiring projections need dated monthly history.

## Seed the Arbor Coffee demo

From the repository root, with the existing `.env` configured:

```sh
.venv/bin/python scripts/seed_nessie.py
```

Preview without making API requests:

```sh
.venv/bin/python scripts/seed_nessie.py --dry-run
```

The script creates the customer as `first_name: "Arbor"`,
`last_name: "Coffee Co."`, with an explicitly fictional Ann Arbor address.
It creates a Checking account with a $26,000 balance, then 25 deposits,
35 purchases, and 36 bills. The history covers May–September 2026 and exactly
matches the requested monthly revenue and realized-expense targets. Historical
bills include existing staff payroll alongside rent, utilities, internet,
insurance, and POS software; six separate recurring bills are dated in October.
The average monthly baseline is $6,340, reduced to $4,000 by an $18/hour,
30-hour/week hire. Projection labels begin in October after September history.

Payloads use the documented customer, account, deposit, and bill fields from
[Nessie's OpenAPI specification](https://nessieisreal.com/nessie-openapi-spec.yaml).
Purchases use the [official SDK contract](https://github.com/nessieisreal/nessie-javascript-sdk/blob/master/lib/purchase.js),
including a real merchant ID. The only new service operations are
`get_merchants()` and `create_merchant()`, using the documented `/merchants`
route. An existing merchant is reused; a minimal demo supplier is created if
none are available.

The customer ID is printed for testing `/businesses/{customer_id}/analysis`.
A second run detects Arbor Coffee and stops without creating additional
records. Run only one seed process at a time. A failure can leave partial data;
the script does not blindly retry writes or automatically delete records.
Inspect partial records before making changes.

The script reads the account balance back after seeding and checks the
$24,000–$28,000 target. The public contract does not specify historical
transaction balance side effects. If Nessie changes the balance outside that
range, the script reports a failure rather than claiming a successful seed or
inventing unsupported balance-update fields.

Offline seed checks:

```sh
.venv/bin/python -m unittest test_seed_nessie test_nessie_service
```

## One-time scenarios

The What if? selector now also supports Equipment Purchase and Owner Withdrawal.
Both reduce current business cash once, before the first projected month's
operating cash flow. They retain the same historical baseline, projection dates,
and `cash_projection` format as hiring. Ongoing monthly cash flow is unchanged;
this version assumes no financing, equipment-driven revenue growth, taxes, or
other secondary effects. These endpoints simulate only; they do not create
Nessie transactions or move funds.

```sh
curl -X POST http://127.0.0.1:8000/businesses/CUSTOMER_ID/scenarios/equipment \
  -H 'Content-Type: application/json' -d '{"amount":5000,"months":6}'
curl -X POST http://127.0.0.1:8000/businesses/CUSTOMER_ID/scenarios/withdrawal \
  -H 'Content-Type: application/json' -d '{"amount":5000,"months":6}'
```

Both bodies accept a nonnegative finite `amount` and a positive integer `months`
(default six). The engine methods are `simulate_equipment(analysis, amount,
months=6)` and `simulate_withdrawal(analysis, amount, months=6)`. Responses include
`one_time_cost`, zero `monthly_added_cost`, unchanged baseline/projected monthly
cash flow, and the existing monthly baseline/scenario balance arrays. A $5,000
outflow keeps the scenario balance $5,000 below baseline each month, rather than
subtracting $5,000 repeatedly. Amounts exceeding available cash are permitted
in the simulation, and negative projected balances remain visible.

The frontend reuses its result panel and Recharts comparison graph, with labels
for each scenario. Hiring retains its recurring monthly wage calculation.

```sh
.venv/bin/python -m unittest test_scenario_engine test_app test_financial_analyzer test_nessie_service
cd frontend
npm test
npm run test:e2e
npm run build
```

## Financial signals and conservative stress case

Analysis now includes a `signals` array. Each signal contains an `id`, `level`
(`positive`, `caution`, or `neutral`), `title`, `explanation`, `value`, and `unit`.
The dashboard displays these in its financial-health panel, with caution signals
first. Calculations use only the analyzer's existing totals and monthly series:

- Revenue and expense changes compare the latest two calendar months. Missing
  history or an undefined percentage is explained as unavailable.
- Expenses growing faster than revenue is flagged only when expense growth is
  positive and exceeds the comparable revenue growth rate.
- Recurring obligations sum listed recurring bills once, divided by positive
  cash as a percentage. This is not an inferred monthly payment schedule.
- Cash coverage divides nonnegative cash by average dated monthly expenses;
  below one month is flagged. It assumes no new revenue and is not a runway
  forecast. Nonpositive average expenses make coverage unavailable.

Calendar gaps count as zero, and the latest recorded month may be partial.
Unavailable ratios use `null`; missing data never produces a positive signal.

All three scenario endpoints accept optional `"stress_test": true`. Omit it or
send `false` to retain the existing response and default projection unchanged.
The frontend checkbox adds a separate conservative comparison underneath the
normal chart, reusing the same chart component.

```json
{"amount":5000,"months":6,"stress_test":true}
```

The conservative case lowers positive average monthly revenue by 10% and raises
positive average monthly expenses by 10%, using the same complete historical
calendar span as the normal scenario. Nonpositive signed averages remain
unchanged so credits cannot accidentally improve the stress projection. Hiring
wages and one-time cash reductions remain unchanged. Starting cash and month
labels are identical to the normal projection.

The response adds `stress_test` containing `assumptions` (percentages, source
averages, stressed amounts, and the calculation basis), stressed baseline and
scenario monthly cash flows, and `cash_projection`. Both the assumptions and
stressed figures are visible in the frontend. This is an illustrative stress
case, not a forecast probability or a guarantee.

## Scenario breaking points

All three scenario responses include `breaking_point`; an enabled `stress_test`
includes its own limits using stressed revenue and expenses. Existing projections
remain unchanged. The dashboard displays these under **Breaking Point**.

Hiring limits use the same historical monthly averages as the projection:

- Required monthly revenue = operating expenses + monthly employee cost.
- Maximum employee cost = revenue − operating expenses. A negative baseline
  returns `null` because even zero additional cost cannot break even.
- Maximum hourly wage = maximum employee cost × 12 / (weekly hours × 52).
  Zero weekly hours produces no finite wage ceiling (`null`). Maximums round
  down to cents; required revenue rounds up.

For equipment and withdrawals, the explicitly labeled buffer assumption is one
month of positive average operating expenses. The maximum one-time amount keeps
that buffer both immediately after the decision and throughout the chosen horizon:
`cash + min(0, baseline_monthly_cash_flow × months) − buffer`. A negative capacity
returns `null` (the buffer is already unattainable). This illustrative assumption
is not a universal definition of a safe decision.

Runway is cash after the decision divided by net monthly burn. Nondepleting cash
returns `null`; an immediate shortfall returns zero. First negative end-of-month
cash is at `floor(runway) + 1`, since zero is not negative. Month index zero means
an immediate shortfall before monthly cash flow and has no calendar date. The
first-negative point may extend beyond the selected horizon, using the same
constant-flow assumption. `negative_within_horizon` includes immediate shortfalls,
even if subsequent revenue restores cash. These limits are model thresholds,
not guarantees or financial advice.

## Ask Your CFO

The dashboard now includes a focused question-and-answer section. Gemini interprets
questions and explains context; FinancialAnalyzer and ScenarioEngine remain the
source of financial calculations. Hiring, equipment, withdrawals, baseline cash
projections, signals, stress assumptions and decision limits are reused. Hiring
questions also receive a deterministic revenue-drop-to-break-even threshold.
Missing inputs prompt clarification rather than guessed wages or amounts.

Backend `.env` configuration (never add these to `frontend/.env`):

```dotenv
GEMINI_API_KEY=your_backend_only_key
# Optional; this model was verified with the configured account:
GEMINI_MODEL=gemini-3.5-flash-lite
```

The service uses Gemini's REST structured-output API through the existing
`requests` dependency; no new packages are required. See Google's
[structured-output documentation](https://ai.google.dev/gemini-api/docs/structured-output)
and [Flash-Lite model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite).
Restart FastAPI after changing environment configuration.

`POST /businesses/{customer_id}/cfo/ask` accepts:

```json
{"question":"Can I afford to hire someone at $20/hour for 30 hours a week?"}
```

It returns `answer`, `status` (`answered` or `needs_information`), cited `facts`
(with value, display, label and historical/projection/scenario source), and
structured `context`. No prior conversation is stored; include decision inputs
in each question. The default projection is six months, with a supported range
of one through 120 months. The context includes available history, signals,
upcoming bills and applicable calculations. Model calls contain the question
and relevant financial data, but never Nessie or Gemini credentials. No questions
or responses are logged or saved by this application.

Gemini must reference backend fact placeholders for numerical statements. The
backend rejects unknown references or newly generated numerical quantities and
substitutes backend-formatted figures. This verifies numerical sources, not every
semantic claim; explanations can still be imperfect. The model is explicitly
instructed to distinguish history from assumptions, acknowledge missing causes
and avoid certainty about future outcomes. Missing data or unsupported questions
return clarification; missing configuration, provider failures and malformed
answers produce sanitized errors. The dashboard and deterministic scenarios do
not depend on Gemini availability.

Offline verification:

```bash
.venv/bin/python -m unittest test_cfo_assistant test_app test_scenario_engine test_financial_analyzer test_nessie_service
cd frontend
npm test
npm run build
npm run test:e2e
```

Run locally in separate terminals from the repository root:

```bash
source .venv/bin/activate
uvicorn backend.app:app --reload
```

```bash
cd frontend
npm run dev
```
