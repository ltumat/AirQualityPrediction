import modal
from pathlib import Path
import os
import papermill as pm
import yaml

def run_backfill():

    with open("backend/sensors/sensors.yml", "r") as f:
        config = yaml.safe_load(f)

    notebook_path = "backend/notebooks/backfill.ipynb"

    for sensor in config["sensors"]:
        pm.execute_notebook(
            notebook_path,
            "/dev/null",
            parameters={
                "country": sensor["country"],
                "city": sensor["city"],
                "street": sensor["street"],
                "aqicn_url": sensor["aqicn_url"],
                "csv_file": sensor["csv_file"],
            }
        )

if __name__ == "__main__":
    run_backfill()