const DEFAULT_USER = {
  username: "admin",
  displayName: "BoardSight Admin",
  role: "admin"
};

const state = {
  meetings: [],
  currentMeetingId: null,
  currentMeeting: null,
  workflowDraft: null,
  selectedWorkflowNodeId: null,
  workflowDrag: null,
  liveSession: null,
  sessionHasProcessed: false,
  authMode: "signin",
  currentUser: DEFAULT_USER,
  authToken: localStorage.getItem("boardsight-token") || "",
  theme: localStorage.getItem("boardsight-theme") || "dark",
  demoGuide: []
};

const API_BASE = (() => {
  const explicitBase = String(window.BOARDSIGHT_API_BASE || "").trim();
  if (explicitBase) {
    return explicitBase.replace(/\/$/, "");
  }
  const { protocol, hostname, port, origin } = window.location;
  if ((hostname === "localhost" || hostname === "127.0.0.1") && port === "8080") {
    return `${protocol}//${hostname}:8000`;
  }
  return origin.replace(/\/$/, "");
})();

function apiUrl(path) {
  if (!path) {
    return API_BASE;
  }
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

const urlParams = new URLSearchParams(window.location.search);
const isLiveCopilotPopup = urlParams.get("popup") === "live-copilot";

document.body.dataset.theme = state.theme;
document.body.classList.toggle("popup-live-copilot", isLiveCopilotPopup);

const loginView = document.getElementById("loginView");
const appView = document.getElementById("appView");
const loginForm = document.getElementById("loginForm");
const themeToggle = document.getElementById("themeToggle");
const landingThemeToggle = document.getElementById("landingThemeToggle");
const authOpenBtn = document.getElementById("authOpenBtn");
const authSignupBtn = document.getElementById("authSignupBtn");
const authCloseBtn = document.getElementById("authCloseBtn");
const authModalBackdrop = document.getElementById("authModalBackdrop");
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
const authVerificationActions = document.getElementById("authVerificationActions");
const resendVerificationBtn = document.getElementById("resendVerificationBtn");
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
const guestHeroBtn = document.getElementById("guestHeroBtn");
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
const openLivePopupBtn = document.getElementById("openLivePopupBtn");
const notificationsBtn = document.getElementById("notificationsBtn");
const notificationsPanel = document.getElementById("notificationsPanel");
const notificationsHeading = notificationsPanel?.querySelector("strong");
const liveSessionTitleInput = document.getElementById("liveSessionTitleInput");
const liveSpeakerInput = document.getElementById("liveSpeakerInput");
const liveStartBtn = document.getElementById("liveStartBtn");
const liveRefreshBtn = document.getElementById("liveRefreshBtn");
const liveOpenPopupBtn = document.getElementById("liveOpenPopupBtn");
const liveFinalizeBtn = document.getElementById("liveFinalizeBtn");
const liveStatus = document.getElementById("liveStatus");
const liveNoteInput = document.getElementById("liveNoteInput");
const liveAddNoteBtn = document.getElementById("liveAddNoteBtn");
const liveTranscriptList = document.getElementById("liveTranscriptList");
const liveQuickSummary = document.getElementById("liveQuickSummary");
const liveCopilotQuestionInput = document.getElementById("liveCopilotQuestionInput");
const liveAskBtn = document.getElementById("liveAskBtn");
const liveCopilotMeta = document.getElementById("liveCopilotMeta");
const liveCopilotAnswer = document.getElementById("liveCopilotAnswer");
const liveAskSummaryBtn = document.getElementById("liveAskSummaryBtn");
const liveAskDecisionsBtn = document.getElementById("liveAskDecisionsBtn");
const liveAskActionsBtn = document.getElementById("liveAskActionsBtn");
const liveAskBlockersBtn = document.getElementById("liveAskBlockersBtn");
const gitlabBaseUrlInput = document.getElementById("gitlabBaseUrlInput");
const gitlabProjectIdInput = document.getElementById("gitlabProjectIdInput");
const gitlabPrivateTokenInput = document.getElementById("gitlabPrivateTokenInput");
const gitlabAssigneeMapInput = document.getElementById("gitlabAssigneeMapInput");
const gitlabPreviewBtn = document.getElementById("gitlabPreviewBtn");
const gitlabSyncBtn = document.getElementById("gitlabSyncBtn");
const gitlabStatus = document.getElementById("gitlabStatus");
const gitlabResult = document.getElementById("gitlabResult");
const meetingGitlabBaseUrlInput = document.getElementById("meetingGitlabBaseUrlInput");
const meetingGitlabProjectIdInput = document.getElementById("meetingGitlabProjectIdInput");
const meetingGitlabPrivateTokenInput = document.getElementById("meetingGitlabPrivateTokenInput");
const meetingGitlabAssigneeMapInput = document.getElementById("meetingGitlabAssigneeMapInput");
const meetingGitlabPreviewBtn = document.getElementById("meetingGitlabPreviewBtn");
const meetingGitlabSyncBtn = document.getElementById("meetingGitlabSyncBtn");
const meetingGitlabStatus = document.getElementById("meetingGitlabStatus");
const meetingGitlabResult = document.getElementById("meetingGitlabResult");
const workflowNewBtn = document.getElementById("workflowNewBtn");
const workflowSaveBtn = document.getElementById("workflowSaveBtn");
const workflowComponentButtons = Array.from(document.querySelectorAll(".workflow-component-btn"));
const floatingLiveLauncher = document.getElementById("floatingLiveLauncher");

let liveRefreshHandle = null;
let liveRecognition = null;
let liveRecognitionActive = false;
let livePopupHandle = null;
let liveScreenStream = null;
let liveScreenCaptureHandle = null;
let liveScreenVideo = null;
let liveScreenCanvas = null;
let authRequestInFlight = false;

themeToggle.addEventListener("click", () => {
  state.theme = state.theme === "light" ? "dark" : "light";
  document.body.dataset.theme = state.theme;
  localStorage.setItem("boardsight-theme", state.theme);
});

landingThemeToggle?.addEventListener("click", () => {
  themeToggle.click();
});

authOpenBtn?.addEventListener("click", () => {
  openAuthModal("signin");
});

authSignupBtn?.addEventListener("click", () => {
  openAuthModal("signup");
});

authCloseBtn?.addEventListener("click", () => {
  closeAuthModal();
});

authModalBackdrop?.addEventListener("click", () => {
  closeAuthModal();
});

authModeToggle.addEventListener("click", () => {
  state.authMode = state.authMode === "signin" ? "signup" : "signin";
  clearAuthFeedback();
  syncAuthMode();
});

resendVerificationBtn?.addEventListener("click", async () => {
  if (authRequestInFlight) {
    return;
  }
  const identifier = resolveVerificationIdentifier();
  if (!identifier) {
    setAuthFeedback("Enter your username or email first so we know where to resend the verification link.");
    return;
  }
  await resendVerification(identifier);
});

guestLogin.addEventListener("click", async () => {
  await launchDemoSession();
});

guestHeroBtn?.addEventListener("click", () => {
  guestLogin.click();
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  if (!username || !password) {
    setAuthFeedback("Username or email and password are required.");
    return;
  }

  clearAuthFeedback();

  if (state.authMode === "signup") {
    await withAuthPending(async () => {
      const result = await registerUser();
      setAuthFeedback(result.message, { success: result.ok });
      if (result.ok) {
        state.authMode = "signin";
        passwordInput.value = "";
        confirmPasswordInput.value = "";
        syncAuthMode();
      } else if (result.requiresVerification) {
        syncAuthMode();
      }
    }, state.authMode === "signup" ? "Creating account..." : "Working...");
    return;
  }

  await withAuthPending(async () => {
    await submitLogin(username, password);
  }, "Signing in...");
});

workflowNewBtn?.addEventListener("click", () => {
  state.workflowDraft = buildEditableWorkflowDraft(state.currentMeeting, { forceReset: true });
  state.selectedWorkflowNodeId = state.workflowDraft?.nodes?.[0]?.id || null;
  renderWorkflow();
});

workflowSaveBtn?.addEventListener("click", () => {
  saveWorkflowDraft();
});

workflowComponentButtons.forEach((button) => {
  button.addEventListener("click", () => {
    addWorkflowNode(button.dataset.workflowComponent || "review");
  });
});

function clearAuthFeedback() {
  authStatus.textContent = "";
  authStatus.classList.remove("success-text", "error-text");
}

function openAuthModal(mode = "signin") {
  state.authMode = mode;
  clearAuthFeedback();
  syncAuthMode();
  loginView.classList.add("auth-modal-open");
}

function closeAuthModal() {
  loginView.classList.remove("auth-modal-open");
}

function setAuthFeedback(message, { success = false } = {}) {
  authStatus.textContent = message;
  authStatus.classList.toggle("success-text", Boolean(success));
  authStatus.classList.toggle("error-text", Boolean(message) && !success);
}

function resolveVerificationIdentifier() {
  return (usernameInput.value.trim() || emailInput.value.trim().toLowerCase());
}

function setAuthBusy(active, busyLabel = "Working...") {
  authRequestInFlight = active;
  authSubmit.disabled = active;
  guestLogin.disabled = active;
  authModeToggle.disabled = active;
  resendVerificationBtn.disabled = active;
  usernameInput.disabled = active;
  passwordInput.disabled = active;
  displayNameInput.disabled = active;
  emailInput.disabled = active;
  confirmPasswordInput.disabled = active;
  roleInput.disabled = active;
  if (active) {
    authSubmit.innerHTML = `<span class="spinner" aria-hidden="true"></span><span>${busyLabel}</span>`;
  } else {
    guestLogin.textContent = guestLogin.dataset.defaultLabel || "Continue as Demo";
    syncAuthMode();
  }
}

async function withAuthPending(task, busyLabel) {
  if (authRequestInFlight) {
    return;
  }
  setAuthBusy(true, busyLabel);
  try {
    await task();
  } finally {
    setAuthBusy(false);
  }
}

async function resendVerification(identifier) {
  await withAuthPending(async () => {
    const response = await fetch(apiUrl("/api/v1/auth/resend-verification"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier })
    });

    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok) {
      setAuthFeedback(normalizeMessage(payload.detail || payload.error || "Could not resend verification email."));
      return;
    }
    const sent = Boolean(payload.verification_sent);
    setAuthFeedback(
      sent
        ? "Verification email sent. Check your inbox and spam folder."
        : "The account exists, but the verification email could not be sent right now.",
      { success: sent }
    );
  }, "Sending email...");
}

refreshBtn.addEventListener("click", () => loadMeetings());
signOutBtn.addEventListener("click", async () => {
  if (state.authToken) {
    try {
      await fetch(apiUrl("/api/v1/auth/logout"), {
        method: "POST",
        headers: { Authorization: `Bearer ${state.authToken}` }
      });
    } catch {
      // Best-effort server-side logout.
    }
  }
  clearSession();
  authStatus.textContent = "Signed out.";
  authStatus.classList.remove("success-text");
  passwordInput.value = "";
  confirmPasswordInput.value = "";
  setView("dashboard");
});
uploadInput.addEventListener("change", handleUpload);
searchInput.addEventListener("input", renderMeetingList);

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
openLivePopupBtn?.addEventListener("click", openLiveCopilotPopup);
notificationsBtn?.addEventListener("click", (event) => {
  event.stopPropagation();
  const willOpen = notificationsPanel?.classList.contains("hidden");
  notificationsPanel?.classList.toggle("hidden", !willOpen);
  notificationsBtn.classList.toggle("is-active", Boolean(willOpen));
  notificationsBtn.setAttribute("aria-expanded", willOpen ? "true" : "false");
});

