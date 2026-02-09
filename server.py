# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Server script for running the DeerFlow API.
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

# 创建 logs 目录（如果不存在）
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# 配置日志格式
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
date_format = "%Y-%m-%d %H:%M:%S"

# 配置根日志记录器
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# 清除现有的处理器
root_logger.handlers.clear()

# 添加控制台处理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(log_format, date_format))
root_logger.addHandler(console_handler)

# 添加文件处理器（使用轮转日志，避免文件过大）
log_file = log_dir / "academic-agent.log"
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,  # 保留5个备份文件
    encoding="utf-8"
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(log_format, date_format))
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

# To ensure compatibility with Windows event loop issues when using Uvicorn and Asyncio Checkpointer,
# This is necessary because some libraries expect a selector-based event loop.
# This is a workaround for issues with Uvicorn and Watchdog on Windows.
# See:
# Since Python 3.8 the default on Windows is the Proactor event loop,
# which lacks add_reader/add_writer and can break libraries that expect selector-based I/O (e.g., some Uvicorn/Watchdog/stdio integrations).
# For compatibility, this forces the selector loop.
if os.name == "nt":
    logger.info("Setting Windows event loop policy for asyncio")
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def handle_shutdown(signum, frame):
    """Handle graceful shutdown on SIGTERM/SIGINT"""
    logger.info("Received shutdown signal. Starting graceful shutdown...")
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run the DeerFlow API server")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (default: True except on Windows)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Host to bind the server to (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Log level (default: info)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to log file (default: logs/deerflow.log). Set to empty string to disable file logging.",
    )

    args = parser.parse_args()

    # Determine reload setting
    reload = False
    if args.reload:
        reload = True

    # Check for DEBUG environment variable to override log level
    if os.getenv("DEBUG", "").lower() in ("true", "1", "yes"):
        log_level = "debug"
    else:
        log_level = args.log_level

    # 配置日志文件路径（如果指定）
    if args.log_file is not None:
        if args.log_file == "":
            # 禁用文件日志
            for handler in root_logger.handlers[:]:
                if isinstance(handler, RotatingFileHandler):
                    root_logger.removeHandler(handler)
                    handler.close()
        else:
            # 使用指定的日志文件
            custom_log_file = Path(args.log_file)
            custom_log_file.parent.mkdir(parents=True, exist_ok=True)
            # 移除旧的文件处理器
            for handler in root_logger.handlers[:]:
                if isinstance(handler, RotatingFileHandler):
                    root_logger.removeHandler(handler)
                    handler.close()
            # 添加新的文件处理器
            custom_file_handler = RotatingFileHandler(
                custom_log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8"
            )
            custom_file_handler.setLevel(logging.INFO)
            custom_file_handler.setFormatter(logging.Formatter(log_format, date_format))
            root_logger.addHandler(custom_file_handler)

    try:
        logger.info(f"Starting DeerFlow API server on {args.host}:{args.port}")
        logger.info(f"Log level: {log_level.upper()}")
        # 显示日志文件位置
        file_handlers = [h for h in root_logger.handlers if isinstance(h, RotatingFileHandler)]
        if file_handlers:
            logger.info(f"Log file: {file_handlers[0].baseFilename}")
        
        # 设置日志级别
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)
        root_logger.setLevel(numeric_level)
        # 更新所有处理器的日志级别
        for handler in root_logger.handlers:
            handler.setLevel(numeric_level)
        
        # Set the appropriate logging level for the src package if debug is enabled
        if log_level.lower() == "debug":
            logging.getLogger("src").setLevel(logging.DEBUG)
            logging.getLogger("langchain").setLevel(logging.DEBUG)
            logging.getLogger("langgraph").setLevel(logging.DEBUG)
            logger.info("DEBUG logging enabled for src, langchain, and langgraph packages - detailed diagnostic information will be logged")
        
        uvicorn.run(
            "src.server:app",
            host=args.host,
            port=args.port,
            reload=reload,
            log_level=log_level,
        )
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        sys.exit(1)
