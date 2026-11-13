/* Genshin RAG chat UI — EN/FA bilingual, same query_log + engine as the Telegram bot */
"use strict";

const SAMPLE = {
  en: {
    q: "“I don’t have Kazuha. What alternatives can I use?”",
    a1: "No — Kazuha isn't easily replaceable 1:1, but here's who covers his role: Sucrose is the closest free option (same Anemo grouping via her Skill, plus the shared Elemental Mastery buff), while Venti excels against lighter enemies that can be pulled. For a Kazuha-style EM buff, as a 4-star option, still run Sucrose with the Viridescent Venerer set.",
    a2: "If you're after damage instead, Anemo Traveler works as a budget substitute.",
    srcs: "Kazuha, Ganyu, Sucrose, Viridescent Venerer",
  },
  fa: {
    q: "«کازوها ندارم. چه جایگزینی می‌تونم استفاده کنم؟»",
    a1: "نه — کازوها جایگزین یک‌به‌یک نداره، ولی اینا نقشش رو پوشش می‌دن: سوزو نزدیک‌ترین گزینه رایگانه (همون جمع‌کردن دشمن آنموی اسکیل + باف الِمنتال ماستری)، ونتی هم برای دشمن‌های سبک‌تر که کشیده می‌شن عالیه. برای باف EM مشابه کازوها بین گزینه‌های ۴ ستاره، سوزو با ست Viridescent Venerer رو ببند.",
    a2: "اگه دنبال دمیج هستی، مسافر آنمو (Anemo Traveler) جایگزین ارزونی هست.",
    srcs: "Kazuha, Ganyu, Sucrose, Viridescent Venerer",
  },
};

const I18N = {
  en: {
    title: "GIGPT",
    subtitle: "Your AI Genshin Companion — answers from live game data: characters, skills, constellations, materials, weapons & builds.",
    headline: "Your Genshin Journey, Smarter.",
    tagline: "Ask anything. Explore builds. Compare teams. Make better decisions in Teyvat.",
    placeholder: "Ask about characters, builds, teams, weapons, or game mechanics...",
    limit: "Limit: 15 questions/hour.",
    beta: "Some beta information is datamined and may change before release.",
    tgLink: "Also available on Telegram → @GIGPT_bot",
    thinking: "Consulting the archives… ⏳",
    errGeneric: "Something went wrong. Try again in a minute.",
    errNet: "Can't reach the server. Check your connection and try again.",
    sources: "Sources",
    inputLabel: "Ask a Genshin question",
    send: "Send",
    suggestionsGroup: "Suggested questions",
    featuresH: "What GIGPT does",
    f1h: "Game Knowledge",
    f1p: "Explore characters, weapons, artifacts, skills, and game mechanics.",
    f2h: "Source-backed Answers",
    f2p: "Get answers supported by game data — every answer shows the sources it used.",
    f3h: "Team & Build Analysis",
    f3p: "Compare builds, weapons, and team options to make informed choices.",
    sampleH: "Sample answer",
    sampleNote: "Example of a real GIGPT answer — shortened. Ask your own question above.",
    suggestions: [
      "What's the best build for Varesa?",
      "Compare Nahida and Yae Miko for a Hyperbloom team.",
      "Is Vortex Vanquisher worth upgrading?",
      "How does the Vaporize reaction work?",
    ],
  },
  fa: {
    title: "GIGPT",
    subtitle: "همیار هوشمند جنشین ایمپکت — پاسخ از روی دیتای زنده بازی: کاراکترها، اسکیل‌ها، کانستلیشن، متریال‌ها، سلاح‌ها و بیلدها.",
    headline: "سفر جنشینت، هوشمندتر.",
    tagline: "هرچی می‌خوای بپرس. بیلد بساز. تیم‌ها رو مقایسه کن. تصمیم‌های بهتری در تِیوات بگیر.",
    placeholder: "درباره کاراکترها، بیلدها، تیم‌ها، سلاح‌ها یا مکانیک بازی بپرس…",
    limit: "محدودیت: ۱۵ سوال در ساعت.",
    beta: "بعضی اطلاعات بتا دیتاماین شدن و ممکنه قبل از انتشار تغییر کنن.",
    tgLink: "نسخه تلگرام ← ‎@GIGPT_bot",
    thinking: "دارم از آرشیو می‌پرسم… ⏳",
    errGeneric: "یه خطایی پیش اومد. یه دقیقه دیگه دوباره امتحان کن.",
    errNet: "به سرور دسترسی ندارم. اتصالت رو چک کن و دوباره امتحان کن.",
    sources: "منابع",
    inputLabel: "سوال جنشین بپرس",
    send: "ارسال",
    suggestionsGroup: "سوال‌های پیشنهادی",
    featuresH: "GIGPT چه کاری انجام می‌ده",
    f1h: "دانش بازی",
    f1p: "کاوش در کاراکترها، سلاح‌ها، آرتیفکت‌ها، اسکیل‌ها و مکانیک‌های بازی.",
    f2h: "پاسخ‌های مستند",
    f2p: "پاسخ‌ها تکیه بر دیتای بازی دارن — هر جواب منابع استفاده‌شده رو نشون می‌ده.",
    f3h: "آنالیز تیم و بیلد",
    f3p: "بیلدها، سلاح‌ها و گزینه‌های تیم رو مقایسه کن و انتخاب آگاهانه داشته باش.",
    sampleH: "نمونه پاسخ",
    sampleNote: "نمونه‌ای از یه پاسخ واقعی GIGPT — خلاصه شده. سوال خودت رو بالا بپرس.",
    suggestions: [
      "بهترین بیلد برای وارسا چیه؟",
      "ناحیده و یه میکو رو برای تیم هایپربلوم مقایسه کن.",
      "آیا Vortex Vanquisher ارزش ارتقا داره؟",
      "واکنش بخار (Vaporize) چطور کار می‌کنه؟",
    ],
  },
};

