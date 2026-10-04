// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance.testng;

import java.util.Objects;

import io.mosip.testrig.apirig.conformance.Outcome;

/**
 * One TestNG row of a rig's conformance test: usually one conformance test module, otherwise a row that explains
 * why there are no module rows (not configured, runner failed, unreadable results).
 *
 * @param uniqueIdentifier report id, {@code TC_OIDF_<COMPONENT>_<nn>}; {@code nn} is the module's position in the
 *                         plan, {@code 00} for a row that is not a module
 * @param testCaseName     report name, {@code <RigPrefix>_OpenIDConformance_<module>}
 * @param description      what the row checks, shown next to the id in the report
 * @param target           base URL of the system under test, or {@code null} when unknown
 * @param outcome          the TestNG result this row produces
 */
public record ConformanceCase(
        String uniqueIdentifier, String testCaseName, String description, String target, Outcome outcome) {

    public ConformanceCase {
        Objects.requireNonNull(uniqueIdentifier, "uniqueIdentifier");
        Objects.requireNonNull(testCaseName, "testCaseName");
        Objects.requireNonNull(description, "description");
        Objects.requireNonNull(outcome, "outcome");
    }
}
