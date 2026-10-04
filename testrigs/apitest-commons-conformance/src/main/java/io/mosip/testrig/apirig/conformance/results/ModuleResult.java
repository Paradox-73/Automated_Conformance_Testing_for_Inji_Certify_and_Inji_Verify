// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance.results;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * One conformance test module of a {@code results.json} file (the {@code modules[]} items of results.schema.json).
 *
 * @param name          suite test module name, for example {@code oid4vp-1final-verifier-happy-flow}
 * @param testId        suite test id; {@code null} when the module never started
 * @param description   the suite's summary of the module; {@code null} when the runner did not record one
 * @param variant       variant selections of this module (may be empty)
 * @param status        last suite status, for example {@code FINISHED} or {@code INTERRUPTED}
 * @param result        suite result ({@code PASSED}, {@code FAILED}, {@code WARNING}, {@code REVIEW},
 *                      {@code SKIPPED}, {@code UNKNOWN}); {@code null} while the module has none
 * @param verdict       the runner's verdict; the bridge maps it and never re-classifies
 * @param verdictReason one line on why; the runner writes it for regressions and stale benchmark entries
 * @param failures      every FAILURE and WARNING log entry of the module
 * @param benchmark     benchmark entries that apply to this module, with whether each matched
 * @param review        checked outcome of a module the suite ends in REVIEW; {@code null} otherwise
 * @param handoffs      steps the harness performed where the suite waits for a person or the system under test
 * @param suiteLogUrl   live log page on the suite; {@code null} when not recorded
 * @param exportPath    extracted HTML export, relative to the run folder; {@code null} when not recorded
 * @param durationSeconds module run time; {@code null} when not measured
 */
public record ModuleResult(
        String name,
        String testId,
        String description,
        Map<String, String> variant,
        String status,
        String result,
        Verdict verdict,
        String verdictReason,
        List<Failure> failures,
        List<BenchmarkEntry> benchmark,
        Review review,
        List<Handoff> handoffs,
        String suiteLogUrl,
        String exportPath,
        Double durationSeconds) {

    public ModuleResult {
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(verdict, "verdict");
        variant = variant == null ? Map.of() : Collections.unmodifiableMap(new LinkedHashMap<>(variant));
        failures = failures == null ? List.of() : List.copyOf(failures);
        benchmark = benchmark == null ? List.of() : List.copyOf(benchmark);
        handoffs = handoffs == null ? List.of() : List.copyOf(handoffs);
    }

    /**
     * A FAILURE or WARNING log entry of the module.
     *
     * @param condition    suite condition class, for example {@code PostToRequestUriAndExtractRequestObject}
     * @param severity     {@code FAILURE} or {@code WARNING}
     * @param message      the suite's message; may be {@code null}
     * @param block        title of the block the condition ran in; may be {@code null}
     * @param requirements specification requirement ids the suite links to the condition
     * @param expected     {@code true} when a benchmark entry lists this condition; {@code null} when unknown
     */
    public record Failure(
            String condition, String severity, String message, String block, List<String> requirements,
            Boolean expected) {
        public Failure {
            requirements = requirements == null ? List.of() : List.copyOf(requirements);
        }
    }

    /**
     * A benchmark entry (expected failure or expected skip) copied into the results by the runner.
     *
     * @param kind      {@code expected_failure} or {@code expected_skip}
     * @param condition the listed condition; {@code null} for an expected skip
     * @param comment   why the problem is expected
     * @param owner     who has to act: {@code inji}, {@code suite} or {@code environment}
     * @param spec      the specification clause the entry is about
     * @param issue     link or path of the issue draft that tracks it
     * @param matched   {@code false} when the listed problem did not occur in this run (a stale entry)
     */
    public record BenchmarkEntry(
            String kind, String condition, String comment, String owner, String spec, String issue, boolean matched) {
    }

    /**
     * Checked outcome of a REVIEW module: what Inji Verify showed, compared with what the module expects.
     *
     * @param expected {@code valid} or {@code invalid}
     * @param observed {@code valid}, {@code invalid} or {@code missing}
     * @param evidence image uploaded to the suite, relative to the run folder; {@code null} when none was made
     */
    public record Review(String expected, String observed, String evidence) {
    }

    /**
     * One handoff the harness performed, for example delivering Inji Verify's authorization request to the suite.
     *
     * @param kind       handoff kind, for example {@code authorization_request}
     * @param httpStatus status of the HTTP call that delivered it; {@code null} when no response arrived
     * @param durationMs how long it took
     * @param detail     what was done; may be {@code null}
     * @param error      what went wrong; {@code null} when nothing did
     */
    public record Handoff(String kind, Integer httpStatus, double durationMs, String detail, String error) {
    }
}
