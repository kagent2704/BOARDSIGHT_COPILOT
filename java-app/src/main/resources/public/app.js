const DEFAULT_USER = {
  username: "admin",
  displayName: "BoardSight Admin",
  role: "admin"
};

const state = {
  meetings: [],
  currentMeetingId: null,
  currentMeeting: null,
  liveSession: null,
  sessionHasProcessed: false,
  authMode: "signin",
  currentUser: DEFAULT_USER,
  authToken: localStorage.getItem("boardsight-token") || "",
  theme: localStorage.getItem("boardsight-theme") || "light"
};

document.body.dataset.theme = state.theme;

const loginView = document.getElementById("loginView");
const appView = document.getElementById("appView");
const loginForm = document.getElementById("loginForm");
const themeToggle = document.getElementById("themeToggle");
const refreshBtn = document.getElementById("refreshBtn");
const signOutBtn = document.getElementById("signOutBtn");
const uploadInput = document.getElementById("uploadInput");
const uploadStatus = document.getElementById("uploadStatus");
const searchInput = document.getElementById("searchInput");
const donutChart = document.getElementById("donutChart");
const authTitle = document.getElementById("authTitle");
const authSubtitle = document.getElementById("authSubtitle");
const authSubmit = document.getElementById("authSubmit");
const authPrompt = document.getElementById("authPrompt");
const authModeToggle = document.getElementById("authModeToggle");
const authStatus = document.getElementById("authStatus");
const nameField = document.getElementById("nameField");
const usernameField = document.getElementById("usernameField");
const emailField = document.getElementById("emailField");
const confirmPasswordField = document.getElementById("confirmPasswordField");
const displayNameInput = document.getElementById("displayName");
const usernameInput = document.getElementById("username");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const confirmPasswordInput = document.getElementById("confirmPassword");
const roleInput = document.getElementById("role");
const guestLogin = document.getElementById("guestLogin");
const userName = document.getElementById("userName");
const userRole = document.getElementById("userRole");
const userInitials = document.getElementById("userInitials");
const topAvatar = document.getElementById("topAvatar");
const heroGreeting = document.getElementById("heroGreeting");
const exportPdfBtn = document.getElementById("exportPdfBtn");
const exportDocxBtn = document.getElementById("exportDocxBtn");
const exportXlsxBtn = document.getElementById("exportXlsxBtn");
const exportTraceBtn = document.getElementById("exportTraceBtn");
const processingOverlay = document.getElementById("processingOverlay");
const analysisStartInput = document.getElementById("analysisStartInput");
const analysisEndInput = document.getElementById("analysisEndInput");
const analysisProfileInput = document.getElementById("analysisProfileInput");
const liveTitleInput = document.getElementById("liveTitleInput");
const liveSourceInput = document.getElementById("liveSourceInput");
const liveProfileInput = document.getElementById("liveProfileInput");
const startLiveBtn = document.getElementById("startLiveBtn");
const stopLiveBtn = document.getElementById("stopLiveBtn");
const liveStatusBadge = document.getElementById("liveStatusBadge");
const liveStatusText = document.getElementById("liveStatusText");
const liveSessionId = document.getElementById("liveSessionId");
const liveSegmentCount = document.getElementById("liveSegmentCount");
const liveDecisionCount = document.getElementById("liveDecisionCount");
const liveActionCount = document.getElementById("liveActionCount");
const liveProblemCount = document.getElementById("liveProblemCount");
const liveDuration = document.getElementById("liveDuration");
const liveSummaryText = document.getElementById("liveSummaryText");
const liveSuggestions = document.getElementById("liveSuggestions");
const liveProblems = document.getElementById("liveProblems");
const liveActions = document.getElementById("liveActions");
const liveDiscussionPoints = document.getElementById("liveDiscussionPoints");
const liveOutcomes = document.getElementById("liveOutcomes");
const liveVisualArtifacts = document.getElementById("liveVisualArtifacts");
const livePresentationInsights = document.getElementById("livePresentationInsights");
const liveTranscript = document.getElementById("liveTranscript");
const previewGitlabBtn = document.getElementById("previewGitlabBtn");
const syncGitlabBtn = document.getElementById("syncGitlabBtn");
const gitlabBaseUrlInput = document.getElementById("gitlabBaseUrlInput");
const gitlabProjectIdInput = document.getElementById("gitlabProjectIdInput");
const gitlabTokenInput = document.getElementById("gitlabTokenInput");
const gitlabStatusText = document.getElementById("gitlabStatusText");
const gitlabPlanPreview = document.getElementById("gitlabPlanPreview");

let liveCaptureStream = null;
let liveSourceStreams = [];
let liveRecorder = null;
let liveUploadChain = Promise.resolve();
let liveClock = null;
let liveStartedAtMs = 0;
let liveChunkStartSeconds = 0;
let liveFinalizeRequested = false;

themeToggle.addEventListener("click", () => {
  state.theme = state.theme === "light" ? "dark" : "light";
  document.body.dataset.theme = state.theme;
  localStorage.setItem("boardsight-theme", state.theme);
});

authModeToggle.addEventListener("click", () => {
  state.authMode = state.authMode === "signin" ? "signup" : "signin";
  authStatus.textContent = "";
  syncAuthMode();
});

guestLogin.addEventListener("click", async () => {
  usernameInput.value = "admin";
  passwordInput.value = "boardsight123";
  await submitLogin("admin", "boardsight123");
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  if (!username || !password) {
    authStatus.textContent = "Username or email and password are required.";
    authStatus.classList.remove("success-text");
    return;
  }

  if (state.authMode === "signup") {
    const result = await registerUser();
    authStatus.textContent = result.message;
    authStatus.classList.toggle("success-text", result.ok);
    if (result.ok) {
      state.authMode = "signin";
      passwordInput.value = "";
      syncAuthMode();
    }
    return;
  }

  await submitLogin(username, password);
});

refreshBtn.addEventListener("click", () => loadMeetings());
signOutBtn.addEventListener("click", () => {
  clearSession();
  authStatus.textContent = "Signed out.";
  authStatus.classList.remove("success-text");
  passwordInput.value = "";
  confirmPasswordInput.value = "";
  setView("dashboard");
});
uploadInput.addEventListener("change", handleUpload);
searchInput.addEventListener("input", renderMeetingList);
startLiveBtn?.addEventListener("click", startLiveSession);
stopLiveBtn?.addEventListener("click", () => stopLiveSession(false));
previewGitlabBtn?.addEventListener("click", () => runGitlabPlan(true));
syncGitlabBtn?.addEventListener("click", () => runGitlabPlan(false));

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

document.querySelectorAll(".link-btn[data-view-target]").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.viewTarget));
});

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
    button.classList.add("active");
  });
});

exportPdfBtn.addEventListener("click", () => openReport("structured_report.pdf"));
exportDocxBtn.addEventListener("click", () => openReport("structured_report.docx"));
exportXlsxBtn.addEventListener("click", () => openReport("structured_report.xlsx"));
exportTraceBtn.addEventListener("click", () => openReport("structured_report.pdf"));

syncAuthMode();
updateUserChip();
bootstrapSession();
renderLiveSession();

async function bootstrapSession() {
  if (!state.authToken) {
    loginView.classList.remove("hidden");
    appView.classList.add("hidden");
    return;
  }

  try {
    const response = await apiFetch("/api/auth/me");
    const payload = await response.json();
    state.currentUser = normalizeUser(payload);
    updateUserChip();
    loginView.classList.add("hidden");
    appView.classList.remove("hidden");
    await loadMeetings();
  } catch {
    clearSession();
  }
}

function syncAuthMode() {
  const signingIn = state.authMode === "signin";
  authTitle.textContent = signingIn ? "Sign in to BoardSight" : "Create your BoardSight account";
  authSubtitle.textContent = signingIn
    ? "Access your governance workspace"
    : "Create a user account and store your own meeting history";
  authSubmit.textContent = signingIn ? "Sign In" : "Sign Up";
  authPrompt.textContent = signingIn ? "New here?" : "Already have an account?";
  authModeToggle.textContent = signingIn ? "Create account" : "Back to sign in";
  nameField.classList.toggle("hidden", signingIn);
  emailField.classList.toggle("hidden", signingIn);
  confirmPasswordField.classList.toggle("hidden", signingIn);
  setLabelText(usernameField, signingIn ? "Username or Email" : "Username");
}

