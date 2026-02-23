"""
TG 卖货机器人主程序
支持：自动发货 + 人工发货 | USDT TRC20 收款 | 管理员后台
"""
import asyncio
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
import config
import database as db
import tron_payment

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ConversationHandler 状态
(
    ADMIN_MENU, ADD_PRODUCT_NAME, ADD_PRODUCT_DESC, ADD_PRODUCT_PRICE,
    ADD_PRODUCT_TYPE, ADD_CARDS_SELECT, ADD_CARDS_INPUT,
    SET_PRICE_SELECT, SET_PRICE_INPUT, DELIVER_SELECT, DELIVER_INPUT,
    BAN_INPUT, BROADCAST_INPUT
) = range(13)

# 支付轮询任务存储 {order_id: task}
payment_tasks = {}

# ============================================================
# 工具函数
# ============================================================
def is_admin(user_id):
    return user_id in config.ADMIN_IDS

def product_type_label(auto):
    return "🤖 自动发货" if auto else "👤 人工发货"

def status_label(s):
    return {"pending": "⏳ 待付款", "paid": "💰 已付款待发货",
            "delivered": "✅ 已发货", "cancelled": "❌ 已取消"}.get(s, s)

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 商品列表", callback_data="shop")],
        [InlineKeyboardButton("📋 我的订单", callback_data="my_orders")],
    ])

def admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 商品管理", callback_data="admin_products"),
         InlineKeyboardButton("🃏 添加卡密", callback_data="admin_cards")],
        [InlineKeyboardButton("📋 所有订单", callback_data="admin_orders"),
         InlineKeyboardButton("💰 待发货订单", callback_data="admin_pending_deliver")],
        [InlineKeyboardButton("🚫 封禁用户", callback_data="admin_ban"),
         InlineKeyboardButton("✅ 解封用户", callback_data="admin_unban")],
        [InlineKeyboardButton("📢 广播消息", callback_data="admin_broadcast")],
    ])

# ============================================================
# 支付轮询
# ============================================================
async def poll_payment(order_id, user_id, context, created_ts):
    timeout = config.PAYMENT_TIMEOUT * 60
    interval = 30  # 每30秒检测一次
    elapsed = 0
    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval
        order = db.get_order(order_id)
        if not order or order['status'] != 'pending':
            return
        if tron_payment.check_payment(order_id, order['amount'], created_ts):
            db.mark_order_paid(order_id)
            if order['auto_delivery']:
                card = db.get_available_card(order['product_id'])
                if card:
                    db.mark_card_used(card['id'], order_id)
                    db.update_stock_count(order['product_id'])
                    db.mark_order_delivered(order_id, card['content'])
                    await context.bot.send_message(
                        user_id,
                        f"✅ *付款成功，自动发货！*\n\n"
                        f"商品：{order['product_name']}\n"
                        f"内容：\n`{card['content']}`\n\n"
                        f"感谢购买！有问题请联系 {config.CUSTOMER_SERVICE}",
                        parse_mode="Markdown"
                    )
                    # 通知管理员
                    for admin_id in config.ADMIN_IDS:
                        try:
                            await context.bot.send_message(
                                admin_id,
                                f"🤖 自动发货成功\n订单#{order_id}\n用户：@{order['username']}\n商品：{order['product_name']}\n金额：{order['amount']} USDT"
                            )
                        except:
                            pass
                else:
                    # 库存不足，转人工
                    db.mark_order_paid(order_id)
                    await context.bot.send_message(
                        user_id,
                        f"✅ *付款成功！*\n\n很抱歉，库存暂时不足，已转人工处理。\n客服：{config.CUSTOMER_SERVICE}\n订单号：#{order_id}",
                        parse_mode="Markdown"
                    )
                    for admin_id in config.ADMIN_IDS:
                        try:
                            await context.bot.send_message(
                                admin_id,
                                f"⚠️ 库存不足！需人工处理\n订单#{order_id}\n用户：@{order['username']}\n商品：{order['product_name']}\n金额：{order['amount']} USDT",
                                reply_markup=InlineKeyboardMarkup([[
                                    InlineKeyboardButton(f"📤 发货 #{order_id}", callback_data=f"do_deliver_{order_id}")
                                ]])
                            )
                        except:
                            pass
            else:
                # 人工发货
                await context.bot.send_message(
                    user_id,
                    f"✅ *付款成功！*\n\n订单号：#{order_id}\n商品：{order['product_name']}\n\n客服将尽快为您发货，请等待。\n客服：{config.CUSTOMER_SERVICE}",
                    parse_mode="Markdown"
                )
                for admin_id in config.ADMIN_IDS:
                    try:
                        await context.bot.send_message(
                            admin_id,
                            f"💰 收到付款！需人工发货\n订单#{order_id}\n用户：@{order['username']} (ID:{user_id})\n商品：{order['product_name']}\n金额：{order['amount']} USDT",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton(f"📤 发货 #{order_id}", callback_data=f"do_deliver_{order_id}")
                            ]])
                        )
                    except:
                        pass
            return
    # 超时
    order = db.get_order(order_id)
    if order and order['status'] == 'pending':
        db.cancel_order(order_id)
        await context.bot.send_message(user_id, f"⏰ 订单 #{order_id} 已超时取消，如已付款请联系 {config.CUSTOMER_SERVICE}")

