// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance.testng;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

import io.mosip.testrig.apirig.conformance.Outcome;
import io.mosip.testrig.apirig.conformance.OutcomeMapper;
import io.mosip.testrig.apirig.conformance.results.ConformanceResults;
import io.mosip.testrig.apirig.conformance.results.ModuleResult;
import io.mosip.testrig.apirig.conformance.results.ResultsFormatException;
import io.mosip.testrig.apirig.conformance.results.ResultsReader;
import io.mosip.testrig.apirig.conformance.runner.ConformanceSettings;
import io.mosip.testrig.apirig.conformance.runner.RunnerInvoker;
import io.mosip.testrig.apirig.utils.GlobalConstants;

/**
 * Turns {@link ConformanceSettings} into the rows of a rig's conformance test.
 *
 * <p>Every way the run can go wrong becomes a failing row with the reason, never an exception out of the data
 * provider: TestNG would otherwise skip the whole test method silently and the rig would exit as if nothing was
 * wrong. The one exception is "not configured", which is a single Ignored row by design.
 *
 * <p>Rule kept here: a gating run whose gate failed always yields at least one failing row, so the rig's exit code
 * (computed from failures) matches the conformance gate.
 */
public final class ConformanceCaseLoader {

    /** Lines of the runner log copied into a failing row. */
    static final int LOG_TAIL_LINES = 20;

    /** Message of the single Ignored row when no conformance source is configured. */
    public static final String NOT_CONFIGURED_MESSAGE = GlobalConstants.FEATURE_NOT_SUPPORTED
            + ": conformance runner not configured (set " + ConformanceSettings.RESULTS_FILE + " or "
            + ConformanceSettings.RUNNER_COMMAND + ")";

    private final ResultsReader reader;
    private final RunnerInvoker invoker;
    private final OutcomeMapper mapper;

    public ConformanceCaseLoader() {
        this(new ResultsReader(), new RunnerInvoker(), new OutcomeMapper());
    }

    ConformanceCaseLoader(ResultsReader reader, RunnerInvoker invoker, OutcomeMapper mapper) {
        this.reader = Objects.requireNonNull(reader, "reader");
        this.invoker = Objects.requireNonNull(invoker, "invoker");
        this.mapper = Objects.requireNonNull(mapper, "mapper");
    }

    /**
     * Loads the rows for one rig.
     *
     * @param settings  where the results come from
     * @param rigPrefix test case name prefix of the rig, for example {@code InjiVerify}
     * @return at least one row
     * @throws InterruptedException when the thread is interrupted while the runner runs
     */
    public List<ConformanceCase> load(ConformanceSettings settings, String rigPrefix) throws InterruptedException {
        Rows rows = new Rows(settings, rigPrefix);
        return switch (settings.mode()) {
            case NOT_CONFIGURED -> List.of(rows.single("NotConfigured",
                    "OpenID conformance run of " + settings.component() + " (not configured in this run)",
                    new Outcome(Outcome.Kind.IGNORED, NOT_CONFIGURED_MESSAGE, List.of(settings.describe()))));
            case CONSUME -> fromResults(rows, settings, settings.resultsFile(),
                    List.of("Results source: " + settings.describe()));
            case INVOKE -> invoke(rows, settings);
        };
    }

    private List<ConformanceCase> invoke(Rows rows, ConformanceSettings settings) throws InterruptedException {
        RunnerInvoker.Invocation run;
        try {
            run = invoker.invoke(settings);
        } catch (RunnerInvoker.RunnerStartException | IllegalArgumentException e) {
            return List.of(rows.failure("Runner", "conformance runner could not start: " + e.getMessage(),
                    List.of(settings.describe())));
        }
        List<String> context = new ArrayList<>();
        context.add("Runner: " + String.join(" ", run.command()));
        context.add("Runner " + (run.timedOut() ? "timed out" : "exit code " + run.exitCode()) + " after "
                + run.elapsed().toSeconds() + " s; log " + run.logFile());

        if (run.timedOut()) {
            return List.of(rows.failure("Runner", "conformance runner timed out after "
                    + settings.runnerTimeout().toMinutes() + " min (" + ConformanceSettings.RUNNER_TIMEOUT_MINUTES
                    + ")", withLogTail(context, run)));
        }
        if (!Files.isRegularFile(run.resultsFile())) {
            return List.of(rows.failure("Runner", "conformance runner exited with code " + run.exitCode()
                    + " without writing " + run.resultsFile(), withLogTail(context, run)));
        }
        List<ConformanceCase> cases = new ArrayList<>(fromResults(rows, settings, run.resultsFile(), context));
        // Exit codes 0 and 1 are the gate's own (pass, fail); anything else is a usage, environment or timeout
        // error the results may not show as a failing module.
        boolean anyFailure = cases.stream().anyMatch(c -> c.outcome().kind() == Outcome.Kind.FAIL);
        if (run.exitCode() != 0 && run.exitCode() != 1 && !anyFailure) {
            cases.add(rows.failure("Runner", "conformance runner exited with code " + run.exitCode(),
                    withLogTail(context, run)));
        }
        return cases;
    }

