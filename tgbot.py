import asyncio
import logging
import json
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
import paho.mqtt.client as mqtt
from collections import defaultdict

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
TOKEN = ""
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Глобальные переменные
mqtt_client = None
loop = asyncio.new_event_loop()  # Создаем новую event loop

class UserData:
    def __init__(self):
        self.mqtt_config = {
            'broker': '',
            'port': 1883,
            'username': '',
            'password': ''
        }
        self.devices_info = {}
        self.current_device = None
        self.relay_status = {}
        self.automode_status = {}
        self.known_devices = set()

    def save_to_file(self, user_id):
        data = {
            'mqtt_config': self.mqtt_config,
            'devices_info': self.devices_info,
            'current_device': self.current_device,
            'relay_status': self.relay_status,
            'automode_status': self.automode_status,
            'known_devices': list(self.known_devices)
        }
        with open(f'user_{user_id}.json', 'w') as f:
            json.dump(data, f)

    @classmethod
    def load_from_file(cls, user_id):
        try:
            with open(f'user_{user_id}.json', 'r') as f:
                data = json.load(f)
                user_data = cls()
                user_data.mqtt_config = data.get('mqtt_config', user_data.mqtt_config)
                user_data.devices_info = data.get('devices_info', {})
                user_data.current_device = data.get('current_device')
                user_data.relay_status = data.get('relay_status', {})
                user_data.automode_status = data.get('automode_status', {})
                user_data.known_devices = set(data.get('known_devices', []))
                return user_data
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()

users_data = defaultdict(UserData)

def on_connect(client, userdata, flags, rc):
    logger.info(f"Connected to MQTT with result code {rc}")
    for user_id, user_data in users_data.items():
        if user_data.mqtt_config.get('username'):
            client.subscribe(f"{user_data.mqtt_config['username']}/info")
            if user_data.current_device:
                base_topic = f"{user_data.mqtt_config['username']}/{user_data.current_device}/relay"
                for relay_num in range(1, 5):
                    client.subscribe(f"{base_topic}{relay_num}/status")
                    client.subscribe(f"{base_topic}{relay_num}/automode")

def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode()
        logger.info(f"Received message on {topic}: {payload}")

        if topic.endswith('/info'):
            username = topic.split('/')[0]
            handle_device_info(payload, username)
            return
            
        parts = topic.split('/')
        if len(parts) == 4 and parts[2].startswith('relay'):
            username = parts[0]
            device_name = parts[1]
            relay_num = parts[2][5:]
            topic_type = parts[3]

            for user_id, user_data in users_data.items():
                if (user_data.mqtt_config.get('username') == username and 
                    user_data.current_device == device_name):
                    
                    if topic_type == "status":
                        user_data.relay_status[relay_num] = payload
                    elif topic_type == "automode":
                        user_data.automode_status[relay_num] = payload
                    
                    user_data.save_to_file(user_id)
                    asyncio.run_coroutine_threadsafe(update_user_keyboard(user_id), loop)
        
    except Exception as e:
        logger.error(f"Error processing MQTT message: {e}", exc_info=True)

def handle_device_info(payload, username):
    lines = payload.split('\n')
    if len(lines) >= 2:
        device_name = lines[0].strip()
        try:
            pc_count = int(lines[1].strip())
            for user_id, user_data in users_data.items():
                if user_data.mqtt_config.get('username') == username:
                    user_data.devices_info[device_name] = {
                        'pc_count': pc_count,
                        'payload': payload
                    }
                    user_data.save_to_file(user_id)
                    asyncio.run_coroutine_threadsafe(
                        bot.send_message(
                            user_id,
                            f"🔎Обнаружено новое устройство: {device_name} с {pc_count} ПК"
                        ), 
                        loop
                    )
        except ValueError:
            logger.error(f"Invalid PC count for device {device_name}")

async def update_user_keyboard(user_id):
    try:
        user_data = users_data[user_id]
        if user_data.current_device:
            device = user_data.devices_info.get(user_data.current_device)
            if device:
                pc_count = device['pc_count']
                keyboard = create_device_keyboard(pc_count, user_data.current_device, user_data)
                await bot.send_message(
                    user_id,
                   "<i>Обновление интерфейса...</i>",
                   parse_mode='HTML',
                    reply_markup=keyboard
                )
    except Exception as e:
        logger.error(f"Error updating keyboard for user {user_id}: {e}")

async def request_mqtt_config(message: types.Message):
    await message.answer("<b>Пожалуйста, введите настройки MQTT в формате:</b>\n"
                       "<b>broker port username password</b>\n"
                       "Пример: mqtt.example.com 1883 user pass", parse_mode='HTML')

async def process_mqtt_config(message: types.Message):
    user_data = users_data[message.from_user.id]
    try:
        parts = message.text.split(' ')
        if len(parts) != 4:
            raise ValueError("Неверный формат")
        
        user_data.mqtt_config = {
            'broker': parts[0],
            'port': int(parts[1]),
            'username': parts[2],
            'password': parts[3]
        }
        user_data.save_to_file(message.from_user.id)
        await setup_mqtt_client(message)
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nПожалуйста, попробуйте еще раз.")
        await request_mqtt_config(message)

