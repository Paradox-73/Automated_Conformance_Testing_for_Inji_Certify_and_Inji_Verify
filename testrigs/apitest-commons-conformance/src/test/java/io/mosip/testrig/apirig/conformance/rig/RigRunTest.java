// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance.rig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import io.mosip.testrig.apirig.conformance.Fixtures;

class RigRunTest {

    private static Path reportDir(Map<String, String> properties, Map<String, String> environment) {
        return RigRun.reportDir("injiverify", properties::get, environment::get);
    }

    @Test
    void reportDirComesFromThePropertyThenTheRunFolderThenTheWorkingDirectory(@TempDir Path dir) {
        Path explicit = dir.resolve("wp11");
        assertEquals(explicit, reportDir(Map.of(RigRun.REPORT_DIR, explicit.toString()),
                Map.of("HARNESS_RUN_DIR", "/elsewhere")));
        assertEquals(explicit, reportDir(Map.of(), Map.of("CONFORMANCE_REPORT_DIR", explicit.toString())));
        assertEquals(dir.resolve("testrig").resolve("injiverify"),
                reportDir(Map.of(), Map.of("HARNESS_RUN_DIR", dir.toString())));
        assertEquals(dir.resolve("testng-report").resolve("conformance"),
                reportDir(Map.of("user.dir", dir.toString()), Map.of()));
    }

    @Test
    void outputDirIsRelativeToTheWorkingDirectory(@TempDir Path dir) {
        Path rig = dir.resolve("repo").resolve("testrigs").resolve("inji-verify-api-test");
        Path report = dir.resolve("run").resolve("harness").resolve("wp11");

        assertEquals("../../../run/harness/wp11", RigRun.relativeOutputDir(rig, report));
        assertEquals(".", RigRun.relativeOutputDir(rig, rig));
    }

    @Test
    void outputDirOnAnotherDriveIsRefused() {
        if (!System.getProperty("os.name").toLowerCase(java.util.Locale.ROOT).contains("windows")) {
            return; // Only Windows paths can have different roots.
        }
        IllegalArgumentException e = assertThrows(IllegalArgumentException.class,
                () -> RigRun.relativeOutputDir(Path.of("C:\\rig"), Path.of("D:\\report")));
        assertTrue(e.getMessage().contains("same drive"));
    }

    @Test
    void exitCodeFollowsTestNgResults() throws IOException {
        TestNgResults pass = TestNgResults.read(Fixtures.OWN.resolve("testng-results-pass.xml"));
        assertEquals(11, pass.total());
        assertEquals(10, pass.passed());
        assertEquals(1, pass.skipped());
        assertEquals(TestNgResults.EXIT_OK, pass.exitCode());

        TestNgResults fail = TestNgResults.read(Fixtures.OWN.resolve("testng-results-fail.xml"));
        assertEquals(TestNgResults.EXIT_FAILED, fail.exitCode());
        assertTrue(fail.summary().contains("failed 1"), fail.summary());

        TestNgResults config = TestNgResults.read(Fixtures.OWN.resolve("testng-results-config-fail.xml"));
        assertEquals(0, config.failed());
        assertEquals(TestNgResults.EXIT_FAILED, config.exitCode());
        assertTrue(config.failedMethods().contains("setUp (configuration)"));
    }

    @Test
    void missingOrForeignResultsAreAnError(@TempDir Path dir) {
        assertThrows(IOException.class, () -> TestNgResults.read(dir.resolve("testng-results.xml")));
        assertThrows(IOException.class, () -> TestNgResults.read(Fixtures.example("results-verify.example.json")));
    }
}
