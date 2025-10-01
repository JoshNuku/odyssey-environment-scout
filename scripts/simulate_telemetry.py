#!/usr/bin/env python3
"""
simulate_telemetry.py

Small MQTT telemetry simulator for Odyssey dashboard development.
- Publishes telemetry JSON to the telemetry topic at a configurable interval.
- Subscribes to the command topic and logs commands received (and optionally responds to power_on/power_off).

Usage:
  python scripts/simulate_telemetry.py [--interval 1.0] [--retain]

Environment variables (optional, fallbacks shown):
  MQTT_BROKER_HOSTNAME (default: localhost)
  MQTT_BROKER_PORT     (default: 1883)
  MQTT_USERNAME        (default: '')
  MQTT_PASSWORD        (default: '')
  MQTT_TOPIC_TELEMETRY (default: 'rover/telemetry')
  MQTT_TOPIC_COMMAND   (default: 'rover/command')
  USE_TLS              (set to '1' to enable TLS; default: off)

This script is intended for local frontend development when hardware isn't available.
"""

import os
import time
import json
import random
import argparse
import threading
import sys

import paho.mqtt.client as mqtt

# Config (env overrides)
BROKER = os.environ.get('MQTT_BROKER_HOSTNAME', '8bf0e6b18e164489b4b2da737bfee4ed.s1.eu.hivemq.cloud')
PORT = int(os.environ.get('MQTT_BROKER_PORT', 8883))
USERNAME = os.environ.get('MQTT_USERNAME', 'group2')
PASSWORD = os.environ.get('MQTT_PASSWORD', 'Odyssey2')
TOPIC_TELEMETRY = os.environ.get('MQTT_TOPIC_TELEMETRY', 'rover/telemetry')
TOPIC_COMMAND = os.environ.get('MQTT_TOPIC_COMMAND', 'rover/command')
# By default enable TLS when using the typical secure MQTT port (8883) or when explicitly set via USE_TLS env
USE_TLS = os.environ.get('USE_TLS', '').lower() in ('1', 'true', 'yes') or PORT == 8883

args = None

state = {
    'power': True,
    'power_state': 'ON',
    'mode': 'manual',
}

client = None
stop_event = threading.Event()
# Event set when on_connect fires successfully
connected_event = threading.Event()


def on_connect(c, userdata, flags, rc):
    print(f"Connected to MQTT broker (rc={rc})")
    connected_event.set()
    c.subscribe(TOPIC_COMMAND)

def on_publish(c, userdata, mid):
    print(f"Published message id: {mid}")

def on_message(c, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
    except Exception:
        payload = msg.payload.decode('utf-8', 'ignore')
    print(f"[CMD] Topic={msg.topic} Payload={payload}")
    # Optionally emulate simple responses for power commands
    if isinstance(payload, dict):
        cmd = payload.get('command')
        if cmd == 'power_off':
            state['power'] = False
            state['power_state'] = 'OFF'
        elif cmd == 'power_on':
            state['power'] = True
            state['power_state'] = 'ON'
        elif cmd == 'mode_change' and 'mode' in payload:
            state['mode'] = str(payload['mode']).lower()


def connect_mqtt():
    global client
    client = mqtt.Client(client_id='Simulator')
    if USERNAME:
        client.username_pw_set(USERNAME, PASSWORD)
    if USE_TLS:
        try:
            client.tls_set()
        except Exception as e:
            print(f"Warning: tls_set() failed: {e}")
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_publish = on_publish
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
    except Exception as e:
        print(f"Connect to MQTT broker failed: {e}")
        raise
    # wait briefly for on_connect
    if not connected_event.wait(timeout=5):
        print(f"Warning: did not receive on_connect within 5s. Broker={BROKER}:{PORT} USE_TLS={USE_TLS}")
    else:
        print("MQTT connection established and subscribed")


def make_telemetry(t):
    # small deterministic-ish variations
    base_temp = 22.0
    base_hum = 45.0
    temp = round(base_temp + 2.0 * math_sin(t/60.0) + random.uniform(-0.3, 0.3), 2)
    hum = round(base_hum + 5.0 * math_cos(t/90.0) + random.uniform(-0.5, 0.5), 2)
    aq = int(32000 + 1500 * math_sin(t/30.0) + random.uniform(-200, 200))
    dist = round(100 + 20 * math_sin(t/10.0) + random.uniform(-2, 2), 2)
    payload = {
        'power': state['power'],
        'power_state': state['power_state'],
        'mode': state['mode'],
        'temperature_c': temp if state['power'] else None,
        'humidity_percent': hum if state['power'] else None,
        'air_quality_raw': aq if state['power'] else None,
        'forward_distance_cm': dist if state['power'] else None,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    }
    return payload


def math_sin(x):
    return __import__('math').sin(x)

def math_cos(x):
    return __import__('math').cos(x)


def publisher_loop(interval, retain=False):
    i = 0
    while not stop_event.is_set():
        payload = make_telemetry(i)
        try:
            client.publish(TOPIC_TELEMETRY, json.dumps(payload), qos=0, retain=retain)
            print(f"[PUB] {TOPIC_TELEMETRY} {payload}")
        except Exception as e:
            print(f"Publish failed: {e}")
        time.sleep(interval)
        i += 1


def main():
    parser = argparse.ArgumentParser(description='Simulate rover telemetry over MQTT')
    parser.add_argument('--interval', type=float, default=float(os.environ.get('INTERVAL', '1.0')),
                        help='publish interval in seconds (default: 1.0)')
    parser.add_argument('--retain', action='store_true', help='publish retained telemetry')
    parser.add_argument('--host', help='MQTT broker hostname (overrides env)')
    parser.add_argument('--port', type=int, help='MQTT broker port (overrides env)')
    parser.add_argument('--username', help='MQTT username (overrides env)')
    parser.add_argument('--password', help='MQTT password (overrides env)')
    parser.add_argument('--tls', action='store_true', help='force TLS (overrides env)')
    parser.add_argument('--topic', help='telemetry topic (overrides env)')
    args = parser.parse_args()

    # override globals from CLI
    global BROKER, PORT, USERNAME, PASSWORD, TOPIC_TELEMETRY, USE_TLS
    if args.host:
        BROKER = args.host
    if args.port:
        PORT = args.port
    if args.username:
        USERNAME = args.username
    if args.password:
        PASSWORD = args.password
    if args.topic:
        TOPIC_TELEMETRY = args.topic
    if args.tls:
        USE_TLS = True

    print(f"Simulator config -> Broker: {BROKER}:{PORT}, TLS: {USE_TLS}, User: {'(set)' if USERNAME else '(none)'}, Telemetry topic: {TOPIC_TELEMETRY}")

    try:
        connect_mqtt()
    except Exception as e:
        print(f"Failed to connect to MQTT broker {BROKER}:{PORT} - {e}")
        sys.exit(1)

    pub_thread = threading.Thread(target=publisher_loop, args=(args.interval, args.retain), daemon=True)
    pub_thread.start()

    print("Simulator running. Ctrl-C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping simulator...")
        stop_event.set()
        client.loop_stop()
        client.disconnect()


if __name__ == '__main__':
    main()
