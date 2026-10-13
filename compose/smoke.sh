#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
#
# Smoke test of the compose stack: start the given profiles, check that every service answers the way the
# conformance runs need, measure start time and peak memory, then remove everything again.
#
#   bash compose/smoke.sh PROFILE...        PROFILE: suite, verify, certify, reports
#
# On this laptop run it under the shared Docker lock, after pulling images outside the lock:
#   bash scripts/dc.sh --profile verify pull
#   with_lock docker-stack bash compose/smoke.sh verify
#   bash scripts/dc.sh --profile certify --profile reports pull
#   with_lock docker-stack bash compose/smoke.sh certify reports
#
# Output: one line per check, "<check> PASS|FAIL <detail>", with detail lines indented below. The lines other
# scripts and the acceptance checks look for:
#   suite PASS <version>                      suite API answers on the host and inside the network
#   verify PASS 201 x509_san_dns request_uri  Inji Verify creates a signed request object over TLS
#   certify PASS credential_issuer=<url>      Inji Certify issuer metadata at the root well-known URL over TLS
#   certify-as PASS token_endpoint            Certify is its own authorization server (AS metadata, token URL)
#   certify-preauth PASS offer                a pre-authorized credential offer is created and can be fetched
#   certify-token PASS Bearer                 the offer's code is redeemed at Certify's token endpoint
#   minio PASS bucket automationtests         the report bucket exists and takes path-style S3 uploads
#   teardown PASS                             no container or volume of the project is left
# Measurements and logs go to $HARNESS_RUN_DIR/smoke/<UTC time>-<profiles>/ (smoke.json, stats.tsv, and
# compose.log when a check failed).
#
# Exit status: 0 when every check passed, 1 when a check failed, 2 for a usage error.
#
# The script refuses to start when containers of the project already exist, because it would remove them at the
# end: stop them first (bash scripts/dc.sh --profile '*' down). Settings:
#   SMOKE_START_TIMEOUT   seconds "up --wait" may take (default 420)
#   SMOKE_STATS_INTERVAL  seconds between memory samples (default 3)

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../scripts/lib/common.sh
source "$SCRIPT_DIR/../scripts/lib/common.sh"

readonly KNOWN_PROFILES=(suite verify certify reports)
readonly START_TIMEOUT=${SMOKE_START_TIMEOUT:-420}
readonly STATS_INTERVAL=${SMOKE_STATS_INTERVAL:-3}
readonly PROJECT_LABEL=com.docker.compose.project=$HARNESS_COMPOSE_PROJECT

# What the Inji Verify check asks for: the client id whose certificate is bundled in the Verify image, and a DCQL
# query for the credential type the suite issues when it plays the wallet (urn:eudi:pid:1).
readonly VERIFY_URL=https://verify.inji.test:18451/v1/verify
readonly VERIFY_CLIENT_ID=x509_san_dns:verify.inji.test
readonly VERIFY_DCQL='{"credentials":[{"id":"pid","format":"dc+sd-jwt","meta":{"vct_values":["urn:eudi:pid:1"]},"claims":[{"path":["given_name"]}]}]}'

# What the Inji Certify checks use: the issuer identifier (mosip.certify.domain.url, served by tls-proxy) and a
# pre-authorized offer for the FarmerCredential configuration that upstream's certify_init.sql seeds, with claims
# from that configuration. The conformance runs add their own dc+sd-jwt configuration (runner, "seed certify").
readonly CERTIFY_URL=https://certify.inji.test:18450
readonly CERTIFY_API=$CERTIFY_URL/v1/certify
readonly CERTIFY_OFFER_REQUEST='{"credential_configuration_id":"FarmerCredential","claims":{"fullName":"Smoke Test","dateOfBirth":"1990-01-15","gender":"Female"},"expires_in":600}'
readonly PRE_AUTH_GRANT=urn:ietf:params:oauth:grant-type:pre-authorized_code

# The bucket the api-testrigs upload to (the name the problem statement and the testrigs use), and MinIO's S3 API
# as the testrigs reach it on the compose network.
readonly MINIO_BUCKET_NAME=automationtests
readonly MINIO_URL=http://minio:9000

