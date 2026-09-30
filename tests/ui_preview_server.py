"""Local-only UI fixture; never included in a release or connected to real jobs."""
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "studio" / "web"
PROFILES = json.loads((ROOT / "studio" / "profiles.json").read_text(encoding="utf-8"))
TOOLS = dict.fromkeys(("java", "dex_tools", "manifest_tool", "split_tool", "signer", "zipalign", "resource_tool", "fully_ready"), True)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def reply(self, body, content_type="application/json"):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        request_url = urlsplit(self.path)
        path = request_url.path
        if path == "/":
            capture = parse_qs(request_url.query).get("capture", [""])[0]
            if capture == "mobile-result":
                self.reply('''<!doctype html><html lang="tr"><head><meta charset="utf-8"><title>Mobil sonuç önizlemesi</title>
                <style>body{margin:0;background:#151b19;display:flex;justify-content:center}
                iframe{width:390px;height:1800px;border:0;background:#0d1515}</style></head>
                <body><iframe title="Mobil sonuç" src="/?embedded=android&amp;capture=result"></iframe></body></html>''', "text/html")
                return
            html = (WEB / "index.html").read_text(encoding="utf-8")
            marks = [dict(id=key, label=value["label"], references=4313 - i * 199) for i, (key, value) in enumerate(PROFILES.items())]
            bridge = '''<script>const qaApps=Array.from({length:100},(_,i)=>({package:'com.example.app'+i,label:'Test uygulaması '+(i+1),version:'1.2.0',splits:i%3,icon:'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><rect width="48" height="48" rx="12" fill="#239b84"/><circle cx="24" cy="24" r="12" fill="#d9ff43"/></svg>')})); globalThis.AndroidThemeBridge={setTheme(){},requestInstalledPackages(){onInstalledPackagesLoaded(JSON.stringify(qaApps));}};</script>'''
            controls_display = "none" if capture else "flex"
            controls = f'''<nav id="qa" style="position:fixed;bottom:0;left:0;right:0;z-index:9999;background:#eee;padding:6px;display:{controls_display};gap:6px;flex-wrap:wrap;color:#111;font:12px system-ui">
            <button onclick="document.querySelector('#networkTitle').scrollIntoView()">QA Simgeler</button>
            <button onclick="openInstalledApps()">QA Liste</button>
            <button onclick="qaIconIdentity()">QA İkon testi</button><output id="qaResult" role="status"></output>
            <button onclick="qaAnalysis(true)">QA Analiz</button>
            <button onclick="qaAnalysis(false)">QA Reklamsız</button>
            <button onclick="document.querySelector('.special-thanks').scrollIntoView()">QA Teşekkürler</button>
            <button onclick="openReportViewer('fixture','Örnek işlem raporu')">QA Rapor</button>
            <button onclick="confirmAction('Örnek onay','Bu yalnızca görsel bir testtir.')">QA Onay</button>
            <button onclick="openMessageReview()">QA Mesaj</button>
            <button onclick="showView('#workingView');resetProgress();updateProgress(50,'Yerel işlem sürüyor');document.querySelector('#workingView').scrollIntoView()">QA İlerleme</button>
            <button onclick="showView('#resultView');document.querySelector('#resultView').scrollIntoView()">QA Sonuç</button>
            <button onclick="setNativeVisibility(false)">QA Arka plan</button>
            <button onclick="setNativeVisibility(true)">QA Ön plan</button>
            <button onclick="applyTheme('light')">QA Açık</button><button onclick="applyTheme('dark')">QA Koyu</button>
            </nav>'''
            if capture in {"analysis", "analysis-apk", "result", "failure", "store-updates"}:
                html = html.replace(
                    "</head>",
                    "<style>.hero,#mobileHttpsBanner,.starter-content,footer{display:none!important}.workspace{margin-top:24px!important}</style></head>",
                    1,
                )
            elif capture == "working":
                html = html.replace(
                    "</head>",
                    "<style>.hero,#mobileHttpsBanner,footer{display:none!important}.workspace{margin-top:24px!important}</style></head>",
                    1,
                )
            html = html.replace('<script src="ui-runtime.js', bridge + '<script src="ui-runtime.js', 1)
            setup = '''function qaAnalysis(ads,shouldScroll=true,split=true) { const analysis={filename:split?'Görsel test.apks':'Görsel test.apk',package_name:'com.example.visualtest',size:10240,dex_count:3,network_count:ads?18:0,detections:ads?qaMarks:[],split_merged:split,split_options:split?{abis:['arm64-v8a','armeabi-v7a'],languages:[{code:'tr',label:'Türkçe'},{code:'en',label:'İngilizce'}]}:null}; prepareAnalysisView(analysis.filename,analysis.size,split); applyAnalysisResult({job_id:'fixture',analysis}); if(shouldScroll)document.querySelector('#analysisView').scrollIntoView(); }'''
            setup += '''function qaIconIdentity(){openInstalledApps();const images=[...document.querySelectorAll('.installed-app-icon')];const same=()=>images.every((image,i)=>image===document.querySelectorAll('.installed-app-icon')[i]);renderInstalledApps('Test uygulaması 2');renderInstalledApps();openInstalledApps();onInstalledPackagesLoaded(JSON.stringify(qaApps));const passed=images.length===100&&same();document.querySelector('#qaResult').textContent=passed?'PASS: 100 ikon düğümü korundu':'FAIL: ikon değişti';}'''
            capture_actions = {
                "apps": "setTimeout(()=>openInstalledApps(),900);",
                "analysis": "setTimeout(()=>qaAnalysis(true,false),1100);",
                "analysis-apk": "setTimeout(()=>qaAnalysis(true,false,false),1100);",
                "store-updates": "setTimeout(()=>{qaAnalysis(false,false,false);document.querySelector('#restrictStoreUpdates').closest('.option').scrollIntoView({block:'center'});},1100);",
                "messages": "setTimeout(()=>{qaAnalysis(true,false);setTimeout(()=>openMessageReview(),450);},900);",
                "working": "setTimeout(()=>{showView('#workingView');resetProgress();updateProgress(50,'Yerel işlem sürüyor');},1100);",
                "result": "setTimeout(()=>{qaAnalysis(true,false,false);runJob();},1100);",
                "failure": "setTimeout(()=>{qaAnalysis(true,false,false);runJob();},1100);",
            }
            capture_action = capture_actions.get(capture, "")
            html = html.replace('</body>', controls + '<script>const qaMarks=' + json.dumps(marks) + ';' + setup + 'renderNetworks({detections:qaMarks,network_count:18,dex_count:3});' + capture_action + '</script><script src="/qa-motion.js"></script></body>')
            self.reply(html, "text/html")
        elif path == "/qa-motion.js":
            self.reply((ROOT / "tests" / "ui_motion_probe.js").read_text(encoding="utf-8"), "text/javascript")
        elif path == "/api/status":
            self.reply(json.dumps(dict(toolchain=TOOLS, platform="android", clients=[], channel="dev", version="0.6.3-dev.3", engine_version="2.0")))
        elif path == "/api/history":
            self.reply('{"jobs":[]}')
        elif path == "/api/update":
            capture = parse_qs(urlsplit(self.headers.get("Referer", "")).query).get("capture", [""])[0]
            update = {
                "latest_version": "0.6.3-dev.2", "source": "github", "automatic": True,
                "install_mode": "android", "notes": "Yeni test sürümü kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz.",
                "release_notes": (ROOT / "RELEASE-NOTES-v0.6.3-dev.2.md").read_text(encoding="utf-8"),
                "release_url": "https://example.invalid/preview-only",
            }
            self.reply(json.dumps({"available": capture == "update", "update": update if capture == "update" else None}))
        elif path.endswith("/state"):
            self.reply(json.dumps({"status": "error", "message": "Çıktı doğrulanamadı: seçilen paketin native kütüphanesi eksik.",
                "failure": {"message": "Çıktı doğrulanamadı: seçilen paketin native kütüphanesi eksik.",
                            "stage": "Çıktı APK doğrulanıyor", "operation": "patch", "profile": "balanced"}}))
        elif path == "/api/storage":
            jobs = [
                {"job_id": f"{index:032x}", "filename": f"Örnek paket {index}.apk", "can_delete": False,
                 "sizes": {"source": 32_000_000, "output": 24_000_000, "working": 40_000_000}}
                for index in range(1, 6)
            ]
            self.reply(json.dumps({"jobs": jobs, "totals": {"source": 160_000_000, "output": 120_000_000, "working": 200_000_000}}))
        elif path.endswith('/diagnostic'):
            self.reply("APK Cleaner Studio · Örnek hata raporu\n\nAçıklama: Çıktı doğrulanamadı: seçilen paketin native kütüphanesi eksik.\nTemizlik profili: Dengeli\n\nBu yalnızca yerel önizleme verisidir.", "text/plain")
        elif path.endswith('/report'):
            self.reply("Görsel test raporu\nOrijinal paket korundu.\n" * 70, "text/plain")
        elif path.startswith('/api/'):
            self.reply('{}')
        else:
            super().do_GET()

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if urlsplit(self.path).path == "/api/clean":
            capture = parse_qs(urlsplit(self.headers.get("Referer", "")).query).get("capture", [""])[0]
            if capture in {"result", "store-updates"}:
                payload = json.loads(raw or b"{}")
                result = {"operation": payload.get("operation", "patch"), "output": "Ornek-sonuc.apk", "signed": True,
                    "source_size_bytes": 52_428_800, "output_size_bytes": 48_234_496, "duration_seconds": 74.2,
                    "cleaning_profile_applied": payload.get("profile", "balanced") if payload.get("patch_ads") else None,
                    "patches": {"void_patches": 14, "boolean_patches": 3, "debug_directives_removed": 28},
                    "manifest": {"count": 6}, "layouts": {"count": 2}, "removed_files": ["assets/example-ad.json"],
                    "verification": {"passed": True, "archive_crc": "ok", "manifest": "ok", "signature": "ok"}}
                if capture == "store-updates":
                    result.update(store_updates={"version_code_before": 42, "version_code_after": 2100000000,
                                  "version_code_major": 0, "changed": True} if payload.get("restrict_store_updates") else None,
                                  patches={"void_patches": 0, "boolean_patches": 0, "debug_directives_removed": 0},
                                  manifest={"count": 0}, layouts={"count": 0}, removed_files=[])
                self.reply(json.dumps({"status": "done", "result": result}))
            else:
                self.reply('{"status":"working"}')
        elif urlsplit(self.path).path.endswith("/message-candidates"):
            candidates = [dict(id="classes.dex:lc-fixture", dex="classes.dex", kind="Diyalog",
                owner_class="Lexample/MainActivity;", owner_method="onCreate", target_class="Lxpk8a;",
                target_method="StartGame", location="before_super", confidence="candidate", focus="priority", deferred=False,
                trace="Lxpk8a;->StartGame(Context)V > Landroid/app/AlertDialog;->show()V")]
            candidates.append(dict(candidates[0], id="classes.dex:lc-toast", kind="Toast", target_method="Start"))
            candidates.append(dict(candidates[0], id="classes.dex:lc-other", focus="other", confidence="review", target_method="init"))
            self.reply(json.dumps(dict(candidates=candidates, count=len(candidates))))
        else:
            self.send_error(404)

if __name__ == "__main__":
    print("UI fixture: http://127.0.0.1:18081/?embedded=android", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 18081), Handler).serve_forever()
