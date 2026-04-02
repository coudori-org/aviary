FROM node:22-slim

WORKDIR /app

# Install deps from lock file (cached layer — only reruns on manifest/lock change)
ARG NPM_CONFIG_REGISTRY
COPY package.json package-lock.json /app/
RUN npm ci

# Copy application code (overridden by volume mount in dev)
COPY . /app/

EXPOSE 3000

CMD ["npm", "run", "dev"]
