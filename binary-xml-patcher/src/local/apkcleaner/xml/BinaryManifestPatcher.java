package local.apkcleaner.xml;

import com.reandroid.arsc.chunk.xml.AndroidManifestBlock;
import com.reandroid.arsc.chunk.xml.ResXmlAttribute;
import com.reandroid.arsc.chunk.xml.ResXmlElement;
import com.reandroid.arsc.value.ValueType;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Removes selected advertising components directly from binary AndroidManifest.xml.
 *
 * The document is never converted to text and resources.arsc is never rebuilt. A
 * post-write audit verifies that every surviving resource reference keeps the
 * exact same type/data pair.
 */
public final class BinaryManifestPatcher {
    private static final Set<String> COMPONENT_TAGS = new LinkedHashSet<String>();
    private static final Set<String> PERMISSION_TAGS = new LinkedHashSet<String>();
    private static final String ANDROID_URI = "http://schemas.android.com/apk/res/android";

    static {
        Collections.addAll(COMPONENT_TAGS, "activity", "activity-alias", "service", "receiver", "provider");
        Collections.addAll(PERMISSION_TAGS, "uses-permission", "uses-permission-sdk-23");
    }

    private static final class Options {
        File input;
        File output;
        final List<String> prefixes = new ArrayList<String>();
        final List<String> metadata = new ArrayList<String>();
        final Set<String> permissions = new LinkedHashSet<String>();
        boolean inspectPackage;
        String clonePackage;
    }

    private BinaryManifestPatcher() {
    }

    public static void main(String[] args) throws Exception {
        Options options = parse(args);
        AndroidManifestBlock manifest = AndroidManifestBlock.load(options.input);
        String originalPackage = safe(manifest.getPackageName());
        if (originalPackage.isEmpty()) {
            throw new IllegalStateException("Manifest package name is missing");
        }
        if (options.inspectPackage) {
            System.out.println("PACKAGE\t" + originalPackage);
            return;
        }
        List<ResXmlElement> removals = new ArrayList<ResXmlElement>();
        List<String> descriptions = new ArrayList<String>();

        Iterator<ResXmlElement> iterator = manifest.recursiveElements();
        while (iterator.hasNext()) {
            ResXmlElement element = iterator.next();
            String tag = safe(element.getName());
            String name = safe(AndroidManifestBlock.getAndroidNameValue(element));
            boolean remove = false;
            if (COMPONENT_TAGS.contains(tag)) {
                remove = startsWithAny(name, options.prefixes);
            } else if ("meta-data".equals(tag)) {
                remove = startsWithAny(name, options.metadata);
            } else if (PERMISSION_TAGS.contains(tag)) {
                remove = options.permissions.contains(name);
            }
            if (remove) {
                removals.add(element);
                descriptions.add(tag + ": " + name);
            }
        }

        for (ResXmlElement element : removals) {
            if (!element.removeSelf()) {
                throw new IllegalStateException("Manifest element could not be removed: " + element.getName());
            }
        }

        List<String> cloneChanges = new ArrayList<String>();
        List<String> cloneWarnings = new ArrayList<String>();
        Map<String, String> authorityChanges = new HashMap<String, String>();
        if (options.clonePackage != null) {
            cloneManifest(manifest, originalPackage, options.clonePackage, cloneChanges, cloneWarnings, authorityChanges);
        }

        Map<String, Integer> referencesBefore = referenceMultiset(manifest);
        manifest.refreshFull();
        manifest.writeBytes(options.output);
        AndroidManifestBlock written = AndroidManifestBlock.load(options.output);
        Map<String, Integer> referencesAfter = referenceMultiset(written);
        if (!referencesBefore.equals(referencesAfter)) {
            throw new IllegalStateException("Surviving manifest resource references changed during binary write");
        }
        if (options.clonePackage != null && !options.clonePackage.equals(written.getPackageName())) {
            throw new IllegalStateException("Cloned package name was not retained in output manifest");
        }

        for (String description : descriptions) {
            System.out.println("REMOVED\t" + description);
        }
        for (String change : cloneChanges) {
            System.out.println("CLONE\t" + change);
        }
        for (String warning : cloneWarnings) {
            System.out.println("WARNING\t" + warning);
        }
        for (Map.Entry<String, String> entry : authorityChanges.entrySet()) {
            System.out.println("AUTHORITY\t" + entry.getKey() + "\t" + entry.getValue());
        }
        System.out.println("REFERENCES preserved=" + referencesAfter.size());
        System.out.println("RESULT removed=" + removals.size());
    }

