// SPDX-License-Identifier: MPL-2.0
package io.mosip.testrig.apirig.conformance.testng;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Prepares one detail line for {@code Reporter.log}.
 *
 * <p>{@code EmailableReport} writes reporter messages into its HTML as they are unless TestNG's
 * {@code Reporter.getEscapeHtml()} is on (it is off by default). Suite messages can contain {@code <} and
 * {@code &}, so the line is escaped here, and http(s) URLs become links, so a reader can open the suite's log page
 * for the module straight from the rig report.
 */
final class ReportText {

    private static final Pattern URL = Pattern.compile("https?://[^\\s<>\"']+");

    private ReportText() {
    }

    /**
     * Returns {@code line} ready for {@code Reporter.log}.
     *
     * @param reporterEscapes {@code true} when TestNG escapes reporter output itself; the line is then returned as is
     */
    static String line(String line, boolean reporterEscapes) {
        if (reporterEscapes) {
            return line;
        }
        StringBuilder html = new StringBuilder();
        Matcher url = URL.matcher(line);
        int last = 0;
        while (url.find()) {
            html.append(escape(line.substring(last, url.start())));
            String href = escape(url.group());
            html.append("<a href=\"").append(href).append("\">").append(href).append("</a>");
            last = url.end();
        }
        html.append(escape(line.substring(last)));
        return html.toString();
    }

    static String escape(String text) {
        StringBuilder out = new StringBuilder(text.length());
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            switch (c) {
                case '<' -> out.append("&lt;");
                case '>' -> out.append("&gt;");
                case '&' -> out.append("&amp;");
                case '"' -> out.append("&quot;");
                case '\'' -> out.append("&#39;");
                default -> out.append(c);
            }
        }
        return out.toString();
    }
}
