# 企业级开发实战指南

> 基于 Python + Node.js + Vue 的初学者入门路径，**贯穿 OOP 思想设计**

## 目录

1. [技术栈概览](#1-技术栈概览)
2. [Python 核心概念](#2-python-核心概念)
   - 2.1 基础语法（含 OOP）
   - 2.2 环境管理
   - 2.3 类型提示（企业级必需）
   - 2.4 异步编程
   - 2.5 企业级框架
   - 2.6 常用库
3. [Node.js 企业应用](#3-nodejs-企业应用)
   - 3.1 包管理
   - 3.2 TypeScript 基础语法（含 OOP）
   - 3.3 TypeScript 配置
   - 3.4 异步模式
   - 3.5 Vite 构建配置
   - 3.6 常用企业库
4. [Vue 3 现代前端](#4-vue-3-现代前端)
   - 4.1 项目结构
   - 4.2 模板语法详解
   - 4.3 响应式原理（OOP 状态封装）
   - 4.4 组件生命周期（对象生命周期）
   - 4.5 组件通信模式（OOP 协作）
   - 4.6 组件设计原则（SOLID）
   - 4.7 组合式 API
   - 4.8 路由守卫
   - 4.9 状态管理
   - 4.10 API 调用
5. [实战项目架构](#5-实战项目架构)
6. [企业级最佳实践](#6-企业级最佳实践)
7. [企业级代码规范 Spec](#7-企业级代码规范-spec)
   - 7.1 文件命名约定
   - 7.2 目录结构标准
   - 7.3 OOP 设计原则（SOLID）
   - 7.4 设计模式简要说明
   - 7.5 代码注释规范
   - 7.6 Git 提交规范
8. [业内基础框架模板](#8-业内基础框架模板)
   - 8.1 Python 框架模板（FastAPI - 依赖注入 OOP）
   - 8.2 Node.js 框架模板（NestJS - 完整模块化 OOP）
   - 8.3 Vue 3 框架模板（组件化 OOP）
9. [学习路径](#9-学习路径)
10. [快速参考](#10-快速参考)

---

## 1. 技术栈概览

### 1.1 各技术定位

| 技术 | 定位 | 企业用途 | 学习优先级 |
|------|------|----------|------------|
| **Python** | 后端 API / AI / 数据处理 | FastAPI, Django, LangChain, 数据分析 | ⭐⭐⭐⭐⭐ |
| **Node.js** | 后端 / 构建工具 / SSR | Express, NestJS, Vite, 全栈开发 | ⭐⭐⭐⭐ |
| **Vue 3** | 前端框架 | 响应式 UI, 组件化开发 | ⭐⭐⭐⭐⭐ |

### 1.2 典型企业架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Vue 3)                     │
│  components → composables → stores → router              │
└────────────────────────┬────────────────────────────────┘
                       │ HTTP/WebSocket
┌──────────────────────▼────────────────────────────────┐
│                  Backend (Python/Node.js)                  │
│  FastAPI/Express → Services → Models → Database        │
└────────────────────────┬────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────┐
│                   Database / Cache                     │
│  PostgreSQL → Redis → ChromaDB (向量)               │
└─────────────────────────────────────────────────────┘
```

### 1.3 OOP 思想贯穿

> **核心观点**：一切皆对象
- **Python**：类（Class）是组织代码的基本单位
- **TypeScript**：接口（Interface）+ 类（Class）构建企业级应用
- **Vue 3**：组件（Component）= 可复用的对象

---

## 2. Python 核心概念

### 2.1 基础语法（含 OOP）

#### 2.1.1 变量与数据类型

```python
# 基础类型注解
age: int = 25
name: str = "Alice"
price: float = 19.99
is_active: bool = True

# 容器类型
scores: list[int] = [1, 2, 3]              # Python 3.9+
user: dict[str, str] = {"name": "Alice"}     # Python 3.9+
unique_ids: set[int] = {1, 2, 3}
point: tuple[int, int] = (10, 20)

# 或使用 typing（兼容旧版本）
from typing import List, Dict, Set, Tuple, Union, Optional

scores: List[int] = [1, 2, 3]
user: Dict[str, str] = {"name": "Alice"}
user_id: Optional[int] = None  # = int | None (Python 3.10+)
```

#### 2.1.2 控制流

```python
# 条件（封装逻辑）
if age >= 18:
    print("成年")
elif age >= 6:
    print("青少年")
else:
    print("未成年")

# 循环（遍历集合）
for score in scores:
    print(score)

# 列表推导式（函数式+OOP结合）
squares = [x**2 for x in range(10)]
even_squares = [x**2 for x in range(10) if x % 2 == 0]

# 字典推导式
name_len = {name: len(name) for name in ["alice", "bob"]}
```

#### 2.1.3 函数（面向过程 → 面向对象的过渡）

```python
# 基础函数
def greet(name: str) -> str:
    return f"Hello, {name}"

# 默认参数
def greet(name: str, prefix: str = "Hello") -> str:
    return f"{prefix}, {name}"

# *args / **kwargs（可变参数）
def sum(*args: int) -> int:
    return sum(args)

def print_info(**kwargs) -> None:
    for key, value in kwargs.items():
        print(f"{key}: {value}")

# 高阶函数（函数作为参数/返回值）
def apply(func, value):
    return func(value)

def multiplier(n):
    return lambda x: x * n

double = multiplier(2)
print(double(5))  # 10
```

#### 2.1.4 类与 OOP 核心（重点）

```python
# ========== 基础类定义 ==========
class User:
    """用户类 - 封装数据和行为"""
    
    # 类属性（所有实例共享）
    count: int = 0
    
    # 构造函数 - 初始化对象状态
    def __init__(self, name: str, email: str):
        # 实例属性（每个对象独立）
        self.name = name      # 公有属性
        self._token = ""     # 私有属性（约定：下划线开头）
        self.__password = "" # 真正的私有（会 Name Mangling）
        
        # 计数器
        User.count += 1
    
    # 实例方法
    def get_name(self) -> str:
        return self.name
    
    # 魔术方法
    def __str__(self) -> str:
        return f"User({self.name})"
    
    def __repr__(self) -> str:
        return f"User(name={self.name!r})"
    
    def __eq__(self, other) -> bool:
        return self.name == other.name
    
    def __len__(self) -> int:
        return len(self.name)

# 使用
user = User("Alice", "alice@example.com")
print(user)              # User(Alice)
print(len(user))          # 5


# ========== 继承 ==========
class Admin(User):
    """管理员类 - 继承 User"""
    
    def __init__(self, name: str, email: str, level: int = 1):
        # 调用父类构造函数
        super().__init__(name, email)
        self.level = level
    
    # 方法重写
    def get_name(self) -> str:
        return f"[Admin] {self.name}"

admin = Admin("Bob", "bob@example.com", 2)
print(admin.get_name())  # [Admin] Bob


# ========== 封装（访问控制）==========
class SecureUser:
    def __init__(self, password: str):
        self.__password = password  # 私有属性
    
    def verify(self, password: str) -> bool:
        return self.__password == password
    
    @property
    def password(self) -> str:
        return "***"  # 只读，不能直接访问
    
    @password.setter
    def password(self, new_pwd: str):
        if len(new_pwd) >= 6:
            self.__password = new_pwd


# ========== 抽象类 ==========
from abc import ABC, abstractmethod

class Animal(ABC):
    """抽象基类 - 定义接口"""
    
    @abstractmethod
    def speak(self) -> str:
        """子类必须实现"""
        pass
    
    def sleep(self) -> str:
        return f"{self.__class__.__name__} is sleeping"

class Dog(Animal):
    def speak(self) -> str:
        return "Woof!"

dog = Dog()
print(dog.sleep())  # Dog is sleeping


# ========== 多继承与 Mixin ==========
class LogMixin:
    """Mixin - 可复用的日志功能"""
    
    def log(self, message: str):
        print(f"[LOG] {message}")

class Repository(ABC):
    @abstractmethod
    def save(self):
        pass

class UserRepository(Repository, LogMixin):
    def save(self):
        self.log("Saving user...")

user_repo = UserRepository()
user_repo.save()  # [LOG] Saving user...
```

#### 2.1.5 模块与包（模块化 OOP）

```python
# ========== 模块化组织 ==========
# mypackage/__init__.py     - 包入口，可定义导出
# mypackage/user/          - 用户模块
# mypackage/user/models.py  - 数据模型
# mypackage/user/service.py # 业务服务

# 导入方式
from mypackage.user import User, UserService
from mypackage.user.service import UserService

# 相对导入（包内）
from . import module_name      # 同级
from .. import sibling      # 上级
```

### 2.2 环境管理

```bash
# 创建虚拟环境（推荐做法）
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
pip install -e .  # 开发模式安装
```

### 2.3 类型提示（企业级必需）

```python
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class User(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=50)
    email: str
    roles: List[str] = []
    metadata: Dict[str, Any] = {}

    class Config:
        from_attributes = True
```

### 2.4 异步编程

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

# 异步函数
async def fetch_data(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# 并发执行
async def main():
    tasks = [fetch_data(url) for url in urls]
    results = await asyncio.gather(*tasks)
```

### 2.5 企业级框架

```python
# FastAPI 示例
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
)

@app.get("/items/{item_id}")
async def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}
```

### 2.6 常用库

| 场景 | 库 | 说明 |
|------|-----|------|
| HTTP 客户端 | `httpx`, `aiohttp` | 异步请求 |
| 数据库 | `sqlalchemy`, `peewee` | ORM |
| 数据验证 | `pydantic` | 类型校验 |
| 配置管理 | `pydantic-settings` | 环境变量 |
| AI/ML | `langchain`, `openai` | 大模型 |
| 命令行 | `typer`, `click` | CLI 工具 |

---

## 3. Node.js 企业应用

### 3.1 包管理

```bash
# 使用 pnpm（企业推荐）
npm install -g pnpm
pnpm add express
pnpm add -D typescript @types/node

# package.json 核心字段
{
  "name": "my-app",
  "type": "module",  # ESM
  "scripts": {
    "dev": "tsx watch src/index.ts",
    "build": "tsc",
    "start": "node dist/index.js"
  }
}
```

### 3.2 TypeScript 基础语法（含 OOP）

#### 3.2.1 基础类型

```typescript
// 基础类型
let name: string = "Alice";
let age: number = 25;
let isActive: boolean = true;
let scores: number[] = [1, 2, 3];
let user: [string, number] = ["Alice", 25]; // 元组

// any / unknown / void / never
function warn(): void {
  console.log("warning");
}
function fail(): never {
  throw new Error("error");
}
```

#### 3.2.2 接口与类型（OOP 契约）

```typescript
// 接口 - 对象的形状
interface User {
  name: string;
  age: number;
  email?: string;     // 可选属性
  readonly id: number; // 只读
}

interface Admin extends User {
  level: number;
}

// 使用
const user: User = {
  name: "Alice",
  age: 25,
  id: 1  // 可以在创建时赋值
};
// user.id = 2;  // 错误：只读
```

#### 3.2.3 类与 OOP（TypeScript 的完整 OOP 实现）

```typescript
// ========== 基础类 ==========
class User {
  // 实例属性
  name: string;
  age: number;
  
  // 构造函数
  constructor(name: string, age: number) {
    this.name = name;
    this.age = age;
  }
  
  // 方法
  greet(): string {
    return `Hello, ${this.name}`;
  }
  
  // 静态成员
  static count: number = 0;
  static create(name: string, age: number): User {
    User.count++;
    return new User(name, age);
  }
}

const user = new User("Alice", 25);
console.log(user.greet());


// ========== 继承 ==========
class Admin extends User {
  level: number;
  
  constructor(name: string, age: number, level: number) {
    super(name, age);  // 调用父类
    this.level = level;
  }
  
  // 方法重写
  greet(): string {
    return `[Admin] ${super.greet()}`;
  }
}


// ========== 访问控制 ==========
class SecureUser {
  // 公开
  public name: string;
  // 私有（类外部不可访问）
  private password: string;
  // 受保护（子类可访问）
  protected token: string;
  // 只读
  readonly id: number;
  
  constructor(name: string, password: string) {
    this.name = name;
    this.password = password;
    this.id = 1;
  }
  
  // Getter/Setter
  get pwd(): string {
    return "***";
  }
  
  set pwd(value: string) {
    if (value.length >= 6) {
      this.password = value;
    }
  }
}


// ========== 抽象类 ==========
abstract class Animal {
  abstract speak(): string;  // 抽象方法
  
  sleep(): string {
    return "Sleeping...";
  }
}

class Dog extends Animal {
  speak(): string {
    return "Woof!";
  }
}
```

#### 3.2.4 函数类型

```typescript
// 函数类型注解
function greet(name: string): string {
  return `Hello, ${name}`;
}

// 箭头函数类型
const greet = (name: string): string => `Hello, ${name}`;

// 函数重载
function overload(id: string): User;
function overload(id: number): User;
function overload(id: string | number): User {
  if (typeof id === "string") {
    return { name: id };
  }
  return { id };
}
```

#### 3.2.5 泛型（参数化类型，OOP 的重要工具）

```typescript
// 基础泛型
function identity<T>(value: T): T {
  return value;
}
const num = identity<number>(5);
const str = identity("hello");

// 泛型约束
interface HasId {
  id: number;
}
function findById<T extends HasId>(items: T[], id: number): T | undefined {
  return items.find(item => item.id === id);
}

// 泛型接口
interface Repository<T> {
  findAll(): T[];
  findById(id: number): T | undefined;
  save(item: T): void;
}

interface User {
  name: string;
}
class UserRepository implements Repository<User> {
  findAll(): User[] {
    return [];
  }
  findById(id: number): User | undefined {
    return undefined;
  }
  save(item: User): void {}
}

// 实用类型
type PartialUser = Partial<User>;       // 所有属性可选
type RequiredUser = Required<User>;   // 所有属性必需
type PickUser = Pick<User, "name">;   // 选取部分属性
type OmitUser = Omit<User, "name">; // 排除部分属性
```

### 3.3 TypeScript 配置

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true
  }
}
```

### 3.4 异步模式

```typescript
//  Express 路由
import { Request, Response, NextFunction } from 'express';

async function asyncHandler(
  fn: (req: Request, res: Response, next: NextFunction) => Promise<any>
) {
  return (req: Request, res: Response, next: NextFunction) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

// 使用
app.get('/users', asyncHandler(async (req, res) => {
  const users = await UserService.findAll();
  res.json(users);
}));
```

### 3.5 Vite 构建配置

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    target: 'es2022',
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['vue', 'vue-router'],
        },
      },
    },
  },
});
```

### 3.6 常用企业库

| 场景 | 库 | 说明 |
|------|-----|------|
| Web 框架 | `express`, `fastify` | HTTP 服务 |
| ORM | `prisma`, `drizzle` | 数据库 |
| 验证 | `zod`, `joi` | 数据校验 |
| 日志 | `pino`, `winston` | 日志系统 |
| 实时通信 | `socket.io` | WebSocket |

---

## 4. Vue 3 现代前端

### 4.1 项目结构

```
src/
├── assets/           # 静态资源
├── components/      # 公共组件
│   └── Button.vue
├── composables/     # 组合式函数
│   └── useAuth.ts
├── views/          # 页面组件
│   └── Home.vue
├── stores/         # 状态管理
│   └── counter.ts
├── router/        # 路由配置
│   └── index.ts
├── api/            # 接口定义
│   └── user.ts
├── App.vue        # 根组件
└── main.ts       # 入口
```

### 4.2 模板语法详解

```vue
<template>
  <!-- 插值 -->
  <p>{{ message }}</p>
  <p v-html="htmlContent"></p>
  
  <!-- 指令 -->
  <div v-if="isVisible">显示</div>
  <div v-show="isVisible">切换</div>
  
  <!-- 循环 -->
  <ul>
    <li v-for="item in items" :key="item.id">{{ item.name }}</li>
  </ul>
  
  <!-- 绑定 -->
  <img :src="imageUrl" :alt="name" :class="{ active: isActive }" :style="{ color }" />
  
  <!-- 事件 -->
  <button @click="handleClick" @dblclick="handleDblClick">Click</button>
  <input @keyup.enter="submit" />
</template>
```

### 4.3 响应式原理（OOP 状态封装）

```typescript
// ref - 封装基础类型
import { ref } from 'vue';

const count = ref(0);
count.value++;  // 修改
console.log(count.value);  // 读取

// reactive - 封装对象
import { reactive } from 'vue';

const state = reactive({
  user: null,
  items: [] as string[],
});
state.user = { name: "Alice" };

// computed - 派生状态（类似 getter）
import { computed } from 'vue';

const doubled = computed(() => count.value * 2);

// watch / watchEffect - 观察者模式
import { watch, watchEffect } from 'vue';

watch(count, (newVal, oldVal) => {
  console.log(`Changed from ${oldVal} to ${newVal}`);
});

watchEffect(() => {
  console.log(`Count is ${count.value}`);
});
```

### 4.4 组件生命周期（对象生命周期）

```vue
<script setup lang="ts">
import { 
  onBeforeMount, 
  onMounted, 
  onBeforeUpdate, 
  onUpdated,
  onBeforeUnmount, 
  onUnmounted 
} from 'vue';

onBeforeMount(() => {
  // 组件挂载前
  console.log("Before mount");
});

onMounted(() => {
  // 组件挂载后（常用于初始化）
  console.log("Mounted");
});

onBeforeUpdate(() => {
  // 更新前
  console.log("Before update");
});

onUpdated(() => {
  // 更新后
  console.log("Updated");
});

onBeforeUnmount(() => {
  // 卸载前
  console.log("Before unmount");
});

onUnmounted(() => {
  // 卸载后（常用于清理）
  console.log("Unmounted");
});
</script>
```

### 4.5 组件通信模式（OOP 协作）

```vue
<!-- 子组件: UserCard.vue -->
<script setup lang="ts">
// Props - 构造函数参数
interface Props {
  name: string;
  email?: string;  // 可选
  readonly?: boolean;
}

const props = defineProps<Props>();

// Emits - 事件回调
const emit = defineEmits<{
  (e: 'update', data: { name: string; email: string }): void;
  (e: 'delete'): void;
}>();

// provide/inject - 依赖注入（IoC）
import { inject } from 'vue';

const userService = inject<UserService>('userService');
</script>

<template>
  <div class="card">
    <h3>{{ name }}</h3>
    <p v-if="email">{{ email }}</p>
    <button @click="$emit('update', { name, email })">Update</button>
  </div>
</template>

<!-- 父组件使用 -->
<script setup lang="ts">
import { provide } from 'vue';
import UserCard from './UserCard.vue';

// provide - 依赖注入
provide('userService', {
  fetchUser: () => {},
});
</script>

<template>
  <UserCard name="Alice" email="alice@example.com" @update="handleUpdate" />
</template>
```

### 4.6 组件设计原则（SOLID）

```typescript
// S - 单一职责：每个组件只做一件事
// Bad: 一个组件既显示用户又处理编辑
// Good: UserDisplay + UserEditor

// O - 开闭原则：通过 props 扩展
// <Button size="small" /> <Button size="large" />

// L - ���氏替换原则：子组件可以替换父组件
// <BaseButton /> <PrimaryButton extends BaseButton />

// I - 接口隔离：小而专注的 props
// Bad: interface Props { all: any }
// Good: interface NameProps { name: string }

// D - 依赖倒置：通过 props/provide 解耦
```

### 4.7 组合式 API

```vue
<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useUserStore } from '@/stores/user';

const userStore = useUserStore();
const count = ref(0);
const doubled = computed(() => count.value * 2);

function increment() {
  count.value++;
}

onMounted(() => {
  console.log('Component mounted');
});

watch(count, (newVal) => {
  console.log(`Count: ${newVal}`);
});
</script>

<template>
  <button @click="increment">
    Count: {{ count }} (double: {{ doubled }})
  </button>
</template>
```

### 4.8 路由守卫

```typescript
// router/index.ts
import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('@/views/Home.vue') },
    { path: '/profile', component: () => import('@/views/Profile.vue') },
  ],
});

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore();
  
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next('/login');
  } else {
    next();
  }
});

export default router;
```

### 4.9 状态管理

```typescript
// stores/user.ts - Pinia
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

export const useUserStore = defineStore('user', () => {
  const user = ref<{ name: string; email: string } | null>(null);
  const isLoggedIn = computed(() => user.value !== null);

  function login(credentials: any) {
    user.value = { name: 'Alice', email: 'alice@example.com' };
  }

  function logout() {
    user.value = null;
  }

  return { user, isLoggedIn, login, logout };
});
```

### 4.10 API 调用

```typescript
// api/client.ts
import axios from 'axios';

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 10000,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // 处理未授权
    }
    return Promise.reject(error);
  }
);

// 使用
const { data } = await apiClient.get('/users');
```

---

## 5. 实战项目架构

### 5.1 前后端分离模式

```
项目结构:
├── src/                    # Python 后端
│   ├── agent/              # AI Agent 核心
│   ├── tools/              # 工具注册
│   ├── skills/             # 技能系统
│   ├── context/           # 上下文管理
│   └── main.py            # 入口
├── ui/                     # Vue 前端
│   ├── src/
│   │   ├── App.vue
│   │   └── main.ts
│   └── vite.config.ts
├── server.py               # API 服务器
├── pyproject.toml         # Python 配置
└── package.json          # 前端依赖
```

### 5.2 核心配置

```toml
# pyproject.toml
[project]
name = "my-app"
version = "0.1.0"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = ["ruff", "mypy", "pytest"]

[tool.ruff]
line-length = 100
ignore = ["E501"]

[tool.mypy]
strict = true
```

```json
// package.json
{
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc && vite build",
    "preview": "vite preview"
  }
}
```

---

## 6. 企业级最佳实践

### 6.1 代码质量

```bash
# Python
ruff check . --fix       # Lint
mypy .                  # 类��检查
pytest tests/           # 测试

# Node.js/Vue
pnpm run lint           # ESLint
pnpm run typecheck     # TS 检查
pnpm run test          # 测试
```

### 6.2 安全实践

```python
# 环境变量管理
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    DATABASE_URL: str
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

```typescript
// 敏感信息不提交到前端
const API_BASE_URL = import.meta.env.VITE_API_URL;
```

### 6.3 错误处理

```python
# Python
from fastapi import HTTPException

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"error": str(exc)}
    )
```

```typescript
// Vue
const { data, error } = await useFetch('/api/users');
if (error.value) {
  // 统一错误处理
  showToast(error.value.message);
}
```

### 6.4 日志系统

```python
import logging

logger = logging.getLogger(__name__)
logger.info("User logged in", extra={"user_id": user.id})
```

```typescript
// Node.js
import pino from 'pino';
const logger = pino();
logger.info({ userId: user.id }, 'User logged in');
```

---

## 7. 企业级代码规范 Spec

### 7.1 文件命名约定（体现职责）

| 类型 | 规范 | 示例 | OOP 对应 |
|------|------|------|----------|
| Python 模块 | snake_case.py | user_service.py | 服务类 |
| Python 类 | PascalCase | UserService | 类定义 |
| TS/JS 文件 | kebab-case.ts | user-store.ts | 模块/服务 |
| Vue 组件 | PascalCase.vue | UserProfile.vue | 组件类 |
| 配置文件 | kebab-case | vite.config.ts | 配置对象 |
| 类型定义 | kebab-case.d.ts | user-type.d.ts | 接口定义 |

### 7.2 目录结构标准（模块化 OOP）

```
# Python 后端
src/
├── agent/              # 按功能垂直拆分（高内聚）
│   ├── tools/          # 工具注册（策略模式）
│   ├── skills/         # 技能系统
│   ├── context/       # 上下文管理
│   └── agent.py       # Agent 核心类

# Node.js 后端
src/
├── modules/           # 按功能模块拆分
│   ├── auth/         # 认证模块
│   │   ├── auth.module.ts
│   │   ├── auth.service.ts
│   │   └── auth.controller.ts
│   └── common/        # 公共模块

# Vue 前端
ui/src/
├── components/         # 公共组件（可复用）
│   ├── base/         # 基础组件（Button, Input）
│   ├── business/     # 业务组件
│   └── layout/      # 布局组件
├── composables/       # 组合式函数（逻辑复用）
├── views/            # 页面组件（路由级别）
├── stores/           # 状态（单例）
├── api/              # API 定义
└── types/           # TypeScript 类型
```

### 7.3 命名语法规范（代码元素）

#### 7.3.1 Python 命名规范

| 元素 | 规范 | 示例 | 说明 |
|------|------|------|------|
| **类名** | PascalCase | `UserService`, `AgentConfig` | 名词，表示对象 |
| **函数** | snake_case | `get_user()`, `fetch_data()` | 动词/动词短语 |
| **方法** | snake_case | `def save(self)` | 动词短语 |
| **私有方法** | `_method()` | `_validate()` | 单下划线前缀 |
| **魔术方法** | `__method__()` | `__init__()` | 双下划线前后缀 |
| **变量** | snake_case | `user_name`, `items_list` | 名词短语 |
| **实例变量** | snake_case | `self.user_id` | `self.` 开头 |
| **类变量** | snake_case | `default_timeout` | 类级别共享 |
| **常量** | UPPER_SNAKE | `MAX_RETRY = 3` | 全大写 + 下划线 |
| **私有变量** | `_private_var` | `_cache` | 单下划线前缀 |
| **模块名** | snake_case.py | `user_service.py` | 文件名 |
| **包名** | snake_case | `my_package` | 目录名 |
| **抽象类** | ABC / Base 开头 | `BaseRepository`, `Animal` | `ABC` 后缀 |
| **异常类** | Exception 结尾 | `UserNotFoundError` | `Error` 后缀 |
| **枚举** | PascalCase | `UserRole` | 类形式 |

```python
# 类名
class UserService:
    pass

# 函数
def get_user_by_id(user_id: int) -> User | None:
    pass

# 私有方法
def _validate_input(data: dict) -> bool:
    pass

# 常量
DEFAULT_TIMEOUT = 30
MAX_RETRY_COUNT = 3

# 抽象基类
from abc import ABC, abstractmethod

class BaseRepository(ABC):
    @abstractmethod
    def find_by_id(self, id: int):
        pass

# 异常
class UserNotFoundError(Exception):
    pass

# 枚举
from enum import Enum

class UserRole(Enum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"
```

#### 7.3.2 TypeScript/JavaScript 命名规范

| 元素 | 规范 | 示例 | 说明 |
|------|------|------|------|
| **接口名** | PascalCase | `User`, `UserProfile` | 名词 |
| **类型别名** | PascalCase | `UserStatus` | `type` 关键字 |
| **类名** | PascalCase | `UserService` | 名词 |
| **枚举** | PascalCase | `UserRole` | 大写字母值 |
| **函数** | camelCase | `getUser()`, `fetchData()` | 动词短语 |
| **方法** | camelCase | `save()` | 动词/动词短语 |
| **变量** | camelCase | `userName`, `itemsList` | 名词短语 |
| **常量** | UPPER_SNAKE | `MAX_RETRY`, `API_BASE_URL` | 全大写 |
| **私有属性** | `_property` | `_cache` | 下划线前缀 |
| **���读属性** | `readonly prop` | `readonly id` | `readonly` |
| **文件名** | kebab-case.ts | `user-service.ts` | 服务 |
| **组件名** | PascalCase | `UserCard.vue` | Vue 组件 |
| **泛型** | `<T>`, `<K, V>` | `Repository<T>` | 大写单字母 |

```typescript
// 接口
interface User {
  id: number;
  name: string;
  email?: string;
}

// 类型别名
type UserStatus = 'active' | 'inactive' | 'pending';

// 枚举
enum UserRole {
  Admin = 'ADMIN',
  User = 'USER',
  Guest = 'GUEST',
}

// 类
class UserService {
  private cache: Map<number, User>;
  
  constructor() {
    this.cache = new Map();
  }
  
  async getUser(id: number): Promise<User | undefined> {
    return this.cache.get(id);
  }
}

// 函数
function getUserById(id: number): User | undefined {
  return undefined;
}

// 常量
const MAX_RETRY_COUNT = 3;
const API_BASE_URL = '/api';
```

#### 7.3.3 Vue 3 命名规范

| 元素 | 规范 | 示例 | 说明 |
|------|------|------|------|
| **组件名** | PascalCase | `UserCard.vue`, `AppHeader.vue` | 描述性名词 |
| **基础组件** | Base 开头 | `BaseButton.vue` | `Base` 前缀 |
| **业务组件** | 功能 + 类型 | `UserCard.vue` | 业务 + 类型 |
| **布局组件** | Layout 结尾 | `AppLayout.vue` | 布局类组件 |
| **Props** | camelCase | `userName`, `isLoading` | 名词 |
| **Events** | camelCase | `update`, `delete` | 动词 |
| **自定义事件** | kebab-case | `user-updated` | 模板中使用 |
| **Slots** | camelCase | `default`, `footer` | 描述性名词 |
| **Composable** | use + 名词 | `useUser.ts`, `useAuth.ts` | `use` 前缀 |
| **Store** | 名词 + .ts | `auth.ts`, `user.ts` | 功能名 |
| **Router** | kebab-case | `user-profile.ts` | 路由文件 |
| **类型文件** | .d.ts | `user.d.ts`, `env.d.ts` | 类型定义 |

```vue
<!-- 组件命名 -->
<!-- BaseButton.vue -->
<!-- UserCard.vue -->
<!-- AppLayout.vue -->

<!-- Props -->
<script setup lang="ts">
defineProps<{
  userName: string;
  isLoading?: boolean;
  userId: number;
}>();
</script>

<!-- Emits -->
<script setup lang="ts">
const emit = defineEmits<{
  (e: 'update', user: User): void;
  (e: 'delete', id: number): void;
  (e: 'user-updated', payload: any): void;  // 模板中 kebab-case
}>();
</script>

<!-- 使用 -->
<template>
  <UserCard
    :user-name="name"
    @update="handleUpdate"
    @user-updated="handleUserUpdated"
  >
    <template #footer>
      <span>Footer content</span>
    </template>
  </UserCard>
</template>
```

```typescript
// composables/useUser.ts
export function useUser() {
  // 逻辑
  return { user, fetchUser };
}

// stores/auth.ts
export const useAuthStore = defineStore('auth', () => {
  // 状态和方法
  return { user, login, logout };
});
```

#### 7.3.4 SQL/数据库命名规范

| 元素 | 规范 | 示例 | 说明 |
|------|------|------|------|
| **表名** | snake_case | `user`, `user_profile` | 小写 + 下划线 |
| **视图名** | v_ + 表名 | `v_user_active` | `v_` 前缀 |
| **字段名** | snake_case | `user_name`, `created_at` | 功能描述 |
| **主键** | id | `id` | 通用主键名 |
| **外键** | table_id | `user_id` | 表名 + id |
| **索引** | idx_ + 表名 + 字段 | `idx_user_email` | `idx_` 前缀 |
| **唯一索引** | uk_ + 表名 + 字段 | `uk_user_email` | `uk_` 前缀 |
| **约束** | ck_ + 表名 + 条件 | `ck_user_status` | `ck_` 前缀 |
| **序列** | seq_ + 表名 | `seq_user_id` | `seq_` 前缀 |

```sql
-- 表名
CREATE TABLE user (
    id SERIAL PRIMARY KEY,
    user_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 外���
ALTER TABLE order ADD CONSTRAINT fk_order_user FOREIGN KEY (user_id) REFERENCES user(id);

-- 索引
CREATE INDEX idx_user_email ON user(email);
CREATE UNIQUE INDEX uk_user_email ON user(email);

-- 视图
CREATE VIEW v_user_active AS SELECT * FROM user WHERE status = 'active';
```

#### 7.3.5 Git 提交规范

| 类型 | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat: add user login` |
| `fix` | 修复 bug | `fix: resolve login timeout` |
| `refactor` | 重构 | `refactor: extract UserService` |
| `style` | 格式调整 | `style: format code` |
| `docs` | 文档更新 | `docs: update README` |
| `test` | 测试相关 | `test: add unit test` |
| `chore` | 构建/工具 | `chore: update deps` |
| `perf` | 性能优化 | `perf: improve query` |
| `ci` | CI/CD 变更 | `ci: add github action` |
| `build` | 构建系统 | `build: update vite` |

```bash
# 提交格式
git commit -m "type: description"

# 示例
git commit -m "feat: add user profile page"
git commit -m "fix: resolve login timeout issue"
git commit -m "refactor: extract UserService from Agent"
git commit -m "docs: update API documentation"
```

#### 7.3.6 综合命名速查表

```python
# ===================== Python =====================
# 类
class UserService: pass
class BaseRepository(ABC): pass
class UserNotFoundError(Exception): pass

# 函数/方法
def get_user_by_id(user_id: int): pass
def _private_helper(): pass

# 变量/常量
user_name = "alice"
MAX_RETRY_COUNT = 3

# 模块/包
user_service.py
my_package/
```

```typescript
// ===================== TypeScript =====================
// 接口/类型
interface User {}
type UserStatus = 'active' | 'inactive';

// 类
class UserService {}

// 函数/方法
function getUser(): void {}
private _cache: {};

// 常量
const MAX_RETRY = 3;

// 文件
user-service.ts
user.d.ts
```

```vue
<!-- ===================== Vue ===================== -->
<!-- 组件 -->
UserCard.vue
BaseButton.vue

<!-- Props/Events -->
defineProps<{ userName: string }>()
defineEmits<{ (e: 'update'): void }>()

<!-- Composable/Store -->
useUser.ts
auth.ts
```

```sql
-- ===================== SQL =====================
-- 表/字段
user
user_name, created_at

-- 索引
idx_user_email
```

### 7.3 OOP 设计原则（SOLID）

#### 7.3.1 单一职责原则（S）

> 一个类/组件只负责一件事

```python
# Bad: 一个类做太多
class UserManager:
    def login(self): ...
    def logout(self): ...
    def send_email(self): ...
    def generate_report(self): ...

# Good: 分离职责
class AuthService:      # 认证
class EmailService:   # 邮件
class ReportService:  # 报表
```

#### 7.3.2 开闭原则（O）

> 对扩展开放，对修改关闭

```typescript
// Bad: 修改现有代码添加功能
if (type === 'admin') { ... }
else if (type === 'user') { ... }

// Good: 通过扩展添加
interface Role {
  checkPermission(action: string): boolean;
}
class AdminRole implements Role { ... }
class UserRole implements Role { ... }
```

#### 7.3.3 里氏替换原则（L）

> 子类可以替换父类

```python
class BaseRepository:
    def find_all(self): ...

class MockRepository(BaseRepository):  # 替换父类用于测试
    def find_all(self): 
        return [MockUser()]  # 返回 mock 数据
```

#### 7.3.4 接口隔离原则（I）

> 接口应该小而专注

```typescript
// Bad: 大接口
interface UserService {
  login(): void;
  logout(): void;
  create(): void;
  update(): void;
  delete(): void;
  findAll(): void;
  export(): void;
}

// Good: 拆分小接口
interface AuthService { login(): void; logout(): void; }
interface UserCrudService { create(); update(); delete(); findAll(); }
interface ExportService { export(): void; }
```

#### 7.3.5 依赖倒置原则（D）

> 依赖抽象而非具体

```python
# Bad: 依赖具体类
class OrderService:
    def __init__(self, db: SQLAlchemyDB):
        self.db = db

# Good: 依赖抽象
class OrderService:
    def __init__(self, repo: Repository):
        self.repo = repo
```

### 7.4 设计模式简要说明

| 模式 | 应用场景 | 示例 |
|------|--------|------|
| **工厂模式** | 创建对象 | `createAgent()`, `Factory<T>` |
| **单例模式** | 全局唯一 | `useUserStore()`, `app.use()` |
| **观察者模式** | 事件系统 | Vue 响应式、EventEmitter |
| **策略模式** | 算法族 | 不同 tool 实现 |
| **装饰器模式** | 增强功能 | `@route()`, `@computed()` |
| **依赖注入** | 解耦 | FastAPI `Depends()`, Vue `provide/inject` |

### 7.5 代码注释规范

```python
# Python: Google Style / NumPy Style
class UserService:
    """User service for managing user operations.
    
    This service handles user CRUD operations and authentication.
    
    Attributes:
        db: Database connection instance.
        logger: Logger instance for tracking operations.
    
    Example:
        >>> service = UserService(db)
        >>> user = service.get_user(1)
    """
    
    def get_user(self, user_id: int) -> User | None:
        """Get user by ID.
        
        Args:
            user_id: The unique identifier of the user.
            
        Returns:
            User instance or None if not found.
            
        Raises:
            ValueError: If user_id is invalid.
        """
        pass
```

```typescript
// TypeScript: TSDoc
/**
 * User service for managing user operations.
 * 
 * @example
 * const service = new UserService(db);
 * const user = await service.getUser(1);
 */
class UserService {
  /**
   * Get user by ID.
   * @param userId - The unique identifier
   * @returns User instance or undefined
   * @throws Will throw if userId is invalid
   */
  async getUser(userId: number): Promise<User | undefined> {
    // ...
  }
}
```

```vue
<!-- Vue: 组件注释 -->
<script setup lang="ts">
/**
 * User card component
 * @displayName UserCard
 * @seeDocs /docs/user-card
 */
</script>
```

### 7.6 Git 提交规范

| 类型 | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | 添加用户管理模块 |
| `fix` | 修复 bug | 修复登录问题 |
| `refactor` | 重构 | 优化 OOP 设计 |
| `docs` | 文档 | 更新 README |
| `style` | 格式 | 代码格式化 |
| `test` | 测试 | 添加单元测试 |
| `chore` | 构建/工具 | 更新依赖 |

```bash
git commit -m "feat: add user management module"
git commit -m "fix: resolve login timeout issue"
git commit -m "refactor: extract UserService from Agent"
```

---

## 8. 业内基础框架模板

### 8.1 Python 框架模板（FastAPI - 依赖注入 OOP）

#### 项目结构

```
project/
├── app/
│   ├── __init__.py
│   ├── main.py              # 入口
│   ├── config.py           # 配置类
│   ├── models/            # 数据模型（Pydantic）
│   │   ├─�� __init__.py
│   │   └── user.py
│   ├── schemas/           # 请求/响应模型
│   │   ├── __init__.py
│   │   └── user.py
│   ├── services/          # 业务服务层（OOP）
│   │   ├── __init__.py
│   │   └── user_service.py
│   ├── repositories/      # 数据访问层
│   │   ├── __init__.py
│   │   └── user_repo.py
│   ├── routers/           # 路由层
│   │   ├── __init__.py
│   │   └── user.py
│   └── deps.py            # 依赖注入
├── tests/
│   └── test_user.py
├── pyproject.toml
└── .env.example
```

#### 核心代码模板

```python
# app/main.py
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.routers import user_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时（类似构造函数）
    print("Startup...")
    yield
    # 关闭时（类似析构函数）
    print("Shutdown...")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
)

app.include_router(user_router.router, prefix="/api/users", tags=["users"])
```

```python
# app/models/user.py - 数据模型（OOP）
from pydantic import BaseModel, EmailStr, Field

class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    email: EmailStr

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None

class UserResponse(UserBase):
    id: int
    is_active: bool
    
    model_config = {"from_attributes": True}
```

```python
# app/services/user_service.py - 业务服务类（OOP）
from abc import ABC, abstractmethod

class AbstractUserService(ABC):
    @abstractmethod
    def get_user(self, user_id: int): ...
    
    @abstractmethod
    def create_user(self, user_data): ...

class UserService(AbstractUserService):
    def __init__(self, repository):
        self.repository = repository  # 依赖注入
    
    def get_user(self, user_id: int):
        return self.repository.find_by_id(user_id)
    
    def create_user(self, user_data):
        # 业务逻辑
        return self.repository.create(user_data)
```

```python
# app/deps.py - 依赖注入
from app.services.user_service import UserService
from app.repositories.user_repo import UserRepository

def get_user_repository():
    return UserRepository()

def get_user_service(repo: UserRepository = Depends(get_user_repository)):
    return UserService(repo)
```

```python
# app/routers/user.py - 路由
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.user import UserCreate, UserResponse
from app.services.user_service import UserService
from app.deps import get_user_service

router = APIRouter()

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service)
):
    return user_service.create_user(user_data)

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service)
):
    user = user_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

### 8.2 Node.js 框架模板（NestJS - 完整模块化 OOP）

#### 项目结构

```
project/
├── src/
│   ├── main.ts                 # 入口
│   ├── app.module.ts           # 根模块
│   ├── config/               # 配置模块
│   │   ├── config.module.ts
│   │   └── config.service.ts
│   ├── auth/                 # 认证模块
│   │   ├── auth.module.ts
│   │   ├── auth.service.ts
│   │   ├── auth.controller.ts
│   │   ├── auth.guard.ts
│   │   └── dto/
│   │       ├── login.dto.ts
│   │       └── register.dto.ts
│   ├── users/                 # 用户模块
│   │   ├── users.module.ts
│   │   ├── users.service.ts
│   │   ├── users.controller.ts
│   │   └── schemas/
│   │       └── user.schema.ts
│   ├── common/               # 公共模块
│   │   ├── decorators/
│   │   ├── filters/
│   │   ├── guards/
│   │   └── interceptors/
│   └── shared/
│       ├── dto/
│       └── entities/
├── test/
├── package.json
├── tsconfig.json
└── nest-cli.json
```

#### 核心代码模板

```typescript
// main.ts
import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  
  app.useGlobalPipes(new ValidationPipe({
    whitelist: true,
    transform: true,
  }));
  
  app.enableCors();
  await app.listen(3000);
}
bootstrap();
```

```typescript
// app.module.ts - 根模块（类似 Spring 的 @SpringBootApplication）
import { Module } from '@nestjs/common';
import { ConfigModule } from './config/config.module';
import { AuthModule } from './auth/auth.module';
import { UsersModule } from './users/users.module';

@Module({
  imports: [
    ConfigModule,
    AuthModule,
    UsersModule,
  ],
})
export class AppModule {}
```

```typescript
// users/users.module.ts
import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { UsersController } from './users.controller';
import { UsersService } from './users.service';
import { User, UserSchema } from './schemas/user.schema';

@Module({
  imports: [
    MongooseModule.forFeature([{ name: User.name, schema: UserSchema }]),
  ],
  controllers: [UsersController],
  providers: [UsersService],
  exports: [UsersService],
})
export class UsersModule {}
```

```typescript
// users/users.service.ts - 服务类（@Injectable 单例）
import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { User } from './schemas/user.schema';

@Injectable()
export class UsersService {
  constructor(
    @InjectModel(User.name) private userModel: Model<User>,
  ) {}
  
  async findAll(): Promise<User[]> {
    return this.userModel.find().exec();
  }
  
  async findById(id: string): Promise<User> {
    const user = await this.userModel.findById(id).exec();
    if (!user) {
      throw new NotFoundException(`User #${id} not found`);
    }
    return user;
  }
  
  async create(createUserDto: any): Promise<User> {
    const user = new this.userModel(createUserDto);
    return user.save();
  }
}
```

```typescript
// users/users.controller.ts - 控制器
import { Controller, Get, Post, Body, Param, UseGuards } from '@nestjs/common';
import { UsersService } from './users.service';
import { CreateUserDto } from './dto/create-user.dto';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Controller('users')
export class UsersController {
  constructor(private readonly usersService: UsersService) {}
  
  @Get()
  async findAll() {
    return this.usersService.findAll();
  }
  
  @Get(':id')
  async findOne(@Param('id') id: string) {
    return this.usersService.findById(id);
  }
  
  @Post()
  async create(@Body() createUserDto: CreateUserDto) {
    return this.usersService.create(createUserDto);
  }
}
```

### 8.3 Vue 3 框架模板（组件化 OOP）

#### 项目结构

```
project/
├── public/
│   └── favicon.ico
├── src/
│   ├── assets/              # 静态资源
│   │   ├── styles/
│   │   │   └── main.scss
│   │   └── images/
│   ├── components/          # 公共组件（可复用对象）
│   │   ├── base/            # 基础组件
│   │   │   ├── Button.vue
│   │   │   ├── Input.vue
│   │   │   └── Modal.vue
│   │   ├── business/        # 业务组件
│   │   │   ├── UserCard.vue
│   │   │   └── UserForm.vue
│   │   └── layout/          # 布局组件
│   │       ├── AppHeader.vue
│   │       ├── AppSidebar.vue
│   │       └── AppLayout.vue
│   ├── composables/        # 组合式函数（逻辑复用）
│   │   ├── useAuth.ts
│   │   ├── useUser.ts
│   │   ├── useFetch.ts
│   │   └── useModal.ts
│   ├── views/             # 页���组件（路由级别）
│   │   ├── HomeView.vue
│   │   ├── UsersView.vue
│   │   └── NotFoundView.vue
│   ├── stores/             # 状态管理（Pinia）
│   │   ├── auth.ts
│   │   ├── user.ts
│   │   └── app.ts
│   ├── api/               # API 接口定义
│   │   ├── client.ts
│   │   ├── user.ts
│   │   └── auth.ts
│   ├── router/            # 路由配置
│   │   ├── index.ts
│   │   └── guards.ts
│   ├── types/             # TypeScript 类型定义
│   │   ├── user.d.ts
│   │   ├── api.d.ts
│   │   └── env.d.ts
│   ├── utils/             # 工具函数
│   │   ├── date.ts
│   │   ├── validate.ts
│   │   └── storage.ts
│   ├── App.vue            # 根组件
│   ├── main.ts           # 入口
│   └── env.d.ts         # Vite 环境变量
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── .env.example
```

#### 核心代码模板

```typescript
// main.ts - 入口（组合各个组件）
import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import router from './router';
import './assets/styles/main.css';

const app = createApp(App);

app.use(createPinia());
app.use(router);

app.mount('#app');
```

```typescript
// router/index.ts - 路由配置
import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/HomeView.vue'),
    },
    {
      path: '/users',
      name: 'users',
      component: () => import('@/views/UsersView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
    },
  ],
});

// 路由守卫
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore();
  
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({ name: 'login', query: { redirect: to.fullPath } });
  } else {
    next();
  }
});

export default router;
```

```typescript
// stores/auth.ts - 状态管理（单例模式）
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

export const useAuthStore = defineStore('auth', () => {
  // 状态
  const token = ref<string | null>(null);
  const user = ref<{ id: number; name: string; email: string } | null>(null);
  
  // 计算属性
  const isAuthenticated = computed(() => !!token.value);
  
  // 方法
  async function login(credentials: { email: string; password: string }) {
    const { data } = await apiClient.post('/auth/login', credentials);
    token.value = data.token;
    user.value = data.user;
  }
  
  function logout() {
    token.value = null;
    user.value = null;
  }
  
  return { token, user, isAuthenticated, login, logout };
});
```

```typescript
// composables/useUser.ts - 组合式函数（复用逻辑）
import { ref, computed } from 'vue';
import { apiClient } from '@/api/client';

export function useUser() {
  const user = ref<{ id: number; name: string; email: string } | null>(null);
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  
  const userName = computed(() => user.value?.name ?? 'Guest');
  
  async function fetchUser(id: number) {
    isLoading.value = true;
    error.value = null;
    
    try {
      const { data } = await apiClient.get(`/users/${id}`);
      user.value = data;
    } catch (e) {
      error.value = e.message;
    } finally {
      isLoading.value = false;
    }
  }
  
  return { user, userName, isLoading, error, fetchUser };
}
```

```vue
<!-- components/business/UserCard.vue - 业务组件 -->
<script setup lang="ts">
import { ref, computed } from 'vue';
import type { User } from '@/types/user';

// Props - 构造函数参数
interface Props {
  user: User;
  readonly?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  readonly: false,
});

// Emits - 事件回调
const emit = defineEmits<{
  (e: 'update', user: User): void;
  (e: 'delete', id: number): void;
}>();

// 状态
const isEditing = ref(false);
const editedName = ref(props.user.name);

// 计算属性
const displayName = computed(() => props.user.name ?? 'Unknown');

// 方法
function save() {
  emit('update', { ...props.user, name: editedName.value });
  isEditing.value = false;
}

function remove() {
  emit('delete', props.user.id);
}
</script>

<template>
  <div class="user-card">
    <div v-if="isEditing">
      <input v-model="editedName" />
      <button @click="save">Save</button>
      <button @click="isEditing = false">Cancel</button>
    </div>
    <div v-else>
      <h3>{{ displayName }}</h3>
      <p>{{ user.email }}</p>
      <button v-if="!readonly" @click="isEditing = true">Edit</button>
      <button v-if="!readonly" @click="remove">Delete</button>
    </div>
  </div>
</template>
```

---

## 9. 学习路径

### 9.1 第一阶段：基础（1-2周）

- [ ] Python 语法 + 类型提示
- [ ] Python OOP：类、继承、封装
- [ ] FastAPI 基础路由
- [ ] TypeScript 基础 + 类与接口
- [ ] Vue 3 基础指令 + 模板语法

### 9.2 第二阶段：进阶（2-4周）

- [ ] Pydantic 数据验证
- [ ] Python 抽象类 + 设计模式
- [ ] 数据库操作 (SQLAlchemy/Prisma)
- [ ] Vue 组合式 API + 响应式原理
- [ ] 路由 + 状态管理

### 9.3 第三阶段：实战（4-8周）

- [ ] 企业级项目架构（OOP 分层）
- [ ] 依赖注入实践
- [ ] 认证/授权
- [ ] 部署 + CI/CD
- [ ] 性能优化

### 9.4 推荐资源

| 技术 | 官方文档 | 视频教程 |
|------|----------|----------|
| Python | [docs.python.org](https://docs.python.org/) | Corey Schafer |
| FastAPI | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/) | Python Engineer |
| TypeScript | [typescriptlang.org](https://www.typescriptlang.org/) | Traversy Media |
| Vue | [vuejs.org](https://vuejs.org/) | Vue Mastery |
| NestJS | [docs.nestjs.com](https://docs.nestjs.com/) | Net Ninja |

---

## 10. 快速参考

### 10.1 命令行

```bash
# Python
python -m venv .venv          # 创建环境
pip install -r requirements.txt
pip install -e .              # 开发安装
uv pip install -e .           # 使用 uv

# Node.js
pnpm create vite . --template vue-ts
pnpm install
pnpm run dev

# 项目命令 (本项目)
python -m src.agent.main --input "your task"
cd ui && pnpm run dev
```

### 10.2 代码规范

```python
# Python: ruff format + type hints
def process_user(user_id: int) -> User | None:
    """Process user by ID."""
    ...
```

```typescript
// TypeScript: strict mode
async function fetchUser(id: number): Promise<User> {
  const { data } = await apiClient.get(`/users/${id}`);
  return data;
}
```

```vue
<!-- Vue: script setup -->
<script setup lang="ts">
defineProps<{ title: string }>();
const emit = defineEmits<{ (e: 'submit', data: string): void }>();
</script>
```

---

*最后更新: 2026-05-03*