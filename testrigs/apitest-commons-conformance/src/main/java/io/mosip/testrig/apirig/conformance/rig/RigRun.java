// SPDX-License-Identifier: MPL-2.0
package io.mosip.testrig.apirig.conformance.rig;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Consumer;
import java.util.function.UnaryOperator;

import org.testng.TestNG;

import io.mosip.testrig.apirig.utils.ConfigManager;

/**
 * The rig-independent part of a {@code ConformanceRigRunner}: where the report goes, how TestNG is pointed there,
 * and the exit code.
 *
 * <p>Two upstream behaviours shape this class:
 * <ul>
 * <li>{@code EmailableReport} finds its own report at {@code user.dir + "/" + testng.outpur.dir + "/" + name}
 * (the property name is spelled that way upstream) before renaming it to the {@code _T-.._P-..} form and uploading
 * it. The output folder is therefore given to it as a path relative to the working directory.</li>
 * <li>When S3 upload is off, {@code EmailableReport} copies the renamed report to {@code mountPathForReport}
 * (default {@code /home/mosip/testrig/report}). Pointing that key at the report folder keeps every file of the run
 * in one place.</li>
 * </ul>
 */
public final class RigRun {

    /** Folder for the TestNG output and the rig report. */
    public static final String REPORT_DIR = "conformance.report.dir";
    /** System property {@code EmailableReport} reads to find the TestNG output folder (upstream spelling). */
    static final String TESTNG_OUTPUT_PROPERTY = "testng.outpur.dir";
    /** apitest-commons key for the folder {@code EmailableReport} copies the report to when S3 upload is off. */
    static final String MOUNT_PATH_KEY = "mountPathForReport";
    /** apitest-commons keys of the S3/MinIO report upload that {@code EmailableReport} reads. */
    static final List<String> UPLOAD_KEYS = List.of("push-reports-to-s3", "s3-host", "s3-account", "s3-region",
            "s3-user-key", "s3-user-secret");

    private RigRun() {
    }

    /**
     * The report folder for {@code module}: {@value #REPORT_DIR} (system property, environment variable of the same
     * name, or {@code CONFORMANCE_REPORT_DIR}), else {@code ${HARNESS_RUN_DIR}/testrig/<module>}, else
     * {@code <working directory>/testng-report/conformance}.
     */
    public static Path reportDir(String module, UnaryOperator<String> properties, UnaryOperator<String> environment) {
        String configured = firstNonBlank(properties.apply(REPORT_DIR), environment.apply(REPORT_DIR),
                environment.apply("CONFORMANCE_REPORT_DIR"));
        if (configured != null) {
            return Path.of(configured).toAbsolutePath().normalize();
        }
        String runDir = firstNonBlank(environment.apply("HARNESS_RUN_DIR"));
        if (runDir != null) {
            return Path.of(runDir, "testrig", module).toAbsolutePath().normalize();
        }
        return Path.of(properties.apply("user.dir"), "testng-report", "conformance").toAbsolutePath().normalize();
    }

    /** {@link #reportDir(String, UnaryOperator, UnaryOperator)} from this JVM's properties and environment. */
    public static Path reportDir(String module) {
        return reportDir(module, System::getProperty, System::getenv);
    }

    /**
     * {@code reportDir} as a path relative to {@code workingDir}, with forward slashes.
     *
     * @throws IllegalArgumentException when the two are on different drives (Windows), so no relative path exists
     */
    public static String relativeOutputDir(Path workingDir, Path reportDir) {
        Path from = workingDir.toAbsolutePath().normalize();
        Path to = reportDir.toAbsolutePath().normalize();
        if (!from.getRoot().equals(to.getRoot())) {
            throw new IllegalArgumentException("the report folder " + to + " must be on the same drive as the working "
                    + "directory " + from + " (EmailableReport resolves its report relative to the working directory)");
        }
        String relative = from.relativize(to).toString().replace('\\', '/');
        return relative.isEmpty() ? "." : relative;
    }

