"use strict";

const API_BASE = "https://datalens-api-lh9p.onrender.com";

// ── State ──────────────────────────────────────────────────────────────────
let selectedFile = null;
let lastReport = null;

// ── DOM refs ───────────────────────────────────────────────────────────────
const sectionUpload   = document.getElementById("section-upload");
const sectionLoading  = document.getElementById("section-loading");
const sectionError    = document.getElementById("section-error");
const sectionReport   = document.getElementById("section-report");
const paywallOverlay  = document.getElementById("paywall-overlay");

const dropZone        = document.getElementById("drop-zone");
const fileInput       = document.getElementById("file-input");
const selectedFileEl  = document.getElementById("selected-file");
const fileNameEl      = document.getElementById("selected-file-name");
const btnClear        = document.getElementById("btn-clear");
const btnAnalyze      = document.getElementById("btn-analyze");

const errorTitle      = document.getElementById("error-title");
const errorMessage    = document.getElementById("error-message");
const btnRetry        = document.getElementById("btn-retry");

const btnSubscribe    = document.getElementById("btn-subscribe");
const btnPaywallClose = document.getElementById("btn-paywall-close");
const paywallEmail    = document.getElementById("paywall-email");

const btnNew          = document.getElementById("btn-new");
const btnExport       = document.getElementById("btn-export");

// ── Theme toggle ───────────────────────────────────────────────────────────
(function () {
  const btn = document.querySelector("[data-theme-toggle]");
  const root = document.documentElement;
  let theme = matchMedia("(prefers-color-scheme:dark)").matches ? "dark" : "light";
  root.setAttribute("data-theme", theme);
  function updateIcon() {
    if (!btn) return;
    btn.innerHTML = theme === "dark"
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
      : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  }
  updateIcon();
  if (btn) btn.addEventListener("click", function () {
    theme = theme === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", theme);
    btn.setAttribute("aria-label", "Passer en mode " + (theme === "dark" ? "clair" : "sombre"));
    updateIcon();
  });
})();

// ── Stripe token recovery from URL ────────────────────────────────────────
(function () {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token");
  if (token) {
    sessionStorage.setItem("datalens_token", token);
    window.history.replaceState({}, "", window.location.pathname);
  }
})();

// ── File selection ─────────────────────────────────────────────────────────
function setFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".csv")) {
    showError("Format invalide", "Seuls les fichiers .csv sont acceptés.");
    return;
  }
  selectedFile = file;
  fileNameEl.textContent = file.name;
  selectedFileEl.hidden = false;
  btnAnalyze.disabled = false;
}

fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) setFile(fileInput.files[0]);
});

dropZone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    fileInput.click();
  }
});

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) setFile(file);
});

btnClear.addEventListener("click", clearFile);
function clearFile() {
  selectedFile = null;
  fileInput.value = "";
  selectedFileEl.hidden = true;
  btnAnalyze.disabled = true;
}

// ── Analyze ────────────────────────────────────────────────────────────────
btnAnalyze.addEventListener("click", () => {
  if (selectedFile) auditCSV(selectedFile);
});

async function auditCSV(file, retryToken = null) {
  showSection("loading");
  const loadingHint = document.getElementById("loading-hint");
  loadingHint.textContent = "Détection des types, métriques, score qualité";

  // After 8s, hint the user the server may be warming up (Render free cold start)
  const wakeTimer = setTimeout(() => {
    loadingHint.textContent = "Le serveur se réveille… encore quelques secondes ☕";
  }, 8000);

  const token = retryToken || sessionStorage.getItem("datalens_token");
  const formData = new FormData();
  formData.append("file", file);
  if (token) formData.append("token", token);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 75000); // 75s for cold start

  let res;
  try {
    res = await fetch(`${API_BASE}/api/audit`, { method: "POST", body: formData, signal: controller.signal });
  } catch (err) {
    clearTimeout(wakeTimer);
    clearTimeout(timeoutId);
    if (err.name === "AbortError") {
      showError("Délai dépassé", "Le serveur met trop de temps à répondre. Réessayez dans 30 secondes.");
    } else {
      showError("Impossible de joindre le serveur", "Le serveur est peut-être en cours de démarrage. Patientez 30 secondes et réessayez.");
    }
    return;
  }
  clearTimeout(wakeTimer);
  clearTimeout(timeoutId);

  if (res.status === 402) {
    showSection("upload");
    showPaywall();
    return;
  }

  if (res.status === 413) {
    showError("Fichier trop volumineux", "La taille maximale acceptée est 50 MB.");
    return;
  }

  if (res.status === 400) {
    const data = await res.json().catch(() => ({}));
    showError("Fichier invalide", data.detail || "Vérifiez que votre fichier est un CSV valide.");
    return;
  }

  if (!res.ok) {
    showError("Erreur serveur", "Une erreur inattendue est survenue. Réessayez dans un instant.");
    return;
  }

  let report;
  try {
    report = await res.json();
  } catch {
    showError("Erreur de réponse", "La réponse du serveur est invalide.");
    return;
  }

  lastReport = report;
  renderReport(report);
  showSection("report");
}

