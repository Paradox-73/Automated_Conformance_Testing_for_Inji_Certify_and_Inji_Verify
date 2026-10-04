// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance.runner;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import io.mosip.testrig.apirig.conformance.Fixtures;

public class RunnerInvokerTest {

    /** A command that starts FakeRunner.java with the JVM running the tests, so no Python or shell is needed. */
    public static String fakeRunner(String arguments) {
        Path java = Path.of(System.getProperty("java.home"), "bin", "java");
        Path source = Fixtures.OWN.resolve("FakeRunner.java").toAbsolutePath();
        return "\"" + java + "\" \"" + source + "\" " + arguments;
    }

    static ConformanceSettings invokeSettings(String command, Path out, Duration timeout) {
        return new ConformanceSettings("verify", null, command, "https://verify.inji.test:18451", out, timeout);
    }

    @Test
    void splitsLikeAShellAndReplacesPlaceholdersPerArgument() {
        List<String> args = RunnerInvoker.expand(
                "inji-conformance run --component {component} --target {target} --out '{out}' --note \"a b\" x\\ y",
                Map.of("{component}", "verify", "{target}", "https://v:1", "{out}", "/run dir/r"));

        assertEquals(List.of("inji-conformance", "run", "--component", "verify", "--target", "https://v:1",
                "--out", "/run dir/r", "--note", "a b", "x y"), args);
    }

    @Test
    void keepsWindowsPathsAndEmptyQuotedArguments() {
        assertEquals(List.of("C:\\tools\\runner.exe", "", "a\"b"),
                RunnerInvoker.expand("C:\\tools\\runner.exe '' a\\\"b", Map.of()));
    }

    @Test
    void rejectsAnUnclosedQuote() {
        assertThrows(IllegalArgumentException.class, () -> RunnerInvoker.expand("run 'oops", Map.of()));
    }

    @Test
    void runsTheCommandAndPointsAtItsResults(@TempDir Path out) throws Exception {
        Path example = Fixtures.example("results-verify.example.json").toAbsolutePath();
        RunnerInvoker.Invocation run = new RunnerInvoker().invoke(invokeSettings(
                fakeRunner("copy \"" + example + "\" {out} {component} 1"), out, Duration.ofMinutes(2)));

        assertFalse(run.timedOut());
        assertEquals(1, run.exitCode());
        assertEquals(out.toAbsolutePath().normalize().resolve("verify").resolve("results.json"), run.resultsFile());
        assertTrue(Files.isRegularFile(run.resultsFile()));
        assertTrue(Files.readString(run.logFile()).contains("wrote "));
    }

    @Test
    void endsARunnerThatTakesTooLong() throws Exception {
        // Not a @TempDir: on Windows the killed JVM can release runner.log a moment after it ends, and a failed
        // temp folder cleanup would fail the test. target/ is removed by "mvn clean".
        Path out = Files.createTempDirectory(Files.createDirectories(Path.of("target", "test-runs")), "timeout");
        RunnerInvoker.Invocation run = new RunnerInvoker().invoke(
                invokeSettings(fakeRunner("sleep"), out, Duration.ofSeconds(5)));

        assertTrue(run.timedOut());
        assertEquals(-1, run.exitCode());
        assertTrue(run.elapsed().toSeconds() < 60, run.elapsed().toString());
    }

    @Test
    void reportsAProgramThatDoesNotExist(@TempDir Path out) {
        assertThrows(RunnerInvoker.RunnerStartException.class, () -> new RunnerInvoker().invoke(
                invokeSettings("no-such-program-for-conformance-tests", out, Duration.ofSeconds(5))));
    }

    @Test
    void tailReturnsTheLastLines(@TempDir Path dir) throws Exception {
        Path log = dir.resolve("runner.log");
        Files.write(log, List.of("1", "2", "3", "4"));
        assertEquals(List.of("3", "4"), RunnerInvoker.tail(log, 2));
        assertEquals(List.of(), RunnerInvoker.tail(dir.resolve("missing.log"), 2));
    }
}
