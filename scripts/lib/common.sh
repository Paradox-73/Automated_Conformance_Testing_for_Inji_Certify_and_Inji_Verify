# shellcheck shell=bash
# Shared helpers for the harness shell scripts. Source this file; do not run it.
#
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
#
# Settings (environment variables, all optional):
#   HARNESS_RUN_DIR          runtime state: downloads, logs, generated keys, the Python venv. Default <repo>/run,
#                            which .gitignore excludes. Nothing a script writes at run time goes into the repository.
#   HARNESS_COMPOSE_PROJECT  Docker Compose project name. Default inji-conformance.
#   HARNESS_TOOLS_DIR        extra tool folder searched after PATH (<dir>/bin). Default $HARNESS_RUN_DIR/tools.
#   NO_COLOR                 any value turns off coloured log output (https://no-color.org).
#
# Needs bash 4.4 or newer: Linux, Git Bash on Windows, or macOS with bash from Homebrew (macOS ships bash 3.2).

if [[ -n ${_HARNESS_COMMON_LOADED:-} ]]; then
  return 0
fi
_HARNESS_COMMON_LOADED=1

if ((BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 4))); then
  printf '[error] bash 4.4 or newer is needed, this is bash %s (on macOS: brew install bash)\n' "$BASH_VERSION" >&2
  exit 1
fi

HARNESS_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
HARNESS_RUN_DIR=${HARNESS_RUN_DIR:-$HARNESS_ROOT/run}
HARNESS_COMPOSE_PROJECT=${HARNESS_COMPOSE_PROJECT:-inji-conformance}
HARNESS_TOOLS_DIR=${HARNESS_TOOLS_DIR:-$HARNESS_RUN_DIR/tools}
# Exported so child scripts and containers started from them resolve the same folders.
export HARNESS_ROOT HARNESS_RUN_DIR HARNESS_COMPOSE_PROJECT HARNESS_TOOLS_DIR

# Minimum Python version for the runner and the check scripts (the runner package targets 3.12).
HARNESS_PYTHON_MIN_MINOR=12

# ---------------------------------------------------------------------------------------------------------------
# Logging. Everything goes to stderr so that stdout stays usable for values a caller captures with $(...).
# ---------------------------------------------------------------------------------------------------------------

_harness_color() {
  # $1 = ANSI colour code. Colour only when stderr is a terminal and NO_COLOR is unset.
  if [[ -t 2 && -z ${NO_COLOR:-} ]]; then
    printf '\033[%sm' "$1"
  fi
}

_harness_log() {
  local level=$1 color=$2
  shift 2
  printf '%s[%s]%s %s\n' "$(_harness_color "$color")" "$level" "$(_harness_color 0)" "$*" >&2
}

log_info() { _harness_log info 36 "$@"; }
log_warn() { _harness_log warn 33 "$@"; }
log_error() { _harness_log error 31 "$@"; }

# die MESSAGE [EXIT_CODE]: log an error and exit (default exit code 1).
die() {
  log_error "$1"
  exit "${2:-1}"
}

# ---------------------------------------------------------------------------------------------------------------
# Platform and paths
# ---------------------------------------------------------------------------------------------------------------

# True in Git Bash, MSYS2 and Cygwin on Windows.
harness_is_windows() {
  case ${OSTYPE:-} in
    msys* | cygwin* | win32*) return 0 ;;
  esac
  return 1
}

# harness_container_user: print the uid:gid the harness's containers run as (HARNESS_UID and HARNESS_GID override).
# On Windows (Git Bash) the uid is a large SID-derived number; Docker Desktop ignores ownership of bind mounts, so
# the image's ordinary user id 1000 is used there, the same user that pki-init writes the run's keys as.
harness_container_user() {
  if harness_is_windows; then
    printf '%s:%s\n' "${HARNESS_UID:-1000}" "${HARNESS_GID:-1000}"
  else
    printf '%s:%s\n' "${HARNESS_UID:-$(id -u)}" "${HARNESS_GID:-$(id -g)}"
  fi
}

# harness_native_path PATH: print PATH in the form native programs expect. On Windows that is C:/x/y (forward
# slashes, which docker, java and python all accept); elsewhere the path is printed unchanged.
harness_native_path() {
  if harness_is_windows && command -v cygpath >/dev/null 2>&1; then
    cygpath -m -- "$1"
  else
    printf '%s\n' "$1"
  fi
}

# harness_no_pathconv CMD [ARGS...]: run a command with Git Bash argument rewriting turned off. Git Bash turns
# arguments that look like POSIX paths (for example /etc/nginx in a docker volume spec) into Windows paths, which
# breaks container paths. Elsewhere the variables have no effect.
harness_no_pathconv() {
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' "$@"
}

# harness_run_dir [SUBDIR]: create (if needed) and print $HARNESS_RUN_DIR or a folder below it.
harness_run_dir() {
  local dir=$HARNESS_RUN_DIR${1:+/$1}
  mkdir -p -- "$dir" || die "cannot create run folder $dir"
  printf '%s\n' "$dir"
}

# ---------------------------------------------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------------------------------------------

# harness_find_tool NAME: print the path of NAME, looked up on PATH first and then in $HARNESS_TOOLS_DIR/bin.
# Returns 1 (printing nothing) when the tool is not installed.
harness_find_tool() {
  local name=$1 candidate
  if candidate=$(command -v "$name" 2>/dev/null); then
    printf '%s\n' "$candidate"
    return 0
  fi
  for candidate in "$HARNESS_TOOLS_DIR/bin/$name" "$HARNESS_TOOLS_DIR/bin/$name.exe"; do
    if [[ -x $candidate ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

# harness_find_python: print the path of a Python 3.12+ interpreter (python3 first, then python). On Windows,
# python3 can be the Microsoft Store placeholder that only prints a hint, so each candidate is run once to prove
# it works. Returns 1 when none qualifies.
harness_find_python() {
  local candidate path
  # Versioned names last: macOS and some Linux distributions install a newer Python only as python3.1x.
  for candidate in python3 python python3.14 python3.13 python3.12; do
    path=$(command -v "$candidate" 2>/dev/null) || continue
    if "$path" -c "import sys; sys.exit(0 if sys.version_info >= (3, $HARNESS_PYTHON_MIN_MINOR) else 1)" \
      >/dev/null 2>&1; then
      printf '%s\n' "$path"
      return 0
    fi
  done
  return 1
}

# harness_venv_python VENV_DIR: print the interpreter path inside a virtual environment (bin/ on Linux and macOS,
# Scripts/ on Windows). Returns 1 when the venv does not exist.
harness_venv_python() {
  local venv=$1 candidate
  for candidate in "$venv/bin/python" "$venv/Scripts/python.exe"; do
    if [[ -x $candidate ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

# harness_require_cmd NAME [HINT]: exit with a clear message when a command is missing.
harness_require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1${2:+ ($2)}"
}

# dc ARGS...: docker compose through scripts/dc.sh (project, files, env.local and the run folder set).
dc() {
  bash "$HARNESS_ROOT/scripts/dc.sh" "$@"
}
