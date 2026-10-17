// Process-local REA 6.4.0 route to a verified completed Ghidra project.
import { createHash } from "node:crypto";
import { readFileSync, realpathSync, statSync } from "node:fs";
import { registerHooks } from "node:module";
import { join, isAbsolute } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const requiredPath = (key) => {
    const value = process.env[key];
    if (typeof value !== "string" || !isAbsolute(value)) throw new Error(`Missing absolute ${key}`);
    return realpathSync(value);
};
const packageRoot = requiredPath("EU4_REA_PACKAGE_ROOT");
const projectRoot = requiredPath("EU4_REA_CACHE_PROJECT");
const manifestPath = requiredPath("EU4_REA_CACHE_MANIFEST");
const manifestBytes = readFileSync(manifestPath);
const manifest = JSON.parse(manifestBytes);
if (JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8")).version !== "6.4.0")
    throw new Error("Persistent REA loader is verified for 6.4.0 only");
if (manifest.status !== "complete" || manifest.analysis_report?.default_auto_analysis_completed !== true ||
    manifest.analysis_report?.analysis_timed_out !== false || manifest.project_name !== "EU4Full" || manifest.program !== "eu4.exe")
    throw new Error("Persistent REA loader refuses incomplete/unexpected analysis manifest");
if (!statSync(join(projectRoot, "EU4Full.gpr")).isFile()) throw new Error("Missing completed Ghidra project");
if (process.env.REA_GHIDRA_SEED_FILE) throw new Error("Persistent read-only queries refuse analysis seeds");
const commitment = process.env.EU4_REA_CACHE_DATABASE_SHA256;
if (typeof commitment !== "string" || !/^[0-9a-f]{64}$/.test(commitment)) throw new Error("Missing database commitment");
const adapterSha = createHash("sha256").update(readFileSync(fileURLToPath(import.meta.url))).digest("hex");
const manifestSha = createHash("sha256").update(manifestBytes).digest("hex");
const replace = (source, anchor, value) => {
    const first = source.indexOf(anchor);
    if (first < 0 || source.indexOf(anchor, first + anchor.length) >= 0)
        throw new Error(`REA cache adapter cannot uniquely match ${anchor.slice(0, 80)}`);
    return source.slice(0, first) + value + source.slice(first + anchor.length);
};
const transforms = new Map([
    ["GhidraLauncher.js", (source) => {
        // Change final argv only. REA's private runtime/DACL ownership stays intact.
        let result = replace(source,
            '        options.projectRoot,\n        "rea-project",\n        "-import",\n        options.targetPath,',
            `        ${JSON.stringify(projectRoot)},\n        "EU4Full",\n        "-process",\n        "eu4.exe",\n        "-noanalysis",\n        "-max-cpu",\n        "2",`);
        return replace(result, '        "-deleteProject",\n', "");
    }],
    ["GhidraAnalysisProfile.js", (source) => {
        let result = replace(source, '            import_mode: "ephemeral-source-immutable",',
            '            import_mode: "persistent-completed-project-read-only",');
        return replace(result, '            analyzer_preset: "ghidra-default",', [
            '            analyzer_preset: "eu4-persistent-default-analysis-v1",',
            `            local_adapter_sha256: ${JSON.stringify(adapterSha)},`,
            `            completed_manifest_sha256: ${JSON.stringify(manifestSha)},`,
            `            completed_database_sha256: ${JSON.stringify(commitment)},`,
            '            query_reanalysis: false,',
            '            database_mutation: "read-only-no-save",',
        ].join("\n"));
    }],
    ["GhidraProviderCapabilities.js", (source) => {
        let result = replace(source,
            '    "The session serves operations only after Ghidra reports default auto-analysis complete; incomplete analysis does not expose partial results.",',
            '    "This project adapter reads a separately completed default-analysis Ghidra database without rerunning analysis. Automatic analysis does not establish all semantic types, indirect calls, or runtime behavior.",');
        result = replace(result,
            '    "The imported Program and temporary project are ephemeral and deleted on close. Annotation operations edit session database metadata; original executable bytes are never written.",',
            '    "The completed analysis project is retained. Queries use -readOnly and -noanalysis; only REA private endpoint/log/temporary-input resources are deleted on close. This project entry exposes read-only function queries.",');
        return replace(result,
            '    "Cancelling an active Ghidra request terminates its ephemeral database and discards session annotations. The selected target remains open; the next provider query imports the original artifact again.",',
            '    "Cancelling this query closes its read-only database view and REA private runtime; the completed project remains available for the next query.",');
    }],
]);
const modules = new Map([...transforms].map(([name, transform]) => [pathToFileURL(join(packageRoot, "dist", "ghidra", name)).href, transform]));
registerHooks({load(url, context, nextLoad) {
    const loaded = nextLoad(url, context);
    const transform = modules.get(url);
    if (!transform) return loaded;
    if (loaded.source === undefined) throw new Error("No REA source for cache adapter");
    return {...loaded, source: transform(String(loaded.source).replace(/\r\n/g, "\n")), shortCircuit: true};
}});
