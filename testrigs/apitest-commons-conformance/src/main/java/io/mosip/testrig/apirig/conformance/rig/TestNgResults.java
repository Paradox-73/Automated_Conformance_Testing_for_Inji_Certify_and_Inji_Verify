// SPDX-License-Identifier: MPL-2.0
package io.mosip.testrig.apirig.conformance.rig;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.SAXException;

/**
 * Counts from TestNG's {@code testng-results.xml}, and the exit code a rig run should end with.
 *
 * <p>The stock rig runners always exit 0 (each {@code InjiTestRunner.main} ends with {@code System.exit(0)}), so a
 * pipeline cannot fail on test failures. A conformance rig run instead exits {@value #EXIT_FAILED} when any test
 * method or configuration method failed, so a CI job fails exactly when the conformance gate fails.
 *
 * @param total         {@code total} attribute of the root element
 * @param passed        {@code passed} attribute
 * @param failed        {@code failed} attribute
 * @param skipped       {@code skipped} attribute (TestNG counts Known Issue and Ignored rows here too)
 * @param failedMethods names of failed methods, configuration methods included, for the log
 */
public record TestNgResults(int total, int passed, int failed, int skipped, List<String> failedMethods) {

    /** Every test passed or was skipped. */
    public static final int EXIT_OK = 0;
    /** At least one test or configuration method failed. */
    public static final int EXIT_FAILED = 1;
    /** The run could not start or left no results file. */
    public static final int EXIT_ERROR = 2;

    public TestNgResults {
        failedMethods = List.copyOf(failedMethods);
    }

    /** {@value #EXIT_FAILED} when anything failed, else {@value #EXIT_OK}. */
    public int exitCode() {
        return failed > 0 || !failedMethods.isEmpty() ? EXIT_FAILED : EXIT_OK;
    }

    /** One line for the log, for example {@code total 11, passed 10, failed 0, skipped 1}. */
    public String summary() {
        return "total " + total + ", passed " + passed + ", failed " + failed + ", skipped " + skipped
                + (failedMethods.isEmpty() ? "" : "; failed: " + String.join(", ", failedMethods));
    }

    /**
     * Reads {@code testng-results.xml}.
     *
     * @throws IOException when the file is missing or is not a TestNG results file
     */
    public static TestNgResults read(Path file) throws IOException {
        if (!Files.isRegularFile(file)) {
            throw new IOException("TestNG results not found: " + file.toAbsolutePath());
        }
        Document document;
        try {
            document = parser().parse(file.toFile());
        } catch (SAXException | ParserConfigurationException e) {
            throw new IOException("cannot parse " + file + ": " + e.getMessage(), e);
        }
        Element root = document.getDocumentElement();
        if (!"testng-results".equals(root.getTagName())) {
            throw new IOException(file + " is not a testng-results.xml file (root element " + root.getTagName() + ")");
        }

        List<String> failedMethods = new ArrayList<>();
        NodeList methods = root.getElementsByTagName("test-method");
        for (int i = 0; i < methods.getLength(); i++) {
            Element method = (Element) methods.item(i);
            if ("FAIL".equals(method.getAttribute("status"))) {
                String config = "true".equals(method.getAttribute("is-config")) ? " (configuration)" : "";
                failedMethods.add(method.getAttribute("name") + config);
            }
        }
        return new TestNgResults(count(root, "total"), count(root, "passed"), count(root, "failed"),
                count(root, "skipped"), failedMethods);
    }

    private static int count(Element root, String attribute) throws IOException {
        String value = root.getAttribute(attribute);
        if (value.isEmpty()) {
            return 0;
        }
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException e) {
            throw new IOException("testng-results attribute " + attribute + " is not a number: " + value, e);
        }
    }

    /** A parser that refuses DOCTYPEs and external entities: the file is ours, but there is no reason to allow them. */
    private static DocumentBuilder parser() throws ParserConfigurationException {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        return factory.newDocumentBuilder();
    }
}
