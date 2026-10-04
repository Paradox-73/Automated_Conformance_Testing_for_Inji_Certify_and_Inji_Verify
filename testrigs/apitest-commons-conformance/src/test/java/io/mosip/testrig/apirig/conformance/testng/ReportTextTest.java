// SPDX-License-Identifier: MIT
package io.mosip.testrig.apirig.conformance.testng;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ReportTextTest {

    @Test
    void escapesMarkupAndLinksUrls() {
        assertEquals("Suite log: <a href=\"https://suite:18443/log-detail.html?log=a&amp;b=1\">"
                        + "https://suite:18443/log-detail.html?log=a&amp;b=1</a> &lt;b&gt;",
                ReportText.line("Suite log: https://suite:18443/log-detail.html?log=a&b=1 <b>", false));
    }

    @Test
    void leavesTheLineAloneWhenTestNgEscapes() {
        assertEquals("a <b> https://x", ReportText.line("a <b> https://x", true));
    }
}
