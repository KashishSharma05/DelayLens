"""Flight-delay prediction: train, compare and test the models.

Run with:  python -m src.ml.train

Question: 30 minutes before a flight's scheduled departure, can we tell
whether it will take off 30 or more minutes late?

The data grows by one day at a time, so this script is run every day by
the pipeline:
  - the last TEST_DAYS days are held back as the test set,
  - the models learn from every earlier day,
  - the result of the best model is added to data/ml/metrics_history.csv,
    so the website can show how the model changes as the data grows.

How the test is kept honest
  - Time split: learn from earlier days, test on later days.
  - Every feature is known 30 minutes before departure (sql/06_ml_features.sql).
  - A rule of thumb with no model is scored the same way, as the baseline to beat.

With only a few days of data the numbers move a lot from day to day.
They are a first reading, not a settled result.
"""

import json
import os

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

from src.db import get_engine

APP_DATA_DIR = "app/data"
HISTORY_FILE = "data/ml/metrics_history.csv"
TEST_DAYS = 2
MIN_TRAIN_DAYS = 3
RANDOM_STATE = 42
FLAG_SHARE = 0.20  # the share of flights called "high risk"

NUMERIC = [
    "is_international", "dep_hour", "weekday",
    "precipitation_mm", "wind_gusts_kmh", "visibility_m", "temperature_c",
    "has_prev_leg", "prev_leg_late", "prev_arrival_delay_min",
    "airport_now_flights", "airport_now_late_rate",
    "flight_past_flights", "flight_past_late_rate", "airline_past_late_rate", "hour_past_late_rate",
]
CATEGORICAL = ["origin", "airline_name", "dest", "weather_condition"]
FEATURES = NUMERIC + CATEGORICAL

FEATURE_LABELS = {
    "is_international": "International flight",
    "dep_hour": "Hour of departure",
    "weekday": "Day of the week",
    "precipitation_mm": "Rain forecast for the hour",
    "wind_gusts_kmh": "Wind gusts",
    "visibility_m": "Visibility",
    "temperature_c": "Temperature",
    "has_prev_leg": "Aircraft's previous flight is known",
    "prev_leg_late": "Aircraft arrived late from its previous flight",
    "prev_arrival_delay_min": "Previous flight: minutes late on arrival",
    "airport_now_flights": "Airport: departures in the last few hours",
    "airport_now_late_rate": "Airport: late rate in the last few hours",
    "flight_past_flights": "This flight number: days seen before",
    "flight_past_late_rate": "This flight number: late rate on earlier days",
    "airline_past_late_rate": "Airline at this airport: late rate on earlier days",
    "hour_past_late_rate": "This hour at this airport: late rate on earlier days",
    "origin": "Airport",
    "airline_name": "Airline",
    "dest": "Destination",
    "weather_condition": "Weather condition",
}


def load_data():
    data = pd.read_sql("SELECT * FROM ml.flight_features", get_engine(), parse_dates=["flight_date"])
    for column in NUMERIC:
        data[column] = pd.to_numeric(data[column])
    days = sorted(data["flight_date"].unique())
    if len(days) < MIN_TRAIN_DAYS + TEST_DAYS:
        return None, None, days
    test_start = days[-TEST_DAYS]
    return data[data["flight_date"] < test_start], data[data["flight_date"] >= test_start], days


def prepare(scale):
    """Fill missing numbers with the median, and turn each category into 0/1 columns."""
    numeric_steps = [("fill", SimpleImputer(strategy="median"))]
    if scale:  # logistic regression needs numbers on a similar scale; tree models do not
        numeric_steps.append(("scale", StandardScaler()))
    return ColumnTransformer([
        ("numeric", Pipeline(numeric_steps), NUMERIC),
        ("category", OneHotEncoder(handle_unknown="ignore", min_frequency=20, sparse_output=False), CATEGORICAL),
    ])


def build_models():
    return {
        "Logistic regression": Pipeline([
            ("prepare", prepare(scale=True)),
            ("model", LogisticRegression(class_weight="balanced", max_iter=2000)),
        ]),
        "Random forest": Pipeline([
            ("prepare", prepare(scale=False)),
            ("model", RandomForestClassifier(n_estimators=300, min_samples_leaf=10, class_weight="balanced_subsample",
                                             n_jobs=-1, random_state=RANDOM_STATE)),
        ]),
        "Gradient boosting": Pipeline([
            ("prepare", prepare(scale=False)),
            ("model", HistGradientBoostingClassifier(learning_rate=0.05, max_iter=200, class_weight="balanced",
                                                     random_state=RANDOM_STATE)),
        ]),
        # A small neural network: two hidden layers. It needs scaled inputs, like logistic regression.
        "Neural network (MLP)": Pipeline([
            ("prepare", prepare(scale=True)),
            ("model", MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-3, early_stopping=True,
                                    max_iter=300, random_state=RANDOM_STATE)),
        ]),
    }


