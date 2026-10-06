#!/usr/bin/env bash
# Anonymous registry state for one immutable image tag. Source this file to use
# resolve_registry_images without requests, logging, or other side effects.
# Endpoint overrides: GHCR_TOKEN_URL, GHCR_REGISTRY_URL, DOCKERHUB_TOKEN_URL,
# DOCKERHUB_REGISTRY_URL. The defaults are the public registry endpoints.
# Timing overrides (integer seconds, 0..99999 without leading zeros): IMAGE_STATE_RETRY_DELAY (2),
# IMAGE_STATE_WAIT_SECONDS (30), IMAGE_STATE_WAIT_INTERVAL (2; must be positive).
# Transient failures get an initial attempt plus exactly three retries. --wait
# polls manifest 404s until the wait deadline; token 404s are always errors.

resolve_registry_images() {
  local component='[a-z0-9]+(([.]|_{1,2}|-+)[a-z0-9]+)*'
  local repository_pattern="^${component}(/${component})*$"
  local ghcr_repository hub_repository

  if [[ ${GHCR_IMAGE:-} != ghcr.io/* ]]; then
    printf '%s\n' 'GHCR_IMAGE must be ghcr.io/<repository>, without a tag or digest.' >&2
    return 1
  fi
  ghcr_repository=${GHCR_IMAGE#ghcr.io/}
  if [[ ! $ghcr_repository =~ $repository_pattern ]]; then
    printf '%s\n' 'GHCR_IMAGE has an invalid lowercase repository path.' >&2
    return 1
  fi
  GHCR_IMAGE="ghcr.io/$ghcr_repository"
  if [[ -z ${DOCKERHUB_USERNAME:-} ]]; then
    DOCKERHUB_IMAGE=''
    return 0
  fi
  hub_repository=${DOCKERHUB_IMAGE:-${DOCKERHUB_USERNAME}/sava-openjdk}
  hub_repository=${hub_repository#docker.io/}
  if [[ ! $hub_repository =~ $repository_pattern ]]; then
    printf '%s\n' 'DOCKERHUB_IMAGE has an invalid lowercase repository path.' >&2
    return 1
  fi
  DOCKERHUB_IMAGE=$hub_repository
}

# The caller supplies dynamically scoped request result variables. Never log
# response bodies or credentials, including when the token endpoint fails.
image_state_request() {
  local kind=$1 url=$2 repository=$3 token=${4:-}
  local attempt=0 code curl_status
  local -a arguments=(-q --silent --show-error --connect-timeout 5 --max-time 10
    --dump-header "$work_dir/headers" --write-out '%{http_code}')
  if [[ $kind == token ]]; then
    arguments+=(--output "$work_dir/body" --get
      --data-urlencode "scope=repository:$repository:pull")
    if [[ $registry_name == DockerHub ]]; then
      arguments+=(--data-urlencode 'service=registry.docker.io')
    fi
  else
    arguments+=(--head --output /dev/null
      --header "Authorization: Bearer $token"
      --header 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json')
  fi
  while :; do
    code=$(curl "${arguments[@]}" "$url" 2>"$work_dir/curl-error")
    curl_status=$?
    if (( curl_status == 0 )) && [[ $code =~ ^[0-9]{3}$ ]]; then
      REQUEST_HTTP=$code
      case $code in
        200|404) return 0 ;;
        429|5??) ;;
        *)
          printf '%s\n' "$registry_name $kind request failed: HTTP $code." >&2
          return 1
          ;;
      esac
    else
      REQUEST_HTTP=''
    fi
    if (( attempt == 3 )); then
      if [[ -n $REQUEST_HTTP ]]; then
        printf '%s\n' "$registry_name $kind request failed after 4 attempts: HTTP $REQUEST_HTTP." >&2
      else
        printf '%s\n' "$registry_name $kind request failed after 4 attempts: curl exit $curl_status." >&2
      fi
      return 1
    fi
    (( attempt += 1 ))
    sleep "$retry_delay"
  done
}

image_state_registry() {
  local registry_name=$1 repository=$2 token_url=$3 registry_url=$4
  local token deadline REQUEST_HTTP=''
  REGISTRY_STATUS=error
  REGISTRY_DIGEST=''
  if ! image_state_request token "$token_url" "$repository"; then
    return 1
  fi
  if [[ $REQUEST_HTTP != 200 ]]; then
    printf '%s\n' "$registry_name token request failed: HTTP $REQUEST_HTTP." >&2
    return 1
  fi
  if ! token=$(jq -er '(.token // .access_token) | select(type == "string" and test("\\A[A-Za-z0-9._~+/-]+=*\\z"))' "$work_dir/body" 2>/dev/null) ||
    [[ ! $token =~ ^[A-Za-z0-9._~+/-]+=*$ ]]; then
    printf '%s\n' "$registry_name token response has no valid token." >&2
    return 1
  fi
  deadline=$((SECONDS + wait_seconds))
  while :; do
    if ! image_state_request manifest "${registry_url%/}/v2/$repository/manifests/$tag" "$repository" "$token"; then
      return 1
    fi
    if [[ $REQUEST_HTTP == 200 ]]; then
      REGISTRY_DIGEST=$(awk 'tolower($1) == "docker-content-digest:" {sub(/^[^:]*:[ \t]*/, ""); sub(/\r$/, ""); sub(/[ \t]+$/, ""); print}' "$work_dir/headers")
      if [[ ! $REGISTRY_DIGEST =~ ^sha256:[a-fA-F0-9]{64}$ ]]; then
        REGISTRY_DIGEST=''
        printf '%s\n' "$registry_name manifest response has no valid SHA-256 digest." >&2
        return 1
      fi
      REGISTRY_DIGEST=$(printf '%s' "$REGISTRY_DIGEST" | tr '[:upper:]' '[:lower:]')
      REGISTRY_STATUS=present
      return 0
    fi
    if (( ! wait_mode || SECONDS >= deadline )); then
      REGISTRY_STATUS=absent
      return 0
    fi
    local remaining=$((deadline - SECONDS))
    if (( remaining < wait_interval )); then
      sleep "$remaining"
    else
      sleep "$wait_interval"
    fi
  done
}

