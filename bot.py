import asyncio
import csv
import io
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# ----------------------------------------------------
# CONFIGURATION & CONSTANTS
# ----------------------------------------------------
BOT_TOKEN = "7880979409:AAGD_8_S0z8c-6z8tJ2e1Vv7X_910111213"  # O'zingizning tokeningiz
ADMIN_ID = 8867842080  # Admin Telegram ID raqami

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ----------------------------------------------------
# FSM STATES (Muloqot holatlari)
# ----------------------------------------------------
class AdminStates(StatesGroup):
  waiting_for_delete_id = State()
  waiting_for_broadcast = State()


# ----------------------------------------------------
# DATABASE FUNCTIONS (Baza bilan ishlash)
# ----------------------------------------------------
def init_db():
  conn = sqlite3.connect("new_bot_database.db")
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            phone_number TEXT,
            username TEXT
        )
    """)
  conn.commit()
  conn.close()


init_db()


def get_all_users():
  conn = sqlite3.connect("new_bot_database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT user_id, full_name, phone_number, username FROM users")
  users = cursor.fetchall()
  conn.close()
  return users


def delete_user(user_id: int) -> bool:
  conn = sqlite3.connect("new_bot_database.db")
  cursor = conn.cursor()
  cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
  changes = conn.total_changes
  conn.commit()
  conn.close()
  return changes > 0


def delete_all_users():
  conn = sqlite3.connect("new_bot_database.db")
  cursor = conn.cursor()
  cursor.execute("DELETE FROM users")
  conn.commit()
  conn.close()


# ----------------------------------------------------
# KEYBOARDS (Klaviaturalar)
# ----------------------------------------------------
def get_admin_keyboard():
  return ReplyKeyboardMarkup(
      keyboard=[
          [
              KeyboardButton(text="📞 Ro'yxatdan o'tganlar raqamlari"),
              KeyboardButton(text="📊 Statistika"),
          ],
          [
              KeyboardButton(text="📊 Excel yuklab olish"),
              KeyboardButton(text="📢 Reklama yuborish"),
          ],
          [KeyboardButton(text="❌ Obunachini o'chirish")],
      ],
      resize_keyboard=True,
      is_persistent=True,
  )


def get_delete_options_inline():
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🆔 ID bo'yicha o'chirish",
                  callback_data="delete_by_id",
              )
          ],
          [
              InlineKeyboardButton(
                  text="⚠️ Barcha obunachilarni o'chirish",
                  callback_data="delete_all_users",
              )
          ],
      ]
  )


# ----------------------------------------------------
# HANDLERS (Buyruqlar va xabarlarga javob)
# ----------------------------------------------------


# Admin menyusi (/admin)
@dp.message(Command("admin"))
@dp.message(F.text == "/admin")
async def admin_start(message: Message, state: FSMContext):
  await state.clear()  # Har safar /admin bosilganda oldingi holat tozalanadi
  if message.from_user.id == ADMIN_ID:
    await message.answer(
        "👑 Siz adminsiz. Kerakli bo'limni tanlang:",
        reply_markup=get_admin_keyboard(),
    )
  else:
    await message.answer("Siz admin emassiz.")


# Barcha menyu tugmalari bosilganda FSM state avtomatik tozalanadi
@dp.message(F.text.in_({
    "📞 Ro'yxatdan o'tganlar raqamlari",
    "📊 Statistika",
    "📊 Excel yuklab olish",
    "📢 Reklama yuborish",
}))
async def clear_state_on_menu(message: Message, state: FSMContext):
  await state.clear()


# Obunachini o'chirish tugmasi
@dp.message(F.text == "❌ Obunachini o'chirish")
async def delete_menu(message: Message, state: FSMContext):
  await state.clear()
  if message.from_user.id == ADMIN_ID:
    await message.answer(
        "🗑 Obunachilarni botdan o'chirish bo'limi:\n\nO'chirish turini"
        " tanlang:",
        reply_markup=get_delete_options_inline(),
    )


# ID bo'yicha o'chirish tugmasi bosilganda (Inline)
@dp.callback_query(F.data == "delete_by_id")
async def cb_delete_by_id(callback: CallbackQuery, state: FSMContext):
  await callback.answer()
  await state.set_state(AdminStates.waiting_for_delete_id)
  await callback.message.answer(
      "O'chirmoqchi bo'lgan foydalanuvchining Telegram ID raqamini"
      " kiriting:\n\n(Bekor qilish uchun shunchaki menyudagi boshqa tugmani"
      " bosing)"
  )


# Barcha obunachilarni o'chirish (Inline)
@dp.callback_query(F.data == "delete_all_users")
async def cb_delete_all(callback: CallbackQuery, state: FSMContext):
  await callback.answer()
  await state.clear()
  delete_all_users()
  await callback.message.answer(
      "✅ Barcha obunachilar baza ma'lumotlaridan to'liq o'chirib tashlandi!"
  )


# FSM: ID raqami kiritilganda uni tekshirish va o'chirish
@dp.message(AdminStates.waiting_for_delete_id)
async def process_delete_user_id(message: Message, state: FSMContext):
  text = message.text.strip()

  # Agar foydalanuvchi menyudagi boshqa tugmani bosib yuborgan bo'lsa
  if text in [
      "📞 Ro'yxatdan o'tganlar raqamlari",
      "📊 Statistika",
      "📊 Excel yuklab olish",
      "📢 Reklama yuborish",
      "❌ Obunachini o'chirish",
  ]:
    await state.clear()
    await message.answer(
        "❌ ID kiritish bekor qilindi.", reply_markup=get_admin_keyboard()
    )
    return

  if not text.isdigit():
    await message.answer(
        "❌ Noto'g'ri ID kiritdingiz! Faqat raqamlardan iborat Telegram ID"
        " kiriting:"
    )
    return

  target_id = int(text)
  success = delete_user(target_id)
  await state.clear()

  if success:
    await message.answer(
        f"✅ ID: {target_id} foydalanuvchisi muvaffaqiyatli o'chirildi!",
        reply_markup=get_admin_keyboard(),
    )
  else:
    await message.answer(
        f"⚠️ ID: {target_id} bazadan topilmadi.",
        reply_markup=get_admin_keyboard(),
    )


# Excel yuklab olish
@dp.message(F.text == "📊 Excel yuklab olish")
async def export_excel(message: Message, state: FSMContext):
  await state.clear()
  if message.from_user.id != ADMIN_ID:
    return

  users = get_all_users()
  if not users:
    await message.answer("Bazada hech qanday obunachi topilmadi.")
    return

  output = io.StringIO()
  writer = csv.writer(output)
  writer.writerow(["Telegram ID", "Ism-familiya", "Telefon raqam", "Username"])
  for row in users:
    writer.writerow(row)

  csv_bytes = output.getvalue().encode("utf-8-sig")
  file = BufferedInputFile(csv_bytes, filename="obunachilar.csv")

  await message.answer_document(
      document=file,
      caption=f"📁 Barcha foydalanuvchilar ro'yxati ({len(users)} ta obunachi)",
  )


# Ro'yxatdan o'tganlar raqamlari
@dp.message(F.text == "📞 Ro'yxatdan o'tganlar raqamlari")
async def show_numbers(message: Message, state: FSMContext):
  await state.clear()
  if message.from_user.id != ADMIN_ID:
    return

  users = get_all_users()
  if not users:
    await message.answer("Bazada foydalanuvchilar yo'q.")
    return

  msg_text = "<b>Foydalanuvchilar ro'yxati:</b>\n\n"
  for idx, u in enumerate(users, start=1):
    u_id, name, phone, username = u
    user_str = f"@{username}" if username else "Mavjud emas"
    msg_text += (
        f"{idx}. {name or 'Noma'lum'}\n📱 Tel: {phone or 'Noma'lum'}\n👤 User:"
        f" {user_str}\n🆔 ID: <code>{u_id}</code>\n\n"
    )

    if len(msg_text) > 3500:
      await message.answer(msg_text, parse_mode="HTML")
      msg_text = ""

  if msg_text:
    await message.answer(msg_text, parse_mode="HTML")


# Statistika
@dp.message(F.text == "📊 Statistika")
async def show_stats(message: Message, state: FSMContext):
  await state.clear()
  if message.from_user.id == ADMIN_ID:
    users = get_all_users()
    await message.answer(f"📊 Jamiy obunachilar soni: <b>{len(users)}</b> ta")


# ----------------------------------------------------
# MAIN RUNNER
# ----------------------------------------------------
async def main():
  print("Bot muvaffaqiyatli ishga tushdi...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())

