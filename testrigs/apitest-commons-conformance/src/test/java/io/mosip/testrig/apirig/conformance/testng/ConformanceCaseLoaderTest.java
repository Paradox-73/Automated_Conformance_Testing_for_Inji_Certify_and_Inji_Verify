// SPDX-License-Identifier: MPL-2.0
package io.mosip.testrig.apirig.conformance.testng;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import io.mosip.testrig.apirig.conformance.Fixtures;
import io.mosip.testrig.apirig.conformance.Outcome;
import io.mosip.testrig.apirig.conformance.runner.ConformanceSettings;
import io.mosip.testrig.apirig.conformance.runner.RunnerInvokerTest;
import io.mosip.testrig.apirig.utils.GlobalConstants;

class ConformanceCaseLoaderTest {

    private final ConformanceCaseLoader loader = new ConformanceCaseLoader();

    private static ConformanceSettings consume(Path results) {
        return new ConformanceSettings("verify", results, null, "https://verify.inji.test:18451", Path.of("out"),
                Duration.ofMinutes(1));
    }

    private static ConformanceSettings invoke(String command, Path out) {
        return new ConformanceSettings("verify", null, command, "https://verify.inji.test:18451", out,
                Duration.ofMinutes(2));
    }

    private static long count(List<ConformanceCase> cases, Outcome.Kind kind) {
        return cases.stream().filter(c -> c.outcome().kind() == kind).count();
    }

    @Test
    void notConfiguredGivesOneIgnoredRow() throws Exception {
        ConformanceSettings settings = ConformanceSettings.from("verify", Map.<String, String>of()::get,
                Map.<String, String>of()::get);
        List<ConformanceCase> cases = loader.load(settings, "InjiVerify");

        assertEquals(1, cases.size());
        ConformanceCase row = cases.get(0);
        assertEquals("TC_OIDF_VERIFY_00", row.uniqueIdentifier());
        assertEquals("InjiVerify_OpenIDConformance_NotConfigured", row.testCaseName());
        assertEquals(Outcome.Kind.IGNORED, row.outcome().kind());
        assertTrue(row.outcome().message().startsWith("feature not supported: conformance runner not configured"));
    }

    @Test
    void consumeModeGivesOneRowPerModuleInPlanOrder() throws Exception {
        List<ConformanceCase> cases = loader.load(consume(Fixtures.example("results-verify.example.json")),
                "InjiVerify");

        assertEquals(11, cases.size());
        assertEquals("TC_OIDF_VERIFY_01", cases.get(0).uniqueIdentifier());
        assertEquals("TC_OIDF_VERIFY_11", cases.get(10).uniqueIdentifier());
        assertEquals("InjiVerify_OpenIDConformance_oid4vp-1final-verifier-happy-flow", cases.get(0).testCaseName());
        assertTrue(cases.get(0).description().startsWith("The suite acts as a wallet"));
        assertTrue(cases.get(0).description().endsWith("[oid4vp-1final-verifier-test-plan]"));
        assertTrue(cases.get(1).description().startsWith("Conformance suite test module"));
        assertEquals("https://verify.inji.test:18451/v1/verify", cases.get(0).target());
        assertEquals(10, count(cases, Outcome.Kind.PASS));
        assertEquals(1, count(cases, Outcome.Kind.KNOWN_ISSUE));
        assertTrue(cases.get(2).outcome().message().startsWith(GlobalConstants.KNOWN_ISSUES));
        assertTrue(cases.get(0).outcome().details().get(0).startsWith("Results source: consume mode"));
    }

    @Test
    void theRegressionExampleHasExactlyOneFailingRow() throws Exception {
        List<ConformanceCase> cases = loader.load(
                consume(Fixtures.example("results-verify-regression.example.json")), "InjiVerify");

        assertEquals(11, cases.size());
        assertEquals(1, count(cases, Outcome.Kind.FAIL));
    }

    @Test
    void aFailedGateWithoutAFailingModuleAddsAGateRow(@TempDir Path dir) throws Exception {
        Path results = Fixtures.editedExample(dir, "results-verify.example.json",
                text -> text.replace("\"passed\": true", "\"passed\": false"));
        List<ConformanceCase> cases = loader.load(consume(results), "InjiVerify");

        assertEquals(12, cases.size());
        ConformanceCase gate = cases.get(11);
        assertEquals("InjiVerify_OpenIDConformance_Gate", gate.testCaseName());
        assertEquals(Outcome.Kind.FAIL, gate.outcome().kind());
        assertTrue(gate.outcome().message().startsWith("conformance gate failed: gate: 0 regressions"));
    }

    @Test
    void resultsOfTheOtherComponentFail() throws Exception {
        List<ConformanceCase> cases = loader.load(consume(Fixtures.example("results-certify.example.json")),
                "InjiVerify");

        assertEquals(1, cases.size());
        assertEquals(Outcome.Kind.FAIL, cases.get(0).outcome().kind());
        assertTrue(cases.get(0).outcome().message().contains("is for component certify"));
    }

    @Test
    void unreadableResultsFail() throws Exception {
        List<ConformanceCase> cases = loader.load(
                consume(Fixtures.example("results-unknown-verdict.invalid.json")), "InjiVerify");

        assertEquals(1, cases.size());
        assertEquals("InjiVerify_OpenIDConformance_Results", cases.get(0).testCaseName());
        assertTrue(cases.get(0).outcome().message().startsWith("conformance results unreadable"));
    }

    @Test
    void invokeModeReadsWhatTheRunnerWrote(@TempDir Path out) throws Exception {
        Path example = Fixtures.example("results-verify-regression.example.json").toAbsolutePath();
        List<ConformanceCase> cases = loader.load(invoke(
                RunnerInvokerTest.fakeRunner("copy \"" + example + "\" {out} {component} 1"), out), "InjiVerify");

        assertEquals(11, cases.size());
        assertEquals(1, count(cases, Outcome.Kind.FAIL));
        assertTrue(cases.get(0).outcome().details().get(1).startsWith("Runner exit code 1"),
                cases.get(0).outcome().details().get(1));
    }

    @Test
    void anEnvironmentErrorExitCodeFailsEvenWithPassingResults(@TempDir Path out) throws Exception {
        Path example = Fixtures.example("results-verify.example.json").toAbsolutePath();
        List<ConformanceCase> cases = loader.load(invoke(
                RunnerInvokerTest.fakeRunner("copy \"" + example + "\" {out} {component} 3"), out), "InjiVerify");

        assertEquals(12, cases.size());
        assertEquals("conformance runner exited with code 3", cases.get(11).outcome().message());
    }

    @Test
    void aRunnerWithoutResultsFailsWithItsLog(@TempDir Path out) throws Exception {
        List<ConformanceCase> cases = loader.load(invoke(RunnerInvokerTest.fakeRunner("fail 3"), out),
                "InjiVerify");

        assertEquals(1, cases.size());
        Outcome outcome = cases.get(0).outcome();
        assertEquals(Outcome.Kind.FAIL, outcome.kind());
        assertTrue(outcome.message().startsWith("conformance runner exited with code 3 without writing"));
        assertTrue(outcome.details().contains("environment not ready: suite not reachable"),
                String.join("\n", outcome.details()));
    }

    @Test
    void aRunnerThatCannotStartFails(@TempDir Path out) throws Exception {
        List<ConformanceCase> cases = loader.load(invoke("no-such-program-for-conformance-tests", out),
                "InjiVerify");

        assertEquals(1, cases.size());
        assertTrue(cases.get(0).outcome().message().startsWith("conformance runner could not start"));
    }
}
