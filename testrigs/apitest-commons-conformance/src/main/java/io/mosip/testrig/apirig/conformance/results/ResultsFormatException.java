// SPDX-License-Identifier: MPL-2.0
package io.mosip.testrig.apirig.conformance.results;

/** A {@code results.json} file is missing, unreadable, or does not follow results.schema.json version 1. */
public class ResultsFormatException extends Exception {

    public ResultsFormatException(String message) {
        super(message);
    }

    public ResultsFormatException(String message, Throwable cause) {
        super(message, cause);
    }
}
