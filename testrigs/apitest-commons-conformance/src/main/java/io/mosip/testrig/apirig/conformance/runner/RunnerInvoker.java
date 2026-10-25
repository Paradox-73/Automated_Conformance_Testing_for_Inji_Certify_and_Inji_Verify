// SPDX-License-Identifier: MPL-2.0
package io.mosip.testrig.apirig.conformance.runner;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Starts the conformance runner as a child process and waits for it with a time limit (invoke mode).
 *
 * <p>The command comes from {@link ConformanceSettings#runnerCommand()}, for example
 * {@code inji-conformance run --component {component} --target {target} --out {out}}. It is split into arguments
 * the way a POSIX shell would split it (single and double quotes group words; no variable expansion), and no shell
 * is started, so a target URL can never inject a command. The placeholders are replaced inside each argument.
 *
 * <p>Standard output and error go to {@code <out>/runner.log}: a pipe that nobody reads would block the child once
 * the pipe buffer is full. On timeout the process and all its descendants are killed, because the runner starts
 * the suite's own Python scripts as children.
 */
public final class RunnerInvoker {

    /** Log file name inside the runner output folder. */
    public static final String LOG_FILE = "runner.log";

    /**
     * What happened to the runner process.
     *
     * @param command     the arguments that were started
     * @param exitCode    the process exit code; {@code -1} when it timed out or could not start
     * @param timedOut    {@code true} when the time limit ended the process
     * @param resultsFile where the runner writes its results ({@code <out>/<component>/results.json})
     * @param logFile     the process output
     * @param elapsed     wall time
     */
    public record Invocation(
            List<String> command, int exitCode, boolean timedOut, Path resultsFile, Path logFile, Duration elapsed) {
        public Invocation {
            command = List.copyOf(command);
        }
    }

    /** Thrown when the process cannot be started, for example because the program does not exist. */
    public static final class RunnerStartException extends Exception {
        public RunnerStartException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    /**
     * Runs the command of {@code settings} and waits for it.
     *
     * @throws RunnerStartException when the output folder cannot be created or the process cannot start
     * @throws InterruptedException when this thread is interrupted while waiting; the process is killed first
     */
    public Invocation invoke(ConformanceSettings settings) throws RunnerStartException, InterruptedException {
        if (settings.runnerCommand() == null) {
            throw new IllegalArgumentException("no runner command configured");
        }
        Path out = settings.runnerOutDir().toAbsolutePath().normalize();
        List<String> command = expand(settings.runnerCommand(), Map.of(
                "{component}", settings.component(),
                "{target}", settings.target() == null ? "" : settings.target(),
                "{out}", out.toString()));
        if (command.isEmpty()) {
            throw new IllegalArgumentException("the runner command is empty");
        }

        Path log = out.resolve(LOG_FILE);
        try {
            Files.createDirectories(out);
        } catch (IOException e) {
            throw new RunnerStartException("cannot create runner output folder " + out + ": " + e.getMessage(), e);
        }

        ProcessBuilder builder = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .redirectOutput(ProcessBuilder.Redirect.to(log.toFile()));
        long started = System.nanoTime();
        Process process;
        try {
            process = builder.start();
        } catch (IOException e) {
            throw new RunnerStartException("cannot start the conformance runner " + command + ": " + e.getMessage(), e);
        }

        boolean finished;
        try {
            finished = process.waitFor(settings.runnerTimeout().toMillis(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            killTree(process);
            throw e;
        }
        if (!finished) {
            killTree(process);
        }
        Duration elapsed = Duration.ofNanos(System.nanoTime() - started);
        Path results = out.resolve(settings.component()).resolve("results.json");
        return new Invocation(command, finished ? process.exitValue() : -1, !finished, results, log, elapsed);
    }

    /**
     * Kills the process and every process it started, then waits up to 10 seconds for each to end, so none of them
     * still holds the log file open (Windows refuses to delete a file that a process has open).
     */
    private static void killTree(Process process) throws InterruptedException {
        List<ProcessHandle> tree = process.descendants().toList();
        tree.forEach(ProcessHandle::destroyForcibly);
        process.destroyForcibly();
        process.waitFor(10, TimeUnit.SECONDS);
        for (ProcessHandle handle : tree) {
            try {
                handle.onExit().get(10, TimeUnit.SECONDS);
            } catch (ExecutionException | TimeoutException e) {
                // Best effort: the run is reported as timed out either way.
            }
        }
    }

    /**
     * Splits {@code template} into arguments and replaces the placeholders in each one.
     *
     * <p>Whitespace separates arguments; text inside single or double quotes stays one argument. Outside single
     * quotes a backslash keeps a following quote, backslash or whitespace character literally; before any other
     * character it is an ordinary character, so Windows paths such as {@code C:\tools\runner.exe} work unquoted.
     * Placeholders are replaced after splitting, so a value with spaces stays one argument.
     *
     * @throws IllegalArgumentException when a quote is not closed
     */
    public static List<String> expand(String template, Map<String, String> placeholders) {
        List<String> args = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        boolean inArgument = false;
        char quote = 0;
        for (int i = 0; i < template.length(); i++) {
            char c = template.charAt(i);
            if (quote == '\'') {
                if (c == '\'') {
                    quote = 0;
                } else {
                    current.append(c);
                }
            } else if (c == '\\' && i + 1 < template.length() && isEscapable(template.charAt(i + 1))) {
                current.append(template.charAt(++i));
                inArgument = true;
            } else if (quote == '"') {
                if (c == '"') {
                    quote = 0;
                } else {
                    current.append(c);
                }
            } else if (c == '\'' || c == '"') {
                quote = c;
                inArgument = true;
            } else if (Character.isWhitespace(c)) {
                if (inArgument) {
                    args.add(current.toString());
                    current.setLength(0);
                    inArgument = false;
                }
            } else {
                current.append(c);
                inArgument = true;
            }
        }
        if (quote != 0) {
            throw new IllegalArgumentException("unclosed " + quote + " quote in runner command: " + template);
        }
        if (inArgument) {
            args.add(current.toString());
        }
        List<String> expanded = new ArrayList<>(args.size());
        for (String arg : args) {
            for (Map.Entry<String, String> placeholder : placeholders.entrySet()) {
                arg = arg.replace(placeholder.getKey(), placeholder.getValue());
            }
            expanded.add(arg);
        }
        return expanded;
    }

    private static boolean isEscapable(char c) {
        return c == '"' || c == '\'' || c == '\\' || Character.isWhitespace(c);
    }

    /** The last {@code maxLines} lines of the runner log, for report rows; empty when the log cannot be read. */
    public static List<String> tail(Path log, int maxLines) {
        try {
            List<String> lines = Files.readAllLines(log, StandardCharsets.UTF_8);
            return List.copyOf(lines.subList(Math.max(0, lines.size() - maxLines), lines.size()));
        } catch (IOException | RuntimeException e) {
            return List.of();
        }
    }
}