document.addEventListener("click", (event) => {
  if (!notificationsPanel || !notificationsBtn) return;
  if (notificationsPanel.classList.contains("hidden")) return;
  const target = event.target;
  if (target instanceof Node && (notificationsPanel.contains(target) || notificationsBtn.contains(target))) return;
  notificationsPanel.classList.add("hidden");
  notificationsBtn.classList.remove("is-active");
  notificationsBtn.setAttribute("aria-expanded", "false");
});
liveStartBtn?.addEventListener("click", startLiveSession);
liveRefreshBtn?.addEventListener("click", () => refreshLiveSession());
liveOpenPopupBtn?.addEventListener("click", openLiveCopilotPopup);
liveFinalizeBtn?.addEventListener("click", finalizeLiveSession);
liveAddNoteBtn?.addEventListener("click", submitLiveNote);
liveAskBtn?.addEventListener("click", submitLiveQuestion);
liveAskSummaryBtn?.addEventListener("click", () => askLiveShortcut("What happened so far?"));
liveAskDecisionsBtn?.addEventListener("click", () => askLiveShortcut("What decisions have been made so far?"));
liveAskActionsBtn?.addEventListener("click", () => askLiveShortcut("What action items should I know right now?"));
liveAskBlockersBtn?.addEventListener("click", () => askLiveShortcut("What blockers or risks have been raised so far?"));
gitlabPreviewBtn?.addEventListener("click", () => runGitLabAssignmentRequest("preview"));
gitlabSyncBtn?.addEventListener("click", () => runGitLabAssignmentRequest("sync"));
meetingGitlabPreviewBtn?.addEventListener("click", () => runMeetingGitLabAssignmentRequest("preview"));
meetingGitlabSyncBtn?.addEventListener("click", () => runMeetingGitLabAssignmentRequest("sync"));
floatingLiveLauncher?.addEventListener("click", openLiveCopilotPopup);

syncAuthMode();
updateUserChip();
renderLiveSession();
bootstrapSession();

function openLiveCopilotPopup() {
  const popupUrl = new URL(window.location.href);
  popupUrl.searchParams.set("popup", "live-copilot");
  const popupFeatures = [
    "width=480",
    "height=760",
    "resizable=yes",
    "scrollbars=yes"
  ].join(",");
  livePopupHandle = window.open(popupUrl.toString(), "boardsight-live-copilot", popupFeatures);
  if (livePopupHandle) {
    livePopupHandle.focus();
  } else {
    setLiveStatus("Popup blocked by the browser. Allow popups for BoardSight to keep the live copilot visible.");
  }
}

function activateLivePopupMode() {
  setView("live");
  document.querySelectorAll(".content-view").forEach((view) => view.classList.add("hidden"));
  document.getElementById("liveView")?.classList.remove("hidden");
}

function syncFloatingLauncher() {
  if (!floatingLiveLauncher) {
    return;
  }
  const hasActiveSession = state.liveSession?.session?.status === "active";
  floatingLiveLauncher.classList.toggle("hidden", !hasActiveSession || isLiveCopilotPopup);
}

