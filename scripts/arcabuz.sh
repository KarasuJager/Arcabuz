#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#     _    ____   ____    _    ____  _   _ _____
#    / \  |  _ \ / ___|  / \  | __ )| | | |__  /
#   / _ \ | |_) | |     / _ \ |  _ \| | | | / /
#  / ___ \|  _ <| |___ / ___ \| |_) | |_| |/ /_
# /_/   \_\_| \_\\____/_/   \_\____/ \___//____|
#
#  AEGIR Security — Arcabuz
#  Multi-tool fuzzing for bug bounty
# ============================================================

HANDLE="${HANDLE:-researcher}"
UA="bugbounty-${HANDLE}"

usage() {
    cat <<'HELP'
Arcabuz — Multi-tool fuzzing (ffuf + gobuster + dirsearch + feroxbuster)

Modos:
  arcabuz dirs   -u URL -w WORDLIST          Fuzzear directorios/ficheros
  arcabuz subs   -d DOMAIN -w WORDLIST       Fuzzear subdominios
  arcabuz params -u URL -w WORDLIST          Fuzzear parámetros
  arcabuz vhosts -u URL -d DOMAIN -w WORDLIST  Fuzzear virtual hosts

Opciones:
  -u URL         URL target (con FUZZ si quieres posición custom)
  -d DOMAIN      Dominio root
  -w WORDLIST    Wordlist (nombre de SecLists o path completo)
  -t THREADS     Hilos (default: 40)
  -x EXTENSIONS  Extensiones para dirs (ej: php,asp,jsp)
  -o OUTPUT      Directorio de output (default: /data/<mode>-<timestamp>)
  --help         Esta ayuda

Wordlists incluidas en /wordlists/Discovery/:
  DNS/subdomains-top1million-5000.txt
  DNS/subdomains-top1million-20000.txt
  Web-Content/raft-medium-directories.txt
  Web-Content/raft-medium-files.txt
  Web-Content/common.txt
  Web-Content/directory-list-2.3-medium.txt
  Web-Content/api/api-endpoints.txt
  Web-Content/burp-parameter-names.txt
HELP
    exit 0
}

# ---- Parse mode ----
MODE="${1:-}"
[ -z "$MODE" ] && usage
[ "$MODE" = "--help" ] && usage
shift

# ---- Parse arguments ----
URL="" DOMAIN="" WORDLIST="" THREADS="40" EXTENSIONS="" OUTPUT="" TOOL_TIMEOUT="300"

while [ $# -gt 0 ]; do
    case "$1" in
        -u) URL="$2"; shift 2 ;;
        -d) DOMAIN="$2"; shift 2 ;;
        -w) WORDLIST="$2"; shift 2 ;;
        -t) THREADS="$2"; shift 2 ;;
        -x) EXTENSIONS="$2"; shift 2 ;;
        -o) OUTPUT="$2"; shift 2 ;;
        -T) TOOL_TIMEOUT="$2"; shift 2 ;;
        --help) usage ;;
        *) echo "[!] Unknown option: $1"; usage ;;
    esac
done

# ---- Resolve wordlist path ----
if [ -n "$WORDLIST" ]; then
    if [ -f "$WORDLIST" ]; then
        WL="$WORDLIST"
    elif [ -f "/wordlists/Discovery/$WORDLIST" ]; then
        WL="/wordlists/Discovery/$WORDLIST"
    elif [ -f "/wordlists/Discovery/Web-Content/$WORDLIST" ]; then
        WL="/wordlists/Discovery/Web-Content/$WORDLIST"
    elif [ -f "/wordlists/Discovery/DNS/$WORDLIST" ]; then
        WL="/wordlists/Discovery/DNS/$WORDLIST"
    else
        echo "[!] Wordlist not found: $WORDLIST"
        echo "    Available in /wordlists/Discovery/:"
        find /wordlists -name "*.txt" -type f | sort
        exit 1
    fi
else
    echo "[!] Wordlist required (-w)"
    exit 1