async def setup_mqtt_client(message: types.Message):
    global mqtt_client
    user_data = users_data[message.from_user.id]
    
    try:
        if mqtt_client is not None:
            mqtt_client.disconnect()
        
        mqtt_client = mqtt.Client()
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        
        if user_data.mqtt_config['username'] and user_data.mqtt_config['password']:
            mqtt_client.username_pw_set(
                user_data.mqtt_config['username'],
                user_data.mqtt_config['password']
            )
        
        mqtt_client.connect(
            user_data.mqtt_config['broker'],
            user_data.mqtt_config['port'],
            60
        )
        mqtt_client.loop_start()
        
        mqtt_client.publish(f"{user_data.mqtt_config['username']}/answer", "info")
        await message.answer("<b>Настройки MQTT сохранены.</b>", parse_mode='HTML')
        await show_settings(message)
        
    except Exception as e:
        await message.answer(f"Ошибка подключения к MQTT: {e}")
        logger.error(f"MQTT connection error: {e}")

def create_device_keyboard(pc_count: int, device_name: str, user_data):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=pc_count)
    
    status_buttons = []
    for i in range(1, pc_count+1):
        status = user_data.relay_status.get(str(i), "OFF")
        emoji = "🟢" if status == "ON" else "🔴"
        status_buttons.append(KeyboardButton(f"ПК{i}: {emoji}"))
    keyboard.add(*status_buttons)
    
    power_buttons = [KeyboardButton(f"🔘Включить ПК{i}") for i in range(1, pc_count+1)]
    keyboard.add(*power_buttons)
    
    auto_buttons = []
    for i in range(1, pc_count+1):
        auto_status = user_data.automode_status.get(str(i), "OFF")
        emoji = "✅" if auto_status == "ON" else "❌"
        auto_buttons.append(KeyboardButton(f"Автомод ПК{i} {emoji}"))
    keyboard.add(*auto_buttons)
    
    keyboard.add(KeyboardButton("⚙️Настройки"), KeyboardButton(device_name))
    return keyboard

async def select_device(message: types.Message, device_name: str):
    user_data = users_data[message.from_user.id]
    if device_name not in user_data.devices_info:
        await message.answer("Устройство не найдено")
        return
    
    mqtt_client.publish(f"{user_data.mqtt_config['username']}/answer", "info1")

    user_data.current_device = device_name
    user_data.known_devices.add(device_name)
    device = user_data.devices_info[device_name]
    pc_count = device['pc_count']
    
    if mqtt_client:
        base_topic = f"{user_data.mqtt_config['username']}/{device_name}/relay"
        for relay_num in range(1, pc_count+1):
            mqtt_client.subscribe(f"{base_topic}{relay_num}/status")
            mqtt_client.subscribe(f"{base_topic}{relay_num}/automode")
    
    keyboard = create_device_keyboard(pc_count, device_name, user_data)
    user_data.save_to_file(message.from_user.id)
    
    await message.answer(f"ℹ️Выбрано устройство: {device_name}", reply_markup=keyboard)

async def show_settings(message: types.Message):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [
        KeyboardButton("⚙️Изменить конфигурацию MQTT"),
        KeyboardButton("♻️Сменить устройство"),
        KeyboardButton("🗑️Забыть устройство"),
        KeyboardButton("🔎Добавить новое устройство")
    ]
    
    user_data = users_data[message.from_user.id]
    if user_data.current_device:
        buttons.append(KeyboardButton("⬅️Назад"))
    
    keyboard.add(*buttons)
    await message.answer("⚙️Настройки:", reply_markup=keyboard)

async def show_device_selection(message: types.Message, action: str):
    user_data = users_data[message.from_user.id]
    if not user_data.devices_info:
        await message.answer("Нет доступных устройств")
        return
    
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for device in user_data.devices_info:
        keyboard.add(KeyboardButton(f"{action}_{device}"))
    keyboard.add(KeyboardButton("⚙️Настройки"))
    
    await message.answer("Выберите устройство:", reply_markup=keyboard)

async def forget_device(message: types.Message, device_name: str):
    user_data = users_data[message.from_user.id]
    if device_name in user_data.devices_info:
        del user_data.devices_info[device_name]
        await message.answer(f"ℹ️Устройство {device_name} забыто")
    else:
        await message.answer("Устройство не найдено")
    
    if user_data.current_device == device_name:
        user_data.current_device = None
    
    user_data.save_to_file(message.from_user.id)
    await show_settings(message)

async def add_new_device(message: types.Message):
    user_data = users_data[message.from_user.id]
    if not mqtt_client:
        await message.answer("MQTT клиент не инициализирован")
        return
    
    mqtt_client.publish(f"{user_data.mqtt_config['username']}/answer", "info")
    await message.answer("<i>Поиск новых устройств...</i>", parse_mode='HTML')

