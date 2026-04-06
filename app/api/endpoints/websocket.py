"""WebSocket endpoint for real-time network events."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import ws_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Client connects here to receive real-time events:
    - device_status_change
    - link_status_change
    - new_incident
    - rca_result
    - metric_update
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; client can also send commands
            data = await websocket.receive_text()
            # Echo back as acknowledgment
            await ws_manager.send_personal(websocket, "ack", {"message": data})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
