"use strict";

const $ = (s) => document.querySelector(s);
const HEADERS = { "X-Video-Downloader": "1", "Content-Type": "application/json" };

async function api(path, body) {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: HEADERS,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok && !data.error) data.error = `Something went wrong (${res.status}).`;
  return data;
}

function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) node.append(kid);
  return node;
}

const fmt = {
  duration(s) {
    if (!s) return "";
    s = Math.round(s);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return (h ? `${h}:${String(m).padStart(2, "0")}` : m) + ":" + String(sec).padStart(2, "0");
  },
  bytes(b) {
    if (!b) return "";
    const u = ["B", "KB", "MB", "GB"]; let i = 0;
    while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
    return `${b.toFixed(b < 10 && i ? 1 : 0)} ${u[i]}`;
  },
  eta(s) { if (s == null) return ""; return s < 60 ? `${s}s left` : `${Math.round(s / 60)} min left`; },
  host(url) { try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; } },
  quality(q) { return { best: "Best", audio: "Audio only" }[q] || (q ? `≤${q}p` : ""); },
  when(iso) {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + ", " +
      d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  },
};

let settings = {};
let lastState = null;
const handledPending = new Set();

/* ------------------------------------------------------------ lookup + preview */

const preview = $("#preview");

async function lookUp(url, pendingId) {
  url = url.trim();
  if (!url) return;
  $("#urlInput").value = url;
  preview.hidden = false;
  preview.className = "preview loading";
  preview.replaceChildren(
    el("div", { class: "thumb" }),
    el("div", { class: "info" }, el("div", { class: "title" }, el("span", { class: "spinner" }), "Looking at the link…"),
      el("div", { class: "sub" }, fmt.host(url))),
  );
  const info = await api("/api/info", { url });
  if (info.error) {
    preview.className = "preview error";
    preview.replaceChildren(el("div", { class: "info" }, el("div", { class: "title" }, info.error),
      el("div", { class: "sub" }, url)));
    return;
  }
  renderPreview(info, pendingId);
}

function qualityOptions(heights) {
  const opts = [["best", "Best available"]];
  const caps = [2160, 1440, 1080, 720, 480];
  caps.forEach((h, i) => {
    const below = caps[i + 1] || 0;
    // only offer a cap if the video really has a size in that band
    if (!heights.length || heights.some((x) => x <= h && x > below)) opts.push([String(h), `${h}p`]);
  });
  opts.push(["audio", "Audio only (M4A)"]);
  return opts;
}

function renderPreview(info, pendingId) {
  preview.className = "preview";
  const thumb = el("div", { class: "thumb" });
  if (info.thumbnail) thumb.style.backgroundImage = `url("${info.thumbnail.replace(/"/g, "%22")}")`;
  if (info.duration) thumb.append(el("span", { class: "dur" }, fmt.duration(info.duration)));

  const isList = info.kind === "playlist";
  const select = el("select", { "aria-label": "Quality" });
  for (const [v, label] of qualityOptions(isList ? [] : info.heights || [])) select.append(el("option", { value: v }, label));
  select.value = [...select.options].some((o) => o.value === settings.quality) ? settings.quality : "best";

  const sub = isList
    ? [info.site, `${info.count} videos`].filter(Boolean).join(" · ")
    : [info.site, info.uploader, info.is_live ? "Live now" : null].filter(Boolean).join(" · ");

  const start = (playlist) => async () => {
    const job = await api("/api/download", {
      url: info.url, title: isList ? info.title : info.title, quality: select.value, playlist, pending_id: pendingId,
    });
    if (job.error) return alert(job.error);
    preview.hidden = true;
    $("#urlInput").value = "";
    poll();
  };

  const buttons = isList
    ? [el("button", { class: "primary", onclick: start(true) }, `Download all ${info.count}`)]
    : [el("button", { class: "primary", onclick: start(false) }, "Download")];

  preview.replaceChildren(thumb, el("div", { class: "info" },
    el("div", { class: "title" }, info.title),
    el("div", { class: "sub" }, sub),
    info.is_live ? el("div", { class: "sub" }, "This is a live stream; it records until the stream ends or you cancel.") : null,
    el("div", { class: "go" }, select, ...buttons,
      el("button", { class: "ghost", onclick: () => { preview.hidden = true; } }, "Close")),
  ));
}

