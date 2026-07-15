import {
  CALENDAR_LEGEND,
  CALENDAR_RESPONSE_STYLES,
  CONTACT_DATE_COLUMN,
  CONTACT_NOTE_COLUMN,
  CONTACT_RESPONSE_COLUMN,
  DEFAULT_RESPONSES,
  INTERVIEW_TIME_COLUMN,
  LEGACY_CONTACT_NOTE_COLUMNS,
  STATUS_COLUMN,
  VALID_STATUSES,
  addCalendarDays,
  calendarResponseState,
  contactEntryFromRow,
  entryHasData,
  escapeHtml,
  formatCalendarDay,
  formatInterviewAt,
  joinResponses,
  localTodayIso,
  mergeContactEntries,
  norm,
  normalizeContactEntry,
  normalizeInterviewAt,
  normalizeStatus,
  numberValue,
  safeUrl,
  splitResponses,
  startOfCalendarWeek,
  uniqueJoinText,
  validDateIso,
} from "./core.js";
const SIDEBAR_STORAGE_KEY = "tutor-viewer-sidebar-collapsed";
const CALENDAR_STORAGE_KEY = "tutor-viewer-calendar-collapsed";
const FILTER_PREFERENCES_STORAGE_KEY = "tutor-viewer-filter-preferences-v1";
const TABLE_BATCH_SIZE = 120;
const SEARCH_DEBOUNCE_MS = 160;

const state = {
  csrfToken: "",
  profiles: [],
  currentProfileId: "",
  statusStore: { version: 4, updated_at: "", statuses: {} },
  records: [],
  filtered: [],
  calendarFiltered: [],
  tableRenderLimit: TABLE_BATCH_SIZE,
  selectedKey: "",
  sidebarCollapsed: false,
  calendarCollapsed: false,
  filterPreferencesReady: false,
  calendarRangeStart: "",
  selectedCalendarDate: "",
  calendarDateInteracted: false,
  dirty: false,
  pendingSaves: 0,
  saveFailures: 0,
  saveQueue: Promise.resolve(),
};

const $ = (id) => document.getElementById(id);

const els = {
  summary: $("summary"),
  profileSelector: $("profileSelector"),
  appShell: $("appShell"),
  calendarSchoolFilter: $("calendarSchoolFilter"),
  calendarCollegeFilter: $("calendarCollegeFilter"),
  calendarFilterReset: $("calendarFilterReset"),
  searchInput: $("searchInput"),
  schoolFilter: $("schoolFilter"),
  collegeFilter: $("collegeFilter"),
  levelFilter: $("levelFilter"),
  contactFilter: $("contactFilter"),
  contactedOnly: $("contactedOnly"),
  hideContacted: $("hideContacted"),
  weakEvidenceOnly: $("weakEvidenceOnly"),
  listFilterReset: $("listFilterReset"),
  teacherRows: $("teacherRows"),
  tablePane: document.querySelector(".table-pane"),
  workbench: $("workbench"),
  calendarPane: $("calendarPane"),
  calendarLayout: $("calendarLayout"),
  calendarToggle: $("calendarToggle"),
  calendarCollapsedSummary: $("calendarCollapsedSummary"),
  calendarPrev: $("calendarPrev"),
  calendarToday: $("calendarToday"),
  calendarNext: $("calendarNext"),
  calendarRangeLabel: $("calendarRangeLabel"),
  calendarRangeSummary: $("calendarRangeSummary"),
  calendarLegend: $("calendarLegend"),
  calendarProgressSummary: $("calendarProgressSummary"),
  calendarProgressBody: $("calendarProgressBody"),
  calendarGrid: $("calendarGrid"),
  calendarSelectedDate: $("calendarSelectedDate"),
  calendarSelectedCount: $("calendarSelectedCount"),
  calendarSelectedDay: $("calendarSelectedDay"),
  calendarSelectedTeachers: $("calendarSelectedTeachers"),
  missingDateSection: $("missingDateSection"),
  missingDateCount: $("missingDateCount"),
  missingDateList: $("missingDateList"),
  detailPane: $("detailPane"),
  detailToggle: $("detailToggle"),
};

function statusValue(key) {
  return normalizeStatus(normalizeContactEntry(state.statusStore.statuses?.[key]).status);
}

function applyContactEntryToRecord(record, entry) {
  const contact = normalizeContactEntry(entry);
  record.contact = contact;
  record.status = contact.status || "";
  record.raw[STATUS_COLUMN] = record.status;
  record.raw[CONTACT_DATE_COLUMN] = contact.contacted_at || "";
  record.raw[CONTACT_RESPONSE_COLUMN] = joinResponses(contact.responses || []);
  record.raw[INTERVIEW_TIME_COLUMN] = contact.interview_at || "";
  record.raw[CONTACT_NOTE_COLUMN] = contact.note || "";
  LEGACY_CONTACT_NOTE_COLUMNS.forEach((column) => {
    if (column in record.raw) record.raw[column] = "";
  });
}

function contactEntryForRecord(record) {
  const rawEntry = contactEntryFromRow(record.raw || {});
  const storeHasEntry = Object.prototype.hasOwnProperty.call(state.statusStore.statuses || {}, record.key);
  if (!storeHasEntry) return rawEntry;
  return mergeContactEntries(rawEntry, normalizeContactEntry(state.statusStore.statuses[record.key]));
}

function setDirty(isDirty) {
  state.dirty = isDirty;
  els.summary.classList.toggle("dirty", isDirty);
}

function setSummary() {
  const total = state.records.length;
  const shown = state.filtered.length;
  const contacted = state.records.filter((record) => record.status === "已套磁").length;
  const blocked = state.records.filter((record) =>
    ["先不考虑", "不可能", "不匹配"].includes(record.status),
  ).length;
  els.summary.textContent = total
    ? `${shown}/${total} 位教师 · 已套磁 ${contacted} · 排除 ${blocked}`
    : "未加载数据";
}

function showToast(message) {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  document.body.appendChild(node);
  window.setTimeout(() => node.remove(), 3000);
}

function readSidebarPreference() {
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeSidebarPreference(collapsed) {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "1" : "0");
  } catch {
    // The layout still works when local storage is unavailable.
  }
}

function sidebarCanCollapse() {
  return window.matchMedia("(min-width: 1101px)").matches;
}

function applySidebarState() {
  const canCollapse = sidebarCanCollapse();
  const collapsed = canCollapse && state.sidebarCollapsed;
  els.workbench.classList.toggle("sidebar-collapsed", collapsed);
  els.detailPane.hidden = collapsed;
  els.detailToggle.hidden = !canCollapse;
  els.detailToggle.title = collapsed ? "展开教师详情" : "收起教师详情";
  els.detailToggle.setAttribute("aria-label", els.detailToggle.title);
  els.detailToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
}

function setSidebarCollapsed(collapsed) {
  state.sidebarCollapsed = Boolean(collapsed);
  writeSidebarPreference(state.sidebarCollapsed);
  applySidebarState();
}

