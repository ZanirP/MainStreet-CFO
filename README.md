# MainStreet-CFO

`backend/services/nessie_service.py` owns Nessie API calls. Load `.env` with
`python-dotenv` at the application/script entry point, then instantiate
`NessieService()`. It reads `NESSIE_API_KEY` from the environment and uses
`https://api.nessieisreal.com` with the `key` query parameter, matching the
previous successful smoke test. Keep `.env` ignored by Git.

Methods return parsed JSON (including POST response envelopes). HTTP failures,
network failures, and invalid JSON raise `NessieServiceError`; HTTP errors have
`status_code`. Error messages omit response bodies and authenticated URLs.
Requests have a 15-second timeout and do not follow redirects. Successful
empty account-deletion responses return `None`.

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
| `get_account`, `delete_account` | `/accounts/{account_id}` (GET / DELETE) | — |
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

Transaction inputs default to empty lists; omitted `loans` mean unavailable debt
data, while `loans=[]` means no loans were returned. The result contains `summary`,
`expense_breakdown`, `largest_expenses`, `monthly_revenue`, `monthly_expenses`,
`trends`, `recurring_bills`, `health`, `signals`, and `debt`. Money and percentages are numeric,
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

## Seed three contrasting demo businesses

The deterministic May–September 2026 plan uses customer names and explicitly
fictional Ann Arbor addresses, checking accounts, real Nessie merchant IDs,
multiple unequal sales deposits, supplier invoices, completed historical bills,
and separate October recurring obligations. No financial conclusions or CFO
answers are stored in the seed data.

| Business | Monthly net cash flow, May → September | Economic opening cash | Current cash target | Deposits / purchases / bills |
| --- | --- | --- | --- | --- |
| Arbor Coffee Co. | −$3,000; −$1,500; +$500; +$2,000; +$1,500 | $9,500 | $9,000 | 30 / 75 / 42 |
| MainStreet Market | +$4,000; +$2,000; $0; −$2,000; −$5,000 | $16,000 | $15,000 | 30 / 51 / 42 |
| Pixel Palace Arcade | +$11,000; +$9,000; +$12,000; +$11,000; +$12,000 | $30,000 | $85,000 | 40 / 44 / 48 |

Arbor's card/catering sales grow while early losses leave little cash; September
includes a $1,750 espresso-machine repair. Market's wholesale inventory rises
from $21,000 to $23,500 and refrigeration utilities from $1,200 to $2,200 while
sales decline. Produce orders decrease, so costs do not all move together.
Waste disposal is a cash service expense, not a second charge for lost stock.
Pixel Palace has fluctuating admissions, parties and concessions sales, healthy
net cash generation and a $2,400 cabinet repair in July.

Historical payroll, rent, utilities, insurance and software payments are
completed bills and count toward expenses. October recurring bills are excluded
from realized historical totals. Purchases describe actual supplier payments;
merchant IDs are resolved by vendor name through `get_merchants()` or
`create_merchant()`. Fictional demo suppliers are never replaced with an
unrelated first merchant or fabricated IDs. Internal planning fields are removed
before sending supported Nessie payloads.

Preview **without Nessie or Gemini requests**, including monthly/category figures,
opening/current cash, record counts, derived signals and a standard hire:

```sh
.venv/bin/python scripts/seed_nessie.py --dry-run
```

For a fresh API dataset, seed all three:

```sh
.venv/bin/python scripts/seed_nessie.py
```

To migrate the existing Arbor dataset, explicitly rebuild mismatched **recognized
demo operating accounts** while retaining the customer IDs:

```sh
.venv/bin/python scripts/seed_nessie.py --replace-existing
```

This flag deletes and recreates only accounts with the known demo nickname and
matching fictional customer address. Complete matching datasets remain untouched,
even with the flag. Other accounts, ambiguous populated duplicate customers, or
matching names at different addresses cause a stop before writes. The old
empty duplicate Arbor customer, if present, is preserved; the populated customer
is reused. Use the printed customer IDs to select the seeded businesses.

All payload fields, counts, statuses, dates, amounts and final cash are read back
and verified. A rerun verifies a complete dataset without adding records. A
partial or changed dataset is refused unless replacement is explicit. Run one
seed process at a time; writes are not transactional and are not blindly retried.
An API rejection identifies the business, record type and index without exposing
keys, authenticated URLs, or response bodies.