async function bootstrapSession() {
  if (!state.authToken) {
    closeAuthModal();
    loginView.classList.remove("hidden");
    appView.classList.add("hidden");
    return;
  }

  try {
    const response = await apiFetch("/api/v1/me");
    const payload = await response.json();
    state.currentUser = normalizeUser(payload);
    updateUserChip();
    closeAuthModal();
    loginView.classList.add("hidden");
    appView.classList.remove("hidden");
    if (isLiveCopilotPopup) {
      activateLivePopupMode();
    }
    await loadMeetings();
    await loadActiveLiveSession();
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
  authVerificationActions?.classList.toggle("hidden", !signingIn);
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

  const response = await fetch(apiUrl("/api/v1/auth/register"), {
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
    payload = await response.json();
  } catch {
    payload = {};
  }

  if (!response.ok) {
    return { ok: false, message: normalizeMessage(payload.detail || payload.error || "Registration failed.") };
  }

  if (payload.status === "verification_pending") {
    return {
      ok: true,
      requiresVerification: true,
      message: payload.verification_sent
        ? "Account created. Check your email and verify before signing in."
        : "Account created, but we could not send the verification email yet. Use resend verification below."
    };
  }

  return { ok: true, message: "Account created. Verify your email before signing in." };
}

async function submitLogin(username, password) {
  const response = await fetch(apiUrl("/api/v1/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identifier: username, password })
  });

  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }

  if (!response.ok) {
    const message = normalizeMessage(payload.detail || payload.error || "Invalid username or password.");
    setAuthFeedback(message);
    if (/verify/i.test(message)) {
      authVerificationActions?.classList.remove("hidden");
    }
    return;
  }

  await activateAuthenticatedApp(payload);
}

async function launchDemoSession() {
  await withAuthPending(async () => {
    const response = await fetch(apiUrl("/api/v1/demo/session"), {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok) {
      setAuthFeedback(normalizeMessage(payload.detail || payload.error || "Unable to load the demo workspace."));
      return;
    }
    await activateAuthenticatedApp(payload, {
      featuredMeetingId: payload.demo?.featuredMeetingId || payload.demo?.featured_meeting_id || "",
      preferredView: payload.demo?.preferredView || payload.demo?.preferred_view || "dashboard",
      guide: payload.demo?.guide || []
    });
  }, "Loading demo...");
}

async function activateAuthenticatedApp(payload, options = {}) {
  state.authToken = payload.token || "";
  localStorage.setItem("boardsight-token", state.authToken);
  state.currentUser = normalizeUser(payload);
  state.demoGuide = Array.isArray(options.guide) ? options.guide.filter(Boolean) : [];
  updateUserChip();
  updateNotificationsPanel();
  clearAuthFeedback();
  closeAuthModal();
  loginView.classList.add("hidden");
  appView.classList.remove("hidden");
  if (isLiveCopilotPopup) {
    activateLivePopupMode();
  }
  await loadMeetings();
  await loadActiveLiveSession();
  const featuredMeetingId = String(options.featuredMeetingId || "").trim();
  if (featuredMeetingId) {
    await loadMeetingDetail(featuredMeetingId);
  }
  if (!isLiveCopilotPopup) {
    setView(options.preferredView || "dashboard");
  }
}

function clearSession() {
  state.authToken = "";
  state.currentMeeting = null;
  state.currentMeetingId = null;
  state.workflowDraft = null;
  state.selectedWorkflowNodeId = null;
  state.liveSession = null;
  state.meetings = [];
  state.sessionHasProcessed = false;
  state.demoGuide = [];
  state.currentUser = DEFAULT_USER;
  localStorage.removeItem("boardsight-token");
  stopLiveListening();
  stopLiveScreenCapture();
  stopLivePolling();
  updateUserChip();
  updateNotificationsPanel();
  renderEmptyDashboard();
  renderMeetingList();
  renderMeetingDetail();
  renderLiveSession();
  renderCvFeaturePanel();
  renderTrace();
  renderWorkflow();
  loginView.classList.remove("hidden");
  closeAuthModal();
  appView.classList.add("hidden");
  syncFloatingLauncher();
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
  heroGreeting.textContent = `${timeOfDayGreeting()}, ${firstName} 👋`;
  document.querySelector(".hero p")?.replaceChildren("Here's what's happening in your workspace today.");
}

function updateNotificationsPanel() {
  if (!notificationsPanel) {
    return;
  }
  const heading = notificationsHeading || notificationsPanel.querySelector("strong");
  if (!heading) {
    return;
  }
  notificationsPanel.querySelectorAll(".notification-item").forEach((item) => item.remove());
  const items = state.demoGuide.length
    ? ["Demo workspace ready.", ...state.demoGuide]
    : [
        "Live Copilot is ready when a meeting session starts.",
        "Recorded meeting analysis will appear in Recent Meetings after upload."
      ];
  items.forEach((message) => {
    const item = document.createElement("div");
    item.className = "notification-item";
    item.textContent = message;
    notificationsPanel.appendChild(item);
  });
}

async function loadMeetings() {
  try {
    const response = await apiFetch("/api/v1/meetings");
    const payload = await response.json();
    state.meetings = payload.items || [];
    state.sessionHasProcessed = state.meetings.length > 0;
    updateDashboard();
    renderMeetingList();
    renderLiveSession();
    if (state.currentMeetingId) {
      await loadMeetingDetail(state.currentMeetingId);
    } else {
      renderMeetingDetail();
      renderGovernancePanel();
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
  const response = await apiFetch(`/api/v1/meetings/${encodeURIComponent(resolvedMeetingId)}`);
  state.currentMeeting = await response.json();
  state.currentMeetingId = resolvedMeetingId;
  state.workflowDraft = buildEditableWorkflowDraft(state.currentMeeting);
  state.selectedWorkflowNodeId = state.workflowDraft?.nodes?.[0]?.id || null;
  state.sessionHasProcessed = true;
  updateDashboard();
  renderMeetingDetail();
  renderGovernancePanel();
  renderCvFeaturePanel();
  renderTrace();
  renderWorkflow();
}

function normalizeWorkflowDraft(rawDraft, meetingId) {
  const draft = rawDraft && typeof rawDraft === "object" ? rawDraft : {};
  const nodes = Array.isArray(draft.nodes) ? draft.nodes : [];
  const links = Array.isArray(draft.links) ? draft.links : [];
  return {
    meetingId: String(draft.meetingId || meetingId || "workspace"),
    title: String(draft.title || `${prettifyMeetingId(meetingId)} Workflow Draft`),
    nodes: nodes.map((node, index) => ({
      id: String(node?.id || `node-${index + 1}`),
      type: String(node?.type || "review"),
      title: String(node?.title || ""),
      owner: String(node?.owner || ""),
      status: String(node?.status || ""),
      summary: String(node?.summary || ""),
      description: String(node?.description || node?.detailedDescription || ""),
      notes: String(node?.notes || ""),
      handoffNotes: String(node?.handoffNotes || ""),
      acceptanceCriteria: String(node?.acceptanceCriteria || ""),
      decisionId: String(node?.decisionId || ""),
      traceId: String(node?.traceId || ""),
      sourceStage: String(node?.sourceStage || ""),
      dueDate: String(node?.dueDate || ""),
      priority: String(node?.priority || "Medium"),
      x: Number.isFinite(Number(node?.x)) ? Number(node.x) : null,
      y: Number.isFinite(Number(node?.y)) ? Number(node.y) : null
    })),
    links: links.map((link) => ({
      from: String(link?.from || ""),
      to: String(link?.to || ""),
      label: String(link?.label || "next")
    })).filter((link) => link.from && link.to),
    meta: {
      derivedFrom: String(draft.meta?.derivedFrom || "BoardSight workflow editor"),
      status: String(draft.meta?.status || "draft"),
      overview: String(draft.meta?.overview || ""),
      notes: String(draft.meta?.notes || ""),
      savedAt: String(draft.meta?.savedAt || "")
    }
  };
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
  document.getElementById("kpiMeetingsMeta").textContent = `${Math.max(1, totalMeetings)} meeting${totalMeetings === 1 ? "" : "s"} in workspace`;
  document.getElementById("kpiDecisionsMeta").textContent = `${totalDecisions || 0} signal${totalDecisions === 1 ? "" : "s"} in active review`;
  document.getElementById("kpiAttentionMeta").textContent = `${capitalize(overallSentiment)} engagement pattern`;
  document.getElementById("kpiDominanceMeta").textContent = `${primarySpeaker?.speaker || "Speaker"} leading this session`;
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
  const workflowSnapshot = document.getElementById("workflowSnapshot");
  if (workflowSnapshot) {
    workflowSnapshot.innerHTML =
      prioritizedDecisions.length === 0 && workflowStages.length === 0
        ? `<div class="empty-state">Workflow stages will appear after decision modelling runs.</div>`
        : renderWorkflowSnapshot(prioritizedDecisions, workflowStages, state.currentMeeting.workflow_model?.execution_plan || []);
  }
}

function renderEmptyDashboard() {
  document.getElementById("kpiMeetings").textContent = "--";
  document.getElementById("kpiDecisions").textContent = "--";
  document.getElementById("kpiAttention").textContent = "--";
  document.getElementById("kpiDominance").textContent = "--";
  document.getElementById("kpiMeetingsMeta").textContent = "Workspace coverage";
  document.getElementById("kpiDecisionsMeta").textContent = "Tracked decision moments";
  document.getElementById("kpiAttentionMeta").textContent = "Attention across the active meeting";
  document.getElementById("kpiDominanceMeta").textContent = "Top speaker share";
  document.getElementById("donutValue").textContent = "--";
  donutChart.classList.add("is-empty");
  document.getElementById("speakerLegend").className = "legend-list empty-list";
  document.getElementById("speakerLegend").innerHTML = `<li class="empty-state">No speaker balance data yet.</li>`;
  document.getElementById("timelineChart").className = "line-chart empty-chart";
  document.getElementById("timelineChart").innerHTML = `<div class="empty-state">No decision timeline yet.</div>`;
  const workflowSnapshot = document.getElementById("workflowSnapshot");
  if (workflowSnapshot) {
    workflowSnapshot.innerHTML = `<div class="empty-state">Workflow stages will appear after decision modelling runs.</div>`;
  }
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
    const sentiment = capitalize(item.overallSentiment || "Neutral");
    const impact = formatMetric(item.impactScore || 0);
    node.innerHTML = `
      <div class="meeting-date"><span>${formatDate(item.createdAt || item.created_at).replace(" ", "<br>")}</span></div>
      <div class="meeting-meta">
        <strong>${item.title || `Meeting ${item.id}`}</strong>
        <div class="muted">${item.conclusion || "BoardSight analysis ready."}</div>
      </div>
      <div class="meeting-sentiment">
        <span>Sentiment</span>
        <strong>${sentiment}</strong>
      </div>
      <div class="meeting-impact">
        <span>Impact Score</span>
        <strong>${impact}</strong>
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
    `/api/v1/meetings/${encodeURIComponent(state.currentMeeting.storage?.meeting_id || state.currentMeetingId)}/reports/summary_card.png`,
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

function buildGovernanceModel(meeting) {
  if (!meeting) {
    return {
      decisions: [],
      actions: [],
      risks: [],
      traces: [],
      stats: []
    };
  }

  const decisionMoments = meeting.decision_moments || [];
  const prioritized = meeting.workflow_model?.prioritized_decisions || [];
  const executionPlan = meeting.workflow_model?.execution_plan || [];
  const bottlenecks = meeting.workflow_model?.bottlenecks || [];
  const traces = meeting.decision_traces || [];
  const riskSignals = meeting.metadata?.agentic_contract?.entities?.risk_signals || [];
  const priorityLookup = new Map(prioritized.map((item) => [String(item.decision_id || ""), item]));
  const traceLookup = new Map();
  traces.forEach((trace) => {
    (trace.execution_tasks || []).forEach((task) => {
      if (task?.decision_id) {
        traceLookup.set(String(task.decision_id), trace);
      }
    });
    if (trace?.trace_id?.startsWith?.("TRACE-")) {
      traceLookup.set(String(trace.trace_id).replace("TRACE-", "DM-"), trace);
    }
  });

  const decisions = decisionMoments.map((moment, index) => {
    const decisionId = String(moment.event_id || `DEC-${index + 1}`);
    const priority = priorityLookup.get(decisionId) || {};
    const relatedTasks = executionPlan.filter((task) => String(task.decision_id || "") === decisionId);
    const trace = traceLookup.get(decisionId) || traces.find((item) =>
      String(item.title || item.summary || "").toLowerCase().includes(String(moment.text || "").slice(0, 18).toLowerCase())
    );
    const blockers = bottlenecks.filter((item) =>
      String(item || "").toLowerCase().includes(String(moment.speaker || "").toLowerCase())
      || String(item || "").toLowerCase().includes(String(moment.text || "").split(" ").slice(0, 3).join(" ").toLowerCase())
    );
    const priorityScore = Number(priority.priority_score ?? moment.confidence ?? 0);
    const urgency = priorityScore >= 0.85 ? "High" : priorityScore >= 0.6 ? "Medium" : "Low";
    const status = blockers.length > 0
      ? "Blocked"
      : relatedTasks.length > 0
        ? "Ready"
        : "Captured";
    return {
      decisionId,
      title: shorten(trace?.title || moment.text || `Decision ${index + 1}`, 60),
      exactText: moment.text || "No decision text captured.",
      owner: trace?.owner || relatedTasks[0]?.owner || moment.speaker || "Unassigned",
      timestamp: moment.timestamp || "--",
      urgency,
      impact: urgency,
      status,
      nextAction: relatedTasks[0]?.title || trace?.next_steps?.[0] || "No follow-through recorded",
      blockers: blockers.length > 0 ? blockers.join(" | ") : "None",
      evidence: (moment.evidence || []).join(" | ") || "Transcript grounded",
      gitlab: relatedTasks[0]?.issue_web_url || relatedTasks[0]?.web_url || "Not synced"
    };
  });

  const actions = executionPlan.map((task, index) => {
    const notes = String(task.notes || task.text || "");
    const dueDate = inferDueDate(`${task.title || ""} ${notes}`);
    const blockerFlag = /\b(block|depend|waiting|pending)\b/i.test(notes) ? "Yes" : "No";
    const gitlabLink = task.issue_web_url || task.web_url || "";
    const owner = task.owner || "Unassigned";
    const status = blockerFlag === "Yes"
      ? "Blocked"
      : owner === "Unassigned"
        ? "Needs owner"
        : dueDate
          ? (gitlabLink ? "Synced" : "Ready")
          : "Needs due date";
    return {
      actionId: task.task_id || `ACTION-${index + 1}`,
      title: task.title || `Action ${index + 1}`,
      decisionId: task.decision_id || "",
      owner,
      dueDate: dueDate || "Not inferred",
      confidence: Number(task.priority_score || 0),
      dependencies: notes || "None",
      blockerFlag,
      gitlabSync: gitlabLink ? "Synced" : "Not synced",
      gitlabLink: gitlabLink || "Not synced",
      status
    };
  });

  const risks = [
    ...bottlenecks.map((item, index) => ({
      riskId: `BLOCKER-${index + 1}`,
      category: "Blocker",
      severity: "High",
      description: String(item || ""),
      followUp: "Resolve before closing linked execution item."
    })),
    ...riskSignals.map((item, index) => ({
      riskId: item.risk_id || `RISK-${index + 1}`,
      category: capitalize(String(item.kind || "risk").replace(/-/g, " ")),
      severity: "Medium",
      description: item.summary || item.kind || "Execution risk flagged.",
      followUp: "Review and assign follow-through."
    }))
  ];

  if (actions.some((item) => item.owner === "Unassigned")) {
    risks.push({
      riskId: "RISK-OWNER",
      category: "Missing owner",
      severity: "High",
      description: "One or more action items do not yet have a named owner.",
      followUp: "Assign an owner before the next checkpoint."
    });
  }
  if (actions.some((item) => item.dueDate === "Not inferred")) {
    risks.push({
      riskId: "RISK-DATE",
      category: "Missing deadline",
      severity: "Medium",
      description: "One or more action items are missing a clear due date.",
      followUp: "Add due dates to operationalize follow-through."
    });
  }

  const traceRows = traces.map((trace) => ({
    traceId: trace.trace_id || "TRACE",
    title: trace.title || "Trace",
    owner: trace.owner || "Unassigned",
    summary: trace.summary || "No summary available.",
    nextSteps: (trace.next_steps || []).join(" | ") || "No next steps recorded",
    artifacts: (trace.related_artifacts || []).join(", ") || "None",
    linkedDecision: findLinkedDecisionId(trace, decisions)
  }));

  const stats = [
    { label: "Decisions Captured", value: String(decisions.length), tone: "primary" },
    { label: "Execution Actions", value: String(actions.length), tone: "success" },
    { label: "Open Risks", value: String(risks.length), tone: "warning" },
    { label: "Trace Links", value: String(traceRows.length), tone: "accent" }
  ];

  return { decisions, actions, risks, traces: traceRows, stats };
}

function findLinkedDecisionId(trace, decisions) {
  const traceText = `${trace.title || ""} ${trace.summary || ""}`.toLowerCase();
  const match = decisions.find((item) => traceText.includes(String(item.decisionId || "").toLowerCase()));
  return match?.decisionId || "";
}

function inferDueDate(text) {
  const lowered = String(text || "").toLowerCase();
  const weekdays = {
    monday: 1,
    tuesday: 2,
    wednesday: 3,
    thursday: 4,
    friday: 5,
    saturday: 6,
    sunday: 0
  };
  const explicit = lowered.match(/\b(\d{4}-\d{2}-\d{2})\b/);
  if (explicit) {
    return explicit[1];
  }
  const now = new Date();
  for (const [day, value] of Object.entries(weekdays)) {
    if (lowered.includes(day)) {
      const copy = new Date(now);
      let delta = (value - copy.getDay() + 7) % 7;
      delta = delta === 0 ? 7 : delta;
      copy.setDate(copy.getDate() + delta);
      return copy.toISOString().slice(0, 10);
    }
  }
  return "";
}

function renderGovernancePanel() {
  const snapshot = document.getElementById("governanceSnapshot");
  const decisionRegister = document.getElementById("decisionRegister");
  const actionRegister = document.getElementById("actionRegister");
  const riskRegister = document.getElementById("riskRegister");
  const traceabilityRegister = document.getElementById("traceabilityRegister");
  const decisionCount = document.getElementById("decisionRegisterCount");
  const actionCount = document.getElementById("actionRegisterCount");
  const riskCount = document.getElementById("riskRegisterCount");
  const traceabilityCount = document.getElementById("traceabilityCount");
  if (!snapshot || !decisionRegister || !actionRegister || !riskRegister || !traceabilityRegister) {
    return;
  }

  if (!state.currentMeeting) {
    snapshot.innerHTML = `<div class="empty-state">Open a processed meeting to inspect the structured governance view.</div>`;
    decisionRegister.innerHTML = `<div class="empty-state">No decision register available.</div>`;
    actionRegister.innerHTML = `<div class="empty-state">No action register available.</div>`;
    riskRegister.innerHTML = `<div class="empty-state">No blockers or risks surfaced yet.</div>`;
    traceabilityRegister.innerHTML = `<div class="empty-state">No traceability links available yet.</div>`;
    decisionCount.textContent = "0 items";
    actionCount.textContent = "0 items";
    riskCount.textContent = "0 items";
    traceabilityCount.textContent = "0 links";
    return;
  }

  const model = buildGovernanceModel(state.currentMeeting);
  snapshot.innerHTML = model.stats.map((item) => `
    <article class="governance-stat ${item.tone}">
      <span>${item.label}</span>
      <strong>${escapeHtml(item.value)}</strong>
    </article>
  `).join("");

  decisionCount.textContent = `${model.decisions.length} item${model.decisions.length === 1 ? "" : "s"}`;
  actionCount.textContent = `${model.actions.length} item${model.actions.length === 1 ? "" : "s"}`;
  riskCount.textContent = `${model.risks.length} item${model.risks.length === 1 ? "" : "s"}`;
  traceabilityCount.textContent = `${model.traces.length} link${model.traces.length === 1 ? "" : "s"}`;

  decisionRegister.innerHTML = model.decisions.length === 0
    ? `<div class="empty-state">No decision register available.</div>`
    : renderGovernanceTable(
      ["Decision", "Owner", "Urgency", "Status", "Next Action"],
      model.decisions.map((item) => [
        `<div class="governance-cell-stack"><strong>${escapeHtml(item.decisionId)}</strong><span class="muted">${escapeHtml(item.title)}</span></div>`,
        escapeHtml(item.owner),
        `<span class="status-badge ${item.urgency.toLowerCase()}">${escapeHtml(item.urgency)}</span>`,
        `<span class="status-badge neutral">${escapeHtml(item.status)}</span>`,
        `<div class="governance-cell-stack"><span>${escapeHtml(item.nextAction)}</span><small class="muted">${escapeHtml(item.blockers)}</small></div>`
      ])
    );

  actionRegister.innerHTML = model.actions.length === 0
    ? `<div class="empty-state">No action register available.</div>`
    : renderGovernanceTable(
      ["Action", "Owner", "Due Date", "Status", "GitLab"],
      model.actions.map((item) => [
        `<div class="governance-cell-stack"><strong>${escapeHtml(item.actionId)}</strong><span class="muted">${escapeHtml(item.title)}</span></div>`,
        escapeHtml(item.owner),
        escapeHtml(item.dueDate),
        `<span class="status-badge neutral">${escapeHtml(item.status)}</span>`,
        `<div class="governance-cell-stack"><span>${escapeHtml(item.gitlabSync)}</span><small class="muted">${escapeHtml(item.decisionId || "No linked decision")}</small></div>`
      ])
    );

  riskRegister.innerHTML = model.risks.length === 0
    ? `<div class="empty-state">No blockers or risks surfaced yet.</div>`
    : model.risks.map((item) => `
      <article class="governance-note risk-${String(item.severity || "").toLowerCase()}">
        <div class="governance-note-head">
          <strong>${escapeHtml(item.riskId)}</strong>
          <span class="status-badge ${String(item.severity || "").toLowerCase()}">${escapeHtml(item.severity)}</span>
        </div>
        <div class="muted">${escapeHtml(item.category)}</div>
        <p>${escapeHtml(item.description)}</p>
        <small class="muted">Follow-up: ${escapeHtml(item.followUp)}</small>
      </article>
    `).join("");

  traceabilityRegister.innerHTML = model.traces.length === 0
    ? `<div class="empty-state">No traceability links available yet.</div>`
    : model.traces.map((item) => `
      <article class="governance-note">
        <div class="governance-note-head">
          <strong>${escapeHtml(item.traceId)}</strong>
          <span class="model-pill subtle">${escapeHtml(item.linkedDecision || "Unlinked trace")}</span>
        </div>
        <p>${escapeHtml(item.title)}</p>
        <small class="muted">Owner: ${escapeHtml(item.owner)} | Next steps: ${escapeHtml(item.nextSteps)}</small>
      </article>
    `).join("");
}

function renderGovernanceTable(headers, rows) {
  return `
    <div class="governance-table">
      <div class="governance-table-row governance-table-head">
        ${headers.map((header) => `<span>${escapeHtml(header)}</span>`).join("")}
      </div>
      ${rows.map((row) => `
        <div class="governance-table-row">
          ${row.map((cell) => `<div class="governance-table-cell">${cell}</div>`).join("")}
        </div>
      `).join("")}
    </div>
  `;
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
  const chartWindows = sumCounts(artifactCounts, ["chart", "charts", "graph", "graphs", "dashboard"]);
  const documentWindows = sumCounts(artifactCounts, ["document", "documents", "slide", "slides", "presentation-slide"]);
  const peopleVisibleWindows = visualArtifacts.filter((artifact) => Number(artifact.visible_people_count || 0) > 0).length;
  const detectionTotal = visualArtifacts.reduce((sum, artifact) => sum + ((artifact.detections || []).length), 0);
  const hybridWindows = sumCounts(displayCounts, ["hybrid", "mixed"]);
  const ocrCoverage = sampleCount > 0 ? Math.round((contentArtifacts.length / sampleCount) * 100) : 0;
  const strongestArtifact = Object.entries(artifactCounts).sort((left, right) => right[1] - left[1])[0];
  const strongestDisplayMode = Object.entries(displayCounts).sort((left, right) => right[1] - left[1])[0];
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
          <span>Live meeting stats</span>
        </div>
        <div class="cv-note-list">
          <div>
            <strong>Primary display mode</strong>
            <p class="muted">${strongestDisplayMode ? `${strongestDisplayMode[0]} led ${strongestDisplayMode[1]} of ${sampleCount} sampled windows.` : "No display-mode classification was returned for this meeting."}</p>
          </div>
          <div>
            <strong>Primary artifact family</strong>
            <p class="muted">${strongestArtifact ? `${strongestArtifact[0]} was the most common artifact label across ${strongestArtifact[1]} windows.` : "No artifact-type classification was returned for this meeting."}</p>
          </div>
          <div>
            <strong>Readable presentation content</strong>
            <p class="muted">${contentArtifacts.length} of ${sampleCount} windows exposed readable slide or screen text (${ocrCoverage}% OCR coverage).</p>
          </div>
          <div>
            <strong>Charts, docs, and speaker presence</strong>
            <p class="muted">${chartWindows} chart/dashboard windows, ${documentWindows} document/slide windows, and ${peopleVisibleWindows} windows with visible people. ${hybridWindows} windows were mixed or hybrid views.</p>
          </div>
          <div>
            <strong>Detection yield</strong>
            <p class="muted">${detectionTotal} object detections across ${sampleCount} sampled windows. ${classifierSummary}</p>
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
            <p class="muted">${audioSpeakerWindows.length} timeline segments came from audio-dominance speaker activity, covering ${transcriptSegments.length > 0 ? Math.round((audioSpeakerWindows.length / transcriptSegments.length) * 100) : 0}% of transcript windows.</p>
          </div>
          <div>
            <strong>Visual speaker windows</strong>
            <p class="muted">${visualSpeakerWindows.length} windows came from visual active-speaker enrichment. ${visualSpeakerWindows.length > 0 ? "Visual speaker evidence was available." : "Speaker tracking relied entirely on audio cues here."}</p>
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
  const workflowCanvas = document.getElementById("workflowCanvas");
  const workflowProperties = document.getElementById("workflowProperties");
  if (!workflowCanvas || !workflowProperties) {
    return;
  }

  if (!state.currentMeeting) {
    workflowCanvas.innerHTML = `<div class="empty-state">No workflow model available yet.</div>`;
    workflowProperties.innerHTML = `<div class="empty-state">Process a meeting to inspect workflow properties.</div>`;
    return;
  }

  state.workflowDraft = state.workflowDraft || buildEditableWorkflowDraft(state.currentMeeting);
  const draft = state.workflowDraft;
  ensureWorkflowNodeLayout(draft);
  const selectedNode = draft.nodes.find((node) => node.id === state.selectedWorkflowNodeId) || draft.nodes[0] || null;
  state.selectedWorkflowNodeId = selectedNode?.id || null;

  if (!draft.nodes.length) {
    workflowCanvas.innerHTML = `<div class="empty-state">No workflow model available yet.</div>`;
    workflowProperties.innerHTML = `<div class="empty-state">Use New Workflow to start from a clean flow.</div>`;
    return;
  }

  workflowCanvas.innerHTML = `
    <div class="workflow-toolbar">
      <div class="workflow-toolbar-copy">
        <strong>${escapeHtml(draft.title || "Workflow draft")}</strong>
        <span class="muted">${draft.nodes.length} nodes | ${draft.links.length} links | ${draft.meta.derivedFrom}</span>
      </div>
      <div class="workflow-toolbar-copy">
        <span class="model-pill subtle">${escapeHtml(draft.meta.status || "draft")}</span>
      </div>
    </div>
    <div class="workflow-board workflow-board-visual">
      <div class="workflow-map-shell">
        <svg class="workflow-link-layer" viewBox="0 0 1000 ${workflowCanvasHeight(draft)}" preserveAspectRatio="none">
          ${draft.links.map((link) => renderWorkflowLink(link, draft)).join("")}
        </svg>
        <div class="workflow-map" style="height:${workflowCanvasHeight(draft)}px;">
          ${draft.nodes.map((node, index) => renderWorkflowNodeCard(node, index)).join("")}
        </div>
      </div>
    </div>
  `;

  workflowCanvas.querySelectorAll("[data-workflow-node-id]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.dragMoved === "true") {
        button.dataset.dragMoved = "false";
        return;
      }
      state.selectedWorkflowNodeId = button.dataset.workflowNodeId;
      renderWorkflow();
    });
  });
  bindWorkflowCanvasInteractions(workflowCanvas, draft);

  workflowProperties.innerHTML = selectedNode
    ? renderWorkflowPropertiesPanel(selectedNode, draft)
    : `<div class="empty-state">Select a node to edit its workflow properties.</div>`;

  bindWorkflowPropertyInputs();
}

function workflowCanvasHeight(draft) {
  const maxY = draft.nodes.reduce((highest, node) => Math.max(highest, Number(node.y || 0)), 0);
  return Math.max(560, maxY + 220);
}

function defaultWorkflowPosition(node, index) {
  const laneByType = {
    start: 420,
    review: 120,
    decision: 380,
    approval: 640,
    parallel: 640,
    escalation: 180,
    end: 420
  };
  return {
    x: laneByType[node.type] ?? 360,
    y: 36 + (index * 146)
  };
}

function ensureWorkflowNodeLayout(draft) {
  if (!draft?.nodes?.length) {
    return;
  }
  const lanes = new Map();
  draft.nodes.forEach((node, index) => {
    if (Number.isFinite(node.x) && Number.isFinite(node.y)) {
      return;
    }
    const laneIndex = lanes.get(node.type) || 0;
    const basePosition = defaultWorkflowPosition(node, index);
    node.x = Number.isFinite(node.x) ? node.x : basePosition.x + (laneIndex % 2 === 0 ? 0 : 24);
    node.y = Number.isFinite(node.y) ? node.y : basePosition.y + (laneIndex * 12);
    lanes.set(node.type, laneIndex + 1);
  });
}

function workflowNodeRect(node) {
  return {
    x: Number(node.x || 0),
    y: Number(node.y || 0),
    width: 248,
    height: 172
  };
}

function workflowNodeCenter(node) {
  const rect = workflowNodeRect(node);
  return {
    x: rect.x + (rect.width / 2),
    y: rect.y + (rect.height / 2)
  };
}

function renderWorkflowNodeCard(node, index) {
  const trace = findTraceForWorkflowNode(node, state.currentMeeting);
  const detailBits = [node.decisionId || "", trace?.trace_id || "", node.dueDate ? `Due ${node.dueDate}` : ""].filter(Boolean);
  const rect = workflowNodeRect(node);
  return `
    <button
      type="button"
      class="workflow-card workflow-card-floating ${node.id === state.selectedWorkflowNodeId ? "is-selected" : ""} type-${escapeHtml(node.type)}"
      data-workflow-node-id="${escapeHtml(node.id)}"
      style="left:${rect.x}px;top:${rect.y}px;"
    >
      <span class="workflow-card-step">${String(index + 1).padStart(2, "0")}</span>
      <strong>${escapeHtml(node.title)}</strong>
      <div class="workflow-card-meta">
        <span>${escapeHtml(capitalize(node.type))}</span>
        <span>${escapeHtml(node.owner || "Unassigned")}</span>
      </div>
      <p>${escapeHtml(node.summary || "No summary recorded.")}</p>
      ${node.description ? `<p class="workflow-card-detail">${escapeHtml(shorten(node.description, 140))}</p>` : ""}
      ${detailBits.length ? `<div class="workflow-card-tags">${detailBits.map((item) => `<span class="workflow-tag">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
      <div class="workflow-card-footer">
        <span class="status-badge neutral">${escapeHtml(node.status || "Draft")}</span>
        <small>${escapeHtml(node.decisionId || node.sourceStage || "Manual node")}</small>
      </div>
      <span class="workflow-card-grab">Drag to map</span>
    </button>
  `;
}

function renderWorkflowLink(link, draft) {
  const fromNode = draft.nodes.find((node) => node.id === link.from);
  const toNode = draft.nodes.find((node) => node.id === link.to);
  if (!fromNode || !toNode) {
    return "";
  }
  const start = workflowNodeCenter(fromNode);
  const end = workflowNodeCenter(toNode);
  const deltaX = Math.max(80, Math.abs(end.x - start.x) * 0.5);
  const path = `M ${start.x} ${start.y} C ${start.x + deltaX} ${start.y}, ${end.x - deltaX} ${end.y}, ${end.x} ${end.y}`;
  const labelX = (start.x + end.x) / 2;
  const labelY = (start.y + end.y) / 2 - 12;
  return `
    <path class="workflow-link-path" d="${path}" />
    <text class="workflow-link-label" x="${labelX}" y="${labelY}" text-anchor="middle">${escapeHtml(link.label || "next")}</text>
  `;
}

function bindWorkflowCanvasInteractions(workflowCanvas, draft) {
  workflowCanvas.querySelectorAll("[data-workflow-node-id]").forEach((button) => {
    button.addEventListener("pointerdown", (event) => {
      const nodeId = button.dataset.workflowNodeId;
      const node = draft.nodes.find((item) => item.id === nodeId);
      if (!node) {
        return;
      }
      button.dataset.dragMoved = "false";
      button.setPointerCapture(event.pointerId);
      state.workflowDrag = {
        nodeId,
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        originX: Number(node.x || 0),
        originY: Number(node.y || 0)
      };
    });
    button.addEventListener("pointermove", (event) => {
      if (!state.workflowDrag || state.workflowDrag.pointerId !== event.pointerId || state.workflowDrag.nodeId !== button.dataset.workflowNodeId) {
        return;
      }
      const node = draft.nodes.find((item) => item.id === state.workflowDrag.nodeId);
      if (!node) {
        return;
      }
      const deltaX = event.clientX - state.workflowDrag.startX;
      const deltaY = event.clientY - state.workflowDrag.startY;
      if (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3) {
        button.dataset.dragMoved = "true";
      }
      node.x = Math.max(24, Math.min(728, Math.round(state.workflowDrag.originX + deltaX)));
      node.y = Math.max(24, Math.round(state.workflowDrag.originY + deltaY));
      button.style.left = `${node.x}px`;
      button.style.top = `${node.y}px`;
      const layer = workflowCanvas.querySelector(".workflow-link-layer");
      if (layer) {
        layer.setAttribute("viewBox", `0 0 1000 ${workflowCanvasHeight(draft)}`);
        layer.innerHTML = draft.links.map((link) => renderWorkflowLink(link, draft)).join("");
      }
      const map = workflowCanvas.querySelector(".workflow-map");
      if (map) {
        map.style.height = `${workflowCanvasHeight(draft)}px`;
      }
    });
    button.addEventListener("pointerup", (event) => {
      if (state.workflowDrag?.pointerId === event.pointerId) {
        state.selectedWorkflowNodeId = button.dataset.workflowNodeId;
        state.workflowDrag = null;
        renderWorkflow();
      }
    });
    button.addEventListener("pointercancel", () => {
      state.workflowDrag = null;
    });
  });
}

function workflowStorageKey(meetingId) {
  return `boardsight-workflow-draft:${meetingId || "workspace"}`;
}

function buildTraceLookup(meeting) {
  const traces = meeting?.decision_traces || [];
  const lookup = new Map();
  traces.forEach((trace) => {
    if (trace?.trace_id) {
      lookup.set(String(trace.trace_id), trace);
      if (String(trace.trace_id).startsWith("TRACE-")) {
        lookup.set(String(trace.trace_id).replace("TRACE-", "DM-"), trace);
      }
    }
    (trace.execution_tasks || []).forEach((task) => {
      if (task?.decision_id) {
        lookup.set(String(task.decision_id), trace);
      }
    });
  });
  return lookup;
}

function findTraceForWorkflowNode(node, meeting) {
  if (!node || !meeting) {
    return null;
  }
  const traces = meeting.decision_traces || [];
  const lookup = buildTraceLookup(meeting);
  if (node.traceId && lookup.has(String(node.traceId))) {
    return lookup.get(String(node.traceId));
  }
  if (node.decisionId && lookup.has(String(node.decisionId))) {
    return lookup.get(String(node.decisionId));
  }
  const comparison = `${node.title || ""} ${node.summary || ""} ${node.description || ""}`.toLowerCase();
  return traces.find((trace) => {
    const traceText = `${trace.trace_id || ""} ${trace.title || ""} ${trace.summary || ""}`.toLowerCase();
    return comparison && (traceText.includes(comparison.slice(0, 32)) || comparison.includes(traceText.slice(0, 32)));
  }) || null;
}

function buildEditableWorkflowDraft(meeting, { forceReset = false } = {}) {
  const meetingId = meeting?.storage?.meeting_id || state.currentMeetingId || "workspace";
  if (!forceReset) {
    const remoteDraft = meeting?.workflow_editor;
    if (remoteDraft?.nodes?.length) {
      return normalizeWorkflowDraft(remoteDraft, meetingId);
    }
    const saved = localStorage.getItem(workflowStorageKey(meetingId));
    if (saved) {
      try {
        return normalizeWorkflowDraft(JSON.parse(saved), meetingId);
      } catch (error) {
      }
    }
  }

  const workflowModel = meeting?.workflow_model || {};
  const prioritized = workflowModel.prioritized_decisions || [];
  const tasks = workflowModel.execution_plan || [];
  const stages = workflowModel.stages || [];
  const bottlenecks = workflowModel.bottlenecks || [];
  const decisions = meeting?.decision_moments || [];
  const traceLookup = buildTraceLookup(meeting);

  const generatedNodes = [];
  generatedNodes.push({
    id: "node-start",
    type: "start",
    title: "Meeting Intake",
    owner: meeting?.metadata?.source_mode === "live" ? "Live session" : "Recorded upload",
    status: "Ready",
    summary: "BoardSight ingests transcript, speaker, and visual context before workflow routing.",
    description: "This entry step captures the incoming meeting context, analysis mode, and source signals before the workflow is modeled.",
    notes: buildMeetingSubtitle(meeting),
    handoffNotes: "Confirm the right meeting, source mode, and transcript coverage before downstream editing.",
    acceptanceCriteria: "Meeting is loaded and core transcript, decision, and artifact signals are available.",
    decisionId: "",
    sourceStage: "start",
    dueDate: "",
    priority: "High"
  });

  if (stages.length > 0) {
    stages.slice(0, 3).forEach((stage, index) => {
      generatedNodes.push({
        id: `node-stage-${index + 1}`,
        type: "review",
        title: capitalize(stage.stage || stage.name || `Stage ${index + 1}`),
        owner: stage.speaker || tasks[index]?.owner || "Meeting owner",
        status: "Observed",
        summary: stage.summary || "Workflow stage inferred from the meeting timeline.",
        description: `BoardSight inferred this stage from discussion flow and execution signals around ${stage.stage || stage.name || `Stage ${index + 1}`}.`,
        notes: `Confidence ${formatMetric(stage.confidence || 0)} | Source ${stage.source || "workflow inference"}`,
        handoffNotes: "Validate whether this inferred stage reflects the real operating process.",
        acceptanceCriteria: "Stage label, owner, and downstream consequence are specific enough to act on.",
        decisionId: "",
        sourceStage: stage.stage || stage.name || "",
        dueDate: "",
        priority: "Medium"
      });
    });
  }

  prioritized.forEach((decision, index) => {
    const linkedTask = tasks.find((task) => String(task.decision_id || "") === String(decision.decision_id || ""));
    const linkedMoment = decisions.find((moment) => String(moment.event_id || "") === String(decision.decision_id || ""));
    const linkedTrace = traceLookup.get(String(decision.decision_id || ""));
    generatedNodes.push({
      id: `node-decision-${index + 1}`,
      type: index === 0 ? "decision" : "approval",
      title: linkedTask?.title || linkedMoment?.text || decision.decision_id || `Decision ${index + 1}`,
      owner: linkedTask?.owner || decision.speaker || linkedMoment?.speaker || "Unassigned",
      status: bottlenecks.length > 0 && index === 0 ? "Blocked" : "Ready",
      summary: linkedMoment?.text || decision.text || "Decision captured from the meeting.",
      description: linkedTrace?.summary || "This node represents a concrete decision or approval checkpoint that should drive downstream execution ownership.",
      notes: `Priority ${formatMetric(decision.priority_score || 0)} | ${renderWorkflowReasoning(decision.reasoning || [])}`,
      handoffNotes: linkedTrace?.next_steps?.join(" | ") || "Ensure the exact decision text, owner, and urgency are explicit before finalizing.",
      acceptanceCriteria: linkedTrace?.rationale?.join(" | ") || "Decision is unambiguous, traceable to meeting evidence, and linked to next action.",
      decisionId: decision.decision_id || "",
      traceId: linkedTrace?.trace_id || "",
      sourceStage: "decision",
      dueDate: inferDueDate(`${linkedTask?.title || ""} ${linkedTask?.notes || ""}`),
      priority: Number(decision.priority_score || 0) >= 80 ? "High" : "Medium"
    });
    if (linkedTask) {
      generatedNodes.push({
        id: `node-action-${index + 1}`,
        type: "parallel",
        title: linkedTask.title || `Execution task ${index + 1}`,
        owner: linkedTask.owner || "Unassigned",
        status: /\b(block|depend|waiting|pending)\b/i.test(String(linkedTask.notes || "")) ? "Blocked" : "Planned",
        summary: linkedTask.notes || "Execution task derived from the workflow model.",
        description: "This node converts the captured decision into an operational follow-through step with an owner and sequencing.",
        notes: `Task type ${linkedTask.task_type || "workflow"} | Order ${linkedTask.execution_order || index + 1}`,
        handoffNotes: linkedTrace?.next_steps?.join(" | ") || "Clarify dependencies, timing, and external tooling before handing off execution.",
        acceptanceCriteria: linkedTrace?.rationale?.join(" | ") || "Task has an owner, expected outcome, and enough detail for direct follow-through.",
        decisionId: linkedTask.decision_id || "",
        traceId: linkedTrace?.trace_id || "",
        sourceStage: "execution",
        dueDate: inferDueDate(`${linkedTask.title || ""} ${linkedTask.notes || ""}`),
        priority: Number(linkedTask.priority_score || 0) >= 80 ? "High" : "Medium"
      });
    }
  });

  if (bottlenecks.length > 0) {
    generatedNodes.push({
      id: "node-escalation",
      type: "escalation",
      title: "Escalate blocker resolution",
      owner: "PMO / Governance lead",
      status: "Attention needed",
      summary: bottlenecks.join(" | "),
      description: "BoardSight identified workflow blockers that can stall execution or leave responsibility unresolved.",
      notes: "Workflow bottlenecks were detected and should be resolved before closure.",
      handoffNotes: "Escalate unresolved blockers, ownership gaps, and missing deadlines to the right approver.",
      acceptanceCriteria: "Every blocker has a named resolver, next checkpoint, or explicit close decision.",
      decisionId: "",
      sourceStage: "escalation",
      dueDate: "",
      priority: "High"
    });
  }

  generatedNodes.push({
    id: "node-end",
    type: "end",
    title: "Close and monitor follow-through",
    owner: "BoardSight",
    status: "Pending",
    summary: "Finalize the meeting workflow after owners, blockers, and next steps are validated.",
    description: "This closing node confirms that the workflow is reviewable, assigned, and ready for follow-through after the meeting.",
    notes: "Use Save to persist this draft in the workspace browser.",
    handoffNotes: "Share the finalized workflow with the operating team and update any linked systems.",
    acceptanceCriteria: "Owners, notes, blockers, and next actions are complete enough to export or operationalize.",
    decisionId: "",
    sourceStage: "end",
    dueDate: "",
    priority: "Medium"
  });

  const dedupedNodes = generatedNodes.filter((node, index, items) =>
    index === items.findIndex((candidate) => candidate.title === node.title && candidate.type === node.type)
  );
  const links = dedupedNodes.slice(0, -1).map((node, index) => ({
    from: node.id,
    to: dedupedNodes[index + 1].id,
    label: index === 0 ? "ingest" : "next"
  }));

  return {
    meetingId: String(meetingId),
    title: `${prettifyMeetingId(meetingId)} Workflow Draft`,
    nodes: dedupedNodes,
    links,
    meta: {
      derivedFrom: workflowModel?.workflow_summary?.source || "BoardSight workflow draft",
      status: workflowModel?.workflow_summary?.status || (dedupedNodes.length > 2 ? "generated" : "draft"),
      overview: workflowModel?.workflow_summary?.top_priority_decision
        ? `Top workflow signal: ${workflowModel.workflow_summary.top_priority_decision}`
        : "",
      notes: bottlenecks.slice(0, 3).join(" | ")
    }
  };
}

function renderWorkflowReasoning(reasoning) {
  const items = Array.isArray(reasoning) ? reasoning : [];
  return items.length ? shorten(items.join(" | "), 90) : "No detailed reasoning recorded";
}

function renderWorkflowPropertiesPanel(node, draft) {
  const linkedCount = draft.links.filter((link) => link.from === node.id || link.to === node.id).length;
  const trace = findTraceForWorkflowNode(node, state.currentMeeting);
  return `
    <div class="workflow-property-form">
      <label>Workflow Overview
        <textarea rows="3" data-workflow-meta-field="overview">${escapeHtml(draft.meta?.overview || "")}</textarea>
      </label>
      <label>Workflow Notes
        <textarea rows="4" data-workflow-meta-field="notes">${escapeHtml(draft.meta?.notes || "")}</textarea>
      </label>
      <div class="speaker-row"><span>Node Type</span><strong>${escapeHtml(capitalize(node.type))}</strong></div>
      <div class="speaker-row"><span>Linked edges</span><strong>${linkedCount}</strong></div>
      <label>Title
        <input type="text" data-workflow-field="title" value="${escapeAttribute(node.title)}">
      </label>
      <label>Owner
        <input type="text" data-workflow-field="owner" value="${escapeAttribute(node.owner || "")}">
      </label>
      <label>Status
        <input type="text" data-workflow-field="status" value="${escapeAttribute(node.status || "")}">
      </label>
      <label>Due Date
        <input type="text" data-workflow-field="dueDate" value="${escapeAttribute(node.dueDate || "")}" placeholder="YYYY-MM-DD or Friday">
      </label>
      <label>Priority
        <select data-workflow-field="priority">
          ${["High", "Medium", "Low"].map((option) => `<option value="${option}" ${node.priority === option ? "selected" : ""}>${option}</option>`).join("")}
        </select>
      </label>
      <label>Summary
        <textarea rows="4" data-workflow-field="summary">${escapeHtml(node.summary || "")}</textarea>
      </label>
      <label>Detailed Description
        <textarea rows="6" data-workflow-field="description">${escapeHtml(node.description || "")}</textarea>
      </label>
      <label>Notes
        <textarea rows="5" data-workflow-field="notes">${escapeHtml(node.notes || "")}</textarea>
      </label>
      <label>Handoff Notes
        <textarea rows="4" data-workflow-field="handoffNotes">${escapeHtml(node.handoffNotes || "")}</textarea>
      </label>
      <label>Acceptance Criteria
        <textarea rows="4" data-workflow-field="acceptanceCriteria">${escapeHtml(node.acceptanceCriteria || "")}</textarea>
      </label>
      <div class="workflow-context-card">
        <strong>Trace Context</strong>
        <div class="speaker-row"><span>Linked Decision</span><strong>${escapeHtml(node.decisionId || "None")}</strong></div>
        <div class="speaker-row"><span>Linked Trace</span><strong>${escapeHtml(trace?.trace_id || node.traceId || "None")}</strong></div>
        <div class="speaker-row"><span>Next Step Signal</span><strong>${escapeHtml(trace?.next_steps?.[0] || "None recorded")}</strong></div>
        <p class="muted">${escapeHtml(trace?.summary || "No decision trace context is linked to this node yet.")}</p>
      </div>
      <div class="button-row">
        <button type="button" class="ghost-btn" id="workflowDuplicateBtn">Duplicate</button>
        <button type="button" class="ghost-btn" id="workflowDeleteBtn">Delete</button>
      </div>
      <div class="upload-status" id="workflowStatus">Save writes this workflow to BoardSight so it stays available across devices and sessions.</div>
    </div>
  `;
}

function bindWorkflowPropertyInputs() {
  const workflowProperties = document.getElementById("workflowProperties");
  if (!workflowProperties) {
    return;
  }
  workflowProperties.querySelectorAll("[data-workflow-field]").forEach((input) => {
    input.addEventListener("input", () => {
      updateWorkflowNodeField(input.dataset.workflowField, input.value);
    });
  });
  workflowProperties.querySelectorAll("[data-workflow-meta-field]").forEach((input) => {
    input.addEventListener("input", () => {
      updateWorkflowMetaField(input.dataset.workflowMetaField, input.value);
    });
  });
  document.getElementById("workflowDuplicateBtn")?.addEventListener("click", duplicateWorkflowNode);
  document.getElementById("workflowDeleteBtn")?.addEventListener("click", deleteWorkflowNode);
}

function updateWorkflowNodeField(field, value) {
  if (!state.workflowDraft || !state.selectedWorkflowNodeId) {
    return;
  }
  const node = state.workflowDraft.nodes.find((item) => item.id === state.selectedWorkflowNodeId);
  if (!node) {
    return;
  }
  node[field] = value;
  renderWorkflow();
}

function updateWorkflowMetaField(field, value) {
  if (!state.workflowDraft) {
    return;
  }
  state.workflowDraft.meta = state.workflowDraft.meta || {};
  state.workflowDraft.meta[field] = value;
  renderWorkflow();
}

function addWorkflowNode(type) {
  if (!state.currentMeeting) {
    return;
  }
  state.workflowDraft = state.workflowDraft || buildEditableWorkflowDraft(state.currentMeeting);
  const newId = `node-${type}-${Date.now()}`;
  const newNode = {
    id: newId,
    type,
    title: `${capitalize(type)} step`,
    owner: "Unassigned",
    status: "Draft",
    summary: "Describe what should happen at this workflow step.",
    description: "Capture the full routing context, approvals, deliverables, and decision logic for this step.",
    notes: "Add detailed routing, approval, or execution guidance here.",
    handoffNotes: "",
    acceptanceCriteria: "",
    decisionId: "",
    traceId: "",
    sourceStage: "manual",
    dueDate: "",
    priority: "Medium",
    x: 360,
    y: Math.max(48, ...state.workflowDraft.nodes.map((node) => Number(node.y || 0) + 146))
  };
  const endIndex = state.workflowDraft.nodes.findIndex((node) => node.type === "end");
  const insertAt = endIndex >= 0 ? endIndex : state.workflowDraft.nodes.length;
  state.workflowDraft.nodes.splice(insertAt, 0, newNode);
  rebuildWorkflowLinks();
  state.selectedWorkflowNodeId = newId;
  renderWorkflow();
}

function duplicateWorkflowNode() {
  if (!state.workflowDraft || !state.selectedWorkflowNodeId) {
    return;
  }
  const index = state.workflowDraft.nodes.findIndex((node) => node.id === state.selectedWorkflowNodeId);
  if (index < 0) {
    return;
  }
  const source = state.workflowDraft.nodes[index];
  const clone = {
    ...source,
    id: `${source.id}-copy-${Date.now()}`,
    title: `${source.title} Copy`,
    x: Number(source.x || 0) + 36,
    y: Number(source.y || 0) + 36
  };
  state.workflowDraft.nodes.splice(index + 1, 0, clone);
  rebuildWorkflowLinks();
  state.selectedWorkflowNodeId = clone.id;
  renderWorkflow();
}

function deleteWorkflowNode() {
  if (!state.workflowDraft || !state.selectedWorkflowNodeId) {
    return;
  }
  const node = state.workflowDraft.nodes.find((item) => item.id === state.selectedWorkflowNodeId);
  if (!node || node.type === "start" || node.type === "end") {
    return;
  }
  state.workflowDraft.nodes = state.workflowDraft.nodes.filter((item) => item.id !== state.selectedWorkflowNodeId);
  rebuildWorkflowLinks();
  state.selectedWorkflowNodeId = state.workflowDraft.nodes[0]?.id || null;
  renderWorkflow();
}

function rebuildWorkflowLinks() {
  if (!state.workflowDraft) {
    return;
  }
  state.workflowDraft.links = state.workflowDraft.nodes.slice(0, -1).map((node, index) => ({
    from: node.id,
    to: state.workflowDraft.nodes[index + 1].id,
    label: "next"
  }));
}

async function saveWorkflowDraft() {
  if (!state.workflowDraft) {
    return;
  }
  const key = workflowStorageKey(state.workflowDraft.meetingId || state.currentMeetingId);
  state.workflowDraft.meta = {
    ...state.workflowDraft.meta,
    status: "saving",
    savedAt: new Date().toISOString()
  };
  localStorage.setItem(key, JSON.stringify(state.workflowDraft));
  const workflowStatus = document.getElementById("workflowStatus");
  if (workflowStatus) {
    workflowStatus.textContent = "Saving workflow to BoardSight...";
  }
  renderWorkflow();
  try {
    const response = await apiFetch(`/api/v1/meetings/${encodeURIComponent(state.currentMeeting.storage?.meeting_id || state.currentMeetingId)}/workflow`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workflow_editor: state.workflowDraft })
    });
    if (!response.ok) {
      throw new Error("Workflow save failed.");
    }
    const payload = await response.json();
    state.currentMeeting = payload.meeting || state.currentMeeting;
    state.workflowDraft = normalizeWorkflowDraft(payload.workflow_editor || state.workflowDraft, state.currentMeetingId);
    state.selectedWorkflowNodeId = state.workflowDraft.nodes.find((node) => node.id === state.selectedWorkflowNodeId)?.id || state.workflowDraft.nodes[0]?.id || null;
    localStorage.setItem(key, JSON.stringify(state.workflowDraft));
    renderWorkflow();
    const refreshedStatus = document.getElementById("workflowStatus");
    if (refreshedStatus) {
      refreshedStatus.textContent = "Workflow saved to BoardSight and synced for future sessions.";
    }
  } catch (error) {
    console.error(error);
    state.workflowDraft.meta.status = "saved-local";
    localStorage.setItem(key, JSON.stringify(state.workflowDraft));
    renderWorkflow();
    const failureStatus = document.getElementById("workflowStatus");
    if (failureStatus) {
      failureStatus.textContent = "BoardSight save failed, so this draft is only stored in this browser right now.";
    }
  }
}

async function loadActiveLiveSession() {
  try {
    const response = await apiFetch("/api/v1/live/active");
    if (!response.ok) {
      renderLiveSession();
      return;
    }
    const payload = await response.json();
    state.liveSession = payload?.session ? payload : null;
    renderLiveSession();
    if (state.liveSession?.session?.status === "active") {
      ensureLivePolling();
    } else {
      stopLivePolling();
    }
  } catch (error) {
    if (error?.status !== 401) {
      renderLiveSession();
    }
  }
}

async function refreshLiveSession() {
  if (!state.liveSession?.session?.id) {
    await loadActiveLiveSession();
    return;
  }
  try {
    const response = await apiFetch(`/api/v1/live/${encodeURIComponent(state.liveSession.session.id)}`);
    if (!response.ok) {
      return;
    }
    state.liveSession = await response.json();
    renderLiveSession();
  } catch (error) {
    if (error?.status !== 401) {
      setLiveStatus("Unable to refresh the live session right now.");
    }
  }
}

function renderLiveSession() {
  if (!liveTranscriptList || !liveQuickSummary || !liveCopilotAnswer) {
    return;
  }

  const livePayload = state.liveSession;
  if (!livePayload?.session) {
    liveTranscriptList.innerHTML = `<div class="empty-state">Start a live session and add updates to see the running transcript.</div>`;
    liveQuickSummary.innerHTML = `<span>Session Summary</span><strong>Awaiting transcript</strong>`;
    liveCopilotMeta.textContent = "Copilot is ready when a live session is active.";
    liveCopilotAnswer.innerHTML = `<div class="empty-state">BoardSight will answer from the live transcript accumulated so far.</div>`;
    setLiveStatus("No live session started.");
    syncFloatingLauncher();
    return;
  }

  const transcriptSegments = livePayload.transcript?.segments || [];
  const liveVisualCues = livePayload.live_visual_cues || [];
  liveTranscriptList.innerHTML = transcriptSegments.length === 0
    ? `<div class="empty-state">Listening is active, but no transcript chunks have been stored yet.</div>`
    : transcriptSegments.slice(-20).map((segment) => `
      <div class="transcript-row">
        <strong>${segment.timestamp}</strong>
        <span>${escapeHtml(segment.speaker)}</span>
        <span>${escapeHtml(segment.text)}</span>
      </div>
    `).join("");

  const summary = String(livePayload.copilot_context?.summary || "").trim();
  liveQuickSummary.innerHTML = `
    <span>Session Summary</span>
    <strong>${escapeHtml(summary || "Live summary will appear as the transcript grows.")}</strong>
  `;
  liveCopilotMeta.textContent = `${livePayload.session.event_count || 0} updates captured | ${livePayload.session.speaker_count || 0} speakers tracked | ${liveVisualCues.length || 0} visual cues | Source: ${livePayload.copilot_context?.source || "live-heuristic"}`;
  setLiveStatus(
    livePayload.session.status === "active"
      ? `Live session active: ${livePayload.session.title}`
      : `Live session finalized: ${livePayload.session.title}`
  );
  syncFloatingLauncher();
}

function ensureLivePolling() {
  if (liveRefreshHandle !== null) {
    return;
  }
  liveRefreshHandle = window.setInterval(() => {
    if (state.liveSession?.session?.status === "active") {
      refreshLiveSession();
    }
  }, 5000);
}

function stopLivePolling() {
  if (liveRefreshHandle !== null) {
    window.clearInterval(liveRefreshHandle);
    liveRefreshHandle = null;
  }
}

function setLiveStatus(message) {
  if (liveStatus) {
    liveStatus.textContent = message;
  }
}

function setGitLabStatus(message) {
  if (gitlabStatus) {
    gitlabStatus.textContent = message;
  }
}

function setMeetingGitLabStatus(message) {
  if (meetingGitlabStatus) {
    meetingGitlabStatus.textContent = message;
  }
}

async function startLiveSession() {
  let pendingShareStream = null;
  try {
    const hasActiveSession = state.liveSession?.session?.status === "active";
    if (!isLiveCopilotPopup && (!livePopupHandle || livePopupHandle.closed)) {
      openLiveCopilotPopup();
    }
    if (navigator.mediaDevices?.getDisplayMedia) {
      try {
        pendingShareStream = await navigator.mediaDevices.getDisplayMedia({
          video: { frameRate: { ideal: 1, max: 2 } },
          audio: true
        });
      } catch {
        setLiveStatus("Screen or audio sharing was cancelled. Live session was not started.");
        return;
      }
    }

    if (!hasActiveSession) {
      const title = (liveSessionTitleInput?.value || "").trim() || `Live Session ${new Date().toLocaleTimeString()}`;
      const response = await apiFetch("/api/v1/live/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title })
      });
      if (!response.ok) {
        pendingShareStream?.getTracks().forEach((track) => {
          try {
            track.stop();
          } catch {
            // no-op
          }
        });
        const payload = await response.json().catch(() => ({}));
        setLiveStatus(payload.error || payload.detail || "Unable to start a live session.");
        return;
      }
      const payload = await response.json();
      state.liveSession = { session: payload.session, transcript: { segments: [], full_text: "" }, copilot_context: { source: "pending" } };
      renderLiveSession();
      ensureLivePolling();
      startLiveListening();
    } else {
      ensureLivePolling();
      startLiveListening();
    }

    if (pendingShareStream) {
      await startLiveScreenCapture(pendingShareStream);
      return;
    } else {
      setLiveStatus(
        hasActiveSession
          ? `Live session already active: ${state.liveSession.session.title}`
          : "Live session started. Speech capture is active. Screen sharing is not supported in this browser."
      );
    }
    await refreshLiveSession();
  } catch (error) {
    pendingShareStream?.getTracks().forEach((track) => {
      try {
        track.stop();
      } catch {
        // no-op
      }
    });
    if (error?.status !== 401) {
      setLiveStatus("Unable to start a live session right now.");
    }
  }
}

function currentLiveSpeaker() {
  return (liveSpeakerInput?.value || "").trim() || state.currentUser.displayName || "Participant";
}

function currentLiveElapsedSeconds() {
  const startedAt = state.liveSession?.session?.started_at;
  const startedAtMs = startedAt ? Date.parse(startedAt.replace(" ", "T")) : Date.now();
  if (!Number.isFinite(startedAtMs)) {
    return 0;
  }
  return Math.max(0, Math.floor((Date.now() - startedAtMs) / 1000));
}

async function appendLiveUpdate(text) {
  if (!state.liveSession?.session?.id) {
    setLiveStatus("Start a live session first.");
    return false;
  }
  const normalizedText = String(text || "").trim();
  if (!normalizedText) {
    return false;
  }
  const startSeconds = currentLiveElapsedSeconds();
  const endSeconds = startSeconds + Math.max(4, Math.ceil(normalizedText.split(/\s+/).length / 2));
  const response = await apiFetch(`/api/v1/live/${encodeURIComponent(state.liveSession.session.id)}/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      speaker: currentLiveSpeaker(),
      text: normalizedText,
      start_seconds: startSeconds,
      end_seconds: endSeconds
    })
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    setLiveStatus(payload.error || payload.detail || "Unable to store the live update.");
    return false;
  }
  state.liveSession = await response.json();
  renderLiveSession();
  return true;
}

async function submitLiveNote() {
  try {
    const success = await appendLiveUpdate(liveNoteInput?.value || "");
    if (success && liveNoteInput) {
      liveNoteInput.value = "";
    }
  } catch (error) {
    if (error?.status !== 401) {
      setLiveStatus("Unable to add the live note right now.");
    }
  }
}

async function submitLiveQuestion() {
  if (!state.liveSession?.session?.id) {
    setLiveStatus("Start a live session before asking the copilot.");
    return;
  }
  const question = (liveCopilotQuestionInput?.value || "").trim();
  if (!question) {
    setLiveStatus("Enter a question for the live copilot.");
    return;
  }
  liveCopilotMeta.textContent = "BoardSight is thinking over the live transcript...";
  try {
    const response = await apiFetch(`/api/v1/live/${encodeURIComponent(state.liveSession.session.id)}/copilot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setLiveStatus(payload.error || payload.detail || "Live copilot could not answer right now.");
      return;
    }
    const payload = await response.json();
    liveCopilotMeta.textContent = `Answer source: ${payload.source} | ${payload.event_count || 0} updates considered`;
    liveCopilotAnswer.textContent = payload.answer || "No answer returned.";
  } catch (error) {
    if (error?.status !== 401) {
      setLiveStatus("Live copilot is unavailable right now.");
    }
  }
}

function askLiveShortcut(question) {
  if (liveCopilotQuestionInput) {
    liveCopilotQuestionInput.value = question;
  }
  submitLiveQuestion();
}

function gitLabConnectionPayload() {
  const payload = {};
  const baseUrl = (gitlabBaseUrlInput?.value || "").trim();
  const projectId = (gitlabProjectIdInput?.value || "").trim();
  const privateToken = (gitlabPrivateTokenInput?.value || "").trim();
  const assigneeMap = (gitlabAssigneeMapInput?.value || "").trim();
  if (baseUrl) {
    payload.base_url = baseUrl;
  }
  if (projectId) {
    payload.project_id = projectId;
  }
  if (privateToken) {
    payload.private_token = privateToken;
  }
  if (assigneeMap) {
    payload.assignee_map = assigneeMap;
  }
  return payload;
}

function meetingGitLabConnectionPayload() {
  const payload = {};
  const baseUrl = (meetingGitlabBaseUrlInput?.value || "").trim();
  const projectId = (meetingGitlabProjectIdInput?.value || "").trim();
  const privateToken = (meetingGitlabPrivateTokenInput?.value || "").trim();
  const assigneeMap = (meetingGitlabAssigneeMapInput?.value || "").trim();
  if (baseUrl) {
    payload.base_url = baseUrl;
  }
  if (projectId) {
    payload.project_id = projectId;
  }
  if (privateToken) {
    payload.private_token = privateToken;
  }
  if (assigneeMap) {
    payload.assignee_map = assigneeMap;
  }
  return payload;
}

function renderGitLabResult(payload, mode) {
  if (!gitlabResult) {
    return;
  }
  const plan = payload.plan || {};
  const issues = plan.issues || [];
  const syncResult = payload.sync_result || {};
  const createdIssues = syncResult.created_issues || [];
  const createdLinks = syncResult.created_links || [];
  const summaryLines = [
    `${mode === "sync" ? "Sync" : "Preview"} status: ${escapeHtml(payload.status || "unknown")}`,
    `Meeting: ${escapeHtml(payload.meeting_title || plan.meeting_title || "Live session")}`,
    `Planned issues: ${issues.length}`,
    `Dependency links: ${(plan.issue_links || []).length}`,
  ];
  if (payload.approval_id) {
    summaryLines.push(`Approval id: ${escapeHtml(payload.approval_id)}`);
  }
  if (syncResult.reason) {
    summaryLines.push(`Reason: ${escapeHtml(syncResult.reason)}`);
  }
  if (syncResult.project_id) {
    summaryLines.push(`Project: ${escapeHtml(syncResult.project_id)}`);
  }

  const issueLines = issues.length === 0
    ? ["No issues were generated from the live session yet."]
    : issues.slice(0, 12).map((issue) => {
      const owner = issue.owner ? ` | owner ${issue.owner}` : "";
      const dueDate = issue.due_date ? ` | due ${issue.due_date}` : "";
      return `${issue.local_key} | ${issue.kind} | ${issue.title}${owner}${dueDate}`;
    });

  const createdLines = createdIssues.map((issue) => `${issue.local_key} -> #${issue.iid} ${issue.title || ""}`.trim());
  const linkLines = createdLinks.map((link) => `#${link.source_issue_iid} ${link.link_type || "links"} #${link.target_issue_iid}`);

  gitlabResult.textContent = [
    summaryLines.join("\n"),
    "",
    "Planned issues:",
    issueLines.join("\n"),
    createdLines.length > 0 ? `\nCreated issues:\n${createdLines.join("\n")}` : "",
    linkLines.length > 0 ? `\nCreated links:\n${linkLines.join("\n")}` : "",
  ].filter(Boolean).join("\n");
}

function renderMeetingGitLabResult(payload, mode) {
  if (!meetingGitlabResult) {
    return;
  }
  const plan = payload.plan || {};
  const issues = plan.issues || [];
  const syncResult = payload.sync_result || {};
  const createdIssues = syncResult.created_issues || [];
  const createdLinks = syncResult.created_links || [];
  const summaryLines = [
    `${mode === "sync" ? "Sync" : "Preview"} status: ${escapeHtml(payload.status || "unknown")}`,
    `Meeting: ${escapeHtml(payload.meeting_title || plan.meeting_title || "Recorded meeting")}`,
    `Planned issues: ${issues.length}`,
    `Dependency links: ${(plan.issue_links || []).length}`,
  ];
  if (payload.approval_id) {
    summaryLines.push(`Approval id: ${escapeHtml(payload.approval_id)}`);
  }
  if (syncResult.reason) {
    summaryLines.push(`Reason: ${escapeHtml(syncResult.reason)}`);
  }
  if (syncResult.project_id) {
    summaryLines.push(`Project: ${escapeHtml(syncResult.project_id)}`);
  }
  const issueLines = issues.length === 0
    ? ["No issues were generated from the recorded meeting yet."]
    : issues.slice(0, 12).map((issue) => {
      const owner = issue.owner ? ` | owner ${issue.owner}` : "";
      const dueDate = issue.due_date ? ` | due ${issue.due_date}` : "";
      return `${issue.local_key} | ${issue.kind} | ${issue.title}${owner}${dueDate}`;
    });
  const createdLines = createdIssues.map((issue) => `${issue.local_key} -> #${issue.iid} ${issue.title || ""}`.trim());
  const linkLines = createdLinks.map((link) => `#${link.source_issue_iid} ${link.link_type || "links"} #${link.target_issue_iid}`);
  meetingGitlabResult.textContent = [
    summaryLines.join("\n"),
    "",
    "Planned issues:",
    issueLines.join("\n"),
    createdLines.length > 0 ? `\nCreated issues:\n${createdLines.join("\n")}` : "",
    linkLines.length > 0 ? `\nCreated links:\n${linkLines.join("\n")}` : "",
  ].filter(Boolean).join("\n");
}

async function runGitLabAssignmentRequest(mode) {
  if (!state.liveSession?.session?.id) {
    setGitLabStatus("Start a live session before using GitLab assignment.");
    return;
  }

  const isSync = mode === "sync";
  setGitLabStatus(isSync ? "Assigning live-session work into GitLab..." : "Building GitLab preview from the live session...");

  try {
    const requestPayload = { ...gitLabConnectionPayload() };
    if (isSync && state.liveSession?.gitlabApprovalId) {
      requestPayload.approval_id = state.liveSession.gitlabApprovalId;
    }
    const response = await apiFetch(`/api/v1/live/${encodeURIComponent(state.liveSession.session.id)}/gitlab/${isSync ? "sync" : "preview"}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      setGitLabStatus(payload.error || payload.detail || "GitLab assignment request failed.");
      return;
    }
    if (payload.approval_id) {
      state.liveSession = { ...state.liveSession, gitlabApprovalId: payload.approval_id };
    }
    renderGitLabResult(payload, mode);
    setGitLabStatus(
      isSync
        ? (payload.sync_result?.status === "synced" ? "GitLab assignment synced successfully." : "GitLab sync completed in preview or dry-run mode.")
        : "GitLab preview generated from the current live session."
    );
  } catch (error) {
    if (error?.status !== 401) {
      setGitLabStatus("GitLab assignment is unavailable right now.");
    }
  }
}

async function runMeetingGitLabAssignmentRequest(mode) {
  const meetingId = state.currentMeeting?.storage?.meeting_id || state.currentMeetingId;
  if (!meetingId) {
    setMeetingGitLabStatus("Open a recorded meeting before using GitLab assignment.");
    return;
  }

  const isSync = mode === "sync";
  setMeetingGitLabStatus(isSync ? "Assigning recorded-meeting work into GitLab..." : "Building GitLab preview from the recorded meeting...");

  try {
    const requestPayload = { ...meetingGitLabConnectionPayload() };
    if (isSync && state.currentMeeting?.gitlabApprovalId) {
      requestPayload.approval_id = state.currentMeeting.gitlabApprovalId;
    }
    const response = await apiFetch(`/api/v1/meetings/${encodeURIComponent(meetingId)}/gitlab/${isSync ? "sync" : "preview"}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMeetingGitLabStatus(payload.error || payload.detail || "GitLab assignment request failed.");
      return;
    }
    state.currentMeeting = { ...state.currentMeeting, gitlabApprovalId: payload.approval_id || state.currentMeeting?.gitlabApprovalId };
    renderMeetingGitLabResult(payload, mode);
    setMeetingGitLabStatus(
      isSync
        ? (payload.sync_result?.status === "synced" ? "Recorded-meeting GitLab assignment synced successfully." : "Recorded-meeting GitLab sync completed in preview or dry-run mode.")
        : "Recorded-meeting GitLab preview generated."
    );
  } catch (error) {
    if (error?.status !== 401) {
      setMeetingGitLabStatus("Recorded-meeting GitLab assignment is unavailable right now.");
    }
  }
}

async function finalizeLiveSession() {
  if (!state.liveSession?.session?.id) {
    setLiveStatus("There is no live session to finalize.");
    return;
  }
  try {
    const response = await apiFetch(`/api/v1/live/${encodeURIComponent(state.liveSession.session.id)}/finalize`, {
      method: "POST"
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setLiveStatus(payload.error || payload.detail || "Unable to finalize the live session.");
      return;
    }
    stopLiveListening();
    stopLiveScreenCapture();
    stopLivePolling();
    await refreshLiveSession();
    setLiveStatus("Live session finalized. Screen sharing and listening have stopped.");
  } catch (error) {
    if (error?.status !== 401) {
      setLiveStatus("Unable to finalize the live session right now.");
    }
  }
}

function ensureSpeechRecognition() {
  const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognitionCtor) {
    return null;
  }
  if (liveRecognition) {
    return liveRecognition;
  }
  liveRecognition = new SpeechRecognitionCtor();
  liveRecognition.continuous = true;
  liveRecognition.interimResults = true;
  liveRecognition.lang = "en-US";
  liveRecognition.onresult = async (event) => {
    let interimText = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      const transcript = String(result[0]?.transcript || "").trim();
      if (!transcript) {
        continue;
      }
      if (result.isFinal) {
        await appendLiveUpdate(transcript);
      } else {
        interimText += `${transcript} `;
      }
    }
    if (interimText.trim()) {
      setLiveStatus(`Listening... ${interimText.trim()}`);
    }
  };
  liveRecognition.onerror = (event) => {
    setLiveStatus(`Speech capture issue: ${event.error || "unknown error"}`);
  };
  liveRecognition.onend = () => {
    if (liveRecognitionActive) {
      try {
        liveRecognition.start();
      } catch {
        liveRecognitionActive = false;
      }
    }
  };
  return liveRecognition;
}

function startLiveListening() {
  if (!state.liveSession?.session?.id) {
    setLiveStatus("Start a live session before enabling speech capture.");
    return;
  }
  const recognition = ensureSpeechRecognition();
  if (!recognition) {
    setLiveStatus("This browser does not support built-in speech recognition. You can still paste live transcript updates manually.");
    return;
  }
  liveRecognitionActive = true;
  try {
    recognition.start();
    setLiveStatus("Speech capture started. Final transcript chunks will flow into the live copilot.");
  } catch {
    setLiveStatus("Speech capture is already running.");
  }
}

function stopLiveListening() {
  liveRecognitionActive = false;
  if (liveRecognition) {
    try {
      liveRecognition.stop();
    } catch {
      // no-op
    }
  }
}

function ensureLiveScreenElements() {
  if (!liveScreenVideo) {
    liveScreenVideo = document.createElement("video");
    liveScreenVideo.muted = true;
    liveScreenVideo.playsInline = true;
    liveScreenVideo.style.position = "fixed";
    liveScreenVideo.style.opacity = "0";
    liveScreenVideo.style.pointerEvents = "none";
    liveScreenVideo.style.width = "1px";
    liveScreenVideo.style.height = "1px";
    document.body.appendChild(liveScreenVideo);
  }
  if (!liveScreenCanvas) {
    liveScreenCanvas = document.createElement("canvas");
  }
}

async function uploadLiveScreenSample() {
  if (!state.liveSession?.session?.id || !liveScreenVideo || !liveScreenCanvas) {
    return;
  }
  const width = liveScreenVideo.videoWidth;
  const height = liveScreenVideo.videoHeight;
  if (!width || !height) {
    return;
  }
  const maxWidth = 960;
  const scale = Math.min(1, maxWidth / width);
  liveScreenCanvas.width = Math.max(1, Math.round(width * scale));
  liveScreenCanvas.height = Math.max(1, Math.round(height * scale));
  const context = liveScreenCanvas.getContext("2d");
  if (!context) {
    return;
  }
  context.drawImage(liveScreenVideo, 0, 0, liveScreenCanvas.width, liveScreenCanvas.height);
  const imageBase64 = liveScreenCanvas.toDataURL("image/jpeg", 0.82);
  try {
    const response = await apiFetch(`/api/v1/live/${encodeURIComponent(state.liveSession.session.id)}/visual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image_base64: imageBase64,
        timestamp_seconds: currentLiveElapsedSeconds()
      })
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setLiveStatus(payload.error || payload.detail || "Unable to analyze live screen sample.");
      return;
    }
    state.liveSession = await response.json();
    renderLiveSession();
  } catch (error) {
    if (error?.status !== 401) {
      setLiveStatus("Live screen analysis is unavailable right now.");
    }
  }
}

async function startLiveScreenCapture(prefetchedStream = null) {
  if (!state.liveSession?.session?.id) {
    setLiveStatus("Start a live session before enabling screen capture.");
    return;
  }
  if (!prefetchedStream && !navigator.mediaDevices?.getDisplayMedia) {
    setLiveStatus("This browser does not support screen capture.");
    return;
  }
  if (liveScreenStream) {
    setLiveStatus("Screen capture is already running.");
    return;
  }
  try {
    ensureLiveScreenElements();
    liveScreenStream = prefetchedStream || await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: { ideal: 1, max: 2 } },
      audio: true
    });
    liveScreenVideo.srcObject = liveScreenStream;
    await liveScreenVideo.play();
    const [track] = liveScreenStream.getVideoTracks();
    if (track) {
      track.onended = () => {
        stopLiveScreenCapture();
      };
    }
    await uploadLiveScreenSample();
    liveScreenCaptureHandle = window.setInterval(() => {
      uploadLiveScreenSample();
    }, 15000);
    setLiveStatus("Live session started. Screen sharing is active and BoardSight will sample shared visuals every 15 seconds.");
  } catch (error) {
    stopLiveScreenCapture();
    setLiveStatus("Screen capture was cancelled or could not be started.");
  }
}

function stopLiveScreenCapture() {
  if (liveScreenCaptureHandle !== null) {
    window.clearInterval(liveScreenCaptureHandle);
    liveScreenCaptureHandle = null;
  }
  if (liveScreenStream) {
    liveScreenStream.getTracks().forEach((track) => {
      try {
        track.stop();
      } catch {
        // no-op
      }
    });
    liveScreenStream = null;
  }
  if (liveScreenVideo) {
    liveScreenVideo.pause();
    liveScreenVideo.srcObject = null;
  }
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

  const analysisProfile = analysisProfileInput?.value || "production";
  const profileLabel = "production analysis";
  setProcessingState(true, `Uploading ${file.name} and running ${profileLabel}...`);
  const formData = new FormData();
  formData.append("file", file);
  const requestUrl = new URL(apiUrl("/api/v1/pipeline/run"));
  requestUrl.searchParams.set("analysis_profile", analysisProfile);
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
    uploadStatus.textContent = `${capitalize(profileLabel)} complete. Loading meeting results...`;
    await loadMeetings();

    if (derivedMeetingId && /^\d+$/.test(derivedMeetingId)) {
      await loadMeetingDetail(derivedMeetingId);
    } else if (state.meetings.length > 0) {
      await loadMeetingDetail(state.meetings[0].meetingId || state.meetings[0].id);
    }

    uploadStatus.textContent = `${capitalize(profileLabel)} complete.`;
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
  if (isLiveCopilotPopup) {
    viewName = "live";
  }
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === viewName));
  document.querySelectorAll(".content-view").forEach((view) => view.classList.add("hidden"));
  document.getElementById(`${viewName}View`).classList.remove("hidden");
}

function openReport(fileName) {
  if (!state.currentMeetingId) return;
  downloadProtectedFile(
    `/api/v1/meetings/${encodeURIComponent(state.currentMeeting.storage?.meeting_id || state.currentMeetingId)}/reports/${fileName}`,
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
  const runtimeProfile = meeting.metadata?.performance_report?.runtime_profile;
  if (runtimeProfile) {
    rows.unshift({
      left: "Analysis Profile",
      middle: runtimeProfile,
      right: meeting.metadata?.performance_report?.no_heuristics_policy || "Profile-specific runtime path"
    });
  }
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

function timeOfDayGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function timelineTagLabel(tone) {
  if (tone === "risk") return "Risk";
  if (tone === "action") return "Action";
  if (tone === "follow-up") return "Follow-up";
  return "Strategic";
}

function buildTranscriptPreview(meeting) {
  return (meeting.transcript?.segments || [])
    .slice(0, 5)
    .map((segment) => `${formatTime(segment.start)} ${segment.speaker}: ${segment.text}`)
    .join(" | ");
}

function renderDecisionTimelineChart(container, meeting) {
  container.innerHTML = "";
  const prioritized = meeting.workflow_model?.prioritized_decisions || [];
  const tasks = meeting.workflow_model?.execution_plan || [];
  const decisions = (meeting.decision_moments || []).slice(0, 4);
  if (decisions.length === 0) {
    container.innerHTML = `<div class="empty-state">No decision timeline yet.</div>`;
    return;
  }

  const rows = decisions.map((decision, index) => {
    const label = String(decision.label || "").toLowerCase();
    const tone = label.includes("risk")
      ? "risk"
      : label.includes("action")
        ? "action"
        : index === decisions.length - 1
          ? "follow-up"
          : "strategic";
    const title = label.includes("action")
      ? "Action Assigned"
      : label.includes("risk")
        ? "Risk Flagged"
        : index === decisions.length - 1
          ? "Follow-up Scheduled"
          : "Decision Made";
    const supportingTask = tasks[index];
    const supportingDecision = prioritized[index];
    const detail = supportingTask?.title
      || supportingDecision?.text
      || decision.text
      || "BoardSight detected a timeline event.";
    return `
      <div class="timeline-entry">
        <div class="timeline-time">${decision.timestamp || "--:--"}</div>
        <div class="timeline-dot ${tone}"></div>
        <div class="timeline-content">
          <strong>${title}</strong>
          <p>${escapeHtml(shorten(detail, 92))}</p>
        </div>
        <span class="timeline-tag ${tone}">${timelineTagLabel(tone)}</span>
      </div>
    `;
  }).join("");

  container.innerHTML = rows;
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

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#96;");
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

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.authToken) {
    headers.set("Authorization", `Bearer ${state.authToken}`);
  }
  const response = await fetch(apiUrl(url), { ...options, headers });
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
