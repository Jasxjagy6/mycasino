#!/usr/bin/env bash
# Blue-green deployment switch for the mycasino Telegram bot.
#
#   ./deploy/blue_green_switch.sh deploy <git-ref>     # full upgrade
#   ./deploy/blue_green_switch.sh status               # show active color
#   ./deploy/blue_green_switch.sh switch blue|green    # flip without redeploy
#
# Lifecycle of `deploy`:
#   1. Determine current active color (CURR) and target (NEXT).
#   2. Stop the inactive color (NEXT) if it's leftover from a previous run.
#   3. Check out <git-ref> into /opt/mycasino-$NEXT.
#   4. systemctl start mycasino-bot@$NEXT.
#   5. Poll /healthz on the inactive color until it returns 200.
#   6. Atomically rewrite /etc/nginx/active_color.conf to "$NEXT" and
#      `nginx -s reload`.
#   7. Send SIGTERM to the now-old color; the bot's drain handler keeps
#      finishing in-flight Telegram requests for ~25s before exiting.
#
# Telegram never sees a single dropped update because (a) nginx reloads
# are zero-downtime, (b) the new color is fully ready before traffic
# switches, and (c) the old color drains gracefully.

set -euo pipefail

ACTIVE_COLOR_FILE=${ACTIVE_COLOR_FILE:-/etc/nginx/active_color.conf}
DEPLOY_ROOT=${DEPLOY_ROOT:-/opt/mycasino}
NGINX_RELOAD=${NGINX_RELOAD:-"sudo nginx -s reload"}
HEALTH_BLUE=${HEALTH_BLUE:-http://127.0.0.1:9000/healthz}
HEALTH_GREEN=${HEALTH_GREEN:-http://127.0.0.1:9001/healthz}
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-90}      # seconds
DRAIN_GRACE=${DRAIN_GRACE:-30}            # seconds the old color gets to drain

current_color() {
    if [[ -f "$ACTIVE_COLOR_FILE" ]]; then
        # Match: set $mycasino_active_color "blue";
        local color
        color=$(grep -oE '"(blue|green)"' "$ACTIVE_COLOR_FILE" | head -n1 | tr -d '"')
        if [[ -n "$color" ]]; then
            echo "$color"
            return 0
        fi
    fi
    echo "blue"
}

other_color() {
    if [[ "$1" == "blue" ]]; then echo "green"; else echo "blue"; fi
}

health_url_for() {
    if [[ "$1" == "blue" ]]; then echo "$HEALTH_BLUE"; else echo "$HEALTH_GREEN"; fi
}

wait_for_health() {
    local url=$1
    local deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
    while (( $(date +%s) < deadline )); do
        if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo "ERROR: $url did not become healthy within ${HEALTH_TIMEOUT}s" >&2
    return 1
}

write_active_color() {
    local color=$1
    local tmp
    tmp=$(mktemp)
    printf 'set $mycasino_active_color "%s";\n' "$color" > "$tmp"
    sudo install -m 0644 "$tmp" "$ACTIVE_COLOR_FILE"
    rm -f "$tmp"
}

cmd_status() {
    local cur
    cur=$(current_color)
    echo "active: $cur"
    echo "blue health:  $(curl -s --max-time 2 "$HEALTH_BLUE"  || echo unreachable)"
    echo "green health: $(curl -s --max-time 2 "$HEALTH_GREEN" || echo unreachable)"
}

cmd_switch() {
    local target=${1:-}
    if [[ "$target" != "blue" && "$target" != "green" ]]; then
        echo "Usage: $0 switch blue|green" >&2
        exit 2
    fi
    if ! curl -fsS --max-time 3 "$(health_url_for "$target")" >/dev/null; then
        echo "ERROR: $target instance is not healthy; refusing to switch" >&2
        exit 1
    fi
    write_active_color "$target"
    eval "$NGINX_RELOAD"
    echo "switched to $target"
}

cmd_deploy() {
    local ref=${1:-}
    if [[ -z "$ref" ]]; then
        echo "Usage: $0 deploy <git-ref>" >&2
        exit 2
    fi
    local curr next
    curr=$(current_color)
    next=$(other_color "$curr")

    echo "==> deploying $ref to $next (currently active: $curr)"

    local target_dir="${DEPLOY_ROOT}-${next}"
    if [[ -d "$target_dir/.git" ]]; then
        (cd "$target_dir" && git fetch --all && git checkout "$ref" && git pull --ff-only)
    else
        sudo mkdir -p "$target_dir"
        sudo git clone https://github.com/Jasxjagy6/mycasino.git "$target_dir"
        (cd "$target_dir" && git checkout "$ref")
    fi

    # Optional: install deps inside the per-color venv.
    if [[ -f "$target_dir/requirements.txt" ]]; then
        if [[ ! -d "$target_dir/.venv" ]]; then
            python3 -m venv "$target_dir/.venv"
        fi
        "$target_dir/.venv/bin/pip" install -r "$target_dir/requirements.txt"
    fi

    sudo systemctl restart "mycasino-bot@${next}.service"
    echo "==> waiting for $next health..."
    wait_for_health "$(health_url_for "$next")"

    echo "==> flipping nginx upstream blue<->green"
    write_active_color "$next"
    eval "$NGINX_RELOAD"

    echo "==> draining $curr (${DRAIN_GRACE}s)"
    sudo systemctl kill --signal=SIGTERM "mycasino-bot@${curr}.service" || true
    sleep "$DRAIN_GRACE"
    sudo systemctl stop "mycasino-bot@${curr}.service" || true

    echo "==> deploy complete; active color is now $next"
}

main() {
    local cmd=${1:-status}
    shift || true
    case "$cmd" in
        status)  cmd_status ;;
        switch)  cmd_switch "$@" ;;
        deploy)  cmd_deploy "$@" ;;
        *) echo "Usage: $0 {status|switch|deploy} ..." >&2; exit 2 ;;
    esac
}

main "$@"