# ============================================================
# 用户命令
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username or "", user.first_name or "")
    if db.is_banned(user.id):
        await update.message.reply_text("❌ 您已被封禁，请联系客服。")
        return
    await update.message.reply_text(
        config.WELCOME_TEXT,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ 无权限")
        return
    await update.message.reply_text("🛠 *管理员后台*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())

# ============================================================
# 商品列表
# ============================================================
async def show_shop(query, context):
    products = db.get_products()
    if not products:
        await query.edit_message_text("暂无商品，请稍后再来 🙏")
        return
    keyboard = []
    for p in products:
        stock_info = f" (库存:{p['stock_count']})" if p['auto_delivery'] else ""
        label = f"{'🤖' if p['auto_delivery'] else '👤'} {p['name']} - {p['price']} USDT{stock_info}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"product_{p['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="back_home")])
    await query.edit_message_text("🛍 *请选择商品：*", parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(keyboard))

async def show_product_detail(query, context, pid):
    p = db.get_product(pid)
    if not p:
        await query.edit_message_text("商品不存在")
        return
    stock_text = f"\n📦 库存：{p['stock_count']} 件" if p['auto_delivery'] else ""
    text = (f"*{p['name']}*\n\n"
            f"📝 {p['description'] or '暂无描述'}\n"
            f"💰 价格：{p['price']} USDT\n"
            f"🚀 {product_type_label(p['auto_delivery'])}{stock_text}")
    keyboard = [
        [InlineKeyboardButton("🛒 立即购买", callback_data=f"buy_{pid}")],
        [InlineKeyboardButton("🔙 返回商品列表", callback_data="shop")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ============================================================
# 购买流程
# ============================================================
async def handle_buy(query, context, pid):
    user = query.from_user
    if db.is_banned(user.id):
        await query.answer("您已被封禁")
        return
    p = db.get_product(pid)
    if not p:
        await query.edit_message_text("商品不存在")
        return
    if p['auto_delivery'] and p['stock_count'] <= 0:
        await query.edit_message_text("❌ 该商品库存不足，请选择其他商品或联系客服。")
        return

    order_id = db.create_order(user.id, user.username or str(user.id),
                               pid, p['name'], p['price'], p['auto_delivery'])
    created_ts = time.time()

    text = config.PAYMENT_TEXT.format(
        timeout=config.PAYMENT_TIMEOUT,
        amount=p['price'],
        address=config.USDT_WALLET
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ 取消订单", callback_data=f"cancel_order_{order_id}")]
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # 启动支付轮询
    task = asyncio.create_task(poll_payment(order_id, user.id, context, created_ts))
    payment_tasks[order_id] = task

# ============================================================
# 我的订单
# ============================================================
async def show_my_orders(query, context):
    orders = db.get_user_orders(query.from_user.id)
    if not orders:
        await query.edit_message_text("您还没有任何订单。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="back_home")]]))
        return
    lines = ["📋 *我的订单（最近10条）*\n"]
    for o in orders:
        lines.append(f"#{o['id']} {o['product_name']} {o['amount']}U - {status_label(o['status'])}")
        if o['status'] == 'delivered' and o['delivery_content']:
            lines.append(f"  📦 发货内容：`{o['delivery_content']}`")
    text = "\n".join(lines)
    await query.edit_message_text(text, parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="back_home")]]))

# ============================================================
# 管理员：商品管理
# ============================================================
async def admin_show_products(query, context):
    products = db.get_products(enabled_only=False)
    if not products:
        text = "暂无商品"
    else:
        lines = ["📦 *商品列表：*\n"]
        for p in products:
            status = "✅" if p['enabled'] else "🔴"
            lines.append(f"{status} #{p['id']} {p['name']} - {p['price']}U | {product_type_label(p['auto_delivery'])} | 库存:{p['stock_count']}")
        text = "\n".join(lines)
    keyboard = [
        [InlineKeyboardButton("➕ 添加商品", callback_data="admin_add_product")],
        [InlineKeyboardButton("✏️ 修改价格", callback_data="admin_set_price")],
        [InlineKeyboardButton("🔙 关闭/开启", callback_data="admin_toggle_product")],
        [InlineKeyboardButton("🗑 删除商品", callback_data="admin_delete_product")],
        [InlineKeyboardButton("🔙 返回", callback_data="admin_home")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ============================================================
# 管理员：所有订单
# ============================================================
async def admin_show_orders(query, context):
    orders = db.get_all_orders(20)
    if not orders:
        text = "暂无订单"
    else:
        lines = ["📋 *最近20条订单：*\n"]
        for o in orders:
            lines.append(f"#{o['id']} @{o['username']} {o['product_name']} {o['amount']}U {status_label(o['status'])}")
        text = "\n".join(lines)
    await query.edit_message_text(text, parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="admin_home")]]))

async def admin_show_pending_deliver(query, context):
    orders = db.get_paid_orders()
    if not orders:
        await query.edit_message_text("✅ 暂无待发货订单",
                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="admin_home")]]))
        return
    keyboard = []
    for o in orders:
        keyboard.append([InlineKeyboardButton(
            f"📤 #{o['id']} @{o['username']} {o['product_name']} {o['amount']}U",
            callback_data=f"do_deliver_{o['id']}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="admin_home")])
    await query.edit_message_text("💰 *待发货订单：*", parse_mode="Markdown",
                                   reply_markup=InlineKeyboardMarkup(keyboard))

# ============================================================
# 主 CallbackQuery 路由
# ============================================================
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_home" or data == "start":
        await query.edit_message_text(config.WELCOME_TEXT, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    elif data == "admin_home":
        await query.edit_message_text("🛠 *管理员后台*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())
    elif data == "shop":
        await show_shop(query, context)
    elif data == "my_orders":
        await show_my_orders(query, context)
    elif data.startswith("product_"):
        await show_product_detail(query, context, int(data.split("_")[1]))
    elif data.startswith("buy_"):
        await handle_buy(query, context, int(data.split("_")[1]))
    elif data.startswith("cancel_order_"):
        oid = int(data.split("_")[2])
        order = db.get_order(oid)
        if order and order['status'] == 'pending' and order['user_id'] == query.from_user.id:
            db.cancel_order(oid)
            if oid in payment_tasks:
                payment_tasks[oid].cancel()
            await query.edit_message_text("❌ 订单已取消", reply_markup=main_menu_keyboard())
        else:
            await query.edit_message_text("订单无法取消（已付款或不存在）")

    # ===== 管理员 =====
    elif data == "admin_products" and is_admin(query.from_user.id):
        await admin_show_products(query, context)
    elif data == "admin_orders" and is_admin(query.from_user.id):
        await admin_show_orders(query, context)
    elif data == "admin_pending_deliver" and is_admin(query.from_user.id):
        await admin_show_pending_deliver(query, context)
    elif data.startswith("do_deliver_") and is_admin(query.from_user.id):
        oid = int(data.split("_")[2])
        context.user_data['deliver_order_id'] = oid
        await query.edit_message_text(f"📤 请发送订单 #{oid} 的发货内容（账号密码等），直接回复即可：")
        context.user_data['state'] = 'delivering'
    elif data == "admin_ban" and is_admin(query.from_user.id):
        await query.edit_message_text("请发送要封禁的用户 ID（数字）：")
        context.user_data['state'] = 'banning'
    elif data == "admin_unban" and is_admin(query.from_user.id):
        await query.edit_message_text("请发送要解封的用户 ID（数字）：")
        context.user_data['state'] = 'unbanning'
    elif data == "admin_add_product" and is_admin(query.from_user.id):
        await query.edit_message_text("请发送新商品名称：")
        context.user_data['state'] = 'add_product_name'
        context.user_data['new_product'] = {}
    elif data == "admin_set_price" and is_admin(query.from_user.id):
        products = db.get_products(enabled_only=False)
        keyboard = [[InlineKeyboardButton(f"#{p['id']} {p['name']}", callback_data=f"setprice_{p['id']}")] for p in products]
        await query.edit_message_text("选择要修改价格的商品：", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("setprice_") and is_admin(query.from_user.id):
        pid = int(data.split("_")[1])
        context.user_data['set_price_pid'] = pid
        context.user_data['state'] = 'set_price_input'
        await query.edit_message_text(f"请发送商品 #{pid} 的新价格（USDT）：")
    elif data == "admin_toggle_product" and is_admin(query.from_user.id):
        products = db.get_products(enabled_only=False)
        keyboard = [[InlineKeyboardButton(
            f"{'✅' if p['enabled'] else '🔴'} #{p['id']} {p['name']}",
            callback_data=f"toggle_{p['id']}_{0 if p['enabled'] else 1}"
        )] for p in products]
        await query.edit_message_text("点击切换商品上架/下架：", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("toggle_") and is_admin(query.from_user.id):
        parts = data.split("_")
        pid, enabled = int(parts[1]), int(parts[2])
        db.toggle_product(pid, enabled)
        await query.edit_message_text(f"商品 #{pid} 已{'上架' if enabled else '下架'}")
    elif data == "admin_delete_product" and is_admin(query.from_user.id):
        products = db.get_products(enabled_only=False)
        keyboard = [[InlineKeyboardButton(f"🗑 #{p['id']} {p['name']}", callback_data=f"delproduct_{p['id']}")] for p in products]
        await query.edit_message_text("⚠️ 选择要删除的商品（同时删除所有卡密）：", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("delproduct_") and is_admin(query.from_user.id):
        pid = int(data.split("_")[1])
        db.delete_product(pid)
        await query.edit_message_text(f"✅ 商品 #{pid} 已删除")
    elif data == "admin_cards" and is_admin(query.from_user.id):
        products = db.get_products(enabled_only=False)
        auto_products = [p for p in products if p['auto_delivery']]
        if not auto_products:
            await query.edit_message_text("暂无自动发货商品，请先添加")
            return
        keyboard = [[InlineKeyboardButton(f"#{p['id']} {p['name']} (库存:{p['stock_count']})", callback_data=f"addcards_{p['id']}")] for p in auto_products]
        await query.edit_message_text("选择要添加卡密的商品：", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("addcards_") and is_admin(query.from_user.id):
        pid = int(data.split("_")[1])
        context.user_data['add_cards_pid'] = pid
        context.user_data['state'] = 'add_cards_input'
        await query.edit_message_text(f"请发送卡密内容（每行一条，可批量粘贴）：")
    elif data == "admin_broadcast" and is_admin(query.from_user.id):
        await query.edit_message_text("请发送广播消息内容（将发送给所有用户）：")
        context.user_data['state'] = 'broadcasting'

# ============================================================
# 文字消息处理（状态机）
# ============================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if db.is_banned(update.effective_user.id):
        return
    state = context.user_data.get('state')
    text = update.message.text.strip()

    if state == 'delivering' and is_admin(update.effective_user.id):
        oid = context.user_data.get('deliver_order_id')
        order = db.get_order(oid)
        if order:
            db.mark_order_delivered(oid, text)
            try:
                await context.bot.send_message(
                    order['user_id'],
                    f"✅ *您的订单已发货！*\n\n商品：{order['product_name']}\n\n发货内容：\n`{text}`\n\n感谢购买！有问题联系 {config.CUSTOMER_SERVICE}",
                    parse_mode="Markdown"
                )
            except:
                pass
            await update.message.reply_text(f"✅ 订单 #{oid} 已发货并通知用户")
        context.user_data['state'] = None

    elif state == 'banning' and is_admin(update.effective_user.id):
        try:
            uid = int(text)
            db.ban_user(uid, True)
            await update.message.reply_text(f"✅ 用户 {uid} 已封禁")
        except:
            await update.message.reply_text("格式错误，请输入数字ID")
        context.user_data['state'] = None

    elif state == 'unbanning' and is_admin(update.effective_user.id):
        try:
            uid = int(text)
            db.ban_user(uid, False)
            await update.message.reply_text(f"✅ 用户 {uid} 已解封")
        except:
            await update.message.reply_text("格式错误，请输入数字ID")
        context.user_data['state'] = None

    elif state == 'add_product_name' and is_admin(update.effective_user.id):
        context.user_data['new_product']['name'] = text
        context.user_data['state'] = 'add_product_desc'
        await update.message.reply_text("请发送商品描述（发送 - 跳过）：")

    elif state == 'add_product_desc' and is_admin(update.effective_user.id):
        context.user_data['new_product']['desc'] = "" if text == "-" else text
        context.user_data['state'] = 'add_product_price'
        await update.message.reply_text("请发送商品价格（USDT，例如：9.9）：")

    elif state == 'add_product_price' and is_admin(update.effective_user.id):
        try:
            price = float(text)
            context.user_data['new_product']['price'] = price
            context.user_data['state'] = 'add_product_type'
            await update.message.reply_text(
                "发货方式？",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 自动发货", callback_data="newproduct_auto")],
                    [InlineKeyboardButton("👤 人工发货", callback_data="newproduct_manual")],
                ])
            )
        except:
            await update.message.reply_text("价格格式错误，请输入数字（如 9.9）：")

    elif state == 'add_cards_input' and is_admin(update.effective_user.id):
        pid = context.user_data.get('add_cards_pid')
        lines = text.splitlines()
        db.add_cards(pid, lines)
        p = db.get_product(pid)
        await update.message.reply_text(f"✅ 成功添加 {len([l for l in lines if l.strip()])} 条卡密，当前库存：{p['stock_count']}")
        context.user_data['state'] = None

    elif state == 'set_price_input' and is_admin(update.effective_user.id):
        pid = context.user_data.get('set_price_pid')
        try:
            price = float(text)
            db.update_product_price(pid, price)
            await update.message.reply_text(f"✅ 商品 #{pid} 价格已更新为 {price} USDT")
        except:
            await update.message.reply_text("价格格式错误")
        context.user_data['state'] = None

    elif state == 'broadcasting' and is_admin(update.effective_user.id):
        users = db.get_all_users()
        success, fail = 0, 0
        for u in users:
            try:
                await context.bot.send_message(u['user_id'], f"📢 *公告*\n\n{text}", parse_mode="Markdown")
                success += 1
            except:
                fail += 1
        await update.message.reply_text(f"📢 广播完成：成功 {success}，失败 {fail}")
        context.user_data['state'] = None

    else:
        await update.message.reply_text("请使用 /start 开始", reply_markup=main_menu_keyboard())

# ============================================================
# 处理添加商品类型选择
# ============================================================
async def handle_new_product_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if not is_admin(query.from_user.id):
        return
    np = context.user_data.get('new_product', {})
    auto = 1 if data == "newproduct_auto" else 0
    pid = db.add_product(np.get('name',''), np.get('desc',''), np.get('price', 0), auto)
    await query.edit_message_text(
        f"✅ 商品添加成功！\n\n#{pid} {np.get('name')} - {np.get('price')} USDT\n{product_type_label(auto)}\n\n"
        + ("自动发货请用 /admin → 添加卡密 添加库存" if auto else "")
    )
    context.user_data['state'] = None
    context.user_data['new_product'] = {}

# ============================================================
# 启动
# ============================================================
def main():
    db.init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))

    # 新商品类型选择
    app.add_handler(CallbackQueryHandler(handle_new_product_type, pattern="^newproduct_"))
    # 所有其他按钮
    app.add_handler(CallbackQueryHandler(callback_router))
    # 文字消息
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("机器人启动中...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
