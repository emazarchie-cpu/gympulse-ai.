"""GymPulse AI · the risk model: a demonstration model trained on simulated (synthetic) members.

Shared by the app (app.py) and scheduled jobs (e.g. scripts/send_owner_weekly.py), so both score members the
same way.
"""
import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

import numpy as np

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression

@st.cache_resource
def load_model():
    """Demonstration model trained on simulated members."""
    rng = np.random.default_rng(42)
    n = 4000
    plan = rng.choice(["Monthly", "Quarterly", "Annual"], size=n, p=[0.55, 0.25, 0.20])
    base = rng.integers(0, 21, n)
    gap = 30 / np.maximum(base, 1)
    lapsing = rng.random(n) < 0.22
    days = np.where(lapsing, rng.integers(7, 60, n),
                    np.minimum(rng.exponential(gap), 45)).astype(int)
    recent = np.where(lapsing, np.maximum(0, base - rng.integers(3, 15, n)),
                      np.clip(base + rng.integers(-3, 4, n), 0, 20))
    change = recent - base
    renew = rng.integers(0, 91, n)
    pt = rng.integers(0, 13, n)

    z = (-2.5 + 0.10 * days - 0.11 * change - 0.12 * pt - 0.04 * renew
         + np.where(plan == "Monthly", 0.5, 0)
         + np.where(plan == "Annual", -0.4, 0)
         + rng.normal(0, 0.6, n))
    label = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)

    training_data = pd.DataFrame({
        "membership_type": plan,
        "days_since_last_visit": days,
        "attendance_change": change,
        "renewal_due_days": renew,
        "pt_sessions_attended": pt,
    })
    preprocessing = ColumnTransformer([
        ("membership", OneHotEncoder(handle_unknown="ignore"), ["membership_type"]),
        ("numeric", StandardScaler(), ["days_since_last_visit", "attendance_change",
                                       "renewal_due_days", "pt_sessions_attended"]),
    ])
    pipeline = Pipeline([
        ("preprocessing", preprocessing),
        ("classifier", LogisticRegression(max_iter=1000)),
    ])
    pipeline.fit(training_data, label)
    return pipeline



model = load_model()
def prepare_member_data(data):
    """Validate member records and prepare model features."""

    data = data.copy()

    required_columns = [
        "membership_type",
        "days_since_last_visit",
        "visits_previous_30_days",
        "visits_last_30_days",
        "renewal_due_days",
        "pt_sessions_attended"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in data.columns
    ]

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing_columns)
        )

    numeric_columns = [
        "days_since_last_visit",
        "visits_previous_30_days",
        "visits_last_30_days",
        "renewal_due_days",
        "pt_sessions_attended"
    ]

    for column in numeric_columns:
        data[column] = pd.to_numeric(
            data[column],
            errors="raise"
        )

        if data[column].isna().any():
            raise ValueError(
                f"{column} contains missing values."
            )

        if (data[column] < 0).any():
            raise ValueError(
                f"{column} cannot contain negative values."
            )

    if not data["membership_type"].isin(
        ["Monthly", "Quarterly", "Annual"]
    ).all():
        raise ValueError(
            "Membership type must be Monthly, Quarterly, or Annual."
        )

    data["attendance_change"] = (
        data["visits_last_30_days"]
        - data["visits_previous_30_days"]
    )

    model_features = [
        "membership_type",
        "days_since_last_visit",
        "attendance_change",
        "renewal_due_days",
        "pt_sessions_attended"
    ]

    return data[model_features]

def assess_members(data):
    """Generate cancellation probabilities and provisional risk labels."""

    if data.empty:
        raise ValueError("The uploaded dataset contains no members.")

    # Score every plan on the three plan types the model was trained on
    features = prepare_member_data(
        data.assign(membership_type=data["membership_type"].map(gw.model_plan)))

    # Never 0% or 100%: an estimate can't be certain, and "100%" reads as a mistake to an owner
    probabilities = np.clip(model.predict_proba(features)[:, 1], 0.01, 0.99)

    results = data.copy()

    results["cancellation_probability"] = probabilities

    results["risk_category"] = [
        "High" if probability >= 0.50
        else "Medium" if probability >= 0.30
        else "Low"
        for probability in probabilities
    ]

    return results
