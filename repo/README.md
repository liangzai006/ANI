# KuberCloud ANI — Monorepo

广州常青云科技有限公司 | AI 专有云平台

## 当前状态

```text
当前阶段：Phase 1 / Sprint 2
当前优先级：SPEC-CORE-ALPHA → M1-INSTANCE-U → M1-INSTANCE-V
当前执行入口：CURRENT-SPRINT.md
全局计划入口：../ANI-06-开发计划.md
文档导航：../ANI-DOCS-INDEX.md
```

## 代码仓库结构

```
repo/
├── services/                   # Go 微服务（平台层）
│   ├── ani-gateway/            # 统一 Web Server 层（Hertz + gRPC-Gateway）
│   ├── model-service/          # 模型管理服务（仓库/加解密/导入）
│   ├── kb-service/             # 知识库管理服务
│   ├── auth-service/           # 认证授权服务（JWT/RBAC）
│   └── metering-service/       # 计量采集服务
│
├── ai/                         # Python AI 应用层
│   ├── rag-engine/             # RAG 引擎（LangChain + Milvus）
│   ├── doc-parser/             # 文档解析服务（Docling + PaddleOCR）
│   └── whisper-service/        # 语音转写服务（Faster-Whisper）
│
├── operators/                  # Go K8s Operator
│   ├── inference-operator/     # InferenceService CRD Controller
│   └── upgrade-operator/       # ANIPatch CRD Controller（在线升级）
│
├── frontends/                  # TypeScript 前端（Monorepo）
│   ├── console/                # 用户控制台（React 18 + TDesign）
│   └── boss/                   # 运营运维后台（React 18 + TDesign）
│
├── cli/ani/                    # Go CLI 工具（cobra + viper）
├── installer/ani-installer/    # Go 安装程序（bubbletea TUI）
│
├── api/
│   ├── openapi/                # API 契约（v1.yaml 为 Core 唯一真实来源）
│   └── proto/                  # Protobuf 定义（内部 gRPC）
│
├── deploy/
│   ├── helm/                   # ANI 平台 Helm Charts
│   └── docker/                 # docker-compose 本地开发环境
│
├── scripts/                    # 构建、发布、维护脚本
├── Makefile                    # 统一构建入口
├── .github/workflows/          # CI/CD 流水线
└── .env.example                # 环境变量模板
```

## 快速开始

```bash
# 进入仓库后先做基础验证
make build
make test
make validate-architecture

# 当前冲刺任务和更细的启动方式见 CURRENT-SPRINT.md
```

详见：[本地开发环境搭建指南](deploy/docker/README.md)

## 文档

产品规划文档位于 `../`（父目录）。新开发者或 AI 工具不要从头顺读所有文档，推荐顺序：

1. `../ANI-DOCS-INDEX.md`
2. `../CLAUDE.md`
3. `CURRENT-SPRINT.md`
4. `../ANI-06-开发计划.md` Section 零和当前 Sprint
5. `api/openapi/v1.yaml`

版本管理：
- 策略文档：`../ANI-12-版本管理策略.md`
- 当前阶段：`v0.x` 开发期
- 首个正式版本目标：`v1.0.0`，2026-09-30
- 发布前至少执行：`make gen-proto && make test && make build`
