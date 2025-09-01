import logging
import os
import asyncio
import json
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Get API keys from environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Please set TELEGRAM_BOT_TOKEN in your .env file")
if not GEMINI_API_KEY:
    raise ValueError("Please set GEMINI_API_KEY in your .env file")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash-lite')

categories = ['Motivational', 'Anime', 'Jokes']

# In-memory storage for current session
user_subscriptions = {}
current_quotes = {}  # Store current quote per user

scheduler = AsyncIOScheduler()

# Initialize SQLite database
def init_database():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            preferences TEXT,
            daily_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Chat history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message TEXT,
            response TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES users (chat_id)
        )
    ''')
    
    # Favorites table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            quote_text TEXT,
            quote_category TEXT,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES users (chat_id)
        )
    ''')
    
    conn.commit()
    conn.close()


# Database helper functions
def save_user_preference(chat_id, key, value):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT preferences FROM users WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    
    if result:
        prefs = json.loads(result[0]) if result[0] else {}
        prefs[key] = value
        cursor.execute('UPDATE users SET preferences = ? WHERE chat_id = ?', 
                      (json.dumps(prefs), chat_id))
    else:
        prefs = {key: value}
        cursor.execute('INSERT INTO users (chat_id, preferences) VALUES (?, ?)', 
                      (chat_id, json.dumps(prefs)))
    
    conn.commit()
    conn.close()

def get_user_preferences(chat_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT preferences FROM users WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    
    conn.close()
    return json.loads(result[0]) if result and result[0] else {}

def save_chat_history(chat_id, message, response):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    cursor.execute('INSERT INTO chat_history (chat_id, message, response) VALUES (?, ?, ?)',
                  (chat_id, message, response))
    
    conn.commit()
    conn.close()

def get_recent_chat_history(chat_id, limit=10):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT message, response FROM chat_history 
        WHERE chat_id = ? 
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (chat_id, limit))
    
    results = cursor.fetchall()
    conn.close()
    
    return list(reversed(results))

def save_favorite_quote(chat_id, quote_text, category):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    cursor.execute('INSERT INTO favorites (chat_id, quote_text, quote_category) VALUES (?, ?, ?)',
                  (chat_id, quote_text, category))
    
    conn.commit()
    conn.close()

def get_favorite_quotes(chat_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT quote_text, quote_category, saved_at FROM favorites WHERE chat_id = ? ORDER BY saved_at DESC',
                  (chat_id,))
    
    results = cursor.fetchall()
    conn.close()
    
    return results

# Quote fetching functions
def fetch_motivational_quote():
    try:
        response = requests.get('https://zenquotes.io/api/random', timeout=5)
        data = response.json()
        quote = data[0]['q']
        author = data[0]['a']
        return f'"{quote}"\n- {author}', 'Motivational'
    except Exception as e:
        logging.error(f"Error fetching motivational quote: {e}")
        return '"The only way to do great work is to love what you do."\n- Steve Jobs', 'Motivational'

def fetch_anime_quote():
    try:
        response = requests.get('https://animechan.vercel.app/api/random', timeout=5)
        data = response.json()
        quote = data['quote']
        character = data['character']
        anime = data['anime']
        return f'"{quote}"\n- {character} ({anime})', 'Anime'
    except Exception as e:
        logging.error(f"Error fetching anime quote: {e}")
        return '"Believe in yourself. Not in the you who believes in me. Not the me who believes in you. Believe in the you who believes in yourself."\n- Kamina (Gurren Lagann)', 'Anime'

def fetch_joke():
    try:
        response = requests.get('https://official-joke-api.appspot.com/random_joke', timeout=5)
        data = response.json()
        return f"{data['setup']}\n\n{data['punchline']}", 'Jokes'
    except Exception as e:
        logging.error(f"Error fetching joke: {e}")
        return "Why don't scientists trust atoms?\n\nBecause they make up everything!", 'Jokes'

