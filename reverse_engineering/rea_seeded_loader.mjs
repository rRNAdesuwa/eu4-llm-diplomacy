import { createHash } from "node:crypto";
import { readFileSync, realpathSync, statSync } from "node:fs";
import { registerHooks } from "node:module";
import { isAbsolute, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REQUIRED_REA_VERSION = "6.4.0";
const packageRootSetting = process.env.EU4_REA_PACKAGE_ROOT;
const seedFileSetting = process.env.REA_GHIDRA_SEED_FILE;
const decodeScriptSetting = process.env.EU4_REA_DECODE_SCRIPT;
const rangesSetting = process.env.EU4_REA_RANGES;

if (typeof registerHooks !== "function") {
    throw new Error("EU4 REA seeded loader requires Node's synchronous module registerHooks API");
}
if (typeof packageRootSetting !== "string" || packageRootSetting.length === 0) {
    throw new Error("EU4 REA seeded loader requires EU4_REA_PACKAGE_ROOT");
}
if (!isAbsolute(packageRootSetting)) {
    throw new Error("EU4_REA_PACKAGE_ROOT must be an absolute path");
}
if (typeof seedFileSetting !== "string" || seedFileSetting.length === 0) {
    throw new Error("EU4 REA seeded loader requires a non-empty REA_GHIDRA_SEED_FILE");
}
for (const setting of [decodeScriptSetting, rangesSetting]) {
    if (typeof setting !== "string" || !isAbsolute(setting) || !statSync(setting).isFile())
        throw new Error("EU4 REA seeded loader requires absolute existing decode script and range file");
}
const decodeSha256 = createHash("sha256").update(readFileSync(decodeScriptSetting)).digest("hex");
const rangesSha256 = createHash("sha256").update(readFileSync(rangesSetting)).digest("hex");

const packageRoot = realpathSync(packageRootSetting);
if (!statSync(packageRoot).isDirectory()) {
    throw new Error(`EU4_REA_PACKAGE_ROOT is not a directory: ${packageRoot}`);
}

const packageMetadata = JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8"));
if (packageMetadata.version !== REQUIRED_REA_VERSION) {
    throw new Error(
        `EU4 REA seeded loader supports rea-agents ${REQUIRED_REA_VERSION} only; found ${String(packageMetadata.version)}`,
    );
}

const adapterSource = readFileSync(fileURLToPath(import.meta.url), "utf8");
const adapterSha256 = createHash("sha256").update(adapterSource, "utf8").digest("hex");

const exactReplace = (source, anchor, replacement, label) => {
    const first = source.indexOf(anchor);
    if (first < 0) {
        throw new Error(`EU4 REA seeded loader anchor is missing: ${label}`);
    }
    if (source.indexOf(anchor, first + anchor.length) >= 0) {
        throw new Error(`EU4 REA seeded loader anchor is not unique: ${label}`);
    }
    return `${source.slice(0, first)}${replacement}${source.slice(first + anchor.length)}`;
};

const transformLauncher = (source) => {
    const seedGuardAnchor = [
        "    if (override !== undefined &&",
        "        (options.dosMz === true || options.dosCom === true))",
        '        throw new Error("A Ghidra language override cannot be combined with a DOS import.");',
        "    return [",
    ].join("\n");
    const seedGuardReplacement = [
        "    if (override !== undefined &&",
        "        (options.dosMz === true || options.dosCom === true))",
        '        throw new Error("A Ghidra language override cannot be combined with a DOS import.");',
        '    if (typeof options.seedPath !== "string" || options.seedPath.length === 0)',
        '        throw new Error("EU4 REA seeded loader requires a Ghidra seed path");',
        "    return [",
    ].join("\n");
    let transformed = exactReplace(source, seedGuardAnchor, seedGuardReplacement, "launcher seed guard");
    transformed = exactReplace(
        transformed,
        "        options.targetPath,\n        ...(options.dosMz === true",
        "        options.targetPath,\n        \"-noanalysis\",\n        \"-max-cpu\",\n        \"2\",\n        ...(options.dosMz === true",
        "launcher noanalysis/max-cpu arguments",
    );
    transformed = exactReplace(transformed, "        bridgeDirectory,\n        ...(options.dosCom === true",
        `        bridgeDirectory + \";\" + scriptPath.dirname(${JSON.stringify(decodeScriptSetting)}),\n        ...(options.dosCom === true`,
        "bounded decode script path");
    transformed = exactReplace(transformed,
        '        options.bridgeScriptPath,\n        options.descriptorPath,',
        `        ${JSON.stringify(decodeScriptSetting)},\n        ${JSON.stringify(rangesSetting)},\n        ${JSON.stringify(rangesSha256)},\n        \"-postScript\",\n        options.bridgeScriptPath,\n        options.descriptorPath,`,
        "bounded decode before bridge");
    return transformed;
};

const transformProfile = (source) => exactReplace(
    source,
    '            analyzer_preset: "ghidra-default",',
    [
        '            analyzer_preset: "eu4-declared-seeds-pdata-noanalysis-v2",',
        `            local_adapter_sha256: ${JSON.stringify(adapterSha256)},`,
        `            local_decode_script_sha256: ${JSON.stringify(decodeSha256)},`,
        `            declared_ranges_sha256: ${JSON.stringify(rangesSha256)},`,
        '            function_body_scope: "selected-exact-PE-unwind-ranges",',
        '            xref_scope: "declared-seeds-only-global-incomplete",',
    ].join("\n"),
    "profile analyzer commitment",
);

const transformCapabilities = (source) => exactReplace(
    source,
    '    "The session serves operations only after Ghidra reports default auto-analysis complete; incomplete analysis does not expose partial results.",',
    '    "This EU4 seeded session decodes selected exact PE unwind ranges only. Those ranges do not establish all semantic function chunks or an externally callable ABI. Global xref, string, type, and CFG coverage is incomplete, and an empty reference result does not prove that no caller exists.",',
    "capability seeded-analysis limitation",
);

const targetModules = new Map([
    [
        pathToFileURL(join(packageRoot, "dist", "ghidra", "GhidraLauncher.js")).href,
        transformLauncher,
    ],
    [
        pathToFileURL(join(packageRoot, "dist", "ghidra", "GhidraAnalysisProfile.js")).href,
        transformProfile,
    ],
    [
        pathToFileURL(join(packageRoot, "dist", "ghidra", "GhidraProviderCapabilities.js")).href,
        transformCapabilities,
    ],
]);

registerHooks({
    load(url, context, nextLoad) {
        const loaded = nextLoad(url, context);
        const transform = targetModules.get(url);
        if (transform === undefined) {
            return loaded;
        }
        if (loaded.source === undefined) {
            throw new Error(`EU4 REA seeded loader received no source for ${url}`);
        }
        const source = String(loaded.source).replace(/\r\n/g, "\n");
        const transformed = transform(source);
        return {
            ...loaded,
            format: loaded.format,
            source: transformed,
            shortCircuit: true,
        };
    },
});
