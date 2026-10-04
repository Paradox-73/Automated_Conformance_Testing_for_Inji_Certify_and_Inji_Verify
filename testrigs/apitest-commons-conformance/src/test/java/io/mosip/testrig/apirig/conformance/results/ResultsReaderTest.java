// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance.results;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import io.mosip.testrig.apirig.conformance.Fixtures;

class ResultsReaderTest {

    private final ResultsReader reader = new ResultsReader();

    @Test
    void readsTheVerifyExample() throws Exception {
        ConformanceResults results = reader.read(Fixtures.example("results-verify.example.json"));

        assertEquals("verify", results.component());
        assertEquals("gate", results.track());
        assertTrue(results.gating());
        assertTrue(results.gatePassed());
        assertFalse(results.allowStale());
        assertEquals("oid4vp-1final-verifier-test-plan", results.planName());
        assertEquals("x509_san_dns", results.planVariant().get("client_id_prefix"));
        assertEquals(11, results.modules().size());

        ModuleResult happy = results.modules().get(0);
        assertEquals("oid4vp-1final-verifier-happy-flow", happy.name());
        assertEquals(Verdict.CONFORMS, happy.verdict());
        assertEquals("REVIEW", happy.result());
        assertNotNull(happy.description());
        assertEquals("valid", happy.review().observed());
        assertEquals(2, happy.handoffs().size());
        assertEquals(200, happy.handoffs().get(0).httpStatus());
        assertTrue(happy.suiteLogUrl().endsWith("log=vpexample0001"));
        assertEquals("exports/vpexample0001.html", happy.exportPath());

        ModuleResult gap = results.modules().get(2);
        assertEquals(Verdict.KNOWN_GAP, gap.verdict());
        assertEquals(Boolean.TRUE, gap.failures().get(0).expected());
        assertEquals("docs/findings/verify-request-uri-method-post.md", gap.benchmark().get(0).issue());
        assertTrue(gap.benchmark().get(0).matched());
        assertNull(gap.review());
    }

    @Test
    void readsTheRegressionExample() throws Exception {
        ConformanceResults results = reader.read(Fixtures.example("results-verify-regression.example.json"));

        assertFalse(results.gatePassed());
        long regressions = results.modules().stream().filter(m -> m.verdict() == Verdict.REGRESSION).count();
        assertEquals(1, regressions);
    }

    @Test
    void readsTheCertifyExampleWithExpectedSkips() throws Exception {
        ConformanceResults results = reader.read(Fixtures.example("results-certify.example.json"));

        assertEquals("certify", results.component());
        assertEquals(15, results.modules().size());
        assertEquals(4, results.modules().stream().filter(m -> m.verdict() == Verdict.NOT_APPLICABLE).count());
    }

    @Test
    void rejectsAnUnknownVerdictWithItsJsonPath() {
        ResultsFormatException e = assertThrows(ResultsFormatException.class,
                () -> reader.read(Fixtures.example("results-unknown-verdict.invalid.json")));
        assertTrue(e.getMessage().contains("$.modules["), e.getMessage());
        assertTrue(e.getMessage().contains("verdict"), e.getMessage());
    }

    @Test
    void rejectsAnotherSchemaVersion(@TempDir Path dir) throws Exception {
        Path file = Fixtures.editedExample(dir, "results-verify.example.json",
                text -> text.replace("\"schema_version\": \"1\"", "\"schema_version\": \"2\""));
        ResultsFormatException e = assertThrows(ResultsFormatException.class, () -> reader.read(file));
        assertTrue(e.getMessage().contains("$.schema_version"), e.getMessage());
    }

    @Test
    void rejectsAnUnknownComponent(@TempDir Path dir) throws Exception {
        Path file = Fixtures.editedExample(dir, "results-verify.example.json",
                text -> text.replace("\"component\": \"verify\"", "\"component\": \"mimoto\""));
        ResultsFormatException e = assertThrows(ResultsFormatException.class, () -> reader.read(file));
        assertTrue(e.getMessage().contains("$.component"), e.getMessage());
    }

    @Test
    void reportsAMissingFile(@TempDir Path dir) {
        ResultsFormatException e = assertThrows(ResultsFormatException.class,
                () -> reader.read(dir.resolve("absent.json")));
        assertTrue(e.getMessage().startsWith("results file not found"), e.getMessage());
    }

    @Test
    void reportsBrokenJson(@TempDir Path dir) throws Exception {
        Path file = dir.resolve("broken.json");
        Files.writeString(file, "{\"schema_version\": ");
        ResultsFormatException e = assertThrows(ResultsFormatException.class, () -> reader.read(file));
        assertTrue(e.getMessage().contains("is not valid JSON"), e.getMessage());
    }

    @Test
    void mapsEveryVerdictValue() {
        for (Verdict verdict : Verdict.values()) {
            assertEquals(verdict, Verdict.fromJson(verdict.json()).orElseThrow());
        }
        assertTrue(Verdict.fromJson("passed").isEmpty());
    }
}