# Gemini integration functions
async def translate_text(text, target_language="Hindi"):
    try:
        prompt = f"Translate this text to {target_language}. Return ONLY the translation:\n\n{text}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logging.error(f"Translation error: {e}")
        return f"Sorry, couldn't translate to {target_language}."

async def chat_with_gemini(message, chat_id):
    try:
        # Get recent chat history for context
        history = get_recent_chat_history(chat_id, 3)
        user_prefs = get_user_preferences(chat_id)
        
        # Build specialized prompt for direct answers and quotes
        system_prompt = """You are a helpful assistant that gives DIRECT, CONCISE answers. Rules:

1. ALWAYS answer the main question FIRST, then optionally add a relevant quote
2. For factual questions (like "PM of India", "8+9"), give the answer immediately
3. For quote requests ("quote about soil", "quote of flower"), provide a relevant quote directly
4. Accept imperfect grammar - understand intent (e.g., "of" instead of "about")
5. Keep responses under 200 characters when possible
6. If adding quotes, make them relevant and inspiring

Examples:
- "PM of India" → "Narendra Modi. 'Dreams are not what you see in sleep, dreams are things which do not let you sleep.' - A.P.J. Abdul Kalam"
- "8+9" → "17. 'Mathematics is the music of reason.' - James Joseph Sylvester"
- "quote about soil" → "'To forget how to dig the earth and to tend the soil is to forget ourselves.' - Mahatma Gandhi"

Current conversation context:"""
        
        if history:
            system_prompt += "\nRecent chat:\n"
            for msg, resp in history[-2:]:
                system_prompt += f"User: {msg}\nBot: {resp}\n"
        
        full_prompt = f"{system_prompt}\n\nUser question: {message}\n\nDirect answer:"
        
        response = model.generate_content(full_prompt)
        bot_response = response.text.strip()
        
        # Save to chat history
        save_chat_history(chat_id, message, bot_response)
        
        return bot_response
    except Exception as e:
        logging.error(f"Gemini chat error: {e}")
        return "Sorry, I'm having trouble right now. Try again!"

