FROM node:20-alpine AS base

RUN apk add --no-cache libc6-compat
ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN corepack enable && corepack prepare pnpm@10.19.0 --activate

FROM base AS deps
WORKDIR /app
COPY shared/package.json shared/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
# Copy Next.js app contents from shared/ directory
COPY shared/app ./app
COPY shared/components ./components
COPY shared/lib ./lib
COPY shared/public ./public
COPY shared/styles ./styles
COPY shared/types ./types
COPY shared/next.config.ts ./
COPY shared/postcss.config.js ./
COPY shared/tailwind.config.ts ./
COPY shared/tsconfig.json ./
RUN pnpm run build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8080

COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static

EXPOSE 8080
CMD ["node", "server.js"]
