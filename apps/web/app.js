const API = "/api";

const views = {
  portfolio: ["Tìm dự án", "Tìm một dự án, mở hồ sơ rồi tự bung mạng lưới dự án ↔ nhà quảng cáo."],
  command: ["Bước 2 · Chuẩn bị campaign", "Các dự án đã đủ dữ liệu Bước 1 và được lưu để chuẩn bị nội dung, cấu trúc campaign."],
  intelligence: ["Nhà quảng cáo & dự án", "Bổ sung snapshot có nguồn để mạng lưới dự án ↔ nhà quảng cáo ngày càng rộng."],
  compliance: ["Terms Warning", "Cảnh báo theo bằng chứng; không loại dự án khỏi phân tích."],
  resources: ["Tài nguyên", "Theo dõi email, tài khoản Ads, thanh toán và cảnh báo để chuẩn bị campaign an toàn."],
  economics: ["Economics Lab", "Tính break-even CPC theo loại hoa hồng và độ tin cậy của giả định."],
  exposure: ["Risk & Exposure", "Theo dõi spend và commission cùng cảnh báo terms, nhưng luôn giữ dự án trong hệ thống."],
  programs: ["Terms Evidence Center", "Thu thập proposal có nguồn; commission tách riêng và permission vẫn khóa cho tới khi được xác nhận."],
  finance: ["Finance & Reconciliation", "Quy đổi có nguồn, giữ số gốc và đưa ngoại lệ vào hàng đợi đối soát."],
  system: ["Backup & Restore", "Sao lưu dữ liệu trước mọi thay đổi lớn và khôi phục có kiểm soát."],
};

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function sourceChangeLabel(value) {
  return {
    ADDED: "nguồn mới",
    REMOVED: "không còn tìm thấy",
    CONTENT_CHANGED: "nội dung thay đổi",
    UNAVAILABLE: "tạm thời không đọc được",
  }[value] || value;
}

function sourceAuthorityLabel(value) {
  return {
    OFFICIAL: "Nguồn merchant chính thức",
    PARTNER_PORTAL: "Cổng đối tác",
    WRITTEN_CONFIRMATION: "Xác nhận bằng văn bản",
    THIRD_PARTY: "Nguồn bên thứ ba",
    UNKNOWN: "Nguồn chưa xác định",
  }[value] || "Nguồn chưa xác định";
}

function safeExternalUrl(url) {
  try {
    const parsed = new URL(url);
    return ['http:', 'https:'].includes(parsed.protocol) && parsed.hostname ? parsed : null;
  } catch (_) {
    return null;
  }
}

function safeExternalHostname(url) {
  return safeExternalUrl(url)?.hostname || "";
}

function safeExternalLink(url, label) {
  const parsed = safeExternalUrl(url);
  if (!parsed) return esc(url);
  return `<a href="${esc(parsed.href)}" target="_blank" rel="noopener">${esc(label)}</a>`;
}

function safeExternalHostLink(url) {
  return safeExternalLink(url, safeExternalHostname(url) || "Mở nguồn");
}

function researchSourceLink(url, authorities = {}) {
  const authority = authorities[url] || "UNKNOWN";
  return `${safeExternalHostLink(url)}<br><span class="small">${esc(sourceAuthorityLabel(authority))}</span>`;
}

async function request(path, options = {}) {
  const isForm = options.body instanceof FormData;
  const headers = isForm
    ? { ...(options.headers || {}) }
    : { "Content-Type": "application/json", ...(options.headers || {}) };
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string"
        ? body.detail
        : body.detail?.message || JSON.stringify(body.detail || body);
    } catch (_) {}
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function setApiStatus(ok, text) {
  const dot = document.getElementById("apiDot");
  dot.classList.toggle("ok", ok);
  dot.classList.toggle("error", !ok);
  document.getElementById("apiStatus").textContent = text;
}

function switchView(name, {loadData = true} = {}) {
  document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".nav-item[data-view]").forEach((el) => el.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
  document.querySelector(`.nav-item[data-view="${name}"]`).classList.add("active");
  document.getElementById("viewTitle").textContent = views[name][0];
  document.getElementById("viewSubtitle").textContent = views[name][1];
  if (!loadData) return;
  if (name === "portfolio") loadPortfolio();
  if (name === "command") loadStepTwoProjects();
  if (name === "resources") loadResources();
  if (name === "programs") loadPrograms();
  if (name === "intelligence") {
    loadCaptureReviewQueue();
    loadCaptures();
  }
  if (name === "exposure") loadExposure();
  if (name === "finance") loadFinance();
  if (name === "system") loadBackups();
}

function metric(label, value, note) {
  return `<div class="metric"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div><div class="note">${esc(note)}</div></div>`;
}

let portfolioCache = [];
const appraisalCache = new Map();
let stepTwoProjectCache = [];
let activeCampPlanProject = null;
let activeCampPlan = null;
let resourceOverview = null;

const riskLabels = {
  REGISTRATION_BLOCKED: "Không đăng ký được",
  PPC_NOT_CHECKED: "PPC chưa rõ",
  PPC_CONFLICT: "PPC mâu thuẫn",
  PPC_PROHIBITED: "PPC bị cấm",
  COMMISSION_CONFLICT: "Commission mâu thuẫn",
  COMMISSION_REVIEW_REQUIRED: "Commission chờ duyệt",
  ADVERTISER_DATA_MISSING: "Chưa thu thập advertiser",
  CAMPAIGN_DATA_MISSING: "Thiếu campaign",
  CTR_BELOW_40: "CTR dưới 40%",
};

const projectStageLabels = {
  INTAKE: "Tiếp nhận",
  RESEARCH: "Kiểm chứng",
  EVALUATION: "Chấm điểm",
  PREP: "Chuẩn bị",
  LIVE: "Đang chạy",
  PAUSED: "Tạm dừng",
  CLOSED: "Đã đóng",
};

const registrationLabels = {
  NOT_STARTED: "Chưa đăng ký",
  APPLYING: "Đang đăng ký",
  PENDING_APPROVAL: "Chờ duyệt",
  APPROVED: "Đã duyệt",
  BLOCKED_REGISTRATION: "Không đăng ký được",
  REJECTED: "Bị từ chối",
  CLOSED: "Đã đóng",
};

const termsGateLabels = {
  TERMS_OK: "PPC đã có bằng chứng",
  WARNING_TERMS_UNVERIFIED: "PPC chưa xác minh",
  WARNING_TERMS_CONFLICT: "PPC có nguồn mâu thuẫn",
  WARNING_TERMS_PROHIBITED: "PPC bị cấm",
  WARNING_APPROVAL_REQUIRED: "PPC cần phê duyệt",
};

function portfolioBadge(value, labels, critical = []) {
  const ready = ["LIVE", "APPROVED", "TERMS_OK"].includes(value);
  const className = ready ? "gate-ready" : critical.includes(value) ? "gate-blocked" : "gate-pending";
  return `<span class="gate ${className}">${esc(labels[value] || value)}</span>`;
}

function commissionContext(metricItem, state) {
  if (state === "CONFLICT") return "Nguồn commission mâu thuẫn";
  if (state !== "RESOLVED") return "Chờ xác nhận commission";
  const reason = metricItem.change_reason || "";
  if (reason.includes("RECURRING_LIFETIME")) return "Định kỳ trọn đời";
  if (reason.includes("RECURRING_LIMITED")) return "Định kỳ có giới hạn";
  if (reason.includes("ONE_TIME")) return "Hoa hồng một lần";
  return "Commission đã xác nhận";
}

function displayMetricValue(metricItem) {
  if (!metricItem || metricItem.value == null) {
    const missingLabels = {
      independent_advertisers: "Chưa thu thập",
      active_advertisers_30d: "Chưa đủ dữ liệu",
      campaigns: "Chưa liên kết",
      impressions: "Chưa nhập",
      clicks: "Chưa nhập",
      conversions: "Chưa nhập",
      ctr: "Chưa nhập",
      cost: "Chưa nhập",
      commission: "Chưa xác nhận",
    };
    return missingLabels[metricItem?.key] || "Chưa có dữ liệu";
  }
  if (typeof metricItem.value === "number") {
    const maximumFractionDigits = Number.isInteger(metricItem.value) ? 0 : 2;
    const number = metricItem.value.toLocaleString("vi-VN", {maximumFractionDigits});
    return `${number}${metricItem.unit === "%" ? "%" : metricItem.unit ? ` ${metricItem.unit}` : ""}`;
  }
  return `${metricItem.value}${metricItem.unit ? ` ${metricItem.unit}` : ""}`;
}

function portfolioMetricButton(item, key, prefix = "") {
  const metricItem = item.metrics[key];
  const missing = !metricItem || metricItem.value == null;
  return `<button type="button" class="portfolio-metric${missing ? " missing" : ""}" data-truth-project="${item.id}" data-truth-metric="${esc(key)}">${esc(prefix)}${esc(displayMetricValue(metricItem))}</button>`;
}

function riskChips(badges) {
  if (!badges.length) return '<span class="risk-chip">Không có cảnh báo mở</span>';
  return badges.map((badge) => {
    const critical = ["REGISTRATION_BLOCKED", "PPC_CONFLICT", "PPC_PROHIBITED", "COMMISSION_CONFLICT", "CTR_BELOW_40"].includes(badge);
    const missing = badge.endsWith("_MISSING");
    return `<span class="risk-chip${critical ? " critical" : missing ? " missing" : ""}">${esc(riskLabels[badge] || badge)}</span>`;
  }).join("");
}

function portfolioQueryString() {
  const values = new FormData(document.getElementById("portfolioFilters"));
  const params = new URLSearchParams();
  for (const [key, value] of values.entries()) {
    if (String(value).trim()) params.set(key, String(value).trim());
  }
  return params.toString();
}

function normalizeProjectDomainCandidate(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw || /\s/.test(raw)) return null;
  try {
    const parsed = new URL(raw.includes("://") ? raw : `https://${raw}`);
    const host = parsed.hostname.replace(/^www\./, "").replace(/\.$/, "");
    if (!host.includes(".") || !/^[a-z0-9.-]+$/.test(host)) return null;
    return host;
  } catch (_error) {
    return null;
  }
}

function portfolioDomainCandidate() {
  const input = document.querySelector('#portfolioFilters input[name="query"]');
  return normalizeProjectDomainCandidate(input?.value);
}

async function loadPortfolio() {
  const query = portfolioQueryString();
  const items = await request(`/portfolio/projects${query ? `?${query}` : ""}`);
  portfolioCache = items;
  const body = document.getElementById("portfolioRows");
  const summary = document.getElementById("portfolioSummary");
  const warnings = items.reduce((total, item) => total + item.risk_badges.length, 0);
  const incomplete = items.filter((item) => item.opportunity_state !== "SCORABLE").length;
  summary.textContent = `${items.length} dự án · ${warnings} cảnh báo đang theo dõi · ${incomplete} dự án đang bổ sung data. Không dự án nào bị tự loại.`;
  if (!items.length) {
    const candidate = portfolioDomainCandidate();
    body.innerHTML = candidate
      ? `<tr><td colspan="9"><div class="portfolio-intake-empty"><strong>Chưa có ${esc(candidate)} trong AFI-OS.</strong><span>Thêm hồ sơ ngay; Terms, commission, advertiser và campaign sẽ được bổ sung dần. PPC vẫn NOT_CHECKED cho tới khi có bằng chứng.</span><button type="button" class="button primary" data-project-intake="${esc(candidate)}">Thêm dự án và bắt đầu rà nguồn</button></div></td></tr>`
      : '<tr><td colspan="9" class="empty">Không có dự án phù hợp bộ lọc.</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => {
    const commission = item.metrics.commission;
    const advertiser = portfolioMetricButton(item, "independent_advertisers");
    const activeAdvertiser = portfolioMetricButton(item, "active_advertisers_30d");
    const campaign = portfolioMetricButton(item, "campaigns");
    const ctr = portfolioMetricButton(item, "ctr", "CTR ");
    const cost = portfolioMetricButton(item, "cost");
    const commissionLabel = displayMetricValue(commission);
    const nextAction = item.next_action || "Chưa đặt việc tiếp theo";
    const potential = item.opportunity_potential == null ? "Chờ data" : item.opportunity_potential;
    return `<tr>
      <td class="portfolio-project"><strong>${esc(item.brand_name)}</strong><span class="small">${esc(item.domain)} · ${esc(item.category || "Chưa phân loại")}</span></td>
      <td class="portfolio-workflow">${portfolioBadge(item.stage, projectStageLabels, ["CLOSED"])}<span class="next-action">${esc(nextAction)}</span></td>
      <td>${portfolioBadge(item.registration_status, registrationLabels, ["BLOCKED_REGISTRATION", "REJECTED", "CLOSED"])}${item.owner ? `<br><span class="small">${esc(item.owner)}</span>` : ""}</td>
      <td>${portfolioBadge(item.terms_gate_status, termsGateLabels, ["WARNING_TERMS_CONFLICT", "WARNING_TERMS_PROHIBITED"])}<br><button type="button" class="portfolio-metric${commission.value == null ? " missing" : ""}" data-truth-project="${item.id}" data-truth-metric="commission">${esc(commissionLabel)}</button><br><span class="small">${esc(commissionContext(commission, item.commission_state))}</span></td>
      <td><strong>${advertiser}</strong><br><span class="small">Active 30d: ${activeAdvertiser}</span></td>
      <td>${campaign}<br><span class="small">${ctr} · Cost ${cost}</span></td>
      <td><div class="portfolio-confidence"><strong>${esc(potential)}</strong><span class="small">Tin cậy ${item.evidence_confidence}/100</span><div class="confidence-bar"><span style="width:${item.evidence_confidence}%"></span></div></div></td>
      <td><div class="risk-stack">${riskChips(item.risk_badges)}</div></td>
      <td><button type="button" class="button secondary" data-project-detail="${item.id}">Mở</button></td>
    </tr>`;
  }).join("");
}

async function intakePortfolioProject(domain, button, messageNode = null) {
  const summary = document.getElementById("portfolioSummary");
  const message = messageNode || summary;
  button.disabled = true;
  const originalLabel = button.textContent;
  button.textContent = "Đang check…";
  message.textContent = `Đang check ${domain}: 10 nhóm dữ liệu có nguồn…`;
  try {
    const result = await request("/appraise", {
      method: "POST",
      body: JSON.stringify({domain}),
    });
    appraisalCache.set(domain, result);
    renderAppraisal(result);
    const filters = document.getElementById("portfolioFilters");
    filters.reset();
    filters.elements.query.value = domain;
    await Promise.all([loadPortfolio(), loadPrograms(), loadOperations(), loadSummary()]);
    const pending = appraisalPendingLabels(result);
    message.textContent = pending.length
      ? `Đã check ${domain}. Đang chờ: ${pending.join(" · ")}.`
      : `Đã check đủ dữ liệu nguồn cho ${domain}.`;
    button.disabled = false;
    button.textContent = originalLabel;
    document.getElementById("appraisalResult").scrollIntoView({behavior: "smooth", block: "start"});
    return result;
  } catch (error) {
    message.textContent = `Không thể truy vết ${domain}: ${error.message}`;
    button.disabled = false;
    button.textContent = originalLabel;
    return null;
  }
}

function appraisalKnown(value) {
  return value !== null && value !== undefined && value !== "";
}

function appraisalDisplay(value, suffix = "") {
  if (!appraisalKnown(value)) return '<span class="appraisal-pending">Đang chờ nguồn</span>';
  if (Array.isArray(value)) {
    return value.length ? esc(value.map((item) => Array.isArray(item) ? item.join(" · ") : item).join(", ")) : "Không có mục khác";
  }
  if (typeof value === "boolean") return value ? "Có" : "Không";
  if (typeof value === "number") return `${value.toLocaleString("vi-VN")}${suffix}`;
  return `${esc(value)}${suffix}`;
}

function appraisalSource(source) {
  return `<small>Nguồn: ${appraisalKnown(source) ? esc(source) : '<span class="appraisal-pending">đang chờ kết nối</span>'}</small>`;
}

function appraisalCard(index, title, body, source = null) {
  return `<article class="appraisal-card"><div class="appraisal-card-head"><span>${String(index).padStart(2, "0")}</span><h3>${esc(title)}</h3></div><div class="appraisal-card-body">${body}</div>${appraisalSource(source)}</article>`;
}

function appraisalPendingLabels(result) {
  const groups = [
    ["traffic", result.traffic.monthly, result.traffic.top_countries],
    ["keyword", result.keyword.search_volume, result.keyword.bid_low_vnd, result.keyword.bid_high_vnd],
    ["advertiser", result.advertisers.count],
    ["commission", result.commission.percent, result.commission.avg_package],
    ["payment", result.payment.gateways, result.payment.min_payment, result.payment.clear_days],
    ["terms", result.terms.ads_allowed, result.terms.brand_bid_restricted],
    ["payback", result.payback.days_low, result.payback.days_high],
    ["score engine", result.score.total, result.score.pass],
  ];
  return groups.filter(([, ...values]) => values.some((value) => !appraisalKnown(value))).map(([name]) => name);
}

function renderAppraisal(result) {
  const target = document.getElementById("appraisalResult");
  const scoreState = result.score.pass === true ? "pass" : result.score.pass === false ? "warning" : "pending";
  const scoreLabel = result.score.pass === true ? "ĐẠT BƯỚC 1" : result.score.pass === false ? "CẢNH BÁO" : "ĐANG BỔ SUNG";
  const score = appraisalKnown(result.score.total) ? `${result.score.total}/100` : "Chờ engine";
  const countries = result.traffic.top_countries?.map(([country, share]) => `${country} ${(Number(share) * 100).toFixed(1)}%`) || null;
  const packages = result.commission.packages?.map(([name, percent]) => `${name}: ${percent}%`) || null;
  const flags = (result.score.flags || []).map((item) => `<li class="flag-${esc(item.level)}">${esc(item.msg)}</li>`).join("");
  const cards = [
    appraisalCard(1, "Nhà quảng cáo", `<strong>${appraisalDisplay(result.advertisers.count)}</strong><p>Cùng chạy dự án khác: ${appraisalDisplay(result.advertisers.also_running)}</p>`, result.advertisers.source),
    appraisalCard(2, "Traffic website", `<strong>${appraisalDisplay(result.traffic.monthly, " visit/tháng")}</strong><p>Top quốc gia: ${appraisalDisplay(countries)}</p><b>${esc(result.traffic.source_status)}</b>`, result.traffic.source),
    appraisalCard(3, "Affiliate link", `<strong>${appraisalKnown(result.affiliate_link) ? safeExternalLink(result.affiliate_link, result.affiliate_link) : appraisalDisplay(null)}</strong>`, result.affiliate_link),
    appraisalCard(4, "Điều khoản PPC", `<strong>Ads: ${appraisalDisplay(result.terms.ads_allowed)}</strong><p>Hạn chế brand bid: ${appraisalDisplay(result.terms.brand_bid_restricted)}</p><p>${appraisalDisplay(result.terms.summary)}</p>`, result.terms.source),
    appraisalCard(5, "Ngành dự án", `<strong>${appraisalDisplay(result.niche)}</strong>`, null),
    appraisalCard(6, "Thanh toán", `<strong>${appraisalDisplay(result.payment.gateways)}</strong><p>Min: ${appraisalDisplay(result.payment.min_payment)} · Clear: ${appraisalDisplay(result.payment.clear_days, " ngày")} · Cookie: ${appraisalDisplay(result.payment.cookie_days, " ngày")}</p><p>Network: ${appraisalDisplay(result.payment.net)}</p>`, result.payment.net),
    appraisalCard(7, "Commission & giá gói", `<strong>${appraisalDisplay(result.commission.percent, "%")} · ${appraisalDisplay(result.commission.type)}</strong><p>Gói: ${appraisalDisplay(packages)}</p><p>Giá trung bình: ${appraisalDisplay(result.commission.avg_package)}</p>`, null),
    appraisalCard(8, "Giá thầu từ khóa chính", `<strong>${appraisalDisplay(result.keyword.term)}</strong><p>Thấp: ${appraisalDisplay(result.keyword.bid_low_vnd, " VND")} · Cao: ${appraisalDisplay(result.keyword.bid_high_vnd, " VND")}</p>`, result.keyword.source),
    appraisalCard(9, "Hoàn vốn ước tính", `<strong>${appraisalDisplay(result.payback.days_low, " ngày")} → ${appraisalDisplay(result.payback.days_high, " ngày")}</strong><p>${appraisalDisplay(result.payback.mode)}</p>`, result.payback.mode),
    appraisalCard(10, "Lượt tìm kiếm", `<strong>${appraisalDisplay(result.keyword.search_volume, "/tháng")}</strong><p>Global · English · Google Ads Keyword Planner</p>`, result.keyword.source),
  ];
  target.hidden = false;
  target.innerHTML = `<article class="panel appraisal-summary"><div class="appraisal-verdict"><div><span>BƯỚC 1 · ${esc(result.domain)}</span><h2>Tổng quan quyết định</h2><p>10 nhóm dữ liệu trên cùng một màn hình; chưa nối nguồn hiện “Đang chờ”.</p></div><div class="appraisal-score score-${scoreState}"><strong>${scoreLabel}</strong><b>${esc(score)}</b></div></div><div class="appraisal-grid">${cards.join("")}</div><div class="appraisal-decision"><ul>${flags || '<li>Không có cảnh báo.</li>'}</ul><button class="button primary" type="button" data-appraisal-save="${esc(result.domain)}"${result.score.pass === true ? "" : " disabled"}>Lưu và chuyển Bước 2</button><span>${result.score.pass === true ? "Đủ điều kiện theo engine." : "Nút sẽ mở khi engine trả pass = true."}</span></div></article>`;
}

