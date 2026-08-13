"""Generates the collection_activity table: escalating outreach sequences on overdue
invoices, with cadence and outcome fulfillment driven by the merchant's payer archetype."""
import numpy as np
import pandas as pd

from src.utils import config as cfg

ESCALATION_LADDER = ["Reminder", "Email", "Phone", "Escalation", "Payment Promise"]
CHANNEL_BY_TYPE = {
    "Reminder": "Email", "Email": "Email", "Phone": "Phone",
    "Escalation": "Phone", "Payment Promise": "WhatsApp", "Dispute": "Email", "Resolution": "Phone",
}
STEPS_BY_ARCHETYPE = {"Excellent": (1, 2), "Good": (1, 3), "Moderate": (2, 4), "High-risk": (3, 6)}

NOTE_TEMPLATES = {
    "Reminder": "Automated reminder sent for invoice {inv} due {due}.",
    "Email": "Followed up via email regarding outstanding invoice {inv}.",
    "Phone": "Called merchant to discuss overdue invoice {inv}.",
    "Escalation": "Escalated invoice {inv} to account manager for non-payment.",
    "Payment Promise": "Merchant committed to paying invoice {inv} by {promise}.",
    "Dispute": "Merchant disputed charges on invoice {inv}.",
    "Resolution": "Payment issue on invoice {inv} resolved with merchant.",
}


def generate_collection_activity(invoices: pd.DataFrame, payer_archetypes: dict) -> pd.DataFrame:
    rng = cfg.new_rng(offset=9)

    eligible = invoices[invoices["invoice_status"] == "Overdue"].copy()
    eligible = pd.concat([eligible, invoices[(invoices["payment_status"] == "Partially Paid")]]).drop_duplicates("invoice_id")
    eligible["archetype"] = eligible["merchant_id"].map(payer_archetypes)

    rows = []
    seq = 1
    for _, inv in eligible.iterrows():
        archetype = inv["archetype"]
        lo, hi = STEPS_BY_ARCHETYPE.get(archetype, (1, 3))
        n_steps = rng.integers(lo, hi + 1)
        ladder = ESCALATION_LADDER[:n_steps]

        eventually_paid = inv["payment_status"] in ("Paid", "Partially Paid")
        fulfillment_prob = {"Excellent": 0.95, "Good": 0.8, "Moderate": 0.5, "High-risk": 0.25}.get(archetype, 0.5)

        activity_date = pd.Timestamp(inv["due_date"]) + pd.Timedelta(days=int(rng.integers(3, 10)))
        for step_i, activity_type in enumerate(ladder):
            is_last = step_i == len(ladder) - 1
            if is_last and eventually_paid and rng.random() < fulfillment_prob:
                outcome = "Payment Received" if activity_type != "Payment Promise" else "Payment Received"
            elif activity_type == "Payment Promise":
                outcome = "Promise to Pay" if rng.random() < fulfillment_prob else "No Response"
            elif activity_type == "Escalation":
                outcome = rng.choice(["Escalated", "Disputed", "No Response"], p=[0.5, 0.2, 0.3])
            else:
                outcome = rng.choice(["No Response", "Promise to Pay", "Disputed"], p=[0.55, 0.35, 0.10])

            promised_payment_date = pd.NaT
            promised_amount = np.nan
            if activity_type == "Payment Promise" or outcome == "Promise to Pay":
                promised_payment_date = activity_date + pd.Timedelta(days=int(rng.integers(3, 15)))
                promised_amount = round(float(inv["total_invoice_amount"]) * rng.uniform(0.5, 1.0), 2)

            collector = rng.choice(cfg.COLLECTORS)
            channel = CHANNEL_BY_TYPE.get(activity_type, "Email")
            note = NOTE_TEMPLATES[activity_type].format(
                inv=inv["invoice_id"], due=pd.Timestamp(inv["due_date"]).date(),
                promise=promised_payment_date.date() if pd.notna(promised_payment_date) else "N/A",
            )

            rows.append({
                "collection_id": f"COL{str(seq).zfill(7)}",
                "merchant_id": inv["merchant_id"],
                "invoice_id": inv["invoice_id"],
                "activity_date": activity_date,
                "activity_type": activity_type,
                "contact_channel": channel,
                "collector": collector,
                "outcome": outcome,
                "promised_payment_date": promised_payment_date,
                "promised_amount": promised_amount,
                "notes": note,
            })
            seq += 1
            activity_date = activity_date + pd.Timedelta(days=int(rng.integers(5, 15)))

    return pd.DataFrame(rows)
