#!/usr/bin/env python3
"""
WebRTC signaling server with integrated HTTPS server and dynamic JS generation.
"""
import os
import sys
import ssl
import logging
import asyncio
import argparse
import http.server
import threading
from websockets.server import serve
from websockets.exceptions import ConnectionClosed

class WebRTCSimpleServer:
    def __init__(self, options):
        # Global data
        self.peers = dict()
        self.sessions = dict()
        self.rooms = dict()

        # Options
        self.addr = options.addr
        self.port = options.port
        self.web_port = options.web_port
        self.keepalive_timeout = options.keepalive_timeout
        self.disable_ssl = options.disable_ssl
        self.health_path = options.health
        self.certfile = options.certfile
        self.keyfile = options.keyfile
        # [Previous initialization code remains the same...]
        self.web_root = options.web_root or os.path.dirname(os.path.abspath(__file__))
        
    # [Keep all your existing WebSocket handler methods...]
    async def health_check(self, path, request_headers):
        if path == self.health_path:
            return http.HTTPStatus.OK, [], b"OK\n"
        return None
    
    async def recv_msg_ping(self, websocket, raddr):
        """Wait for a message and send a ping to keep the connection alive."""
        msg = None
        while msg is None:
            try:
                msg = await asyncio.wait_for(websocket.recv(), self.keepalive_timeout)
            except asyncio.TimeoutError:
                print(f"Sending keepalive ping to {raddr}")
                await websocket.ping()
        return msg

    async def cleanup_session(self, uid):
        """Clean up a session."""
        if uid in self.sessions:
            other_id = self.sessions[uid]
            del self.sessions[uid]
            print(f"Cleaned up {uid} session")
            if other_id in self.sessions:
                del self.sessions[other_id]
                print(f"Also cleaned up {other_id} session")
                if other_id in self.peers:
                    print(f"Closing connection to {other_id}")
                    wso, _, _ = self.peers[other_id]
                    del self.peers[other_id]
                    await wso.close()

    async def cleanup_room(self, uid, room_id):
        """Clean up a room."""
        if room_id not in self.rooms or uid not in self.rooms[room_id]:
            return
        self.rooms[room_id].remove(uid)
        for pid in self.rooms[room_id]:
            wsp, _, _ = self.peers[pid]
            msg = f"ROOM_PEER_LEFT {uid}"
            print(f"room {room_id}: {uid} -> {pid}: {msg}")
            await wsp.send(msg)

    async def remove_peer(self, uid):
        """Remove a peer and clean up their sessions/rooms."""
        await self.cleanup_session(uid)
        if uid in self.peers:
            ws, raddr, status = self.peers[uid]
            if status and status != "session":
                await self.cleanup_room(uid, status)
            del self.peers[uid]
            await ws.close()
            print(f"Disconnected from peer {uid} at {raddr}")

    async def connection_handler(self, websocket, uid):
        """Handle a WebSocket connection."""
        raddr = websocket.remote_address
        peer_status = None
        self.peers[uid] = (websocket, raddr, peer_status)
        print(f"Registered peer {uid} at {raddr}")
        while True:
            msg = await self.recv_msg_ping(websocket, raddr)
            peer_status = self.peers[uid][2]
            if peer_status is not None:
                if peer_status == "session":
                    other_id = self.sessions[uid]
                    wso, _, _ = self.peers[other_id]
                    print(f"{uid} -> {other_id}: {msg}")
                    await wso.send(msg)
                elif peer_status:
                    if msg.startswith("ROOM_PEER_MSG"):
                        _, other_id, msg = msg.split(maxsplit=2)
                        if other_id not in self.peers:
                            await websocket.send(f"ERROR peer {other_id} not found")
                            continue
                        wso, _, status = self.peers[other_id]
                        if status != peer_status:
                            await websocket.send(f"ERROR peer {other_id} is not in the room")
                            continue
                        msg = f"ROOM_PEER_MSG {uid} {msg}"
                        print(f"room {peer_status}: {uid} -> {other_id}: {msg}")
                        await wso.send(msg)
                    elif msg == "ROOM_PEER_LIST":
                        room_peers = " ".join([pid for pid in self.rooms[peer_status] if pid != uid])
                        msg = f"ROOM_PEER_LIST {room_peers}"
                        print(f"room {peer_status}: -> {uid}: {msg}")
                        await websocket.send(msg)
                    else:
                        await websocket.send("ERROR invalid msg, already in room")
                        continue
                else:
                    raise AssertionError(f"Unknown peer status {peer_status}")
            elif msg.startswith("SESSION"):
                _, callee_id = msg.split(maxsplit=1)
                if callee_id not in self.peers:
                    await websocket.send(f"ERROR peer {callee_id} not found")
                    continue
                if peer_status is not None:
                    await websocket.send(f"ERROR peer {callee_id} busy")
                    continue
                await websocket.send("SESSION_OK")
                wsc, _, _ = self.peers[callee_id]
                print(f"Session from {uid} ({raddr}) to {callee_id} ({wsc.remote_address})")
                self.peers[uid] = (websocket, raddr, "session")
                self.sessions[uid] = callee_id
                self.peers[callee_id] = (wsc, wsc.remote_address, "session")
                self.sessions[callee_id] = uid
            elif msg.startswith("ROOM"):
                _, room_id = msg.split(maxsplit=1)
                if room_id == "session" or room_id.split() != [room_id]:
                    await websocket.send(f"ERROR invalid room id {room_id}")
                    continue
                if room_id not in self.rooms:
                    self.rooms[room_id] = set()
                room_peers = " ".join([pid for pid in self.rooms[room_id]])
                await websocket.send(f"ROOM_OK {room_peers}")
                self.peers[uid] = (websocket, raddr, room_id)
                self.rooms[room_id].add(uid)
                for pid in self.rooms[room_id]:
                    if pid == uid:
                        continue
                    wsp, _, _ = self.peers[pid]
                    msg = f"ROOM_PEER_JOINED {uid}"
                    print(f"room {room_id}: {uid} -> {pid}: {msg}")
                    await wsp.send(msg)
            else:
                print(f"Ignoring unknown message {msg} from {uid}")

    async def hello_peer(self, websocket):
        """Exchange hello and register the peer."""
        raddr = websocket.remote_address
        hello = await websocket.recv()
        hello, uid = hello.split(maxsplit=1)
        if hello != "HELLO":
            await websocket.close(code=1002, reason="invalid protocol")
            raise Exception(f"Invalid hello from {raddr}")
        if not uid or uid in self.peers or uid.split() != [uid]:
            await websocket.close(code=1002, reason="invalid peer uid")
            raise Exception(f"Invalid uid {uid} from {raddr}")
        await websocket.send("HELLO")
        return uid

    async def handler(self, websocket):
        """Handle incoming WebSocket connections."""
        raddr = websocket.remote_address
        print(f"Connected to {raddr}")
        try:
            uid = await self.hello_peer(websocket)
            await self.connection_handler(websocket, uid)
        except ConnectionClosed:
            print(f"Connection to peer {raddr} closed")
        finally:
            await self.remove_peer(uid)

    def run_https_server(self):
        """Run the HTTPS server in a separate thread."""
        handler = http.server.SimpleHTTPRequestHandler
        httpd = http.server.HTTPServer((self.addr, self.web_port), handler)
        
        if not self.disable_ssl:
            if not os.path.exists(self.certfile) or not os.path.exists(self.keyfile):
                print(f"Certificate files not found: {self.certfile}, {self.keyfile}")
                sys.exit(1)
                
            httpd.socket = ssl.wrap_socket(
                httpd.socket,
                server_side=True,
                certfile=self.certfile,
                keyfile=self.keyfile,
                ssl_version=ssl.PROTOCOL_TLS
            )
            print(f"Serving HTTPS on https://{self.addr}:{self.web_port}")
        else:
            print(f"Serving HTTP on http://{self.addr}:{self.web_port}")
            
        httpd.serve_forever()

    async def run_websocket_server(self):
        """Run the WebSocket server."""
        ssl_context = None if self.disable_ssl else self.get_ssl_ctx()
        
        async with serve(
            self.handler,
            self.addr,
            self.port,
            ssl=ssl_context,
        ):
            proto = "wss" if ssl_context else "ws"
            print(f"WebSocket server running on {proto}://{self.addr}:{self.port}")
            await asyncio.Future()  # Run forever

    def get_ssl_ctx(self):
        """Create an SSL context for WebSocket server."""
        if not os.path.exists(self.certfile) or not os.path.exists(self.keyfile):
            print(f"Certificate files not found: {self.certfile}, {self.keyfile}")
            sys.exit(1)
            
        sslctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        sslctx.load_cert_chain(certfile=self.certfile, keyfile=self.keyfile)
        sslctx.check_hostname = False
        sslctx.verify_mode = ssl.CERT_NONE
        return sslctx

    def run(self):
        """Start both HTTP/HTTPS and WebSocket servers."""
        # Start HTTPS server in a separate thread
        http_thread = threading.Thread(target=self.run_https_server, daemon=True)
        http_thread.start()
        
        # Start WebSocket server in main thread
        asyncio.run(self.run_websocket_server())


    def generate_webrtc_js(self):
        """Generate webrtc.js with current server configuration."""
        js_content = f"""
    var ws_server = "{self.addr}";
    var ws_port = "{self.port}";
        """

        js_path = os.path.join(self.web_root, "webrtc.js")
        template_js_path = os.path.join(self.web_root, "webrtc_template.js")
        with open(js_path, "w") as f:
            f.write(js_content)
            with open (template_js_path) as r:
                for line in r.readlines():
                    f.write(line)
        print(f"Generated webrtc.js with server address: {self.addr}:{self.port}")

    def run_https_server(self):
        """Run the HTTPS server with dynamic JS generation."""
        self.generate_webrtc_js()  # Generate JS file before starting server
        # Create a reference to the outer self for use in the handler class
        outer_self = self
        class RequestHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self2, *args, **kwargs):
                super().__init__(*args, directory=outer_self.web_root, **kwargs)
            
            def do_GET(self2):
                # Regenerate JS file on each request (optional)
                if self2.path == "/webrtc.js":
                    print("huy")
                    outer_self.generate_webrtc_js()
                super().do_GET()

        handler = RequestHandler
        #handler.server = self  # Pass server instance to handler
        
        httpd = http.server.HTTPServer((self.addr, self.web_port), handler)
        
        if not self.disable_ssl:
            httpd.socket = ssl.wrap_socket(
                httpd.socket,
                server_side=True,
                certfile=self.certfile,
                keyfile=self.keyfile,
                ssl_version=ssl.PROTOCOL_TLS
            )
            print(f"Serving HTTPS on https://{self.addr}:{self.web_port}")
        else:
            print(f"Serving HTTP on http://{self.addr}:{self.web_port}")
            
        httpd.serve_forever()

    # [Rest of your class methods remain the same...]

