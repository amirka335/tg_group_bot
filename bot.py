import os
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, Chat
from aiogram.enums import ParseMode
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv
from peewee import (
    SqliteDatabase, Model, AutoField, TextField, DateTimeField, IntegerField,
    ForeignKeyField, DoesNotExist
)

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize bot and dispatcher
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()

# Initialize Cerebras client
cerebras_client = Cerebras(api_key=os.getenv("CEREBRAS_API_KEY"))

DEFAULT_MESSAGE_COUNT = 100
CEREBRAS_MODEL = "qwen-3-235b-a22b-thinking-2507"

# --- Database Setup ---
db = SqliteDatabase('chat_history.db')

class BaseModel(Model):
    class Meta:
        database = db

class Chat(BaseModel):
    chat_id = IntegerField(unique=True, primary_key=True)
    chat_title = TextField(null=True)
    chat_type = TextField() # 'group', 'supergroup', 'private', 'channel'

class ChatMessage(BaseModel):
    message_id = AutoField()
    chat = ForeignKeyField(Chat, backref='messages')
    user_id = IntegerField()
    username = TextField(null=True)
    first_name = TextField()
    last_name = TextField(null=True)
    text = TextField()
    date = DateTimeField()

def initialize_db():
    """Connects to the database and creates tables."""
    logging.info("Connecting to the database and creating tables if they don't exist.")
    db.connect()
    db.create_tables([Chat, ChatMessage])
    logging.info("Database initialized successfully.")

async def save_message_to_db(message: Message):
    """Saves a text message to the database."""
    if not message.text or not message.chat: # Skip empty messages or non-chat updates
        return

    try:
        chat_obj, created = Chat.get_or_create(
            chat_id=message.chat.id,
            defaults={
                'chat_title': message.chat.title,
                'chat_type': message.chat.type
            }
        )
        if not created and message.chat.title != chat_obj.chat_title:
            chat_obj.chat_title = message.chat.title
            chat_obj.save()

        ChatMessage.create(
            chat=chat_obj,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            text=message.text,
            date=message.date
        )
        # logging.info(f"Saved message from {message.from_user.first_name} in chat {message.chat.id}")
    except Exception as e:
        logging.error(f"Error saving message to DB: {e}", exc_info=True)

def get_chat_history_from_db(chat_id: int, limit: int) -> List[Dict[str, Any]]:
    """
    Fetches the last 'limit' messages for a given chat_id from the database.
    Returns a list of dictionaries, sorted chronologically (oldest first).
    """
    history = []
    try:
        chat_obj = Chat.get_by_id(chat_id)
        # Fetch messages ordered by date descending (newest first), then limit
        messages = (ChatMessage
                    .select()
                    .where(ChatMessage.chat == chat_obj)
                    .order_by(ChatMessage.date.desc())
                    .limit(limit))
        
        for msg in messages:
            sender_name = msg.first_name
            if msg.last_name:
                sender_name += f" {msg.last_name}"
            # if msg.username: # Optional: add username
            #     sender_name += f" (@{msg.username})"
            
            message_date = msg.date
            if isinstance(message_date, str):
                try:
                    message_date = datetime.fromisoformat(message_date)
                except ValueError:
                    logging.warning(f"Could not parse date string: {message_date} for message_id {msg.message_id}")
                    # Fallback to current time or skip, for now, let's use current time to avoid crashing
                    message_date = datetime.now() 
            
            history.append({
                "sender_name": sender_name,
                "text": msg.text,
                "date": message_date
            })
        
        # Messages are fetched newest to oldest, reverse for chronological order
        return history[::-1]
    except DoesNotExist:
        logging.info(f"No chat found in DB with id: {chat_id}")
        return []
    except Exception as e:
        logging.error(f"Error fetching chat history from DB for chat {chat_id}: {e}", exc_info=True)
        return []

