#!/usr/bin/env bash
# ============================================================================
# Module 6 — Live Evidence Collection (Lab Day 4, OT Forensics; Section 6.4)
#
# Collects evidence from a Linux device under investigation in order of
# volatility (RFC 3227): most volatile first, because every second the
# device keeps running changes it.
#
#   1. CPU & processes  — CPU state, load, full process table, per-process
#                          executable hash, command line, open files
#   2. Network state    — interfaces, routes, ARP cache, live connections
#                          mapped to processes, firewall rules
#   3. Memory (RAM)     — memory statistics; full RAM image with --memory
#   4. Network traffic  — optional live capture with --pcap SECONDS
#   5. Storage triage   — disks/mounts, recently modified files, SUID files,
#                          temp dirs, logs, /etc, shell histories, cron
#   6. Storage image    — optional bit-for-bit disk image with --disk
#
# Every command is logged (UTC time, exit code) in collection_log.txt and
# every output file is hashed in manifest.sha256. Hash that manifest into
# your chain-of-custody record and the whole collection is sealed.
#
# Two ways to run it:
#
#   On the device itself (real investigation; run as root, write to external media):
#     sudo ./collect_evidence.sh -c CASE-001 -e "Jane Doe" -o /media/usb/evidence \
#          [--memory] [--pcap 60] [--disk /dev/sda]
#
#   From the lab host against a Docker container (Palanca lab):
#     ./collect_evidence.sh -c CASE-001 -e "Jane Doe" --container plc-main-01 [--pcap 60]
#
# Exit code: 0 = collection complete, 1 = completed with warnings
# (see collection_log.txt), 2 = could not start.
# ============================================================================
set -uo pipefail
umask 077
VERSION="1.0"
SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

usage() {
  cat <<'EOF'
Usage: collect_evidence.sh -c CASE_ID -e EXAMINER [options]

Required:
  -c, --case ID          case / incident reference (e.g. IR-2026-004)
  -e, --examiner NAME    who is collecting (goes in the chain-of-custody log)

Target (default: this machine):
      --container NAME   collect from a running Docker container (lab mode, run on the Docker host)

Options:
  -o, --out DIR          where to write evidence (default: ./evidence). On a real
                         device use external media, never the disk under investigation
      --pcap SECONDS     capture network traffic for SECONDS (default: off)
      --memory           acquire a full RAM image (device mode, root; needs AVML or LiME)
      --avml PATH        path to the avml binary (default: avml on PATH)
      --lime PATH        path to a LiME kernel module (.ko) built for this kernel
      --disk DEVICE      bit-for-bit image of DEVICE, e.g. /dev/sda (device mode, root)
      --days N           "recently modified files" window in days (default: 7)
      --no-export        container mode: skip the filesystem export (docker export)
      --capture-image IMG
                         container mode: image with tcpdump for --pcap
                         (default: the image eng-ws-01 runs)
  -h, --help             show this help
EOF
}

# ---------------------------------------------------------------- helpers ---
utc() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

WARNINGS=0
log() { echo "$(utc)  $*" | tee -a "$LOG" >&2; }
warn() { WARNINGS=$((WARNINGS+1)); log "WARNING: $*"; }

# run <output-file relative to $OUT> <command...> : run, save stdout, log it.
# stderr goes to <output-file>.stderr (kept only if non-empty), so binary
# outputs such as .tar archives are never corrupted by warning messages.
run() {
  local dest="$OUT/$1"; shift
  mkdir -p "$(dirname "$dest")"
  local start rc
  start=$(utc)
  "$@" >"$dest" 2>"$dest.stderr" </dev/null
  rc=$?
  [ -s "$dest.stderr" ] || rm -f "$dest.stderr"
  echo "$start  rc=$rc  $*  ->  ${dest#"$OUT"/}" >>"$LOG"
  return $rc
}

# have <tool> : is it installed?
have() { command -v "$1" >/dev/null 2>&1; }

# copy_raw <output-file> <source-file> : copy a /proc or config file if readable
copy_raw() {
  [ -r "$2" ] || return 0
  run "$1" cat "$2"
}

