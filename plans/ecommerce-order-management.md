# 电商订单管理系统 - 后端实现计划

## 项目概述

构建一个完整的电商订单管理系统后端 API，包含订单管理、商品管理、用户管理、库存管理、支付处理等核心功能。

## 技术栈

- **框架**: FastAPI (与当前项目一致)
- **ORM**: SQLAlchemy 2.0
- **数据库**: PostgreSQL (开发环境可用 SQLite)
- **认证**: JWT (python-jose)
- **验证**: Pydantic v2
- **测试**: pytest + pytest-asyncio

---

## 步骤 1: 项目结构初始化

**目标**: 创建基础项目结构和依赖配置

### 任务清单

1. 创建项目目录结构 `src/ecommerce/`
   - `__init__.py`
   - `main.py` - FastAPI 应用入口
   - `config.py` - 配置管理
   - `models/` - 数据模型
   - `schemas/` - Pydantic schemas
   - `routers/` - API 路由
   - `services/` - 业务逻辑
   - `utils/` - 工具函数
   - `tests/` - 测试文件

2. 创建 `pyproject.toml` 或更新现有配置

3. 创建 `.env.example` 包含数据库连接等配置

**验证命令**

```bash
python -c "from src.ecommerce.main import app; print('App loaded')"
```

**退出标准**: 项目结构创建完成，依赖可安装

---

## 步骤 2: 数据库模型定义

**目标**: 定义所有数据表模型

### 任务清单

1. **用户模型** (`models/user.py`)
   - id, username, email, password_hash
   - role (customer, admin)
   - created_at, updated_at, is_active

2. **商品模型** (`models/product.py`)
   - id, name, description, price
   - category_id, sku, stock_quantity
   - images (JSON), is_active
   - created_at, updated_at

3. **分类模型** (`models/category.py`)
   - id, name, parent_id (自关联)
   - description

4. **订单模型** (`models/order.py`)
   - id, user_id, order_number
   - status (pending, paid, shipped, delivered, cancelled, refunded)
   - total_amount, shipping_address (JSON)
   - payment_method, payment_status
   - created_at, updated_at

5. **订单项模型** (`models/order_item.py`)
   - id, order_id, product_id
   - quantity, unit_price, subtotal

6. **库存模型** (`models/inventory.py`)
   - id, product_id, warehouse_location
   - quantity, reserved_quantity
   - last_updated

7. **支付模型** (`models/payment.py`)
   - id, order_id, amount
   - method, status, transaction_id
   - created_at, updated_at

8. **创建 Base 类和 Alembic 迁移配置** (`models/base.py`)

**验证命令**

```bash
python -c "from src.ecommerce.models import User, Product, Order, OrderItem, Category, Inventory, Payment; print('All models imported')"
```

**退出标准**: 所有模型可导入，无循环依赖

---

## 步骤 3: Pydantic Schemas

**目标**: 定义 API 请求/响应数据模型

### 任务清单

1. **用户 Schema** (`schemas/user.py`)
   - UserCreate, UserUpdate, UserResponse
   - UserLogin (用于认证)

2. **商品 Schema** (`schemas/product.py`)
   - ProductCreate, ProductUpdate, ProductResponse
   - ProductListResponse (分页)

3. **分类 Schema** (`schemas/category.py`)
   - CategoryCreate, CategoryResponse

4. **订单 Schema** (`schemas/order.py`)
   - OrderCreate, OrderUpdate, OrderResponse
   - OrderItemResponse
   - OrderStatusUpdate

5. **库存 Schema** (`schemas/inventory.py`)
   - InventoryUpdate, InventoryResponse

6. **支付 Schema** (`schemas/payment.py`)
   - PaymentCreate, PaymentResponse

**验证命令**

```bash
python -c "from src.ecommerce.schemas import UserCreate, ProductCreate, OrderCreate; print('Schemas imported')"
```

**退出标准**: 所有 Schema 可导入，类型正确

---

## 步骤 4: 数据库工具和依赖

**目标**: 创建数据库连接和会话管理

### 任务清单

1. 创建 `utils/database.py`
   - create_engine, create_sessionmaker
   - get_db() 依赖注入函数
   - init_db() 初始化函数

2. 创建 `utils/security.py`
   - hash_password(), verify_password()
   - create_access_token(), decode_token()
   - get_current_user() 依赖

