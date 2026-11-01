# ============================================================
# Arcabuz — Multi-tool fuzzing for bug bounty
# Part of AEGIR Security toolkit
# ============================================================
# Stage 1: compile Go tools (ffuf, gobuster)
# ============================================================
FROM golang:1.25-bookworm AS go-builder

RUN go install github.com/ffuf/ffuf/v2@latest && \
    go install github.com/OJ/gobuster/v3@latest

# ============================================================
# Stage 2: compile Rust tools (feroxbuster)
# ============================================================
FROM rust:bookworm AS rust-builder

RUN cargo install feroxbuster

# ============================================================
# Stage 3: main image
# ============================================================
FROM python:3.12-slim-bookworm

LABEL maintainer="Manuel Miguel Fernandez-Gallego Olivares"
LABEL description="Arcabuz — multi-tool fuzzing for bug bounty"

# ---- system deps -------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl jq git unzip \
    && rm -rf /var/lib/apt/lists/*

# ---- Go binaries from builder ------------------------------
COPY --from=go-builder /go/bin/ffuf /usr/local/bin/ffuf
COPY --from=go-builder /go/bin/gobuster /usr/local/bin/gobuster

# ---- Rust binary from builder ------------------------------
COPY --from=rust-builder /usr/local/cargo/bin/feroxbuster /usr/local/bin/feroxbuster

# ---- dirsearch (Python) ------------------------------------
RUN git clone --depth 1 https://github.com/maurosoria/dirsearch.git /opt/dirsearch && \
    pip install --break-system-packages -r /opt/dirsearch/requirements.txt 2>/dev/null || true && \
    ln -s /opt/dirsearch/dirsearch.py /usr/local/bin/dirsearch

# ---- SecLists (selected wordlists only, not the full 2GB) --
RUN mkdir -p /wordlists && \
    git clone --depth 1 --filter=blob:none --sparse \
        https://github.com/danielmiessler/SecLists.git /tmp/seclists && \
    cd /tmp/seclists && \
    git sparse-checkout set \
        Discovery/Web-Content/raft-medium-directories.txt \
        Discovery/Web-Content/raft-medium-files.txt \
        Discovery/Web-Content/raft-small-words.txt \
        Discovery/Web-Content/common.txt \
        Discovery/Web-Content/directory-list-2.3-medium.txt \
        Discovery/Web-Content/api/api-endpoints.txt \
        Discovery/Web-Content/burp-parameter-names.txt \
        Discovery/DNS/subdomains-top1million-5000.txt \
        Discovery/DNS/subdomains-top1million-20000.txt \
        Discovery/DNS/namelist.txt && \
    cp -r Discovery /wordlists/Discovery && \
    rm -rf /tmp/seclists

# ---- app scripts -------------------------------------------
COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

WORKDIR /app

ENTRYPOINT ["/app/scripts/arcabuz.sh"]
CMD ["--help"]
