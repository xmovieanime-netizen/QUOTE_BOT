# AI Quote Bot

An advanced AI-powered Telegram bot that delivers motivational, anime, and joke quotes with smart translation, daily reminders, and favorites management. It leverages Google Gemini AI for intelligent chat responses, supports all official Indian languages (plus additional options), and provides an engaging typing effect for smoother conversations.

## Features

- 💝 **Quotes**  
  - Motivational, Anime, and Joke categories  
  - Random quote on demand  
- 🌍 **Translation**  
  - Translate any quote into all 22 official Indian languages, plus English, Spanish, French, German, Italian, Japanese, Chinese, Russian, Portuguese, and Arabic  
- ❤️ **Favorites**  
  - Save quotes to your personal favorites  
  - Remove saved favorites  
  - View and manage your top quotes  
- 🔔 **Daily Reminders**  
  - Schedule a daily quote at your preferred time (`/daily HH:MM`)  
- 🤖 **AI Chat**  
  - Free-text chat powered by Google Gemini AI  
  - Direct, concise answers with optional inspirational quotes  
- ⌨️ **Typing Effect**  
  - Simulates typing before sending responses for a natural feel  

## Screenshots

![Main Menu](docs/main_menu.png)  
![Quote View](docs/quote_view.png)  
![Favorites](docs/favorites_view.png)  
![Settings](docs/settings_view.png)  

## Prerequisites

- Python 3.10+  
- Telegram bot token  
- Google Gemini AI API key  

## Installation

1. **Clone this repository**
   ```bash
    git clone https://github.com/yourusername/telegram-quote-bot.git
    cd telegram-quote-bot
2. Create and Activate Virtual Environment
   ```
    python -m venv venv
   ```
   ```
    source venv/bin/activate   # On macOS/Linux
   ```
   ```
    venv\Scripts\activate      # On Windows
   ```

4. Install Dependencies
    ```
    pip install -r requirements.txt

5. Setup Environment Variables

Create a .env file in the root directory:
```
 TELEGRAM_BOT_TOKEN=your-telegram-bot-token
 GEMINI_API_KEY=your-gemini-api-key
```
Get Telegram Bot Token from @BotFather
Get Gemini API Key from Google AI Studio

5. Run the Bot
```
python app.py
```
📖 Usage

Start bot: /start
-
Get a motivational quote: /quote
-
Set daily reminder: /daily HH:MM (24-hour format, e.g., /daily 08:30)
-
View favorites: /favorites
-
Chat directly with Gemini by sending any message

🖥️ Example Interaction

User: "quote about soil"
Bot: "'To forget how to dig the earth and to tend the soil is to forget ourselves.' - Mahatma Gandhi"

🗄 Database

SQLite (bot_data.db) automatically stores:
- Users (chat_id, username, preferences, reminder times)
- Chat history (messages + responses)
- Favorite quotes

🚀 Deployment

Run locally with python app.py
Or deploy on a cloud service (Heroku, Render, Railway, etc.)

📝 License

This project is licensed under the MIT License.

👨‍💻 Author

Developed by [ VENKATA SIVA KUMAR PARUVADA ] ✨
Feel free to ⭐ this repo if you like it!

📦 requirements.txt
python-telegram-bot==20.3
apscheduler
requests
python-dotenv
google-generativeai

🌍 .env.example
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
GEMINI_API_KEY=your-gemini-api-key
"""

