package local.apkcleaner.dex;

import com.android.tools.smali.dexlib2.DexFileFactory;
import com.android.tools.smali.dexlib2.Opcode;
import com.android.tools.smali.dexlib2.Opcodes;
import com.android.tools.smali.dexlib2.dexbacked.DexBackedDexFile;
import com.android.tools.smali.dexlib2.dexbacked.instruction.DexBackedInstruction;
import com.android.tools.smali.dexlib2.iface.ClassDef;
import com.android.tools.smali.dexlib2.iface.DexFile;
import com.android.tools.smali.dexlib2.iface.Method;
import com.android.tools.smali.dexlib2.iface.MethodImplementation;
import com.android.tools.smali.dexlib2.iface.debug.DebugItem;
import com.android.tools.smali.dexlib2.iface.instruction.Instruction;
import com.android.tools.smali.dexlib2.iface.instruction.OneRegisterInstruction;
import com.android.tools.smali.dexlib2.iface.instruction.ReferenceInstruction;
import com.android.tools.smali.dexlib2.iface.reference.StringReference;
import com.android.tools.smali.dexlib2.iface.reference.MethodReference;
import com.android.tools.smali.dexlib2.immutable.ImmutableMethodImplementation;
import com.android.tools.smali.dexlib2.immutable.instruction.ImmutableInstruction21c;
import com.android.tools.smali.dexlib2.immutable.instruction.ImmutableInstruction31c;
import com.android.tools.smali.dexlib2.immutable.reference.ImmutableStringReference;
import com.android.tools.smali.dexlib2.rewriter.DexRewriter;
import com.android.tools.smali.dexlib2.rewriter.InstructionRewriter;
import com.android.tools.smali.dexlib2.rewriter.MethodImplementationRewriter;
import com.android.tools.smali.dexlib2.rewriter.Rewriter;
import com.android.tools.smali.dexlib2.rewriter.RewriterModule;
import com.android.tools.smali.dexlib2.rewriter.Rewriters;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.EnumSet;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.HashSet;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.zip.Adler32;

/**
 * Direct DEX instruction patcher. It never emits or parses Smali text.
 *
 * Target invoke instructions are replaced with the same number of Dalvik code
 * units, so branch targets, try blocks and debug code addresses remain stable.
 */
public final class DirectDexPatcher {
    private static final Pattern VOID_METHODS = Pattern.compile(
        "^(?:initialize|init|loadAds?|showAds?|loadAd|showAd|show|load|requestAd|" +
        "request(?:Interstitial|Banner|Native|Rewarded)(?:Ad)?|" +
        "(?:load|show)(?:Interstitial|Rewarded|RewardedVideo|Banner|Native|AppOpen|Mediation)(?:Ad)?|" +
        "preloadAd|fetchAds?|cacheAd|startAd|openAd|displayAd|presentAd|" +
        "showFullScreenAd|showFullscreenAd|loadAdViewAd|" +
        "(?:create|setup|prepare|attach|add|inflate|refresh|resume|pause|destroy)(?:Adaptive)?Banner(?:Ad|View)?|" +
        "(?:load|show|request|refresh)(?:Adaptive|Collapsible|AnchoredAdaptive|InlineAdaptive)?Banner(?:Ad)?|" +
        "loadAdManagerAd|loadPublisherAd|setAdSize|setAdUnitId|" +
        "setNativeAd|setAd|setAdView|bindAd|renderAd|populateAd|attachAd|" +
        "setBannerAd|setNativeAdView|renderNativeAd|bindNativeAd)$",
        Pattern.CASE_INSENSITIVE
    );
    private static final Pattern DEEP_AD_CLASS = Pattern.compile(
        "(?:^|[/.$])[^/;$]*(?:AdView|AdManagerAdView|PublisherAdView|AdLoader|AdSize|" +
        "Banner|NativeAd|NativeAdView|Mrec|MRec|Interstitial|Rewarded|AppOpen|" +
        "MobileAds|MediationBanner|MediationNative)[^/;$]*;?$",
        Pattern.CASE_INSENSITIVE
    );
    private static final Pattern BOOL_METHODS = Pattern.compile(
        "^(?:isReady|isLoaded|canShow|canShowAd|hasAd|isAdReady|isAdLoaded|isAdAvailable|isAvailable)$",
        Pattern.CASE_INSENSITIVE
    );
    private static final Pattern AD_LOADED_CALLBACKS = Pattern.compile(
        "^(?:onAdLoaded|onAdsLoaded|onNativeAdLoaded|onBannerAdLoaded|" +
        "onInterstitialAdLoaded|onRewardedAdLoaded|onAdReceived|onAdAvailable|onAdDisplayed)$",
        Pattern.CASE_INSENSITIVE
    );
    private static final Set<Opcode> TARGET_INVOKES = EnumSet.of(
        Opcode.INVOKE_STATIC,
        Opcode.INVOKE_STATIC_RANGE,
        Opcode.INVOKE_DIRECT,
        Opcode.INVOKE_DIRECT_RANGE,
        Opcode.INVOKE_VIRTUAL,
        Opcode.INVOKE_VIRTUAL_RANGE,
        Opcode.INVOKE_INTERFACE,
        Opcode.INVOKE_INTERFACE_RANGE
    );

