/**
 * calendar.js — WeeklyAI
 * Handles:
 *   - Weekly grid rendering (day columns, time rows)
 *   - Task event card absolute positioning by start_time / end_time
 *   - Mini calendar rendering with month navigation
 *   - Week navigation (prev / next)
 *   - Card interaction: done, delete, reschedule via fetch
 */

/* ─────────────────────────────────────────
   Constants
───────────────────────────────────────── */
const HOUR_START   = 0;     // grid starts at 00:00
const HOUR_END     = 24;    // grid ends at 24:00
const SLOT_H       = 80;    // px per hour row
const DAYS         = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
const MONTHS       = ['January','February','March','April','May','June',
                      'July','August','September','October','November','December'];

/* ─────────────────────────────────────────
   State
───────────────────────────────────────── */
let currentWeekOffset = 0;   // 0 = this week, -1 = last week, +1 = next week
let miniCalOffset     = 0;   // months relative to today
let allTasks          = [];  // parsed from #task-data JSON
let calendarEvents    = [];  // parsed from #calendar-event-data JSON
let selectedMiniDate  = null;

/* ─────────────────────────────────────────
   Entry point — called from dashboard.html
───────────────────────────────────────── */
function initCalendar() {
  // Parse task data embedded by Jinja
  const dataEl = document.getElementById('task-data');
  if (dataEl) {
    try {
      allTasks = JSON.parse(dataEl.textContent);
    } catch (e) {
      console.error('WeeklyAI: failed to parse task data', e);
      allTasks = [];
    }
  }

  const eventEl = document.getElementById('calendar-event-data');
  if (eventEl) {
    try {
      calendarEvents = JSON.parse(eventEl.textContent);
    } catch (e) {
      console.error('WeeklyAI: failed to parse calendar event data', e);
      calendarEvents = [];
    }
  }

  selectedMiniDate = toDateKey(new Date());

  renderWeek();
  renderMiniCal();
  renderSelectedDateEvents();
  bindNavButtons();
}

/* ─────────────────────────────────────────
   Week rendering
───────────────────────────────────────── */
function getWeekDates(offset) {
  const today  = new Date();
  const dow    = today.getDay();                  // 0=Sun…6=Sat
  const monday = new Date(today);
  // Adjust so Monday=0
  const diffToMon = (dow === 0) ? -6 : 1 - dow;
  monday.setDate(today.getDate() + diffToMon + offset * 7);

  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    return d;
  });
}

function renderWeek() {
  const weekDates = getWeekDates(currentWeekOffset);
  const today     = new Date();

  // Update topbar grid date label
  const label = document.getElementById('gridDateLabel');
  if (label) {
    const first = weekDates[0];
    const last  = weekDates[6];
    label.textContent =
      `${MONTHS[first.getMonth()].slice(0,3)} ${first.getDate()} – ` +
      `${MONTHS[last.getMonth()].slice(0,3)} ${last.getDate()}, ${last.getFullYear()}`;
  }

  // Render each day column header + body
  weekDates.forEach((date, i) => {
    const numEl = document.getElementById(`col-num-${i}`);
    if (!numEl) return;

    const isToday = isSameDay(date, today);
    numEl.textContent    = date.getDate();
    numEl.className      = 'col-day-num' + (isToday ? ' today-num' : '');

    // Render time-row backgrounds + task cards into the body
    const body = document.querySelector(`.day-col-body[data-day="${i}"]`);
    if (!body) return;
    body.innerHTML = '';

    // Background time rows
    const rowCount = HOUR_END - HOUR_START;
    for (let r = 0; r < rowCount; r++) {
      const row = document.createElement('div');
      row.className = 'time-row-bg';
      body.appendChild(row);
    }

    // Filter tasks for this column date
    const dayTasks = allTasks.filter(t => {
      if (!t.start_time) return false;
      const d = new Date(t.start_time);
      return isSameDay(d, date);
    });

    dayTasks.forEach(task => placeTaskCard(body, task));
  });
}

