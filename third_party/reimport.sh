#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
#
# Keeps third_party/oidf-conformance-suite/ identical to the OpenID Foundation conformance suite files it was
# imported from, and moves it to a newer suite release.
#
#   bash third_party/reimport.sh check          offline: every file under oidf-conformance-suite/ has the git blob id
#                                               recorded in this script's manifest, and no other file is there
#   bash third_party/reimport.sh verify         the manifest matches the upstream commit: the recorded tag still
#                                               points at the recorded commit and every recorded blob id is the
#                                               file at that commit (fetches the tag once if the clone lacks it)
#   bash third_party/reimport.sh import REF     replace the imported files with those of upstream REF (a tag such as
#                                               release-v5.4.0, or a full 40-character commit id), then rewrite the
#                                               manifest in this script; it never commits
#
# Exit status: 0 success, 1 a file or id does not match, 2 usage error or upstream problem.
#
# Settings (environment variables, all optional):
#   OIDF_SUITE_URL    upstream repository. Default https://gitlab.com/openid/conformance-suite.git
#   OIDF_SUITE_CLONE  local clone used by verify and import. Default ../upstream/conformance-suite next to the
#                     repository when that folder exists, otherwise $HARNESS_RUN_DIR/upstream/conformance-suite
#                     (created on first use with a shallow fetch of the one tag needed).
#
# Files are written with "git cat-file blob <commit>:<path>", which copies the stored bytes with no conversion at
# all. "git archive" would also do, but only with core.autocrlf=false: Git for Windows defaults to
# core.autocrlf=true and archive then rewrites LF to CRLF. Archive also applies export-subst and export-ignore
# attributes. The repository's .gitattributes ("* -text") keeps git from converting the files on commit.
#
# Upgrade procedure (see third_party/README.md):
#   1. bash third_party/reimport.sh import release-vX.Y.Z
#   2. commit third_party/oidf-conformance-suite alone: "import: upstream openid/conformance-suite@<commit> (MIT)"
#   3. update the provenance table in third_party/README.md, commit it with this script (the rewritten manifest)

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SELF=$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")
# shellcheck source=../scripts/lib/common.sh
source "$SCRIPT_DIR/../scripts/lib/common.sh"

