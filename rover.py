# rover.py
# The complete code for the "Odyssey" mobile rover unit.

import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO
import time
import json
import ssl
import board
import busio
import adafruit_dht
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import threading

# --- Pin Definitions (BCM Mode) ---
# L298N Motor Driver
ENA, IN1, IN2 = 17, 19, 26  # ENA = Left Motor Speed (PWM)
ENB, IN3, IN4 = 18, 20, 21  # ENB = Right Motor Speed (PWM)

# HC-SR04 Ultrasonic Sensor
TRIG = 23
ECHO = 24

# DHT22 Temperature & Humidity Sensor
DHT_PIN = 7

# User Interface Components (LEDs only)
LED_MANUAL = 27    # Blue LED
LED_ASSISTED = 22  # Yellow LED
LED_AUTONOMOUS = 4 # Green LED
MODE_LEDS = [LED_MANUAL, LED_ASSISTED, LED_AUTONOMOUS]

# --- Cloud MQTT Configuration (EDIT THESE) ---
MQTT_BROKER_HOSTNAME = "8bf0e6b18e164489b4b2da737bfee4ed.s1.eu.hivemq.cloud"
MQTT_BROKER_PORT = 8883
MQTT_USERNAME = "group2"
MQTT_PASSWORD = "Odyssey2"

# --- Other Constants ---
MQTT_TOPIC_TELEMETRY = "rover/telemetry"
MQTT_TOPIC_COMMAND = "rover/command"
SAFE_DISTANCE_CM = 25

