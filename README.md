# CropSight AI

CropSight AI is a trained crop-yield prediction dashboard built with Flask, scikit-learn, Chart.js, and the ICRISAT district-level datasets.

## Live dashboard

https://cropsight-ai.onrender.com

The dashboard provides:

- 43 crop yield models where sufficient data is available
- State and district selection from dataset values
- Kharif, Rabi, Summer, and Whole Year season controls
- Historical trend, confidence interval, crop comparison, season comparison, and growing-condition chart sheets
- Multilingual dashboard labels
- PDF report export

## Run locally

Requirements: Python 3.11 or newer.

```powershell
cd rooman/astrava
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

To retrain the model artifacts:

```powershell
python train_model.py
python app.py
```

## API

- `GET /` - Dashboard
- `GET /health` - Service health and loaded model count
- `GET /api/catalog` - Dataset states, districts, crops, labels, and crop statistics
- `POST /api/predict` - Yield prediction
- `GET /model_metrics.json` - Validation metrics

Example prediction request:

```json
{
  "crop": "rice",
  "state": "Karnataka",
  "district": "Dharwad",
  "year": 2024,
  "season": "Kharif"
}
```

## Deploy to Render

1. Push this repository to GitHub.
2. Use the deployment button below.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/MAHANTHESHVINU/astrava)

The service health endpoint is `/health`.

## Data sources

- `ICRISAT-District Level Data.csv`
- `horizontal_crop_vertical_year_report.xls`

The model is saved in `crop_yield_model.joblib`, and validation metrics are stored in `model_metrics.json`.
