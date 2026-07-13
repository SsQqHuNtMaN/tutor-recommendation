export const STATUS_COLUMN = "套磁情况";
export const CONTACT_DATE_COLUMN = "套磁时间";
export const CONTACT_RESPONSE_COLUMN = "回复情况";
export const INTERVIEW_TIME_COLUMN = "约面试时间";
export const CONTACT_NOTE_COLUMN = "回复情况备注";
export const LEGACY_CONTACT_NOTE_COLUMNS = ["套磁备注"];
export const VALID_STATUSES = ["已套磁", "先不考虑", "不可能", "不匹配"];
export const DEFAULT_RESPONSES = ["已发", "官回", "添加微信", "约面试", "考核", "已满"];

const LEGACY_STATUS_ALIASES = { 不考虑: "先不考虑" };

export const CALENDAR_RESPONSE_STYLES = {
  已发: "response-sent",
  官回: "response-official",
  添加微信: "response-wechat",
  约面试: "response-interview",
  考核: "response-assessment",
  已满: "response-full",
};

export const CALENDAR_RESPONSE_PRIORITY = ["已满", "考核", "约面试", "添加微信", "官回", "已发"];
export const CALENDAR_LEGEND = [
  ["已发", "response-sent"],
  ["官回", "response-official"],
  ["添加微信", "response-wechat"],
  ["约面试", "response-interview"],
  ["考核", "response-assessment"],
  ["已满", "response-full"],
  ["未记录", "response-unset"],
];

export function norm(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/\s+/g, " ").trim();
}

export function numberValue(value) {
  const parsed = Number(norm(value));
  return Number.isFinite(parsed) ? parsed : 0;
}

export function normalizeStatus(value) {
  const text = norm(value);
  const mapped = LEGACY_STATUS_ALIASES[text] || text;
  return VALID_STATUSES.includes(mapped) ? mapped : "";
}

export function localTodayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60 * 1000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

export function validDateIso(value) {
  const text = norm(value).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return "";
  const date = new Date(`${text}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "";
  const [year, month, day] = text.split("-").map(Number);
  return date.getFullYear() === year && date.getMonth() + 1 === month && date.getDate() === day ? text : "";
}

export function dateToIso(date) {
  const offset = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

export function startOfCalendarWeek(value = localTodayIso()) {
  const valid = validDateIso(value) || localTodayIso();
  const date = new Date(`${valid}T00:00:00`);
  const mondayOffset = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - mondayOffset);
  return dateToIso(date);
}

export function addCalendarDays(dateIso, offset) {
  const valid = validDateIso(dateIso) || localTodayIso();
  const date = new Date(`${valid}T00:00:00`);
  date.setDate(date.getDate() + offset);
  return dateToIso(date);
}

export function normalizeInterviewAt(value) {
  const text = norm(value).replace(" ", "T").slice(0, 16);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(text)) return "";
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? "" : text;
}

export function formatInterviewAt(value, includeDate = true) {
  const interviewAt = normalizeInterviewAt(value);
  if (!interviewAt) return "";
  const date = new Date(interviewAt);
  return new Intl.DateTimeFormat("zh-CN", {
    ...(includeDate ? { month: "numeric", day: "numeric" } : {}),
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function formatCalendarDay(dateIso, options = {}) {
  const valid = validDateIso(dateIso);
  if (!valid) return "";
  return new Intl.DateTimeFormat("zh-CN", options).format(new Date(`${valid}T00:00:00`));
}

export function splitResponses(value) {
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

export function calendarResponseState(record) {
  const responses = splitResponses(record.contact?.responses || record.raw[CONTACT_RESPONSE_COLUMN]);
  const primary = CALENDAR_RESPONSE_PRIORITY.find((response) => responses.includes(response)) || "";
  return {
    responses,
    primary,
    className: CALENDAR_RESPONSE_STYLES[primary] || "response-unset",
  };
}

export function joinResponses(value) {
  return splitResponses(value).join("；");
}

export function uniqueJoinText(values) {
  const seen = new Set();
  const output = [];
  values.map(norm).forEach((value) => {
    if (!value || seen.has(value)) return;
    seen.add(value);
    output.push(value);
  });
  return output.join("；");
}

export function splitKnownAndCustomResponses(value) {
  const known = [];
  const custom = [];
  splitResponses(value).forEach((response) => {
    if (DEFAULT_RESPONSES.includes(response)) known.push(response);
    else custom.push(response);
  });
  return { known, custom };
}

export function normalizeContactEntry(value) {
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
    interview_at: normalizeInterviewAt(value.interview_at || value.interviewAt || value[INTERVIEW_TIME_COLUMN]),
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

export function contactEntryFromRow(row) {
  return normalizeContactEntry({
    status: row[STATUS_COLUMN],
    contacted_at: row[CONTACT_DATE_COLUMN],
    responses: row[CONTACT_RESPONSE_COLUMN],
    interview_at: row[INTERVIEW_TIME_COLUMN],
    note: row[CONTACT_NOTE_COLUMN],
    ...Object.fromEntries(LEGACY_CONTACT_NOTE_COLUMNS.map((column) => [column, row[column]])),
  });
}

export function mergeContactEntries(base, override) {
  const merged = { ...base, ...override };
  if (!override.responses?.length) merged.responses = base.responses || [];
  return normalizeContactEntry(merged);
}

export function entryHasData(entry) {
  const normalized = normalizeContactEntry(entry);
  return Boolean(
    normalized.status ||
      normalized.contacted_at ||
      normalized.responses?.length ||
      normalized.interview_at ||
      normalized.note
  );
}

export function escapeHtml(value) {
  return norm(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function safeUrl(value) {
  const url = norm(value);
  return /^https?:\/\//i.test(url) ? url : "";
}
