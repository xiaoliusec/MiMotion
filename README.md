# MiMotion - 微信运动步数修改工具

一个基于 Flask 的 Web 应用程序，通过修改小米运动（Zepp）绑定数据来实现修改微信运动步数。

> ⚠️ **警告**：此工具仅供学习 Zepp/小米研究使用，违反/微信 服务条款，可能导致账号被封禁。请谨慎使用。

## 功能特性

- 🔐 验证码登录系统
- 👥 多账号管理
- 📱 支持手机号和邮箱登录
- 🔄 自动刷新登录 Token
- 👑 管理员后台管理验证码
- 🏃 一键修改微信运动步数（需绑定小米运动）

## 环境要求

- Python 3.8+
- SQLite3

## 准备工作

在使用本工具前，你需要：

1. 下载 **Zepp**（原小米运动）APP
2. 注册账号（推荐使用邮箱）
3. 绑定微信运动：我的 → 第三方接入 → 绑定微信运动

## 安装部署

### 1. 克隆项目

```bash
git clone https://github.com/你的用户名/MiMotion.git
cd MiMotion
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动服务（首次运行会自动创建数据库）

```bash
python app.py
```

服务运行在 `http://0.0.0.0:50000`

### 4. 添加管理员验证码

```bash
python manage.py add admin123
```

验证码要求：1-16位字母或数字，例如 `admin123`、`test01`、`ABC`

## 使用教程

### 第一步：登录

1. 打开浏览器访问 `http://localhost:50000`
2. 输入验证码登录
3. 首次登录自动成为管理员

### 第二步：添加小米账号

1. 登录后点击「添加账号」
2. 输入小米账号（手机号或邮箱）和密码
3. 点击确认添加

**注意**：
- 手机号无需加 +86，自动处理
- 首次添加会进行登录验证

### 第三步：修改步数

1. 选择要修改的账号
2. 输入目标步数
3. 点击「修改步数」

修改成功后，步数会同步到你的微信运动。

## 管理命令

使用 `manage.py` 管理验证码：

```bash
# 添加管理员验证码
python manage.py add admin123

# 添加普通用户验证码
python manage.py add user001 0

# 列出所有验证码
python manage.py list

# 删除验证码（需要先 list 查看 ID）
python manage.py delete 1
```

## API 文档

### 认证

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/verify-code` | POST | 验证码登录 |

### 用户

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/accounts` | GET | 获取账号列表 |
| `/api/accounts` | POST | 添加账号 |
| `/api/accounts/<id>` | DELETE | 删除账号 |
| `/api/set-step` | POST | 修改步数 |

### 管理员

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/admin/codes` | GET | 获取所有验证码 |
| `/api/admin/codes` | POST | 创建验证码 |
| `/api/admin/codes/<id>` | DELETE | 删除验证码 |

## 项目结构

```
MiMotion/
├── app.py              # Flask 主程序
├── manage.py           # 管理脚本
├── zpwx.py             # Zepp API 核心逻辑
├── requirements.txt    # Python 依赖
├── static/
│   ├── script.js       # 前端脚本
│   └── style.css       # 样式文件
├── templates/
│   └── index.html      # 主页模板
└── zpwx.db             # SQLite 数据库
```

## 技术栈

- **后端**: Flask, SQLite, JWT
- **前端**: HTML5, CSS3, Vanilla JavaScript
- **核心库**: pycryptodome (AES加密), requests

## 常见问题

### Q: 步数修改失败怎么办？
A: 
1. 检查账号是否有效
2. 尝试删除账号后重新添加
3. 确保网络连接正常
4. 确认已在 Zepp APP 中绑定微信运动

### Q: 如何添加更多管理员？
A: 
```bash
python manage.py add 新验证码
```

### Q: 如何查看当前有哪些验证码？
A: 
```bash
python manage.py list
```

## 免责声明

本项目仅供学习研究使用，与 Zepp、小米、微信无任何关联。使用本工具造成的一切后果由使用者自行承担。

## License

MIT License
