"""Local-only UI fixture; never included in a release or connected to real jobs."""
import json
import base64
import time
import xml.etree.ElementTree as ET
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "studio" / "web"
PROFILES = json.loads((ROOT / "studio" / "profiles.json").read_text(encoding="utf-8"))
TOOLS = dict.fromkeys(("java", "dex_tools", "manifest_tool", "split_tool", "signer", "zipalign", "resource_tool", "fully_ready"), True)
VERSION = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]


def capture_mode(url):
    capture = parse_qs(urlsplit(url).query).get("capture", [""])[0]
    return {"dev6-working": "dev5", "dev6-apps": "apps", "dev6-share": "result"}.get(capture, capture)

class Handler(SimpleHTTPRequestHandler):
    preview_jobs = {}
    history_time = time.time()

    @classmethod
    def preview_history(cls):
        names = ("Günlük Notlar", "Şehir Haritası", "Müzik Çalar", "Dosya Yöneticisi", "Fotoğraf Galerisi", "Takvim")
        statuses = ("done", "error", "cancelled", "ready", "done", "error")
        return [dict(job_id=f"d5a0{index:028x}", filename=f"{names[index % 6]}_{index + 1}.apk",
                     app_name="Eski Arşiv" if index == 35 else names[index % 6],
                     package_name=f"com.preview.app{index}", updated_at=cls.history_time - index * 7200,
                     status=statuses[index % 6], interrupted=index == 5, can_reuse=False, can_delete=False,
                     has_report=False, has_output=False) for index in range(48)]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def reply(self, body, content_type="application/json", status=200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        request_url = urlsplit(self.path)
        path = request_url.path
        if path == "/":
            capture = capture_mode(self.path)
            if capture in {"dev6-mobile", "dev6-desktop"}:
                embedded = "embedded=android&" if capture == "dev6-mobile" else ""
                width = "390px" if capture == "dev6-mobile" else "100%"
                self.reply(f'''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dev.6 test ekranı</title>
                <style>html,body{{height:100%;margin:0}}body{{height:100dvh;display:flex;flex-direction:column;overflow:hidden;background:#0d1515;color:#e8efea;font:14px system-ui}}header{{padding:8px 12px;text-align:center}}nav{{display:flex;flex-wrap:wrap;justify-content:center;gap:6px 16px}}a{{color:#d9ff43;font-size:12px}}small{{display:block;color:#a9b6b0;font-size:11px;margin-top:5px}}iframe{{display:block;flex:1;min-height:0;box-sizing:border-box;width:min({width},100%);margin:0 auto;border:1px solid #34493f;border-radius:14px}}</style></head><body>
                <header><nav><a href="/?{embedded}capture=dev6-working" target="preview">İşlem ekranı</a><a href="/?embedded=android&capture=dev6-apps" target="preview">Uygulama listesi</a><a href="/?embedded=android&capture=dev6-share" target="preview">Paylaşım</a></nav><small>Dev.6 · Örnek veriler. Android simge üretimi ve sistem paylaşımı cihaz testi gerektirir.</small></header>
                <iframe name="preview" title="Dev.6 önizleme" src="/?{embedded}capture=dev6-working"></iframe></body></html>''', "text/html")
                return
            if capture == "dev5-splash":
                theme = parse_qs(request_url.query).get("theme", ["light"])[0]
                theme = "dark" if theme == "dark" else "light"
                folder = "values-night" if theme == "dark" else "values"
                palette = ET.parse(ROOT / "android/app/src/main/res" / folder / "colors.xml").getroot()
                html = (ROOT / "tests/splash_preview.html").read_text(encoding="utf-8")
                for item in palette:
                    html = html.replace("{{" + item.get("name") + "}}", item.text or "")
                self.reply(html.replace("{{theme}}", theme), "text/html")
                return
            if capture in {"dev5-mobile", "dev5-desktop"}:
                embedded = "embedded=android&" if capture == "dev5-mobile" else ""
                width = "390px" if capture == "dev5-mobile" else "100%"
                self.reply(f'''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dev.5 önizleme</title>
                <style>html,body{{height:100%;margin:0}}body{{height:100dvh;display:flex;flex-direction:column;overflow:hidden;background:#0d1515;color:#e8efea;font:14px system-ui}}header{{flex:0 0 auto;box-sizing:border-box;max-height:36dvh;overflow:auto;padding:8px 12px;text-align:center}}nav{{display:flex;flex-wrap:wrap;justify-content:center;align-items:center;gap:4px 12px}}a{{display:inline-block;color:#d9ff43;font-size:12px;line-height:1.5;margin:0}}iframe{{display:block;flex:1 1 0;min-height:0;box-sizing:border-box;width:min({width},100%);margin:0 auto;border:1px solid #34493f;border-radius:14px}}small{{display:block;font-size:11px;line-height:1.4;color:#a9b6b0;margin-top:4px}}</style></head><body>
                <header><nav aria-label="Test senaryoları"><a href="/?{embedded}capture=dev5" target="preview">İşlem / iptal onayı</a><a href="/?{embedded}capture=dev5-analysis" target="preview">Analiz / simge</a><a href="/?{embedded}capture=dev5-battery" target="preview">Pil uyarısı</a><a href="/?{embedded}capture=dev5-recovery" target="preview">Yenileyerek işleme dön</a><a href="/?{embedded}capture=dev5-interrupted" target="preview">Kesilen işlem</a><a href="/?{embedded}capture=dev5-space-warning" target="preview">Az boş alan</a><a href="/?{embedded}capture=dev5-space-blocked" target="preview">Dolu depolama</a><a href="/?{embedded}capture=dev5-connection" target="preview">Bağlantı kesilmesi / geri gelmesi</a><a href="/?{embedded}capture=dev5-history" target="preview">Geçmiş / arama</a><a href="/?{embedded}capture=dev5-stop" target="preview">Motoru durdurma onayı</a></nav><small>Dev.5 · Örnek veriler; gerçek paket işlenmez, cihaz ayarları değiştirilmez.</small></header>
                <iframe name="preview" title="Dev.5 test ekranı" src="/?{embedded}capture=dev5"></iframe></body></html>''', "text/html")
                return
            if capture == "mobile-result":
                self.reply('''<!doctype html><html lang="tr"><head><meta charset="utf-8"><title>Mobil sonuç önizlemesi</title>
                <style>body{margin:0;background:#151b19;display:flex;justify-content:center}
                iframe{width:390px;height:1800px;border:0;background:#0d1515}</style></head>
                <body><iframe title="Mobil sonuç" src="/?embedded=android&amp;capture=result"></iframe></body></html>''', "text/html")
                return
            html = (WEB / "index.html").read_text(encoding="utf-8")
            marks = [dict(id=key, label=value["label"], references=4313 - i * 199) for i, (key, value) in enumerate(PROFILES.items())]
            bridge = '''<script>const qaApps=Array.from({length:100},(_,i)=>({package:'com.example.app'+i,label:'Test uygulaması '+(i+1),version:'1.2.0',splits:i%3,icon:'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><rect width="48" height="48" rx="12" fill="#239b84"/><circle cx="24" cy="24" r="12" fill="#d9ff43"/></svg>')})); globalThis.AndroidThemeBridge={setTheme(){},requestInstalledPackages(){onInstalledPackagesLoaded(JSON.stringify(qaApps));}};</script>'''
            bridge = bridge.replace("</script>", '''let qaBatteryUnrestricted=false;AndroidThemeBridge.requestBackgroundPolicy=()=>{if(new URLSearchParams(location.search).get('capture')==='dev5-battery')globalThis.onBackgroundPolicy?.({known:true,backgroundRestricted:!qaBatteryUnrestricted,ignoringOptimizations:qaBatteryUnrestricted});};AndroidThemeBridge.openBatterySettings=()=>toast('Tarayıcı önizlemesi cihaz ayarlarını değiştirmez.');AndroidThemeBridge.requestBatteryExemption=()=>toast('Android uygulamasında sistem onayı açılır. Bu tarayıcı önizlemesi cihaz ayarlarını değiştirmez.');</script>''')
            bridge = bridge.replace("</script>", '''AndroidThemeBridge.resolveEngineStop=(token,approved)=>toast(approved?'Önizleme: onay alındı; gerçek motor kapatılmadı.':'Önizleme: motor çalışmaya devam eder.');</script>''')
            bridge = bridge.replace("</script>", '''AndroidThemeBridge.shareOutput=(url,filename)=>{globalThis.qaSharedName=filename;toast('Paylaşılacak dosya: '+filename);globalThis.onNativeAction?.('share',JSON.stringify({status:'opened'}));};</script>''')
            # Fixture pointers must not attach to unrelated demos; never clear real job pointers.
            bridge = bridge.replace("</script>", '''for(const storage of [localStorage,sessionStorage]){const key='apk-cleaner-active-job-v1';try{const record=JSON.parse(storage.getItem(key)||'null');const capture=new URLSearchParams(location.search).get('capture');const prefix=capture==='dev5-recovery'?'f1f1f1f1':capture==='dev5-interrupted'?'f2f2f2f2':'';if(/^f[12]f[12]f[12]f[12]/.test(record?.jobId||'')&&!record.jobId.startsWith(prefix||'not-a-fixture'))storage.removeItem(key);}catch{}}</script>''')
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
            <button onclick="qaWorking();document.querySelector('#workingView').scrollIntoView()">QA İlerleme</button>
            <button onclick="qaAnalysis(true,false,false);runJob();">QA Sonuç</button>
            <button onclick="setNativeVisibility(false)">QA Arka plan</button>
            <button onclick="setNativeVisibility(true)">QA Ön plan</button>
            <button onclick="applyTheme('light')">QA Açık</button><button onclick="applyTheme('dark')">QA Koyu</button>
            </nav>'''
            if capture == "dev5-battery":
                controls = ""
            if capture in {"analysis", "analysis-apk", "selection-summary", "result", "comparison", "failure", "store-updates", "dev5-analysis"}:
                html = html.replace(
                    "</head>",
                    "<style>.hero,#mobileHttpsBanner,.starter-content,footer{display:none!important}.workspace{margin-top:24px!important}</style></head>",
                    1,
                )
            elif capture in {"working", "working-long", "working-split", "dev5"}:
                html = html.replace(
                    "</head>",
                    "<style>.hero,#mobileHttpsBanner,footer{display:none!important}.workspace{margin-top:24px!important}</style></head>",
                    1,
                )
            html = html.replace('<script src="ui-runtime.js', bridge + '<script src="ui-runtime.js', 1)
            html = html.replace("v0.6.3-dev.4</b>", "v" + VERSION + "</b>")
            qa_icon = "data:image/png;base64," + base64.b64encode((WEB / "favicon.png").read_bytes()).decode("ascii")
            setup = 'const qaAppIcon=' + json.dumps(qa_icon) + ';const qaSelection=' + json.dumps(self.preview_selection()) + ';'
            setup += '''function qaAnalysis(ads,shouldScroll=true,split=true) { const analysis={filename:split?'Görsel test.apks':'Görsel test.apk',package_name:'com.example.visualtest',package_info:{app_name:'Görsel Test',version_name:'1.4.2',min_sdk:26,target_sdk:37,abis:['arm64-v8a','armeabi-v7a'],signature_schemes:['V2','V3'],permissions:['android.permission.INTERNET','android.permission.POST_NOTIFICATIONS']},app_icon:qaAppIcon,size:10240,dex_count:3,network_count:ads?18:0,detections:ads?qaMarks:[],split_merged:split,split_options:split?{abis:['arm64-v8a','armeabi-v7a'],languages:[{code:'tr',label:'Türkçe'},{code:'en',label:'İngilizce'}]}:null}; prepareAnalysisView(analysis.filename,analysis.size,split); applyAnalysisResult({job_id:'fixture',analysis}); if(shouldScroll)document.querySelector('#analysisView').scrollIntoView(); }'''
            setup += '''function qaWorking(longName=false,split=false){qaAnalysis(true,false,split);state.analysis.dex_count=10;if(longName){state.analysis.filename='Çok uzun uygulama adı ve paket dosyası ile mobil görünüm testi 2026.apk';state.analysis.package_name='com.example.verylongapplicationpackagename.withadditionalsegments.preview';}setStep(3);showView('#workingView');resetProgress();const messages=['Yerel işlem motoru hazırlanıyor','DEX dosyaları hazırlanıyor',...Array.from({length:9},(_,i)=>`${i?'classes'+(i+1):'classes'}.dex işlendi (${i+1}/10) · ${i===2?'Değişiklik gerekmedi':(i+2)+' reklam yaması'}`)];const events=messages.map((message,i)=>({id:i+1,message,elapsed_seconds:i*3.2}));updateProgress(53,events.at(-1).message,events);}'''
            setup += '''function qaDev5Working(){qaWorking();state.jobId='preview-'+Date.now()+'-'+Math.floor(Math.random()*10000);setJobRunning(true);const jobId=state.jobId;async function tick(){if(state.jobId!==jobId||!state.jobRunning)return;const response=await fetch('/api/jobs/'+jobId+'/state');const data=await response.json();if(data.status==='cancelled'){setJobRunning(false);const error=new Error('İşlem isteğin üzerine iptal edildi.');error.jobStatus='cancelled';renderJobFailure(error);setStep(2);showView('#analysisView');return;}updateProgress(data.progress,data.message,data.events);setTimeout(tick,1400);}tick();}'''
            setup += '''function qaRecovery(interrupted=false){if(state.jobRunning||state.sessionRestoreInFlight||state.analysis)return;const prefix=interrupted?'f2f2f2f2':'f1f1f1f1';const id=rememberedActiveJob()||prefix+crypto.randomUUID().replaceAll('-','').slice(0,24);rememberActiveJob(id);restoreJobSession(id);}'''
            setup += '''const originalQaWorking=qaWorking;qaWorking=(...args)=>{originalQaWorking(...args);state.jobSelection={...qaSelection,operation:'patch',split_selection:null,clone_package_name:null};renderWorkingSelection(state.jobSelection);};'''
            setup += '''function qaIconIdentity(){openInstalledApps();const images=[...document.querySelectorAll('.installed-app-icon')];const same=()=>images.every((image,i)=>image===document.querySelectorAll('.installed-app-icon')[i]);renderInstalledApps('Test uygulaması 2');renderInstalledApps();openInstalledApps();onInstalledPackagesLoaded(JSON.stringify(qaApps));const passed=images.length===100&&same();document.querySelector('#qaResult').textContent=passed?'PASS: 100 ikon düğümü korundu':'FAIL: ikon değişti';}'''
            capture_actions = {
                "dev5": "setTimeout(qaDev5Working,700);",
                "dev5-analysis": "setTimeout(()=>qaAnalysis(true,false,false),700);",
                "dev5-battery": "setTimeout(()=>AndroidThemeBridge.requestBackgroundPolicy(),700);",
                "dev5-history": "setTimeout(()=>document.querySelector('#historyCard').scrollIntoView({block:'center'}),700);",
                "dev5-history-filter": "setTimeout(()=>{document.querySelector('#historyCard').scrollIntoView({block:'center'});openHistoryStatus();},700);",
                "dev5-thanks": "setTimeout(()=>document.querySelector('#specialThanks').scrollIntoView({block:'center'}),700);",
                "dev5-stop": "setTimeout(()=>onEngineStopRequested('preview-stop-token'),700);",
                "dev5-recovery": "setTimeout(()=>qaRecovery(),700);",
                "dev5-connection": "setTimeout(()=>qaRecovery(),700);",
                "dev5-interrupted": "setTimeout(()=>qaRecovery(true),700);",
                "dev5-space-warning": "setTimeout(()=>qaAnalysis(true,false,false),700);",
                "dev5-space-blocked": "setTimeout(()=>qaAnalysis(true,false,false),700);",
                "apps": "setTimeout(()=>openInstalledApps(),900);",
                "analysis": "setTimeout(()=>qaAnalysis(true,false),1100);",
                "analysis-apk": "setTimeout(()=>qaAnalysis(true,false,false),1100);",
                "appearance": "setTimeout(()=>{qaAnalysis(false,false,false);setInlineDisclosureOpen(document.querySelector('#appAppearance'),true);document.querySelector('#appAppearance').scrollIntoView({block:'start'});},1100);",
                "compatibility": "setTimeout(()=>{qaAnalysis(true,false,true);setInlineDisclosureOpen(document.querySelector('#packageInfo'),true);document.querySelector('#packageInfo').scrollIntoView({block:'start'});},1100);",
                "selection-summary": "setTimeout(()=>{qaAnalysis(true,false);document.querySelector('#selectionSummary').scrollIntoView({block:'center'});},1100);",
                "store-updates": "setTimeout(()=>{qaAnalysis(false,false,false);document.querySelector('#restrictStoreUpdates').closest('.option').scrollIntoView({block:'center'});},1100);",
                "messages": "setTimeout(()=>{qaAnalysis(true,false);setTimeout(()=>openMessageReview(),450);},900);",
                "working": "setTimeout(()=>qaWorking(),1100);",
                "working-long": "setTimeout(()=>qaWorking(true),1100);",
                "working-split": "setTimeout(()=>qaWorking(false,true),1100);",
                "result": "setTimeout(()=>{qaAnalysis(true,false,false);runJob();},1100);",
                "comparison": "setTimeout(()=>{qaAnalysis(true,false,false);setOperation('clone');document.querySelector('#clonePackageName').value='com.example.visualtest.clone';document.querySelector('#restrictStoreUpdates').checked=true;runJob();},1100);",
                "failure": "setTimeout(()=>{qaAnalysis(true,false,false);runJob();},1100);",
            }
            capture_action = capture_actions.get(capture, "")
            html = html.replace('</body>', controls + '<script>const qaMarks=' + json.dumps(marks) + ';' + setup + 'renderNetworks({detections:qaMarks,network_count:18,dex_count:3});' + capture_action + '</script><script src="/qa-motion.js"></script></body>')
            self.reply(html, "text/html")
        elif path == "/qa-motion.js":
            self.reply((ROOT / "tests" / "ui_motion_probe.js").read_text(encoding="utf-8"), "text/javascript")
        elif path == "/api/status":
            self.reply(json.dumps(dict(toolchain=TOOLS, platform="android", clients=[], channel="dev", version=VERSION, engine_version="2.0")))
        elif path == "/api/history":
            capture = capture_mode(self.headers.get("Referer", ""))
            rows = self.preview_history() if capture in {"dev5-history", "dev5-history-filter"} else []
            query = parse_qs(request_url.query)
            search = query.get("q", [""])[0].casefold().replace("i\u0307", "i").replace("ı", "i")
            status = query.get("status", ["all"])[0]
            rows = [row for row in rows if (not search or any(search in row[key].casefold().replace("i\u0307", "i").replace("ı", "i") for key in ("filename", "app_name", "package_name")))
                    and (status == "all" or row["status"] == status or status == "interrupted" and row["interrupted"])]
            total = len(rows)
            offset = min(max(0, int(query.get("offset", ["0"])[0])), ((total - 1) // 20) * 20) if total else 0
            self.reply(json.dumps({"jobs": rows[offset:offset + 20], "total": total, "offset": offset, "limit": 20, "has_more": offset + 20 < total}))
        elif path == "/api/update":
            capture = capture_mode(self.headers.get("Referer", ""))
            update = {
                "latest_version": "0.6.3-dev.2", "source": "github", "automatic": True,
                "install_mode": "android", "notes": "Yeni test sürümü kullanıma hazır. Güncelleme notlarına aşağıdan ulaşabilirsiniz.",
                "release_notes": (ROOT / "RELEASE-NOTES-v0.6.3-dev.2.md").read_text(encoding="utf-8"),
                "release_url": "https://example.invalid/preview-only",
            }
            self.reply(json.dumps({"available": capture == "update", "update": update if capture == "update" else None}))
        elif path.endswith("/preflight"):
            capture = capture_mode(self.headers.get("Referer", ""))
            status = "blocked" if capture == "dev5-space-blocked" else "warning" if capture == "dev5-space-warning" else "ok"
            messages = {"blocked": "İşlem alanı kritik düzeyde dolu. Depolama Yönetimi'nden yer açıp yeniden deneyin.",
                        "warning": "Boş alan, tahmini çalışma alanından düşük. İşlem sırasında depolama hatası oluşabilir; önce yer açmanız önerilir.",
                        "ok": "Şu anki boş alan, tahmini çalışma alanını karşılıyor."}
            self.reply(json.dumps({"status": status, "estimated": True, "message": messages[status],
                                  "free_bytes": {"blocked": 8_000_000, "warning": 70_000_000, "ok": 9_000_000_000}[status],
                                  "recommended_bytes": 320_000_000}))
        elif path.endswith("/session"):
            job_id = path.split("/")[-2]
            analysis = {"filename": "Görsel test.apk", "size": 10240, "package_name": "com.example.visualtest",
                        "app_icon": "data:image/png;base64," + base64.b64encode((WEB / "favicon.png").read_bytes()).decode("ascii"),
                        "dex_count": 120, "network_count": 18, "detections": [], "split_merged": False}
            job_state = self.preview_state(job_id)
            if job_id.startswith("f2f2f2f2"):
                job_state = {"status": "error", "interrupted": True, "progress": 0,
                             "message": "Yerel motorun kapanması nedeniyle işlem yarıda kaldı. Kaynak paket korundu; işlemi yeniden başlatabilirsin.",
                             "failure": {"stage": "DEX dosyaları işleniyor", "operation": "patch", "profile": "balanced"}}
            self.reply(json.dumps({"job_id": job_id, "analysis": analysis, "job": job_state, "selection": self.preview_selection()}))
        elif path.endswith("/state"):
            job_id = path.split("/")[-2]
            if job_id.startswith(("preview-", "f1f1f1f1")):
                capture = capture_mode(self.headers.get("Referer", ""))
                age = time.monotonic() - self.preview_jobs.get(job_id, {}).get("start", time.monotonic())
                if capture == "dev5-connection" and 2 <= age < 9:
                    self.reply('{"error":"Örnek bağlantı kesintisi"}', status=503)
                    return
                self.reply(json.dumps(self.preview_state(job_id)))
                return
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

    @staticmethod
    def preview_selection():
        return {"schema": 1, "operation": "clone", "profile": "deep", "patch_ads": True,
                "strip_debug": True, "normalize_dex": False, "optimize_apk": True,
                "restrict_store_updates": True, "deobfuscate_resources": False,
                "clone_package_name": "com.example.visualtest.clone", "message_targets": [],
                "split_selection": None, "app_appearance": {"name": "Görsel Test Klon"}}

    def preview_state(self, job_id):
        if len(self.preview_jobs) > 128:
            self.preview_jobs.pop(next(iter(self.preview_jobs)))
        job = self.preview_jobs.setdefault(job_id, {"start": time.monotonic(), "cancelled": False})
        count = min(100, 18 + int((time.monotonic() - job["start"]) / 2))
        events = [{"id": i + 1, "elapsed_seconds": i * 2,
                   "message": "Yerel işlem motoru hazırlanıyor" if i == 0 else f"classes{i}.dex işlendi ({i}/120) · {i % 7 + 12} reklam yaması"} for i in range(count)]
        return {"status": "cancelled" if job["cancelled"] else "working", "progress": min(90, 53 + count - 18), "events": events, "message": events[-1]["message"]}

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        request_path = urlsplit(self.path).path
        if request_path.startswith(("/api/jobs/preview-", "/api/jobs/f1f1f1f1")) and request_path.endswith("/cancel"):
            job_id = request_path.split("/")[-2]
            job = self.preview_jobs.get(job_id)
            if job:
                job["cancelled"] = True
            self.reply('{"status":"cancelling"}')
            return
        if urlsplit(self.path).path == "/api/clean":
            capture = capture_mode(self.headers.get("Referer", ""))
            if capture in {"", "result", "comparison", "store-updates", "appearance", "compatibility", "dev5-space-warning", "dev5-space-blocked"}:
                payload = json.loads(raw or b"{}")
                result = {"operation": payload.get("operation", "patch"), "output": "Görsel Test_1.4.2-processed.apk", "signed": True,
                    "source_size_bytes": 52_428_800, "output_size_bytes": 48_234_496, "duration_seconds": 74.2,
                    "cleaning_profile_applied": payload.get("profile", "balanced") if payload.get("patch_ads") else None,
                    "patches": {"void_patches": 14, "boolean_patches": 3, "debug_directives_removed": 28},
                    "manifest": {"count": 6}, "layouts": {"count": 2}, "removed_files": ["assets/example-ad.json"],
                    "verification": {"passed": True, "archive_crc": "ok", "manifest": "ok", "signature": "ok"}}
                result["split_merged"] = bool(payload.get("split_selection"))
                appearance = payload.get("app_appearance") or {}
                if appearance.get("name") or appearance.get("icon"):
                    result["app_appearance"] = {"name": appearance.get("name") or None, "icon_changed": bool(appearance.get("icon"))}
                result["identity_comparison"] = {
                    "before": {"package_name": "com.example.visualtest", "version_code": "42"},
                    "after": {"package_name": payload.get("clone_package_name") or "com.example.visualtest",
                              "version_code": "2100000000" if payload.get("restrict_store_updates") else "42"},
                }
                if payload.get("operation") == "clone":
                    result["clone"] = {"original_package": "com.example.visualtest", "new_package": payload.get("clone_package_name"),
                                       "dex_strings_changed": 12, "changes": ["package"]}
                if payload.get("restrict_store_updates"):
                    result["store_updates"] = {"version_code_before": 42, "version_code_after": 2100000000,
                                               "version_code_major": 0, "changed": True}
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
