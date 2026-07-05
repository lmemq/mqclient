import socket
import struct
import threading
import sys
import time

HOST = "127.0.0.1"
PORT = 54233
HEADER_FMT = '<qqIHBB'
HEADER_SIZE = 24

class ChatClient:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.sock = None
        self.user_id = None
        self.running = True
        self.ping_enabled = False
        self.ping_interval = 30  # секунд
        
    def connect(self):
        """Подключение к серверу"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        print(f"[✓] Подключен к {self.host}:{self.port}")
    
    def send_ping(self):
        """Отправить ping серверу"""
        if self.sock:
            header = struct.pack(HEADER_FMT, 0, 0, 0, 0, 4, 0)  # cmd_id=4 (Ping), flag=0
            self.sock.sendall(header)
            # print("[→] Ping отправлен")  # закомментировано, чтобы не спамить
        
    def ping_thread(self):
        """Фоновый поток для отправки ping"""
        while self.running:
            if self.ping_enabled:
                self.send_ping()
            time.sleep(self.ping_interval)
        
    def receive_thread(self):
        """Поток для приема сообщений"""
        while self.running:
            try:
                header_bytes = self.sock.recv(HEADER_SIZE)
                if not header_bytes:
                    print("\n[!] Сервер закрыл соединение")
                    self.running = False
                    break
                
                if len(header_bytes) == HEADER_SIZE:
                    rec_id, snd_id, msg_len, reserved, cmd_id, cmd_flag = struct.unpack(HEADER_FMT, header_bytes)
                    
                    # Читаем тело если есть
                    body = b""
                    if msg_len > 0:
                        body = self.sock.recv(msg_len)
                    
                    # Обработка ответов
                    if cmd_id == 0:  # Disconnect
                        if cmd_flag == 1:
                            print("\n[✓] Отключение подтверждено")
                            self.running = False
                            break
                    elif cmd_id == 1:  # Auth
                        if cmd_flag == 1:
                            self.user_id = rec_id
                            print(f"\n[✓] Регистрация успешна! Ваш ID: {self.user_id}")
                        elif cmd_flag == 3:
                            self.user_id = rec_id
                            print(f"\n[✓] Вход выполнен! Ваш ID: {self.user_id}")
                    elif cmd_id == 2:  # Error
                        error_msgs = {
                            0: "Неверный флаг команды",
                            1: "Неверный ключ авторизации",
                            2: "Разорванный пакет",
                            3: "Пользователь уже существует",
                            4: "Пользователь не найден",
                            5: "Ошибка на сервере"
                        }
                        print(f"\n[✗] Ошибка: {error_msgs.get(cmd_flag, f'Неизвестная ошибка ({cmd_flag})')}")
                    elif cmd_id == 3:  # Message
                        try:
                            text = body.decode('utf-8')
                            print(f"\n[Сообщение от {snd_id}]: {text}")
                        except:
                            print(f"\n[Сообщение от {snd_id}]: (бинарные данные)")
                    elif cmd_id == 4:  # Ping
                        if cmd_flag == 1:  # Pong
                            print("pong rec")
                    
                    print("\n> ", end="", flush=True)
                    
            except Exception as e:
                if self.running:
                    print(f"\n[!] Ошибка приема: {e}")
                break
                
    def send_auth(self, nickname, auth_key, is_login=False):
        """Отправить авторизацию (регистрация или вход)"""
        nickname_bytes = nickname.encode('utf-8').ljust(32, b'\x00')[:32]
        auth_key_bytes = auth_key.encode('utf-8').ljust(64, b'\x00')[:64]
        body = nickname_bytes + auth_key_bytes
        
        flag = 4 if is_login else 0
        header = struct.pack(HEADER_FMT, 0, -1, len(body), 0, 1, flag)
        self.sock.sendall(header + body)
        print(f"[→] Отправка {'входа' if is_login else 'регистрации'} для '{nickname}'")
        
    def send_message(self, receiver_id, text):
        """Отправить сообщение пользователю"""
        if self.user_id is None:
            print("[!] Вы не авторизованы")
            return
            
        body = text.encode('utf-8')
        header = struct.pack(HEADER_FMT, receiver_id, self.user_id, len(body), 0, 3, 0)
        self.sock.sendall(header + body)
        print(f"[→] Сообщение для {receiver_id}: {text}")
        
    def send_disconnect(self):
        """Отправить запрос на отключение"""
        if self.sock:
            header = struct.pack(HEADER_FMT, 0, 0, 0, 0, 0, 0)
            self.sock.sendall(header)
            print("[→] Отправка запроса на отключение")
            
    def start(self):
        """Запуск клиента"""
        try:
            self.connect()
            
            # Запускаем поток приема
            t = threading.Thread(target=self.receive_thread, daemon=True)
            t.start()
            
            # Запускаем поток пинга
            ping_thread = threading.Thread(target=self.ping_thread, daemon=True)
            ping_thread.start()
            
            print("\n" + "="*50)
            print("Команды:")
            print("  /reg <ник> <ключ>     - регистрация")
            print("  /login <ник> <ключ>   - вход")
            print("  /msg <id> <текст>     - отправить сообщение")
            print("  /ping on/off          - включить/выключить автопинг")
            print("  /ping                 - показать статус пинга")
            print("  /exit                 - отключиться")
            print("  /help                 - эта справка")
            print("="*50 + "\n")
            
            while self.running:
                try:
                    user_input = input("> ").strip()
                    if not user_input:
                        continue
                        
                    if user_input.startswith("/reg "):
                        parts = user_input[5:].split(maxsplit=1)
                        if len(parts) == 2:
                            self.send_auth(parts[0], parts[1], is_login=False)
                        else:
                            print("[!] Формат: /reg <ник> <ключ>")
                            
                    elif user_input.startswith("/login "):
                        parts = user_input[6:].split(maxsplit=1)
                        if len(parts) == 2:
                            self.send_auth(parts[0], parts[1], is_login=True)
                        else:
                            print("[!] Формат: /login <ник> <ключ>")
                            
                    elif user_input.startswith("/msg "):
                        parts = user_input[5:].split(maxsplit=1)
                        if len(parts) == 2:
                            try:
                                receiver_id = int(parts[0])
                                self.send_message(receiver_id, parts[1])
                            except ValueError:
                                print("[!] ID должен быть числом")
                        else:
                            print("[!] Формат: /msg <id> <текст>")
                            
                    elif user_input == "/ping":
                        status = "включен" if self.ping_enabled else "выключен"
                        print(f"[Пинг] {status} (интервал: {self.ping_interval}с)")
                        
                    elif user_input.startswith("/ping "):
                        parts = user_input[6:].strip().lower()
                        if parts == "on":
                            self.ping_enabled = True
                            print("[✓] Автопинг включен")
                        elif parts == "off":
                            self.ping_enabled = False
                            print("[✓] Автопинг выключен")
                        else:
                            print("[!] Формат: /ping on  или  /ping off")
                            
                    elif user_input == "/exit":
                        self.send_disconnect()
                        time.sleep(0.5)
                        self.running = False
                        break
                        
                    elif user_input == "/help":
                        print("\nКоманды:")
                        print("  /reg <ник> <ключ>     - регистрация")
                        print("  /login <ник> <ключ>   - вход")
                        print("  /msg <id> <текст>     - отправить сообщение")
                        print("  /ping on/off          - включить/выключить автопинг")
                        print("  /ping                 - показать статус пинга")
                        print("  /exit                 - отключиться")
                        print()
                        
                    else:
                        print("[!] Неизвестная команда. /help для справки")
                        
                except KeyboardInterrupt:
                    print("\n[!] Прерывание...")
                    self.running = False
                    break
                    
        except Exception as e:
            print(f"[!] Ошибка: {e}")
        finally:
            self.cleanup()
            
    def cleanup(self):
        """Очистка ресурсов"""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        print("[✓] Клиент завершен")


if __name__ == "__main__":
    client = ChatClient()
    client.start()