class Rover:
    def __init__(self):
        # GPIO Setup
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # UI Component Setup (LEDs)
        GPIO.setup(MODE_LEDS, GPIO.OUT, initial=GPIO.LOW)
        
        # Motor Pins & PWM Initialization
        GPIO.setup([IN1, IN2, IN3, IN4], GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup([ENA, ENB], GPIO.OUT)
        self.pwm_left = GPIO.PWM(ENA, 100)
        self.pwm_right = GPIO.PWM(ENB, 100)
        
        # Sensor Pin Setup
        GPIO.setup(TRIG, GPIO.OUT)
        GPIO.setup(ECHO, GPIO.IN)
        self.dht_device = adafruit_dht.DHT22(getattr(board, f'D{DHT_PIN}'), use_pulseio=False)
        
        # I2C/ADC Setup
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.ads = ADS.ADS1115(self.i2c)
        self.mq135_channel = AnalogIn(self.ads, ADS.P0)
        
        # State Variables
        # use lowercase mode names to match server/frontend expectations: 'manual', 'assisted', 'autonomous'
        self.power_state = "OFF"
        self.mode = "manual"
        self.last_command = "stop"
        self.last_temp = None
        self.last_humidity = None

        # Lightweight lock to protect state accessed from MQTT callbacks and main loop
        self.state_lock = threading.Lock()

        # MQTT Client Setup
        self.mqtt_client = mqtt.Client(client_id="OdysseyRover")
        # Last-Will: if rover drops unexpectedly, broker will publish OFF retained state
        self.mqtt_client.will_set(MQTT_TOPIC_TELEMETRY, payload=json.dumps({"power": False, "power_state": "OFF", "mode": self.mode}), qos=1, retain=True)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.on_disconnect = self.on_disconnect
        self.mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        self.mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLS)

        # Reconnect control
        self.reconnect_thread = None
        self._reconnect_stop = threading.Event()
    # No hardware power button on rover; power controls via code or MQTT

    def on_disconnect(self, client, userdata, rc):
        print(f"MQTT disconnected (rc={rc})")
        # If disconnect was unexpected and rover is powered, try to reconnect in background
        if rc != 0:
            with self.state_lock:
                powered = (self.power_state == "ON")
            if powered:
                # start reconnect thread if not already running
                if not self.reconnect_thread or not self.reconnect_thread.is_alive():
                    self._reconnect_stop.clear()
                    self.reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
                    self.reconnect_thread.start()

    def _reconnect_loop(self):
        backoff = 1.0
        while not self._reconnect_stop.is_set():
            with self.state_lock:
                if self.power_state != "ON":
                    break
            try:
                print(f"Attempting MQTT reconnect (backoff={backoff}s)...")
                self.mqtt_client.reconnect()
                print("MQTT reconnect successful")
                # on successful reconnect, stop loop
                break
            except Exception as e:
                print(f"MQTT reconnect failed: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
        self._reconnect_stop.set()

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        # Handle both int reason codes and richer reason objects
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
            client.subscribe(MQTT_TOPIC_COMMAND)
            # Publish a retained ON state so backend sees rover online (overwrites LWT)
            try:
                with self.state_lock:
                    retained_msg = {"power": True if self.power_state == "ON" else False, "power_state": self.power_state, "mode": self.mode}
                client.publish(MQTT_TOPIC_TELEMETRY, json.dumps(retained_msg), qos=1, retain=True)
            except Exception as e:
                print(f"Failed to publish retained ON state: {e}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            command = payload.get("command")
            # allow remote power control now that there's no hardware button
            if command == "power_on":
                with self.state_lock:
                    self.power_on()
                return
            if command == "power_off":
                with self.state_lock:
                    self.power_off()
                return

            if command == "mode_change":
                # normalize to lowercase strings
                new_mode = str(payload.get("mode", "manual")).lower()
                with self.state_lock:
                    self.mode = new_mode
                    print(f"Mode changed to: {self.mode}")
                    self.update_leds()
                    self.stop()
                return

            # movement commands only apply when powered on
            with self.state_lock:
                powered = (self.power_state == "ON")
            if not powered:
                return

            # store last_command (no complex parsing here)
            with self.state_lock:
                if self.mode in ["manual", "assisted"]:
                    self.last_command = command
        except Exception as e:
            print(f"Error processing MQTT message: {e}")

    def update_leds(self):
        GPIO.output(MODE_LEDS, GPIO.LOW)
        if self.power_state == "ON":
            # mode stored in lowercase
            if self.mode == "manual": GPIO.output(LED_MANUAL, GPIO.HIGH)
            elif self.mode == "assisted": GPIO.output(LED_ASSISTED, GPIO.HIGH)
            elif self.mode == "autonomous": GPIO.output(LED_AUTONOMOUS, GPIO.HIGH)

    def power_on(self):
        if self.power_state == "ON": return
        print("Powering ON rover systems...")
        self.power_state = "ON"
        self.pwm_left.start(0); self.pwm_right.start(0)
        try:
            # ensure MQTT connected
            try:
                self._reconnect_stop.clear()
                self.mqtt_client.connect(MQTT_BROKER_HOSTNAME, MQTT_BROKER_PORT, 60)
                self.mqtt_client.loop_start()
            except Exception as e:
                print(f"Failed to connect on power on: {e}")
            self.mode = "manual"; self.update_leds()
            # publish an initial telemetry message to indicate power state (retained)
            try:
                telemetry = {"power": True, "power_state": "ON", "mode": self.mode}
                telemetry.update(self.read_sensors())
                self.mqtt_client.publish(MQTT_TOPIC_TELEMETRY, json.dumps(telemetry), qos=1, retain=True)
            except Exception as e:
                print(f"Failed to publish initial telemetry: {e}")
        except Exception as e:
            print(f"Power on failure: {e}")
            self.power_state = "OFF"

    def power_off(self):
        if self.power_state == "OFF": return
        print("Powering OFF rover systems...")
        self.power_state = "OFF"; self.stop(); self.pwm_left.stop(); self.pwm_right.stop()
        # stop any reconnect attempts
        try:
            self._reconnect_stop.set()
        except Exception:
            pass
        try:
            # publish a final OFF state (boolean) so the server/front-end knows rover is offline (retained)
            self.mqtt_client.publish(MQTT_TOPIC_TELEMETRY, json.dumps({"power": False, "power_state": "OFF", "mode": self.mode}), qos=1, retain=True)
            time.sleep(0.1)
        except Exception as e:
            print(f"Could not publish final OFF state: {e}")
        try:
            self.mqtt_client.loop_stop(); self.mqtt_client.disconnect()
        except Exception:
            pass
        GPIO.output(MODE_LEDS, GPIO.LOW)

    # no button callback — power is controlled via code or MQTT commands

    def stop(self):
        self.pwm_left.ChangeDutyCycle(0); self.pwm_right.ChangeDutyCycle(0)
        GPIO.output([IN1, IN2, IN3, IN4], GPIO.LOW)

    def move(self, left_speed, right_speed):
        if left_speed > 0: GPIO.output(IN1, GPIO.HIGH); GPIO.output(IN2, GPIO.LOW)
        else: GPIO.output(IN1, GPIO.LOW); GPIO.output(IN2, GPIO.HIGH)
        self.pwm_left.ChangeDutyCycle(abs(left_speed))
        if right_speed > 0: GPIO.output(IN3, GPIO.HIGH); GPIO.output(IN4, GPIO.LOW)
        else: GPIO.output(IN3, GPIO.LOW); GPIO.output(IN4, GPIO.HIGH)
        self.pwm_right.ChangeDutyCycle(abs(right_speed))

    def get_distance(self):
        # Robust HC-SR04 read with timeouts; returns distance in cm or None on timeout/error
        try:
            GPIO.output(TRIG, False)
            time.sleep(0.00005)
            GPIO.output(TRIG, True)
            time.sleep(0.00001)
            GPIO.output(TRIG, False)

            start = time.time()
            timeout = start + 0.05  # 50 ms to wait for echo start
            while GPIO.input(ECHO) == 0 and time.time() < timeout:
                pass
            if time.time() >= timeout:
                return None
            pulse_start = time.time()

            timeout = pulse_start + 0.05  # 50 ms max pulse width
            while GPIO.input(ECHO) == 1 and time.time() < timeout:
                pass
            pulse_end = time.time()

            if pulse_end <= pulse_start:
                return None
            duration = pulse_end - pulse_start
            distance_cm = (duration * 34300) / 2
            return round(distance_cm, 2)
        except Exception:
            return None

    def read_sensors(self):
        try:
            self.last_temp = self.dht_device.temperature
            self.last_humidity = self.dht_device.humidity
        except RuntimeError as error:
            print(f"DHT22 Read Error: {error.args[0]}")
        except Exception as error:
            try:
                self.dht_device.exit()
            except Exception:
                pass
            raise error

        distance = self.get_distance()
        # Map sensor names to the names expected by the server/frontend
        result = {
            "temperature_c": self.last_temp,
            "humidity_percent": self.last_humidity,
            "air_quality_raw": None,
            "forward_distance_cm": None
        }
        try:
            result["air_quality_raw"] = int(self.mq135_channel.value)
        except Exception:
            result["air_quality_raw"] = None
        result["forward_distance_cm"] = distance if distance is not None else None
        return result
            
    def run(self):
        print("Rover initialized.")
        try:
            while True:
                with self.state_lock:
                    powered = (self.power_state == "ON")
                if powered:
                    telemetry = self.read_sensors()
                    # include standardized mode and boolean power
                    with self.state_lock:
                        telemetry['mode'] = self.mode
                        telemetry['power'] = True
                        telemetry['power_state'] = self.power_state
                    # publish telemetry (allow None values)
                    try:
                        self.mqtt_client.publish(MQTT_TOPIC_TELEMETRY, json.dumps(telemetry))
                    except Exception as e:
                        print(f"Telemetry publish failed: {e}")

                    # movement logic uses lowercase mode names
                    distance_val = telemetry.get('forward_distance_cm') if telemetry.get('forward_distance_cm') is not None else telemetry.get('distance', 999)

                    with self.state_lock:
                        current_mode = self.mode
                        current_command = self.last_command

                    if current_mode == "manual":
                        if current_command == "forward": self.move(80, 80)
                        elif current_command == "backward": self.move(-80, -80)
                        elif current_command == "left": self.move(-70, 70)
                        elif current_command == "right": self.move(70, -70)
                        else: self.stop()
                    elif current_mode == "assisted":
                        if distance_val is not None and distance_val <= SAFE_DISTANCE_CM and current_command == "forward":
                            self.stop()
                        else:
                            if current_command == "forward": self.move(80, 80)
                            elif current_command == "backward": self.move(-80, -80)
                            elif current_command == "left": self.move(-70, 70)
                            elif current_command == "right": self.move(70, -70)
                            else: self.stop()
                    elif current_mode == "autonomous":
                        if distance_val is None or distance_val > SAFE_DISTANCE_CM: self.move(70, 70)
                        else: self.move(-70, -70); time.sleep(0.5); self.move(70, -70); time.sleep(0.7)
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Program exiting.")
        finally:
            self.power_off()
            GPIO.cleanup()

if __name__ == "__main__":
    rover = Rover()
    rover.run()