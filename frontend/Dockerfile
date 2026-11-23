# Das Frontend ist plattformunabhängig: immer nativ bauen (unter ARM-Emulation stürzt Node ab)
FROM --platform=$BUILDPLATFORM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
# npm install statt npm ci: neue Pakete aus package.json kommen dazu, auch wenn die Sperrdatei noch älter ist
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