async function registerUser() {
  const displayName = displayNameInput.value.trim();
  const username = usernameInput.value.trim();
  const email = emailInput.value.trim().toLowerCase();
  const password = passwordInput.value;
  const confirmPassword = confirmPasswordInput.value;
  const role = normalizeRole(roleInput.value);

  if (!displayName || !username || !email || !password || !confirmPassword) {
    return { ok: false, message: "Name, username, email, password, and confirmation are required." };
  }
  if (password !== confirmPassword) {
    return { ok: false, message: "Password and confirm password must match." };
  }

  const query = new URLSearchParams({
    username,
    email,
    password,
    confirm_password: confirmPassword,
    display_name: displayName,
    role
  });
  const response = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username,
      email,
      password,
      confirm_password: confirmPassword,
      display_name: displayName,
      role
    })
  });

  const queryResponse = response.ok ? response : await fetch(`/api/auth/register?${query.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username,
      email,
      password,
      confirm_password: confirmPassword,
      display_name: displayName,
      role
    })
  });

  let payload = {};
  try {
    payload = await queryResponse.json();
  } catch {
    payload = {};
  }

  if (!queryResponse.ok) {
    return { ok: false, message: normalizeMessage(payload.detail || payload.error || "Registration failed.") };
  }

  return { ok: true, message: "Account created. Sign in to access your meeting history." };
}

async function submitLogin(username, password) {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identifier: username, password })
  });

  const queryResponse = response.ok ? response : await fetch(
    `/api/auth/login?identifier=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier: username, password })
    }
  );

  let payload = {};
  try {
    payload = await queryResponse.json();
  } catch {
    payload = {};
  }

  if (!queryResponse.ok) {
    authStatus.textContent = normalizeMessage(payload.detail || payload.error || "Invalid username or password.");
    authStatus.classList.remove("success-text");
    return;
  }

  state.authToken = payload.token || "";
  localStorage.setItem("boardsight-token", state.authToken);
  state.currentUser = normalizeUser(payload);
  updateUserChip();
  authStatus.textContent = "";
  loginView.classList.add("hidden");
  appView.classList.remove("hidden");
  await loadMeetings();
}

function clearSession() {
  state.authToken = "";
  state.currentMeeting = null;
  state.currentMeetingId = null;
  state.meetings = [];
  state.liveSession = null;
  state.sessionHasProcessed = false;
  state.currentUser = DEFAULT_USER;
  localStorage.removeItem("boardsight-token");
  updateUserChip();
  renderEmptyDashboard();
  renderMeetingList();
  renderMeetingDetail();
  renderCvFeaturePanel();
  renderTrace();
  renderWorkflow();
  teardownLiveCapture();
  renderLiveSession();
  loginView.classList.remove("hidden");
  appView.classList.add("hidden");
}

function normalizeUser(payload) {
  const displayName = payload.display_name || payload.displayName || payload.username || "BoardSight User";
  return {
    username: payload.username || "",
    email: payload.email || "",
    displayName,
    role: prettifyRole(payload.role || "analyst")
  };
}

function updateUserChip() {
  userName.textContent = state.currentUser.displayName;
  userRole.textContent = state.currentUser.role;
  const initials = initialsFor(state.currentUser.displayName);
  userInitials.textContent = initials;
  topAvatar.textContent = initials;
  const firstName = state.currentUser.displayName.split(/\s+/).filter(Boolean)[0] || "there";
  heroGreeting.textContent = `Good Morning, ${firstName}!`;
}

async function loadMeetings() {
  try {
    const response = await apiFetch("/api/meetings");
    const payload = await response.json();
    state.meetings = payload.items || [];
    state.sessionHasProcessed = state.meetings.length > 0;
    updateDashboard();
    renderMeetingList();
    if (state.currentMeetingId) {
      await loadMeetingDetail(state.currentMeetingId);
    } else {
      renderMeetingDetail();
      renderCvFeaturePanel();
      renderTrace();
      renderWorkflow();
    }
  } catch (error) {
    if (error?.status === 401) {
      clearSession();
      return;
    }
    throw error;
  }
}

async function loadMeetingDetail(meetingId) {
  const resolvedMeetingId = String(meetingId || "").trim();
  if (!/^\d+$/.test(resolvedMeetingId)) {
    return;
  }
  const response = await apiFetch(`/api/meeting?id=${encodeURIComponent(resolvedMeetingId)}`);
  state.currentMeeting = await response.json();
  state.currentMeetingId = resolvedMeetingId;
  state.sessionHasProcessed = true;
  updateDashboard();
  renderMeetingDetail();
  renderCvFeaturePanel();
  renderTrace();
  renderWorkflow();
}

function updateDashboard() {
  if (!state.sessionHasProcessed || !state.currentMeeting) {
    renderEmptyDashboard();
    return;
  }

  const totalMeetings = state.meetings.length;
  const totalDecisions = state.currentMeeting.decision_moments?.length || 0;
  const avgAttention = state.currentMeeting.attention_sentiment?.overall_attention?.toFixed?.(1) ?? "--";
  const overallSentiment = state.currentMeeting.attention_sentiment?.overall_sentiment || "--";
  const primarySpeaker = state.currentMeeting.speaker_dominance?.speakers?.[0];
  const dominance = primarySpeaker?.dominance_ratio?.toFixed?.(1) ?? primarySpeaker?.dominanceRatio?.toFixed?.(1) ?? "--";

  document.getElementById("kpiMeetings").textContent = totalMeetings;
  document.getElementById("kpiDecisions").textContent = totalDecisions;
  document.getElementById("kpiAttention").textContent = `${avgAttention}%`;
  document.getElementById("kpiDominance").textContent = `${dominance}%`;
  document.getElementById("donutValue").textContent = `${dominance}%`;
  donutChart.classList.remove("is-empty");

  const speakerSeries = (state.currentMeeting.speaker_dominance?.speakers || []).slice(0, 4);
  if (speakerSeries.length > 0) {
    const segments = [];
    let offset = 0;
    const palette = ["var(--primary)", "#7acdf1", "#7bdcc6", "#d9dffb"];
    speakerSeries.forEach((speaker, index) => {
      const ratio = Number(speaker.dominance_ratio ?? speaker.dominanceRatio ?? 0);
      const nextOffset = Math.min(100, offset + ratio);
      segments.push(`${palette[index % palette.length]} ${offset}% ${nextOffset}%`);
      offset = nextOffset;
    });
    if (offset < 100) {
      segments.push(`rgba(69,104,255,0.08) ${offset}% 100%`);
    }
    donutChart.style.background =
      `radial-gradient(circle at center, var(--surface-strong) 0 44%, transparent 45%), conic-gradient(${segments.join(", ")})`;
  }

  const legend = document.getElementById("speakerLegend");
  legend.classList.remove("empty-list");
  legend.innerHTML = "";
  const sentimentItem = document.createElement("li");
  sentimentItem.innerHTML = `<span>Meeting sentiment</span><strong>${capitalize(overallSentiment)}</strong>`;
  legend.appendChild(sentimentItem);
  (state.currentMeeting.speaker_dominance?.speakers || []).slice(0, 5).forEach((speaker) => {
    const item = document.createElement("li");
    const ratio = speaker.dominance_ratio ?? speaker.dominanceRatio ?? 0;
    item.innerHTML = `<span>${speaker.speaker}</span><strong>${ratio}%</strong>`;
    legend.appendChild(item);
  });

  const timelineChart = document.getElementById("timelineChart");
  timelineChart.classList.remove("empty-chart");
  renderDecisionTimelineChart(timelineChart, state.currentMeeting);

  const workflowStages = state.currentMeeting.workflow_model?.stages || [];
  const prioritizedDecisions = state.currentMeeting.workflow_model?.prioritized_decisions || [];
  document.getElementById("workflowSnapshot").innerHTML =
    prioritizedDecisions.length === 0 && workflowStages.length === 0
      ? `<div class="empty-state">Workflow stages will appear after decision modelling runs.</div>`
      : renderWorkflowSnapshot(prioritizedDecisions, workflowStages, state.currentMeeting.workflow_model?.execution_plan || []);
}

function renderEmptyDashboard() {
  document.getElementById("kpiMeetings").textContent = "--";
  document.getElementById("kpiDecisions").textContent = "--";
  document.getElementById("kpiAttention").textContent = "--";
  document.getElementById("kpiDominance").textContent = "--";
  document.getElementById("donutValue").textContent = "--";
  donutChart.classList.add("is-empty");
  document.getElementById("speakerLegend").className = "legend-list empty-list";
  document.getElementById("speakerLegend").innerHTML = `<li class="empty-state">No speaker balance data yet.</li>`;
  document.getElementById("timelineChart").className = "line-chart empty-chart";
  document.getElementById("timelineChart").innerHTML = `<div class="empty-state">No decision timeline yet.</div>`;
  document.getElementById("workflowSnapshot").innerHTML = `<div class="empty-state">Workflow stages will appear after decision modelling runs.</div>`;
}

function renderMeetingList() {
  const meetingList = document.getElementById("meetingList");
  meetingList.innerHTML = "";

  if (!state.sessionHasProcessed) {
    meetingList.innerHTML = `<div class="empty-state">Your analyzed meetings will appear here after the first run.</div>`;
    return;
  }

  const query = searchInput.value.trim().toLowerCase();
  const visibleMeetings = state.meetings.filter((item) =>
    !query
    || String(item.title || "").toLowerCase().includes(query)
    || String(item.conclusion || "").toLowerCase().includes(query)
  );

  if (visibleMeetings.length === 0) {
    meetingList.innerHTML = `<div class="empty-state">No processed meetings match your search.</div>`;
    return;
  }

  visibleMeetings.forEach((item) => {
    const node = document.createElement("button");
    node.className = "meeting-item";
    node.innerHTML = `
      <div class="meeting-date"><span>${formatDate(item.createdAt || item.created_at)}</span></div>
      <div class="meeting-meta">
        <strong>${item.title || `Meeting ${item.id}`}</strong>
        <div class="muted">${item.conclusion || "BoardSight analysis ready."}</div>
      </div>
      <div class="meeting-pill">${item.decisions || item.decision_count || 0} Decisions</div>
    `;
    node.addEventListener("click", async () => {
      setView("meetings");
      await loadMeetingDetail(item.id || item.meetingId);
    });
    meetingList.appendChild(node);
  });
}

