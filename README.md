# TG 卖货机器人（修复版）

## 修复内容

- ✅ 修复 Supervisor 守护进程无法启动的 Bug（原脚本引用了不存在的 venv 路径）
- ✅ 自动检测系统 Python3 真实路径，不再依赖虚拟环境
- ✅ pip 安装兼容新系统（自动加 `--break-system-packages`）
- ✅ 依赖安装失败时自动切换国内镜像源
- ✅ 启动失败时自动打印日志帮助排查

---

## 宝塔部署步骤

### 前提条件
- 宝塔面板已安装 **Supervisor** 插件（软件商店搜索安装）
- 服务器已安装 Python 3.8+

### 步骤一：上传文件

将整个 `TG-Bot-Fixed` 文件夹上传到服务器任意目录，例如 `/root/`

### 步骤二：SSH 执行安装

```bash
cd /root/TG-Bot-Fixed
chmod +x install.sh
bash install.sh
```

脚本会引导你输入：
1. Bot Token（从 @BotFather 获取）
2. 管理员 Telegram 数字 ID（从 @userinfobot 获取）
3. USDT 收款地址（TRC20，T 开头）
4. TronGrid API Key（可选，留空也能用）
5. 客服用户名（可选）

### 步骤三：验证启动

```bash
supervisorctl status tg_shop_bot
```

看到 `RUNNING` 表示成功。

---

## 查看日志

```bash
tail -f /www/wwwroot/tg-bot/bot.log
```

---

## 常见问题

**Q：守护进程显示 FATAL / STOPPED？**
- 查看日志：`tail -50 /www/wwwroot/tg-bot/bot.log`
- 最常见原因：Bot Token 填错、服务器访问不了 Telegram（国内服务器需配置代理）

**Q：国内服务器连不上 Telegram？**
- 需要在服务器配置代理，或使用香港/海外服务器

**Q：再次运行 install.sh 会重装吗？**
- 不会，检测到已安装会直接进入管理菜单

---

## 文件结构

```
TG-Bot-Fixed/
├── bot.py              # 主程序
├── config.py           # 配置模板（安装脚本会覆盖）
├── database.py         # 数据库操作
├── tron_payment.py     # TRC20 收款检测
├── requirements.txt    # Python 依赖
├── install.sh          # 一键安装脚本（已修复）
├── handlers/
│   ├── __init__.py
│   ├── admin_handlers.py
│   └── user_handlers.py
└── README.md
```
