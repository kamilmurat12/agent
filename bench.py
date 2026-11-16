
"""Benchmark: build the 1M-listing store, measure memory and response times."""

import os
import time

import psutil

from app.generator import LargeListingStore
from app.pipeline import process_lead

proc = psutil.Process(os.getpid())
rss_before = proc.memory_info().rss / 1024 / 1024

store = LargeListingStore()
t0 = time.perf_counter()
store.build()
build_s = time.perf_counter() - t0
rss_after = proc.memory_info().rss / 1024 / 1024

print("Listings generated : {:,}".format(store.size))
print("Build time         : {:.2f} s".format(build_s))
print("RSS before/after   : {:.0f} MB -> {:.0f} MB (delta {:.0f} MB)".format(
    rss_before, rss_after, rss_after - rss_before))
print()

QUERIES = [
    ("reloc family", "We are relocating and need a 3 bedroom house under $520k, "
                     "good school district and a yard, South Congress area, within 2 months."),
    ("condo budget", "Budget around 380000, 2 bed condo downtown, modern and walkable."),
    ("waterfront", "Budget 2 million, 5 bedrooms, must have pool and home office, waterfront."),
]

for label, text in QUERIES:
    t0 = time.perf_counter()
    card = process_lead(text, store)
    dt = (time.perf_counter() - t0) * 1000
    print("[{:<14}] {:>7.0f} ms | score {:>3} {} | funnel {:,}/{:,}".format(
        label, dt, card["score"], card["tier"],
        card["listings_matched"], card["listings_screened"]))

print()
print("Determinism check: rebuilding from the same seed yields the same inventory.")
store2 = LargeListingStore()
store2.build()
print("  identical arrays:", bool((store2.feat == store.feat).all() and
                                  (store2.price == store.price).all()))
