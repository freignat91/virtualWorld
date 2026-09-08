#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

CERT_FILE="certs/cert.pem"
KEY_FILE="certs/key.pem"

if [ ! -s "$CERT_FILE" ] || [ ! -s "$KEY_FILE" ]; then
    if [ -e "$CERT_FILE" ] || [ -e "$KEY_FILE" ]; then
        echo "Certificat HTTPS incomplet: supprimez ou restaurez certs/cert.pem et certs/key.pem." >&2
        exit 1
    fi
    if ! command -v openssl >/dev/null 2>&1; then
        echo "OpenSSL est requis pour generer le certificat HTTPS." >&2
        exit 1
    fi

    mkdir -p certs
    TEMP_CERT_DIR=$(mktemp -d "certs/.generate.XXXXXX")
    trap 'rm -rf "$TEMP_CERT_DIR"' EXIT

    CERT_NAME=localhost
    SUBJECT_ALT_NAME="DNS:localhost,IP:127.0.0.1"
    if command -v hostname >/dev/null 2>&1; then
        HOST_NAME=$(hostname -f 2>/dev/null || hostname 2>/dev/null || true)
        if [[ $HOST_NAME =~ ^[A-Za-z0-9.-]+$ ]]; then
            CERT_NAME=$HOST_NAME
            SUBJECT_ALT_NAME+=",DNS:$HOST_NAME"
        fi
        for host_ip in $(hostname -I 2>/dev/null || true); do
            if [[ $host_ip =~ ^[0-9A-Fa-f:.]+$ ]]; then
                SUBJECT_ALT_NAME+=",IP:$host_ip"
            fi
        done
    fi

    echo "Generation d'un certificat HTTPS auto-signe pour $CERT_NAME..."
    openssl req -x509 -newkey rsa:4096 -sha256 -nodes \
        -keyout "$TEMP_CERT_DIR/key.pem" -out "$TEMP_CERT_DIR/cert.pem" \
        -days 3650 -subj "/CN=$CERT_NAME" \
        -addext "subjectAltName=$SUBJECT_ALT_NAME"
    chmod 0600 "$TEMP_CERT_DIR/key.pem"
    chmod 0644 "$TEMP_CERT_DIR/cert.pem"
    mv "$TEMP_CERT_DIR/key.pem" "$KEY_FILE"
    mv "$TEMP_CERT_DIR/cert.pem" "$CERT_FILE"
    rmdir "$TEMP_CERT_DIR"
    trap - EXIT
fi

# Utilise le venv si présent (apporte SB3 + torch pour les bots RL).
PY=python3
if [ -x ".venv/bin/python" ]; then
    PY=.venv/bin/python
elif [ -x "venv/bin/python" ]; then
    PY=venv/bin/python
fi
"$PY" server.py "$@" 2>&1 | "$PY" logfilter.py
