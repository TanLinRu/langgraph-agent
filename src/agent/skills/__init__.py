SKILLS_INDEX = """
## 可用 Skills

- **code_review**: 代码审查与质量检查
- **data_analysis**: 数据处理与可视化
- **debugging**: 问题诊断与修复
- **refactoring**: 代码重构与优化
- **testing**: 测试编写与执行
- **api_design**: API 设计与文档生成
- **documentation**: 技术文档编写
- **performance_optimization**: 性能分析与优化
- **security_audit**: 安全审计与漏洞检测
- **database_design**: 数据库设计与查询优化
- **cli_dispatch**: 调度编码任务到外部 CLI
- **flow_design**: 流程设计与可视化
- **html_prototype**: HTML 原型生成

使用方式：当你需要执行特定类型任务时，加载对应 Skill。
"""

SKILLS_REGISTRY = {
    "code_review": {
        "name": "code_review",
        "description": "审查代码质量和安全性",
        "use_when": ["审查代码", "检查代码质量", "寻找潜在 bug", "PR review"],
        "dont_use_when": ["只是讨论架构", "编写新代码", "运行测试"],
        "full_content": """你是代码审查专家。审查维度：

1. 代码风格
- 遵循 PEP 8 / 项目规范
- 命名一致性
- 文档完整性

2. 潜在 bug
- 空指针引用
- 资源泄漏
- 边界条件

3. 性能问题
- 算法复杂度
- 重复计算
- 不必要的循环

4. 安全漏洞
- SQL 注入
- XSS
- 认证绕过

输出格式：
## 发现问题
- [严重/中等/轻微] 行号: 问题描述
## 修复建议
- 具体修复方案
## 总体评价
- 通过/需要修改"""
    },
    "data_analysis": {
        "name": "data_analysis",
        "description": "数据清洗、转换、统计与可视化",
        "use_when": ["分析数据", "清洗数据", "生成报告", "CSV 处理"],
        "dont_use_when": ["只是读取文件", "修改配置", "编写代码"],
        "full_content": """你是数据分析专家。工作流程：

1. 数据探索
- 查看数据结构 (head, describe)
- 识别缺失值、异常值
- 确定数据类型

2. 数据清洗
- 处理缺失值 (删除/填充/插值)
- 类型转换
- 异常值处理

3. 数据分析
- 描述性统计
- 分组聚合
- 相关性分析

4. 可视化
- 分布图、趋势图、热力图
- 输出格式: PNG/SVG

5. 结论
- 关键发现
- 业务建议"""
    },
    "debugging": {
        "name": "debugging",
        "description": "问题诊断、调试与修复",
        "use_when": ["程序崩溃", "输出错误", "行为异常", "bug"],
        "dont_use_when": ["只是优化性能", "编写新功能", "代码审查"],
        "full_content": """你是调试专家。诊断流程：

1. 复现问题
- 最小复现步骤
- 环境信息收集

2. 定位根因
- 日志分析
- 堆栈跟踪
- 代码审查

3. 修复验证
- 应用修复
- 验证修复
- 回归测试

输出格式：
## 问题描述
## 根因分析
## 修复方案
## 验证结果"""
    },
    "refactoring": {
        "name": "refactoring",
        "description": "代码重构、结构优化与技术债清理",
        "use_when": ["重构代码", "优化结构", "消除重复", "提取函数", "拆分模块", "技术债"],
        "dont_use_when": ["修复紧急 bug", "添加新功能", "性能调优"],
        "full_content": """你是重构专家。重构原则：

1. 识别代码异味
- 重复代码 (Duplicated Code)
- 过长函数 (Long Method)
- 过大类 (Large Class)
- 过长参数列表 (Long Parameter List)
- 发散式变化 (Divergent Change)

2. 重构策略
- 提取函数/方法 (Extract Method)
- 内联函数 (Inline Method)
- 提取类 (Extract Class)
- 引入参数对象 (Introduce Parameter Object)
- 用多态替换条件 (Replace Conditional with Polymorphism)

3. 重构安全
- 确保有测试覆盖
- 小步重构，频繁提交
- 每次只做一个重构
- 重构后运行测试验证

输出格式：
## 识别的代码异味
- [类型] 位置: 描述
## 重构方案
- 步骤 1: ...
- 步骤 2: ...
## 重构后代码
- 展示关键变更"""
    },
    "testing": {
        "name": "testing",
        "description": "单元测试、集成测试编写与测试覆盖率提升",
        "use_when": ["编写测试", "补充测试", "提高覆盖率", "测试用例", "单元测试", "集成测试"],
        "dont_use_when": ["只是运行测试", "修复 bug", "代码审查"],
        "full_content": """你是测试专家。测试策略：

1. 测试类型
- 单元测试 (Unit Tests): 单个函数/方法的行为
- 集成测试 (Integration Tests): 多个组件协作
- E2E 测试 (End-to-End): 完整用户流程

2. 测试框架选择
- Python: pytest (推荐), unittest
- TypeScript/JS: Jest, Vitest
- Java: JUnit 5

3. 测试编写原则
- AAA 模式: Arrange (准备) → Act (执行) → Assert (断言)
- 每个测试只验证一个行为
- 测试名称描述预期行为
- 使用参数化测试覆盖边界条件
- Mock 外部依赖

4. 覆盖率目标
- 行覆盖率 > 80%
- 分支覆盖率 > 70%
- 关注核心业务逻辑覆盖率

输出格式：
## 测试计划
- 需要测试的功能点
## 测试代码
- 完整的测试文件
## 覆盖率报告
- 当前覆盖率 vs 目标"""
    },
    "api_design": {
        "name": "api_design",
        "description": "RESTful API 设计、OpenAPI 文档生成与最佳实践",
        "use_when": ["设计 API", "生成 OpenAPI", "API 文档", "接口设计", "REST"],
        "dont_use_when": ["实现 API 逻辑", "调试 API", "数据库设计"],
        "full_content": """你是 API 设计专家。设计原则：

1. RESTful 设计
- 资源导向的 URL 设计 (/users, /users/{id}/orders)
- 正确的 HTTP 方法 (GET/POST/PUT/PATCH/DELETE)
- 标准状态码 (200/201/400/401/403/404/500)
- 版本控制策略 (/v1/users 或 Header)

2. 请求/响应设计
- 统一的错误响应格式
- 分页 (offset/limit 或 cursor)
- 过滤、排序、字段选择
- 请求/响应示例

3. OpenAPI/Swagger 规范
- 完整的 operationId
- 详细的 description
- schema 定义与引用
- 安全方案定义

4. 最佳实践
- 幂等性设计
- 速率限制
- 认证与授权 (OAuth2, JWT, API Key)
- 缓存策略 (ETag, Cache-Control)

输出格式：
## API 设计
- 端点列表及说明
## OpenAPI Spec
- YAML/JSON 规范
## 使用示例
- curl / SDK 示例"""
    },
    "documentation": {
        "name": "documentation",
        "description": "技术文档编写、README、API 文档、架构文档",
        "use_when": ["写文档", "README", "技术文档", "架构文档", "注释代码"],
        "dont_use_when": ["编写代码逻辑", "调试", "代码审查"],
        "full_content": """你是技术文档专家。文档类型：

1. README 文档
- 项目简介
- 快速开始 (Quick Start)
- 安装步骤
- 使用示例
- 贡献指南
- License

2. API 文档
- 端点描述
- 请求/响应示例
- 错误码说明
- 认证方式

3. 架构文档
- 系统概述
- 架构图 (组件关系)
- 数据流
- 技术栈说明
- 部署架构

4. 代码注释
- 函数/类 docstring
- 复杂逻辑注释
- TODO/FIXME 标记

文档写作原则：
- 面向读者 (开发者/用户/运维)
- 简洁明确
- 示例驱动
- 保持更新

输出格式：
## 文档类型
## 文档内容
- Markdown 格式
## 建议改进
- 缺失内容建议"""
    },
    "performance_optimization": {
        "name": "performance_optimization",
        "description": "性能分析、瓶颈识别、优化建议与基准测试",
        "use_when": ["性能优化", "速度慢", "性能分析", "基准测试", "profiling", "优化"],
        "dont_use_when": ["功能开发", "代码审查", "bug 修复"],
        "full_content": """你是性能优化专家。优化流程：

1. 性能分析 (Profiling)
- 使用工具: cProfile, line_profiler, py-spy (Python)
- 火焰图 (Flame Graph) 分析
- 识别 CPU/内存/IO 瓶颈

2. 常见优化策略
- 算法优化 (O(n²) → O(n log n))
- 缓存 (LRU, Redis, 内存缓存)
- 批量操作代替循环
- 异步/并发处理
- 数据库查询优化 (索引, 分页)
- 延迟加载

3. 内存优化
- 对象池/复用
- 生成器代替列表
- 弱引用
- 内存泄漏检测

4. 基准测试
- 建立基线 (Baseline)
- 前后对比
- 统计学显著性检验
- 自动化基准测试

输出格式：
## 性能分析结果
- 瓶颈位置及数据
## 优化方案
- 方案 1: 描述, 预期提升
- 方案 2: 描述, 预期提升
## 基准测试结果
- Before vs After"""
    },
    "security_audit": {
        "name": "security_audit",
        "description": "安全审计、漏洞扫描、OWASP Top 10 检查",
        "use_when": ["安全检查", "漏洞扫描", "安全审计", "OWASP", "渗透测试"],
        "dont_use_when": ["功能开发", "性能优化", "代码审查 (非安全维度)"],
        "full_content": """你是安全审计专家。检查维度：

1. OWASP Top 10 (2021)
- A01: 访问控制失效 (Broken Access Control)
- A02: 加密机制失效 (Cryptographic Failures)
- A03: 注入 (Injection) - SQL, NoSQL, OS, LDAP
- A04: 不安全设计 (Insecure Design)
- A05: 安全配置错误 (Security Misconfiguration)
- A06: 组件漏洞 (Vulnerable Components)
- A07: 认证与识别失败 (Authentication Failures)
- A08: 软件与数据完整性故障
- A09: 安全日志与监控不足
- A10: 服务端请求伪造 (SSRF)

2. 输入验证
- 白名单验证
- 参数化查询
- 输出编码

3. 认证与授权
- 密码策略
- Token 管理
- 权限模型 (RBAC/ABAC)
- 会话管理

4. 数据保护
- 传输加密 (TLS)
- 静态加密
- 敏感数据脱敏
- 密钥管理

5. 依赖安全
- 已知 CVE 检查
- 依赖版本更新
- SBOM 生成

输出格式：
## 发现的漏洞
- [严重/高/中/低] 位置: 描述, 修复建议
## 安全建议
- 优先级排序
## 合规检查
- 是否符合标准"""
    },
    "database_design": {
        "name": "database_design",
        "description": "数据库设计、SQL 优化、索引策略、迁移方案",
        "use_when": ["数据库设计", "SQL 优化", "索引设计", "表结构设计", "迁移"],
        "dont_use_when": ["查询数据", "应用逻辑开发", "缓存策略"],
        "full_content": """你是数据库设计专家。设计原则：

1. 表结构设计
- 范式化 vs 反范式化
- 主键策略 (UUID, Snowflake, 自增)
- 数据类型选择
- 外键约束

2. 索引策略
- B-Tree, Hash, GIN, GiST
- 复合索引与最左前缀
- 覆盖索引
- 避免过度索引

3. 查询优化
- EXPLAIN 分析
- 避免 N+1 查询
- 分页优化 (游标 vs OFFSET)
- 子查询 vs JOIN

4. 迁移管理
- 向前兼容
- 回滚策略
- 零停机迁移
- 数据迁移验证

5. 最佳实践
- 软删除 vs 硬删除
- 审计字段 (created_at, updated_at)
- 连接池配置
- 备份策略

输出格式：
## ER 图
- 表结构及关系
## DDL 语句
- CREATE TABLE 语句
## 索引建议
- 索引列表及理由
## 迁移方案
- 步骤及回滚策略"""
    },
    "cli_dispatch": {
        "name": "cli_dispatch",
        "description": "调度复杂编码任务到外部 Coding CLI (opencode/claude)",
        "use_when": ["调度到 CLI", "外部编码代理", "复杂重构", "多文件修改", "新功能开发", "大规模编码"],
        "dont_use_when": ["简单文件读写", "单文件修改", "运行脚本", "数据查询"],
        "full_content": """你是任务调度专家。当你需要执行以下任务时，使用 dispatch_to_cli 工具：

1. 何时调度
- 大规模代码重构（涉及多个文件/模块）
- 新功能开发（需要完整的编码能力）
- 复杂的代码审查和修复
- 需要深度理解代码库的任务

2. 调度参数
- task: 详细任务描述，包含上下文和要求
- cli_name: "opencode"（首选）或 "claude"
- working_dir: 项目根目录
- mode: "run"（默认，同步等待结果）
- timeout: 默认 600 秒

3. 任务描述编写
- 提供充分的上下文信息
- 指定需要修改的文件
- 明确期望的输出
- 包含约束和注意事项

4. 任务完成后
- 检查返回结果
- 确认文件变更
- 如有问题，可再次调度修正

示例任务描述：
"在 src/agent/tools/__init__.py 中添加一个新工具函数，该函数需要：
1. 接收文件路径列表作为输入
2. 统计每个文件的行数
3. 返回 JSON 格式的结果
请遵循现有的代码风格和规范。"

可用 CLI：
- opencode: 支持 run 和 serve 模式，功能最全面
- claude: 支持 run 模式，适合快速编码任务"""
    },
}


