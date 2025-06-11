#include <ESP8266WiFi.h>
#include <WiFiManager.h>
#include <PubSubClient.h>
#include <EEPROM.h>

// MQTT параметры
const char* mqtt_server = "";
const int mqtt_port = ;
const char* mqtt_user = "";
const char* mqtt_pass = "";

#define IN_PC1 12 // Пин входа ПК1
#define IN_PC2 13 // Пин входа ПК2
#define IN_PC3 14 // Пин входа ПК3 
#define OUT_PC1 4 // Пин выхода ПК1 
#define OUT_PC2 5 // Пин выхода ПК2 
#define OUT_PC3 3 // Пин выхода ПК3

int max_conn = 2; // Количество подключаемых ПК (для ESP8266 лучше не больше 3)

const unsigned long interval = 10000;  // Интервал задержки автовключения в миллисекундах

String name = "device1"; // Имя устройства менять если больше одного 


//...................Служебные..переменные....................
#define EEPROM_SIZE 3
#define AUTO_MODE_1_ADDR 0
#define AUTO_MODE_2_ADDR 1
#define AUTO_MODE_3_ADDR 2

bool autoModeEnabled1 = false;
bool autoModeEnabled2 = false;
bool autoModeEnabled3 = false;
unsigned long previousMillis = 0;
bool lastState1 = false;
bool lastState2 = false;
bool lastState3 = false;

String topic_relay1_set = String(mqtt_user) + "/" + name + "/relay1/set";
String topic_relay2_set = String(mqtt_user) + "/" + name + "/relay2/set";
String topic_relay3_set = String(mqtt_user) + "/" + name + "/relay3/set";
String topic_relay1_automode = String(mqtt_user) + "/" + name + "/relay1/automode";
String topic_relay2_automode = String(mqtt_user) + "/" + name + "/relay2/automode";
String topic_relay3_automode = String(mqtt_user) + "/" + name + "/relay3/automode";
String topic_relay1_status = String(mqtt_user) + "/" + name + "/relay1/status";
String topic_relay2_status = String(mqtt_user) + "/" + name + "/relay2/status";
String topic_relay3_status = String(mqtt_user) + "/" + name + "/relay3/status";
String topic_info = String(mqtt_user) + "/info";
String topic_answer = String(mqtt_user) + "/answer";

String infoMessage = name + "\n" + String(max_conn);


WiFiClient espClient;
PubSubClient client(espClient);


void setup() {
  Serial.begin(115200);

  EEPROM.begin(EEPROM_SIZE);  // Инициализация EEPROM

  // Чтение сохраненных состояний из EEPROM
  autoModeEnabled1 = EEPROM.read(AUTO_MODE_1_ADDR);
  autoModeEnabled2 = EEPROM.read(AUTO_MODE_2_ADDR);
  autoModeEnabled3 = EEPROM.read(AUTO_MODE_3_ADDR);

  if(max_conn >= 1) {
    pinMode(IN_PC1, INPUT);
    pinMode(OUT_PC1, OUTPUT); 
    digitalWrite(OUT_PC1, HIGH);
  }
  
  if(max_conn >= 2) {
    pinMode(IN_PC2, INPUT);
    pinMode(OUT_PC2, OUTPUT); 
    digitalWrite(OUT_PC2, HIGH);
  }

  if(max_conn >= 3) {
    pinMode(IN_PC3, INPUT);
    pinMode(OUT_PC3, OUTPUT); 
    digitalWrite(OUT_PC3, HIGH);
  }
  
  
  
  WiFiManager wm;
  if(!wm.autoConnect("MQTT-Setup")) {
    Serial.println("Не удалось подключиться");
    ESP.restart();
  }

  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);

  reconnect();
  
  client.publish(topic_info.c_str(), infoMessage.c_str());

  if (autoModeEnabled1) {
     client.publish(topic_relay1_automode.c_str(), "ON");
    } else if (!autoModeEnabled1) {
      client.publish(topic_relay1_automode.c_str(), "OFF");
      }
 if (autoModeEnabled2) {
     client.publish(topic_relay2_automode.c_str(), "ON");
    } else if (!autoModeEnabled2) {
      client.publish(topic_relay2_automode.c_str(), "OFF");
      }
 if (autoModeEnabled3) {
     client.publish(topic_relay3_automode.c_str(), "ON");
    } else if (!autoModeEnabled3) {
      client.publish(topic_relay3_automode.c_str(), "OFF");
      }      
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Подключение к MQTT...");
    if (client.connect("ESP8266Client", mqtt_user, mqtt_pass)) {
      Serial.println("Успех");
      client.subscribe(topic_relay1_set.c_str());
      client.subscribe(topic_relay1_automode.c_str());
      client.subscribe(topic_relay2_set.c_str());
      client.subscribe(topic_relay2_automode.c_str());
      client.subscribe(topic_relay3_set.c_str());
      client.subscribe(topic_relay3_automode.c_str());
      client.subscribe(topic_answer.c_str());
    } else {
      Serial.print("Ошибка, повтор через 5 сек...");
      delay(5000);
    }
  }
}



