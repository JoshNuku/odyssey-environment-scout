from flask import Flask, render_template, request, jsonify
import paho.mqtt.client as mqtt
import json
import ssl
import threading
import pandas as pd
from datetime import datetime, timezone, timedelta
import os, random, math, csv
from pathlib import Path

app = Flask(__name__)
app.jinja_env.globals['datetime'] = datetime

# --- Cloud MQTT Configuration (env vars preferred) ---
MQTT_BROKER_HOSTNAME = os.environ.get('MQTT_BROKER_HOSTNAME', '8bf0e6b18e164489b4b2da737bfee4ed.s1.eu.hivemq.cloud')
MQTT_BROKER_PORT = int(os.environ.get('MQTT_BROKER_PORT', 8883))
MQTT_USERNAME = os.environ.get('MQTT_USERNAME', 'group2')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD', 'Odyssey2')

# --- Other Constants ---
MQTT_TOPIC_TELEMETRY = os.environ.get('MQTT_TOPIC_TELEMETRY', 'rover/telemetry')
MQTT_TOPIC_COMMAND = os.environ.get('MQTT_TOPIC_COMMAND', 'rover/command')
DATA_FILE = Path('data/odyssey_log.csv')

# --- Global State & Data Logging ---
rover_state = {
    'power': False,
    'mode': 'manual',
    'last_seen': '—',
    'forward_distance_cm': 0,
    'temperature_c': 0,
    'humidity_percent': 0,
    'air_quality_raw': 0,
}
state_lock = threading.Lock()

mqtt_client = None
mqtt_connected = threading.Event()

# --- Helpers ---
def init_log_file():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        df = pd.DataFrame(columns=['timestamp', 'power', 'mode', 'forward_distance', 'temperature', 'humidity', 'air_quality'])
        df.to_csv(DATA_FILE, index=False)

def log_data(data):
    try:
        new_log = pd.DataFrame([{
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z'),
            'power': data.get('power'),
            'mode': data.get('mode'),
            'forward_distance': data.get('forward_distance_cm'),
            'temperature': data.get('temperature_c'),
            'humidity': data.get('humidity_percent'),
            'air_quality': data.get('air_quality_raw'),
        }])
        new_log.to_csv(DATA_FILE, mode='a', header=not DATA_FILE.exists(), index=False)
    except Exception as e:
        print('Error logging data:', e)

# --- MQTT Callbacks ---
def on_connect(client, userdata, flags, reason_code, properties=None):
    try:
        failed = False
        if hasattr(reason_code, 'is_failure') and reason_code.is_failure:
            failed = True
        elif isinstance(reason_code, int) and reason_code != 0:
            failed = True
    except Exception:
        failed = False
    if failed:
        print('Failed to connect to MQTT broker:', reason_code)
        mqtt_connected.clear()
    else:
        print('Connected to MQTT broker')
        mqtt_connected.set()
        client.subscribe(MQTT_TOPIC_TELEMETRY)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        with state_lock:
            rover_state['power'] = payload.get('power', rover_state['power'])
            rover_state['mode'] = payload.get('mode', rover_state['mode'])
            rover_state['last_seen'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')
            rover_state['forward_distance_cm'] = payload.get('forward_distance_cm', rover_state['forward_distance_cm'])
            rover_state['temperature_c'] = payload.get('temperature_c', rover_state['temperature_c'])
            rover_state['humidity_percent'] = payload.get('humidity_percent', rover_state['humidity_percent'])
            rover_state['air_quality_raw'] = payload.get('air_quality_raw', rover_state['air_quality_raw'])
        log_data(rover_state)
    except Exception as e:
        print('Error processing telemetry message:', e)

# --- MQTT Client Startup ---
def start_mqtt_client():
    global mqtt_client
    mqtt_client = mqtt.Client(client_id='MissionControl')
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLS)
    try:
        mqtt_client.connect(MQTT_BROKER_HOSTNAME, MQTT_BROKER_PORT, 60)
        threading.Thread(target=mqtt_client.loop_forever, daemon=True).start()
    except Exception as e:
        print('Could not connect to MQTT broker:', e)

