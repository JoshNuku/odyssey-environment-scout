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

// Power toggle (use the hidden checkbox inside the iOS-style toggle)
const powerCheckbox = document.getElementById("power-toggle-checkbox");
const powerMobileBtn = document.getElementById("power-toggle-mobile");
let ignorePowerCheckboxChange = false;
if (powerCheckbox) {
  powerCheckbox.addEventListener("change", async () => {
    if (ignorePowerCheckboxChange) return;
    const checked = powerCheckbox.checked;
    const cmd = checked ? "power_on" : "power_off";
    // optimistic UI change
    const ps = document.getElementById("power-state");
    if (ps) {
      ps.textContent = "Rover Power: " + (checked ? "ON" : "OFF");
      ps.classList.toggle("on", checked);
      ps.classList.toggle("off", !checked);
    }
    // update unified button UI
    if (powerMobileBtn) {
      powerMobileBtn.classList.toggle('on', checked);
      powerMobileBtn.classList.toggle('off', !checked);
      powerMobileBtn.setAttribute('aria-pressed', String(checked));
      powerMobileBtn.textContent = checked ? 'On' : 'Off';
    }
    await postJson("/command", { command: cmd });
  });
}

// Mobile / unified button handler
if (powerMobileBtn) {
  powerMobileBtn.addEventListener('click', async () => {
    // toggle visual state immediately
    const isOn = powerMobileBtn.classList.contains('on');
    const newState = !isOn;
    powerMobileBtn.classList.toggle('on', newState);
    powerMobileBtn.classList.toggle('off', !newState);
    powerMobileBtn.setAttribute('aria-pressed', String(newState));
    powerMobileBtn.textContent = newState ? 'On' : 'Off';
    // also sync the hidden checkbox to keep polling logic simple
    if (powerCheckbox) {
      ignorePowerCheckboxChange = true;
      powerCheckbox.checked = newState;
      setTimeout(() => { ignorePowerCheckboxChange = false; }, 0);
    }
    const cmd = newState ? 'power_on' : 'power_off';
    await postJson('/command', { command: cmd });
  });
}

// Movement controls (scope to .ps-controls to avoid colliding with other buttons)
document.querySelectorAll(".ps-controls [data-direction]").forEach((btn) => {
  // guard to prevent double-send while a press is being handled
  let sending = false;
  const sendCommand = async () => {
    if (sending) return;
    sending = true;
    const command = btn.getAttribute("data-direction");
    btn.classList.add("pressed");
    try {
      await postJson("/command", { command });
    } catch (e) {
      // ignore
    } finally {
      setTimeout(() => {
        btn.classList.remove("pressed");
        sending = false;
      }, 150);
    }
  };

  // pointerdown handles touch/mouse immediately (avoids 300ms delays on some browsers)
  btn.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    sendCommand();
  });

  // keyboard accessibility
  btn.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      sendCommand();
    }
  });
});

// Mode selector (buttons are .chip.mode-button inside .mode-selector)
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
    // optimistic local override for a few seconds to avoid poll clobbering the UI
    localModeOverride.mode = mode;
    localModeOverride.expires = Date.now() + 5000; // 5 seconds
    const label =
      "Current Mode: " + mode.charAt(0).toUpperCase() + mode.slice(1);
    const cm = document.getElementById("current-mode");
    if (cm) cm.textContent = label;
    await postJson("/command", { command: "mode_change", mode });
  })
);

// Poll telemetry
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
      // sync the checkbox without triggering its handler
      if (powerCheckbox) {
        ignorePowerCheckboxChange = true;
        powerCheckbox.checked = power;
        // allow the event loop to clear the ignore flag
        setTimeout(() => {
          ignorePowerCheckboxChange = false;
        }, 0);
      }
    }
    // Update unified power button so UI stays in sync
    if (powerMobileBtn) {
      powerMobileBtn.classList.toggle('on', power);
      powerMobileBtn.classList.toggle('off', !power);
      powerMobileBtn.setAttribute('aria-pressed', String(power));
      powerMobileBtn.textContent = power ? 'On' : 'Off';
    }
    if (data.mode) {
      // If we have a recent local override, prefer it until it expires unless server confirms the change
      if (localModeOverride.mode && Date.now() < localModeOverride.expires) {
        if (data.mode === localModeOverride.mode) {
          // server confirms, clear override and sync UI
          localModeOverride.mode = null;
          localModeOverride.expires = 0;
          setActiveModeButton(data.mode);
          const cm = document.getElementById("current-mode");
          if (cm)
            cm.textContent =
              "Current Mode: " +
              String(data.mode).charAt(0).toUpperCase() +
              String(data.mode).slice(1);
        } else {
          // still waiting for server — do not overwrite local UI
        }
      } else {
        // No override in effect — update UI from server
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
      // support multiple possible field names coming from MQTT vs CSV
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
        if (el) el.textContent = String(aq);
      }
    }
  } catch (e) {
    /* ignore */
  }
}
poll();
setInterval(poll, 1000);