# --- Cerebras API Interaction ---
async def call_cerebras_api(prompt: str, is_qwen_command: bool = False) -> str:
    """
    Sends a prompt to the Cerebras API and returns the response.
    """
    try:
        logging.info(f"Sending prompt to Cerebras: {prompt[:200]}...")
        
        system_prompt_content = (
            "Ты — полезный ассистент. Отвечай на русском языке, если в запросе используется русский язык. "
            "Будь краток, по существу. "
            "Используй только разметку MarkdownV2, поддерживаемую Telegram: **жирный**, __курсив__, `код`, ~~перечеркнутый~~, ```блок кода```, ||скрытый текст||. "
            "Не используй HTML или другие форматы разметки. "
            "Убедись, что вся разметка корректна для MarkdownV2: экранируй специальные символы \\, _, *, [, ], (, ), ~, `, >, #, +, -, =, |, {, }, ., !"
        )

        if is_qwen_command:
            system_prompt_content += (
                " Если для ответа на вопрос пользователя в предоставленных сообщениях чата нет информации, "
                "отвечай на вопрос самостоятельно, используя свои знания."
                "Никогда не отвечай на вопрос в формате [Информации о ... в предоставленных сообщениях чата нет.]"
                "Всегда отвечай на вопрос, даже если он не связан с чатом."
                "Не пиши, что в чате нет информации, если в чате нет информации, генерирует ответ, не опираясь на нее."
                "То есть решение задачи превыше информации в чате. Даже если в чате информация не полная,"
                "то на ее основе дополняй информацию и генерирует ответ."
            )
        else: # For /history command
            system_prompt_content += (
                "Предоставляй сводки, основываясь *только* на предоставленном контексте чата. "
                "Не добавляй информацию, отсутствующую в чате."
            )

        chat_completion = cerebras_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt_content},
                {"role": "user", "content": prompt}
            ],
            model=CEREBRAS_MODEL,
        )
        response_content = chat_completion.choices[0].message.content
        logging.info(f"Raw Cerebras response: {response_content[:500]}...")
        
        # Attempt to filter out the reasoning part for "thinking" models
        final_response = response_content.strip()
        
        # Try to split by a closing thinking tag if it exists.
        # If no tag is found, the full response will be returned.
        thinking_tags = ["</think>", "</reasoning>", "<|im_end|>"]
        for tag in thinking_tags:
            if tag in final_response:
                logging.info(f"Found thinking tag '{tag}', splitting response.")
                final_response = final_response.split(tag, 1)[-1].strip()
                break # Stop after the first found tag
        else:
            # This 'else' belongs to the 'for' loop, executed if no 'break' occurred (i.e., no tag found)
            logging.info("No thinking tag found, returning the full response.")

        logging.info(f"Final Cerebras response: {final_response[:200]}...")
        return final_response
    except Exception as e:
        logging.error(f"Error calling Cerebras API: {type(e).__name__} - {e}", exc_info=True)
        return "Извините, произошла ошибка при обработке вашего запроса сервисом ИИ."

# --- Command Handlers ---
@dp.message(Command("history"))
async def handle_history_command(message: Message):
    processing_msg = None
    try:
        parts = message.text.split()
        num_messages = DEFAULT_MESSAGE_COUNT
        if len(parts) > 1 and parts[1].isdigit():
            num_messages = int(parts[1])
            if num_messages <= 0 or num_messages > 500:
                num_messages = DEFAULT_MESSAGE_COUNT
        
        processing_msg = await message.reply(f"Анализирую последние {num_messages} сообщений из сохраненной истории... Это может занять некоторое время.")
        
        # Save the bot's processing message to database
        if processing_msg:
            await save_message_to_db(processing_msg)

        chat_history = get_chat_history_from_db(message.chat.id, num_messages)

        if not chat_history:
            if processing_msg:
                await processing_msg.delete()
            error_msg = await message.reply("В моей базе данных еще нет сохраненных сообщений из этого чата. Пожалуйста, подождите, пока я их соберу.")
            await save_message_to_db(error_msg)
            return

        formatted_history = "\n".join(
            [f"{msg['sender_name']} ({msg['date'].strftime('%Y-%m-%d %H:%M:%S')}): {msg['text']}" for msg in chat_history]
        )

        summary_prompt = (
            f"Проанализируй следующие сообщения чата, которые идут в хронологическом порядке (сначала самые старые). "
            f"Предоставь краткую и информативную сводку последних новостей или важных обсуждений. "
            f"Сосредоточься на ключевых моментах, решениях или обновлениях. Избегай ненужных деталей и 'воды'. "
            f"Не упоминай, что ты суммируешь чат, просто предоставь сводку напрямую на русском языке.\n\n"
            f"Сообщения чата:\n{formatted_history}\n\n"
            f"Выводи только финальный ответ, без своих рассуждений."
        )
        
        summary = await call_cerebras_api(summary_prompt, is_qwen_command=False)

        if processing_msg:
            await processing_msg.delete()
        response_msg = await message.reply(summary, parse_mode=ParseMode.MARKDOWN_V2)
        await save_message_to_db(response_msg)

    except ValueError:
        if processing_msg:
            try:
                await processing_msg.delete()
            except Exception as del_e:
                logging.warning(f"Could not delete processing message in /history ValueError: {del_e}")
        error_msg = await message.reply(f"Неверное число. Используется значение по умолчанию: {DEFAULT_MESSAGE_COUNT} сообщений.")
        await save_message_to_db(error_msg)
    except Exception as e:
        logging.error(f"Error in /history command: {e}", exc_info=True)
        if processing_msg:
            try:
                await processing_msg.delete()
            except Exception as del_e:
                logging.warning(f"Could not delete processing message in /history Exception: {del_e}")
        error_msg = await message.reply("Произошла ошибка при попытке обработать команду /history.")
        await save_message_to_db(error_msg)

