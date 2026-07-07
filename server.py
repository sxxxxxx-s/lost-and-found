# -*- coding: utf-8 -*-
"""实验四本地入口：统一启动微服务并提供聊天 API。"""

import threading
from http.server import ThreadingHTTPServer

import services.handover_service as handover_service
import tools
from services.claim_service import ClaimHandler
from services.handover_service import HandoverHandler
from services.item_service import ItemHandler
from web_server import WebHandler, create_web_server


def stop_servers(servers):
    """停止由当前进程启动的 HTTP 服务。"""
    for server in servers:
        server.shutdown()
        server.server_close()


def start_business_services(ports=(8001, 8002, 8003)):
    """启动三个业务微服务并把实际地址注入工具层。"""
    specs = [
        (ItemHandler, ports[0]),
        (ClaimHandler, ports[1]),
        (HandoverHandler, ports[2]),
    ]
    servers = []
    try:
        for handler, port in specs:
            server = ThreadingHTTPServer(("127.0.0.1", port), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            servers.append(server)
    except Exception:
        stop_servers(servers)
        raise

    urls = [
        f"http://127.0.0.1:{server.server_port}" for server in servers
    ]
    tools.ITEM_URL, tools.CLAIM_URL, tools.HANDOVER_URL = urls
    handover_service.CLAIM_URL = tools.CLAIM_URL
    return servers


def main():
    services = start_business_services()
    web_server = create_web_server()
    try:
        print("寻迹校园已启动：http://localhost:8000")
        web_server.serve_forever()
    finally:
        web_server.server_close()
        stop_servers(services)


if __name__ == "__main__":
    main()