def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="WebRTC signaling server with integrated web server"
    )
    parser.add_argument("--addr", default="0.0.0.0", 
                       help="Address to listen on (0.0.0.0 for all interfaces)")
    parser.add_argument("--port", default=9000, type=int, 
                       help="WebSocket server port")
    parser.add_argument("--web-port", default=8000, type=int,
                       help="HTTP/HTTPS server port")
    parser.add_argument("--web-root", default=None,
                       help="Directory to serve web files from")    
    parser.add_argument("--keepalive-timeout", default=30, type=int, 
                       help="Keepalive timeout (seconds)")
    parser.add_argument("--disable-ssl", action="store_true", 
                       help="Disable SSL (use HTTP/WS instead of HTTPS/WSS)")
    parser.add_argument("--health", default="/health", 
                       help="Health check route")
    parser.add_argument("--certfile", default="cert.pem",
                       help="SSL certificate file")
    parser.add_argument("--keyfile", default="key.pem",
                       help="SSL private key file")
    # [Rest of your argument parsing remains the same...]

    options = parser.parse_args()

    # [Rest of your main() code remains the same...]
    # Create certificate files if they don't exist
    if not options.disable_ssl and (
        not os.path.exists(options.certfile) or 
        not os.path.exists(options.keyfile)
    ):
        print("Generating self-signed certificates...")
        os.system(
            f"openssl req -x509 -newkey rsa:4096 -keyout {options.keyfile} "
            f"-out {options.certfile} -days 365 -nodes -subj '/CN={options.addr}'"
        )

    server = WebRTCSimpleServer(options)
    try:
        server.run()
    except KeyboardInterrupt:
        print("\nServer shutting down...")

if __name__ == "__main__":
    main()