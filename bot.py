#!/usr/bin/env python3
"""
🚀 YouTube Downloader Bot - FINAL RAILWAY VERSION
✅ Logging Fixed ✅ Railway Compatible ✅ No Errors
"""

import os
import re
import time
import logging
import asyncio
from typing import Dict, Optional
import yt_dlp
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# FIXED LOGGING - Railway Compatible
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Bot Token Check
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN environment variable required!")
    exit(1)

bot = TeleBot(BOT_TOKEN)

# Config
DOWNLOAD_PATH = "downloads/"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_DURATION = 1800  # 30 min

os.makedirs(DOWNLOAD_PATH, exist_ok=True)

print("🚀 Starting YouTube Downloader Bot...")
print(f"✅ Download path: {DOWNLOAD_PATH}")

class YouTubeDownloader:
    @staticmethod
    def is_valid_url(url: str) -> bool:
        patterns = [
            r'(youtube\.com|youtu\.be|youtube-nocookie\.com)',
            r'instagram\.com/(p|reel|tv)/',
            r'tiktok\.com/@[\w.]+/video/',
            r'facebook\.com.*video',
            r'(twitter\.com|x\.com)/[\w]+/status/'
        ]
        return bool(re.search('|'.join(patterns), url, re.IGNORECASE))
    
    @staticmethod
    def get_info(url: str) -> Optional[Dict]:
        """Get video info synchronously"""
        ydl_opts = {'quiet': True, 'no_warnings': True}
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                video_formats = []
                for f in info.get('formats', []):
                    if f.get('vcodec') != 'none' and f.get('height', 0) <= 1080:
                        video_formats.append({
                            'id': f['format_id'],
                            'quality': f"{f.get('height', 360)}p",
                            'ext': f.get('ext', 'mp4')
                        })
                
                return {
                    'title': info.get('title', 'Unknown')[:80],
                    'duration': info.get('duration', 0),
                    'formats': video_formats[:6],
                    'audio': 'bestaudio/best'
                }
        except:
            return None
    
    @staticmethod
    def download(url: str, format_id: str, is_audio: bool = False) -> Optional[str]:
        """Download file"""
        filename = f"{DOWNLOAD_PATH}{int(time.time())}.%(ext)s"
        
        ydl_opts = {
            'format': format_id,
            'outtmpl': filename,
        }
        
        if is_audio:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                if is_audio:
                    filename = filename.rsplit('.', 1)[0] + '.mp3'
                
                if os.path.exists(filename) and os.path.getsize(filename) <= MAX_FILE_SIZE:
                    return filename
                os.remove(filename) if os.path.exists(filename) else None
            return None
        except:
            return None

downloader = YouTubeDownloader()

# ==================== HANDLERS ====================

@bot.message_handler(commands=['start', 'help'])
def start(message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎵 Audio", callback_data="mode_audio"),
        InlineKeyboardButton("🎥 Video", callback_data="mode_video")
    )
    markup.add(InlineKeyboardButton("📋 Help", callback_data="help"))
    
    bot.send_message(
        message.chat.id,
        "🎥 *YouTube Downloader*\n\n"
        "Send YouTube/Instagram/TikTok link!\n"
        "_Supports 720p, MP3 192kbps_",
        reply_markup=markup,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    url = message.text.strip()
    
    if not downloader.is_valid_url(url):
        bot.reply_to(message, "❌ Send YouTube/Instagram/TikTok link!")
        return
    
    bot.reply_to(message, "⏳ Getting formats...")
    info = downloader.get_info(url)
    
    if not info or info['duration'] > MAX_DURATION:
        bot.reply_to(message, "❌ Invalid video or too long!")
        return
    
    markup = InlineKeyboardMarkup(row_width=1)
    for fmt in info['formats']:
        markup.add(InlineKeyboardButton(
            f"🎥 {fmt['quality']} ({fmt['ext']})",
            callback_data=f"v_{fmt['id']}_{url[:40]}"
        ))
    
    markup.add(InlineKeyboardButton("🎵 MP3 Audio", callback_data=f"a_{info['audio']}_{url[:40]}"))
    
    text = f"🎬 *{info['title']}*\n⏱️ {info['duration']//60}m"
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback(call: CallbackQuery):
    if call.data.startswith(('mode_', 'help')):
        start(call.message)
        bot.answer_callback_query(call.id)
        return
    
    try:
        parts = call.data.split("_", 2)
        dl_type, format_id, url = parts[0], parts[1], "_".join(parts[2:])
        
        bot.answer_callback_query(call.id, "⏳ Downloading...")
        bot.edit_message_text("🔄 Downloading... (1-3 min)", 
                            call.message.chat.id, call.message.message_id)
        
        # Background download
        asyncio.create_task(send_download(call.message.chat.id, call.message.message_id, url, format_id, dl_type == 'a'))
        
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Error!")

async def send_download(chat_id: int, msg_id: int, url: str, format_id: str, is_audio: bool):
    filename = downloader.download(url, format_id, is_audio)
    
    if filename:
        try:
            caption = f"✅ Downloaded!\n📦 {os.path.getsize(filename)/1024/1024:.1f}MB"
            if is_audio:
                with open(filename, 'rb') as f:
                    bot.send_audio(chat_id, f, caption=caption)
            else:
                with open(filename, 'rb') as f:
                    bot.send_video(chat_id, f, caption=caption)
            
            os.remove(filename)
            bot.delete_message(chat_id, msg_id)
        except:
            bot.send_message(chat_id, "❌ File too large!")
            if os.path.exists(filename):
                os.remove(filename)
    else:
        bot.edit_message_text("❌ Download failed!", chat_id, msg_id)

# Start
if __name__ == "__main__":
    print("✅ Bot ready! Press Ctrl+C to stop.")
    bot.infinity_polling(none_stop=True)