    /**
     * Points {@code mountPathForReport} at {@code reportDir}, unless an environment variable of that name is set
     * (apitest-commons gives environment variables priority over every properties file, and so does this method).
     * Call it after the rig's config manager has loaded its properties.
     */
    public static void keepReportCopyIn(Path reportDir) {
        ConfigManager.getValueForKeyAddToPropertiesMap(
                Map.of(MOUNT_PATH_KEY, reportDir.toAbsolutePath().toString()), MOUNT_PATH_KEY);
    }

    /**
     * Puts the report upload settings into apitest-commons' configuration, so {@code EmailableReport} uploads the
     * report to S3/MinIO: for each of {@link #UPLOAD_KEYS} the system property of that name, else the environment
     * variable of that name, else the upper-case one with underscores ({@code S3_USER_SECRET}).
     *
     * <p>apitest-commons lets an environment variable replace only keys its property files already have, and the
     * rigs' files have none of these; and a POSIX shell drops environment variables whose names contain a hyphen
     * before it starts Java. Returns the keys that were set.
     */
    public static List<String> applyUploadSettings(UnaryOperator<String> properties, UnaryOperator<String> environment) {
        List<String> applied = new java.util.ArrayList<>();
        for (String key : UPLOAD_KEYS) {
            String value = firstNonBlank(properties.apply(key), environment.apply(key),
                    environment.apply(key.toUpperCase(Locale.ROOT).replace('-', '_')));
            if (value != null) {
                ConfigManager.getValueForKeyAddToPropertiesMap(Map.of(key, value), key);
                applied.add(key);
            }
        }
        return applied;
    }

    /** {@link #applyUploadSettings(UnaryOperator, UnaryOperator)} from this JVM's properties and environment. */
    public static List<String> applyUploadSettings() {
        return applyUploadSettings(System::getProperty, System::getenv);
    }

    /**
     * Runs one TestNG suite file with its output in {@code reportDir} and returns the exit code.
     *
     * @return {@link TestNgResults#EXIT_OK}, {@link TestNgResults#EXIT_FAILED}, or {@link TestNgResults#EXIT_ERROR}
     *         when the suite file is missing or TestNG wrote no results
     */
    public static int runSuite(Path suiteFile, Path reportDir, Consumer<String> log) {
        if (!Files.isRegularFile(suiteFile)) {
            log.accept("TestNG suite file not found: " + suiteFile.toAbsolutePath());
            return TestNgResults.EXIT_ERROR;
        }
        String outputDir;
        try {
            outputDir = relativeOutputDir(Path.of(System.getProperty("user.dir")), reportDir);
            Files.createDirectories(reportDir);
            // A results file left by an earlier run would hide a run that wrote none.
            Files.deleteIfExists(reportDir.resolve("testng-results.xml"));
        } catch (IllegalArgumentException | IOException e) {
            log.accept("cannot prepare the report folder: " + e.getMessage());
            return TestNgResults.EXIT_ERROR;
        }

        System.setProperty(TESTNG_OUTPUT_PROPERTY, outputDir);
        TestNG testng = new TestNG();
        testng.setTestSuites(List.of(suiteFile.toAbsolutePath().toString()));
        testng.setOutputDirectory(reportDir.toString());
        testng.run();

        try {
            TestNgResults results = TestNgResults.read(reportDir.resolve("testng-results.xml"));
            log.accept("TestNG results: " + results.summary() + "; report folder " + reportDir);
            return results.exitCode();
        } catch (IOException e) {
            log.accept(e.getMessage());
            return TestNgResults.EXIT_ERROR;
        }
    }

    /**
     * The suite file {@code name} in the rig's {@code testNgXmlFiles} folder, found the way the stock runners find
     * it: {@code <working directory>/testNgXmlFiles} when that exists (local and IDE runs, Windows), else
     * {@code <parent of working directory>/<home>/testNgXmlFiles} (the rig image, working directory {@code /home/<home>}).
     */
    public static Path suiteFile(String name, String imageHome) {
        Path workingDir = Path.of(System.getProperty("user.dir")).toAbsolutePath();
        Path local = workingDir.resolve("testNgXmlFiles").resolve(name);
        if (Files.isRegularFile(local) || workingDir.getParent() == null) {
            return local;
        }
        return workingDir.getParent().resolve(imageHome.toLowerCase(Locale.ROOT)).resolve("testNgXmlFiles")
                .resolve(name);
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value.trim();
            }
        }
        return null;
    }
}
