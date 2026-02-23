from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode
import database as db
from config import ADMIN_IDS
from datetime import datetime

# ConversationHandler 状态
(
    ADD_PRODUCT_NAME, ADD_PRODUCT_DESC, ADD_PRODUCT_PRICE,
    ADD_PRODUCT_CATEGORY, ADD_PRODUCT_DELIVER,
    ADD_CARDS_PRODUCT, ADD_CARDS_CONTENT,
    EDIT_PRODUCT_SELECT, EDIT_PRODUCT_FIELD, EDIT_PRODUCT_VALUE,
    MANUAL_DELIVER_ORDER, MANUAL_DELIVER_CONTENT,
    BROADCAST_MSG
) = range(13)


def is_admin(user_id):
    return user_id in ADMIN_IDS


async def admin_check(update: Update):
    user = update.effective_user
    if not is_admin(user.id):
        if update.message:
            await update.message.reply_text("无权限")
        elif update.callback_query:
            await update.callback_query.answer("无权限")
        return False
    return True


# ===== 管理员主菜单 =====

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    if query:
        await query.answer()
        reply = query.message.reply_text
    else:
        reply = update.message.reply_text

    stats = db.get_stats()
    text = f"""🔧 管理员后台

📊 数据概览：
👥 总用户数：{stats['total_users']}
📦 总订单数：{stats['total_orders']}
💰 总收入：{stats['total_revenue']:.2f} USDT
⏳ 待处理订单：{stats['pending_orders']}
"""
    kb = [
        [InlineKeyboardButton("📦 商品管理", callback_data="admin_products"),
         InlineKeyboardButton("🗃 卡密管理", callback_data="admin_cards")],
        [InlineKeyboardButton("📋 订单管理", callback_data="admin_orders"),
         InlineKeyboardButton("👥 用户管理", callback_data="admin_users")],
        [InlineKeyboardButton("📊 数据统计", callback_data="admin_stats")],
    ]
    await reply(text, reply_markup=InlineKeyboardMarkup(kb))


# ===== 商品管理 =====

async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()

    products = db.get_all_products(active_only=False)
    text = "📦 商品管理\n\n"
    kb = []
    for p in products:
        status = "✅" if p['is_active'] else "❌"
        deliver = "⚡自动" if p['auto_deliver'] else "👤人工"
        stock = f"库存:{p['stock_count']}" if p['auto_deliver'] else ""
        text += f"{status} [{p['id']}] {p['name']} {p['price']}U {deliver} {stock}\n"
        kb.append([
            InlineKeyboardButton(f"编辑 {p['name']}", callback_data=f"admin_edit_product_{p['id']}"),
            InlineKeyboardButton("🗑删除" if p['is_active'] else "✅恢复", callback_data=f"admin_toggle_product_{p['id']}")
        ])

    kb.append([InlineKeyboardButton("➕ 添加商品", callback_data="admin_add_product")])
    kb.append([InlineKeyboardButton("⬅️ 返回", callback_data="admin_menu")])
    await query.message.reply_text(text or "暂无商品", reply_markup=InlineKeyboardMarkup(kb))


async def admin_toggle_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    p = db.get_product(product_id)
    new_status = 0 if p['is_active'] else 1
    db.update_product(product_id, is_active=new_status)
    action = "下架" if not new_status else "上架"
    await query.message.reply_text(f"✅ 商品已{action}")
    await admin_products(update, context)


async def admin_add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.reply_text("请输入商品名称：\n\n输入 /cancel 取消")
    return ADD_PRODUCT_NAME


async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text.strip()
    await update.message.reply_text("请输入商品描述（或发送 - 跳过）：")
    return ADD_PRODUCT_DESC


async def add_product_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data['desc'] = '' if text == '-' else text
    await update.message.reply_text("请输入商品价格（USDT，如：9.9）：")
    return ADD_PRODUCT_PRICE


async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        context.user_data['price'] = price
    except ValueError:
        await update.message.reply_text("价格格式错误，请重新输入：")
        return ADD_PRODUCT_PRICE
    await update.message.reply_text("请输入商品分类（如：TG账号、谷歌账号、TG会员）：")
    return ADD_PRODUCT_CATEGORY


async def add_product_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['category'] = update.message.text.strip()
    kb = [[
        InlineKeyboardButton("⚡ 自动发货", callback_data="deliver_auto"),
        InlineKeyboardButton("👤 人工发货", callback_data="deliver_manual")
    ]]
    await update.message.reply_text("选择发货方式：", reply_markup=InlineKeyboardMarkup(kb))
    return ADD_PRODUCT_DELIVER