FAILURES=0
STARTED=0
SAMPLER_PID=
OUT_DIR=
START_SECONDS=
declare -a PROFILES=() PROFILE_ARGS=() CHECKS=()

usage() {
  cat <<EOF
Usage: bash compose/smoke.sh PROFILE...
Profiles: ${KNOWN_PROFILES[*]}
EOF
}

dc() {
  bash "$HARNESS_ROOT/scripts/dc.sh" "$@"
}

# result CHECK STATUS [DETAIL]: print one result line and remember it for smoke.json.
result() {
  local check=$1 status=$2 detail=${3:-}
  printf '%s %s%s\n' "$check" "$status" "${detail:+ $detail}"
  CHECKS+=("$check $status${detail:+ $detail}")
  [[ $status == PASS ]] || FAILURES=$((FAILURES + 1))
}

detail() {
  printf '  %s\n' "$@"
}

# probe ARGS...: curl inside the compose network (service probe), with the run-time test CA mounted at /pki.
# Compose progress messages are turned off so that stdout carries only curl's output and stderr only curl's errors.
probe() {
  dc --progress quiet run --rm --no-deps -T probe "$@"
}

# probe_errors: show the last error lines of the probe calls (curl's stderr is kept apart from the parsed output).
probe_errors() {
  tail -n 5 "$OUT_DIR/probe.log" 2>/dev/null | sed 's/^/  /'
}