/* ─────────────────────────────────────────
   Task card positioning
───────────────────────────────────────── */
function placeTaskCard(container, task) {
  if (!task.start_time) return;

  const start    = new Date(task.start_time);
  const end      = task.end_time ? new Date(task.end_time) : new Date(start.getTime() + 60 * 60 * 1000);

  const startMin = (start.getHours() - HOUR_START) * 60 + start.getMinutes();
  const endMin   = (end.getHours()   - HOUR_START) * 60 + end.getMinutes();

  // Skip if outside visible range
  if (endMin <= 0 || startMin >= (HOUR_END - HOUR_START) * 60) return;

  const clampedStart = Math.max(startMin, 0);
  const clampedEnd   = Math.min(endMin, (HOUR_END - HOUR_START) * 60);

  const topPx    = (clampedStart / 60) * SLOT_H;
  const heightPx = Math.max(((clampedEnd - clampedStart) / 60) * SLOT_H, 36);

  const card = document.createElement('div');
  card.className = `event-card ${cardColorClass(task)}`;
  if (taskIsUrgent(task)) card.classList.add('event-card-urgent');
  card.style.cssText = `top:${topPx}px; height:${heightPx}px;`;
  card.dataset.taskId = task.id;

  // Format time label
  const timeLabel = formatTime(start) + ' – ' + formatTime(end);

  // Build attendee bubbles (max 3)
  const bubbleCount = Math.min(task.attendees || 1, 3);
  const initials    = ['A','B','C','D','E'];
  let bubblesHTML   = '';
  if (bubbleCount > 1) {
    bubblesHTML = `<div class="attendee-row">`;
    for (let b = 0; b < bubbleCount; b++) {
      bubblesHTML += `<div class="attendee-bubble">${initials[b]}</div>`;
    }
    if ((task.attendees || 1) > 3) {
      bubblesHTML += `<div class="attendee-bubble">+${task.attendees - 3}</div>`;
    }
    bubblesHTML += `</div>`;
  }

  card.innerHTML = `
    <div class="event-actions">
      <button class="event-action-btn" onclick="event.stopPropagation();markDone(${task.id})" title="Mark done">✓</button>
      <button class="event-action-btn" onclick="event.stopPropagation();deleteTask(${task.id})" title="Delete">✕</button>
    </div>
    <div class="event-title">${escapeHtml(task.title)}</div>
    <div class="event-time">${timeLabel}</div>
    ${bubblesHTML}
  `;

  // Strike-through done tasks
  if (task.status === 'Completed') card.classList.add('card-done');

  container.appendChild(card);
}

/* ─────────────────────────────────────────
   Mini calendar rendering
───────────────────────────────────────── */
function renderMiniCal() {
  const today  = new Date();
  const target = new Date(today.getFullYear(), today.getMonth() + miniCalOffset, 1);
  const year   = target.getFullYear();
  const month  = target.getMonth();

  const labelEl = document.getElementById('calMonthLabel');
  if (labelEl) labelEl.textContent = `${MONTHS[month]} ${year}`;

  const container = document.getElementById('miniCalDays');
  if (!container) return;
  container.innerHTML = '';

  // First day of month (adjusted so Mon=0)
  const firstDow = (new Date(year, month, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrev  = new Date(year, month, 0).getDate();

  // Task dates set for dot indicators
  const taskDates = new Set(
    allTasks
      .filter(t => t.start_time)
      .map(t => {
        const d = new Date(t.start_time);
        return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      })
  );
  const eventDates = new Set(
    calendarEvents.map(event => event.event_date)
  );

  // Prev month trailing days
  for (let p = firstDow - 1; p >= 0; p--) {
    appendCalDay(container, daysInPrev - p, true, false, false);
  }

  // Current month days
  for (let d = 1; d <= daysInMonth; d++) {
    const isToday   = (d === today.getDate() && month === today.getMonth() && year === today.getFullYear());
    const key       = `${year}-${month}-${d}`;
    const isoDate   = formatIsoDate(year, month, d);
    const hasTask   = taskDates.has(key);
    const hasEvent  = eventDates.has(isoDate);
    appendCalDay(container, d, false, isToday, hasTask || hasEvent, isoDate);
  }

  // Next month leading days (fill to complete 6 rows = 42 cells)
  const total = firstDow + daysInMonth;
  const remainder = total % 7 === 0 ? 0 : 7 - (total % 7);
  for (let n = 1; n <= remainder; n++) {
    appendCalDay(container, n, true, false, false, null);
  }
}

function appendCalDay(container, num, otherMonth, isToday, hasTask, isoDate) {
  const cell = document.createElement('div');
  cell.className = 'cal-day-cell' +
    (otherMonth ? ' other-month' : '') +
    (isToday    ? ' today'       : '') +
    (hasTask    ? ' has-task'    : '') +
    (isoDate && isoDate === selectedMiniDate ? ' selected' : '');
  cell.textContent = num;
  if (isoDate) {
    cell.dataset.date = isoDate;
    cell.addEventListener('click', () => {
      selectedMiniDate = isoDate;
      renderMiniCal();
      renderSelectedDateEvents();
    });
  }
  container.appendChild(cell);
}

/* ─────────────────────────────────────────
   Navigation button bindings
───────────────────────────────────────── */
function bindNavButtons() {
  // Week grid navigation
  const gridPrev = document.getElementById('gridPrev');
  const gridNext = document.getElementById('gridNext');
  if (gridPrev) gridPrev.addEventListener('click', () => { currentWeekOffset--; renderWeek(); });
  if (gridNext) gridNext.addEventListener('click', () => { currentWeekOffset++; renderWeek(); });

  // Mini calendar navigation
  const calPrev = document.getElementById('calPrev');
  const calNext = document.getElementById('calNext');
  if (calPrev) calPrev.addEventListener('click', () => { miniCalOffset--; renderMiniCal(); });
  if (calNext) calNext.addEventListener('click', () => { miniCalOffset++; renderMiniCal(); });
}

function goToToday() {
  currentWeekOffset = 0;
  miniCalOffset     = 0;
  selectedMiniDate  = toDateKey(new Date());
  renderWeek();
  renderMiniCal();
  renderSelectedDateEvents();
}

/* ─────────────────────────────────────────
   Task CRUD actions
───────────────────────────────────────── */
async function markDone(taskId) {
  try {
    const res = await fetch(`/update_task/${taskId}`, {
      method:  'PUT',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ status: 'Completed' }),
    });
    if (res.ok) {
      // Update local state + re-render without full reload
      const task = allTasks.find(t => t.id === taskId);
      if (task) task.status = 'Completed';
      renderWeek();
      showToast('Task marked as done');
    }
  } catch (err) {
    console.error('markDone failed:', err);
  }
}

