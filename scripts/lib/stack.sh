# shellcheck shell=bash
# Helpers of the one-command scripts (run-conformance.sh, run-full-stack-conformance.sh): preflight checks, run ids,
# and what the run manifest needs from the host. Source after scripts/lib/common.sh; do not run it.

# Host ports of the stack (docker-compose.yml), with the service that publishes each.
declare -gA STACK_PORTS=(
  [18443]="conformance suite (suite-nginx)"
  [18444]="conformance suite mTLS listener (suite-nginx)"
  [18450]="Inji Certify over TLS (tls-proxy)"
  [18451]="Inji Verify over TLS (tls-proxy)"
  [18460]="Inji Certify debug port (certify)"
  [18461]="Inji Verify debug port (verify-service)"
  [18900]="MinIO S3 API (minio)"
  [18901]="MinIO console (minio)"
)

# Docker memory below which a run is likely to fail (bytes). The certify profile peaked at 1.5 GiB and the full
# combined stack ran in a 4 GiB Docker VM on 2026-10-14; the runner and testrig containers come on top.
readonly STACK_MIN_MEMORY=$((3 * 1024 * 1024 * 1024))

# stack_ports PROFILE...: the host ports the given profiles publish.
stack_ports() {
  local profile ports=()
  for profile in "$@"; do
    case $profile in
      verify) ports+=(18443 18444 18451 18461) ;;
      certify) ports+=(18443 18444 18450 18460) ;;
      reports) ports+=(18900 18901) ;;
    esac
  done
  ((${#ports[@]})) && printf '%s\n' "${ports[@]}" | sort -u
}

# port_in_use PORT: true when something accepts connections on 127.0.0.1:PORT.
port_in_use() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

# stack_preflight PROFILE...: Docker with Compose v2, no stack of this project running, free ports, enough memory.
# Dies with what to do; prints one "preflight ok" line otherwise.
stack_preflight() {
  harness_require_cmd docker "install Docker Desktop, or Docker Engine with the Compose plugin"
  docker info >/dev/null 2>&1 || die "preflight: the Docker daemon does not answer; start Docker Desktop (or the docker service)" 3
  local compose
  compose=$(docker compose version --short 2>/dev/null) ||
    die "preflight: 'docker compose' (Compose v2) is missing; install the Compose plugin" 3
  if [[ -n $(docker ps -aq --filter "label=com.docker.compose.project=$HARNESS_COMPOSE_PROJECT") ]]; then
    die "preflight: containers of $HARNESS_COMPOSE_PROJECT already exist; stop them with: bash scripts/dc.sh --profile '*' down -v" 3
  fi
  local port busy=()
  while read -r port; do
    [[ -n $port ]] || continue
    if port_in_use "$port"; then
      busy+=("$port (${STACK_PORTS[$port]})")
    fi
  done < <(stack_ports "$@")
  if ((${#busy[@]})); then
    die "preflight: ports in use on 127.0.0.1: ${busy[*]}. Stop the program that holds them (netstat -ano on Windows, lsof -iTCP -sTCP:LISTEN on macOS, ss -ltnp on Linux); the harness ports are fixed in docker-compose.yml" 3
  fi
  local memory
  memory=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
  if [[ $memory =~ ^[0-9]+$ ]] && ((memory > 0 && memory < STACK_MIN_MEMORY)); then
    log_warn "preflight: Docker has $((memory / 1024 / 1024)) MiB of memory; give it at least 4 GiB (Docker Desktop, Settings, Resources)"
  fi
  log_info "preflight ok: Docker Compose $compose, $((memory / 1024 / 1024)) MiB, ports free: $(stack_ports "$@" | tr '\n' ' ')"
}

# stack_merge_exit_code RUNNER RIG: the run's exit code from the runner's and one testrig's. A regression (1) from
# either side wins, because only 1 is about Inji and CI retries on 3. The rig's 2 ("could not run") is an
# environment problem, so it becomes 3; otherwise the larger code wins.
stack_merge_exit_code() {
  local runner=$1 rig=$2
  ((rig == 2)) && rig=3
  if ((runner == 1 || rig == 1)); then
    echo 1
  elif ((rig > runner)); then
    echo "$rig"
  else
    echo "$runner"
  fi
}

# stack_new_run_id: UTC start time plus 6 random hex characters, the format of inji_conformance.run.new_run_id.
stack_new_run_id() {
  printf '%s-%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$(od -An -N3 -tx1 /dev/urandom | tr -d ' \n')"
}

# stack_git_commit / stack_git_dirty: the checkout the run used (empty / unset outside a git checkout).
stack_git_commit() {
  git -C "$HARNESS_ROOT" rev-parse --short=12 HEAD 2>/dev/null || true
}
stack_git_dirty() {
  if [[ -n $(git -C "$HARNESS_ROOT" status --porcelain --untracked-files=no 2>/dev/null) ]]; then echo 1; else echo 0; fi
}

stack_host_os() {
  local os
  os=$(uname -s 2>/dev/null || echo unknown)
  case $os in
    Darwin) os="macOS $(sw_vers -productVersion 2>/dev/null) ($(uname -m))" ;;
    Linux) os="Linux $(uname -r) ($(uname -m))" ;;
    MINGW* | MSYS* | CYGWIN*) os="Windows (Git Bash, $(uname -r))" ;;
  esac
  printf '%s\n' "$os"
}

# stack_images_json FILE: one JSON object per running container of the project: service, image, registry digest
# (null when the image was built here) and source commit label when the image has one.
stack_images_json() {
  local file=$1 id service image image_id digests revision digest first=1
  {
    printf '['
    while read -r id; do
      [[ -n $id ]] || continue
      IFS='|' read -r service image image_id < <(docker inspect -f \
        '{{index .Config.Labels "com.docker.compose.service"}}|{{.Config.Image}}|{{.Image}}' "$id")
      IFS='|' read -r digests revision < <(docker image inspect -f \
        '{{join .RepoDigests ","}}|{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image_id" 2>/dev/null ||
        echo '|')
      digest=null
      if [[ $image == *@sha256:* ]]; then
        digest="\"${image##*@}\""
      elif [[ $digests == *@sha256:* ]]; then
        digest=${digests%%,*}
        digest="\"${digest##*@}\""
      fi
      ((first)) || printf ','
      first=0
      printf '\n  {"service": "%s", "image": "%s", "digest": %s' "$service" "$image" "$digest"
      if [[ $revision =~ ^[0-9a-f]{7,40}$ ]]; then
        printf ', "commit": "%s"' "$revision"
      fi
      printf '}'
    done < <(docker ps -aq --filter "label=com.docker.compose.project=$HARNESS_COMPOSE_PROJECT")
    printf '\n]\n'
  } >"$file"
}