@dp.message(Command("qwen"))
async def handle_qwen_command(message: Message):
    processing_msg = None
    try:
        parts = message.text.split(maxsplit=2)
        
        num_messages = DEFAULT_MESSAGE_COUNT
        user_question = ""

        if len(parts) == 1:
            await message.reply("Пожалуйста, задайте вопрос после команды /qwen. Например: /qwen Что было решено по проекту?")
            return
        elif len(parts) == 2:
            user_question = parts[1]
        elif len(parts) == 3:
            if parts[1].isdigit():
                num_messages = int(parts[1])
                if num_messages <= 0 or num_messages > 500:
                    num_messages = DEFAULT_MESSAGE_COUNT
                user_question = parts[2]
            else:
                user_question = f"{parts[1]} {parts[2]}"
        
        if not user_question:
             await message.reply("Пожалуйста, задайте вопрос. Например: /qwen Что было решено по проекту?")
             return

        processing_msg = await message.reply(f"Ищу в последних {num_messages} сохраненных сообщениях ответ на ваш вопрос... Это может занять некоторое время.")

        chat_history = get_chat_history_from_db(message.chat.id, num_messages)

        if not chat_history:
            if processing_msg:
                await processing_msg.delete()
            await message.reply("В моей базе данных еще нет сохраненных сообщений из этого чата для ответа на ваш вопрос. Пожалуйста, подождите.")
            return

        formatted_history = "\n".join(
            [f"{msg['sender_name']} ({msg['date'].strftime('%Y-%m-%d %H:%M:%S')}): {msg['text']}" for msg in chat_history]
        )

        qwen_prompt = (
            f"Основываясь *только* на следующих сообщениях чата (в хронологическом порядке, сначала самые старые), "
            f"пожалуйста, кратко и точно ответь на вопрос пользователя. "
            f"Если информации в чате нет, четко укажи на это. Отвечай на русском языке.\n\n"
            f"Сообщения чата:\n{formatted_history}\n\n"
            f"Вопрос пользователя: {user_question}\n\n"
            f"Выводи только финальный ответ, без своих рассуждений."
        )
        
        answer = await call_cerebras_api(qwen_prompt, is_qwen_command=True)

        # Post-process the answer to extract only the final response after "Вывод:"
        if "Вывод:" in answer:
            answer = answer.split("Вывод:", 1)[1].strip()
        elif "вывод:" in answer:
            answer = answer.split("вывод:", 1)[1].strip()
        elif "Ответ:" in answer:
            answer = answer.split("Ответ:", 1)[1].strip()
        elif "ответ:" in answer:
            answer = answer.split("ответ:", 1)[1].strip()
        elif "### Ответ" in answer:
            answer = answer.split("### Ответ", 1)[1].strip()
        elif "### Ответ:" in answer:
            answer = answer.split("### Ответ:", 1)[1].strip()
        elif "### Вывод" in answer:
            answer = answer.split("### Вывод", 1)[1].strip()
        elif "### Вывод:" in answer:
            answer = answer.split("### Вывод:", 1)[1].strip()
        elif "### Финальный Ответ" in answer:
            answer = answer.split("### Финальный Ответ", 1)[1].strip()
        elif "### Финальный Ответ:" in answer:
            answer = answer.split("### Финальный Ответ:", 1)[1].strip()
        elif "### Финальный Вывод" in answer:
            answer = answer.split("### Финальный Вывод", 1)[1].strip()
        elif "### Финальный Вывод:" in answer:
            answer = answer.split("### Финальный Вывод:", 1)[1].strip()
        elif "### Final Answer" in answer:
            answer = answer.split("### Final Answer", 1)[1].strip()
        elif "### Final Answer:" in answer:
            answer = answer.split("### Final Answer:", 1)[1].strip()
        elif "### Final Response" in answer:
            answer = answer.split("### Final Response", 1)[1].strip()
        elif "### Final Response:" in answer:
            answer = answer.split("### Final Response:", 1)[1].strip()
        elif "Final Answer:" in answer:
            answer = answer.split("Final Answer:", 1)[1].strip()
        elif "Final Response:" in answer:
            answer = answer.split("Final Response:", 1)[1].strip()
        elif "Итоговый ответ:" in answer:
            answer = answer.split("Итоговый ответ:", 1)[1].strip()
        elif "Итоговый ответ" in answer:
            answer = answer.split("Итоговый ответ", 1)[1].strip()
        elif "Итог:" in answer:
            answer = answer.split("Итог:", 1)[1].strip()
        elif "итог:" in answer:
            answer = answer.split("итог:", 1)[1].strip()
        elif "Решение:" in answer:
            answer = answer.split("Решение:", 1)[1].strip()
        elif "решение:" in answer:
            answer = answer.split("решение:", 1)[1].strip()
        elif "Результат:" in answer:
            answer = answer.split("Результат:", 1)[1].strip()
        elif "результат:" in answer:
            answer = answer.split("результат:", 1)[1].strip()
        elif "Заключение:" in answer:
            answer = answer.split("Заключение:", 1)[1].strip()
        elif "заключение:" in answer:
            answer = answer.split("заключение:", 1)[1].strip()
        elif "Summary:" in answer:
            answer = answer.split("Summary:", 1)[1].strip()
        elif "Summary" in answer:
            answer = answer.split("Summary", 1)[1].strip()
        elif "Ответ на вопрос:" in answer:
            answer = answer.split("Ответ на вопрос:", 1)[1].strip()
        elif "Ответ на вопрос" in answer:
            answer = answer.split("Ответ на вопрос", 1)[1].strip()
        elif "###" in answer:
            parts = answer.split("###", 1)
            if len(parts) > 1:
                answer = parts[1].strip()
        # If none of the above patterns are found, the full answer is sent as is.

        if processing_msg:
            await processing_msg.delete()
        # Don't escape the text - let the AI handle markdown formatting
        try:
            response_msg = await message.reply(answer, parse_mode=ParseMode.MARKDOWN_V2)
            await save_message_to_db(response_msg)
        except Exception as e:
            # Fallback to plain text if MarkdownV2 parsing fails
            logging.warning(f"MarkdownV2 parsing failed, sending plain text: {e}")
            response_msg = await message.reply(answer)
            await save_message_to_db(response_msg)

    except ValueError:
        if processing_msg:
            await processing_msg.delete()
        error_msg = await message.reply(f"Неверное число. Используется значение по умолчанию: {DEFAULT_MESSAGE_COUNT} сообщений для вашего вопроса.")
        await save_message_to_db(error_msg)
    except Exception as e:
        logging.error(f"Error in /qwen command: {e}", exc_info=True)
        if processing_msg:
            await processing_msg.delete()
        error_msg = await message.reply("Произошла ошибка при попытке обработать команду /qwen.")
        await save_message_to_db(error_msg)

