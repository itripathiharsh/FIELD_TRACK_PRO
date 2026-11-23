#!/usr/bin/env bash
# Run the QA server LOCALLY against the local build database, configured like the Render service. Port 8099.
set -e
export MSYS_NO_PATHCONV=1 MSYS2_ENV_CONV_EXCL="*"
cd "$(dirname "$0")/repo/fieldtrackpro-backend"
URLS=$(cd .. && cd .. && python -c "
import setup_build_db as t; e=t.test_env(); print(e['DATABASE_URL']); print(e['MIGRATION_DATABASE_URL'])")
export DATABASE_URL="$(echo "$URLS" | sed -n 1p)" MIGRATION_DATABASE_URL="$(echo "$URLS" | sed -n 2p)"
export ENVIRONMENT=production DEBUG=false API_V1_PREFIX=/api/v1
export JWT_SECRET="local-qa-$(date +%s)-jwt" MEDIA_SIGNING_SECRET="local-qa-$(date +%s)-media" OTP_HMAC_SECRET="local-qa-$(date +%s)-otp"
export CORS_ALLOWED_ORIGINS="http://localhost:8099,http://127.0.0.1:8099"
export TRUSTED_PROXY_HOPS=1 REFRESH_COOKIE_SAMESITE=lax ENFORCE_PASSWORD_CHANGE=false
export STORAGE_PROVIDER=LOCAL MEDIA_STORAGE_PATH=qa_media
export TALLY_WRITEBACK_ENABLED=false ENABLE_SCHEDULER=false ALLOW_MOCK_COMMUNICATIONS=true SMS_PROVIDER=mock FIREBASE_CREDENTIALS_PATH=""
export ORGANIZATION_NAME="DEMO Distribution Co. (QA - fictional)" ORGANIZATION_HUB="Demo City (fictional)"
export ORGANIZATION_DIVISIONS="Demo Mobiles & Demo Electronics (fictional)" ORGANIZATION_CONTACT_EMAIL="demo@fieldtrack-demo.test"
export ORGANIZATION_CONTACT_PHONE="+91 99999 00000" ORGANIZATION_GSTIN="09DEMO0000A1Z0"
exec python -m uvicorn qa_asgi:application --host 127.0.0.1 --port 8099 --no-proxy-headers --log-level warning
