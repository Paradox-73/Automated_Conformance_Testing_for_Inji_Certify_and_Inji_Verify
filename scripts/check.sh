#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
#
# Repository checks. Prints one line per check: PASS, FAIL or SKIP, the check name and a short reason.
#
#   bash scripts/check.sh [--strict] [all | CHECK...]
#
# CHECK is one or more of:
#   eol        team files use LF line endings. Upstream files that are stored with CRLF upstream are allowed only
#              while they stay byte-identical to the imported blob listed in scripts/eol-exempt.txt.
#   secrets    no private keys, access tokens or credential assignments in files git would commit. Paths listed
#              under secret.ignored-paths in .gitguardian.yaml (upstream test fixtures) and lines carrying a
#              "ggignore" marker are left out, the same rules GitGuardian's ggshield applies.
#   shell      shellcheck on every *.sh and *.bash file, then every scripts/tests/test-*.sh test script.
#   runner     when runner/pyproject.toml exists: installs the runner into $HARNESS_RUN_DIR/venv, runs ruff and
#              pytest, then "inji-conformance validate" on conformance/schema/examples/*.json (files named
#              *.invalid.json must be rejected, every other example must be valid).
#   testrigs   when testrigs/pom.xml exists: Maven "verify" of the conformance bridge module (and what it needs),
#              or of the whole testrigs build when the bridge module does not exist. Needs JDK 21.
#   workflows  when .github/workflows or .github/examples hold YAML files: actionlint on them.
#   docs       when docs/tools/check_docs.py exists: runs it; its exit status is the result.
# With no CHECK, or with "all", every check runs in the order above.
#
# A check whose inputs do not exist yet prints SKIP. A check whose inputs exist but whose tool (shellcheck,
# actionlint, Python 3.12+, Maven, JDK 21) is missing also prints SKIP, with the reason; in strict mode
# (--strict, CI=true as set by GitHub Actions, or HARNESS_CHECK_STRICT=1) it prints FAIL instead, so CI never
# passes by skipping.
#
# Exit status: 0 when no check failed, 1 when at least one check failed, 2 for a usage error.
#
# The checks read the working tree: tracked files plus untracked files that .gitignore does not exclude, so new
# files are checked before they are committed.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

readonly ALL_CHECKS=(eol secrets shell runner testrigs workflows docs)

# Exit codes a check uses to report its result to run_check. Anything else is an unexpected error.
readonly RC_PASS=0 RC_FAIL=1 RC_SKIP=3

# Carriage return and line feed, set once at top level: the MSYS build of bash in Git Bash drops a $'\r' written
# inside $(...) or <(...), which would turn the CRLF search into a search for the empty string.
readonly CR=$'\r' LF=$'\n'

STRICT=0
if [[ ${CI:-} == true || ${HARNESS_CHECK_STRICT:-0} == 1 ]]; then
  STRICT=1
fi

usage() {
  cat <<EOF
Usage: bash scripts/check.sh [--strict] [all | CHECK...]
Checks: ${ALL_CHECKS[*]}
EOF
}

# ---------------------------------------------------------------------------------------------------------------
# Result helpers. Each check runs in a subshell, writes its one-line reason to $RESULT_FILE and exits with RC_*.
# Detail lines (which file failed, tool output) go to stdout before the result line, indented by two spaces.
# ---------------------------------------------------------------------------------------------------------------

pass() {
  printf '%s' "$1" >"$RESULT_FILE"
  exit "$RC_PASS"
}
fail() {
  printf '%s' "$1" >"$RESULT_FILE"
  exit "$RC_FAIL"
}
skip() {
  printf '%s' "$1" >"$RESULT_FILE"
  exit "$RC_SKIP"
}
# skip_tool REASON: the inputs exist but a tool is missing. FAIL in strict mode, SKIP otherwise.
skip_tool() {
  if ((STRICT)); then
    fail "$1 (strict mode)"
  fi
  skip "$1"
}

