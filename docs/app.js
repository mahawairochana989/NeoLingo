(function () {
  var LESSONS = [
    "Урок 1", "Урок 2", "Урок 3", "Урок 4",
    "Урок 5", "Урок 6", "Урок 7", "Урок 8",
  ];
  var STORAGE_KEY = "neolingo_results_v1";
  var API_URL = (window.NEOLINGO_API_URL || "").trim().replace(/\/$/, "");
  var API_KEY = (window.NEOLINGO_API_KEY || "").trim();
  var records = [];
  var chartLessons = null;
  var chartUsers = null;

  function byId(id) { return document.getElementById(id); }
  function buildHeaders() {
    var h = { "Content-Type": "application/json" };
    if (API_KEY) h["x-api-key"] = API_KEY;
    return h;
  }

  function loadLocal() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      records = raw ? JSON.parse(raw) : [];
    } catch (_) {
      records = [];
    }
  }
  function saveLocal() { localStorage.setItem(STORAGE_KEY, JSON.stringify(records)); }

  async function loadFromApi() {
    if (!API_URL) return false;
    try {
      var resp = await fetch(API_URL + "/api/results?limit=2000");
      if (!resp.ok) return false;
      records = await resp.json();
      return true;
    } catch (_) {
      return false;
    }
  }

  function lessonName(index) { return LESSONS[Number(index) - 1] || ("Урок " + index); }

  function fillLessonSelects() {
    var lessonSelect = byId("f-lesson");
    var filterSelect = byId("filter-lesson");
    LESSONS.forEach(function (name, idx) {
      var value = String(idx + 1);
      lessonSelect.insertAdjacentHTML("beforeend", '<option value="' + value + '">' + name + "</option>");
      filterSelect.insertAdjacentHTML("beforeend", '<option value="' + value + '">' + name + "</option>");
    });
  }

  function toLocalDateInputValue() {
    var now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    return now.toISOString().slice(0, 16);
  }

  function addRecord(item) {
    if (API_URL) {
      fetch(API_URL + "/api/results", {
        method: "POST",
        headers: buildHeaders(),
        body: JSON.stringify(item),
      })
        .then(function () { refresh(); })
        .catch(function () {
          records.push(item);
          saveLocal();
          render();
        });
      return;
    }
    records.push(item);
    saveLocal();
    render();
  }

  function deleteRecord(id) {
    if (API_URL) {
      alert("Удаление записей в API-режиме отключено для безопасности.");
      return;
    }
    records = records.filter(function (x) { return x.id !== id; });
    saveLocal();
    render();
  }

  function aggregateUserStats() {
    var map = {};
    records.forEach(function (r) {
      if (!map[r.user]) {
        map[r.user] = { user: r.user, points: 0, stars: 0, total: 0, correct: 0 };
      }
      map[r.user].points += Number(r.points) || 0;
      map[r.user].stars += Number(r.stars) || 0;
      map[r.user].total += 1;
      if (r.correct === "correct") map[r.user].correct += 1;
    });
    return Object.values(map).sort(function (a, b) { return b.points - a.points; });
  }

  function lessonProgress() {
    return LESSONS.map(function (_, i) {
      var lesson = String(i + 1);
      var lessonRows = records.filter(function (r) { return r.lesson === lesson; });
      var sum = lessonRows.reduce(function (acc, r) { return acc + (Number(r.points) || 0); }, 0);
      return { count: lessonRows.length, avgPoints: lessonRows.length ? sum / lessonRows.length : 0 };
    });
  }

  function drawCharts() {
    var lp = lessonProgress();
    var users = aggregateUserStats().slice(0, 8);
    var labelsLessons = LESSONS;
    var lessonCounts = lp.map(function (x) { return x.count; });
    var lessonAvgPoints = lp.map(function (x) { return Number(x.avgPoints.toFixed(2)); });

    if (chartLessons) chartLessons.destroy();
    chartLessons = new Chart(byId("chart-lessons"), {
      type: "bar",
      data: {
        labels: labelsLessons,
        datasets: [
          { label: "Кол-во записей", data: lessonCounts, borderWidth: 1 },
          { label: "Средний балл", data: lessonAvgPoints, type: "line", yAxisID: "y1" },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { labels: { color: "#dfe7ff" } } },
        scales: {
          x: { ticks: { color: "#a9b4dd" } },
          y: { ticks: { color: "#a9b4dd" }, beginAtZero: true },
          y1: { position: "right", ticks: { color: "#ffb5ec" }, beginAtZero: true, grid: { drawOnChartArea: false } },
        },
      },
    });

    if (chartUsers) chartUsers.destroy();
    chartUsers = new Chart(byId("chart-users"), {
      type: "bar",
      data: {
        labels: users.map(function (x) { return x.user; }),
        datasets: [{ label: "Сумма баллов", data: users.map(function (x) { return x.points; }) }],
      },
      options: {
        responsive: true,
        plugins: { legend: { labels: { color: "#dfe7ff" } } },
        scales: {
          x: { ticks: { color: "#a9b4dd" } },
          y: { ticks: { color: "#a9b4dd" }, beginAtZero: true },
        },
      },
    });
  }

  function applyFilters(items) {
    var q = byId("search-user").value.trim().toLowerCase();
    var lesson = byId("filter-lesson").value;
    var correct = byId("filter-correct").value;
    return items.filter(function (r) {
      if (q && r.user.toLowerCase().indexOf(q) === -1) return false;
      if (lesson && r.lesson !== lesson) return false;
      if (correct && r.correct !== correct) return false;
      return true;
    });
  }

  function renderTable() {
    var body = byId("results-body");
    var filtered = applyFilters(records).sort(function (a, b) { return new Date(b.time) - new Date(a.time); });
    body.innerHTML = "";
    filtered.forEach(function (r) {
      var correctLabel = r.correct === "correct" ? "Верно" : (r.correct === "partial" ? "Частично" : "Неверно");
      var tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + r.user + "</td>" +
        "<td>" + lessonName(r.lesson) + "</td>" +
        "<td>" + r.type + "</td>" +
        "<td>" + r.points + "</td>" +
        "<td>" + r.stars + "</td>" +
        '<td><div class="status ' + r.correct + '">' + correctLabel + "</div><small>" + (r.answer || "-") + "</small></td>' +
        "<td>" + (r.duration || 0) + " c</td>" +
        "<td>" + new Date(r.time).toLocaleString("ru-RU") + "</td>" +
        '<td><button class="btn danger" data-del="' + r.id + '">Удалить</button></td>';
      body.appendChild(tr);
    });
  }

  function renderStats() {
    var users = aggregateUserStats();
    var totalPoints = records.reduce(function (acc, r) { return acc + (Number(r.points) || 0); }, 0);
    var totalCorrect = records.filter(function (r) { return r.correct === "correct"; }).length;
    byId("stat-users").textContent = String(users.length);
    byId("stat-records").textContent = String(records.length);
    byId("stat-score").textContent = records.length ? (totalPoints / records.length).toFixed(1) : "0";
    byId("stat-accuracy").textContent = records.length ? ((totalCorrect / records.length) * 100).toFixed(1) + "%" : "0%";

    var completedLessons = lessonProgress().filter(function (x) { return x.count > 0; }).length;
    byId("lesson-status").textContent = "Пройдено уроков: " + completedLessons + "/8. Записей: " + records.length + ".";
  }

  function render() {
    renderStats();
    renderTable();
    drawCharts();
  }

  function seedDemoData() {
    var now = Date.now();
    var demo = [
      ["Polina", "1", "translation", 8, 1, "correct", "こんにちは", "привет", 34],
      ["Polina", "2", "vocab_quiz", 6, 1, "partial", "がくせい", "学生", 22],
      ["Anna", "1", "translation", 10, 2, "correct", "私はロシア人です", "", 41],
      ["Anna", "3", "logic_quiz", 4, 0, "incorrect", "12", "14", 56],
      ["Mika", "4", "vocab_quiz", 9, 2, "correct", "図書館", "", 28],
      ["Mika", "5", "logic_quiz", 7, 1, "partial", "可能です", "はい", 33],
      ["Akira", "7", "translation", 10, 3, "correct", "明日は雨です", "", 19],
      ["Akira", "8", "logic_quiz", 10, 3, "correct", "24", "24", 20],
    ];
    demo.forEach(function (x, i) {
      addRecord({
        id: crypto.randomUUID(),
        user: x[0],
        lesson: x[1],
        type: x[2],
        points: x[3],
        stars: x[4],
        correct: x[5],
        answer: x[6],
        expected: x[7],
        duration: x[8],
        time: new Date(now - i * 3600000).toISOString(),
      });
    });
  }

  function exportJson() {
    var blob = new Blob([JSON.stringify(records, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "neolingo-results.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  function importJson(file) {
    var reader = new FileReader();
    reader.onload = function () {
      try {
        var incoming = JSON.parse(reader.result);
        if (!Array.isArray(incoming)) return;
        records = incoming;
        saveLocal();
        render();
      } catch (_) {}
    };
    reader.readAsText(file);
  }

  function wireEvents() {
    byId("f-time").value = toLocalDateInputValue();

    byId("result-form").addEventListener("submit", function (e) {
      e.preventDefault();
      addRecord({
        id: crypto.randomUUID(),
        user: byId("f-user").value.trim(),
        lesson: byId("f-lesson").value,
        type: byId("f-type").value,
        points: Number(byId("f-points").value || 0),
        stars: Number(byId("f-stars").value || 0),
        correct: byId("f-correct").value,
        duration: Number(byId("f-duration").value || 0),
        time: new Date(byId("f-time").value).toISOString(),
        answer: byId("f-answer").value.trim(),
        expected: byId("f-expected").value.trim(),
      });
      e.target.reset();
      byId("f-time").value = toLocalDateInputValue();
    });

    byId("results-body").addEventListener("click", function (e) {
      var id = e.target.getAttribute("data-del");
      if (id) deleteRecord(id);
    });

    ["search-user", "filter-lesson", "filter-correct"].forEach(function (id) {
      byId(id).addEventListener("input", renderTable);
      byId(id).addEventListener("change", renderTable);
    });

    byId("seed-demo").addEventListener("click", function () {
      if (records.length && !confirm("Добавить демо к текущим данным?")) return;
      seedDemoData();
    });
    byId("export-json").addEventListener("click", exportJson);
    byId("import-json").addEventListener("change", function (e) {
      if (e.target.files[0]) importJson(e.target.files[0]);
      e.target.value = "";
    });
    byId("clear-all").addEventListener("click", function () {
      if (!confirm("Удалить все локальные записи?")) return;
      records = [];
      saveLocal();
      render();
    });
  }

  async function refresh() {
    var ok = await loadFromApi();
    if (!ok) loadLocal();
    render();
  }

  fillLessonSelects();
  wireEvents();
  refresh();
})();
