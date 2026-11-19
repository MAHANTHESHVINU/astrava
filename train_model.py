import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "ICRISAT-District Level Data.csv"
HORIZONTAL_PATH = ROOT / "horizontal_crop_vertical_year_report.xls"
MODEL_PATH = ROOT / "crop_yield_model.joblib"
METRICS_PATH = ROOT / "model_metrics.json"

CROP_MAP = {
    "rice": "RICE YIELD (Kg per ha)",
    "wheat": "WHEAT YIELD (Kg per ha)",
    "sorghum": "SORGHUM YIELD (Kg per ha)",
    "ragi": "FINGER MILLET YIELD (Kg per ha)",
    "maize": "MAIZE YIELD (Kg per ha)",
    "sunflower": "SUNFLOWER YIELD (Kg per ha)",
    "groundnut": "GROUNDNUT YIELD (Kg per ha)",
    "soybean": "SOYABEAN YIELD (Kg per ha)",
    "cotton": "COTTON YIELD (Kg per ha)",
    "chickpea": "CHICKPEA YIELD (Kg per ha)",
    "sugarcane": "SUGARCANE YIELD (Kg per ha)",
}

HORIZONTAL_MAP = {
    "Rice": "rice",
    "Wheat": "wheat",
    "Jowar": "sorghum",
    "Ragi": "ragi",
    "Maize": "maize",
    "Sunflower": "sunflower",
    "Groundnut": "groundnut",
    "Soyabean": "soybean",
    "Cotton(lint)": "cotton",
    "Gram": "chickpea",
    "Sugarcane": "sugarcane",
}


def normalize_year(value):
    match = re.match(r"\s*(\d{4})", str(value))
    return int(match.group(1)) if match else pd.NA


def clean_name(value):
    return re.sub(r"^\d+\.\s*", "", str(value)).strip()


def crop_slug(value):
    value = re.sub(r"\([^)]*\)", "", str(value))
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    return value.strip("_").lower()


def load_primary():
    df = pd.read_csv(CSV_PATH)
    rows = []
    area_columns = {crop: column.replace(" YIELD ", " AREA ") for crop, column in CROP_MAP.items()
                    if column.replace(" YIELD ", " AREA ") in df.columns}

    for crop, yield_column in CROP_MAP.items():
        subset = pd.DataFrame({
            "crop": crop,
            "year": pd.to_numeric(df["Year"], errors="coerce"),
            "state": df["State Name"].astype(str),
            "district": df["Dist Name"].astype(str),
            "area": pd.to_numeric(df[area_columns[crop]], errors="coerce") if crop in area_columns else np.nan,
            "yield": pd.to_numeric(df[yield_column], errors="coerce"),
        })
        subset = subset[(subset["yield"] > 0) & subset["year"].notna()]
        rows.append(subset)
    return pd.concat(rows, ignore_index=True)


def load_horizontal():
    table = pd.read_html(HORIZONTAL_PATH)[0]
    table.columns = pd.MultiIndex.from_tuples(table.columns)
    state = table[("State", "State", "State")] if ("State", "State", "State") in table.columns else table.iloc[:, 0]
    district = table[("District", "District", "District")] if ("District", "District", "District") in table.columns else table.iloc[:, 1]
    year_raw = table[("Year", "Year", "Year")] if ("Year", "Year", "Year") in table.columns else table.iloc[:, 2]

    rows = []
    for horizontal_crop in sorted(set(column[0] for column in table.columns
                                    if str(column[0]) not in {"State", "District", "Year"})):
        crop = crop_slug(horizontal_crop)
        matching = [
            col for col in table.columns
            if col[0] == horizontal_crop and str(col[2]).startswith("Yield")
        ]
        for column in matching:
            if not str(column[2]).startswith("Yield (Tonne/Hectare)"):
                continue
            season = column[1]
            yield_tonnes = pd.to_numeric(table[column], errors="coerce")
            valid = yield_tonnes.notna() & (yield_tonnes > 0)
            part = pd.DataFrame({
                "crop": crop,
                "year": [normalize_year(value) for value in year_raw],
                "state": [clean_name(value) for value in state],
                "district": [clean_name(value) for value in district],
                "area": np.nan,
                "yield": (yield_tonnes * 1000).round(3),
                "season": season,
            })
            part = part[valid & part["year"].notna()].copy()
            rows.append(part)
    return pd.concat(rows, ignore_index=True)


def train():
    primary = load_primary()
    horizontal = load_horizontal()

    # Keep the target unit consistent: kg/hectare. Horizontal values are converted above.
    data = pd.concat([
        primary.assign(source="icrisat"),
        horizontal.assign(source="horizontal"),
    ], ignore_index=True)

    categorical = ["state", "district", "crop"]
    numeric = ["year"]
    models = {}
    metrics = {}
    available_crops = sorted(set(data["crop"].dropna()))
    crop_labels = {crop: crop.replace("_", " ").title() for crop in available_crops}
    for crop_name, column in CROP_MAP.items():
        if crop_name in crop_labels:
            crop_labels[crop_name] = column.replace(" YIELD (Kg per ha)", "").title()

    for crop in available_crops:
        subset = data[data["crop"] == crop].copy()
        subset = subset[subset["yield"].notna()]
        if len(subset) < 100:
            continue

        subset = subset.sort_values("year")
        train_mask = subset["year"] <= 2012
        test_mask = (subset["year"] >= 2013) & (subset["year"] <= 2017)
        if train_mask.sum() < 50 or test_mask.sum() < 20:
            continue

        X_train = subset.loc[train_mask, categorical + numeric]
        y_train = subset.loc[train_mask, "yield"]
        X_test = subset.loc[test_mask, categorical + numeric]
        y_test = subset.loc[test_mask, "yield"]

        preprocessor = ColumnTransformer([
            ("category", OneHotEncoder(handle_unknown="ignore"), categorical),
            ("number", StandardScaler(), numeric),
        ])

        ridge = Pipeline([
            ("preprocess", preprocessor),
            ("model", Ridge(alpha=10.0)),
        ])
        ridge.fit(X_train, y_train)
        prediction = np.clip(ridge.predict(X_test), 0, None)

        metrics[crop] = {
            "train_rows": int(train_mask.sum()),
            "test_rows": int(test_mask.sum()),
            "mae": round(float(mean_absolute_error(y_test, prediction)), 2),
            "mape": round(float(mean_absolute_percentage_error(y_test, prediction) * 100), 2),
            "r2": round(float(r2_score(y_test, prediction)), 4),
        }
        models[crop] = ridge

    district_catalog = (
        data[["state", "district"]]
        .drop_duplicates()
        .sort_values(["state", "district"])
        .groupby("state")["district"]
        .apply(list)
        .to_dict()
    )
    crop_history = {}
    for crop in models:
        subset = data[data["crop"] == crop]
        crop_history[crop] = {
            "mean": round(float(subset["yield"].mean()), 2),
            "median": round(float(subset["yield"].median()), 2),
            "min_year": int(subset["year"].min()),
            "max_year": int(subset["year"].max()),
        }

    joblib.dump({
        "models": models,
        "crop_map": CROP_MAP,
        "crop_labels": crop_labels,
        "district_catalog": district_catalog,
        "crop_history": crop_history,
    }, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps({
        "source": ["ICRISAT-District Level Data.csv", "horizontal_crop_vertical_year_report.xls"],
        "target_unit": "kg/hectare",
        "test_period": "2013-2017",
        "crops": metrics,
    }, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"Saved model: {MODEL_PATH}")
    print(f"Saved metrics: {METRICS_PATH}")


if __name__ == "__main__":
    train()
