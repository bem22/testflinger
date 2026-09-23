#include <inttypes.h>
#include <stdio.h>

#include "esp_err.h"
#include "esp_mac.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

void app_main(void)
{
    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_read_mac(mac, ESP_MAC_WIFI_STA));
    setvbuf(stdout, NULL, _IONBF, 0);

    /* Repeat so a monitor attached after reset cannot miss the test marker.
     * No Wi-Fi/BLE, external RAM, GPIO, or sleep configuration is needed.
     */
    for (uint32_t sequence = 0;; ++sequence) {
        printf("Hello world from ESP32-S3-Zero!\n");
        printf("TF_ESP32S3_HELLO_V1_PASS mac=" MACSTR " seq=%" PRIu32 "\n",
               MAC2STR(mac), sequence);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
