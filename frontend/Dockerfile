FROM node:20-alpine

WORKDIR /app/frontend

# Install JS dependencies once at build time (cached layer).
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --include=dev

COPY frontend/ ./

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
