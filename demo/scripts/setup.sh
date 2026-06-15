#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$DEMO_DIR/.env"
ENV_EXAMPLE="$DEMO_DIR/backend/.env.example"

if [ -f "$ENV_FILE" ]; then
    echo ".env already exists at $ENV_FILE"
    echo "Delete it and re-run to regenerate secrets."
    exit 0
fi

if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required to generate secrets."
    exit 1
fi

echo "Generating secrets..."

APP_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
# Works with or without the cryptography package installed
ENC_KEY=$(python3 -c "
try:
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())
except ImportError:
    import base64, os
    print(base64.urlsafe_b64encode(os.urandom(32)).decode())
")

cat > "$ENV_FILE" <<EOF
APP_ENV=development
APP_DEBUG=true

DATABASE_URL=sqlite:///./demo.db
REDIS_URL=redis://localhost:6379

APP_SECRET_KEY=$APP_SECRET
JWT_SECRET_KEY=$JWT_SECRET
ENCRYPTION_KEY=$ENC_KEY

FRONTEND_BASE_URL=http://localhost:4200
CORS_ORIGINS=http://localhost:4200
EOF

echo "Created $ENV_FILE"
echo ""
echo "Next steps:"
echo "  Backend:  cd demo/backend && pip install -e ../../ && pip install -r requirements.txt"
echo "  Frontend: cd demo/frontend && npm install"
echo ""
echo "Then run:  make start   (or make docker-up for Docker)"
