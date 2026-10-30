# Hope Foundation Donor Portal

The original donor portal UI is preserved. Registration and login use the FastAPI donor API. The donation wizard is restored to the original prototype simulation; it does not initiate a real payment or write donations to the backend. The remaining legacy dashboard and donor-management screens are not fully API-connected.

## Development

```bash
npm install
npm run dev
npm run build
```

In Figma Make, the development server is started and supervised automatically.

## Frontend configuration

The frontend uses `VITE_API_BASE_URL` to select the backend API and defaults to `http://localhost:8000`. Put the variable in the Vite environment before starting the dev server if your API runs elsewhere. Authentication tokens are kept for the current browser session. Razorpay checkout is not connected to the frontend; donations use the original clearly labelled prototype simulation.

The existing UI is supplied as compiled assets, so a small Vite plugin applies targeted, checked transformations to the original bundles at development and build time. It does not replace or redesign the portal.

## Backend

The PostgreSQL-backed FastAPI service, setup and pgAdmin instructions, environment configuration, migrations, administrator bootstrap, API documentation, and tests are described in [`backend/README.md`](./backend/README.md).
