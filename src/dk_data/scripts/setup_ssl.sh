#!/bin/bash
# SSL Certificate Setup Script
# Generates self-signed certificates for development/testing
# For production, use Let's Encrypt with certbot

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SSL_DIR="$PROJECT_ROOT/nginx/ssl"

# Default values
DOMAIN="${1:-localhost}"
DAYS="${2:-365}"

echo "=== SSL Certificate Setup ==="
echo "Domain: $DOMAIN"
echo "Validity: $DAYS days"
echo ""

# Create SSL directory
mkdir -p "$SSL_DIR"

# Check if certificates already exist
if [ -f "$SSL_DIR/fullchain.pem" ] && [ -f "$SSL_DIR/privkey.pem" ]; then
    read -p "Certificates already exist. Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing certificates."
        exit 0
    fi
fi

echo "Generating self-signed certificate..."

# Generate private key
openssl genrsa -out "$SSL_DIR/privkey.pem" 2048

# Generate certificate signing request (CSR)
openssl req -new -key "$SSL_DIR/privkey.pem" \
    -out "$SSL_DIR/csr.pem" \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=$DOMAIN"

# Generate self-signed certificate
openssl x509 -req -days "$DAYS" \
    -in "$SSL_DIR/csr.pem" \
    -signkey "$SSL_DIR/privkey.pem" \
    -out "$SSL_DIR/fullchain.pem"

# Clean up CSR
rm "$SSL_DIR/csr.pem"

# Set permissions
chmod 600 "$SSL_DIR/privkey.pem"
chmod 644 "$SSL_DIR/fullchain.pem"

echo ""
echo "=== Certificates Generated ==="
echo "Private key: $SSL_DIR/privkey.pem"
echo "Certificate: $SSL_DIR/fullchain.pem"
echo ""
echo "NOTE: This is a self-signed certificate for testing."
echo "For production, use Let's Encrypt:"
echo ""
echo "  # Install certbot"
echo "  sudo apt install certbot"
echo ""
echo "  # Get certificate"
echo "  sudo certbot certonly --standalone -d $DOMAIN"
echo ""
echo "  # Copy certificates"
echo "  sudo cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem $SSL_DIR/"
echo "  sudo cp /etc/letsencrypt/live/$DOMAIN/privkey.pem $SSL_DIR/"
echo ""