function renderMeetingDetail() {
  const meetingCover = document.getElementById("meetingCover");
  const meetingMediaEmpty = document.getElementById("meetingMediaEmpty");
  const mediaCard = meetingCover.closest(".media-card");
  const progressRow = mediaCard.querySelector(".progress-row");
  const progressLabel = progressRow.querySelector("span");
  const progressValue = progressRow.querySelector("strong");
  const speakerSummary = document.getElementById("speakerSummary");
  const transcriptList = document.getElementById("transcriptList");

  if (!state.currentMeeting) {
    document.getElementById("meetingTitle").textContent = "Meeting Detail";
    document.getElementById("meetingConclusion").textContent = "Upload and process a meeting to populate this view.";
    meetingCover.removeAttribute("src");
    meetingCover.classList.add("hidden");
    meetingMediaEmpty.classList.remove("hidden");
    mediaCard.classList.add("is-empty");
    progressRow.classList.add("hidden");
    progressLabel.textContent = "Analysis Progress";
    progressValue.textContent = "Complete";
    speakerSummary.innerHTML = `<div class="empty-state">No speaker summary yet.</div>`;
    speakerSummary.classList.add("is-empty");
    transcriptList.innerHTML = `<div class="empty-state">No transcript available yet.</div>`;
    toggleMeetingActions(false);
    return;
  }

  document.getElementById("meetingTitle").textContent = prettifyMeetingId(state.currentMeeting.storage?.meeting_id || state.currentMeetingId);
  document.getElementById("meetingConclusion").textContent = buildMeetingSubtitle(state.currentMeeting);
  loadProtectedImage(
    `/api/reports/${encodeURIComponent(state.currentMeeting.storage?.meeting_id || state.currentMeetingId)}/summary_card.png`,
    meetingCover
  );
  meetingCover.classList.remove("hidden");
  meetingMediaEmpty.classList.add("hidden");
  mediaCard.classList.remove("is-empty");
  progressRow.classList.remove("hidden");
  progressLabel.textContent = "Attention Model";
  progressValue.textContent = `${formatMetric(state.currentMeeting.attention_sentiment?.overall_attention)}%`;
  speakerSummary.classList.remove("is-empty");
  toggleMeetingActions(true);

  speakerSummary.innerHTML = "";
  const participantStates = new Map(
    (state.currentMeeting.attention_sentiment?.participant_states || []).map((item) => [item.speaker, item])
  );
  (state.currentMeeting.speaker_dominance?.speakers || []).forEach((speaker) => {
    const ratio = speaker.dominance_ratio ?? speaker.dominanceRatio ?? 0;
    const stateInfo = participantStates.get(speaker.speaker);
    const item = document.createElement("div");
    item.className = "speaker-row";
    item.innerHTML = `
      <div>
        <strong>${speaker.speaker}</strong>
        <div class="muted">${speaker.talk_time_sec || speaker.talkTimeSec || 0}s total airtime</div>
        ${
          stateInfo
            ? `<div class="muted">Attention ${formatMetric(stateInfo.average_attention)}% | Emotion ${stateInfo.dominant_emotion}</div>`
            : `<div class="muted">Attention model pending for this speaker</div>`
        }
        <div class="bar"><span style="width:${ratio}%"></span></div>
      </div>
      <strong>${ratio}%</strong>
    `;
    speakerSummary.appendChild(item);
  });

  transcriptList.innerHTML = "";
  buildMeetingDetailRows(state.currentMeeting).forEach((payload) => {
    const row = document.createElement("div");
    row.className = "transcript-row";
    row.innerHTML = `<strong>${payload.left}</strong><span>${payload.middle}</span><span>${payload.right}</span>`;
    transcriptList.appendChild(row);
  });

  const transcriptPreview = document.createElement("div");
  transcriptPreview.className = "transcript-row";
  transcriptPreview.innerHTML = `<strong>Transcript Preview</strong><span>Showing first 5 entries only</span><span>${buildTranscriptPreview(state.currentMeeting)}</span>`;
  transcriptList.appendChild(transcriptPreview);

  const transcriptDownload = document.createElement("div");
  transcriptDownload.className = "transcript-row";
  transcriptDownload.innerHTML = `<strong>Transcript File</strong><span>Download full CSV transcript</span><span><button class="ghost-btn" type="button" id="downloadTranscriptBtn">Download Transcript</button></span>`;
  transcriptList.appendChild(transcriptDownload);
  const transcriptButton = document.getElementById("downloadTranscriptBtn");
  if (transcriptButton) {
    transcriptButton.addEventListener("click", () => openReport("transcript.csv"));
  }
}

function renderCvFeaturePanel() {
  const container = document.getElementById("cvFeatureContent");
  if (!container) {
    return;
  }

  if (!state.currentMeeting) {
    container.innerHTML = `<div class="empty-state">Process a meeting to inspect the visual-analysis extension.</div>`;
    return;
  }

  const meeting = state.currentMeeting;
  const visualArtifacts = meeting.visual_artifacts || [];
  const videoProbe = meeting.metadata?.video_probe || {};
  const sampling = meeting.metadata?.performance_report?.sampling_limits || {};
  const frameWindows = visualArtifacts.map((artifact, index) => ({
    artifact,
    index,
    displayMode: normalizeCvLabel(resolveDisplayMode(artifact)),
    artifactType: normalizeCvLabel(resolveArtifactType(artifact)),
    detectionCount: (artifact.detections || []).length
  }));
  const duration = Number(videoProbe.duration_sec || 0);
  const fps = Number(videoProbe.fps || 0);
  const frameCount = Number(videoProbe.frame_count || 0);
  const sampleSeconds = Number(sampling.visual_sample_seconds || inferSampleSeconds(visualArtifacts));
  const sampleCount = frameWindows.length;
  const sampledFrameEstimate = sampleCount > 0 && fps > 0 && sampleSeconds > 0
    ? Math.max(sampleCount, Math.round(sampleCount * fps * sampleSeconds))
    : sampleCount;
  const displayCounts = countBy(frameWindows, (item) => item.displayMode);
  const artifactCounts = countBy(frameWindows, (item) => item.artifactType);
  const contentArtifacts = visualArtifacts.filter((artifact) =>
    String(artifact.content_text || "").trim() || String(artifact.content_insight || "").trim()
  );
  const transcriptSegments = meeting.transcript?.segments || [];
  const activeSpeakerTimeline = meeting.speaker_dominance?.active_speaker_timeline || [];
  const visualSpeakerWindows = activeSpeakerTimeline.filter((entry) => entry.source === "visual-active-speaker");
  const audioSpeakerWindows = activeSpeakerTimeline.filter((entry) => entry.source === "audio-dominance");
  const presentationInsights = meeting.metadata?.presentation_insights || {};
  const classifierSummary =
    meeting.metadata?.performance_report?.current_status?.visual_artifact_logging
    || meeting.metadata?.performance_report?.current_status?.speaker_dominance
    || "Model-backed CV signals available.";

  container.innerHTML = `
    <div class="cv-highlight-grid">
      <article class="cv-stat-card">
        <span>Sampled windows</span>
        <strong>${sampleCount}</strong>
        <small class="muted">${sampleSeconds ? `Approx. every ${formatMetric(sampleSeconds)}s` : "Derived from artifact windows"}</small>
      </article>
      <article class="cv-stat-card">
        <span>Frames covered</span>
        <strong>${sampledFrameEstimate}</strong>
        <small class="muted">${fps ? `${formatMetric(fps)} fps source video` : "Frame rate unavailable"}</small>
      </article>
      <article class="cv-stat-card">
        <span>Speaker video windows</span>
        <strong>${sumCounts(displayCounts, ["speaker video"])}</strong>
        <small class="muted">Frames classified as speaker-led visuals</small>
      </article>
      <article class="cv-stat-card">
        <span>Presentation windows</span>
        <strong>${sumCounts(displayCounts, ["screen share", "presentation"])}</strong>
        <small class="muted">Frames classified as shared slides, text, charts, or dashboards</small>
      </article>
    </div>
    <div class="cv-summary-grid">
      <section class="cv-lane-card">
        <div class="cv-lane-head">
          <strong>Display-mode split</strong>
          <span>${sampleCount} sampled windows</span>
        </div>
        <div class="cv-lane-list">
          ${renderCvCountRows(displayCounts, sampleCount)}
        </div>
      </section>
      <section class="cv-lane-card">
        <div class="cv-lane-head">
          <strong>Artifact-type split</strong>
          <span>${Object.keys(artifactCounts).length} categories</span>
        </div>
        <div class="cv-lane-list">
          ${renderCvCountRows(artifactCounts, sampleCount)}
        </div>
      </section>
    </div>
    <div class="cv-lane-grid">
      <section class="cv-content-card">
        <div class="cv-timeline-meta">
          <strong>Presentation Insight</strong>
          <span>${presentationInsights.summary_source ? `Summary source: ${presentationInsights.summary_source}` : "Slide and transcript synthesis"}</span>
        </div>
        <div class="cv-content-list">
          ${renderPresentationInsights(presentationInsights)}
        </div>
      </section>
      <section class="cv-notes-card">
        <div class="cv-lane-head">
          <strong>What the CV pass is showing</strong>
          <span>Extension only</span>
        </div>
        <div class="cv-note-list">
          <div>
            <strong>Frame splitting</strong>
            <p class="muted">The video is sampled into time windows, then each sampled frame is classified for display mode and artifact type rather than changing the rest of the BoardSight workflow.</p>
          </div>
          <div>
            <strong>Speaker vs presentation</strong>
            <p class="muted">Display mode separates speaker-video scenes from screen-share or hybrid views so presentation-heavy segments stand apart from talking-head segments.</p>
          </div>
          <div>
            <strong>Slides, text, charts, and graphs</strong>
            <p class="muted">Artifact labels group each sampled window into presentation content such as slides, dashboards, documents, and charts/graphs whenever the classifier identifies them.</p>
          </div>
          <div>
            <strong>Model path</strong>
            <p class="muted">${classifierSummary}</p>
          </div>
        </div>
      </section>
      <section class="cv-notes-card">
        <div class="cv-lane-head">
          <strong>Cross-signal context</strong>
          <span>Audio + visual</span>
        </div>
        <div class="cv-note-list">
          <div>
            <strong>Transcript segments</strong>
            <p class="muted">${transcriptSegments.length} ASR segments aligned to the meeting timeline.</p>
          </div>
          <div>
            <strong>Audio speaker windows</strong>
            <p class="muted">${audioSpeakerWindows.length} timeline segments came from audio-dominance speaker activity.</p>
          </div>
          <div>
            <strong>Visual speaker windows</strong>
            <p class="muted">${visualSpeakerWindows.length} windows came from visual active-speaker enrichment.</p>
          </div>
          <div>
            <strong>Video probe</strong>
            <p class="muted">${frameCount || "--"} frames | ${duration ? `${formatMetric(duration)}s` : "Duration unavailable"} | ${videoProbe.width || "--"}x${videoProbe.height || "--"}.</p>
          </div>
        </div>
      </section>
    </div>
    <section class="cv-content-card">
      <div class="cv-timeline-meta">
        <strong>Extracted Slide Content</strong>
        <span>${contentArtifacts.length > 0 ? "Best-effort OCR from sampled presentation windows" : "No readable slide text was extracted for this meeting"}</span>
      </div>
      <div class="cv-content-list">
        ${renderCvContentArtifacts(contentArtifacts)}
      </div>
    </section>
    <section class="cv-timeline-card">
      <div class="cv-timeline-meta">
        <strong>Sampled frame windows</strong>
        <span>${sampleCount > 0 ? "Each row is one sampled CV window" : "No sampled windows detected"}</span>
      </div>
      <div class="cv-frame-list">
        ${renderCvTimeline(frameWindows, duration)}
      </div>
    </section>
  `;
}

