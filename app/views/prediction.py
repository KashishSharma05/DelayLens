"""Delay prediction: can a late departure be spotted 30 minutes ahead?"""

import json
import os

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from common import AMBER, DATA_DIR, PRIMARY, ROSE, chart_layout, load, page_header, tile_title

page_header("Delay prediction", "Can a late departure be spotted 30 minutes before the scheduled time?")

summary_path = os.path.join(DATA_DIR, "ml_summary.json")
if not os.path.exists(summary_path):
    st.info("The model needs at least five complete days of data. It will appear here once they are collected.")
    st.stop()

with open(summary_path, encoding="utf-8") as summary_file:
    summary = json.load(summary_file)
comparison = load("ml_model_comparison")
importance = load("ml_feature_importance")
groups = load("ml_risk_groups")
history = load("ml_metrics_history")

best = comparison[comparison["model"] == summary["best_model"]].iloc[0]
rule = comparison.iloc[0]
base_rate = summary["test_late_pct"]

st.warning(
    f"**Early result.** The model has only **{summary['days_of_data']} days** of flights to learn from. It is retrained "
    f"every morning as a new day arrives, and its scores will move until several weeks of data, with different "
    f"weather, have been collected."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Best model", summary["best_model"])
c2.metric("ROC AUC", f"{best['roc_auc']:.2f}", f"rule of thumb: {rule['roc_auc']:.2f}", delta_color="off")
c3.metric(f"Late flights found in the riskiest {summary['flag_share_pct']}%", f"{best['late_flights_found_pct']:.0f}%",
          f"{summary['flag_share_pct']}% expected by chance", delta_color="off")
c4.metric("High-risk flights that were late", f"{best['flagged_that_were_late_pct']:.0f}%",
          f"{base_rate}% across all flights", delta_color="off")

st.markdown(
    f"Trained on **{summary['train_flights']:,} flights** from the first {summary['train_days']} days and tested on "
    f"**{summary['test_flights']:,} flights** from the last {summary['test_days']} days (up to {summary['data_until']}). "
    f"A flight counts as late when it takes off 30 or more minutes after schedule."
)

# ------------------------------------------------------------------ comparison
left, right = st.columns([3, 2])
with left.container(border=True):
    tile_title("Models compared on the test days")
    table = comparison.copy()
    table["model"] = table["model"].str.replace("Rule of thumb: this flight's past late rate", "Rule of thumb (no model)")
    table = table.rename(columns={
        "model": "Model", "roc_auc": "AUC", "average_precision": "Avg precision",
        "late_flights_found_pct": f"Late found in top {summary['flag_share_pct']}% (%)",
        "flagged_that_were_late_pct": "High-risk that were late (%)",
    })
    st.dataframe(table, width="stretch", hide_index=True)
    st.caption(
        "The first row is not a model: it ranks flights by how often the same flight number was late on earlier days. "
        f"The best model beats it by {best['roc_auc'] - rule['roc_auc']:.2f} AUC, a small margin: with this little "
        "data, a flight's own track record already says most of what can be said."
    )

with right.container(border=True):
    tile_title("Late rate in each risk group (best model)")
    figure = px.bar(groups, x="risk_group", y="late_rate_pct", text="late_rate_pct", color_discrete_sequence=[PRIMARY],
                    labels={"risk_group": "Risk group (1 = riskiest 20%)", "late_rate_pct": "Late (%)"})
    figure.add_hline(y=base_rate, line_dash="dash", line_color=ROSE, annotation_text=f"all flights: {base_rate}%")
    figure.update_xaxes(dtick=1)
    st.plotly_chart(chart_layout(figure, height=290), width="stretch")

# ------------------------------------------------------------------ importance
left, right = st.columns([3, 2])
with left.container(border=True):
    tile_title("What the model relies on")
    top = importance.head(10).iloc[::-1]
    figure = go.Figure(go.Bar(x=top["importance"], y=top["feature"], orientation="h", marker_color=AMBER))
    figure.update_xaxes(title="Drop in average precision when the column is shuffled")
    st.plotly_chart(chart_layout(figure, height=340), width="stretch")

with right.container(border=True):
    tile_title("How the model changes as data grows")
    if len(history) >= 2:
        figure = go.Figure()
        figure.add_scatter(x=history["data_until"], y=history["roc_auc"], mode="lines+markers", name="Best model", line=dict(color=PRIMARY))
        figure.add_scatter(x=history["data_until"], y=history["baseline_roc_auc"], mode="lines+markers", name="Rule of thumb",
                           line=dict(color=ROSE, dash="dash"))
        figure.update_yaxes(title="ROC AUC on the last two days")
        st.plotly_chart(chart_layout(figure, height=300), width="stretch")
    else:
        st.write("One line is added here every day the model is retrained. After a few days this becomes a chart of "
                 "the score over time.")
        st.dataframe(history[["data_until", "days_of_data", "train_flights", "best_model", "roc_auc"]],
                     width="stretch", hide_index=True)

st.subheader("How the test is kept honest")
st.markdown(
    """
- **Time split.** The models learn from earlier days and are tested on the last two, as they would be used.
- **Only what is known 30 minutes before departure.** Track records come from previous days; the state of the airport
  comes from flights scheduled at least an hour earlier; the aircraft's previous flight has already flown.
- **A baseline to beat.** A rule with no model is scored in exactly the same way.
- **No official cause exists** for a delay in India, so the model predicts lateness, not its reason.
"""
)
st.caption("Models: logistic regression, random forest, gradient boosting and a neural network (MLP), all scikit-learn. "
           "Code: sql/06_ml_features.sql and src/ml/train.py.")