    private DirectDexPatcher() {}

    private static final class Options {
        Path input;
        Path output;
        String mode = "balanced";
        boolean stripDebug;
        boolean normalizeDex;
        boolean listMessages;
        final List<String> descriptors = new ArrayList<>();
        final Set<String> messageTargets = new HashSet<>();
        final Set<String> startupTargets = new HashSet<>();
        final Map<String, String> cloneStrings = new LinkedHashMap<>();
    }

    private static final class Stats {
        int voidPatches;
        int booleanPatches;
        int callbackPatches;
        int debugItemsRemoved;
        int messagePatches;
        int cloneStringsChanged;
        boolean changed;
        final List<String> riskyCalls = new ArrayList<>();
        final List<String> messageCalls = new ArrayList<>();
    }

    public static void main(String[] args) throws Exception {
        // Structured scan output contains obfuscated Unicode identifiers.
        // Do not let a Windows console code page replace them with question marks.
        System.out.write(execute(args).getBytes(java.nio.charset.StandardCharsets.UTF_8));
        System.out.flush();
    }

    /** In-process Android çağrılarında global System.out yakalamadan çalışır. */
    public static String execute(String[] args) throws Exception {
        if (args.length > 0 && "--scan-startup".equals(args[0])) return StartupMessageScanner.execute(args);
        Options options = parseArgs(args);
        Stats stats = new Stats();
        byte[] dexBytes = Files.readAllBytes(options.input);
        DexBackedDexFile inputDex = new DexBackedDexFile(Opcodes.getDefault(), dexBytes);
        patchInstructionsInPlace(inputDex, dexBytes, options, stats);
        if (!options.cloneStrings.isEmpty()) {
            for (ClassDef cls : inputDex.getClasses()) {
                for (Method method : cls.getMethods()) {
                    MethodImplementation impl = method.getImplementation();
                    if (impl == null) continue;
                    for (Instruction instruction : impl.getInstructions()) {
                        if ((instruction.getOpcode() == Opcode.CONST_STRING || instruction.getOpcode() == Opcode.CONST_STRING_JUMBO)
                            && instruction instanceof ReferenceInstruction
                            && ((ReferenceInstruction) instruction).getReference() instanceof StringReference
                            && options.cloneStrings.containsKey(((StringReference) ((ReferenceInstruction) instruction).getReference()).getString())) {
                            stats.cloneStringsChanged++;
                        }
                    }
                }
            }
            if (stats.cloneStringsChanged > 0) stats.changed = true;
        }
        if (!options.startupTargets.isEmpty()) throw new IllegalArgumentException("Seçilen başlangıç çağrısı artık eşleşmiyor; paketi yeniden tara.");

        Files.createDirectories(options.output.toAbsolutePath().getParent());
        if (options.stripDebug || options.normalizeDex || stats.cloneStringsChanged > 0 || dexVersion(dexBytes) >= 41) {
            writeWithDebugRewrite(dexBytes, options, stats);
        } else {
            refreshDexHeader(dexBytes);
            Files.write(options.output, dexBytes);
        }

        StringBuilder output = new StringBuilder();
        for (String risky : stats.riskyCalls) output.append("RISKY\t").append(risky).append('\n');
        for (String message : stats.messageCalls) output.append("MESSAGE\t").append(message).append('\n');
        output.append(String.format(
            "RESULT changed_files=%d void_patches=%d boolean_patches=%d callback_patches=%d message_patches=%d debug_directives_removed=%d clone_strings_changed=%d%n",
            stats.changed ? 1 : 0,
            stats.voidPatches,
            stats.booleanPatches,
            stats.callbackPatches,
            stats.messagePatches,
            stats.debugItemsRemoved,
            stats.cloneStringsChanged
        ));
        return output.toString();
    }

