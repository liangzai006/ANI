FROM golang:1.23-alpine AS build

WORKDIR /src
COPY pkg ./pkg
COPY services/reconcile-worker ./services/reconcile-worker

ENV GOWORK=off
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    cd services/reconcile-worker && \
    CGO_ENABLED=0 go build -tags stdjson -ldflags "-s -w" -o /out/reconcile-worker .

FROM scratch

COPY --from=build /out/reconcile-worker /usr/local/bin/reconcile-worker

USER 65532
EXPOSE 9205

ENTRYPOINT ["/usr/local/bin/reconcile-worker"]
