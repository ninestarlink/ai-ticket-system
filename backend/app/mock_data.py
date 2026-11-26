from typing import Any, Dict

# 题目要求的模拟业务数据：只有这两张订单（A9999 视为不存在）
ORDERS: Dict[str, Dict[str, Any]] = {
    "A1001": {
        "order_id": "A1001",
        "status": "已发货",
        "product": "无线降噪耳机 ×1",
        "amount": 199,
        "created_at": "2026-03-02 10:20:31",
    },
    "A1002": {
        "order_id": "A1002",
        "status": "待发货",
        "product": "智能手环 ×2",
        "amount": 598,
        "created_at": "2026-03-05 09:12:10",
    },
}

PAYMENTS: Dict[str, list] = {
    "A1001": [
        {
            "payment_id": "PAY-A1001-01",
            "amount": 199,
            "currency": "CNY",
            "status": "支付成功",
            "channel": "微信支付",
            "paid_at": "2026-03-02 10:21:08",
        }
    ],
    "A1002": [
        {
            "payment_id": "PAY-A1002-01",
            "amount": 299,
            "currency": "CNY",
            "status": "支付成功",
            "channel": "微信支付",
            "paid_at": "2026-03-05 09:12:44",
        },
        {
            "payment_id": "PAY-A1002-02",
            "amount": 299,
            "currency": "CNY",
            "status": "支付成功",
            "channel": "支付宝",
            "paid_at": "2026-03-05 09:13:02",
        },
    ],
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "query_order",
            "description": "根据订单号查询订单状态。只读工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号，例如 A1001",
                    }
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_payment",
            "description": "根据订单号查询支付记录。只读工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号，例如 A1002",
                    }
                },
                "required": ["order_id"],
            },
        },
    },
]


def _order_not_found(order_id: str) -> Dict[str, Any]:
    return {
        "ok": True,
        "order_id": order_id,
        "exists": False,
        "message": "订单不存在",
    }


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """执行只读工具，数据只来自本文件的模拟数据。"""
    order_id = str(arguments.get("order_id", "")).strip().upper()

    if not order_id:
        return {"ok": False, "error": "缺少订单号 order_id"}

    if name == "query_order":
        order = ORDERS.get(order_id)
        if not order:
            return _order_not_found(order_id)
        return {
            "ok": True,
            "order_id": order_id,
            "exists": True,
            "order": order,
        }

    if name == "query_payment":
        payments = PAYMENTS.get(order_id)
        if not payments:
            return _order_not_found(order_id)
        return {
            "ok": True,
            "order_id": order_id,
            "exists": True,
            "count": len(payments),
            "total_amount": sum(item["amount"] for item in payments),
            "payments": payments,
        }

    return {"ok": False, "error": f"未知工具：{name}"}
