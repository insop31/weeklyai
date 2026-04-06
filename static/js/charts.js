const COLORS = {
  lime: '#C5F135',
  limeAlpha: 'rgba(197,241,53,0.3)',
  purple: '#B8B0E8',
  purpleAlpha: 'rgba(184,176,232,0.3)',
  active: '#5B4FD4',
  activeAlpha: 'rgba(91,79,212,0.15)',
  muted: 'rgba(180,170,220,0.4)',
  text: '#2D2B55',
  textMuted: '#8E8BAE',
  grid: 'rgba(200,195,230,0.4)',
  catColors: {
    Work: '#5B4FD4',
    Personal: '#B8B0E8',
    Health: '#C5F135',
    Study: '#7C6FE0',
  },
};

function applyChartDefaults() {
  if (!window.Chart) return;

  Chart.defaults.font.family = "'Plus Jakarta Sans', sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = COLORS.textMuted;
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.plugins.tooltip.backgroundColor = '#FFFFFF';
  Chart.defaults.plugins.tooltip.titleColor = COLORS.text;
  Chart.defaults.plugins.tooltip.bodyColor = COLORS.textMuted;
  Chart.defaults.plugins.tooltip.borderColor = 'rgba(180,170,220,0.35)';
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
}

function initAnalyticsCharts(data) {
  applyChartDefaults();
  renderDonut(data);
  renderBarChart(data);
  renderLineChart(data);
  renderCategoryChart(data);
  renderHabitChart(data);
}

function renderDonut(data) {
  const canvas = document.getElementById('donutChart');
  if (!canvas) return;

  new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: ['Completed', 'Pending', 'Missed'],
      datasets: [{
        data: [data.completed, data.pending, data.missed],
        backgroundColor: [COLORS.lime, COLORS.purple, COLORS.muted],
        borderWidth: 0,
        borderRadius: 4,
        spacing: 3,
      }],
    },
    options: {
      cutout: '72%',
      responsive: true,
    },
  });
}

function renderBarChart(data) {
  const canvas = document.getElementById('barChart');
  if (!canvas) return;
  const labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: data.daily,
        backgroundColor: data.daily.map(value => value > 0 ? COLORS.lime : COLORS.muted),
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: COLORS.grid }, beginAtZero: true, ticks: { stepSize: 1, precision: 0 } },
      },
    },
  });
}

function renderLineChart(data) {
  const canvas = document.getElementById('lineChart');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  const grad = ctx.createLinearGradient(0, 0, 0, 200);
  grad.addColorStop(0, COLORS.limeAlpha);
  grad.addColorStop(1, 'rgba(197,241,53,0)');

  new Chart(canvas, {
    type: 'line',
    data: {
      labels: data.progress_labels,
      datasets: [{
        data: data.progress_values,
        borderColor: COLORS.lime,
        backgroundColor: grad,
        borderWidth: 2.5,
        pointRadius: 5,
        pointBackgroundColor: COLORS.lime,
        pointBorderColor: '#FFFFFF',
        pointBorderWidth: 2,
        tension: 0.4,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: COLORS.grid }, beginAtZero: true, ticks: { stepSize: 1, precision: 0 } },
      },
    },
  });
}

function renderCategoryChart(data) {
  const canvas = document.getElementById('categoryChart');
  if (!canvas) return;

  const categories = Object.keys(data.category_hours || {});
  const hours = Object.values(data.category_hours || {});
  const bgColors = categories.map(category => COLORS.catColors[category] || COLORS.purple);

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: categories,
      datasets: [{
        data: hours,
        backgroundColor: bgColors,
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      scales: {
        x: { grid: { color: COLORS.grid }, beginAtZero: true },
        y: { grid: { display: false } },
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.parsed.x} hours`,
          },
        },
      },
    },
  });
}

function renderHabitChart(data) {
  const canvas = document.getElementById('habitChart');
  if (!canvas) return;

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: data.habit_labels,
      datasets: [{
        data: data.habit_percentages,
        backgroundColor: COLORS.active,
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      scales: {
        x: { grid: { display: false } },
        y: {
          grid: { color: COLORS.grid },
          beginAtZero: true,
          max: 100,
          ticks: {
            callback: value => `${value}%`,
          },
        },
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.parsed.y}% consistent`,
          },
        },
      },
    },
  });
}