    private static void patchInstructionsInPlace(
        DexBackedDexFile dexFile,
        byte[] dexBytes,
        Options options,
        Stats stats
    ) {
        Short const4Value = dexFile.getOpcodes().getOpcodeValue(Opcode.CONST_4);
        if (const4Value == null) {
            throw new IllegalStateException("DEX opcode tablosunda CONST_4 bulunamadı.");
        }
        Short returnVoidValue = dexFile.getOpcodes().getOpcodeValue(Opcode.RETURN_VOID);
        if (returnVoidValue == null) {
            throw new IllegalStateException("DEX opcode tablosunda RETURN_VOID bulunamadı.");
        }
        Short goto16Value = dexFile.getOpcodes().getOpcodeValue(Opcode.GOTO_16);
        Short goto32Value = dexFile.getOpcodes().getOpcodeValue(Opcode.GOTO_32);
        if (goto16Value == null || goto32Value == null) {
            throw new IllegalStateException("DEX opcode tablosunda geçiş komutları bulunamadı.");
        }
        for (ClassDef classDef : dexFile.getClasses()) {
            for (Method method : classDef.getMethods()) {
                MethodImplementation implementation = method.getImplementation();
                if (implementation == null) {
                    continue;
                }
                List<Instruction> instructions = new ArrayList<>();
                for (Instruction instruction : implementation.getInstructions()) {
                    instructions.add(instruction);
                }
                if ("deep".equals(options.mode)
                    && "V".equals(method.getReturnType())
                    && AD_LOADED_CALLBACKS.matcher(method.getName()).matches()
                    && isVerifiedAdCallback(classDef, method, options.descriptors)
                    && writeImmediateReturn(dexBytes, instructions, returnVoidValue)) {
                    stats.callbackPatches++;
                    stats.changed = true;
                    continue;
                }
                for (int index = 0; index < instructions.size(); index++) {
                    Instruction instruction = instructions.get(index);
                    if (!options.startupTargets.isEmpty() && StartupMessageScanner.lifecycle(method)
                        && instruction instanceof DexBackedInstruction && instruction instanceof ReferenceInstruction) {
                        Object ref = ((ReferenceInstruction) instruction).getReference();
                        if (ref instanceof MethodReference && StartupMessageScanner.rootCall(instruction, (MethodReference) ref)
                            && StartupMessageScanner.unusedResult(instructions, index)) {
                            String identity = startupIdentity(classDef, method, (MethodReference) ref, instruction);
                            if (options.startupTargets.remove(identity)) {
                                writeNeutralizedInstruction(dexBytes, (DexBackedInstruction) instruction, goto16Value, goto32Value);
                                stats.messagePatches++; stats.changed = true;
                                continue;
                            }
                        }
                    }
                    if (instruction instanceof DexBackedInstruction) {
                        MethodReference messageReference = messageReference(instruction, instructions, index);
                        if (messageReference != null) {
                            String identity = messageIdentity(classDef, method, messageReference, (DexBackedInstruction) instruction);
                            String kind = messageKind(messageReference);
                            if (options.listMessages) {
                                stats.messageCalls.add(
                                    identity + "\t" + kind + "\t" + classDef.getType() + "\t" +
                                    method.getName() + "\t" + messageReference.getDefiningClass() + "\t" +
                                    messageReference.getName() + "\t" + messageContext(instructions, index) + "\t" +
                                    messageReference.getParameterTypes() + messageReference.getReturnType()
                                );
                            }
                            if (options.messageTargets.contains(identity)
                                && patchMessageCall(dexBytes, instructions, index, const4Value, goto16Value, goto32Value)) {
                                stats.messagePatches++;
                                stats.changed = true;
                                if (!"V".equals(messageReference.getReturnType())
                                    && index + 1 < instructions.size()
                                    && (instructions.get(index + 1).getOpcode() == Opcode.MOVE_RESULT_OBJECT
                                        || instructions.get(index + 1).getOpcode() == Opcode.MOVE_RESULT)) {
                                    index++;
                                }
                                continue;
                            }
                        }
                    }
                    MethodReference reference = targetReference(instruction, options.descriptors);
                    if (reference == null || !(instruction instanceof DexBackedInstruction)) {
                        continue;
                    }

                    String methodName = reference.getName();
                    String returnType = reference.getReturnType();
                    boolean namedAdOperation = VOID_METHODS.matcher(methodName).matches();
                    boolean deepSdkOperation = "deep".equals(options.mode)
                        && !"<init>".equals(methodName)
                        && !"<clinit>".equals(methodName)
                        && DEEP_AD_CLASS.matcher(reference.getDefiningClass()).find();
                    if ("V".equals(returnType) && (namedAdOperation || deepSdkOperation)) {
                        writeNeutralizedInstruction(dexBytes, (DexBackedInstruction) instruction, goto16Value, goto32Value);
                        stats.voidPatches++;
                        stats.changed = true;
                        continue;
                    }

                    if (("balanced".equals(options.mode) || "deep".equals(options.mode))
                        && "Z".equals(returnType)
                        && BOOL_METHODS.matcher(methodName).matches()
                        && index + 1 < instructions.size()
                        && instructions.get(index + 1).getOpcode() == Opcode.MOVE_RESULT
                        && instructions.get(index + 1) instanceof OneRegisterInstruction
                        && instructions.get(index + 1) instanceof DexBackedInstruction) {
                        OneRegisterInstruction moveResult = (OneRegisterInstruction) instructions.get(index + 1);
                        if (moveResult.getRegisterA() <= 15) {
                            writeNeutralizedInstruction(dexBytes, (DexBackedInstruction) instruction, goto16Value, goto32Value);
                            writeConst4(
                                dexBytes,
                                (DexBackedInstruction) instructions.get(index + 1),
                                const4Value,
                                moveResult.getRegisterA()
                            );
                            index++;
                            stats.booleanPatches++;
                            stats.changed = true;
                            continue;
                        }
                    }

                    if (stats.riskyCalls.size() < 1000) {
                        stats.riskyCalls.add(
                            reference.getDefiningClass() + "->" + methodName + "(...)" + returnType
                        );
                    }
                }
            }
        }
    }

