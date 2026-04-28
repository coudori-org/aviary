FROM node:22-slim AS base
WORKDIR /app
ARG NPM_CONFIG_REGISTRY
COPY package.json package-lock.json /app/
RUN npm ci
COPY . /app/
EXPOSE 3000

# Dev target: bind-mounted source + next dev server (see docker-compose.override.yml).
FROM base AS dev
CMD ["npm", "run", "dev"]

# Prod target: bake a full production build. INTERNAL_API_URL is baked into
# routes-manifest.json by next.config.ts's rewrites(), so it must be supplied
# at build time. Browser-side URLs are derived from window.location at runtime.
FROM base AS runner
ARG INTERNAL_API_URL=http://api:8000
ENV INTERNAL_API_URL=$INTERNAL_API_URL \
    NODE_ENV=production
RUN npm run build
CMD ["npm", "run", "start"]
