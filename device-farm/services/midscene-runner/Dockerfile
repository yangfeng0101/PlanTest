FROM node:22-bookworm-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    android-tools-adb \
    ca-certificates \
    curl \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY midscene-runner/package*.json ./
RUN npm install --omit=dev

COPY midscene-runner/src ./src

ENV NODE_ENV=production
EXPOSE 8005

CMD ["npm", "start"]
