FROM node:22-slim

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install

# Copy project code
COPY . .

EXPOSE 5173

# Start Vite development server bound to all interfaces
CMD ["npm", "run", "dev", "--", "--host"]
