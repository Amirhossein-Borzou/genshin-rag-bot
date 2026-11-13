/* Genshin RAG chat UI — EN/FA bilingual, same query_log + engine as the Telegram bot */
"use strict";

const I18N = {
  en: {
    title: "Genshin Impact Assistant",
    subtitle: "Answers from live game data — characters, skills, constellations, materials, weapons & builds.",
    placeholder: "Ask about a character, weapon, artifact…",
    limit: "Limit: 15 questions/hour.",
    beta: "Beta content is datamined and may change.",
    tgLink: "Also on Telegram → @GIGPT_bot",
    thinking: "Consulting the archives… ⏳",
    errGeneric: "Something went wrong. Try again in a minute.",
    errNet: "Can't reach the server. Check your connection and try again.",
    sources: "Sources",
    suggestions: [
      "What does Ayaka's burst do?",
      "Nahida ascension materials",
      "Mavuika C2 effect",
      "Best artifact set for Arlecchino?",
    ],
  },
  fa: {
    title: "دستیار بازی جنشین ایمپکت",
    subtitle: "پاسخ از روی دیتای زنده بازی — کاراکترها، اسکیل‌ها، کانستلیشن، متریال‌ها، سلاح‌ها و بیلدها.",
    placeholder: "درباره کاراکتر، سلاح یا آرتیفکت بپرس…",
    limit: "محدودیت: ۱۵ سوال در ساعت.",
    beta: "محتوای بتا دیتاماین شده و ممکنه تغییر کنه.",
    tgLink: "نسخه تلگرام ← ‎@GIGPT_bot",
    thinking: "دارم از آرشیو می‌پرسم… ⏳",
    errGeneric: "یه خطایی پیش اومد. یه دقیقه دیگه دوباره امتحان کن.",
    errNet: "به سرور دسترسی ندارم. اتصالت رو چک کن و دوباره امتحان کن.",
    sources: "منابع",
    suggestions: [
      "التیمیت آیاکا چیکار می‌کنه؟",
      "متریال‌های ارتقای ناحیده",
      "افکت C2 ماویکا",
      "بهترین آرتیفکت برای آرلچینو؟",
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
      typing.classList.remove("typing", "bot");
      typing.classList.add("err");
      typing.textContent = data.message || I18N[lang].errGeneric;
    } else {
      typing.classList.remove("typing", "bot");
      typing.classList.add("err");
      typing.textContent = data.message || I18N[lang].errGeneric;
    }
  } catch (err) {
    typing.classList.remove("typing", "bot");
    typing.classList.add("err");
    typing.textContent = I18N[lang].errNet;
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

fetch(`${API}/health`).then((r) => r.json()).then((d) => {
  if (d && d.version) $("ver").textContent = "v" + d.version;
}).catch(() => { $("ver").textContent = "offline"; });

applyLang();
