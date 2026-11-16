
"""Streamlit console for the lead-qualifying agent."""

import pandas as pd
import streamlit as st

try:
    from .data import feature_label
    from .pipeline import qualify_lead, process_lead, SAMPLES
    from .generator import DemoListingStore, LargeListingStore
except ImportError:
    # прямой запуск: streamlit run app/ui.py — пакет не виден,
    # импортируем как обычные модули из папки app/
    from data import feature_label
    from pipeline import qualify_lead, process_lead, SAMPLES
    from generator import DemoListingStore, LargeListingStore

st.set_page_config(page_title="Lead-qualifying agent", layout="wide")
st.title("Lead-qualifying agent")
st.caption("Paste a buyer inquiry as it arrives (form, WhatsApp, email). "
           "The agent extracts criteria, scores the lead and matches listings.")

st.sidebar.header("Dataset")
dataset = st.sidebar.radio(
    "Store", ["Demo (20 listings)", "Synthetic (1M)"], index=0)

@st.cache_resource
def get_store(kind):
    if kind == "large":
        store = LargeListingStore()
        with st.spinner("Building 1,000,000 listings from seed..."):
            store.build()
        return store
    return DemoListingStore()

store = get_store("large" if dataset.startswith("Synthetic") else "demo")

choice = st.selectbox("Or use a sample inquiry:", ["(own text)"] + list(SAMPLES.keys()))
# streamlit quirk (found in live testing): a text_area with key= keeps its own
# session-state slot, so presets must be written into st.session_state["ta"]
# rather than passed as value=, which streamlit silently ignores after first run.
if choice != "(own text)":
    st.session_state["ta"] = SAMPLES[choice]

lead_text = st.text_area("Buyer inquiry", height=120, key="ta")

if st.button("🚀 Process lead", type="primary"):
    if not lead_text.strip():
        st.warning("Paste a buyer inquiry first.")
    else:
        card = process_lead(lead_text, store)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Qualification score", "{} /100".format(card["score"]))
        tier_icon = {"HOT": "🔥 HOT", "WARM": "🌤 WARM", "COLD": "❄️ COLD"}[card["tier"]]
        c2.metric("Tier", tier_icon)
        c3.metric("Urgency", card["urgency"])
        c4.metric("Inventory funnel", "{:,} / {:,}".format(
            card["listings_matched"], card["listings_screened"]))

        if card["agent_notes"]:
            for note in card["agent_notes"]:
                st.warning(note)

        st.markdown("**Agent summary:** " + card["summary"])

        with st.expander("Extracted criteria (what the agent understood)"):
            st.caption("Pipeline mode: " + card["pipeline_mode"])
            ex = card["extracted"]
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Budget", "≤ ${:,.0f}".format(ex["budget"]) if ex["budget"] else "not specified")
            col2.metric("Bedrooms", "{}+".format(ex["bedrooms"]) if ex["bedrooms"] else "any")
            col3.metric("Bathrooms", "{}+".format(ex["bathrooms"]) if ex["bathrooms"] else "any")
            col4.metric("Urgency", ex["urgency"])
            st.markdown("**Property type:** " + (ex["property_type"] or "any"))
            st.markdown("**Preferred areas:** " + (", ".join(ex["areas"]) if ex["areas"] else "—"))
            st.markdown("**Buyer profile:** " + (ex["profile"] or "not detected"))
            if ex["must_haves"]:
                st.markdown("**Must-haves:** " + ", ".join(feature_label(f) for f in ex["must_haves"]))
            if ex["nice_to_have"]:
                st.markdown("**Nice to have:** " + ", ".join(feature_label(f) for f in ex["nice_to_have"]))

        st.subheader("Top matches")
        for m in card["matches"]:
            with st.container(border=True):
                st.markdown("**{}** · {}, {}".format(m["name"], m["region"], m["city"]))
                st.caption("${:,.0f} · {} BR / {} BA · {:,} sqft".format(
                    m["price"], m["beds"], m["baths"], m["sqft"]))
                for r in m["reasons"]:
                    st.markdown("{} {}".format(r["icon"], r["text"]))
                st.progress(min(m["score"] / 100.0, 1.0))
                st.caption("Match {:.1f}".format(m["score"]))

        n = card["listings_matched"]
        if n:
            candidates, total, capped = store.search(card["extracted"], limit=200)
            with st.expander("Show matched listings ({} of {:,})".format(len(candidates), n)):
                rows = [{
                    "id": l["id"], "name": l["name"], "region": l["region"],
                    "city": l["city"], "type": l["property_type"],
                    "price": l["price"], "beds": l["beds"], "baths": l["baths"],
                    "sqft": l["sqft"],
                } for l in candidates]
                st.dataframe(pd.DataFrame(rows), use_container_width=True)