async function runAppraisalBatch() {
  const input = document.getElementById("appraisalBatchInput");
  const button = document.getElementById("appraisalBatchRun");
  const target = document.getElementById("appraisalBatchResults");
  const domains = [...new Set(input.value.split(/\s+/).map(normalizeProjectDomainCandidate).filter(Boolean))].slice(0, 50);
  if (!domains.length) {
    target.textContent = "Hãy dán ít nhất một domain hợp lệ.";
    return;
  }
  button.disabled = true;
  target.innerHTML = domains.map((domain) => `<button type="button" class="batch-result pending" data-appraisal-domain="${esc(domain)}"><strong>${esc(domain)}</strong><span>Đang chờ…</span></button>`).join("");
  try {
    const results = await request("/appraise/batch", {
      method: "POST",
      body: JSON.stringify({domains}),
    });
    const resultByDomain = new Map(results.map((result) => [result.domain, result]));
    for (const domain of domains) {
      const row = target.querySelector(`[data-appraisal-domain="${CSS.escape(domain)}"]`);
      const result = resultByDomain.get(domain);
      if (!result) {
        row.className = "batch-result error";
        row.querySelector("span").textContent = "Không có dữ liệu trả về";
        continue;
      }
      appraisalCache.set(domain, result);
      const pending = appraisalPendingLabels(result).length;
      row.className = `batch-result ${result.score.pass === true ? "pass" : "warning"}`;
      row.querySelector("span").textContent = result.score.pass === true ? "Đạt" : `${pending} nhóm đang chờ`;
    }
  } catch (error) {
    for (const domain of domains) {
      const row = target.querySelector(`[data-appraisal-domain="${CSS.escape(domain)}"]`);
      row.className = "batch-result error";
      row.querySelector("span").textContent = `Lỗi: ${error.message}`;
    }
  }
  button.disabled = false;
  await loadPortfolio();
}

async function saveAppraisalToStepTwo(domain, button) {
  button.disabled = true;
  const projects = await request(`/portfolio/projects?query=${encodeURIComponent(domain)}&limit=10`);
  const project = projects.find((item) => item.domain === domain);
  if (!project) throw new Error("Không tìm thấy hồ sơ đã lưu");
  await request(`/portfolio/projects/${project.id}/step-one-decision`, {method: "POST", body: JSON.stringify({decision: "PREPARE_STEP_2", actor: "local-user"})});
  await Promise.all([loadPortfolio(), loadStepTwoProjects()]);
  switchView("command");
}

async function tracePortfolioProject(form) {
  const input = form.elements.domain;
  const button = form.querySelector('button[type="submit"]');
  const message = document.getElementById("projectTraceMessage");
  const domain = normalizeProjectDomainCandidate(input.value);
  if (!domain) {
    message.textContent = "Domain không hợp lệ. Hãy nhập dạng example.com hoặc URL đầy đủ.";
    input.focus();
    return;
  }
  input.value = domain;
  await intakePortfolioProject(domain, button, message);
}

function openTruthDrawer(title, html) {
  document.getElementById("truthDrawerTitle").textContent = title;
  document.getElementById("truthDrawerBody").innerHTML = html;
  document.getElementById("truthBackdrop").hidden = false;
  document.getElementById("truthDrawer").classList.add("open");
  document.getElementById("truthDrawer").setAttribute("aria-hidden", "false");
  document.body.classList.add("drawer-open");
}

function closeTruthDrawer() {
  document.getElementById("truthDrawer").classList.remove("open");
  document.getElementById("truthDrawer").setAttribute("aria-hidden", "true");
  document.getElementById("truthBackdrop").hidden = true;
  document.body.classList.remove("drawer-open");
}

function truthMeta(metricItem) {
  const source = metricItem.source_url
    ? safeExternalLink(metricItem.source_url, metricItem.source_name)
    : esc(metricItem.source_name);
  return `<div class="truth-value">${esc(displayMetricValue(metricItem))}</div>
    <div class="truth-meta">
      <div><span>Chất lượng</span><strong>${esc(metricItem.quality)}</strong></div>
      <div><span>Trạng thái thu thập</span><strong>${esc(metricItem.collection_state || "NOT_COLLECTED")}</strong></div>
      <div><span>Confidence</span><strong>${Math.round(Number(metricItem.confidence || 0) * 100)}%</strong></div>
      <div><span>Nguồn</span><strong>${source}</strong></div>
      <div><span>Ngày quan sát</span><strong>${metricItem.observed_at ? new Date(metricItem.observed_at).toLocaleString("vi-VN") : "Chưa thu thập"}</strong></div>
      <div><span>Khoảng dữ liệu</span><strong>${esc(metricItem.date_from || "—")} → ${esc(metricItem.date_to || "—")}</strong></div>
      <div><span>Phương pháp</span><strong>${esc(metricItem.method_version)}</strong></div>
    </div>
    ${metricItem.change_reason ? `<div class="notice warning">${esc(metricItem.change_reason)}</div>` : ""}
    <div class="truth-lineage"><h2>Dấu vết nguồn</h2>${metricItem.lineage.length ? `<pre>${esc(JSON.stringify(metricItem.lineage, null, 2))}</pre>` : '<div class="empty">Chưa có lineage vì dữ liệu chưa được thu thập.</div>'}</div>`;
}

async function openMetricTruth(projectId, metricKey) {
  openTruthDrawer("Đang đọc nguồn…", '<div class="empty">Đang tải dấu vết số liệu…</div>');
  try {
    const metricItem = await request(`/portfolio/projects/${projectId}/truth/${encodeURIComponent(metricKey)}`);
    openTruthDrawer(metricItem.label, truthMeta(metricItem));
  } catch (error) {
    openTruthDrawer("Không đọc được nguồn", `<div class="notice warning">${esc(error.message)}</div>`);
  }
}

