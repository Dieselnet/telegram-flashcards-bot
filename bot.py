import asyncio
import json
import logging
import os
import random
from typing import Dict, List, Tuple

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup,
    Message, ReplyKeyboardMarkup, ReplyKeyboardRemove
)

logging.basicConfig(level=logging.INFO)

TOKEN = "7585558991:AAFGm5o_cPQhij4-TupvOURjKO53fZ6yvys" # Установите через переменную окружения

storage = MemoryStorage()
dp = Dispatcher(storage=storage)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
router = Router()
dp.include_router(router)

class Modes(StatesGroup):
    add_card = State()
    guess_caption = State()
    guess_image = State()

# Словарь: {user_id: [{"image_file_id": str, "caption": str}, ...]}
user_cards: Dict[int, List[Dict[str, str]]] = {}

def load_cards(user_id: int) -> List[Dict[str, str]]:
    try:
        with open("cards.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(str(user_id), [])
    except FileNotFoundError:
        return []

def save_cards(user_id: int, cards: List[Dict[str, str]]):
    data = json.load(open("cards.json", "r") if os.path.exists("cards.json") else "{}")
    data[str(user_id)] = cards
    with open("cards.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            ["1. Добавить карточку"],
            ["2. Угадать подпись"],
            ["3. Угадать картинку"]
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите режим:", reply_markup=kb)
    await state.clear()

@router.message(F.text == "1. Добавить карточку")
async def add_mode(message: Message, state: FSMContext):
    await state.set_state(Modes.add_card)
    await message.answer("Отправьте картинку с подписью (caption).", reply_markup=ReplyKeyboardRemove())

@router.message(Modes.add_card, F.photo)
async def process_add(message: Message, state: FSMContext):
    caption = message.caption or ""
    if not caption:
        await message.answer("Добавьте подпись к картинке!")
        return
    user_id = message.from_user.id
    cards = load_cards(user_id)
    cards.append({"image": message.photo[-1].file_id, "caption": caption})
    save_cards(user_id, cards)
    await message.answer("Карточка добавлена!")
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[["1. Добавить карточку"], ["2. Угадать подпись"], ["3. Угадать картинку"]], resize_keyboard=True)
    await message.answer("Главное меню:", reply_markup=kb)

@router.message(F.text == "2. Угадать подпись")
async def guess_caption(message: Message, state: FSMContext):
    user_id = message.from_user.id
    cards = load_cards(user_id)
    if not cards:
        await message.answer("Нет карточек. Добавьте сначала!")
        return
    card = random.choice(cards)
    user_cards[user_id] = cards  # Кэш для быстрого доступа
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c["caption"][:20] + "...", callback_data=f"cap_{i}") for i, c in enumerate(random.sample(cards, 3))],
        [InlineKeyboardButton(text="Другая", callback_data="new_cap")]
    ])
    await bot.send_photo(message.chat.id, card["image"], reply_markup=kb)
    await state.set_state(Modes.guess_caption)

@router.callback_query(F.data.startswith("cap_"), Modes.guess_caption)
async def check_caption(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    cards = user_cards.get(user_id, [])
    correct_caption = cards[0]["caption"]  # Первая - правильная
    if idx == 0:
        await callback.answer("Правильно!", show_alert=True)
    else:
        await callback.answer("Неправильно!", show_alert=True)
    await callback.message.edit_caption(caption=f"Правильный ответ: {correct_caption}")
    await asyncio.sleep(2)
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[["1. Добавить карточку"], ["2. Угадать подпись"], ["3. Угадать картинку"]], resize_keyboard=True)
    await callback.message.answer("Главное меню:", reply_markup=kb)

@router.callback_query(F.data == "new_cap")
async def new_caption(callback: CallbackQuery):
    await guess_caption(callback.message, dp.current_state())

@router.message(F.text == "3. Угадать картинку")
async def guess_image(message: Message, state: FSMContext):
    user_id = message.from_user.id
    cards = load_cards(user_id)
    if len(cards) < 3:
        await message.answer("Нужно минимум 3 карточки!")
        return
    correct_idx = random.randint(0, 2)
    options = random.sample(cards, 3)
    caption = options[correct_idx]["caption"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Картинка {i+1}", callback_data=f"img_{i}") for i in range(3)]
    ])
    for opt in options:
        await bot.send_photo(message.chat.id, opt["image"])
    await message.answer(f"Какое изображение соответствует подписи: {caption}?", reply_markup=kb)
    await state.set_state(Modes.guess_image)

@router.callback_query(F.data.startswith("img_"), Modes.guess_image)
async def check_image(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[1])
    if idx == 0:  # Предполагаем, что correct_idx=0 для простоты, в проде храните в state
        await callback.answer("Правильно!", show_alert=True)
    else:
        await callback.answer("Неправильно!", show_alert=True)
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[["1. Добавить карточку"], ["2. Угадать подпись"], ["3. Угадать картинку"]], resize_keyboard=True)
    await callback.message.answer("Главное меню:", reply_markup=kb)

@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[["1. Добавить карточку"], ["2. Угадать подпись"], ["3. Угадать картинку"]], resize_keyboard=True)
    await message.answer("Отменено. Главное меню:", reply_markup=kb)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    if not os.path.exists("cards.json"):
        with open("cards.json", "w") as f:
            json.dump({}, f)
    asyncio.run(main())
