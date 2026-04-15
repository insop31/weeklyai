const HOUR_START = 0;
const HOUR_END = 24;
const SLOT_H = 80;
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

let currentViewMode = "weekly";
let currentWeekOffset = 0;
let currentDayOffset = 0;
let currentMonthOffset = 0;
let miniCalOffset = 0;
let allTasks = [];
let calendarEvents = [];
let selectedMiniDate = null;

function initCalendar() {
  const dataEl = document.getElementById("task-data");
  if (dataEl) {
    try {
      allTasks = JSON.parse(dataEl.textContent);
    } catch (error) {
      console.error("TaskNova: failed to parse task data", error);
      allTasks = [];
    }
  }

  const eventEl = document.getElementById("calendar-event-data");
  if (eventEl) {
    try {
      calendarEvents = JSON.parse(eventEl.textContent);
    } catch (error) {
      console.error("TaskNova: failed to parse calendar event data", error);
      calendarEvents = [];
    }
  }

  currentViewMode = getDashboardView();
  selectedMiniDate = toDateKey(new Date());

  renderCalendarView();
  renderMiniCal();
  renderSelectedDateEvents();
  bindNavButtons();
}

function getDashboardView() {
  const params = new URLSearchParams(window.location.search);
  const view = (params.get("view") || "weekly").toLowerCase();
  return ["daily", "weekly", "monthly"].includes(view) ? view : "weekly";
}

function renderCalendarView() {
  if (currentViewMode === "monthly") {
    renderMonthView();
    return;
  }
  renderTimelineView();
}

function renderTimelineView() {
  const visibleDates = currentViewMode === "daily"
    ? [getDayDate(currentDayOffset)]
    : getWeekDates(currentWeekOffset);
  const wrap = document.getElementById("calendarGridWrap");
  if (!wrap) return;

  wrap.innerHTML = buildTimelineMarkup(visibleDates);
  updateTimelineLabel(visibleDates);
  populateTimelineColumns(visibleDates);
}

function buildTimelineMarkup(visibleDates) {
  const timeLabels = Array.from({ length: HOUR_END - HOUR_START }, (_, hour) => {
    const displayHour = hour % 12 === 0 ? 12 : hour % 12;
    const suffix = hour < 12 ? "Am" : "Pm";
    return `<div class="time-slot-label">${displayHour} ${suffix}</div>`;
  }).join("");

  const dayColumns = visibleDates.map((date, index) => {
    const dayName = currentViewMode === "daily"
      ? date.toLocaleDateString(undefined, { weekday: "long" })
      : DAYS[index];

    return `
      <div class="day-column">
        <div class="day-col-header">
          <span class="col-day-name">${dayName}</span>
          <span class="col-day-num" id="col-num-${index}"></span>
        </div>
        <div class="day-col-body" data-day="${index}"></div>
      </div>
    `;
  }).join("");

  return `
    <div class="calendar-grid calendar-grid--${currentViewMode}" id="calendarGrid">
      <div class="time-gutter">
        <div class="gutter-tz">GMT+5</div>
        ${timeLabels}
      </div>
      ${dayColumns}
    </div>
  `;
}

function populateTimelineColumns(visibleDates) {
  const today = new Date();

  visibleDates.forEach((date, index) => {
    const numEl = document.getElementById(`col-num-${index}`);
    if (!numEl) return;

    numEl.textContent = date.getDate();
    numEl.className = "col-day-num" + (isSameDay(date, today) ? " today-num" : "");

    const body = document.querySelector(`.day-col-body[data-day="${index}"]`);
    if (!body) return;
    body.innerHTML = "";

    for (let rowIndex = 0; rowIndex < HOUR_END - HOUR_START; rowIndex++) {
      const row = document.createElement("div");
      row.className = "time-row-bg";
      body.appendChild(row);
    }

    const dayTasks = allTasks.filter((task) => {
      if (!task.start_time) return false;
      return isSameDay(new Date(task.start_time), date);
    });

    dayTasks.forEach((task) => placeTaskCard(body, task));
  });
}