# Create side menu
def create_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("💝 Motivational", callback_data="category_Motivational"),
         InlineKeyboardButton("🎌 Anime", callback_data="category_Anime")],
        [InlineKeyboardButton("😂 Jokes", callback_data="category_Jokes"),
         InlineKeyboardButton("📖 Favorites", callback_data="favorites")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("🔄 Random Quote", callback_data="random_quote")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_quote_keyboard(category):
    keyboard = [
        [InlineKeyboardButton("🔄 Next", callback_data=f"category_{category}"),
         InlineKeyboardButton("🌍 Translate", callback_data=f"translate_{category}")],
        [InlineKeyboardButton("❤️ Save", callback_data=f"save_{category}"),
         InlineKeyboardButton("📤 Share", callback_data=f"share_{category}")],
        [InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # Save user to database
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO users (chat_id, username) VALUES (?, ?)', 
                  (chat_id, username))
    conn.commit()
    conn.close()
    
    reply_markup = create_main_menu_keyboard()
    welcome_text = f"👋 Hi {username}!\n\n🤖 I'm your AI quote bot with:\n✅ Smart quotes & translation\n✅ Memory of our chats\n✅ Daily reminders\n\nChoose an option or just chat with me!"
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = update.effective_chat.id
    
    if data.startswith("category_") or data == "random_quote":
        if data == "random_quote":
            import random
            category = random.choice(categories)
        else:
            category = data.split("_")[1]
        
        # Fetch quote based on category
        if category == "Motivational":
            quote, cat = fetch_motivational_quote()
        elif category == "Anime":
            quote, cat = fetch_anime_quote()
        elif category == "Jokes":
            quote, cat = fetch_joke()
        
        # Store current quote for this user
        current_quotes[chat_id] = {
            'text': quote,
            'category': cat
        }
        
        keyboard = create_quote_keyboard(category)
        await query.edit_message_text(text=f"📝 {cat}:\n\n{quote}", reply_markup=keyboard)
    
    elif data.startswith("translate_"):
        if chat_id not in current_quotes:
            await query.edit_message_text("No quote to translate. Please select a quote first.")
            return
            
        current_quote = current_quotes[chat_id]['text']
        user_prefs = get_user_preferences(chat_id)
        target_lang = user_prefs.get('language', 'Hindi')
        
        translated = await translate_text(current_quote, target_lang)
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_quote"),
                    InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=f"🌍 In {target_lang}:\n\n{translated}",
            reply_markup=reply_markup
        )
    
    elif data.startswith("save_"):
        if chat_id not in current_quotes:
            await query.edit_message_text("No quote to save. Please select a quote first.")
            return
        
        current_quote = current_quotes[chat_id]['text']
        current_category = current_quotes[chat_id]['category']
        
        save_favorite_quote(chat_id, current_quote, current_category)
        
        keyboard = create_quote_keyboard(current_category.replace(' ', ''))
        await query.edit_message_text(
            text=f"❤️ Saved to favorites!\n\n{current_quote}",
            reply_markup=keyboard
        )
    
    elif data.startswith("share_"):
        if chat_id not in current_quotes:
            await query.edit_message_text("No quote to share. Please select a quote first.")
            return
        
        current_quote = current_quotes[chat_id]['text']
        share_text = f"📤 Share this quote:\n\n{current_quote}\n\n~ Shared via Quote Bot"
        
        keyboard = create_quote_keyboard(current_quotes[chat_id]['category'].replace(' ', ''))
        await query.edit_message_text(text=share_text, reply_markup=keyboard)
    
    elif data == "favorites":
        favorites = get_favorite_quotes(chat_id)
        if favorites:
            text = "📖 Your Favorites:\n\n"
            for i, (quote, category, saved_at) in enumerate(favorites[:5], 1):
                # Clean quote display
                clean_quote = quote.replace('\n', ' ')[:60] + "..." if len(quote) > 60 else quote.replace('\n', ' ')
                text += f"{i}. [{category}] {clean_quote}\n\n"
            if len(favorites) > 5:
                text += f"...and {len(favorites) - 5} more"
        else:
            text = "📖 No favorites yet!\n\nSave quotes using the ❤️ button."
        
        keyboard = [[InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "settings":
        user_prefs = get_user_preferences(chat_id)
        current_lang = user_prefs.get('language', 'Hindi')
        daily_time = user_subscriptions.get(chat_id, 'Not set')
        if isinstance(daily_time, tuple):
            daily_time = f"{daily_time[0]:02d}:{daily_time[1]:02d}"
        
        keyboard = [
            [InlineKeyboardButton(f"🌍 Language: {current_lang}", callback_data="change_language")],
            [InlineKeyboardButton(f"🔔 Daily: {daily_time}", callback_data="daily_settings")],
            [InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]
        ]
        
        text = f"⚙️ Settings:\n\n🌍 Translation: {current_lang}\n🔔 Daily quotes: {daily_time}\n\nUse /daily HH:MM to set time"
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "change_language":
        languages = ["Hindi","Assamese", "Bengali", "Bodo", "Dogri", "Gujarati", "Kannada", "Kashmiri", "Konkani", "Maithili", "Malayalam", "Manipuri", "Marathi", "Nepali", "Odia", "Punjabi", "Sanskrit", "Santali", "Sindhi", "Tamil", "Telugu", "Urdu", "Spanish", "French", "German", "Italian", "Japanese","Chinese", "Russian", "Portuguese", "Arabic"]
        keyboard = [[InlineKeyboardButton(lang, callback_data=f"lang_{lang}")] for lang in languages]
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="settings")])
        
        await query.edit_message_text(
            text="🌍 Choose translation language:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data.startswith("lang_"):
        lang = data.split("_")[1]
        save_user_preference(chat_id, 'language', lang)
        await query.edit_message_text(
            text=f"✅ Language set to {lang}!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]])
        )
    
    elif data == "back_to_quote":
        if chat_id in current_quotes:
            quote = current_quotes[chat_id]['text']
            category = current_quotes[chat_id]['category']
            keyboard = create_quote_keyboard(category.replace(' ', ''))
            await query.edit_message_text(text=f"📝 {category}:\n\n{quote}", reply_markup=keyboard)
        else:
            await query.edit_message_text("Quote not found.", reply_markup=create_main_menu_keyboard())
    
    elif data == "main_menu":
        reply_markup = create_main_menu_keyboard()
        await query.edit_message_text(
            text="🏠 Main Menu\n\nChoose an option or chat with me:",
            reply_markup=reply_markup
        )

async def quote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quote, category = fetch_motivational_quote()
    chat_id = update.effective_chat.id
    current_quotes[chat_id] = {'text': quote, 'category': category}
    keyboard = create_quote_keyboard('Motivational')
    await update.message.reply_text(f"📝 {category}:\n\n{quote}", reply_markup=keyboard)

async def daily_quote_job(chat_id, bot):
    try:
        quote, category = fetch_motivational_quote()
        keyboard = create_quote_keyboard('Motivational')
        current_quotes[chat_id] = {'text': quote, 'category': category}
        await bot.send_message(
            chat_id=chat_id, 
            text=f"🌅 Daily Quote:\n\n{quote}",
            reply_markup=keyboard
        )
        logging.info(f"Daily quote sent to chat_id: {chat_id}")
    except Exception as e:
        logging.error(f"Error sending daily quote to {chat_id}: {e}")

def schedule_daily_quote(bot, chat_id, hour, minute):
    job_id = str(chat_id)
    existing_job = scheduler.get_job(job_id)
    if existing_job:
        existing_job.remove()

    trigger = CronTrigger(hour=hour, minute=minute)
    scheduler.add_job(
        daily_quote_job,
        trigger=trigger,
        args=[chat_id, bot],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=300
    )

async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("⏰ Format: /daily HH:MM\nExample: /daily 08:30")
        return

    time_str = context.args[0]
    try:
        hour, minute = map(int, time_str.split(':'))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid time")
        chat_id = update.effective_chat.id
        user_subscriptions[chat_id] = (hour, minute)
        schedule_daily_quote(context.bot, chat_id, hour, minute)
        await update.message.reply_text(f"✅ Daily quotes set for {time_str}!")
    except Exception:
        await update.message.reply_text("❌ Invalid format. Use HH:MM (24-hour)")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free text messages with Gemini AI"""
    message_text = update.message.text
    chat_id = update.effective_chat.id
    
    # Skip commands
    if message_text.startswith('/'):
        return
    
    # Chat with Gemini using improved prompting
    response = await chat_with_gemini(message_text, chat_id)
    await update.message.reply_text(response)

async def favorites_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    favorites = get_favorite_quotes(chat_id)
    
    if not favorites:
        keyboard = create_main_menu_keyboard()
        await update.message.reply_text(
            "📖 No favorites yet!\n\nStart saving quotes with the ❤️ button.",
            reply_markup=keyboard
        )
        return
    
    text = "📖 Your Favorite Quotes:\n\n"
    for i, (quote, category, saved_at) in enumerate(favorites[:10], 1):
        clean_quote = quote[:100] + "..." if len(quote) > 100 else quote
        text += f"{i}. [{category}]\n{clean_quote}\n\n"
    
    if len(favorites) > 10:
        text += f"...and {len(favorites) - 10} more quotes!"
    
    keyboard = create_main_menu_keyboard()
    await update.message.reply_text(text, reply_markup=keyboard)

async def on_startup(app):
    init_database()
    scheduler.start()
    logging.info("🚀 Bot started with database and scheduler")

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('quote', quote_command))
    app.add_handler(CommandHandler('daily', daily_command))
    app.add_handler(CommandHandler('favorites', favorites_command))
    
    # Callback query handler for buttons
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Message handler for free text (Gemini chat)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.post_init = on_startup

    print("🤖 Advanced Quote Bot with Gemini AI is starting...")
    print("✅ Features: Smart quotes, AI chat, translation, favorites, daily reminders")
    app.run_polling()

if __name__ == '__main__':
    main()


