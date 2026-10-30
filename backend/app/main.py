from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.settings import settings

app = FastAPI(
    title="Hope Foundation Donor API",
    version="1.0.0",
    description="Donor profiles, verified donations, receipts, and material donation workflows.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Razorpay-Signature"],
)
app.include_router(router)