fi

# ---- Setup output ----
TS=$(date +%Y%m%d-%H%M%S)
[ -z "$OUTPUT" ] && OUTPUT="/data/${MODE}-${TS}"
mkdir -p "$OUTPUT"/{raw,merged}

echo "============================================"
echo " Arcabuz — $MODE"
echo " $(date)"
echo " Wordlist: $(basename "$WL") ($(wc -l < "$WL") entries)"
echo " Threads: $THREADS"
echo " Timeout: ${TOOL_TIMEOUT}s por herramienta"
echo " Output: $OUTPUT"
echo "============================================"
echo ""

# ════════════════════════════════════════════════════════════
# MODE: dirs — Directory/file fuzzing
# ════════════════════════════════════════════════════════════
if [ "$MODE" = "dirs" ]; then
    [ -z "$URL" ] && { echo "[!] URL required (-u)"; exit 1; }

    EXT_FLAG_FFUF=""
    EXT_FLAG_GOBUSTER=""
    EXT_FLAG_DIRSEARCH=""
    EXT_FLAG_FEROX=""
    if [ -n "$EXTENSIONS" ]; then
        EXT_FLAG_FFUF="-e .$( echo "$EXTENSIONS" | sed 's/,/,./g' )"
        EXT_FLAG_GOBUSTER="-x $EXTENSIONS"
        EXT_FLAG_DIRSEARCH="-e $EXTENSIONS"
        EXT_FLAG_FEROX="-x $( echo "$EXTENSIONS" | sed 's/,/ -x /g' )"
    fi

    echo "══════════════════════════════════════════"
    echo " [1/4] ffuf"
    echo "══════════════════════════════════════════"
    echo '{"results":[]}' > "$OUTPUT/raw/ffuf.json"
    timeout --kill-after=10 "$TOOL_TIMEOUT" ffuf -u "${URL}/FUZZ" -w "$WL" -t "$THREADS" \
        -H "User-Agent: ${UA}" \
        -mc all -fc 404 \
        -o "$OUTPUT/raw/ffuf.json" -of json \
        $EXT_FLAG_FFUF \
        2>/dev/null || true
    FFUF_COUNT=$(jq '.results | length' "$OUTPUT/raw/ffuf.json" 2>/dev/null || echo 0)
    echo "    -> $FFUF_COUNT results"
    [ "$FFUF_COUNT" -eq 0 ] && echo "    (timeout o sin resultados)"
    echo ""

    echo "══════════════════════════════════════════"
    echo " [2/4] gobuster"
    echo "══════════════════════════════════════════"
    touch "$OUTPUT/raw/gobuster.txt"
    timeout --kill-after=10 "$TOOL_TIMEOUT" gobuster dir -u "$URL" -w "$WL" -t "$THREADS" \
        -a "$UA" \
        -s "200,201,204,301,302,307,401,403,405" \
        -o "$OUTPUT/raw/gobuster.txt" \
        --no-error -q \
        $EXT_FLAG_GOBUSTER \
        2>/dev/null || true
    GOBUSTER_COUNT=$(wc -l < "$OUTPUT/raw/gobuster.txt" 2>/dev/null || echo 0)
    echo "    -> $GOBUSTER_COUNT results"
    echo ""

    echo "══════════════════════════════════════════"
    echo " [3/4] dirsearch"
    echo "══════════════════════════════════════════"
    echo '{"results":{}}' > "$OUTPUT/raw/dirsearch.json"
    timeout --kill-after=10 "$TOOL_TIMEOUT" python3 /opt/dirsearch/dirsearch.py -u "$URL" -w "$WL" \
        -t "$THREADS" \
        --user-agent="$UA" \
        --format=json -o "$OUTPUT/raw/dirsearch.json" \
        $EXT_FLAG_DIRSEARCH \
        -q 2>/dev/null || true
    DIRSEARCH_COUNT=$(jq '[.results[]] | length' "$OUTPUT/raw/dirsearch.json" 2>/dev/null || echo 0)
    echo "    -> $DIRSEARCH_COUNT results"
    echo ""

    echo "══════════════════════════════════════════"
    echo " [4/4] feroxbuster"
    echo "══════════════════════════════════════════"
    touch "$OUTPUT/raw/feroxbuster.txt"
    timeout --kill-after=10 "$TOOL_TIMEOUT" feroxbuster -u "$URL" -w "$WL" -t "$THREADS" \
        -H "User-Agent: ${UA}" \
        -s 200,201,204,301,302,307,401,403,405 \
        -o "$OUTPUT/raw/feroxbuster.txt" \
        --no-state -q \
        $EXT_FLAG_FEROX \
        2>/dev/null || true
    FEROX_COUNT=$(grep -cE "^[0-9]+ +[A-Z]+ .+http" "$OUTPUT/raw/feroxbuster.txt" 2>/dev/null || echo 0)
    echo "    -> $FEROX_COUNT results"
    echo ""

