
"""FastAPI wrapper around the lead pipeline."""

import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

try:
    from .generator import DemoListingStore, LargeListingStore
    from .pipeline import process_lead
except ImportError:
    # прямой запуск из папки app/ — пакет не виден
    from generator import DemoListingStore, LargeListingStore
    from pipeline import process_lead

app = FastAPI(title="Lead-qualifying agent API")
_store = None


def get_store():
    global _store
    if _store is None:
        if os.environ.get("LEAD_AGENT_DATASET", "demo").lower() == "large":
            _store = LargeListingStore()
            _store.build()
        else:
            _store = DemoListingStore()
    return _store


class LeadIn(BaseModel):
    inquiry: str


class ListingOut(BaseModel):
    id: int
    name: str
    region: str
    city: str
    property_type: str
    price: float
    beds: int
    baths: int
    sqft: int
    features: List[str]


@app.get("/health")
def health():
    return {"status": "ok", "dataset_size": get_store().size}


@app.get("/listings")
def listings(limit: int = 20):
    store = get_store()
    cands, total, capped = store.search({}, limit=limit)
    return {"total": total, "listings": cands[:limit]}


@app.post("/lead")
def lead(body: LeadIn):
    try:
        return process_lead(body.inquiry, get_store())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
