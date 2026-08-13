const form = document.getElementById("form");
const message = document.getElementById("message");
let page = { url: "", title: "", selected: "", visible: "" };

async function collectPage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => ({
      url: location.href,
      title: document.title,
      selected: window.getSelection()?.toString()?.trim() || "",
      visible: (document.body?.innerText || "").slice(0, 50000),
    }),
  });
  page = result;
  form.elements.selected_text.value = page.selected || "";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "Đang gửi…";
  const data = Object.fromEntries(new FormData(form).entries());
  Object.keys(data).forEach((key) => data[key] === "" && delete data[key]);
  const payload = {
    ...data,
    source_url: page.url,
    page_title: page.title,
    visible_text: page.visible,
    selected_text: data.selected_text || page.selected,
    country: data.country?.toUpperCase(),
    metadata: { capture_method: "chrome-extension-review-queue-v2" },
  };
  try {
    const response = await fetch("http://127.0.0.1:8765/api/ad-intelligence/captures", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(await response.text());
    const result = await response.json();
    if (result.status === "NEEDS_REVIEW" || result.status === "RAW") {
      message.textContent = `Đã lưu snapshot #${result.id} · Đang chờ duyệt advertiser/domain`;
    } else if (result.status === "PARSED") {
      message.textContent = `Đã lưu snapshot #${result.id} · Đã tạo observation`;
    } else {
      message.textContent = `Đã nhận snapshot #${result.id} · ${result.status || "UNKNOWN"}`;
    }
  } catch (error) {
    message.textContent = `Không gửi được: ${error.message}`;
  }
});

collectPage().catch((error) => { message.textContent = `Không đọc được trang: ${error.message}`; });
