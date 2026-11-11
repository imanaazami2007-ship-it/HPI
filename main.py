import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from .config import BOT_TOKEN, ADMIN_ID, CARD_NUMBER, CARD_OWNER
from . import db

class Purchase(StatesGroup):
    waiting_receipt = State()

dp = Dispatcher()
bot = None

def is_admin(user_id: int) -> bool:
    return ADMIN_ID != 0 and user_id == ADMIN_ID

def plans_keyboard(plans):
    rows = []
    for months, price in plans:
        label = f"{months} ماهه — {price:,} تومان"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"plan:{months}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "به ZEUS SELF خوش آمدید.\n"
        "برای مشاهده اشتراک‌ها: /plans\n"
        "برای دیدن وضعیت اشتراک: /status\n\n"
        "این نسخه اولیه فقط مدیریت اشتراک و پرداخت دستی را انجام می‌دهد."
    )

@dp.message(Command("plans"))
async def show_plans(message: Message):
    plans = await db.get_plans()
    await message.answer("مدت اشتراک موردنظر را انتخاب کنید:", reply_markup=plans_keyboard(plans))

@dp.callback_query(F.data.startswith("plan:"))
async def choose_plan(callback: CallbackQuery, state: FSMContext):
    months = int(callback.data.split(":")[1])
    plans = dict(await db.get_plans())
    price = plans.get(months)
    if price is None or price <= 0:
        await callback.answer("این پلن هنوز قیمت‌گذاری نشده است.", show_alert=True)
        return
    await state.update_data(months=months, amount=price)
    await state.set_state(Purchase.waiting_receipt)
    await callback.message.answer(
        f"اشتراک {months} ماهه انتخاب شد.\n"
        f"مبلغ: {price:,} تومان\n\n"
        f"شماره کارت: {CARD_NUMBER}\n"
        f"به نام: {CARD_OWNER}\n\n"
        "پس از واریز، تصویر رسید را همین‌جا ارسال کنید."
    )
    await callback.answer()

@dp.message(Purchase.waiting_receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    payment_id = await db.create_payment(
        message.from_user.id, data["months"], data["amount"], message.photo[-1].file_id
    )
    await state.clear()
    await message.answer("رسید دریافت شد و پس از بررسی مدیر، نتیجه اعلام می‌شود.")
    if ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="تأیید", callback_data=f"payok:{payment_id}"),
            InlineKeyboardButton(text="رد", callback_data=f"payno:{payment_id}")
        ]])
        await bot.send_photo(
            ADMIN_ID, message.photo[-1].file_id,
            caption=(
                f"رسید پرداخت #{payment_id}\n"
                f"کاربر: {message.from_user.id}\n"
                f"پلن: {data['months']} ماه\n"
                f"مبلغ: {data['amount']:,} تومان"
            ),
            reply_markup=kb
        )

@dp.message(Purchase.waiting_receipt)
async def receipt_hint(message: Message):
    await message.answer("لطفاً تصویر رسید پرداخت را به‌صورت عکس ارسال کنید.")

@dp.callback_query(F.data.startswith("payok:"))
@dp.callback_query(F.data.startswith("payno:"))
async def payment_decision(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("اجازه دسترسی ندارید.", show_alert=True)
        return
    approve = callback.data.startswith("payok:")
    payment_id = int(callback.data.split(":")[1])
    result = await db.decide_payment(payment_id, approve)
    if result is None:
        await callback.answer("این پرداخت قبلاً بررسی شده یا وجود ندارد.", show_alert=True)
        return
    user_id, expiry = result
    if approve:
        await bot.send_message(user_id, f"پرداخت تأیید شد. اشتراک شما تا {expiry} فعال است.")
        await callback.message.edit_caption((callback.message.caption or "") + "\n\nوضعیت: تأیید شد")
    else:
        await bot.send_message(user_id, "رسید پرداخت تأیید نشد. برای راهنمایی با مدیر تماس بگیرید.")
        await callback.message.edit_caption((callback.message.caption or "") + "\n\nوضعیت: رد شد")
    await callback.answer("انجام شد.")

@dp.message(Command("status"))
async def status(message: Message):
    expiry = await db.get_user_expiry(message.from_user.id)
    if not expiry:
        await message.answer("اشتراک فعالی برای شما ثبت نشده است.")
        return
    try:
        dt = datetime.fromisoformat(expiry)
        await message.answer(f"تاریخ پایان اشتراک (UTC): {dt.strftime('%Y-%m-%d %H:%M')}")
    except ValueError:
        await message.answer("اطلاعات اشتراک ثبت شده است.")

@dp.message(Command("setprice"))
async def setprice(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.answer("فرمت: /setprice ماه مبلغ_تومان\nمثال: /setprice 1 150000")
        return
    months, price = int(parts[1]), int(parts[2])
    if months < 1 or months > 12 or price < 1:
        await message.answer("ماه باید بین ۱ تا ۱۲ و مبلغ بیشتر از صفر باشد.")
        return
    await db.set_price(months, price)
    await message.answer(f"قیمت اشتراک {months} ماهه روی {price:,} تومان تنظیم شد.")

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("اجازه دسترسی ندارید.")
        return
    count = await db.pending_count()
    await message.answer(
        f"پنل مدیریت ZEUS SELF\nپرداخت‌های در انتظار بررسی: {count}\n\n"
        "تنظیم قیمت: /setprice ماه مبلغ_تومان"
    )

async def main():
    global bot
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Set it in Railway Variables.")
    if not ADMIN_ID:
        raise RuntimeError("ADMIN_ID is missing. Set your Telegram numeric user ID.")
    await db.init_db()
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