function datetimeLocal(value) {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

const checkStateLabels = {
  AVAILABLE: "Đã có số liệu",
  PARTIAL: "Chưa đủ phạm vi",
  NOT_COLLECTED: "Chưa thu thập",
};

const permissionLabels = {
  PROHIBITED: "Cấm",
  NON_BRAND_ONLY: "Chỉ non-brand",
  BRAND_ALLOWED: "Cho phép brand",
  APPROVAL_REQUIRED: "Cần phê duyệt",
  AMBIGUOUS: "Mơ hồ",
  CONFLICT: "Mâu thuẫn",
  NOT_CHECKED: "Chưa xác minh",
};

function projectCheckFieldCard(field) {
  const available = field.value !== null && field.value !== undefined && field.value !== "";
  const source = field.source_url
    ? safeExternalLink(field.source_url, field.source_name)
    : esc(field.source_name);
  return `<article class="step-one-field${available ? "" : " missing"}">
    <div class="step-one-field-head"><span>${esc(field.label)}</span><b class="collection-state state-${String(field.collection_state || "NOT_COLLECTED").toLowerCase()}">${esc(checkStateLabels[field.collection_state] || field.collection_state)}</b></div>
    <strong>${available ? esc(displayMetricValue(field)) : "Chưa có số liệu"}</strong>
    <small>Nguồn: ${source} · tin cậy ${Math.round(Number(field.confidence || 0) * 100)}%</small>
    ${field.note ? `<p>${esc(field.note)}</p>` : ""}
  </article>`;
}

function projectCheckSection(title, subtitle, fields) {
  return `<section class="step-one-section"><div class="step-one-section-head"><div><h3>${esc(title)}</h3><p>${esc(subtitle)}</p></div></div><div class="step-one-field-grid">${fields.map(projectCheckFieldCard).join("")}</div></section>`;
}

function proposalReviewActions(type, item, check) {
  if (item.review_status !== "PROPOSED") return "";
  const attributes = type === "commercial"
    ? `data-step-commercial-id="${item.id}" data-project-id="${check.project_id}"`
    : type === "commission"
    ? `data-step-commission-id="${item.commission_fact_id}" data-project-id="${check.project_id}" data-program-id="${check.program_id}"`
    : `data-step-evidence-id="${item.evidence_id}" data-project-id="${check.project_id}" data-program-id="${check.program_id}"`;
  return `<div class="review-actions proposal-actions"><button type="button" class="button primary" ${attributes} data-action="ACCEPT">✓ Chấp nhận</button><button type="button" class="button secondary" ${attributes} data-action="REJECT">✗ Bỏ</button></div>`;
}

function commercialProposalValue(item) {
  if (item.scope === "PACKAGES") {
    return (item.payload_json.packages || []).map((pkg) => `${pkg.name}: $${Number(pkg.price_usd).toLocaleString("vi-VN")}/${pkg.period || "kỳ"}`).join(" · ") || "Chưa có gói hợp lệ";
  }
  const payload = item.payload_json || {};
  return [
    (payload.gateways || []).join(", "),
    payload.min_payment_usd == null ? null : `min $${payload.min_payment_usd}`,
    payload.clear_days == null ? null : `${payload.clear_days} ngày thanh toán`,
    payload.cookie_days == null ? null : `cookie ${payload.cookie_days} ngày`,
    payload.net_platform || null,
  ].filter(Boolean).join(" · ") || "Chưa có giá trị hợp lệ";
}

function projectStepOneHtml(check) {
  const f = check.fields;
  const identityKeys = ["project_name", "category", "website_url", "website_traffic_monthly", "google_search_traffic_monthly", "top_traffic_countries", "financial_license"];
  const affiliateKeys = ["affiliate_signup_url", "affiliate_login_url", "affiliate_ref_url", "affiliate_contact_channel", "affiliate_network", "payout_methods", "minimum_payout", "payout_timing_days", "cookie_days"];
  const marketKeys = ["independent_advertisers", "active_advertisers_30d", "primary_keyword", "primary_keyword_search_volume", "primary_keyword_bid_low", "primary_keyword_bid_high"];
  const economicsKeys = ["average_package_price", "accepted_commission_rate", "accepted_commission_flat", "accepted_commission_type", "clicks_per_buyer", "estimated_commission_per_buyer", "estimated_payback_days_low_bid", "estimated_payback_days_high_bid"];
  const permissionCards = Object.entries(check.permissions).map(([scope, value]) =>
    `<div class="permission-card ${["PROHIBITED", "CONFLICT"].includes(value) ? "danger" : value === "NOT_CHECKED" ? "pending" : ""}"><span>${esc(scope)}</span><strong>${esc(permissionLabels[value] || value)}</strong></div>`
  ).join("");
  const evidence = check.terms_evidence.length
    ? check.terms_evidence.map((item) => `<article class="evidence-card${item.review_status === "PROPOSED" ? " proposal-card" : ""}"><div><span>${esc(item.scope)} · ${esc(item.review_status)}</span><strong>${esc(permissionLabels[item.decision] || item.decision)}</strong></div><p>${esc(item.excerpt)}</p><small>${safeExternalHostLink(item.source_url)} · ${new Date(item.checked_at).toLocaleDateString("vi-VN")} · ${Math.round(Number(item.confidence) * 100)}%</small>${proposalReviewActions("evidence", item, check)}</article>`).join("")
    : '<div class="step-one-empty">Chưa có bằng chứng điều khoản PPC công khai. Trạng thái giữ NOT_CHECKED và chỉ cảnh báo.</div>';
  const commissions = check.commission_facts.length
    ? check.commission_facts.map((item) => {
      const value = item.commission_rate != null
        ? `${(Number(item.commission_rate) * 100).toLocaleString("vi-VN")}%`
        : item.commission_flat != null ? `$${Number(item.commission_flat).toLocaleString("vi-VN")}` : "Chưa rõ mức";
      const cadence = item.recurring_months ? `${item.commission_type} · ${item.recurring_months} tháng` : item.commission_type;
      return `<article class="evidence-card${item.review_status === "PROPOSED" ? " proposal-card" : ""}"><div><span>${esc(item.review_status)}${item.rate_is_maximum ? " · UP TO · KHÔNG TÍNH PAYBACK" : ""}</span><strong>${esc(value)} · ${esc(cadence)}</strong></div><p>${esc(item.excerpt)}</p><small>${safeExternalHostLink(item.source_url)} · ${new Date(item.checked_at).toLocaleDateString("vi-VN")} · ${Math.round(Number(item.confidence) * 100)}%</small>${proposalReviewActions("commission", item, check)}</article>`;
    }).join("")
    : '<div class="step-one-empty">Chưa có commission fact có nguồn. Hệ thống không tính hoàn vốn.</div>';
  const commercial = check.commercial_proposals?.length
    ? check.commercial_proposals.map((item) => `<article class="evidence-card${item.review_status === "PROPOSED" ? " proposal-card" : ""}"><div><span>${esc(item.scope)} · ${esc(item.review_status)}</span><strong>${esc(commercialProposalValue(item))}</strong></div><p>${esc(item.excerpt)}</p><small>${safeExternalHostLink(item.source_url)} · ${Math.round(Number(item.confidence) * 100)}%</small>${proposalReviewActions("commercial", item, check)}</article>`).join("")
    : '<div class="step-one-empty">Chưa có đề xuất gói giá hoặc thanh toán từ Claude.</div>';
  const criteria = check.criteria.map((item) => `<article class="criterion-card criterion-${item.status.toLowerCase()}"><span>${esc(item.label)}</span><strong>${esc(item.status)}</strong><b>${esc(item.value ?? "Chưa có số")}</b><small>Ngưỡng: ${esc(item.threshold)} · ${esc(item.explanation)}</small></article>`).join("");
  const needs = check.collection_needs.length
    ? check.collection_needs.map((item) => `<article class="collection-need"><div><strong>${esc(item.group)}</strong><span>${esc(item.status)}</span></div><p>Thiếu: ${item.fields.map(esc).join(" · ")}</p><b>Cần: ${esc(item.source_required)}</b></article>`).join("")
    : '<div class="step-one-complete">Đã có đủ nguồn cốt lõi để quyết định và tính hoàn vốn.</div>';
  const blockerText = check.blocking_fields.length ? check.blocking_fields.map(esc).join(" · ") : "Không còn đầu vào cốt lõi bị thiếu";
  return `<div class="step-one-hero">
      <div><span>BƯỚC 1 · CHECK DỰ ÁN</span><h2>Tổng quan trước khi quyết định</h2><p>Mỗi số đều có nguồn. Không có nguồn thì hiện yêu cầu API, không biến thành 0.</p></div>
      <div class="step-one-readiness ${check.decision_ready ? "ready" : "blocked"}"><strong>${check.decision_ready ? "ĐỦ SỐ LIỆU QUYẾT ĐỊNH" : "CHƯA ĐỦ SỐ LIỆU"}</strong><span>${check.passed_criteria}/${check.total_criteria} tiêu chí đạt · ${check.known_criteria}/${check.total_criteria} đã có kết luận</span></div>
    </div>
    <section class="step-one-section auto-check-section"><div class="step-one-section-head"><div><h3>Thu thập tự động từ domain</h3><p>Anh chỉ nhập tên website. AFI-OS tự gọi các nguồn đã kết nối, lưu số liệu kèm nguồn và nói rõ kết nối còn thiếu.</p></div><span class="badge">MỘT Ô DOMAIN</span></div>
      <div id="projectAutoCheckSources" class="auto-check-sources"><div class="step-one-empty">Bấm “Kiểm tra lại tự động” để làm mới toàn bộ nguồn của ${esc(check.domain)}.</div></div>
      <div class="form-actions"><button type="button" class="button primary" data-project-auto-check="${check.project_id}" data-domain="${esc(check.domain)}">Kiểm tra lại tự động</button><button type="button" class="button secondary" data-project-extract-terms="${check.project_id}">Trích Terms bằng Claude</button><span id="projectAutoCheckMessage" class="form-message">Không cần nhập traffic, ngày hay URL nguồn.</span></div>
    </section>
    ${projectCheckSection("Hồ sơ & thị trường", "Thông tin dự án, traffic và yêu cầu pháp lý.", identityKeys.map((key) => f[key]))}
    ${projectCheckSection("Affiliate & thanh toán", "Link đăng ký/đăng nhập/ref cùng cách và thời gian nhận tiền.", affiliateKeys.map((key) => f[key]))}
    ${projectCheckSection("Nhà quảng cáo, từ khóa & CPC", "Sức cầu và cạnh tranh quốc tế bằng tiếng Anh.", marketKeys.map((key) => f[key]))}
    <section class="step-one-section"><div class="step-one-section-head"><div><h3>Điều khoản PPC</h3><p>Cảnh báo đi cùng dự án nhưng không tự loại hoặc dừng campaign.</p></div><span class="gate gate-pending">${esc(termsGateLabels[check.terms_gate_status] || check.terms_gate_status)}</span></div><div class="permission-grid">${permissionCards}</div><div class="evidence-list">${evidence}</div></section>
    <section class="step-one-section"><div class="step-one-section-head"><div><h3>Commission đã xác minh</h3><p>Tách khỏi quyền PPC. Proposal, “up to” và nguồn mâu thuẫn không được dùng làm sự thật để tính tiền.</p></div><span class="gate ${check.commission_state === "RESOLVED" ? "gate-ready" : "gate-blocked"}">${esc(check.commission_state)}</span></div><div class="evidence-list">${commissions}</div></section>
    <section class="step-one-section"><div class="step-one-section-head"><div><h3>Gói giá & thanh toán do Claude đề xuất</h3><p>Chữ mờ là proposal. Bấm ✓ sau khi đọc đúng trích dẫn; lúc đó dữ liệu mới vào công thức.</p></div><span class="badge">HUMAN REVIEW</span></div><div class="evidence-list">${commercial}</div><span id="proposalReviewMessage" class="form-message"></span></section>
    ${projectCheckSection("Hoàn vốn ước tính", "30 × (150 click × bid) ÷ (giá gói trung bình × % hoa hồng đã xác minh).", economicsKeys.map((key) => f[key]))}
    <section class="step-one-section"><div class="step-one-section-head"><div><h3>Bảng chấm điểm</h3><p>Điểm giúp quyết định; cảnh báo Terms không xóa dự án.</p></div></div><div class="criteria-grid">${criteria}</div></section>
    <section class="step-one-section api-needs"><div class="step-one-section-head"><div><h3>Nguồn/API cần triển khai</h3><p>Danh sách hành động cụ thể để lần check sau không còn dữ liệu rỗng.</p></div></div><div class="collection-needs">${needs}</div></section>
    <section class="step-one-decision"><div><strong>${check.decision_ready ? "Có thể lưu Bước 1 và chuyển sang Bước 2" : "Chưa thể chuyển Bước 2"}</strong><p>${esc(blockerText)}</p><small>Dữ liệu đang có đã nằm trong database; khi bấm lưu, hệ thống ghi thêm snapshot quyết định và audit.</small></div><div class="step-one-actions"><button type="button" class="button secondary" data-step-one-decision="KEEP_RESEARCHING" data-project-id="${check.project_id}">Lưu và tiếp tục bổ sung</button><button type="button" class="button primary" data-step-one-decision="PREPARE_STEP_2" data-project-id="${check.project_id}"${check.decision_ready ? "" : " disabled"}>Lưu và chuyển Bước 2</button></div><span id="stepOneDecisionMessage" class="form-message"></span></section>`;
}

function projectDetailHtml(item, check) {
  const metrics = Object.values(item.metrics).map((metricItem) =>
    `<button type="button" class="truth-metric-card" data-truth-project="${item.id}" data-truth-metric="${esc(metricItem.key)}"><span>${esc(metricItem.label)}</span><strong>${esc(displayMetricValue(metricItem))}</strong><small>${esc(metricItem.collection_state || "NOT_COLLECTED")} · ${esc(metricItem.quality)} · ${Math.round(Number(metricItem.confidence || 0) * 100)}%</small></button>`
  ).join("");
  return `${projectStepOneHtml(check)}<div class="project-journey" aria-label="Luồng truy vết">
      <span class="active">1 · ${esc(item.brand_name)}</span><b>→</b><span>2 · Nhà quảng cáo</span><b>→</b><span>3 · Dự án liên quan</span>
    </div>
    <div class="risk-stack">${riskChips(item.risk_badges)}</div>
    <section class="relationship-network">
      <div class="relationship-network-head"><div><strong>Mạng lưới tự mở rộng</strong><span>Dự án → nhà quảng cáo → các dự án khác của từng nhà quảng cáo.</span></div><span class="badge">CÓ NGUỒN</span></div>
      <div id="projectNetworkBody" data-center-project="${item.id}" class="relationship-network-body"><div class="empty">Đang tải nhà quảng cáo và dự án liên quan…</div></div>
    </section>
    <div class="truth-metric-grid">${metrics}</div>
    <form id="projectWorkflowForm" class="form-grid workflow-form" data-project-id="${item.id}">
      <label>Giai đoạn<select name="stage"><option value="INTAKE">Tiếp nhận</option><option value="RESEARCH">Kiểm chứng</option><option value="EVALUATION">Chấm điểm</option><option value="PREP">Chuẩn bị</option><option value="LIVE">Đang chạy</option><option value="PAUSED">Tạm dừng</option><option value="CLOSED">Đã đóng</option></select></label>
      <label>Trạng thái đăng ký<select name="registration_status"><option value="NOT_STARTED">Chưa đăng ký</option><option value="APPLYING">Đang đăng ký</option><option value="PENDING_APPROVAL">Chờ duyệt</option><option value="APPROVED">Đã duyệt</option><option value="BLOCKED_REGISTRATION">Không đăng ký được</option><option value="REJECTED">Bị từ chối</option><option value="CLOSED">Đã đóng</option></select></label>
      <label class="span-2">Người phụ trách<input name="owner" value="${esc(item.owner || "")}" placeholder="Tran"></label>
      <label class="span-2">Việc tiếp theo<textarea name="next_action" rows="3" placeholder="Bước cụ thể tiếp theo">${esc(item.next_action || "")}</textarea></label>
      <label class="span-2">Hạn xử lý<input name="next_action_due_at" type="datetime-local" value="${esc(datetimeLocal(item.next_action_due_at))}"></label>
      <div class="span-2 form-actions"><button class="button primary" type="submit">Lưu workflow</button><span id="projectWorkflowMessage" class="form-message">Chỉ cập nhật quản lý nội bộ, không sửa Google Ads.</span></div>
    </form>`;
}

function relationshipDate(value) {
  if (!value) return "Chưa có ngày";
  return new Intl.DateTimeFormat("vi-VN", {dateStyle: "medium"}).format(new Date(value));
}

function projectNetworkHtml(data) {
  if (data.collection_state !== "AVAILABLE" || !data.advertisers.length) {
    return `<div class="relationship-empty"><strong>Chưa thu thập mạng lưới cho ${esc(data.domain)}</strong><span>Đây không phải là 0 nhà quảng cáo. Hãy bổ sung snapshot có URL nguồn ở mục “Nhà quảng cáo & dự án”.</span><button type="button" class="button secondary" data-switch-view="intelligence">Bổ sung dữ liệu có nguồn</button></div>`;
  }
  const branches = data.advertisers.map((advertiser) => {
    const source = advertiser.source_urls?.[0]
      ? `${safeExternalHostLink(advertiser.source_urls[0])}${advertiser.source_count > 1 ? ` · +${advertiser.source_count - 1} nguồn` : ""}`
      : "Chưa có URL nguồn";
    const projects = advertiser.projects.map((project) => {
      const isCenter = Number(project.project_id) === Number(data.project_id);
      const ads = project.reported_ads === null || project.reported_ads === undefined
        ? "Chưa có số quảng cáo"
        : `${Number(project.reported_ads).toLocaleString("vi-VN")} quảng cáo theo nguồn`;
      const projectSource = project.source_urls?.[0]
        ? safeExternalHostLink(project.source_urls[0])
        : "Chưa có URL nguồn";
      return `<div class="related-project-node${isCenter ? " current" : ""}">
        <button type="button" ${isCenter ? "disabled" : `data-project-network="${project.project_id}"`}>
          <span>${isCenter ? "Dự án đang xem" : "Mở rộng từ dự án này"}</span>
          <strong>${esc(project.brand_name)}</strong><small>${esc(project.domain)}</small>
        <em>${esc(ads)} · quan sát ${esc(relationshipDate(project.observed_at))}</em>
        </button>
        <i>Nguồn: ${projectSource}</i>
      </div>`;
    }).join("");
    return `<article class="advertiser-branch">
      <div class="advertiser-branch-head">
        <div><span>Nhà quảng cáo</span><strong>${esc(advertiser.advertiser_name)}</strong><small>${esc(advertiser.advertiser_location || "Chưa có vị trí")} · ${esc(advertiser.classification)}</small></div>
        <div class="relationship-count"><strong>${advertiser.projects.length}</strong><span>dự án đã biết</span></div>
      </div>
      <div class="relationship-source">Nguồn quan hệ: ${source} · kiểm tra ${esc(relationshipDate(advertiser.observed_at))}</div>
      <div class="related-project-list">${projects || '<span class="empty">Chưa thu thập dự án liên quan.</span>'}</div>
    </article>`;
  }).join("");
  return `<div class="network-summary"><strong>${data.advertisers.length} nhà quảng cáo đã biết</strong><span>Các dự án dưới mỗi nhà quảng cáo tự hiện. Bấm một dự án ngoài để lấy nó làm trung tâm và bung tiếp.</span></div>${branches}`;
}

async function loadProjectNetwork(projectId) {
  const target = document.getElementById("projectNetworkBody");
  if (!target || Number(target.dataset.centerProject) !== Number(projectId)) return;
  try {
    const data = await request(`/ad-intelligence/projects/${projectId}/network`);
    const currentTarget = document.getElementById("projectNetworkBody");
    if (!currentTarget || Number(currentTarget.dataset.centerProject) !== Number(projectId)) return;
    currentTarget.innerHTML = projectNetworkHtml(data);
  } catch (error) {
    const currentTarget = document.getElementById("projectNetworkBody");
    if (currentTarget) currentTarget.innerHTML = `<div class="notice warning">Không tải được mạng lưới: ${esc(error.message)}</div>`;
  }
}

function autoCheckSourcesHtml(sources) {
  if (!sources?.length) return '<div class="step-one-empty">Chưa chạy lượt kiểm tra tự động trong cửa sổ này.</div>';
  return sources.map((item) => {
    const links = (item.source_urls || []).slice(0, 3).map((url) => safeExternalHostLink(url)).join(" · ");
    const setup = item.setup_command && item.status === "CONNECTION_REQUIRED"
      ? `<small>Cần chạy một lần: ${esc(item.setup_command)}</small>` : "";
    return `<article class="auto-check-source status-${String(item.status).toLowerCase()}"><div><strong>${esc(item.source)}</strong><span>${esc(item.status)}</span></div><p>${esc(item.detail)}</p>${links ? `<small>Nguồn: ${links}</small>` : ""}${setup}</article>`;
  }).join("");
}

function renderAutoCheckSources(sources) {
  const target = document.getElementById("projectAutoCheckSources");
  if (target) target.innerHTML = autoCheckSourcesHtml(sources);
}

async function openProjectDetail(projectId, autoCheckSources = null) {
  openTruthDrawer("Đang tải dự án…", '<div class="empty">Đang tải hồ sơ…</div>');
  try {
    const [item, check] = await Promise.all([
      request(`/portfolio/projects/${projectId}`),
      request(`/portfolio/projects/${projectId}/step-one`),
    ]);
    openTruthDrawer(`${item.brand_name} · ${item.domain}`, projectDetailHtml(item, check));
    const form = document.getElementById("projectWorkflowForm");
    form.elements.stage.value = item.stage;
    form.elements.registration_status.value = item.registration_status;
    loadProjectNetwork(item.id);
    if (autoCheckSources) renderAutoCheckSources(autoCheckSources);
  } catch (error) {
    openTruthDrawer("Không mở được dự án", `<div class="notice warning">${esc(error.message)}</div>`);
  }
}

async function runProjectAutoCheck(button) {
  const domain = button.dataset.domain;
  const message = document.getElementById("projectAutoCheckMessage");
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Đang kiểm tra…";
  message.textContent = `Đang tự lấy dữ liệu cho ${domain}…`;
  try {
    const result = await request("/portfolio/projects/auto-check", {
      method: "POST",
      body: JSON.stringify({domain, actor: "local-user"}),
    });
    await Promise.all([loadPortfolio(), loadPrograms(), loadOperations()]);
    await openProjectDetail(result.project.id, result.sources);
    const current = document.getElementById("projectAutoCheckMessage");
    if (current) current.textContent = result.decision_ready
      ? "Đã đủ đầu vào quyết định. Có thể lưu sang Bước 2."
      : `Đã kiểm tra; còn thiếu: ${result.blocking_fields.join(" · ")}.`;
  } catch (error) {
    message.textContent = `Không thể kiểm tra tự động: ${error.message}`;
    button.disabled = false;
    button.textContent = original;
  }
}

async function extractProjectTerms(button) {
  const projectId = button.dataset.projectExtractTerms;
  const message = document.getElementById("projectAutoCheckMessage");
  button.disabled = true;
  if (message) message.textContent = "Đang đọc trang Terms/Pricing và trích dẫn bằng Claude…";
  try {
    const result = await request(`/projects/${projectId}/extract-terms`, {method: "POST"});
    await openProjectDetail(projectId);
    const current = document.getElementById("projectAutoCheckMessage");
    if (current) current.textContent = `${result.cached ? "Đã dùng cache" : "Đã trích xuất"}: ${result.commission_facts.length} commission · ${result.terms_evidence.length} terms · ${result.commercial_proposals.length} gói/thanh toán. Hãy đọc nguồn rồi bấm ✓.`;
  } catch (error) {
    button.disabled = false;
    if (message) message.textContent = `Chưa trích được: ${error.message}`;
  }
}

async function reviewStepOneProposal(button) {
  const action = button.dataset.action;
  const projectId = button.dataset.projectId;
  const programId = button.dataset.programId;
  const message = document.getElementById("proposalReviewMessage") || document.getElementById("projectAutoCheckMessage");
  if (action === "ACCEPT" && !window.confirm("Chỉ bấm Chấp nhận khi trích dẫn và link nguồn đúng. Tiếp tục?")) return;
  button.disabled = true;
  if (message) message.textContent = action === "ACCEPT" ? "Đang xác nhận dữ kiện…" : "Đang bỏ đề xuất…";
  let path;
  if (button.dataset.stepCommercialId) {
    path = `/projects/${projectId}/commercial-proposals/${button.dataset.stepCommercialId}/review`;
  } else if (button.dataset.stepCommissionId) {
    path = `/programs/${programId}/commission-facts/${button.dataset.stepCommissionId}/review`;
  } else {
    path = `/programs/${programId}/evidence/${button.dataset.stepEvidenceId}/review`;
  }
  try {
    await request(path, {
      method: "POST",
      body: JSON.stringify({action, reviewed_by: "Tran"}),
    });
    await Promise.all([loadPortfolio(), loadPrograms(), loadOperations()]);
    await openProjectDetail(projectId);
    const current = document.getElementById("proposalReviewMessage") || document.getElementById("projectAutoCheckMessage");
    if (current) current.textContent = action === "ACCEPT"
      ? "Đã xác nhận và tính lại Bước 1. PPC/campaign không bị tự thay đổi ngoài đúng evidence anh vừa duyệt."
      : "Đã loại đề xuất; dữ liệu này không được dùng tính hoàn vốn.";
  } catch (error) {
    button.disabled = false;
    if (message) message.textContent = `Không xử lý được: ${error.message}`;
  }
}

async function saveProjectWorkflow(form) {
  const message = document.getElementById("projectWorkflowMessage");
  const projectId = form.dataset.projectId;
  const payload = {
    stage: form.elements.stage.value,
    registration_status: form.elements.registration_status.value,
    owner: form.elements.owner.value.trim() || null,
    next_action: form.elements.next_action.value.trim() || null,
    next_action_due_at: form.elements.next_action_due_at.value ? new Date(form.elements.next_action_due_at.value).toISOString() : null,
    actor: "local-user",
  };
  message.textContent = "Đang lưu…";
  try {
    const item = await request(`/portfolio/projects/${projectId}/workflow`, {method: "PATCH", body: JSON.stringify(payload)});
    await loadPortfolio();
    await openProjectDetail(item.id);
    document.getElementById("projectWorkflowMessage").textContent = "Đã lưu và ghi audit. Không có Google Ads write.";
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
  }
}

async function saveProjectStepOneDecision(button) {
  const message = document.getElementById("stepOneDecisionMessage");
  const projectId = button.dataset.projectId;
  const decision = button.dataset.stepOneDecision;
  button.disabled = true;
  message.textContent = "Đang lưu snapshot Bước 1…";
  try {
    const result = await request(`/portfolio/projects/${projectId}/step-one-decision`, {
      method: "POST",
      body: JSON.stringify({decision, actor: "local-user"}),
    });
    await Promise.all([loadPortfolio(), loadStepTwoProjects()]);
    await openProjectDetail(result.project.id);
    document.getElementById("stepOneDecisionMessage").textContent = decision === "PREPARE_STEP_2"
      ? "Đã lưu snapshot và đưa dự án vào Bước 2. Không có Google Ads write."
      : "Đã lưu snapshot; dự án tiếp tục ở Bước 1 để bổ sung nguồn.";
  } catch (error) {
    button.disabled = false;
    message.textContent = `Không thể lưu: ${error.message}`;
  }
}

async function loadStepTwoProjects() {
  const body = document.getElementById("stepTwoProjectRows");
  const summary = document.getElementById("stepTwoProjectSummary");
  if (!body || !summary) return;
  const items = await request("/projects/camp-plan/eligible");
  stepTwoProjectCache = items;
  summary.textContent = `${items.length} dự án PASS sẵn sàng làm nội dung`;
  body.innerHTML = items.length ? items.map((item) => {
    const signup = item.signup_url ? safeExternalLink(item.signup_url, "Mở link đăng ký") : '<span class="warning-text">Chưa có link đăng ký</span>';
    const planStatus = item.camp_plan_status === "DEPLOYED"
      ? '<span class="gate gate-ready">ĐÃ SANG BƯỚC 3</span>'
      : item.camp_plan_status === "DRAFT"
      ? '<span class="gate gate-pending">BẢN NHÁP</span>'
      : '<span class="gate">CHƯA SINH</span>';
    return `<tr>
      <td><strong>${esc(item.brand_name)}</strong><br><span class="small">${esc(item.domain)}</span></td>
      <td><span class="score">${esc(item.score_total ?? "—")}/100</span><br><span class="small">PASS</span></td>
      <td>${signup}</td>
      <td>${planStatus}</td>
      <td><div class="review-actions"><button type="button" class="button primary" data-camp-plan-project="${item.project_id}">${item.camp_plan_status ? "Mở bộ nội dung" : "Chuẩn bị content"}</button><button type="button" class="button secondary" data-project-detail="${item.project_id}">Xem Bước 1</button></div></td>
    </tr>`;
  }).join("") : '<tr><td colspan="5" class="empty">Chưa có dự án PASS. Hãy hoàn tất số liệu và bấm “Lưu và chuyển Bước 2” ở Bước 1.</td></tr>';
}

function campPlanIssueHtml(issue) {
  return `<span class="camp-plan-issue ${esc(issue.level)}">${esc(issue.message)}</span>`;
}

function campPlanLineIssues(issues, section, index) {
  return issues
    .filter((item) => item.section === section && item.index === index)
    .map(campPlanIssueHtml)
    .join("");
}

function renderCampPlanTextLines(targetId, field, section, values, maxLength, issues, multiline = false) {
  const target = document.getElementById(targetId);
  target.innerHTML = values.map((value, index) => {
    const input = multiline
      ? `<textarea rows="2" data-camp-field="${field}" data-camp-section="${section}" data-camp-index="${index}" data-camp-max="${maxLength}">${esc(value)}</textarea>`
      : `<input type="text" value="${esc(value)}" data-camp-field="${field}" data-camp-section="${section}" data-camp-index="${index}" data-camp-max="${maxLength}">`;
    return `<div class="camp-plan-line">
      <span class="camp-plan-line-number">${index + 1}</span>
      ${input}
      <span class="camp-plan-char-count ${value.length > maxLength ? "over" : ""}">${value.length}/${maxLength}</span>
      <div class="camp-plan-line-issues">${campPlanLineIssues(issues, section, index)}</div>
    </div>`;
  }).join("");
}

function renderCampPlanSitelinks(values, issues) {
  document.getElementById("campPlanSitelinks").innerHTML = values.map((item, index) => `<div class="camp-plan-line sitelink">
    <span class="camp-plan-line-number">${index + 1}</span>
    <input type="text" value="${esc(item.label)}" aria-label="Nhãn sitelink ${index + 1}" data-camp-field="sitelink-label" data-camp-index="${index}" data-camp-max="25">
    <input type="url" value="${esc(item.final_url)}" aria-label="URL sitelink ${index + 1}" data-camp-field="sitelink-url" data-camp-index="${index}">
    <div class="camp-plan-line-issues">${campPlanLineIssues(issues, "sitelinks", index)}</div>
  </div>`).join("");
}

function renderCampPlan(result) {
  activeCampPlan = result;
  const issues = result.linter || [];
  const errors = issues.filter((item) => item.level === "error");
  const warnings = issues.filter((item) => item.level === "warning");
  document.getElementById("campPlanEditor").hidden = false;
  document.getElementById("campPlanStatus").textContent = result.status === "DEPLOYED" ? "ĐÃ TRIỂN KHAI" : "BẢN NHÁP";
  document.getElementById("campPlanRefUrl").value = result.ref_url;
  const accountSelect = document.getElementById("campPlanAdsAccount");
  if (result.ads_account_id && !Array.from(accountSelect.options).some((item) => item.value === String(result.ads_account_id))) {
    accountSelect.add(new Option(result.ads_account_label || `Tài khoản #${result.ads_account_id}`, String(result.ads_account_id)));
  }
  accountSelect.value = result.ads_account_id ? String(result.ads_account_id) : "";
  document.getElementById("campPlanPlanIssues").innerHTML = issues
    .filter((item) => item.section === "plan")
    .map(campPlanIssueHtml)
    .join("");
  renderCampPlanTextLines("campPlanHeadlines", "headline", "headlines", result.plan.headlines, 30, issues);
  renderCampPlanTextLines("campPlanDescriptions", "description", "descriptions", result.plan.descriptions, 90, issues, true);
  renderCampPlanSitelinks(result.plan.sitelinks, issues);
  renderCampPlanTextLines("campPlanCallouts", "callout", "callouts", result.plan.callouts, 25, issues);
  document.getElementById("campPlanDeploy").disabled = errors.length > 0 || !result.ads_account_id || result.status === "DEPLOYED";
  document.getElementById("campPlanLintSummary").textContent = errors.length
    ? `${errors.length} lỗi · ${warnings.length} cảnh báo — sửa rồi bấm Kiểm tra lại.`
    : result.ads_account_id
      ? `Không còn lỗi · ${warnings.length} cảnh báo. Có thể chuyển sang Bước 3.`
      : `Không còn lỗi nội dung, nhưng phải chọn tài khoản Ads hợp lệ.`;
  const stepThree = document.getElementById("campPlanStepThree");
  stepThree.hidden = result.status !== "DEPLOYED";
  if (result.status === "DEPLOYED") {
    document.getElementById("campPlanStepThreeTitle").textContent = `${result.brand_name} đã sẵn sàng cho Bước 3`;
  }
}

async function loadCampPlanAccountOptions(selectedId = null) {
  const select = document.getElementById("campPlanAdsAccount");
  const items = await request("/ads-accounts/selectable");
  select.innerHTML = '<option value="">Chọn tài khoản đã sẵn sàng</option>' + items.map((item) =>
    `<option value="${item.id}">${esc(item.display_name)} · ${esc(item.email_address || "chưa có email")}</option>`
  ).join("");
  if (selectedId) select.value = String(selectedId);
}

function collectCampPlanEditor() {
  const values = (field) => Array.from(document.querySelectorAll(`[data-camp-field="${field}"]`)).map((input) => input.value);
  const labels = values("sitelink-label");
  const urls = values("sitelink-url");
  return {
    headlines: values("headline"),
    descriptions: values("description"),
    sitelinks: labels.map((label, index) => ({label, final_url: urls[index] || ""})),
    callouts: values("callout"),
  };
}

async function openCampPlanProject(projectId) {
  activeCampPlanProject = stepTwoProjectCache.find((item) => String(item.project_id) === String(projectId));
  if (!activeCampPlanProject) return;
  const workspace = document.getElementById("campPlanWorkspace");
  workspace.hidden = false;
  document.getElementById("campPlanProjectTitle").textContent = `${activeCampPlanProject.brand_name} · ${activeCampPlanProject.domain}`;
  document.getElementById("campPlanProjectMeta").innerHTML = activeCampPlanProject.signup_url
    ? `Link đăng ký: ${safeExternalLink(activeCampPlanProject.signup_url, "Mở trang đăng ký affiliate")}`
    : "Chưa có link đăng ký affiliate; vẫn có thể nhập link ref đã được cấp.";
  document.getElementById("campPlanRefUrl").value = activeCampPlanProject.ref_url || "";
  document.getElementById("campPlanMessage").textContent = "Đang mở bản đã lưu…";
  document.getElementById("campPlanEditor").hidden = true;
  document.getElementById("campPlanStepThree").hidden = true;
  await loadCampPlanAccountOptions(activeCampPlanProject.ads_account_id);
  try {
    const result = await request(`/projects/${projectId}/camp-plan`);
    renderCampPlan(result);
    document.getElementById("campPlanMessage").textContent = "Đã mở bộ nội dung đã lưu.";
  } catch (error) {
    if (error.status !== 404) throw error;
    activeCampPlan = null;
    document.getElementById("campPlanStatus").textContent = "CHƯA SINH";
    document.getElementById("campPlanMessage").textContent = "Nhập link ref rồi bấm Sinh content.";
  }
  workspace.scrollIntoView({behavior: "smooth", block: "start"});
}

async function generateActiveCampPlan(useExistingPlan) {
  if (!activeCampPlanProject) {
    document.getElementById("campPlanMessage").textContent = "Hãy chọn một dự án PASS trong danh sách.";
    return;
  }
  const refUrl = document.getElementById("campPlanRefUrl").value.trim();
  if (!safeExternalUrl(refUrl)) {
    document.getElementById("campPlanMessage").textContent = "Link ref phải là URL đầy đủ bắt đầu bằng http:// hoặc https://";
    return;
  }
  const message = document.getElementById("campPlanMessage");
  message.textContent = useExistingPlan ? "Đang kiểm tra lại từng dòng…" : "Đang sinh bộ nội dung…";
  const payload = {ref_url: refUrl};
  const adsAccountId = Number(document.getElementById("campPlanAdsAccount").value || 0);
  if (!adsAccountId) {
    message.textContent = "Hãy chọn tài khoản Ads READY có email chín và sạch.";
    return;
  }
  payload.ads_account_id = adsAccountId;
  if (useExistingPlan) payload.existing_plan = collectCampPlanEditor();
  try {
    const result = await request(`/projects/${activeCampPlanProject.project_id}/camp-plan/generate`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderCampPlan(result);
    message.textContent = result.has_errors
      ? "Đã lưu bản nháp. Hãy sửa các dòng đỏ rồi kiểm tra lại."
      : "Đã lưu bản nháp và kiểm tra xong. Không có thao tác ghi Google Ads.";
    await loadStepTwoProjects();
  } catch (error) {
    message.textContent = `Không thể sinh nội dung: ${error.message}`;
  }
}

async function deployActiveCampPlan() {
  if (!activeCampPlanProject || !activeCampPlan) return;
  const button = document.getElementById("campPlanDeploy");
  const message = document.getElementById("campPlanMessage");
  button.disabled = true;
  message.textContent = "Đang lưu trạng thái và bàn giao sang Bước 3…";
  try {
    const result = await request(`/projects/${activeCampPlanProject.project_id}/camp-plan/deploy`, {
      method: "POST",
      body: JSON.stringify({actor: "local-user"}),
    });
    renderCampPlan(result);
    await loadStepTwoProjects();
    message.textContent = "Đã triển khai nội bộ sang Bước 3. Chưa tạo hay sửa Google Ads.";
    document.getElementById("campPlanStepThree").scrollIntoView({behavior: "smooth", block: "center"});
  } catch (error) {
    button.disabled = false;
    message.textContent = `Chưa thể triển khai: ${error.message}`;
  }
}

const resourceTypeLabels = {
  paypal: "PayPal", payoneer: "Payoneer", wise: "Wise", card: "Thẻ",
  crypto_wallet: "Ví crypto", exchange: "Sàn", sim: "SIM", device: "Thiết bị",
  website: "Website", social: "Mạng xã hội",
};

function resourceStageLabel(value) {
  return {SOAK: "Ngâm 48 giờ", DECLARED: "Cần khai báo", INTERACTING: "Đang nuôi", CHIN: "CHÍN"}[value] || value;
}

function renderResourceOverview(data) {
  resourceOverview = data;
  const kpis = data.kpis || {};
  document.getElementById("resourceKpis").innerHTML = [
    metric("Email chín sạch", kpis.chin || 0, "Đủ tuổi và không có lịch sử ngách hạn chế"),
    metric("Đang nuôi", kpis.nurturing || 0, "Tự tính số ngày còn lại"),
    metric("Email bẩn", kpis.dirty || 0, "Không dùng cho dự án mới"),
    metric("TK Ads sẵn sàng", kpis.accounts_ready || 0, "Có thể chọn ở Bước 2"),
  ].join("");
  document.getElementById("resourcePlanSource").textContent = data.planned_camps_source === "manual"
    ? `Đang tính theo kế hoạch nhập tay: ${data.planned_camps_this_month} campaign.`
    : `Tự đếm ${data.planned_camps_this_month} bộ campaign đã lưu trong tháng.`;

  const alerts = data.alerts || [];
  document.getElementById("resourceAlertSummary").textContent = `${alerts.length} CẢNH BÁO`;
  document.getElementById("resourceAlerts").innerHTML = alerts.length ? alerts.map((item) => `
    <div class="resource-alert ${esc(item.level)}">
      <div><strong>${esc(item.subject)}</strong><span>${esc(item.code)}</span></div>
      <p>${esc(item.message)}</p>
    </div>`).join("") : '<div class="notice">Chưa có cảnh báo tài nguyên.</div>';

  const emails = data.emails || [];
  document.getElementById("resourceEmailSummary").textContent = `${emails.length} EMAIL`;
  document.getElementById("resourceEmailRows").innerHTML = emails.length ? emails.map((item) => {
    const nurture = item.nurture_status;
    const tasks = nurture.tasks_today || [];
    const done = new Set(nurture.tasks_done || []);
    return `<tr data-nurture-email="${item.id}">
      <td><strong>${esc(item.address)}</strong><br><span class="small">${esc(item.source)}${item.status_override ? ` · ${esc(item.status_override)}` : ""}</span></td>
      <td><span class="resource-stage stage-${esc(nurture.stage.toLowerCase())}">${esc(resourceStageLabel(nurture.stage))}</span>${nurture.is_dirty ? '<br><span class="resource-dirty">BẨN</span>' : ""}</td>
      <td>${nurture.age_days} ngày<br><span class="small">${nurture.chin_eta_days ? `còn ${nurture.chin_eta_days} ngày` : "đã đủ tuổi"}</span></td>
      <td>${esc((item.usage_history || []).join(", ") || "Chưa ghi nhận")}</td>
      <td><div class="nurture-tasks">${tasks.length ? tasks.map((task) => `<label><input type="checkbox" data-nurture-task value="${esc(task)}" ${done.has(task) ? "checked" : ""}><span>${esc(task)}</span></label>`).join("") : '<span class="small">Không có tác vụ hôm nay.</span>'}</div></td>
      <td>${tasks.length ? `<button class="button secondary small-button" type="button" data-save-nurture="${item.id}">Lưu tick</button>` : "—"}</td>
    </tr>`;
  }).join("") : '<tr><td colspan="6" class="empty">Chưa có email. Thêm email ở biểu mẫu phía trên.</td></tr>';

  const emailSelect = document.getElementById("resourceAdsEmail");
  const currentEmail = emailSelect.value;
  emailSelect.innerHTML = '<option value="">Chưa gắn email</option>' + emails.map((item) =>
    `<option value="${item.id}">${esc(item.address)} · ${esc(resourceStageLabel(item.nurture_status.stage))}${item.nurture_status.is_dirty ? " · BẨN" : ""}</option>`
  ).join("");
  emailSelect.value = currentEmail;

  const accounts = data.ads_accounts || [];
  document.getElementById("resourceAccountSummary").textContent = `${accounts.length} TÀI KHOẢN`;
  document.getElementById("resourceAccountRows").innerHTML = accounts.length ? accounts.map((item) => `<tr>
    <td>${esc(item.email_address || "Chưa gắn email")}</td>
    <td><strong>${esc(item.display_name)}</strong><br><span class="small mono">${esc(item.external_id)}</span></td>
    <td>${esc(item.type || "—")}<br><span class="small">Thuê $${Number(item.rent_cost).toLocaleString("en-US")} · phí ${Number(item.spend_fee_pct)}%</span></td>
    <td><span class="badge">${esc(item.state)}</span><br><span class="small">${esc(item.health)}</span></td>
    <td>${item.camp_plan_id ? `<strong>#${item.camp_plan_id}</strong><br><span class="small">${esc(item.camp_plan_status || "—")}</span>` : "Chưa tạo"}</td>
    <td>${item.current_project_domain ? `<strong>${esc(item.current_project_domain)}</strong>` : "Đang rảnh"}</td>
    <td>${item.selectable ? '<span class="risk-green">ĐƯỢC CHỌN</span>' : '<span class="small">Chưa đủ điều kiện</span>'}</td>
  </tr>`).join("") : '<tr><td colspan="7" class="empty">Chưa có tài khoản Ads.</td></tr>';

  document.getElementById("resourceTypeChips").innerHTML = Object.entries(data.type_counts || {}).map(([key, count]) =>
    `<span class="resource-type-chip"><strong>${count}</strong>${esc(resourceTypeLabels[key] || key)}</span>`
  ).join("");
  const resources = data.resources || [];
  document.getElementById("resourceInventoryRows").innerHTML = resources.length ? resources.map((item) => `<tr>
    <td>${esc(resourceTypeLabels[item.type] || item.type)}</td><td><strong>${esc(item.label)}</strong></td>
    <td>$${Number(item.monthly_in_usd).toLocaleString("en-US", {maximumFractionDigits: 2})}</td>
    <td>${esc((item.linked_gateways || []).join(", ") || "—")}</td><td>${esc(item.owner_name || "—")}</td><td>${esc(item.note || "—")}</td>
  </tr>`).join("") : '<tr><td colspan="6" class="empty">Chưa có tài nguyên.</td></tr>';
}

async function loadResources() {
  const planned = document.getElementById("resourcePlannedCamps").value;
  const query = planned === "" ? "" : `?planned_camps=${encodeURIComponent(planned)}`;
  renderResourceOverview(await request(`/resources/overview${query}`));
}

async function submitResourceEmail(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = formObject(form);
  const payload = {
    address: values.address,
    source: values.source,
    created_at: new Date(values.created_at).toISOString(),
    declared_done: form.elements.declared_done.checked,
    device_changes: Number(values.device_changes || 0),
    usage_history: String(values.usage_history || "").split(",").map((item) => item.trim()).filter(Boolean),
    note: values.note || null,
  };
  const message = document.getElementById("resourceEmailMessage");
  try {
    await request("/emails", {method: "POST", body: JSON.stringify(payload)});
    form.reset();
    setLocalDateTime(form.elements.created_at);
    form.elements.device_changes.value = "0";
    message.textContent = "Đã lưu email và tự tính lịch nuôi.";
    await loadResources();
  } catch (error) { message.textContent = `Lỗi: ${error.message}`; }
}

async function submitResourceAdsAccount(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = formObject(form);
  const payload = {
    email_id: values.email_id ? Number(values.email_id) : null,
    type: values.type, display_name: values.display_name,
    state: values.state, health: values.health,
    rent_cost: Number(values.rent_cost || 0), spend_fee_pct: Number(values.spend_fee_pct || 0),
    note: values.note || null,
  };
  const message = document.getElementById("resourceAdsMessage");
  try {
    await request("/ads-accounts", {method: "POST", body: JSON.stringify(payload)});
    form.reset();
    form.elements.rent_cost.value = "0";
    form.elements.spend_fee_pct.value = "0";
    message.textContent = "Đã lưu tài khoản. Bước 2 chỉ hiện khi đủ điều kiện.";
    await loadResources();
    await loadCampPlanAccountOptions();
  } catch (error) { message.textContent = `Lỗi: ${error.message}`; }
}

async function submitResourceInventory(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = formObject(form);
  const payload = {
    type: values.type, label: values.label,
    monthly_in_usd: Number(values.monthly_in_usd || 0),
    linked_gateways: String(values.linked_gateways || "").split(",").map((item) => item.trim()).filter(Boolean),
    owner_name: values.owner_name || null, note: values.note || null,
  };
  const message = document.getElementById("resourceInventoryMessage");
  try {
    await request("/resources", {method: "POST", body: JSON.stringify(payload)});
    form.reset();
    form.elements.monthly_in_usd.value = "0";
    message.textContent = "Đã lưu và tính lại cảnh báo.";
    await loadResources();
  } catch (error) { message.textContent = `Lỗi: ${error.message}`; }
}

async function saveNurtureCheck(button) {
  const row = button.closest("tr");
  const tasksDone = Array.from(row.querySelectorAll("[data-nurture-task]:checked")).map((item) => item.value);
  button.disabled = true;
  try {
    await request(`/emails/${button.dataset.saveNurture}/nurture-check`, {
      method: "POST", body: JSON.stringify({tasks_done: tasksDone}),
    });
    await loadResources();
  } catch (error) {
    button.disabled = false;
    window.alert(`Chưa lưu được checklist: ${error.message}`);
  }
}

async function loadHealth() {
  try {
    const data = await request("/health");
    setApiStatus(true, `API ${data.version} · ${data.database}`);
  } catch (error) {
    setApiStatus(false, `Mất kết nối: ${error.message}`);
  }
}

async function loadSummary() {
  const data = await request("/dashboard/summary");
  document.getElementById("summaryCards").innerHTML = [
    metric("Projects", data.projects, "Dự án đã lưu trong radar"),
    metric("Advertisers", data.advertisers, "Advertiser xác minh khác nhau"),
    metric("Observations", data.observations, "Snapshot quan hệ advertiser ↔ project"),
    metric("Terms warnings", data.programs_with_terms_warnings, "Chỉ cảnh báo; không loại dự án"),
  ].join("");
}

async function loadOperations() {
  const data = await request("/operations/inbox");
  const summary = document.getElementById("operationsSummary");
  const body = document.getElementById("operationsRows");
  summary.textContent = `${data.requires_user_count} cần xử lý · ${data.warning_count} cảnh báo`;
  if (!data.items.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">Không có ngoại lệ đang mở.</td></tr>';
    return;
  }
  body.innerHTML = data.items.map((item) => {
    const source = item.source_url
      ? safeExternalLink(item.source_url, "Mở nguồn")
      : "—";
    const evidencePack = item.program_id
      ? `<button class="button operation-export-pack" data-evidence-pack-program="${esc(item.program_id)}">Tải pack</button>`
      : "";
    return `<tr>
      <td>${stateBadge(item.severity)}</td>
      <td><strong>${esc(item.title)}</strong><br><span class="small">${esc(item.item_type)}</span></td>
      <td>${esc(item.program_name || item.merchant_domain || "—")}</td>
      <td>${esc(item.detail)}</td>
      <td>${source}</td>
      <td><div class="review-actions"><button class="button operation-open" data-operation-view="${esc(item.action_view)}" data-operation-item-type="${esc(item.item_type)}" data-operation-entity-id="${esc(item.entity_id || "")}" data-program-id="${esc(item.program_id || "")}" data-domain="${esc(item.merchant_domain || "")}">${esc(item.action_label)}</button>${evidencePack}</div></td>
    </tr>`;
  }).join("");
}

const automationJobLabels = {
  TERMS_RESEARCH: "Rà Terms có nguồn",
  ADS_IMPORT: "Nhập Google Ads",
  COMMISSION_IMPORT: "Nhập commission",
  CAMPAIGN_AUTO_MAP: "Ghép campaign",
  PROJECT_DISCOVERY: "Tìm dữ liệu dự án",
  ADVERTISER_REFRESH: "Làm mới advertiser",
};

const automationStatusLabels = {
  PENDING: "Chờ chạy",
  RUNNING: "Đang chạy",
  RETRY_WAIT: "Chờ thử lại",
  SUCCEEDED: "Đã xong",
  DEAD_LETTER: "Cần kiểm tra",
  CANCELLED: "Đã hủy",
};

function automationStateBadge(status) {
  const cls = status === "SUCCEEDED"
    ? "gate-ready"
    : status === "DEAD_LETTER" ? "gate-blocked" : "gate-pending";
  return `<span class="gate ${cls}">${esc(automationStatusLabels[status] || status)}</span>`;
}

async function loadAutomationQueue() {
  const [summary, jobs] = await Promise.all([
    request("/automation/queue/summary"),
    request("/automation/queue?limit=30"),
  ]);
  const badge = document.getElementById("automationQueueSummary");
  const rows = document.getElementById("automationQueueRows");
  badge.textContent = `${summary.due} đến hạn · ${summary.retry_wait} chờ lại · ${summary.dead_letter} lỗi cuối`;
  badge.className = `badge ${summary.dead_letter ? "runtime-attention" : "runtime-healthy"}`;
  if (!jobs.length) {
    rows.innerHTML = '<tr><td colspan="6" class="empty">Worker đang rảnh; công việc sẽ xuất hiện khi đến hạn.</td></tr>';
    return;
  }
  rows.innerHTML = jobs.map((job) => {
    const result = job.last_error_message
      ? `${job.last_error_code || "ERROR"}: ${job.last_error_message}`
      : job.result_json?.status || (job.status === "SUCCEEDED" ? "Đã hoàn tất an toàn" : "—");
    const retryable = ["RETRY_WAIT", "DEAD_LETTER", "CANCELLED"].includes(job.status);
    const when = job.completed_at || job.run_after;
    return `<tr data-automation-job-row="${job.id}">
      <td><strong>${esc(automationJobLabels[job.job_type] || job.job_type)}</strong><br><span class="small">#${job.id} · ${esc(job.created_by)}</span></td>
      <td>${automationStateBadge(job.status)}</td>
      <td>${job.attempts}/${job.max_attempts}</td>
      <td>${esc(formatRuntimeTime(when))}</td>
      <td>${esc(result)}</td>
      <td>${retryable ? `<button class="button automation-retry" data-automation-job-id="${job.id}">Thử lại ngay</button>` : "Tự động"}</td>
    </tr>`;
  }).join("");
}

async function retryAutomationJob(jobId) {
  await request(`/automation/queue/${jobId}/retry`, {
    method: "POST",
    body: JSON.stringify({actor: "local-user", note: "Operator requested retry from Command Center"}),
  });
  await loadAutomationQueue();
}

function focusAutomationJobTarget(jobId) {
  const rows = Array.from(
    document.querySelectorAll("#automationQueueRows tr[data-automation-job-row]"),
  );
  const target = rows.find((row) => row.dataset.automationJobRow === String(jobId));
  if (!target) {
    document.getElementById("automationQueueSummary").scrollIntoView({behavior: "auto", block: "center"});
    return "MISSING";
  }
  rows.forEach((row) => row.classList.remove("review-row-target"));
  target.classList.add("review-row-target");
  target.scrollIntoView({behavior: "auto", block: "center"});
  const retryButton = target.querySelector(".automation-retry");
  if (retryButton) retryButton.focus({preventScroll: true});
  return "EXACT";
}

function formatRuntimeTime(value) {
  if (!value) return "Chưa có";
  return new Date(value).toLocaleString("vi-VN");
}

function formatGoogleAdsCustomerId(value) {
  const digits = String(value || "").replace(/\D/g, "");
  return digits.length === 10
    ? `${digits.slice(0, 3)}-${digits.slice(3, 6)}-${digits.slice(6)}`
    : String(value || "");
}

async function loadRuntimeStatus() {
  const data = await request("/operations/runtime-status");
  const badge = document.getElementById("runtimeBadge");
  const labels = {
    HEALTHY: "24/7 đang hoạt động",
    STARTING: "Đang khởi động",
    ATTENTION: "Cần kiểm tra",
    NOT_CONFIGURED: "Chưa bật 24/7",
  };
  badge.textContent = labels[data.status] || data.status;
  badge.className = `badge runtime-${data.status.toLowerCase()}`;

  const services = data.server_service_loaded && data.maintenance_service_loaded
    ? "Server + bảo trì"
    : data.server_service_loaded ? "Chỉ server" : data.maintenance_service_loaded ? "Chỉ bảo trì" : "Chưa bật";
  const apiDetail = data.google_ads_api_sync_status
    ? `${esc(data.google_ads_api_sync_status)} · ${data.google_ads_api_rows_read} dòng · ${data.google_ads_api_reconciliation_differences} lệch`
    : `${data.google_ads_api_customer_count} tài khoản · chỉ đọc${data.google_ads_login_customer_id_configured ? " · MCC đã cấu hình" : ""}`;
  const apiSchedule = data.google_ads_api_next_attempt_at
    ? ` · lần tới ${esc(formatRuntimeTime(data.google_ads_api_next_attempt_at))}`
    : "";
  const adsCustomerIds = (data.google_ads_customer_ids || [])
    .map(formatGoogleAdsCustomerId)
    .filter(Boolean);
  const adsCustomerLabel = adsCustomerIds.join(", ") || "chưa cấu hình";
  document.getElementById("runtimeCards").innerHTML = [
    `<div class="runtime-item"><span>Dịch vụ</span><strong>${esc(services)}</strong><small>${data.server_service_loaded && data.maintenance_service_loaded ? "Đã nạp trên macOS" : "Thiếu dịch vụ tự chạy"}</small></div>`,
    `<div class="runtime-item"><span>Bảo trì gần nhất</span><strong>${esc(data.maintenance_status || "Chưa chạy")}</strong><small>${esc(formatRuntimeTime(data.maintenance_last_ended_at))}</small></div>`,
    `<div class="runtime-item"><span>Backup hợp lệ gần nhất</span><strong>${data.latest_scheduled_backup_size_bytes == null ? "Chưa có" : esc(humanBytes(data.latest_scheduled_backup_size_bytes))}</strong><small>${esc(formatRuntimeTime(data.latest_scheduled_backup_at))}${data.scheduled_backup_due ? " · đã đến hạn" : " · đã xác minh"}${data.scheduled_backup_invalid_count ? ` · ${data.scheduled_backup_invalid_count} bản bị loại` : ""}</small></div>`,
    `<div class="runtime-item"><span>Lần rà Terms còn mới</span><strong>${data.terms_fresh}/${data.programs_total}</strong><small>${data.terms_due_count} đã đến hạn · ${data.terms_retry_pending} chờ tự thử lại</small></div>`,
    `<div class="runtime-item"><span>Terms đến hạn gần nhất</span><strong>${esc(formatRuntimeTime(data.terms_next_refresh_at))}</strong><small>Kết quả ổn định 24 giờ · lỗi web 6 giờ</small></div>`,
    `<div class="runtime-item"><span>Lần rà Terms dự kiến</span><strong>${esc(formatRuntimeTime(data.terms_next_scheduled_refresh_at))}</strong><small>Căn theo heartbeat bảo trì 30 phút</small></div>`,
    `<div class="runtime-item"><span>Terms đã xác minh</span><strong>${data.programs_terms_ok}/${data.programs_total}</strong><small>${data.programs_terms_warnings} chương trình vẫn cảnh báo</small></div>`,
    `<div class="runtime-item"><span>Google Ads tự nhập</span><strong>${esc(data.ads_import_status || "Chưa quét")}</strong><small>${data.ads_rows_read} dòng · tài khoản ${esc(adsCustomerLabel)} · dữ liệu đến ${esc(data.ads_latest_metric_date || "chưa rõ")}${data.ads_confirmed_file_count ? ` · giữ ${data.ads_confirmed_file_count} nguồn đã xác nhận` : ""}${data.ads_latest_report_source_at ? ` · file nguồn ${esc(formatRuntimeTime(data.ads_latest_report_source_at))}` : ""}${data.ads_next_intraday_refresh_at ? ` · làm mới sau ${esc(formatRuntimeTime(data.ads_next_intraday_refresh_at))}` : ""}${data.ads_last_confirmed_at ? ` · xác nhận ${esc(formatRuntimeTime(data.ads_last_confirmed_at))}` : ""}${data.ads_campaign_ids_recovered ? ` · tự khôi phục ${data.ads_campaign_ids_recovered} Campaign ID` : ""}${data.ads_files_content_detected ? ` · tự nhận diện ${data.ads_files_content_detected} file đổi tên` : ""}${data.ads_files_account_mismatch ? ` · chặn ${data.ads_files_account_mismatch} file sai tài khoản` : ""}${data.ads_files_missing_columns ? ` · ${data.ads_files_missing_columns} file thiếu cột` : ""}${data.ads_files_duplicate_skipped ? ` · bỏ qua ${data.ads_files_duplicate_skipped} bản trùng` : ""}${data.ads_files_superseded ? ` · chặn ${data.ads_files_superseded} snapshot cũ` : ""}${data.ads_files_retried_after_error ? ` · thử lại ${data.ads_files_retried_after_error} file lỗi` : ""}${data.ads_files_retried_after_mapping ? ` · thử lại ${data.ads_files_retried_after_mapping} file chưa ghép` : ""}</small></div>`,
    `<div class="runtime-item"><span>Tự ghép campaign</span><strong>${data.campaign_auto_map_mapped} mới</strong><small>${data.campaign_auto_map_unresolved} chưa ghép · giữ ${data.campaign_auto_map_preserved_existing} mapping cũ</small></div>`,
    `<div class="runtime-item"><span>Commission tự nhập</span><strong>${esc(data.commission_import_status || "Chưa quét")}</strong><small>${data.commission_rows_read} dòng · ${data.commission_files_seen} file${data.commission_files_retried_after_error ? ` · thử lại ${data.commission_files_retried_after_error} lỗi` : ""}${data.commission_files_retried_after_mapping ? ` · thử lại ${data.commission_files_retried_after_mapping} thiếu mapping` : ""}</small></div>`,
    `<div class="runtime-item"><span>Google Ads API</span><strong>${esc(data.google_ads_api_status || "Chưa kiểm tra")}</strong><small>${apiDetail}${apiSchedule}</small></div>`,
  ].join("");

  const message = document.getElementById("runtimeMessage");
  if (data.scheduled_backup_due) {
    message.textContent = "Backup hợp lệ đã đến hạn; heartbeat bảo trì sẽ tự tạo bản thay thế. Backup lỗi không được tính là an toàn.";
    message.className = "runtime-message warning";
  } else if (data.ads_files_account_mismatch > 0) {
    message.textContent = `Đã chặn ${data.ads_files_account_mismatch} báo cáo Google Ads sai tài khoản. Hãy đăng nhập Customer ID ${adsCustomerLabel} và xuất lại có cột Customer ID; file chưa được nhập, campaign cũ giữ nguyên.`;
    message.className = "runtime-message warning";
  } else if (data.ads_files_missing_columns > 0) {
    message.textContent = `${data.ads_files_missing_columns} báo cáo Ads gần nhất thiếu cột; mở Operations Inbox để xem đúng vị trí cần thêm trong Google Ads.`;
    message.className = "runtime-message warning";
  } else if (data.ads_data_stale) {
    message.textContent = `Dữ liệu Google Ads mới nhất chỉ đến ${data.ads_latest_metric_date}; mở Operations Inbox để xem cách xuất báo cáo mới.`;
    message.className = "runtime-message warning";
  } else if (data.ads_intraday_refresh_due) {
    message.textContent = "Snapshot Google Ads hôm nay đã hơn 6 giờ; hệ thống sẽ ưu tiên làm mới bằng phiên đọc-chỉ. Campaign không bị sửa hoặc dừng.";
    message.className = "runtime-message warning";
  } else if (data.ads_error_count > 0) {
    message.textContent = `${data.ads_error_count} báo cáo Ads chưa đọc được; mở Operations Inbox để xem nguyên nhân và bước xử lý an toàn.`;
    message.className = "runtime-message warning";
  } else if (data.commission_mapping_required_count > 0) {
    message.textContent = `${data.commission_mapping_required_count} báo cáo commission chưa xác định được chương trình; mở Operations Inbox để xem cách đặt tên file.`;
    message.className = "runtime-message warning";
  } else if (data.commission_error_count > 0) {
    message.textContent = `${data.commission_error_count} báo cáo commission chưa đọc được; file chưa được nhập và doanh thu cũ vẫn giữ nguyên.`;
    message.className = "runtime-message warning";
  } else if (data.maintenance_error) {
    message.textContent = `Bảo trì gần nhất có lỗi: ${data.maintenance_error}`;
    message.className = "runtime-message warning";
  } else if (data.status === "NOT_CONFIGURED") {
    message.textContent = "Chế độ 24/7 chưa được bật; mở ENABLE-AFI-OS-24-7.command đúng một lần.";
    message.className = "runtime-message warning";
  } else if (data.status === "ATTENTION") {
    message.textContent = "Một dịch vụ hoặc lịch bảo trì cần kiểm tra; dữ liệu và campaign vẫn được giữ nguyên.";
    message.className = "runtime-message warning";
  } else if (data.google_ads_api_status !== "READY") {
    message.textContent = "Google Ads API chỉ-đọc cần file OAuth Desktop JSON + Developer Token; mở SETUP-GOOGLE-ADS-READ-ONLY.command và nhập Manager Customer ID nếu token thuộc MCC. Hệ thống kiểm tra quyền đọc trước khi lưu Keychain; CSV vẫn đang hoạt động.";
    message.className = "runtime-message warning";
  } else {
    message.textContent = `Lần bảo trì tiếp theo dự kiến: ${formatRuntimeTime(data.maintenance_next_due_at)} · backup tiếp theo: ${formatRuntimeTime(data.next_backup_due_at)}.`;
    message.className = "runtime-message";
  }
}

function focusCaptureReviewTarget(captureId) {
  const panel = document.getElementById("captureReviewPanel");
  const message = document.getElementById("captureReviewMessage");
  const rows = Array.from(
    document.querySelectorAll("#captureReviewRows tr[data-capture-review-id]"),
  );
  const exactRow = rows.find((row) => row.dataset.captureReviewId === String(captureId));
  const targetRow = exactRow || rows[0];

  if (!targetRow) {
    panel.scrollIntoView({behavior: "auto", block: "start"});
    panel.focus({preventScroll: true});
    message.textContent = "Snapshot đã được xử lý và hàng đợi hiện trống. Operations Inbox đã được làm mới.";
    return "EMPTY";
  }

  rows.forEach((row) => row.classList.remove("review-row-target"));
  targetRow.classList.add("review-row-target");
  targetRow.scrollIntoView({behavior: "auto", block: "center"});
  const inputs = Array.from(targetRow.querySelectorAll("[data-review-advertiser], [data-review-domain]"));
  const firstBlankInput = inputs.find((input) => !input.value.trim());
  const focusTarget = firstBlankInput
    || targetRow.querySelector('[data-capture-review-action="ACCEPT"]');
  if (focusTarget) focusTarget.focus({preventScroll: true});

  const targetId = targetRow.dataset.captureReviewId;
  if (exactRow) {
    message.textContent = `Đã mở snapshot #${targetId}. Kiểm tra evidence trước khi quyết định.`;
    return "EXACT";
  }
  message.textContent = `Snapshot #${captureId} không còn chờ duyệt; đã chuyển tới snapshot #${targetId} cũ nhất còn lại.`;
  return "FALLBACK";
}

async function openOperation(button) {
  const view = button.dataset.operationView;
  const itemType = button.dataset.operationItemType;
  const entityId = button.dataset.operationEntityId;
  const isCaptureReviewOperation = view === "intelligence" && itemType === "AD_CAPTURE_REVIEW";
  const isAutomationDeadLetter = view === "command" && itemType === "AUTOMATION_DEAD_LETTER";
  switchView(view, {loadData: !isCaptureReviewOperation});
  if (isAutomationDeadLetter) {
    await loadAutomationQueue();
    focusAutomationJobTarget(entityId);
    return;
  }
  if (isCaptureReviewOperation) {
    await Promise.all([loadCaptureReviewQueue(), loadCaptures()]);
    const focusResult = focusCaptureReviewTarget(entityId);
    if (focusResult !== "EXACT") await loadOperations();
    return;
  }
  if (view === "programs") {
    await loadPrograms();
    const programId = button.dataset.programId;
    if (programId) {
      setEvidenceProgramSelection(programId);
      await Promise.all([
        loadEvidence(programId),
        loadCommissionFacts(programId),
        loadResearchAttempts(programId),
      ]);
    } else if (button.dataset.domain) {
      document.querySelector('#researchForm input[name="domain"]').value = button.dataset.domain;
    }
  }
  if (view === "finance") await loadFinance();
  if (view === "exposure") await loadExposure();
}

async function loadRadar() {
  const items = await request("/ad-intelligence/radar");
  const body = document.getElementById("radarRows");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="5" class="empty">Chưa có dữ liệu. Hãy lưu snapshot đầu tiên.</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => `
    <tr>
      <td><strong>${esc(item.brand_name)}</strong><br><span class="small">${esc(item.domain)} · ${esc(item.category || "Chưa phân loại")}</span></td>
      <td>${item.distinct_advertisers == null ? "Chưa thu thập" : item.distinct_advertisers}</td>
      <td>${item.active_advertisers_30d == null ? (item.distinct_advertisers == null ? "Chưa thu thập" : "Chưa đủ dữ liệu") : item.active_advertisers_30d}</td>
      <td>${item.top_advertiser_share == null ? (item.distinct_advertisers == null ? "Chưa thu thập" : "Chưa đủ dữ liệu") : `${Math.round(item.top_advertiser_share * 100)}%`}</td>
      <td><span class="score">${item.independent_advertiser_score == null ? "—" : item.independent_advertiser_score}</span><br><span class="small">${esc(item.score_label)}</span></td>
    </tr>`).join("");
}

function renderGraph(data) {
  const canvas = document.getElementById("graphCanvas");
  if (!data.nodes.length) {
    canvas.innerHTML = '<div class="empty">Chưa có graph.</div>';
    return;
  }
  const width = 720;
  const rowGap = 48;
  const advertisers = data.nodes.filter((n) => n.type === "ADVERTISER");
  const projects = data.nodes.filter((n) => n.type === "PROJECT");
  const height = Math.max(310, Math.max(advertisers.length, projects.length) * rowGap + 60);
  const positions = new Map();
  advertisers.forEach((node, i) => positions.set(node.id, { x: 145, y: 45 + i * rowGap }));
  projects.forEach((node, i) => positions.set(node.id, { x: 570, y: 45 + i * rowGap }));
  const lines = data.edges.map((edge) => {
    const a = positions.get(edge.source);
    const b = positions.get(edge.target);
    if (!a || !b) return "";
    const opacity = Math.min(.75, .18 + edge.weight * .08);
    return `<path d="M ${a.x + 65} ${a.y} C 340 ${a.y}, 375 ${b.y}, ${b.x - 65} ${b.y}" fill="none" stroke="#7da899" stroke-width="${Math.min(6, 1 + edge.weight)}" opacity="${opacity}"/>`;
  }).join("");
  const nodeSvg = data.nodes.map((node) => {
    const p = positions.get(node.id);
    const isAdvertiser = node.type === "ADVERTISER";
    const fill = isAdvertiser ? "#173f34" : "#e3f2ed";
    const text = isAdvertiser ? "#fff" : "#174d3e";
    const label = node.label.length > 22 ? `${node.label.slice(0, 21)}…` : node.label;
    return `<g><rect x="${p.x - 65}" y="${p.y - 16}" width="130" height="32" rx="10" fill="${fill}"/><text x="${p.x}" y="${p.y + 4}" text-anchor="middle" font-size="10" fill="${text}">${esc(label)}</text></g>`;
  }).join("");
  canvas.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Advertiser project graph">
    <text x="80" y="20" class="graph-label">ADVERTISERS</text><text x="505" y="20" class="graph-label">PROJECTS</text>${lines}${nodeSvg}</svg>`;
}

async function loadGraph() {
  renderGraph(await request("/ad-intelligence/graph"));
}

async function loadCaptures() {
  const items = await request("/ad-intelligence/captures?limit=30");
  const body = document.getElementById("captureRows");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="4" class="empty">Chưa có snapshot.</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => {
    const p = item.parsed_payload || {};
    const label = [p.advertiser_name, p.project_domain].filter(Boolean).join(" → ") || "Chưa parse";
    return `<tr><td>${new Date(item.captured_at).toLocaleString("vi-VN")}</td><td>${esc(item.status)}</td><td>${safeExternalLink(item.source_url, "Mở nguồn")}</td><td>${esc(label)}</td></tr>`;
  }).join("");
}

async function loadCaptureReviewQueue() {
  const items = await request("/ad-intelligence/captures/review-queue?limit=50");
  const summary = document.getElementById("captureReviewSummary");
  const body = document.getElementById("captureReviewRows");
  summary.textContent = `${items.length} chờ duyệt`;
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="5" class="empty">Không có snapshot nào cần duyệt.</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => {
    const parsed = item.parsed_payload || {};
    const rawEvidence = item.selected_text || item.visible_text || item.page_title || "Không có đoạn text";
    const evidence = rawEvidence.length > 180 ? `${rawEvidence.slice(0, 179)}…` : rawEvidence;
    return `<tr data-capture-review-id="${esc(item.id)}">
      <td>${new Date(item.captured_at).toLocaleString("vi-VN")}<br>${safeExternalLink(item.source_url, "Mở nguồn")}</td>
      <td><div class="review-evidence-preview">${esc(evidence)}</div>
        <details class="review-evidence-details"><summary>Xem đầy đủ evidence</summary><div class="review-evidence-full">${esc(rawEvidence)}</div></details>
      </td>
      <td><input class="review-inline-input" data-review-advertiser value="${esc(parsed.advertiser_name || "")}" placeholder="Tên advertiser"></td>
      <td><input class="review-inline-input" data-review-domain value="${esc(parsed.project_domain || "")}" placeholder="example.com"></td>
      <td><div class="review-actions">
        <button class="button" data-capture-review-action="ACCEPT">Chấp nhận</button>
        <button class="button danger" data-capture-review-action="REJECT">Loại</button>
      </div></td>
    </tr>`;
  }).join("");
}

async function reviewCapture(button) {
  const row = button.closest("tr[data-capture-review-id]");
  if (!row) return;
  const action = button.dataset.captureReviewAction;
  const captureId = row.dataset.captureReviewId;
  const summary = document.getElementById("captureReviewSummary");
  const message = document.getElementById("captureReviewMessage");
  const payload = {action, reviewed_by: "local-user"};
  if (action === "ACCEPT") {
    payload.advertiser_name = row.querySelector("[data-review-advertiser]").value.trim();
    payload.project_domain = row.querySelector("[data-review-domain]").value.trim();
    if (!payload.advertiser_name || !payload.project_domain) {
      message.textContent = `Snapshot #${captureId}: cần nhập đủ advertiser và domain trước khi chấp nhận.`;
      return;
    }
  } else {
    const reason = window.prompt(
      "Nhập lý do loại snapshot. Raw evidence vẫn được giữ, nhưng quyết định này không thể đổi lại:",
      "",
    );
    if (reason === null) return;
    payload.reason = reason.trim();
    if (!payload.reason) {
      message.textContent = `Snapshot #${captureId}: phải nhập lý do cụ thể để loại.`;
      return;
    }
  }
  const controls = Array.from(row.querySelectorAll("button, input"));
  controls.forEach((control) => { control.disabled = true; });
  row.classList.add("review-row-saving");
  row.setAttribute("aria-busy", "true");
  summary.textContent = "Đang lưu quyết định…";
  message.textContent = `Snapshot #${captureId}: đang ${action === "ACCEPT" ? "chấp nhận" : "loại"}…`;
  try {
    await request(`/ad-intelligence/captures/${captureId}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await refreshAll();
    message.textContent = action === "ACCEPT"
      ? `Đã chấp nhận snapshot #${captureId} và cập nhật graph.`
      : `Đã loại snapshot #${captureId}; raw evidence và lý do vẫn được giữ để kiểm toán.`;
  } catch (error) {
    summary.textContent = "Chưa lưu được quyết định";
    message.textContent = `Snapshot #${captureId}: lỗi ${error.message}`;
    controls.forEach((control) => { control.disabled = false; });
    row.classList.remove("review-row-saving");
    row.removeAttribute("aria-busy");
  }
}

