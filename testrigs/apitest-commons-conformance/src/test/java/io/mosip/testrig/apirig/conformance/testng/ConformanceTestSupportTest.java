// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance.testng;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.testng.SkipException;

import io.mosip.testrig.apirig.conformance.Fixtures;
import io.mosip.testrig.apirig.conformance.runner.ConformanceSettings;
import io.mosip.testrig.apirig.dto.TestCaseDTO;
import io.mosip.testrig.apirig.utils.GlobalConstants;

class ConformanceTestSupportTest {

    private static ConformanceTestSupport support(String example) {
        ConformanceSettings settings = new ConformanceSettings("verify", Fixtures.example(example), null,
                "https://verify.inji.test:18451", Path.of("out"), Duration.ofMinutes(1));
        return new ConformanceTestSupport("InjiVerify", () -> settings, new ConformanceCaseLoader());
    }

    private static List<TestCaseDTO> rows(ConformanceTestSupport support) {
        return Arrays.stream(support.testCases()).map(TestCaseDTO.class::cast).toList();
    }

    @Test
    void rowsAreTestCaseDtosWithIdNameAndDescription() {
        List<TestCaseDTO> rows = rows(support("results-verify.example.json"));

        assertEquals(11, rows.size());
        TestCaseDTO first = rows.get(0);
        assertEquals("TC_OIDF_VERIFY_01", first.getUniqueIdentifier());
        assertEquals("InjiVerify_OpenIDConformance_oid4vp-1final-verifier-happy-flow", first.getTestCaseName());
        assertTrue(first.getDescription().contains("presents a valid SD-JWT VC"));
        assertEquals("https://verify.inji.test:18451/v1/verify", first.getEndPoint());
    }

    @Test
    void checkPassesConformingRowsAndSkipsKnownGapsAsKnownIssues() {
        ConformanceTestSupport support = support("results-verify.example.json");
        List<TestCaseDTO> rows = rows(support);

        assertDoesNotThrow(() -> support.check(rows.get(0)));
        SkipException skip = assertThrows(SkipException.class, () -> support.check(rows.get(2)));
        assertTrue(skip.getMessage().contains(GlobalConstants.KNOWN_ISSUES));
    }

    @Test
    void checkFailsRegressions() {
        ConformanceTestSupport support = support("results-verify-regression.example.json");
        TestCaseDTO regression = rows(support).get(7);

        AssertionError failure = assertThrows(AssertionError.class, () -> support.check(regression));
        assertTrue(failure.getMessage().startsWith("regression: "), failure.getMessage());
    }

    @Test
    void notConfiguredRowIsIgnored() {
        ConformanceSettings settings = ConformanceSettings.from("verify", Map.<String, String>of()::get,
                Map.<String, String>of()::get);
        ConformanceTestSupport support = new ConformanceTestSupport("InjiVerify", () -> settings,
                new ConformanceCaseLoader());
        List<TestCaseDTO> rows = rows(support);

        assertEquals(1, rows.size());
        SkipException skip = assertThrows(SkipException.class, () -> support.check(rows.get(0)));
        assertTrue(skip.getMessage().contains(GlobalConstants.FEATURE_NOT_SUPPORTED));
    }

    @Test
    void anUnknownRowFails() {
        ConformanceTestSupport support = support("results-verify.example.json");
        rows(support);
        TestCaseDTO stranger = new TestCaseDTO();
        stranger.setUniqueIdentifier("TC_OIDF_VERIFY_99");

        assertThrows(AssertionError.class, () -> support.check(stranger));
    }
}