# ------------------------------------------------- stage 1: CPU/processes ---
collect_cpu_processes() {
  log "[1/6] CPU & processes"
  run system/date_utc.txt date -u
  run system/date_local.txt date
  run system/uname.txt uname -a
  copy_raw system/hostname.txt /proc/sys/kernel/hostname
  copy_raw system/uptime.txt /proc/uptime
  copy_raw system/os-release.txt /etc/os-release
  copy_raw cpu/cpuinfo.txt /proc/cpuinfo
  copy_raw cpu/loadavg.txt /proc/loadavg
  copy_raw cpu/stat.txt /proc/stat
  copy_raw cpu/interrupts.txt /proc/interrupts
  copy_raw system/kernel_modules.txt /proc/modules
  copy_raw system/mounts.txt /proc/mounts
  have ps && run processes/ps_auxwwf.txt ps auxwwf
  have who && run system/logged_in_users.txt who -a
  have last && run system/last_logins.txt last -Faiwx

  # Process table straight from /proc, so it works on minimal systems with no ps.
  local btime hz
  btime=$(awk '/^btime/ {print $2}' /proc/stat)
  hz=$(getconf CLK_TCK 2>/dev/null || echo 100)
  local table="$OUT/processes/process_table.tsv"
  mkdir -p "$OUT/processes/per_pid"
  printf 'pid\tppid\tuid\tstate\tstart_utc\tname\texe\texe_sha256\tcmdline\n' >"$table"
  local p pid name ppid uid state stat ticks start exe hash cmd
  for p in /proc/[0-9]*; do
    pid=${p#/proc/}
    [ -r "$p/status" ] || continue
    name=$(awk '/^Name:/ {print $2}' "$p/status" 2>/dev/null)
    ppid=$(awk '/^PPid:/ {print $2}' "$p/status" 2>/dev/null)
    uid=$(awk '/^Uid:/ {print $2}' "$p/status" 2>/dev/null)
    stat=$(cat "$p/stat" 2>/dev/null) || continue
    stat=${stat##*) }
    # shellcheck disable=SC2086
    set -- $stat
    state=$1; ticks=${20:-0}
    start=$(date -u -d "@$((btime + ticks / hz))" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo "?")
    exe=$(readlink "$p/exe" 2>/dev/null || echo "")
    hash=""
    [ -n "$exe" ] && hash=$(sha256sum "$p/exe" 2>/dev/null | awk '{print $1}')
    cmd=$(tr '\0' ' ' <"$p/cmdline" 2>/dev/null)
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$pid" "$ppid" "$uid" "$state" "$start" \
      "$name" "$exe" "$hash" "$cmd" >>"$table"
    # Per-process detail. A "(deleted)" exe or LD_PRELOAD in environ are classic red flags.
    local d="$OUT/processes/per_pid/$pid"
    mkdir -p "$d"
    cp "$p/status" "$d/status.txt" 2>/dev/null
    tr '\0' '\n' <"$p/cmdline" >"$d/cmdline.txt" 2>/dev/null
    tr '\0' '\n' <"$p/environ" >"$d/environ.txt" 2>/dev/null
    cp "$p/maps" "$d/maps.txt" 2>/dev/null
    ls -l "$p/fd/" >"$d/open_files.txt" 2>/dev/null
    readlink "$p/cwd" >"$d/cwd.txt" 2>/dev/null
  done
  echo "$(utc)  rc=0  /proc process walk  ->  processes/process_table.tsv" >>"$LOG"
  grep -q '(deleted)' "$table" && warn "a running process's executable has been deleted from disk — see processes/process_table.tsv"
}

# ----------------------------------------------------- stage 2: network ---
hex2ip4() {   # 0100A8C0 -> 192.168.0.1 (/proc/net stores IPv4 little-endian)
  local h=$1
  printf '%d.%d.%d.%d' "0x${h:6:2}" "0x${h:4:2}" "0x${h:2:2}" "0x${h:0:2}"
}
tcp_state() {
  case $1 in
    01) echo ESTABLISHED ;; 02) echo SYN_SENT ;; 03) echo SYN_RECV ;; 04) echo FIN_WAIT1 ;;
    05) echo FIN_WAIT2 ;; 06) echo TIME_WAIT ;; 07) echo CLOSE ;; 08) echo CLOSE_WAIT ;;
    09) echo LAST_ACK ;; 0A) echo LISTEN ;; 0B) echo CLOSING ;; *) echo "$1" ;;
  esac
}

