-- Changed by the inji-conformance-harness project (Apache-2.0 section 4(b) notice): 2026-10-07 added the
-- statements at the end of this file; the rest is inji-verify@6a6ab3b docker-compose/docker-compose-injistack/init.sql.
CREATE SCHEMA IF NOT EXISTS verify;

CREATE TABLE IF NOT EXISTS verify.authorization_request_details (
    request_id character varying(40) NOT NULL,
    transaction_id character varying(40) NOT NULL,
    authorization_details text NOT NULL,
    expires_at bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS verify.vc_submission(
    transaction_id character varying(40) NOT NULL,
    vc text NOT NULL
);

CREATE TABLE IF NOT EXISTS verify.vp_submission(
    request_id character varying(40) NOT NULL,
    vp_token VARCHAR NOT NULL,
    presentation_submission text NOT NULL,
    error character varying(100) NULL,
    error_description character varying(200) NULL
);

-- Harness change, not upstream: the inji-verify-service 1.0.x image (ad3595f) stores a response code with every
-- wallet response, and without these columns its direct-post endpoint answers HTTP 500. The statements below
-- bring vp_submission in line with db_scripts/inji_verify/ddl/verify-vp_submission.sql at the same commit
-- (6a6ab3b), which this compose file did not follow: nullable token and submission (a wallet may send only an
-- error), the three response code columns, the primary key and the unique response code.
ALTER TABLE verify.vp_submission ALTER COLUMN vp_token DROP NOT NULL;
ALTER TABLE verify.vp_submission ALTER COLUMN presentation_submission DROP NOT NULL;
ALTER TABLE verify.vp_submission ADD COLUMN IF NOT EXISTS response_code character varying(200) NULL;
ALTER TABLE verify.vp_submission ADD COLUMN IF NOT EXISTS response_code_expiry_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE verify.vp_submission ADD COLUMN IF NOT EXISTS response_code_used boolean DEFAULT false;
ALTER TABLE verify.vp_submission ADD CONSTRAINT pk_vp_submission_request_id PRIMARY KEY (request_id);
ALTER TABLE verify.vp_submission ADD CONSTRAINT uq_vp_submission_response_code UNIQUE (response_code);
