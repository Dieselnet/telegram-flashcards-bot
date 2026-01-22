import asyncio
import json
import logging
import os
import random
from typing import Dict, List

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")

MAX_CARDS_PER_USER = 200

storage = MemoryStorage()
dp = Dispatcher(storage=storage)
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
router = Router()
dp.include_router(router)


class Modes(StatesGroup):
    add_card = State()
    add_caption_only = State()


user_cards: Dict[int, List[Dict[str, str]]] = {}


def load_all() -> Dict[str, List[Dict[str, str]]]:
    if not os.path.exists("cards.json"):
        return {}
    try:
        with open("cards.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("Ошибка чтения cards.json:", e)
        return {}


def save_all(data: Dict[str, List[Dict[str, str]]]) -> None:
    with open("cards.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_cards(user_id: int) -> List[Dict[str, str]]:
    data = load_all()
    return data.get(str(user_id), [])


def save_cards(user_id: int, cards: List[Dict[str, str]]) -> None:
    data = load_all()
    data[str(user_id)] = cards
    save_all(data)


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1. Добавить карточку")],
            [KeyboardButton(text="2. Угадать подпись")],
            [KeyboardButton(text="3. Угадать картинку")],
            [KeyboardButton(text="📋 Мои карточки")],
        ],
        resize_keyboard=True
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    print(">>> /start от", message.from_user.id)
    await state.clear()
    await message.answer(
        "Привет! Это бот для карточек.\n"
        "Сейчас доступны:\n"
        "1) Добавление карточек\n"
        "2) Угадать подпись\n"
        "3) Угадать картинку\n"
        "📋 Просмотр/удаление карточек\n\n"
        "Выбери режим:",
        reply_markup=main_menu_kb(),
    )


# ---------- РЕЖИМ 1: ДОБАВЛЕНИЕ КАРТОЧЕК ----------

@router.message(F.text == "1. Добавить карточку")
async def add_mode(message: Message, state: FSMContext):
    print(">>> выбор режима: добавить карточку")
    await state.set_state(Modes.add_card)
    await message.answer(
        "Отправь картинку. Можно:\n"
        "- сразу с подписью в caption\n"
        "- или без подписи — тогда я попрошу текст отдельно.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Modes.add_card, F.photo)
async def process_add_card_photo(message: Message, state: FSMContext):
    user_id = message.from_user.id

    cards = load_cards(user_id)
    if len(cards) >= MAX_CARDS_PER_USER:
        await message.answer(
            f"Достигнут лимит {MAX_CARDS_PER_USER} карточек.\n"
            f"Сначала удалите лишние через кнопку '📋 Мои карточки'."
        )
        await state.clear()
        await message.answer("Главное меню:", reply_markup=main_menu_kb())
        return

    caption = (message.caption or "").strip()
    file_id = message.photo[-1].file_id

    if caption:
        cards.append({"image": file_id, "caption": caption})
        save_cards(user_id, cards)
        print(f">>> новая карточка от {user_id}: file_id={file_id}, caption={caption!r}")
        await message.answer("Карточка сохранена ✅")
        await state.clear()
        await message.answer("Главное меню. Выбери режим:", reply_markup=main_menu_kb())
    else:
        print(f">>> фото без подписи от {user_id}: file_id={file_id}")
        await state.update_data(pending_image=file_id)
        await state.set_state(Modes.add_caption_only)
        await message.answer("Теперь напиши подпись к этой картинке (слово/фраза).")


@router.message(Modes.add_caption_only, F.text)
async def process_add_caption_only(message: Message, state: FSMContext):
    user_id = message.from_user.id
    caption = message.text.strip()
    data = await state.get_data()
    file_id = data.get("pending_image")

    if not file_id:
        await message.answer("Не нашёл картинку в памяти, начнём сначала.")
        await state.clear()
        await message.answer("Главное меню. Выбери режим:", reply_markup=main_menu_kb())
        return

    cards = load_cards(user_id)
    if len(cards) >= MAX_CARDS_PER_USER:
        await message.answer(
            f"Достигнут лимит {MAX_CARDS_PER_USER} карточек.\n"
            f"Сначала удалите лишние через кнопку '📋 Мои карточки'."
        )
        await state.clear()
        await message.answer("Главное меню:", reply_markup=main_menu_kb())
        return

    cards.append({"image": file_id, "caption": caption})
    save_cards(user_id, cards)

    print(f">>> отдельная подпись от {user_id}: file_id={file_id}, caption={caption!r}")
    await message.answer("Карточка сохранена ✅")

    await state.clear()
    await message.answer("Главное меню. Выбери режим:", reply_markup=main_menu_kb())


# ---------- ПРОСМОТР / УДАЛЕНИЕ КАРТОЧЕК ----------

def card_inline_kb(index: int, total: int) -> InlineKeyboardMarkup:
    buttons = []
    if index > 0:
        buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"card_prev:{index}"))
    buttons.append(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"card_del:{index}"))
    if index < total - 1:
        buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"card_next:{index}"))

    return InlineKeyboardMarkup(inline_keyboard=[buttons])