DEST=$SCRIPT_DIR/oidf-conformance-suite
SUITE_URL=${OIDF_SUITE_URL:-https://gitlab.com/openid/conformance-suite.git}

# Upstream paths to import, relative to the suite's repository root. The runner needs the first four scripts:
# run-test-plan.py drives a plan through the suite's REST API and imports conformance.py (the API client) and
# test_plan_parser.py; compare-results.py diffs two exports. requirements.txt lists their Python dependencies and
# LICENSE.txt carries the MIT terms. scripts/certs-keys/ is deliberately absent: it holds upstream test private
# keys, and the harness generates its own keys at run time.
IMPORT_PATHS=(
  LICENSE.txt
  scripts/compare-results.py
  scripts/conformance.py
  scripts/requirements.txt
  scripts/run-test-plan.py
  scripts/test_plan_parser.py
)

# BEGIN MANIFEST (rewritten by "reimport.sh import"; one line per file: <git blob id> <path>)
SUITE_REF=release-v5.3.1
SUITE_COMMIT=440eec8bac7b12b7389d7ca9cbc459b53507a443
SUITE_FILES=(
  "a25d7ee3d339e80d91714e4427ca5d695287241c LICENSE.txt"
  "3cedbda8d37c71e95daeb41db75a2cabd3918620 scripts/compare-results.py"
  "b72f7f6d53f3029986e6b98f39f0b96b3dc61201 scripts/conformance.py"
  "c491c56b29d622544d18387f78a664d42189b6d7 scripts/requirements.txt"
  "45e82abab5713cd03b9305ae2ed5bbac9c3a7ba2 scripts/run-test-plan.py"
  "872aff69b61635a147730343bb4184ef304c92ee scripts/test_plan_parser.py"
)
# END MANIFEST

usage() {
  sed -n '4,16p' "$SELF" | sed 's/^# \{0,1\}//'
}

# blob_id FILE: the git blob id of FILE's bytes, with no line-ending or attribute filters applied.
blob_id() {
  git hash-object --no-filters -- "$1"
}

# ---------------------------------------------------------------------------------------------------------------
# check: offline comparison of the working tree with the manifest.
# ---------------------------------------------------------------------------------------------------------------

cmd_check() {
  local entry id path problems=0
  local -A listed=()
  [[ -d $DEST ]] || die "$DEST does not exist" 1
  for entry in "${SUITE_FILES[@]}"; do
    id=${entry%% *} path=${entry#* }
    listed[$path]=1
    if [[ ! -f $DEST/$path ]]; then
      log_error "missing: $path"
      problems=$((problems + 1))
    elif [[ $(blob_id "$DEST/$path") != "$id" ]]; then
      log_error "changed: $path (blob $(blob_id "$DEST/$path"), manifest $id)"
      problems=$((problems + 1))
    fi
  done
  # Anything else in the folder is either a local edit or upstream material that must not be imported, such as
  # scripts/certs-keys/.
  while IFS= read -r -d '' path; do
    path=${path#"$DEST"/}
    if [[ -z ${listed[$path]:-} ]]; then
      log_error "not in the manifest: $path"
      problems=$((problems + 1))
    fi
  done < <(find "$DEST" -type f -print0)
  if ((problems)); then
    log_error "$problems problem(s): oidf-conformance-suite/ differs from openid/conformance-suite@${SUITE_COMMIT:0:12}"
    return 1
  fi
  log_info "oidf-conformance-suite/: ${#SUITE_FILES[@]} files identical to openid/conformance-suite@${SUITE_COMMIT:0:12} ($SUITE_REF)"
}

# ---------------------------------------------------------------------------------------------------------------
# Upstream clone helpers for verify and import.
# ---------------------------------------------------------------------------------------------------------------

suite_clone_dir() {
  if [[ -n ${OIDF_SUITE_CLONE:-} ]]; then
    printf '%s\n' "$OIDF_SUITE_CLONE"
  elif [[ -d $HARNESS_ROOT/../upstream/conformance-suite/.git ]]; then
    (cd "$HARNESS_ROOT/../upstream/conformance-suite" && pwd)
  else
    printf '%s\n' "$HARNESS_RUN_DIR/upstream/conformance-suite"
  fi
}

# open_clone: set CLONE, creating an empty repository with an origin remote when the folder does not exist yet.
open_clone() {
  CLONE=$(suite_clone_dir)
  if [[ ! -d $CLONE/.git ]]; then
    log_info "creating $CLONE (fetches only the commits that are asked for)"
    mkdir -p "$CLONE"
    git -C "$CLONE" init -q
    git -C "$CLONE" config core.longpaths true
    git -C "$CLONE" remote add origin "$SUITE_URL"
  fi
}

local_commit() {
  git -C "$CLONE" rev-parse -q --verify "$1^{commit}" 2>/dev/null
}

# resolve_ref REF: print the commit id REF names, fetching it shallowly from origin when the clone lacks it. A
# tag is looked up locally first and then on origin; a 40-character id is fetched by id.
resolve_ref() {
  local ref=$1 commit
  if [[ $ref =~ ^[0-9a-f]{40}$ ]]; then
    if ! commit=$(local_commit "$ref"); then
      git -C "$CLONE" fetch -q --depth 1 origin "$ref" >&2 || die "cannot fetch commit $ref from $(git -C "$CLONE" remote get-url origin)" 2
      commit=$(local_commit "$ref") || die "commit $ref not found after fetching" 2
    fi
  elif ! commit=$(local_commit "refs/tags/$ref"); then
    log_info "fetching tag $ref from $(git -C "$CLONE" remote get-url origin)"
    git -C "$CLONE" fetch -q --depth 1 --no-tags origin "refs/tags/$ref:refs/tags/$ref" >&2 ||
      die "cannot fetch tag $ref (only tags and full commit ids are accepted, so an import is always pinned)" 2
    commit=$(local_commit "refs/tags/$ref") || die "tag $ref does not name a commit" 2
  fi
  printf '%s\n' "$commit"
}

# remote_tag_commit TAG: print the commit TAG names on origin (empty when the tag does not exist there). Returns 1
# when origin cannot be reached. For an annotated tag, ls-remote lists the tag object and, with "^{}", the commit.
# shellcheck disable=SC2329 # used by cmd_verify, which main runs as "cmd_$cmd"
remote_tag_commit() {
  local tag=$1 lines
  lines=$(git -C "$CLONE" ls-remote origin "refs/tags/$tag" "refs/tags/$tag^{}" 2>/dev/null) || return 1
  awk -v peeled="refs/tags/$tag^{}" -v plain="refs/tags/$tag" '
    $2 == peeled { commit = $1 }
    $2 == plain && commit == "" { commit = $1 }
    END { print commit }' <<<"$lines"
}

# ---------------------------------------------------------------------------------------------------------------
# verify: the manifest describes the upstream commit exactly.
# ---------------------------------------------------------------------------------------------------------------

# shellcheck disable=SC2329 # run by main as "cmd_$cmd"
cmd_verify() {
  local entry id path upstream commit problems=0
  open_clone
  # Ask origin where the tag points today, so a tag that was moved after the import is reported. Without network
  # the local copy of the tag is the best evidence available.
  if commit=$(remote_tag_commit "$SUITE_REF"); then
    if [[ -z $commit ]]; then
      log_error "tag $SUITE_REF no longer exists in $(git -C "$CLONE" remote get-url origin)"
      problems=$((problems + 1))
    elif [[ $commit != "$SUITE_COMMIT" ]]; then
      log_error "tag $SUITE_REF now points at $commit upstream, the manifest records $SUITE_COMMIT"
      problems=$((problems + 1))
    fi
  else
    log_warn "cannot reach $(git -C "$CLONE" remote get-url origin); comparing with the local tag only"
    commit=$(local_commit "refs/tags/$SUITE_REF") || commit=
    if [[ -n $commit && $commit != "$SUITE_COMMIT" ]]; then
      log_error "local tag $SUITE_REF points at $commit, the manifest records $SUITE_COMMIT"
      problems=$((problems + 1))
    fi
  fi
  # Make sure the recorded commit itself is present: fetch the tag (the usual case), else the commit by id.
  if ! local_commit "$SUITE_COMMIT" >/dev/null; then
    (resolve_ref "$SUITE_REF" >/dev/null) || true
    local_commit "$SUITE_COMMIT" >/dev/null || resolve_ref "$SUITE_COMMIT" >/dev/null
  fi
  for entry in "${SUITE_FILES[@]}"; do
    id=${entry%% *} path=${entry#* }
    if ! upstream=$(git -C "$CLONE" rev-parse -q --verify "$SUITE_COMMIT:$path"); then
      log_error "upstream commit ${SUITE_COMMIT:0:12} has no $path"
      problems=$((problems + 1))
    elif [[ $upstream != "$id" ]]; then
      log_error "manifest id of $path is $id, upstream blob is $upstream"
      problems=$((problems + 1))
    fi
  done
  ((problems == 0)) || return 1
  log_info "manifest matches openid/conformance-suite@${SUITE_COMMIT:0:12} ($SUITE_REF) in $CLONE"
}

# ---------------------------------------------------------------------------------------------------------------
# import: replace the files and rewrite the manifest.
# ---------------------------------------------------------------------------------------------------------------

# write_manifest REF COMMIT ENTRY...: rewrite the lines between the MANIFEST markers of this script in place.
write_manifest() {
  local ref=$1 commit=$2 entry tmp
  shift 2
  tmp=$(mktemp "$(harness_run_dir tmp)/reimport.XXXXXX")
  {
    sed -n '1,/^# BEGIN MANIFEST/p' "$SELF"
    printf 'SUITE_REF=%s\nSUITE_COMMIT=%s\nSUITE_FILES=(\n' "$ref" "$commit"
    for entry in "$@"; do
      printf '  "%s"\n' "$entry"
    done
    printf ')\n'
    sed -n '/^# END MANIFEST/,$p' "$SELF"
  } >"$tmp"
  # Overwrite in place (same file, same mode). Safe while this script runs: bash has already read the whole
  # "{ main ...; exit; }" block at the end of the file.
  cat "$tmp" >"$SELF"
  rm -f "$tmp"
}

cmd_import() {
  local ref=$1 commit path type id entry
  local -a entries=()
  open_clone
  commit=$(resolve_ref "$ref")
  for path in "${IMPORT_PATHS[@]}"; do
    type=$(git -C "$CLONE" cat-file -t "$commit:$path" 2>/dev/null) || type=missing
    [[ $type == blob ]] ||
      die "upstream $ref (${commit:0:12}) has no file $path ($type); update IMPORT_PATHS in $SELF first" 2
  done

  # The folder holds upstream files only, so it is rebuilt from scratch: a file upstream dropped disappears too.
  rm -rf "$DEST"
  for path in "${IMPORT_PATHS[@]}"; do
    mkdir -p "$(dirname "$DEST/$path")"
    git -C "$CLONE" cat-file blob "$commit:$path" >"$DEST/$path"
    id=$(git -C "$CLONE" rev-parse "$commit:$path")
    [[ $(blob_id "$DEST/$path") == "$id" ]] || die "copy of $path does not match blob $id" 2
    entries+=("$id $path")
  done
  write_manifest "$ref" "$commit" "${entries[@]}"
  # The rewritten file is not re-read, so the check below needs the new values in memory as well.
  SUITE_REF=$ref SUITE_COMMIT=$commit SUITE_FILES=("${entries[@]}")
  cmd_check

  cat <<EOF

Imported openid/conformance-suite $ref ($commit). Next steps, from the repository root:
  1. git diff --stat -- third_party/oidf-conformance-suite     (review what upstream changed)
  2. commit only third_party/oidf-conformance-suite with the message
       import: upstream openid/conformance-suite@$commit (MIT)
  3. update the provenance table in third_party/README.md with the rows below, then commit it together with
     third_party/reimport.sh (its manifest was rewritten)

| File | Upstream path | Git blob id |
|---|---|---|
EOF
  # shellcheck disable=SC2016 # the backticks are Markdown code spans, not command substitution
  for entry in "${entries[@]}"; do
    printf '| `oidf-conformance-suite/%s` | `%s` | `%s` |\n' "${entry#* }" "${entry#* }" "${entry%% *}"
  done
}

main() {
  local cmd=${1:-}
  case $cmd in
    check | verify)
      (($# == 1)) || {
        usage >&2
        exit 2
      }
      "cmd_$cmd"
      ;;
    import)
      (($# == 2)) || {
        usage >&2
        exit 2
      }
      cmd_import "$2"
      ;;
    -h | --help)
      usage
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

# Braces make bash read the whole block before running it, so "import" may rewrite this file while it runs.
{
  main "$@"
  exit
}
