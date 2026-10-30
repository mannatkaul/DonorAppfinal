# Donor API

FastAPI service for donor profiles, monetary and material donations, verified Razorpay payments, dashboard totals, and acknowledgments. The API is PostgreSQL-backed. It never simulates a successful payment: checkout is disabled until Razorpay test credentials are configured, and the dashboard counts only payments verified as captured.

## 1. Create a PostgreSQL database

In pgAdmin, connect to your local PostgreSQL server and open **Query Tool**. Create a dedicated login role and an owned database (replace the example password):

```sql
CREATE ROLE donor_app LOGIN PASSWORD 'replace-with-a-strong-password';
CREATE DATABASE donor_management OWNER donor_app;
```

If you prefer the pgAdmin dialogs, create a login role with **Can login** and then create `donor_management` with that role as its owner.

Copy the repository-root `.env.example` to `.env`, then set:

- `DATABASE_URL`: `postgresql+psycopg://donor_app:<URL-ENCODED-PASSWORD>@localhost:5432/donor_management`
- `JWT_SECRET_KEY`: a private random secret of at least 32 characters
- `FRONTEND_ORIGINS`: comma-separated exact origins of the Vite app, including its port
- `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`: optional Razorpay **test-mode** API credentials
- `RAZORPAY_WEBHOOK_SECRET`: optional secret configured for the Razorpay webhook

URL-encode special characters in the database password. Keep `.env` private and do not commit it. The API serves registration and donor features without Razorpay credentials; checkout returns `503` until test credentials are supplied.

## 2. Install, migrate, and start

From the repository root in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
alembic -c backend\alembic.ini upgrade head
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

Create the first administrator in another terminal. From the repository root:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m app.cli create-admin --email admin@example.com --name "Foundation Admin"
Pop-Location
```

The command prompts for a password and stores only its Argon2 password hash. Administrator privileges are not assignable through donor registration or the public donor API.

Open `http://127.0.0.1:8000/docs` for the interactive API documentation and `http://127.0.0.1:8000/api/health` for the service health check. Apply future migrations with `alembic -c backend\alembic.ini upgrade head`.

## 3. Check records in pgAdmin

After running migrations, expand **Databases → donor_management → Schemas → public → Tables** and refresh. The initial migration creates:

- `donors`
- `donations`
- `payments`
- `material_donations`
- `receipts`
- `alembic_version`

Use pgAdmin's **View/Edit Data → All Rows** to inspect them. Password hashes are stored, not raw passwords. A monetary receipt is inserted only after Razorpay signature and captured-payment verification. Material receipts are created only after an administrator confirms receipt of an approved, scheduled donation.

## API outline

- `POST /api/auth/register`, `POST /api/auth/login`
- `GET/PATCH /api/donors/me`; administrator-only donor CRUD/search at `/api/donors`
- `POST /api/donations`; donor-scoped history at `GET /api/donations`
- `POST /api/donations/{id}/checkout`, `POST /api/payments/verify`, and Razorpay webhook at `/api/payments/razorpay/webhook`
- `POST/GET /api/material-donations`; administrator approval, scheduling, and receipt confirmation under `/api/admin/material-donations`
- `GET /api/receipts`, `GET /api/receipts/{id}`, and printable acknowledgment at `/api/receipts/{id}/document`
- `GET /api/dashboard/stats`

Protected endpoints require `Authorization: Bearer <access_token>`. Checkout accepts an optional `Idempotency-Key` header. Configure the Razorpay webhook to send `payment.captured` and `payment.failed` events to the endpoint above; use the same webhook secret in `.env`.

## Tests

With the dependencies installed, run:

```powershell
python -m pytest backend\tests -q
```

Tests use an isolated in-memory SQLite database and stub provider responses; they do not call Razorpay or need a running PostgreSQL server. PostgreSQL schema migration and Razorpay connectivity still require the local database and credentials described above.

## Frontend integration

The original compiled portal UI is preserved. Its registration and login forms use the API. The frontend donation wizard has been restored to the original prototype simulation and does not create backend donations or initiate a real payment. The backend Razorpay endpoints remain separate and require valid test credentials; no simulated frontend donation should be treated as a database record or a real receipt.

The other legacy dashboard, donor-management, material-donation, and history screens are not fully connected to these API endpoints. Do not treat their existing display data as database-backed. Set `VITE_API_BASE_URL` in the frontend environment if the API is not at `http://localhost:8000`, and add the frontend's exact origin to `FRONTEND_ORIGINS` before starting the API.
