from flask import Flask ,render_template, request, jsonify
from datetime import datetime, timezone, timedelta
import random, math, csv
from pathlib import Path

app = Flask(__name__)
app.jinja_env.globals['datetime'] = datetime

DATA_FILE = Path("data/odyssey_log.csv")

def _parse_bool(value: str) -> bool:
    return str(value).strip().upper() in {"1", "TRUE", "ON", "YES"}

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
                "power": _parse_bool(last_row.get("power", "OFF")),
                "mode": (last_row.get("mode") or "manual").lower(),
                "last_seen": (last_row.get("timestamp") or ""),
                "forward_distance_cm": float(last_row.get("forward_distance", 0) or 0),
                "temperature_c": float(last_row.get("temperature", 0) or 0),
                "humidity_percent": float(last_row.get("humidity", 0) or 0),
                "air_quality_raw": int(float(last_row.get("air_quality", 0) or 0)),
            }
    except Exception:
        return None

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

@app.route("/")
def main():
    return render_template("home.html")
@app.route("/index")
def home():
    return  render_template("index.html")
 
@app.route("/history")
def history():
    return render_template("history.html")

@app.route("/api/data")
def api_data():
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
    # For now, just echo back the command received
    return jsonify({"ok": True, "received": payload})
    


if __name__ == "__main__":
    app.run(debug=True)