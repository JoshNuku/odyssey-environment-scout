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

# --- Cloud MQTT Configuration (EDIT THESE or set env vars) ---
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


# MQTT callbacks
def on_connect(client, userdata, flags, reason_code, properties=None):
    # handle both int and object-style reason codes
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


# CSV helpers
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
        with DATA_FILE.open('r', newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))[-limit:]
        labels, temps, hums, aqs = [], [], [], []
        for r in rows:
            labels.append((r.get('timestamp') or '').strip())
            temps.append(float(r.get('temperature', 0) or 0))
            hums.append(float(r.get('humidity', 0) or 0))
            aqs.append(int(float(r.get('air_quality', 0) or 0)))
        return {'labels': labels, 'temperature_c': temps, 'humidity_percent': hums, 'air_quality_raw': aqs}
    except Exception:
        return None


# --- Flask routes ---
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
    if not state['last_seen'] or state['last_seen'] == '—':
        latest = read_latest_from_csv()
        if latest:
            return jsonify(latest)
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')
        return jsonify({
            'power': True,
            'mode': 'manual',
            'last_seen': now,
            'forward_distance_cm': round(100 + random.random()*80, 2),
            'temperature_c': round(22 + random.random()*6, 2),
            'humidity_percent': round(40 + random.random()*20, 2),
            'air_quality_raw': int(30000 + random.random()*10000),
        })
    return jsonify(state)


@app.route('/api/history')
def api_history():
    series = read_series_from_csv()
    if series:
        return jsonify(series)
    points = 60
    now = datetime.now(timezone.utc)
    label_strs = [(now.replace(microsecond=0) - timedelta(minutes=(points-1-i))).strftime('%H:%M') for i in range(points)]
    temps = [round(22 + 2*math.sin(i/6), 2) for i in range(points)]
    hums  = [round(45 + 5*math.cos(i/8), 2) for i in range(points)]
    aqs   = [int(32000 + 1500*math.sin(i/5) + 800*random.random()) for i in range(points)]
    return jsonify({'labels': label_strs, 'temperature_c': temps, 'humidity_percent': hums, 'air_quality_raw': aqs})


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

# --- Cloud MQTT Configuration (EDIT THESE) ---
MQTT_BROKER_HOSTNAME = "8bf0e6b18e164489b4b2da737bfee4ed.s1.eu.hivemq.cloud"
MQTT_BROKER_PORT = 8883
MQTT_USERNAME = "group2"
MQTT_PASSWORD = "Odyssey2"

# --- Other Constants ---
MQTT_TOPIC_TELEMETRY = "rover/telemetry"
MQTT_TOPIC_COMMAND = "rover/command"
DATA_FILE = Path("data/odyssey_log.csv")

# --- Global State & Data Logging ---
rover_state = {
    "power": False,
    "mode": "manual",
    "last_seen": "—",
    "forward_distance_cm": 0,
    "temperature_c": 0,
    "humidity_percent": 0,
    "air_quality_raw": 0
}
state_lock = threading.Lock()

def init_log_file():
    if not DATA_FILE.exists():
        df = pd.DataFrame(columns=["timestamp", "power", "mode", "forward_distance", "temperature", "humidity", "air_quality"])
        df.to_csv(DATA_FILE, index=False)

def log_data(data):
    try:
        new_log = pd.DataFrame([{
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"),
            "power": data.get("power"),
            "mode": data.get("mode"),
            "forward_distance": data.get("forward_distance_cm"),
            "temperature": data.get("temperature_c"),
            "humidity": data.get("humidity_percent"),
            "air_quality": data.get("air_quality_raw")
        }])
        new_log.to_csv(DATA_FILE, mode='a', header=not DATA_FILE.exists(), index=False)
    except Exception as e:
        print(f"Error logging data: {e}")

# --- MQTT Client ---
def on_connect(client, userdata, flags, reason_code, properties=None):
    # reason_code may be an object (newer API) or an int (older API)
    failed = False
    try:
        if hasattr(reason_code, 'is_failure') and reason_code.is_failure:
            failed = True
        elif isinstance(reason_code, int) and reason_code != 0:
            failed = True
    except Exception:
        failed = False

    if failed:
        print(f"Failed to connect to cloud broker: {reason_code}")
    else:
        print("Successfully connected to HiveMQ Cloud Broker!")
        client.subscribe(MQTT_TOPIC_TELEMETRY)

def on_message(client, userdata, msg):
    global rover_state
    try:
        payload = json.loads(msg.payload.decode())
        with state_lock:
            # Map incoming payload to dashboard fields
            rover_state["power"] = payload.get("power", rover_state["power"])
            rover_state["mode"] = payload.get("mode", rover_state["mode"])
            rover_state["last_seen"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
            rover_state["forward_distance_cm"] = payload.get("forward_distance_cm", rover_state["forward_distance_cm"])
            rover_state["temperature_c"] = payload.get("temperature_c", rover_state["temperature_c"])
            rover_state["humidity_percent"] = payload.get("humidity_percent", rover_state["humidity_percent"])
            rover_state["air_quality_raw"] = payload.get("air_quality_raw", rover_state["air_quality_raw"])
        log_data(rover_state)
    except Exception as e:
        print(f"Error processing telemetry: {e}")

mqtt_client = mqtt.Client(client_id="MissionControl")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLS)

try:
    mqtt_client.connect(MQTT_BROKER_HOSTNAME, MQTT_BROKER_PORT, 60)
except Exception as e:
    print(f"Could not connect to MQTT Broker: {e}")

threading.Thread(target=mqtt_client.loop_forever, daemon=True).start()


