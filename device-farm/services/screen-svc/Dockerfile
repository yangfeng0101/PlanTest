FROM golang:alpine AS builder

ENV GOTOOLCHAIN=auto

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache git

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o main ./cmd

# Final stage
FROM alpine:3.22

WORKDIR /app

# Install runtime dependencies (Alpine 3.22 has scrcpy 3.2, required for Android 15/16)
RUN apk add --no-cache scrcpy android-tools ffmpeg

# Copy binary from builder
COPY --from=builder /app/main .

# Expose port
EXPOSE 8002

# Run the application
CMD ["./main"]
