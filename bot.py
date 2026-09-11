import os
import glob
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaVideo, InputMediaPhoto, BotCommand
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.request import HTTPXRequest
import yt_dlp
import instaloader

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# خواندن توکن به صورت امن از متغیرهای محیطی سرور (Render)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 0

download_queue = asyncio.Queue()
active_users = set()

# متغیر برای کنترل وضعیت کارگر (Worker) هنگام خاموش شدن ربات
is_running = True

L = instaloader.Instaloader(
    download_videos=True,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    compress_json=False,
    post_metadata_txt_pattern=""
)

# بارگذاری امن کوکی اینستاگرام با مسیر مطلق
try:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for cookie_filename in ["cookies.txt", "cookies1.txt", "www.instagram.com_cookies.txt"]:
        c_path = os.path.join(base_dir, cookie_filename)
        if os.path.exists(c_path):
            L.load_session_from_file(c_path)
            break
except Exception:
    pass

async def set_bot_commands(application):
    """تنظیم لیست دستورات منو برای نمایش در تلگرام"""
    commands = [
        BotCommand("start", "شروع به کار ربات"),
        BotCommand("help", "راهنمای استفاده از ربات"),
        BotCommand("support", "ارتباط با پشتیبانی"),
        BotCommand("admin", "پنل مدیریت")
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    active_users.add(user.id)
    welcome_text = (
        f"سلام {user.first_name}! 👋\n\n"
        "من ربات پیشرفته و حرفه‌ای دانلودر شما هستم. 🚀\n"
        "لینک ویدیو، شورتز یا عکس از یوتیوب، اینستاگرام، تیک‌تاک یا ساندکلاد را بفرستید."
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر دستور راهنما (/help)"""
    help_text = (
        "🤖 **راهنمای استفاده از ربات دانلودر مدیا**\n\n"
        "با این ربات می‌توانید به سادگی و با بالاترین کیفیت، محتوای دلخواه خود را از شبکه‌های اجتماعی دانلود کنید.\n\n"
        "📥 **نحوه دانلود از یوتیوب:**\n"
        "کافی است لینک ویدیوی یوتیوب را بفرستید تا گزینه‌های انتخاب کیفیت یا تبدیل به صوت (MP3) را دریافت کنید.\n\n"
        "📥 **نحوه دانلود از اینستاگرام:**\n"
        "لینک پست، ریلز یا ویدیو را بفرستید تا فایل مستقیماً ارسال شود.\n\n"
        "💬 برای شروع کافی است لینک خود را همینجا ارسال کنید!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر دستور پشتیبانی (/support)"""
    support_text = (
        "🛠 **پشتیبانی و ارتباط با سازنده**\n\n"
        "اگر در حین دانلود ویدیوها با خطایی مواجه شدید یا پیشنهادی دارید، می‌توانید از طریق لینک زیر با ما در ارتباط باشید:\n\n"
        "👤 [ارتباط با پشتیبانی](https://t.me/Alirezazpx)"
    )
    await update.message.reply_text(support_text, parse_mode="Markdown")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if ADMIN_ID and user.id != ADMIN_ID:
        await update.message.reply_text("❌ شما دسترسی ادمین ندارید.")
        return
     
    stats_msg = (
        "📊 پنل مدیریت ربات\n\n"
        f"👥 تعداد کل کاربران فعال این نشست: {len(active_users)}\n"
        f"📦 تعداد درخواست‌های در صف: {download_queue.qsize()}\n"
        f"⚙️ وضعیت سیستم: پایدار و آماده به کار"
    )
    await update.message.reply_text(stats_msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith("http"):
        await update.message.reply_text("لطفاً یک لینک معتبر (شروع شده با http) ارسال کنید.")
        return

    if any(domain in url for domain in ["youtube.com", "youtu.be"]):
        keyboard = [
            [
                InlineKeyboardButton("🔥 بالاترین کیفیت (Full HD/4K)", callback_data=f"yt_best|{url}"),
                InlineKeyboardButton("💻 کیفیت خوب (720p)", callback_data=f"yt_720|{url}")
            ],
            [
                InlineKeyboardButton("📱 کیفیت متوسط (480p)", callback_data=f"yt_480|{url}"),
                InlineKeyboardButton("🎵 تبدیل به موزیک (MP3)", callback_data=f"yt_audio_mp3|{url}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🎬 لینک یوتیوب شناسایی شد. لطفاً کیفیت مورد نظر خود را انتخاب کنید:",
            reply_markup=reply_markup
        )
    else:
        status_msg = await update.message.reply_text("`[░░░░░░░░░░] 0%`", parse_mode="Markdown")
        await download_queue.put((update, "generic", url, status_msg))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    action, url = data.split("|", 1)
    
    try:
        await query.message.edit_text("`[░░░░░░░░░░] 0%`", parse_mode="Markdown")
    except Exception:
        pass
        
    status_msg = query.message
    await download_queue.put((query, action, url, status_msg))

async def download_worker():
    global is_running
    while is_running:
        try:
            # استفاده از تایم‌اوت برای اینکه حلقه قفل نشود و بتواند وضعیت is_running را بررسی کند
            try:
                item = await asyncio.wait_for(download_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            target_obj, action, url, status_msg = item
            downloaded_files = []
            temp_dirs = []
            post_caption = ""
            is_callback = hasattr(target_obj, "message")
            message_context = target_obj.message if is_callback else target_obj.effective_message

            try:
                last_reported_percent = [-1]

                def make_progress_hook(msg_obj, loop):
                    def hook(d):
                        if d['status'] == 'downloading':
                            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                            downloaded = d.get('downloaded_bytes', 0)
                            if total > 0:
                                percent = int((downloaded / total) * 100)
                                percent = (percent // 10) * 10
                                if percent > 90:
                                    percent = 90
                                
                                if percent != last_reported_percent[0]:
                                    last_reported_percent[0] = percent
                                    filled = int(percent / 10)
                                    bar = '▓' * filled + '░' * (10 - filled)
                                    text = f"`[{bar}] {percent}%`"
                                    
                                    async def external_update():
                                        try:
                                            await msg_obj.edit_text(text, parse_mode="Markdown")
                                        except Exception:
                                            pass
                                    
                                    asyncio.run_coroutine_threadsafe(external_update(), loop)
                    return hook

                if "instagram.com" in url:
                    try:
                        if "/p/" in url or "/reel/" in url or "/tv/" in url:
                            async def insta_stepper():
                                try:
                                    for p in [10, 30, 50, 70, 90]:
                                        await asyncio.sleep(0.4)
                                        filled = int(p / 10)
                                        bar = '▓' * filled + '░' * (10 - filled)
                                        try:
                                            await status_msg.edit_text(f"`[{bar}] {p}%`", parse_mode="Markdown")
                                        except:
                                            pass
                                except asyncio.CancelledError:
                                    pass

                            stepper_t = asyncio.create_task(insta_stepper())

                            shortcode = url.split("/p/")[1].split("/")[0].split("?")[0] if "/p/" in url else url.split("/reel/")[1].split("/")[0].split("?")[0]
                            post = instaloader.Post.from_shortcode(L.context, shortcode)
                            
                            if post.caption:
                                post_caption = post.caption
                                if len(post_caption) > 1000:
                                    post_caption = post_caption[:997] + "..."

                            target_dir = f"temp_{shortcode}"
                            os.makedirs(target_dir, exist_ok=True)
                            temp_dirs.append(target_dir)
                            
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, lambda: L.download_post(post, target=target_dir))
                            
                            stepper_t.cancel()
                            try:
                                await stepper_t
                            except asyncio.CancelledError:
                                pass

                            for file in sorted(glob.glob(os.path.join(target_dir, "*.*"))):
                                if file.endswith(('.mp4', '.jpg', '.jpeg', '.png', '.webp')) and not file.endswith('.json'):
                                    downloaded_files.append(file)
                    except Exception as inst_err:
                        logger.error(f"Instaloader fast download error: {inst_err}")

                if not downloaded_files:
                    loop = asyncio.get_event_loop()
                    ydl_opts = {
                        'ignoreerrors': True,
                        'socket_timeout': 60,
                        'extractor_retries': 5,
                        'outtmpl': 'downloaded_media_%(id)s_%(autonumber)s.%(ext)s',
                        'progress_hooks': [make_progress_hook(status_msg, loop)],
                    }

                    # تنظیم دقیق مسیر مطلق فایل کوکی یوتیوب
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    for c_file in ["www.youtube.com_cookies.txt", "cookies.txt", "cookies1.txt"]:
                        c_path = os.path.join(base_dir, c_file)
                        if os.path.exists(c_path):
                            ydl_opts['cookiefile'] = c_path
                            break

                    if action == "yt_audio_mp3":
                        ydl_opts['format'] = 'bestaudio/best'
                        ydl_opts['postprocessors'] = [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': '192',
                        }]
                    else:
                        ydl_opts['merge_output_format'] = 'mp4'
                        if action == "yt_720":
                            ydl_opts['format'] = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
                        elif action == "yt_480":
                            ydl_opts['format'] = 'bestvideo[height<=480]+bestaudio/best[height<=480]/best'
                        else:
                            ydl_opts['format'] = 'best/bestvideo+bestaudio/best'

                    def run_ytdlp():
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            return ydl.extract_info(url, download=True)

                    info = await loop.run_in_executor(None, run_ytdlp)

                    if info:
                        media_ids = []
                        if 'entries' in info:
                            for entry in info['entries']:
                                if entry and 'id' in entry:
                                    media_ids.append(entry['id'])
                        elif 'id' in info:
                            media_ids.append(info['id'])

                        if info and 'title' in info:
                            post_caption = f"📌 {info.get('title')}"

                        for mid in media_ids:
                            for found_file in sorted(glob.glob(f"*{mid}*")):
                                if found_file not in downloaded_files and not found_file.endswith(('.py', '.txt', '.json')):
                                    downloaded_files.append(found_file)

                if not downloaded_files:
                    await status_msg.edit_text("❌ دانلود انجام نشد. لینک معتبر نیست یا فایل در دسترس نمی‌باشد.")
                    download_queue.task_done()
                    continue

                try:
                    await status_msg.edit_text("`[▓▓▓▓▓▓▓▓▓▓] 100%`", parse_mode="Markdown")
                except Exception:
                    pass

                if len(downloaded_files) > 1:
                    media_group = []
                    file_objects = []
                    try:
                        for i, file_path in enumerate(downloaded_files):
                            if len(media_group) >= 10:
                                break
                            f = open(file_path, 'rb')
                            file_objects.append(f)
                            
                            caption = post_caption if i == 0 else None
                            
                            if file_path.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                                media_group.append(InputMediaPhoto(media=f, caption=caption))
                            elif file_path.endswith(('.mp4', '.m4v')):
                                media_group.append(InputMediaVideo(media=f, caption=caption))
                        
                        if media_group:
                            await message_context.reply_media_group(media=media_group)
                    finally:
                        for f in file_objects:
                            try:
                                f.close()
                            except:
                                pass
                else:
                    for file_path in downloaded_files:
                        if not os.path.exists(file_path):
                            continue
                        file_size = os.path.getsize(file_path)
                        with open(file_path, 'rb') as f:
                            if action == "yt_audio_mp3" or file_path.endswith('.mp3'):
                                await message_context.reply_audio(audio=f, caption=post_caption)
                            elif file_path.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                                if file_size > 5000:
                                    await message_context.reply_photo(photo=f, caption=post_caption)
                            else:
                                await message_context.reply_video(video=f, caption=post_caption, supports_streaming=True)

                try:
                    await status_msg.delete()
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"Worker download error: {e}")
                try:
                    await status_msg.edit_text(f"❌ خطایی رخ داد:\n`{str(e)}`", parse_mode="Markdown")
                except Exception:
                    pass
            finally:
                for file_path in downloaded_files:
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass
                for d in temp_dirs:
                    if os.path.isdir(d):
                        for f in glob.glob(os.path.join(d, "*.*")):
                            try:
                                os.remove(f)
                            except Exception:
                                pass
                        try:
                            os.rmdir(d)
                        except Exception:
                            pass
                download_queue.task_done()
        except Exception:
            pass

async def post_init(application):
    asyncio.create_task(download_worker())
    await set_bot_commands(application)
    print("🚀 ربات آماده به کار است...")

async def post_shutdown(application):
    global is_running
    is_running = False

if __name__ == '__main__':
    request = HTTPXRequest(connect_timeout=60.0, read_timeout=90.0)
    
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CommandHandler("admin", admin_stats))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    app.run_polling()