    private static boolean isVerifiedAdCallback(
        ClassDef classDef,
        Method method,
        List<String> descriptors
    ) {
        if (matchesDescriptor(classDef.getSuperclass(), descriptors)) {
            return true;
        }
        for (String interfaceName : classDef.getInterfaces()) {
            if (matchesDescriptor(interfaceName, descriptors)) {
                return true;
            }
        }
        for (CharSequence parameter : method.getParameterTypes()) {
            if (matchesDescriptor(parameter == null ? null : parameter.toString(), descriptors)) {
                return true;
            }
        }
        return false;
    }

    private static boolean matchesDescriptor(String type, List<String> descriptors) {
        if (type == null) {
            return false;
        }
        String normalized = type.startsWith("L") ? type.substring(1) : type;
        if (normalized.endsWith(";")) {
            normalized = normalized.substring(0, normalized.length() - 1);
        }
        for (String descriptor : descriptors) {
            if (normalized.startsWith(descriptor)) {
                return true;
            }
        }
        return false;
    }

    private static boolean writeImmediateReturn(
        byte[] dexBytes,
        List<Instruction> instructions,
        short returnVoidValue
    ) {
        if (instructions.isEmpty()
            || !(instructions.get(0) instanceof DexBackedInstruction)
            || !(instructions.get(instructions.size() - 1) instanceof DexBackedInstruction)) {
            return false;
        }
        DexBackedInstruction first = (DexBackedInstruction) instructions.get(0);
        int start = first.instructionStart;
        int end = start + first.getCodeUnits() * 2;
        Arrays.fill(dexBytes, start, end, (byte) 0);
        dexBytes[start] = (byte) (returnVoidValue & 0xff);
        dexBytes[start + 1] = 0;
        return true;
    }

