const BASE_COLORS = {
  mint: '#BFE9DA',
  mintAlpha: 'rgba(191,233,218,0.35)',
  peach: '#F6CFC3',
  peachAlpha: 'rgba(246,207,195,0.38)',
  lavender: '#CFC6F4',
  lavenderAlpha: 'rgba(207,198,244,0.38)',
  sky: '#C8E5F6',
  skyAlpha: 'rgba(200,229,246,0.36)',
  butter: '#F7E7A8',
  butterAlpha: 'rgba(247,231,168,0.34)',
  rose: '#EFC4DA',
  roseAlpha: 'rgba(239,196,218,0.34)',
  sage: '#D8E8C8',
  sageAlpha: 'rgba(216,232,200,0.34)',
  active: '#7A6BCF',
  activeAlpha: 'rgba(122,107,207,0.18)',
  muted: 'rgba(201,195,228,0.55)',
  text: '#2D2B55',
  textMuted: '#8E8BAE',
  grid: 'rgba(200,195,230,0.4)',
  catColors: {
    Work: ['#CFC6F4', '#B9D8F5'],
    Personal: ['#F6D7CC', '#EFC4DA'],
    Health: ['#D8E8C8', '#BFE9DA'],
    Study: ['#F7E7A8', '#F6CFC3'],
  },
};

let analyticsCharts = [];

function cssVar(name, fallback) {
  const value = getComputedStyle(document.body).getPropertyValue(name).trim();
  return value || fallback;
}

function getThemeColors() {
  const isDark = document.body.dataset.theme === 'dark';
  return {
    ...BASE_COLORS,
    text: cssVar('--text-dark', BASE_COLORS.text),
    textMuted: cssVar('--text-muted', BASE_COLORS.textMuted),
    grid: isDark ? 'rgba(185,176,233,0.18)' : BASE_COLORS.grid,
    tooltipBg: isDark ? 'rgba(32,27,54,0.96)' : '#FFFFFF',
    tooltipBorder: isDark ? 'rgba(185,176,233,0.18)' : 'rgba(180,170,220,0.35)',
    pointFill: isDark ? cssVar('--surface-base', '#201B36') : '#FFFFFF',
  };
}

function createVerticalGradient(ctx, area, start, end) {
  const gradient = ctx.createLinearGradient(0, area.top, 0, area.bottom);
  gradient.addColorStop(0, start);
  gradient.addColorStop(1, end);
  return gradient;
}

function createHorizontalGradient(ctx, area, start, end) {
  const gradient = ctx.createLinearGradient(area.left, 0, area.right, 0);
  gradient.addColorStop(0, start);
  gradient.addColorStop(1, end);
  return gradient;
}

function applyChartDefaults(colors) {
  if (!window.Chart) return;

  Chart.defaults.font.family = "'Plus Jakarta Sans', sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = colors.textMuted;
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.plugins.tooltip.backgroundColor = colors.tooltipBg;
  Chart.defaults.plugins.tooltip.titleColor = colors.text;
  Chart.defaults.plugins.tooltip.bodyColor = colors.textMuted;
  Chart.defaults.plugins.tooltip.borderColor = colors.tooltipBorder;
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
}

function initAnalyticsCharts(data) {
  const colors = getThemeColors();
  applyChartDefaults(colors);
  destroyAnalyticsCharts();
  renderDonut(data, colors);
  renderBarChart(data, colors);
  renderLineChart(data, colors);
  renderCategoryChart(data, colors);
  renderHabitChart(data, colors);
}

function destroyAnalyticsCharts() {
  analyticsCharts.forEach(chart => chart.destroy());
  analyticsCharts = [];
}

function renderDonut(data, colors) {
  const canvas = document.getElementById('donutChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.style.backgroundColor = 'transparent';
  const completedGradient = ctx.createLinearGradient(0, 0, 180, 180);
  completedGradient.addColorStop(0, colors.mint);
  completedGradient.addColorStop(1, colors.sage);
  const pendingGradient = ctx.createLinearGradient(0, 0, 180, 180);
  pendingGradient.addColorStop(0, colors.lavender);
  pendingGradient.addColorStop(1, colors.sky);
  const missedGradient = ctx.createLinearGradient(0, 0, 180, 180);
  missedGradient.addColorStop(0, colors.peach);
  missedGradient.addColorStop(1, colors.rose);

  analyticsCharts.push(new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: ['Completed', 'Pending', 'Missed'],
      datasets: [{
        data: [data.completed, data.pending, data.missed],
        backgroundColor: [completedGradient, pendingGradient, missedGradient],
        borderWidth: 0,
        borderRadius: 4,
        spacing: 3,
      }],
    },
    options: {
      cutout: '72%',
      responsive: true,
    },
  }));
}

