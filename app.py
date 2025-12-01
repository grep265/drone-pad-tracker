# -*- coding: utf-8 -*-
import websocket
import json
import cv2
import numpy as np
import time
import socket

# ---------------------------
# CONFIGURATION
# ---------------------------

DEBUG_DETECTION = False
isFlip = True

IMAGE_WIDTH = 96
IMAGE_HEIGHT = 96
IMAGE_CENTER = (IMAGE_WIDTH // 2, IMAGE_HEIGHT // 2)

ws_url = "ws://<your-rpi5-ip:4912>"   # EI WebSocket
HOST = "0.0.0.0"                     # Listen on ALL network interfaces
PORT = 5000

# ---------------------------
# PID PARAMETERS
# ---------------------------

Kp_x = 0.5
Ki_x = 0.01
Kd_x = 0.0

Kp_y = 0.05
Ki_y = 0.01
Kd_y = 0.0

pid_state = {
    "x_integral": 0,
    "y_integral": 0,
    "x_prev_error": 0,
    "y_prev_error": 0,
    "last_time": None
}

ERROR_THRESHOLD_X = 5   # pixels
ERROR_THRESHOLD_Y = 5   # pixels

# ---------------------------
# SERVO us RANGES
# ---------------------------

X_MIN_US = 500
X_MAX_US = 1100
Y_MIN_US = 500
Y_MAX_US = 1200

# Start position
servo_x_us = 650
servo_y_us = 900

SERVO_GAIN_X = 0.3
SERVO_GAIN_Y = 0.3

# ---------------------------
# SCANNING STATE
# ---------------------------

scanning_direction = 1             # 1 = right, -1 = left
SCAN_STEP = 2                      # us per frame
last_detection_time = 0
DETECTION_TIMEOUT = 2            # seconds before returning to scan mode

# ---------------------------
# TCP SERVER FOR ESP32
# ---------------------------

print("Waiting for ESP32...")
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((HOST, PORT))
server.listen(1)
conn, addr = server.accept()
print("ESP32 connected:", addr)

# ---------------------------
# PID CONTROLLER
# ---------------------------

def pid_controller(center_bb):
    now = time.time()
    dt = 0
    if pid_state["last_time"] is not None:
        dt = now - pid_state["last_time"]
    pid_state["last_time"] = now

    # Compute error
    error_x = IMAGE_CENTER[0] - center_bb[0]
    error_y = IMAGE_CENTER[1] - center_bb[1]

    # Deadzone: hold position if within threshold
    if abs(error_x) < ERROR_THRESHOLD_X:
        error_x = 0
        pid_state["x_integral"] = 0   # reset integral

    if abs(error_y) < ERROR_THRESHOLD_Y:
        error_y = 0
        pid_state["y_integral"] = 0   # reset integral

    if dt > 0:
        pid_state["x_integral"] += error_x * dt
        pid_state["y_integral"] += error_y * dt

    dx = (error_x - pid_state["x_prev_error"]) / dt if dt > 0 else 0
    dy = (error_y - pid_state["y_prev_error"]) / dt if dt > 0 else 0

    pid_state["x_prev_error"] = error_x
    pid_state["y_prev_error"] = error_y

    out_x = Kp_x*error_x + Ki_x*pid_state["x_integral"] + Kd_x*dx
    out_y = Kp_y*error_y + Ki_y*pid_state["y_integral"] + Kd_y*dy

    return out_x, out_y

# ---------------------------
# SEND SERVO VALUES TO ESP32
# ---------------------------

def send_servo_us(x_us, y_us):
    msg = f"X:{int(x_us)} Y:{int(y_us)}\n"
    conn.sendall(msg.encode())

    if DEBUG_DETECTION:
        print("TX ? ESP32:", msg.strip())

# ---------------------------
# SCANNING MODE (NO DETECTIONS)
# ---------------------------

def scanning_behavior():
    global servo_x_us, scanning_direction

    servo_x_us += scanning_direction * SCAN_STEP

    # Bounce at limits
    if servo_x_us >= X_MAX_US:
        servo_x_us = X_MAX_US
        scanning_direction = -1
    elif servo_x_us <= X_MIN_US:
        servo_x_us = X_MIN_US
        scanning_direction = 1

    # Keep Y steady
    send_servo_us(servo_x_us, servo_y_us)

# ---------------------------
# DRAW DETECTION + PID + SCAN
# ---------------------------

def handle_detection(bounding_boxes):
    global servo_x_us, servo_y_us, last_detection_time

    img = np.ones((IMAGE_HEIGHT, IMAGE_WIDTH, 3), dtype=np.uint8) * 255

    image_center_y = IMAGE_CENTER[1]
    if isFlip:
        image_center_y = IMAGE_HEIGHT - IMAGE_CENTER[1]

    if bounding_boxes and len(bounding_boxes) > 0:
        last_detection_time = time.time()

        for bb in bounding_boxes:
            x = int(bb["x"])
            y = int(bb["y"])
            w = int(bb["width"])
            h = int(bb["height"])

            if isFlip:
                y = IMAGE_HEIGHT - (y + h)

            center_bb = (int(x + w / 2), int(y + h / 2))

            if DEBUG_DETECTION:
                print(f"Bounding Box Center: {center_bb}, Image Center: {IMAGE_CENTER}")

            # PID controller
            out_x, out_y = pid_controller(center_bb)

            # Update servo commands
            servo_x_us -= out_x * SERVO_GAIN_X
            servo_y_us -= out_y * SERVO_GAIN_Y

            # Clamp
            servo_x_us = max(X_MIN_US, min(X_MAX_US, servo_x_us))
            servo_y_us = max(Y_MIN_US, min(Y_MAX_US, servo_y_us))

            send_servo_us(servo_x_us, servo_y_us)

    else:
        # No detections - scanning mode
        if time.time() - last_detection_time > DETECTION_TIMEOUT:
            scanning_behavior()
            print(f"Scanning")

# ---------------------------
# WEBSOCKET CALLBACKS
# ---------------------------

def on_message(ws, message):
    data = json.loads(message)
    bbs = data.get("result", {}).get("bounding_boxes", [])
    handle_detection(bbs)

def on_error(ws, error):
    print("Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("### WebSocket Closed ###")

def on_open(ws):
    print("### WebSocket Connected ###")

# ---------------------------
# START EI WEBSOCKET
# ---------------------------

ws = websocket.WebSocketApp(
    ws_url,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
    on_open=on_open
)

ws.run_forever()