def score_model(name, y_true, risk):
    """The measures for one set of risk scores (higher score = more likely late)."""
    flagged = risk.rank(method="first", ascending=False) <= round(FLAG_SHARE * len(risk))
    late_found = int(y_true[flagged].sum())
    return {
        "model": name,
        "roc_auc": round(roc_auc_score(y_true, risk), 4),
        "average_precision": round(average_precision_score(y_true, risk), 4),
        "late_flights_found_pct": round(100 * late_found / y_true.sum(), 1),      # recall in the flagged group
        "flagged_that_were_late_pct": round(100 * late_found / flagged.sum(), 1),  # precision in the flagged group
    }


def save_history(row):
    """Keep one line per run date, so re-running on the same data does not add duplicates."""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    history = pd.read_csv(HISTORY_FILE) if os.path.exists(HISTORY_FILE) else pd.DataFrame()
    if not history.empty:
        history = history[history["data_until"] != row["data_until"]]
    history = pd.concat([history, pd.DataFrame([row])], ignore_index=True).sort_values("data_until")
    history.to_csv(HISTORY_FILE, index=False)
    history.to_csv(f"{APP_DATA_DIR}/ml_metrics_history.csv", index=False)


def main():
    train, test, days = load_data()
    if train is None:
        print(f"Only {len(days)} complete days of data; the model needs {MIN_TRAIN_DAYS + TEST_DAYS}. Skipped.")
        return

    y_train, y_test = train["is_late"], test["is_late"]
    print(f"Train: {len(train):,} flights on {train['flight_date'].nunique()} days, {100 * y_train.mean():.1f}% late")
    print(f"Test : {len(test):,} flights on {test['flight_date'].nunique()} days, {100 * y_test.mean():.1f}% late\n")

    results, risks = [], {}

    # Baseline: no model, one rule of thumb: how late has this flight number been on earlier days?
    rule = test["flight_past_late_rate"].fillna(train["is_late"].mean())
    results.append(score_model("Rule of thumb: this flight's past late rate", y_test, rule))

    models = build_models()
    for name, model in models.items():
        if name.startswith("Neural network"):
            # MLPClassifier has no class_weight option, so the same balancing is passed as row weights.
            model.fit(train[FEATURES], y_train, model__sample_weight=compute_sample_weight("balanced", y_train))
        else:
            model.fit(train[FEATURES], y_train)
        risks[name] = pd.Series(model.predict_proba(test[FEATURES])[:, 1], index=test.index)
        results.append(score_model(name, y_test, risks[name]))

    comparison = pd.DataFrame(results)
    print(comparison.to_string(index=False))

    best_name = comparison[comparison["model"].isin(models)].sort_values("average_precision").iloc[-1]["model"]
    best_model, best_risk = models[best_name], risks[best_name]
    best_row = comparison[comparison["model"] == best_name].iloc[0]
    print(f"\nBest model by average precision: {best_name}")

    # Which features matter: shuffle one column at a time and see how much the score drops.
    importance = permutation_importance(best_model, test[FEATURES], y_test, scoring="average_precision",
                                        n_repeats=10, random_state=RANDOM_STATE, n_jobs=-1)
    importance = pd.DataFrame({
        "feature": [FEATURE_LABELS[f] for f in FEATURES],
        "importance": importance.importances_mean.round(4),
    }).sort_values("importance", ascending=False)
    print("\n" + importance.head(8).to_string(index=False))

    # Five equal groups from riskiest to safest.
    groups = pd.DataFrame({"risk": best_risk, "is_late": y_test})
    groups["risk_group"] = pd.qcut(groups["risk"].rank(method="first", ascending=False), 5, labels=range(1, 6))
    groups = groups.groupby("risk_group", observed=True).agg(flights=("is_late", "size"), late_flights=("is_late", "sum")).reset_index()
    groups["late_rate_pct"] = (100 * groups["late_flights"] / groups["flights"]).round(1)

    summary = {
        "data_until": f"{days[-1]:%Y-%m-%d}",
        "days_of_data": len(days),
        "train_flights": len(train), "train_days": int(train["flight_date"].nunique()),
        "test_flights": len(test), "test_days": int(test["flight_date"].nunique()),
        "test_late_pct": round(100 * y_test.mean(), 1),
        "best_model": best_name, "flag_share_pct": int(100 * FLAG_SHARE), "features": len(FEATURES),
    }
    comparison.to_csv(f"{APP_DATA_DIR}/ml_model_comparison.csv", index=False)
    importance.to_csv(f"{APP_DATA_DIR}/ml_feature_importance.csv", index=False)
    groups.to_csv(f"{APP_DATA_DIR}/ml_risk_groups.csv", index=False)
    with open(f"{APP_DATA_DIR}/ml_summary.json", "w", encoding="utf-8") as summary_file:
        json.dump(summary, summary_file, indent=1)
    save_history({
        "data_until": summary["data_until"], "days_of_data": len(days), "train_flights": len(train),
        "test_flights": len(test), "best_model": best_name, "roc_auc": best_row["roc_auc"],
        "average_precision": best_row["average_precision"],
        "late_flights_found_pct": best_row["late_flights_found_pct"],
        "baseline_roc_auc": comparison.iloc[0]["roc_auc"],
    })
    print(f"\nWrote the ml_* files to {APP_DATA_DIR}/ and added a line to {HISTORY_FILE}")


if __name__ == "__main__":
    main()