async function refreshAll() {
  try {
    await Promise.all([
      loadHealth(), loadSummary(), loadRadar(), loadGraph(), loadCaptures(),
      loadCaptureReviewQueue(),
      loadPrograms(), loadPortfolio(), loadStepTwoProjects(), loadExposure(), loadFinance(), loadBackups(), loadOperations(),
      loadRuntimeStatus(), loadAutomationQueue(), loadResources(),
    ]);
  } catch (error) {
    setApiStatus(false, `Lỗi dữ liệu: ${error.message}`);
  }
}

function formObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function submitCapture(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formObject(form);
  Object.keys(payload).forEach((key) => {
    if (payload[key] === "") delete payload[key];
  });
  if (payload.country) payload.country = payload.country.toUpperCase();
  const message = document.getElementById("captureMessage");
  const hasStructuredIdentity = Boolean(payload.advertiser_name && payload.project_domain);
  message.textContent = hasStructuredIdentity ? "Đang lưu vào graph…" : "Đang lưu vào hàng đợi duyệt…";
  try {
    const result = await request("/ad-intelligence/captures", { method: "POST", body: JSON.stringify(payload) });
    message.textContent = result.status === "NEEDS_REVIEW"
      ? `Đã lưu snapshot #${result.id} để duyệt sau; chưa tạo graph.`
      : `Đã lưu snapshot #${result.id} và cập nhật graph.`;
    form.reset();
    updateCaptureSubmitMode(form, false);
    await refreshAll();
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
  }
}