async def add_product_deliver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    auto = 1 if query.data == "deliver_auto" else 0
    context.user_data['auto_deliver'] = auto

    pid = db.add_product(
        context.user_data['name'],
        context.user_data['desc'],
        context.user_data['price'],
        context.user_data['category'],
        auto
    )
    deliver_str = "自动发货" if auto else "人工发货"
    await query.message.reply_text(
        f"✅ 商品添加成功！\n\nID: {pid}\n名称: {context.user_data['name']}\n价格: {context.user_data['price']} USDT\n发货: {deliver_str}"
        + ("\n\n⚠️ 请记得添加卡密库存！使用 /admin 进入后台" if auto else "")
    )
    context.user_data.clear()
    return ConversationHandler.END


# ===== 编辑商品 =====

async def admin_edit_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    context.user_data['edit_product_id'] = product_id
    p = db.get_product(product_id)

    text = f"编辑商品: {p['name']}\n\n选择要修改的字段："
    kb = [
        [InlineKeyboardButton("名称", callback_data="editfield_name"),
         InlineKeyboardButton("描述", callback_data="editfield_description")],
        [InlineKeyboardButton("价格", callback_data="editfield_price"),
         InlineKeyboardButton("分类", callback_data="editfield_category")],
        [InlineKeyboardButton("⬅️ 返回", callback_data="admin_products")]
    ]
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return EDIT_PRODUCT_FIELD


async def edit_product_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data.split("_", 1)[1]
    context.user_data['edit_field'] = field
    field_names = {'name': '名称', 'description': '描述', 'price': '价格', 'category': '分类'}
    await query.message.reply_text(f"请输入新的{field_names.get(field, field)}：")
    return EDIT_PRODUCT_VALUE


async def edit_product_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data.get('edit_field')
    product_id = context.user_data.get('edit_product_id')
    value = update.message.text.strip()

    if field == 'price':
        try:
            value = float(value)
        except ValueError:
            await update.message.reply_text("价格格式错误，请重新输入：")
            return EDIT_PRODUCT_VALUE

    db.update_product(product_id, **{field: value})
    await update.message.reply_text(f"✅ 已更新！")
    context.user_data.clear()
    return ConversationHandler.END


# ===== 卡密管理 =====

