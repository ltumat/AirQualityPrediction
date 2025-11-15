import modal
from pathlib import Path
import os
import papermill as pm
import yaml

def run_training():

    with open("backend/sensors/sensors.yml", "r") as f:
        config = yaml.safe_load(f)

    with open("backend/models/lags.yml", "r") as f:
        lags = yaml.safe_load(f)

    notebook_path = "backend/notebooks/train_model.ipynb"

    for sensor in config["sensors"]:
        for lag_feature in lags["lags"]:
            pm.execute_notebook(
                notebook_path,
                "/dev/null",
                parameters={
                    "country": sensor["country"],
                    "city": sensor["city"],
                    "street": sensor["street"],
                    "lag_feature": lag_feature["feature"],
                }
            )

if __name__ == "__main__":
    run_training()