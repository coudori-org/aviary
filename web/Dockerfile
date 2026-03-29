FROM node:22-slim

WORKDIR /app

# Install deps (cached layer — only re-runs when package.json changes)
COPY package.json package-lock.json* /app/
RUN npm install

# Copy application code (overridden by volume mount in dev)
COPY . /app/

EXPOSE 3000

CMD ["npm", "run", "dev"]
