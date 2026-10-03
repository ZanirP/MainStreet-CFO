
## Run the frontend

The `frontend/` app uses React, TypeScript, Vite, Tailwind CSS, and Recharts.
It communicates only with FastAPI; no Nessie credentials belong in frontend
files or `VITE_` variables. Business labels come from customer `first_name` and
`last_name`, with the customer ID as a fallback. No demo financial results are
included in production components.

Start FastAPI from the repository root in one terminal:

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Start the frontend in another terminal:

```sh
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://127.0.0.1:5173`. The default backend URL is
`http://localhost:8000`; change `VITE_API_BASE_URL` in `.env.local` if needed,
then restart Vite. Port 5173 is fixed to match existing development CORS.
Node 20.19+ or 22.12+ is required by Vite; development was verified on Node 26.

Select a business to load financial metrics, monthly charts, expense details,
listed bills, and health indicators. Submit “Hire an Employee” to compare
baseline and hiring cash projections. Changing businesses clears previous
results and cancels outstanding requests. Editing scenario inputs marks shown
results as needing an update. Charts include currency tooltips and expandable
numerical tables.

If the backend has no customers, the app shows an empty state. The hire scenario
needs dated monthly transaction history. Set up businesses and their records
through the existing backend/Nessie workflow to populate the dashboard.

Build and test from `frontend/`:

```sh
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

The browser tests exercise desktop and mobile charts, submission payloads,
projection results, and switching businesses with backend-shaped test fixtures.
The component tests cover the full request flow, empty lists, retries, and
loading/error states. Fixtures are confined to tests.
