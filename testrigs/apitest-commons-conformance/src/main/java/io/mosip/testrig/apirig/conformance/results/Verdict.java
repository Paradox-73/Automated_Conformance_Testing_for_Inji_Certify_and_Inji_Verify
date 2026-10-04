// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance.results;

import java.util.Arrays;
import java.util.Optional;

/**
 * The harness verdict for one conformance test module, as the runner writes it in {@code results.json}.
 *
 * <p>The runner computes the verdict once from the suite's outcome and the benchmark (the list of expected failures
 * and skips). Every reader, this bridge included, maps the verdict and never re-classifies the suite outcome, so the
 * gate, the HTML report and the TestNG report always agree.
 */
public enum Verdict {
    /** The module passed, or a REVIEW module showed the expected result. */
    CONFORMS("conforms"),
    /** Every problem the module found is listed in the benchmark with a reason and an issue. */
    KNOWN_GAP("known_gap"),
    /** An unlisted problem, an unexpected skip, an interruption or a timeout. Fails the gate. */
    REGRESSION("regression"),
    /** The suite skipped the module and the benchmark lists that skip. */
    NOT_APPLICABLE("not_applicable"),
    /** A benchmark entry lists a problem that did not happen. Fails the gate unless the run allowed stale entries. */
    STALE_BENCHMARK("stale_benchmark");

    private final String json;

    Verdict(String json) {
        this.json = json;
    }

    /** The value used in {@code results.json}. */
    public String json() {
        return json;
    }

    /** Looks up a verdict by its {@code results.json} value; empty for an unknown value. */
    public static Optional<Verdict> fromJson(String value) {
        return Arrays.stream(values()).filter(v -> v.json.equals(value)).findFirst();
    }
}
