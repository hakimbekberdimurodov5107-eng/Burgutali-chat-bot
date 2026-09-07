import asyncio
import csv
import logging
import os
import re
import sqlite3
import sys
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session import aiohttp_key
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

# Load environment variables from .env file (if present locally)
load_dotenv()

# --- CONFIGURATION (load from environment variables) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@burgutali")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8904071143"))

# Validate required configuration
if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN environment variable is not set!", file=sys.stderr)
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

logger.info(f"[STARTUP] Bot version: v2_with_env_vars")
logger.info(f"[STARTUP] Channel: {CHANNEL_USERNAME}")
logger.info(f"[STARTUP] Admin ID: {ADMIN_ID}")

# Initialize bot and dispatcher with conflict handling
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="Markdown")
)
dp = Dispatcher(storage=MemoryStorage())

# --- DATABASE ---
DB_PATH = "bot_database.db"

def db_init():
    """Initialize database with proper connection handling"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for stability
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
    logger.info(f"[DB] Database initialized at {DB_PATH}")

def clean_text(text: str) -> str:
    """Sanitize text for Markdown rendering"""
    if not text:
        return ""
    return re.sub(r'[*_`\[\]()~>#+\-=|{}.!]', '', str(text))

def add_user(user_id: int, full_name: str, username: str, phone_number: str):
    """Add or update user in database"""
    try:
        conn = sqlite3.connect(DB_PATH)
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
        logger.debug(f"[DB] User {user_id} added/updated")
    except sqlite3.OperationalError as e:
        logger.error(f"[DB] Error adding user: {e}")

def get_all_users():
    """Retrieve all users from database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, full_name, username, phone_number FROM users")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except sqlite3.OperationalError as e:
        logger.error(f"[DB] Error retrieving users: {e}")
        return []

def delete_user_by_id(user_id: int) -> bool:
    """Delete a user by ID"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0
    except sqlite3.OperationalError as e:
        logger.error(f"[DB] Error deleting user: {e}")
        return False

def delete_all_users() -> int:
    """Delete all users from database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users")
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected
    except sqlite3.OperationalError as e:
        logger.error(f"[DB] Error deleting all users: {e}")
        return 0

# --- STATES ---
class Registration(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_id = State()

# --- HELPER FUNCTIONS ---
async def check_subscription(user_id: int) -> bool:
    """Check if user is subscribed to the channel"""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logger.warning(f"[TELEGRAM] Subscription check failed for user {user_id}: {e}")
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
    """Send payment instructions to user"""
    is_sub = await check_subscription(user_id)
    
    if not is_sub:
        await message_or_call_msg.answer(
            "⚠️ Davom etish uchun avval kanalimizga obuna bo'ling!",
            reply_markup=get_sub_keyboard()
        )
        return

    payment_text = (
        "Ana endi to'lov qismiga o'tamiz.\n\n"
        "To'lov uchun karta: `9860170109974155`\n"
        "**Marufboyev Ramazon**\n\n"
        "To'lovni amalga oshirganingizdan so'ng chekni screenshotini adminga yuboring! "
        "To'lov admin tomonidan tekshirilgach tasdiqlanadi"
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
        except Exception as e:
            logger.debug(f"[BROADCAST] Failed to send to {user_id}: {e}")
            count_blocked += 1

    await message.answer(
        f"✅ **Reklama yuborish yakunlandi!**\n\n"
        f"🟢 Yetib bordi: **{count_success}** ta\n"
        f"🔴 Yetib bormadi (Botni bloklagan): **{count_blocked}** ta",
        reply_markup=get_admin_keyboard()
    )

async def set_bot_description(bot_instance: Bot):
    """Set bot description in Telegram"""
    desc = (
        "Bu bot nimalar qila oladi?\n"
        "Bu bot orqali siz Burgutali Eshquvvatovning "MS TURBO 9" Noyabr oyi uchun intensiv kursiga qo'shilish uchun to'lov amalga oshirishingiz mumkin.\n"
        "Foydalanish uchun "Start" tugmasini bosing!\n"
        "Aloqa uchun admin +998504054048"
    )
    try:
        await bot_instance.set_my_description(desc)
        await bot_instance.set_my_short_description(desc)
        logger.info("[TELEGRAM] Bot description set successfully")
    except Exception as e:
        logger.error(f"[TELEGRAM] Failed to set description: {e}")

@dp.message()
async def handle_other_messages(message: types.Message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        await message.answer("👑 Siz adminsiz. Buyruqlardan foydalanish uchun /admin deb yozing.", reply_markup=get_admin_keyboard())
        return
    await message.answer("Qo'shimcha savollaringiz bo'lsa @burgutali_admin ga yozing.")

async def main():
    """Main bot function with proper startup/shutdown handling"""
    try:
        db_init()
        await set_bot_description(bot)
        logger.info("[STARTUP] Bot started successfully")
        logger.info("[STARTUP] Listening for updates...")
        
        # Delete any pending webhooks and start polling
        await bot.delete_webhook(drop_pending_updates=True)
        
        # Start polling with timeout handling
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except asyncio.CancelledError:
        logger.info("[SHUTDOWN] Bot shutdown signal received")
    except Exception as e:
        logger.error(f"[ERROR] Unexpected error in main: {e}", exc_info=True)
        raise
    finally:
        await bot.session.close()
        logger.info("[SHUTDOWN] Bot session closed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[SHUTDOWN] Keyboard interrupt received")
    except Exception as e:
        logger.error(f"[ERROR] Fatal error: {e}", exc_info=True)
        sys.exit(1)

