import asyncio
import logging
import sqlite3
import csv
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardRemove,
    FSInputFile
)

# --- KONFIGURATSIYA ---
BOT_TOKEN = "8893922149:AAGZIV4N7y2bHEKGz3ucNK0dvHpF3R3XC8w"
CHANNEL_USERNAME = "@burgutali"    # Kanal username
ADMIN_ID = 8904071143              # Admin Telegram ID

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
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
    """, (user_id, full_name, username, phone_number))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, full_name, username, phone_number FROM users")
    rows = cursor.fetchall()
    conn.close()
    return rows

# --- STATES ---
class Registration(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

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
            [KeyboardButton(text="📢 Reklama yuborish")]
        ],
        resize_keyboard=True
    )

# --- USER REGISTRATION FLOW ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        await message.answer("👑 **Admin panelga xush kelibsiz!**\nQuyidagi tugmalardan birini tanlang:", reply_markup=get_admin_keyboard())
        return

    await message.answer(
        "👋 Assalomu alaykum, men Burgutali ustozning AI yordamchisiman. Keling, siz bilan yaqindan tanishib olamiz!\n\n"
        "Ism va familiyangizni yozing.\n"
        "(Masalan: Burgutali Eshquvvatov)"
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

    await message.answer(
        "📱 Telefon raqamingiz qabul qilindi!",
        reply_markup=ReplyKeyboardRemove()
    )

    await message.answer(
        "📅 5-6-7 sentyabrda bo'lib o'tadigan bepul Webinarimizda ishtirok etish uchun kanalimizga obuna bo'ling!",
        reply_markup=get_sub_keyboard()
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    is_sub = await check_subscription(call.from_user.id)
    if is_sub:
        await call.message.delete()
        await call.message.answer(
            "✅ Kanalga obuna bo'ldingiz!\n\n"
            "🎉 Tabriklaymiz, siz Webinar uchun muvaffaqiyatli ro'yxatdan o'tdingiz. Barcha muhim yangiliklar va havola kanalimizda berib boriladi!"
        )
    else:
        await call.answer("⚠️ Siz hali kanalga obuna bo'lmadingiz! Iltimos, avval kanalga obuna bo'ling.", show_alert=True)

# --- ADMIN COMMANDS & BUTTONS ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 **Admin panel!** Kerakli bo'limni tanlang:", reply_markup=get_admin_keyboard())
    else:
        await message.answer("⛔️ Siz admin emassiz.")

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

# --- TUZATILGAN BO'LIM (RO'YXATNI BO'LIB YUBORISH) ---
@dp.message(F.text == "📞 Ro'yxatdan o'tganlar raqamlari")
async def show_users_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    users = get_all_users()
    if not users:
        await message.answer("📁 Hozircha ro'yxatdan o'tgan foydalanuvchilar yo meyo'q.")
        return

    header = f"📋 **Ro'yxatdan o'tganlar ({len(users)} ta):**\n\n"
    current_text = header

    for idx, u in enumerate(users, 1):
        u_id, name, uname, phone = u
        safe_name = str(name).replace("*", "").replace("_", "").replace("`", "")
        safe_uname = str(uname).replace("*", "").replace("_", "").replace("`", "")
        
        user_info = f"{idx}. **{safe_name}**\n   📱 Tel: `{phone}`\n   👤 User: {safe_uname}\n   🆔 ID: `{u_id}`\n\n"
        
        if len(current_text) + len(user_info) > 3000:
            await message.answer(current_text, parse_mode="Markdown")
            current_text = user_info
        else:
            current_text += user_info

    if current_text:
        await message.answer(current_text, parse_mode="Markdown")

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = get_all_users()
    await message.answer(f"📊 **Bot statistikasi:**\n\n👥 Baza bo'yicha ro'yxatdan o'tganlar: **{len(users)} ta**")

@dp.message(F.text == "📢 Reklama yuborish")
async def start_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "📝 Yubormoqchi bo'lgan reklamangizni (Matn, Rasm, Video yoki Post) botga yuboring:\n\n"
        "❌ Bekor qilish uchun /cancel buyrug'ini bosing.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(AdminStates.waiting_for_broadcast)

@dp.message(Command("cancel"), AdminStates.waiting_for_broadcast)
async def cancel_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Reklama yuborish bekor qilindi.", reply_markup=get_admin_keyboard())

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

# --- ANY OTHER MESSAGES ---
@dp.message()
async def handle_other_messages(message: types.Message):
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        await message.answer("👑 Siz adminsiz. Buyruqlardan foydalanish uchun /admin deb yozing.", reply_markup=get_admin_keyboard())
        return

    await message.answer("Qo'shimcha savollaringiz bo'lsa @Burgutali_admin ga yozing.")

async def main():
    db_init()
    print("Bot muvaffaqiyatli ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
