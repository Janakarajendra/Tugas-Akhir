import sys
import time
import board
import adafruit_dht
import RPi.GPIO as GPIO
from sds011 import SDS011
from collections import deque

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton
)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont

#Inisialisasi Sensor
sensor = SDS011('/dev/ttyUSB0', use_query_mode=False)
sensor.sleep(sleep=False)
time.sleep(1)

dht_device1 = adafruit_dht.DHT22(board.D5)
dht_device2 = adafruit_dht.DHT22(board.D0)
dht_device3 = adafruit_dht.DHT22(board.D9)
sensor_count = 3

buffer_pm25 = deque(maxlen=5)
buffer_pm10 = deque(maxlen=5)

last_pm25 = last_pm10 = last_temp = last_hum = None

#Inisialisasi pin Relay dan Servo
RELAYACONOFF = 21
RELAYMODE = 20
SERVO_PIN = 2
RELAY_HUMIDIFIER = 26

GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAYACONOFF, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(RELAYMODE, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(RELAY_HUMIDIFIER, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(SERVO_PIN, GPIO.OUT)

servo_pwm = GPIO.PWM(SERVO_PIN, 50)
servo_pwm.start(0)

ac_state = False
humid_mode = False
filter_state = False
humidifier_on = False

#buat servo
def set_servo_angle(angle):
    duty = 2 + (angle / 18)
    GPIO.output(SERVO_PIN, True)
    servo_pwm.ChangeDutyCycle(duty)
    time.sleep(0.5)
    GPIO.output(SERVO_PIN, False)
    servo_pwm.ChangeDutyCycle(0)

def toggle_air_filter(pm25):
    global filter_state
    if pm25 > 35 and not filter_state:
        print("PM2.5 > 35 - Aktifkan Air Filter")
        set_servo_angle(118)
        time.sleep(1)
        set_servo_angle(90)
        filter_state = True
        print("[STATUS] Air Filter: ON")
        time.sleep(1)
    elif pm25 <= 35 and filter_state:
        print("PM2.5 <= 35 - Matikan Air Filter")
        set_servo_angle(118)
        time.sleep(1)
        set_servo_angle(90)
        filter_state = False
        print("[STATUS] Air Filter: OFF")
        time.sleep(1)

# kontrol relay 
def trigger_relay(pin):
    GPIO.output(pin, GPIO.HIGH)
    time.sleep(0.1)
    GPIO.output(pin, GPIO.LOW)

def trigger_mode_relay(pin, times):
    for _ in range(times):
        trigger_relay(pin)
        time.sleep(1)

def kontrol_ac_dengan_trigger(suhu):
    global ac_state
    if suhu > 26 and not ac_state:
        print("Suhu di atas 26°C - Nyalakan AC")
        trigger_relay(RELAYACONOFF)
        ac_state = True
        print("[STATUS] AC: ON")
        time.sleep(1)
    elif suhu < 24 and ac_state:
        if humid_mode:
            print("Suhu < 23°C tapi masih di mode HUMID - AC tidak dimatikan")
        else:
            print("Suhu di bawah 23°C - Matikan AC")
            trigger_relay(RELAYACONOFF)
            ac_state = False
            print("[STATUS] AC: OFF")
            time.sleep(1)

def kontrol_humid_mode(kelembapan, suhu):
    global humid_mode, ac_state

    if kelembapan > 60 and not humid_mode:
        print("Kelembapan > 60% - Pindah ke mode HUMID")
        if not ac_state:
            trigger_relay(RELAYACONOFF)
            ac_state = True
            print("[STATUS] AC: ON")
            time.sleep(1)
        trigger_mode_relay(RELAYMODE, 1)
        humid_mode = True
        print("[STATUS] Mode: HUMID")
        time.sleep(1)

    elif kelembapan < 55 and humid_mode:
        print("Kelembapan < 50% - Pindah ke mode COOL")
        trigger_mode_relay(RELAYMODE, 4)
        humid_mode = False
        print("[STATUS] Mode: COOL")
        time.sleep(1)

        if suhu < 23:
            print("Suhu < 23°C dan kelembapan sudah < 50% - Matikan AC")
            trigger_relay(RELAYACONOFF)
            ac_state = False
            print("[STATUS] AC: OFF")
            time.sleep(1)

def kontrol_humidifier(kelembapan):
    global humidifier_on
    if kelembapan < 30 and not humidifier_on:
        print("Kelembapan < 30% - Nyalakan Humidifier")
        trigger_relay(RELAY_HUMIDIFIER)
        humidifier_on = True
        print("[STATUS] Humidifier: ON")
        time.sleep(1)
    elif kelembapan >= 35 and humidifier_on:
        print("Kelembapan >= 35% - Matikan Humidifier")
        for _ in range(3):
            trigger_relay(RELAY_HUMIDIFIER)
            time.sleep(1)
        humidifier_on = False
        print("[STATUS] Humidifier: OFF")
        time.sleep(1)

def kontrol_sistem(suhu, kelembapan, pm25):
    pass

def read_sds011():
    global last_pm25, last_pm10
    result = sensor.read()
    if result:
        pm25, pm10 = result
        buffer_pm25.append(pm25)
        buffer_pm10.append(pm10)
        last_pm25 = round(sum(buffer_pm25) / len(buffer_pm25), 1)
        last_pm10 = round(sum(buffer_pm10) / len(buffer_pm10), 1)
    return last_pm25, last_pm10

def read_dht22():
    global last_temp, last_hum
    try:
        t1 = dht_device1.temperature
        h1 = dht_device1.humidity - 5.5
        t2 = dht_device2.temperature
        h2 = dht_device2.humidity - 3.5
        t3 = dht_device3.temperature
        h3 = dht_device3.humidity - 8.5
        last_temp = round((t1 + t2 + t3) / sensor_count, 1)
        last_hum = round((h1 + h2 + h3) / sensor_count, 1)
    except:
        pass
    return last_temp, last_hum

class SensorDisplay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sensor Monitor")
        self.setStyleSheet("background-color: #f2f2f2;")
        self.font_family = "Segoe UI"

        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        exit_button = QPushButton("\u2715")
        exit_button.setFixedSize(30, 30)
        exit_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border-radius: 15px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        exit_button.clicked.connect(QApplication.instance().quit)

        exit_layout = QHBoxLayout()
        exit_layout.addStretch()
        exit_layout.addWidget(exit_button)
        exit_layout.setContentsMargins(10, 10, 10, 0)
        main_layout.addLayout(exit_layout)

        title = QLabel("Office Air Monitoring")
        title.setFont(QFont(self.font_family, 30, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #333333; margin-bottom: 20px;")
        main_layout.addWidget(title)

        bubble_layout = QHBoxLayout()
        bubble_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.pm25_bubble = self.create_bubble(150, "#444", "#ffffff", 15)
        self.pm10_bubble = self.create_bubble(150, "#555", "#ffffff", 15)
        self.temp_bubble = self.create_bubble(150, "#666", "#ffffff", 20)
        self.hum_bubble = self.create_bubble(150, "#777", "#ffffff", 20)

        bubble_layout.addWidget(self.wrap_bubble("PM2.5", self.pm25_bubble))
        bubble_layout.addWidget(self.wrap_bubble("PM10", self.pm10_bubble))
        bubble_layout.addWidget(self.wrap_bubble("Temp", self.temp_bubble))
        bubble_layout.addWidget(self.wrap_bubble("Humidity", self.hum_bubble))

        main_layout.addLayout(bubble_layout)

        self.status_ac_label = QLabel("AC: OFF")
        self.status_filter_label = QLabel("Filter: OFF")
        self.status_humidifier_label = QLabel("Humidifier: OFF")

        for label in [self.status_ac_label, self.status_filter_label, self.status_humidifier_label]:
            label.setFont(QFont(self.font_family, 12, QFont.Weight.Medium))
            label.setStyleSheet("color: #333333;")

        status_layout = QVBoxLayout()
        status_layout.addWidget(self.status_ac_label)
        status_layout.addWidget(self.status_filter_label)
        status_layout.addWidget(self.status_humidifier_label)
        status_layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        container = QWidget()
        container.setLayout(status_layout)

        status_wrapper = QHBoxLayout()
        status_wrapper.addStretch()
        status_wrapper.addWidget(container)

        main_layout.addStretch()
        main_layout.addLayout(status_wrapper)

        self.setLayout(main_layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(5000)
        self.update_data()

    def create_bubble(self, size, bg_color, text_color, font_size):
        label = QLabel("...")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFixedSize(size, size)
        label.setFont(QFont(self.font_family, font_size, QFont.Weight.DemiBold))
        label.setStyleSheet(f"""
            background-color: {bg_color};
            border-radius: {size // 2}px;
            color: {text_color};
            border: 2px solid #aaa;
        """)
        return label

    def wrap_bubble(self, title_text, bubble):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(title_text)
        title.setFont(QFont(self.font_family, 12, QFont.Weight.Normal))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #333; margin-bottom: 5px;")

        layout.addWidget(title)
        layout.addWidget(bubble)
        container.setLayout(layout)
        return container

    def update_status_labels(self):
        self.status_ac_label.setText(f"AC: {'ON' if ac_state else 'OFF'}")
        self.status_filter_label.setText(f"Filter: {'ON' if filter_state else 'OFF'}")
        self.status_humidifier_label.setText(f"Humidifier: {'ON' if humidifier_on else 'OFF'}")

    def update_data(self):
        pm25, pm10 = read_sds011()
        suhu, hum = read_dht22()

        self.pm25_bubble.setText(f"{pm25} µg/m³" if pm25 is not None else self.pm25_bubble.text())
        self.pm10_bubble.setText(f"{pm10} µg/m³" if pm10 is not None else self.pm10_bubble.text())
        self.temp_bubble.setText(f"{suhu}°C" if suhu is not None else self.temp_bubble.text())
        self.hum_bubble.setText(f"{hum}%" if hum is not None else self.hum_bubble.text())

        if suhu is not None and hum is not None and pm25 is not None:
            kontrol_sistem(suhu, hum, pm25)
            kontrol_ac_dengan_trigger(suhu)
            kontrol_humid_mode(hum, suhu)
            kontrol_humidifier(hum)
            toggle_air_filter(pm25)

        self.update_status_labels()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SensorDisplay()
    window.showFullScreen()
    try:
        ret = app.exec()
    finally:
        servo_pwm.stop()
        GPIO.cleanup()
        sys.exit(ret)