    private static void writeWithDebugRewrite(byte[] dexBytes, Options options, Stats stats) throws Exception {
        DexFile inputDex = new DexBackedDexFile(Opcodes.getDefault(), dexBytes);
        RewriterModule module = new RewriterModule() {
            @Override
            public Rewriter<MethodImplementation> getMethodImplementationRewriter(Rewriters rewriters) {
                return new MethodImplementationRewriter(rewriters) {
                    @Override
                    public MethodImplementation rewrite(MethodImplementation implementation) {
                        return super.rewrite(rewriteDebugItems(implementation, options, stats));
                    }
                };
            }
            @Override
            public Rewriter<Instruction> getInstructionRewriter(Rewriters rewriters) {
                return new InstructionRewriter(rewriters) {
                    @Override
                    public Instruction rewrite(Instruction instruction) {
                        if ((instruction.getOpcode() == Opcode.CONST_STRING || instruction.getOpcode() == Opcode.CONST_STRING_JUMBO)
                            && instruction instanceof ReferenceInstruction
                            && ((ReferenceInstruction) instruction).getReference() instanceof StringReference) {
                            String original = ((StringReference) ((ReferenceInstruction) instruction).getReference()).getString();
                            String replacement = options.cloneStrings.get(original);
                            if (replacement != null && instruction instanceof OneRegisterInstruction) {
                                int register = ((OneRegisterInstruction) instruction).getRegisterA();
                                ImmutableStringReference reference = new ImmutableStringReference(replacement);
                                return instruction.getOpcode() == Opcode.CONST_STRING
                                    ? new ImmutableInstruction21c(Opcode.CONST_STRING, register, reference)
                                    : new ImmutableInstruction31c(Opcode.CONST_STRING_JUMBO, register, reference);
                            }
                        }
                        return super.rewrite(instruction);
                    }
                };
            }
        };
        DexFile outputDex = new DexRewriter(module).getDexFileRewriter().rewrite(inputDex);
        DexFileFactory.writeDexFile(options.output.toString(), outputDex);
    }

    private static MethodImplementation rewriteDebugItems(
        MethodImplementation implementation,
        Options options,
        Stats stats
    ) {
        if (implementation == null) {
            return null;
        }
        List<DebugItem> debugItems = new ArrayList<>();
        for (DebugItem item : implementation.getDebugItems()) {
            debugItems.add(item);
        }
        if (!options.stripDebug || debugItems.isEmpty()) {
            return implementation;
        }
        stats.debugItemsRemoved += debugItems.size();
        stats.changed = true;
        return new ImmutableMethodImplementation(
            implementation.getRegisterCount(),
            implementation.getInstructions(),
            implementation.getTryBlocks(),
            Collections.<DebugItem>emptyList()
        );
    }

    private static MethodReference targetReference(Instruction instruction, List<String> descriptors) {
        if (!TARGET_INVOKES.contains(instruction.getOpcode())
            || !(instruction instanceof ReferenceInstruction)) {
            return null;
        }
        ReferenceInstruction referenceInstruction = (ReferenceInstruction) instruction;
        if (!(referenceInstruction.getReference() instanceof MethodReference)) {
            return null;
        }
        MethodReference methodReference = (MethodReference) referenceInstruction.getReference();
        String definingClass = methodReference.getDefiningClass();
        String normalized = definingClass.startsWith("L") ? definingClass.substring(1) : definingClass;
        if (normalized.endsWith(";")) {
            normalized = normalized.substring(0, normalized.length() - 1);
        }
        for (String descriptor : descriptors) {
            if (normalized.startsWith(descriptor)) {
                return methodReference;
            }
        }
        return null;
    }

