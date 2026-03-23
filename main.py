import asyncio
import logging
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton


# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# ID админов, которым разрешено пользоваться ботом
ADMIN_IDS = {
    7923768233,  # замени на свой Telegram user_id
    5682655968,  # если нужен второй админ
}

# ID чатов / каналов, куда бот будет публиковать курс
TARGET_CHATS = [
    -1003483750029,
    -1003363430472,
    -1003455248093,
    -1003453808641,
]

# Шаблон поста
POST_TEMPLATE = """
📅 <b>{post_date}</b> курс обмена рублей на юани

💱 <b>500¥+</b> ➡️ <b>{rate_500}</b>₽
💱 <b>1000¥+</b> ➡️ <b>{rate_1000}</b>₽
💱 <b>3000¥+</b> ➡️ <b>{rate_3000}</b>₽
💱 <b>10000¥+</b> ➡️ <b>{rate_10000}</b>₽
💱 <b>25000¥+</b> ➡️ <b>{rate_25000}</b>₽

💵 Для оплаты в <b>USDT</b> уточните курс в лс

🏦 Принимаем рубли с любого банка России

✅Перевод на Alipay, Wechat,  оплата поставщику напрямую поставщикам

📝 Отзывы: @reviews_lilei

📩 Пишите по обмену — @lei_rmb
""".strip()


# =========================
# ЛОГИРОВАНИЕ
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


# =========================
# FSM
# =========================

class PublishRateState(StatesGroup):
    waiting_for_date = State()
    waiting_for_rates = State()


# =========================
# КЛАВИАТУРА
# =========================

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Опубликовать курс")]
    ],
    resize_keyboard=True
)


# =========================
# ROUTER
# =========================

router = Router()


# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def validate_date(date_text: str) -> str:
    try:
        parsed_date = datetime.strptime(date_text.strip(), "%d.%m.%Y")
        return parsed_date.strftime("%d.%m.%Y")
    except ValueError:
        raise ValueError("Дата должна быть в формате ДД.ММ.ГГГГ, например: 04.03.2026")


def normalize_rate(raw_value: str) -> str:
    value = raw_value.strip().replace(",", ".")
    try:
        decimal_value = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"Некорректное число: {raw_value}")

    if decimal_value <= 0:
        raise ValueError(f"Курс должен быть больше нуля: {raw_value}")

    normalized = format(decimal_value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")

    return normalized.replace(".", ",")


def parse_rates(text: str) -> List[str]:
    parts = text.replace("\n", " ").split()
    if len(parts) != 5:
        raise ValueError(
            "Нужно ввести ровно 5 значений через пробел.\n\n"
            "Порядок такой:\n"
            "500¥+ 1000¥+ 3000¥+ 10000¥+ 25000¥+\n\n"
            "Пример:\n"
            "11,85 11,75 11,70 11,68 11,65"
        )

    return [normalize_rate(part) for part in parts]


def build_post(post_date: str, rates: List[str]) -> str:
    return POST_TEMPLATE.format(
        post_date=post_date,
        rate_500=rates[0],
        rate_1000=rates[1],
        rate_3000=rates[2],
        rate_10000=rates[3],
        rate_25000=rates[4],
    )


# =========================
# ХЕНДЛЕРЫ
# =========================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()

    if not is_admin(message.from_user.id):
        await message.answer("У тебя нет доступа к этому боту.")
        return

    await message.answer(
        "Бот для публикации курса.\n\n"
        "Нажми кнопку ниже, чтобы опубликовать новый курс.",
        reply_markup=main_keyboard
    )


@router.message(F.text == "Опубликовать курс")
async def publish_rate_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("У тебя нет доступа к этому действию.")
        return

    await state.set_state(PublishRateState.waiting_for_date)
    await message.answer(
        "Введи дату для поста в формате:\n"
        "<code>04.03.2026</code>"
    )


@router.message(PublishRateState.waiting_for_date)
async def process_post_date(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("У тебя нет доступа к этому действию.")
        await state.clear()
        return

    try:
        post_date = validate_date(message.text)
    except ValueError as e:
        await message.answer(f"Ошибка:\n{e}")
        return

    await state.update_data(post_date=post_date)
    await state.set_state(PublishRateState.waiting_for_rates)

    await message.answer(
        "Теперь введи 5 значений курса через пробел в таком порядке:\n\n"
        "1. 500¥+\n"
        "2. 1000¥+\n"
        "3. 3000¥+\n"
        "4. 10000¥+\n"
        "5. 25000¥+\n\n"
        "Пример:\n"
        "<code>11,85 11,75 11,70 11,68 11,65</code>"
    )


@router.message(PublishRateState.waiting_for_rates)
async def process_rates(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("У тебя нет доступа к этому действию.")
        await state.clear()
        return

    try:
        rates = parse_rates(message.text)
        data = await state.get_data()
        post_date = data["post_date"]
        post_text = build_post(post_date, rates)
    except ValueError as e:
        await message.answer(f"Ошибка:\n{e}")
        return
    except KeyError:
        await state.clear()
        await message.answer("Ошибка состояния. Нажми «Опубликовать курс» заново.")
        return

    success_chats = []
    failed_chats = []

    for chat_id in TARGET_CHATS:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=post_text,
                disable_web_page_preview=True
            )
            success_chats.append(str(chat_id))
        except Exception as e:
            logger.exception("Не удалось отправить сообщение в чат %s", chat_id)
            failed_chats.append(f"{chat_id} — {e}")

    await state.clear()

    result_text = [
        "✅ Публикация завершена.",
        "",
        f"Дата: {post_date}",
        f"Курсы: {' | '.join(rates)}",
    ]

    if success_chats:
        result_text.append("")
        result_text.append("Успешно отправлено в чаты:")
        result_text.extend([f"• {chat_id}" for chat_id in success_chats])

    if failed_chats:
        result_text.append("")
        result_text.append("Ошибки отправки:")
        result_text.extend([f"• {item}" for item in failed_chats])

    await message.answer("\n".join(result_text), reply_markup=main_keyboard)


@router.message()
async def fallback_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("У тебя нет доступа к этому боту.")
        return

    await message.answer(
        "Используй кнопку <b>«Опубликовать курс»</b>.",
        reply_markup=main_keyboard
    )


# =========================
# ЗАПУСК
# =========================

async def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("Не найден BOT_TOKEN. Добавь токен в переменные окружения.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())