// SPDX-License-Identifier: MPL-2.0
package io.mosip.testrig.apirig.conformance.testng;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;

import org.testng.Reporter;
import org.testng.SkipException;

import io.mosip.testrig.apirig.conformance.Outcome;
import io.mosip.testrig.apirig.conformance.runner.ConformanceSettings;
import io.mosip.testrig.apirig.dto.TestCaseDTO;

/**
 * What a rig's {@code OpenIDConformanceTest} delegates to: the data provider rows and the per-row check.
 *
 * <p>A rig class keeps the shape of every other rig script ({@code ITest}, a {@code testcaselist} data provider,
 * one {@code @Test} method taking a {@link TestCaseDTO}, an {@code @AfterMethod} that names the row) and calls
 * {@link #testCases()} and {@link #check(TestCaseDTO)}. Passing {@code TestCaseDTO} objects is what makes
 * {@code EmailableReport} show each row as {@code <uniqueIdentifier> # <description>}.
 *
 * <p>Results are loaded once per instance, on the first {@link #testCases()} call; in invoke mode that is when the
 * conformance runner runs.
 */
public final class ConformanceTestSupport {

    private final String rigPrefix;
    private final Supplier<ConformanceSettings> settings;
    private final ConformanceCaseLoader loader;
    private Map<String, ConformanceCase> cases;

    /**
     * Support for one rig, configured from system properties and environment variables.
     *
     * @param component {@code certify} or {@code verify}
     * @param rigPrefix test case name prefix of the rig, for example {@code InjiVerify}
     */
    public ConformanceTestSupport(String component, String rigPrefix) {
        this(rigPrefix, () -> ConformanceSettings.fromEnvironment(component), new ConformanceCaseLoader());
    }

    ConformanceTestSupport(String rigPrefix, Supplier<ConformanceSettings> settings, ConformanceCaseLoader loader) {
        this.rigPrefix = Objects.requireNonNull(rigPrefix, "rigPrefix");
        this.settings = Objects.requireNonNull(settings, "settings");
        this.loader = Objects.requireNonNull(loader, "loader");
    }

    /**
     * The data provider rows: one {@link TestCaseDTO} per conformance test module, or one explaining row.
     *
     * @throws IllegalStateException when the thread is interrupted while the runner runs
     */
    public synchronized Object[] testCases() {
        if (cases == null) {
            List<ConformanceCase> loaded;
            try {
                loaded = loader.load(settings.get(), rigPrefix);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted while the conformance runner was running", e);
            }
            Map<String, ConformanceCase> byId = new LinkedHashMap<>();
            loaded.forEach(c -> byId.put(c.uniqueIdentifier(), c));
            cases = byId;
        }
        return cases.values().stream().map(ConformanceTestSupport::toTestCase).toArray();
    }

    /**
     * Turns one row into its TestNG result: returns for a pass, throws {@link AssertionError} for a failure and
     * {@link SkipException} for Known Issue, Ignored and plain skip rows. The row's details go to the report first.
     */
    public void check(TestCaseDTO testCase) {
        ConformanceCase row = cases == null ? null : cases.get(testCase.getUniqueIdentifier());
        if (row == null) {
            throw new AssertionError("no conformance result for test case " + testCase.getUniqueIdentifier()
                    + " (" + testCase.getTestCaseName() + ")");
        }
        Outcome outcome = row.outcome();
        outcome.details().forEach(line -> Reporter.log(ReportText.line(line, Reporter.getEscapeHtml())));
        switch (outcome.kind()) {
            case PASS -> {
                // A pass needs no exception; the details above are the evidence.
            }
            case FAIL -> throw new AssertionError(outcome.message());
            case KNOWN_ISSUE, IGNORED, SKIP -> throw new SkipException(outcome.message());
        }
    }

    /** The report row for {@code row}: name, id, description and the target as the end point. */
    static TestCaseDTO toTestCase(ConformanceCase row) {
        TestCaseDTO dto = new TestCaseDTO();
        dto.setTestCaseName(row.testCaseName());
        dto.setUniqueIdentifier(row.uniqueIdentifier());
        dto.setDescription(row.description());
        dto.setEndPoint(row.target());
        dto.setRestMethod("conformance");
        return dto;
    }
}