@router.message(F.text == "📋 Мои карточки")
@router.message(Command("cards"))
async def show_cards(message: Message):
    user_id = message.from_user.id
    cards = load_cards(user_id)
    if not cards:
        await message.answer("У тебя пока нет карточек.")
        return

    index = 0
    card = cards[index]
    caption = f"Карточка {index+1}/{len(cards)}\n\n{card['caption']}"
    await message.answer_photo(
        photo=card["image"],
        caption=caption,
        reply_markup=card_inline_kb(index, len(cards)),
    )


@router.callback_query(F.data.startswith("card_"))
async def cards_callbacks(callback: CallbackQuery):
    user_id = callback.from_user.id
    cards = load_cards(user_id)
    if not cards:
        await callback.answer("Карточек больше нет.", show_alert=True)
        try:
            await callback.message.delete()
        except Exception:
            pass
        return

    action, arg = callback.data.split(":")
    index = int(arg)

    if action == "card_prev":
        index = max(0, index - 1)
    elif action == "card_next":
        index = min(len(cards) - 1, index + 1)
    elif action == "card_del":
        deleted = cards.pop(index)
        save_cards(user_id, cards)
        print(f">>> удалена карточка пользователя {user_id}: {deleted!r}")

        if not cards:
            await callback.message.edit_caption("Все карточки удалены.")
            await callback.answer("Карточка удалена, список пуст.")
            return

        if index >= len(cards):
            index = len(cards) - 1

        await callback.answer("Карточка удалена.")
    else:
        await callback.answer("Неизвестное действие.")
        return

    card = cards[index]
    caption = f"Карточка {index+1}/{len(cards)}\n\n{card['caption']}"
    try:
        await callback.message.edit_media(
            media={"type": "photo", "media": card["image"]},
            reply_markup=card_inline_kb(index, len(cards)),
        )
        await callback.message.edit_caption(
            caption=caption,
            reply_markup=card_inline_kb(index, len(cards)),
        )
    except Exception:
        await callback.message.answer_photo(
            photo=card["image"],
            caption=caption,
            reply_markup=card_inline_kb(index, len(cards)),
        )


# ---------- РЕЖИМ 2: УГАДАТЬ ПОДПИСЬ ----------

def build_quiz_keyboard(options: List[str], correct_idx: int) -> InlineKeyboardMarkup:
    buttons = []
    for i, text in enumerate(options):
        buttons.append(
            [InlineKeyboardButton(text=text, callback_data=f"quiz2_{i}_{correct_idx}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(F.text == "2. Угадать подпись")
async def guess_caption_start(message: Message):
    user_id = message.from_user.id
    cards = load_cards(user_id)
    if len(cards) < 3:
        await message.answer("Нужно минимум 3 карточки, чтобы играть в режим 'Угадать подпись'.")
        return

    question_card = random.choice(cards)

    other_cards = [c for c in cards if c is not question_card]
    random.shuffle(other_cards)
    distractors = [c["caption"] for c in other_cards[:2]]

    options = [question_card["caption"]] + distractors
    random.shuffle(options)

    correct_idx = options.index(question_card["caption"])

    kb = build_quiz_keyboard(options, correct_idx)

    await message.answer_photo(
        photo=question_card["image"],
        caption="Выбери правильную подпись к картинке:",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("quiz2_"))
async def guess_caption_check(callback: CallbackQuery):
    _, pressed_str, correct_str = callback.data.split("_")
    pressed = int(pressed_str)
    correct = int(correct_str)

    if pressed == correct:
        await callback.answer("✅ Правильно!", show_alert=False)
    else:
        await callback.answer("❌ Неправильно.", show_alert=False)


# ---------- РЕЖИМ 3: УГАДАТЬ КАРТИНКУ ----------

def build_quiz3_keyboard(correct_idx: int) -> InlineKeyboardMarkup:
    # три кнопки: Картинка 1/2/3
    row = []
    for i in range(3):
        row.append(
            InlineKeyboardButton(
                text=f"Картинка {i+1}",
                callback_data=f"quiz3_{i}_{correct_idx}",
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=[row])


@router.message(F.text == "3. Угадать картинку")
async def guess_image_start(message: Message):
    user_id = message.from_user.id
    cards = load_cards(user_id)
    if len(cards) < 3:
        await message.answer("Нужно минимум 3 карточки, чтобы играть в режим 'Угадать картинку'.")
        return

    # выбираем 3 случайные карточки
    options = random.sample(cards, 3)
    correct_idx = random.randint(0, 2)
    correct_card = options[correct_idx]

    # отправляем три картинки подряд
    for idx, card in enumerate(options, start=1):
        await message.answer_photo(
            photo=card["image"],
            caption=f"Вариант {idx}",
        )

    # отдельно задаём вопрос с кнопками
    kb = build_quiz3_keyboard(correct_idx)
    await message.answer(
        f"Какое изображение соответствует подписи:\n\n<b>{correct_card['caption']}</b>",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("quiz3_"))
async def guess_image_check(callback: CallbackQuery):
    _, pressed_str, correct_str = callback.data.split("_")
    pressed = int(pressed_str)
    correct = int(correct_str)

    if pressed == correct:
        await callback.answer("✅ Правильно! Это нужная картинка.", show_alert=False)
    else:
        await callback.answer("❌ Неправильно. Попробуй ещё раз или запусти режим заново.", show_alert=False)


async def main():
    print("Бот запускается...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    if not os.path.exists("cards.json"):
        with open("cards.json", "w", encoding="utf-8") as f:
            json.dump({}, f)
    asyncio.run(main())
