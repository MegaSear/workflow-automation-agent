FROM node:24-alpine AS builder

WORKDIR /app

COPY src/react_agent/frontend/package.json src/react_agent/frontend/package-lock.json ./
RUN npm ci

COPY src/react_agent/frontend/ ./
RUN npm run build

FROM nginx:1.29-alpine AS runtime

COPY src/react_agent/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]