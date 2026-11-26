import json


def tool_call(name: str, order_id: str, call_id: str = "call_1"):
    return {
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "name": name,
                "arguments": json.dumps({"order_id": order_id}, ensure_ascii=False),
            }
        ],
    }


def final(category: str, priority: str, summary: str, suggestion: str):
    return {
        "content": json.dumps(
            {
                "category": category,
                "priority": priority,
                "summary": summary,
                "suggestion": suggestion,
            },
            ensure_ascii=False,
        ),
        "tool_calls": [],
    }


LOW_CONSULT = final(
    "其他",
    "低",
    "客户咨询批量采购优惠",
    "建议客服组跟进，确认采购数量与预算后提供报价，不得编造具体折扣。",
)

HIGH_DUPLICATE = final(
    "支付与退款",
    "高",
    "订单 A1002 存在两笔成功支付",
    "已通过工具核实两笔成功支付，建议售后组人工核对并按流程发起退款审核，不得直接声称已退款。",
)

MEDIUM_SINGLE_PAYMENT = final(
    "支付与退款",
    "中",
    "订单 A1001 仅有一笔成功支付",
    "工具查询仅发现一笔成功支付，未发现重复扣款，需人工核实客户所述情况。",
)

MEDIUM_ORDER_QUERY = final(
    "其他",
    "中",
    "咨询订单 A1001 的物流进度",
    "订单 A1001 状态为已发货，建议客服组向客户同步物流进度。",
)
