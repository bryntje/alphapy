FROM node:20-alpine AS base
RUN apk add --no-cache libc6-compat
ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN corepack enable && corepack prepare pnpm@10.19.0 --activate

# === DEPS ===
FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# === BUILD ===
FROM base AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# Kopieer node_modules
COPY --from=deps /app/node_modules ./node_modules

# Kopieer Next.js essentials van root (standaard setup)
COPY package.json ./
COPY tsconfig.json ./
COPY next.config.ts ./
COPY app ./app
COPY public ./public

# Nu ziet Next.js app/ of pages/ in /app
RUN pnpm run build

# === RUNNER ===
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8080

COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static

EXPOSE 8080
CMD ["node", "server.js"]