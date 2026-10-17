// Decode only exact PE unwind ranges selected by the hash-bound Python entry.
// @category EU4.REA
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public class Eu4ReaDecodeFunctions extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2) throw new IllegalArgumentException("Expected range file and SHA-256");
        Path path = Path.of(args[0]);
        if (Files.size(path) > 65536) throw new IllegalArgumentException("Range file exceeds budget");
        byte[] bytes = Files.readAllBytes(path);
        String digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        if (!digest.equals(args[1])) throw new IllegalArgumentException("Range commitment mismatch");
        String[] rows = new String(bytes, StandardCharsets.UTF_8).strip().split("\n");
        if (rows.length == 0 || rows.length > 32) throw new IllegalArgumentException("Invalid range count");
        for (String row : rows) {
            monitor.checkCancelled();
            String[] fields = row.strip().split("\t", -1);
            if (fields.length != 2) throw new IllegalArgumentException("Malformed range row");
            Address begin = toAddr(fields[0]);
            Address end = toAddr(fields[1]).subtract(1);
            if (end.compareTo(begin) < 0 || end.subtract(begin) >= 0x8000)
                throw new IllegalArgumentException("Invalid range bounds");
            if (!currentProgram.getMemory().getLoadedAndInitializedAddressSet().contains(begin, end))
                throw new IllegalArgumentException("Range not in initialized image");
            Function function = getFunctionAt(begin);
            if (function == null) throw new IllegalArgumentException("Missing seeded function at " + begin);
            AddressSet range = new AddressSet(begin, end);
            DisassembleCommand command = new DisassembleCommand(begin, range, true);
            command.enableCodeAnalysis(false);
            if (!command.applyTo(currentProgram, monitor) || getInstructionAt(begin) == null)
                throw new IllegalArgumentException("Bounded disassembly failed: " + command.getStatusMsg());
            function.setBody(range);
            println("EU4 bounded function: " + begin + ".." + end + " (PE unwind range)");
        }
        println("EU4 range commitment: " + digest + "; decoded functions=" + rows.length);
    }
}
