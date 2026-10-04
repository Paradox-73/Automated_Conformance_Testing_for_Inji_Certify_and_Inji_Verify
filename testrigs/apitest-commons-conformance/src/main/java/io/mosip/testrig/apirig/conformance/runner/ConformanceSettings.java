// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance.runner;

import java.nio.file.Path;
import java.time.Duration;
import java.util.Locale;
import java.util.Objects;
import java.util.function.UnaryOperator;

/**
 * Where a rig's conformance rows come from, read from JVM system properties or environment variables.
 *
 * <p>Three modes:
 * <ul>
 * <li><b>consume</b>: {@value #RESULTS_FILE} names a {@code results.json} the runner already wrote (CI runs the
 * runner as its own step, then the rig);</li>
 * <li><b>invoke</b>: {@value #RUNNER_COMMAND} is a command line that runs the conformance runner against the rig's
 * {@code env.endpoint}; the bridge starts it, waits at most {@value #RUNNER_TIMEOUT_MINUTES} minutes and reads
 * {@code <out>/<component>/results.json};</li>
 * <li><b>not configured</b>: neither is set. The rig reports one Ignored row, so adding the conformance suite file
 * to a rig never breaks a pipeline that has no conformance runner.</li>
 * </ul>
 *
 * <p>Each key is looked up as a system property ({@code -Dconformance.results.file=...}), then as an environment
 * variable with the same name (the apitest-commons {@code ConfigManager} convention), then as an environment
 * variable in upper snake case ({@code CONFORMANCE_RESULTS_FILE}), which every shell can set.
 *
 * @param component      {@code certify} or {@code verify}
 * @param resultsFile    consume mode: the results file; {@code null} otherwise
 * @param runnerCommand  invoke mode: the command template; {@code null} otherwise
 * @param target         base URL of the system under test, passed to the runner as {@code {target}}
 * @param runnerOutDir   folder the runner writes its run into, passed as {@code {out}}
 * @param runnerTimeout  time limit for the runner process
 */
public record ConformanceSettings(
        String component,
        Path resultsFile,
        String runnerCommand,
        String target,
        Path runnerOutDir,
        Duration runnerTimeout) {

    /** Consume mode: path of an existing {@code results.json}. Wins over {@value #RUNNER_COMMAND}. */
    public static final String RESULTS_FILE = "conformance.results.file";
    /** Invoke mode: command template with the placeholders {@code {component}}, {@code {target}}, {@code {out}}. */
    public static final String RUNNER_COMMAND = "conformance.runner.command";
    /** Base URL of the system under test; default {@code env.endpoint}. */
    public static final String TARGET = "conformance.target";
    /** Folder for the runner's output in invoke mode; default {@code ${HARNESS_RUN_DIR}/testrig/runner}. */
    public static final String RUNNER_OUT = "conformance.runner.out";
    /** Time limit of the runner process in minutes; default {@value #DEFAULT_TIMEOUT_MINUTES}. */
    public static final String RUNNER_TIMEOUT_MINUTES = "conformance.runner.timeout.minutes";
    /** Run folder of the harness; used for defaults only. */
    public static final String HARNESS_RUN_DIR = "HARNESS_RUN_DIR";

    /**
     * Default time limit. A full verifier or issuer plan takes about 10 to 20 minutes on a laptop; 90 minutes leaves
     * room for image pulls and slow CI runners while still ending a hung run.
     */
    public static final long DEFAULT_TIMEOUT_MINUTES = 90;

    /** How the rig gets its conformance results. */
    public enum Mode { CONSUME, INVOKE, NOT_CONFIGURED }

    public ConformanceSettings {
        Objects.requireNonNull(component, "component");
        Objects.requireNonNull(runnerOutDir, "runnerOutDir");
        Objects.requireNonNull(runnerTimeout, "runnerTimeout");
    }

    /** The mode these settings select. */
    public Mode mode() {
        if (resultsFile != null) {
            return Mode.CONSUME;
        }
        return runnerCommand != null ? Mode.INVOKE : Mode.NOT_CONFIGURED;
    }

    /** Settings from this JVM's system properties and environment; the target defaults to {@code env.endpoint}. */
    public static ConformanceSettings fromEnvironment(String component) {
        return from(component, System::getProperty, System::getenv);
    }

    /**
     * Settings from explicit lookups, so tests need not touch the real environment.
     *
     * @param component  {@code certify} or {@code verify}
     * @param properties system property lookup
     * @param environment environment variable lookup
     * @throws IllegalArgumentException when the timeout is not a positive whole number
     */
    public static ConformanceSettings from(
            String component, UnaryOperator<String> properties, UnaryOperator<String> environment) {
        Lookup lookup = new Lookup(properties, environment);
        Path resultsFile = lookup.path(RESULTS_FILE);
        String command = lookup.value(RUNNER_COMMAND);
        String target = lookup.value(TARGET);
        if (target == null) {
            target = lookup.value("env.endpoint");
        }

        Path outDir = lookup.path(RUNNER_OUT);
        if (outDir == null) {
            String runDir = lookup.value(HARNESS_RUN_DIR);
            outDir = runDir != null
                    ? Path.of(runDir, "testrig", "runner")
                    // testng-report/ is the folder the stock rigs already write to and ignore in git.
                    : Path.of(Objects.requireNonNullElse(properties.apply("user.dir"), "."), "testng-report", "runner");
        }

        Duration timeout = Duration.ofMinutes(DEFAULT_TIMEOUT_MINUTES);
        String minutes = lookup.value(RUNNER_TIMEOUT_MINUTES);
        if (minutes != null) {
            try {
                long value = Long.parseLong(minutes);
                if (value <= 0) {
                    throw new NumberFormatException("not positive");
                }
                timeout = Duration.ofMinutes(value);
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException(
                        RUNNER_TIMEOUT_MINUTES + " must be a positive whole number of minutes, got \"" + minutes + "\"",
                        e);
            }
        }
        return new ConformanceSettings(component, resultsFile, command, target, outDir, timeout);
    }

    /** One line for logs and report rows; never prints more than the command template. */
    public String describe() {
        return switch (mode()) {
            case CONSUME -> "consume mode, results file " + resultsFile;
            case INVOKE -> "invoke mode, command \"" + runnerCommand + "\", target " + target + ", output " + runnerOutDir
                    + ", timeout " + runnerTimeout.toMinutes() + " min";
            case NOT_CONFIGURED -> "not configured: set " + RESULTS_FILE + " or " + RUNNER_COMMAND;
        };
    }

    /** Lookup order: system property, environment variable of the same name, environment variable in upper case. */
    private record Lookup(UnaryOperator<String> properties, UnaryOperator<String> environment) {
        String value(String key) {
            String value = properties.apply(key);
            if (isBlank(value)) {
                value = environment.apply(key);
            }
            if (isBlank(value)) {
                value = environment.apply(key.replace('.', '_').toUpperCase(Locale.ROOT));
            }
            return isBlank(value) ? null : value.trim();
        }

        Path path(String key) {
            String value = value(key);
            return value == null ? null : Path.of(value);
        }

        private static boolean isBlank(String value) {
            return value == null || value.isBlank();
        }
    }
}
