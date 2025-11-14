"""
Trading Agents 端到端演示脚本。

步骤：
1. 在本地启动一个简单的 HTTP 服务器，模拟外部研究服务。
2. 通过 TradingAgentsManager + REST adapter 请求研究数据。
3. 打印返回的研究包与单个 ResearchItem。

运行示例：
    python -m script.trading_agents_e2e --symbol AAPL
"""

from __future__ import annotations

import argparse
import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict

from chanlun_quant.ai.trading_agents import TradingAgentsManager
from chanlun_quant.config import Config
from datetime import datetime


@dataclass
class StubServer(threading.Thread):
    port: int
    response: Dict[str, object]
    httpd: HTTPServer | None = None

    def run(self) -> None:  # type: ignore[override]
        handler_response = self.response

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # type: ignore[override]
                length = int(self.headers.get("Content-Length", "0"))
                payload = self.rfile.read(length).decode("utf-8")
                print("[stub] 收到请求:", payload)
                data = json.dumps(handler_response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format, *args):  # type: ignore[override]
                return

        with HTTPServer(("127.0.0.1", self.port), Handler) as httpd:
            self.httpd = httpd
            httpd.serve_forever()

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Trading Agents + REST adapter 端到端示例。")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--port", type=int, default=8989)
    args = parser.parse_args()

    stub = StubServer(
        port=args.port,
        response={
            "analysis": [
                {
                    "symbol": args.symbol,
                    "ta_score": 0.72,
                    "ta_recommendation": "buy",
                    "ta_gate": True,
                    "risk_mult": 0.8,
                    "L_mult": 1.2,
                    "thesis": {
                        "technical": "多级别共振，5m/30m 均线多头排列。",
                        "fundamental": "盈利指引良好。",
                        "macro": "宏观环境中性。",
                    },
                    "valid_until": "2099-12-31T00:00:00Z",
                }
            ],
            "top_picks": [args.symbol],
            "metadata": {"source": "local_stub"},
        },
    )
    stub.daemon = True
    stub.start()

    cfg = Config(
        ta_enabled=True,
        ta_adapter_class="chanlun_quant.agents.adapters.rest.RESTTradingAgentAdapter",
        ta_kwargs_json=json.dumps(
            {
                "base_url": f"http://127.0.0.1:{args.port}",
                "timeout": 5.0,
            }
        ),
    )
    manager = TradingAgentsManager(cfg, now_fn=lambda: datetime.utcnow())

    try:
        packet, item = manager.get_research(
            symbol=args.symbol,
            structure_packet={"structure_summary": {"trend": "up"}},
            stage="INITIAL",
        )
    finally:
        stub.stop()

    print("ResearchPacket:", packet.to_dict() if packet else None)
    print("ResearchItem:", item.to_dict() if item else None)


if __name__ == "__main__":
    main()

