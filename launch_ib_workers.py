#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
IB Workers Launcher - works with Windows multiprocessing
"""
import force_utf8

import sys
import os
import time
from multiprocessing import Process

sys.path.insert(0, r'F:\Cursor\chanlun\src')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from chanlun import rd
from chanlun.exchange.exchange_ib import CmdEnum, ib_res_hkey


def main():
    print("IB Workers Launcher")
    print("=" * 60)
    
    # Import worker function from module (必须在这里导入才能被pickle)
    from script.crontab.ib_worker_core import run_worker
    
    # 清空队列
    print("Clearing Redis queues...")
    for _k in [
        CmdEnum.SEARCH_STOCKS.value,
        CmdEnum.KLINES.value,
        CmdEnum.TICKS.value,
        CmdEnum.STOCK_INFO.value,
        CmdEnum.BALANCE.value,
        CmdEnum.POSITIONS.value,
        CmdEnum.ORDERS.value,
    ]:
        rd.Robj().delete(_k)
    
    h_keys = rd.Robj().keys(f"{ib_res_hkey}*")
    for _k in h_keys:
        rd.Robj().delete(_k)
    print(f"Cleared {len(h_keys)} result keys")
    
    # 启动5个worker进程
    processes = []
    client_ids = [21, 22, 23, 24, 25]
    
    print("\nStarting workers...")
    for client_id in client_ids:
        p = Process(target=run_worker, args=(client_id,), name=f"IBWorker-{client_id}")
        p.daemon = False
        p.start()
        print(f"  Worker {client_id} started (PID: {p.pid})")
        processes.append(p)
        time.sleep(1.5)  # 间隔启动避免同时连接IB Gateway
    
    print(f"\n✓ All {len(processes)} workers running!")
    print("  Press Ctrl+C to stop all workers")
    print("=" * 60)
    
    # 保持主进程运行
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\n\nShutting down workers...")
        for p in processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=5)
        print("All workers stopped.")


if __name__ == "__main__":
    main()


