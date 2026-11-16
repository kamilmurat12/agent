
"""PDF export of a lead card (reportlab). One page: metrics, summary,
top matches with reasons, agent notes — the artifact an agent forwards
to the client."""

import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def build_pdf(card, path):
    width, height = A4
    margin = 18 * mm
    c = canvas.Canvas(path, pagesize=A4)
    y = height - margin

    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, y, "Lead qualification report")
    y -= 8 * mm
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.drawString(margin, y, "generated {} · pipeline: {} · search: {}".format(
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        card.get("pipeline_mode", "-"),
        card.get("search_backend", "-")))
    c.setFillColorRGB(0, 0, 0)
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, "Summary: {} / 100 — {}".format(card["score"], card["tier"]))
    y -= 7 * mm
    c.setFont("Helvetica", 10)
    for line in _wrap(card["summary"], 95):
        c.drawString(margin, y, line)
        y -= 5.5 * mm
    y -= 2 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Funnel: {:,} of {:,} listings passed hard filters{}".format(
        card["listings_matched"], card["listings_screened"],
        " (capped ranking slice)" if card.get("candidates_capped") else ""))
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin, y, "Top matches")
    y -= 7 * mm
    for m in card["matches"]:
        if y < 30 * mm:
            c.showPage()
            y = height - margin
        c.setFont("Helvetica-Bold", 11)
        c.drawString(margin, y, "{} — ${:,.0f}".format(m["name"], m["price"]))
        y -= 5.5 * mm
        c.setFont("Helvetica", 9)
        meta = "{}, {} · {} BR / {} BA · {:,} sqft · match {:.1f}".format(
            m["region"], m["city"], m["beds"], m["baths"], m["sqft"], m["score"])
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawString(margin, y, meta)
        c.setFillColorRGB(0, 0, 0)
        y -= 5.5 * mm
        for r in m["reasons"]:
            line = "{} {}".format(r["icon"], r["text"])
            for sub in _wrap(line, 100):
                c.drawString(margin + 3 * mm, y, sub)
                y -= 5 * mm
        y -= 3 * mm

    if card.get("agent_notes"):
        if y < 45 * mm:
            c.showPage()
            y = height - margin
        c.setFont("Helvetica-Bold", 11)
        c.drawString(margin, y, "Agent notes")
        y -= 6 * mm
        c.setFont("Helvetica", 9)
        for note in card["agent_notes"]:
            for sub in _wrap("• " + note, 100):
                c.drawString(margin, y, sub)
                y -= 5 * mm
    c.save()
    return path


def _wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines
