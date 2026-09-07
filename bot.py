import asyncio
import csv
import logging
import os
import re
import sqlite3

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

BOT_VERSION = "v2_with_updated_keyboards"
print(f"[STARTUP] Loading bot version: {BOT_VERSION}", flush=True)
# --- KONFIGURATSIYA ---
BOT_TOKEN = "8893922149:AAGZIV4N7y2bHEKGz3ucNK0dvHpF3R3XC8w"
CHANNEL_USERNAME = "@burgutali"    # Kanal username
ADMIN_ID = 8904071143              # Admin Telegram ID

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher(storage=MemoryStorage())

# --- DATABASE ---
def db_init():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            phone_number TEXT
        )
    """)
    conn.commit()
    conn.close()

def clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'[*_`\[\]()~>#+\-=|{}.!]', '', str(text))

def add_user(user_id: int, full_name: str, username: str, phone_number: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, full_name, username, phone_number)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            full_name=excluded.full_name,
            username=excluded.username,
            phone_number=excluded.phone_number
    """, (user_id, clean_text(full_name), clean_text(username), clean_text(phone_number)))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, full_name, username, phone_number FROM users")
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_user_by_id(user_id: int) -> bool:
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def delete_all_users() -> int:
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users")
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected

# --- STATES ---
class Registration(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_id = State()

# --- HELPER FUNCTIONS ---
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logging.error(f"Obunani tekshirishda xatolik: {e}")
        return False

def get_sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")]
    ])

def get_payment_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Chekni adminga yuborish", url="https://t.me/burgutali_admin")]
    ])

def get_phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Ro'yxatdan o'tganlar raqamlari")],
            [KeyboardButton(text="📊 Excel yuklab olish"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="📢 Reklama yuborish"), KeyboardButton(text="❌ Obunachini o'chirish")]
        ],
        resize_keyboard=True
    )

def get_delete_options_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🆔 ID bo'yicha o'chirish", callback_data="delete_by_id")],
            [InlineKeyboardButton(text="⚠️ Barcha obunachilarni o'chirish", callback_data="delete_all_users")]
        ]
    )

async def send_payment_info(message_or_call_msg, user_id: int):
    is_sub = await check_subscription(user_id)
    
    # 5-band: Kanalga a'zo bo'lmagan bo'lsagina kanalga a'zolikni so'raymiz
    if not is_sub:
        await message_or_call_msg.answer(
            "⚠️ Davom etish uchun avval kanalimizga obuna bo'ling!",
            reply_markup=get_sub_keyboard()
        )
        return

    # 6-band: Ro'yxatdan o'tib bo'lgach to'lov xabari va tugmasi ko'rsatiladi
    payment_text = (
        "Ana endi to'lov qismiga o'tamiz.\n\n"
        "To’lov uchun karta: `9860170109974155`\n"
        "**Marufboyev Ramazon**\n\n"
        "To'lovni amalga oshirganingizdan so’ng chekni screenshotini adminga yuboring! "
        "To’lov admin tomonidan tekshirilgach tasdiqlanadi"
    )
    await message_or_call_msg.answer(payment_text, reply_markup=get_payment_keyboard())

# --- USER REGISTRATION FLOW ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        await message.answer("👑 **Admin panelga xush kelibsiz!**\nQuyidagi tugmalardan birini tanlang:", reply_markup=get_admin_keyboard())
        return

    await state.clear()
    await message.answer(
        "👋 Assalomu alaykum! Keling, siz bilan yaqindan tanishib olamiz!\n\n"
        "Ism va familiyangizni kiriting.\n"
        "(Masalan: Burgutali Eshquvvatov)",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Registration.waiting_for_name)

