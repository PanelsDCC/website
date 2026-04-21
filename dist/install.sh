#!/usr/bin/env bash

set -euo pipefail

CONNECT_REPO="PanelsDCC/connect"
CONTROL_REPO="PanelsDCC/control"
TMP_DIR="$(mktemp -d)"
ARCH="$(dpkg --print-architecture)"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

log() {
  echo "[panelsdcc-install] $*"
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Please run as root (example: curl -fsSL https://panelsd.cc/install.sh | sudo bash)"
    exit 1
  fi
}

require_tools() {
  local missing=0
  for cmd in curl jq dpkg apt-get; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
      echo "Missing required command: ${cmd}"
      missing=1
    fi
  done
  if [[ "${missing}" -ne 0 ]]; then
    echo "Installing required packages..."
    apt-get update
    apt-get install -y curl jq
  fi
}

pick_asset_url() {
  local repo="$1"
  local release_json="$2"

  local pattern
  case "${ARCH}" in
    arm64) pattern='(arm64|aarch64|all)\.deb$' ;;
    armhf) pattern='(armhf|armv7|all)\.deb$' ;;
    amd64) pattern='(amd64|x86_64|all)\.deb$' ;;
    *) pattern='all\.deb$' ;;
  esac

  local url
  url="$(echo "${release_json}" | jq -r --arg pattern "${pattern}" '
    [.assets[]
      | select(.name | test($pattern; "i"))
      | .browser_download_url
    ] | first // empty
  ')"

  if [[ -z "${url}" ]]; then
    url="$(echo "${release_json}" | jq -r '
      [.assets[]
        | select(.name | endswith(".deb"))
        | .browser_download_url
      ] | first // empty
    ')"
  fi

  if [[ -z "${url}" ]]; then
    echo "No .deb asset found for ${repo}."
    exit 1
  fi

  echo "${url}"
}

download_latest_deb() {
  local repo="$1"
  local out_file="$2"
  local api_url="https://api.github.com/repos/${repo}/releases/latest"

  log "Fetching latest release metadata for ${repo}..."
  local release_json
  release_json="$(curl -fsSL "${api_url}")"

  local tag
  tag="$(echo "${release_json}" | jq -r '.tag_name')"
  local asset_url
  asset_url="$(pick_asset_url "${repo}" "${release_json}")"

  log "Downloading ${repo} ${tag}..."
  curl -fL "${asset_url}" -o "${out_file}"
}

install_deb() {
  local deb_file="$1"
  log "Installing $(basename "${deb_file}")..."
  apt-get install -y "${deb_file}"
}

maybe_enable_connect_service() {
  if systemctl list-unit-files | grep -q '^panelsdcc-connect\.service'; then
    log "Enabling and starting panelsdcc-connect.service..."
    systemctl enable --now panelsdcc-connect.service
    return
  fi

  if systemctl list-unit-files | grep -q '^connect\.service'; then
    log "Enabling and starting connect.service..."
    systemctl enable --now connect.service
    return
  fi

  log "No known Connect service unit found; skipping service enablement."
}

create_desktop_launcher() {
  local desktop_file="$1"
  local app_name="$2"
  local url="$3"

  cat > "${desktop_file}" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=${app_name}
Comment=Open ${app_name}
Exec=sh -c 'if command -v chromium-browser >/dev/null 2>&1; then chromium-browser --app=${url}; elif command -v chromium >/dev/null 2>&1; then chromium --app=${url}; elif command -v firefox >/dev/null 2>&1; then firefox --kiosk ${url}; else xdg-open ${url}; fi'
Icon=applications-internet
Terminal=false
Categories=Network;WebBrowser;
EOF
}

maybe_create_desktop_shortcuts() {
  local desktop_user="pi"

  if ! id -u "${desktop_user}" >/dev/null 2>&1; then
    log "User '${desktop_user}' not found; skipping desktop shortcuts."
    return
  fi

  local desktop_dir="/home/${desktop_user}/Desktop"
  if [[ ! -d "${desktop_dir}" ]]; then
    log "Desktop folder not found for '${desktop_user}'; skipping desktop shortcuts."
    return
  fi

  local host_name
  host_name="$(hostname)"
  local connect_url="http://${host_name}:9000/"
  local control_url="http://${host_name}/"

  log "Creating desktop launchers for user '${desktop_user}'..."
  create_desktop_launcher "${desktop_dir}/PanelsDCC Connect.desktop" "PanelsDCC Connect" "${connect_url}"
  create_desktop_launcher "${desktop_dir}/PanelsDCC Control.desktop" "PanelsDCC Control" "${control_url}"

  chmod 755 "${desktop_dir}/PanelsDCC Connect.desktop" "${desktop_dir}/PanelsDCC Control.desktop"
  chown "${desktop_user}:${desktop_user}" "${desktop_dir}/PanelsDCC Connect.desktop" "${desktop_dir}/PanelsDCC Control.desktop"
}

main() {
  require_root
  require_tools

  export DEBIAN_FRONTEND=noninteractive
  apt-get update

  local connect_deb="${TMP_DIR}/connect.deb"
  local control_deb="${TMP_DIR}/control.deb"

  download_latest_deb "${CONNECT_REPO}" "${connect_deb}"
  download_latest_deb "${CONTROL_REPO}" "${control_deb}"

  install_deb "${connect_deb}"
  install_deb "${control_deb}"
  maybe_enable_connect_service
  maybe_create_desktop_shortcuts

  local host_name
  host_name="$(hostname)"
  log "Installation complete."
  log "Open Connect at: http://${host_name}:9000/"
  log "Open Control at: http://${host_name}/"
}

main "$@"
