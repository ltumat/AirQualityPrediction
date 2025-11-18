import modal
from pathlib import Path
import os
import papermill as pm
import yaml

app = modal.App("daily-feature")

image = (
    modal.Image.debian_slim(python_version="3.12.11")
    .pip_install_from_requirements(requirements_txt="requirements.txt")
    .add_local_dir("backend/deployment", remote_path="/root/general")
)

if Path(".env").exists():
    from dotenv import dotenv_values
    env_vars = dotenv_values(".env")
else:
    env_vars = {}

@app.function(
    image=image,
    schedule=modal.Period(days=1),
    secrets=[modal.Secret.from_dict(env_vars)],
    timeout=800,
)
def run_daily_feature():

    with open("general/sensors.yml", "r") as f:
        config = yaml.safe_load(f)

    notebook_path = "general/daily_feature.ipynb"

    output_nb = notebook_path.replace(".ipynb", "_output.ipynb")
    print(f"Running {notebook_path} ...")
    try:
        pm.execute_notebook(notebook_path, output_nb)
    except Exception as e:
        print(f"Error executing {notebook_path}: {e}")
        raise
    print(f"Finished {notebook_path} -> {output_nb}")