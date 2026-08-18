FROM node:20-alpine
WORKDIR /workspace
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
