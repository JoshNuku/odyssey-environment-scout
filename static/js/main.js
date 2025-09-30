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
            if (data.forward_distance_cm !== undefined) {
                const el = document.getElementById('forward-distance');
                if (el) el.textContent = data.forward_distance_cm + ' cm';
            }
            if (data.temperature_c !== undefined) {
                const el = document.getElementById('temperature');
                if (el) el.textContent = data.temperature_c + ' °C';
            }
            if (data.humidity_percent !== undefined) {
                const el = document.getElementById('humidity');
                if (el) el.textContent = data.humidity_percent + ' %';
            }
            if (data.air_quality_raw !== undefined) {
                const el = document.getElementById('air-quality');
                if (el) el.textContent = String(data.air_quality_raw);
            }
        }
    } catch (e) { /* ignore */ }
}
poll();
setInterval(poll, 1000);