let lang = "en";
const $ = (id) => document.getElementById(id);
const chat = $("chat");
const form = $("askForm");
const input = $("q");
const sendBtn = $("sendBtn");
let busy = false;
let lastFailed = false;

// API base: same-origin when served by the VPS (borzou.site/genshin/ or dev),
// cross-origin to the VPS API when the UI runs on GitHub Pages (static only).
const SAME_HOST = ["borzou.site", "localhost", "127.0.0.1"].includes(location.hostname);
const API = SAME_HOST ? "api" : "https://borzou.site/genshin/api";

function applyLang() {
  const d = I18N[lang];
  document.documentElement.lang = lang;
  document.body.classList.toggle("rtl", lang === "fa");
  document.body.dir = lang === "fa" ? "rtl" : "ltr";
  for (const el of document.querySelectorAll("[data-i18n]")) {
    el.textContent = d[el.dataset.i18n] ?? el.textContent;
  }
  for (const el of document.querySelectorAll("[data-i18n-ph]")) {
    el.placeholder = d[el.dataset.i18nPh] ?? el.placeholder;
  }
  for (const el of document.querySelectorAll("[data-i18n-aria]")) {
    el.setAttribute("aria-label", d[el.dataset.i18nAria] ?? el.getAttribute("aria-label"));
  }
  // Sample answer section: question, body, sources (sources stay EN entity names — KB ids)
  renderSample();
  // document.title stays EN-only for SEO consistency
  document.title = "GIGPT — Your AI Genshin Companion";
  $("langBtn").textContent = lang === "en" ? "فارسی" : "English";
  renderSuggestions();
  if (!chat.children.length) greet();
}

function greet() {
  const d = I18N[lang];
  const m = document.createElement("div");
  m.className = "msg bot";
  m.textContent = lang === "fa"
    ? "سلام! 👋 هر سوالی از جنشین داری بپرس — کاراکتر، اسکیل، کانستلیشن، متریال ارتقا، سلاح و بیلد."
    : "Hey! 👋 Ask me anything about Genshin — characters, skills, constellations, ascension materials, weapons and builds.";
  chat.appendChild(m);
  renderSuggestions();
}

function renderSuggestions() {
  const box = $("suggestions");
  box.innerHTML = "";
  for (const s of I18N[lang].suggestions) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = s;
    b.addEventListener("click", () => { if (!busy) { input.value = s; form.requestSubmit(); } });
    box.appendChild(b);
  }
}

// Sample answer section: fill from SAMPLE (single source of truth), update on lang switch
function renderSample() {
  const s = SAMPLE[lang];
  const qEl = document.querySelector(".sample-q");
  if (qEl) qEl.textContent = s.q;
  const a1 = document.querySelector(".sample-a [data-i18n='sampleA1']");
  const a2 = document.querySelector(".sample-a [data-i18n='sampleA2']");
  if (a1) a1.textContent = s.a1;
  if (a2) a2.textContent = s.a2;
  const sEl = document.querySelector(".sample-a .srcs");
  if (sEl) sEl.innerHTML = `📚 <span>${I18N[lang].sources}</span>: ${s.srcs} • v7.2`;
}

function bubble(cls, text) {
  const m = document.createElement("div");
  m.className = "msg " + cls;
  m.textContent = text;
  chat.appendChild(m);
  chat.scrollTop = chat.scrollHeight;
  return m;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q || busy) return;
  busy = true;
  lastFailed = false;
  sendBtn.disabled = true;
  input.value = "";
  bubble("user", q);
  const typing = bubble("bot typing", I18N[lang].thinking);
  try {
    const res = await fetch(`${API}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q }),
    });
    const data = await res.json().catch(() => ({}));
    lastFailed = false;
    if (res.ok && data.answer !== undefined) {
      typing.classList.remove("typing");
      typing.textContent = data.answer;
      if (data.sources && data.sources.length) {
        const s = document.createElement("span");
        s.className = "srcs";
        s.textContent = `📚 ${I18N[lang].sources}: ${data.sources.join(", ")}` +
          (data.version ? ` • v${data.version}` : "");
        typing.appendChild(s);
      }
    } else if (res.status === 429) {
      lastFailed = true;
      typing.classList.remove("typing", "bot");
      typing.classList.add("err");
      typing.textContent = data.message || I18N[lang].errGeneric;
    } else {
      lastFailed = true;
      typing.classList.remove("typing", "bot");
      typing.classList.add("err");
      typing.textContent = data.message || I18N[lang].errGeneric;
    }
  } catch (err) {
    lastFailed = true;
    typing.classList.remove("typing", "bot");
    typing.classList.add("err");
    typing.textContent = I18N[lang].errNet;
  }
  if (lastFailed) {
    // Keep the question so the user can retry without retyping
    input.value = q;
    lastFailed = false;
  }
  busy = false;
  sendBtn.disabled = false;
  input.focus();
  chat.scrollTop = chat.scrollHeight;
});

$("langBtn").addEventListener("click", () => {
  lang = lang === "en" ? "fa" : "en";
  applyLang();
});

// Enter sends, Shift+Enter adds a newline (textarea), Esc cancels a failed retry draft
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

fetch(`${API}/health`).then((r) => r.json()).then((d) => {
  if (d && d.version) $("ver").textContent = "v" + d.version;
}).catch(() => { $("ver").textContent = "offline"; });

applyLang();
