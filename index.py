import logging
import telebot
import os
import openai
import json
import boto3
import time
import threading

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_BOT_CHATS = os.environ.get("TG_BOT_CHATS").lower().split(",")
PROXY_API_KEY = os.environ.get("PROXY_API_KEY")
YANDEX_KEY_ID = os.environ.get("YANDEX_KEY_ID")
YANDEX_KEY_SECRET = os.environ.get("YANDEX_KEY_SECRET")
YANDEX_BUCKET = os.environ.get("YANDEX_BUCKET")
DEEP_SICK = os.environ.get("DEEP_SICK")
OPEN_ROUTER_API_KEY=os.environ.get("OPEN_ROUTER_API_KEY")


logger = telebot.logger
telebot.logger.setLevel(logging.INFO)

bot = telebot.TeleBot(TG_BOT_TOKEN, threaded=False)

chatGptModel="gpt-4o"
deepsickModel="deepseek/deepseek-r1-0528:free"

openRouter="https://openrouter.ai/api/v1"

client = openai.Client(
    api_key=OPEN_ROUTER_API_KEY,
    base_url=openRouter,
)


def get_s3_client():
    session = boto3.session.Session(
        aws_access_key_id=YANDEX_KEY_ID, aws_secret_access_key=YANDEX_KEY_SECRET
    )
    return session.client(
        service_name="s3", endpoint_url="https://storage.yandexcloud.net"
    )


is_typing = False


def start_typing(chat_id):
    global is_typing
    is_typing = True
    typing_thread = threading.Thread(target=typing, args=(chat_id,))
    typing_thread.start()


def typing(chat_id):
    global is_typing
    while is_typing:
        bot.send_chat_action(chat_id, "typing")
        time.sleep(4)


def stop_typing():
    global is_typing
    is_typing = False


@bot.message_handler(commands=["help", "start"])
def send_welcome(message):
    bot.reply_to(
        message,
        ("Привет! Я AI чат-бот. Спроси меня что-нибудь!"),
    )


@bot.message_handler(commands=["new"])
def clear_history(message):
    clear_history_for_chat(message.chat.id)
    bot.reply_to(message, "История чата очищена!")


@bot.message_handler(func=lambda message: True, content_types=["text"])
def echo_message(message):
    start_typing(message.chat.id)

    try:
        text = message.text
        ai_response = process_text_message(text, message.chat.id)
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка, попробуйте позже! {e}")
        return

    stop_typing()

    bot.reply_to(message, ai_response)


def process_text_message(text, chat_id) -> str:
    model = deepsickModel

    s3client = get_s3_client()
    history = []
    try:
        history_object_response = s3client.get_object(
            Bucket=YANDEX_BUCKET, Key=f"{chat_id}.json"
        )
        history = json.loads(history_object_response["Body"].read())
    except:
        pass

    history.append({"role": "user", "content": text})

    try:
        chat_completion = client.chat.completions.create(
            model=model, messages=history
        )
    except Exception as e:
        if type(e).__name__ == "BadRequestError":
            clear_history_for_chat(chat_id)
            return process_text_message(text, chat_id)
        else:
            raise e

    ai_response = chat_completion.choices[0].message.content
    history.append({"role": "assistant", "content": ai_response})

    s3client.put_object(
        Bucket=YANDEX_BUCKET,
        Key=f"{chat_id}.json",
        Body=json.dumps(history),
    )

    return ai_response


def clear_history_for_chat(chat_id):
    try:
        s3client = get_s3_client()
        s3client.put_object(
            Bucket=YANDEX_BUCKET,
            Key=f"{chat_id}.json",
            Body=json.dumps([]),
        )
    except:
        pass


def handler(event, context):
    message = event["body"]
    update = telebot.types.Update.de_json(message)

    if (
        update.message is not None
        and update.message.from_user.username.lower() in TG_BOT_CHATS
    ):
        try:
            bot.process_new_updates([update])
        except Exception as e:
            print(e)

    return {
        "statusCode": 200,
        "body": "ok",
    }
