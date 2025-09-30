import csv
import random
import datetime
import time

def generate_dummy_logs(filename="odyssey_log.csv", rows=20, delay=1):
    # Possible states
    modes = ["Manual", "Assisted", "Autonomous"]
    power_states = ["ON", "OFF"]

    # CSV header
    header = ["timestamp", "temperature", "humidity", "air_quality", "mode", "forward_distance", "power"]

    # Create file with header
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)

    # Append rows
    with open(filename, "a", newline="") as f:
        writer = csv.writer(f)
        for _ in range(rows):
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            temperature = round(random.uniform(23.5, 26.5), 1)
            humidity = round(random.uniform(40, 60), 1)
            air_quality = random.randint(140, 180)
            mode = random.choice(modes)
            forward_distance = round(random.uniform(140.0, 160.0), 2)
            power = random.choice(power_states)

            row = [ts, temperature, humidity, air_quality, mode, forward_distance, power]
            writer.writerow(row)
            print("Generated:", row)
            time.sleep(delay)

# Run the generator
if __name__ == "__main__":
    generate_dummy_logs(rows=20, delay=1)