image_state_report() {
  local state=$1
  printf 'GHCR: %s; digest: %s\n' "$ghcr_status" "${ghcr_digest:--}" >&2
  if [[ -n $DOCKERHUB_IMAGE ]]; then
    printf 'DockerHub: %s; digest: %s\n' "$dockerhub_status" "${dockerhub_digest:--}" >&2
  fi
  if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
    {
      # shellcheck disable=SC2016 # Markdown backticks are intentional.
      printf 'Registry state for `%s`: **%s**\n\n' "$tag" "$state"
      printf '| Registry | Status | Digest |\n| --- | --- | --- |\n'
      printf '| GHCR | %s | %s |\n' "$ghcr_status" "${ghcr_digest:--}"
      if [[ -n $DOCKERHUB_IMAGE ]]; then
        printf '| Docker Hub | %s | %s |\n' "$dockerhub_status" "${dockerhub_digest:--}"
      fi
    } >> "$GITHUB_STEP_SUMMARY" || return 1
  fi
  if [[ -n ${GITHUB_OUTPUT:-} ]]; then
    {
      printf 'state=%s\nghcr_status=%s\nghcr_digest=%s\n' "$state" "$ghcr_status" "$ghcr_digest"
      printf 'dockerhub_status=%s\ndockerhub_digest=%s\n' "$dockerhub_status" "$dockerhub_digest"
      printf 'ghcr_image=%s\ndockerhub_image=%s\n' "$GHCR_IMAGE" "$DOCKERHUB_IMAGE"
    } >> "$GITHUB_OUTPUT" || return 1
  fi
}

