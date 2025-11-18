from dataclasses import dataclass
from typing import Any
import datetime
import shutil

from pathlib import Path

import folium
from folium.plugins import HeatMap

import pandas as pd
import hopsworks
import streamlit as st
from ruamel.yaml import YAML
import time


APP_DIR = Path(__file__).resolve().parent
PAGE_NAME = Path(__file__).stem

static_dir = APP_DIR / "static"
static_dir.mkdir(exist_ok=True)

download_path = APP_DIR / "backend" / "air_quality_models" / "general" / "downloads"
download_path.mkdir(parents=True, exist_ok=True)

# Map constants
STOCKHOLM_CENTER = (59.3293, 18.0686)
MAP_ZOOM = 11
SENSORS_FILE = Path(__file__).resolve().parent / "backend" / "sensors" / "sensors.yml"
CACHE_TTL_S = 12 * 60 * 60


yaml_parser = YAML()
yaml_parser.preserve_quotes = True
yaml_parser.indent(mapping=2, sequence=4, offset=2)


def load_sensors(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as fp:
        return yaml_parser.load(fp)


@st.cache_data(ttl=CACHE_TTL_S)
def get_data():
    sensors_doc = load_sensors(SENSORS_FILE)
    yestarday = datetime.datetime.now() - datetime.timedelta(1)
    sensors: list[dict[str, Any]] = sensors_doc.get("sensors", [])
    new_sensors: list[dict[str, Any]] = []

    project = hopsworks.login(engine="python")
    fs = project.get_feature_store()
    
    time.sleep(1)

    dataset_api = project.get_dataset_api()
    str_yestarday = yestarday.strftime("%Y_%m_%d")
    for sensor in sensors:
        street_new = sensor['street'].replace('-', '_')
        street_new = street_new.replace('ä', 'ae')
        street_new = street_new.replace('ö', 'oe')
        street_new = street_new.replace('å', 'oa')

        local_name = f"pm25_forecast_{street_new}_{str_yestarday}.png"
        local_file = download_path / local_name

        dataset_api.download(
            "Resources/airquality/general" + f"/pm25_forecast_{street_new}_{str_yestarday}.png", 
            str(download_path), 
            overwrite=True,
        )
        shutil.copy(local_file, static_dir / local_name)

        sensor["img_pred"] = f"{PAGE_NAME}/static/{local_name}"
        new_sensors.append(sensor)

    monitor_fg = fs.get_or_create_feature_group(
        name=f'aq_predictions_general',
        description='Air Quality prediction monitoring',
        version=1,
        primary_key=['city','street','date','days_before_forecast_day'],
        event_time="date"
    )
    monitor_df = monitor_fg.filter(monitor_fg.days_before_forecast_day == 1).read()

    sensor_df = pd.DataFrame(sensors)
    sensor_df = sensor_df[["street", "latitude", "longitude", "img_pred"]]
    
    monitor_df = monitor_df.merge(sensor_df, on="street", how="left")
    return monitor_df


@dataclass
class Sensor:
    """Simple container for synthetic sensor metadata."""

    name: str
    lat: float
    lon: float
    pm25: float
    image_url: str
    status_label: str
    status_color: str


def _quality_bucket(pm25: float) -> tuple[str, str]:
    """Translate PM2.5 concentration into a qualitative label and color."""
    if pm25 < 12:
        return "Good air quality", "#2ecc71"  # green
    if pm25 < 35:
        return "Moderate air quality", "#f1c40f"  # yellow
    return "Poor air quality", "#e74c3c"  # red


def build_sensors(df: pd.DataFrame) -> list[Sensor]:
    """Create synthetic sensors scattered around Stockholm."""
    sensors: list[Sensor] = []
    for index, row in df.iterrows():
        lat = row["latitude"]
        lon = row["longitude"]
        pm25 = row["predicted_pm25"]
        img_pred = row["img_pred"]
        label, color = _quality_bucket(pm25)
        sensors.append(
            Sensor(
                name=f"Sensor #{index+1}",
                lat=lat,
                lon=lon,
                pm25=pm25,
                image_url=img_pred,
                status_label=label,
                status_color=color,
            )
        )
    return sensors


def draw_map(sensors: list[Sensor]) -> None:
    """Build a Folium map with hover tooltips and clickable popups."""
    base_map = folium.Map(
        location=STOCKHOLM_CENTER,
        zoom_start=MAP_ZOOM,
        tiles="CartoDB positron",
        control_scale=True,
    )

    def _pm25_to_intensity(pm25: float) -> float:
        # clamp to [0, 500] then scale to [0, 1]
        return max(0.0, min(pm25, 500.0)) / 500.0

    def bucket_color_from_intensity(intensity: float, gradient: dict[float, str]) -> str:
        # make sure intensity is in [0, 1]
        intensity = max(0.0, min(intensity, 1.0))

        # sort the breakpoints
        breaks = sorted(gradient.keys())  # [0.0, 0.1, 0.2, 0.3, 0.4, 0.6]

        color = gradient[breaks[0]]
        for b in breaks:
            if intensity >= b:
                color = gradient[b]
            else:
                break
        return color, b


    gradient = {
        0.0: "#00e400",          # 0
        50/500: "#ffff00",       # 50
        100/500: "#ff7e00",      # 100
        150/500: "#ff0000",      # 150
        200/500: "#8f3f97",      # 200
        300/500: "#7e0023",      # 300–500
    }
    new_gradient = {}
    max_intensity = 0.0

    heatmap_data = []
    i = 0
    for sensor in sensors:
        intensity = _pm25_to_intensity(sensor.pm25)

        if intensity > max_intensity:
            max_intensity = intensity

        color, bucket = bucket_color_from_intensity(intensity, gradient)
        new_gradient[bucket] = color

        html_popup = f"""
        <div style="width:575px;">
            <h4 style="margin-bottom:4px;">{sensor.name}</h4>
            <p style="margin:0 0 8px 0;color:{color};font-weight:bold;">
                {sensor.status_label}
            </p>
            <ul style="padding-left:18px;margin:0 0 8px 0;">
                <li>PM2.5: {sensor.pm25:.1f} µg/m³</li>
            </ul>
            <img src="{sensor.image_url}"
                style="display:block;width:100%;height:auto;border-radius:6px;" />
        </div>
        """
        popup = folium.Popup(html_popup, max_width=600)  # bigger than default 300
        tooltip = folium.Tooltip(f"{sensor.name} • {sensor.status_label}", sticky=True)

        folium.CircleMarker(
            location=(sensor.lat, sensor.lon),
            radius=10,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=popup,
            tooltip=tooltip,
        ).add_to(base_map)

        heatmap_data.append([sensor.lat, sensor.lon, intensity])
    
    HeatMap(
        heatmap_data,
        radius=60,
        blur=25,
        max_zoom=13,
        gradient=new_gradient,
        max=max_intensity,
    ).add_to(base_map)
    # (optional) layer control to toggle heatmap on/off
    folium.LayerControl().add_to(base_map)

    st.components.v1.html(base_map._repr_html_(), height=800)


def main() -> None:
    st.set_page_config(page_title="Stockholm Air Quality Sensors", layout="wide")
    st.title("Air Quality Across Greater Stockholm")
    st.caption(
        "Hover each marker to quickly understand the air quality classification: "
        "green is good, yellow is moderate, and red is poor. Click a marker to "
        "open a popup with the live measurements and an illustrative snapshot."
    )
    
    df = get_data()
    sensors = build_sensors(df)

    draw_map(sensors)


if __name__ == "__main__":
    main()
