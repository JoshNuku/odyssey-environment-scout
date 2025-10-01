async function loadHistory() {
  const res = await fetch("/api/history");
  const data = await res.json();
  const labels = data.labels || [];
  const ctx1 = document.getElementById("tempChart");
  new Chart(ctx1, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Temperature (°C)",
          data: data.temperature_c || data.temperature || [],
          borderColor: "#5b8cff",
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
    },
  });

  const ctx2 = document.getElementById("humChart");
  new Chart(ctx2, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Humidity (%)",
          data: data.humidity_percent || data.humidity || [],
          borderColor: "#22d3ee",
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
    },
  });

  const ctx3 = document.getElementById("aqChart");
  new Chart(ctx3, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Air Quality (Raw)",
          data: data.air_quality_raw || data.air_quality || [],
          borderColor: "#a78bfa",
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
    },
  });
}
loadHistory();
