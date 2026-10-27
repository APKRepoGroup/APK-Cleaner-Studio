/* Comparison of independent, read-only analyses. No before/after inference. */
(() => {
  "use strict";
  function difference(left, right) {
    const a = new Set(left), b = new Set(right);
    const sort = values => values.sort((x, y) => x.localeCompare(y, "tr"));
    return { added: sort([...b].filter(value => !a.has(value))), removed: sort([...a].filter(value => !b.has(value))), common: sort([...a].filter(value => b.has(value))) };
  }
  function compare(left, right) {
    const info = report => report.package_info || {};
    const version = report => {
      const value = info(report).version_code, major = info(report).version_code_major;
      return Number.isInteger(value) ? Number.isInteger(major) && major > 0 ? `${major}:${value}` : String(value) : null;
    };
    const abis = report => Array.isArray(info(report).abis) ? [...new Set(info(report).abis)].sort().join(" · ") || "Native kütüphane yok" : null;
    const row = (label, a, b) => ({ label, left: a ?? "Okunamadı", right: b ?? "Okunamadı", changed: a != null && b != null && a !== b });
    const permissions = difference(info(left).permissions || [], info(right).permissions || []);
    const networks = difference((left.detections || []).map(item => item.label || item.id), (right.detections || []).map(item => item.label || item.id));
    return {
      sameContent: /^[a-f0-9]{64}$/i.test(left.sha256 || "") && left.sha256 === right.sha256,
      samePackage: Boolean(left.package_name && right.package_name && left.package_name === right.package_name),
      rows: [row("Uygulama adı", info(left).app_name, info(right).app_name), row("Paket adı", left.package_name || null, right.package_name || null),
        row("Sürüm adı", info(left).version_name, info(right).version_name), row("Sürüm kodu", version(left), version(right)),
        row("En düşük Android (API)", info(left).min_sdk, info(right).min_sdk), row("Hedef Android (API)", info(left).target_sdk, info(right).target_sdk),
        row("İşlemci mimarileri", abis(left), abis(right)), row("Dosya boyutu (bayt)", left.size, right.size),
        row("DEX dosyaları", left.dex_count, right.dex_count), row("İstenen izinler", info(left).permissions?.length, info(right).permissions?.length),
        row("Tespit edilen reklam ağları", left.detections?.length, right.detections?.length), row("SHA-256", left.sha256 || null, right.sha256 || null)],
      permissions, networks,
    };
  }
  globalThis.StudioComparison = Object.freeze({ compare, difference });
})();