    private static MethodReference messageReference(
        Instruction instruction,
        List<Instruction> instructions,
        int index
    ) {
        if (!TARGET_INVOKES.contains(instruction.getOpcode()) || !(instruction instanceof ReferenceInstruction)) {
            return null;
        }
        Object rawReference = ((ReferenceInstruction) instruction).getReference();
        if (!(rawReference instanceof MethodReference)) {
            return null;
        }
        MethodReference reference = (MethodReference) rawReference;
        return messageKind(reference) == null || !messageCallPatchable(reference, instructions, index)
            ? null : reference;
    }

    private static String messageKind(MethodReference reference) {
        String method = reference.getName();
        String lowerMethod = method.toLowerCase();
        String owner = reference.getDefiningClass();
        if (("show".equals(method) || "showToast".equals(method))
            && ("Landroid/widget/Toast;".equals(owner)
                || owner.contains("Toast") || owner.contains("Toasty") || owner.contains("Crouton"))) {
            return "Toast";
        }
        if ((lowerMethod.equals("toast") || lowerMethod.startsWith("showtoast")
                || lowerMethod.startsWith("displaytoast")) && "V".equals(reference.getReturnType())) {
            return "Toast";
        }
        if (("show".equals(method) || "showSnackbar".equals(method)) && owner.contains("Snackbar")) {
            return "Snackbar";
        }
        if ((lowerMethod.equals("snackbar") || lowerMethod.startsWith("showsnackbar")
                || lowerMethod.startsWith("displaysnackbar")) && "V".equals(reference.getReturnType())) {
            return "Snackbar";
        }
        boolean dialogOwner = owner.endsWith("Dialog;")
            || owner.contains("AlertDialog")
            || owner.contains("DialogFragment")
            || owner.contains("BottomSheetDialog")
            || owner.contains("MaterialAlertDialog")
            || owner.contains("PopupWindow")
            || owner.contains("SweetAlert")
            || owner.contains("compose/ui/window/Dialog");
        boolean dialogMethod = "show".equals(method)
            || "showNow".equals(method)
            || "showAllowingStateLoss".equals(method)
            || "showAtLocation".equals(method)
            || "showAsDropDown".equals(method)
            || "showDialog".equals(method)
            || "displayDialog".equals(method)
            || ("Dialog".equals(method) && owner.contains("compose/ui/window"));
        boolean namedDialogHelper = (lowerMethod.startsWith("show")
                || lowerMethod.startsWith("display")
                || lowerMethod.startsWith("open")
                || lowerMethod.startsWith("present"))
            && (lowerMethod.contains("dialog") || lowerMethod.contains("popup"));
        boolean dialogFragmentSignature = "show".equals(method)
            && reference.getParameterTypes().toString().contains("FragmentManager");
        if ((dialogOwner && dialogMethod)
            || "showDialog".equals(method)
            || "displayDialog".equals(method)
            || namedDialogHelper
            || dialogFragmentSignature) {
            return "Diyalog";
        }
        boolean namedMessageHelper = (lowerMethod.startsWith("show") || lowerMethod.startsWith("display"))
            && (lowerMethod.contains("message") || lowerMethod.contains("notice")
                || lowerMethod.contains("warning") || lowerMethod.contains("announcement"))
            && "V".equals(reference.getReturnType());
        if (namedMessageHelper) return "Mesaj";
        return null;
    }

