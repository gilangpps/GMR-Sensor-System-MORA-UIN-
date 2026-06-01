#include <Wire.h>
#include <Adafruit_ADS1X15.h>

Adafruit_ADS1115 ads;  // Objek untuk ADS1115

void setup() {
    Serial.begin(9600);
    Wire.begin();  // Inisialisasi komunikasi I2C

    if (!ads.begin()) {
        Serial.println("Gagal mendeteksi ADS1115!");
        while (1);  // Hentikan program jika ADS1115 tidak terdeteksi
    }

    ads.setGain(GAIN_TWOTHIRDS);  // Set gain = 1 (±4.096V), sesuaikan dengan kebutuhan
}

void loop() {
    int16_t rawValue = ads.readADC_SingleEnded(0);  // Membaca dari A0 ADS1115

    // Konversi nilai ADC ke tegangan
    float voltage = (rawValue * 4.096) / 32767.0;  

    Serial.println(voltage, 10);  // Menampilkan tegangan dengan 10 digit desimal
    delay(1000);  // Delay untuk pembacaan setiap 1 detik
}