function parseAdvertiserSnapshotLines(value) {
  const output = [];
  const errors = [];
  value.split(/\r?\n/).forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (!line) return;
    const parts = line.split("|").map((part) => part.trim());
    if (parts.length < 2 || parts.length > 3 || !parts[1]) {
      errors.push(`Dòng ${index + 1}: cần ID | Tên | Số quảng cáo`);
      return;
    }
    const adCount = parts[2] === "" || parts[2] == null ? null : Number(parts[2]);
    if (adCount != null && (!Number.isInteger(adCount) || adCount < 0)) {
      errors.push(`Dòng ${index + 1}: số quảng cáo phải là số nguyên không âm`);
      return;
    }
    output.push({
      external_key: parts[0] || null,
      advertiser_name: parts[1],
      reported_ad_count: adCount,
    });
  });
  if (!output.length) errors.push("Cần ít nhất một advertiser hợp lệ.");
  if (errors.length) throw new Error(errors.join("; "));
  return output;
}

async function submitAdvertiserSnapshot(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.getElementById("advertiserSnapshotMessage");
  let advertisers;
  try {
    advertisers = parseAdvertiserSnapshotLines(form.elements.advertisers.value);
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
    return;
  }
  const payload = {
    project_domain: form.elements.target_domain.value.trim(),
    source_name: form.elements.source_name.value.trim(),
    source_url: form.elements.source_url.value.trim(),
    checked_at: new Date(form.elements.checked_at.value).toISOString(),
    evidence_excerpt: form.elements.evidence_excerpt.value.trim(),
    geography: form.elements.geography.value.trim() || null,
    result_set_complete: form.elements.result_set_complete.checked,
    confidence: form.elements.result_set_complete.checked ? 0.85 : 0.65,
    advertisers,
    actor: "local-user",
  };
  message.textContent = `Đang nhập ${advertisers.length} advertiser có nguồn…`;
  try {
    const result = await request("/ad-intelligence/advertiser-snapshots", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    message.textContent = result.duplicate
      ? `Snapshot #${result.capture_id} đã tồn tại; không tạo dữ liệu trùng.`
      : `Đã nhập ${result.advertisers_in_snapshot} advertiser, ${result.reported_ads} quảng cáo được nguồn báo cáo; không có Google Ads write.`;
    await refreshAll();
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
  }
}

function updateCaptureSubmitMode(form = document.getElementById("captureForm"), updateMessage = true) {
  const advertiser = form.elements.advertiser_name.value.trim();
  const domain = form.elements.project_domain.value.trim();
  const button = document.getElementById("captureSubmit");
  const complete = Boolean(advertiser && domain);
  button.textContent = complete ? "Lưu và cập nhật graph" : "Lưu để duyệt sau";
  if (updateMessage) {
    document.getElementById("captureMessage").textContent = complete
      ? "Đủ advertiser + domain: snapshot sẽ cập nhật graph ngay."
      : "Chưa đủ advertiser + domain: chưa tạo graph.";
  }
}

const permissions = ["NOT_CHECKED", "AMBIGUOUS", "CONFLICT", "APPROVAL_REQUIRED", "PROHIBITED", "NON_BRAND_ONLY", "BRAND_ALLOWED"];
function permissionOptions() {
  return permissions.map((value) => `<option value="${value}">${value}</option>`).join("");
}
function setLocalDateTime(input, date = new Date()) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  input.value = local.toISOString().slice(0, 16);
}
function populatePermissionSelects() {
  document.querySelectorAll("select[data-permission]").forEach((select) => {
    select.innerHTML = permissionOptions();
  });

  const evidence = document.getElementById("evidenceForm");
  evidence.elements.decision.value = "NOT_CHECKED";
  evidence.elements.confidence.value = "0";
  evidence.elements.source_authority.value = "UNKNOWN";
  setLocalDateTime(evidence.elements.checked_at);
}

