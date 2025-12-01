#include <WiFi.h>
#include <ESP32Servo.h>

const char* ssid     = "your_network_ssid";
const char* password = "your_network_password";

const char* host = "your_RPi_IP";   // your RPi IP
const uint16_t port = 5000;

// Servo pins
int servoPin1 = 25;
int servoPin2 = 19;

Servo servoX;
Servo servoY;

WiFiClient client;

int mapPulseToAngle(int pulse, int minPulse, int maxPulse) {
  pulse = constrain(pulse, minPulse, maxPulse);
  return map(pulse, minPulse, maxPulse, 0, 180);
}

void setup() {
  Serial.begin(115200);

  // Attach servos and setup ranges
  servoX.attach(servoPin1, 500, 1100);  // X servo
  servoY.attach(servoPin2, 500, 1200);  // Y servo

  WiFi.begin(ssid, password);
  Serial.print("Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected!");

  if (!client.connect(host, port)) {
    Serial.println("Connection failed");
    return;
  }

  Serial.println("Connected to Pi server!");
}

void loop() {

  // Read commands from Raspberry Pi
  if (client.available()) {
    String msg = client.readStringUntil('\n');
    msg.trim();

    Serial.println("Pi says: " + msg);

    // Expected format: "X:650 Y:900"
    int xIndex = msg.indexOf("X:");
    int yIndex = msg.indexOf("Y:");

    if (xIndex >= 0 && yIndex >= 0) {

      int xValue = msg.substring(xIndex + 2, msg.indexOf(' ', xIndex)).toInt();
      int yValue = msg.substring(yIndex + 2).toInt();

      Serial.printf("Parsed X=%d  Y=%d\n", xValue, yValue);

      // Convert pulses to servo angle
      int angleX = mapPulseToAngle(xValue, 500, 900);
      int angleY = mapPulseToAngle(yValue, 500, 1200);

      // Move servos
      servoX.write(angleX);
      servoY.write(angleY);

      Serial.printf("ServoX → %d°   ServoY → %d°\n", angleX, angleY);
    }
  }
}
