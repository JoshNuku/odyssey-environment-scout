function postJson(url, body) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
    .then((r) => r.json())
    .catch(() => ({}));
}

let localModeOverride = { mode: null, expires: 0 };

// Power toggle
const powerCheckbox = document.getElementById("power-toggle-checkbox");
const powerMobileBtn = document.getElementById("power-toggle-mobile");
let ignorePowerCheckboxChange = false;

if (powerCheckbox) {
  powerCheckbox.addEventListener("change", async () => {
    if (ignorePowerCheckboxChange) return;
    const checked = powerCheckbox.checked;
    const cmd = checked ? "power_on" : "power_off";

    const ps = document.getElementById("power-state");
    if (ps) {
      ps.textContent = "Rover Power: " + (checked ? "ON" : "OFF");
      ps.classList.toggle("on", checked);
      ps.classList.toggle("off", !checked);
    }

    if (powerMobileBtn) {
      powerMobileBtn.classList.toggle("on", checked);
      powerMobileBtn.classList.toggle("off", !checked);
      powerMobileBtn.setAttribute("aria-pressed", String(checked));
      powerMobileBtn.textContent = checked ? "On" : "Off";
    }
    await postJson("/command", { command: cmd });
  });
}

if (powerMobileBtn) {
  powerMobileBtn.addEventListener("click", async () => {
    const isOn = powerMobileBtn.classList.contains("on");
    const newState = !isOn;
    powerMobileBtn.classList.toggle("on", newState);
    powerMobileBtn.classList.toggle("off", !newState);
    powerMobileBtn.setAttribute("aria-pressed", String(newState));
    powerMobileBtn.textContent = newState ? "On" : "Off";

    if (powerCheckbox) {
      ignorePowerCheckboxChange = true;
      powerCheckbox.checked = newState;
      setTimeout(() => {
        ignorePowerCheckboxChange = false;
      }, 0);
    }
    const cmd = newState ? "power_on" : "power_off";
    await postJson("/command", { command: cmd });
  });
}

// ================= Movement controls (UI + Gamepad reuse) =================
async function handleDirection(direction) {
  console.log("Direction:", direction);
  await postJson("/command", { command: direction });

  const btn = document.querySelector(
    `.ps-controls [data-direction="${direction}"]`
  );
  if (btn) {
    btn.classList.add("pressed");
    setTimeout(() => btn.classList.remove("pressed"), 150);
  }
}

document.querySelectorAll(".ps-controls [data-direction]").forEach((btn) => {
  let sending = false;
  const sendCommand = async () => {
    if (sending) return;
    sending = true;
    const command = btn.getAttribute("data-direction");
    await handleDirection(command);
    setTimeout(() => {
      sending = false;
    }, 150);
  };

  btn.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    sendCommand();
  });

  btn.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      sendCommand();
    }
  });
});

// ================= Mode selector =================
function setActiveModeButton(mode) {
  document
    .querySelectorAll(".mode-selector .mode-button")
    .forEach((b) =>
      b.classList.toggle("active", b.getAttribute("data-mode") === mode)
    );
}

document.querySelectorAll(".mode-selector .mode-button").forEach((btn) =>
  btn.addEventListener("click", async () => {
    document
      .querySelectorAll(".mode-selector .mode-button")
      .forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const mode = btn.getAttribute("data-mode");
    localModeOverride.mode = mode;
    localModeOverride.expires = Date.now() + 5000;

    const label =
      "Current Mode: " + mode.charAt(0).toUpperCase() + mode.slice(1);
    const cm = document.getElementById("current-mode");
    if (cm) cm.textContent = label;
    await postJson("/command", { command: "mode_change", mode });
  })
);

// ================= Gamepad Support =================
let gamepadIndex = null;
let prevButtons = [];
let lastAxisCommand = null;

window.addEventListener("gamepadconnected", (e) => {
  console.log("Gamepad connected:", e.gamepad);
  gamepadIndex = e.gamepad.index;
});

window.addEventListener("gamepaddisconnected", (e) => {
  console.log("Gamepad disconnected:", e.gamepad);
  gamepadIndex = null;
});

function pollGamepad() {
  if (gamepadIndex !== null) {
    const gp = navigator.getGamepads()[gamepadIndex];
    if (gp) {
      // --- Buttons ---
      gp.buttons.forEach((btn, i) => {
        if (btn.pressed && !prevButtons[i]) {
          handleButtonPress(i);
        }
      });

      // --- D-Pad ---
      console.log("D-Pad state:", {
        up: gp.buttons[12]?.pressed,
        down: gp.buttons[13]?.pressed,
        left: gp.buttons[14]?.pressed,
        right: gp.buttons[15]?.pressed,
      });

      if (gp.buttons[12]?.pressed) handleDirection("forward");
      if (gp.buttons[13]?.pressed) handleDirection("backward");
      if (gp.buttons[14]?.pressed) handleDirection("left");
      if (gp.buttons[15]?.pressed) handleDirection("right");

      // --- Left Stick ---
      const x = gp.axes[0];
      const y = gp.axes[1];
      const deadzone = 0.4;
      let axisCommand = null;

      if (Math.abs(x) > Math.abs(y)) {
        if (x > deadzone) axisCommand = "right";
        else if (x < -deadzone) axisCommand = "left";
      } else {
        if (y > deadzone) axisCommand = "backward";
        else if (y < -deadzone) axisCommand = "forward";
      }

      if (axisCommand && axisCommand !== lastAxisCommand) {
        handleDirection(axisCommand);
        lastAxisCommand = axisCommand;
      }
      if (!axisCommand) {
        lastAxisCommand = null;
      }

      prevButtons = gp.buttons.map((b) => b.pressed);
    }
  }
  requestAnimationFrame(pollGamepad);
}
pollGamepad();

