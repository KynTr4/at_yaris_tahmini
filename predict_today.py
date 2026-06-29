"""Load trained models and generate predictions for today's races."""
import os
import sys
import pickle
import logging
from datetime import date, datetime
import pandas as pd
import numpy as np
from zoneinfo import ZoneInfo

from feature_contract import MODEL_FEATURES, CATEGORICAL_FEATURES, validate_model_feature_contract
from race_scope import is_turkey_track

# Setup logging
os.makedirs("logs", exist_ok=True)
log_date = datetime.now().strftime("%Y_%m_%d")
log_file = f"logs/update_{log_date}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("predict_today")

FAILED_UPDATES_CSV = "failed_updates.csv"

def write_prediction_status(status, message, rows=0, races=0):
    os.makedirs("reports", exist_ok=True)
    with open("reports/prediction_status.md", "w", encoding="utf-8") as f_status:
        f_status.write("# Prediction Status\n\n")
        f_status.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f_status.write(f"- Status: `{status}`\n")
        f_status.write(f"- Message: {message}\n")
        f_status.write(f"- Prediction rows: `{rows}`\n")
        f_status.write(f"- Race count: `{races}`\n")

# The 20 features expected by the models
FEATURE_COLS = MODEL_FEATURES
CATEGORICAL_COLS = CATEGORICAL_FEATURES

def log_failure(entity, error_type, message):
    """Write failure record to failed_updates.csv."""
    row = pd.DataFrame([{
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "script": "predict_today.py",
        "entity": str(entity),
        "error_type": str(error_type),
        "error_message": str(message)
    }])
    file_exists = os.path.exists(FAILED_UPDATES_CSV)
    row.to_csv(FAILED_UPDATES_CSV, mode="a", index=False, header=not file_exists, encoding="utf-8")

def normalize_prediction_frame(df):
    """Normalize probability columns across the whole predictions file by race."""
    pairs = [
        ("cb_prob", "cb_norm_prob"),
        ("xgb_prob", "xgb_norm_prob"),
        ("lr_prob", "lr_norm_prob"),
    ]
    for prob_col, norm_col in pairs:
        if prob_col not in df.columns:
            continue
        df[norm_col] = 0.0
        for rid, group in df.groupby("race_id"):
            idx = group.index
            total = pd.to_numeric(group[prob_col], errors="coerce").fillna(0.0).sum()
            if total > 0:
                df.loc[idx, norm_col] = pd.to_numeric(group[prob_col], errors="coerce").fillna(0.0) / total
            elif len(group) > 0:
                df.loc[idx, norm_col] = 1.0 / len(group)
    if {"lr_norm_prob", "xgb_norm_prob", "cb_norm_prob"}.issubset(df.columns):
        df["ensemble_norm_prob"] = (
            df["lr_norm_prob"] + df["xgb_norm_prob"] + df["cb_norm_prob"]
        ) / 3.0
    return df

