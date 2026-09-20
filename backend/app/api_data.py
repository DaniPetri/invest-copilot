"""Read-only data endpoints (SPEC §9): customers, portfolios, products, KID PDFs and the latest eval report."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .config import REPO_ROOT
from .data.store import DataMissingError, Store, get_store
from .evals_view import NoEvalReportError, build_eval_report
from .portfolio_view import build_portfolio_view
from .schemas.evals import EvalReport
from .schemas.portfolio import Customer, PortfolioView
from .schemas.products import Product
from .tools.base import ToolError

router = APIRouter(prefix="/api")

EVAL_REPORTS = REPO_ROOT / "evals" / "reports"


def store_or_503() -> Store:
    store = get_store()
    try:
        store.products  # noqa: B018  (loads the universe; raises when `make data` has not run)
    except DataMissingError as e:
        raise HTTPException(status_code=503, detail=str(e)) from None
    return store


StoreDep = Annotated[Store, Depends(store_or_503)]


@router.get("/customers")
def customers(store: StoreDep) -> list[Customer]:
    return store.customers


@router.get("/customers/{customer_id}/portfolio")
def portfolio(customer_id: str, store: StoreDep) -> PortfolioView:
    try:
        return build_portfolio_view(store, customer_id)
    except (ToolError, KeyError):
        raise HTTPException(status_code=404, detail=f"unknown customer {customer_id}") from None


@router.get("/products")
def products(store: StoreDep) -> list[Product]:
    return store.products


@router.get("/products/{product_id}")
def product(product_id: str, store: StoreDep) -> Product:
    try:
        return store.product(product_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown product {product_id}") from None


@router.get("/kid/{product_id}.pdf")
def kid(product_id: str, store: StoreDep) -> FileResponse:
    """The KID of one product. Only IDs of real products are served, never a path built from the input."""
    try:
        store.product(product_id)
        path = store.kid_path(product_id)
    except (KeyError, DataMissingError):
        raise HTTPException(status_code=404, detail=f"no KID for {product_id}") from None
    return FileResponse(
        path, media_type="application/pdf", filename=f"KID-{product_id}.pdf", content_disposition_type="inline"
    )


@router.get("/evals/latest")
def evals_latest() -> EvalReport:
    try:
        return build_eval_report(EVAL_REPORTS)
    except NoEvalReportError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
