// SPDX-License-Identifier: MPL-2.0
package io.mosip.testrig.apirig.conformance.runner;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;

class ConformanceSettingsTest {

    private static ConformanceSettings settings(Map<String, String> properties, Map<String, String> environment) {
        return ConformanceSettings.from("verify", properties::get, environment::get);
    }

    @Test
    void nothingSetMeansNotConfigured() {
        ConformanceSettings s = settings(Map.of("user.dir", "/rig"), Map.of());

        assertEquals(ConformanceSettings.Mode.NOT_CONFIGURED, s.mode());
        assertEquals(Path.of("/rig", "testng-report", "runner"), s.runnerOutDir());
        assertEquals(Duration.ofMinutes(ConformanceSettings.DEFAULT_TIMEOUT_MINUTES), s.runnerTimeout());
        assertTrue(s.describe().contains(ConformanceSettings.RESULTS_FILE));
    }

    @Test
    void aResultsFileSelectsConsumeModeEvenWithACommand() {
        ConformanceSettings s = settings(Map.of(
                ConformanceSettings.RESULTS_FILE, "results.json",
                ConformanceSettings.RUNNER_COMMAND, "inji-conformance run"), Map.of());

        assertEquals(ConformanceSettings.Mode.CONSUME, s.mode());
        assertEquals(Path.of("results.json"), s.resultsFile());
    }

    @Test
    void aCommandSelectsInvokeModeWithEnvEndpointAsTarget() {
        ConformanceSettings s = settings(Map.of(
                ConformanceSettings.RUNNER_COMMAND, "inji-conformance run --target {target}",
                "env.endpoint", "https://verify.inji.test:18451"), Map.of("HARNESS_RUN_DIR", "/run"));

        assertEquals(ConformanceSettings.Mode.INVOKE, s.mode());
        assertEquals("https://verify.inji.test:18451", s.target());
        assertEquals(Path.of("/run", "testrig", "runner"), s.runnerOutDir());
    }

    @Test
    void systemPropertiesWinOverEnvironmentAndBothSpellingsWork() {
        ConformanceSettings fromProperty = settings(
                Map.of(ConformanceSettings.TARGET, "https://property"),
                Map.of(ConformanceSettings.TARGET, "https://same-name", "CONFORMANCE_TARGET", "https://upper"));
        assertEquals("https://property", fromProperty.target());

        ConformanceSettings sameName = settings(Map.of(),
                Map.of(ConformanceSettings.TARGET, "https://same-name", "CONFORMANCE_TARGET", "https://upper"));
        assertEquals("https://same-name", sameName.target());

        ConformanceSettings upper = settings(Map.of(), Map.of("CONFORMANCE_RESULTS_FILE", " r.json "));
        assertEquals(Path.of("r.json"), upper.resultsFile());
    }

    @Test
    void blankValuesCountAsUnset() {
        ConformanceSettings s = settings(Map.of(ConformanceSettings.RESULTS_FILE, "  "), Map.of());
        assertNull(s.resultsFile());
        assertEquals(ConformanceSettings.Mode.NOT_CONFIGURED, s.mode());
    }

    @Test
    void readsTheTimeoutAndRejectsNonsense() {
        assertEquals(Duration.ofMinutes(5),
                settings(Map.of(ConformanceSettings.RUNNER_TIMEOUT_MINUTES, "5"), Map.of()).runnerTimeout());

        IllegalArgumentException e = assertThrows(IllegalArgumentException.class,
                () -> settings(Map.of(ConformanceSettings.RUNNER_TIMEOUT_MINUTES, "0"), Map.of()));
        assertTrue(e.getMessage().contains(ConformanceSettings.RUNNER_TIMEOUT_MINUTES));
        assertThrows(IllegalArgumentException.class,
                () -> settings(Map.of(ConformanceSettings.RUNNER_TIMEOUT_MINUTES, "ten"), Map.of()));
    }
}
