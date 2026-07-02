FROM golang:1.23-alpine AS build

WORKDIR /src
COPY pkg ./pkg
COPY services/task-service ./services/task-service

ENV GOWORK=off
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    cd services/task-service && \
    CGO_ENABLED=0 go build -tags stdjson -ldflags "-s -w" -o /out/task-service .

FROM scratch

COPY --from=build /out/task-service /usr/local/bin/task-service

USER 65532
EXPOSE 9104 9204

ENTRYPOINT ["/usr/local/bin/task-service"]
