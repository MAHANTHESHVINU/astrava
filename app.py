from pathlib import Path
import os

import joblib
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory


ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "crop_yield_model.joblib"
bundle = joblib.load(MODEL_PATH)
models = bundle["models"]
district_catalog = bundle["district_catalog"]
crop_history = bundle["crop_history"]
crop_labels = bundle.get("crop_labels", {})

app = Flask(__name__, static_folder=str(ROOT / "astrava"))


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "models": len(models)})


@app.route("/astrava/")
def astrava_index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/catalog")
def catalog():
    return jsonify({
        "districts": district_catalog,
        "crop_history": crop_history,
        "crops": sorted(models),
        "crop_labels": crop_labels,
    })


@app.route("/api/predict", methods=["POST"])
def predict():
    payload = request.get_json(silent=True) or {}
    crop = str(payload.get("crop", "")).lower()
    state = str(payload.get("state", ""))
    district = str(payload.get("district", ""))
    year = int(payload.get("year", 2024))
    season = str(payload.get("season", "Whole Year"))
    custom_rain = payload.get("rain")
    custom_temp = payload.get("temperature")

    model = models.get(crop)
    if model is None:
        return jsonify({"error": f"No trained model for crop: {crop}"}), 400

    state_options = [key for key in district_catalog if key.lower() == state.lower()]
    district_options = []
    if state_options:
        district_options = district_catalog[state_options[0]]
    district_matches = [value for value in district_options if value.lower() == district.lower()]
    if not district_matches:
        district_matches = [district_options[0]] if district_options else [district]
        district = district_matches[0]

    features = pd.DataFrame([{
        "crop": crop,
        "year": year,
        "state": state_options[0] if state_options else state,
        "district": district,
    }])
    predicted = max(0.0, float(model.predict(features)[0]))
    history = crop_history[crop]
    mean = history["mean"]
    pct = (predicted - mean) / mean * 100 if mean else 0
    std = max(predicted * 0.10, mean * 0.08)
    ci_low = max(0.0, predicted - 1.96 * std)
    ci_high = predicted + 1.96 * std

    # Climate overrides are optional UI controls; their uncertainty effect is bounded.
    if custom_temp not in (None, ""):
        temp = float(custom_temp)
        factor = 0.90 if temp > 35 or temp < 15 else 1.0
        predicted *= factor
    if custom_rain not in (None, ""):
        rain = float(custom_rain)
        factor = 0.95 if rain < 300 or rain > 2500 else 1.0
        predicted *= factor
    ci_low = max(0.0, predicted - 1.96 * std)
    ci_high = predicted + 1.96 * std
    pct = (predicted - mean) / mean * 100 if mean else 0

    metrics = __import__("json").loads((ROOT / "model_metrics.json").read_text(encoding="utf-8"))
    mape = metrics["crops"].get(crop, {}).get("mape", 0)
    risk = "HIGH" if pct < -20 else "MEDIUM" if pct < -8 else "LOW"

    return jsonify({
        "crop": crop,
        "predicted": round(predicted),
        "ci_low": round(ci_low),
        "ci_high": round(ci_high),
        "mean": round(mean),
        "pct_vs_avg": round(pct, 1),
        "risk": risk,
        "mape": mape,
        "season": season,
        "env": {
            "temperature": custom_temp,
            "rainfall": custom_rain,
        },
    })


@app.route("/model_metrics.json")
def metrics():
    return send_from_directory(str(ROOT), "model_metrics.json")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
