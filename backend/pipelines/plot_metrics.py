import hopsworks
import yaml
import matplotlib.pyplot as plt
import os
import sys

# project_root = os.path.abspath(os.path.join(os.getcwd(), '../..'))
project_root = "."
if project_root not in sys.path:
    sys.path.append(project_root)
# Set the environment variables from the file <root_dir>/.env
from backend.models import config
settings = config.HopsworksSettings(_env_file=f".env")

def collect_metrics():
    # Load sensors
    with open("backend/sensors/sensors.yml", "r") as f:
        config = yaml.safe_load(f)

    # Load lag features
    with open("backend/models/lags.yml", "r") as f:
        lags = yaml.safe_load(f)

    # Connect to Hopsworks
    project = hopsworks.login(engine="python")
    fs = project.get_feature_store()
    mr = project.get_model_registry()

    # Dictionary to store aggregated metrics
    aggregated = {}   # {lag_feature: {"mse": [...], "r2": [...]}}

    for lag_feature in lags["lags"]:
        lf = lag_feature["feature"]

        aggregated[lf] = {"mse": [], "r2": []}

        for sensor in config["sensors"]:
            country = sensor["country"]
            city = sensor["city"]
            street = sensor["street_new"] if "street_new" in sensor else sensor["street"]
            street_new = street.replace('-', '_')
            street_new = street_new.replace('ä', 'ae')
            street_new = street_new.replace('ö', 'oe')
            street = street_new.replace('å', 'oa')

            model_name = f"air_quality_xgboost_model_{lf}_{country}_{city}_{street}"

            try:
                retrieved_model = mr.get_model(name=model_name, version=1)
                print(retrieved_model)
                metrics = retrieved_model.training_metrics  # {"mse": val, "r2": val}
                print(metrics)

                aggregated[lf]["mse"].append(metrics["MSE"])
                aggregated[lf]["r2"].append(abs(metrics["r squared"]))

            except Exception as e:
                print(f"⚠️ Could not load model: {model_name} ({e})")

    return aggregated


def compute_and_plot(aggregated):
    lag_features = []
    avg_mse = []
    avg_r2 = []

    # Build arrays but skip None values
    for lf, metrics in aggregated.items():
        mse_values = [m for m in metrics["mse"] if m is not None]
        r2_values = [r for r in metrics["r2"] if r is not None]

        if len(mse_values) == 0 or len(r2_values) == 0:
            print(f"⚠️ Skipping {lf}: no valid metrics found.")
            continue

        lag_features.append(lf)
        avg_mse.append(sum(mse_values) / len(mse_values))
        avg_r2.append(sum(r2_values) / len(r2_values))

    # PLOT MSE
    plt.figure(figsize=(10, 5))
    plt.bar(lag_features, avg_mse)
    plt.ylabel("Average MSE")
    plt.title("Average MSE per Lag Feature")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("backend/plots/avg_mse_per_lag.png")
    plt.close()

    # PLOT R²
    plt.figure(figsize=(10, 5))
    plt.bar(lag_features, avg_r2)
    plt.ylabel("Average R²")
    plt.title("Average R² per Lag Feature")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("backend/plots/avg_r2_per_lag.png")
    plt.close()

    print("✅ Saved plots: avg_mse_per_lag.png, avg_r2_per_lag.png")

if __name__ == "__main__":
    aggregated = collect_metrics()
    print(aggregated)
    compute_and_plot(aggregated)
