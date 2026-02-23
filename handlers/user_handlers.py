from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import database as db
from config import WELCOME_TEXT, USDT_WALLET, SUPPORT_CONTACT, ADMIN_IDS
from tron_payment import get_payment_info


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name)
    u = db.get_user(user.id)
    if u and u['is_banned']:
        await update.message.reply_text("已封禁")
        return
    keyboard = [
        [InlineKeyboardButton("商品列表", callback_data="shop")],
        [InlineKeyboardButton("我的订单", callback_data="my_orders"),
         InlineKeyboardButton("联系客服", url=f"https://t.me/{SUPPORT_CONTACT.lstrip('@')}")],
    ]
    await update.message.reply_text(WELCOME_TEXT, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)


async def shop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_shop(update, context, via_query=False)


async def shop_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await _show_shop(update, context, via_query=True)


async def _show_shop(update, context, via_query):
    products = db.get_all_products()
    categories = {}
    for p in products:
        categories.setdefault(p['category'], []).append(p)

    text = "商品列表\n\n"
    keyboard = []
    for cat, items in categories.items():
        text += f"[{cat}]\n"
        for p in items:
            icon = "AUTO" if p['auto_deliver'] else "MANUAL"
            stock = f"库存:{p['stock_count']}" if p['auto_deliver'] else "人工"
            text += f"{icon} {p['name']} - {p['price']}U ({stock})\n"
            keyboard.append([InlineKeyboardButton(
                f"{'⚡' if p['auto_deliver'] else '👤'} {p['name']} {p['price']}U",
                callback_data=f"product_{p['id']}"
            )])
        text += "\n"
    keyboard.append([InlineKeyboardButton("返回首页", callback_data="home")])

    if not products:
        text = "暂无商品"

    msg = update.callback_query.message if via_query else update.message
    await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[1])
    p = db.get_product(product_id)
    if not p or not p['is_active']:
        await query.message.reply_text("商品不存在")
        return

    deliver = "⚡ 自动发货" if p['auto_deliver'] else "👤 人工发货"
    stock = f"库存 {p['stock_count']} 件" if p['auto_deliver'] else "人工处理"
    text = f"*{p['name']}*\n\n{p['description'] or '暂无描述'}\n\n价格: *{p['price']} USDT*\n发货: {deliver}\n库存: {stock}"

    if p['auto_deliver'] and p['stock_count'] == 0:
        text += "\n\n⚠️ 暂时缺货"
        kb = [[InlineKeyboardButton("返回", callback_data="shop")]]
    else:
        kb = [
            [InlineKeyboardButton("立即购买", callback_data=f"buy_{product_id}")],
            [InlineKeyboardButton("返回", callback_data="shop")]
        ]
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)


async def buy_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    product_id = int(query.data.split("_")[1])
    p = db.get_product(product_id)

    if not p or not p['is_active']:
        await query.message.reply_text("商品不存在或已下架")
        return
    u = db.get_user(user.id)
    if u and u['is_banned']:
        await query.message.reply_text("账号已封禁")
        return
    if p['auto_deliver'] and p['stock_count'] == 0:
        await query.message.reply_text("已售罄")
        return

    order_id = db.create_order(user.id, user.username or user.first_name, p['id'], p['name'], p['price'])
    db.update_order(order_id, payment_address=USDT_WALLET)

    pay_info = get_payment_info(p['price'])
    text = f"订单已创建！\n\n📋 订单号: #{order_id}\n📦 商品: {p['name']}\n💰 金额: {p['price']} USDT\n\n{pay_info}\n\n付款后点击下方按钮提交"
    kb = [
        [InlineKeyboardButton("✅ 我已付款", callback_data=f"paid_{order_id}")],
        [InlineKeyboardButton("❌ 取消订单", callback_data=f"cancel_{order_id}")]
    ]
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)


async def confirm_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[1])
    order = db.get_order(order_id)

    if not order:
        await query.message.reply_text("订单不存在")
        return
    if order['user_id'] != query.from_user.id:
        await query.message.reply_text("无权操作")
        return
    if order['status'] != 'pending':
        await query.message.reply_text(f"当前状态: {order['status']}")
        return

    db.update_order(order_id, status='confirming')
    p = db.get_product(order['product_id'])
    deliver_type = '自动' if p and p['auto_deliver'] else '人工'

    admin_text = f"🔔 新付款确认请求\n\n订单: #{order_id}\n用户: {order['username']} ({order['user_id']})\n商品: {order['product_name']}\n金额: {order['amount']} USDT\n发货: {deliver_type}"
    kb = [[
        InlineKeyboardButton("✅ 确认并发货", callback_data=f"admin_confirm_{order_id}"),
        InlineKeyboardButton("❌ 拒绝", callback_data=f"admin_reject_{order_id}")
    ]]
    for aid in ADMIN_IDS:
        try:
            await context.bot.send_message(aid, admin_text, reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            print(f"通知管理员失败: {e}")

    await query.message.reply_text(f"已提交付款确认！\n\n订单 #{order_id} 等待管理员确认，请耐心等待。\n如需加急请联系 {SUPPORT_CONTACT}")


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[1])
    order = db.get_order(order_id)
    if not order or order['user_id'] != query.from_user.id:
        await query.message.reply_text("无权操作")
        return
    if order['status'] != 'pending':
        await query.message.reply_text("只有待付款订单可取消")
        return
    db.update_order(order_id, status='cancelled')
    await query.message.reply_text(f"订单 #{order_id} 已取消")


async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user = query.from_user
        reply = query.message.reply_text
    else:
        user = update.effective_user
        reply = update.message.reply_text

    orders = db.get_user_orders(user.id)
    if not orders:
        await reply("暂无订单")
        return

    status_map = {
        'pending': '⏳待付款', 'confirming': '🔍确认中', 'paid': '✅已付款',
        'delivered': '📬已发货', 'cancelled': '❌已取消', 'rejected': '🚫已拒绝'
    }
    text = "我的订单（最近10条）\n\n"
    for o in orders:
        s = status_map.get(o['status'], o['status'])
        text += f"#{o['id']} {o['product_name']} {o['amount']}U {s}\n"
        if o['status'] == 'delivered' and o['card_content']:
            text += f"   └ 卡密: {o['card_content']}\n"
    await reply(text)


async def home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("商品列表", callback_data="shop")],
        [InlineKeyboardButton("我的订单", callback_data="my_orders"),
         InlineKeyboardButton("联系客服", url=f"https://t.me/{SUPPORT_CONTACT.lstrip('@')}")],
    ]
    await query.message.reply_text(WELCOME_TEXT, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