# ════════════════════════════════════════════════════════════
# MODE: subs — Subdomain fuzzing
# ════════════════════════════════════════════════════════════
elif [ "$MODE" = "subs" ]; then
    [ -z "$DOMAIN" ] && { echo "[!] Domain required (-d)"; exit 1; }

    echo "══════════════════════════════════════════"
    echo " [1/2] ffuf (vhost)"
    echo "══════════════════════════════════════════"
    echo '{"results":[]}' > "$OUTPUT/raw/ffuf-subs.json"
    timeout --kill-after=10 "$TOOL_TIMEOUT" ffuf -u "http://${DOMAIN}" -w "$WL" -t "$THREADS" \
        -H "Host: FUZZ.${DOMAIN}" \
        -H "User-Agent: ${UA}" \
        -mc all -fc 404 \
        -fs 0 \
        -o "$OUTPUT/raw/ffuf-subs.json" -of json \
        2>/dev/null || true
    FFUF_COUNT=$(jq '.results | length' "$OUTPUT/raw/ffuf-subs.json" 2>/dev/null || echo 0)
    echo "    -> $FFUF_COUNT results"
    echo ""

    echo "══════════════════════════════════════════"
    echo " [2/2] gobuster (dns)"
    echo "══════════════════════════════════════════"
    touch "$OUTPUT/raw/gobuster-subs.txt"
    timeout --kill-after=10 "$TOOL_TIMEOUT" gobuster dns -d "$DOMAIN" -w "$WL" -t "$THREADS" \
        -o "$OUTPUT/raw/gobuster-subs.txt" \
        --no-error -q \
        2>/dev/null || true
    GOBUSTER_COUNT=$(wc -l < "$OUTPUT/raw/gobuster-subs.txt" 2>/dev/null || echo 0)
    echo "    -> $GOBUSTER_COUNT results"
    echo ""

# ════════════════════════════════════════════════════════════
# MODE: params — Parameter fuzzing
# ════════════════════════════════════════════════════════════
elif [ "$MODE" = "params" ]; then
    [ -z "$URL" ] && { echo "[!] URL required (-u)"; exit 1; }

    echo "══════════════════════════════════════════"
    echo " [1/2] ffuf (GET params)"
    echo "══════════════════════════════════════════"
    echo '{"results":[]}' > "$OUTPUT/raw/ffuf-params-get.json"
    timeout --kill-after=10 "$TOOL_TIMEOUT" ffuf -u "${URL}?FUZZ=test" -w "$WL" -t "$THREADS" \
        -H "User-Agent: ${UA}" \
        -mc all -fc 404 \
        -fs 0 -fl 0 \
        -o "$OUTPUT/raw/ffuf-params-get.json" -of json \
        2>/dev/null || true
    FFUF_GET=$(jq '.results | length' "$OUTPUT/raw/ffuf-params-get.json" 2>/dev/null || echo 0)
    echo "    -> $FFUF_GET GET params"

    echo ""
    echo "══════════════════════════════════════════"
    echo " [2/2] ffuf (POST params)"
    echo "══════════════════════════════════════════"
    echo '{"results":[]}' > "$OUTPUT/raw/ffuf-params-post.json"
    timeout --kill-after=10 "$TOOL_TIMEOUT" ffuf -u "$URL" -w "$WL" -t "$THREADS" \
        -H "User-Agent: ${UA}" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "FUZZ=test" -X POST \
        -mc all -fc 404 \
        -fs 0 -fl 0 \
        -o "$OUTPUT/raw/ffuf-params-post.json" -of json \
        2>/dev/null || true
    FFUF_POST=$(jq '.results | length' "$OUTPUT/raw/ffuf-params-post.json" 2>/dev/null || echo 0)
    echo "    -> $FFUF_POST POST params"
    echo ""