async def handle_power_button(message: types.Message, pc_num: int):
    user_data = users_data[message.from_user.id]
    if not user_data.current_device or not user_data.mqtt_config.get('username'):
        await message.answer("Ошибка: устройство не выбрано или MQTT не настроен")
        return
    
    topic = f"{user_data.mqtt_config['username']}/{user_data.current_device}/relay{pc_num}/set"
    mqtt_client.publish(topic, "ON")
    await message.answer(f"💡Команда включения отправлена для ПК{pc_num}")

async def handle_automode_button(message: types.Message, pc_num: int):
    user_data = users_data[message.from_user.id]
    if not user_data.current_device or not user_data.mqtt_config.get('username'):
        await message.answer("Ошибка: устройство не выбрано или MQTT не настроен")
        return
    
    current_state = user_data.automode_status.get(str(pc_num), "OFF")
    new_state = "OFF" if current_state == "ON" else "ON"
    
    topic = f"{user_data.mqtt_config['username']}/{user_data.current_device}/relay{pc_num}/automode"
    mqtt_client.publish(topic, new_state)
    await message.answer(f"Режим автовключения для ПК{pc_num} {'включен✅' if new_state == 'ON' else 'выключен❌'}")

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_data = UserData.load_from_file(message.from_user.id)
    users_data[message.from_user.id] = user_data
    
    if user_data.mqtt_config.get('username'):
        await setup_mqtt_client(message)
    else:
        await request_mqtt_config(message)

@dp.message_handler(commands=['help'])
async def cmd_settings(message: types.Message):
    await message.answer("ℹ️ Помощь:\n\n"
            "🟢/🔴 - Текущий статус ПК\n"
            "🔘 Вкл 1/2 - Включить соответствующий ПК\n"
            "✅❌ Авторежим - Переключение авторежима включения ПК")
    await show_settings(message)
    

@dp.message_handler(lambda message: message.text == "⚙️Настройки")
async def cmd_settings(message: types.Message):
    await show_settings(message)

@dp.message_handler(lambda message: message.text == "⚙️Изменить конфигурацию MQTT")
async def cmd_change_mqtt(message: types.Message):
    await request_mqtt_config(message)

@dp.message_handler(lambda message: message.text == "♻️Сменить устройство")
async def cmd_change_device(message: types.Message):
    await show_device_selection(message, "Выбрать")

@dp.message_handler(lambda message: message.text == "🗑️Забыть устройство")
async def cmd_forget_device(message: types.Message):
    await show_device_selection(message, "Забыть")

@dp.message_handler(lambda message: message.text == "🔎Добавить новое устройство")
async def cmd_add_device(message: types.Message):
    await add_new_device(message)

@dp.message_handler(lambda message: message.text == "⬅️Назад")
async def cmd_back(message: types.Message):
    user_data = users_data[message.from_user.id]
    if user_data.current_device:
        device = user_data.devices_info[user_data.current_device]
        keyboard = create_device_keyboard(device['pc_count'], user_data.current_device, user_data)
        await message.answer("⬅️Назад", reply_markup=keyboard)

@dp.message_handler(lambda message: message.text.startswith("Выбрать_"))
async def cmd_select_specific_device(message: types.Message):
    device_name = message.text.split('_')[1]
    await select_device(message, device_name)

@dp.message_handler(lambda message: message.text.startswith("Забыть_"))
async def cmd_forget_specific_device(message: types.Message):
    device_name = message.text.split('_')[1]
    await forget_device(message, device_name)

@dp.message_handler(lambda message: message.text.startswith("🔘Включить ПК"))
async def cmd_power_on(message: types.Message):
    try:
        pc_num = int(message.text.split('ПК')[1])
        await handle_power_button(message, pc_num)
    except (IndexError, ValueError):
        await message.answer("Неверный формат команды")

@dp.message_handler(lambda message: message.text.startswith("Автомод ПК"))
async def cmd_automode(message: types.Message):
    try:
        pc_num = int(message.text.split('ПК')[1].split()[0])
        await handle_automode_button(message, pc_num)
    except (IndexError, ValueError):
        await message.answer("Неверный формат команды")

@dp.message_handler(lambda message: any(message.text.startswith(f"ПК{i}:") for i in range(1, 10)))
async def cmd_status(message: types.Message):
    pass


@dp.message_handler()
async def process_message(message: types.Message):
    if ' ' in message.text and len(message.text.split(' ')) == 4:
        await process_mqtt_config(message)
    else:
        await message.answer("🈲Неизвестная команда")

if __name__ == '__main__':
    # Запускаем event loop в отдельном потоке
    asyncio.set_event_loop(loop)
    
    # Загружаем данные всех пользователей при старте
    for filename in os.listdir():
        if filename.startswith('user_') and filename.endswith('.json'):
            user_id = int(filename[5:-5])
            users_data[user_id] = UserData.load_from_file(user_id)
    
    executor.start_polling(dp, skip_updates=True)