import unittest

from pycodex.exec import (
    DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE,
    OPCODE_CLOSE,
    REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE,
    WebSocketProtocolError,
    build_websocket_handshake_request,
    decode_websocket_frame,
    decode_websocket_text_message,
    encode_websocket_close_frame,
    encode_websocket_frame,
    encode_websocket_text_message,
    generate_websocket_key,
    read_websocket_frame,
    read_websocket_text_message,
    validate_websocket_handshake_response,
    websocket_accept_key,
    websocket_close_code_and_reason,
    websocket_close_reason,
    websocket_frame_event,
)


class ChunkSocket:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)

    def recv(self, byte_count: int) -> bytes:
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if len(chunk) <= byte_count:
            return chunk
        self.chunks.insert(0, chunk[byte_count:])
        return chunk[:byte_count]


class ExecWebSocketTests(unittest.TestCase):
    def test_handshake_key_and_accept_match_rfc_shape(self) -> None:
        self.assertEqual(generate_websocket_key(bytes(range(16))), "AAECAwQFBgcICQoLDA0ODw==")
        self.assertEqual(
            websocket_accept_key("dGhlIHNhbXBsZSBub25jZQ=="),
            "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=",
        )
        self.assertEqual(DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE, REMOTE_APP_SERVER_MAX_WEBSOCKET_MESSAGE_SIZE)
        with self.assertRaisesRegex(ValueError, "exactly 16 bytes"):
            generate_websocket_key(b"short")

    def test_handshake_request_preserves_endpoint_and_authorization_shape(self) -> None:
        request = build_websocket_handshake_request(
            "wss://codex.example:8443/rpc?thread=1",
            "AAECAwQFBgcICQoLDA0ODw==",
            auth_token="token-1",
        ).decode("ascii")

        self.assertEqual(
            request,
            "\r\n".join(
                [
                    "GET /rpc?thread=1 HTTP/1.1",
                    "Host: codex.example:8443",
                    "Upgrade: websocket",
                    "Connection: Upgrade",
                    "Sec-WebSocket-Key: AAECAwQFBgcICQoLDA0ODw==",
                    "Sec-WebSocket-Version: 13",
                    "Authorization: Bearer token-1",
                    "",
                    "",
                ]
            ),
        )
        self.assertIn(
            "Host: localhost\r\n",
            build_websocket_handshake_request(
                "ws://localhost/rpc",
                "AAECAwQFBgcICQoLDA0ODw==",
            ).decode("ascii"),
        )
        with self.assertRaisesRegex(ValueError, "unsupported scheme"):
            build_websocket_handshake_request("http://localhost/rpc", "key")

    def test_handshake_response_validation_matches_websocket_upgrade_rules(self) -> None:
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: keep-alive, Upgrade\r\n"
            "Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n"
            "\r\n"
            "ignored-body"
        )

        parsed = validate_websocket_handshake_response(response, key)

        self.assertEqual(parsed.status_code, 101)
        self.assertEqual(parsed.reason, "Switching Protocols")
        self.assertEqual(parsed.header("connection"), "keep-alive, Upgrade")
        with self.assertRaisesRegex(WebSocketProtocolError, "invalid Sec-WebSocket-Accept"):
            validate_websocket_handshake_response(response.replace("s3p", "bad"), key)
        with self.assertRaisesRegex(WebSocketProtocolError, "status 403 Forbidden"):
            validate_websocket_handshake_response("HTTP/1.1 403 Forbidden\r\n\r\n", key)

    def test_text_frame_round_trip_covers_masked_client_and_unmasked_server_frames(self) -> None:
        masked = encode_websocket_text_message(
            '{"id":1}',
            mask_key=b"\x01\x02\x03\x04",
        )
        decoded, remaining = decode_websocket_text_message(masked + b"tail", expect_masked=True)
        self.assertEqual(decoded, '{"id":1}')
        self.assertEqual(remaining, b"tail")

        unmasked = encode_websocket_text_message("hello", mask=False)
        decoded_server, server_remaining = decode_websocket_text_message(unmasked, expect_masked=False)
        self.assertEqual(decoded_server, "hello")
        self.assertEqual(server_remaining, b"")

        with self.assertRaisesRegex(WebSocketProtocolError, "expected unmasked"):
            decode_websocket_text_message(masked)
        with self.assertRaisesRegex(WebSocketProtocolError, "configured max message size"):
            decode_websocket_frame(
                encode_websocket_text_message("abcdef", mask=False),
                max_message_size=5,
            )

    def test_frame_encoding_handles_extended_lengths_and_control_limits(self) -> None:
        payload = "x" * 126
        frame = encode_websocket_text_message(payload, mask=False)

        self.assertEqual(frame[:4], b"\x81\x7e\x00\x7e")
        self.assertEqual(decode_websocket_text_message(frame)[0], payload)
        with self.assertRaisesRegex(WebSocketProtocolError, "control frames"):
            encode_websocket_frame(b"x" * 126, opcode=OPCODE_CLOSE, mask=False)
        with self.assertRaisesRegex(EOFError, "incomplete websocket frame"):
            decode_websocket_frame(b"\x81")

    def test_socket_frame_reader_handles_split_server_text_and_close_frames(self) -> None:
        frame = encode_websocket_text_message('{"method":"turn/completed"}', mask=False)
        sock = ChunkSocket([frame[:1], frame[1:2], frame[2:5], frame[5:]])

        self.assertEqual(read_websocket_text_message(sock), '{"method":"turn/completed"}')

        close_frame = encode_websocket_frame(b"going away", opcode=OPCODE_CLOSE, mask=False)
        close = read_websocket_frame(ChunkSocket([close_frame[:2], close_frame[2:]]))
        self.assertEqual(close.opcode, OPCODE_CLOSE)
        self.assertEqual(close.payload, b"going away")

    def test_socket_frame_reader_enforces_mask_and_eof_rules(self) -> None:
        masked = encode_websocket_text_message("client text", mask_key=b"\x01\x02\x03\x04")
        self.assertEqual(
            read_websocket_text_message(ChunkSocket([masked]), expect_masked=True),
            "client text",
        )
        with self.assertRaisesRegex(WebSocketProtocolError, "expected unmasked"):
            read_websocket_frame(ChunkSocket([masked]))
        with self.assertRaisesRegex(EOFError, "closed while reading frame"):
            read_websocket_frame(ChunkSocket([b"\x81"]))
        with self.assertRaisesRegex(WebSocketProtocolError, "configured max message size"):
            read_websocket_frame(
                ChunkSocket([encode_websocket_text_message("abcdef", mask=False)]),
                max_message_size=5,
            )

    def test_frame_event_classification_matches_remote_loop_branches(self) -> None:
        text = read_websocket_frame(
            ChunkSocket([encode_websocket_text_message('{"id":1}', mask=False)])
        )
        close = read_websocket_frame(
            ChunkSocket([encode_websocket_close_frame(code=1001, reason="going away", mask=False)])
        )
        empty_close = read_websocket_frame(ChunkSocket([encode_websocket_close_frame(mask=False)]))
        binary = read_websocket_frame(ChunkSocket([encode_websocket_frame(b"\x00\x01", opcode=0x2, mask=False)]))

        self.assertEqual(websocket_frame_event(text).to_mapping(), {"kind": "text", "text": '{"id":1}'})
        self.assertEqual(websocket_close_code_and_reason(close), (1001, "going away"))
        self.assertEqual(websocket_close_reason(close), "going away")
        self.assertEqual(
            websocket_frame_event(close).to_mapping(),
            {"kind": "close", "closeCode": 1001, "closeReason": "going away"},
        )
        self.assertEqual(websocket_close_reason(empty_close), "connection closed")
        self.assertEqual(
            websocket_frame_event(empty_close).to_mapping(),
            {"kind": "close", "closeReason": "connection closed"},
        )
        self.assertEqual(websocket_frame_event(binary).to_mapping(), {"kind": "ignored", "ignoredOpcode": 2})
        with self.assertRaisesRegex(WebSocketProtocolError, "two-byte status code"):
            websocket_frame_event(read_websocket_frame(ChunkSocket([encode_websocket_frame(b"x", opcode=0x8, mask=False)])))


if __name__ == "__main__":
    unittest.main()
