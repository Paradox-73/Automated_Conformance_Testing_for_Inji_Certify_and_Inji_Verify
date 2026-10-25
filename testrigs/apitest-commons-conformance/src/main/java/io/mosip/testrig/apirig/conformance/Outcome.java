// SPDX-License-Identifier: MPL-2.0
package io.mosip.testrig.apirig.conformance;

import java.util.List;
import java.util.Objects;

/**
 * The TestNG result one conformance row gets, before it is turned into a TestNG pass, failure or skip.
 *
 * <p>Keeping this step free of TestNG makes the verdict table testable on its own; {@code ConformanceTestSupport}
 * does the conversion.
 *
 * @param kind    which TestNG result, and for skips which {@code EmailableReport} column
 * @param message the failure or skip message; {@code null} for {@link Kind#PASS}
 * @param details plain-text lines for the report row (suite log link, failures, benchmark entries, evidence)
 */
public record Outcome(Kind kind, String message, List<String> details) {

    /** TestNG result kinds, named after the {@code EmailableReport} column the row lands in. */
    public enum Kind {
        /** TestNG pass (column P). */
        PASS,
        /** TestNG failure (column F); fails the rig run. */
        FAIL,
        /** Skip whose message holds the whole {@code GlobalConstants.KNOWN_ISSUES} text (column KI). */
        KNOWN_ISSUE,
        /** Skip whose message holds {@code GlobalConstants.FEATURE_NOT_SUPPORTED} (column I). */
        IGNORED,
        /** Plain skip (column S); used for results that must not gate, such as the HAIP readiness track. */
        SKIP
    }

    public Outcome {
        Objects.requireNonNull(kind, "kind");
        details = details == null ? List.of() : List.copyOf(details);
    }
}
