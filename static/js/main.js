function postJson(url, body) {
    return fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    }).then(r => r.json()).catch(() => ({}));
}

// Movement controls
document.querySelectorAll('[data-direction]')
    .forEach(btn => btn.addEventListener('click', async () => {
        const command = btn.getAttribute('data-direction');
        btn.classList.add('pressed');
        setTimeout(() => btn.classList.remove('pressed'), 150);
        await postJson('/command', { command });
    }));

// Mode selector
document.querySelectorAll('.mode-button')
    .forEach(btn => btn.addEventListener('click', async () => {
        document.querySelectorAll('.mode-button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const mode = btn.getAttribute('data-mode');
        await postJson('/command', { command: 'mode_change', mode });
        const label = 'Current Mode: ' + mode.charAt(0).toUpperCase() + mode.slice(1);
        const cm = document.getElementById('current-mode');
        if (cm) cm.textContent = label;
    }));

// Poll telemetry
async function poll() {
    try {
        const res = await fetch('/api/data');
        const data = await res.json();
        const power = !!data.power;
        const ps = document.getElementById('power-state');
        if (ps) {
            ps.textContent = 'Rover Power: ' + (power ? 'ON' : 'OFF');
            ps.classList.toggle('on', power);
            ps.classList.toggle('off', !power);
        }
        if (data.mode) {
            const cm = document.getElementById('current-mode');
            if (cm) cm.textContent = 'Current Mode: ' + String(data.mode).charAt(0).toUpperCase() + String(data.mode).slice(1);
        }
        if (data.last_seen) {
            const ls = document.getElementById('last-seen');
            if (ls) ls.textContent = 'Last Seen: ' + data.last_seen;
        }
        if (power) {
            // support multiple possible field names coming from MQTT vs CSV
            const forward = (data.forward_distance_cm !== undefined) ? data.forward_distance_cm : data.forward_distance;
            if (forward !== undefined) {
                const el = document.getElementById('forward-distance');
                if (el) el.textContent = String(forward) + ' cm';
            }

            const temp = (data.temperature_c !== undefined) ? data.temperature_c : data.temperature;
            if (temp !== undefined) {
                const el = document.getElementById('temperature');
                if (el) el.textContent = Number(temp).toFixed(2) + ' °C';
            }

            const hum = (data.humidity_percent !== undefined) ? data.humidity_percent : data.humidity;
            if (hum !== undefined) {
                const el = document.getElementById('humidity');
                if (el) el.textContent = Number(hum).toFixed(2) + ' %';
            }

            const aq = (data.air_quality_raw !== undefined) ? data.air_quality_raw : data.air_quality;
            if (aq !== undefined) {
                const el = document.getElementById('air-quality');
                if (el) el.textContent = String(aq);
            }
        }
    } catch (e) { /* ignore */ }
}
poll();
setInterval(poll, 1000);