3. 更新配置 `config.py`
   - DATABASE_URL
   - SECRET_KEY, ALGORITHM
   - ACCESS_TOKEN_EXPIRE_MINUTES

**验证命令**

```bash
python -c "from src.ecommerce.utils.database import get_db; from src.ecommerce.utils.security import get_current_user; print('Utils imported')"
```

**退出标准**: 数据库连接可建立，认证功能可用

---

## 步骤 5: 用户认证 API

**目标**: 实现用户注册、登录、认证

### 任务清单

1. 创建 `routers/auth.py`
   - POST `/auth/register` - 用户注册
   - POST `/auth/login` - 用户登录，返回 JWT
   - POST `/auth/refresh` - 刷新 token

2. 创建 `routers/users.py`
   - GET `/users/me` - 获取当前用户信息
   - PUT `/users/me` - 更新当前用户信息
   - GET `/users/{user_id}` - 管理员获取用户详情

3. 实现 JWT 认证依赖

**验证命令**

```bash
# 启动服务器后测试
curl -X POST http://localhost:8000/auth/register -H "Content-Type: application/json" -d '{"username":"test","email":"test@example.com","password":"password123"}'
```

**退出标准**: 注册、登录、认证功能正常

---

## 步骤 6: 商品管理 API

**目标**: 实现商品 CRUD 操作

### 任务清单

1. 创建 `routers/products.py`
   - POST `/products` - 创建商品 (Admin)
   - GET `/products` - 列表查询 (支持分页、筛选)
   - GET `/products/{product_id}` - 获取详情
   - PUT `/products/{product_id}` - 更新商品 (Admin)
   - DELETE `/products/{product_id}` - 删除商品 (Admin)
   - GET `/products/{product_id}/inventory` - 获取库存

2. 创建 `routers/categories.py`
   - POST `/categories` - 创建分类
   - GET `/categories` - 分类树形列表
   - GET `/categories/{category_id}` - 获取分类及子分类
   - PUT `/categories/{category_id}` - 更新分类
   - DELETE `/categories/{category_id}` - 删除分类

**验证命令**

```bash
# 获取商品列表
curl -X GET http://localhost:8000/products
```

**退出标准**: 商品和分类的 CRUD 功能正常

---

## 步骤 7: 订单管理 API

**目标**: 实现订单创建、查询、更新

### 任务清单

1. 创建 `routers/orders.py`
   - POST `/orders` - 创建订单 (从购物车)
   - GET `/orders` - 用户订单列表
   - GET `/orders/{order_id}` - 获取订单详情
   - PUT `/orders/{order_id}/status` - 更新订单状态 (Admin)
   - PUT `/orders/{order_id}/cancel` - 取消订单
   - GET `/orders/{order_id}/items` - 获取订单项列表

2. 订单状态流转逻辑
   - pending → paid → shipped → delivered
   - 任意状态 → cancelled (退款)
   - delivered → refunded

3. 订单历史记录 (`models/order_history.py`)
   - id, order_id, old_status, new_status
   - changed_by, reason, created_at

**验证命令**

```bash
# 创建订单
curl -X POST http://localhost:8000/orders -H "Authorization: Bearer <token>" -d '{"items":[{"product_id":1,"quantity":2}]}'
```

**退出标准**: 订单创建、查询、状态更新正常

---

## 步骤 8: 库存管理 API

**目标**: 实现库存管理和锁定

### 任务清单

1. 创建 `routers/inventory.py`
   - GET `/inventory` - 库存列表
   - GET `/inventory/{product_id}` - 获取商品库存
   - POST `/inventory/adjust` - 调整库存 (Admin)
   - POST `/inventory/reserve` - 预留库存 (下单时)
   - POST `/inventory/release` - 释放预留

2. 实现库存检查和锁定逻辑
   - 下单时检查库存是否充足
   - 支付成功后锁定库存
   - 取消订单时释放预留

**验证命令**

```bash
# 检查库存
curl -X GET http://localhost:8000/inventory/1 -H "Authorization: Bearer <token>"
```

**退出标准**: 库存查询、预留、释放功能正常

---

## 步骤 9: 支付处理 API

**目标**: 实现支付接口和回调

### 任务清单

1. 创建 `routers/payments.py`
   - POST `/payments` - 创建支付订单
   - GET `/payments/{payment_id}` - 获取支付状态
   - POST `/payments/{payment_id}/callback` - 支付回调
   - POST `/payments/{payment_id}/refund` - 退款 (Admin)