# --- Message Handlers ---
@dp.message(F.text)
async def handle_all_text_messages(message: Message):
    """Handles all text messages in chats the bot is part of to save them to the DB."""
    # Avoid saving bot's own messages or command messages that are already handled
    if message.from_user.id == bot.id:
        return
    if message.text.startswith('/'):
        # Commands are handled by specific handlers, no need to save them as regular messages
        # However, if you want to include commands in history, remove this check.
        # For now, let's assume commands are not part of the 'discussion' to summarize.
        return

    if message.chat.type in ['group', 'supergroup']:
        await save_message_to_db(message)

@dp.message(F.new_chat_members)
async def on_new_chat_members(message: Message):
    """Sends a welcome message when the bot is added to a group."""
    for member in message.new_chat_members:
        if member.id == bot.id:
            await message.reply(
                "Всем привет! Я здесь, чтобы помочь.\n\n"
                f"Используйте `/history [n]` для получения сводки последних `n` сообщений (по умолчанию: {DEFAULT_MESSAGE_COUNT}).\n"
                f"Используйте `/qwen [n] [ваш вопрос]` чтобы задать вопрос на основе последних `n` сообщений (по умолчанию: {DEFAULT_MESSAGE_COUNT}).\n\n"
                "Я начинаю сохранять сообщения с этого момента, чтобы анализировать их в будущем.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            break

# --- Main Function ---
async def main():
    initialize_db() # Initialize DB before starting polling
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Starting bot polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        if not db.is_closed():
            db.close()
            logging.info("Database connection closed.")
