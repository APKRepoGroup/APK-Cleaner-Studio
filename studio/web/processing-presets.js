/* Portable options only. APK identity, appearance, paths and accounts are excluded. */
(() => {
  "use strict";
  const FORMAT = "apk-cleaner-processing-profiles", MAX_BYTES = 16384, MAX_PROFILES = 12;
  const flags = ["patchAds", "stripDebug", "restrictStoreUpdates", "normalizeDex", "optimizeApk", "deobfuscateResources"];
  const record = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const only = (value, keys) => Object.keys(value).every(key => keys.includes(key));
  function name(value) {
    if (typeof value !== "string" || /[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/.test(value)) throw Error("Profil adı geçersiz.");
    const result = value.replace(/\s+/g, " ").trim();
    if (!result || result.length > 40) throw Error("Profil adı 1–40 karakter olmalı.");
    return result;
  }
  function options(value, strict = false) {
    if (!record(value) || !["patch", "clone", "convert"].includes(value.operation) || !["safe", "balanced", "deep"].includes(value.profile)
      || strict && (!only(value, ["operation", "profile", ...flags]) || flags.some(key => Object.hasOwn(value, key) && typeof value[key] !== "boolean"))) {
      throw Error("Profil işlem seçenekleri geçersiz.");
    }
    const clean = { operation: value.operation, profile: value.profile };
    for (const key of flags) clean[key] = value[key] === true;
    return clean;
  }
  function parse(text) {
    if (typeof text !== "string" || new TextEncoder().encode(text).length > MAX_BYTES) throw Error("Profil dosyası en fazla 16 KB olmalı.");
    let value;
    try { value = JSON.parse(text.replace(/^\ufeff/, "")); } catch { throw Error("Profil dosyası geçerli bir JSON dosyası değil."); }
    if (!record(value) || !only(value, ["format", "version", "profiles"]) || value.format !== FORMAT || value.version !== 1
      || !Array.isArray(value.profiles) || !value.profiles.length || value.profiles.length > MAX_PROFILES) throw Error("Bu dosya desteklenen bir işlem profili dosyası değil.");
    const names = new Set();
    return value.profiles.map(item => {
      if (!record(item) || !only(item, ["name", "options"])) throw Error("Profil kaydı geçersiz.");
      const clean = { name: name(item.name), options: options(item.options, true) }, key = clean.name.toLocaleLowerCase("tr-TR");
      if (names.has(key)) throw Error("Dosyada aynı ada sahip birden fazla profil var.");
      names.add(key); return clean;
    });
  }
  function serialize(profiles) {
    const text = JSON.stringify({ format: FORMAT, version: 1, profiles: profiles.map(item => ({ name: name(item.name), options: options(item.options) })) }, null, 2) + "\n";
    parse(text); return text;
  }
  function merge(existing, incoming, makeId) {
    if (existing.length + incoming.length > MAX_PROFILES) throw Error("En fazla 12 profil saklanabilir. İçe aktarmadan önce yer açın.");
    const used = new Set(existing.map(item => item.name.toLocaleLowerCase("tr-TR")));
    const added = incoming.map(item => {
      let next = item.name, suffix = 1;
      while (used.has(next.toLocaleLowerCase("tr-TR"))) {
        const tail = ` (${++suffix})`; next = item.name.slice(0, 40 - tail.length) + tail;
      }
      used.add(next.toLocaleLowerCase("tr-TR"));
      return { id: makeId(), name: next, options: options(item.options, true) };
    });
    return { profiles: [...existing, ...added], added };
  }
  globalThis.StudioPresets = Object.freeze({ MAX_BYTES, MAX_PROFILES, parse, serialize, merge, options, name });
})();