async function submitCompliance(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = {
    program_id: Number(form.elements.program_id.value),
    wants_brand_keywords: form.elements.wants_brand_keywords.checked,
    wants_direct_link: form.elements.wants_direct_link.checked,
  };
  const panel = document.getElementById("complianceResult");
  try {
    const result = await request("/compliance/evaluate", { method: "POST", body: JSON.stringify(payload) });
    panel.innerHTML = result.allowed
      ? `<div class="result-icon good">✓</div><h2>${esc(result.status)}</h2><p>Evidence hiện tại đủ rõ. Dự án vẫn cần quyết định vận hành riêng.</p>`
      : `<div class="result-icon warn">!</div><h2>${esc(result.status)}</h2><p>Dự án vẫn được giữ lại; đây là cảnh báo terms, không phải bộ lọc loại trừ.</p><div class="reason-list warning-reasons">${result.reasons.map((r) => `<div>${esc(r)}</div>`).join("")}</div>`;
  } catch (error) {
    panel.innerHTML = `<div class="result-icon bad">×</div><h2>Không thể đánh giá</h2><p>${esc(error.message)}</p>`;
  }
}

function numOrUndefined(value) {
  return value === "" || value == null ? undefined : Number(value);
}

async function submitEconomics(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const raw = formObject(form);
  const payload = {
    price: Number(raw.price),
    commission_type: raw.commission_type,
    commission_rate: numOrUndefined(raw.commission_rate),
    commission_flat: numOrUndefined(raw.commission_flat),
    recurring_months: numOrUndefined(raw.recurring_months),
    forecast_horizon_months: Number(raw.forecast_horizon_months),
    clicks_per_sale: raw.conversion_basis === "CLICKS_PER_SALE" ? Number(raw.clicks_per_sale) : undefined,
    outbound_click_rate: raw.conversion_basis === "FUNNEL_RATES" ? Number(raw.outbound_click_rate) : undefined,
    merchant_conversion_rate: raw.conversion_basis === "FUNNEL_RATES" ? Number(raw.merchant_conversion_rate) : undefined,
    approval_rate: Number(raw.approval_rate),
    refund_rate: Number(raw.refund_rate),
    monthly_churn_rate: Number(raw.monthly_churn_rate),
    target_margin: Number(raw.target_margin),
    confidence_discount: Number(raw.confidence_discount),
  };
  Object.keys(payload).forEach((key) => payload[key] === undefined && delete payload[key]);
  const result = await request("/economics/evaluate", { method: "POST", body: JSON.stringify(payload) });
  document.getElementById("resultCommission").textContent = `$${Number(result.commission_per_period).toFixed(2)}`;
  document.getElementById("resultLtv").textContent = `$${Number(result.expected_commission_ltv).toFixed(2)}`;
  document.getElementById("resultCvr").textContent = `${(Number(result.sale_probability_per_ad_click) * 100).toFixed(3)}%`;
  document.getElementById("resultClicks").textContent = result.effective_clicks_per_sale == null
    ? "—"
    : Number(result.effective_clicks_per_sale).toFixed(1);
  document.getElementById("resultBreakEven").textContent = `$${Number(result.break_even_cpc).toFixed(3)}`;
  document.getElementById("resultSafe").textContent = `$${Number(result.safe_cpc).toFixed(3)}`;
}

function syncEconomicsConversionMode() {
  const form = document.getElementById("economicsForm");
  const useClicks = form.elements.conversion_basis.value === "CLICKS_PER_SALE";
  form.elements.clicks_per_sale.disabled = !useClicks;
  document.querySelectorAll("[data-funnel-field]").forEach((label) => {
    label.classList.toggle("muted-field", useClicks);
    label.querySelector("input").disabled = useClicks;
  });
}



let programCache = [];
let importPreviewReady = false;
let campaignImportPreviewReady = false;

function gateBadge(status) {
  const cls = status === "TERMS_OK" || status.includes("READY")
    ? "gate-ready"
    : ((status.includes("PROHIBITED") || status.includes("CONFLICT")) ? "gate-blocked" : "gate-pending");
  return `<span class="gate ${cls}">${esc(status)}</span>`;
}

function stateBadge(status) {
  const cls = status === "ACCEPTED" || status === "RESOLVED" ? "gate-ready" : (status === "CONFLICT" || status === "REJECTED" ? "gate-blocked" : "gate-pending");
  return `<span class="gate ${cls}">${esc(status)}</span>`;
}

async function loadPrograms() {
  const items = await request("/programs");
  programCache = items;
  const rows = document.getElementById("programRows");
  if (!items.length) {
    rows.innerHTML = '<tr><td colspan="8" class="empty">Chưa có chương trình.</td></tr>';
  } else {
    rows.innerHTML = items.map((item) => {
      let researchSummary = '<span class="warning-text">Chưa rà tự động</span>';
      if (item.last_research_attempted_at) {
        const freshness = item.research_is_fresh ? "còn mới" : "đến hạn rà lại";
        const evidenceSummary = item.permission_evidence_found
          ? `${item.evidence_count} evidence · ${item.evidence_proposal_count} proposal${item.evidence_is_stale ? ' · <span class="warning-text">evidence cũ</span>' : ""}`
          : '<span class="warning-text">Không thấy quyền PPC công khai</span>';
        researchSummary = `${evidenceSummary}<br><span class="small">Đã rà ${esc(formatRuntimeTime(item.last_research_attempted_at))} · ${esc(item.research_status || "UNKNOWN")} · ${esc(freshness)}</span>`;
      }
      const signupSource = item.signup_url
        ? `${safeExternalLink(item.signup_url, "Mở link đăng ký")}<br><span class="small">${esc(sourceAuthorityLabel(item.signup_source_authority))}</span>`
        : '<span class="warning-text">Chưa có link đăng ký</span>';
      return `
      <tr class="clickable-row" data-program-id="${item.id}">
        <td><strong>${esc(item.merchant_name)}</strong><br><span class="small">${esc(item.website_domain)} · ${esc(item.program_name)}</span><br>${signupSource}</td>
        <td>${esc(item.network_name || "—")}</td>
        <td>${esc(item.paid_search_permission)}</td>
        <td>${esc(item.brand_keyword_permission)}</td>
        <td>${esc(item.non_brand_permission)}</td>
        <td>${stateBadge(item.commission_state)}<br><span class="small">${item.commission_fact_count} facts</span></td>
        <td>${researchSummary}</td>
        <td>${gateBadge(item.gate_status)}</td>
      </tr>`;
    }).join("");
  }
  const optionHtml = items.map((item) => `<option value="${item.id}">${esc(item.website_domain)} · ${esc(item.program_name)}</option>`).join("");
  const evidenceSelect = document.getElementById("evidenceProgram");
  const financeSelect = document.getElementById("financeProgram");
  const complianceSelect = document.getElementById("complianceProgram");
  const exposureSelect = document.getElementById("exposureProgram");
  const oldEvidence = evidenceSelect.value;
  const oldFinance = financeSelect.value;
  const oldCompliance = complianceSelect.value;
  const oldExposure = exposureSelect.value;
  evidenceSelect.innerHTML = `<option value="">Chọn chương trình</option>${optionHtml}`;
  financeSelect.innerHTML = `<option value="">Chưa xác định</option>${optionHtml}`;
  complianceSelect.innerHTML = `<option value="">Chọn chương trình đã lưu</option>${optionHtml}`;
  exposureSelect.innerHTML = `<option value="">Chưa xác định</option>${optionHtml}`;
  if (items.some((item) => String(item.id) === oldEvidence)) evidenceSelect.value = oldEvidence;
  if (items.some((item) => String(item.id) === oldFinance)) financeSelect.value = oldFinance;
  if (items.some((item) => String(item.id) === oldCompliance)) complianceSelect.value = oldCompliance;
  if (items.some((item) => String(item.id) === oldExposure)) exposureSelect.value = oldExposure;
  document.getElementById("exportEvidencePack").disabled = !evidenceSelect.value;
}

function setEvidenceProgramSelection(programId) {
  const select = document.getElementById("evidenceProgram");
  select.value = programId || "";
  document.getElementById("exportEvidencePack").disabled = !select.value;
  return select.value;
}

function exportEvidencePack(programId = "") {
  programId = programId || document.getElementById("evidenceProgram").value;
  if (!programId) return;
  const link = document.createElement("a");
  link.href = `${API}/programs/${programId}/evidence-pack`;
  link.download = "";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

async function submitProgram(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formObject(form);
  Object.keys(payload).forEach((key) => payload[key] === "" && delete payload[key]);
  if (payload.merchant_country) payload.merchant_country = payload.merchant_country.toUpperCase();
  const message = document.getElementById("programMessage");
  message.textContent = "Đang lưu…";
  try {
    const result = await request("/programs", {method: "POST", body: JSON.stringify(payload)});
    message.textContent = `Đã lưu ${result.website_domain}`;
    form.reset();
    await loadPrograms();
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
  }
}

async function loadEvidence(programId) {
  const body = document.getElementById("evidenceRows");
  if (!programId) {
    body.innerHTML = '<tr><td colspan="7" class="empty">Chọn một chương trình.</td></tr>';
    return;
  }
  const items = await request(`/programs/${programId}/evidence`);
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty">Chưa có proposal. Chương trình vẫn ở trạng thái cảnh báo.</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => {
    const eligible = item.review_status === "PROPOSED"
      && item.confidence >= 0.8
      && ["OFFICIAL", "PARTNER_PORTAL", "WRITTEN_CONFIRMATION"].includes(item.source_authority)
      && !["NOT_CHECKED", "AMBIGUOUS", "CONFLICT"].includes(item.decision);
    const review = item.review_status === "PROPOSED"
      ? `<button class="button evidence-review" data-evidence-id="${item.id}" data-action="ACCEPT" ${eligible ? "" : "disabled"}>Xác nhận</button>
         <button class="button evidence-review" data-evidence-id="${item.id}" data-action="REJECT">Loại</button>`
      : "—";
    return `
    <tr>
      <td>${new Date(item.checked_at).toLocaleDateString("vi-VN")}</td>
      <td>${esc(item.scope)}</td>
      <td>${esc(item.decision)}</td>
      <td>${esc(item.source_authority)}<br><span class="small">${Math.round(item.confidence * 100)}%</span></td>
      <td>${stateBadge(item.review_status)}</td>
      <td>${safeExternalLink(item.source_url, "Mở nguồn")}<br><span class="evidence-excerpt">${esc(item.excerpt)}</span></td>
      <td><div class="review-actions">${review}</div></td>
    </tr>`;
  }).join("");
}

async function loadResearchAttempts(programId) {
  const body = document.getElementById("researchAttemptRows");
  if (!programId) {
    body.innerHTML = '<tr><td colspan="5" class="empty">Chọn một chương trình.</td></tr>';
    return;
  }
  const items = await request(`/programs/${programId}/research-attempts`);
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="5" class="empty">Chưa có lần rà tự động.</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => {
    const allSources = [...new Set([...(item.source_urls || []), ...(item.priority_source_urls || [])])];
    const sources = allSources.length
      ? allSources.map((url) => researchSourceLink(url, item.source_authorities || {})).join("<br>")
      : '<span class="warning-text">Chưa tìm được URL nguồn</span>';
    const detail = item.collection_errors.length
      ? item.collection_errors.map((error) => `<div class="warning-text">${esc(error)}</div>`).join("")
      : `<span>${esc(item.summary || "Đã hoàn tất rà nguồn.")}</span>`;
    const evidenceUnchanged = Math.max(0, Number(item.duplicate_terms_evidence || 0) - Number(item.refreshed_terms_evidence || 0));
    const factsUnchanged = Math.max(0, Number(item.duplicate_commission_facts || 0) - Number(item.refreshed_commission_facts || 0));
    const sourceChanges = item.source_changes || [];
    const sourceChangeSummary = sourceChanges.length
      ? `<div class="warning-text">Nguồn thay đổi: ${sourceChanges.map((change) => `${esc(sourceChangeLabel(change.change_type))} · ${safeExternalHostLink(change.url)}`).join("<br>")}</div>`
      : `<div class="small">Dấu nguồn: ${esc(item.source_change_status || "UNAVAILABLE")}</div>`;
    const result = `${detail}${sourceChangeSummary}<div class="small">Evidence: mới ${item.imported_terms_evidence} · làm mới ${item.refreshed_terms_evidence} · không đổi ${evidenceUnchanged}<br>Commission: mới ${item.imported_commission_facts} · làm mới ${item.refreshed_commission_facts} · không đổi ${factsUnchanged}</div>`;
    const duplicate = item.duplicate_run ? '<br><span class="small">Kết quả trùng · heartbeat mới</span>' : "";
    const safety = item.permissions_changed
      ? '<span class="gate gate-blocked">CÓ THAY ĐỔI</span>'
      : '<span class="gate gate-ready">PPC KHÔNG ĐỔI</span>';
    return `<tr>
      <td>${new Date(item.attempted_at).toLocaleString("vi-VN")}<br><span class="small">${esc(item.actor)}</span></td>
      <td>${stateBadge(item.status)}${duplicate}</td>
      <td>${sources}</td>
      <td>${result}</td>
      <td>${safety}</td>
    </tr>`;
  }).join("");
}

async function loadCommissionFacts(programId) {
  const body = document.getElementById("commissionFactRows");
  if (!programId) {
    body.innerHTML = '<tr><td colspan="7" class="empty">Chọn một chương trình.</td></tr>';
    return;
  }
  const items = await request(`/programs/${programId}/commission-facts`);
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty">Chưa có commission fact.</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => {
    const rate = item.commission_rate == null ? "—" : `${item.rate_is_maximum ? "up to " : ""}${(Number(item.commission_rate) * 100).toFixed(0)}%`;
    const eligible = item.review_status === "PROPOSED"
      && item.confidence >= 0.8
      && ["OFFICIAL", "PARTNER_PORTAL", "WRITTEN_CONFIRMATION"].includes(item.source_authority);
    const review = item.review_status === "PROPOSED"
      ? `<button class="button commission-fact-review" data-fact-id="${item.id}" data-action="ACCEPT" ${eligible ? "" : "disabled"}>Xác nhận</button>
         <button class="button commission-fact-review" data-fact-id="${item.id}" data-action="REJECT">Loại</button>`
      : "—";
    return `<tr>
      <td>${new Date(item.checked_at).toLocaleDateString("vi-VN")}</td>
      <td>${esc(item.commission_type)}</td>
      <td>${esc(rate)}</td>
      <td>${esc(item.applies_to)}</td>
      <td>${stateBadge(item.review_status)}</td>
      <td>${safeExternalLink(item.source_url, "Mở nguồn")}<br><span class="evidence-excerpt">${esc(item.excerpt)}</span></td>
      <td><div class="review-actions">${review}</div></td>
    </tr>`;
  }).join("");
}