void callback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }

  if (String(topic) == topic_answer) {
    if (msg == "info") {
      client.publish(topic_info.c_str(), infoMessage.c_str());
    } 
  }

  if (String(topic) == topic_answer) {
    if (msg == "info1") {
      if (digitalRead(IN_PC1) == HIGH) {
        client.publish(topic_relay1_status.c_str(), "ON");
      } else {
        client.publish(topic_relay1_status.c_str(), "OFF");
      }
      if (digitalRead(IN_PC2) == HIGH) {
        client.publish(topic_relay2_status.c_str(), "ON");
      } else {
        client.publish(topic_relay2_status.c_str(), "OFF");
      }
      if (digitalRead(IN_PC3) == HIGH) {
        client.publish(topic_relay3_status.c_str(), "ON");
      } else {
        client.publish(topic_relay3_status.c_str(), "OFF");
      }
    } 
  }

if(max_conn >= 1) {
  if (String(topic) == topic_relay1_set) {
    if (msg == "ON") {
      digitalWrite(OUT_PC1, LOW);
      delay(200);
      digitalWrite(OUT_PC1, HIGH);
    } 
  }
  if (String(topic) == topic_relay1_automode) {
    if (msg == "ON") {
      autoModeEnabled1 = true;
    } else if (msg == "OFF") {
      autoModeEnabled1 = false;
      }
      saveAutoMode();
  }
}

if(max_conn >= 2) {
  if (String(topic) == topic_relay2_set) {
    if (msg == "ON") {
      digitalWrite(OUT_PC2, LOW);
      delay(200);
      digitalWrite(OUT_PC2, HIGH);
    } 
  }
  if (String(topic) == topic_relay2_automode) {
    if (msg == "ON") {
      autoModeEnabled2 = true;
    } else if (msg == "OFF") {
      autoModeEnabled2 = false;
      }
      saveAutoMode();
  }
}

if(max_conn >= 3) {
  if (String(topic) == topic_relay3_set) {
    if (msg == "ON") {
      digitalWrite(OUT_PC3, LOW);
      delay(200);
      digitalWrite(OUT_PC3, HIGH);
    } 
  }
  if (String(topic) == topic_relay3_automode) {
    if (msg == "ON") {
      autoModeEnabled3 = true;
    } else if (msg == "OFF") {
      autoModeEnabled3 = false;
      }
      saveAutoMode();
  }
}

}

void saveAutoMode() {
  EEPROM.write(AUTO_MODE_1_ADDR, autoModeEnabled1);
  EEPROM.write(AUTO_MODE_2_ADDR, autoModeEnabled2);
  EEPROM.write(AUTO_MODE_3_ADDR, autoModeEnabled3);
  EEPROM.commit();
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long currentMillis = millis();

  if (currentMillis - previousMillis >= interval) {   //текущее время с начала запуска программы - время последней проверки >= интервала
    previousMillis = currentMillis;                  //время последней проверки приравнивается к текущему

    if (autoModeEnabled1) {       
      if (digitalRead(IN_PC1) == LOW) {
        digitalWrite(OUT_PC1, LOW);
        delay(100);
        digitalWrite(OUT_PC1, HIGH);
      }
    }

    if (autoModeEnabled2) {     
      if (digitalRead(IN_PC2) == LOW) {
        digitalWrite(OUT_PC2, LOW);
        delay(100);
        digitalWrite(OUT_PC2, HIGH);
      }
    }

    if (autoModeEnabled3) {     
      if (digitalRead(IN_PC3) == LOW) {
        digitalWrite(OUT_PC3, LOW);
        delay(100);
        digitalWrite(OUT_PC3, HIGH);
      }
    }
  } 

bool currentState1 = digitalRead(IN_PC1);

if (currentState1 != lastState1) {
    if (currentState1 == HIGH) {
      client.publish(topic_relay1_status.c_str(), "ON");
    } else {
      client.publish(topic_relay1_status.c_str(), "OFF");
    }
    lastState1 = currentState1;
  }

bool currentState2 = digitalRead(IN_PC2);

if (currentState2 != lastState2) {
    if (currentState2 == HIGH) {
      client.publish(topic_relay2_status.c_str(), "ON");
    } else {
      client.publish(topic_relay2_status.c_str(), "OFF");
    }
    lastState2 = currentState2;
  }

  bool currentState3 = digitalRead(IN_PC3);

  if (currentState3 != lastState3) {
      if (currentState3 == HIGH) {
        client.publish(topic_relay3_status.c_str(), "ON");
      } else {
        client.publish(topic_relay3_status.c_str(), "OFF");
      }
      lastState3 = currentState3;
    }

}
