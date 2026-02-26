## TG 卖货机器人-Pro

### 机场推荐：
- 曙光云：https://dawnscloud.com
- 超实惠：https://cshjc.net

##

### VPS推荐：
- OCI：https://oci.ee

##

### 发卡网：

- 卡链云：https://marts.cc

## 

- TG群组：https://t.me/yufeng_duxing
- 定制联系：https://t.me/martsccbot
- 博客：https://yufengduxing.xyz/
- Github：https://github.com/yufengduxing

##

## 宝塔部署步骤

### 前提条件
- 宝塔面板已安装 **Supervisor** 插件（软件商店搜索安装）
- 服务器已安装 Python 3.8+

### 步骤一：上传文件

将整个 `TG-Bot-Fixed` 文件夹上传到服务器任意目录，例如 `/root/`

### 步骤二：SSH 执行安装

```bash
cd /root/TG-Bot-Fixed（/root/TG-Bot-Fixed改成自己的根目录）

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

提示：⚠️常见原因：Bot Token 填错 | 服务器无法访问 Telegram（需代理）

```bash
# 卸载旧版，安装兼容 Python 3.13 的最新版
pip3 install --upgrade python-telegram-bot --break-system-packages

# 重启机器人
supervisorctl restart tg_shop_bot
sleep 3
supervisorctl status tg_shop_bot

如果还报错，看下装上什么版本：
pip3 show python-telegram-bot | grep Version
---


## 查看日志

```bash
tail -f /www/wwwroot/tg-bot/bot.log
```

---

## 常见问题

守护进程显示 FATAL / STOPPED？**
- 查看日志：`tail -50 /www/wwwroot/tg-bot/bot.log`
- 最常见原因：Bot Token 填错、服务器访问不了 Telegram（国内服务器需配置代理）

国内服务器连不上 Telegram？**
- 需要在服务器配置代理，或使用香港/海外服务器

再次运行 install.sh 会重装吗？**
- 不会，检测到已安装会直接进入管理菜单