collect_network_state() {
  log "[2/6] Network state"
  copy_raw network/proc_net_dev.txt /proc/net/dev
  copy_raw network/proc_net_route.txt /proc/net/route
  copy_raw network/proc_net_arp.txt /proc/net/arp
  local f
  for f in tcp tcp6 udp udp6 raw unix; do copy_raw "network/proc_net_$f.txt" "/proc/net/$f"; done
  copy_raw network/nf_conntrack.txt /proc/net/nf_conntrack
  copy_raw network/hosts.txt /etc/hosts
  copy_raw network/resolv.conf.txt /etc/resolv.conf
  if have ip; then
    run network/ip_addr.txt ip addr
    run network/ip_route.txt ip route show table all
    run network/ip_neigh.txt ip neigh show
  fi
  have ss && run network/ss_all.txt ss -tunapoe
  have lsof && run network/lsof_network.txt lsof -nP -i
  have iptables-save && run network/iptables-save.txt iptables-save
  have ip6tables-save && run network/ip6tables-save.txt ip6tables-save
  have nft && run network/nft_ruleset.txt nft list ruleset
  have conntrack && run network/conntrack.txt conntrack -L

  # Readable connection table mapped to owning processes (works with no ss/netstat).
  local inode_map="$OUT/network/.socket_owners"
  local fd link
  : >"$inode_map"
  for fd in /proc/[0-9]*/fd/*; do
    link=$(readlink "$fd" 2>/dev/null) || continue
    case $link in socket:\[*\])
      local pid=${fd#/proc/}; pid=${pid%%/*}
      echo "${link//[^0-9]/} $pid $(cat "/proc/$pid/comm" 2>/dev/null)" >>"$inode_map" ;;
    esac
  done
  local out="$OUT/network/connections.tsv"
  printf 'proto\tlocal\tremote\tstate\tuid\tinode\tpid\tprocess\n' >"$out"
  local proto sl la ra st rest uid inode owner
  for proto in tcp udp; do
    [ -r "/proc/net/$proto" ] || continue
    while read -r sl la ra st _ _ _ uid _ inode rest; do
      [ "$sl" = "sl" ] && continue
      owner=$(awk -v i="$inode" '$1 == i {print $2 "\t" $3; exit}' "$inode_map")
      printf '%s\t%s:%d\t%s:%d\t%s\t%s\t%s\t%s\n' "$proto" \
        "$(hex2ip4 "${la%:*}")" "0x${la#*:}" "$(hex2ip4 "${ra%:*}")" "0x${ra#*:}" \
        "$( [ "$proto" = tcp ] && tcp_state "$st" || echo "-")" "$uid" "$inode" "${owner:-?	?}" >>"$out"
    done <"/proc/net/$proto"
  done
  rm -f "$inode_map"
  echo "$(utc)  rc=0  /proc/net decode  ->  network/connections.tsv" >>"$LOG"
}

# ------------------------------------------------ stage 3: memory stats ---
collect_memory_info() {
  log "[3/6] Memory (statistics)"
  copy_raw memory/meminfo.txt /proc/meminfo
  copy_raw memory/vmstat.txt /proc/vmstat
  copy_raw memory/swaps.txt /proc/swaps
  copy_raw memory/slabinfo.txt /proc/slabinfo
}

# ---------------------------------------------- stage 5: storage triage ---
collect_storage_triage() {
  local days=$1 exclude=$2
  log "[5/6] Storage triage (files modified in the last $days days, logs, config)"
  run storage/df.txt df -hT
  have lsblk && run storage/lsblk.txt lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,MODEL,SERIAL,UUID
  have blkid && run storage/blkid.txt blkid
  # Timeline of recently changed files: mtime, size, owner, mode, path
  run storage/recently_modified_files.txt find / -xdev -path "$exclude" -prune -o -type f -mtime "-$days" \
      -printf '%TY-%Tm-%Td %TH:%TM:%TS\t%s\t%u\t%m\t%p\n'
  run storage/suid_sgid_files.txt find / -xdev -path "$exclude" -prune -o -type f \( -perm -4000 -o -perm -2000 \) \
      -printf '%m\t%u\t%p\n'
  run storage/temp_dirs_listing.txt find /tmp /var/tmp /dev/shm -path "$exclude" -prune -o -printf '%TY-%Tm-%Td %TH:%TM\t%s\t%u\t%m\t%p\n'
  run storage/temp_dirs_executables_sha256.txt find /tmp /var/tmp /dev/shm -path "$exclude" -prune -o -type f -perm /111 \
      -exec sha256sum {} +
  # Config and logs. shadow/gshadow and SSH private host keys are deliberately
  # NOT copied (credential material); add them only if your case requires it.
  # /var/log can be large on a real host (systemd journal): size the output media.
  run storage/etc.tar tar -cpf - --ignore-failed-read --exclude=etc/shadow --exclude=etc/gshadow \
      --exclude='etc/shadow-' --exclude='etc/gshadow-' --exclude='etc/ssh/ssh_host_*_key' -C / etc
  [ -d /var/log ] && run storage/var_log.tar tar -cpf - --ignore-failed-read -C / var/log
  local extra=()
  # From .ssh only the files that show access (who may log in, where this
  # host connected to). Private keys are never copied.
  for f in /root/.bash_history /root/.ash_history /root/.python_history \
           /root/.ssh/authorized_keys /root/.ssh/known_hosts /root/.ssh/config \
           /home/*/.bash_history /home/*/.zsh_history /home/*/.python_history \
           /home/*/.ssh/authorized_keys /home/*/.ssh/known_hosts /home/*/.ssh/config \
           /var/spool/cron /etc/crontab /app; do
    [ -e "$f" ] && extra+=("${f#/}")
  done
  [ "${#extra[@]}" -gt 0 ] && run storage/user_artifacts.tar tar -cpf - --ignore-failed-read -C / "${extra[@]}"
}

# ---------------------------------------- inside-target entry (both modes) ---
# Called as: collect_evidence.sh --live-stage volatile|storage DIR DAYS EXCLUDE
if [ "${1:-}" = "--live-stage" ]; then
  stage=$2; OUT=$3; LOG="$OUT/collection_log.txt"
  mkdir -p "$OUT"
  case $stage in
    volatile) collect_cpu_processes; collect_network_state; collect_memory_info ;;
    storage)  collect_storage_triage "$4" "$5" ;;
  esac
  exit 0
fi

# ------------------------------------------------------------ arguments ---
ORIG_ARGS="$*"
CASE=""; EXAMINER=""; OUTBASE="./evidence"; CONTAINER=""; PCAP=0; MEMORY=0
AVML=""; LIME=""; DISK=""; DAYS=7; EXPORT=1; CAPTURE_IMAGE=""
while [ $# -gt 0 ]; do
  case $1 in
    -c|--case) CASE=${2:-}; shift 2 ;;
    -e|--examiner) EXAMINER=${2:-}; shift 2 ;;
    -o|--out) OUTBASE=${2:-}; shift 2 ;;
    --container) CONTAINER=${2:-}; shift 2 ;;
    --pcap) PCAP=${2:-}; shift 2 ;;
    --memory) MEMORY=1; shift ;;
    --avml) AVML=${2:-}; shift 2 ;;
    --lime) LIME=${2:-}; shift 2 ;;
    --disk) DISK=${2:-}; shift 2 ;;
    --days) DAYS=${2:-}; shift 2 ;;
    --no-export) EXPORT=0; shift ;;
    --capture-image) CAPTURE_IMAGE=${2:-}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
if [ -z "$CASE" ] || [ -z "$EXAMINER" ]; then
  echo "ERROR: --case and --examiner are required (they go in the chain-of-custody record)." >&2
  usage >&2; exit 2
fi
case $PCAP in ''|*[!0-9]*) echo "ERROR: --pcap takes a number of seconds." >&2; exit 2 ;; esac
case $DAYS in ''|*[!0-9]*) echo "ERROR: --days takes a number." >&2; exit 2 ;; esac

TARGET=${CONTAINER:-$(cat /proc/sys/kernel/hostname)}
STAMP=$(date -u '+%Y%m%dT%H%M%SZ')
SAFE_CASE=${CASE//[^A-Za-z0-9._-]/_}
mkdir -p "$OUTBASE" || { echo "ERROR: cannot create $OUTBASE" >&2; exit 2; }
OUT="$(cd "$OUTBASE" && pwd)/${SAFE_CASE}_${TARGET}_${STAMP}"
mkdir -p "$OUT"
LOG="$OUT/collection_log.txt"

{
  echo "Case:              $CASE"
  echo "Examiner:          $EXAMINER"
  echo "Target:            $TARGET ($( [ -n "$CONTAINER" ] && echo "Docker container" || echo "local device"))"
  echo "Collected from:    $(cat /proc/sys/kernel/hostname) as $(id -un) (uid $(id -u))"
  echo "Started (UTC):     $(utc)"
  echo "Local time:        $(date)"
  echo "Tool:              collect_evidence.sh v$VERSION"
  echo "Tool SHA-256:      $(sha256sum "$SCRIPT_PATH" | awk '{print $1}')"
  echo "Command line:      $0 $ORIG_ARGS"
} >"$OUT/case_info.txt"
log "Collection started: case $CASE, examiner $EXAMINER, target $TARGET"
log "Output: $OUT"

# ---------------------------------------------------------- device mode ---
collect_device() {
  if [ "$(id -u)" -ne 0 ]; then
    warn "not running as root — other users' process details, firewall rules, memory and disk images will be missing. Re-run with sudo for a complete collection."
  fi
  local outdev
  outdev=$(df -P "$OUT" 2>/dev/null | awk 'NR==2 {print $1}')
  [ "$outdev" = "$(df -P / | awk 'NR==2 {print $1}')" ] && \
    warn "evidence is being written to the same filesystem as the system under investigation ($outdev). On a real investigation, write to external media (-o /media/usb/...)."

  collect_cpu_processes
  collect_network_state
  collect_memory_info

  if [ "$MEMORY" -eq 1 ]; then
    log "[3/6] Memory: acquiring full RAM image"
    local avml_bin=${AVML:-$(command -v avml || true)}
    if [ "$(id -u)" -ne 0 ]; then
      warn "RAM image skipped: needs root."
    elif [ -n "$avml_bin" ] && [ -x "$avml_bin" ]; then
      run memory/avml_output.txt "$avml_bin" "$OUT/memory/memory.lime" || warn "AVML failed — see memory/avml_output.txt"
    elif [ -n "$LIME" ] && [ -r "$LIME" ]; then
      run memory/lime_output.txt insmod "$LIME" "path=$OUT/memory/memory.lime" "format=lime" \
        && rmmod lime 2>/dev/null || warn "LiME failed — see memory/lime_output.txt"
    else
      warn "RAM image NOT acquired: no AVML or LiME available. Download AVML (github.com/microsoft/avml) to your evidence USB and pass --avml /media/usb/avml."
    fi
  fi

  if [ "$PCAP" -gt 0 ]; then
    log "[4/6] Network traffic: capturing for $PCAP s"
    if have tcpdump; then
      run network/capture_tcpdump_log.txt timeout "$PCAP" tcpdump -i any -nn -s 0 -w "$OUT/network/capture.pcap"
      [ -s "$OUT/network/capture.pcap" ] || warn "packet capture is empty — tcpdump needs root/CAP_NET_RAW"
    else
      warn "packet capture skipped: tcpdump not installed"
    fi
  fi

  collect_storage_triage "$DAYS" "$OUT"

  if [ -n "$DISK" ]; then
    log "[6/6] Storage image: $DISK"
    if [ "$(id -u)" -ne 0 ]; then
      warn "disk image skipped: needs root."
    elif [ ! -b "$DISK" ]; then
      warn "disk image skipped: $DISK is not a block device."
    elif [[ "$outdev" == "$DISK"* ]]; then
      warn "disk image skipped: the output directory is ON $DISK. Use external media."
    else
      have lsblk && run storage/disk_info.txt lsblk -b -o NAME,SIZE,MODEL,SERIAL "$DISK"
      local img="$OUT/storage/$(basename "$DISK").raw"
      if have dc3dd; then
        run storage/disk_image_log.txt dc3dd if="$DISK" of="$img" hash=sha256 log="$OUT/storage/dc3dd.log"
      elif have dcfldd; then
        run storage/disk_image_log.txt dcfldd if="$DISK" of="$img" hash=sha256 \
          hashlog="$OUT/storage/disk_image.sha256" bs=4M conv=noerror,sync
      else
        run storage/disk_image_log.txt dd if="$DISK" of="$img" bs=4M conv=noerror,sync status=progress
        run storage/disk_image.sha256 sha256sum "$img"
      fi
      log "Note: a disk imaged while the system is running keeps changing. For court-grade"
      log "      evidence, power down and image through a hardware write blocker."
    fi
  else
    log "[6/6] Storage image: not requested (add --disk /dev/sdX)"
  fi
}

# ------------------------------------------------------- container mode ---
collect_container() {
  if ! have docker || ! docker info >/dev/null 2>&1; then
    warn "cannot talk to Docker (is it running, and are you in the docker group?)"; return 2
  fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
    warn "container '$CONTAINER' is not running (docker ps lists the running ones)"; return 2
  fi
  [ "$MEMORY" -eq 1 ] && warn "--memory ignored: a container shares the host's kernel and RAM. Image the host's memory with device mode on the Docker host."
  [ -n "$DISK" ] && warn "--disk ignored in container mode: the container filesystem is captured with docker export instead."

  # Host-side view first: touches nothing inside the container.
  log "Host-side container metadata"
  run host_view/docker_inspect.json docker inspect "$CONTAINER"
  run host_view/docker_top.txt docker top "$CONTAINER" -eo pid,ppid,user,lstart,args
  run host_view/docker_stats.txt docker stats --no-stream "$CONTAINER"
  run host_view/image_inspect.json docker image inspect "$(docker inspect -f '{{.Image}}' "$CONTAINER")"
  local net
  for net in $(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$CONTAINER"); do
    run "host_view/network_$net.json" docker network inspect "$net"
  done

  # Live collection inside the container. The script and its output live in
  # /dev/shm (RAM-backed), so nothing is written to the container's disk,
  # which is captured later.
  local work="/dev/shm/.evidence_$STAMP"
  docker exec "$CONTAINER" mkdir -p "$work" || { warn "cannot exec into $CONTAINER"; return 2; }
  docker exec -i "$CONTAINER" sh -c "cat > $work/collect.sh" <"$SCRIPT_PATH"
  fetch_stage() {   # copy a stage's output back out with tar, then clear it
    docker exec "$CONTAINER" tar -C "$work/out" -cf - . | tar -C "$OUT" -xf -
    docker exec "$CONTAINER" rm -rf "$work/out"
    if [ -f "$OUT/collection_log.txt.part" ]; then
      WARNINGS=$((WARNINGS + $(grep -c 'WARNING:' "$OUT/collection_log.txt.part")))
      grep 'WARNING:' "$OUT/collection_log.txt.part" >&2
      cat "$OUT/collection_log.txt.part" >>"$LOG"; rm -f "$OUT/collection_log.txt.part"
    fi
  }
  stage_in_container() {
    docker exec "$CONTAINER" bash "$work/collect.sh" --live-stage "$1" "$work/out" "$DAYS" "$work" 2>/dev/null
    docker exec "$CONTAINER" sh -c "mv $work/out/collection_log.txt $work/out/collection_log.txt.part 2>/dev/null"
    fetch_stage
  }
  if ! docker exec "$CONTAINER" sh -c 'command -v bash' >/dev/null 2>&1; then
    warn "$CONTAINER has no bash — in-container live collection skipped; host-side evidence only"
  else
    log "[1-3/6] CPU & processes, network state, memory statistics (inside $CONTAINER)"
    stage_in_container volatile
  fi

  if [ "$PCAP" -gt 0 ]; then
    log "[4/6] Network traffic: capturing $CONTAINER's traffic for $PCAP s"
    local img=$CAPTURE_IMAGE
    [ -z "$img" ] && img=$(docker inspect -f '{{.Config.Image}}' eng-ws-01 2>/dev/null)
    if [ -z "$img" ]; then
      warn "packet capture skipped: no image with tcpdump (start eng-ws-01 or pass --capture-image)"
    else
      # A throwaway sidecar joins the container's network namespace, so it sees
      # exactly its traffic without installing anything in the container.
      mkdir -p "$OUT/network"
      local start; start=$(utc)
      docker run --rm --network "container:$CONTAINER" --cap-add NET_RAW --cap-add NET_ADMIN \
        --entrypoint timeout "$img" "$PCAP" tcpdump -i any -nn -s 0 -U -w - \
        >"$OUT/network/capture.pcap" 2>"$OUT/network/capture_tcpdump_log.txt" </dev/null
      echo "$start  rc=$?  tcpdump sidecar ($img) in $CONTAINER's network namespace, ${PCAP}s  ->  network/capture.pcap" >>"$LOG"
      [ -s "$OUT/network/capture.pcap" ] || warn "packet capture is empty (no traffic in $PCAP s?)"
    fi
  fi

  if docker exec "$CONTAINER" sh -c 'command -v bash' >/dev/null 2>&1; then
    stage_in_container storage
  fi
  docker exec "$CONTAINER" rm -rf "$work"

  log "[6/6] Storage: container filesystem changes and image"
  run host_view/docker_diff.txt docker diff "$CONTAINER"      # A=added C=changed D=deleted vs the image
  # the container's own stderr is part of its log, so merge both streams
  run host_view/docker_logs.txt sh -c 'docker logs --timestamps "$1" 2>&1' _ "$CONTAINER"
  if [ "$EXPORT" -eq 1 ]; then
    run storage/container_filesystem.tar docker export "$CONTAINER"
  else
    log "Filesystem export skipped (--no-export)"
  fi
}

if [ -n "$CONTAINER" ]; then
  collect_container; rc=$?
  [ "$rc" -eq 2 ] && { log "Collection aborted."; exit 2; }
else
  collect_device
fi

# ------------------------------------------------------------- seal it ---
echo "Finished (UTC):    $(utc)" >>"$OUT/case_info.txt"
echo "Warnings:          $WARNINGS (details in collection_log.txt)" >>"$OUT/case_info.txt"
log "Collection finished: $(find "$OUT" -type f | wc -l) files, $(du -sh "$OUT" | cut -f1). Sealing with manifest.sha256."
# Nothing is written to $OUT after this point, so the manifest covers everything.
(cd "$OUT" && find . -type f ! -name manifest.sha256 -print0 | sort -z | xargs -0 sha256sum >manifest.sha256)
MANIFEST_HASH=$(sha256sum "$OUT/manifest.sha256" | awk '{print $1}')

cat <<EOF

==============================================================
 Evidence collected: $OUT
 Manifest SHA-256:   $MANIFEST_HASH
 Warnings:           $WARNINGS
==============================================================
 Record the manifest SHA-256 in your chain-of-custody log now.
 Verify later with:  (cd "$OUT" && sha256sum -c manifest.sha256)
EOF
[ "$WARNINGS" -gt 0 ] && exit 1
exit 0