# Invalid input must still expose a machine-readable failure, without writing
# unvalidated image names to GitHub's line-oriented output file.
image_state_input_error() {
  GHCR_IMAGE=''
  DOCKERHUB_IMAGE=''
  if [[ -n ${DOCKERHUB_USERNAME:-} ]]; then
    dockerhub_status=error
  fi
  image_state_report error || printf '%s\n' 'Unable to write registry state output or summary.' >&2
  printf '%s\n' error
  return 1
}

# A subshell keeps cleanup traps local even when this file is sourced.
image_state_main() (
  local tag='' wait_mode=0 state=error work_dir=''
  local retry_delay=${IMAGE_STATE_RETRY_DELAY:-2}
  local wait_seconds=${IMAGE_STATE_WAIT_SECONDS:-30}
  local wait_interval=${IMAGE_STATE_WAIT_INTERVAL:-2}
  local ghcr_status=error ghcr_digest='' dockerhub_status=disabled dockerhub_digest=''
  local REGISTRY_STATUS REGISTRY_DIGEST
  trap '[[ -z $work_dir ]] || rm -rf "$work_dir"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  local GHCR_IMAGE=${GHCR_IMAGE:-} DOCKERHUB_IMAGE=${DOCKERHUB_IMAGE:-}
  if [[ ${1:-} == --wait ]]; then
    wait_mode=1
    shift
  fi
  if (( $# != 1 )) || [[ ! ${1:-} =~ ^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$ ]]; then
    printf '%s\n' 'Usage: image-state.sh [--wait] TAG (a valid container tag is required).' >&2
    image_state_input_error
    return 1
  fi
  tag=$1
  if ! resolve_registry_images; then
    image_state_input_error
    return 1
  fi
  if [[ -n $DOCKERHUB_IMAGE ]]; then
    dockerhub_status=error
  else
    printf '%s\n' '::warning::Docker Hub is disabled because DOCKERHUB_USERNAME is unset; checked registries: GHCR only.' >&2
  fi
  if [[ ! $retry_delay =~ ^(0|[1-9][0-9]{0,4})$ || ! $wait_seconds =~ ^(0|[1-9][0-9]{0,4})$ || ! $wait_interval =~ ^(0|[1-9][0-9]{0,4})$ ]] ||
    (( wait_interval == 0 )); then
    printf '%s\n' 'Invalid image-state timing configuration.' >&2
  elif ! command -v curl >/dev/null || ! command -v jq >/dev/null; then
    printf '%s\n' 'image-state requires curl and jq.' >&2
  elif ! work_dir=$(mktemp -d); then
    printf '%s\n' 'Unable to create registry request temporary directory.' >&2
  else
    image_state_registry GHCR "${GHCR_IMAGE#ghcr.io/}" "${GHCR_TOKEN_URL:-https://ghcr.io/token}" "${GHCR_REGISTRY_URL:-https://ghcr.io}" || :
    ghcr_status=$REGISTRY_STATUS
    ghcr_digest=$REGISTRY_DIGEST
    if [[ -n $DOCKERHUB_IMAGE ]]; then
      image_state_registry DockerHub "$DOCKERHUB_IMAGE" "${DOCKERHUB_TOKEN_URL:-https://auth.docker.io/token}" "${DOCKERHUB_REGISTRY_URL:-https://registry-1.docker.io}" || :
      dockerhub_status=$REGISTRY_STATUS
      dockerhub_digest=$REGISTRY_DIGEST
    fi
    if [[ $ghcr_status == error || $dockerhub_status == error ]]; then
      state=error
    elif [[ $ghcr_status == absent && ( $dockerhub_status == absent || $dockerhub_status == disabled ) ]]; then
      state=absent
    elif [[ $ghcr_status == present && ( $dockerhub_status == disabled || ( $dockerhub_status == present && $ghcr_digest == "$dockerhub_digest" ) ) ]]; then
      state=published
    else
      state=inconsistent
    fi
  fi
  if ! image_state_report "$state"; then
    printf '%s\n' 'Unable to write registry state output or summary.' >&2
    state=error
  fi
  printf '%s\n' "$state"
  [[ $state != error ]]
)

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  image_state_main "$@"
fi
