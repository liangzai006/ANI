# GATEWAY-METADATA-PERSISTENCE-P6-A3

> 记录类型：Feature batch / Core Gateway metadata persistence（阶段 A · A3）
> 完成日期：2026-06-30
> 范围：ANI Core / branding OpenAPI 补齐 + logo 上传 MinIO + URL 写 PG

## 目标

补齐 Core OpenAPI `PUT /branding` requestBody 与 `POST /branding/logo`（multipart）；logo 文件写入对象存储 branding bucket，公开 URL 回写 `platform_branding`（经既有 `MetadataBrandingService`）。无 object store 配置时 upload 返回 503（`ErrNotConfigured`）。

## 实现

- OpenAPI：`PlatformBranding`、`BrandingUpdateRequest`、`BrandingLogoUploadResponse`；`PUT /branding`、`POST /branding/logo`。
- `ports.BrandingLogoUploadRequest` + `BrandingService.UploadBrandingLogo`。
- `ObjectStoreBrandingService`：EnsureBucket + PutObject + UpdateBranding；key 形如 `logos/{variant}-{uuid}.ext`；tenant=`platform`。
- `MinIOObjectStore.PublicObjectURL`；gateway `newGatewayBrandingService(metadata, objectStore)` 接线。
- Router multipart：`variant` + `file`。
- 新增 `make validate-gateway-metadata-p6-a3`；聚合 gate 扩展含 P6-A3。

## 覆盖范围

| 能力 | PG 元数据 | MinIO 对象 | 无配置行为 |
|------|-----------|------------|------------|
| PUT /branding | ✅（P4 已有） | — | 内存 fallback |
| POST /branding/logo | ✅ URL 字段 | ✅ logo 文件 | upload 503 |

## 验收

```bash
cd repo
make validate-gateway-metadata-p6-a3
make validate-gateway-metadata
```

## 边界

- 需 `OBJECT_STORE_PROVIDER=minio` 及 MinIO 环境变量方可实际上传；local profile 无 MinIO 时不标 production ready。
- 不持久化 logo 二进制到 PostgreSQL。
