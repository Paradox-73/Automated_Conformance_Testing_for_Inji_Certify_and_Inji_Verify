// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

import io.mosip.testrig.apirig.conformance.results.ConformanceResults;
import io.mosip.testrig.apirig.conformance.results.ModuleResult;
import io.mosip.testrig.apirig.conformance.results.ResultsReader;
import io.mosip.testrig.apirig.conformance.results.Verdict;
import io.mosip.testrig.apirig.utils.GlobalConstants;

class OutcomeMapperTest {

    private final OutcomeMapper mapper = new OutcomeMapper();

    @Test
    void conformsIsAPassWithTheSuiteLogInTheDetails() throws Exception {
        ConformanceResults results = read("results-verify.example.json");
        Outcome outcome = mapper.map(results, results.modules().get(0));

        assertEquals(Outcome.Kind.PASS, outcome.kind());
        assertNull(outcome.message());
        assertTrue(outcome.details().stream().anyMatch(line -> line.startsWith("Suite log: https://")),
                String.join("\n", outcome.details()));
        assertTrue(outcome.details().stream().anyMatch(line -> line.startsWith("Checked REVIEW: expected valid")));
    }

    @Test
    void knownGapCarriesTheWholeKnownIssuesTextAndTheIssue() throws Exception {
        ConformanceResults results = read("results-verify.example.json");
        Outcome outcome = mapper.map(results, results.modules().get(2));

        assertEquals(Outcome.Kind.KNOWN_ISSUE, outcome.kind());
        // EmailableReport counts a KI row as a plain skip too unless the whole constant is present.
        assertTrue(outcome.message().startsWith(GlobalConstants.KNOWN_ISSUES), outcome.message());
        assertTrue(outcome.message().contains("PostToRequestUriAndExtractRequestObject"));
        assertTrue(outcome.message().contains("issue docs/findings/verify-request-uri-method-post.md"));
        assertTrue(outcome.message().contains("spec OID4VP-1FINAL-5.10"));
    }

    @Test
    void regressionFailsWithTheRunnersReason() throws Exception {
        ConformanceResults results = read("results-verify-regression.example.json");
        ModuleResult module = results.modules().stream()
                .filter(m -> m.verdict() == Verdict.REGRESSION).findFirst().orElseThrow();
        Outcome outcome = mapper.map(results, module);

        assertEquals(Outcome.Kind.FAIL, outcome.kind());
        assertTrue(outcome.message().startsWith("regression: Inji Verify reported the presentation as valid"),
                outcome.message());
    }

    @Test
    void notApplicableIsIgnored() throws Exception {
        ConformanceResults results = read("results-certify.example.json");
        ModuleResult module = results.modules().stream()
                .filter(m -> m.verdict() == Verdict.NOT_APPLICABLE).findFirst().orElseThrow();
        Outcome outcome = mapper.map(results, module);

        assertEquals(Outcome.Kind.IGNORED, outcome.kind());
        assertTrue(outcome.message().startsWith(GlobalConstants.FEATURE_NOT_SUPPORTED), outcome.message());
        assertFalse(outcome.message().contains(GlobalConstants.KNOWN_ISSUES_STRING));
    }

    @Test
    void regressionWithoutReasonListsTheUnlistedConditions() {
        ModuleResult module = module(Verdict.REGRESSION, null, List.of(
                new ModuleResult.Failure("CheckNonce", "FAILURE", "nonce reused", "", List.of(), false),
                new ModuleResult.Failure("CheckAud", "WARNING", "aud odd", "", List.of(), true)));
        Outcome outcome = mapper.map(results(true, false), module);

        assertEquals(Outcome.Kind.FAIL, outcome.kind());
        assertEquals("regression: conditions not in the benchmark: FAILURE CheckNonce", outcome.message());
    }

    @Test
    void staleBenchmarkFailsUnlessTheRunAllowedStaleEntries() {
        ModuleResult module = module(Verdict.STALE_BENCHMARK, "a listed failure did not occur", List.of(),
                List.of(new ModuleResult.BenchmarkEntry("expected_failure", "CheckNonce",
                        "Inji Verify did not check the nonce before 1.0.1", "inji", "OID4VP-1FINAL-14.1",
                        "docs/findings/x.md", false)));

        Outcome strict = mapper.map(results(true, false), module);
        assertEquals(Outcome.Kind.FAIL, strict.kind());
        assertTrue(strict.message().contains("remove the benchmark entry"), strict.message());
        assertTrue(strict.message().contains("CheckNonce"), strict.message());

        Outcome allowed = mapper.map(results(true, true), module);
        assertEquals(Outcome.Kind.PASS, allowed.kind());
        assertTrue(allowed.details().get(0).startsWith("WARNING (run used --allow-stale)"));
    }

    @Test
    void nonGatingResultsNeverFail() {
        ModuleResult module = module(Verdict.REGRESSION, "suite timed out", List.of());
        Outcome outcome = mapper.map(results(false, false), module);

        assertEquals(Outcome.Kind.SKIP, outcome.kind());
        assertTrue(outcome.message().startsWith("not gating (haip track), would fail: regression: suite timed out"),
                outcome.message());
        assertFalse(outcome.message().contains(GlobalConstants.KNOWN_ISSUES_STRING));
        assertFalse(outcome.message().contains(GlobalConstants.FEATURE_NOT_SUPPORTED));
    }

    private static ConformanceResults read(String example) throws Exception {
        return new ResultsReader().read(Fixtures.example(example));
    }

    private static ModuleResult module(Verdict verdict, String reason, List<ModuleResult.Failure> failures) {
        return module(verdict, reason, failures, List.of());
    }

    private static ModuleResult module(Verdict verdict, String reason, List<ModuleResult.Failure> failures,
            List<ModuleResult.BenchmarkEntry> benchmark) {
        return new ModuleResult("oid4vp-1final-verifier-invalid-kb-jwt-nonce", "t1", null, Map.of(), "FINISHED",
                "FAILED", verdict, reason, failures, benchmark, null, List.of(), null, null, null);
    }

    private static ConformanceResults results(boolean gating, boolean allowStale) {
        return new ConformanceResults(Path.of("results.json"), "20261004T193000Z-x", "verify",
                gating ? "gate" : "haip", gating, "https://suite.test", "5.3.1", "https://verify.test",
                "oid4vp-1final-verifier-test-plan", "p1", Map.of(), List.of(), false, allowStale, List.of());
    }
}
