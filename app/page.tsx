"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import Image from "next/image";
import packageInfo from "../package.json";

type Profile = "safe" | "balanced" | "deep";
type Screen = "select" | "ready" | "working" | "done";
type ThemePreference = "light" | "system" | "dark";

const profiles: Array<{
  id: Profile;
  name: string;
  time: string;
  description: string;
  tone: string;
}> = [
  {
    id: "safe",
    name: "Güvenli",
    time: "En uyumlu",
    description: "Yalnızca doğrulanmış reklam gösterme ve yükleme çağrılarını etkisizleştirir.",
    tone: "green",
  },
  {
    id: "balanced",
    name: "Dengeli",
    time: "Önerilen",
    description: "DEX düzenlemesine manifest bileşenlerini ve doğrulanmış XML alanlarını ekler.",
    tone: "orange",
  },
  {
    id: "deep",
    name: "Kapsamlı",
    time: "En geniş kapsam",
    description: "Dengeli profile ek olarak kesin asset ve native SDK kalıntılarını hedefler.",
    tone: "red",
  },
];

const networks = ["Google Ads", "AppLovin MAX", "Vungle", "Pangle", "InMobi", "Unity Ads"];

function fileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [profile, setProfile] = useState<Profile>("balanced");
  const [screen, setScreen] = useState<Screen>("select");
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState("APK yapısı hazırlanıyor");
  const [theme, setTheme] = useState<ThemePreference>("system");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const saved = localStorage.getItem("apk-cleaner-theme") as ThemePreference | null;
    const preference = saved && ["light", "system", "dark"].includes(saved) ? saved : "system";
    queueMicrotask(() => setTheme(preference));
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = (next: ThemePreference) => {
      const resolved = next === "system" ? (media.matches ? "dark" : "light") : next;
      document.documentElement.dataset.theme = resolved;
      document.documentElement.dataset.themePreference = next;
    };
    apply(theme);
    const onSystemChange = () => {
      if (theme === "system") apply("system");
    };
    media.addEventListener("change", onSystemChange);
    return () => media.removeEventListener("change", onSystemChange);
  }, [theme]);

  useEffect(() => {
    if (screen !== "working") return;
    const phases = [
      "APK yapısı hazırlanıyor",
      "DEX dosyaları taranıyor",
      "Reklam ağları eşleniyor",
      "Güvenli yamalar uygulanıyor",
      "Manifest ve izinler temizleniyor",
      "APK yeniden imzalanıyor",
    ];
    let value = 0;
    const timer = window.setInterval(() => {
      value = Math.min(100, value + 1);
      setProgress(value);
      setPhase(phases[Math.min(phases.length - 1, Math.floor(value / 18))]);
      if (value >= 100) {
        window.clearInterval(timer);
        window.setTimeout(() => setScreen("done"), 450);
      }
    }, 45);
    return () => window.clearInterval(timer);
  }, [screen]);

  function acceptFile(next: File | undefined) {
    if (!next || ![".apk", ".apks", ".apkm", ".xapk"].some((suffix) => next.name.toLowerCase().endsWith(suffix))) {
      setNotice("Lütfen APK, APKS, APKM veya XAPK dosyası seç.");
      return;
    }
    if (next.size > 1024 ** 3) {
      setNotice("APK 1 GB sınırını aşıyor.");
      return;
    }
    setNotice("");
    setFile(next);
    setScreen("ready");
  }

  function chooseTheme(next: ThemePreference) {
    setTheme(next);
    localStorage.setItem("apk-cleaner-theme", next);
  }

  function reset() {
    setFile(null);
    setProgress(0);
    setNotice("");
    setScreen("select");
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="APK Cleaner Studio ana sayfa">
          <span className="brand-mark" aria-hidden="true" />
          <span>
            <b>APK Cleaner</b>
            <small>Studio</small>
          </span>
        </a>
        <div className="status-pill"><i /> Yerel motor hazır</div>
        <div className="top-actions">
          <div className="theme-switcher" role="group" aria-label="Görünüm teması">
            {([
              ["light", "☀", "Açık"],
              ["system", "◐", "Sistem"],
              ["dark", "☾", "Koyu"],
            ] as Array<[ThemePreference, string, string]>).map(([id, icon, label]) => (
              <button key={id} type="button" aria-label={`${label} tema`} aria-pressed={theme === id} title={`${label} tema`} onClick={() => chooseTheme(id)}>
                <span aria-hidden="true">{icon}</span><em>{label}</em>
              </button>
            ))}
          </div>
          <button className="icon-button" aria-label="Ayarlar">⚙</button>
        </div>
      </header>

      <section className="hero" id="top">
        <div className="eyebrow"><span>◆</span> Yerel Android paket işleme stüdyosu</div>
        <h1>Paketini bırak.<br /><em>Temiz, tek APK olarak al.</em></h1>
        <p className="hero-copy">
          APK reklam izlerini temizle; APKS, APKM ve XAPK paketlerini tek kurulabilir APK’ya dönüştür. Tüm düzenleme işlemleri cihazında gerçekleşir.
        </p>
        <div className="hero-metrics" aria-label="Ürün özeti"><span><b>18</b> reklam ağı</span><span><b>4</b> paket türü</span><span><b>%100</b> cihazda işlem</span><span><b>v{packageInfo.version}</b> yerel motor</span></div>
      </section>

      <section className="workspace" aria-label="APK temizleme alanı">
        <div className="stage-card">
          <div className="steps" aria-label="İşlem adımları">
            {["Paket", "Yapılandır", "İşle", "İndir"].map((label, index) => {
              const active = screen === "select" ? 0 : screen === "ready" ? 1 : screen === "working" ? 2 : 3;
              return (
                <div className={index <= active ? "step active" : "step"} key={label}>
                  <span>{index < active ? "✓" : index + 1}</span>{label}
                </div>
              );
            })}
          </div>

          {screen === "select" && (
            <div
              className={dragging ? "dropzone dragging" : "dropzone"}
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => { event.preventDefault(); setDragging(false); acceptFile(event.dataTransfer.files[0]); }}
            >
              <input ref={inputRef} type="file" accept=".apk,.apks,.apkm,.xapk,application/vnd.android.package-archive" onChange={(event) => acceptFile(event.target.files?.[0])} />
              <div className="local-badge"><i /> Güvenli yerel işlem</div>
              <div className="upload-orbit"><span>↑</span></div>
              <h2>İşlenecek paketi buraya bırak</h2>
              <p>APK · APKS · APKM · XAPK</p>
              <button className="primary-button" onClick={() => inputRef.current?.click()}>Dosya seç</button>
              <small>En fazla 1 GB · Dosyan yalnızca bu cihazda işlenir</small>
              {notice && <div className="inline-notice" role="status">{notice}</div>}
            </div>
          )}

          {screen === "ready" && file && (
            <div className="ready-view">
              <div className="file-card">
                <div className="apk-icon">APK</div>
                <div><b>{file.name}</b><span>{fileSize(file.size)} · Yerel analiz için hazır</span></div>
                <button onClick={reset} aria-label="Dosyayı kaldır">×</button>
              </div>
              <div className="profile-heading"><div><span>Temizlik kapsamı</span><h2>Temizlik kapsamını belirle</h2></div><span className="recommendation">Dengeli önerilir</span></div>
              <div className="profile-grid">
                {profiles.map((item) => (
                  <button key={item.id} className={profile === item.id ? `profile selected ${item.tone}` : `profile ${item.tone}`} onClick={() => setProfile(item.id)}>
                    <span className="radio" />
                    <strong>{item.name}</strong>
                    <small>{item.time}</small>
                    <p>{item.description}</p>
                  </button>
                ))}
              </div>
              <div className="action-row">
                <button className="ghost-button" onClick={reset}>Geri</button>
                <button className="primary-button wide" onClick={() => setScreen("working")}>Temizlemeyi başlat <span>→</span></button>
              </div>
            </div>
          )}

          {screen === "working" && (
            <div className="working-view">
              <div className="radar" style={{ "--progress": progress } as CSSProperties}><span>{progress}%</span></div>
              <div className="working-copy"><span>Yerel işlem sürüyor</span><h2>{phase}</h2><p>İşlem tamamlanana kadar bu pencereyi açık bırak. Orijinal APK değiştirilmiyor.</p></div>
              <div className="progress-track"><i style={{ width: `${progress}%` }} /></div>
              <div className="live-log"><span className="done">✓</span> Orijinal imza yedeklendi <span className="done">✓</span> {Math.max(1, Math.floor(progress / 14))} DEX denetlendi <span className="blink">●</span> {phase}</div>
            </div>
          )}

          {screen === "done" && file && (
            <div className="done-view">
              <div className="success-mark">✓</div>
              <span className="completion-label">İşlem tamamlandı</span>
              <h2>Çıktı başarıyla oluşturuldu.</h2>
              <p>Değişiklikler yeni APK’ya yazıldı; orijinal dosyan korunmaya devam ediyor.</p>
              <div className="result-stats">
                <div><b>6</b><span>Reklam ağı</span></div>
                <div><b>184</b><span>Güvenli yama</span></div>
                <div><b>23</b><span>Manifest kaydı</span></div>
                <div><b>0</b><span>Kritik hata</span></div>
              </div>
              <div className="result-actions">
                <button className="primary-button wide">Temiz APK’yı indir <span>↓</span></button>
                <button className="ghost-button">Raporu aç</button>
              </div>
              <button className="text-button" onClick={reset}>Başka bir APK işle</button>
            </div>
          )}
        </div>

        <aside className="side-card">
          <div className="side-card-head"><span>REKLAM AĞI PROFİLLERİ</span><b>12 ağ tanınıyor</b></div>
          <div className="network-list">
            {networks.map((network, index) => <div key={network}><span className={`network-logo n${index}`}>{network.slice(0, 1)}</span><b>{network}</b><i>Hazır</i></div>)}
          </div>
          <button className="all-networks">Tüm profilleri gör <span>12</span></button>
          <div className="privacy-note"><span>⌾</span><div><b>Cihazında ve özel</b><p>APK dosyan internete yüklenmez; tüm işlemler PC veya telefonunda tamamlanır.</p></div></div>
        </aside>
      </section>

      <section className="trust-row" aria-label="Ürün özellikleri">
        <div><span>01</span><b>Orijinal dosya korunur</b><p>Her işlem ayrı bir çıktı ve ayrıntılı rapor üretir.</p></div>
        <div><span>02</span><b>Doğrulanmış profiller</b><p>SDK paketine uygun güvenli kurallar otomatik seçilir.</p></div>
        <div><span>03</span><b>Windows + Termux</b><p>Aynı arayüz, aynı yerel motor ve tutarlı kullanım akışı.</p></div>
      </section>

      <footer className="community-footer">
        <div className="community-brand"><Image src="/apk-repo-icon.png" alt="" aria-hidden="true" width={52} height={52} /><div><b>APK Repo Grubu</b><p>Android araçları, topluluk desteği ve güncel paylaşımlar.</p></div></div>
        <nav className="community-links" aria-label="APK Repo Grubu bağlantıları">
          <a href="https://linktr.ee/apkrepomod" target="_blank" rel="noopener noreferrer"><span className="website" aria-hidden="true" /><div><small>WEB SİTESİ</small><b>APK Repo</b></div></a>
          <a href="https://t.me/+WZbVyByWkExjNmZk" target="_blank" rel="noopener noreferrer"><span className="telegram" aria-hidden="true" /><div><small>TELEGRAM</small><b>Topluluğa katıl</b></div></a>
          <a href="https://github.com/APKRepoGroup/APK-Cleaner-Studio" target="_blank" rel="noopener noreferrer"><span className="github" aria-hidden="true" /><div><small>GITHUB</small><b>Projeyi incele</b></div></a>
          <a href="https://www.patreon.com/cw/APKRepo" target="_blank" rel="noopener noreferrer" aria-label="APK Repo Patreon sayfasını yeni sekmede aç"><span className="patreon" aria-hidden="true" /><div><small>PATREON</small><b>Destek ol</b></div></a>
        </nav>
        <div className="community-legal"><span>© 2026 APK Repo Grubu.</span><span>APK Cleaner Studio · Yerel paket araçları</span></div>
      </footer>
    </main>
  );
}
