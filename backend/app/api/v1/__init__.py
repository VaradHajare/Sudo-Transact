from fastapi import APIRouter

from app.api.v1 import cases, review, transactions

router = APIRouter(prefix="/v1")
router.include_router(transactions.router, tags=["transactions"])
router.include_router(cases.router, tags=["cases"])
router.include_router(review.router, tags=["review"])