    private static void cloneManifest(AndroidManifestBlock manifest, String originalPackage,
                                      String newPackage, List<String> changes, List<String> warnings,
                                      Map<String, String> authorityChanges) {
        if (!newPackage.matches("[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)+")
                || newPackage.length() > 200 || newPackage.equals(originalPackage)) {
            throw new IllegalArgumentException("Invalid or unchanged clone package name");
        }
        ResXmlElement root = manifest.getManifestElement();
        if (root == null) throw new IllegalStateException("Manifest root is missing");
        ResXmlAttribute sharedUser = androidAttribute(root, "sharedUserId");
        if (sharedUser != null && !safe(sharedUser.getValueAsString()).isEmpty()) {
            throw new IllegalStateException("sharedUserId packages cannot be cloned safely");
        }

        Iterator<ResXmlElement> iterator = manifest.recursiveElements();
        while (iterator.hasNext()) {
            ResXmlElement element = iterator.next();
            String tag = safe(element.getName());
            boolean component = COMPONENT_TAGS.contains(tag) || "application".equals(tag)
                    || "instrumentation".equals(tag);
            if (component) {
                qualifyClassAttribute(element, "name", originalPackage, changes);
            }
            if ("activity".equals(tag) || "activity-alias".equals(tag)) {
                qualifyClassAttribute(element, "parentActivityName", originalPackage, changes);
            }
            if ("activity-alias".equals(tag)) {
                qualifyClassAttribute(element, "targetActivity", originalPackage, changes);
            }
            if ("application".equals(tag)) {
                for (String name : new String[]{"backupAgent", "appComponentFactory", "manageSpaceActivity", "zygotePreloadName"}) {
                    qualifyClassAttribute(element, name, originalPackage, changes);
                }
            }
            if ("provider".equals(tag)) {
                ResXmlAttribute authorities = androidAttribute(element, "authorities");
                if (authorities != null) {
                    if (authorities.getValueType() != ValueType.STRING) {
                        throw new IllegalStateException("Resource-based provider authorities cannot be cloned safely");
                    }
                    String before = safe(authorities.getValueAsString());
                    if (!before.isEmpty()) {
                        String[] values = before.split(";", -1);
                        for (int i = 0; i < values.length; i++) {
                            String authority = values[i].trim();
                            if (authority.isEmpty()) continue;
                            if (authority.equals(originalPackage) || authority.startsWith(originalPackage + ".")) {
                                values[i] = newPackage + authority.substring(originalPackage.length());
                            } else {
                                values[i] = authority + "." + newPackage;
                                warnings.add("Custom provider authority changed; hard-coded lookups may fail: " + authority);
                            }
                            if (!authority.equals(values[i])) authorityChanges.put(authority, values[i]);
                        }
                        String after = String.join(";", values);
                        if (!before.equals(after)) {
                            authorities.setValueAsString(after);
                            changes.add("provider authorities: " + before + " -> " + after);
                        }
                    }
                }
            }
            if (PERMISSION_TAGS.contains(tag) || "permission".equals(tag)
                    || "permission-group".equals(tag) || "permission-tree".equals(tag)) {
                replaceOwnNamespace(element, "name", originalPackage, newPackage, changes);
            }
            if (component) {
                for (String name : new String[]{"permission", "readPermission", "writePermission"}) {
                    replaceOwnNamespace(element, name, originalPackage, newPackage, changes);
                }
                replaceOwnNamespace(element, "process", originalPackage, newPackage, changes);
                replaceOwnNamespace(element, "taskAffinity", originalPackage, newPackage, changes);
            }
            if ("instrumentation".equals(tag)) {
                replaceOwnNamespace(element, "targetPackage", originalPackage, newPackage, changes);
            }
        }
        manifest.setPackageName(newPackage);
        changes.add("package: " + originalPackage + " -> " + newPackage);
    }

