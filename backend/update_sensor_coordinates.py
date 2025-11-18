from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from ruamel.yaml import YAML


SENSORS_FILE = Path(__file__).resolve().parent / "sensors" / "sensors.yml"
AQICN_BASE = "https://api.waqi.info/feed"
AQICN_PUBLIC_BASE = "https://api.waqi.info/api/feed"


yaml_parser = YAML()
yaml_parser.preserve_quotes = True
yaml_parser.indent(mapping=2, sequence=4, offset=2)


class SensorUpdateError(RuntimeError):
    """Raised when a sensor coordinate lookup fails."""


def load_sensors(file_path: Path) -> Dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as fp:
        return yaml_parser.load(fp)


def save_sensors(file_path: Path, payload: Dict[str, Any]) -> None:
    with file_path.open("w", encoding="utf-8") as fp:
        yaml_parser.dump(payload, fp)


def build_candidate_urls(sensor: Dict[str, Any]) -> Iterable[str]:
    yield sensor["aqicn_url"]
    yield f"{AQICN_BASE}/{sensor['country']}/{sensor['street']}"
    yield f"{AQICN_BASE}/{sensor['country']}/{sensor['city']}/{sensor['street']}"


def fetch_sensor_payload(
    sensor: Dict[str, Any], token: Optional[str]
) -> Dict[str, Any]:
    if token:
        for candidate in build_candidate_urls(sensor):
            url = f"{candidate}/?token={token}"
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "ok":
                return data
            if data.get("data") != "Unknown station":
                raise SensorUpdateError(f"Unexpected response for {sensor['name']}: {data}")

    # Fallback to unauthenticated obs endpoint which still contains geo metadata.
    api_url = sensor["aqicn_url"].replace(
        "://api.waqi.info/feed/", "://api.waqi.info/api/feed/", 1
    )
    if not api_url.endswith("/obs.en.json"):
        api_url = f"{api_url.rstrip('/')}/obs.en.json"

    response = requests.get(api_url, timeout=20)
    response.raise_for_status()
    data = response.json()
    if not data:
        raise SensorUpdateError(f"No payload returned for {sensor['name']}")
    if data.get("status") == "error":
        raise SensorUpdateError(f"AQICN error for {sensor['name']}: {data.get('data')}")
    return data


def extract_coordinates(api_payload: Dict[str, Any]) -> Tuple[float, float]:
    data_section = api_payload.get("data")
    if isinstance(data_section, dict):
        geo = data_section.get("city", {}).get("geo")
        if geo and len(geo) >= 2:
            return float(geo[0]), float(geo[1])

    obs_entries = api_payload.get("rxs", {}).get("obs", [])
    for obs in obs_entries:
        msg = obs.get("msg", {})
        msg_geo = msg.get("city", {}).get("geo")
        if msg_geo and len(msg_geo) >= 2:
            return float(msg_geo[0]), float(msg_geo[1])

    raise SensorUpdateError("Missing geo coordinates in API payload")


def format_coord(value: float) -> str:
    """Format coordinate with trimmed trailing zeros."""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def apply_lat_lon_updates(file_path: Path, updates: Dict[str, Dict[str, Any]]) -> None:
    """Update only latitude/longitude fields in the YAML file."""
    lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    updated_lines: List[str] = []
    current_sensor: Optional[str] = None

    def _strip_quotes(value: str) -> str:
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            return value[1:-1]
        return value

    for line in lines:
        line_body = line.rstrip("\r\n")
        newline = line[len(line_body) :]
        stripped = line_body.strip()

        if stripped.startswith("- name:") or stripped.startswith("name:"):
            name_value = stripped.split(":", 1)[1].strip()
            current_sensor = _strip_quotes(name_value)

        entry = updates.get(current_sensor or "")
        if entry and stripped.startswith("latitude:"):
            indent = line_body[: len(line_body) - len(line_body.lstrip())]
            lat_text = format_coord(entry["latitude"])
            updated_lines.append(f"{indent}latitude: {lat_text}{newline}")
            entry["lat_written"] = True
            continue
        if entry and stripped.startswith("longitude:"):
            indent = line_body[: len(line_body) - len(line_body.lstrip())]
            lon_text = format_coord(entry["longitude"])
            updated_lines.append(f"{indent}longitude: {lon_text}{newline}")
            entry["lon_written"] = True
            continue

        updated_lines.append(line)

    missing = [
        name
        for name, entry in updates.items()
        if not entry.get("lat_written") or not entry.get("lon_written")
    ]
    if missing:
        missing_display = ", ".join(missing)
        raise SensorUpdateError(
            f"Latitude/longitude lines not found for sensors: {missing_display}. "
            "Ensure the YAML already defines these fields."
        )

    file_path.write_text("".join(updated_lines), encoding="utf-8")


def update_sensor_coordinates(
    token: Optional[str], file_path: Path
) -> List[Dict[str, Any]]:
    sensors_doc = load_sensors(file_path)
    sensors: List[Dict[str, Any]] = sensors_doc.get("sensors", [])
    updates: Dict[str, Dict[str, Any]] = {}

    for sensor in sensors:
        payload = fetch_sensor_payload(sensor, token)
        lat, lon = extract_coordinates(payload)
        sensor["latitude"] = round(lat, 6)
        sensor["longitude"] = round(lon, 6)
        updates[sensor["name"]] = {
            "latitude": sensor["latitude"],
            "longitude": sensor["longitude"],
        }

    for entry in updates.values():
        entry["lat_written"] = False
        entry["lon_written"] = False

    apply_lat_lon_updates(file_path, updates)
    return sensors


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch AQICN coordinates for all configured sensors."
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=SENSORS_FILE,
        help="Path to the sensors.yml file to update.",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="AQICN API token (defaults to AQI_API_KEY env var).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    load_dotenv()
    token = args.token or os.getenv("AQI_API_KEY") or os.getenv("AQICN_API_KEY")

    updated = update_sensor_coordinates(token=token, file_path=args.file)
    print(f"Updated coordinates for {len(updated)} sensors in {args.file}")


if __name__ == "__main__":
    main()