def main():
    logger.info("Starting predict_today.py...")
    
    validate_model_feature_contract(FEATURE_COLS)
    final_parquet = "output/asof_features.parquet"
    if not os.path.exists(final_parquet):
        logger.error(f"Final dataset Parquet file {final_parquet} not found.")
        write_prediction_status("missing_dataset", f"{final_parquet} not found")
        log_failure(final_parquet, "MissingDataset", "Final dataset Parquet file not found")
        return 1
        
    # 1. Load today's races
    today_str = date.today().isoformat()
    logger.info(f"Loading races for date: {today_str}...")
    try:
        df = pd.read_parquet(final_parquet)
        if "race_start_at" not in df.columns:
            raise ValueError("Certified dataset is missing race_start_at")
        local_dates = (
            pd.to_datetime(df["race_start_at"], utc=True, errors="coerce")
            .dt.tz_convert(ZoneInfo("Europe/Istanbul")).dt.date.astype(str)
        )
        df_today = df[local_dates == today_str].copy()
    except Exception as e:
        logger.error(f"Error loading final dataset Parquet: {e}")
        write_prediction_status("dataset_read_error", str(e))
        log_failure(today_str, "DatasetReadError", str(e))
        return 1
        
    if df_today.empty:
        logger.warning(f"No races found in final dataset for today ({today_str}). Predictions cannot be generated.")
        write_prediction_status("no_race_today", f"No races found in final dataset for {today_str}")
        return 0
        
    logger.info(f"Found {len(df_today)} horse entries to predict.")
    
    # 2. Load models
    models = {}
    model_paths = {
        "cb": "models/benter_baseline_catboost.pkl",
        "xgb": "models/xgboost_production.pkl",
        "lr": "models/benter_baseline_logistic.pkl"
    }
    
    for key, path in model_paths.items():
        if os.path.exists(path):
            try:
                with open(path, "rb") as f_model:
                    models[key] = pickle.load(f_model)
                logger.info(f"Successfully loaded model: {path}")
            except Exception as e:
                logger.error(f"Error loading model {path}: {e}")
                log_failure(path, "ModelLoadError", str(e))
                if key == "xgb":
                    write_prediction_status("xgboost_model_load_error", str(e))
                    return 1
        else:
            message = f"Model file not found: {path}"
            if key == "xgb":
                logger.error(message)
                log_failure(path, "MissingModel", message)
                write_prediction_status("xgboost_model_missing", message)
                return 1
            logger.warning(message)
            
    if not models:
        logger.error("No models loaded successfully. Exiting.")
        write_prediction_status("no_models_loaded", "No models loaded successfully")
        return 1
        
    # 3. Prepare features X_today
    X_today = df_today[FEATURE_COLS].copy()
    
    # Keep numeric missing values as NaN so model pipelines can apply their trained imputers.
    for col in FEATURE_COLS:
        if col in CATEGORICAL_COLS:
            X_today[col] = X_today[col].astype(object)
            X_today.loc[X_today[col].isna(), col] = "missing"
            X_today[col] = X_today[col].map(lambda v: "missing" if pd.isna(v) else str(v))
        else:
            X_today[col] = pd.to_numeric(X_today[col], errors="coerce")
            
    # 4. Generate predictions
    predictions = df_today[["race_id", "horse_id", "horse_name"]].copy()
    predictions["is_win"] = 0 # default since race has not run
    
    # A. CatBoost predictions
    if "cb" in models:
        try:
            # CatBoost handles categorical values directly if trained with them
            # Let's ensure string types for categorical features
            X_cb = X_today.copy()
            for col in CATEGORICAL_COLS:
                X_cb[col] = X_cb[col].astype(str)
            probs = models["cb"].predict_proba(X_cb)[:, 1]
            predictions["cb_prob"] = probs
        except Exception as e:
            logger.error(f"CatBoost prediction failed: {e}")
            predictions["cb_prob"] = 0.0
    else:
        predictions["cb_prob"] = 0.0
        
    # B. XGBoost predictions
    if "xgb" in models:
        try:
            probs = models["xgb"].predict_proba(X_today)[:, 1]
            if np.any((probs < 0) | (probs > 1)):
                raise ValueError("XGBoost probabilities outside [0, 1]")
            predictions["xgb_prob"] = probs
            logger.info("XGBoost production model predictions generated without fallback.")
        except Exception as e:
            logger.error(f"XGBoost production prediction failed: {e}")
            log_failure("models/xgboost_production.pkl", "XGBoostPredictionError", str(e))
            write_prediction_status("xgboost_prediction_error", str(e))
            return 1
    else:
        logger.error("XGBoost production model was not loaded.")
        log_failure("models/xgboost_production.pkl", "ModelNotLoaded", "XGBoost production model was not loaded")
        write_prediction_status("xgboost_model_not_loaded", "XGBoost production model was not loaded")
        return 1
        
    # C. Logistic Regression predictions
    if "lr" in models:
        try:
            probs = models["lr"].predict_proba(X_today)[:, 1]
            predictions["lr_prob"] = probs
        except Exception as e:
            logger.error(f"Logistic Regression prediction failed: {e}")
            predictions["lr_prob"] = 0.0
    else:
        predictions["lr_prob"] = 0.0
        
    # 5. Normalization of probabilities within each race
    logger.info("Normalizing prediction probabilities within each race...")
    
    predictions["cb_norm_prob"] = 0.0
    predictions["xgb_norm_prob"] = 0.0
    predictions["lr_norm_prob"] = 0.0
    
    for rid, group in predictions.groupby("race_id"):
        idx = group.index
        
        # CatBoost norm
        cb_sum = group["cb_prob"].sum()
        if cb_sum > 0:
            predictions.loc[idx, "cb_norm_prob"] = group["cb_prob"] / cb_sum
        elif len(group) > 0:
            predictions.loc[idx, "cb_norm_prob"] = 1.0 / len(group)
            
        # XGBoost norm
        xgb_sum = group["xgb_prob"].sum()
        if xgb_sum > 0:
            predictions.loc[idx, "xgb_norm_prob"] = group["xgb_prob"] / xgb_sum
        elif len(group) > 0:
            predictions.loc[idx, "xgb_norm_prob"] = 1.0 / len(group)
            
        # Logistic Regression norm
        lr_sum = group["lr_prob"].sum()
        if lr_sum > 0:
            predictions.loc[idx, "lr_norm_prob"] = group["lr_prob"] / lr_sum
        elif len(group) > 0:
            predictions.loc[idx, "lr_norm_prob"] = 1.0 / len(group)

    predictions["ensemble_norm_prob"] = (
        predictions["lr_norm_prob"] + predictions["xgb_norm_prob"] + predictions["cb_norm_prob"]
    ) / 3.0
            
    # 6. Save to model_predictions.csv
    pred_csv_path = "output/model_predictions.csv"
    cols_order = ['race_id', 'horse_id', 'horse_name', 'is_win', 'lr_prob', 'xgb_prob', 'cb_prob', 'lr_norm_prob', 'xgb_norm_prob', 'cb_norm_prob', 'ensemble_norm_prob']
    predictions_to_save = predictions[cols_order]
    
    # Idempotent append: check duplicates
    if os.path.exists(pred_csv_path):
        try:
            df_existing = pd.read_csv(pred_csv_path)
            # Remove any races we are predicting today from existing to avoid duplicates
            df_existing = df_existing[~df_existing["race_id"].isin(predictions["race_id"].unique())]
            df_combined = pd.concat([df_existing, predictions_to_save], ignore_index=True)
            df_combined = df_combined.drop_duplicates(subset=["race_id", "horse_id"])
            df_combined = normalize_prediction_frame(df_combined)
            df_combined.to_csv(pred_csv_path, index=False, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not read existing predictions CSV to merge: {e}")
            predictions_to_save.to_csv(pred_csv_path, mode="a", index=False, header=False, encoding="utf-8")
    else:
        predictions_to_save.to_csv(pred_csv_path, index=False, encoding="utf-8")
        
    logger.info(f"Predictions saved to {pred_csv_path}")
    write_prediction_status(
        "predictions_generated",
        f"Predictions saved to {pred_csv_path}. XGBoost production predictions generated without fallback.",
        rows=len(predictions_to_save),
        races=predictions_to_save["race_id"].nunique()
    )
    
    # 7. Print top selections summary
    print("\n" + "="*50)
    print("TODAY'S TOP PREDICTED SELECTIONS BY RACE")
    print("="*50)
    
    for rid, group in predictions.groupby("race_id"):
        print(f"\nRace ID: {rid}")
        # Sort by CatBoost normalized prob
        sorted_grp = group.sort_values("cb_norm_prob", ascending=False)
        for rank, (idx, r) in enumerate(sorted_grp.head(3).iterrows(), 1):
            print(f"  {rank}. {r['horse_name']} (CB: {r['cb_norm_prob']:.2%}, XGB: {r['xgb_norm_prob']:.2%}, LR: {r['lr_norm_prob']:.2%})")
    print("="*50 + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
