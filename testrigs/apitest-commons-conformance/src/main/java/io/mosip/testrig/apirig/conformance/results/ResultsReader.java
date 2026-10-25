// SPDX-License-Identifier: MPL-2.0
package io.mosip.testrig.apirig.conformance.results;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Reads {@code results.json} version 1 into {@link ConformanceResults}.
 *
 * <p>The reader checks what the bridge depends on (schema version, component, plan name, and for every module its
 * name, status and a known verdict) and reports the JSON path of the first problem. It does not repeat the full
 * JSON Schema validation: {@code inji-conformance validate} does that, and unknown extra fields are ignored so a
 * newer runner that adds optional fields does not break older rigs.
 *
 * <p>The tree API is used instead of data binding so the reader works with whichever Jackson version the rig's
 * apitest-commons brings.
 */
public final class ResultsReader {

    /** The only {@code schema_version} this reader understands. */
    public static final String SCHEMA_VERSION = "1";

    private static final Set<String> COMPONENTS = Set.of("certify", "verify");

    private final ObjectMapper mapper = new ObjectMapper();

    /**
     * Reads and checks one results file.
     *
     * @throws ResultsFormatException when the file cannot be read or breaks the contract; the message names the file
     *                                and the JSON path of the problem
     */
    public ConformanceResults read(Path file) throws ResultsFormatException {
        if (!Files.isRegularFile(file)) {
            throw new ResultsFormatException("results file not found: " + file.toAbsolutePath());
        }
        JsonNode root;
        try {
            root = mapper.readTree(file.toFile());
        } catch (JsonProcessingException e) {
            throw new ResultsFormatException(
                    "results file " + file + " is not valid JSON: " + e.getOriginalMessage(), e);
        } catch (IOException e) {
            throw new ResultsFormatException("cannot read results file " + file + ": " + e.getMessage(), e);
        }
        return parse(file, root);
    }

    private ConformanceResults parse(Path file, JsonNode root) throws ResultsFormatException {
        Fields top = new Fields(file, "$", root);
        String version = top.requiredText("schema_version");
        if (!SCHEMA_VERSION.equals(version)) {
            throw top.problem("schema_version", "is \"" + version + "\"; this bridge reads version " + SCHEMA_VERSION);
        }
        String component = top.requiredText("component");
        if (!COMPONENTS.contains(component)) {
            throw top.problem("component", "is \"" + component + "\"; expected one of " + COMPONENTS);
        }

        Fields suite = top.object("suite");
        Fields target = top.object("target");
        Fields plan = top.requiredObject("plan");
        Fields gate = top.object("gate");

        List<ModuleResult> modules = new ArrayList<>();
        JsonNode modulesNode = top.requiredArray("modules");
        for (int i = 0; i < modulesNode.size(); i++) {
            modules.add(parseModule(new Fields(file, "$.modules[" + i + "]", modulesNode.get(i))));
        }

        return new ConformanceResults(
                file,
                top.text("run_id"),
                component,
                top.text("track"),
                top.bool("gating", true),
                suite.text("base_url"),
                suite.text("version"),
                target.text("base_url"),
                plan.requiredText("name"),
                plan.text("id"),
                plan.stringMap("variant"),
                modules,
                gate.bool("passed", false),
                gate.bool("allow_stale", false),
                gate.textList("messages"));
    }

