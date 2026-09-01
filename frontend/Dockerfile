FROM node:20-alpine

RUN apk add --no-cache wget

WORKDIR /workspace

COPY package*.json ./
RUN npm install

COPY . .

RUN sh lint_no_ai_punctuation.sh

# Public client values only. These ARGs are baked into the Next.js client bundle
# at build time. Never pass privileged backend keys as image build arguments.
ARG NEXT_PUBLIC_SUPABASE_URL=
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY=
ARG NEXT_PUBLIC_API_BASE=/api/v1
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
ENV NODE_ENV=production
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