async function deleteTask(taskId) {
  if (!confirm('Delete this task?')) return;
  try {
    const res = await fetch(`/delete_task/${taskId}`, { method: 'DELETE' });
    if (res.ok) {
      allTasks = allTasks.filter(t => t.id !== taskId);
      renderWeek();
      renderMiniCal();
      showToast('Task deleted');
    }
  } catch (err) {
    console.error('deleteTask failed:', err);
  }
}

/* ─────────────────────────────────────────
   Toast notification
───────────────────────────────────────── */
function showToast(message) {
  const existing = document.getElementById('wa-toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'wa-toast';
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: #5B4FD4;
    color: white;
    padding: 10px 18px;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 500;
    font-family: 'Plus Jakarta Sans', sans-serif;
    box-shadow: 0 4px 20px rgba(91,79,212,0.35);
    z-index: 9999;
    opacity: 0;
    transform: translateY(8px);
    transition: opacity 0.2s, transform 0.2s;
  `;
  document.body.appendChild(toast);

  // Animate in
  requestAnimationFrame(() => {
    toast.style.opacity   = '1';
    toast.style.transform = 'translateY(0)';
  });

  // Auto-dismiss after 2.5s
  setTimeout(() => {
    toast.style.opacity   = '0';
    toast.style.transform = 'translateY(8px)';
    setTimeout(() => toast.remove(), 250);
  }, 2500);
}

/* ─────────────────────────────────────────
   Helpers
───────────────────────────────────────── */
function isSameDay(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth()    === b.getMonth()    &&
    a.getDate()     === b.getDate()
  );
}

function formatTime(date) {
  const h   = date.getHours();
  const m   = date.getMinutes();
  const ampm = h >= 12 ? 'Pm' : 'Am';
  const h12  = h % 12 || 12;
  return m === 0
    ? `${h12} ${ampm}`
    : `${h12}:${String(m).padStart(2,'0')} ${ampm}`;
}

function cardColorClass(task) {
  if (task.color === 'lime')   return 'card-lime';
  if (task.color === 'white')  return 'card-white';
  return 'card-purple';
}

function taskIsUrgent(task) {
  if (task.status === 'Completed') return false;
  if (task.priority === 'High') return true;
  if (!task.deadline) return false;
  const deadline = new Date(task.deadline);
  return deadline.getTime() <= Date.now() + (24 * 60 * 60 * 1000);
}

function renderSelectedDateEvents() {
  const label = document.getElementById('selectedDateLabel');
  const list = document.getElementById('selectedDateEvents');
  if (!label || !list) return;

  if (!selectedMiniDate) {
    label.textContent = 'Choose a date';
    list.innerHTML = '';
    return;
  }

  const date = new Date(`${selectedMiniDate}T00:00:00`);
  label.textContent = date.toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  const dateTasks = allTasks.filter(task => task.start_time && toDateKey(new Date(task.start_time)) === selectedMiniDate);
  const dateEvents = calendarEvents.filter(event => event.event_date === selectedMiniDate);

  if (!dateTasks.length && !dateEvents.length) {
    list.innerHTML = `<div class="selected-date-empty">No tasks or events yet. <button type="button" class="mini-link-btn" onclick="openEventModal('${selectedMiniDate}')">Add one</button></div>`;
    return;
  }

  list.innerHTML = '';

  dateEvents.forEach(event => {
    const row = document.createElement('div');
    row.className = 'selected-date-item selected-date-item-event';
    row.innerHTML = `
      <div class="selected-date-item-title">${escapeHtml(event.title)}</div>
      <div class="selected-date-item-meta">${escapeHtml(event.event_type || 'Event')}</div>
    `;
    list.appendChild(row);
  });

  dateTasks.forEach(task => {
    const row = document.createElement('div');
    row.className = 'selected-date-item';
    row.innerHTML = `
      <div class="selected-date-item-title">${escapeHtml(task.title)}</div>
      <div class="selected-date-item-meta">${escapeHtml(task.priority || 'Medium')} priority task</div>
    `;
    list.appendChild(row);
  });
}

function formatIsoDate(year, month, day) {
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function toDateKey(date) {
  return formatIsoDate(date.getFullYear(), date.getMonth(), date.getDate());
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