// ── Retry ──────────────────────────────────────────────────────────────────
btnRetry.addEventListener("click", () => {
  showSection("upload");
});

// ── Paywall ────────────────────────────────────────────────────────────────
function showPaywall() {
  paywallOverlay.hidden = false;
  paywallEmail.focus();
}

function hidePaywall() {
  paywallOverlay.hidden = true;
  paywallEmail.classList.remove("invalid");
}

btnPaywallClose.addEventListener("click", hidePaywall);
paywallOverlay.addEventListener("click", (e) => {
  if (e.target === paywallOverlay) hidePaywall();
});

btnSubscribe.addEventListener("click", async () => {
  const email = paywallEmail.value.trim();
  if (!email || !email.includes("@")) {
    paywallEmail.classList.add("invalid");
    paywallEmail.focus();
    return;
  }
  paywallEmail.classList.remove("invalid");
  btnSubscribe.disabled = true;
  btnSubscribe.textContent = "Redirection…";

  let data;
  try {
    const res = await fetch(`${API_BASE}/api/create-checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    data = await res.json();
  } catch {
    btnSubscribe.disabled = false;
    btnSubscribe.textContent = "S'abonner — €7/mois";
    alert("Impossible de créer la session de paiement. Réessayez.");
    return;
  }

  if (data.checkout_url) {
    window.location.href = data.checkout_url;
  } else {
    btnSubscribe.disabled = false;
    btnSubscribe.textContent = "S'abonner — €7/mois";
  }
});

// ── New file / Export ──────────────────────────────────────────────────────
btnNew.addEventListener("click", () => {
  lastReport = null;
  clearFile();
  showSection("upload");
});

btnExport.addEventListener("click", () => {
  if (!lastReport) return;
  exportReportHTML(lastReport);
});

// ── Section visibility ─────────────────────────────────────────────────────
function showSection(name) {
  sectionUpload.hidden  = name !== "upload";
  sectionLoading.hidden = name !== "loading";
  sectionError.hidden   = name !== "error";
  sectionReport.hidden  = name !== "report";
}

function showError(title, message) {
  errorTitle.textContent   = title;
  errorMessage.textContent = message;
  showSection("error");
}

// ── Counter animation ──────────────────────────────────────────────────────
function animateCounter(el, target, duration) {
  let start = 0;
  const step = target / (duration / 16);
  const timer = setInterval(() => {
    start += step;
    if (start >= target) { start = target; clearInterval(timer); }
    el.textContent = Math.round(start);
  }, 16);
}

// ── Score color ────────────────────────────────────────────────────────────
function scoreColor(score) {
  if (score >= 80) return "var(--color-success)";
  if (score >= 60) return "var(--color-warning)";
  return "var(--color-error)";
}

// ── Report rendering ───────────────────────────────────────────────────────
function renderReport(report) {
  const { score, score_label, file_info, overview, columns } = report;

  // Header
  document.getElementById("report-filename").textContent = file_info.filename;
  document.getElementById("report-meta").textContent =
    `${file_info.rows.toLocaleString("fr-FR")} lignes · ${file_info.columns} colonnes · ${file_info.size_kb} KB · ${file_info.encoding}`;

  // Score
  const scoreEl = document.getElementById("score-display");
  scoreEl.textContent = "0";
  animateCounter(scoreEl, score, 800);
  document.getElementById("score-label").textContent = score_label;

  const bar = document.getElementById("score-bar");
  setTimeout(() => {
    bar.style.width = score + "%";
    bar.style.background = scoreColor(score);
  }, 50);

  bar.setAttribute("aria-valuenow", score);
  bar.setAttribute("aria-label", `Score qualité ${score} sur 100`);

  // Pills
  const pillsEl = document.getElementById("score-pills");
  const critical = overview.issues.filter(i => i.level === "critical").length;
  const warnings = overview.issues.filter(i => i.level === "warning").length;
  const healthy  = columns.filter(c => c.issues.length === 0).length;

  pillsEl.innerHTML = "";
  if (critical)  pillsEl.innerHTML += `<span class="pill pill-red">⚠ ${critical} critique${critical > 1 ? "s" : ""}</span>`;
  if (warnings)  pillsEl.innerHTML += `<span class="pill pill-orange">⚠ ${warnings} avertissement${warnings > 1 ? "s" : ""}</span>`;
  if (healthy)   pillsEl.innerHTML += `<span class="pill pill-green">✓ ${healthy} colonne${healthy > 1 ? "s" : ""} saine${healthy > 1 ? "s" : ""}</span>`;

  // Overview grid
  const grid = document.getElementById("overview-grid");
  const nullClass  = overview.total_null_pct >= 10 ? "val-err" : overview.total_null_pct > 0 ? "val-warn" : "val-ok";
  const dupClass   = overview.duplicate_rows > 0 ? "val-warn" : "val-ok";
  const constClass = overview.constant_columns.length > 0 ? "val-warn" : "val-ok";

  grid.innerHTML = `
    <div class="overview-card"><div class="overview-val ${nullClass}">${overview.total_null_pct}%</div><div class="overview-name">Valeurs nulles (global)</div></div>
    <div class="overview-card"><div class="overview-val ${dupClass}">${overview.duplicate_rows.toLocaleString("fr-FR")}</div><div class="overview-name">Lignes dupliquées (${overview.duplicate_rows_pct}%)</div></div>
    <div class="overview-card"><div class="overview-val ${constClass}">${overview.constant_columns.length}</div><div class="overview-name">Colonnes constantes</div></div>
    <div class="overview-card"><div class="overview-val val-neutral">${columns.length}</div><div class="overview-name">Colonnes analysées</div></div>
  `;

  // Issues
  const issuesSec  = document.getElementById("issues-section");
  const issuesList = document.getElementById("issues-list");
  if (overview.issues.length > 0) {
    issuesSec.hidden = false;
    issuesList.innerHTML = overview.issues.map(issue => {
      const cls  = issue.level === "critical" ? "issue-critical" : issue.level === "warning" ? "issue-warning" : "issue-info";
      const icon = issue.level === "critical" ? "🔴" : issue.level === "warning" ? "🟠" : "🔵";
      return `<li class="issue-item ${cls}"><span class="issue-icon" aria-hidden="true">${icon}</span><span>${escapeHtml(issue.message)}</span></li>`;
    }).join("");
  } else {
    issuesSec.hidden = true;
  }

  // Columns
  const colsList = document.getElementById("columns-list");
  colsList.innerHTML = "";
  columns.forEach((col, idx) => colsList.appendChild(buildColCard(col, idx)));
}

// ── Column card ────────────────────────────────────────────────────────────
function buildColCard(col, idx) {
  const card = document.createElement("div");
  card.className = "col-card";
  card.id = `col-card-${idx}`;

  const nullBad  = col.null_pct >= 10;
  const dupBad   = col.duplicate_pct >= 20;
  const hasIssue = col.issues.length > 0;

  const header = document.createElement("div");
  header.className = "col-card-header";
  header.setAttribute("role", "button");
  header.setAttribute("tabindex", "0");
  header.setAttribute("aria-expanded", "false");
  header.innerHTML = `
    <div class="col-card-left">
      <span class="col-name">${escapeHtml(col.name)}</span>
      <span class="col-type-badge">${escapeHtml(col.type)}</span>
      ${hasIssue ? '<span style="color:var(--color-warning);font-size:.9rem" aria-label="Problèmes détectés">⚠</span>' : ""}
    </div>
    <div class="col-card-right">
      <span class="col-stat${nullBad ? " bad" : ""}">${col.null_pct}% nulls</span>
      <span class="col-stat${dupBad ? " bad" : ""}">${col.unique_count.toLocaleString("fr-FR")} uniques</span>
      <span class="col-expand-btn" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      </span>
    </div>
  `;

  const body = document.createElement("div");
  body.className = "col-card-body";
  body.setAttribute("id", `col-body-${idx}`);
  body.innerHTML = buildColBody(col, idx);

  header.addEventListener("click", () => toggleColCard(card, header));
  header.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleColCard(card, header); }
  });

  card.appendChild(header);
  card.appendChild(body);
  return card;
}

function toggleColCard(card, header) {
  const isOpen = card.classList.contains("open");
  card.classList.toggle("open", !isOpen);
  header.setAttribute("aria-expanded", String(!isOpen));

  // Render Plotly chart lazily on first open
  if (!isOpen && card.dataset.chartRendered !== "true") {
    card.dataset.chartRendered = "true";
    const idx = card.id.replace("col-card-", "");
    const report = lastReport;
    if (report) {
      const col = report.columns[parseInt(idx, 10)];
      if (col && col.distribution) renderHistogram(col, idx);
    }
  }
}

function buildColBody(col, idx) {
  let html = '<div class="col-metrics-grid">';

  html += `<div class="col-metric"><div class="col-metric-val">${col.null_pct}%</div><div class="col-metric-name">Valeurs nulles</div></div>`;
  html += `<div class="col-metric"><div class="col-metric-val">${col.unique_count.toLocaleString("fr-FR")}</div><div class="col-metric-name">Valeurs uniques</div></div>`;
  html += `<div class="col-metric"><div class="col-metric-val">${col.duplicate_pct}%</div><div class="col-metric-name">Valeurs dupliquées</div></div>`;

  if (col.stats) {
    html += `<div class="col-metric"><div class="col-metric-val">${col.stats.min}</div><div class="col-metric-name">Min</div></div>`;
    html += `<div class="col-metric"><div class="col-metric-val">${col.stats.max}</div><div class="col-metric-name">Max</div></div>`;
    html += `<div class="col-metric"><div class="col-metric-val">${col.stats.mean}</div><div class="col-metric-name">Moyenne</div></div>`;
    html += `<div class="col-metric"><div class="col-metric-val">${col.stats.median}</div><div class="col-metric-name">Médiane</div></div>`;
    html += `<div class="col-metric"><div class="col-metric-val">${col.stats.outliers_count}</div><div class="col-metric-name">Outliers (${col.stats.outliers_pct}%)</div></div>`;
  }

  if (col.date_stats) {
    html += `<div class="col-metric"><div class="col-metric-val" style="font-size:var(--text-sm)">${col.date_stats.min}</div><div class="col-metric-name">Date min</div></div>`;
    html += `<div class="col-metric"><div class="col-metric-val" style="font-size:var(--text-sm)">${col.date_stats.max}</div><div class="col-metric-name">Date max</div></div>`;
  }

  html += "</div>";

  // Histogram placeholder (rendered lazily)
  if (col.distribution) {
    html += `<div class="chart-wrap" id="chart-${idx}"></div>`;
  }

  // Top values
  if (col.top_values && col.top_values.length > 0) {
    const maxCount = col.top_values[0].count;
    html += '<div class="top-values"><div class="top-values-title">Top valeurs</div><div class="top-values-list">';
    col.top_values.forEach(tv => {
      const pct = Math.round((tv.count / maxCount) * 100);
      html += `
        <div class="top-val-row">
          <span class="top-val-name" title="${escapeHtml(tv.value)}">${escapeHtml(tv.value)}</span>
          <div class="top-val-bar-wrap"><div class="top-val-bar" style="width:${pct}%"></div></div>
          <span class="top-val-count">${tv.count.toLocaleString("fr-FR")}</span>
        </div>`;
    });
    html += "</div></div>";
  }

  // Issues
  if (col.issues.length > 0) {
    html += '<div class="col-issues">';
    col.issues.forEach(iss => {
      html += `<div class="col-issue-item">⚠ ${escapeHtml(iss)}</div>`;
    });
    html += "</div>";
  }

  return html;
}

function renderHistogram(col, idx) {
  const el = document.getElementById(`chart-${idx}`);
  if (!el || typeof Plotly === "undefined") return;

  const isDark = document.documentElement.getAttribute("data-theme") === "dark";
  const textColor = isDark ? "#797876" : "#7a7974";
  const gridColor = isDark ? "#262523" : "#dcd9d5";

  Plotly.newPlot(el, [{
    type: "bar",
    x: col.distribution.bins,
    y: col.distribution.counts,
    marker: { color: "#01696f" },
    hovertemplate: "Bin: %{x}<br>Count: %{y}<extra></extra>",
  }], {
    margin: { t: 10, r: 10, b: 40, l: 40 },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { family: "Inter, sans-serif", size: 11, color: textColor },
    xaxis: { gridcolor: gridColor, zeroline: false },
    yaxis: { gridcolor: gridColor, zeroline: false },
    height: 180,
  }, { displayModeBar: false, responsive: true });
}

// ── HTML Export ────────────────────────────────────────────────────────────
function exportReportHTML(report) {
  const { score, score_label, file_info, overview, columns } = report;
  const date = new Date().toLocaleDateString("fr-FR", { year: "numeric", month: "long", day: "numeric" });
  const color = score >= 80 ? "#437a22" : score >= 60 ? "#964219" : "#a12c7b";

  let colsHtml = columns.map(col => {
    const statsRows = col.stats ? `
      <tr><td>Min</td><td>${col.stats.min}</td></tr>
      <tr><td>Max</td><td>${col.stats.max}</td></tr>
      <tr><td>Moyenne</td><td>${col.stats.mean}</td></tr>
      <tr><td>Médiane</td><td>${col.stats.median}</td></tr>
      <tr><td>Outliers</td><td>${col.stats.outliers_count} (${col.stats.outliers_pct}%)</td></tr>
    ` : "";
    const issHtml = col.issues.length ? col.issues.map(i => `<li>⚠ ${escapeHtml(i)}</li>`).join("") : "<li>✓ Aucun problème détecté</li>";
    return `
      <div style="background:#f9f8f5;border:1px solid #dcd9d5;border-radius:12px;padding:1.25rem;margin-bottom:.75rem">
        <div style="display:flex;align-items:center;gap:.75rem;margin-bottom:1rem">
          <strong>${escapeHtml(col.name)}</strong>
          <span style="background:#cedcd8;color:#01696f;padding:.15rem .6rem;border-radius:999px;font-size:.75rem">${col.type}</span>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:.875rem;margin-bottom:.75rem">
          <tr><td style="color:#7a7974;padding:.2rem 0;width:50%">% Nulls</td><td>${col.null_pct}%</td></tr>
          <tr><td style="color:#7a7974;padding:.2rem 0">Uniques</td><td>${col.unique_count.toLocaleString("fr-FR")}</td></tr>
          <tr><td style="color:#7a7974;padding:.2rem 0">% Doublons</td><td>${col.duplicate_pct}%</td></tr>
          ${statsRows}
        </table>
        <ul style="font-size:.8rem;color:#7a7974;padding-left:1rem">${issHtml}</ul>
      </div>`;
  }).join("");

  const issHtml = overview.issues.map(i => {
    const c = i.level === "critical" ? "#a12c7b" : i.level === "warning" ? "#964219" : "#01696f";
    return `<li style="color:${c};margin-bottom:.4rem">${escapeHtml(i.message)}</li>`;
  }).join("") || "<li>✓ Aucun problème global détecté</li>";

  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>DataLens — Rapport ${escapeHtml(file_info.filename)}</title>
<style>body{font-family:Inter,sans-serif;background:#f7f6f2;color:#28251d;max-width:860px;margin:0 auto;padding:2rem 1.5rem}h1,h2{font-family:Georgia,serif}a{color:#01696f}</style>
</head><body>
<h1 style="font-size:2rem;letter-spacing:-0.02em;margin-bottom:.25rem">DataLens — Rapport qualité</h1>
<p style="color:#7a7974;font-size:.875rem;margin-bottom:2rem">Généré le ${date} · ${escapeHtml(file_info.filename)} · ${file_info.rows.toLocaleString("fr-FR")} lignes · ${file_info.columns} colonnes</p>
<div style="background:white;border-radius:16px;padding:2rem;margin-bottom:1.5rem;border:1px solid #dcd9d5">
  <p style="font-size:.75rem;text-transform:uppercase;letter-spacing:.06em;color:#7a7974;margin-bottom:.25rem">Score qualité</p>
  <p style="font-family:Georgia,serif;font-size:5rem;line-height:1;color:${color};margin:0">${score}</p>
  <p style="color:#7a7974;margin-top:.25rem">${score_label} · / 100</p>
  <div style="height:10px;background:#f3f0ec;border-radius:999px;overflow:hidden;margin-top:1rem">
    <div style="height:100%;width:${score}%;background:${color};border-radius:999px"></div>
  </div>
</div>
<h2 style="font-size:1.25rem;margin-bottom:1rem">Problèmes détectés</h2>
<ul style="margin-bottom:2rem">${issHtml}</ul>
<h2 style="font-size:1.25rem;margin-bottom:1rem">Analyse par colonne</h2>
${colsHtml}
<p style="font-size:.75rem;color:#bab9b4;margin-top:2rem;text-align:center">Rapport généré par <a href="https://datalens.badreddineek.com">DataLens</a></p>
</body></html>`;

  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `datalens-rapport-${file_info.filename.replace(/\.csv$/i, "")}-${Date.now()}.html`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

// ── Helpers ────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