async function handleButtonPress(index) {
  switch (index) {
    case 2: // X
      console.log("X pressed → toggle power");
      if (powerCheckbox) {
        powerCheckbox.checked = !powerCheckbox.checked;
        powerCheckbox.dispatchEvent(new Event("change"));
      }
      break;
    case 3: // Y
      console.log("Y pressed → Manual mode");
      await postJson("/command", { command: "mode_change", mode: "manual" });
      setActiveModeButton("manual");
      break;
    case 1: // B
      console.log("B pressed → Assisted mode");
      await postJson("/command", { command: "mode_change", mode: "assisted" });
      setActiveModeButton("assisted");
      break;
    case 0: // A
      console.log("A pressed → Autonomous mode");
      await postJson("/command", {
        command: "mode_change",
        mode: "autonomous",
      });
      setActiveModeButton("autonomous");
      break;
    case 9: // Start/Pause
      console.log("Pause pressed → STOP");
      await postJson("/command", { command: "stop" });
      break;
  }
}

// ================= Poll telemetry (unchanged) =================
async function poll() {
  try {
    const res = await fetch("/api/data");
    const data = await res.json();
    const power = !!data.power;
    const ps = document.getElementById("power-state");
    if (ps) {
      ps.textContent = "Rover Power: " + (power ? "ON" : "OFF");
      ps.classList.toggle("on", power);
      ps.classList.toggle("off", !power);
      if (powerCheckbox) {
        ignorePowerCheckboxChange = true;
        powerCheckbox.checked = power;
        setTimeout(() => {
          ignorePowerCheckboxChange = false;
        }, 0);
      }
    }
    if (powerMobileBtn) {
      powerMobileBtn.classList.toggle("on", power);
      powerMobileBtn.classList.toggle("off", !power);
      powerMobileBtn.setAttribute("aria-pressed", String(power));
      powerMobileBtn.textContent = power ? "On" : "Off";
    }
    if (data.mode) {
      if (localModeOverride.mode && Date.now() < localModeOverride.expires) {
        if (data.mode === localModeOverride.mode) {
          localModeOverride.mode = null;
          localModeOverride.expires = 0;
          setActiveModeButton(data.mode);
          const cm = document.getElementById("current-mode");
          if (cm)
            cm.textContent =
              "Current Mode: " +
              String(data.mode).charAt(0).toUpperCase() +
              String(data.mode).slice(1);
        }
      } else {
        setActiveModeButton(data.mode);
        const cm = document.getElementById("current-mode");
        if (cm)
          cm.textContent =
            "Current Mode: " +
            String(data.mode).charAt(0).toUpperCase() +
            String(data.mode).slice(1);
      }
    }
    if (data.last_seen) {
      const ls = document.getElementById("last-seen");
      if (ls) ls.textContent = "Last Seen: " + data.last_seen;
    }
    if (power) {
      const forward =
        data.forward_distance_cm !== undefined
          ? data.forward_distance_cm
          : data.forward_distance;
      if (forward !== undefined) {
        const el = document.getElementById("forward-distance");
        if (el) el.textContent = String(forward) + " cm";
      }

      const temp =
        data.temperature_c !== undefined
          ? data.temperature_c
          : data.temperature;
      if (temp !== undefined) {
        const el = document.getElementById("temperature");
        if (el) el.textContent = Number(temp).toFixed(2) + " °C";
      }

      const hum =
        data.humidity_percent !== undefined
          ? data.humidity_percent
          : data.humidity;
      if (hum !== undefined) {
        const el = document.getElementById("humidity");
        if (el) el.textContent = Number(hum).toFixed(2) + " %";
      }

      const aq =
        data.air_quality_raw !== undefined
          ? data.air_quality_raw
          : data.air_quality;
      if (aq !== undefined) {
        const el = document.getElementById("air-quality");
        if (el) {
          // display both raw and estimated ppm
          const ppm = aqRawToPpm(aq);
          el.textContent = `${ppm} ppm`;
          el.title = `Raw: ${aq}`;
          el.classList.add("aq-ppm");
        }
      }
    }
  } catch (e) {
    /* ignore */
  }
}
poll();
setInterval(poll, 1000);

// Theme toggle
const themeToggle = document.getElementById("theme-toggle");
if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    document.documentElement.classList.toggle("light-theme");
    const isLight = document.documentElement.classList.contains("light-theme");
    themeToggle.textContent = isLight ? "Dark" : "Light";
  });
}

// Convert raw ADC value to approximate ppm using 3.5V reference
function aqRawToPpm(raw) {
  // raw expected 0..32767 (ADS1115 16-bit signed positive range used here), scale to voltage
  const maxRaw = 32767;
  const refV = 3.5; // 3.5V reference per request
  const voltage = (Number(raw) / maxRaw) * refV;
  // Simple linear conversion: map 0..3.5V -> 0..1000 ppm (tunable)
  const ppm = (voltage / refV) * 1000.0;
  return Math.round(ppm);
}
