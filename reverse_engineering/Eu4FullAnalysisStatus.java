// Report default headless auto-analysis; retain the database for later queries.
// @category EU4.REA
import ghidra.app.util.headless.HeadlessScript;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

public class Eu4FullAnalysisStatus extends HeadlessScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 3) throw new IllegalArgumentException("Expected report path, SHA and stage");
        String digest = currentProgram.getExecutableSHA256();
        if (!args[1].equals(digest)) throw new IllegalArgumentException("Imported image digest mismatch");
        JsonObject report = new JsonObject();
        report.addProperty("target_sha256", digest);
        report.addProperty("program", currentProgram.getName());
        report.addProperty("language_id", currentProgram.getLanguageID().toString());
        report.addProperty("image_base", currentProgram.getImageBase().toString());
        report.addProperty("stage", args[2]);
        boolean timedOut = args[2].equals("analysis") && analysisTimeoutOccurred();
        report.addProperty("analysis_timed_out", timedOut);
        report.addProperty("default_auto_analysis_completed", args[2].equals("analysis") && !timedOut);
        report.addProperty("function_count", currentProgram.getFunctionManager().getFunctionCount());
        report.addProperty("instruction_count", currentProgram.getListing().getNumInstructions());
        report.addProperty("defined_data_count", currentProgram.getListing().getNumDefinedData());
        report.addProperty("symbol_count", currentProgram.getSymbolTable().getNumSymbols());
        Files.writeString(Path.of(args[0]), new GsonBuilder().setPrettyPrinting().create().toJson(report), StandardCharsets.UTF_8);
        println("EU4 persistent analysis report: " + report.toString());
    }
}