2. 支付状态流转
   - pending → processing → completed / failed

3. 模拟支付网关实现 (可在 `services/payment_service.py`)

**验证命令**

```bash
# 创建支付
curl -X POST http://localhost:8000/payments -H "Authorization: Bearer <token>" -d '{"order_id":1,"amount":100,"method":"alipay"}'
```

**退出标准**: 支付创建、状态更新、回调处理正常

---

## 步骤 10: 业务服务层

**目标**: 封装核心业务逻辑

### 任务清单

1. 创建 `services/order_service.py`
   - create_order_from_cart()
   - calculate_order_total()
   - validate_inventory()
   - process_payment_and_update_order()

2. 创建 `services/inventory_service.py`
   - check_and_reserve_stock()
   - release_stock()
   - adjust_stock()

3. 创建 `services/cart_service.py`
   - add_to_cart()
   - remove_from_cart()
   - get_cart()
   - checkout()

**验证命令**

```python
# 测试订单创建逻辑
from src.ecommerce.services.order_service import OrderService
```

**退出标准**: 业务逻辑封装完成，单元测试通过

---

## 步骤 11: 错误处理和日志

**目标**: 统一错误处理和日志记录

### 任务清单

1. 创建 `utils/exceptions.py`
   - Custom exceptions (NotFoundError, ValidationError, etc.)
   - Exception handlers in `main.py`

2. 配置日志 (`utils/logger.py`)
   - Request/Response logging
   - Error logging

3. 更新 `main.py`
   - 添加全局异常处理器
   - 配置 CORS 中间件

**验证命令**

```bash
# 测试 404 错误
curl -X GET http://localhost:8000/products/99999
```

**退出标准**: 错误返回统一格式，日志正常记录

---

## 步骤 12: 单元测试

**目标**: 编写核心功能测试

### 任务清单

1. 创建 `tests/conftest.py`
   - 测试数据库 fixture
   - 测试客户端 fixture

2. 编写测试文件
   - `tests/test_auth.py` - 认证测试
   - `tests/test_products.py` - 商品测试
   - `tests/test_orders.py` - 订单测试
   - `tests/test_inventory.py` - 库存测试

3. 配置 `pytest.ini` 或 `pyproject.toml` 中的 pytest 配置

**验证命令**

```bash
pytest tests/ -v
```

**退出标准**: 核心测试通过，覆盖关键业务逻辑

---

## 步骤 13: API 文档和部署配置

**目标**: 完善文档和准备部署

### 任务清单

1. 更新 FastAPI 自动生成的 OpenAPI 文档
   - 添加标签、描述
   - 配置 response 模型

2. 创建 `docker-compose.yml` 用于部署

3. 创建 `alembic.ini` 数据库迁移配置

4. 编写 README.md 包含:
   - 快速开始指南
   - API 端点列表
   - 环境变量说明

**验证命令**

```bash
# 访问 API 文档
# http://localhost:8000/docs
# http://localhost:8000/redoc
```

**退出标准**: API 文档完整，Docker Compose 可运行

---

## 依赖关系图

```
步骤 1 (项目结构)
    ↓
步骤 2 (数据库模型) ← 步骤 3 (Schemas) 平行
    ↓                     ↓
步骤 4 (工具和依赖) ← 步骤 5 (认证 API)
    ↓                     ↓
步骤 6 (商品 API) → 步骤 7 (订单 API)
    ↓                     ↓
步骤 8 (库存 API) ← 步骤 9 (支付 API)
    ↓
步骤 10 (业务服务层) ← 步骤 11 (错误处理)
    ↓
步骤 12 (单元测试) ← 步骤 13 (文档部署)
```

---

## 并行执行提示

以下步骤可以并行执行（无依赖冲突）：
- 步骤 6 (商品 API) + 步骤 7 (订单 API)
- 步骤 8 (库存 API) + 步骤 9 (支付 API)
- 步骤 3 (Schemas) 可在任何步骤前独立完成

---

## 验证命令汇总

```bash
# 安装依赖
pip install -e ".[ecommerce]"

# 启动开发服务器
uvicorn src.ecommerce.main:app --reload

# 运行测试
pytest tests/ -v

# 检查类型
mypy src/ecommerce/ --strict

# 代码检查
ruff check src/ecommerce/ --fix
```