$("#grabForm").addEventListener("submit", (e) => { e.preventDefault(); lookUp($("#urlInput").value); });

/* ------------------------------------------------------------ drag & drop links */

let dragDepth = 0;
const hasLink = (e) => [...(e.dataTransfer?.types || [])].some((t) => t === "text/uri-list" || t === "text/plain");
document.addEventListener("dragenter", (e) => { if (hasLink(e)) { dragDepth++; document.body.classList.add("dragging"); } });
document.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; document.body.classList.remove("dragging"); } });
document.addEventListener("dragover", (e) => { if (hasLink(e)) e.preventDefault(); });
document.addEventListener("drop", (e) => {
  e.preventDefault();
  dragDepth = 0;
  document.body.classList.remove("dragging");
  const text = (e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain") || "")
    .split("\n").map((s) => s.trim()).find((s) => /^https?:\/\//.test(s));
  if (text) lookUp(text);
});

/* ------------------------------------------------------------ clipboard prompts */

let pendingKey = "";

function renderPending(items, force = false) {
  const box = $("#pending");
  const visible = items.filter((p) => !handledPending.has(p.id));
  const key = visible.map((p) => p.id).join(",");
  if (key === pendingKey && !force) return;   // re-rendering would replay the slide-in animation
  pendingKey = key;
  box.replaceChildren(...visible.map((p) => el("div", { class: "prompt" },
    el("div", { class: "p-text" },
      el("div", { class: "p-label" }, `Copied link${p.site ? " · " + p.site : ""}`),
      el("div", { class: "p-url", title: p.url }, p.url)),
    el("div", { class: "p-actions" },
      el("button", { class: "small", onclick: () => { handledPending.add(p.id); renderPending(items); lookUp(p.url, p.id); } }, "Preview"),
      el("button", { class: "small primary", onclick: async () => {
        handledPending.add(p.id); renderPending(items);
        await api("/api/download", { url: p.url, pending_id: p.id }); poll();
      } }, "Download"),
      el("button", { class: "small ghost", title: "Ignore", onclick: async () => {
        handledPending.add(p.id); renderPending(items);
        await api(`/api/pending/${p.id}/dismiss`, {});
      } }, "✕")),
  )));
}

/* ------------------------------------------------------------ download list */

const jobNodes = new Map();

function renderJobs(jobs) {
  const list = $("#jobs");
  $("#jobsEmpty").hidden = jobs.length > 0;
  const ids = new Set(jobs.map((j) => j.id));
  for (const [id, node] of jobNodes) if (!ids.has(id)) { node.remove(); jobNodes.delete(id); }

  jobs.forEach((job, i) => {
    let node = jobNodes.get(job.id);
    if (!node) {
      node = $("#jobTpl").content.firstElementChild.cloneNode(true);
      jobNodes.set(job.id, node);
    }
    if (list.children[i] !== node) list.insertBefore(node, list.children[i] || null);
    node.className = `job ${job.status}`;
    node.querySelector(".job-title").textContent = job.title;
    node.querySelector(".job-title").title = job.url;
    node.querySelector(".bar span").style.width = `${job.percent || 0}%`;

    const meta = node.querySelector(".job-meta");
    const site = job.site || fmt.host(job.url);
    let parts;
    switch (job.status) {
      case "queued": parts = ["Waiting…", site]; break;
      case "downloading":
        parts = [`${Math.floor(job.percent || 0)}%`, job.speed ? fmt.bytes(job.speed) + "/s" : "", fmt.eta(job.eta), job.detail];
        break;
      case "processing": parts = [job.detail || "Finishing up…"]; break;
      case "done": parts = [el("span", { class: "ok" }, "Saved"), job.file_count > 1 ? `${job.file_count} files` : "", site, fmt.quality(job.quality)]; break;
      case "cancelled": parts = ["Cancelled", site]; break;
      case "error": parts = [el("span", { class: "err" }, job.error || "Failed")]; break;
    }
    const filtered = parts.filter(Boolean);
    meta.replaceChildren(...filtered.flatMap((p, k) => (k ? [" · ", p] : [p])));

    const actions = node.querySelector(".job-actions");
    const key = `${job.status}|${job.filepath}`;
    if (actions.dataset.key !== key) {
      actions.dataset.key = key;
      const btns = [];
      if (["queued", "downloading", "processing"].includes(job.status))
        btns.push(el("button", { class: "small", onclick: () => api(`/api/jobs/${job.id}/cancel`, {}).then(poll) }, "Cancel"));
      if (job.status === "done" && job.filepath)
        btns.push(el("button", { class: "small", onclick: () => reveal(job.filepath) }, "Show in Finder"));
      if (["error", "cancelled"].includes(job.status))
        btns.push(el("button", { class: "small", onclick: () => api(`/api/jobs/${job.id}/retry`, {}).then(poll) }, "Retry"));
      actions.replaceChildren(...btns);
    }
  });
}

async function reveal(path) {
  const r = await api("/api/reveal", { path });
  if (r.error) alert(r.error);
}

/* ------------------------------------------------------------ notices */

function renderNotices(state) {
  const box = $("#notices");
  const notes = [];
  if (!state.ffmpeg) {
    notes.push(el("div", { class: "notice" },
      el("strong", {}, "ffmpeg isn't installed. "),
      "Without it most sites only offer lower-quality files and audio can't be combined with high-res video. In Terminal, run ",
      el("code", {}, "brew install ffmpeg"), " then restart the app."));
  }
  if (!state.deno) {
    notes.push(el("div", { class: "notice" },
      el("strong", {}, "deno isn't installed. "),
      "YouTube downloads need it (other sites are fine). In Terminal, run ",
      el("code", {}, "brew install deno"), " then restart the app."));
  }
  if (!state.clipboard_available) {
    notes.push(el("div", { class: "notice" }, "Clipboard watching only works on a Mac. Paste links into the box below instead."));
  }
  box.replaceChildren(...notes);
  box.hidden = notes.length === 0;
  const pill = $("#watchPill");
  const on = state.clipboard_available && settings.watch_clipboard;
  pill.textContent = on ? "Watching clipboard" : "Clipboard off";
  pill.classList.toggle("off", !on);
}

/* ------------------------------------------------------------ history */

async function loadHistory() {
  const items = await api("/api/history");
  if (!Array.isArray(items)) return;
  $("#historyCount").textContent = items.length ? `${items.length}` : "";
  $("#history").replaceChildren(...(items.length ? items.map((h) => el("li", {},
    el("div", { class: "h-main" },
      el("div", { class: "h-title" + (h.exists ? "" : " gone"), title: h.path || "" }, h.title || h.url),
      el("div", { class: "h-sub" }, [h.site || fmt.host(h.url), h.files > 1 ? `${h.files} files` : null, fmt.when(h.date), h.exists ? null : "file moved or deleted"].filter(Boolean).join(" · "))),
    h.exists ? el("button", { class: "small", onclick: () => reveal(h.path) }, "Show") : null,
    el("button", { class: "small ghost", title: "Download again", onclick: () => lookUp(h.url) }, "Again"),
  )) : [el("li", { class: "muted" }, settings.keep_history ? "No downloads yet." : "History is turned off in Settings.")]));
}
$("#historyBox").addEventListener("toggle", (e) => { if (e.target.open) loadHistory(); });
$("#clearHistory").addEventListener("click", async () => {
  if (!confirm("Clear your download history? Your video files stay where they are.")) return;
  await api("/api/history/clear", {}); loadHistory();
});

/* ------------------------------------------------------------ settings */

const dlg = $("#settings");
const form = $("#settingsForm");

function fillSettings() {
  for (const [k, v] of Object.entries(settings)) {
    const input = form.elements[k];
    if (!input) continue;
    if (input.type === "checkbox") input.checked = !!v; else input.value = String(v);
  }
}

$("#openSettings").addEventListener("click", () => { fillSettings(); $("#updateNote").hidden = true; dlg.showModal(); });
$("#chooseFolder").addEventListener("click", async () => {
  const s = await api("/api/choose-folder", {});
  if (s.save_dir) { settings.save_dir = s.save_dir; form.elements.save_dir.value = s.save_dir; }
});
dlg.addEventListener("close", async () => {
  if (dlg.returnValue !== "save") return;
  const out = {};
  for (const input of form.elements) {
    if (!input.name) continue;
    out[input.name] = input.type === "checkbox" ? input.checked : input.value;
  }
  settings = await api("/api/settings", out);
  poll();
  if ($("#historyBox").open) loadHistory();
});

$("#updateYtdlp").addEventListener("click", async () => {
  $("#updateYtdlp").disabled = true;
  await api("/api/update-ytdlp", {});
  const note = $("#updateNote");
  note.hidden = false;
  note.textContent = "Updating…";
  const timer = setInterval(async () => {
    const s = await api("/api/state");
    if (s.update && !s.update.running) {
      clearInterval(timer);
      $("#updateYtdlp").disabled = false;
      note.textContent = s.update.ok
        ? (/already satisfied/i.test(s.update.output) && !/Successfully installed/i.test(s.update.output)
            ? "Already up to date."
            : "Updated. Quit and reopen the app to start using the new version.")
        : "Update failed: " + s.update.output.split("\n").filter(Boolean).slice(-2).join(" ");
    }
  }, 1000);
});

/* ------------------------------------------------------------ header buttons */

$("#openFolder").addEventListener("click", () => api("/api/reveal", {}));
$("#clearJobs").addEventListener("click", () => api("/api/jobs/clear", {}).then(poll));
$("#quitApp").addEventListener("click", async () => {
  if (!confirm("Quit Video Downloader? Downloads in progress will stop.")) return;
  await api("/api/quit", {});
  document.body.replaceChildren(el("main", {}, el("div", { class: "panel" },
    el("h1", {}, "Video Downloader has stopped."),
    el("p", { class: "muted" }, "Double-click start.command to open it again. You can close this tab."))));
  stopped = true;
});

/* ------------------------------------------------------------ polling */

let stopped = false;
let failures = 0;
let lastDoneCount = 0;

async function poll() {
  if (stopped) return;
  try {
    const state = await api("/api/state");
    if (state.error) throw new Error(state.error);
    failures = 0;
    lastState = state;
    renderNotices(state);
    renderPending(state.pending || []);
    renderJobs(state.jobs || []);
    $("#ytdlpVersion").textContent = state.ytdlp_version;
    const done = (state.jobs || []).filter((j) => j.status === "done").length;
    if (done !== lastDoneCount) { lastDoneCount = done; if ($("#historyBox").open) loadHistory(); }
  } catch {
    if (++failures === 3) {
      $("#notices").hidden = false;
      $("#notices").replaceChildren(el("div", { class: "notice" },
        "Can't reach the app. It may have been closed. Double-click start.command to start it again."));
    }
  }
}

function loop() {
  const busy = lastState && lastState.jobs.some((j) => ["queued", "downloading", "processing"].includes(j.status));
  poll().finally(() => setTimeout(loop, busy || document.hasFocus() ? 700 : 1500));
}

(async () => {
  settings = await api("/api/settings");
  loop();
})();