function toggleMeetingActions(enabled) {
  [exportPdfBtn, exportDocxBtn, exportXlsxBtn, exportTraceBtn].forEach((button) => {
    button.disabled = !enabled;
    button.classList.toggle("is-disabled", !enabled);
  });
}

function renderTrace() {
  const traceTimeline = document.getElementById("traceTimeline");
  const summary = document.getElementById("decisionSummary");
  traceTimeline.innerHTML = "";
  summary.innerHTML = "";

  if (!state.currentMeeting) {
    traceTimeline.innerHTML = `<div class="empty-state">No decision trace available yet.</div>`;
    summary.innerHTML = `<p class="muted">Process a meeting to generate decision summaries.</p>`;
    return;
  }

  const traces = state.currentMeeting.decision_traces || [];
  if (traces.length === 0) {
    traceTimeline.innerHTML = `<div class="muted">No decision trace available.</div>`;
    summary.innerHTML = `<p class="muted">No explicit decision was detected in the selected meeting.</p>`;
    return;
  }

  traces.forEach((trace) => {
    const tasks = (trace.execution_tasks || []).slice(0, 2).map((task) => task.title).join(" | ");
    const speakers = (trace.supporting_speakers || []).join(", ");
    const item = document.createElement("div");
    item.className = "trace-item";
    item.innerHTML = `<strong>${trace.trace_id}</strong><div class="line"></div><div class="trace-card"><strong>${trace.title}</strong><p>${trace.summary}</p><small class="muted">${trace.rationale.join(" ")}</small><p class="muted">Priority ${formatMetric(trace.priority_score)} | Type ${trace.decision_type || "decision"}</p>${speakers ? `<p class="muted">Supporting speakers: ${speakers}</p>` : ""}${tasks ? `<p class="muted">Tasks: ${tasks}</p>` : ""}</div>`;
    traceTimeline.appendChild(item);
  });

  summary.innerHTML = `
    <div class="speaker-row"><span>Total Decisions</span><strong>${state.currentMeeting.decision_moments.length}</strong></div>
    <div class="speaker-row"><span>Action Items</span><strong>${state.currentMeeting.workflow_model?.execution_plan?.length || 0}</strong></div>
    <div class="speaker-row"><span>Top Topic</span><strong>${traces[0].title}</strong></div>
    <div class="speaker-row"><span>Priority Score</span><strong>${traces[0].priority_score || 0}</strong></div>
    <div class="speaker-row"><span>Artifacts Linked</span><strong>${traces[0].related_artifacts?.length || 0}</strong></div>
    <div class="speaker-row"><span>Attention</span><strong>${formatMetric(state.currentMeeting.attention_sentiment?.overall_attention)}%</strong></div>
    <div class="speaker-row"><span>Sentiment</span><strong>${capitalize(state.currentMeeting.attention_sentiment?.overall_sentiment || "--")}</strong></div>
  `;
}

