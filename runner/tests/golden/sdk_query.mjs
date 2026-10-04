// Reference output for runner/tests/test_inji_verify.py: the query string the Inji Verify SDK builds.
//
// The function body is getAuthorizationRequestParams from inji-verify-sdk/src/components/openid4vp-verification/
// OpenID4VPVerification.tsx (lines 56-83, inji-verify release-1.0.x 6a6ab3b), with VP_FORMATS_SUPPORTED and the
// client_id prefix checks from inji-verify-sdk/src/utils/constants.ts and utils.ts. Run with Node 18 or newer:
//
//   node runner/tests/golden/sdk_query.mjs > runner/tests/golden/sdk_query.json
import { readFileSync } from "node:fs";

const VP_FORMATS_SUPPORTED = {
  ldp_vp: { proof_type: ["Ed25519Signature2018", "Ed25519Signature2020", "RsaSignature2018"] },
  "dc+sd-jwt": {
    "sd-jwt_alg_values": ["RS256", "ES256", "ES256K", "EdDSA"],
    "kb-jwt_alg_values": ["RS256", "ES256", "ES256K", "EdDSA"],
  },
  "vc+sd-jwt": {
    "sd-jwt_alg_values": ["RS256", "ES256", "ES256K", "EdDSA"],
    "kb-jwt_alg_values": ["RS256", "ES256", "ES256K", "EdDSA"],
  },
};
const isSignedRequestScheme = (clientId) =>
  typeof clientId === "string" &&
  (clientId.startsWith("decentralized_identifier:") || clientId.startsWith("x509_san_dns:"));
const isRedirectUriClientId = (clientId) => typeof clientId === "string" && clientId.startsWith("redirect_uri:");

function getAuthorizationRequestParams(clientId, data) {
  const params = new URLSearchParams();
  params.set("client_id", clientId);
  if (data.requestUri) {
    params.set("request_uri", data.requestUri);
  } else if (data.authorizationDetails) {
    params.set("state", data.requestId);
    params.set("response_mode", data.authorizationDetails.responseMode);
    params.set("response_type", data.authorizationDetails.responseType);
    params.set("nonce", data.authorizationDetails.nonce);
    params.set("response_uri", data.authorizationDetails.responseUri);
    if (data.authorizationDetails.dcqlQuery) {
      params.set("dcql_query", JSON.stringify(data.authorizationDetails.dcqlQuery));
    }
    if (isSignedRequestScheme(clientId) || isRedirectUriClientId(clientId)) {
      params.set("client_metadata", JSON.stringify({ vp_formats_supported: VP_FORMATS_SUPPORTED }));
    }
  }
  return params.toString();
}

const cases = JSON.parse(readFileSync(new URL("./sdk_query_cases.json", import.meta.url), "utf8"));
const out = cases.map((c) => ({ name: c.name, query: getAuthorizationRequestParams(c.client_id, c.response) }));
console.log(JSON.stringify(out, null, 2));