**Balance assumptions:** economic opening cash + May–September net = current
cash, with no owner draws, debt flows or other unmodeled financing during this
history. Default `--balance-mode snapshot` creates the account at the **current**
cash target, since existing Nessie deposit/purchase history was observed to leave
the stored balance unchanged. This is a current banking snapshot, distinct from
the inferred economic opening cash. If the API applies completed postings to
balances, use `--balance-mode ledger`, which creates accounts at economic opening
cash and posts records chronologically. Both modes require the exact final cash
target; neither adds artificial balancing revenue/expenses or attempts an
unsupported balance update. A mismatch reports failure and requires inspection
before an explicit rebuild with the appropriate mode.

Contracts were rechecked against the
[official OpenAPI specification](https://nessieisreal.com/nessie-openapi-spec.yaml)
and [official purchase SDK](https://github.com/nessieisreal/nessie-javascript-sdk/blob/master/lib/purchase.js).
The service's new `delete_account()` uses documented `DELETE /accounts/{id}`
only for explicit demo replacement, accepting successful empty responses.

Optional filters and live CFO validation:

```sh
.venv/bin/python scripts/seed_nessie.py --business market --dry-run
.venv/bin/python scripts/seed_nessie.py --replace-existing --validate-cfo
```

`--validate-cfo` reads the actual seeded accounts/transactions, runs the normal
analyzer, and asks Gemini **the same question** for each business: “Is my current
debt manageable?” It requires the backend `GEMINI_API_KEY`.
Missing model availability does not roll back a successful seed. The CFO context
now includes deterministic dated monthly net cash flow and margins, allowing
recent recovery/deterioration to be explained without model arithmetic. No
business-specific responses or risk labels are hardcoded. Expense categories
remain the analyzer's source-based `Purchases`/`Bills`; descriptions and large
supplier payments supply inventory evidence, not an invented category taxonomy.

Forecasts still average the entire supplied history, rather than extrapolating
the latest month. For example, Market's baseline is −$200/month despite September's
−$5,000 net; Arbor averages −$100 despite recent profitability. Pixel Palace
averages +$11,000. These differing inputs naturally produce different scenario
and stress-test results; they do not constitute predictions that the trends
will continue. The existing expense-rise signal may flag Pixel's modest expense
increase even though its cash cushion and cash flow are healthy.

Offline checks:

```sh
.venv/bin/python -m unittest discover
```

## Existing loans and debt-aware decisions

`NessieService.get_loans(account_id)` and `create_loan(account_id, payload)` use
`GET` and `POST /accounts/{id}/loans`, verified against the
[official Nessie OpenAPI specification](https://nessieisreal.com/nessie-openapi-spec.yaml).
The POST body requires `type`, `status`, `credit_score`, `monthly_payment`,
`amount`, and `description`. Payment and amount are integers in that schema.
GET also returns `_id` and server-generated `creation_date`. Type and status
are documented as strings without enums; MainStreet explicitly interprets
`active` as an ongoing obligation, closed/paid/cancelled as inactive, and other
statuses as unresolved. None of these imply credit approval.

All analysis, scenario and CFO endpoints retrieve loans for every supplied
account through the same loader. Upstream loan failures return a sanitized
HTTP error instead of silently treating a business as debt-free. Direct analyzer
callers can supply `loans=[]` for a verified empty list; omitting loans means
unavailable information. Unknown/invalid loan amounts and statuses are flagged
as incomplete, and known-value totals must not be interpreted as complete debt.

Nessie calls `amount` the **amount of the loan**, without specifying remaining
principal. MainStreet displays **reported loan amount**; outstanding/payoff
balance, APR, interest cost, remaining term and amortization are unavailable.
Monthly payment is a cash obligation, not an interest-cost estimate. Principal
is never subtracted from historical expenses or current cash. The required demo
`credit_score=700` is synthetic API metadata, never credit eligibility evidence,
and is omitted from dashboard and CFO context.

| Demo | Reported loan amount | Monthly payment | Purpose |
| --- | --- | --- | --- |
| Arbor Coffee Co. | $48,000 | $1,200 | Startup buildout and espresso equipment |
| MainStreet Market | $90,000 | $1,800 | Store fixtures and refrigeration |
| Pixel Palace Arcade | $18,000 | $600 | Arcade cabinet equipment |

Each business has one active demo loan, five completed payment bills and an
October recurring payment bill. The existing operating budget is reallocated
between payroll and these debt payments; monthly revenue, total cash expenses,
historical net cash flow, and cash targets remain exactly unchanged. No new loan
disbursement is represented as earned sales. Nessie's record creation date is
not used to invent a loan origination date or a repayment term.

**Payment reconciliation:** Nessie has no bill-to-loan foreign key. This app
uses the explicit convention `nickname = "Debt payment: <loan description>"`.
A unique exact description on the same account, plus exactly one recurring bill
whose amount equals `monthly_payment`, verifies the link. Amount or lender-name
similarity alone is insufficient. The HTTP loader attaches local account
provenance to scope links; it never sends these local fields to Nessie.
Unlinked payment inclusion remains unknown. Such payments may already occur in
untagged expenses, so projections leave them unchanged and disclose the gap.
The conservative obligation exposure sums listed bills plus unlinked payments;
it may overlap and is explicitly not a verified total payable.

With verified links, projections remove the average historical linked payment
from cash expenses and add the current linked monthly payment **once**. With the
demo's constant payments this preserves the original default projections; a
changed current payment deterministically changes every scenario's baseline.
Stress keeps linked payments fixed and increases only the other positive cash
expenses. Break-even hiring capacity, revenue requirements, cash buffers and
runway use those same adjusted expenses and existing projection calculations.
Keeping payments constant throughout the horizon is an explicit assumption;
no payoff or new borrowing is inferred.

Debt signals and the compact dashboard section show cash-flow payment coverage
(cash flow before linked payments / monthly payments), remaining flow, and
known obligations. This is not a lender DSCR calculation or an approval rule.
Five-month average coverage is 0.92× / 0.89× / 19.33× for Arbor / Market / Pixel;
the latest-month coverage is 2.25× / −1.78× / 21×. The distinction matters:
Arbor's latest cash flow has recovered, Market's has deteriorated, and Pixel's
strong cash generation supports a much larger cushion. These conclusions follow
from common deterministic calculations, without company-specific risk rules.

Ask Your CFO includes `existing_debt` as current/historical source facts, with
missing terms explicitly null, separate from engine projections and hypothetical
decision assumptions. Gemini receives backend-calculated amounts and ratios,
uses the same numeric citation validation, and is instructed never to infer
interest, offers, credit approval or future financing eligibility.

Preview, migrate the recognized older demo accounts, and optionally validate
Gemini answers against real read-back data (commands from the repository root):

```sh
.venv/bin/python scripts/seed_nessie.py --dry-run
.venv/bin/python scripts/seed_nessie.py --replace-existing --validate-cfo
.venv/bin/python -m unittest discover
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

The v3 debt seed recognizes v2 and original demo account nicknames. Replacement
requires the explicit flag, keeps customer IDs, and rebuilds only owned demo
accounts. Matching complete loan/transaction records and cash are verified and
skipped even with the flag; changed or partial loan records are never appended.
Dry-run stays API-free even with `--validate-cfo`. A failed POST or read-back
leaves a clearly reported partial account, rather than claiming seed success.

Nessie's live Bill endpoint has a readback inconsistency: a completed bill POST
without `recurring_date` succeeds, but `GET /accounts/{id}/bills` can return HTTP
400 with missing `recurring_date` and `upcoming_payment_date` validation errors.
The seed's historical bills are monthly obligations, so each now includes its
actual day-of-month in the supported `recurring_date` field while retaining
`status=completed` and the original payment date/amount. Nessie generates the
upcoming date; it is not an invented POST field. This was confirmed with an
isolated completed-bill POST/readback and cleanup on the live API.

Older accounts affected by this exact error are unreadable and need the explicit
`--replace-existing` flag to rebuild the recognized demo account. The seed only
recovers from the exact observed two-field response-validation error; other 400s,
authentication failures, rate limits and network errors stop without deletion.
Completed verified datasets remain skipped on repeat runs. Service errors report
the HTTP method and route with resource IDs masked, never authenticated URLs,
API keys or upstream response bodies. `--validate-cfo` runs only after all seed
verification succeeds; it directly calls the analyzer/CFO service, not FastAPI.

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
positive average monthly expenses **excluding explicitly linked fixed loan
payments** by 10%, using the same complete historical
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

- Required monthly revenue = cash expenses including linked debt + monthly employee cost.
- Maximum employee cost = revenue − cash expenses including linked debt. A negative baseline
  returns `null` because even zero additional cost cannot break even.
- Maximum hourly wage = maximum employee cost × 12 / (weekly hours × 52).
  Zero weekly hours produces no finite wage ceiling (`null`). Maximums round
  down to cents; required revenue rounds up.

For equipment and withdrawals, the explicitly labeled buffer assumption is one
month of positive average cash expenses including linked debt. The maximum one-time amount keeps
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
## Open Another Location

Choose **Open Another Location** in the decision panel. The workflow reuses the
existing projections, stress charts, current debt handling, and Ask Your CFO.
It never creates a customer, account, transaction, or loan in Nessie.

Starting estimates come from dated, realized financial history: monthly revenue
and rent, payroll, utilities, inventory/supplies, and other operating costs.
Description keywords group expenses; insurance, internet, and POS subscriptions
fall into other costs. Verified current loan-payment bills are excluded from
these operating estimates. Missing categories remain blank, requiring an
explicit entry rather than implying zero. The expandable source detail explains
the history used. These are current-business reference amounts, not promises
about a new location. Every scenario assumption remains editable.

The backend accepts `POST /businesses/{customer_id}/scenarios/location`:

```json
{
  "upfront_cost": 30000,
  "monthly_revenue": 20000,
  "rent": 3000,
  "payroll": 7000,
  "utilities": 750,
  "inventory": 4000,
  "other": 1250,
  "ramp_months": 3,
  "months": 6,
  "financing_amount": 28000,
  "annual_interest_percent": 8,
  "financing_term_months": 60,
  "stress_test": true
}
```

Opening cash equals current cash minus upfront cost plus hypothetical financing.
All additional operating costs start in month one. Additional revenue ramps
linearly: mature revenue times `min(month / ramp_months, 1)`. Existing business
cash flow uses the shared historical baseline and counts verified current debt
once. Hypothetical financing uses fixed-payment amortization, or principal
divided by term for zero interest. Payments stop after the entered term. The
response includes monthly cash and operations, mature cash flow, a cash-funded
comparison, lowest cash point, first negative month, and decision limits.

Decision limits distinguish standalone location break-even from combined
business break-even, identify revenue downside headroom, and solve the minimum
mature revenue needed to preserve a buffer throughout the ramp. The buffer is
explicitly an illustrative one month of combined cash expenses. If cash already
falls below that buffer at opening, later revenue cannot preserve it from the
start. Runway is interpolated only when depletion occurs within the selected
horizon; an absent value does not imply indefinite safety. Stress reduces both
existing and new revenue by 10% and increases operating costs by 10%, keeping
opening cost and debt payments fixed.

Existing Nessie loans are current facts. Scenario financing is hypothetical:
the entered principal, interest, and term imply no offer, eligibility, or
approval. The UI's 8%/60-month financing defaults are visibly labeled editable
assumptions. No fees, tax effects, seasonality, cannibalization, opening delays,
or additional working-capital needs are modeled.

After simulation, Ask Your CFO receives the selected scenario inputs. FastAPI
recomputes the projection from fresh business analysis and separates current
facts, scenario assumptions, and calculated projections before Gemini explains
them. Browser-supplied projection totals are never trusted. Editing inputs or
switching businesses clears the previous scenario context. Without a completed
expansion simulation, the CFO requests missing assumptions rather than guessing.

To demo locally, run these in separate terminals from the repository root:

```sh
.venv/bin/python -m uvicorn backend.app:app --reload
npm --prefix frontend run dev
```

Select the populated Arbor Coffee business, choose Open Another Location, and
enter the example above. First disable financing, then enable $28,000 at the
explicitly assumed 8% for 60 months. With the verified Arbor snapshot of $9,000
cash, cash funding starts at -$21,000; financing starts at $7,000 but still dips
to about -$6,335 during the ramp. Its hypothetical monthly payment is $567.74.
Inspect the cash-funded comparison, stress chart, and decision limits, then ask
“What's the biggest risk with this expansion?” Actual outputs change when the
underlying business data changes.

Regression checks:

```sh
.venv/bin/python -m unittest discover -q
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```