# b64url_decode: decode base64url from stdin (adds the padding JWTs leave out).
b64url_decode() {
  local data
  data=$(tr '_-' '/+')
  while ((${#data} % 4)); do data+='='; done
  printf '%s' "$data" | base64 -d 2>/dev/null
}

# json_string FIELD: value of a top-level string field in a one-line JSON document read from stdin.
json_string() {
  sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -n 1
}

# url_decode: percent-decode stdin (a URL query parameter value; "+" stays "+", as in the offer URLs Certify makes).
url_decode() {
  local data
  data=$(cat)
  printf '%b' "${data//%/\\x}"
}

# env_value NAME [DEFAULT]: NAME from the environment, else from $HARNESS_RUN_DIR/env.local (the generated
# passwords scripts/dc.sh passes to Compose), else DEFAULT.
env_value() {
  local name=$1 default=${2:-} value
  value=${!name:-}
  if [[ -z $value && -f $HARNESS_RUN_DIR/env.local ]]; then
    value=$(sed -n "s/^$name=//p" "$HARNESS_RUN_DIR/env.local" | tail -n 1)
  fi
  printf '%s\n' "${value:-$default}"
}

# has_profile NAME: true when NAME was given on the command line.
has_profile() {
  local p
  for p in "${PROFILES[@]}"; do
    [[ $p == "$1" ]] && return 0
  done
  return 1
}

project_containers() {
  docker ps -aq --filter "label=$PROJECT_LABEL"
}

# ---------------------------------------------------------------------------------------------------------------
# Memory sampling: docker stats every few seconds while the stack runs; the peak per service goes to smoke.json.
# ---------------------------------------------------------------------------------------------------------------

sample_stats() {
  local ids
  while :; do
    ids=$(docker ps -q --filter "label=$PROJECT_LABEL" --filter status=running)
    if [[ -n $ids ]]; then
      # shellcheck disable=SC2086 # one argument per container id
      docker stats --no-stream --format '{{.Name}}\t{{.MemUsage}}' $ids 2>/dev/null |
        sed "s/^/$(date +%s)\t/" >>"$OUT_DIR/stats.tsv" || true
    fi
    sleep "$STATS_INTERVAL"
  done
}

stop_sampler() {
  if [[ -n $SAMPLER_PID ]]; then
    kill "$SAMPLER_PID" 2>/dev/null || true
    wait "$SAMPLER_PID" 2>/dev/null || true
    SAMPLER_PID=
  fi
}

# peak_memory: "service MiB" lines, highest first, from stats.tsv. One-off "run" containers, and containers that
# only ever showed 0 B (pki-init after it exited), are left out.
peak_memory() {
  [[ -s $OUT_DIR/stats.tsv ]] || return 0
  awk -F '\t' -v project="$HARNESS_COMPOSE_PROJECT-" '
    $2 ~ /-run-/ { next }
    {
      name = $2; sub("^" project, "", name); sub(/-[0-9]+$/, "", name)
      split($3, usage, " / "); value = usage[1]; unit = value; gsub(/[0-9.]/, "", unit); sub(/[A-Za-z]+$/, "", value)
      mib = value + 0
      if (unit == "GiB") mib *= 1024; else if (unit == "KiB") mib /= 1024; else if (unit == "B") mib /= 1048576
      if (mib > peak[name]) peak[name] = mib
    }
    END { for (n in peak) if (peak[n] >= 0.5) printf "%s %.0f\n", n, peak[n] }
  ' "$OUT_DIR/stats.tsv" | sort -k2,2nr
}

# ---------------------------------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------------------------------

check_ports_free() {
  local ports port busy=()
  ports=$(dc "${PROFILE_ARGS[@]}" config | sed -n 's/^ *published: "\{0,1\}\([0-9]*\)"\{0,1\}$/\1/p' | sort -u)
  for port in $ports; do
    # A successful connect means something already listens there.
    if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
      busy+=("$port")
    fi
  done
  if ((${#busy[@]})); then
    result ports FAIL "in use on 127.0.0.1: ${busy[*]}"
    return 1
  fi
  result ports PASS "$(tr '\n' ' ' <<<"$ports" | sed 's/ $//') free"
}

check_pki() {
  local out
  if ! out=$(dc --progress quiet run --rm --no-deps -T --entrypoint openssl pki-init verify -CAfile /pki/ca.crt \
    /pki/tls/verify.inji.test.crt /pki/tls/certify.inji.test.crt /pki/suite-mtls-client.crt \
    /pki/suite-signing.crt 2>&1) || [[ $(grep -c ': OK$' <<<"$out") -ne 4 ]]; then
    detail "$out"
    result pki FAIL "certificates do not verify against the test CA"
    return
  fi
  local jwk=$HARNESS_RUN_DIR/pki/suite-signing.jwk.json
  if ! grep -q '"x5c"' "$jwk" 2>/dev/null; then
    result pki FAIL "$jwk has no x5c"
    return
  fi
  result pki PASS "4 certificates chain to the test CA, signing JWK has x5c"
}

# The suite answers GET /api/server with its version, through nginx, on the host and inside the network.
check_suite() {
  local expected body version host_body
  expected=$(dc "${PROFILE_ARGS[@]}" config --images | sed -n 's|.*/conformance-suite:release-v\([0-9][0-9.]*\).*|\1|p' | head -n 1)

  if ! body=$(probe -sS -k --max-time 20 https://localhost.emobix.co.uk:18443/api/server 2>>"$OUT_DIR/probe.log"); then
    probe_errors
    result suite FAIL "no answer at https://localhost.emobix.co.uk:18443 inside the network"
    return
  fi
  version=$(json_string version <<<"$body")
  detail "network: $body"

  if command -v curl >/dev/null 2>&1; then
    # --resolve: the public DNS name points to 127.0.0.1, but the check must not depend on DNS being reachable.
    if ! host_body=$(curl -sS -k --max-time 20 --resolve localhost.emobix.co.uk:18443:127.0.0.1 \
      https://localhost.emobix.co.uk:18443/api/server 2>&1); then
      detail "$host_body"
      result suite FAIL "no answer at https://localhost.emobix.co.uk:18443 from the host"
      return
    fi
    if [[ $(json_string version <<<"$host_body") != "$version" ]]; then
      result suite FAIL "host and network answers differ"
      return
    fi
  else
    detail "host check skipped: curl is not installed"
  fi

  if [[ -z $version ]]; then
    result suite FAIL "no version in the /api/server answer"
  elif [[ -n $expected && $version != "$expected" ]]; then
    result suite FAIL "version $version, image tag says $expected"
  else
    result suite PASS "$version"
  fi

  # Second listener, used by the suite's mTLS variants (client certificate optional at the TLS layer).
  if probe -sS -k --max-time 20 -o /dev/null https://localhost.emobix.co.uk:18444/api/server >/dev/null 2>&1; then
    result suite-mtls PASS 18444
  else
    result suite-mtls FAIL "no answer at https://localhost.emobix.co.uk:18444"
  fi
}

# Inji Verify, through the TLS proxy with the test CA: create an authorization request for x509_san_dns, then
# fetch the signed request object by its request_uri, as the suite (acting as the wallet) will.
check_verify() {
  local out status body request_uri ctype jwt header payload
  if ! out=$(probe -sS --max-time 30 --cacert /pki/ca.crt -H 'Content-Type: application/json' \
    -d "{\"clientId\":\"$VERIFY_CLIENT_ID\",\"dcqlQuery\":$VERIFY_DCQL}" -w '\n%{http_code}' \
    "$VERIFY_URL/v2/vp-request" 2>>"$OUT_DIR/probe.log"); then
    probe_errors
    result verify FAIL "POST $VERIFY_URL/v2/vp-request failed"
    return
  fi
  status=$(tail -n 1 <<<"$out")
  body=$(sed '$d' <<<"$out")
  request_uri=$(json_string requestUri <<<"$body")
  detail "POST /v2/vp-request -> $status, transactionId $(json_string transactionId <<<"$body")"
  if [[ $status != 201 ]]; then
    detail "$body"
    result verify FAIL "POST /v2/vp-request answered $status, expected 201"
    return
  fi
  if [[ $request_uri != "$VERIFY_URL/v2/vp-request/"* ]]; then
    detail "$body"
    result verify FAIL "no requestUri under $VERIFY_URL (signed request by reference expected)"
    return
  fi

  if ! out=$(probe -sS --max-time 30 --cacert /pki/ca.crt -w '\n%{http_code} %{content_type}' "$request_uri" \
    2>>"$OUT_DIR/probe.log"); then
    probe_errors
    result verify FAIL "GET $request_uri failed"
    return
  fi
  read -r status ctype < <(tail -n 1 <<<"$out")
  jwt=$(sed '$d' <<<"$out" | tr -d '\r\n')
  header=$(cut -d . -f 1 <<<"$jwt" | b64url_decode || true)
  payload=$(cut -d . -f 2 <<<"$jwt" | b64url_decode || true)
  detail "GET request_uri -> $status $ctype, header alg $(json_string alg <<<"$header")"
  if [[ $status != 200 || $ctype != application/oauth-authz-req+jwt* ]]; then
    result verify FAIL "request_uri answered $status $ctype"
  elif [[ $header != *'"x5c"'* ]]; then
    result verify FAIL "request object header has no x5c"
  elif [[ $(json_string client_id <<<"$payload") != "$VERIFY_CLIENT_ID" ]]; then
    result verify FAIL "request object client_id is not $VERIFY_CLIENT_ID"
  elif [[ $(json_string response_uri <<<"$payload") != "$VERIFY_URL/"* ]]; then
    result verify FAIL "response_uri is not under $VERIFY_URL"
  else
    result verify PASS "201 x509_san_dns request_uri"
  fi
}

# Inji Certify through the TLS proxy with the test CA, the way the suite (acting as the wallet) and the runner (acting
# as the issuer's back office) will use it: issuer metadata at the root well-known URL, the metadata of Certify as
# its own authorization server, then a pre-authorized offer redeemed at the token endpoint.
check_certify() {
  local out status body commit issuer token_endpoint offer_link offer_url code token_type access_token payload
  commit=$(docker image inspect --format '{{index .Config.Labels "commit_id"}}' \
    "$(dc --profile certify config --images | grep -m 1 inji-certify)" 2>/dev/null || true)
  detail "image commit_id label: ${commit:-unknown}"

  if ! body=$(probe -sS --fail-with-body --max-time 30 --cacert /pki/ca.crt \
    "$CERTIFY_URL/.well-known/openid-credential-issuer" 2>>"$OUT_DIR/probe.log"); then
    probe_errors
    result certify FAIL "GET $CERTIFY_URL/.well-known/openid-credential-issuer failed"
    return
  fi
  issuer=$(json_string credential_issuer <<<"$body")
  detail "credential_endpoint $(json_string credential_endpoint <<<"$body")"
  if [[ $issuer != "$CERTIFY_URL" ]]; then
    result certify FAIL "credential_issuer is '$issuer', expected $CERTIFY_URL"
  elif [[ $(json_string credential_endpoint <<<"$body") != "$CERTIFY_API/issuance/credential" ]]; then
    result certify FAIL "credential_endpoint is not $CERTIFY_API/issuance/credential"
  elif [[ ${body//[[:space:]]/} != *'"authorization_servers":["'"$CERTIFY_URL"'"'* ]]; then
    result certify FAIL "authorization_servers does not start with $CERTIFY_URL (Certify as its own server)"
  else
    result certify PASS "credential_issuer=$issuer"
  fi

  if ! body=$(probe -sS --fail-with-body --max-time 30 --cacert /pki/ca.crt \
    "$CERTIFY_URL/.well-known/oauth-authorization-server" 2>>"$OUT_DIR/probe.log"); then
    probe_errors
    result certify-as FAIL "GET $CERTIFY_URL/.well-known/oauth-authorization-server failed"
    return
  fi
  token_endpoint=$(json_string token_endpoint <<<"$body")
  detail "token_endpoint $token_endpoint"
  if [[ $(json_string issuer <<<"$body") != "$CERTIFY_URL" ]]; then
    result certify-as FAIL "AS issuer is not $CERTIFY_URL"
  elif [[ $token_endpoint != "$CERTIFY_API/oauth/token" ]]; then
    result certify-as FAIL "token_endpoint is not $CERTIFY_API/oauth/token"
  elif [[ $body != *"$PRE_AUTH_GRANT"* ]]; then
    result certify-as FAIL "grant_types_supported lacks the pre-authorized code grant"
  else
    result certify-as PASS token_endpoint
  fi

  # The issuer's back-office call. Errors come back as HTTP 200 with an "errors" list, so both are checked.
  if ! body=$(probe -sS --fail-with-body --max-time 30 --cacert /pki/ca.crt -H 'Content-Type: application/json' \
    -d "$CERTIFY_OFFER_REQUEST" "$CERTIFY_API/pre-authorized-data" 2>>"$OUT_DIR/probe.log"); then
    probe_errors
    result certify-preauth FAIL "POST $CERTIFY_API/pre-authorized-data failed"
    return
  fi
  offer_link=$(json_string credential_offer_uri <<<"$body")
  offer_url=$(sed -n 's/^openid-credential-offer:\/\/?credential_offer_uri=//p' <<<"$offer_link" | url_decode)
  if [[ $offer_url != "$CERTIFY_API/credential-offer-data/"* ]]; then
    detail "$body"
    result certify-preauth FAIL "no credential_offer_uri under $CERTIFY_API/credential-offer-data/"
    return
  fi
  if ! body=$(probe -sS --fail-with-body --max-time 30 --cacert /pki/ca.crt "$offer_url" 2>>"$OUT_DIR/probe.log"); then
    probe_errors
    result certify-preauth FAIL "GET $offer_url failed"
    return
  fi
  code=$(json_string pre-authorized_code <<<"$body")
  detail "offer $offer_url"
  if [[ $(json_string credential_issuer <<<"$body") != "$CERTIFY_URL" || -z $code ]]; then
    detail "$body"
    result certify-preauth FAIL "offer lacks credential_issuer $CERTIFY_URL or a pre-authorized code"
    return
  fi
  result certify-preauth PASS offer

  # The wallet's call: redeem the code. Certify validates its own tokens at the credential endpoint, so the token's
  # issuer must be the same origin as the credential issuer.
  if ! out=$(probe -sS --max-time 30 --cacert /pki/ca.crt -w '\n%{http_code}' \
    --data-urlencode "grant_type=$PRE_AUTH_GRANT" --data-urlencode "pre-authorized_code=$code" \
    "$CERTIFY_API/oauth/token" 2>>"$OUT_DIR/probe.log"); then
    probe_errors
    result certify-token FAIL "POST $CERTIFY_API/oauth/token failed"
    return
  fi
  status=$(tail -n 1 <<<"$out")
  body=$(sed '$d' <<<"$out")
  token_type=$(json_string token_type <<<"$body")
  access_token=$(json_string access_token <<<"$body")
  payload=$(cut -d . -f 2 <<<"$access_token" | b64url_decode || true)
  detail "POST /oauth/token -> $status, token_type $token_type, iss $(json_string iss <<<"$payload")"
  if [[ $status != 200 || -z $access_token ]]; then
    detail "$body"
    result certify-token FAIL "token endpoint answered $status without an access token"
  elif [[ $(json_string iss <<<"$payload") != "$CERTIFY_URL" ]]; then
    result certify-token FAIL "access token issuer is not $CERTIFY_URL"
  else
    result certify-token PASS "$token_type"
  fi
}

# MinIO: the bucket exists (minio-mc, the tools client), and an object can be written, read and deleted with
# signed path-style requests (http://minio:9000/<bucket>/<key>), the addressing the testrigs' S3Adapter uses.
check_minio() {
  local user password key out
  user=$(env_value MINIO_ROOT_USER harness)
  password=$(env_value MINIO_ROOT_PASSWORD)
  if ! out=$(dc --progress quiet run --rm --no-deps -T minio-mc stat "local/$MINIO_BUCKET_NAME" 2>&1); then
    detail "$out"
    result minio FAIL "bucket $MINIO_BUCKET_NAME not found"
    return
  fi
  key=smoke/$(date -u +%Y%m%dT%H%M%SZ)-$$.txt
  # The password goes to curl in a config file on stdin, not on the command line.
  if ! out=$(printf 'user = "%s:%s"\n' "$user" "$password" | probe -sS --fail-with-body --max-time 30 -K - \
    --aws-sigv4 aws:amz:us-east-1:s3 -X PUT --data-binary "smoke $key" "$MINIO_URL/$MINIO_BUCKET_NAME/$key" \
    2>>"$OUT_DIR/probe.log"); then
    probe_errors
    result minio FAIL "path-style PUT $MINIO_URL/$MINIO_BUCKET_NAME/$key failed"
    return
  fi
  out=$(printf 'user = "%s:%s"\n' "$user" "$password" | probe -sS --fail-with-body --max-time 30 -K - \
    --aws-sigv4 aws:amz:us-east-1:s3 "$MINIO_URL/$MINIO_BUCKET_NAME/$key" 2>>"$OUT_DIR/probe.log") || true
  printf 'user = "%s:%s"\n' "$user" "$password" | probe -sS --max-time 30 -K - --aws-sigv4 aws:amz:us-east-1:s3 \
    -X DELETE -o /dev/null "$MINIO_URL/$MINIO_BUCKET_NAME/$key" 2>>"$OUT_DIR/probe.log" || true
  if [[ $out != "smoke $key" ]]; then
    probe_errors
    result minio FAIL "path-style GET did not return the object just written"
    return
  fi
  detail "path-style PUT, GET and DELETE of $MINIO_BUCKET_NAME/$key"
  if command -v curl >/dev/null 2>&1 &&
    ! curl -fsS --max-time 10 -o /dev/null http://127.0.0.1:18900/minio/health/live 2>/dev/null; then
    result minio FAIL "no answer at http://127.0.0.1:18900 from the host"
    return
  fi
  result minio PASS "bucket $MINIO_BUCKET_NAME"
}

# ---------------------------------------------------------------------------------------------------------------
# Report and teardown
# ---------------------------------------------------------------------------------------------------------------

write_summary() {
  local peaks total=0 name mib first=1 check
  peaks=$(peak_memory)
  {
    printf '{\n  "date": "%s",\n  "profiles": "%s",\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${PROFILES[*]}"
    printf '  "start_seconds": %s,\n  "peak_memory_mib": {' "${START_SECONDS:-null}"
    while read -r name mib; do
      [[ -n $name ]] || continue
      ((first)) || printf ','
      printf '\n    "%s": %s' "$name" "$mib"
      total=$((total + mib))
      first=0
    done <<<"$peaks"
    printf '\n  },\n  "peak_memory_total_mib": %s,\n  "checks": [' "$total"
    first=1
    for check in "${CHECKS[@]}"; do
      ((first)) || printf ','
      printf '\n    "%s"' "${check//\"/\'}"
      first=0
    done
    printf '\n  ]\n}\n'
  } >"$OUT_DIR/smoke.json"
}

teardown() {
  local rc=$1
  trap - EXIT INT TERM
  stop_sampler
  ((STARTED)) || exit "$rc"

  if [[ -n $START_SECONDS ]]; then
    local peaks total
    peaks=$(peak_memory)
    total=$(awk '{ s += $2 } END { print s + 0 }' <<<"$peaks")
    if [[ -n $peaks ]]; then
      detail "peak memory (MiB): $(tr '\n' ' ' <<<"$peaks" | sed 's/ $//')"
      result stats PASS "peak ${total} MiB total, start ${START_SECONDS}s"
    fi
  fi
  if ((FAILURES)) || ((rc)); then
    dc --profile '*' logs --no-color --timestamps >"$OUT_DIR/compose.log" 2>&1 || true
    detail "compose logs: $OUT_DIR/compose.log"
  fi

  if dc --profile '*' down --volumes --remove-orphans --timeout 20 >"$OUT_DIR/down.log" 2>&1 &&
    [[ -z $(project_containers) ]] &&
    [[ -z $(docker volume ls -q --filter "label=$PROJECT_LABEL") ]]; then
    result teardown PASS
  else
    detail "see $OUT_DIR/down.log"
    result teardown FAIL "containers or volumes of $HARNESS_COMPOSE_PROJECT are left"
  fi
  write_summary
  detail "summary: $OUT_DIR/smoke.json"
  if ((FAILURES)) || ((rc)); then
    exit 1
  fi
  exit 0
}

main() {
  local profile known p
  (($#)) || {
    usage >&2
    exit 2
  }
  for profile in "$@"; do
    case $profile in
      -h | --help)
        usage
        exit 0
        ;;
    esac
    known=0
    for p in "${KNOWN_PROFILES[@]}"; do [[ $profile == "$p" ]] && known=1; done
    ((known)) || {
      log_error "unknown profile: $profile"
      usage >&2
      exit 2
    }
    PROFILES+=("$profile")
    PROFILE_ARGS+=(--profile "$profile")
  done
  harness_require_cmd docker

  OUT_DIR=$(harness_run_dir "smoke/$(date -u +%Y%m%dT%H%M%SZ)-$(tr ' ' '-' <<<"${PROFILES[*]}")")

  if [[ -n $(project_containers) ]]; then
    result precheck FAIL "containers of $HARNESS_COMPOSE_PROJECT already exist; stop them first: bash scripts/dc.sh --profile '*' down"
    exit 1
  fi
  check_ports_free || exit 1

  # The probe and minio-mc images belong to the tools profile, which "pull --profile <component>" leaves out.
  # Both are small.
  local tool_image
  while read -r tool_image; do
    if [[ -n $tool_image ]] && ! docker image inspect "$tool_image" >/dev/null 2>&1; then
      log_info "pulling the tool image $tool_image"
      docker pull -q "$tool_image" >/dev/null
    fi
  done < <(dc --profile tools config --images | grep -E 'curl|/mc:' || true)

  trap 'teardown $?' EXIT
  trap 'exit 130' INT TERM
  STARTED=1
  sample_stats &
  SAMPLER_PID=$!

  local start end
  start=$(date +%s)
  if ! dc "${PROFILE_ARGS[@]}" up --detach --wait --wait-timeout "$START_TIMEOUT" >"$OUT_DIR/up.log" 2>&1; then
    tail -n 20 "$OUT_DIR/up.log" | sed 's/^/  /'
    result start FAIL "services not healthy within ${START_TIMEOUT}s (log: $OUT_DIR/up.log)"
    exit 1
  fi
  end=$(date +%s)
  START_SECONDS=$((end - start))
  result start PASS "${START_SECONDS}s to healthy (${PROFILES[*]})"

  if has_profile verify || has_profile certify; then
    check_pki
  fi
  # Every component profile brings the suite (docker-compose.yml); "reports" alone does not.
  if has_profile suite || has_profile verify || has_profile certify; then
    check_suite
  fi
  if has_profile verify; then
    check_verify
  fi
  if has_profile certify; then
    check_certify
  fi
  if has_profile reports; then
    check_minio
  fi
  # One more memory sample after the checks, which load the services.
  sleep "$STATS_INTERVAL"
}

# Run main only when executed, so that tests can source this file and call its helpers.
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