    private List<ConformanceCase> fromResults(
            Rows rows, ConformanceSettings settings, Path resultsFile, List<String> context) {
        ConformanceResults results;
        try {
            results = reader.read(resultsFile);
        } catch (ResultsFormatException e) {
            return List.of(rows.failure("Results", "conformance results unreadable: " + e.getMessage(), context));
        }
        if (!results.component().equals(settings.component())) {
            return List.of(rows.failure("Results", "results file " + results.source() + " is for component "
                    + results.component() + ", but this rig tests " + settings.component(), context));
        }
        if (results.modules().isEmpty()) {
            return List.of(rows.failure("Results", "results file " + results.source()
                    + " lists no test modules for plan " + results.planName(), context));
        }

        Map<String, Integer> nameCounts = new HashMap<>();
        results.modules().forEach(m -> nameCounts.merge(m.name(), 1, Integer::sum));

        List<ConformanceCase> cases = new ArrayList<>();
        for (int i = 0; i < results.modules().size(); i++) {
            ModuleResult module = results.modules().get(i);
            Outcome mapped = mapper.map(results, module);
            List<String> details = new ArrayList<>(context);
            details.addAll(mapped.details());
            String name = nameCounts.get(module.name()) > 1 ? module.name() + variantSuffix(module) : module.name();
            cases.add(new ConformanceCase(
                    rows.id(i + 1),
                    rows.name(name),
                    describe(results, module),
                    targetOf(results, settings),
                    new Outcome(mapped.kind(), mapped.message(), details)));
        }

        boolean anyFailure = cases.stream().anyMatch(c -> c.outcome().kind() == Outcome.Kind.FAIL);
        if (results.gating() && !results.gatePassed() && !anyFailure) {
            String messages = results.gateMessages().isEmpty() ? "no gate messages"
                    : String.join("; ", results.gateMessages());
            cases.add(rows.failure("Gate", "conformance gate failed: " + messages, context));
        }
        return cases;
    }

    private static String describe(ConformanceResults results, ModuleResult module) {
        String what = module.description() == null || module.description().isBlank()
                ? "Conformance suite test module " + module.name()
                : module.description();
        return what + " [" + results.planName() + "]";
    }

    private static String targetOf(ConformanceResults results, ConformanceSettings settings) {
        return results.targetBaseUrl() != null ? results.targetBaseUrl() : settings.target();
    }

    private static String variantSuffix(ModuleResult module) {
        if (module.variant().isEmpty()) {
            return "";
        }
        StringBuilder suffix = new StringBuilder();
        module.variant().values().forEach(value -> suffix.append('_').append(value));
        return suffix.toString();
    }

    private static List<String> withLogTail(List<String> context, RunnerInvoker.Invocation run) {
        List<String> lines = new ArrayList<>(context);
        List<String> tail = RunnerInvoker.tail(run.logFile(), LOG_TAIL_LINES);
        if (!tail.isEmpty()) {
            lines.add("Last " + tail.size() + " lines of the runner log:");
            lines.addAll(tail);
        }
        return lines;
    }

    /** Builds ids and names in one rig's scheme. */
    private record Rows(ConformanceSettings settings, String rigPrefix) {
        String id(int position) {
            return String.format(Locale.ROOT, "TC_OIDF_%s_%02d", settings.component().toUpperCase(Locale.ROOT),
                    position);
        }

        String name(String suffix) {
            return rigPrefix + "_OpenIDConformance_" + suffix;
        }

        ConformanceCase single(String suffix, String description, Outcome outcome) {
            return new ConformanceCase(id(0), name(suffix), description, settings.target(), outcome);
        }

        ConformanceCase failure(String suffix, String message, List<String> details) {
            return single(suffix, "OpenID conformance run of " + settings.component() + ": " + suffix.toLowerCase(
                    Locale.ROOT) + " problem", new Outcome(Outcome.Kind.FAIL, message, details));
        }
    }
}