detail() {
  printf '  %s\n' "$@"
}

# run_indented CMD [ARGS...]: run a command with its stdout and stderr indented; return the command's status.
run_indented() {
  local rc=0
  "$@" 2>&1 | sed 's/^/  /' || rc=${PIPESTATUS[0]}
  return "$rc"
}

# repo_files [PATHSPEC...]: NUL-separated list of files git would commit (tracked or untracked and not ignored)
# that exist in the working tree.
repo_files() {
  local -A seen=()
  local file
  while IFS= read -r -d '' file; do
    if [[ -z ${seen[$file]:-} && -f $file ]]; then
      seen[$file]=1
      printf '%s\0' "$file"
    fi
  done < <(git ls-files -z --cached --others --exclude-standard -- "$@")
}

# git_grep ARGS...: git grep over tracked and untracked (not ignored) text files. Prints matches; returns 0 for
# matches or no matches, and fails only on a real git error (status 2 or higher).
git_grep() {
  local rc=0
  git grep -I --untracked "$@" || rc=$?
  ((rc <= 1)) || return "$rc"
}

# collect ARRAY DELIMITER CMD [ARGS...]: run CMD and store its output in ARRAY, split at DELIMITER ('' for NUL).
# Fails the check when CMD fails. Unlike mapfile < <(CMD), a failing command cannot pass as "no output", which
# would turn a broken scan into a PASS.
collect() {
  local -n _collect_into=$1
  local delimiter=$2 tmp
  shift 2
  tmp=$(mktemp)
  if ! "$@" >"$tmp"; then
    rm -f "$tmp"
    fail "command failed: $*"
  fi
  mapfile -t -d "$delimiter" _collect_into <"$tmp"
  rm -f "$tmp"
}

# ---------------------------------------------------------------------------------------------------------------
# eol
# ---------------------------------------------------------------------------------------------------------------

