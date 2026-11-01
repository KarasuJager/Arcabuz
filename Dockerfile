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

# ---- SecLists (selected wordlists, downloaded individually) --
RUN mkdir -p /wordlists/Discovery/Web-Content/api /wordlists/Discovery/DNS && \
    BASE="https://raw.githubusercontent.com/danielmiessler/SecLists/master" && \
    curl -sSL "$BASE/Discovery/Web-Content/raft-medium-directories.txt" -o /wordlists/Discovery/Web-Content/raft-medium-directories.txt && \
    curl -sSL "$BASE/Discovery/Web-Content/raft-medium-files.txt" -o /wordlists/Discovery/Web-Content/raft-medium-files.txt && \
    curl -sSL "$BASE/Discovery/Web-Content/raft-small-words.txt" -o /wordlists/Discovery/Web-Content/raft-small-words.txt && \
    curl -sSL "$BASE/Discovery/Web-Content/common.txt" -o /wordlists/Discovery/Web-Content/common.txt && \
    curl -sSL "$BASE/Discovery/Web-Content/directory-list-2.3-medium.txt" -o /wordlists/Discovery/Web-Content/directory-list-2.3-medium.txt && \
    curl -sSL "$BASE/Discovery/Web-Content/api/api-endpoints.txt" -o /wordlists/Discovery/Web-Content/api/api-endpoints.txt && \
    curl -sSL "$BASE/Discovery/Web-Content/burp-parameter-names.txt" -o /wordlists/Discovery/Web-Content/burp-parameter-names.txt && \
    curl -sSL "$BASE/Discovery/DNS/subdomains-top1million-5000.txt" -o /wordlists/Discovery/DNS/subdomains-top1million-5000.txt && \
    curl -sSL "$BASE/Discovery/DNS/subdomains-top1million-20000.txt" -o /wordlists/Discovery/DNS/subdomains-top1million-20000.txt && \
    curl -sSL "$BASE/Discovery/DNS/namelist.txt" -o /wordlists/Discovery/DNS/namelist.txt

# ---- app scripts -------------------------------------------
COPY scripts/ /app/scripts/
RUN sed -i 's/\r$//' /app/scripts/*.sh /app/scripts/*.py && chmod +x /app/scripts/*.sh

WORKDIR /app

ENTRYPOINT ["/app/scripts/arcabuz.sh"]
CMD ["--help"]