async function reviewCommissionFact(factId, action) {
  const programId = document.getElementById("evidenceProgram").value;
  if (!programId) return;
  if (action === "ACCEPT" && !window.confirm("Chỉ xác nhận khi rate, cadence và nguồn đều đúng. Thao tác này không thay đổi PPC. Tiếp tục?")) return;
  const message = document.getElementById("commissionFactMessage");
  message.textContent = action === "ACCEPT" ? "Đang xác nhận…" : "Đang loại proposal…";
  try {
    const result = await request(`/programs/${programId}/commission-facts/${factId}/review`, {
      method: "POST",
      body: JSON.stringify({action, reviewed_by: "Tran"}),
    });
    message.textContent = `${result.fact.review_status} · Commission ${result.commission_state} · PPC không đổi`;
    await Promise.all([loadPrograms(), loadCommissionFacts(programId), loadOperations()]);
    setEvidenceProgramSelection(programId);
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
  }
}

async function submitEvidence(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const programId = form.elements.program_id.value;
  const payload = formObject(form);
  delete payload.program_id;
  payload.confidence = Number(payload.confidence);
  payload.checked_at = new Date(payload.checked_at).toISOString();
  if (payload.expires_at) payload.expires_at = new Date(payload.expires_at).toISOString();
  else delete payload.expires_at;
  const message = document.getElementById("evidenceMessage");
  message.textContent = "Đang lưu…";
  try {
    const result = await request(`/programs/${programId}/evidence`, {method: "POST", body: JSON.stringify(payload)});
    message.textContent = result.updated
      ? `Đã cập nhật metadata proposal · ${result.program_gate_status}`
      : (result.duplicate ? "Proposal này đã tồn tại, không tạo trùng." : `Đã lưu proposal · ${result.program_gate_status}`);
    form.elements.source_url.value = "";
    form.elements.excerpt.value = "";
    form.elements.decision.value = "NOT_CHECKED";
    form.elements.confidence.value = "0";
    form.elements.source_authority.value = "UNKNOWN";
    await Promise.all([loadPrograms(), loadEvidence(programId), loadSummary(), loadOperations()]);
    setEvidenceProgramSelection(programId);
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
  }
}

async function reviewEvidence(evidenceId, action) {
  const programId = document.getElementById("evidenceProgram").value;
  if (!programId) return;
  if (action === "ACCEPT" && !window.confirm("Chỉ xác nhận khi nguồn và đoạn trích thực sự chứng minh permission này. Tiếp tục?")) return;
  const message = document.getElementById("evidenceMessage");
  message.textContent = action === "ACCEPT" ? "Đang xác nhận…" : "Đang loại proposal…";
  try {
    const result = await request(`/programs/${programId}/evidence/${evidenceId}/review`, {
      method: "POST",
      body: JSON.stringify({action, reviewed_by: "Tran"}),
    });
    message.textContent = `${result.evidence.review_status} · ${result.resolved_permission} · ${result.program_gate_status}`;
    await Promise.all([loadPrograms(), loadEvidence(programId), loadSummary(), loadOperations()]);
    setEvidenceProgramSelection(programId);
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
  }
}

async function submitResearch(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const domain = form.elements.domain.value.trim();
  const message = document.getElementById("researchMessage");
  const panel = document.getElementById("researchResult");
  message.textContent = "Đang thu thập…";
  try {
    const result = await request("/programs/research", {
      method: "POST",
      body: JSON.stringify({domain}),
    });
    const sources = result.source_urls.length
      ? result.source_urls.map((url) => researchSourceLink(url, result.source_authorities || {})).join(" · ")
      : "Chưa có nguồn tự động";
    const permissions = result.permission_proposals.length
      ? result.permission_proposals.map((item) => `<div><strong>${esc(item.scope)}</strong><span>${esc(item.decision)} · ${Math.round(item.confidence * 100)}% · ${esc(sourceAuthorityLabel(item.source_authority))}</span></div>`).join("")
      : '<div><strong>Permissions</strong><span>NOT_CHECKED · cần nhập nguồn chính thức</span></div>';
    const errors = result.collection_errors.length
      ? `<div class="import-errors">${result.collection_errors.map((error) => `<div>${esc(error)}</div>`).join("")}</div>`
      : "";
    const unchangedEvidence = Math.max(0, Number(result.duplicate_terms_evidence || 0) - Number(result.refreshed_terms_evidence || 0));
    const unchangedFacts = Math.max(0, Number(result.duplicate_commission_facts || 0) - Number(result.refreshed_commission_facts || 0));
    const sourceChanges = result.source_changes || [];
    const sourceChangeSummary = sourceChanges.length
      ? `<div class="warning-text"><strong>Nguồn thay đổi:</strong> ${sourceChanges.map((change) => `${esc(sourceChangeLabel(change.change_type))} · ${esc(safeExternalHostname(change.url) || change.url)}`).join("; ")}</div>`
      : `<div class="small">Dấu nguồn: ${esc(result.source_change_status || "UNAVAILABLE")}</div>`;
    panel.className = "research-result";
    panel.innerHTML = `
      <div class="research-head"><div>${stateBadge(result.status)}</div><strong>${esc(result.domain)}</strong><span>${gateBadge(result.gate_status)}</span></div>
      <p>${esc(result.summary)}</p>
      <div class="proposal-grid">${permissions}</div>
      <div class="research-foot"><strong>Terms evidence:</strong> ${result.terms_evidence.length} proposal · mới ${result.imported_terms_evidence} · làm mới ${result.refreshed_terms_evidence} · không đổi ${unchangedEvidence}<br><strong>Commission:</strong> ${stateBadge(result.commission_state)} · ${result.commission_facts.length} facts · mới ${result.imported_commission_facts} · làm mới ${result.refreshed_commission_facts} · không đổi ${unchangedFacts}<br><strong>Nguồn:</strong> ${sources}</div>${sourceChangeSummary}${errors}
      <div class="notice warning">Permission không thay đổi. Mọi evidence vẫn ở PROPOSED; commission facts được lưu riêng.</div>`;
    message.textContent = result.duplicate_run ? "Đã kiểm tra trước đó; không tạo dữ liệu trùng." : "Đã lưu proposal có nguồn.";
    await Promise.all([loadPrograms(), loadOperations()]);
    if (result.program_id) {
      const programId = String(result.program_id);
      setEvidenceProgramSelection(programId);
      await Promise.all([loadEvidence(programId), loadCommissionFacts(programId), loadResearchAttempts(programId)]);
    }
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
    panel.className = "research-result empty";
    panel.textContent = "Không thể thu thập proposal.";
  }
}

function buildCampaignImportFormData() {
  const form = document.getElementById("campaignImportForm");
  const file = form.elements.file.files[0];
  if (!file) throw new Error("Hãy chọn file Google Ads CSV trước.");
  const data = new FormData();
  data.append("file", file);
  data.append("source", form.elements.source.value || "GOOGLE_ADS_CSV");
  data.append("account_external_id", form.elements.account_external_id.value || "CSV-IMPORT");
  data.append("account_name", form.elements.account_name.value || "Google Ads CSV");
  if (form.elements.default_program_id.value) {
    data.append("default_program_id", form.elements.default_program_id.value);
  }
  return data;
}

function renderCampaignImportPreview(result) {
  const errors = result.errors?.length
    ? `<div class="import-errors">${result.errors.map((e) => `<div>Dòng ${e.row}: ${esc(e.message)}</div>`).join("")}</div>`
    : "";
  const currencies = Object.entries(result.totals_by_currency || {})
    .map(([currency, value]) => `${esc(currency)} ${esc(value)}`)
    .join(" · ") || "—";
  const panel = document.getElementById("campaignImportPreview");
  panel.className = "";
  panel.innerHTML = `
    <div class="preview-grid">
      <div><span>Đọc</span><strong>${result.rows_read}</strong></div>
      <div><span>Hợp lệ</span><strong>${result.valid_rows}</strong></div>
      <div><span>Mới</span><strong>${result.new_rows}</strong></div>
      <div><span>Cập nhật</span><strong>${result.update_rows}</strong></div>
      <div><span>Không đổi</span><strong>${result.duplicates_existing}</strong></div>
      <div><span>Đã map</span><strong>${result.mapped_rows}</strong></div>
      <div><span>Chưa map</span><strong>${result.unmapped_rows}</strong></div>
      <div><span>Tự map theo domain</span><strong>${result.auto_mapped_rows || 0}</strong></div>
      <div><span>Lỗi</span><strong>${result.error_count}</strong></div>
    </div>
    <p class="preview-line"><strong>Spend:</strong> ${currencies}</p>
    <p class="preview-line"><strong>Traffic:</strong> ${result.total_impressions.toLocaleString("en-US")} impressions · ${result.total_clicks.toLocaleString("en-US")} clicks · ${esc(result.total_conversions)} conversions</p>${errors}`;
}

async function previewCampaignImport() {
  const message = document.getElementById("campaignImportMessage");
  try {
    message.textContent = "Đang đọc file…";
    const result = await request("/exposure/google-ads-import/preview", {
      method: "POST",
      body: buildCampaignImportFormData(),
    });
    renderCampaignImportPreview(result);
    campaignImportPreviewReady = result.valid_rows > 0;
    document.getElementById("commitCampaignImport").disabled = !campaignImportPreviewReady;
    message.textContent = result.valid_rows
      ? "Preview xong. Chưa ghi dữ liệu."
      : "Không có dòng hợp lệ để nhập.";
  } catch (error) {
    campaignImportPreviewReady = false;
    document.getElementById("commitCampaignImport").disabled = true;
    message.textContent = `Lỗi: ${error.message}`;
  }
}

async function commitCampaignImport() {
  const message = document.getElementById("campaignImportMessage");
  if (!campaignImportPreviewReady) {
    message.textContent = "Phải xem trước thành công trước.";
    return;
  }
  try {
    message.textContent = "Đang nhập…";
    const result = await request("/exposure/google-ads-import/commit", {
      method: "POST",
      body: buildCampaignImportFormData(),
    });
    renderCampaignImportPreview(result);
    message.textContent = `Đã ghi/cập nhật ${result.rows_written} dòng campaign theo ngày.`;
    campaignImportPreviewReady = false;
    document.getElementById("commitCampaignImport").disabled = true;
    await Promise.all([loadExposure(), loadSummary()]);
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
  }
}

function exposureProgramOptions(selectedId) {
  const options = programCache.map((item) => {
    const selected = String(item.id) === String(selectedId) ? " selected" : "";
    return `<option value="${item.id}"${selected}>${esc(item.website_domain)}</option>`;
  }).join("");
  return `<option value="">Chưa xác định</option>${options}`;
}

async function loadExposure() {
  const [summary, programs] = await Promise.all([
    request("/exposure/summary"),
    request("/programs"),
  ]);
  programCache = programs;
  const accountIds = [...new Set(
    summary.campaigns.map((item) => item.account_external_id).filter(Boolean),
  )];
  const accountNames = [...new Set(
    summary.campaigns.map((item) => item.account_name).filter(Boolean),
  )];
  const campaignImportForm = document.getElementById("campaignImportForm");
  if (accountIds.length === 1 && ["", "CSV-IMPORT"].includes(campaignImportForm.elements.account_external_id.value)) {
    campaignImportForm.elements.account_external_id.value = accountIds[0];
  }
  if (accountNames.length === 1 && ["", "Google Ads CSV"].includes(campaignImportForm.elements.account_name.value)) {
    campaignImportForm.elements.account_name.value = accountNames[0];
  }
  const currencies = summary.currencies.map((item) => item.currency).join(", ") || "Chưa có tiền tệ";
  const first = summary.currencies[0];
  document.getElementById("exposureCards").innerHTML = first ? [
    metric("Campaigns", summary.campaign_count, `${summary.active_campaign_count} active`),
    metric("Terms warnings", summary.warning_campaign_count, `${summary.acknowledged_warning_count} đã xác nhận đã biết`),
    metric("Spend at risk", money(first.spend_at_risk, first.currency), `Tổng spend: ${money(first.total_spend, first.currency)}`),
    metric("Actual net cash", money(first.actual_net_cash, first.currency), `Tiền tệ: ${currencies}`),
  ].join("") : [
    metric("Campaigns", summary.campaign_count, "Chưa nhập Google Ads CSV"),
    metric("Terms warnings", summary.warning_campaign_count, "Chỉ cảnh báo; không loại dự án"),
    metric("Spend at risk", "—", "Chưa có spend"),
    metric("Actual net cash", "—", "Cash received trừ spend"),
  ].join("");

  const body = document.getElementById("exposureRows");
  if (!summary.campaigns.length) {
    body.innerHTML = '<tr><td colspan="8" class="empty">Chưa có campaign. Hãy nhập file Google Ads CSV.</td></tr>';
    return;
  }
  body.innerHTML = summary.campaigns.map((item) => {
    const acknowledgement = item.risk_acknowledged
      ? `<span class="gate gate-ready">ĐÃ BIẾT</span><br><span class="small">${esc(item.risk_acknowledged_by || "operator")}</span>`
      : `<button class="button acknowledge-risk" data-campaign-id="${item.campaign_id}">Tôi đã biết</button>`;
    return `<tr>
      <td><strong>${esc(item.campaign_name)}</strong><br><span class="small">${esc(item.account_name)} · ${esc(item.campaign_external_id)}</span></td>
      <td><select class="compact-select campaign-program-map" data-campaign-id="${item.campaign_id}">${exposureProgramOptions(item.program_id)}</select></td>
      <td>${esc(item.campaign_status)}<br><span class="small">${esc(item.channel_type)}</span></td>
      <td>${gateBadge(item.terms_warning_status)}<br><span class="risk-level risk-${item.warning_level.toLowerCase()}">${esc(item.warning_level)} · vẫn theo dõi</span></td>
      <td>${money(item.spend, item.currency)}</td>
      <td>${item.clicks.toLocaleString("en-US")} clicks<br><span class="small">${item.impressions.toLocaleString("en-US")} impressions</span></td>
      <td>${item.average_cpc == null ? "—" : money(item.average_cpc, item.currency)}</td>
      <td>${acknowledgement}</td>
    </tr>`;
  }).join("");
}

async function acknowledgeCampaignRisk(campaignId) {
  const note = window.prompt("Ghi chú tùy chọn (việc xác nhận không thay đổi permission):", "Đã hiểu terms risk");
  if (note === null) return;
  await request(`/exposure/campaigns/${campaignId}/acknowledge`, {
    method: "POST",
    body: JSON.stringify({actor: "Tran", note}),
  });
  await Promise.all([loadExposure(), loadOperations()]);
}

async function mapCampaignProgram(campaignId, programId) {
  await request(`/exposure/campaigns/${campaignId}/program`, {
    method: "POST",
    body: JSON.stringify({program_id: programId ? Number(programId) : null}),
  });
  await loadExposure();
}

function buildImportFormData() {
  const form = document.getElementById("commissionImportForm");
  const file = form.elements.file.files[0];
  if (!file) throw new Error("Hãy chọn file CSV trước.");
  const data = new FormData();
  data.append("file", file);
  data.append("source", form.elements.source.value || "CSV");
  if (form.elements.program_id.value) data.append("program_id", form.elements.program_id.value);
  return data;
}

function renderImportPreview(result) {
  const errors = result.errors?.length
    ? `<div class="import-errors">${result.errors.map((e) => `<div>Dòng ${e.row}: ${esc(e.message)}</div>`).join("")}</div>`
    : "";
  const states = Object.entries(result.totals_by_state || {}).map(([k,v]) => `${esc(k)}: ${esc(v)}`).join(" · ") || "—";
  const currencies = Object.entries(result.totals_by_currency || {}).map(([k,v]) => `${esc(k)} ${esc(v)}`).join(" · ") || "—";
  document.getElementById("importPreview").className = "";
  document.getElementById("importPreview").innerHTML = `
    <div class="preview-grid">
      <div><span>Đọc</span><strong>${result.rows_read}</strong></div>
      <div><span>Sẽ ghi/cập nhật</span><strong>${result.valid_rows}</strong></div>
      <div><span>Cập nhật trạng thái</span><strong>${result.updates_existing}</strong></div>
      <div><span>Đã tồn tại</span><strong>${result.duplicates_existing}</strong></div>
      <div><span>Trùng trong file</span><strong>${result.duplicates_in_file}</strong></div>
      <div><span>CONFLICT</span><strong>${result.conflict_count || 0}</strong></div>
      <div><span>Lỗi</span><strong>${result.error_count}</strong></div>
      <div><span>Match click</span><strong>${result.attributable_rows}</strong></div>
      <div><span>UNATTRIBUTED</span><strong>${result.unattributed_rows}</strong></div>
    </div>
    <p class="preview-line"><strong>State:</strong> ${states}</p>
    <p class="preview-line"><strong>Currency:</strong> ${currencies}</p>${errors}`;
}

async function previewCommissionImport() {
  const message = document.getElementById("importMessage");
  try {
    message.textContent = "Đang đọc file…";
    const result = await request("/finance/commission-import/preview", {method: "POST", body: buildImportFormData()});
    renderImportPreview(result);
    importPreviewReady = result.valid_rows > 0 || result.duplicates_in_file > 0 || result.conflict_count > 0;
    document.getElementById("commitImport").disabled = !importPreviewReady;
    message.textContent = importPreviewReady ? "Preview xong. Chưa ghi dữ liệu." : "Không có dòng mới hoặc ngoại lệ cần ghi.";
  } catch (error) {
    importPreviewReady = false;
    document.getElementById("commitImport").disabled = true;
    message.textContent = `Lỗi: ${error.message}`;
  }
}

async function commitCommissionImport() {
  const message = document.getElementById("importMessage");
  if (!importPreviewReady) {
    message.textContent = "Phải Preview thành công trước.";
    return;
  }
  try {
    message.textContent = "Đang nhập…";
    const result = await request("/finance/commission-import/commit", {method: "POST", body: buildImportFormData()});
    renderImportPreview(result);
    message.textContent = `Đã ghi/cập nhật ${result.rows_written} giao dịch; ngoại lệ đã chuyển vào hàng đợi.`;
    importPreviewReady = false;
    document.getElementById("commitImport").disabled = true;
    await Promise.all([loadFinance(), loadSummary(), loadOperations()]);
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
  }
}

function money(value, currency) {
  const n = Number(value || 0);
  return `${currency} ${n.toLocaleString("en-US", {maximumFractionDigits: 2})}`;
}

function localDateTimeValue(value = new Date()) {
  const offset = value.getTimezoneOffset() * 60000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}

function reconciliationBadge(status) {
  const cls = status === "ATTRIBUTED"
    ? "gate-ready"
    : (["CONFLICT", "DUPLICATE"].includes(status) ? "gate-blocked" : "gate-pending");
  return `<span class="gate ${cls}">${esc(status)}</span>`;
}

async function saveFinanceSettings(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.getElementById("financeSettingsMessage");
  try {
    message.textContent = "Đang lưu và tính lại…";
    const result = await request("/finance/settings", {
      method: "PATCH",
      body: JSON.stringify({
        base_currency: form.elements.base_currency.value.trim().toUpperCase(),
        max_rate_age_days: Number(form.elements.max_rate_age_days.value),
        actor: "Tran",
      }),
    });
    message.textContent = `Đã chuẩn hóa ${result.normalized_rows} dòng; thiếu tỷ giá cho ${result.missing_rows} dòng.`;
    await Promise.all([loadFinance(), loadOperations()]);
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
  }
}

async function submitFxRate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.getElementById("fxRateMessage");
  try {
    message.textContent = "Đang lưu đề xuất…";
    const result = await request("/finance/fx-rates", {
      method: "POST",
      body: JSON.stringify({
        rate_date: form.elements.rate_date.value,
        from_currency: form.elements.from_currency.value.trim().toUpperCase(),
        to_currency: form.elements.to_currency.value.trim().toUpperCase(),
        rate: Number(form.elements.rate.value),
        source_name: form.elements.source_name.value.trim(),
        source_url: form.elements.source_url.value.trim(),
        checked_at: new Date(form.elements.checked_at.value).toISOString(),
        confidence: Number(form.elements.confidence.value || 0),
        actor: "Tran",
      }),
    });
    message.textContent = result.duplicate
      ? "Nguồn này đã tồn tại; metadata đề xuất đã được cập nhật."
      : "Đã lưu PROPOSED; chưa áp dụng vào số tiền.";
    await Promise.all([loadFinance(), loadOperations()]);
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
  }
}