check_eol() {
  local exempt_file=scripts/eol-exempt.txt
  local -A exempt=()
  local line n=0 bad=0 path actual

  if [[ -f $exempt_file ]]; then
    while IFS= read -r line || [[ -n $line ]]; do
      n=$((n + 1))
      [[ $line =~ ^[[:space:]]*(#|$) ]] && continue
      if [[ $line =~ ^([0-9a-f]{40})[[:space:]]+([^[:space:]].*)$ ]]; then
        exempt[${BASH_REMATCH[2]}]=${BASH_REMATCH[1]}
      else
        detail "$exempt_file:$n: expected '<40-hex git blob id> <path>'"
        bad=1
      fi
    done <"$exempt_file"
  fi

  local -a text_files=() crlf_files=()
  collect text_files '' git_grep -z -l -e ''
  collect crlf_files '' git_grep -z -l -e "$CR"

  local exempted=0 offenders=0
  for path in "${crlf_files[@]}"; do
    if [[ -n ${exempt[$path]:-} ]]; then
      # --no-filters hashes the bytes on disk, the same bytes git stores because .gitattributes sets -text.
      actual=$(git hash-object --no-filters -- "$path")
      if [[ $actual == "${exempt[$path]}" ]]; then
        exempted=$((exempted + 1))
        continue
      fi
      detail "$path: CRLF file changed since import (blob $actual, $exempt_file lists ${exempt[$path]})" \
        "  keep the upstream bytes, or convert the file to LF and remove its line from $exempt_file"
    else
      detail "$path: CRLF line endings (convert to LF)"
    fi
    offenders=$((offenders + 1))
  done

  if ((bad)); then
    fail "malformed $exempt_file"
  fi
  if ((offenders)); then
    fail "$offenders of ${#text_files[@]} text files have CRLF line endings"
  fi
  pass "${#text_files[@]} text files use LF ($exempted byte-identical upstream CRLF files exempted)"
}

# ---------------------------------------------------------------------------------------------------------------
# secrets
# ---------------------------------------------------------------------------------------------------------------

# Prints the secret.ignored-paths entries of .gitguardian.yaml, one per line. Reads the subset of YAML that file
# uses: a top-level "secret:" mapping with an "ignored-paths:" block list of plain or quoted strings.
gitguardian_ignored_paths() {
  [[ -f .gitguardian.yaml ]] || return 0
  awk '
    /^[^[:space:]#]/ { top = $0; sub(/:.*/, "", top); in_list = 0; next }
    top == "secret" && /^[[:space:]]+ignored-paths:[[:space:]]*$/ { in_list = 1; next }
    in_list && /^[[:space:]]*(#.*)?$/ { next }
    in_list && /^[[:space:]]+-[[:space:]]/ {
      value = $0
      sub(/^[[:space:]]+-[[:space:]]+/, "", value)
      sub(/[[:space:]]+#.*$/, "", value)
      sub(/[[:space:]]+$/, "", value)
      if (value ~ /^".*"$/ || value ~ /^\047.*\047$/) value = substr(value, 2, length(value) - 2)
      print value
      next
    }
    in_list { in_list = 0 }
  ' .gitguardian.yaml
}

check_secrets() {
  local -a ignored=()
  mapfile -t ignored < <(gitguardian_ignored_paths)

  # is_ignored PATH: true when PATH matches an ignored-paths glob ("*" also matches "/", like ggshield).
  is_ignored() {
    local pattern
    for pattern in "${ignored[@]}"; do
      # shellcheck disable=SC2053 # the right-hand side is a glob on purpose
      [[ $1 == $pattern ]] && return 0
    done
    return 1
  }

  # Rules: a name and a POSIX extended regular expression. JWTs are not a rule: signed test credentials (SD-JWT
  # VCs) are normal test data in this project.
  local tokens='(AKIA|ASIA)[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,}'
  tokens+='|glpat-[A-Za-z0-9_-]{20,}|xox[abposr]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}'
  # A key whose name contains a credential word, assigned a literal of 4+ characters. Values starting with $, {, <
  # or % are references or placeholders, not credentials.
  local assignment='(pass(word|wd)?|pwd|secret|api[_.-]?key|access[_.-]?key|private[_.-]?key|auth[_.-]?token'
  assignment+="|access[_.-]?token|refresh[_.-]?token)[A-Za-z0-9_-]*[\"']?[[:space:]]*[:=][[:space:]]*[\"']?"
  assignment+="[^[:space:]\"'\$<>{}%]{4,}"
  local -a rule_names=(private-key-pem private-jwk access-token credential-assignment)
  local -a rule_patterns=(
    '-----BEGIN[ A-Z0-9]*PRIVATE KEY( BLOCK)?-----'
    '"d"[[:space:]]*:[[:space:]]*"[A-Za-z0-9_-]{16,}"'
    "$tokens"
    "$assignment"
  )
  # The credential-assignment rule only reads configuration-like files; in source code the same shape is a
  # variable assignment, not a credential.
  local -a config_files=('*.properties' '*.yml' '*.yaml' '*.json' '*.env' '*.conf' '*.cfg' '*.ini' '*.toml'
    '*.xml' '*.sh' '*Dockerfile*')

  local findings=0 i match path lineno text
  local -A ignored_hits=()
  for i in "${!rule_names[@]}"; do
    local -a opts=(-n -E -e "${rule_patterns[$i]}")
    local -a specs=()
    if [[ ${rule_names[$i]} == credential-assignment ]]; then
      opts=(-i "${opts[@]}")
      specs=("${config_files[@]}")
    fi
    local -a matches=()
    collect matches "$LF" git_grep "${opts[@]}" -- "${specs[@]}"
    for match in "${matches[@]}"; do
      [[ $match =~ ^([^:]+):([0-9]+):(.*)$ ]] || continue
      path=${BASH_REMATCH[1]} lineno=${BASH_REMATCH[2]} text=${BASH_REMATCH[3]}
      if is_ignored "$path"; then
        ignored_hits[$path]=1
        continue
      fi
      [[ $text == *ggignore* ]] && continue
      if [[ ${rule_names[$i]} == credential-assignment && $text =~ [:=][[:space:]]*[\"\']?[a-z]+:// ]]; then
        continue # a URL (for example a token endpoint), not a credential
      fi
      if [[ ${rule_names[$i]} == credential-assignment && $text =~ [:=][[:space:]]*(true|false|null)[[:space:]]*,?[[:space:]]*$ ]]; then
        continue # a JSON or YAML true, false or null value (a flag such as a gate result), not a credential
      fi
      if [[ ${rule_names[$i]} == credential-assignment && $path == docs/evidence/*/results.json ]]; then
        # Committed run results: a module name that contains a credential word, followed by a colon and the result,
        # has the shape of an assignment. The key and token rules above still read these files.
        continue
      fi
      # The matched text is never printed, so a real secret does not end up in CI logs.
      detail "$path:$lineno: ${rule_names[$i]}"
      findings=$((findings + 1))
    done
  done

  # Key stores are binary, so the content rules above cannot see inside them.
  local -a key_stores=()
  mapfile -d '' key_stores < <(repo_files '*.p12' '*.pfx' '*.jks' '*.keystore' '*.key' '*id_rsa' '*id_ecdsa' \
    '*id_ed25519')
  for path in "${key_stores[@]}"; do
    if is_ignored "$path"; then
      ignored_hits[$path]=1
      continue
    fi
    detail "$path: key store or private key file"
    findings=$((findings + 1))
  done

  if ((findings)); then
    fail "$findings possible secrets (keep them out of git, or list a test-only fixture in .gitguardian.yaml)"
  fi
  local -a scanned=()
  collect scanned '' git_grep -z -l -e ''
  local note="${#ignored_hits[@]} files skipped as fixtures listed in .gitguardian.yaml"
  pass "${#scanned[@]} text files scanned, no findings ($note)"
}

# ---------------------------------------------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------------------------------------------

check_shell() {
  local -a scripts=() tests=()
  mapfile -d '' scripts < <(repo_files '*.sh' '*.bash')
  ((${#scripts[@]})) || skip "no shell scripts"

  local shellcheck
  shellcheck=$(harness_find_tool shellcheck) ||
    skip_tool "shellcheck not found on PATH or in $HARNESS_TOOLS_DIR/bin"
  local version
  version=$("$shellcheck" --version | sed -n 's/^version: //p')

  if ! run_indented "$shellcheck" --external-sources --format=gcc -- "${scripts[@]}"; then
    fail "shellcheck $version reported problems"
  fi

  if [[ -d scripts/tests ]]; then
    mapfile -d '' tests < <(repo_files 'scripts/tests/test-*.sh')
  fi
  local test failed=0 output
  for test in "${tests[@]}"; do
    if ! output=$(bash "$test" 2>&1); then
      detail "$test failed:"
      printf '%s\n' "$output" | tail -n 30 | sed 's/^/    /'
      failed=$((failed + 1))
    fi
  done
  if ((failed)); then
    fail "$failed of ${#tests[@]} shell test scripts failed"
  fi
  pass "${#scripts[@]} scripts clean under shellcheck $version, ${#tests[@]} shell test scripts passed"
}

# ---------------------------------------------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------------------------------------------

check_runner() {
  [[ -f runner/pyproject.toml ]] || skip "no runner/pyproject.toml"

  local python venv venv_python stamp_file want have
  python=$(harness_find_python) || skip_tool "Python 3.$HARNESS_PYTHON_MIN_MINOR or newer not found"
  venv=$HARNESS_RUN_DIR/venv
  if ! venv_python=$(harness_venv_python "$venv"); then
    log_info "creating Python virtual environment in $venv"
    run_indented "$python" -m venv "$venv" || fail "cannot create the virtual environment $venv"
    venv_python=$(harness_venv_python "$venv") || fail "no interpreter in $venv after creating it"
  fi

  # Reinstall only when pyproject.toml or constraints.txt changed; the install is editable (source edits need none).
  stamp_file=$venv/.runner-pyproject.sha256
  want=$("$venv_python" -c \
    'import hashlib, sys; print(hashlib.sha256(b"".join(open(f, "rb").read() for f in sys.argv[1:])).hexdigest())' \
    runner/pyproject.toml runner/constraints.txt)
  have=$(cat "$stamp_file" 2>/dev/null || true)
  if [[ $want != "$have" ]]; then
    log_info "installing the runner and its dev dependencies into $venv"
    run_indented "$venv_python" -m pip install --quiet --disable-pip-version-check -c runner/constraints.txt --editable "./runner[dev]" ||
      fail "pip install of runner[dev] failed"
    printf '%s\n' "$want" >"$stamp_file"
  fi

  "$venv_python" -m ruff --version >/dev/null 2>&1 ||
    fail "ruff is not installed in $venv; declare it in the dev extra of runner/pyproject.toml"
  run_indented "$venv_python" -m ruff check runner || fail "ruff reported problems"

  local tests_note="no runner/tests"
  if [[ -d runner/tests ]]; then
    run_indented "$venv_python" -m pytest -q runner/tests || fail "pytest failed"
    tests_note="pytest passed"
  fi

  local -a examples=()
  local example cli rc valid=0 rejected=0
  shopt -s nullglob
  examples=(conformance/schema/examples/*.json)
  shopt -u nullglob
  if ((${#examples[@]})); then
    cli=$(dirname "$venv_python")/inji-conformance
    [[ -x $cli || -x $cli.exe ]] || fail "the inji-conformance command is not installed in $venv"
    for example in "${examples[@]}"; do
      rc=0
      run_indented "$cli" validate "$example" || rc=$?
      if [[ $example == *.invalid.json ]]; then
        ((rc != 0)) || fail "$example should be rejected but validated"
        rejected=$((rejected + 1))
      else
        ((rc == 0)) || fail "$example should be valid but was rejected"
        valid=$((valid + 1))
      fi
    done
  fi
  pass "ruff clean, $tests_note, $valid examples valid, $rejected invalid examples rejected"
}

# ---------------------------------------------------------------------------------------------------------------
# testrigs
# ---------------------------------------------------------------------------------------------------------------

# java_major: print the major version of the JDK Maven will use (JAVA_HOME first, then java on PATH).
java_major() {
  local java=java version
  if [[ -n ${JAVA_HOME:-} && -x $JAVA_HOME/bin/java ]]; then
    java=$JAVA_HOME/bin/java
  elif ! command -v java >/dev/null 2>&1; then
    return 1
  fi
  version=$("$java" -version 2>&1 | sed -n 's/.*version "\([0-9][0-9]*\).*/\1/p' | head -n 1)
  [[ -n $version ]] && printf '%s\n' "$version"
}

check_testrigs() {
  [[ -f testrigs/pom.xml ]] || skip "no testrigs/pom.xml"

  local mvn major
  mvn=$(harness_find_tool mvn) || skip_tool "Maven (mvn) not found"
  major=$(java_major) || skip_tool "no JDK found (JDK 21 needed)"
  ((major >= 21)) || skip_tool "JDK 21 needed, JAVA_HOME points to JDK $major"

  # Maven 3.9 also reads extra options (for example a settings file) from the MAVEN_ARGS environment variable.
  run_indented "$mvn" -B --no-transfer-progress -f testrigs/pom.xml -pl apitest-commons-conformance -am verify ||
    fail "Maven verify failed (bridge module)"
  pass "Maven verify passed (bridge module, JDK $major)"
}

# ---------------------------------------------------------------------------------------------------------------
# workflows
# ---------------------------------------------------------------------------------------------------------------

check_workflows() {
  local -a files=()
  mapfile -d '' files < <(repo_files '.github/workflows/*.yml' '.github/workflows/*.yaml' \
    '.github/examples/*.yml' '.github/examples/*.yaml')
  ((${#files[@]})) || skip "no workflow files"

  local actionlint shellcheck
  actionlint=$(harness_find_tool actionlint) ||
    skip_tool "actionlint not found on PATH or in $HARNESS_TOOLS_DIR/bin"
  # actionlint also runs shellcheck on every run: step when it can find it; an empty value turns that off.
  shellcheck=$(harness_find_tool shellcheck || true)
  run_indented "$actionlint" -no-color -shellcheck="$shellcheck" "${files[@]}" ||
    fail "actionlint reported problems"
  pass "${#files[@]} workflow files clean under actionlint $("$actionlint" -version | head -n 1)"
}

# ---------------------------------------------------------------------------------------------------------------
# docs
# ---------------------------------------------------------------------------------------------------------------

check_docs() {
  [[ -f docs/tools/check_docs.py ]] || skip "no docs/tools/check_docs.py"
  local python
  # Prefer the runner's venv, which has the project's Python packages; fall back to the system interpreter.
  python=$(harness_venv_python "$HARNESS_RUN_DIR/venv" || harness_find_python) ||
    skip_tool "Python 3.$HARNESS_PYTHON_MIN_MINOR or newer not found"
  # The checker's own tests first (a broken rule must not pass every document), from docs/tools without bytecode.
  (cd docs/tools && PYTHONDONTWRITEBYTECODE=1 run_indented "$python" -m unittest -q test_check_docs) ||
    fail "the tests of docs/tools/check_docs.py failed"
  run_indented "$python" docs/tools/check_docs.py || fail "docs/tools/check_docs.py reported problems"
  pass "docs/tools/check_docs.py and its tests passed"
}

# ---------------------------------------------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------------------------------------------

PASSED=0 FAILED=0 SKIPPED=0

run_check() {
  local name=$1 rc status reason
  RESULT_FILE=$(mktemp)
  # The subshell keeps each check's cd, variables and exit separate. "set +e" around it lets a failing check
  # report instead of stopping the whole script; inside the subshell set -e stays on.
  set +e
  (
    set -e
    cd "$HARNESS_ROOT"
    "check_$name"
  )
  rc=$?
  set -e
  reason=$(cat "$RESULT_FILE")
  rm -f "$RESULT_FILE"
  case $rc in
    "$RC_PASS") status=PASS PASSED=$((PASSED + 1)) ;;
    "$RC_SKIP") status=SKIP SKIPPED=$((SKIPPED + 1)) ;;
    "$RC_FAIL") status=FAIL FAILED=$((FAILED + 1)) ;;
    *)
      status=FAIL FAILED=$((FAILED + 1))
      reason="unexpected error (exit $rc)${reason:+: $reason}"
      ;;
  esac
  printf '%-4s  %-9s  %s\n' "$status" "$name" "$reason"
}

main() {
  local -a selected=()
  local arg name
  for arg in "$@"; do
    case $arg in
      -h | --help)
        usage
        return 0
        ;;
      --strict) STRICT=1 ;;
      all) selected+=("${ALL_CHECKS[@]}") ;;
      *)
        if [[ " ${ALL_CHECKS[*]} " == *" $arg "* ]]; then
          selected+=("$arg")
        else
          usage >&2
          log_error "unknown check: $arg"
          return 2
        fi
        ;;
    esac
  done
  ((${#selected[@]})) || selected=("${ALL_CHECKS[@]}")

  command -v git >/dev/null 2>&1 || die "git not found" 2
  git -C "$HARNESS_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
    die "$HARNESS_ROOT is not a git working tree" 2

  for name in "${selected[@]}"; do
    run_check "$name"
  done
  printf 'checks: %d passed, %d failed, %d skipped\n' "$PASSED" "$FAILED" "$SKIPPED"
  ((FAILED == 0))
}

main "$@"