function renderWorkflow() {
  if (!state.currentMeeting) {
    document.getElementById("workflowCanvas").innerHTML = `<div class="empty-state">No workflow model available yet.</div>`;
    document.getElementById("workflowProperties").innerHTML = `<div class="empty-state">Process a meeting to inspect workflow properties.</div>`;
    return;
  }

  const stages = state.currentMeeting.workflow_model?.stages || [];
  const prioritized = state.currentMeeting.workflow_model?.prioritized_decisions || [];
  const tasks = state.currentMeeting.workflow_model?.execution_plan || [];
  document.getElementById("workflowCanvas").innerHTML =
    stages.length === 0 && prioritized.length === 0
      ? `<div class="empty-state">No workflow model available yet.</div>`
      : `<div class="workflow-nodes">${
          prioritized.slice(0, 6).map((item) => `<div class="workflow-node">#${item.execution_rank} ${item.decision_id}<br><small>${item.priority_score} | ${item.speaker}</small></div>`).join("")
          || stages.slice(0, 6).map((stage) => `<div class="workflow-node">${stage.stage}</div>`).join("")
        }</div>`;

  document.getElementById("workflowProperties").innerHTML = `
    <div class="speaker-row"><span>Stages tracked</span><strong>${stages.length}</strong></div>
    <div class="speaker-row"><span>Bottlenecks</span><strong>${state.currentMeeting.workflow_model?.bottlenecks?.length || 0}</strong></div>
    <div class="speaker-row"><span>Execution readiness</span><strong>${state.currentMeeting.meeting_scores?.execution_readiness || 0}</strong></div>
    <div class="speaker-row"><span>Queued tasks</span><strong>${tasks.length}</strong></div>
    <div class="speaker-row"><span>Top decision</span><strong>${prioritized[0]?.decision_id || "None"}</strong></div>
    <div class="speaker-row"><span>Top owner</span><strong>${tasks[0]?.owner || "Unassigned"}</strong></div>
    <div class="speaker-row"><span>First task</span><strong>${shorten(tasks[0]?.title || "None", 42)}</strong></div>
    <div class="speaker-row"><span>Focus</span><strong>${formatMetric(state.currentMeeting.meeting_scores?.cognitive_rating?.meeting_focus)}%</strong></div>
    <div class="speaker-row"><span>Clarity</span><strong>${formatMetric(state.currentMeeting.meeting_scores?.cognitive_rating?.meeting_clarity)}%</strong></div>
    <div class="speaker-row"><span>Overload Risk</span><strong>${formatMetric(state.currentMeeting.meeting_scores?.cognitive_rating?.overload_risk)}%</strong></div>
    <div class="speaker-row"><span>Coverage</span><strong>${formatMetric((state.currentMeeting.attention_sentiment?.coverage_ratio || 0) * 100)}%</strong></div>
  `;
}

async function handleUpload(event) {
  const file = event.target.files?.[0];
  if (!file) return;

  let startSeconds = null;
  let endSeconds = null;
  try {
    startSeconds = parseTimeInput(analysisStartInput?.value || "");
    endSeconds = parseTimeInput(analysisEndInput?.value || "");
  } catch (error) {
    uploadStatus.textContent = error.message || "Enter time as mm:ss or hh:mm:ss.";
    uploadInput.value = "";
    return;
  }

  if (startSeconds !== null && startSeconds < 0) {
    uploadStatus.textContent = "Start time must be 0 or greater.";
    uploadInput.value = "";
    return;
  }
  if (endSeconds !== null && endSeconds <= 0) {
    uploadStatus.textContent = "End time must be greater than 0.";
    uploadInput.value = "";
    return;
  }
  if (startSeconds !== null && endSeconds !== null && endSeconds <= startSeconds) {
    uploadStatus.textContent = "End time must be later than start time.";
    uploadInput.value = "";
    return;
  }

  setProcessingState(true, `Uploading ${file.name} and running BoardSight analysis...`);
  const formData = new FormData();
  formData.append("file", file);
  const requestUrl = new URL("/api/analyze", window.location.origin);
  requestUrl.searchParams.set("analysis_profile", analysisProfileInput?.value || "recorded-fast");
  requestUrl.searchParams.set("source_mode", "recorded");
  if (startSeconds !== null) {
    requestUrl.searchParams.set("start_seconds", String(startSeconds));
  }
  if (endSeconds !== null) {
    requestUrl.searchParams.set("end_seconds", String(endSeconds));
  }

  try {
    const response = await apiFetch(requestUrl.toString(), { method: "POST", body: formData });
    if (!response.ok) {
      let errorPayload = {};
      try {
        errorPayload = await response.json();
      } catch {
        errorPayload = {};
      }
      uploadStatus.textContent = errorPayload.error || errorPayload.detail || "Upload failed.";
      return;
    }

    const payload = await response.json();
    const derivedMeetingId = deriveMeetingId(payload);
    state.sessionHasProcessed = true;
    uploadStatus.textContent = "Analysis complete. Loading meeting results...";
    await loadMeetings();

    if (derivedMeetingId && /^\d+$/.test(derivedMeetingId)) {
      await loadMeetingDetail(derivedMeetingId);
    } else if (state.meetings.length > 0) {
      await loadMeetingDetail(state.meetings[0].meetingId || state.meetings[0].id);
    }

    uploadStatus.textContent = "Analysis complete.";
    setView("meetings");
  } catch (error) {
    if (error?.status !== 401) {
      uploadStatus.textContent = "Analysis failed. Check the AI service logs and try again.";
    }
  } finally {
    setProcessingState(false);
    uploadInput.value = "";
  }
}

function setProcessingState(active, message = "") {
  document.body.classList.toggle("is-processing", active);
  processingOverlay?.classList.toggle("hidden", !active);
  uploadInput.disabled = active;
  if (message) {
    uploadStatus.textContent = message;
  }
}

function deriveMeetingId(payload) {
  if (payload?.storage?.meeting_id) {
    return String(payload.storage.meeting_id);
  }
  return null;
}

function setView(viewName) {
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === viewName));
  document.querySelectorAll(".content-view").forEach((view) => view.classList.add("hidden"));
  document.getElementById(`${viewName}View`).classList.remove("hidden");
}

function openReport(fileName) {
  if (!state.currentMeetingId) return;
  downloadProtectedFile(
    `/api/reports/${encodeURIComponent(state.currentMeeting.storage?.meeting_id || state.currentMeetingId)}/${fileName}`,
    fileName
  );
}

function formatDate(isoString) {
  const date = new Date(isoString);
  return Number.isNaN(date.getTime()) ? "Recent" : date.toLocaleDateString("en-GB", { month: "short", day: "numeric" });
}

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function prettifyMeetingId(id) {
  return String(id).replace(/[-_]/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function initialsFor(name) {
  return String(name || "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("") || "BS";
}

function formatMetric(value) {
  return typeof value === "number" ? value.toFixed(1) : value ?? "--";
}

function shorten(value, limit) {
  const text = String(value || "");
  return text.length > limit ? `${text.slice(0, limit - 3)}...` : text;
}

function buildMeetingSubtitle(meeting) {
  const conclusion = meeting.meeting_scores?.meeting_conclusion || "";
  const sources = (meeting.attention_sentiment?.model_sources || []).join(", ");
  const tasks = meeting.workflow_model?.execution_plan?.length || 0;
  const sentiment = meeting.attention_sentiment?.overall_sentiment;
  const attention = meeting.attention_sentiment?.overall_attention;
  const range = formatAnalysisRange(meeting.metadata?.analysis_range);
  return [conclusion, typeof attention === "number" ? `Attention: ${formatMetric(attention)}%` : "", sentiment ? `Sentiment: ${capitalize(sentiment)}` : "", sources ? `Signals: ${sources}` : "", tasks ? `Tasks queued: ${tasks}` : "", range ? `Window: ${range}` : ""]
    .filter(Boolean)
    .join(" | ");
}

function buildMeetingDetailRows(meeting) {
  const rows = [];
  rows.push({
    left: "Emotion Model",
    middle: (meeting.attention_sentiment?.model_sources || []).join(", ") || "Unavailable",
    right: `Attention ${formatMetric(meeting.attention_sentiment?.overall_attention)}% | Sentiment ${capitalize(meeting.attention_sentiment?.overall_sentiment || "--")} | Coverage ${formatMetric((meeting.attention_sentiment?.coverage_ratio || 0) * 100)}%`
  });

  (meeting.attention_sentiment?.participant_states || []).slice(0, 3).forEach((stateInfo, index) => {
    rows.push({
      left: `Participant ${index + 1}`,
      middle: stateInfo.speaker,
      right: `Attention ${formatMetric(stateInfo.average_attention)}% | Emotion ${capitalize(stateInfo.dominant_emotion)} | Samples ${stateInfo.samples}`
    });
  });

  const topDecision = meeting.workflow_model?.prioritized_decisions?.[0];
  if (topDecision) {
    rows.push({
      left: "Top Decision",
      middle: `${topDecision.decision_id} | Rank ${topDecision.execution_rank}`,
      right: `${topDecision.text} (Priority ${formatMetric(topDecision.priority_score)})`
    });
  }

  (meeting.workflow_model?.execution_plan || []).slice(0, 3).forEach((task) => {
    rows.push({
      left: `Task ${task.execution_order}`,
      middle: `${task.owner} | ${task.task_type}`,
      right: `${task.title}${task.notes ? ` | ${task.notes}` : ""}`
    });
  });

  (meeting.visual_artifacts || []).slice(0, 2).forEach((artifact) => {
    rows.push({
      left: `${formatTime(artifact.start_time)} - ${formatTime(artifact.end_time)}`,
      middle: `${artifact.display_mode} | ${artifact.artifact_type}`,
      right: artifact.content_summary || "Visual evidence detected."
    });
  });

  const analysisRange = formatAnalysisRange(meeting.metadata?.analysis_range);
  if (analysisRange) {
    rows.unshift({
      left: "Analysis Window",
      middle: meeting.metadata?.analysis_range?.mode || "selected-range",
      right: analysisRange
    });
  }

  return rows;
}

function capitalize(value) {
  const text = String(value || "");
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function buildTranscriptPreview(meeting) {
  return (meeting.transcript?.segments || [])
    .slice(0, 5)
    .map((segment) => `${formatTime(segment.start)} ${segment.speaker}: ${segment.text}`)
    .join(" | ");
}

function renderDecisionTimelineChart(container, meeting) {
  container.innerHTML = "";
  const attentionPoints = meeting.attention_sentiment?.engagement_timeline || [];
  const prioritizedMap = new Map(
    (meeting.workflow_model?.prioritized_decisions || []).map((item) => [item.decision_id, item])
  );
  const decisions = meeting.decision_moments || [];
  const maxTime = Math.max(
    60,
    ...attentionPoints.map((point) => Number(point.timestamp || 0)),
    ...decisions.map((decision) => timestampToSeconds(decision.timestamp))
  );

  attentionPoints.forEach((point) => {
    const bar = document.createElement("div");
    bar.style.position = "absolute";
    bar.style.left = `${8 + (Number(point.timestamp || 0) / maxTime) * 84}%`;
    bar.style.bottom = "28px";
    bar.style.width = "18px";
    bar.style.height = `${Math.max(18, Number(point.attention_score || 0) * 1.45)}px`;
    bar.style.borderRadius = "8px 8px 0 0";
    bar.style.background = "linear-gradient(180deg, rgba(69,104,255,0.95), rgba(127,224,228,0.7))";
    bar.title = `${point.speaker}: attention ${formatMetric(point.attention_score)}%`;
    container.appendChild(bar);
  });

  decisions.forEach((decision, index) => {
    const priority = prioritizedMap.get(decision.event_id);
    const marker = document.createElement("div");
    marker.className = "meeting-pill";
    marker.style.position = "absolute";
    marker.style.left = `${8 + (timestampToSeconds(decision.timestamp) / maxTime) * 82}%`;
    marker.style.top = `${16 + index * 30}px`;
    marker.textContent = priority ? `#${priority.execution_rank} ${formatMetric(priority.priority_score)}` : decision.label;
    container.appendChild(marker);
  });
}