function renderBarChart(data, colors) {
  const canvas = document.getElementById('barChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.style.backgroundColor = 'transparent';
  const labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const dayPairs = [
    [colors.mint, colors.sage],
    [colors.lavender, colors.sky],
    [colors.peach, colors.rose],
    [colors.sky, colors.mint],
    [colors.butter, colors.peach],
    [colors.rose, colors.lavender],
    [colors.sage, colors.sky],
  ];
  const gradients = dayPairs.map(([start, end]) =>
    createVerticalGradient(ctx, { top: 0, bottom: canvas.height || 220 }, start, end)
  );

  analyticsCharts.push(new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: data.daily,
        backgroundColor: data.daily.map((value, index) => value > 0 ? gradients[index] : colors.muted),
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: colors.grid }, beginAtZero: true, ticks: { stepSize: 1, precision: 0 } },
      },
    },
  }));
}

function renderLineChart(data, colors) {
  const canvas = document.getElementById('lineChart');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  canvas.style.backgroundColor = 'transparent';
  const grad = ctx.createLinearGradient(0, 0, 0, 220);
  grad.addColorStop(0, colors.lavenderAlpha);
  grad.addColorStop(0.55, colors.skyAlpha);
  grad.addColorStop(1, 'rgba(200,229,246,0)');
  const strokeGrad = ctx.createLinearGradient(0, 0, canvas.width || 360, 0);
  strokeGrad.addColorStop(0, colors.active);
  strokeGrad.addColorStop(0.5, '#8FB8E8');
  strokeGrad.addColorStop(1, '#87CBB5');

  analyticsCharts.push(new Chart(canvas, {
    type: 'line',
    data: {
      labels: data.progress_labels,
      datasets: [{
        data: data.progress_values,
        borderColor: strokeGrad,
        backgroundColor: grad,
        borderWidth: 2.5,
        pointRadius: 5,
        pointBackgroundColor: colors.pointFill,
        pointBorderColor: colors.pointFill,
        pointBorderWidth: 2,
        pointHoverBackgroundColor: colors.peach,
        pointHoverBorderColor: colors.pointFill,
        tension: 0.4,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: colors.grid }, beginAtZero: true, ticks: { stepSize: 1, precision: 0 } },
      },
    },
  }));
}

function renderCategoryChart(data, colors) {
  const canvas = document.getElementById('categoryChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.style.backgroundColor = 'transparent';

  const categories = Object.keys(data.category_hours || {});
  const hours = Object.values(data.category_hours || {});
  const bgColors = categories.map((category, index) => {
    const pair = colors.catColors[category] || [
      [colors.lavender, colors.sky],
      [colors.peach, colors.rose],
      [colors.mint, colors.sage],
      [colors.butter, colors.peach],
    ][index % 4];
    return createHorizontalGradient(ctx, { left: 0, right: canvas.width || 320 }, pair[0], pair[1]);
  });

  analyticsCharts.push(new Chart(canvas, {
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
        x: { grid: { color: colors.grid }, beginAtZero: true },
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
  }));
}

function renderHabitChart(data, colors) {
  const canvas = document.getElementById('habitChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.style.backgroundColor = 'transparent';

  analyticsCharts.push(new Chart(canvas, {
    type: 'bar',
    data: {
      labels: data.habit_labels,
      datasets: [{
        data: data.habit_percentages,
        backgroundColor: data.habit_percentages.map((_, index) => {
          const palette = [
            [colors.rose, colors.lavender],
            [colors.mint, colors.sky],
            [colors.butter, colors.peach],
            [colors.sage, colors.mint],
          ][index % 4];
          return createVerticalGradient(ctx, { top: 0, bottom: canvas.height || 220 }, palette[0], palette[1]);
        }),
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      scales: {
        x: { grid: { display: false } },
        y: {
          grid: { color: colors.grid },
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
  }));
}
