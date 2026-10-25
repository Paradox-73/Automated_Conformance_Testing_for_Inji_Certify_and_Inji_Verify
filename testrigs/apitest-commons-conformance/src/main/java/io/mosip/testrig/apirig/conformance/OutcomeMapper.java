// SPDX-License-Identifier: MPL-2.0
package io.mosip.testrig.apirig.conformance;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

import io.mosip.testrig.apirig.conformance.results.ConformanceResults;
import io.mosip.testrig.apirig.conformance.results.ModuleResult;
import io.mosip.testrig.apirig.utils.GlobalConstants;

/**
 * Maps a module's verdict to a TestNG outcome, following the verdict table in this library's README
 * ("Verdict mapping"):
 *
 * <table>
 * <caption>Verdict to TestNG row</caption>
 * <tr><th>verdict</th><th>TestNG row</th></tr>
 * <tr><td>conforms</td><td>pass</td></tr>
 * <tr><td>known_gap</td><td>skip filed under Known Issues (KI), with the benchmark reason and issue</td></tr>
 * <tr><td>not_applicable</td><td>skip filed under Ignored (I)</td></tr>
 * <tr><td>regression</td><td>failure with the runner's reason</td></tr>
 * <tr><td>stale_benchmark</td><td>failure asking to remove the entry; pass with a warning when the run allowed
 * stale entries</td></tr>
 * </table>
 *
 * <p>Results with {@code gating: false} (the HAIP readiness track) never fail a rig run: what would be a failure
 * becomes a plain skip (S) that still shows the reason.
 *
 * <p>{@code EmailableReport} sorts skips by message text: a message containing {@code "known issue"} goes under KI,
 * but it is also counted as a plain skip unless it contains the whole {@link GlobalConstants#KNOWN_ISSUES} text,
 * so KI messages start with that whole constant. Ignored messages start with
 * {@link GlobalConstants#FEATURE_NOT_SUPPORTED}.
 */
public final class OutcomeMapper {

    /** Maps one module of {@code results}. */
    public Outcome map(ConformanceResults results, ModuleResult module) {
        List<String> details = details(results, module);
        Outcome outcome = switch (module.verdict()) {
            case CONFORMS -> new Outcome(Outcome.Kind.PASS, null, details);
            case KNOWN_GAP -> new Outcome(Outcome.Kind.KNOWN_ISSUE,
                    GlobalConstants.KNOWN_ISSUES + ": " + knownGapReason(module), details);
            case NOT_APPLICABLE -> new Outcome(Outcome.Kind.IGNORED,
                    GlobalConstants.FEATURE_NOT_SUPPORTED + ": " + notApplicableReason(module), details);
            case REGRESSION -> new Outcome(Outcome.Kind.FAIL, "regression: " + regressionReason(module), details);
            case STALE_BENCHMARK -> staleBenchmark(results, module, details);
        };
        if (outcome.kind() == Outcome.Kind.FAIL && !results.gating()) {
            String track = results.track() == null ? "readiness" : results.track();
            return new Outcome(Outcome.Kind.SKIP,
                    "not gating (" + track + " track), would fail: " + outcome.message(), details);
        }
        return outcome;
    }

    private static Outcome staleBenchmark(ConformanceResults results, ModuleResult module, List<String> details) {
        String entries = module.benchmark().stream()
                .filter(entry -> !entry.matched())
                .map(OutcomeMapper::describeEntry)
                .collect(Collectors.joining("; "));
        String reason = firstNonBlank(module.verdictReason(), "a listed problem did not occur in this run");
        String message = "stale benchmark entry: " + reason
                + (entries.isEmpty() ? "" : " [" + entries + "]")
                + "; remove the benchmark entry or update it to what the suite reports now";
        if (results.allowStale()) {
            List<String> warned = new ArrayList<>(details);
            warned.add(0, "WARNING (run used --allow-stale): " + message);
            return new Outcome(Outcome.Kind.PASS, null, warned);
        }
        return new Outcome(Outcome.Kind.FAIL, message, details);
    }

    private static String knownGapReason(ModuleResult module) {
        String entries = module.benchmark().stream()
                .filter(ModuleResult.BenchmarkEntry::matched)
                .map(OutcomeMapper::describeEntry)
                .collect(Collectors.joining("; "));
        return firstNonBlank(entries, module.verdictReason(), "every problem is listed in the benchmark");
    }

