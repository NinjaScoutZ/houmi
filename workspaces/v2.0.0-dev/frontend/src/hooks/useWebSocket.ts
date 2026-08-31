import { useEffect, useRef, useState } from 'react';
import { apiFetch, buildApiUrl, getAccessToken, getWebSocketOrigin } from '../api/runtime';

export interface WSMessage {
  type: string;
  [key: string]: any;
}

export function useWebSocket(projectId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    if (!projectId) {
      setTimeout(() => setIsConnected(false), 0);
      return;
    }
    const activeProjectId = projectId;

    async function connect() {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }

      let ticket: string | null = null;
      const accessToken = getAccessToken();
      if (accessToken) {
        try {
          const response = await apiFetch(buildApiUrl('/api/auth/ws-ticket'), {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${accessToken}`,
            },
            body: JSON.stringify({ project_id: activeProjectId }),
          });
          if (!response.ok) throw new Error(`WS ticket request failed (${response.status})`);
          const data = await response.json() as { ticket?: string };
          ticket = data.ticket || null;
        } catch (err) {
          console.error('Failed to obtain WebSocket ticket:', err);
          setIsConnected(false);
          return;
        }
      }

      const ticketQuery = ticket ? `?ticket=${encodeURIComponent(ticket)}` : '';
      const wsUrl = `${getWebSocketOrigin()}/ws/pipeline/${encodeURIComponent(activeProjectId)}${ticketQuery}`;

      console.log(`Connecting to WebSocket: ${wsUrl}`);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WSMessage;
          setLastMessage(data);
        } catch (err) {
          console.error('Failed to parse WS message:', err);
        }
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        setIsConnected(false);
        // Auto-reconnect after 3 seconds
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect();
        }, 3000);
      };

      ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        ws.close();
      };
    }

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [projectId]);

  return { isConnected, lastMessage };
}
