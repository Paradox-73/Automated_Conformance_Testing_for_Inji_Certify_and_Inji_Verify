// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance.results;

import java.nio.file.Path;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * The parts of one {@code results.json} (version 1) that the TestNG bridge uses: one component, one test plan, its
 * modules with verdicts, and the gate outcome. The JSON Schema is {@code conformance/schema/results.schema.json}.
 *
 * @param source        file the results were read from
 * @param runId         run id, for example {@code 20261004T193000Z-1a2b3c4}
 * @param component     {@code certify} or {@code verify}
 * @param track         {@code gate} (the 1.0 plans the benchmark gates on) or {@code haip} (readiness only)
 * @param gating        {@code false} when these results must not change the exit code
 * @param suiteBaseUrl  conformance suite the plan ran on
 * @param suiteVersion  suite version as the suite reports it
 * @param targetBaseUrl system under test
 * @param planName      suite test plan name
 * @param planId        plan id the suite assigned; {@code null} when the plan was never created
 * @param planVariant   variant selections of the plan
 * @param modules       the plan's modules in plan order
 * @param gatePassed    the runner's gate decision
 * @param allowStale    {@code true} when the run used {@code --allow-stale}: stale entries warn instead of failing
 * @param gateMessages  the runner's gate messages
 */
public record ConformanceResults(
        Path source,
        String runId,
        String component,
        String track,
        boolean gating,
        String suiteBaseUrl,
        String suiteVersion,
        String targetBaseUrl,
        String planName,
        String planId,
        Map<String, String> planVariant,
        List<ModuleResult> modules,
        boolean gatePassed,
        boolean allowStale,
        List<String> gateMessages) {

    public ConformanceResults {
        Objects.requireNonNull(component, "component");
        Objects.requireNonNull(planName, "planName");
        planVariant = planVariant == null ? Map.of() : Collections.unmodifiableMap(new LinkedHashMap<>(planVariant));
        modules = modules == null ? List.of() : List.copyOf(modules);
        gateMessages = gateMessages == null ? List.of() : List.copyOf(gateMessages);
    }
}
