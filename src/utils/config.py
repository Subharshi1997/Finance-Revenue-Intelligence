"""Shared constants, RNG seeding and lookup tables used by every data-generation module."""
import numpy as np
import pandas as pd

SEED = 42
COMPANY_NAME = "Chekk"
CURRENCY = "INR"

START_DATE = pd.Timestamp("2024-08-01")
END_DATE = pd.Timestamp("2026-07-31")
MONTH_STARTS = pd.date_range(START_DATE, END_DATE, freq="MS")

INDUSTRIES = [
    "Fashion & Apparel",
    "Beauty & Personal Care",
    "Electronics",
    "Home & Living",
    "Food & Beverage",
    "Health & Wellness",
    "Jewellery & Accessories",
    "Sports & Fitness",
]

INDUSTRY_AOV = {
    "Fashion & Apparel": 1500,
    "Beauty & Personal Care": 900,
    "Electronics": 4500,
    "Home & Living": 2200,
    "Food & Beverage": 700,
    "Health & Wellness": 1100,
    "Jewellery & Accessories": 3500,
    "Sports & Fitness": 1800,
}

SEGMENTS = ["Enterprise", "Mid-Market", "SMB", "Long-tail"]
SEGMENT_WEIGHTS = [0.05, 0.15, 0.40, 0.40]

SEGMENT_MONTHLY_TXN_RANGE = {
    "Enterprise": (25, 100),
    "Mid-Market": (8, 32),
    "SMB": (5, 14),
    "Long-tail": (3, 6),
}

SEGMENT_AOV_MULTIPLIER = {
    "Enterprise": 1.4,
    "Mid-Market": 1.2,
    "SMB": 1.0,
    "Long-tail": 0.85,
}

SEGMENT_PAYMENT_TERMS = {
    "Enterprise": [45, 60],
    "Mid-Market": [30, 45],
    "SMB": [15, 30],
    "Long-tail": [15, 30],
}

SEGMENT_FEE_RANGE = {
    "Enterprise": (1.5, 2.0),
    "Mid-Market": (1.8, 2.3),
    "SMB": (2.2, 2.8),
    "Long-tail": (2.5, 3.5),
}

SEGMENT_PRICING_PLAN_WEIGHTS = {
    "Enterprise": {"Enterprise": 0.55, "Custom": 0.40, "Growth": 0.05, "Standard": 0.0},
    "Mid-Market": {"Growth": 0.45, "Enterprise": 0.35, "Custom": 0.10, "Standard": 0.10},
    "SMB": {"Standard": 0.45, "Growth": 0.45, "Enterprise": 0.10, "Custom": 0.0},
    "Long-tail": {"Standard": 0.75, "Growth": 0.25, "Enterprise": 0.0, "Custom": 0.0},
}

PRICING_PLAN_SUBSCRIPTION_FEE = {
    "Standard": 0,
    "Growth": 999,
    "Enterprise": 4999,
    "Custom": 9999,
}

MERCHANT_STATUS_WEIGHTS = {"Active": 0.87, "Churned": 0.11, "Suspended": 0.02}

CITY_STATE = [
    ("Mumbai", "Maharashtra"), ("Pune", "Maharashtra"), ("Delhi", "Delhi"),
    ("Bengaluru", "Karnataka"), ("Chennai", "Tamil Nadu"), ("Hyderabad", "Telangana"),
    ("Kolkata", "West Bengal"), ("Ahmedabad", "Gujarat"), ("Surat", "Gujarat"),
    ("Jaipur", "Rajasthan"), ("Lucknow", "Uttar Pradesh"), ("Chandigarh", "Chandigarh"),
    ("Kochi", "Kerala"), ("Indore", "Madhya Pradesh"), ("Gurugram", "Haryana"),
    ("Noida", "Uttar Pradesh"), ("Coimbatore", "Tamil Nadu"), ("Nagpur", "Maharashtra"),
]

COUNTRY = "India"

ACCOUNT_MANAGERS = [
    "Ananya Sharma", "Rohan Mehta", "Priya Nair", "Karan Malhotra", "Sneha Iyer",
    "Vikram Rao", "Ishita Kapoor", "Aditya Bose", "Neha Kulkarni", "Arjun Reddy",
    "Divya Menon", "Siddharth Joshi", "Pooja Agarwal", "Rahul Verma", "Meera Pillai",
    "Kabir Chatterjee", "Tanvi Shah",
]

COLLECTORS = [
    "Sanjay Kumar", "Ritu Bansal", "Manish Tiwari", "Anjali Desai", "Vivek Nair",
    "Shweta Gupta", "Amit Saxena", "Nandini Rajan", "Farhan Sheikh",
]

PAYER_ARCHETYPES = ["Excellent", "Good", "Moderate", "High-risk"]
PAYER_ARCHETYPE_WEIGHTS = [0.25, 0.35, 0.25, 0.15]

PAYMENT_METHODS = ["UPI", "Card", "NetBanking", "Wallet", "COD"]
PAYMENT_METHOD_WEIGHTS = [0.55, 0.25, 0.08, 0.07, 0.05]

FESTIVE_MONTH_MULTIPLIER = {10: 1.35, 11: 1.5, 12: 1.05, 1: 1.25}

GST_RATE = 0.18


def new_rng(offset=0):
    """Return a deterministic numpy Generator derived from the global SEED."""
    return np.random.default_rng(SEED + offset)


def growth_multiplier(month_start: pd.Timestamp) -> float:
    idx = (month_start.year - START_DATE.year) * 12 + (month_start.month - START_DATE.month)
    total_months = len(MONTH_STARTS)
    return 0.85 + (idx / max(total_months - 1, 1)) * 0.40


def seasonality_multiplier(month_start: pd.Timestamp) -> float:
    return FESTIVE_MONTH_MULTIPLIER.get(month_start.month, 1.0)


def derive_payer_archetypes(merchant_ids) -> dict:
    """Deterministically assign a stable payer archetype per merchant_id."""
    rng = new_rng(offset=777)
    merchant_ids = sorted(merchant_ids)
    choices = rng.choice(PAYER_ARCHETYPES, size=len(merchant_ids), p=PAYER_ARCHETYPE_WEIGHTS)
    return dict(zip(merchant_ids, choices))
