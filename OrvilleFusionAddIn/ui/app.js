const state = {
  apiKeyPresent: false,
  selectedImages: [],
  jobState: {},
  bridgeReady: false,
  bridgeAttempts: 0,
  mode: "iterate",
  recentExpanded: true,
  recentJobs: [],
  recentQuery: "",
  artifactsExpanded: true,
  showKeyForm: false,
  lastRenderedJobMessageKey: null,
};

const MAX_BRIDGE_ATTEMPTS = 80;
const BRIDGE_RETRY_MS = 250;

const els = {
  connection: document.getElementById("connection-state"),
  keyForm: document.getElementById("key-form"),
  keyInput: document.getElementById("api-key-input"),
  changeKey: document.getElementById("change-key-button"),
  saveKey: document.getElementById("save-key-button"),
  deleteKey: document.getElementById("delete-key-button"),
  status: document.getElementById("job-status"),
  newJob: document.getElementById("new-job-button"),
  refresh: document.getElementById("refresh-button"),
  recentToggle: document.getElementById("recent-toggle-button"),
  recentRefresh: document.getElementById("recent-refresh-button"),
  recentBody: document.getElementById("recent-body"),
  recentSearch: document.getElementById("recent-search-input"),
  recentSearchButton: document.getElementById("recent-search-button"),
  recentClear: document.getElementById("recent-clear-button"),
  recentList: document.getElementById("recent-list"),
  messages: document.getElementById("messages"),
  artifacts: document.getElementById("artifacts"),
  artifactsToggle: document.getElementById("artifacts-toggle-button"),
  artifactsBody: document.getElementById("artifacts-body"),
  imageList: document.getElementById("image-list"),
  prompt: document.getElementById("prompt-input"),
  iterateMode: document.getElementById("iterate-mode-button"),
  reviewMode: document.getElementById("review-mode-button"),
  attach: document.getElementById("attach-button"),
  clearImages: document.getElementById("clear-images-button"),
  submit: document.getElementById("submit-button"),
};

function fusionBridge() {
  if (window.adsk && typeof window.adsk.fusionSendData === "function") {
    return window.adsk;
  }
  if (typeof adsk !== "undefined" && typeof adsk.fusionSendData === "function") {
    return adsk;
  }
  return null;
}

function waitForBridge() {
  forcePaint();
  const bridge = fusionBridge();
  if (bridge) {
    state.bridgeReady = true;
    state.bridgeAttempts = 0;
    render();
    forcePaint();
    send("ready");
    return;
  }

  state.bridgeReady = false;
  state.bridgeAttempts += 1;
  els.connection.textContent = "Connecting to Fusion...";

  if (state.bridgeAttempts < MAX_BRIDGE_ATTEMPTS) {
    window.setTimeout(waitForBridge, BRIDGE_RETRY_MS);
    return;
  }

  els.connection.textContent = "Fusion bridge unavailable";
  renderError("Fusion did not expose its palette bridge. Close this palette, stop and run the add-in again.");
}

function send(action, payload = {}) {
  const bridge = fusionBridge();
  if (!bridge) {
    state.bridgeReady = false;
    els.connection.textContent = "Connecting to Fusion...";
    window.setTimeout(waitForBridge, BRIDGE_RETRY_MS);
    return Promise.resolve(null);
  }

  state.bridgeReady = true;
  const result = bridge.fusionSendData(action, JSON.stringify(payload));
  if (result && typeof result.then === "function") {
    return result;
  }
  return Promise.resolve(result);
}

function fusionJavaScriptHandler(action, data) {
  let payload = {};
  try {
    payload = data ? JSON.parse(data) : {};
  } catch (error) {
    renderError("Received invalid data from Fusion.");
    return "ok";
  }

  if (action === "state") {
    state.apiKeyPresent = Boolean(payload.api_key_present);
    state.selectedImages = payload.selected_images || [];
    state.jobState = payload.job_state || {};
    render();
    forcePaint();
  } else if (action === "status") {
    els.status.textContent = payload.message || "";
  } else if (action === "notification") {
    renderMessage("system", payload.message || "");
  } else if (action === "error") {
    renderError(payload.message || "Unexpected error.", payload.details);
  } else if (action === "job") {
    state.jobState = Object.assign({}, state.jobState, payload);
    renderJob(payload);
    render();
  } else if (action === "review") {
    renderReview(payload);
    render();
  } else if (action === "recent_jobs") {
    state.recentJobs = payload.jobs || [];
    renderRecentJobs();
    if (!state.recentJobs.length) {
      els.status.textContent = "No recent jobs found";
    }
  } else if (action === "recent_job_loaded") {
    const job = payload.job || {};
    state.jobState = Object.assign({}, state.jobState, job);
    renderMessages(payload.messages || []);
    render();
  } else if (action === "conversation_cleared") {
    resetConversation();
  } else if (action === "response") {
    return "ok";
  }
  return "ok";
}

