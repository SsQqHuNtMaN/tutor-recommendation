const STATUS_COLUMN = "套磁情况";
const CONTACT_DATE_COLUMN = "套磁时间";
const CONTACT_RESPONSE_COLUMN = "回复情况";
const CONTACT_NOTE_COLUMN = "回复情况备注";
const LEGACY_CONTACT_NOTE_COLUMNS = ["套磁备注"];
const VALID_STATUSES = ["已套磁", "先不考虑", "不可能", "不匹配"];
const LEGACY_STATUS_ALIASES = { 不考虑: "先不考虑" };
const DEFAULT_RESPONSES = ["已发", "官回", "添加微信", "约面试", "考核", "已满"];
const FINAL_FILE_PATTERN = /_teacher_match_full_research\.xlsx$/i;

const SCHOOL_NAMES = {
  sjtu: "上海交通大学",
  nju: "南京大学",
  ruc: "中国人民大学",
  fudan: "复旦大学",
  seu: "东南大学",
  tongji: "同济大学",
  ustc: "中国科学技术大学",
};

const COLLEGE_NAMES = {
  "sjtu/cs": "计算机学院",
  "sjtu/ai": "人工智能学院",
  "nju/cs": "计算机学院",
  "nju/ai": "人工智能学院",
  "nju/ra": "机器人与自动化学院",
  "nju/is": "智能科学与技术学院",
  "nju/ic": "集成电路学院",
  "ruc/gsai": "高瓴人工智能学院",
  "ruc/ssai": "苏州人工智能学院",
  "fudan/ciram": "智能机器人与先进制造创新学院",
  "fudan/ai": "计算与智能创新学院",
  "seu/joint": "三院联合导师名单",
  "seu/cs": "计算机科学系",
  "seu/ce": "计算机工程系",
  "seu/imaging": "影像科学与技术系",
  "tongji/cs": "计算机科学与技术学院",
  "tongji/see": "电子与信息工程学院",
  "ustc/ai_ds": "人工智能与数据科学学院",
};

const state = {
  apiMode: false,
  csrfToken: "",
  outputsHandle: null,
  statusHandle: null,
  statusStore: { version: 3, updated_at: "", statuses: {} },
  records: [],
  filtered: [],
  selectedKey: "",
  viewMode: "all",
  dirty: false,
  pendingSaves: 0,
  saveFailures: 0,
  saveQueue: Promise.resolve(),
};

const $ = (id) => document.getElementById(id);

const els = {
  pickOutputs: $("pickOutputs"),
  fileInput: $("fileInput"),
  statusInput: $("statusInput"),
  saveStatus: $("saveStatus"),
  syncExcel: $("syncExcel"),
  downloadStatus: $("downloadStatus"),
  exportXlsx: $("exportXlsx"),
  summary: $("summary"),
  viewTabs: $("viewTabs"),
  searchInput: $("searchInput"),
  schoolFilter: $("schoolFilter"),
  collegeFilter: $("collegeFilter"),
  levelFilter: $("levelFilter"),
  contactFilter: $("contactFilter"),
  minScore: $("minScore"),
  priorityOnly: $("priorityOnly"),
  hideContacted: $("hideContacted"),
  weakEvidenceOnly: $("weakEvidenceOnly"),
  teacherRows: $("teacherRows"),
  detailPane: $("detailPane"),
};

function norm(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/\s+/g, " ").trim();
}

