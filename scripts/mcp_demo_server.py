"""用于 MCP 协议验收的本地 MCP 服务，全部返回合成数据。"""

import argparse

from mcp.server import MCPServer


def build_server(kind: str) -> MCPServer:
    server = MCPServer(kind)

    if kind == "logistics":

        @server.tool()
        async def query_logistics(tracking_no: str) -> dict[str, str]:
            """根据物流号查询演示物流状态。"""
            return {
                "tracking_no": tracking_no,
                "status_code": "IN_TRANSIT",
                "status": "运输中",
            }

    elif kind == "aftersales":

        @server.tool()
        async def query_warranty(order_id: str) -> dict[str, str]:
            """根据订单号查询演示保修状态。"""
            return {
                "order_id": order_id,
                "warranty": "在保",
            }

        @server.tool()
        async def query_return_status(order_id: str) -> dict[str, str]:
            """根据订单号查询演示退货状态。"""
            return {
                "order_id": order_id,
                "return_status": "无退货记录",
            }

    else:
        raise ValueError(f"未知的演示服务：{kind}")

    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["logistics", "aftersales"])
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    server = build_server(args.kind)
    server.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=args.port,
    )


if __name__ == "__main__":
    main()