window.fusionJavaScriptHandler = { handle: fusionJavaScriptHandler };

function render() {
  if (state.bridgeReady) {
    els.connection.textContent = state.apiKeyPresent ? "API key saved" : "API key required";
  }

  const status = state.jobState.status || "No active job";
  els.status.textContent = state.jobState.current_job_id
    ? `${state.jobState.current_job_id}: ${status}`
    : status;

  els.imageList.innerHTML = "";
  state.selectedImages.forEach((name) => {
    const item = document.createElement("span");
    item.className = "image-chip";
    item.textContent = name;
    els.imageList.appendChild(item);
  });

  renderArtifacts();
  renderMode();
  renderRecentJobs();
  renderKeySettings();
  forcePaint();
}

function renderKeySettings() {
  const showForm = !state.apiKeyPresent || state.showKeyForm;
  const settingsSection = els.keyForm.closest(".settings");
  settingsSection.hidden = !showForm;
  els.keyForm.hidden = !showForm;
  els.changeKey.textContent = state.apiKeyPresent ? "Change key" : "API key";
}

function forcePaint() {
  const shell = document.querySelector(".app-shell");
  if (!shell) {
    return;
  }

  shell.classList.add("paint-ready");
  shell.style.transform = "translateZ(0)";
  shell.style.opacity = "0.999";
  void shell.offsetHeight;

  window.requestAnimationFrame(() => {
    shell.style.opacity = "1";
    shell.style.transform = "none";
    document.body.style.backgroundColor = "#f8f5ef";
  });
}

function renderJob(job) {
  if (!job || !job.status) {
    return;
  }

  const jobId = job.id || state.jobState.current_job_id || "";
  const messageKey = job.explanation
    ? `explanation:${jobId}:${job.latest_revision_id || ""}:${job.explanation}`
    : `status:${jobId}:${job.status}`;
  if (messageKey === state.lastRenderedJobMessageKey) {
    return;
  }
  state.lastRenderedJobMessageKey = messageKey;

  if (job.explanation) {
    renderMessage("assistant", job.explanation);
  } else {
    renderMessage("system", `Job ${job.status}.`);
  }
}

function renderReview(reviewResponse) {
  const review = reviewResponse.review || {};
  const message = review.message || review.content;
  if (message) {
    renderMessage("assistant", message);
  } else {
    renderMessage("system", "Review completed.");
  }

  const proposal = review.iteration_proposal || {};
  if (proposal.summary) {
    renderMessage("system", `Review suggests an iteration: ${proposal.summary}`);
  }
}

function renderMode() {
  const hasJob = Boolean(state.jobState.current_job_id);
  els.iterateMode.classList.toggle("active", state.mode === "iterate");
  els.reviewMode.classList.toggle("active", state.mode === "review");
  els.submit.textContent = hasJob ? (state.mode === "review" ? "Review" : "Iterate") : "Create";
}

function renderArtifacts() {
  const artifacts = state.jobState.artifacts || [];
  const downloads = state.jobState.downloads || {};
  els.artifacts.hidden = !artifacts.length;
  els.artifactsBody.hidden = !state.artifactsExpanded;
  els.artifactsToggle.textContent = state.artifactsExpanded
    ? `STEP Artifacts (${artifacts.length}) ▾`
    : `STEP Artifacts (${artifacts.length}) ▸`;
  els.artifactsBody.innerHTML = "";

  if (!artifacts.length) {
    return;
  }

  artifacts.forEach((artifact) => {
    const row = document.createElement("div");
    row.className = "artifact-row";

    const label = document.createElement("div");
    label.className = "artifact-label";
    label.textContent = artifact.filename || artifact.label || artifact.id;

    const actions = document.createElement("div");
    actions.className = "artifact-actions";

    const importButton = document.createElement("button");
    importButton.type = "button";
    importButton.className = "compact";
    importButton.textContent = downloads[artifact.id] ? "Import" : "Download / Import";
    importButton.addEventListener("click", () => send("download_import_artifact", { artifact_id: artifact.id }));

    actions.appendChild(importButton);
    row.appendChild(label);
    row.appendChild(actions);
    els.artifactsBody.appendChild(row);
  });
}

