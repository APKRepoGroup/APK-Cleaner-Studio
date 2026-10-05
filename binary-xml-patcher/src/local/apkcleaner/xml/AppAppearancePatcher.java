package local.apkcleaner.xml;

import com.reandroid.arsc.chunk.TableBlock;
import com.reandroid.arsc.chunk.PackageBlock;
import com.reandroid.arsc.chunk.xml.AndroidManifestBlock;
import com.reandroid.arsc.chunk.xml.ResXmlElement;
import com.reandroid.arsc.chunk.xml.ResXmlAttribute;
import com.reandroid.arsc.value.Entry;
import com.reandroid.arsc.value.ValueType;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;

/** Opt-in launcher presentation only. Existing resource IDs/values are retained. */
public final class AppAppearancePatcher {
    private static final String NS = "http://schemas.android.com/apk/res/android";

    public static void main(String[] args) throws Exception {
        Map<String, String> options = new HashMap<String, String>();
        for (int i = 0; i < args.length; i += 2) {
            if (i + 1 >= args.length) throw new IllegalArgumentException("Eksik görünüm seçeneği.");
            options.put(args[i], args[i + 1]);
        }
        AndroidManifestBlock manifest = AndroidManifestBlock.load(new File(options.get("--input")));
        String name = options.containsKey("--label-file")
                ? new String(Files.readAllBytes(new File(options.get("--label-file")).toPath()), StandardCharsets.UTF_8) : null;
        String iconPath = options.get("--icon-path");
        List<ResXmlElement> targets = targets(manifest);
        if (targets.isEmpty()) throw new IllegalStateException("Uygulama görünüm kaydı bulunamadı.");
        int iconId = 0;
        if (iconPath != null) {
            TableBlock table = TableBlock.load(new File(options.get("--table")));
            Map<String, String> original = snapshot(table);
            PackageBlock pkg = table.getPackageBlockById(manifest.guessCurrentPackageId());
            if (pkg == null && table.size() == 1) pkg = table.get(0);
            if (pkg == null) throw new IllegalStateException("Simge için kaynak paketi belirlenemedi.");
            String key = new File(iconPath).getName().replace(".png", "");
            if (pkg.getResource("drawable", key) != null) throw new IllegalStateException("Simge kaynak adı çakışıyor.");
            Entry entry = pkg.getOrCreate("", "drawable", key);
            entry.setValueAsString(iconPath);
            iconId = entry.getResourceId();
            table.refreshFull();
            File out = new File(options.get("--table-output"));
            table.writeBytes(out);
            TableBlock written = TableBlock.load(out);
            Map<String, String> after = snapshot(written);
            for (Map.Entry<String, String> item : original.entrySet()) {
                if (!item.getValue().equals(after.get(item.getKey())))
                    throw new IllegalStateException("Mevcut kaynak değeri değişti; görünüm işlemi durduruldu.");
            }
            Iterator<Entry> added = written.getEntries(iconId);
            if (!added.hasNext() || !iconPath.equals(added.next().getValueAsString()))
                throw new IllegalStateException("Yeni simge kaynak kaydı doğrulanamadı.");
        }
        for (ResXmlElement target : targets) {
            if (name != null) target.getOrCreateAndroidAttribute("label", 0x01010001).setValueAsString(name);
            if (iconId != 0) {
                ResXmlAttribute icon = target.getOrCreateAndroidAttribute("icon", 0x01010002);
                icon.setValueType(ValueType.REFERENCE); icon.setData(iconId);
                // roundIcon is application-only. Launcher activities/aliases use icon.
                if ("application".equals(target.getName())) {
                    ResXmlAttribute round = target.getOrCreateAndroidAttribute("roundIcon", 0x0101052c);
                    round.setValueType(ValueType.REFERENCE); round.setData(iconId);
                }
            }
        }
        String packageName = manifest.getPackageName(), versionName = manifest.getVersionName();
        Integer versionCode = manifest.getVersionCode();
        manifest.refreshFull();
        File output = new File(options.get("--output"));
        manifest.writeBytes(output);
        AndroidManifestBlock written = AndroidManifestBlock.load(output);
        if (!Objects.equals(packageName, written.getPackageName()) || !Objects.equals(versionName, written.getVersionName())
                || !Objects.equals(versionCode, written.getVersionCode()))
            throw new IllegalStateException("Paket kimliği veya sürüm bilgisi değişti.");
        for (ResXmlElement target : targets(written)) {
            if (name != null && !name.equals(target.searchAttribute(NS, "label").getValueAsString()))
                throw new IllegalStateException("Uygulama adı doğrulanamadı.");
            if (iconId != 0 && target.searchAttribute(NS, "icon").getData() != iconId)
                throw new IllegalStateException("Uygulama simgesi doğrulanamadı.");
        }
        System.out.println("APPEARANCE\t" + targets.size() + "\t" + iconId);
    }

    private static List<ResXmlElement> targets(AndroidManifestBlock manifest) {
        List<ResXmlElement> result = new ArrayList<ResXmlElement>();
        ResXmlElement app = manifest.getApplicationElement();
        if (app == null) return result;
        result.add(app);
        Iterator<ResXmlElement> elements = app.getElements();
        while (elements.hasNext()) {
            ResXmlElement element = elements.next();
            if (!"activity".equals(element.getName()) && !"activity-alias".equals(element.getName())) continue;
            Iterator<ResXmlElement> filters = element.getElements("intent-filter");
            while (filters.hasNext()) {
                ResXmlElement filter = filters.next();
                boolean main = false, launcher = false;
                Iterator<ResXmlElement> children = filter.getElements();
                while (children.hasNext()) {
                    ResXmlElement child = children.next();
                    String value = AndroidManifestBlock.getAndroidNameValue(child);
                    main |= "action".equals(child.getName()) && "android.intent.action.MAIN".equals(value);
                    launcher |= "category".equals(child.getName()) && ("android.intent.category.LAUNCHER".equals(value)
                            || "android.intent.category.LEANBACK_LAUNCHER".equals(value));
                }
                if (main && launcher) { result.add(element); break; }
            }
        }
        return result;
    }

    private static Map<String, String> snapshot(TableBlock table) {
        Map<String, String> result = new HashMap<String, String>();
        for (PackageBlock pkg : table) {
            Iterator<com.reandroid.arsc.model.ResourceEntry> resources = pkg.getResources();
            while (resources.hasNext()) {
                com.reandroid.arsc.model.ResourceEntry resource = resources.next();
                Iterator<Entry> entries = table.getEntries(resource.getResourceId());
                while (entries.hasNext()) {
                    Entry entry = entries.next();
                    result.put(entry.getResourceId() + ":" + entry.getResConfig(), entry.toJson().toString());
                }
            }
        }
        return result;
    }
}
