FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
RUN npm i -g serve
ENV PORT=${PORT:-80}
EXPOSE 80
CMD ["serve", "-s", "dist", "-l", "$PORT"]
