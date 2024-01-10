import imaplib
import email
from email.header import decode_header
import re

# Учетные данные для входа в Gmail
username = "your_email@gmail.com"
password = "your_password"

# Создаем экземпляр IMAP4_SSL класса
mail = imaplib.IMAP4_SSL("imap.gmail.com")

# Аутентификация
mail.login(username, password)

# Выбираем почтовый ящик (в данном случае "inbox")
mail.select("inbox")

# Ищем письма от helpdesk.perplexity.ai
status, messages = mail.search(None, '(FROM "helpdesk@perplexity.ai")')

# Преобразуем messages в список ID писем
messages = messages[0].split(b' ')

# Инициализируем переменную для хранения URL
signin_url = None

# Проходимся по каждому письму
for mail_id in messages:
    # Получаем данные письма
    _, msg = mail.fetch(mail_id, '(RFC822)')

    # Парсим данные письма
    for response in msg:
        if isinstance(response, tuple):
            # Парсим байтовый объект письма
            msg = email.message_from_bytes(response[1])

            # Извлекаем тело письма
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/html":
                        body = part.get_payload(decode = True).decode()
                        # Используем регулярное выражение для поиска URL
                        urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', body)
                        if urls:
                            # Предполагаем, что первый найденный URL - это искомый URL для входа
                            signin_url = urls[0]
                            break
            else:
                content_type = msg.get_content_type()
                if content_type == "text/html":
                    body = msg.get_payload(decode = True).decode()
                    urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', body)
                    if urls:
                        signin_url = urls[0]

# Выводим найденный URL
print(f"Sign-in URL: {signin_url}")

# Закрываем соединение и выходим
mail.close()
mail.logout()
