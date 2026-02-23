"""
波场 USDT (TRC20) 收款检测模块
使用 TronGrid 公共 API 查询链上转账记录
"""
import requests
import time
import config

TRON_USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # TRC20 USDT 合约地址

def get_recent_usdt_transfers(wallet_address, limit=20):
    """获取钱包最近的 USDT TRC20 转账记录"""
    url = f"https://api.trongrid.io/v1/accounts/{wallet_address}/transactions/trc20"
    headers = {}
    if config.TRONGRID_API_KEY:
        headers["TRON-PRO-API-KEY"] = config.TRONGRID_API_KEY
    params = {
        "limit": limit,
        "contract_address": TRON_USDT_CONTRACT,
        "only_to": "true"
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        print(f"[TronGrid] 查询失败: {e}")
        return []

def check_payment(order_id, expected_amount, created_timestamp):
    """
    检查是否收到对应金额的 USDT
    order_id: 订单ID（用于日志）
    expected_amount: 期望收款金额（USDT浮点数）
    created_timestamp: 订单创建时间戳（Unix秒），只检测此时间之后的转账
    返回: True / False
    """
    transfers = get_recent_usdt_transfers(config.USDT_WALLET)
    for tx in transfers:
        try:
            tx_time = int(tx.get("block_timestamp", 0)) / 1000  # 毫秒转秒
            if tx_time < created_timestamp:
                continue
            value = int(tx.get("value", 0)) / 1_000_000  # USDT 精度 6
            if abs(value - expected_amount) <= config.AMOUNT_TOLERANCE:
                print(f"[订单#{order_id}] 检测到到账 {value} USDT")
                return True
        except Exception as e:
            print(f"[TronGrid] 解析交易异常: {e}")
    return False
