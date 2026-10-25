// SPDX-License-Identifier: MPL-2.0
// Test stand-in for the conformance runner, started by RunnerInvokerTest with the java source launcher.
// Usage: java FakeRunner.java copy SOURCE OUT COMPONENT EXIT | java FakeRunner.java fail EXIT | java FakeRunner.java sleep
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class FakeRunner {
    public static void main(String[] args) throws Exception {
        switch (args[0]) {
            case "copy" -> {
                Path target = Path.of(args[2], args[3], "results.json");
                Files.createDirectories(target.getParent());
                Files.copy(Path.of(args[1]), target, StandardCopyOption.REPLACE_EXISTING);
                System.out.println("wrote " + target);
                System.exit(Integer.parseInt(args[4]));
            }
            case "fail" -> {
                System.out.println("environment not ready: suite not reachable");
                System.exit(Integer.parseInt(args[1]));
            }
            case "sleep" -> {
                System.out.println("sleeping");
                Thread.sleep(120_000);
            }
            default -> System.exit(64);
        }
    }
}
