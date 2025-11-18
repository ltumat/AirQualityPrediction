import modal
from pathlib import Path
import os
import papermill as pm
import yaml

app = modal.App("daily-pipeline")

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
    timeout=1000,
)
def run_pipeline():

    notebooks = [
        "general/daily_feature.ipynb",
        "general/model_predict.ipynb",
    ]

    for nb in notebooks:
        output_nb = nb.replace(".ipynb", "_output.ipynb")
        print(f"Running {nb} ...")
        try:
            pm.execute_notebook(nb, nb.replace(".ipynb", "_output.ipynb"))
        except Exception as e:
            print(f"Error executing {nb}: {e}")
            raise
        print(f"Finished {nb} -> {output_nb}")