def get_skill(name: str) -> dict | None:
    """获取 Skill"""
    return SKILLS_REGISTRY.get(name)


def get_skill_content(name: str) -> str:
    """获取 Skill 完整内容"""
    skill = get_skill(name)
    return skill["full_content"] if skill else ""


def should_load_skill(task: str, skill_name: str) -> bool:
    """判断是否需要加载 Skill"""
    skill = get_skill(skill_name)
    if not skill:
        return False

    for keyword in skill["use_when"]:
        if keyword.lower() in task.lower():
            return True
    return False


__all__ = [
    "SKILLS_INDEX",
    "SKILLS_REGISTRY",
    "get_skill",
    "get_skill_content",
    "should_load_skill",
]


SKILLS_REGISTRY["flow_design"] = {
    "name": "flow_design",
    "description": "业务流程设计与可视化",
    "use_when": ["设计流程", "绘制流程图", "梳理业务逻辑", "PRD flow"],
    "dont_use_when": ["只是写代码", "调试问题"],
    "full_content": """你是流程设计专家。基于 PRD 生成用户流程图。

分析维度：
1. 用户角色 - 谁在使用系统
2. 核心流程 - 主要业务流程
3. 分支逻辑 - 条件分支
4. 异常处理 - 错误流程

输出格式：
## 流程节点
- 节点名称
- 节点类型（开始/结束/操作/判断）
- 参与者

## 流程路径
- 主路径
- 备选路径
- 异常路径

使用 Mermaid 语法生成流程图。
""",
}

SKILLS_REGISTRY["html_prototype"] = {
    "name": "html_prototype",
    "description": "HTML 原型生成",
    "use_when": ["生成 HTML", "原型设计", "UI _mockup", "PRD prototype"],
    "dont_use_when": ["只是讨论需求", "后端开发"],
    "full_content": """你是 HTML 原型生成专家。基于 PRD 和流程图生成可编辑的 HTML 原型。

要求：
1. 使用 Tailwind CSS 进行样式
2. 响应式布局
3. 交互效果（hover, focus, active）
4. 可编辑的表单元素

输出：
- 单文件 HTML
- 内联 CSS
- 基础 JavaScript 交互

禁止：
- 外部依赖（除 Tailwind CDN）
- 服务器端代码
- 数据库操作
""",
}