async def admin_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()

    products = db.get_all_products()
    auto_products = [p for p in products if p['auto_deliver']]
    if not auto_products:
        await query.message.reply_text("暂无自动发货商品", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回", callback_data="admin_menu")]]))
        return

    text = "🗃 卡密管理\n\n选择要管理的商品："
    kb = []
    for p in auto_products:
        kb.append([InlineKeyboardButton(f"{p['name']} (库存:{p['stock_count']})", callback_data=f"admin_cards_{p['id']}")])
    kb.append([InlineKeyboardButton("⬅️ 返回", callback_data="admin_menu")])
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def admin_add_cards_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    context.user_data['cards_product_id'] = product_id
    p = db.get_product(product_id)
    await query.message.reply_text(
        f"为商品「{p['name']}」添加卡密\n\n请发送卡密内容，每行一条：\n\n例如：\nabc123:pass1\nabc456:pass2\n\n输入 /cancel 取消"
    )
    return ADD_CARDS_CONTENT


async def add_cards_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product_id = context.user_data.get('cards_product_id')
    lines = update.message.text.strip().split('\n')
    added = db.add_cards(product_id, lines)
    p = db.get_product(product_id)
    await update.message.reply_text(f"✅ 成功添加 {added} 条卡密\n当前库存: {p['stock_count']} 条")
    context.user_data.clear()
    return ConversationHandler.END


# ===== 订单管理 =====

async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()

    kb = [
        [InlineKeyboardButton("⏳ 待确认", callback_data="admin_orders_confirming"),
         InlineKeyboardButton("📬 待人工发货", callback_data="admin_orders_paid")],
        [InlineKeyboardButton("📋 所有订单", callback_data="admin_orders_all")],
        [InlineKeyboardButton("⬅️ 返回", callback_data="admin_menu")]
    ]
    await query.message.reply_text("📋 订单管理\n\n选择查看类型：", reply_markup=InlineKeyboardMarkup(kb))


async def admin_orders_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    status = parts[-1] if parts[-1] in ['confirming', 'paid', 'all'] else None
    actual_status = None if status == 'all' else status

    orders = db.get_all_orders(limit=20, status=actual_status)
    if not orders:
        await query.message.reply_text("暂无订单", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回", callback_data="admin_orders")]]))
        return

    status_map = {
        'pending': '⏳', 'confirming': '🔍', 'paid': '✅',
        'delivered': '📬', 'cancelled': '❌', 'rejected': '🚫'
    }
    text = f"订单列表（最近20条）\n\n"
    kb = []
    for o in orders:
        s = status_map.get(o['status'], '')
        text += f"{s} #{o['id']} {o['product_name']} {o['amount']}U - {o['username']}\n"
        if o['status'] in ['confirming', 'paid']:
            kb.append([InlineKeyboardButton(f"处理 #{o['id']} {o['product_name']}", callback_data=f"admin_process_{o['id']}")])

    kb.append([InlineKeyboardButton("⬅️ 返回", callback_data="admin_orders")])
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def admin_process_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[-1])
    order = db.get_order(order_id)
    if not order:
        await query.message.reply_text("订单不存在")
        return

    p = db.get_product(order['product_id'])
    text = f"处理订单 #{order_id}\n\n商品: {order['product_name']}\n用户: {order['username']} ({order['user_id']})\n金额: {order['amount']} USDT\n状态: {order['status']}\n发货方式: {'自动' if p and p['auto_deliver'] else '人工'}"
    kb = [
        [InlineKeyboardButton("✅ 确认收款并发货", callback_data=f"admin_confirm_{order_id}"),
         InlineKeyboardButton("❌ 拒绝", callback_data=f"admin_reject_{order_id}")],
        [InlineKeyboardButton("⬅️ 返回", callback_data="admin_orders")]
    ]
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def admin_confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[-1])
    order = db.get_order(order_id)
    if not order:
        await query.message.reply_text("订单不存在")
        return

    p = db.get_product(order['product_id'])
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if p and p['auto_deliver']:
        # 自动发货
        card = db.get_unused_card(order['product_id'])
        if not card:
            await query.message.reply_text(f"❌ 自动发货失败：商品库存不足！\n请手动发货或补充库存。")
            return
        db.mark_card_used(card['id'], order_id)
        db.update_order(order_id, status='delivered', card_content=card['content'], paid_at=now, delivered_at=now)
        db.update_stock_count(order['product_id'])

        # 通知用户
        user_text = f"✅ 您的订单已完成！\n\n📦 商品: {order['product_name']}\n\n🎁 您的卡密：\n`{card['content']}`\n\n感谢购买！如有问题请联系客服。"
        try:
            await context.bot.send_message(order['user_id'], user_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            print(f"通知用户失败: {e}")
        await query.message.reply_text(f"✅ 自动发货完成！\n卡密: {card['content']}")
    else:
        # 人工发货 - 先确认收款，然后提示输入发货内容
        db.update_order(order_id, status='paid', paid_at=now)
        context.user_data['manual_deliver_order_id'] = order_id
        await query.message.reply_text(f"✅ 收款已确认！\n\n请输入发货内容（账号信息等）：\n\n输入 /cancel 取消")
        return MANUAL_DELIVER_CONTENT


async def manual_deliver_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_id = context.user_data.get('manual_deliver_order_id')
    content = update.message.text.strip()
    order = db.get_order(order_id)
    if not order:
        await update.message.reply_text("订单不存在")
        return ConversationHandler.END

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.update_order(order_id, status='delivered', card_content=content, delivered_at=now)

    user_text = f"✅ 您的订单已完成！\n\n📦 商品: {order['product_name']}\n\n🎁 发货内容：\n{content}\n\n感谢购买！如有问题请联系客服。"
    try:
        await context.bot.send_message(order['user_id'], user_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"通知用户失败: {e}")

    await update.message.reply_text(f"✅ 人工发货完成！")
    context.user_data.clear()
    return ConversationHandler.END


async def admin_reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[-1])
    order = db.get_order(order_id)
    if not order:
        await query.message.reply_text("订单不存在")
        return
    db.update_order(order_id, status='rejected')
    try:
        await context.bot.send_message(order['user_id'], f"❌ 您的订单 #{order_id} 付款未确认，已被拒绝。\n\n如有疑问请联系客服。")
    except Exception:
        pass
    await query.message.reply_text(f"已拒绝订单 #{order_id}")


# ===== 用户管理 =====

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "👥 用户管理\n\n使用命令操作：\n/ban <用户ID> - 封禁用户\n/unban <用户ID> - 解封用户",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ 返回", callback_data="admin_menu")]])
    )


async def ban_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    if not context.args:
        await update.message.reply_text("用法: /ban <用户ID>")
        return
    try:
        uid = int(context.args[0])
        db.ban_user(uid, True)
        await update.message.reply_text(f"✅ 用户 {uid} 已封禁")
        await context.bot.send_message(uid, "您的账号已被封禁，如有疑问请联系客服。")
    except Exception as e:
        await update.message.reply_text(f"操作失败: {e}")


async def unban_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    if not context.args:
        await update.message.reply_text("用法: /unban <用户ID>")
        return
    try:
        uid = int(context.args[0])
        db.ban_user(uid, False)
        await update.message.reply_text(f"✅ 用户 {uid} 已解封")
    except Exception as e:
        await update.message.reply_text(f"操作失败: {e}")


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_check(update):
        return
    query = update.callback_query
    await query.answer()
    stats = db.get_stats()
    text = f"""📊 数据统计

👥 总用户数: {stats['total_users']}
📦 完成订单: {stats['total_orders']}
💰 总收入: {stats['total_revenue']:.2f} USDT
⏳ 待处理: {stats['pending_orders']}
"""
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ 返回", callback_data="admin_menu")]]))


async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update.message:
        await update.message.reply_text("已取消")
    return ConversationHandler.END
