// SPDX-License-Identifier: MIT
package io.inji.testrig.apirig.injiverify.testscripts;

import org.apache.log4j.Level;
import org.apache.log4j.Logger;
import org.testng.ITest;
import org.testng.ITestResult;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeClass;
import org.testng.annotations.DataProvider;
import org.testng.annotations.Test;

import io.inji.testrig.apirig.injiverify.utils.InjiVerifyConfigManager;
import io.inji.testrig.apirig.injiverify.utils.InjiVerifyUtil;
import io.mosip.testrig.apirig.conformance.testng.ConformanceTestSupport;
import io.mosip.testrig.apirig.dto.TestCaseDTO;
import io.mosip.testrig.apirig.testrunner.BaseTestCase;
import io.mosip.testrig.apirig.utils.GlobalConstants;

/**
 * OpenID Foundation conformance results for Inji Verify, one report row per conformance test module.
 *
 * <p>The rows come from the conformance runner's {@code results.json}: either an existing file
 * ({@code -Dconformance.results.file=...}) or a runner this class starts against {@code env.endpoint}
 * ({@code -Dconformance.runner.command=...}). With neither, the class reports one Ignored row, so the stock
 * {@code InjiTestRunner}, which runs every {@code *MasterTestSuite*} file, still passes without a conformance setup.
 * The mapping from verdicts to pass, fail, Known Issue and Ignored lives in the apitest-commons-conformance library.
 *
 * <p>Same shape as the other scripts of this rig ({@link SimplePost}): {@code ITest}, a {@code testcaselist} data
 * provider of {@link TestCaseDTO}s, and an {@code @AfterMethod} that names each row.
 */
public class OpenIDConformanceTest extends InjiVerifyUtil implements ITest {
	private static final Logger logger = Logger.getLogger(OpenIDConformanceTest.class);

	/** Report name part; keeps the conformance report apart from the rig's API report. */
	public static final String REPORT_MODULE = GlobalConstants.INJIVERIFY + "-conformance";

	private final ConformanceTestSupport conformance = new ConformanceTestSupport("verify", "InjiVerify");
	protected String testCaseName = "";

	@BeforeClass
	public static void setUp() {
		logger.setLevel(InjiVerifyConfigManager.IsDebugEnabled() ? Level.ALL : Level.ERROR);
		// EmailableReport reads the name when the suite ends, so this also applies under the stock InjiTestRunner.
		BaseTestCase.setReportName(REPORT_MODULE);
	}

	@Override
	public String getTestName() {
		return testCaseName;
	}

	@DataProvider(name = "testcaselist")
	public Object[] getTestCaseList() {
		Object[] rows = conformance.testCases();
		logger.info("OpenID conformance rows: " + rows.length);
		return rows;
	}

	@Test(dataProvider = "testcaselist")
	public void test(TestCaseDTO testCaseDTO) {
		testCaseName = testCaseDTO.getTestCaseName();
		// Honours the rig's skip list and testCasesToExecute like every other script.
		testCaseName = InjiVerifyUtil.isTestCaseValidForExecution(testCaseDTO);
		conformance.check(testCaseDTO);
	}

	@AfterMethod(alwaysRun = true)
	public void setResultTestName(ITestResult result) {
		result.setAttribute("TestCaseName", testCaseName);
	}
}
