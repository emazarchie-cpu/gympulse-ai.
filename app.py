import os

import joblib
import pandas as pd
import streamlit as st


# -----------------------------------------
# 1. PAGE CONFIGURATION
# -----------------------------------------

st.set_page_config(
    page_title="GymPulse AI",
    page_icon="💪",
    layout="wide"
)


# -----------------------------------------
# 2. LOAD TRAINED MODEL
# -----------------------------------------

MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "models",
    "gympulse_model.joblib"
)


@st.cache_resource
def load_model():
    return joblib.load(MODEL_PATH)


try:
    model = load_model()
except Exception as error:
    st.error(
        "The trained model could not be loaded. "
        "Check that models/gympulse_model.joblib exists "
        "in your repository."
    )
    st.stop()


# -----------------------------------------
# 3. PREDICTION FUNCTION
# -----------------------------------------

def prepare_member_data(data):
    """
    Prepare raw membership records for the trained model.
    Accepts either a single record or a DataFrame.
    """

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
        column for column in required_columns
        if column not in data.columns
    ]

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing_columns)
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
    """
    Return cancellation probabilities and
    provisional risk categories.
    """

    features = prepare_member_data(data)

    probabilities = model.predict_proba(features)[:, 1]

    results = data.copy()

    results["cancellation_probability"] = probabilities

    results["risk_category"] = [
        "High" if probability >= 0.50
        else "Medium" if probability >= 0.30
        else "Low"
        for probability in probabilities
    ]

    return results


# -----------------------------------------
# 4. APPLICATION HEADER
# -----------------------------------------

st.title("💪 GymPulse AI")

st.subheader(
    "Experimental Gym Membership Cancellation-Risk Assessment"
)

st.info(
    "Educational prototype using a model trained on synthetic data. "
    "Its predictions have not been validated on real gym members."
)


# -----------------------------------------
# 5. SIDEBAR NAVIGATION
# -----------------------------------------

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Member Assessment",
        "Batch Assessment",
        "About the Model"
    ]
)


# -----------------------------------------
# 6. DASHBOARD
# -----------------------------------------

if page == "Dashboard":

    st.header("Cancellation-Risk Dashboard")

    st.write(
        "Assess an individual member or upload a CSV file "
        "to explore cancellation-risk estimates."
    )

    col1, col2, col3 = st.columns(3)

    col1.metric("Model", "Logistic Regression")
    col2.metric("Risk Threshold", "30%")
    col3.metric("Input Features", "5")

    st.markdown("### How it works")

    st.markdown(
        """
        1. Enter membership and attendance information.
        2. GymPulse AI processes the member's features.
        3. The trained model estimates cancellation probability.
        4. The app assigns a provisional risk category.
        """
    )

    st.warning(
        "A risk category is an experimental model output, "
        "not a confirmed prediction of a member's future behaviour."
    )


# -----------------------------------------
# 7. INDIVIDUAL MEMBER ASSESSMENT
# -----------------------------------------

elif page == "Member Assessment":

    st.header("Individual Member Assessment")

    with st.form("member_assessment_form"):

        membership_type = st.selectbox(
            "Membership type",
            ["Monthly", "Quarterly", "Annual"]
        )

        col1, col2 = st.columns(2)

        with col1:
            days_since_last_visit = st.number_input(
                "Days since last visit",
                min_value=0,
                max_value=365,
                value=7
            )

            visits_previous_30_days = st.number_input(
                "Visits in the previous 30 days",
                min_value=0,
                max_value=100,
                value=10
            )

            renewal_due_days = st.number_input(
                "Days until renewal",
                min_value=0,
                max_value=365,
                value=14
            )

        with col2:
            visits_last_30_days = st.number_input(
                "Visits in the most recent 30 days",
                min_value=0,
                max_value=100,
                value=5
            )

            pt_sessions_attended = st.number_input(
                "Personal-training sessions attended",
                min_value=0,
                max_value=100,
                value=2
            )

        submitted = st.form_submit_button(
            "Assess Member"
        )

    if submitted:

        member = pd.DataFrame([{
            "membership_type": membership_type,
            "days_since_last_visit": days_since_last_visit,
            "visits_previous_30_days": visits_previous_30_days,
            "visits_last_30_days": visits_last_30_days,
            "renewal_due_days": renewal_due_days,
            "pt_sessions_attended": pt_sessions_attended
        }])

        try:
            result = assess_members(member).iloc[0]

            probability = result["cancellation_probability"]
            risk = result["risk_category"]

            st.markdown("### Assessment Results")

            col1, col2 = st.columns(2)

            col1.metric(
                "Estimated Cancellation Probability",
                f"{probability:.1%}"
            )

            col2.metric(
                "Provisional Risk Category",
                risk
            )

            st.progress(float(probability))

            attendance_change = (
                visits_last_30_days
                - visits_previous_30_days
            )

            st.write(
                f"Attendance change: {attendance_change:+} visits"
            )

            if attendance_change < 0:
                st.write(
                    "Attendance has declined compared with "
                    "the previous 30-day period."
                )
            elif attendance_change > 0:
                st.write(
                    "Attendance has increased compared with "
                    "the previous 30-day period."
                )
            else:
                st.write(
                    "Attendance is unchanged between the two periods."
                )

            st.caption(
                "This estimate is generated by an experimental model "
                "trained on synthetic data."
            )

        except Exception as error:
            st.error(f"Assessment failed: {error}")


