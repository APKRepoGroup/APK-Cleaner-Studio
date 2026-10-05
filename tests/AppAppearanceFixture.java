import com.reandroid.arsc.chunk.TableBlock;
import com.reandroid.arsc.chunk.PackageBlock;
import com.reandroid.arsc.chunk.xml.AndroidManifestBlock;
import com.reandroid.arsc.chunk.xml.ResXmlElement;
import java.io.File;

public final class AppAppearanceFixture {
    public static void main(String[] args) throws Exception {
        File manifestFile = new File(args[1]), tableFile = new File(args[2]);
        if ("read".equals(args[0])) {
            AndroidManifestBlock m = AndroidManifestBlock.load(manifestFile);
            TableBlock t = TableBlock.load(tableFile);
            System.out.println(m.getPackageName() + "\t" + m.getVersionCode() + "\t" + m.getVersionName()
                + "\t" + m.getApplicationLabelString() + "\t" + m.getIconResourceId() + "\t" + m.getRoundIconResourceId());
            System.out.println(t.get(0).getEntry("string", "original_title").getValueAsString());
            System.out.println(t.get(0).getEntry("drawable", "original_icon").getValueAsString());
            System.out.println(m.getMainActivity().searchAttribute("http://schemas.android.com/apk/res/android", "label").getValueAsString());
            return;
        }
        TableBlock t = new TableBlock();
        PackageBlock pkg = t.newPackage(0x7f, "com.example.fixture");
        int titleId = pkg.getOrCreate("", "string", "original_title").setValueAsString("Original title").getEntry().getResourceId();
        com.reandroid.arsc.value.Entry icon = pkg.getOrCreate("", "drawable", "original_icon");
        icon.setValueAsString("res/drawable/original.png");
        pkg.getOrCreate("tr", "string", "original_title").setValueAsString("Özgün ad");
        pkg.getOrCreate("", "string", "reference").setValueAsReference(titleId);
        t.refreshFull(); t.writeBytes(tableFile);
        AndroidManifestBlock m = new AndroidManifestBlock();
        m.setPackageName("com.example.fixture"); m.setVersionCode(42); m.setVersionName("1.2.3");
        m.setMinSdkVersion(26); m.setTargetSdkVersion(37); m.setApplicationLabel(titleId); m.setIconResourceId(icon.getResourceId());
        ResXmlElement activity = m.getOrCreateMainActivity("com.example.fixture.MainActivity");
        activity.getOrCreateAndroidAttribute("label", 0x01010001).setValueAsString("Launcher title");
        ResXmlElement alias = m.getApplicationElement().newElement("activity-alias");
        alias.getOrCreateAndroidAttribute("name", 0x01010003).setValueAsString("com.example.fixture.Alias");
        alias.getOrCreateAndroidAttribute("targetActivity", 0x01010202).setValueAsString("com.example.fixture.MainActivity");
        ResXmlElement filter = alias.newElement("intent-filter");
        filter.newElement("action").getOrCreateAndroidAttribute("name", 0x01010003).setValueAsString("android.intent.action.MAIN");
        filter.newElement("category").getOrCreateAndroidAttribute("name", 0x01010003).setValueAsString("android.intent.category.LAUNCHER");
        m.addUsesPermission("android.permission.INTERNET");
        m.refreshFull(); m.writeBytes(manifestFile);
    }
}
