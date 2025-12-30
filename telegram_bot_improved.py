#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت Telegram للإشراف التلقائي على المجموعات - النسخة المحسّنة
يوفر تصفية الكلمات المسيئة والروابط وأرقام الهواتف
مع نظام إحصائيات متقدم ونظام عقوبات تدريجي
"""

import re
import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from telegram import Update, ChatMember
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

# إعداد نظام السجلات
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# استخدام التوكن من متغير البيئة (أكثر أماناً)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TOKEN:
    raise ValueError("⚠️ خطأ: لم يتم تعيين متغير البيئة TELEGRAM_BOT_TOKEN")

# ==================== قائمة الكلمات المحظورة الموسعة ====================

# 1️⃣ كلمات الخدمات الطلابية
ACADEMIC_SERVICES = [
    "أحل الواجبات",
    "أحل الاختبارات",
    "أحل الأسئلة",
    "حل الواجب",
    "حل الاختبار",
    "احل الأسئلة",
    "أكتب البحث",
    "كتابة البحث",
    "حل المسائل",
    "حل الواجبات",
    "حل الاختبارات",
]

# 2️⃣ كلمات الترويج الشخصي
PERSONAL_PROMOTION = [
    "تعال خاص",
    "راسلني خاص",
    "تواصل معي خاص",
    "اتصل بي",
    "رسالة خاصة",
    "في الخاص",
    "بالخاص",
    "تعال الخاص",
    "روابط في البايو",
    "شوف البايو",
    "البايو عندي",
    "تابعني",
    "اتبعني",
    "اضغط على البايو",
]

# 3️⃣ كلمات الأوراق والشهادات المزيفة
FAKE_DOCUMENTS = [
    "سكليف",
    "شهادة مضمونة",
    "ورقة مضمونة",
    "إجازة مضمونة",
    "إجازة طبية مضمونة",
    "تقرير طبي مضمون",
    "شهادة غياب مضمونة",
    "شهادة غياب",
    "تقرير طبي",
    "إجازة طبية",
]

# 4️⃣ كلمات الخدمات المريبة
SUSPICIOUS_SERVICES = [
    "أجازات طبية",
    "تقارير طبية",
    "شهادات غياب",
    "حل الواجبات مقابل",
    "كتابة الأبحاث",
]

# 5️⃣ كلمات الإعلانات العامة
ADVERTISEMENTS = [
    "للبيع",
    "للإيجار",
    "عرض خاص",
    "خصم كبير",
    "توظيف",
    "وظائف",
    "فرصة ذهبية",
    "استثمار مضمون",
    "عرض محدود",
    "سعر خاص",
    "تخفيض",
]

# 6️⃣ الكلمات المسيئة والبذيئة
BAD_WORDS = [
    "كلب",
    "حمار",
    "قذر",
    "غبي",
    "أحمق",
    "ملعون",
    "لعين",
    "وسخ",
    "قاذورة",
    "سافل",
    "خسيس",
    "دنيء",
    "نذل",
    "عاهر",
    "زنا",
    "شرموطة",
    "كس",
    "نيك",
    "طيز",
    "خول",
]

# دمج جميع القوائم
ALL_BANNED_WORDS = (
    ACADEMIC_SERVICES + 
    PERSONAL_PROMOTION + 
    FAKE_DOCUMENTS + 
    SUSPICIOUS_SERVICES + 
    ADVERTISEMENTS + 
    BAD_WORDS
)

# نمط التعرف على الروابط
URL_PATTERN = r"https?://|www\.|ftp://|t\.me/|@\w+|#\w+"

# نمط التعرف على أرقام الهواتف (أرقام محلية ودولية)
PHONE_PATTERN = r"(\+\d{1,3}[-\.\s]?)?\(?\d{3,4}\)?[-\.\s]?\d{3,4}[-\.\s]?\d{4,}|00\d{1,3}\d{7,}"

# قاموس لتخزين إحصائيات المستخدمين
STATS: Dict[str, Dict[str, Any]] = {}
STATS_FILE = "bot_stats.json"

# ثابت لمدة عرض رسائل التحذير (بالثواني)
WARNING_MESSAGE_DURATION = 30

# عدد التحذيرات قبل الحظر
WARNINGS_BEFORE_BAN = 3

# ==================== دوال تحميل وحفظ الإحصائيات ====================

def load_stats() -> None:
    """تحميل الإحصائيات من الملف"""
    global STATS
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                STATS = json.load(f)
                logger.info(f"✅ تم تحميل الإحصائيات من {STATS_FILE}")
        else:
            STATS = {}
            logger.info("📝 ملف الإحصائيات جديد")
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"❌ خطأ في تحميل الإحصائيات: {e}")
        STATS = {}


def save_stats() -> None:
    """حفظ الإحصائيات في الملف"""
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(STATS, f, ensure_ascii=False, indent=2)
            logger.debug("💾 تم حفظ الإحصائيات")
    except IOError as e:
        logger.error(f"❌ خطأ في حفظ الإحصائيات: {e}")


def update_stats(
    chat_id: int, 
    user_id: int, 
    username: str, 
    action: str,
    reason: str = ""
) -> None:
    """تحديث الإحصائيات
    
    Args:
        chat_id: معرف المجموعة
        user_id: معرف المستخدم
        username: اسم المستخدم
        action: نوع الإجراء (warning, ban, delete)
        reason: سبب الإجراء
    """
    chat_key = str(chat_id)
    user_key = str(user_id)

    if chat_key not in STATS:
        STATS[chat_key] = {}

    if user_key not in STATS[chat_key]:
        STATS[chat_key][user_key] = {
            "warnings": 0,
            "bans": 0,
            "deleted_messages": 0,
            "username": username,
            "first_seen": datetime.now().isoformat(),
            "last_violation": None,
            "violations": []
        }
    else:
        # تحديث اسم المستخدم
        STATS[chat_key][user_key]["username"] = username

    if action == "warning":
        STATS[chat_key][user_key]["warnings"] += 1
    elif action == "ban":
        STATS[chat_key][user_key]["bans"] += 1
    elif action == "delete":
        STATS[chat_key][user_key]["deleted_messages"] += 1

    # تسجيل الانتهاك
    STATS[chat_key][user_key]["last_violation"] = datetime.now().isoformat()
    STATS[chat_key][user_key]["violations"].append({
        "action": action,
        "reason": reason,
        "timestamp": datetime.now().isoformat()
    })

    save_stats()


def get_user_warnings(chat_id: int, user_id: int) -> int:
    """الحصول على عدد تحذيرات المستخدم
    
    Args:
        chat_id: معرف المجموعة
        user_id: معرف المستخدم
        
    Returns:
        عدد التحذيرات
    """
    chat_key = str(chat_id)
    user_key = str(user_id)
    
    if chat_key in STATS and user_key in STATS[chat_key]:
        return STATS[chat_key][user_key].get("warnings", 0)
    return 0


# ==================== دوال التحقق من المحتوى ====================

def contains_bad_words(text: str) -> Tuple[bool, Optional[str]]:
    """التحقق من وجود كلمات مسيئة في النص
    
    Args:
        text: النص المراد التحقق منه
        
    Returns:
        tuple: (وجود كلمة مسيئة، الكلمة المكتشفة)
    """
    text_lower = text.lower()

    for word in ALL_BANNED_WORDS:
        # البحث عن الكلمة مع تجاهل المسافات الزائدة
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, text_lower):
            return True, word

        # البحث عن الكلمة مع نقاط أو شرطات بينها
        pattern_with_separators = r"\b" + "[-._]*".join(re.escape(c) for c in word) + r"\b"
        if re.search(pattern_with_separators, text_lower):
            return True, word
        
        # البحث عن الكلمة مع مسافات متعددة
        word_with_spaces = "\\s+".join(re.escape(c) for c in word.split())
        pattern_with_spaces = r"\b" + word_with_spaces + r"\b"
        if re.search(pattern_with_spaces, text_lower):
            return True, word

    return False, None


def contains_url(text: str) -> bool:
    """التحقق من وجود روابط في النص
    
    Args:
        text: النص المراد التحقق منه
        
    Returns:
        True إذا كان يحتوي على روابط، False وإلا
    """
    return bool(re.search(URL_PATTERN, text))


def contains_phone(text: str) -> bool:
    """التحقق من وجود أرقام هاتف في النص
    
    Args:
        text: النص المراد التحقق منه
        
    Returns:
        True إذا كان يحتوي على أرقام هاتف، False وإلا
    """
    return bool(re.search(PHONE_PATTERN, text))


# ==================== دوال إرسال الرسائل ====================

async def send_warning_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message: str,
    duration: int = WARNING_MESSAGE_DURATION
) -> None:
    """إرسال رسالة تحذير وحذفها بعد وقت معين
    
    Args:
        context: سياق التطبيق
        chat_id: معرف المجموعة
        message: نص الرسالة
        duration: مدة عرض الرسالة بالثواني
    """
    try:
        warning_msg = await context.bot.send_message(
            chat_id,
            message,
            parse_mode="HTML",
        )
        # جدولة حذف الرسالة
        context.job_queue.run_once(
            delete_message,
            duration,
            data={"chat_id": chat_id, "message_id": warning_msg.message_id},
            name=f"delete_{warning_msg.message_id}"
        )
    except TelegramError as e:
        logger.error(f"❌ خطأ في إرسال رسالة التحذير: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في إرسال الرسالة: {e}")


async def delete_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """حذف رسالة التحذير بعد وقت معين
    
    Args:
        context: سياق التطبيق
    """
    try:
        await context.bot.delete_message(
            chat_id=context.job.data["chat_id"],
            message_id=context.job.data["message_id"]
        )
        logger.debug("🗑️ تم حذف رسالة التحذير")
    except TelegramError as e:
        logger.debug(f"⚠️ لم يتمكن من حذف الرسالة: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ في حذف الرسالة: {e}")


# ==================== الإشراف التلقائي ====================

async def auto_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الدالة الرئيسية للإشراف التلقائي
    
    Args:
        update: تحديث من Telegram
        context: سياق التطبيق
    """
    if not update.message or not update.message.text:
        return

    text = update.message.text
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    username = (
        update.message.from_user.username or 
        update.message.from_user.first_name or 
        "مستخدم"
    )

    try:
        # التحقق من وجود روابط
        if contains_url(text):
            try:
                await update.message.delete()
                update_stats(chat_id, user_id, username, "delete", "روابط")
            except TelegramError as e:
                logger.warning(f"⚠️ لم يتمكن من حذف الرسالة: {e}")

            try:
                await context.bot.ban_chat_member(chat_id, user_id)
                update_stats(chat_id, user_id, username, "ban", "روابط")
            except TelegramError as e:
                logger.warning(f"⚠️ لم يتمكن من حظر المستخدم {user_id}: {e}")

            warning_msg = (
                f"⛔ تم حظر المستخدم <b>{username}</b> لمحاولة نشر روابط\n"
                f"<i>الروابط غير مسموحة في هذه المجموعة</i>"
            )
            await send_warning_message(context, chat_id, warning_msg)
            logger.info(f"🔗 تم حظر {username} ({user_id}) لنشر روابط")
            return

        # التحقق من وجود أرقام هاتف
        if contains_phone(text):
            try:
                await update.message.delete()
                update_stats(chat_id, user_id, username, "delete", "أرقام هاتف")
            except TelegramError as e:
                logger.warning(f"⚠️ لم يتمكن من حذف الرسالة: {e}")

            try:
                await context.bot.ban_chat_member(chat_id, user_id)
                update_stats(chat_id, user_id, username, "ban", "أرقام هاتف")
            except TelegramError as e:
                logger.warning(f"⚠️ لم يتمكن من حظر المستخدم {user_id}: {e}")

            warning_msg = (
                f"⛔ تم حظر المستخدم <b>{username}</b> لمحاولة نشر أرقام هاتف\n"
                f"<i>مشاركة أرقام الهاتف غير مسموحة</i>"
            )
            await send_warning_message(context, chat_id, warning_msg)
            logger.info(f"📱 تم حظر {username} ({user_id}) لنشر أرقام هاتف")
            return

        # التحقق من وجود كلمات مسيئة
        has_bad_word, detected_word = contains_bad_words(text)
        if has_bad_word:
            try:
                await update.message.delete()
                update_stats(chat_id, user_id, username, "delete", f"كلمة مسيئة: {detected_word}")
            except TelegramError as e:
                logger.warning(f"⚠️ لم يتمكن من حذف الرسالة: {e}")

            # نظام العقوبات التدريجي
            current_warnings = get_user_warnings(chat_id, user_id)
            
            if current_warnings >= WARNINGS_BEFORE_BAN - 1:
                # حظر المستخدم بعد عدد معين من التحذيرات
                try:
                    await context.bot.ban_chat_member(chat_id, user_id)
                    update_stats(chat_id, user_id, username, "ban", f"كلمات مسيئة متكررة")
                except TelegramError as e:
                    logger.warning(f"⚠️ لم يتمكن من حظر المستخدم {user_id}: {e}")

                warning_msg = (
                    f"⛔ تم حظر المستخدم <b>{username}</b> بسبب استخدام كلمات مسيئة متكررة\n"
                    f"<i>يرجى احترام قوانين المجموعة</i>"
                )
                logger.info(f"💬 تم حظر {username} ({user_id}) بسبب كلمات مسيئة متكررة")
            else:
                # تحذير المستخدم
                update_stats(chat_id, user_id, username, "warning", f"كلمة مسيئة: {detected_word}")
                remaining_warnings = WARNINGS_BEFORE_BAN - current_warnings - 1
                
                warning_msg = (
                    f"⚠️ تم حذف رسالة من <b>{username}</b> لاحتوائها على كلمات مسيئة\n"
                    f"<i>تحذير {current_warnings + 1}/{WARNINGS_BEFORE_BAN}</i>\n"
                    f"<i>لديك {remaining_warnings} تحذيرات متبقية قبل الحظر</i>"
                )
                logger.info(f"💬 تم تحذير {username} ({user_id}) - التحذير {current_warnings + 1}")

            await send_warning_message(context, chat_id, warning_msg)
            return

    except TelegramError as e:
        logger.error(f"❌ خطأ في الإشراف التلقائي (Telegram): {e}")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في الإشراف التلقائي: {e}")