# --- CSV Helpers ---
def read_latest_from_csv():
    if not DATA_FILE.exists():
        return None
    try:
        with DATA_FILE.open('r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            last_row = None
            for row in reader:
                last_row = row
            if not last_row:
                return None
            return {
                'power': str(last_row.get('power', 'OFF')).strip().upper() in {'1', 'TRUE', 'ON', 'YES'},
                'mode': (last_row.get('mode') or 'manual').lower(),
                'last_seen': (last_row.get('timestamp') or ''),
                'forward_distance_cm': float(last_row.get('forward_distance', 0) or 0),
                'temperature_c': float(last_row.get('temperature', 0) or 0),
                'humidity_percent': float(last_row.get('humidity', 0) or 0),
                'air_quality_raw': int(float(last_row.get('air_quality', 0) or 0)),
            }
    except Exception:
        return None

def read_series_from_csv(limit: int = 300):
    if not DATA_FILE.exists():
        return None
    try:
        # Prefer pandas for robust CSV parsing; handle files missing the header row by supplying expected column names
        expected = ['timestamp', 'power', 'mode', 'forward_distance', 'temperature', 'humidity', 'air_quality']
        try:
            df = pd.read_csv(DATA_FILE, parse_dates=['timestamp'], keep_default_na=False, na_values=[''])
        except Exception:
            # Try reading without headers (old files may lack them)
            df = pd.read_csv(DATA_FILE, names=expected, header=None, keep_default_na=False, na_values=[''])
        # If the file was parsed but doesn't contain expected columns, coerce by re-reading without header
        if not set(expected).issubset(df.columns):
            df = pd.read_csv(DATA_FILE, names=expected, header=None, keep_default_na=False, na_values=[''])
        df = df.tail(limit)
        labels = df['timestamp'].astype(str).tolist()
        temps = df['temperature'].replace('', 0).fillna(0).astype(float).tolist()
        hums = df['humidity'].replace('', 0).fillna(0).astype(float).tolist()
        aqs = df['air_quality'].replace('', 0).fillna(0).astype(int).tolist()
        return {'labels': labels, 'temperature_c': temps, 'humidity_percent': hums, 'air_quality_raw': aqs}
    except Exception:
        # Fallback: parse manually using csv.reader for malformed files
        try:
            with DATA_FILE.open('r', newline='', encoding='utf-8') as f:
                rows = list(csv.reader(f))[-limit:]
            labels, temps, hums, aqs = [], [], [], []
            for r in rows:
                # Ensure we have at least 7 columns; pad if necessary
                while len(r) < 7:
                    r.append('')
                labels.append((r[0] or '').strip())
                try:
                    temps.append(float(r[4] or 0))
                except Exception:
                    temps.append(0.0)
                try:
                    hums.append(float(r[5] or 0))
                except Exception:
                    hums.append(0.0)
                try:
                    aqs.append(int(float(r[6] or 0)))
                except Exception:
                    aqs.append(0)
            return {'labels': labels, 'temperature_c': temps, 'humidity_percent': hums, 'air_quality_raw': aqs}
        except Exception:
            return None

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/history')
def history():
    return render_template('history.html')

@app.route('/api/data')
def api_data():
    with state_lock:
        state = dict(rover_state)
    # Prefer live telemetry; if not available try CSV. Do NOT fabricate random data.
    if not state['last_seen'] or state['last_seen'] == '—':
        latest = read_latest_from_csv()
        if latest:
            return jsonify(latest)
        # No live telemetry and no CSV available — return the current in-memory state (may be defaults)
        return jsonify(state)
    return jsonify(state)

@app.route('/api/history')
def api_history():
    series = read_series_from_csv()
    if series:
        return jsonify(series)
    # No stored history available — return an empty series (no synthetic generation)
    return jsonify({'labels': [], 'temperature_c': [], 'humidity_percent': [], 'air_quality_raw': []})

@app.route('/command', methods=['POST'])
def command():
    payload = request.get_json(silent=True) or request.form.to_dict()
    if mqtt_client is None or not mqtt_connected.is_set():
        return jsonify({'ok': False, 'error': 'MQTT not connected'}), 503
    try:
        mqtt_client.publish(MQTT_TOPIC_COMMAND, json.dumps(payload))
        return jsonify({'ok': True, 'received': payload})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

if __name__ == '__main__':
    init_log_file()
    start_mqtt_client()
    app.run(host='0.0.0.0', port=5000, debug=True)