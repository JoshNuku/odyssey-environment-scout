# Odyssey — Environment Scout

A small fleet-style project that provides a web dashboard (Mission Control) and a Raspberry Pi based rover that publishes environmental telemetry and accepts remote commands over MQTT.

This repository contains:

- `app.py` — Flask web application (dashboard + API) that subscribes to telemetry via an MQTT broker, stores telemetry to `data/odyssey_log.csv`, and exposes a UI and REST endpoints.
- `rover.py` — Rover runtime designed to run on a Raspberry Pi. Reads sensors (DHT22, HC-SR04 ultrasonic, MQ‑135 via ADS1115), controls motors via L298N, and communicates with the cloud broker over MQTT.
- `static/`, `templates/` — Frontend code (HTML/CSS/JS) for the dashboard.
- `data/generate_dummy.py` — helper to generate synthetic CSV data for development.
- `requirements.txt` — Python dependencies.

Quick goals

- Provide a responsive dashboard showing last known telemetry and history charts.
- Accept remote control commands (movement, modes, power) from the dashboard.
- Rover publishes telemetry to a cloud MQTT broker and responds to commands.

Table of contents

- Requirements
- Configuration
- Run the backend (dashboard)
- Run the rover (Raspberry Pi)
- API & MQTT contract
- Data format / CSV logging
- Frontend notes
- Troubleshooting
- Security & safety
- License

---

## Requirements

- Python 3.10+ recommended.
- A working MQTT broker (HiveMQ Cloud, Mosquitto, AWS IoT, etc.).
- For rover hardware: Raspberry Pi, L298N motor driver, HC-SR04, DHT22, ADS1115 + MQ‑135, wiring as expected in `rover.py`.

Install python deps:

```bash
python -m pip install -r requirements.txt
```

Note: `RPi.GPIO`, `board`, `adafruit_dht`, and other Pi-specific packages will only work on Raspberry Pi OS. To run the backend locally without the Pi-specific libs you may run the server on your development machine (it doesn't import Pi-only libs).

## Configuration

`app.py` reads configuration from environment variables (defaults shown):

- `MQTT_BROKER_HOSTNAME` (default set to a HiveMQ Cloud example)
- `MQTT_BROKER_PORT` (default: 8883)
- `MQTT_USERNAME` (default: group2)
- `MQTT_PASSWORD` (default: Odyssey2)
- `MQTT_TOPIC_TELEMETRY` (default: `rover/telemetry`)
- `MQTT_TOPIC_COMMAND` (default: `rover/command`)

You can set these in your shell or a systemd service file before starting the server.

## Run the backend (dashboard)

1. Initialize log file (the app will create it automatically):

```bash
python app.py
```

2. The Flask app runs on `0.0.0.0:5000` by default (debug mode enabled in development). Visit `http://localhost:5000/` to open the dashboard.

Endpoints

- GET `/` — web dashboard (index)
- GET `/history` — history page
- GET `/api/data` — latest telemetry JSON (returns live telemetry or CSV fallback)
- GET `/api/history` — time series JSON for charts
- POST `/command` — forward a JSON command to the rover (the server publishes to the configured MQTT command topic)

Example command payload (POST /command):

```json
{ "command": "mode_change", "mode": "assisted" }
```

## Run the rover (Raspberry Pi)

1. Copy `rover.py` to the Raspberry Pi and ensure your wiring matches the pin constants at the top of the file.
2. Install Pi-specific dependencies and enable I2C if using ADS1115.

Run on the Pi (may require sudo for GPIO access):

```bash
sudo python rover.py
```

Rover behavior summary

- On receiving `{"command":"power_on"}` the rover starts PWM, connects to the broker, and publishes retained telemetry showing it is ON.
- On receiving `{"command":"mode_change", "mode":"autonomous"}` the rover switches mode (LEDs updated) and the dashboard will reflect the new mode.
- Movement commands (strings such as `forward`, `backward`, `left`, `right`, `stop`) are stored to `last_command` and executed in the main loop according to the current mode.
- The rover publishes telemetry periodically while powered (temperature_c, humidity_percent, air_quality_raw, forward_distance_cm, mode, power)
- The rover sets an MQTT Last Will (LWT) retained OFF message so the backend immediately knows if the rover disconnects unexpectedly.
- The rover includes a reconnect/backoff loop that runs if the broker disconnects while powered.

## API & MQTT contract

Topics (defaults):

- Telemetry topic: `rover/telemetry` — rover publishes JSON telemetry here.
- Command topic: `rover/command` — server publishes UI commands here; rover subscribes.

Telemetry JSON keys (sent by rover):

- `power` (boolean)
- `power_state` (string: "ON"/"OFF")
- `mode` (string: "manual"/"assisted"/"autonomous")
- `temperature_c` (float|null)
- `humidity_percent` (float|null)
- `air_quality_raw` (int|null)
- `forward_distance_cm` (float|null)

Command JSON examples (sent to command topic):

- Movement: `{ "command": "forward" }`
- Stop: `{ "command": "stop" }`
- Power on/off: `{ "command": "power_on" }`, `{ "command": "power_off" }`
- Mode change: `{ "command": "mode_change", "mode": "assisted" }`

## Data format / CSV logging

- The backend logs telemetry to `data/odyssey_log.csv` with columns: `timestamp,power,mode,forward_distance,temperature,humidity,air_quality`
- `app.py` reads the CSV to provide history and a fallback for the dashboard.

## Frontend notes

- The UI front-end is in `templates/index.html` and `static/js/main.js`.
- The dashboard polls `/api/data` every second and `/api/history` for charts.
- The dashboard includes:
  - Movement D-pad and Stop buttons (send movement commands)
  - Mode selector chips (Manual / Assisted / Autonomous)
  - Power toggle (sends power_on/power_off)
  - Live telemetry panel and history charts

## Troubleshooting

- If you run the backend locally and see errors importing Pi-only libraries, run only the server on your dev machine — those imports live in `rover.py`, not `app.py`.
- Common Raspberry Pi issues:
  - `RPi.GPIO` may require running as root or adding your user to the `gpio` group.
  - DHT22: the Adafruit DHT library sometimes fails intermittently; the code handles RuntimeError and will keep working.
  - I2C: enable via `raspi-config` and verify `i2cdetect -y 1` shows ADS1115 address.
- MQTT connection issues: check credentials, broker hostname, and that port 8883 allows TLS connections. You can test with `mosquitto_pub`/`mosquitto_sub` or `mqttfx`.
- If the frontend never shows telemetry, verify rover is publishing to the telemetry topic and the backend is connected to the same broker and topic.

## Security & safety

- Do not expose the MQTT broker credentials in public repositories. Use environment variables for production.
- Motors and moving parts require safe testing conditions. Use a test stand or remove propulsive components when running initial tests.
- The repo contains example credentials and a broker hostname for development — replace with your own secure broker for deployment.

## Extras & suggestions

- Add TLS client certs or OAuth to the broker if you plan to expose telemetry on the public Internet.
- Calibrate MQ135 and translate ADC readings into a meaningful air-quality index before using it for decisions.
- Add more robust error handling, logs, and unit tests for non-hardware code paths.

## License

MIT License 

---