# ==================== معالجات الأوامر ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج أمر /start
    
    Args:
        update: تحديث من Telegram
        context: سياق التطبيق
    """
    try:
        welcome_text = (
            "👋 مرحباً بك في بوت الإشراف الآلي المحسّن!\n\n"
            "🔒 <b>الميزات:</b>\n"
            "• حظر الروابط والمواقع\n"
            "• حظر أرقام الهواتف\n"
            "• حذف الكلمات المسيئة\n"
            "• نظام عقوبات تدريجي\n"
            "• تتبع الإحصائيات المتقدم\n\n"
            "📊 استخدم /stats لعرض الإحصائيات\n"
            "ℹ️ استخدم /help للمزيد من المعلومات"
        )
        await update.message.reply_text(welcome_text, parse_mode="HTML")
    except TelegramError as e:
        logger.error(f"❌ خطأ في معالج /start: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في /start: {e}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج أمر /help
    
    Args:
        update: تحديث من Telegram
        context: سياق التطبيق
    """
    try:
        help_text = (
            "📋 <b>قائمة الأوامر:</b>\n\n"
            "/start - عرض رسالة الترحيب\n"
            "/help - عرض هذه الرسالة\n"
            "/stats - عرض إحصائيات المجموعة\n"
            "/mystats - عرض إحصائياتك الشخصية\n"
            "/rules - عرض قوانين المجموعة\n"
            "/info - معلومات عن البوت\n\n"
            "⚠️ <b>القوانين:</b>\n"
            "❌ لا يسمح بنشر الروابط\n"
            "❌ لا يسمح بنشر أرقام الهواتف\n"
            "❌ لا يسمح باستخدام الكلمات المسيئة\n"
            "❌ احترم جميع أعضاء المجموعة"
        )
        await update.message.reply_text(help_text, parse_mode="HTML")
    except TelegramError as e:
        logger.error(f"❌ خطأ في معالج /help: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في /help: {e}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض إحصائيات المجموعة
    
    Args:
        update: تحديث من Telegram
        context: سياق التطبيق
    """
    try:
        chat_id = str(update.message.chat.id)

        if chat_id not in STATS or not STATS[chat_id]:
            await update.message.reply_text("📊 لا توجد إحصائيات حتى الآن")
            return

        stats_text = "📊 <b>إحصائيات المجموعة:</b>\n\n"

        total_warnings = 0
        total_bans = 0
        total_deleted = 0

        for user_id, user_stats in STATS[chat_id].items():
            total_warnings += user_stats.get("warnings", 0)
            total_bans += user_stats.get("bans", 0)
            total_deleted += user_stats.get("deleted_messages", 0)

        stats_text += f"⚠️ إجمالي التحذيرات: {total_warnings}\n"
        stats_text += f"🚫 إجمالي الحظر: {total_bans}\n"
        stats_text += f"🗑️ إجمالي الرسائل المحذوفة: {total_deleted}\n"
        stats_text += f"👥 عدد المستخدمين المراقبين: {len(STATS[chat_id])}\n"

        await update.message.reply_text(stats_text, parse_mode="HTML")
    except TelegramError as e:
        logger.error(f"❌ خطأ في معالج /stats: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في /stats: {e}")


async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض إحصائيات المستخدم الشخصية
    
    Args:
        update: تحديث من Telegram
        context: سياق التطبيق
    """
    try:
        user_id = str(update.message.from_user.id)
        chat_id = str(update.message.chat.id)
        username = update.message.from_user.username or update.message.from_user.first_name

        if chat_id not in STATS or user_id not in STATS[chat_id]:
            await update.message.reply_text("📊 ليس لديك إحصائيات في هذه المجموعة")
            return

        user_stats = STATS[chat_id][user_id]

        stats_text = f"📊 <b>إحصائياتك الشخصية:</b>\n\n"
        stats_text += f"👤 المستخدم: <b>{username}</b>\n"
        stats_text += f"⚠️ التحذيرات: {user_stats.get('warnings', 0)}\n"
        stats_text += f"🚫 الحظر: {user_stats.get('bans', 0)}\n"
        stats_text += f"🗑️ الرسائل المحذوفة: {user_stats.get('deleted_messages', 0)}\n"

        await update.message.reply_text(stats_text, parse_mode="HTML")
    except TelegramError as e:
        logger.error(f"❌ خطأ في معالج /mystats: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في /mystats: {e}")


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض قوانين المجموعة
    
    Args:
        update: تحديث من Telegram
        context: سياق التطبيق
    """
    try:
        rules_text = (
            "📋 <b>قوانين المجموعة:</b>\n\n"
            "1️⃣ احترم جميع الأعضاء\n"
            "2️⃣ لا تنشر روابط أو مواقع\n"
            "3️⃣ لا تشارك أرقام هواتفك أو هواتف الآخرين\n"
            "4️⃣ لا تستخدم كلمات مسيئة أو بذيئة\n"
            "5️⃣ لا تنشر محتوى إباحي أو عنيف\n"
            "6️⃣ لا تقم بالإزعاج أو التنمر\n"
            "7️⃣ لا تنشر رسائل تجارية أو إعلانية\n"
            "8️⃣ احترم خصوصية الآخرين\n\n"
            "⚠️ <b>العقوبات:</b>\n"
            "🗑️ حذف الرسالة\n"
            "⚠️ تحذير (حتى 3 تحذيرات)\n"
            "🚫 حظر من المجموعة"
        )
        await update.message.reply_text(rules_text, parse_mode="HTML")
    except TelegramError as e:
        logger.error(f"❌ خطأ في معالج /rules: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في /rules: {e}")


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معلومات عن البوت
    
    Args:
        update: تحديث من Telegram
        context: سياق التطبيق
    """
    try:
        info_text = (
            "ℹ️ <b>معلومات البوت:</b>\n\n"
            "🤖 <b>الاسم:</b> بوت الإشراف الآلي المحسّن\n"
            "📅 <b>الإصدار:</b> 3.0.0\n"
            "👨‍💻 <b>المطور:</b> فريق التطوير\n\n"
            "✨ <b>الميزات الرئيسية:</b>\n"
            "• الإشراف التلقائي على الرسائل\n"
            "• حظر الروابط والأرقام\n"
            "• تصفية الكلمات المسيئة والإعلانات\n"
            "• نظام عقوبات تدريجي\n"
            "• نظام الإحصائيات المتقدم\n"
            "• معالجة أخطاء محسّنة\n"
            "• استجابة فورية وسريعة\n\n"
            "🔐 <b>الأمان:</b>\n"
            "البوت يعمل بأعلى معايير الأمان والخصوصية"
        )
        await update.message.reply_text(info_text, parse_mode="HTML")
    except TelegramError as e:
        logger.error(f"❌ خطأ في معالج /info: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في /info: {e}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج الأخطاء
    
    Args:
        update: تحديث من Telegram
        context: سياق التطبيق
    """
    logger.error(f"❌ خطأ: {context.error}", exc_info=context.error)
    
    try:
        if update and update.message:
            await update.message.reply_text(
                "❌ حدث خطأ ما. يرجى المحاولة لاحقاً.",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"❌ خطأ في معالج الأخطاء: {e}")


# ==================== الدالة الرئيسية ====================

def main() -> None:
    """الدالة الرئيسية لتشغيل البوت"""
    # تحميل الإحصائيات
    load_stats()

    # بناء التطبيق
    app = ApplicationBuilder().token(TOKEN).build()

    # إضافة معالجات الأوامر
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("mystats", mystats_command))
    app.add_handler(CommandHandler("rules", rules_command))
    app.add_handler(CommandHandler("info", info_command))

    # إضافة معالج الرسائل للإشراف التلقائي
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_moderation))

    # إضافة معالج الأخطاء
    app.add_error_handler(error_handler)

    # تشغيل البوت
    logger.info("🤖 البوت قيد التشغيل...")
    logger.info("اضغط Ctrl+C لإيقاف البوت")

    try:
        app.run_polling(
            allowed_updates=["message", "edited_message"],
            drop_pending_updates=True
        )
    except KeyboardInterrupt:
        logger.info("⏹️ تم إيقاف البوت")
    except TelegramError as e:
        logger.error(f"❌ خطأ في Telegram: {e}")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")


if __name__ == "__main__":
    main()