    private static ResXmlAttribute androidAttribute(ResXmlElement element, String name) {
        Iterator<ResXmlAttribute> attributes = element.getAttributes();
        while (attributes.hasNext()) {
            ResXmlAttribute attribute = attributes.next();
            if (name.equals(attribute.getName()) && ANDROID_URI.equals(attribute.getUri())) return attribute;
        }
        return null;
    }

    private static void qualifyClassAttribute(ResXmlElement element, String name, String originalPackage,
                                              List<String> changes) {
        ResXmlAttribute attribute = androidAttribute(element, name);
        if (attribute == null || attribute.getValueType() != ValueType.STRING) return;
        String before = safe(attribute.getValueAsString());
        if (before.isEmpty()) return;
        String after = before.startsWith(".") ? originalPackage + before
                : before.indexOf('.') < 0 ? originalPackage + "." + before : before;
        if (!before.equals(after)) {
            attribute.setValueAsString(after);
            changes.add(element.getName() + " " + name + ": " + before + " -> " + after);
        }
    }

    private static void replaceOwnNamespace(ResXmlElement element, String name, String originalPackage,
                                            String newPackage, List<String> changes) {
        ResXmlAttribute attribute = androidAttribute(element, name);
        if (attribute == null || attribute.getValueType() != ValueType.STRING) return;
        String before = safe(attribute.getValueAsString());
        if (!before.equals(originalPackage) && !before.startsWith(originalPackage + ".")) return;
        String after = newPackage + before.substring(originalPackage.length());
        attribute.setValueAsString(after);
        changes.add(element.getName() + " " + name + ": " + before + " -> " + after);
    }

    private static Map<String, Integer> referenceMultiset(AndroidManifestBlock manifest) {
        Map<String, Integer> result = new HashMap<String, Integer>();
        Iterator<ResXmlElement> elements = manifest.recursiveElements();
        while (elements.hasNext()) {
            Iterator<ResXmlAttribute> attributes = elements.next().getAttributes();
            while (attributes.hasNext()) {
                ResXmlAttribute attribute = attributes.next();
                ValueType type = attribute.getValueType();
                if (type != ValueType.REFERENCE && type != ValueType.DYNAMIC_REFERENCE
                        && type != ValueType.ATTRIBUTE && type != ValueType.DYNAMIC_ATTRIBUTE) {
                    continue;
                }
                String key = attribute.getNameId() + ":" + type.name() + ":" + attribute.getData();
                Integer count = result.get(key);
                result.put(key, count == null ? 1 : count + 1);
            }
        }
        return result;
    }

    private static boolean startsWithAny(String value, List<String> prefixes) {
        if (value.isEmpty()) {
            return false;
        }
        for (String prefix : prefixes) {
            if (!prefix.isEmpty() && value.startsWith(prefix)) {
                return true;
            }
        }
        return false;
    }

    private static String safe(String value) {
        return value == null ? "" : value;
    }

    private static Options parse(String[] args) {
        Options options = new Options();
        for (int i = 0; i < args.length; i++) {
            String arg = args[i];
            if ("--input".equals(arg)) {
                options.input = new File(requireValue(args, ++i, arg));
            } else if ("--output".equals(arg)) {
                options.output = new File(requireValue(args, ++i, arg));
            } else if ("--prefix".equals(arg)) {
                options.prefixes.add(requireValue(args, ++i, arg));
            } else if ("--metadata".equals(arg)) {
                options.metadata.add(requireValue(args, ++i, arg));
            } else if ("--permission".equals(arg)) {
                options.permissions.add(requireValue(args, ++i, arg));
            } else if ("--inspect-package".equals(arg)) {
                options.inspectPackage = true;
            } else if ("--clone-package".equals(arg)) {
                options.clonePackage = requireValue(args, ++i, arg);
            } else {
                throw new IllegalArgumentException("Unknown argument: " + arg);
            }
        }
        if (options.input == null || (!options.inspectPackage && options.output == null)) {
            throw new IllegalArgumentException("--input and --output are required unless inspecting package");
        }
        if (options.inspectPackage && options.clonePackage != null) {
            throw new IllegalArgumentException("Package inspection and cloning cannot be combined");
        }
        return options;
    }

    private static String requireValue(String[] args, int index, String argument) {
        if (index >= args.length) {
            throw new IllegalArgumentException("Missing value for " + argument);
        }
        return args[index];
    }
}