@dp.message(Registration.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    user_name = message.text.strip()
    await state.update_data(full_name=user_name)

    await message.answer(
        "Tanishganimdan xursandman😊\n\n"
        "Endi siz bilan doimiy aloqada bo'lib turishimiz uchun telefon raqamingizni yuboring!",
        reply_markup=get_phone_keyboard()
    )
    await state.set_state(Registration.waiting_for_phone)

@dp.message(Registration.waiting_for_phone, F.contact)
async def process_phone(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    full_name = user_data.get("full_name", message.from_user.full_name)
    phone = message.contact.phone_number
    user = message.from_user

    add_user(
        user_id=user.id,
        full_name=full_name,
        username=f"@{user.username}" if user.username else "Mavjud emas",
        phone_number=phone
    )

    await state.clear()
    await message.answer("📱 Telefon raqamingiz qabul qilindi!", reply_markup=ReplyKeyboardRemove())
    await send_payment_info(message, user.id)

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    is_sub = await check_subscription(call.from_user.id)
    if is_sub:
        await call.message.delete()
        await send_payment_info(call.message, call.from_user.id)
    else:
        await call.answer("⚠️ Siz hali kanalga obuna bo'lmadingiz! Iltimos, avval kanalga obuna bo'ling.", show_alert=True)

# --- ADMIN COMMANDS & USER MANAGEMENT ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 **Admin panel!** Kerakli bo'limni tanlang:", reply_markup=get_admin_keyboard())
    else:
        await message.answer("⛔️ Siz admin emassiz.")

# 1-band va 2-band: Obunachilarni chiqarib tashlash (ID va Barchasi)
@dp.message(F.text == "❌ Obunachini o'chirish")
async def admin_delete_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🗑 **Obunachilarni botdan o'chirish bo'limi:**\n\nO'chirish turini tanlang:", reply_markup=get_delete_options_keyboard())

@dp.callback_query(F.data == "delete_by_id")
async def delete_by_id_callback(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.answer()
    await call.message.answer("✏️ O'chirmoqchi bo'lgan obunachining **Telegram ID** sini kiriting:\n\n❌ Bekor qilish uchun /cancel bosing.")
    await state.set_state(AdminStates.waiting_for_user_id)

@dp.message(AdminStates.waiting_for_user_id)
async def process_delete_user_id(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    user_input = message.text.strip()
    if not user_input.isdigit():
        await message.answer("❌ Noto'g'ri ID kiritdingiz! Faqat raqamlardan iborat Telegram ID kiriting:")
        return

    target_id = int(user_input)
    success = delete_user_by_id(target_id)
    await state.clear()

    if success:
        await message.answer(f"✅ Telegram ID: `{target_id}` bo'lgan obunachi bazadan muvaffaqiyatli o'chirildi!", reply_markup=get_admin_keyboard())
    else:
        await message.answer(f"⚠️ Telegram ID: `{target_id}` bo'lgan obunachi bazadan topilmadi.", reply_markup=get_admin_keyboard())

@dp.callback_query(F.data == "delete_all_users")
async def delete_all_callback(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.answer()
    deleted_count = delete_all_users()
    await call.message.answer(f"💥 **Barcha obunachilar bazadan o'chirildi!**\n\nJami o'chirilganlar: **{deleted_count} ta**", reply_markup=get_admin_keyboard())

# Oldingi Excel yuklab olish
@dp.message(F.text == "📊 Excel yuklab olish")
async def export_excel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    users = get_all_users()
    if not users:
        await message.answer("📁 Hozircha bazada foydalanuvchilar yo'q.")
        return

    file_path = "obunachilar.csv"
    with open(file_path, mode='w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["Telegram ID", "Ism-Familiya", "Username", "Telefon Raqam"])
        writer.writerows(users)

    excel_file = FSInputFile(file_path)
    await message.answer_document(excel_file, caption=f"📁 **Barcha foydalanuvchilar ro'yxati** ({len(users)} ta obunachi)")
    
    if os.path.exists(file_path):
        os.remove(file_path)

# Oldingi a'zolar raqamlari hamda ID ro'yxati
@dp.message(F.text == "📞 Ro'yxatdan o'tganlar raqamlari")
async def show_users_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    users = get_all_users()
    if not users:
        await message.answer("📁 Hozircha ro'yxatdan o'tgan foydalanuvchilar yo'q.")
        return

    header = f"📋 **Ro'yxatdan o'tganlar ({len(users)} ta):**\n\n"
    current_text = header

    for idx, u in enumerate(users, 1):
        u_id, name, uname, phone = u
        safe_name = clean_text(name)
        safe_uname = clean_text(uname)
        
        user_info = f"{idx}. **{safe_name}**\n   📱 Tel: `{phone}`\n   👤 User: {safe_uname}\n   🆔 ID: `{u_id}`\n\n"
        
        if len(current_text) + len(user_info) > 3000:
            await message.answer(current_text)
            current_text = user_info
        else:
            current_text += user_info

    if current_text:
        await message.answer(current_text)

# Oldingi a'zolarni hisoblash (Statistika)
@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = get_all_users()
    await message.answer(f"📊 **Bot statistikasi:**\n\n👥 Baza bo'yicha ro'yxatdan o'tganlar: **{len(users)} ta**")

# REKLAMA YUBORISH
@dp.message(F.text == "📢 Reklama yuborish")
async def start_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "📝 Yubormoqchi bo'lgan reklamangizni botga yuboring:\n\n"
        "❌ Bekor qilish uchun /cancel buyrug'ini bosing.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(AdminStates.waiting_for_broadcast)

@dp.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Amaliyot bekor qilindi.", reply_markup=get_admin_keyboard())

@dp.message(AdminStates.waiting_for_broadcast)
async def send_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    users = get_all_users()
    await state.clear()

    if not users:
        await message.answer("❌ Bazada foydalanuvchilar topilmadi.", reply_markup=get_admin_keyboard())
        return

    await message.answer("🚀 Reklama yuborish boshlandi...")

    count_success = 0
    count_blocked = 0

    for u in users:
        user_id = u[0]
        try:
            await message.copy_to(chat_id=user_id)
            count_success += 1
            await asyncio.sleep(0.05)
        except Exception:
            count_blocked += 1

    await message.answer(
        f"✅ **Reklama yuborish yakunlandi!**\n\n"
        f"🟢 Yetib bordi: **{count_success}** ta\n"
        f"🔴 Yetib bormadi (Botni bloklagan): **{count_blocked}** ta",
        reply_markup=get_admin_keyboard()
    )

# --- O'ZGARTIRILDI: START BOSILISHDAN OLDIN CHIQADIGAN TAVSIF ---
async def set_bot_description(bot_instance: Bot):
    desc = (
        "Bu bot nimalar qila oladi?\n"
        "Bu bot orqali siz Burgutali Eshquvvatovning “MS TURBO 9” Noyabr oyi uchun intensiv kursiga qo’shilish uchun to’lov amalga oshirishingiz mumkin.\n"
        "Foydalanish uchun “Start” tugmasini bosing!\n"
        "Aloqa uchun admin +998504054048"
    )
    try:
        await bot_instance.set_my_description(desc)
        await bot_instance.set_my_short_description(desc)
    except Exception as e:
        logging.error(f"Tavsifni o'rnatishda xatolik: {e}")

@dp.message()
async def handle_other_messages(message: types.Message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        await message.answer("👑 Siz adminsiz. Buyruqlardan foydalanish uchun /admin deb yozing.", reply_markup=get_admin_keyboard())
        return
    await message.answer("Qo'shimcha savollaringiz bo'lsa @burgutali_admin ga yozing.")

async def main():
    db_init()
    await set_bot_description(bot)
    print("Bot muvaffaqiyatli ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