    private ModuleResult parseModule(Fields m) throws ResultsFormatException {
        String verdictText = m.requiredText("verdict");
        Verdict verdict = Verdict.fromJson(verdictText)
                .orElseThrow(() -> m.problem("verdict", "has unknown value \"" + verdictText + "\""));

        List<ModuleResult.Failure> failures = new ArrayList<>();
        for (Fields f : m.objects("failures")) {
            failures.add(new ModuleResult.Failure(
                    f.requiredText("condition"), f.requiredText("severity"), f.text("message"), f.text("block"),
                    f.textList("requirements"), f.optionalBool("expected")));
        }
        List<ModuleResult.BenchmarkEntry> benchmark = new ArrayList<>();
        for (Fields b : m.objects("benchmark")) {
            benchmark.add(new ModuleResult.BenchmarkEntry(
                    b.requiredText("kind"), b.text("condition"), b.text("comment"), b.text("owner"), b.text("spec"),
                    b.text("issue"), b.bool("matched", true)));
        }
        List<ModuleResult.Handoff> handoffs = new ArrayList<>();
        for (Fields h : m.objects("handoffs")) {
            JsonNode status = h.node.get("http_status");
            handoffs.add(new ModuleResult.Handoff(
                    h.requiredText("kind"), status != null && status.isInt() ? status.intValue() : null,
                    h.number("duration_ms", 0), h.text("detail"), h.text("error")));
        }
        ModuleResult.Review review = null;
        if (m.node.hasNonNull("review")) {
            Fields r = m.object("review");
            review = new ModuleResult.Review(r.text("expected"), r.text("observed"), r.text("evidence"));
        }
        Fields links = m.object("links");
        JsonNode duration = m.node.get("duration_s");

        return new ModuleResult(
                m.requiredText("name"),
                m.text("test_id"),
                m.text("description"),
                m.stringMap("variant"),
                m.requiredText("status"),
                m.text("result"),
                verdict,
                m.text("verdict_reason"),
                failures,
                benchmark,
                review,
                handoffs,
                links.text("suite_log"),
                links.text("export"),
                duration != null && duration.isNumber() ? duration.doubleValue() : null);
    }

    /** Typed access to the fields of one JSON object, with error messages that carry the file and JSON path. */
    private static final class Fields {
        private final Path file;
        private final String path;
        private final JsonNode node;

        Fields(Path file, String path, JsonNode node) throws ResultsFormatException {
            this.file = file;
            this.path = path;
            if (node != null && !node.isNull() && !node.isObject()) {
                throw new ResultsFormatException(file + ": " + path + " must be an object");
            }
            this.node = node == null || node.isNull() ? MISSING : node;
        }

        private static final JsonNode MISSING = new ObjectMapper().createObjectNode();

        ResultsFormatException problem(String field, String what) {
            return new ResultsFormatException(file + ": " + path + "." + field + " " + what);
        }

        String text(String field) {
            JsonNode value = node.get(field);
            return value != null && value.isTextual() ? value.textValue() : null;
        }

        String requiredText(String field) throws ResultsFormatException {
            String value = text(field);
            if (value == null || value.isBlank()) {
                throw problem(field, "is missing or not a non-empty string");
            }
            return value;
        }

        boolean bool(String field, boolean fallback) {
            Boolean value = optionalBool(field);
            return value == null ? fallback : value;
        }

        Boolean optionalBool(String field) {
            JsonNode value = node.get(field);
            return value != null && value.isBoolean() ? value.booleanValue() : null;
        }

        double number(String field, double fallback) {
            JsonNode value = node.get(field);
            return value != null && value.isNumber() ? value.doubleValue() : fallback;
        }

        Fields object(String field) throws ResultsFormatException {
            return new Fields(file, path + "." + field, node.get(field));
        }

        Fields requiredObject(String field) throws ResultsFormatException {
            if (!node.hasNonNull(field)) {
                throw problem(field, "is missing");
            }
            return object(field);
        }

        JsonNode requiredArray(String field) throws ResultsFormatException {
            JsonNode value = node.get(field);
            if (value == null || !value.isArray()) {
                throw problem(field, "is missing or not an array");
            }
            return value;
        }

        List<Fields> objects(String field) throws ResultsFormatException {
            JsonNode value = node.get(field);
            List<Fields> items = new ArrayList<>();
            if (value == null || value.isNull()) {
                return items;
            }
            if (!value.isArray()) {
                throw problem(field, "must be an array");
            }
            for (int i = 0; i < value.size(); i++) {
                items.add(new Fields(file, path + "." + field + "[" + i + "]", value.get(i)));
            }
            return items;
        }

        List<String> textList(String field) {
            List<String> items = new ArrayList<>();
            JsonNode value = node.get(field);
            if (value != null && value.isArray()) {
                value.forEach(item -> {
                    if (item.isTextual()) {
                        items.add(item.textValue());
                    }
                });
            }
            return items;
        }

        Map<String, String> stringMap(String field) {
            Map<String, String> map = new LinkedHashMap<>();
            JsonNode value = node.get(field);
            if (value != null && value.isObject()) {
                value.fields().forEachRemaining(e -> map.put(e.getKey(), e.getValue().asText()));
            }
            return map;
        }
    }
}