def read_latest_from_csv():
    if not DATA_FILE.exists():
        return None
    try:
        with DATA_FILE.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            last_row = None
            for row in reader:
                last_row = row
            if not last_row:
                return None
            return {
                "power": str(last_row.get("power", "OFF")).strip().upper() in {"1", "TRUE", "ON", "YES"},
                "mode": (last_row.get("mode") or "manual").lower(),
                "last_seen": (last_row.get("timestamp") or ""),
                "forward_distance_cm": float(last_row.get("forward_distance", 0) or 0),
                "temperature_c": float(last_row.get("temperature", 0) or 0),
                "humidity_percent": float(last_row.get("humidity", 0) or 0),
                "air_quality_raw": int(float(last_row.get("air_quality", 0) or 0)),
            }
    except Exception:
        return None


# --- Flask Web Server ---
@app.route("/")
def main():
    return render_template("index.html")

@app.route("/index")
def home():
    return render_template("index.html")

@app.route("/history")
def history():
    # For charting, pass data as JSON or let JS fetch from /api/history
    return render_template("history.html")


@app.route("/api/data")
def api_data():
    # Return the latest state (from MQTT or fallback to CSV)
    with state_lock:
        state = dict(rover_state)
    # If no live data, fallback to CSV
    if not state["last_seen"] or state["last_seen"] == "—":
        latest = read_latest_from_csv()
        if latest:
            return jsonify(latest)
        # Fallback to synthetic if CSV not available
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        return jsonify({
            "power": True,
            "mode": "manual",
            "last_seen": now,
            "forward_distance_cm": round(100 + random.random()*80, 2),
            "temperature_c": round(22 + random.random()*6, 2),
            "humidity_percent": round(40 + random.random()*20, 2),
            "air_quality_raw": int(30000 + random.random()*10000)
        })
    return jsonify(state)


@app.route("/api/history")
def api_history():
    series = read_series_from_csv()
    if series:
        return jsonify(series)
    # Fallback to synthetic series
    points = 60
    now = datetime.now(timezone.utc)
    label_strs = [(now.replace(microsecond=0) - timedelta(minutes=(points-1-i))).strftime('%H:%M') for i in range(points)]
    temps = [round(22 + 2*math.sin(i/6), 2) for i in range(points)]
    hums  = [round(45 + 5*math.cos(i/8), 2) for i in range(points)]
    aqs   = [int(32000 + 1500*math.sin(i/5) + 800*random.random()) for i in range(points)]
    return jsonify({"labels": label_strs, "temperature_c": temps, "humidity_percent": hums, "air_quality_raw": aqs})


@app.route("/command", methods=["POST"])
def command():
    payload = request.get_json(silent=True) or request.form.to_dict()
    # Forward command to MQTT
    try:
        mqtt_client.publish(MQTT_TOPIC_COMMAND, json.dumps(payload))
        return jsonify({"ok": True, "received": payload})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    init_log_file()
    app.run(host='0.0.0.0', port=5000, debug=True)
def read_series_from_csv(limit: int = 300):
    if not DATA_FILE.exists():
        return None
    try:
        with DATA_FILE.open("r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))[-limit:]
        labels, temps, hums, aqs = [], [], [], []
        for r in rows:
            labels.append((r.get("timestamp") or "").strip())
            temps.append(float(r.get("temperature", 0) or 0))
            hums.append(float(r.get("humidity", 0) or 0))
            aqs.append(int(float(r.get("air_quality", 0) or 0)))
        return {"labels": labels, "temperature_c": temps, "humidity_percent": hums, "air_quality_raw": aqs}
    except Exception:
        return None


# --- Flask Web Server ---
@app.route("/")
def main():
    return render_template("index.html")

@app.route("/index")
def home():
    return render_template("index.html")

@app.route("/history")
def history():
    # For charting, pass data as JSON or let JS fetch from /api/history
    return render_template("history.html")


@app.route("/api/data")
def api_data():
    # Return the latest state (from MQTT or fallback to CSV)
    with state_lock:
        state = dict(rover_state)
    # If no live data, fallback to CSV
    if not state["last_seen"] or state["last_seen"] == "—":
        latest = read_latest_from_csv()
        if latest:
            return jsonify(latest)
        # Fallback to synthetic if CSV not available
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        return jsonify({
            "power": True,
            "mode": "manual",
            "last_seen": now,
            "forward_distance_cm": round(100 + random.random()*80, 2),
            "temperature_c": round(22 + random.random()*6, 2),
            "humidity_percent": round(40 + random.random()*20, 2),
            "air_quality_raw": int(30000 + random.random()*10000)
        })
    return jsonify(state)


@app.route("/api/history")
def api_history():
    series = read_series_from_csv()
    if series:
        return jsonify(series)
    # Fallback to synthetic series
    points = 60
    now = datetime.now(timezone.utc)
    label_strs = [(now.replace(microsecond=0) - timedelta(minutes=(points-1-i))).strftime('%H:%M') for i in range(points)]
    temps = [round(22 + 2*math.sin(i/6), 2) for i in range(points)]
    hums  = [round(45 + 5*math.cos(i/8), 2) for i in range(points)]
    aqs   = [int(32000 + 1500*math.sin(i/5) + 800*random.random()) for i in range(points)]
    return jsonify({"labels": label_strs, "temperature_c": temps, "humidity_percent": hums, "air_quality_raw": aqs})


@app.route("/command", methods=["POST"])
def command():
    payload = request.get_json(silent=True) or request.form.to_dict()
    # Forward command to MQTT
    try:
        mqtt_client.publish(MQTT_TOPIC_COMMAND, json.dumps(payload))
        return jsonify({"ok": True, "received": payload})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    init_log_file()
    app.run(host='0.0.0.0', port=5000, debug=True)