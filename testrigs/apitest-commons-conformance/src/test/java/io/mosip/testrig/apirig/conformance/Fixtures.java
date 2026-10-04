// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.UnaryOperator;

/** Paths of shared test inputs. Surefire runs the tests with the module folder as working directory. */
public final class Fixtures {

    /** The repository's results examples (conformance/schema/examples), the same files the runner tests use. */
    public static final Path EXAMPLES = Path.of("..", "..", "conformance", "schema", "examples");

    /** This module's own fixtures. */
    public static final Path OWN = Path.of("src", "test", "resources", "fixtures");

    private Fixtures() {
    }

    public static Path example(String name) {
        return EXAMPLES.resolve(name);
    }

    /** A copy of example {@code name} in {@code dir} with {@code edit} applied to its text. */
    public static Path editedExample(Path dir, String name, UnaryOperator<String> edit) throws IOException {
        String text = Files.readString(example(name), StandardCharsets.UTF_8);
        String edited = edit.apply(text);
        if (edited.equals(text)) {
            throw new IllegalArgumentException("edit changed nothing in " + name);
        }
        Path copy = dir.resolve(name);
        Files.writeString(copy, edited, StandardCharsets.UTF_8);
        return copy;
    }
}