function renderRecentJobs() {
  els.recentBody.hidden = !state.recentExpanded;
  els.recentToggle.textContent = state.recentExpanded ? "Recent Jobs ▾" : "Recent Jobs ▸";
  els.recentList.innerHTML = "";

  if (!state.recentJobs.length) {
    const empty = document.createElement("div");
    empty.className = "recent-empty";
    empty.textContent = state.apiKeyPresent ? "No recent jobs loaded." : "Save an API key to load recent jobs.";
    els.recentList.appendChild(empty);
    return;
  }

  state.recentJobs.forEach((job) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "recent-job";
    item.dataset.jobId = job.id;

    const title = document.createElement("span");
    title.className = "recent-title";
    title.textContent = job.title || job.prompt_preview || job.id || "Untitled job";

    const meta = document.createElement("span");
    meta.className = "recent-meta";
    meta.textContent = [job.status, job.source, formatDate(job.updated_at || job.created_at)]
      .filter(Boolean)
      .join(" · ");

    item.appendChild(title);
    item.appendChild(meta);
    item.addEventListener("click", () => {
      renderMessage("system", `Loading ${title.textContent}...`);
      send("load_recent_job", { job_id: job.id });
    });
    els.recentList.appendChild(item);
  });
}

function renderMessages(messages) {
  els.messages.innerHTML = "";
  state.lastRenderedJobMessageKey = null;
  messages.forEach((message) => {
    if (message.review && message.review.message) {
      renderMessage("assistant", message.review.message);
    } else {
      renderMessage(message.role === "user" ? "user" : "assistant", message.content || "");
    }
  });
}

function formatDate(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function renderMessage(role, text) {
  if (!text) {
    return;
  }
  const message = document.createElement("div");
  message.className = `message ${role}`;
  message.textContent = text;
  els.messages.appendChild(message);
  els.messages.scrollTop = els.messages.scrollHeight;
}

function renderError(message, details) {
  let text = message;
  if (details && details.code) {
    text += ` (${details.code})`;
  }
  if (details && details.request_id) {
    text += ` Request: ${details.request_id}`;
  }
  renderMessage("error", text);
}

function resetConversation() {
  state.jobState = {};
  state.selectedImages = [];
  state.mode = "iterate";
  state.lastRenderedJobMessageKey = null;
  els.messages.innerHTML = "";
  els.prompt.value = "";
  render();
}

function submitPrompt() {
  const prompt = els.prompt.value.trim();
  if (!prompt) {
    return;
  }
  renderMessage("user", prompt);
  send("submit_prompt", { prompt, mode: state.mode }).then(() => {
    els.prompt.value = "";
  });
}

els.saveKey.addEventListener("click", () => {
  const apiKey = els.keyInput.value;
  send("save_api_key", { api_key: apiKey }).then(() => {
    els.keyInput.value = "";
    state.showKeyForm = false;
    renderKeySettings();
  });
});

els.changeKey.addEventListener("click", () => {
  state.showKeyForm = true;
  renderKeySettings();
  els.keyInput.focus();
});
els.deleteKey.addEventListener("click", () => {
  state.showKeyForm = true;
  send("delete_api_key");
});
els.attach.addEventListener("click", () => send("select_images"));
els.clearImages.addEventListener("click", () => send("clear_images"));
els.newJob.addEventListener("click", () => {
  resetConversation();
  send("new_job");
});
els.refresh.addEventListener("click", () => send("refresh_job"));
els.recentToggle.addEventListener("click", () => {
  state.recentExpanded = !state.recentExpanded;
  renderRecentJobs();
});
els.recentRefresh.addEventListener("click", () => {
  state.recentQuery = els.recentSearch.value.trim();
  send("refresh_recent_jobs", { query: state.recentQuery });
});
els.recentSearchButton.addEventListener("click", () => {
  state.recentQuery = els.recentSearch.value.trim();
  send("refresh_recent_jobs", { query: state.recentQuery });
});
els.recentClear.addEventListener("click", () => {
  els.recentSearch.value = "";
  state.recentQuery = "";
  send("refresh_recent_jobs", { query: "" });
});
els.recentSearch.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    state.recentQuery = els.recentSearch.value.trim();
    send("refresh_recent_jobs", { query: state.recentQuery });
  }
});
els.artifactsToggle.addEventListener("click", () => {
  state.artifactsExpanded = !state.artifactsExpanded;
  renderArtifacts();
});
els.iterateMode.addEventListener("click", () => {
  state.mode = "iterate";
  renderMode();
});
els.reviewMode.addEventListener("click", () => {
  state.mode = "review";
  renderMode();
});

els.submit.addEventListener("click", submitPrompt);
els.prompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    submitPrompt();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  render();
  forcePaint();
  window.setTimeout(forcePaint, 50);
  window.setTimeout(forcePaint, 250);
  window.setTimeout(forcePaint, 750);
  waitForBridge();
});