    /**
     * Stable, offset-independent fingerprint around a message call. Rebuilt mod
     * APKs often move instruction addresses, while the surrounding operations
     * of an original call remain the same. This lets the host match original
     * occurrences before presenting only genuinely added calls.
     */
    private static String messageContext(List<Instruction> instructions, int center) {
        StringBuilder raw = new StringBuilder();
        int start = Math.max(0, center - 4);
        int end = Math.min(instructions.size() - 1, center + 4);
        for (int index = start; index <= end; index++) {
            if (index == center) continue;
            Instruction instruction = instructions.get(index);
            raw.append(index < center ? '<' : '>').append(instruction.getOpcode().name());
            if (instruction instanceof ReferenceInstruction) {
                raw.append(':').append(String.valueOf(((ReferenceInstruction) instruction).getReference()));
            }
            raw.append('|');
        }
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(raw.toString().getBytes("UTF-8"));
            StringBuilder value = new StringBuilder();
            for (int index = 0; index < 12; index++) value.append(String.format("%02x", digest[index]));
            return value.toString();
        } catch (Exception error) {
            throw new IllegalStateException("Mesaj bağlamı üretilemedi.", error);
        }
    }

    private static boolean messageCallPatchable(
        MethodReference reference,
        List<Instruction> instructions,
        int index
    ) {
        String returnType = reference.getReturnType();
        if ("V".equals(returnType)) return true;
        if ("J".equals(returnType) || "D".equals(returnType)) return false;
        if (index + 1 >= instructions.size()) {
            return true;
        }
        Instruction move = instructions.get(index + 1);
        boolean expectedMove = (returnType.startsWith("L") || returnType.startsWith("["))
            ? move.getOpcode() == Opcode.MOVE_RESULT_OBJECT
            : move.getOpcode() == Opcode.MOVE_RESULT;
        if (!expectedMove) return true;
        return move instanceof OneRegisterInstruction
            && move instanceof DexBackedInstruction
            && ((OneRegisterInstruction) move).getRegisterA() <= 15;
    }

    private static boolean patchMessageCall(
        byte[] dexBytes,
        List<Instruction> instructions,
        int index,
        short const4Value,
        short goto16Value,
        short goto32Value
    ) {
        Instruction instruction = instructions.get(index);
        if (!(instruction instanceof DexBackedInstruction)) return false;
        MethodReference reference = messageReference(instruction, instructions, index);
        if (reference == null) return false;
        writeNeutralizedInstruction(dexBytes, (DexBackedInstruction) instruction, goto16Value, goto32Value);
        if (!"V".equals(reference.getReturnType()) && index + 1 < instructions.size()) {
            Instruction move = instructions.get(index + 1);
            boolean moveResult = move.getOpcode() == Opcode.MOVE_RESULT_OBJECT || move.getOpcode() == Opcode.MOVE_RESULT;
            if (!moveResult) return true;
            if (!(move instanceof OneRegisterInstruction) || !(move instanceof DexBackedInstruction)) return false;
            writeConst4(
                dexBytes,
                (DexBackedInstruction) move,
                const4Value,
                ((OneRegisterInstruction) move).getRegisterA()
            );
        }
        return true;
    }

    private static String messageIdentity(
        ClassDef classDef,
        Method method,
        MethodReference target,
        DexBackedInstruction instruction
    ) {
        String raw = classDef.getType() + "->" + method.getName() + method.getParameterTypes() +
            method.getReturnType() + "|" + target.getDefiningClass() + "->" + target.getName() +
            target.getParameterTypes() + target.getReturnType() + "|" + instruction.instructionStart;
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(raw.getBytes("UTF-8"));
            StringBuilder value = new StringBuilder();
            for (int index = 0; index < 12; index++) value.append(String.format("%02x", digest[index]));
            return value.toString();
        } catch (Exception error) {
            throw new IllegalStateException("Mesaj çağrısı kimliği üretilemedi.", error);
        }
    }

    static String startupIdentity(ClassDef cls, Method owner, MethodReference target, Instruction instruction) {
        return "lc-" + messageIdentity(cls, owner, target, (DexBackedInstruction) instruction);
    }

    private static void writeNeutralizedInstruction(
        byte[] dexBytes,
        DexBackedInstruction instruction,
        short goto16Value,
        short goto32Value
    ) {
        int start = instruction.instructionStart;
        int codeUnits = instruction.getCodeUnits();
        int end = start + codeUnits * 2;
        Arrays.fill(dexBytes, start, end, (byte) 0);
        if (codeUnits == 2) {
            dexBytes[start] = (byte) (goto16Value & 0xff);
            dexBytes[start + 2] = 2;
        } else if (codeUnits == 3) {
            dexBytes[start] = (byte) (goto32Value & 0xff);
            dexBytes[start + 2] = 3;
        }
    }

    private static void writeConst4(
        byte[] dexBytes,
        DexBackedInstruction instruction,
        short opcodeValue,
        int register
    ) {
        int start = instruction.instructionStart;
        dexBytes[start] = (byte) (opcodeValue & 0xff);
        dexBytes[start + 1] = (byte) (register & 0x0f);
    }

    private static int dexVersion(byte[] dexBytes) {
        if (dexBytes.length < 8 || dexBytes[0] != 'd' || dexBytes[1] != 'e' || dexBytes[2] != 'x') {
            return Integer.MAX_VALUE;
        }
        return (dexBytes[4] - '0') * 100 + (dexBytes[5] - '0') * 10 + (dexBytes[6] - '0');
    }

    private static void refreshDexHeader(byte[] dexBytes) throws Exception {
        MessageDigest sha1 = MessageDigest.getInstance("SHA-1");
        sha1.update(dexBytes, 32, dexBytes.length - 32);
        byte[] signature = sha1.digest();
        System.arraycopy(signature, 0, dexBytes, 12, signature.length);

        Adler32 adler32 = new Adler32();
        adler32.update(dexBytes, 12, dexBytes.length - 12);
        long checksum = adler32.getValue();
        dexBytes[8] = (byte) checksum;
        dexBytes[9] = (byte) (checksum >>> 8);
        dexBytes[10] = (byte) (checksum >>> 16);
        dexBytes[11] = (byte) (checksum >>> 24);
    }

    private static Options parseArgs(String[] args) {
        Options options = new Options();
        for (int index = 0; index < args.length; index++) {
            String argument = args[index];
            switch (argument) {
                case "--input":
                    options.input = Paths.get(requireValue(args, ++index, argument));
                    break;
                case "--output":
                    options.output = Paths.get(requireValue(args, ++index, argument));
                    break;
                case "--mode":
                    options.mode = requireValue(args, ++index, argument);
                    break;
                case "--strip-debug":
                    options.stripDebug = Boolean.parseBoolean(requireValue(args, ++index, argument));
                    break;
                case "--normalize-dex":
                    options.normalizeDex = Boolean.parseBoolean(requireValue(args, ++index, argument));
                    break;
                case "--list-messages":
                    options.listMessages = Boolean.parseBoolean(requireValue(args, ++index, argument));
                    break;
                case "--message-target":
                    options.messageTargets.add(requireValue(args, ++index, argument));
                    break;
                case "--startup-target":
                    options.startupTargets.add(requireValue(args, ++index, argument));
                    break;
                case "--descriptor":
                    options.descriptors.add(requireValue(args, ++index, argument));
                    break;
                case "--clone-string":
                    String original = requireValue(args, ++index, argument);
                    String replacement = requireValue(args, ++index, argument);
                    if (original.isEmpty() || replacement.isEmpty()) throw new IllegalArgumentException("Empty clone string mapping");
                    options.cloneStrings.put(original, replacement);
                    break;
                default:
                    throw new IllegalArgumentException("Bilinmeyen argüman: " + argument);
            }
        }
        if (options.input == null || options.output == null) {
            throw new IllegalArgumentException("--input ve --output zorunludur.");
        }
        if (!("safe".equals(options.mode) || "balanced".equals(options.mode) || "deep".equals(options.mode))) {
            throw new IllegalArgumentException("Geçersiz mod: " + options.mode);
        }
        return options;
    }

    private static String requireValue(String[] args, int index, String option) {
        if (index >= args.length) {
            throw new IllegalArgumentException(option + " için değer eksik.");
        }
        return args[index];
    }
}
