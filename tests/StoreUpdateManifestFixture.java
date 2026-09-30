import com.reandroid.arsc.chunk.xml.AndroidManifestBlock;
import com.reandroid.arsc.chunk.xml.ResXmlAttribute;
import java.io.File;

/** Synthetic binary AXML, built with the same library used by production. */
public final class StoreUpdateManifestFixture {
    public static void main(String[] args) throws Exception {
        File path = new File(args[1]);
        if ("read".equals(args[0])) {
            AndroidManifestBlock block = AndroidManifestBlock.load(path);
            System.out.println(block.getPackageName() + "\t" + block.getVersionName());
            return;
        }
        AndroidManifestBlock block = new AndroidManifestBlock();
        block.setPackageName("com.example.fixture");
        block.setVersionName("1.2.3");
        if (!"missing".equals(args[2])) {
            block.setVersionCode(Integer.parseInt(args[3]));
            ResXmlAttribute code = block.getManifestElement().getOrCreateAndroidAttribute("versionCode", 16843291);
            if ("string".equals(args[2])) code.setValueAsString("123");
            if ("reference".equals(args[2])) code.setValueAsResourceId(0x7f010001);
            if ("hex".equals(args[2])) code.setValueAsHex(Integer.parseInt(args[3]));
        }
        // android.R.attr.versionCodeMajor from the local Android SDK.
        block.getManifestElement().getOrCreateAndroidAttribute("versionCodeMajor", 16844150)
                .setValueAsDecimal(Integer.parseInt(args[4]));
        block.getOrCreateApplicationElement().getOrCreateAndroidAttribute("label", 16842753)
                .setValueAsResourceId(0x7f020001);
        block.getOrCreateActivity("com.google.android.gms.ads.AdActivity", false);
        block.refreshFull();
        block.writeBytes(path);
    }
}