function numberValue(value) {
  const parsed = Number(norm(value));
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalizeStatus(value) {
  const text = norm(value);
  const mapped = LEGACY_STATUS_ALIASES[text] || text;
  return VALID_STATUSES.includes(mapped) ? mapped : "";
}

function splitResponses(value) {
  const source = Array.isArray(value) ? value : norm(value).replace(/[；;、,]/g, "|").split("|");
  const seen = new Set();
  const responses = [];
  source.forEach((item) => {
    const response = norm(item);
    if (!response || seen.has(response)) return;
    seen.add(response);
    responses.push(response);
  });
  return responses;
}

function joinResponses(value) {
  return splitResponses(value).join("；");
}

function uniqueJoinText(values) {
  const seen = new Set();
  const output = [];
  values.map(norm).forEach((value) => {
    if (!value || seen.has(value)) return;
    seen.add(value);
    output.push(value);
  });
  return output.join("；");
}

function splitKnownAndCustomResponses(value) {
  const known = [];
  const custom = [];
  splitResponses(value).forEach((response) => {
    if (DEFAULT_RESPONSES.includes(response)) known.push(response);
    else custom.push(response);
  });
  return { known, custom };
}

function normalizeContactEntry(value) {
  if (typeof value === "string") {
    const status = normalizeStatus(value);
    return status ? { status, responses: [] } : { responses: [] };
  }
  if (!value || typeof value !== "object") return { responses: [] };
  const responseParts = splitKnownAndCustomResponses(
    value.responses || value.reply_statuses || value[CONTACT_RESPONSE_COLUMN],
  );
  const entry = {
    status: normalizeStatus(value.status || value.contactStatus || value[STATUS_COLUMN]),
    contacted_at: norm(value.contacted_at || value.contactedAt || value.date || value[CONTACT_DATE_COLUMN]),
    responses: responseParts.known,
    note: uniqueJoinText([
      value.note,
      value.contact_note,
      value[CONTACT_NOTE_COLUMN],
      ...LEGACY_CONTACT_NOTE_COLUMNS.map((column) => value[column]),
      joinResponses(responseParts.custom),
    ]),
    name: norm(value.name),
    school: norm(value.school),
    college: norm(value.college),
    teacher_url: norm(value.teacher_url),
    updated_at: norm(value.updated_at || value.updatedAt),
  };
  return Object.fromEntries(Object.entries(entry).filter(([, item]) => (Array.isArray(item) ? item.length : item)));
}

function contactEntryFromRow(row) {
  return normalizeContactEntry({
    status: row[STATUS_COLUMN],
    contacted_at: row[CONTACT_DATE_COLUMN],
    responses: row[CONTACT_RESPONSE_COLUMN],
    note: row[CONTACT_NOTE_COLUMN],
    ...Object.fromEntries(LEGACY_CONTACT_NOTE_COLUMNS.map((column) => [column, row[column]])),
  });
}

function mergeContactEntries(base, override) {
  const merged = { ...base, ...override };
  if (!override.responses?.length) merged.responses = base.responses || [];
  return normalizeContactEntry(merged);
}

function entryHasData(entry) {
  const normalized = normalizeContactEntry(entry);
  return Boolean(normalized.status || normalized.contacted_at || normalized.responses?.length || normalized.note);
}

function targetKey(schoolSlug, collegeSlug) {
  return `${schoolSlug}/${collegeSlug}`;
}

function makeKey(record) {
  const row = record.raw || record;
  const name = norm(row["姓名"]);
  const teacherUrl = norm(row["教师主页链接"]);
  const personalUrl = norm(row["个人主页"]);
  return `${targetKey(record.schoolSlug, record.collegeSlug)}|${name}|${teacherUrl || personalUrl}`;
}

function escapeHtml(value) {
  return norm(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function safeUrl(value) {
  const url = norm(value);
  if (!/^https?:\/\//i.test(url)) return "";
  return url;
}

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

function setApiMode(enabled) {
  state.apiMode = enabled;
  els.pickOutputs.textContent = enabled ? "刷新" : "打开";
  els.pickOutputs.title = enabled ? "从本地服务重新加载 outputs" : "选择 outputs 目录";
  els.fileInput.closest(".file-button").style.display = enabled ? "none" : "";
  els.statusInput.closest(".file-button").style.display = enabled ? "none" : "";
  els.saveStatus.title = enabled ? "保存到 outputs/contact_status.json" : "保存 contact_status.json";
  els.syncExcel.style.display = enabled ? "" : "none";
}

function setSummary() {
  const total = state.records.length;
  const shown = state.filtered.length;
  const contacted = state.records.filter((record) => record.status === "已套磁").length;
  const blocked = state.records.filter((record) =>
    ["先不考虑", "不可能", "不匹配"].includes(record.status),
  ).length;
  const viewLabel = state.viewMode === "contacted" ? "已套磁视图 · " : "";
  els.summary.textContent = total
    ? `${viewLabel}${shown}/${total} 位教师 · 已套磁 ${contacted} · 排除 ${blocked}`
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
  if (!state.apiMode) return;
  const payload = { key: record.key, entry: contactPayload(record) };
  state.pendingSaves += 1;
  setDirty(true);
  state.saveQueue = state.saveQueue
    .catch(() => {})
    .then(async () => {
      const data = await postJson("/api/contact", payload);
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

function parseTargetFromPath(path, fileName) {
  const normalized = path.replaceAll("\\", "/");
  const parts = normalized.split("/").filter(Boolean);
  const outputIndex = parts.indexOf("outputs");
  if (outputIndex >= 0 && parts.length > outputIndex + 2) {
    return { schoolSlug: parts[outputIndex + 1], collegeSlug: parts[outputIndex + 2] };
  }
  if (parts.length >= 3) {
    const filePart = parts[parts.length - 1];
    if (FINAL_FILE_PATTERN.test(filePart)) {
      return { schoolSlug: parts[parts.length - 3], collegeSlug: parts[parts.length - 2] };
    }
  }
  const match = fileName.match(/^([^_]+)_(.+)_teacher_match_full_research\.xlsx$/i);
  if (match) return { schoolSlug: match[1], collegeSlug: match[2] };
  return { schoolSlug: "", collegeSlug: "" };
}

function sheetRows(workbook, sheetName) {
  const sheet = workbook.Sheets[sheetName];
  if (!sheet) return [];
  return XLSX.utils.sheet_to_json(sheet, { defval: "", raw: false });
}

function buildRecord(raw, meta, details) {
  const record = {
    schoolSlug: meta.schoolSlug,
    collegeSlug: meta.collegeSlug,
    schoolName: SCHOOL_NAMES[meta.schoolSlug] || meta.schoolSlug,
    collegeName: COLLEGE_NAMES[targetKey(meta.schoolSlug, meta.collegeSlug)] || meta.collegeSlug,
    sourcePath: meta.path,
    raw: { ...raw },
    dblp: [],
    arxiv: [],
    web: [],
    webSearch: [],
    contact: {},
    status: "",
    key: "",
  };
  record.key = makeKey(record);
  applyContactEntryToRecord(record, contactEntryForRecord(record));

  const name = norm(raw["姓名"]);
  const teacherUrl = norm(raw["教师主页链接"]);
  record.dblp = details.dblp.filter((item) => sameTeacher(item, name, teacherUrl));
  record.arxiv = details.arxiv.filter((item) => sameTeacher(item, name, teacherUrl));
  record.web = details.web.filter((item) => sameTeacher(item, name, teacherUrl));
  record.webSearch = details.webSearch.filter((item) => sameTeacher(item, name, teacherUrl));
  return record;
}

function sameTeacher(item, name, teacherUrl) {
  if (norm(item["姓名"]) !== name) return false;
  const itemTeacherUrl = norm(item["教师主页链接"]);
  return !itemTeacherUrl || !teacherUrl || itemTeacherUrl === teacherUrl;
}

async function readWorkbookFile(file, path) {
  if (!FINAL_FILE_PATTERN.test(file.name) || file.name.startsWith("~$")) return [];
  const meta = parseTargetFromPath(path, file.name);
  if (!meta.schoolSlug || !meta.collegeSlug) return [];
  meta.path = path;
  const data = await file.arrayBuffer();
  const workbook = XLSX.read(data, { type: "array" });
  const rows = sheetRows(workbook, "全量教师名录");
  const details = {
    dblp: sheetRows(workbook, "DBLP近三年明细").concat(sheetRows(workbook, "DBLP近三年论文明细")),
    arxiv: sheetRows(workbook, "arXiv近三年明细"),
    web: sheetRows(workbook, "网页证据明细"),
    webSearch: sheetRows(workbook, "WebSearch证据明细"),
  };
  return rows.map((row) => buildRecord(row, meta, details));
}

async function walkDirectory(handle, prefix = "") {
  const files = [];
  for await (const [name, entry] of handle.entries()) {
    const path = prefix ? `${prefix}/${name}` : name;
    if (entry.kind === "directory") {
      files.push(...(await walkDirectory(entry, path)));
    } else if (entry.kind === "file") {
      files.push({ handle: entry, path });
    }
  }
  return files;
}

async function getOutputsHandle(rootHandle) {
  if (rootHandle.name === "outputs") return rootHandle;
  try {
    return await rootHandle.getDirectoryHandle("outputs");
  } catch {
    return rootHandle;
  }
}

async function loadStatusFromHandle(outputsHandle) {
  try {
    const handle = await outputsHandle.getFileHandle("contact_status.json", { create: false });
    const file = await handle.getFile();
    const text = await file.text();
    state.statusStore = normalizeStore(JSON.parse(text));
    state.statusHandle = handle;
  } catch {
    state.statusStore = { version: 3, updated_at: "", statuses: {} };
    state.statusHandle = null;
  }
}

function normalizeStore(data) {
  const store = { version: 2, updated_at: "", statuses: {} };
  if (!data || typeof data !== "object") return store;
  store.version = Math.max(Number(data.version || 1), 2);
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
  state.selectedKey = state.records[0]?.key || "";
  populateFilters();
  applyFilters();
  setDirty(false);
}

async function openOutputsDirectory() {
  if (!window.showDirectoryPicker) {
    showToast("当前浏览器不支持目录授权");
    return;
  }
  const rootHandle = await window.showDirectoryPicker({ mode: "readwrite" });
  const outputsHandle = await getOutputsHandle(rootHandle);
  state.outputsHandle = outputsHandle;
  await loadStatusFromHandle(outputsHandle);
  const files = await walkDirectory(outputsHandle);
  const records = [];
  for (const item of files) {
    if (!FINAL_FILE_PATTERN.test(item.path)) continue;
    const file = await item.handle.getFile();
    records.push(...(await readWorkbookFile(file, item.path)));
  }
  mergeLoadedRecords(records);
  showToast(`已加载 ${records.length} 位教师`);
}

async function handleFileInput(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;
  const jsonFile = files.find((file) => file.name === "contact_status.json");
  if (jsonFile) {
    const text = await jsonFile.text();
    state.statusStore = normalizeStore(JSON.parse(text));
  }
  const records = [];
  for (const file of files) {
    const path = file.webkitRelativePath || file.name;
    records.push(...(await readWorkbookFile(file, path)));
  }
  mergeLoadedRecords(records);
  showToast(`已加载 ${records.length} 位教师`);
}

async function handleStatusInput(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const text = await file.text();
  state.statusStore = normalizeStore(JSON.parse(text));
  mergeLoadedRecords(state.records);
  showToast("状态已导入");
}

async function loadFromApi() {
  const sessionResponse = await fetch("/api/session", { cache: "no-store" });
  if (sessionResponse.status === 404) {
    throw new Error("当前运行的是旧版看板服务，请关闭旧服务后重新运行 start_viewer.bat");
  }
  if (!sessionResponse.ok) throw new Error(`会话初始化失败：${sessionResponse.status}`);
  const session = await sessionResponse.json();
  state.csrfToken = norm(session.token);
  if (!state.csrfToken) throw new Error("会话令牌缺失");
  const response = await fetch("/api/data", { cache: "no-store" });
  if (!response.ok) throw new Error(`加载失败：${response.status}`);
  const data = await response.json();
  state.statusStore = normalizeStore(data.statusStore || {});
  const records = (data.records || []).map((record) => ({
    schoolSlug: record.schoolSlug,
    collegeSlug: record.collegeSlug,
    schoolName: record.schoolName,
    collegeName: record.collegeName,
    sourcePath: record.sourcePath,
    raw: record.raw || {},
    dblp: record.dblp || [],
    arxiv: record.arxiv || [],
    web: record.web || [],
    webSearch: record.webSearch || [],
    contact: normalizeContactEntry(record.contact || {}),
    status: normalizeStatus(record.status),
    key: record.key,
  }));
  mergeLoadedRecords(records);
  showToast(`已从 outputs 加载 ${records.length} 位教师`);
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

function populateFilters() {
  populateSelect(
    els.schoolFilter,
    [...new Set(state.records.map((record) => record.schoolName).filter(Boolean))].sort(),
    "全部学校",
  );
  populateCollegeFilter();
  populateSelect(els.levelFilter, ["强烈建议", "可以考虑", "暂不优先"], "全部推荐");
  populateSelect(els.contactFilter, VALID_STATUSES, "全部状态");
}

function renderViewTabs() {
  const buttons = Array.from(els.viewTabs.querySelectorAll("button[data-view]"));
  buttons.forEach((button) => {
    const active = button.dataset.view === state.viewMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  els.contactFilter.disabled = state.viewMode === "contacted";
  els.hideContacted.disabled = state.viewMode === "contacted";
}

function setViewMode(viewMode) {
  state.viewMode = viewMode;
  renderViewTabs();
  applyFilters();
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
  const arxiv = numberValue(record.raw["arXiv近三年论文数"]);
  const web = numberValue(record.raw["网页证据条数"]);
  const webSearch = numberValue(record.raw["WebSearch证据条数"]);
  return dblp + arxiv + web + webSearch <= 1;
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
    row["arXiv关键词"],
    row["网页关键词"],
    row["WebSearch关键词"],
    row["WebSearch代表证据"],
    row["WebSearch建议"],
    row["推荐理由"],
    record.raw[CONTACT_DATE_COLUMN],
    record.raw[CONTACT_RESPONSE_COLUMN],
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
  const status = state.viewMode === "contacted" ? "" : els.contactFilter.value;
  const minScore = numberValue(els.minScore.value);
  const priorityOnly = els.priorityOnly.checked;
  const hideMarked = state.viewMode !== "contacted" && els.hideContacted.checked;
  const weakOnly = els.weakEvidenceOnly.checked;

  state.filtered = state.records.filter((record) => {
    const row = record.raw;
    if (query && !searchableText(record).includes(query)) return false;
    if (state.viewMode === "contacted" && record.status !== "已套磁") return false;
    if (hideMarked && record.status) return false;
    if (school && record.schoolName !== school) return false;
    if (college && record.collegeName !== college) return false;
    if (level && norm(row["推荐等级"]) !== level) return false;
    if (status && record.status !== status) return false;
    if (minScore && numberValue(row["匹配分"]) < minScore) return false;
    if (priorityOnly && norm(row["是否建议套磁"]) !== "是") return false;
    if (weakOnly && !isWeakEvidence(record)) return false;
    return true;
  });
  if (!state.filtered.some((record) => record.key === state.selectedKey)) {
    state.selectedKey = state.filtered[0]?.key || "";
  }
  renderTable();
  renderDetail();
  setSummary();
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
  const officialItems = uniqueParts([
    ["教师主页", row["研究方向"]],
    ["导师信息库", row["导师信息库研究方向"]],
    ["官方团队材料", row["团队PDF证据"]],
  ]);
  const seen = new Set(matchedKeywords.map(canonicalSignal));
  const sourceGroups = [
    ["DBLP", uniqueSignals([row["DBLP近三年关键词"]], seen)],
    ["arXiv", uniqueSignals([row["arXiv关键词"]], seen)],
    ["网页", uniqueSignals([row["网页关键词"]], seen)],
    ["搜索补充", uniqueSignals([row["WebSearch关键词"]], seen)],
  ].filter(([, terms]) => terms.length);
  const fallback = norm(
    row["综合研究方向（主页+DBLP+arXiv+网页）"] || row["综合研究方向（主页+DBLP）"],
  );
  return { matchedKeywords, officialItems, sourceGroups, fallback };
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
    ["回复备注", entry.note],
  ])
    .map(([label, value]) => `${label}: ${value}`)
    .join("；");
}

function renderTable() {
  const fragment = document.createDocumentFragment();
  state.filtered.forEach((record) => {
    const row = record.raw;
    const tr = document.createElement("tr");
    if (record.key === state.selectedKey) tr.classList.add("selected");
    tr.addEventListener("click", () => {
      state.selectedKey = record.key;
      renderTable();
      renderDetail();
    });

    tr.appendChild(td(row["姓名"], "cell-main"));
    const statusTd = document.createElement("td");
    statusTd.appendChild(contactSelect(record));
    tr.appendChild(statusTd);
    tr.appendChild(institutionCell(record));
    tr.appendChild(tdPill(row["推荐等级"], levelClass(norm(row["推荐等级"]))));
    tr.appendChild(td(row["匹配分"]));
    tr.appendChild(matchCell(row));
    tr.appendChild(reviewCell(row));
    tr.appendChild(td(contactSummary(record), "cell-note"));
    fragment.appendChild(tr);
  });
  els.teacherRows.replaceChildren(fragment);
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
  if (normalizedStatus === "已套磁" && !entry.responses?.length) entry.responses = ["已发"];
  writeContactEntry(record, entry);
  setDirty(true);
  applyFilters();
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
  renderTable();
  setSummary();
  if (refresh) renderDetail();
}

function currentRecord() {
  return state.records.find((record) => record.key === state.selectedKey) || null;
}

function dateInputValue(value) {
  const text = norm(value);
  return /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(0, 10) : "";
}

function responseOptions(record) {
  return splitResponses([...DEFAULT_RESPONSES, ...(record.contact?.responses || [])]);
}

function contactEditorSection(record) {
  const entry = normalizeContactEntry(record.contact || {});
  const selected = new Set(entry.responses || []);
  const options = responseOptions(record)
    .map((response) => {
      const checked = selected.has(response) ? " checked" : "";
      return `<label class="response-chip"><input type="checkbox" name="contactResponse" value="${escapeHtml(response)}"${checked} /><span>${escapeHtml(response)}</span></label>`;
    })
    .join("");
  return `
    <section class="section contact-editor">
      <h2>套磁记录</h2>
      <div class="contact-grid">
        <label>
          <span>套磁时间</span>
          <input id="contactDateInput" type="date" value="${escapeHtml(dateInputValue(entry.contacted_at))}" />
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
  const noteInput = els.detailPane.querySelector("#contactNoteInput");
  const responseInputs = Array.from(els.detailPane.querySelectorAll('input[name="contactResponse"]'));

  dateInput?.addEventListener("change", () => {
    updateContactMeta(record.key, { contacted_at: dateInput.value });
  });
  noteInput?.addEventListener("change", () => {
    updateContactMeta(record.key, { note: noteInput.value });
  });
  responseInputs.forEach((input) => {
    input.addEventListener("change", () => {
      const responses = responseInputs.filter((item) => item.checked).map((item) => item.value);
      updateContactMeta(record.key, { responses });
    });
  });

}

function extraInfoSection(row) {
  const items = affiliationItems(row);
  if (!items.length) return "";
  return `<section class="section"><h2>补充信息</h2><div class="info-grid">${items
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
    <section class="decision-panel ${stateClass}">
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
    ["arXiv", "arXiv证据分", row["arXiv置信度"]],
    ["网页", "网页证据分", row["网页状态"]],
    ["搜索", "WebSearch证据分", row["WebSearch置信度"]],
  ];
  const hasStructuredScores = scoreEntries.some(([, field]) => norm(row[field]) !== "");
  const entries = hasStructuredScores
    ? scoreEntries.map(([label, field, meta]) => [label, norm(row[field]) || "0", norm(meta)])
    : [
        ["DBLP论文", norm(row["DBLP近三年论文数"]) || "0", ""],
        ["arXiv论文", norm(row["arXiv近三年论文数"]) || "0", ""],
        ["网页证据", norm(row["网页证据条数"]) || "0", ""],
        ["搜索证据", norm(row["WebSearch证据条数"]) || "0", ""],
      ];
  const title = hasStructuredScores ? "计分构成" : "证据概览";
  return `<section class="section score-section"><h2>${title}</h2><div class="score-strip">${entries
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
  const fallback = !matched && !official && !sources && view.fallback
    ? `<div class="direction-group"><div class="direction-group-label">历史综合结果</div><p class="direction-official">${escapeHtml(
        view.fallback,
      )}</p></div>`
    : "";
  if (!matched && !official && !sources && !fallback) return "";
  return `<section class="section direction-section"><h2>方向判断</h2>${matched}${official}${sources}${fallback}</section>`;
}

function renderDetail() {
  const record = currentRecord();
  if (!record) {
    els.detailPane.innerHTML = '<div class="empty-detail">选择一位教师</div>';
    return;
  }
  const row = record.raw;
  els.detailPane.innerHTML = `
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
    ${evidenceSection("DBLP近三年", record.dblp, ["年份", "venue", "题名", "链接"])}
    ${evidenceSection("arXiv近三年", record.arxiv, ["发布日期", "题名", "分类", "链接"])}
    ${evidenceSection("网页证据", record.web, ["网页URL", "证据"])}
    ${evidenceSection("WebSearch证据", record.webSearch, ["WebSearch置信度", "来源类型", "标题", "证据", "关键词", "来源URL"])}
  `;
  els.detailPane.querySelector("#detailStatus").appendChild(contactSelect(record));
  bindContactEditor(record);
}

function linksSection(row) {
  const links = [
    ["教师主页", row["教师主页链接"]],
    ["个人主页", row["个人主页"]],
    ["DBLP作者", row["DBLP作者链接"]],
  ].filter(([, url]) => safeUrl(url));
  if (!links.length) return "";
  return `<section class="section"><h2>链接</h2><div class="link-list">${links
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
    const main = norm(row["题名"] || row["标题"] || row["证据"] || row["链接"] || row["网页URL"] || row["来源URL"]);
    const link = safeUrl(row["链接"] || row["网页URL"] || row["来源URL"]);
    const body = link
      ? `<a href="${escapeHtml(link)}" target="_blank" rel="noreferrer">${escapeHtml(main || link)}</a>`
      : escapeHtml(main);
    return `<div class="evidence-item"><div class="evidence-meta">${escapeHtml(meta)}</div><div>${body}</div></div>`;
  });
  return `<details class="section evidence-section"><summary><span>${escapeHtml(title)}</span><span class="evidence-count">${rows.length} 条</span></summary><div class="evidence-list">${items.join("")}</div></details>`;
}

function statusJson() {
  state.statusStore.version = 3;
  state.statusStore.statuses = Object.fromEntries(
    Object.entries(state.statusStore.statuses || {})
      .map(([key, value]) => [key, normalizeContactEntry(value)])
      .filter(([, value]) => entryHasData(value)),
  );
  state.statusStore.updated_at = new Date().toISOString().slice(0, 19);
  return JSON.stringify(state.statusStore, null, 2);
}

async function saveStatus() {
  if (state.apiMode) {
    await state.saveQueue.catch(() => {});
    const store = JSON.parse(statusJson());
    const data = await postJson("/api/status-store", { statusStore: store });
    state.statusStore = normalizeStore(data.statusStore || store);
    state.pendingSaves = 0;
    state.saveFailures = 0;
    setDirty(false);
    showToast("状态已保存到 outputs/contact_status.json");
    return;
  }
  if (state.outputsHandle && !state.statusHandle) {
    state.statusHandle = await state.outputsHandle.getFileHandle("contact_status.json", { create: true });
  }
  if (!state.statusHandle) {
    downloadStatus();
    return;
  }
  const writable = await state.statusHandle.createWritable();
  await writable.write(statusJson());
  await writable.close();
  setDirty(false);
  showToast("状态已保存");
}

async function syncExcel() {
  if (!state.apiMode) {
    showToast("请通过 python viewer_server.py 打开网页后同步 Excel");
    return;
  }
  await saveStatus();
  const result = await postJson("/api/sync-excel", {});
  const changed = result.synced?.length || 0;
  const total = result.workbooks || 0;
  showToast(`已同步 ${changed}/${total} 个工作簿`);
}

function downloadStatus() {
  downloadBlob(new Blob([statusJson()], { type: "application/json;charset=utf-8" }), "contact_status.json");
  setDirty(false);
}

function downloadBlob(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function exportFilteredXlsx() {
  if (!state.filtered.length) {
    showToast("没有可导出的行");
    return;
  }
  const rows = state.filtered.map((record) => ({
    学校: record.schoolName,
    学院: record.collegeName,
    归属备注: affiliationSummary(record),
    套磁时间: record.raw[CONTACT_DATE_COLUMN],
    回复情况: record.raw[CONTACT_RESPONSE_COLUMN],
    回复情况备注: record.raw[CONTACT_NOTE_COLUMN],
    ...record.raw,
    来源文件: record.sourcePath,
  }));
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(rows), "教师看板");
  const data = XLSX.write(workbook, { bookType: "xlsx", type: "array" });
  downloadBlob(
    new Blob([data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }),
    "teacher-contact-dashboard.xlsx",
  );
}

function bindEvents() {
  els.pickOutputs.addEventListener("click", () => {
    const loader = state.apiMode ? loadFromApi : openOutputsDirectory;
    loader().catch((error) => showToast(error.message));
  });
  els.fileInput.addEventListener("change", (event) => handleFileInput(event).catch((error) => showToast(error.message)));
  els.statusInput.addEventListener("change", (event) => handleStatusInput(event).catch((error) => showToast(error.message)));
  els.saveStatus.addEventListener("click", () => saveStatus().catch((error) => showToast(error.message)));
  els.syncExcel.addEventListener("click", () => syncExcel().catch((error) => showToast(error.message)));
  els.downloadStatus.addEventListener("click", downloadStatus);
  els.exportXlsx.addEventListener("click", exportFilteredXlsx);
  els.viewTabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-view]");
    if (!button) return;
    setViewMode(button.dataset.view);
  });
  els.schoolFilter.addEventListener("input", () => {
    populateCollegeFilter();
    applyFilters();
  });
  [
    els.searchInput,
    els.collegeFilter,
    els.levelFilter,
    els.contactFilter,
    els.minScore,
    els.priorityOnly,
    els.hideContacted,
    els.weakEvidenceOnly,
  ].forEach((element) => element.addEventListener("input", applyFilters));
  window.addEventListener("beforeunload", (event) => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
}

async function init() {
  bindEvents();
  populateFilters();
  renderViewTabs();
  setSummary();
  setApiMode(window.location.protocol !== "file:");
  if (!state.apiMode) return;
  try {
    await loadFromApi();
  } catch (error) {
    setApiMode(false);
    showToast(`本地服务不可用：${error.message}`);
  }
}

init();
