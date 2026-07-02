FROM golang:1.23-alpine AS build

WORKDIR /src
COPY pkg ./pkg
COPY services/model-service ./services/model-service

ENV GOWORK=off
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    cd services/model-service && \
    CGO_ENABLED=0 go build -tags stdjson -ldflags "-s -w" -o /out/model-service .

FROM scratch

COPY --from=build /out/model-service /usr/local/bin/model-service

USER 65532
EXPOSE 9103 9203

ENTRYPOINT ["/usr/local/bin/model-service"]