    private static String notApplicableReason(ModuleResult module) {
        String entries = module.benchmark().stream()
                .filter(entry -> "expected_skip".equals(entry.kind()))
                .map(OutcomeMapper::describeEntry)
                .collect(Collectors.joining("; "));
        return "the suite skipped this module and the benchmark expects that: "
                + firstNonBlank(entries, module.verdictReason(), "no reason recorded");
    }

    private static String regressionReason(ModuleResult module) {
        if (module.verdictReason() != null && !module.verdictReason().isBlank()) {
            return module.verdictReason();
        }
        List<String> unlisted = module.failures().stream()
                .filter(failure -> !Boolean.TRUE.equals(failure.expected()))
                .map(failure -> failure.severity() + " " + failure.condition())
                .toList();
        if (!unlisted.isEmpty()) {
            return "conditions not in the benchmark: " + String.join(", ", unlisted);
        }
        return "suite status " + module.status() + ", result " + module.result();
    }

    private static String describeEntry(ModuleResult.BenchmarkEntry entry) {
        List<String> facts = new ArrayList<>();
        if (entry.owner() != null) {
            facts.add("owner " + entry.owner());
        }
        if (entry.spec() != null) {
            facts.add("spec " + entry.spec());
        }
        if (entry.issue() != null) {
            facts.add("issue " + entry.issue());
        }
        String subject = entry.condition() == null ? "" : entry.condition() + ": ";
        String comment = firstNonBlank(entry.comment(), "no comment");
        return subject + comment + (facts.isEmpty() ? "" : " (" + String.join(", ", facts) + ")");
    }

    /** Plain-text lines that explain the row: where it ran, what the suite said and which evidence exists. */
    static List<String> details(ConformanceResults results, ModuleResult module) {
        List<String> lines = new ArrayList<>();
        lines.add("Conformance test module " + module.name() + " of plan " + results.planName()
                + (results.planId() == null ? "" : " (plan id " + results.planId() + ")")
                + (module.testId() == null ? ", never started" : ", suite test id " + module.testId()));
        lines.add("Suite outcome: status " + module.status() + ", result " + module.result()
                + "; harness verdict: " + module.verdict().json());
        Map<String, String> variant = module.variant().isEmpty() ? results.planVariant() : module.variant();
        if (!variant.isEmpty()) {
            lines.add("Variant: " + variant.entrySet().stream()
                    .map(e -> e.getKey() + "=" + e.getValue())
                    .collect(Collectors.joining(", ")));
        }
        if (module.suiteLogUrl() != null) {
            lines.add("Suite log: " + module.suiteLogUrl());
        }
        if (module.exportPath() != null) {
            lines.add("Suite log export (in the run folder): " + module.exportPath());
        }
        for (ModuleResult.Failure failure : module.failures()) {
            String listed = Boolean.TRUE.equals(failure.expected()) ? " [in benchmark]" : "";
            String where = failure.block() == null || failure.block().isBlank() ? "" : " (block: " + failure.block() + ")";
            String reqs = failure.requirements().isEmpty() ? ""
                    : " requirements: " + String.join(", ", failure.requirements());
            lines.add(failure.severity().toUpperCase(Locale.ROOT) + " " + failure.condition() + listed + ": "
                    + firstNonBlank(failure.message(), "(no message)") + where + reqs);
        }
        for (ModuleResult.BenchmarkEntry entry : module.benchmark()) {
            lines.add("Benchmark " + entry.kind() + (entry.matched() ? " (matched)" : " (did not occur)") + ": "
                    + describeEntry(entry));
        }
        if (module.review() != null) {
            ModuleResult.Review review = module.review();
            lines.add("Checked REVIEW: expected " + review.expected() + ", observed " + review.observed()
                    + ", evidence " + firstNonBlank(review.evidence(), "none"));
        }
        for (ModuleResult.Handoff handoff : module.handoffs()) {
            String status = handoff.httpStatus() == null ? "no response" : "HTTP " + handoff.httpStatus();
            lines.add("Handoff " + handoff.kind() + ": " + status + " in " + Math.round(handoff.durationMs()) + " ms"
                    + (handoff.detail() == null ? "" : " - " + handoff.detail())
                    + (handoff.error() == null ? "" : " - error: " + handoff.error()));
        }
        if (module.durationSeconds() != null) {
            lines.add(String.format(Locale.ROOT, "Duration: %.1f s", module.durationSeconds()));
        }
        lines.add("Results: " + results.source() + (results.runId() == null ? "" : ", run " + results.runId()));
        return lines;
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return "";
    }
}