async function reviewFxRate(rateId, action) {
  const message = document.getElementById("fxRateMessage");
  try {
    message.textContent = action === "ACCEPT" ? "Đang xác nhận và tính lại…" : "Đang từ chối…";
    const result = await request(`/finance/fx-rates/${rateId}/review`, {
      method: "POST",
      body: JSON.stringify({action, reviewed_by: "Tran"}),
    });
    message.textContent = `${result.rate.review_status} · ${result.normalization.normalized_rows} dòng đã có tỷ giá.`;
    await Promise.all([loadFinance(), loadOperations()]);
  } catch (error) {
    message.textContent = `Lỗi: ${error.message}`;
  }
}

async function resolveReconciliation(itemId) {
  const note = window.prompt("Ghi lý do đóng mục đối soát:", "Đã kiểm tra và ghi nhận.");
  if (!note) return;
  await request(`/finance/reconciliation/${itemId}/resolve`, {
    method: "POST",
    body: JSON.stringify({resolved_by: "Tran", note}),
  });
  await Promise.all([loadFinance(), loadOperations()]);
}

async function loadFinance() {
  const [summary, rows, normalization, settings, rates, reconciliation] = await Promise.all([
    request("/finance/summary"),
    request("/finance/commissions?limit=100"),
    request("/finance/normalization"),
    request("/finance/settings"),
    request("/finance/fx-rates"),
    request("/finance/reconciliation"),
  ]);
  const settingsForm = document.getElementById("financeSettingsForm");
  settingsForm.elements.base_currency.value = settings.base_currency;
  settingsForm.elements.max_rate_age_days.value = settings.max_rate_age_days;
  const fxForm = document.getElementById("fxRateForm");
  if (!fxForm.elements.rate_date.value) fxForm.elements.rate_date.value = new Date().toISOString().slice(0, 10);
  if (!fxForm.elements.checked_at.value) fxForm.elements.checked_at.value = localDateTimeValue();
  if (!fxForm.elements.to_currency.value) fxForm.elements.to_currency.value = settings.base_currency;

  document.getElementById("financeCards").innerHTML = [
    metric("Transactions", summary.total_transactions, `${summary.total_unattributed} unattributed`),
    metric("Spend đã quy đổi", money(normalization.normalized_spend, normalization.base_currency), `${normalization.spend_normalized}/${normalization.spend_rows} dòng`),
    metric("Cash received", money(normalization.cash_received, normalization.base_currency), `${normalization.commission_normalized}/${normalization.commission_rows} commission`),
    metric("Actual net cash", money(normalization.actual_net_cash, normalization.base_currency), "Cash received trừ spend"),
  ].join("");

  const missingPairs = Object.entries(normalization.missing_pairs || {})
    .map(([pair, count]) => `${esc(pair)}: ${count}`)
    .join(" · ") || "Không thiếu tỷ giá";
  document.getElementById("normalizationCoverage").innerHTML =
    `<strong>Độ phủ:</strong> spend ${normalization.spend_normalized}/${normalization.spend_rows} · commission ${normalization.commission_normalized}/${normalization.commission_rows}<br><strong>Còn thiếu:</strong> ${missingPairs}`;

  const fxBody = document.getElementById("fxRateRows");
  if (!rates.length) {
    fxBody.innerHTML = '<tr><td colspan="7" class="empty">Chưa có tỷ giá. Số tiền cùng đồng tiền chung vẫn được giữ theo tỷ lệ 1:1.</td></tr>';
  } else {
    fxBody.innerHTML = rates.map((item) => {
      const eligible = item.review_status === "PROPOSED" && Number(item.confidence) >= 0.8;
      const actions = item.review_status === "PROPOSED"
        ? `<button class="button fx-review" data-rate-id="${item.id}" data-action="ACCEPT"${eligible ? "" : " disabled"}>Chấp nhận</button> <button class="button secondary fx-review" data-rate-id="${item.id}" data-action="REJECT">Từ chối</button>`
        : "—";
      return `<tr>
        <td>${esc(item.rate_date)}</td>
        <td><strong>${esc(item.from_currency)} → ${esc(item.to_currency)}</strong></td>
        <td>${Number(item.rate).toLocaleString("en-US", {maximumFractionDigits: 12})}</td>
        <td>${safeExternalLink(item.source_url, item.source_name)}</td>
        <td>${Number(item.confidence).toFixed(2)}</td>
        <td>${stateBadge(item.review_status)}</td>
        <td>${actions}</td>
      </tr>`;
    }).join("");
  }

  const body = document.getElementById("commissionRows");
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">Chưa có commission.</td></tr>';
  } else {
    body.innerHTML = rows.map((item) => `
      <tr>
        <td>${new Date(item.occurred_at).toLocaleString("vi-VN")}</td>
        <td><span class="mono">${esc(item.external_id)}</span></td>
        <td>${esc(item.source)}</td>
        <td><span class="state state-${item.state.toLowerCase()}">${esc(item.state)}</span></td>
        <td>${money(item.amount, item.currency)}${item.normalized_amount == null ? "" : `<br><span class="small">${money(item.normalized_amount, item.normalized_currency)}</span>`}</td>
        <td>${reconciliationBadge(item.reconciliation_status || "UNATTRIBUTED")}<br><span class="small">${esc(item.click_reference || "")}</span></td>
      </tr>`).join("");
  }

  const counts = Object.entries(reconciliation.status_counts || {})
    .map(([status, count]) => `${esc(status)}: ${count}`).join(" · ") || "Chưa có commission";
  const issues = Object.entries(reconciliation.open_issue_counts || {})
    .map(([status, count]) => `${esc(status)}: ${count}`).join(" · ") || "Không có DUPLICATE/CONFLICT mở";
  document.getElementById("reconciliationSummary").innerHTML =
    `<strong>Attribution:</strong> ${counts}<br><strong>Ngoại lệ:</strong> ${issues}`;
  const reconciliationBody = document.getElementById("reconciliationRows");
  if (!reconciliation.items.length) {
    reconciliationBody.innerHTML = '<tr><td colspan="5" class="empty">Chưa có mục đối soát.</td></tr>';
  } else {
    reconciliationBody.innerHTML = reconciliation.items.map((item) => {
      const action = item.resolved_at
        ? `<span class="small">Đã đóng · ${esc(item.resolved_by || "system")}</span>`
        : `<button class="button secondary reconciliation-resolve" data-item-id="${item.id}">Đánh dấu đã xử lý</button>`;
      return `<tr>
        <td>${reconciliationBadge(item.status)}</td>
        <td>${esc(item.entity_type)}<br><span class="mono">${esc(item.entity_id || "—")}</span></td>
        <td>${esc(item.reason)}</td>
        <td>${new Date(item.updated_at).toLocaleString("vi-VN")}</td>
        <td>${action}</td>
      </tr>`;
    }).join("");
  }
}

function humanBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes/1024).toFixed(1)} KB`;
  return `${(bytes/1024/1024).toFixed(2)} MB`;
}

function backupStatusLabel(status) {
  const labels = {
    OK: "ĐÃ XÁC MINH",
    CHECKSUM_MISMATCH: "SAI CHECKSUM",
    INTEGRITY_ERROR: "LỖI TOÀN VẸN",
    FOREIGN_KEY_ERROR: "LỖI LIÊN KẾT",
    SCHEMA_MISMATCH: "SAI SCHEMA",
    INVALID: "KHÔNG ĐỌC ĐƯỢC",
    UNKNOWN: "CHƯA XÁC MINH",
  };
  const value = status || "UNKNOWN";
  const className = value === "OK" ? "risk-green" : "risk-red";
  return `<span class="${className}">${esc(labels[value] || value)}</span>`;
}

async function loadBackups() {
  const items = await request("/system/backups");
  const body = document.getElementById("backupRows");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">Chưa có backup.</td></tr>';
    return;
  }
  body.innerHTML = items.map((item) => `
    <tr><td>${new Date(item.created_at).toLocaleString("vi-VN")}</td><td>${esc(item.name)}</td><td>${humanBytes(item.size_bytes)}</td><td><span class="mono">${esc((item.alembic_versions || []).join(", ") || "không rõ")}</span></td><td>${backupStatusLabel(item.database_status)}</td><td><span class="mono">${esc(item.sha256.slice(0, 16))}…</span></td></tr>`).join("");
}

async function createBackupNow() {
  const message = document.getElementById("backupMessage");
  message.textContent = " Đang tạo backup…";
  try {
    const result = await request("/system/backups", {method: "POST", body: "{}"});
    message.textContent = ` ${result.message} (${result.backup.name} · ${result.backup.database_status === "OK" ? "ĐÃ XÁC MINH" : result.backup.database_status})`;
    await loadBackups();
  } catch (error) {
    message.textContent = ` Lỗi: ${error.message}`;
  }
}

document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.view));
});
document.getElementById("refreshAll").addEventListener("click", refreshAll);
document.getElementById("projectTraceForm").addEventListener("submit", (event) => {
  event.preventDefault();
  tracePortfolioProject(event.currentTarget);
});
document.getElementById("appraisalBatchToggle").addEventListener("click", () => {
  const panel = document.getElementById("appraisalBatchPanel");
  panel.hidden = !panel.hidden;
});
document.getElementById("appraisalBatchRun").addEventListener("click", () => {
  runAppraisalBatch().catch((error) => {
    document.getElementById("appraisalBatchResults").textContent = `Lỗi: ${error.message}`;
  });
});
document.getElementById("appraisalBatchResults").addEventListener("click", (event) => {
  const button = event.target.closest("[data-appraisal-domain]");
  const result = button ? appraisalCache.get(button.dataset.appraisalDomain) : null;
  if (result) renderAppraisal(result);
});
document.getElementById("appraisalResult").addEventListener("click", (event) => {
  const button = event.target.closest("[data-appraisal-save]");
  if (!button || button.disabled) return;
  saveAppraisalToStepTwo(button.dataset.appraisalSave, button).catch((error) => {
    button.disabled = false;
    window.alert(`Không thể lưu Bước 2: ${error.message}`);
  });
});
document.getElementById("portfolioFilters").addEventListener("submit", (event) => {
  event.preventDefault();
  loadPortfolio().catch((error) => {
    document.getElementById("portfolioSummary").textContent = `Lỗi: ${error.message}`;
  });
});
document.getElementById("portfolioRows").addEventListener("click", (event) => {
  const intakeButton = event.target.closest("button[data-project-intake]");
  if (intakeButton) {
    intakePortfolioProject(intakeButton.dataset.projectIntake, intakeButton);
    return;
  }
  const metricButton = event.target.closest("button[data-truth-metric]");
  if (metricButton) {
    openMetricTruth(metricButton.dataset.truthProject, metricButton.dataset.truthMetric);
    return;
  }
  const detailButton = event.target.closest("button[data-project-detail]");
  if (detailButton) openProjectDetail(detailButton.dataset.projectDetail);
});
document.getElementById("stepTwoProjectRows").addEventListener("click", (event) => {
  const campPlanButton = event.target.closest("button[data-camp-plan-project]");
  if (campPlanButton) {
    openCampPlanProject(campPlanButton.dataset.campPlanProject).catch((error) => {
      document.getElementById("stepTwoProjectSummary").textContent = `Lỗi: ${error.message}`;
    });
    return;
  }
  const detailButton = event.target.closest("button[data-project-detail]");
  if (detailButton) openProjectDetail(detailButton.dataset.projectDetail);
});
document.getElementById("campPlanGenerate").addEventListener("click", () => generateActiveCampPlan(false));
document.getElementById("campPlanRelint").addEventListener("click", () => generateActiveCampPlan(true));
document.getElementById("campPlanDeploy").addEventListener("click", deployActiveCampPlan);
document.getElementById("campPlanAdsAccount").addEventListener("change", () => {
  document.getElementById("campPlanDeploy").disabled = true;
  document.getElementById("campPlanLintSummary").textContent = "Tài khoản đã đổi; bấm Kiểm tra lại để lưu trước khi triển khai.";
});
document.getElementById("campPlanEditor").addEventListener("input", (event) => {
  const input = event.target.closest("[data-camp-field]");
  if (!input) return;
  const max = Number(input.dataset.campMax || 0);
  const counter = input.parentElement.querySelector(".camp-plan-char-count");
  if (counter && max) {
    counter.textContent = `${input.value.length}/${max}`;
    counter.classList.toggle("over", input.value.length > max);
  }
  document.getElementById("campPlanDeploy").disabled = true;
  document.getElementById("campPlanLintSummary").textContent = "Nội dung đã sửa; bấm Kiểm tra lại trước khi triển khai.";
});
document.getElementById("campPlanStepThree").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-switch-view]");
  if (button) switchView(button.dataset.switchView);
});
document.getElementById("truthDrawerBody").addEventListener("click", (event) => {
  const proposalButton = event.target.closest("button[data-step-commercial-id], button[data-step-commission-id], button[data-step-evidence-id]");
  if (proposalButton) {
    reviewStepOneProposal(proposalButton);
    return;
  }
  const extractTermsButton = event.target.closest("button[data-project-extract-terms]");
  if (extractTermsButton) {
    extractProjectTerms(extractTermsButton);
    return;
  }
  const decisionButton = event.target.closest("button[data-step-one-decision]");
  if (decisionButton) {
    saveProjectStepOneDecision(decisionButton);
    return;
  }
  const autoCheckButton = event.target.closest("button[data-project-auto-check]");
  if (autoCheckButton) {
    runProjectAutoCheck(autoCheckButton);
    return;
  }
  const networkProject = event.target.closest("button[data-project-network]");
  if (networkProject) {
    openProjectDetail(networkProject.dataset.projectNetwork);
    return;
  }
  const switchButton = event.target.closest("button[data-switch-view]");
  if (switchButton) {
    closeTruthDrawer();
    switchView(switchButton.dataset.switchView);
    return;
  }
  const metricButton = event.target.closest("button[data-truth-metric]");
  if (metricButton) openMetricTruth(metricButton.dataset.truthProject, metricButton.dataset.truthMetric);
});
document.getElementById("truthDrawerBody").addEventListener("submit", (event) => {
  if (event.target.id === "projectWorkflowForm") {
    event.preventDefault();
    saveProjectWorkflow(event.target);
  }
});
document.getElementById("truthDrawerClose").addEventListener("click", closeTruthDrawer);
document.getElementById("truthBackdrop").addEventListener("click", closeTruthDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeTruthDrawer();
});
document.getElementById("operationsRows").addEventListener("click", (event) => {
  const exportButton = event.target.closest("button[data-evidence-pack-program]");
  if (exportButton) {
    exportEvidencePack(exportButton.dataset.evidencePackProgram);
    return;
  }
  const button = event.target.closest("button[data-operation-view]");
  if (!button) return;
  openOperation(button).catch((error) => {
    document.getElementById("operationsSummary").textContent = `Lỗi: ${error.message}`;
  });
});
document.getElementById("automationQueueRows").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-automation-job-id]");
  if (!button || button.disabled) return;
  button.disabled = true;
  retryAutomationJob(button.dataset.automationJobId).catch((error) => {
    document.getElementById("automationQueueSummary").textContent = `Lỗi: ${error.message}`;
    button.disabled = false;
  });
});
document.getElementById("captureForm").addEventListener("submit", submitCapture);
document.getElementById("advertiserSnapshotForm").addEventListener("submit", submitAdvertiserSnapshot);
document.getElementById("captureForm").addEventListener("input", (event) => {
  if (["advertiser_name", "project_domain"].includes(event.target.name)) {
    updateCaptureSubmitMode(event.currentTarget);
  }
});
document.getElementById("captureReviewRows").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-capture-review-action]");
  if (!button || button.disabled) return;
  reviewCapture(button);
});
document.getElementById("complianceForm").addEventListener("submit", submitCompliance);
document.getElementById("economicsForm").addEventListener("submit", submitEconomics);
document.getElementById("researchForm").addEventListener("submit", submitResearch);
document.getElementById("programForm").addEventListener("submit", submitProgram);
document.getElementById("evidenceForm").addEventListener("submit", submitEvidence);
document.getElementById("evidenceProgram").addEventListener("change", (event) => {
  setEvidenceProgramSelection(event.target.value);
  loadEvidence(event.target.value);
  loadCommissionFacts(event.target.value);
  loadResearchAttempts(event.target.value);
});
document.getElementById("evidenceRows").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-evidence-id]");
  if (!button || button.disabled) return;
  reviewEvidence(button.dataset.evidenceId, button.dataset.action);
});
document.getElementById("commissionFactRows").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-fact-id]");
  if (!button || button.disabled) return;
  reviewCommissionFact(button.dataset.factId, button.dataset.action);
});
document.getElementById("programRows").addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-program-id]");
  if (!row) return;
  setEvidenceProgramSelection(row.dataset.programId);
  loadEvidence(row.dataset.programId);
  loadCommissionFacts(row.dataset.programId);
  loadResearchAttempts(row.dataset.programId);
});
document.getElementById("exportEvidencePack").addEventListener("click", () => exportEvidencePack());
document.getElementById("previewImport").addEventListener("click", previewCommissionImport);
document.getElementById("commitImport").addEventListener("click", commitCommissionImport);
document.getElementById("financeSettingsForm").addEventListener("submit", saveFinanceSettings);
document.getElementById("fxRateForm").addEventListener("submit", submitFxRate);
document.getElementById("fxRateRows").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-rate-id]");
  if (!button || button.disabled) return;
  reviewFxRate(button.dataset.rateId, button.dataset.action);
});
document.getElementById("reconciliationRows").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-item-id]");
  if (!button) return;
  resolveReconciliation(button.dataset.itemId).catch((error) => {
    document.getElementById("reconciliationSummary").textContent = `Lỗi: ${error.message}`;
  });
});
document.getElementById("previewCampaignImport").addEventListener("click", previewCampaignImport);
document.getElementById("commitCampaignImport").addEventListener("click", commitCampaignImport);
document.querySelector('#campaignImportForm input[type="file"]').addEventListener("change", () => {
  campaignImportPreviewReady = false;
  document.getElementById("commitCampaignImport").disabled = true;
  document.getElementById("campaignImportMessage").textContent = "File đã đổi; hãy xem trước lại.";
});
document.getElementById("exposureRows").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-campaign-id]");
  if (!button) return;
  acknowledgeCampaignRisk(button.dataset.campaignId).catch((error) => {
    document.getElementById("campaignImportMessage").textContent = `Lỗi: ${error.message}`;
  });
});
document.getElementById("exposureRows").addEventListener("change", (event) => {
  const select = event.target.closest("select[data-campaign-id]");
  if (!select) return;
  mapCampaignProgram(select.dataset.campaignId, select.value).catch((error) => {
    document.getElementById("campaignImportMessage").textContent = `Lỗi: ${error.message}`;
  });
});
document.querySelector('#commissionImportForm input[type="file"]').addEventListener("change", () => {
  importPreviewReady = false;
  document.getElementById("commitImport").disabled = true;
  document.getElementById("importMessage").textContent = "File đã đổi; hãy Preview lại.";
});
document.getElementById("createBackup").addEventListener("click", createBackupNow);
document.getElementById("resourcePlanApply").addEventListener("click", () => loadResources().catch((error) => {
  document.getElementById("resourcePlanSource").textContent = `Lỗi: ${error.message}`;
}));
document.getElementById("resourceEmailForm").addEventListener("submit", submitResourceEmail);
document.getElementById("resourceAdsForm").addEventListener("submit", submitResourceAdsAccount);
document.getElementById("resourceInventoryForm").addEventListener("submit", submitResourceInventory);
document.getElementById("resourceEmailRows").addEventListener("click", (event) => {
  const button = event.target.closest("[data-save-nurture]");
  if (button) saveNurtureCheck(button);
});
document.querySelector('[name="conversion_basis"]').addEventListener("change", syncEconomicsConversionMode);
syncEconomicsConversionMode();
populatePermissionSelects();
updateCaptureSubmitMode();
setLocalDateTime(document.getElementById("advertiserSnapshotForm").elements.checked_at);
setLocalDateTime(document.getElementById("resourceEmailForm").elements.created_at);
refreshAll();