# ════════════════════════════════════════════════════════════
# MODE: vhosts — Virtual host fuzzing
# ════════════════════════════════════════════════════════════
elif [ "$MODE" = "vhosts" ]; then
    [ -z "$URL" ] && { echo "[!] URL required (-u)"; exit 1; }
    [ -z "$DOMAIN" ] && { echo "[!] Domain required (-d)"; exit 1; }

    echo "══════════════════════════════════════════"
    echo " [1/2] ffuf (vhost)"
    echo "══════════════════════════════════════════"
    echo '{"results":[]}' > "$OUTPUT/raw/ffuf-vhosts.json"
    timeout --kill-after=10 "$TOOL_TIMEOUT" ffuf -u "$URL" -w "$WL" -t "$THREADS" \
        -H "Host: FUZZ.${DOMAIN}" \
        -H "User-Agent: ${UA}" \
        -mc all -fc 404 \
        -o "$OUTPUT/raw/ffuf-vhosts.json" -of json \
        2>/dev/null || true
    FFUF_COUNT=$(jq '.results | length' "$OUTPUT/raw/ffuf-vhosts.json" 2>/dev/null || echo 0)
    echo "    -> $FFUF_COUNT results"
    echo ""

    echo "══════════════════════════════════════════"
    echo " [2/2] gobuster (vhost)"
    echo "══════════════════════════════════════════"
    touch "$OUTPUT/raw/gobuster-vhosts.txt"
    timeout --kill-after=10 "$TOOL_TIMEOUT" gobuster vhost -u "$URL" -w "$WL" -t "$THREADS" \
        -a "$UA" \
        -o "$OUTPUT/raw/gobuster-vhosts.txt" \
        --no-error -q --append-domain \
        2>/dev/null || true
    GOBUSTER_COUNT=$(wc -l < "$OUTPUT/raw/gobuster-vhosts.txt" 2>/dev/null || echo 0)
    echo "    -> $GOBUSTER_COUNT results"
    echo ""

else
    echo "[!] Modo desconocido: $MODE"
    echo "    Modos: dirs, subs, params, vhosts"
    exit 1
fi

# ════════════════════════════════════════════════════════════
# MERGE + DEDUP
# ════════════════════════════════════════════════════════════
echo "══════════════════════════════════════════"
echo " Merge + deduplicación"
echo "══════════════════════════════════════════"

python3 /app/scripts/merge.py "$OUTPUT" "$MODE"

MERGED_COUNT=$(wc -l < "$OUTPUT/merged/unique-results.txt" 2>/dev/null || echo 0)
DUPES=$(cat "$OUTPUT/merged/duplicates.txt" 2>/dev/null | wc -l || echo 0)

echo ""
echo "============================================"
echo " Arcabuz complete — $MODE"
echo "============================================"
echo ""
echo " Resultados únicos: $MERGED_COUNT"
echo " Duplicados eliminados: $DUPES"
echo " Output: $OUTPUT/"
echo "   raw/       resultados individuales de cada herramienta"
echo "   merged/    resultados deduplicados + clasificados"
echo ""
echo " Next: Mimir analiza los resultados"
echo "============================================"