function updateTimelineLabel(visibleDates) {
  const label = document.getElementById("gridDateLabel");
  if (!label) return;

  if (currentViewMode === "daily") {
    const date = visibleDates[0];
    label.textContent = date.toLocaleDateString(undefined, {
      weekday: "long",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
    return;
  }

  const first = visibleDates[0];
  const last = visibleDates[visibleDates.length - 1];
  label.textContent =
    `${MONTHS[first.getMonth()].slice(0, 3)} ${first.getDate()} - ` +
    `${MONTHS[last.getMonth()].slice(0, 3)} ${last.getDate()}, ${last.getFullYear()}`;
}

function renderMonthView() {
  const wrap = document.getElementById("calendarGridWrap");
  const label = document.getElementById("gridDateLabel");
  if (!wrap || !label) return;

  const today = new Date();
  const target = new Date(today.getFullYear(), today.getMonth() + currentMonthOffset, 1);
  const year = target.getFullYear();
  const month = target.getMonth();

  label.textContent = `${MONTHS[month]} ${year}`;

  const firstDow = (new Date(year, month, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrev = new Date(year, month, 0).getDate();
  const cells = [];

  for (let prev = firstDow - 1; prev >= 0; prev--) {
    cells.push({
      date: new Date(year, month - 1, daysInPrev - prev),
      otherMonth: true,
    });
  }

  for (let day = 1; day <= daysInMonth; day++) {
    cells.push({
      date: new Date(year, month, day),
      otherMonth: false,
    });
  }

  while (cells.length < 42) {
    const nextDay = cells.length - (firstDow + daysInMonth) + 1;
    cells.push({
      date: new Date(year, month + 1, nextDay),
      otherMonth: true,
    });
  }

  wrap.innerHTML = `
    <div class="month-grid">
      ${DAYS.map((day) => `<div class="month-grid-head">${day}</div>`).join("")}
      ${cells.map((cell) => buildMonthCell(cell.date, cell.otherMonth)).join("")}
    </div>
  `;
}

function buildMonthCell(date, otherMonth) {
  const isoDate = toDateKey(date);
  const tasks = allTasks.filter((task) => task.start_time && toDateKey(new Date(task.start_time)) === isoDate);
  const events = calendarEvents.filter((event) => event.event_date === isoDate);
  const itemCount = tasks.length + events.length;
  const previewItems = [
    ...tasks.slice(0, 2).map((task) => `
      <div class="month-item month-item--task${task.status === "Completed" ? " month-item--done" : ""}">
        ${escapeHtml(task.title)}
      </div>
    `),
    ...events.slice(0, Math.max(0, 2 - Math.min(tasks.length, 2))).map((event) => `
      <div class="month-item month-item--event">${escapeHtml(event.title)}</div>
    `),
  ].join("");
  const extraCount = Math.max(itemCount - 2, 0);

  return `
    <button
      type="button"
      class="month-cell${otherMonth ? " month-cell--muted" : ""}${isSameDay(date, new Date()) ? " month-cell--today" : ""}"
      onclick="selectMonthDate('${isoDate}')"
    >
      <div class="month-cell-top">
        <span class="month-cell-date">${date.getDate()}</span>
        ${itemCount ? `<span class="month-cell-count">${itemCount}</span>` : ""}
      </div>
      <div class="month-cell-items">
        ${previewItems}
        ${extraCount ? `<div class="month-item month-item--more">+${extraCount} more</div>` : ""}
      </div>
    </button>
  `;
}

function placeTaskCard(container, task) {
  if (!task.start_time) return;

  const start = new Date(task.start_time);
  const end = task.end_time ? new Date(task.end_time) : new Date(start.getTime() + 60 * 60 * 1000);
  const startMin = (start.getHours() - HOUR_START) * 60 + start.getMinutes();
  const endMin = (end.getHours() - HOUR_START) * 60 + end.getMinutes();
  if (endMin <= 0 || startMin >= (HOUR_END - HOUR_START) * 60) return;

  const clampedStart = Math.max(startMin, 0);
  const clampedEnd = Math.min(endMin, (HOUR_END - HOUR_START) * 60);
  const topPx = (clampedStart / 60) * SLOT_H;
  const heightPx = Math.max(((clampedEnd - clampedStart) / 60) * SLOT_H, 36);

  const card = document.createElement("div");
  card.className = `event-card event-card--enter ${cardColorClass(task)}`;
  if (taskIsUrgent(task)) card.classList.add("event-card-urgent");
  if (task.status === "Completed") card.classList.add("card-done");
  card.style.cssText = `top:${topPx}px; height:${heightPx}px;`;
  card.dataset.taskId = task.id;
  card.title = "Click to edit task";
  card.style.cursor = "pointer";
  card.addEventListener("click", () => {
    if (typeof window.openTaskEditor === "function") {
      window.openTaskEditor(task);
    }
  });

  const timeLabel = `${formatTime(start)} - ${formatTime(end)}`;
  const bubbleCount = Math.min(task.attendees || 1, 3);
  let bubblesHTML = "";
  if (bubbleCount > 1) {
    const initials = ["A", "B", "C", "D", "E"];
    bubblesHTML = `<div class="attendee-row">`;
    for (let index = 0; index < bubbleCount; index++) {
      bubblesHTML += `<div class="attendee-bubble">${initials[index]}</div>`;
    }
    if ((task.attendees || 1) > 3) {
      bubblesHTML += `<div class="attendee-bubble">+${task.attendees - 3}</div>`;
    }
    bubblesHTML += `</div>`;
  }

  card.innerHTML = `
    <div class="event-actions">
      <button class="event-action-btn" onclick="event.stopPropagation();markDone(${task.id})" title="Mark done">OK</button>
      <button class="event-action-btn" onclick="event.stopPropagation();deleteTask(${task.id})" title="Delete">X</button>
    </div>
    <div class="event-badges">
      <span class="event-type-badge">${taskBadgeIcon(task)}</span>
      ${taskIsUrgent(task) ? '<span class="event-type-badge event-type-badge--urgent">Hot</span>' : ""}
    </div>
    <div class="event-title">${escapeHtml(task.title)}</div>
    <div class="event-time">${timeLabel}</div>
    ${bubblesHTML}
  `;

  container.appendChild(card);
  requestAnimationFrame(() => card.classList.remove("event-card--enter"));
}

function renderMiniCal() {
  const today = new Date();
  const target = new Date(today.getFullYear(), today.getMonth() + miniCalOffset, 1);
  const year = target.getFullYear();
  const month = target.getMonth();

  const labelEl = document.getElementById("calMonthLabel");
  if (labelEl) labelEl.textContent = `${MONTHS[month]} ${year}`;

  const container = document.getElementById("miniCalDays");
  if (!container) return;
  container.innerHTML = "";

  const firstDow = (new Date(year, month, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrev = new Date(year, month, 0).getDate();

  const taskDates = new Set(
    allTasks
      .filter((task) => task.start_time)
      .map((task) => {
        const date = new Date(task.start_time);
        return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
      })
  );
  const eventDates = new Set(calendarEvents.map((event) => event.event_date));

  for (let prev = firstDow - 1; prev >= 0; prev--) {
    appendCalDay(container, daysInPrev - prev, true, false, false);
  }

  for (let day = 1; day <= daysInMonth; day++) {
    const isToday = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();
    const key = `${year}-${month}-${day}`;
    const isoDate = formatIsoDate(year, month, day);
    appendCalDay(container, day, false, isToday, taskDates.has(key) || eventDates.has(isoDate), isoDate);
  }

  const total = firstDow + daysInMonth;
  const remainder = total % 7 === 0 ? 0 : 7 - (total % 7);
  for (let next = 1; next <= remainder; next++) {
    appendCalDay(container, next, true, false, false, null);
  }
}

function appendCalDay(container, num, otherMonth, isToday, hasTask, isoDate) {
  const cell = document.createElement("div");
  cell.className = "cal-day-cell" +
    (otherMonth ? " other-month" : "") +
    (isToday ? " today" : "") +
    (hasTask ? " has-task" : "") +
    (isoDate && isoDate === selectedMiniDate ? " selected" : "");
  cell.textContent = num;

  if (isoDate) {
    cell.dataset.date = isoDate;
    cell.addEventListener("click", () => {
      selectedMiniDate = isoDate;
      renderMiniCal();
      renderSelectedDateEvents();
    });
  }

  container.appendChild(cell);
}

function bindNavButtons() {
  const gridPrev = document.getElementById("gridPrev");
  const gridNext = document.getElementById("gridNext");
  if (gridPrev) gridPrev.addEventListener("click", () => shiftCurrentView(-1));
  if (gridNext) gridNext.addEventListener("click", () => shiftCurrentView(1));

  const calPrev = document.getElementById("calPrev");
  const calNext = document.getElementById("calNext");
  if (calPrev) calPrev.addEventListener("click", () => {
    miniCalOffset -= 1;
    renderMiniCal();
  });
  if (calNext) calNext.addEventListener("click", () => {
    miniCalOffset += 1;
    renderMiniCal();
  });
}

function shiftCurrentView(direction) {
  if (currentViewMode === "daily") {
    currentDayOffset += direction;
  } else if (currentViewMode === "monthly") {
    currentMonthOffset += direction;
    miniCalOffset = currentMonthOffset;
  } else {
    currentWeekOffset += direction;
  }

  renderCalendarView();
  renderMiniCal();
}

function goToToday() {
  currentWeekOffset = 0;
  currentDayOffset = 0;
  currentMonthOffset = 0;
  miniCalOffset = 0;
  selectedMiniDate = toDateKey(new Date());
  renderCalendarView();
  renderMiniCal();
  renderSelectedDateEvents();
}

function selectMonthDate(isoDate) {
  selectedMiniDate = isoDate;
  renderMiniCal();
  renderSelectedDateEvents();
}

async function markDone(taskId) {
  try {
    const res = await fetch(`/update_task/${taskId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "Completed" }),
    });
    if (res.ok) {
      const payload = await res.json();
      const task = allTasks.find((item) => item.id === taskId);
      if (task) task.status = "Completed";
      renderCalendarView();
      renderSelectedDateEvents();
      if (typeof refreshGamificationPanelFromPayload === "function") {
        refreshGamificationPanelFromPayload(payload);
      }
      if (task && typeof showTaskFinishPopup === "function") {
        showTaskFinishPopup(task.title);
      }
      showToast("Task marked as done");
    }
  } catch (error) {
    console.error("markDone failed:", error);
  }
}

async function deleteTask(taskId) {
  if (!confirm("Delete this task?")) return;
  try {
    const res = await fetch(`/delete_task/${taskId}`, { method: "DELETE" });
    if (res.ok) {
      allTasks = allTasks.filter((item) => item.id !== taskId);
      renderCalendarView();
      renderMiniCal();
      renderSelectedDateEvents();
      showToast("Task deleted");
    }
  } catch (error) {
    console.error("deleteTask failed:", error);
  }
}

function showToast(message) {
  const existing = document.getElementById("wa-toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.id = "wa-toast";
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

  requestAnimationFrame(() => {
    toast.style.opacity = "1";
    toast.style.transform = "translateY(0)";
  });

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(8px)";
    setTimeout(() => toast.remove(), 250);
  }, 2500);
}

function renderSelectedDateEvents() {
  const label = document.getElementById("selectedDateLabel");
  const list = document.getElementById("selectedDateEvents");
  if (!label || !list) return;

  if (!selectedMiniDate) {
    label.textContent = "Choose a date";
    list.innerHTML = "";
    return;
  }

  const date = new Date(`${selectedMiniDate}T00:00:00`);
  label.textContent = date.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  const dateTasks = allTasks.filter((task) => task.start_time && toDateKey(new Date(task.start_time)) === selectedMiniDate);
  const dateEvents = calendarEvents.filter((event) => event.event_date === selectedMiniDate);

  if (!dateTasks.length && !dateEvents.length) {
    list.innerHTML = `<div class="selected-date-empty">No tasks or events yet. <button type="button" class="mini-link-btn" onclick="openEventModal('${selectedMiniDate}')">Add one</button></div>`;
    return;
  }

  list.innerHTML = "";

  dateEvents.forEach((event) => {
    const row = document.createElement("div");
    row.className = "selected-date-item selected-date-item-event";
    row.innerHTML = `
      <div class="selected-date-inline">
        <span class="mini-type-icon">Cal</span>
        <div class="selected-date-item-title">${escapeHtml(event.title)}</div>
      </div>
      <div class="selected-date-item-meta">${escapeHtml(event.event_type || "Event")}</div>
    `;
    list.appendChild(row);
  });

  dateTasks.forEach((task) => {
    const row = document.createElement("div");
    row.className = "selected-date-item";
    row.style.cursor = "pointer";
    row.innerHTML = `
      <div class="selected-date-inline">
        <span class="mini-type-icon">${taskMiniTag(task)}</span>
        <div class="selected-date-item-title">${escapeHtml(task.title)}</div>
      </div>
      <div class="selected-date-item-meta">${escapeHtml(task.priority || "Medium")} priority task</div>
    `;
    row.addEventListener("click", () => {
      if (typeof window.openTaskEditor === "function") {
        window.openTaskEditor(task);
      }
    });
    list.appendChild(row);
  });
}

window.handleTaskUpdated = function handleTaskUpdated(updatedTask, payload) {
  const index = allTasks.findIndex((task) => task.id === updatedTask.id);
  if (index !== -1) {
    allTasks[index] = {
      ...allTasks[index],
      ...updatedTask,
    };
  }

  renderCalendarView();
  renderMiniCal();
  renderSelectedDateEvents();

  if (payload && typeof refreshGamificationPanelFromPayload === "function") {
    refreshGamificationPanelFromPayload(payload);
  }

  showToast("Task updated");
};

function getWeekDates(offset) {
  const today = new Date();
  const dow = today.getDay();
  const monday = new Date(today);
  const diffToMon = dow === 0 ? -6 : 1 - dow;
  monday.setDate(today.getDate() + diffToMon + offset * 7);

  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(monday);
    date.setDate(monday.getDate() + index);
    return date;
  });
}

function getDayDate(offset) {
  const date = new Date();
  date.setDate(date.getDate() + offset);
  return date;
}

window.getCurrentVisibleWeekStart = function getCurrentVisibleWeekStart() {
  let anchorDate;

  if (currentViewMode === "daily") {
    anchorDate = getDayDate(currentDayOffset);
  } else if (currentViewMode === "monthly" && selectedMiniDate) {
    anchorDate = new Date(`${selectedMiniDate}T00:00:00`);
  } else {
    anchorDate = getWeekDates(currentWeekOffset)[0];
  }

  const monday = new Date(anchorDate);
  const day = monday.getDay();
  const diffToMon = day === 0 ? -6 : 1 - day;
  monday.setDate(monday.getDate() + diffToMon);
  monday.setHours(0, 0, 0, 0);
  return `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, "0")}-${String(monday.getDate()).padStart(2, "0")}T00:00:00`;
};

function isSameDay(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function formatTime(date) {
  const hour = date.getHours();
  const minute = date.getMinutes();
  const suffix = hour >= 12 ? "Pm" : "Am";
  const hour12 = hour % 12 || 12;
  return minute === 0
    ? `${hour12} ${suffix}`
    : `${hour12}:${String(minute).padStart(2, "0")} ${suffix}`;
}

function cardColorClass(task) {
  if (task.color === "lime") return "card-lime";
  if (task.color === "pink") return "card-pink";
  return "card-purple";
}

function taskIsUrgent(task) {
  if (task.status === "Completed") return false;
  if (task.priority === "High") return true;
  if (!task.deadline) return false;
  return new Date(task.deadline).getTime() <= Date.now() + (24 * 60 * 60 * 1000);
}

function taskBadgeIcon(task) {
  const category = (task.category || "").toLowerCase();
  if (category === "health") return "Fit";
  if (category === "study") return "XP";
  if (category === "personal") return "Life";
  return "Work";
}

function taskMiniTag(task) {
  const category = (task.category || "").toLowerCase();
  if (category === "health") return "HP";
  if (category === "study") return "Lv";
  if (category === "personal") return "Fun";
  return "Pro";
}

function formatIsoDate(year, month, day) {
  return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function toDateKey(date) {
  return formatIsoDate(date.getFullYear(), date.getMonth(), date.getDate());
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