function renderCvCountRows(counts, total) {
  const entries = Object.entries(counts).sort((left, right) => right[1] - left[1]);
  if (entries.length === 0) {
    return `<div class="empty-state">No visual classifications available for this meeting.</div>`;
  }
  return entries.map(([label, count]) => {
    const width = total > 0 ? Math.max(10, (count / total) * 100) : 0;
    return `
      <div class="cv-lane-item">
        <div class="cv-lane-head">
          <strong>${label}</strong>
          <span>${count} window${count === 1 ? "" : "s"}</span>
        </div>
        <div class="cv-mini-bar"><span style="width:${width}%"></span></div>
      </div>
    `;
  }).join("");
}

function renderCvTimeline(frameWindows, duration) {
  if (frameWindows.length === 0) {
    return `<div class="empty-state">No visual artifact windows were returned for this meeting.</div>`;
  }
  const totalDuration = duration > 0
    ? duration
    : Math.max(...frameWindows.map((item) => Number(item.artifact.end_time || 0)), 1);
  return frameWindows.map(({ artifact, index, displayMode, artifactType, detectionCount }) => {
    const start = Number(artifact.start_time || 0);
    const end = Number(artifact.end_time || start);
    const width = Math.max(6, ((Math.max(0.1, end - start)) / totalDuration) * 100);
    const confidence = Number(artifact.confidence || 0);
    const summary = artifact.content_summary || buildArtifactSummary(artifact);
    return `
      <article class="cv-frame-item">
        <div class="cv-frame-head">
          <strong>Window ${index + 1}: ${formatTime(start)} - ${formatTime(end)}</strong>
          <span class="meeting-pill">${Math.round(confidence * 100)}% confidence</span>
        </div>
        <div class="cv-frame-track"><span style="width:${width}%"></span></div>
        <div class="cv-frame-tags">
          <span class="cv-chip">${displayMode}</span>
          <span class="cv-chip">${artifactType}</span>
          <span class="cv-chip is-muted">${detectionCount} object detection${detectionCount === 1 ? "" : "s"}</span>
        </div>
        <div class="muted">${summary}</div>
      </article>
    `;
  }).join("");
}

function renderCvContentArtifacts(artifacts) {
  if (!artifacts || artifacts.length === 0) {
    return `<div class="empty-state">Presentation windows were detected, but no reliable slide text could be read from the sampled frames.</div>`;
  }
  return artifacts.map((artifact) => `
    <article class="cv-content-item">
      <div class="cv-frame-head">
        <strong>${formatTime(Number(artifact.start_time || 0))} - ${formatTime(Number(artifact.end_time || 0))}</strong>
        <span class="cv-chip">${normalizeCvLabel(artifact.artifact_type || artifact.artifactType || "visual-artifact")}</span>
      </div>
      <p>${escapeHtml(String(artifact.content_text || artifact.content_insight || ""))}</p>
      <div class="muted">${escapeHtml(String(artifact.content_summary || "Model-backed presentation content extraction."))}</div>
    </article>
  `).join("");
}

function renderPresentationInsights(presentationInsights) {
  const summary = String(presentationInsights?.summary || "").trim();
  const evidence = Array.isArray(presentationInsights?.evidence) ? presentationInsights.evidence : [];
  if (!summary && evidence.length === 0) {
    return `<div class="empty-state">No meeting-level presentation insight is available for this run yet.</div>`;
  }
  return `
    <article class="cv-content-item">
      <div class="cv-frame-head">
        <strong>What the video appears to be about</strong>
        <span class="cv-chip">${Number(presentationInsights?.visual_window_count || 0)} presentation window${Number(presentationInsights?.visual_window_count || 0) === 1 ? "" : "s"}</span>
      </div>
      <p>${escapeHtml(summary || "Model-backed presentation insight is unavailable for this meeting.")}</p>
      <div class="muted">${renderPresentationEvidenceLine(evidence)}</div>
    </article>
  `;
}

function renderPresentationEvidenceLine(evidence) {
  if (!evidence || evidence.length === 0) {
    return "No aligned slide evidence was stored for this meeting.";
  }
  return evidence.slice(0, 2).map((item) => {
    const timeRange = `${formatTime(Number(item?.time_range?.start_seconds || 0))} - ${formatTime(Number(item?.time_range?.end_seconds || 0))}`;
    const content = String(item?.content_text || item?.content_insight || item?.nearby_transcript || "").trim();
    return `${timeRange}: ${shorten(content, 160)}`;
  }).join(" | ");
}

