import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 在这里硬编码您的 Emby 服务器地址 ---
EMBY_HOST = "192.168.50.12"
EMBY_PORT = 8096
# --- 代理监听的端口 ---
PROXY_PORT = 8999

async def pipe(reader, writer, direction):
    try:
        while not reader.at_eof():
            data = await reader.read(4096)
            if not data:
                break
            writer.write(data)
            await writer.drain()
            # logging.info(f"Forwarded {len(data)} bytes in direction {direction}")
    except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
        pass # 连接关闭是正常现象
    finally:
        if not writer.is_closing():
            writer.close()
            await writer.wait_closed()

async def handle_client(client_reader, client_writer):
    client_addr = client_writer.get_extra_info('peername')
    logging.info(f"Accepted connection from {client_addr}")
    
    try:
        server_reader, server_writer = await asyncio.open_connection(EMBY_HOST, EMBY_PORT)
        logging.info(f"Connected to upstream Emby server at {EMBY_HOST}:{EMBY_PORT}")
    except Exception as e:
        logging.error(f"Failed to connect to upstream server: {e}")
        client_writer.close()
        await client_writer.wait_closed()
        return

    # 并发处理双向数据流
    await asyncio.gather(
        pipe(client_reader, server_writer, "C->S"),
        pipe(server_reader, client_writer, "S->C")
    )

    logging.info(f"Connection from {client_addr} closed.")

async def main():
    server = await asyncio.start_server(handle_client, '0.0.0.0', PROXY_PORT)
    addr = server.sockets[0].getsockname()
    logging.info(f'Serving on {addr}')

    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Shutting down.")