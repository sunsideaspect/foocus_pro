FROM node:22-alpine

WORKDIR /workspace

COPY package.json /workspace/package.json
COPY apps/web/package.json /workspace/apps/web/package.json
COPY packages/shared/package.json /workspace/packages/shared/package.json
RUN npm install

COPY apps/web /workspace/apps/web
COPY packages/shared /workspace/packages/shared

WORKDIR /workspace/apps/web
CMD ["npm", "run", "dev"]