function renderWorkflowSnapshot(prioritizedDecisions, workflowStages, executionPlan) {
  if (prioritizedDecisions.length > 0) {
    return `<div class="workflow-nodes">${prioritizedDecisions.slice(0, 4).map((decision) => {
      const barWidth = Math.max(24, Math.min(100, Number(decision.priority_score || 0)));
      return `<div class="workflow-node"><strong>#${decision.execution_rank} ${decision.decision_id}</strong><br><small>${decision.speaker}</small><div class="bar"><span style="width:${barWidth}%"></span></div><small>${decision.priority_score} priority</small></div>`;
    }).join("")}</div>`;
  }
  return `<div class="workflow-nodes">${workflowStages.slice(0, 4).map((stage, index) => `<div class="workflow-node"><strong>${stage.stage}</strong><br><small>${executionPlan[index]?.task_type || "workflow-stage"}</small></div>`).join("")}</div>`;
}

function timestampToSeconds(timestamp) {
  const parts = String(timestamp || "0:0").split(":");
  if (parts.length !== 2) return 0;
  return Number(parts[0] || 0) * 60 + Number(parts[1] || 0);
}

function normalizeCvLabel(value) {
  return String(value || "unclassified")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function resolveDisplayMode(artifact) {
  const explicit = String(artifact.display_mode || artifact.displayMode || "").trim();
  if (explicit) {
    return explicit;
  }
  const artifactType = String(artifact.artifact_type || artifact.artifactType || "").toLowerCase();
  if (artifactType.includes("slide") || artifactType.includes("chart") || artifactType.includes("graph") || artifactType.includes("dashboard") || artifactType.includes("document")) {
    return "screen-share";
  }
  if (artifactType.includes("speaker") || artifactType.includes("person")) {
    return "speaker-video";
  }
  return "presentation";
}

function resolveArtifactType(artifact) {
  const explicit = String(artifact.artifact_type || artifact.artifactType || "").trim();
  if (explicit) {
    return explicit;
  }
  const displayMode = String(artifact.display_mode || artifact.displayMode || "").toLowerCase();
  if (displayMode.includes("screen")) {
    return "presentation-content";
  }
  if (displayMode.includes("speaker")) {
    return "speaker-frame";
  }
  return "visual-artifact";
}

function inferSampleSeconds(artifacts) {
  if (!artifacts || artifacts.length < 2) {
    return 0;
  }
  const starts = artifacts
    .map((artifact) => Number(artifact.start_time || 0))
    .filter((value) => Number.isFinite(value))
    .sort((left, right) => left - right);
  const gaps = [];
  for (let index = 1; index < starts.length; index += 1) {
    const gap = starts[index] - starts[index - 1];
    if (gap > 0) {
      gaps.push(gap);
    }
  }
  if (gaps.length === 0) {
    return 0;
  }
  return gaps.reduce((sum, value) => sum + value, 0) / gaps.length;
}

function countBy(items, getKey) {
  return items.reduce((accumulator, item) => {
    const key = getKey(item) || "Unclassified";
    accumulator[key] = (accumulator[key] || 0) + 1;
    return accumulator;
  }, {});
}

function sumCounts(counts, labels) {
  return labels.reduce((sum, label) => sum + (counts[normalizeCvLabel(label)] || 0), 0);
}

function buildArtifactSummary(artifact) {
  const detections = (artifact.detections || []).map((item) => item.label || item.class_name || item.className).filter(Boolean);
  if (detections.length > 0) {
    return `Detected objects: ${detections.join(", ")}.`;
  }
  return "Sampled visual window classified by the CV pipeline.";
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeRole(value) {
  return String(value || "analyst").trim().toLowerCase().replace(/\s+/g, "_");
}

function prettifyRole(value) {
  return String(value || "analyst")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function setLabelText(labelElement, text) {
  const input = labelElement.querySelector("input, select");
  labelElement.textContent = text;
  if (input) {
    labelElement.appendChild(input);
  }
}

function normalizeMessage(value) {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => normalizeMessage(item?.msg || item?.detail || item)).join(" ");
  }
  if (value && typeof value === "object") {
    return value.msg || value.detail || JSON.stringify(value);
  }
  return String(value || "");
}

function parseTimeInput(value) {
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }
  if (/^\d+(\.\d+)?$/.test(text)) {
    return Number(text);
  }
  const parts = text.split(":").map((item) => item.trim());
  if (parts.some((item) => item === "" || Number.isNaN(Number(item)))) {
    throw new Error("Use seconds, mm:ss, or hh:mm:ss for the analysis window.");
  }
  if (parts.length === 2) {
    return Number(parts[0]) * 60 + Number(parts[1]);
  }
  if (parts.length === 3) {
    return Number(parts[0]) * 3600 + Number(parts[1]) * 60 + Number(parts[2]);
  }
  throw new Error("Use seconds, mm:ss, or hh:mm:ss for the analysis window.");
}

function formatAnalysisRange(range) {
  if (!range || range.mode === "full-video") {
    return "";
  }
  const start = typeof range.start_seconds === "number" ? formatTime(range.start_seconds) : "00:00";
  const end = typeof range.end_seconds === "number" ? formatTime(range.end_seconds) : "End";
  const duration = typeof range.duration_seconds === "number" ? ` (${formatTime(range.duration_seconds)} selected)` : "";
  return `${start} to ${end}${duration}`;
}

async function startLiveSession() {
  if (state.liveSession?.status === "active") {
    liveStatusText.textContent = "A live session is already running.";
    return;
  }

  if (!window.MediaRecorder || !navigator.mediaDevices) {
    liveStatusText.textContent = "This browser does not support live media capture.";
    return;
  }

  const title = (liveTitleInput?.value || "").trim() || `Live Meeting ${new Date().toLocaleTimeString()}`;
  const sourceType = liveSourceInput?.value || "display-audio";
  const analysisProfile = liveProfileInput?.value || "live";

  startLiveBtn.disabled = true;
  liveStatusText.textContent = "Starting live session...";

  try {
    const params = new URLSearchParams({
      title,
      source_type: sourceType,
      analysis_profile: analysisProfile
    });
    const response = await apiFetch(`/api/live/start?${params.toString()}`, {
      method: "POST"
    });
    const payload = await response.json();
    if (!response.ok) {
      liveStatusText.textContent = payload.detail || payload.error || "Failed to start live session.";
      return;
    }

    state.liveSession = payload;
    renderLiveSession();
    setView("live");

    liveCaptureStream = await createLiveCaptureStream(sourceType);
    const recorderOptions = resolveRecorderOptions(liveCaptureStream);
    liveRecorder = recorderOptions ? new MediaRecorder(liveCaptureStream, recorderOptions) : new MediaRecorder(liveCaptureStream);
    liveStartedAtMs = Date.now();
    liveChunkStartSeconds = 0;
    liveFinalizeRequested = false;
    liveUploadChain = Promise.resolve();

    liveRecorder.ondataavailable = (event) => {
      if (!event.data || event.data.size === 0 || !state.liveSession?.session_id) {
        return;
      }
      const elapsedSeconds = Math.max(1, Math.round((Date.now() - liveStartedAtMs) / 1000));
      const chunkStart = liveChunkStartSeconds;
      const chunkEnd = Math.max(chunkStart + 1, elapsedSeconds);
      liveChunkStartSeconds = chunkEnd;
      liveUploadChain = liveUploadChain
        .then(() => uploadLiveChunk(event.data, chunkStart, chunkEnd))
        .catch((error) => {
          liveStatusText.textContent = error?.message || "Live chunk upload failed.";
        });
    };

    liveRecorder.onstop = async () => {
      await liveUploadChain;
      await finalizeLiveSession();
      teardownLiveCapture();
    };

    try {
      liveRecorder.start(15000);
    } catch (error) {
      throw new Error(`Unable to start live recording: ${error?.message || "MediaRecorder could not start."}`);
    }
    startLiveClock();
    const audioTracks = liveCaptureStream.getAudioTracks().length;
    const videoTracks = liveCaptureStream.getVideoTracks().length;
    liveStatusText.textContent = `Live session is running. Capturing ${audioTracks} audio track(s) and ${videoTracks} video track(s).`;
  } catch (error) {
    teardownLiveCapture();
    state.liveSession = null;
    renderLiveSession();
    liveStatusText.textContent = error?.message || "Unable to start live capture.";
  } finally {
    startLiveBtn.disabled = false;
  }
}

async function stopLiveSession(forceImmediate) {
  if (!state.liveSession?.session_id) {
    return;
  }
  liveFinalizeRequested = true;
  stopLiveBtn.disabled = true;
  liveStatusText.textContent = "Finalizing live session...";

  if (!forceImmediate && liveRecorder && liveRecorder.state !== "inactive") {
    try {
      liveRecorder.stop();
    } catch {
      await finalizeLiveSession();
      teardownLiveCapture();
    }
    return;
  }

  await finalizeLiveSession();
  teardownLiveCapture();
}

async function finalizeLiveSession() {
  if (!state.liveSession?.session_id) {
    stopLiveBtn.disabled = false;
    return;
  }

  try {
    const response = await apiFetch(`/api/live/${encodeURIComponent(state.liveSession.session_id)}/finalize`, {
      method: "POST"
    });
    const payload = await response.json();
    if (response.ok) {
      state.liveSession = payload.final_result || payload;
      renderLiveSession();
      liveStatusText.textContent = "Live session finalized. Final meeting summary and outcomes are ready.";
    } else {
      liveStatusText.textContent = payload.detail || payload.error || "Finalization failed.";
    }
  } catch (error) {
    liveStatusText.textContent = error?.message || "Finalization failed.";
  } finally {
    stopLiveBtn.disabled = false;
  }
}

async function uploadLiveChunk(blob, chunkStartSeconds, chunkEndSeconds) {
  if (!state.liveSession?.session_id) {
    return;
  }
  const formData = new FormData();
  formData.append("file", blob, `live-chunk-${chunkStartSeconds}.webm`);
  formData.append("chunk_start_seconds", String(chunkStartSeconds));
  formData.append("chunk_end_seconds", String(chunkEndSeconds));

  const response = await apiFetch(`/api/live/${encodeURIComponent(state.liveSession.session_id)}/chunk`, {
    method: "POST",
    body: formData
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || "Live chunk processing failed.");
  }
  state.liveSession = payload;
  renderLiveSession();
}

async function createLiveCaptureStream(sourceType) {
  if (sourceType === "microphone") {
    const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    liveSourceStreams = [micStream];
    return micStream;
  }

  const displayStream = await navigator.mediaDevices.getDisplayMedia({
    video: true,
    audio: true
  });
  liveSourceStreams = [displayStream];

  if (displayStream.getAudioTracks().length > 0) {
    return displayStream;
  }

  const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  liveSourceStreams.push(micStream);
  const merged = new MediaStream([
    ...displayStream.getVideoTracks(),
    ...micStream.getAudioTracks()
  ]);
  return merged;
}

function resolveRecorderOptions(stream) {
  const hasVideo = (stream?.getVideoTracks?.() || []).length > 0;
  const candidates = hasVideo
    ? [
        "video/webm;codecs=vp9,opus",
        "video/webm;codecs=vp8,opus",
        "video/webm",
        "audio/webm;codecs=opus",
        "audio/webm"
      ]
    : [
        "audio/webm;codecs=opus",
        "audio/webm",
        "video/webm;codecs=vp8,opus",
        "video/webm"
      ];
  for (const mimeType of candidates) {
    if (MediaRecorder.isTypeSupported?.(mimeType)) {
      return { mimeType };
    }
  }
  return null;
}

function startLiveClock() {
  stopLiveClock();
  liveClock = window.setInterval(() => {
    if (liveStartedAtMs > 0) {
      const elapsed = Math.max(0, Math.round((Date.now() - liveStartedAtMs) / 1000));
      liveDuration.textContent = formatTime(elapsed);
    }
  }, 1000);
}

function stopLiveClock() {
  if (liveClock) {
    window.clearInterval(liveClock);
    liveClock = null;
  }
}

function teardownLiveCapture() {
  stopLiveClock();
  if (liveCaptureStream) {
    liveCaptureStream.getTracks().forEach((track) => track.stop());
    liveCaptureStream = null;
  }
  for (const stream of liveSourceStreams) {
    try {
      stream.getTracks().forEach((track) => track.stop());
    } catch {}
  }
  liveSourceStreams = [];
  liveRecorder = null;
  liveStartedAtMs = 0;
  liveChunkStartSeconds = 0;
}

function renderLiveSession() {
  const session = state.liveSession;
  if (!session) {
    liveStatusBadge.textContent = "Idle";
    liveSessionId.textContent = "--";
    liveSegmentCount.textContent = "0";
    liveDecisionCount.textContent = "0";
    liveActionCount.textContent = "0";
    liveProblemCount.textContent = "0";
    liveDuration.textContent = "00:00";
    liveSummaryText.textContent = "Start a session to generate live meeting context.";
    liveSuggestions.innerHTML = `<div class="empty-state">Suggestions will appear during the meeting.</div>`;
    liveProblems.innerHTML = `<div class="empty-state">Problems and risks will appear when they are detected.</div>`;
    liveActions.innerHTML = `<div class="empty-state">Decisions and to-dos will appear as the meeting progresses.</div>`;
    liveDiscussionPoints.innerHTML = `<div class="empty-state">Discussion points will be extracted from the live transcript.</div>`;
    liveOutcomes.innerHTML = `<div class="empty-state">Meeting outcomes will populate when the session is finalized.</div>`;
    liveVisualArtifacts.innerHTML = `<div class="empty-state">Screen-share and visual evidence will appear when live video is available.</div>`;
    livePresentationInsights.innerHTML = `<div class="empty-state">Presentation context will appear when slide or screen windows are detected.</div>`;
    liveTranscript.innerHTML = `<div class="empty-state">Transcript chunks will appear here during the meeting.</div>`;
    gitlabPlanPreview.innerHTML = `<div class="empty-state">Preview the GitLab execution plan after the meeting starts.</div>`;
    return;
  }

  liveStatusBadge.textContent = capitalize(session.status || "active");
  liveSessionId.textContent = session.session_id || session.storage?.session_id || "--";
  liveSegmentCount.textContent = String(session.transcript?.length || 0);
  liveDecisionCount.textContent = String(session.decisions?.length || 0);
  liveActionCount.textContent = String(session.action_items?.length || 0);
  liveProblemCount.textContent = String(session.problems?.length || 0);
  if (!liveClock && session.transcript?.length) {
    const lastSegment = session.transcript[session.transcript.length - 1];
    liveDuration.textContent = formatTime(Number(lastSegment.end || 0));
  }
  liveSummaryText.textContent = session.final_summary || session.rolling_summary || "Live analysis is in progress.";

  liveSuggestions.innerHTML = renderLiveCardList(
    session.suggestions || [],
    (item) => ({
      title: "Suggestion",
      body: item
    }),
    "Suggestions will appear during the meeting."
  );
  liveProblems.innerHTML = renderLiveCardList(
    session.problems || [],
    (item) => ({
      title: `${formatTime(Number(item.timestamp || 0))} | ${item.category || "Problem"}`,
      body: item.text || "",
      meta: `${item.speaker || "Unknown"} | confidence ${formatMetric(item.confidence || 0)}`
    }),
    "Problems and risks will appear when they are detected."
  );
  liveActions.innerHTML = renderLiveCardList(
    (session.action_items || []).length > 0 ? session.action_items : (session.decisions || []),
    (item) => ({
      title: item.title || `${item.label || "Decision"} | ${item.speaker || "Unknown"}`,
      body: item.notes || item.text || "",
      meta: item.owner || item.timestamp || ""
    }),
    "Decisions and to-dos will appear as the meeting progresses."
  );
  liveDiscussionPoints.innerHTML = renderLiveCardList(
    session.discussion_points || [],
    (item) => ({
      title: "Discussion Point",
      body: item
    }),
    "Discussion points will be extracted from the live transcript."
  );
  liveOutcomes.innerHTML = renderLiveCardList(
    session.meeting_outcomes || [],
    (item) => ({
      title: "Outcome",
      body: item
    }),
    "Meeting outcomes will populate when the session is finalized."
  );
  liveVisualArtifacts.innerHTML = renderLiveCardList(
    session.visual_artifacts || [],
    (item) => ({
      title: `${formatTime(Number(item.start_time || 0))} | ${normalizeCvLabel(item.artifact_type || "visual-artifact")}`,
      body: item.content_insight || item.content_text || item.content_summary || item.display_mode || "Visual evidence detected.",
      meta: `${normalizeCvLabel(item.display_mode || "screen-share")} | confidence ${formatMetric((Number(item.confidence || 0) * 100))}%`
    }),
    "Screen-share and visual evidence will appear when live video is available."
  );
  livePresentationInsights.innerHTML = renderLiveCardList(
    session.presentation_windows || [],
    (item) => ({
      title: item.summary_source || "presentation-summary",
      body: item.summary || "Presentation context unavailable.",
      meta: `${Number(item.visual_window_count || 0)} visual windows`
    }),
    "Presentation context will appear when slide or screen windows are detected."
  );
  liveTranscript.innerHTML = renderLiveTranscript(session.transcript || []);
  if (!state.liveSession?.gitlabPlan) {
    gitlabPlanPreview.innerHTML = `<div class="empty-state">Preview the GitLab execution plan after the meeting starts.</div>`;
  } else {
    gitlabPlanPreview.innerHTML = renderGitlabPlan(state.liveSession.gitlabPlan, state.liveSession.gitlabSyncResult);
  }
}

async function runGitlabPlan(dryRun) {
  if (!state.liveSession?.session_id) {
    gitlabStatusText.textContent = "Start or finalize a live session first.";
    return;
  }
  gitlabStatusText.textContent = dryRun ? "Generating GitLab execution plan..." : "Syncing BoardSight actions to GitLab...";
  const connection = {
    base_url: (gitlabBaseUrlInput?.value || "").trim(),
    project_id: (gitlabProjectIdInput?.value || "").trim(),
    private_token: (gitlabTokenInput?.value || "").trim()
  };
  const payload = {
    source_kind: "live",
    source_id: state.liveSession.session_id,
    connection,
    assignee_map: {}
  };
  const params = new URLSearchParams({
    source_kind: payload.source_kind,
    source_id: payload.source_id
  });
  if (!dryRun) {
    if (connection.base_url) params.set("gitlab_base_url", connection.base_url);
    if (connection.project_id) params.set("gitlab_project_id", connection.project_id);
    if (connection.private_token) params.set("gitlab_private_token", connection.private_token);
  }
  const url = dryRun ? `/api/gitlab/plan?${params.toString()}` : `/api/gitlab/sync?${params.toString()}`;
  try {
    const response = await apiFetch(url, {
      method: "POST"
    });
    const result = await response.json();
    if (!response.ok) {
      gitlabStatusText.textContent = result.detail || result.error || "GitLab execution failed.";
      return;
    }
    state.liveSession.gitlabPlan = result.plan;
    state.liveSession.gitlabSyncResult = result.sync_result || null;
    gitlabPlanPreview.innerHTML = renderGitlabPlan(result.plan, result.sync_result || null);
    gitlabStatusText.textContent = dryRun
      ? "GitLab execution plan generated."
      : (result.sync_result?.status === "synced"
          ? "GitLab issues and links created successfully."
          : "GitLab settings are missing, so a dry-run style result was returned.");
  } catch (error) {
    gitlabStatusText.textContent = error?.message || "GitLab execution failed.";
  }
}

function renderGitlabPlan(plan, syncResult) {
  if (!plan) {
    return `<div class="empty-state">No GitLab plan available.</div>`;
  }
  const issues = plan.issues || [];
  const links = plan.issue_links || [];
  const syncSummary = syncResult
    ? `<div class="live-card-item"><strong>Sync Status</strong><div>${escapeHtml(syncResult.status || "unknown")}</div><small>${escapeHtml(syncResult.reason || "")}</small></div>`
    : "";
  return `
    <div class="live-card-list">
      ${syncSummary}
      <article class="live-card-item">
        <strong>Milestone</strong>
        <div>${escapeHtml(plan.milestone?.title || "Meeting milestone")}</div>
        <small>${escapeHtml(plan.milestone?.due_date || "No due date inferred")}</small>
      </article>
      <article class="live-card-item">
        <strong>Execution Graph</strong>
        <div>${issues.length} issues, ${links.length} dependency links</div>
        <small>${escapeHtml(plan.traceability?.generated_at || "")}</small>
      </article>
      ${issues.slice(0, 12).map((issue) => `
        <article class="live-card-item">
          <strong>${escapeHtml(issue.local_key)} | ${escapeHtml(issue.title)}</strong>
          <div>${escapeHtml(issue.owner || "Unassigned")} | ${escapeHtml((issue.labels || []).join(", "))}</div>
          <small>${escapeHtml(issue.due_date || "No due date")} ${issue.dependencies?.length ? `| depends on ${issue.dependencies.join(", ")}` : ""}</small>
        </article>
      `).join("")}
    </div>
  `;
}

function renderLiveCardList(items, toCard, emptyMessage) {
  if (!items || items.length === 0) {
    return `<div class="empty-state">${emptyMessage}</div>`;
  }
  return `<div class="live-card-list">${items.slice(0, 12).map((item) => {
    const card = toCard(item);
    return `<article class="live-card-item"><strong>${escapeHtml(card.title || "Item")}</strong><div>${escapeHtml(card.body || "")}</div>${card.meta ? `<small>${escapeHtml(card.meta)}</small>` : ""}</article>`;
  }).join("")}</div>`;
}

function renderLiveTranscript(segments) {
  if (!segments || segments.length === 0) {
    return `<div class="empty-state">Transcript chunks will appear here during the meeting.</div>`;
  }
  return segments.slice(-24).map((segment) => `
    <div class="transcript-row">
      <strong>${formatTime(Number(segment.start || 0))}</strong>
      <span>${escapeHtml(segment.speaker || "Live Speaker")}</span>
      <div>${escapeHtml(segment.text || "")}</div>
    </div>
  `).join("");
}

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.authToken) {
    headers.set("Authorization", `Bearer ${state.authToken}`);
  }
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    clearSession();
    throw { status: 401 };
  }
  return response;
}

async function downloadProtectedFile(url, fileName) {
  const response = await apiFetch(url);
  if (!response.ok) {
    return;
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

async function loadProtectedImage(url, imageElement) {
  try {
    const response = await apiFetch(url);
    if (!response.ok) {
      imageElement.classList.add("hidden");
      return;
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    imageElement.src = objectUrl;
    imageElement.classList.remove("hidden");
  } catch {
    imageElement.removeAttribute("src");
    imageElement.classList.add("hidden");
  }
}
