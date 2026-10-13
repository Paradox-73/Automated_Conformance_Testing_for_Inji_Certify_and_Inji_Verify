// SPDX-License-Identifier: MIT
package io.inji.testrig.apirig.injiverify.testrunner;

import java.nio.file.Path;

import org.apache.log4j.Logger;

import io.inji.testrig.apirig.injiverify.testscripts.OpenIDConformanceTest;
import io.inji.testrig.apirig.injiverify.utils.InjiVerifyConfigManager;
import io.mosip.testrig.apirig.conformance.rig.RigRun;
import io.mosip.testrig.apirig.conformance.rig.TestNgResults;
import io.mosip.testrig.apirig.testrunner.BaseTestCase;
import io.mosip.testrig.apirig.testrunner.ExtractResource;
import io.mosip.testrig.apirig.utils.AdminTestUtil;
import io.mosip.testrig.apirig.utils.GlobalConstants;
import io.mosip.testrig.apirig.utils.SkipTestCaseHandler;

/**
 * Runs only the OpenID conformance suite of the Inji Verify rig and exits with a code a pipeline can gate on.
 *
 * <p>Start-up is the same as {@link InjiTestRunner#main} (resource extraction, config, {@code BaseTestCase}
 * initialisation, skip list) without the parts a conformance run does not need: the health checker thread, the
 * API suites and the database cleanup. The TestNG output and the {@code EmailableReport} HTML go to
 * {@code conformance.report.dir} (default {@code ${HARNESS_RUN_DIR}/testrig/injiverify}); S3 upload follows the
 * usual {@code push-reports-to-s3} and {@code s3-*} settings.
 *
 * <p>Exit code: 0 when no row failed, 1 when a row failed (a conformance regression or a runner problem), 2 when
 * the run could not start or TestNG wrote no results. The stock runner always exits 0.
 *
 * <pre>
 * java -Dmodules=injiverify -Denv.user=ps01 -Denv.endpoint=https://verify.inji.test:18451 \
 *      -Denv.testLevel=smokeAndRegression -Dconformance.results.file=results.json \
 *      -cp apitest-injiverify-...-jar-with-dependencies.jar \
 *      io.inji.testrig.apirig.injiverify.testrunner.ConformanceRigRunner
 * </pre>
 */
public final class ConformanceRigRunner {
	private static final Logger LOGGER = Logger.getLogger(ConformanceRigRunner.class);

	/** Master suite with the EmailableReport listener; it includes injiverifyConformanceSuite.xml. */
	static final String SUITE_FILE = "injiverifyConformanceMasterTestSuite.xml";

	private ConformanceRigRunner() {
	}

	public static void main(String[] args) {
		int exitCode;
		try {
			exitCode = run();
		} catch (Exception | LinkageError e) {
			LOGGER.error("conformance rig run failed before TestNG finished", e);
			exitCode = TestNgResults.EXIT_ERROR;
		}
		LOGGER.info("conformance rig run exit code " + exitCode);
		// Exit explicitly: apitest-commons leaves non-daemon threads behind.
		System.exit(exitCode);
	}

	static int run() {
		Path reportDir = RigRun.reportDir(GlobalConstants.INJIVERIFY);
		String runType = InjiTestRunner.getRunType();

		BaseTestCase.setRunContext(runType, InjiTestRunner.jarUrl);
		ExtractResource.removeOldMosipTestTestResource();
		if ("JAR".equalsIgnoreCase(runType)) {
			ExtractResource.extractCommonResourceFromJar();
		} else {
			ExtractResource.copyCommonResources();
		}
		AdminTestUtil.init();
		InjiVerifyConfigManager.init();
		RigRun.keepReportCopyIn(reportDir);
		LOGGER.info("report upload settings: " + RigRun.applyUploadSettings());
		InjiTestRunner.suiteSetup(runType);
		SkipTestCaseHandler.loadTestcaseToBeSkippedList("testCaseSkippedList.txt");
		BaseTestCase.setReportName(OpenIDConformanceTest.REPORT_MODULE);

		Path suite = RigRun.suiteFile(SUITE_FILE, "inji");
		LOGGER.info("conformance suite " + suite + ", report folder " + reportDir);
		return RigRun.runSuite(suite, reportDir, LOGGER::info);
	}
}
