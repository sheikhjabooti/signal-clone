"""Disposable live connections. Saved messages never depend on this registry."""
import asyncio
from dataclasses import dataclass, field
from fastapi import WebSocket
from .security import Identity


@dataclass(eq=False)
class Peer:
    websocket: WebSocket
    identity: Identity
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=128))


class Hub:
    def __init__(self):
        self.peers: set[Peer] = set()

    def online(self, uid: int) -> bool:
        return any(peer.identity.user_id == uid for peer in self.peers)

    def add(self, websocket: WebSocket, identity: Identity) -> Peer:
        peer = Peer(websocket, identity)
        self.peers.add(peer)
        return peer

    def remove(self, peer: Peer):
        self.peers.discard(peer)

    async def publish(self, user_ids: list[int], event: dict):
        audience = set(user_ids)
        for peer in list(self.peers):
            if peer.identity.user_id not in audience:
                continue
            try:
                peer.queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop the connection, not a persisted message. The client resyncs.
                self.peers.discard(peer)
                await self._close(peer, 1013)

    async def broadcast_presence(self, uid: int):
        # Presence is intentionally approximate. No message content is broadcast.
        await self.publish([p.identity.user_id for p in self.peers], {
            "type": "presence.changed", "user_id": uid, "online": self.online(uid)
        })

    async def writer(self, peer: Peer):
        while True:
            event = await peer.queue.get()
            await asyncio.wait_for(peer.websocket.send_json(event), timeout=10)

    async def revoke(self, token_hash: str):
        for peer in list(self.peers):
            if peer.identity.token_hash == token_hash:
                self.peers.discard(peer)
                await self._close(peer, 4401)

    async def close_all(self):
        for peer in list(self.peers):
            await self._close(peer, 1012)
        self.peers.clear()

    @staticmethod
    async def _close(peer: Peer, code: int):
        try:
            await asyncio.wait_for(peer.websocket.close(code=code), timeout=2)
        except (RuntimeError, TimeoutError):
            pass
