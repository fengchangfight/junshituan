# ── Stage 1: Build ─────────────────────────────────────────────────
FROM node:20-alpine AS builder

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

# Tier 1: dependencies (cached unless package*.json changes)
COPY package.json package-lock.json ./
RUN npm ci

# Tier 2: source code + build (frequently changes)
COPY . .
RUN npm run build

# ── Stage 2: Production runtime ─────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Only production deps (no tailwind/postcss/typescript)
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/next.config.js .
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next

EXPOSE 3000

CMD ["npx", "next", "start", "-p", "3000"]
