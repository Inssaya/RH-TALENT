FROM node:22-alpine AS deps
WORKDIR /app
# Optional extra CA certificates (corporate proxy): drop *.crt files in ./ca at the repository root.
COPY ca/ /extra-ca/
RUN cat /extra-ca/*.crt > /extra-ca.pem 2>/dev/null || true
ENV NODE_EXTRA_CA_CERTS=/extra-ca.pem
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM deps AS build
COPY frontend/ ./
ARG NEXT_PUBLIC_SITE_URL=http://localhost
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S app && adduser -S app -G app
COPY --from=build --chown=app:app /app/.next/standalone ./
COPY --from=build --chown=app:app /app/.next/static ./.next/static
COPY --from=build --chown=app:app /app/public ./public
USER app
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -q -O /dev/null http://localhost:3000/login || exit 1
CMD ["node", "server.js"]