function readCalendarPreference() {
  try {
    return window.localStorage.getItem(CALENDAR_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeCalendarPreference(collapsed) {
  try {
    window.localStorage.setItem(CALENDAR_STORAGE_KEY, collapsed ? "1" : "0");
  } catch {
    // The calendar remains usable when local storage is unavailable.
  }
}

function readFilterPreferences() {
  try {
    const key = `${FILTER_PREFERENCES_STORAGE_KEY}:${state.currentProfileId || "default"}`;
    const parsed = JSON.parse(window.localStorage.getItem(key) || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function selectHasValue(select, value) {
  return Boolean(value) && Array.from(select.options).some((option) => option.value === value);
}

function restoreFilterPreferences() {
  const preferences = readFilterPreferences();
  const list = preferences.list && typeof preferences.list === "object" ? preferences.list : {};
  const calendar = preferences.calendar && typeof preferences.calendar === "object" ? preferences.calendar : {};

  els.schoolFilter.value = selectHasValue(els.schoolFilter, list.school) ? list.school : "";
  populateCollegeFilter();
  els.collegeFilter.value = selectHasValue(els.collegeFilter, list.college) ? list.college : "";
  els.levelFilter.value = selectHasValue(els.levelFilter, list.level) ? list.level : "";
  els.contactFilter.value = selectHasValue(els.contactFilter, list.status) ? list.status : "";
  els.contactedOnly.checked = list.contactedOnly === true;
  els.hideContacted.checked = list.hideMarked === true;
  els.weakEvidenceOnly.checked = list.weakOnly === true;

  els.calendarSchoolFilter.value = selectHasValue(els.calendarSchoolFilter, calendar.school) ? calendar.school : "";
  populateCalendarCollegeFilter();
  els.calendarCollegeFilter.value = selectHasValue(els.calendarCollegeFilter, calendar.college) ? calendar.college : "";
}

function writeFilterPreferences() {
  if (!state.filterPreferencesReady) return;
  const preferences = {
    version: 1,
    list: {
      school: els.schoolFilter.value,
      college: els.collegeFilter.value,
      level: els.levelFilter.value,
      status: els.contactFilter.value,
      contactedOnly: els.contactedOnly.checked,
      hideMarked: els.hideContacted.checked,
      weakOnly: els.weakEvidenceOnly.checked,
    },
    calendar: {
      school: els.calendarSchoolFilter.value,
      college: els.calendarCollegeFilter.value,
    },
  };
  try {
    const key = `${FILTER_PREFERENCES_STORAGE_KEY}:${state.currentProfileId || "default"}`;
    window.localStorage.setItem(key, JSON.stringify(preferences));
  } catch {
    // Filter preferences are optional; no private contact content is stored here.
  }
}

function applyCalendarState() {
  const collapsed = state.calendarCollapsed;
  els.appShell.classList.toggle("calendar-collapsed", collapsed);
  els.calendarPane.classList.toggle("is-collapsed", collapsed);
  els.calendarLayout.hidden = collapsed;
  els.calendarToggle.title = collapsed ? "展开套磁日历" : "收起套磁日历";
  els.calendarToggle.setAttribute("aria-label", els.calendarToggle.title);
  els.calendarToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
}

function setCalendarCollapsed(collapsed) {
  state.calendarCollapsed = Boolean(collapsed);
  writeCalendarPreference(state.calendarCollapsed);
  applyCalendarState();
}

function detailToolbar() {
  return `
    <div class="detail-toolbar">
      <span>教师详情</span>
      <div class="detail-toolbar-actions">
        <select id="detailJumpSelect" class="detail-jump-select" aria-label="快速定位详情内容" disabled>
          <option value="">快速定位</option>
        </select>
        <button id="detailPrev" type="button" title="上一位教师（Alt+↑）">上一位</button>
        <button id="detailNext" type="button" title="下一位教师（Alt+↓）">下一位</button>
      </div>
    </div>
  `;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tutor-Viewer-Token": state.csrfToken,
    },
    body: JSON.stringify(payload || {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.errors?.[0]?.error || `请求失败：${response.status}`);
  }
  return data;
}

function contactPayload(record) {
  return normalizeContactEntry(state.statusStore.statuses?.[record.key] || {});
}

function queueContactSave(record) {
  const profileId = state.currentProfileId;
  const payload = { profileId, key: record.key, entry: contactPayload(record) };
  state.pendingSaves += 1;
  setDirty(true);
  state.saveQueue = state.saveQueue
    .catch(() => {})
    .then(async () => {
      const data = await postJson("/api/contact", payload);
      if (data.profileId !== state.currentProfileId) return;
      state.statusStore = normalizeStore(data.statusStore || state.statusStore);
      state.saveFailures = 0;
    })
    .catch((error) => {
      state.saveFailures += 1;
      showToast(`自动保存失败：${error.message}`);
    })
    .finally(() => {
      state.pendingSaves = Math.max(0, state.pendingSaves - 1);
      if (state.pendingSaves === 0 && state.saveFailures === 0) setDirty(false);
    });
}

function normalizeStore(data) {
  const store = { version: 4, updated_at: "", statuses: {} };
  if (!data || typeof data !== "object") return store;
  store.version = Math.max(Number(data.version || 1), 4);
  store.updated_at = data.updated_at || data.updatedAt || "";
  const statuses = data.statuses || data.records || {};
  Object.entries(statuses).forEach(([key, value]) => {
    const entry = normalizeContactEntry(value);
    if (entryHasData(entry)) store.statuses[key] = entry;
  });
  return store;
}

function mergeLoadedRecords(records) {
  state.records = records.map((record) => {
    applyContactEntryToRecord(record, contactEntryForRecord(record));
    return record;
  });
  state.records.sort(compareRecords);
  state.tableRenderLimit = TABLE_BATCH_SIZE;
  state.selectedKey = state.records[0]?.key || "";
  populateFilters();
  restoreFilterPreferences();
  state.filterPreferencesReady = true;
  applyCalendarFilters();
  applyFilters();
  setDirty(false);
}

function populateProfileSelector() {
  els.profileSelector.innerHTML = "";
  state.profiles.forEach((profile) => {
    const option = document.createElement("option");
    option.value = profile.profileId;
    option.textContent = `${profile.displayName}${profile.hasResults ? "" : " · 暂无结果"}`;
    els.profileSelector.appendChild(option);
  });
  els.profileSelector.value = state.currentProfileId;
  els.profileSelector.disabled = state.profiles.length <= 1;
}

async function loadProfileData(profileId, { announce = true } = {}) {
  const response = await fetch(`/api/data?profile=${encodeURIComponent(profileId)}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`加载失败：${response.status}`);
  const data = await response.json();
  state.currentProfileId = norm(data.profileId || profileId);
  els.profileSelector.value = state.currentProfileId;
  state.statusStore = normalizeStore(data.statusStore || {});
  state.selectedKey = "";
  state.filterPreferencesReady = false;
  const records = (data.records || []).map((record) => ({
    schoolSlug: record.schoolSlug,
    collegeSlug: record.collegeSlug,
    schoolName: record.schoolName,
    collegeName: record.collegeName,
    sourcePath: record.sourcePath,
    raw: record.raw || {},
    dblp: record.dblp || [],
    publication: record.publication || [],
    publicationCandidates: record.publicationCandidates || [],
    publicationSources: record.publicationSources || [],
    arxiv: record.arxiv || [],
    web: record.web || [],
    webSearch: record.webSearch || [],
    detailsLoaded: false,
    detailsLoading: false,
    detailsError: "",
    contact: normalizeContactEntry(record.contact || {}),
    status: normalizeStatus(record.status),
    key: record.key,
  }));
  mergeLoadedRecords(records);
  if (announce) {
    showToast(records.length ? `已加载 ${records.length} 位教师` : "该学生画像尚未生成匹配结果");
  }
}

async function switchProfile(profileId) {
  if (!profileId || profileId === state.currentProfileId) return;
  const previous = state.currentProfileId;
  els.profileSelector.disabled = true;
  await state.saveQueue.catch(() => {});
  if (state.saveFailures) {
    els.profileSelector.value = previous;
    els.profileSelector.disabled = state.profiles.length <= 1;
    showToast("存在未保存的联系记录，请先重试保存后再切换画像");
    return;
  }
  try {
    await postJson("/api/profile-selection", { profileId });
    await loadProfileData(profileId);
  } catch (error) {
    state.currentProfileId = previous;
    els.profileSelector.value = previous;
    showToast(`画像切换失败：${error.message}`);
  } finally {
    els.profileSelector.disabled = state.profiles.length <= 1;
  }
}

async function loadFromApi() {
  const sessionResponse = await fetch("/api/session", { cache: "no-store" });
  if (sessionResponse.status === 404) {
    throw new Error("当前运行的是旧版看板服务，请关闭旧服务后重新运行 start_viewer.bat");
  }
  if (!sessionResponse.ok) throw new Error(`会话初始化失败：${sessionResponse.status}`);
  const session = await sessionResponse.json();
  if (Number(session.apiVersion || 0) < 5) {
    throw new Error("当前运行的是旧版看板服务，请关闭旧服务后重新运行 start_viewer.bat");
  }
  state.csrfToken = norm(session.token);
  if (!state.csrfToken) throw new Error("会话令牌缺失");
  state.profiles = Array.isArray(session.profiles) ? session.profiles : [];
  state.currentProfileId = norm(session.defaultProfileId || state.profiles[0]?.profileId);
  if (!state.currentProfileId) throw new Error("没有可用的本地学生画像");
  populateProfileSelector();
  await loadProfileData(state.currentProfileId);
}

function populateSelect(select, values, allLabel) {
  const current = select.value;
  select.replaceChildren();
  const all = document.createElement("option");
  all.value = "";
  all.textContent = allLabel;
  select.appendChild(all);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  select.value = values.includes(current) ? current : "";
}

function collegeValuesForSelectedSchool() {
  const school = els.schoolFilter.value;
  return [
    ...new Set(
      state.records
        .filter((record) => !school || record.schoolName === school)
        .map((record) => record.collegeName)
        .filter(Boolean),
    ),
  ].sort();
}

function populateCollegeFilter() {
  populateSelect(els.collegeFilter, collegeValuesForSelectedSchool(), "全部学院");
}

function calendarCollegeValuesForSelectedSchool() {
  const school = els.calendarSchoolFilter.value;
  return [
    ...new Set(
      state.records
        .filter((record) => !school || record.schoolName === school)
        .map((record) => record.collegeName)
        .filter(Boolean),
    ),
  ].sort();
}

function populateCalendarCollegeFilter() {
  populateSelect(els.calendarCollegeFilter, calendarCollegeValuesForSelectedSchool(), "全部学院");
}

function populateFilters() {
  const schools = [...new Set(state.records.map((record) => record.schoolName).filter(Boolean))].sort();
  populateSelect(
    els.schoolFilter,
    schools,
    "全部学校",
  );
  populateSelect(els.calendarSchoolFilter, schools, "全部学校");
  populateCollegeFilter();
  populateCalendarCollegeFilter();
  populateSelect(els.levelFilter, ["强烈建议", "可以考虑", "暂不优先"], "全部推荐");
  populateSelect(els.contactFilter, VALID_STATUSES, "全部状态");
}

function applyCalendarFilters() {
  const school = els.calendarSchoolFilter.value;
  const college = els.calendarCollegeFilter.value;
  state.calendarFiltered = state.records.filter((record) => {
    if (school && record.schoolName !== school) return false;
    if (college && record.collegeName !== college) return false;
    return true;
  });
  const hasCalendarFilters = Boolean(school || college);
  els.calendarFilterReset.disabled = !hasCalendarFilters;
  els.calendarFilterReset.setAttribute("aria-label", hasCalendarFilters ? "重置日历筛选" : "日历筛选未启用");
  writeFilterPreferences();
  renderCalendar();
}

function resetCalendarFilters() {
  els.calendarSchoolFilter.value = "";
  populateCalendarCollegeFilter();
  els.calendarCollegeFilter.value = "";
  applyCalendarFilters();
}

function compareRecords(a, b) {
  const rank = { 强烈建议: 0, 可以考虑: 1, 暂不优先: 2 };
  const levelA = rank[norm(a.raw["推荐等级"])] ?? 9;
  const levelB = rank[norm(b.raw["推荐等级"])] ?? 9;
  if (levelA !== levelB) return levelA - levelB;
  return numberValue(b.raw["匹配分"]) - numberValue(a.raw["匹配分"]);
}

function isWeakEvidence(record) {
  const dblp = numberValue(record.raw["DBLP近三年论文数"]);
  const publication = numberValue(record.raw["近五年论文数"]);
  const arxiv = numberValue(record.raw["arXiv近五年论文数"] || record.raw["arXiv近三年论文数"]);
  const web = numberValue(record.raw["网页证据条数"]);
  const webSearch = numberValue(record.raw["WebSearch证据条数"]);
  return dblp + publication + arxiv + web + webSearch <= 1;
}

function searchableText(record) {
  const row = record.raw;
  return [
    row["姓名"],
    record.schoolName,
    record.collegeName,
    row["职称"],
    affiliationSummary(record),
    row["推荐等级"],
    row["研究方向"],
    row["综合研究方向（主页+DBLP+arXiv+网页）"],
    row["命中关键词"],
    row["显式核心锚点"],
    row["评分警告"],
    row["DBLP近三年关键词"],
    row["近五年关键词"],
    row["近五年代表论文"],
    row["主要数学分类"],
    row["arXiv关键词"],
    row["网页关键词"],
    row["WebSearch关键词"],
    row["WebSearch代表证据"],
    row["WebSearch建议"],
    row["推荐理由"],
    record.raw[CONTACT_DATE_COLUMN],
    record.raw[CONTACT_RESPONSE_COLUMN],
    record.raw[INTERVIEW_TIME_COLUMN],
    record.raw[CONTACT_NOTE_COLUMN],
  ]
    .map(norm)
    .join(" ")
    .toLowerCase();
}

function applyFilters() {
  const query = norm(els.searchInput.value).toLowerCase();
  const school = els.schoolFilter.value;
  const college = els.collegeFilter.value;
  const level = els.levelFilter.value;
  const status = els.contactFilter.value;
  const contactedOnly = els.contactedOnly.checked;
  const hideMarked = els.hideContacted.checked;
  const weakOnly = els.weakEvidenceOnly.checked;

  state.filtered = state.records.filter((record) => {
    const row = record.raw;
    if (query && !searchableText(record).includes(query)) return false;
    if (contactedOnly && record.status !== "已套磁") return false;
    if (hideMarked && record.status) return false;
    if (school && record.schoolName !== school) return false;
    if (college && record.collegeName !== college) return false;
    if (level && norm(row["推荐等级"]) !== level) return false;
    if (status && record.status !== status) return false;
    if (weakOnly && !isWeakEvidence(record)) return false;
    return true;
  });
  state.filtered.sort(compareRecords);
  const filterCount = [query, school, college, level, status].filter(Boolean).length
    + [contactedOnly, hideMarked, weakOnly].filter(Boolean).length;
  els.listFilterReset.disabled = filterCount === 0;
  els.listFilterReset.textContent = filterCount ? `重置筛选 ${filterCount}` : "重置筛选";
  els.listFilterReset.setAttribute("aria-label", filterCount ? `重置 ${filterCount} 项教师列表筛选` : "教师列表筛选未启用");
  writeFilterPreferences();
  state.tableRenderLimit = TABLE_BATCH_SIZE;
  els.tablePane.scrollTop = 0;
  if (!state.records.some((record) => record.key === state.selectedKey)) {
    state.selectedKey = state.filtered[0]?.key || "";
  }
  renderTable();
  renderDetail();
  setSummary();
}

function resetListFilters() {
  els.searchInput.value = "";
  els.schoolFilter.value = "";
  populateCollegeFilter();
  els.collegeFilter.value = "";
  els.levelFilter.value = "";
  els.contactFilter.value = "";
  els.contactedOnly.checked = false;
  els.hideContacted.checked = false;
  els.weakEvidenceOnly.checked = false;
  applyFilters();
  els.searchInput.focus();
}

function levelClass(level) {
  if (level === "强烈建议") return "level-strong";
  if (level === "可以考虑") return "level-mid";
  return "level-low";
}

function statusClass(status) {
  if (status === "已套磁") return "status-done";
  if (status === "先不考虑") return "status-ignore";
  if (status === "不可能") return "status-impossible";
  if (status === "不匹配") return "status-mismatch";
  return "";
}

function contactSelect(record) {
  const select = document.createElement("select");
  select.className = "contact-select";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "";
  select.appendChild(empty);
  VALID_STATUSES.forEach((status) => {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    select.appendChild(option);
  });
  select.value = record.status || "";
  select.addEventListener("click", (event) => event.stopPropagation());
  select.addEventListener("change", () => updateStatus(record.key, select.value));
  return select;
}

function uniqueParts(items) {
  const seen = new Set();
  return items
    .map(([label, value]) => [label, norm(value)])
    .filter(([, value]) => value)
    .filter(([, value]) => {
      if (seen.has(value)) return false;
      seen.add(value);
      return true;
    });
}

function canonicalSignal(value) {
  return norm(value)
    .normalize("NFKC")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[。.]$/, "")
    .trim();
}

function splitSignals(value) {
  return norm(value)
    .replace(/(?:DBLP|arXiv|WebSearch|网页)(?:近三年)?关键词\s*[:：]/gi, ";")
    .split(/[;；,，、|\n]+/)
    .map((item) => norm(item))
    .filter(Boolean);
}

function uniqueSignals(values, seen = new Set()) {
  const output = [];
  values.flatMap(splitSignals).forEach((value) => {
    const key = canonicalSignal(value);
    if (!key || seen.has(key)) return;
    seen.add(key);
    output.push(value);
  });
  return output;
}

function directionViewModel(row) {
  const matchedKeywords = uniqueSignals([row["命中关键词"]]);
  const matchedGroups = uniqueSignals([row["画像方向分组"]]);
  const officialItems = uniqueParts([
    ["教师主页", row["研究方向"]],
    ["导师信息库", row["导师信息库研究方向"]],
    ["官方团队材料", row["团队PDF证据"]],
  ]);
  const seen = new Set(matchedKeywords.map(canonicalSignal));
  const sourceGroups = [
    ["DBLP", uniqueSignals([row["DBLP近三年关键词"]], seen)],
    ["数学文献", uniqueSignals([row["近五年关键词"], row["主要数学分类"]], seen)],
    ["arXiv", uniqueSignals([row["arXiv关键词"]], seen)],
    ["网页", uniqueSignals([row["网页关键词"]], seen)],
    ["搜索补充", uniqueSignals([row["WebSearch关键词"]], seen)],
  ].filter(([, terms]) => terms.length);
  const fallback = norm(
    row["综合研究方向（主页+DBLP+arXiv+网页）"] || row["综合研究方向（主页+DBLP）"],
  );
  return { matchedKeywords, matchedGroups, officialItems, sourceGroups, fallback };
}

function signalChips(terms, limit = 6, extraClass = "") {
  const visible = terms.slice(0, limit);
  const remaining = terms.length - visible.length;
  const chips = visible
    .map((term) => `<span class="signal-chip ${extraClass}" title="${escapeHtml(term)}">${escapeHtml(term)}</span>`)
    .join("");
  const more = remaining > 0 ? `<span class="signal-more">+${remaining}</span>` : "";
  return `${chips}${more}`;
}

function institutionCell(record) {
  const cell = document.createElement("td");
  cell.className = "institution-cell";
  const school = document.createElement("div");
  school.className = "cell-main";
  school.textContent = record.schoolName;
  const college = document.createElement("div");
  college.className = "cell-subtle";
  college.textContent = record.collegeName;
  cell.append(school, college);
  return cell;
}

function matchCell(row) {
  const cell = document.createElement("td");
  cell.className = "match-cell";
  const terms = directionViewModel(row).matchedKeywords;
  if (!terms.length) {
    cell.classList.add("muted");
    cell.textContent = norm(row["研究方向"]) || "未提取";
    cell.title = cell.textContent;
    return cell;
  }
  cell.innerHTML = `<div class="table-signals">${signalChips(terms, 3)}</div>`;
  cell.title = terms.join("；");
  return cell;
}

function officialDirectionCell(row) {
  const cell = document.createElement("td");
  cell.className = "official-direction-cell";
  const direction = norm(row["研究方向"]);
  const text = document.createElement("div");
  text.className = "official-direction-text";
  text.textContent = direction || "未提取";
  cell.title = direction || "教师主页暂未提取到研究方向";
  if (!direction) cell.classList.add("muted");
  cell.appendChild(text);
  return cell;
}

function reviewCell(row) {
  const cell = document.createElement("td");
  cell.className = "review-cell";
  const anchor = norm(row["显式核心锚点"]);
  const warning = norm(row["评分警告"]);
  const hasPolicyFields = Boolean(anchor || norm(row["评分规则版本"]));
  const signals = [];
  if (anchor === "是") signals.push(["官方锚点", "signal-positive", "已确认官方显式核心方向"]);
  else if (hasPolicyFields) signals.push(["无核心锚点", "signal-muted", "未确认官方显式核心方向"]);
  else signals.push(["旧数据", "signal-muted", "尚未按新版策略重跑"]);
  if (warning) signals.push(["需复核", "signal-warning", warning]);
  signals.forEach(([label, className, title]) => {
    const badge = document.createElement("span");
    badge.className = `review-signal ${className}`;
    badge.textContent = label;
    badge.title = title;
    cell.appendChild(badge);
  });
  return cell;
}

function affiliationItems(row) {
  return uniqueParts([
    ["学院归属", row["学院归属"]],
    ["归属状态", row["学院归属状态"]],
    ["归属方式", row["学院归属方式"]],
    ["归属证据", row["学院归属证据"]],
    ["归属来源", row["学院归属来源"]],
    ["名录研究所", row["名录研究所"]],
    ["主页研究所", row["主页研究所"]],
    ["官方系别", row["官方系别"]],
    ["所内职务", row["所内职务"]],
    ["是否兼职", row["是否兼职"]],
    ["电话", row["电话"]],
    ["地址", row["地址"]],
    ["抓取状态", row["抓取状态"]],
    ["备注", row["备注"]],
  ]);
}

function affiliationSummary(record) {
  return affiliationItems(record.raw)
    .map(([label, value]) => `${label}: ${value}`)
    .join("；");
}

function contactSummary(record) {
  const entry = normalizeContactEntry(record.contact || {});
  return uniqueParts([
    ["时间", entry.contacted_at],
    ["回复", joinResponses(entry.responses || [])],
    ["约面试", formatInterviewAt(entry.interview_at)],
    ["回复备注", entry.note],
  ])
    .map(([label, value]) => `${label}: ${value}`)
    .join("；");
}

function renderTable() {
  const fragment = document.createDocumentFragment();
  if (!state.filtered.length) {
    const tr = document.createElement("tr");
    tr.className = "table-empty-row";
    const cell = document.createElement("td");
    cell.colSpan = 9;
    const message = document.createElement("strong");
    message.textContent = state.records.length ? "没有符合当前筛选的教师" : "尚未加载教师数据";
    cell.appendChild(message);
    if (state.records.length) {
      const hint = document.createElement("span");
      hint.textContent = "可调整条件或清除教师列表筛选。";
      const reset = document.createElement("button");
      reset.type = "button";
      reset.className = "filter-reset table-empty-reset";
      reset.textContent = "清除筛选";
      reset.addEventListener("click", resetListFilters);
      cell.append(hint, reset);
    }
    tr.appendChild(cell);
    fragment.appendChild(tr);
  }
  state.filtered.slice(0, state.tableRenderLimit).forEach((record) => {
    const row = record.raw;
    const tr = document.createElement("tr");
    tr.dataset.recordKey = record.key;
    tr.tabIndex = 0;
    tr.setAttribute("aria-selected", record.key === state.selectedKey ? "true" : "false");
    tr.setAttribute("aria-label", `${norm(row["姓名"])}，${record.schoolName}，${record.collegeName}`);
    if (record.key === state.selectedKey) tr.classList.add("selected");
    const selectRow = () => {
      state.selectedKey = record.key;
      updateSelectedElements();
      renderDetail();
    };
    tr.addEventListener("click", selectRow);
    tr.addEventListener("keydown", (event) => {
      if (event.target !== tr || !["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      selectRow();
    });

    tr.appendChild(td(row["姓名"], "cell-main"));
    const statusTd = document.createElement("td");
    statusTd.appendChild(contactSelect(record));
    tr.appendChild(statusTd);
    tr.appendChild(institutionCell(record));
    tr.appendChild(tdPill(row["推荐等级"], levelClass(norm(row["推荐等级"]))));
    tr.appendChild(td(row["匹配分"]));
    tr.appendChild(matchCell(row));
    tr.appendChild(officialDirectionCell(row));
    tr.appendChild(reviewCell(row));
    tr.appendChild(td(contactSummary(record), "cell-note"));
    fragment.appendChild(tr);
  });
  els.teacherRows.replaceChildren(fragment);
}

function selectCalendarRecord(key) {
  if (!state.calendarFiltered.some((record) => record.key === key)) return;
  state.selectedKey = key;
  updateSelectedElements();
  renderDetail();
  if (window.matchMedia("(max-width: 900px)").matches) {
    els.detailPane.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function calendarEventButton(record, compact = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.recordKey = record.key;
  const responseState = calendarResponseState(record);
  const interviewText = formatInterviewAt(record.contact?.interview_at);
  button.className = `calendar-event ${responseState.className}${record.key === state.selectedKey ? " selected" : ""}${interviewText ? " has-interview" : ""}${compact ? " compact" : ""}`;
  const responseText = responseState.responses.join(" · ") || "未记录回复";
  const responseWithInterview = interviewText ? `${responseText} · ◆ 面试 ${interviewText}` : responseText;
  button.title = `${norm(record.raw["姓名"])} · ${record.schoolName} · ${record.collegeName} · ${responseWithInterview}`;
  const name = document.createElement("span");
  name.className = "calendar-event-name";
  name.textContent = norm(record.raw["姓名"]);
  const institution = document.createElement("span");
  institution.className = "calendar-event-institution";
  institution.textContent = `${record.schoolName} · ${record.collegeName}`;
  const responses = document.createElement("span");
  responses.className = "calendar-event-responses";
  const visibleResponses = compact && responseState.responses.length > 1
    ? [responseState.primary]
    : responseState.responses;
  if (visibleResponses.length) {
    visibleResponses.forEach((label) => {
      const response = document.createElement("span");
      response.className = `calendar-event-response ${CALENDAR_RESPONSE_STYLES[label] || "response-unset"}`;
      response.textContent = label;
      responses.appendChild(response);
    });
    if (compact && responseState.responses.length > 1) {
      const more = document.createElement("span");
      more.className = "calendar-event-response response-unset";
      more.textContent = `+${responseState.responses.length - 1}`;
      responses.appendChild(more);
    }
  } else {
    const response = document.createElement("span");
    response.className = "calendar-event-response response-unset";
    response.textContent = "未记录回复";
    responses.appendChild(response);
  }
  if (interviewText) {
    const interview = document.createElement("span");
    interview.className = "calendar-event-response calendar-event-interview";
    interview.textContent = `◆ ${interviewText}`;
    interview.title = `面试 ${interviewText}`;
    responses.appendChild(interview);
  }
  button.append(name, institution, responses);
  button.addEventListener("click", () => selectCalendarRecord(record.key));
  return button;
}

function recordsByCalendarDate(records) {
  const grouped = new Map();
  records.forEach((record) => {
    const dates = new Set([
      validDateIso(record.contact?.contacted_at || record.raw[CONTACT_DATE_COLUMN]),
      normalizeInterviewAt(record.contact?.interview_at || record.raw[INTERVIEW_TIME_COLUMN]).slice(0, 10),
    ]);
    dates.delete("");
    dates.forEach((date) => {
      if (!grouped.has(date)) grouped.set(date, []);
      grouped.get(date).push(record);
    });
  });
  grouped.forEach((items) => items.sort((a, b) => norm(a.raw["姓名"]).localeCompare(norm(b.raw["姓名"]), "zh-CN")));
  return grouped;
}

function calendarRangeDates() {
  const start = state.calendarRangeStart || startOfCalendarWeek();
  return Array.from({ length: 28 }, (_, index) => addCalendarDays(start, index));
}

function recordsInCalendarRange(dates) {
  const start = dates[0];
  const end = dates[dates.length - 1];
  return state.calendarFiltered.filter((record) => {
    const contactDate = validDateIso(record.contact?.contacted_at || record.raw[CONTACT_DATE_COLUMN]);
    const interviewDate = normalizeInterviewAt(record.contact?.interview_at || record.raw[INTERVIEW_TIME_COLUMN]).slice(0, 10);
    return (contactDate >= start && contactDate <= end) || (interviewDate >= start && interviewDate <= end);
  });
}

function calendarResponseCounts(records) {
  const counts = new Map(CALENDAR_LEGEND.map(([label]) => [label, 0]));
  records.forEach((record) => {
    const responses = calendarResponseState(record).responses;
    if (!responses.length) {
      counts.set("未记录", counts.get("未记录") + 1);
      return;
    }
    responses.forEach((response) => {
      if (counts.has(response)) counts.set(response, counts.get(response) + 1);
    });
  });
  return counts;
}

function calendarProgressStats(records) {
  let contacted = 0;
  let progressed = 0;
  let interviews = 0;
  records.forEach((record) => {
    const responses = splitResponses(record.contact?.responses || record.raw[CONTACT_RESPONSE_COLUMN]);
    const interviewAt = normalizeInterviewAt(record.contact?.interview_at || record.raw[INTERVIEW_TIME_COLUMN]);
    if (record.status === "已套磁") contacted += 1;
    if (responses.some((response) => response !== "已发")) progressed += 1;
    if (responses.includes("约面试") || interviewAt) interviews += 1;
  });
  return { total: records.length, contacted, progressed, interviews };
}

function renderCalendarProgressOverview() {
  const groups = new Map();
  state.calendarFiltered.forEach((record) => {
    const key = `${record.schoolName}\u0000${record.collegeName}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  });
  const rows = [...groups.entries()]
    .map(([key, records]) => {
      const [school, college] = key.split("\u0000");
      return { school, college, ...calendarProgressStats(records) };
    })
    .sort((a, b) => a.school.localeCompare(b.school, "zh-CN") || a.college.localeCompare(b.college, "zh-CN"));
  const schoolCount = new Set(rows.map((row) => row.school).filter(Boolean)).size;
  els.calendarProgressSummary.textContent = `${schoolCount} 所学校 · ${rows.length} 个学院`;

  const fragment = document.createDocumentFragment();
  if (!rows.length) {
    const tr = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = "当前日历筛选下没有教师记录";
    tr.appendChild(cell);
    fragment.appendChild(tr);
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    [row.school, row.college, row.total, `${row.contacted} · ${row.total ? Math.round((row.contacted / row.total) * 100) : 0}%`, row.progressed, row.interviews]
      .forEach((value) => tr.appendChild(td(value)));
    fragment.appendChild(tr);
  });
  els.calendarProgressBody.replaceChildren(fragment);
}

function relativeWeekLabel(weekStart) {
  const current = new Date(`${startOfCalendarWeek()}T00:00:00`).getTime();
  const target = new Date(`${weekStart}T00:00:00`).getTime();
  const offset = Math.round((target - current) / (7 * 24 * 60 * 60 * 1000));
  if (offset === 0) return "本周";
  if (offset === -1) return "上周";
  if (offset === 1) return "下周";
  return offset < 0 ? `前${Math.abs(offset)}周` : `后${offset}周`;
}

function renderCalendarLegend(records, dates) {
  const fragment = document.createDocumentFragment();
  const counts = calendarResponseCounts(records);
  CALENDAR_LEGEND.forEach(([label, className]) => {
    const item = document.createElement("span");
    item.className = `calendar-legend-item ${className}`;
    item.title = `${label}：当前四周 ${counts.get(label)} 条状态记录`;
    const dot = document.createElement("i");
    const text = document.createElement("span");
    text.textContent = label;
    const count = document.createElement("strong");
    count.textContent = String(counts.get(label));
    item.append(dot, text, count);
    fragment.appendChild(item);
  });
  const interviewCount = state.calendarFiltered.filter((record) => {
    const date = normalizeInterviewAt(record.contact?.interview_at).slice(0, 10);
    return dates.includes(date);
  }).length;
  const interviewItem = document.createElement("span");
  interviewItem.className = "calendar-legend-item calendar-interview-legend";
  interviewItem.title = `已安排具体面试时间：当前四周 ${interviewCount} 位教师`;
  const diamond = document.createElement("i");
  const label = document.createElement("span");
  label.textContent = "已定时间";
  const count = document.createElement("strong");
  count.textContent = String(interviewCount);
  interviewItem.append(diamond, label, count);
  fragment.appendChild(interviewItem);
  els.calendarLegend.replaceChildren(fragment);
}

function renderCalendarGrid(grouped, dates) {
  const fragment = document.createDocumentFragment();
  const today = localTodayIso();
  for (let weekIndex = 0; weekIndex < 4; weekIndex += 1) {
    const weekDates = dates.slice(weekIndex * 7, weekIndex * 7 + 7);
    const week = document.createElement("section");
    week.className = "calendar-week-strip";
    const weekLabel = document.createElement("div");
    weekLabel.className = "calendar-week-label";
    weekLabel.textContent = relativeWeekLabel(weekDates[0]);
    weekLabel.title = `${formatCalendarDay(weekDates[0], { month: "numeric", day: "numeric" })}—${formatCalendarDay(weekDates[6], { month: "numeric", day: "numeric" })}`;
    const days = document.createElement("div");
    days.className = "calendar-week-days";
    weekDates.forEach((date) => {
      const records = grouped.get(date) || [];
      const day = document.createElement("button");
      day.type = "button";
      day.className = "calendar-strip-day";
      day.dataset.date = date;
      if (date === today) day.classList.add("today");
      if (date === state.selectedCalendarDate) day.classList.add("selected");
      day.setAttribute("aria-pressed", date === state.selectedCalendarDate ? "true" : "false");
      day.title = `${formatCalendarDay(date, { year: "numeric", month: "long", day: "numeric", weekday: "long" })} · ${records.length} 位教师`;
      const heading = document.createElement("span");
      heading.className = "calendar-strip-day-heading";
      heading.textContent = formatCalendarDay(date, { month: "numeric", day: "numeric" });
      const countsNode = document.createElement("span");
      countsNode.className = "calendar-strip-counts";
      const counts = calendarResponseCounts(records);
      CALENDAR_LEGEND.forEach(([label, className]) => {
        const count = counts.get(label);
        if (!count) return;
        const badge = document.createElement("span");
        badge.className = `calendar-status-count ${className}`;
        badge.textContent = String(count);
        badge.title = `${label} ${count}`;
        countsNode.appendChild(badge);
      });
      const interviewCount = records.filter(
        (record) => normalizeInterviewAt(record.contact?.interview_at).slice(0, 10) === date,
      ).length;
      if (interviewCount) {
        const marker = document.createElement("span");
        marker.className = "calendar-interview-marker";
        marker.title = `${interviewCount} 位教师已安排具体面试时间`;
        marker.innerHTML = `<i></i><strong>${interviewCount}</strong>`;
        countsNode.appendChild(marker);
      }
      if (!records.length) {
        const empty = document.createElement("span");
        empty.className = "calendar-strip-empty";
        empty.textContent = "—";
        countsNode.appendChild(empty);
      }
      day.append(heading, countsNode);
      day.addEventListener("click", () => {
        state.selectedCalendarDate = date;
        state.calendarDateInteracted = true;
        renderCalendar();
      });
      days.appendChild(day);
    });
    week.append(weekLabel, days);
    fragment.appendChild(week);
  }
  els.calendarGrid.replaceChildren(fragment);
}

function renderSelectedCalendarDay(grouped) {
  const date = state.selectedCalendarDate;
  const records = grouped.get(date) || [];
  els.calendarSelectedDate.textContent = formatCalendarDay(date, {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  });
  els.calendarSelectedCount.textContent = String(records.length);
  els.calendarSelectedDay.classList.toggle("is-user-selected", state.calendarDateInteracted);
  const fragment = document.createDocumentFragment();
  if (!records.length) {
    const empty = document.createElement("div");
    empty.className = "calendar-empty compact";
    empty.textContent = "当天没有套磁记录";
    fragment.appendChild(empty);
  }
  records.forEach((record) => fragment.appendChild(calendarEventButton(record)));
  els.calendarSelectedTeachers.replaceChildren(fragment);
}

function renderMissingDates() {
  const missing = state.calendarFiltered
    .filter(
      (record) =>
        record.status === "已套磁" &&
        !validDateIso(record.contact?.contacted_at || record.raw[CONTACT_DATE_COLUMN]),
    )
    .sort(compareRecords);
  els.missingDateCount.textContent = String(missing.length);
  els.missingDateSection.hidden = !missing.length;
  const fragment = document.createDocumentFragment();
  if (!missing.length) {
    const empty = document.createElement("div");
    empty.className = "calendar-empty compact";
    empty.textContent = "没有缺少日期的已套磁记录";
    fragment.appendChild(empty);
  }
  missing.forEach((record) => fragment.appendChild(calendarEventButton(record)));
  els.missingDateList.replaceChildren(fragment);
}

function renderCalendar() {
  if (!state.calendarRangeStart) state.calendarRangeStart = startOfCalendarWeek();
  const dates = calendarRangeDates();
  const grouped = recordsByCalendarDate(state.calendarFiltered);
  const rangeRecords = recordsInCalendarRange(dates);
  if (!dates.includes(state.selectedCalendarDate)) {
    const firstWithRecords = dates.find((date) => (grouped.get(date) || []).length);
    state.selectedCalendarDate = dates.includes(localTodayIso()) ? localTodayIso() : firstWithRecords || dates[0];
  }
  const startLabel = formatCalendarDay(dates[0], { year: "numeric", month: "long", day: "numeric" });
  const endLabel = formatCalendarDay(dates[27], { year: "numeric", month: "long", day: "numeric" });
  els.calendarRangeLabel.textContent = `${startLabel}—${endLabel}`;
  els.calendarRangeSummary.textContent = `四周共 ${rangeRecords.length} 位教师 · 日历范围 ${state.calendarFiltered.length} 位教师`;
  els.calendarCollapsedSummary.textContent = `${startLabel}起 · ${rangeRecords.length} 位教师`;
  renderCalendarLegend(rangeRecords, dates);
  renderCalendarProgressOverview();
  renderCalendarGrid(grouped, dates);
  renderSelectedCalendarDay(grouped);
  renderMissingDates();
}

function renderOverview() {
  renderTable();
  renderCalendar();
}

function updateSelectedElements() {
  document.querySelectorAll("[data-record-key]").forEach((element) => {
    const selected = element.dataset.recordKey === state.selectedKey;
    element.classList.toggle("selected", selected);
    if (element.matches("tr")) element.setAttribute("aria-selected", selected ? "true" : "false");
  });
}

function appendTableBatch() {
  if (state.tableRenderLimit >= state.filtered.length) return;
  state.tableRenderLimit = Math.min(state.filtered.length, state.tableRenderLimit + TABLE_BATCH_SIZE);
  renderTable();
}

function td(value, className = "") {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = norm(value);
  cell.title = norm(value);
  return cell;
}

function tdPill(value, className) {
  const cell = document.createElement("td");
  const span = document.createElement("span");
  span.className = `pill ${className}`;
  span.textContent = norm(value);
  cell.appendChild(span);
  return cell;
}

function updateStatus(key, status) {
  const record = state.records.find((item) => item.key === key);
  if (!record) return;
  const entry = normalizeContactEntry(record.contact || state.statusStore.statuses[key] || {});
  const normalizedStatus = normalizeStatus(status);
  if (normalizedStatus) entry.status = normalizedStatus;
  else delete entry.status;
  if (normalizedStatus === "已套磁") {
    if (!entry.contacted_at) entry.contacted_at = localTodayIso();
    if (!entry.responses?.length) entry.responses = ["已发"];
  }
  writeContactEntry(record, entry);
  setDirty(true);
  applyFilters();
  renderCalendar();
}

function writeContactEntry(record, entry) {
  const normalized = normalizeContactEntry(entry);
  applyContactEntryToRecord(record, normalized);
  if (!entryHasData(normalized)) {
    delete state.statusStore.statuses[record.key];
    queueContactSave(record);
    return;
  }
  state.statusStore.statuses[record.key] = {
    ...normalized,
    name: norm(record.raw["姓名"]),
    school: record.schoolSlug,
    college: record.collegeSlug,
    teacher_url: norm(record.raw["教师主页链接"]),
    updated_at: new Date().toISOString().slice(0, 19),
  };
  queueContactSave(record);
}

function updateContactMeta(key, patch, refresh = false) {
  const record = state.records.find((item) => item.key === key);
  if (!record) return;
  const entry = normalizeContactEntry({ ...(record.contact || {}), ...patch });
  writeContactEntry(record, entry);
  setDirty(true);
  if (refresh) applyFilters();
  else {
    renderOverview();
    setSummary();
  }
}

function currentRecord() {
  return state.records.find((record) => record.key === state.selectedKey) || null;
}

function dateInputValue(value) {
  const text = norm(value);
  return /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(0, 10) : "";
}

function datetimeInputValue(value) {
  return normalizeInterviewAt(value);
}

function responseOptions(record) {
  return splitResponses([...DEFAULT_RESPONSES, ...(record.contact?.responses || [])]);
}

function contactEditorSection(record) {
  const entry = normalizeContactEntry(record.contact || {});
  const selected = new Set(entry.responses || []);
  const showInterviewField = selected.has("约面试") || Boolean(entry.interview_at);
  const options = responseOptions(record)
    .map((response) => {
      const checked = selected.has(response) ? " checked" : "";
      return `<label class="response-chip"><input type="checkbox" name="contactResponse" value="${escapeHtml(response)}"${checked} /><span>${escapeHtml(response)}</span></label>`;
    })
    .join("");
  return `
    <section id="detailContact" class="section contact-editor">
      <h2>套磁记录</h2>
      <div class="contact-grid">
        <label>
          <span>套磁时间</span>
          <input id="contactDateInput" type="date" value="${escapeHtml(dateInputValue(entry.contacted_at))}" />
        </label>
        <label id="interviewTimeField"${showInterviewField ? "" : " hidden"}>
          <span>约面试时间</span>
          <input id="interviewTimeInput" type="datetime-local" step="60" value="${escapeHtml(datetimeInputValue(entry.interview_at))}" />
        </label>
        <label>
          <span>回复情况备注</span>
          <textarea id="contactNoteInput" rows="3" placeholder="记录自定义回复、邮件主题、后续动作或判断理由">${escapeHtml(entry.note || "")}</textarea>
        </label>
      </div>
      <div class="response-area">
        <div class="response-list">${options}</div>
      </div>
    </section>
  `;
}

function bindContactEditor(record) {
  const dateInput = els.detailPane.querySelector("#contactDateInput");
  const interviewTimeField = els.detailPane.querySelector("#interviewTimeField");
  const interviewTimeInput = els.detailPane.querySelector("#interviewTimeInput");
  const noteInput = els.detailPane.querySelector("#contactNoteInput");
  const responseInputs = Array.from(els.detailPane.querySelectorAll('input[name="contactResponse"]'));

  dateInput?.addEventListener("change", () => {
    updateContactMeta(record.key, { contacted_at: dateInput.value });
  });
  interviewTimeInput?.addEventListener("change", () => {
    updateContactMeta(record.key, { interview_at: interviewTimeInput.value });
  });
  noteInput?.addEventListener("change", () => {
    updateContactMeta(record.key, { note: noteInput.value });
  });
  responseInputs.forEach((input) => {
    input.addEventListener("change", () => {
      const responses = responseInputs.filter((item) => item.checked).map((item) => item.value);
      const hasInterview = responses.includes("约面试");
      interviewTimeField.hidden = !hasInterview;
      if (!hasInterview) interviewTimeInput.value = "";
      updateContactMeta(record.key, {
        responses,
        interview_at: hasInterview ? interviewTimeInput.value : "",
      });
    });
  });

}

function extraInfoSection(row) {
  const items = affiliationItems(row);
  if (!items.length) return "";
  return `<section id="detailExtra" class="section"><h2>补充信息</h2><div class="info-grid">${items
    .map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`)
    .join("")}</div></section>`;
}

function decisionFact(label, value, className = "") {
  return `<span class="decision-fact ${className}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></span>`;
}

function decisionSection(row) {
  const shouldContact = norm(row["是否建议套磁"]);
  const level = norm(row["推荐等级"]) || "待复核";
  const anchor = norm(row["显式核心锚点"]);
  const identity = norm(row["身份置信度"]);
  const policy = norm(row["评分规则版本"]);
  const warning = norm(row["评分警告"]);
  const reasons = norm(row["推荐理由"])
    .split(/[；;\n]+/)
    .map((item) => norm(item))
    .filter(Boolean);
  let title = "待复核是否适合套磁";
  let stateClass = "decision-review";
  if (shouldContact === "是") {
    title = "适合进入套磁名单";
    stateClass = "decision-positive";
  } else if (shouldContact === "否") {
    title = "暂不建议优先套磁";
    stateClass = "decision-negative";
  }
  const anchorText = anchor === "是" ? "已确认" : anchor ? "未确认" : "旧结果未记录";
  const facts = [
    decisionFact("匹配分", norm(row["匹配分"]) || "—", "fact-score"),
    decisionFact("官方核心锚点", anchorText, anchor === "是" ? "fact-positive" : ""),
    decisionFact("身份置信度", identity || "未记录"),
    decisionFact("评分规则", policy || "旧结果"),
  ].join("");
  const reasonList = reasons.length
    ? `<ul class="reason-list">${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>`
    : '<p class="muted decision-empty">暂无可读推荐理由</p>';
  const warningBox = warning
    ? `<div class="warning-box"><strong>需要复核</strong><span>${escapeHtml(warning)}</span></div>`
    : "";
  return `
    <section id="detailDecision" class="decision-panel ${stateClass}">
      <div class="decision-head">
        <div>
          <div class="decision-label">套磁判断</div>
          <div class="decision-title">${escapeHtml(title)}</div>
        </div>
        <span class="pill ${levelClass(level)}">${escapeHtml(level)}</span>
      </div>
      <div class="decision-facts">${facts}</div>
      ${reasonList}
      ${warningBox}
    </section>
  `;
}

function scoreBreakdownSection(row) {
  const scoreEntries = [
    ["官方", "官方证据分", ""],
    ["DBLP", "DBLP证据分", row["DBLP匹配置信度"]],
    ["数学论文", "论文证据分", row["学术作者匹配置信度"]],
    ["arXiv", "arXiv证据分", row["arXiv置信度"]],
    ["网页", "网页证据分", row["网页状态"]],
    ["搜索", "WebSearch证据分", row["WebSearch置信度"]],
  ];
  const hasStructuredScores = scoreEntries.some(([, field]) => norm(row[field]) !== "");
  const entries = hasStructuredScores
    ? scoreEntries.map(([label, field, meta]) => [label, norm(row[field]) || "0", norm(meta)])
    : [
        ["DBLP论文", norm(row["DBLP近三年论文数"]) || "0", ""],
        ["数学论文", norm(row["近五年论文数"]) || "0", ""],
        ["arXiv论文", norm(row["arXiv近五年论文数"] || row["arXiv近三年论文数"]) || "0", ""],
        ["网页证据", norm(row["网页证据条数"]) || "0", ""],
        ["搜索证据", norm(row["WebSearch证据条数"]) || "0", ""],
      ];
  const title = hasStructuredScores ? "计分构成" : "证据概览";
  return `<section id="detailScores" class="section score-section"><h2>${title}</h2><div class="score-strip">${entries
    .map(
      ([label, value, meta]) =>
        `<div class="score-item"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>${
          meta ? `<small>${escapeHtml(meta)}</small>` : ""
        }</div>`,
    )
    .join("")}</div></section>`;
}

function directionSection(row) {
  const view = directionViewModel(row);
  const groups = view.matchedGroups.length
    ? `<div class="direction-group"><div class="direction-group-label">画像方向分组</div><div class="signal-list">${signalChips(
        view.matchedGroups,
        8,
        "signal-secondary",
      )}</div></div>`
    : "";
  const matched = view.matchedKeywords.length
    ? `<div class="direction-group direction-primary"><div class="direction-group-label">匹配重点</div><div class="signal-list">${signalChips(
        view.matchedKeywords,
        8,
        "signal-primary",
      )}</div></div>`
    : "";
  const official = view.officialItems
    .map(
      ([label, value]) =>
        `<div class="direction-group"><div class="direction-group-label">${escapeHtml(label)}</div><p class="direction-official">${escapeHtml(
          value,
        )}</p></div>`,
    )
    .join("");
  const sources = view.sourceGroups
    .map(
      ([label, terms]) =>
        `<div class="direction-group direction-aux"><div class="direction-group-label">${escapeHtml(
          label,
        )}</div><div class="signal-list">${signalChips(terms, 8, "signal-secondary")}</div></div>`,
    )
    .join("");
  const fallback = !groups && !matched && !official && !sources && view.fallback
    ? `<div class="direction-group"><div class="direction-group-label">历史综合结果</div><p class="direction-official">${escapeHtml(
        view.fallback,
      )}</p></div>`
    : "";
  if (!groups && !matched && !official && !sources && !fallback) return "";
  return `<section id="detailDirection" class="section direction-section"><h2>方向判断</h2>${groups}${matched}${official}${sources}${fallback}</section>`;
}

const DETAIL_JUMP_TARGETS = [
  ["detailDecision", "套磁判断"],
  ["detailScores", "计分构成"],
  ["detailDirection", "方向判断"],
  ["detailContact", "套磁记录"],
  ["detailExtra", "补充信息"],
  ["detailLinks", "链接"],
  ["detailEvidence", "证据明细"],
];

function selectAdjacentTeacher(offset) {
  const currentIndex = state.filtered.findIndex((record) => record.key === state.selectedKey);
  if (currentIndex < 0) return;
  const nextIndex = currentIndex + offset;
  const next = state.filtered[nextIndex];
  if (!next) return;
  state.selectedKey = next.key;
  if (nextIndex >= state.tableRenderLimit) {
    state.tableRenderLimit = Math.min(state.filtered.length, Math.ceil((nextIndex + 1) / TABLE_BATCH_SIZE) * TABLE_BATCH_SIZE);
    renderTable();
  } else {
    updateSelectedElements();
  }
  renderDetail();
  window.requestAnimationFrame(() => {
    document.querySelector(`tr[data-record-key="${CSS.escape(next.key)}"]`)?.scrollIntoView({ block: "nearest" });
  });
}

function bindDetailToolbar() {
  const currentIndex = state.filtered.findIndex((record) => record.key === state.selectedKey);
  const previous = els.detailPane.querySelector("#detailPrev");
  const next = els.detailPane.querySelector("#detailNext");
  if (previous) {
    previous.disabled = currentIndex <= 0;
    previous.addEventListener("click", () => selectAdjacentTeacher(-1));
  }
  if (next) {
    next.disabled = currentIndex < 0 || currentIndex >= state.filtered.length - 1;
    next.addEventListener("click", () => selectAdjacentTeacher(1));
  }

  const jump = els.detailPane.querySelector("#detailJumpSelect");
  if (!jump) return;
  DETAIL_JUMP_TARGETS.forEach(([id, label]) => {
    if (!els.detailPane.querySelector(`#${id}`)) return;
    const option = document.createElement("option");
    option.value = id;
    option.textContent = label;
    jump.appendChild(option);
  });
  jump.disabled = jump.options.length <= 1;
  jump.addEventListener("change", () => {
    const target = jump.value ? els.detailPane.querySelector(`#${jump.value}`) : null;
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
    jump.value = "";
  });
}

function renderDetail() {
  const record = currentRecord();
  if (!record) {
    els.detailPane.innerHTML = `${detailToolbar()}<div class="empty-detail">选择一位教师</div>`;
    bindDetailToolbar();
    applySidebarState();
    return;
  }
  const row = record.raw;
  const shouldLoadDetails = !record.detailsLoaded && !record.detailsLoading && !record.detailsError;
  if (shouldLoadDetails) record.detailsLoading = true;
  els.detailPane.innerHTML = `
    ${detailToolbar()}
    <div class="detail-head">
      <div>
        <div class="detail-name">${escapeHtml(row["姓名"])}</div>
        <div class="detail-subtitle">${escapeHtml(record.schoolName)} · ${escapeHtml(record.collegeName)} · ${escapeHtml(row["职称"])}</div>
      </div>
      <div id="detailStatus"></div>
    </div>
    ${decisionSection(row)}
    ${scoreBreakdownSection(row)}
    ${directionSection(row)}
    ${contactEditorSection(record)}
    ${extraInfoSection(row)}
    ${linksSection(row)}
    <div id="detailEvidence">${detailEvidenceSections(record)}</div>
  `;
  els.detailPane.querySelector("#detailStatus").appendChild(contactSelect(record));
  bindContactEditor(record);
  bindDetailToolbar();
  applySidebarState();
  if (shouldLoadDetails) loadRecordDetails(record);
}

function detailEvidenceSections(record) {
  if (record.detailsLoading) {
    return '<section class="section detail-loading">正在加载论文与网页证据…</section>';
  }
  if (record.detailsError) {
    return `<section class="section detail-error">证据加载失败：${escapeHtml(record.detailsError)}</section>`;
  }
  if (!record.detailsLoaded) return "";
  return [
    evidenceSection("DBLP近三年", record.dblp, ["年份", "venue", "题名", "链接"]),
    evidenceSection("数学文献近五年", record.publication, ["来源", "作者身份置信度", "是否计入匹配", "年份", "题名", "分类", "主题", "证据URL"]),
    evidenceSection("学术作者候选", record.publicationCandidates, ["来源", "候选排名", "候选作者ID", "候选状态", "身份置信度", "候选决策", "是否需人工复核", "证据信号", "冲突原因"]),
    evidenceSection("论文来源状态", record.publicationSources, ["来源", "阶段", "状态", "来源健康度", "原始记录数", "接受记录数", "是否截断", "原因"]),
    evidenceSection("arXiv近年", record.arxiv, ["发布日期", "题名", "分类", "链接"]),
    evidenceSection("网页证据", record.web, ["网页URL", "证据"]),
    evidenceSection("WebSearch证据", record.webSearch, ["WebSearch置信度", "来源类型", "标题", "证据", "关键词", "来源URL"]),
  ].join("");
}

async function loadRecordDetails(record) {
  const profileId = state.currentProfileId;
  try {
    const response = await fetch(`/api/detail?profile=${encodeURIComponent(profileId)}&key=${encodeURIComponent(record.key)}`, { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `请求失败：${response.status}`);
    record.dblp = data.dblp || [];
    record.publication = data.publication || [];
    record.publicationCandidates = data.publicationCandidates || [];
    record.publicationSources = data.publicationSources || [];
    record.arxiv = data.arxiv || [];
    record.web = data.web || [];
    record.webSearch = data.webSearch || [];
    record.detailsLoaded = true;
    record.detailsError = "";
  } catch (error) {
    record.detailsError = error.message || String(error);
  } finally {
    record.detailsLoading = false;
    if (state.currentProfileId === profileId && state.selectedKey === record.key) renderDetail();
  }
}

function linksSection(row) {
  const links = [
    ["教师主页", row["教师主页链接"]],
    ["个人主页", row["个人主页"]],
    ["DBLP作者", row["DBLP作者链接"]],
    ["zbMATH作者", row["zbMATH作者链接"]],
    ["OpenAlex作者", row["OpenAlex作者链接"]],
  ].filter(([, url]) => safeUrl(url));
  if (!links.length) return "";
  return `<section id="detailLinks" class="section"><h2>链接</h2><div class="link-list">${links
    .map(([label, url]) => `<a href="${escapeHtml(safeUrl(url))}" target="_blank" rel="noreferrer">${escapeHtml(label)} · ${escapeHtml(url)}</a>`)
    .join("")}</div></section>`;
}

function evidenceSection(title, rows, fields) {
  if (!rows.length) return "";
  const items = rows.slice(0, 8).map((row) => {
    const meta = fields
      .filter((field) => field !== "题名" && field !== "证据")
      .map((field) => norm(row[field]))
      .filter(Boolean)
      .join(" · ");
    const main = norm(row["题名"] || row["标题"] || row["证据"] || row["链接"] || row["证据URL"] || row["网页URL"] || row["来源URL"]);
    const link = safeUrl(row["链接"] || row["证据URL"] || row["网页URL"] || row["来源URL"]);
    const body = link
      ? `<a href="${escapeHtml(link)}" target="_blank" rel="noreferrer">${escapeHtml(main || link)}</a>`
      : escapeHtml(main);
    return `<div class="evidence-item"><div class="evidence-meta">${escapeHtml(meta)}</div><div>${body}</div></div>`;
  });
  return `<details class="section evidence-section"><summary><span>${escapeHtml(title)}</span><span class="evidence-count">${rows.length} 条</span></summary><div class="evidence-list">${items.join("")}</div></details>`;
}

function bindEvents() {
  els.profileSelector.addEventListener("change", () => switchProfile(els.profileSelector.value));
  els.tablePane.addEventListener("scroll", () => {
    const remaining = els.tablePane.scrollHeight - els.tablePane.scrollTop - els.tablePane.clientHeight;
    if (remaining < 240) appendTableBatch();
  });
  els.detailToggle.addEventListener("click", () => setSidebarCollapsed(!state.sidebarCollapsed));
  els.calendarToggle.addEventListener("click", () => setCalendarCollapsed(!state.calendarCollapsed));
  els.calendarPrev.addEventListener("click", () => {
    state.calendarRangeStart = addCalendarDays(state.calendarRangeStart, -7);
    state.selectedCalendarDate = "";
    state.calendarDateInteracted = false;
    renderCalendar();
  });
  els.calendarToday.addEventListener("click", () => {
    state.calendarRangeStart = startOfCalendarWeek();
    state.selectedCalendarDate = localTodayIso();
    state.calendarDateInteracted = false;
    renderCalendar();
  });
  els.calendarNext.addEventListener("click", () => {
    state.calendarRangeStart = addCalendarDays(state.calendarRangeStart, 7);
    state.selectedCalendarDate = "";
    state.calendarDateInteracted = false;
    renderCalendar();
  });
  els.calendarSchoolFilter.addEventListener("input", () => {
    populateCalendarCollegeFilter();
    applyCalendarFilters();
  });
  els.calendarCollegeFilter.addEventListener("input", applyCalendarFilters);
  els.calendarFilterReset.addEventListener("click", resetCalendarFilters);
  els.schoolFilter.addEventListener("input", () => {
    populateCollegeFilter();
    applyFilters();
  });
  let searchTimer = 0;
  els.searchInput.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(applyFilters, SEARCH_DEBOUNCE_MS);
  });
  [
    els.collegeFilter,
    els.levelFilter,
    els.contactFilter,
    els.contactedOnly,
    els.hideContacted,
    els.weakEvidenceOnly,
  ].forEach((element) => element.addEventListener("input", applyFilters));
  els.listFilterReset.addEventListener("click", resetListFilters);
  window.addEventListener("keydown", (event) => {
    const target = event.target;
    const isEditing = target instanceof HTMLElement
      && (target.matches("input, select, textarea") || target.isContentEditable);
    if (isEditing || !event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.key === "ArrowUp") {
      event.preventDefault();
      selectAdjacentTeacher(-1);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      selectAdjacentTeacher(1);
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
  window.addEventListener("resize", applySidebarState);
}

async function init() {
  state.calendarRangeStart = startOfCalendarWeek();
  state.selectedCalendarDate = localTodayIso();
  state.sidebarCollapsed = readSidebarPreference();
  state.calendarCollapsed = readCalendarPreference();
  bindEvents();
  populateFilters();
  renderOverview();
  renderDetail();
  applyCalendarState();
  setSummary();
  try {
    await loadFromApi();
  } catch (error) {
    showToast(`本地服务不可用：${error.message}`);
  }
}

init();