# -----------------------------------------
# 8. BATCH CSV ASSESSMENT
# -----------------------------------------

elif page == "Batch Assessment":

    st.header("Batch Member Assessment")

    st.write(
        "Upload a CSV containing membership and attendance records."
    )

    st.markdown(
        """
        **Required columns:**

        - `membership_type`
        - `days_since_last_visit`
        - `visits_previous_30_days`
        - `visits_last_30_days`
        - `renewal_due_days`
        - `pt_sessions_attended`
        """
    )

    uploaded_file = st.file_uploader(
        "Upload membership CSV",
        type=["csv"]
    )

    if uploaded_file is not None:

        try:
            uploaded_data = pd.read_csv(uploaded_file)

            st.write("Uploaded data preview")
            st.dataframe(
                uploaded_data.head(),
                use_container_width=True
            )

            if st.button("Assess All Members"):

                results = assess_members(uploaded_data)

                total_members = len(results)

                high_risk = (
                    results["risk_category"] == "High"
                ).sum()

                medium_risk = (
                    results["risk_category"] == "Medium"
                ).sum()

                low_risk = (
                    results["risk_category"] == "Low"
                ).sum()

                col1, col2, col3, col4 = st.columns(4)

                col1.metric("Members Assessed", total_members)
                col2.metric("High Risk", int(high_risk))
                col3.metric("Medium Risk", int(medium_risk))
                col4.metric("Low Risk", int(low_risk))

                st.markdown("### Assessment Results")

                st.dataframe(
                    results,
                    use_container_width=True
                )

                csv_output = results.to_csv(
                    index=False
                ).encode("utf-8")

                st.download_button(
                    label="Download Assessment Results",
                    data=csv_output,
                    file_name="gympulse_assessment_results.csv",
                    mime="text/csv"
                )

        except Exception as error:
            st.error(
                "Could not process the uploaded file. "
                f"Check its columns and values. Details: {error}"
            )


# -----------------------------------------
# 9. MODEL INFORMATION
# -----------------------------------------

elif page == "About the Model":

    st.header("About GymPulse AI")

    st.write(
        "GymPulse AI is an educational machine-learning project "
        "exploring gym membership cancellation-risk assessment."
    )

    st.markdown("### Model details")

    st.markdown(
        """
        - **Algorithm:** Logistic Regression
        - **Training data:** Synthetic gym membership records
        - **Training features:** Five
        - **Candidate classification threshold:** 0.30
        - **Development evaluation:** Train, validation and test splits
        """
    )

    st.markdown("### Recorded test results")

    metrics = pd.DataFrame({
        "Metric": [
            "Accuracy",
            "Precision",
            "Recall",
            "F1-score",
            "ROC-AUC"
        ],
        "Test result": [
            "59.0%",
            "44.9%",
            "75.7%",
            "56.4%",
            "65.1%"
        ]
    })

    st.dataframe(
        metrics,
        hide_index=True,
        use_container_width=True
    )

    st.warning(
        "These results are specific to the synthetic dataset. "
        "They do not demonstrate predictive performance on real "
        "gym membership data. Earlier test-set exploration also "
        "means the final test results should be interpreted cautiously."
    )

    st.markdown("### Responsible use")

    st.write(
        "Risk estimates should be treated as decision-support "
        "signals for experimentation, not definitive statements "
        "about individual members. The model should be evaluated "
        "on suitable real-world data before operational use."
    )


# -----------------------------------------
# 10. FOOTER
# -----------------------------------------

st.divider()

st.caption(
    "GymPulse AI | Machine Learning Portfolio Project | "
    "Experimental prototype"
)
